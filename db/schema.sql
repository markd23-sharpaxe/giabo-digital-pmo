-- =============================================================================
-- Digital PMO Agent Swarm -- PostgreSQL Schema
--
-- Covers:
--   * Azure Marketplace tenant/billing state (see 02-maf-billing-gates.mdc)
--   * Project baselines & lifecycle (see 07-maf-digital-pmo-sop.mdc)
--   * RAID / governance artifact log with deterministic idempotent keys
--     (see 03-maf-writeback-agents.mdc, 05-maf-cron-governance.mdc)
--   * SharePoint delta document cache (dedupe by content hash)
--   * Agent execution + token/metering audit trail
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

-- -----------------------------------------------------------------------------
-- Shared trigger: keep updated_at current on every row mutation.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

-- Azure Marketplace plan tiers (02-maf-billing-gates.mdc, Section 1).
CREATE TYPE plan_tier_enum AS ENUM (
    'free_trial',
    'paid_monthly'
);

-- Swarm execution state driven by the billing gate. 'trial_expired' is the
-- hard-halt state raised when a free_trial tenant exceeds its $20 allowance.
CREATE TYPE swarm_status_enum AS ENUM (
    'provisioning',
    'active',
    'trial_expired',
    'suspended',
    'cancelled'
);

-- Project lifecycle branch (07-maf-digital-pmo-sop.mdc, Section 1):
-- 'new' -> Initiation Phase (cold start ingestion), 'initiated' -> Steady-State.
CREATE TYPE project_status_enum AS ENUM (
    'new',
    'initiated'
);

-- The 9 RAID(+SDCL) artifact families (03-maf-writeback-agents.mdc).
CREATE TYPE artifact_type_enum AS ENUM (
    'risk',
    'action',
    'issue',
    'assumption',
    'dependency',
    'sprint',
    'decision',
    'change',
    'lesson'
);

-- Which write-back/read-only/cron tier produced an agent_executions row
-- (03/04/05-maf-*.mdc).
CREATE TYPE agent_tier_enum AS ENUM (
    'readonly',
    'writeback',
    'cron'
);

-- What caused the agent node to fire (01-maf-core-orchestrator.mdc routing,
-- 05-maf-cron-governance.mdc deterministic sweeps, 06-maf-teams... interaction modes).
CREATE TYPE trigger_type_enum AS ENUM (
    'delta_dispatch',
    'cron_sweep',
    'teams_interaction',
    'manual'
);

-- Outcome of an agent node execution, including the schema self-correction
-- loop limit (06-maf-teams-interface-guardrails.mdc, Token Loop Limit = 3).
CREATE TYPE execution_status_enum AS ENUM (
    'in_progress',
    'success',
    'failed',
    'schema_retry_exhausted',
    'circuit_broken'
);

-- =============================================================================
-- 1. TENANTS
-- Azure subscription mapping, plan tier, 14-day trial window, raw spend.
-- =============================================================================
CREATE TABLE tenants (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Azure Marketplace SaaS subscription mapping.
    azure_subscription_id       UUID NOT NULL UNIQUE,
    azure_customer_tenant_id    UUID NOT NULL,
    azure_plan_id               TEXT,
    organization_name          TEXT NOT NULL,

    plan_tier                  plan_tier_enum NOT NULL DEFAULT 'free_trial',
    swarm_status               swarm_status_enum NOT NULL DEFAULT 'provisioning',

    -- 14-day trial window. trial_end_date is derived so callers never drift
    -- from the contractual 14-day allowance in 02-maf-billing-gates.mdc.
    trial_start_date           DATE,
    trial_end_date             DATE GENERATED ALWAYS AS (trial_start_date + 14) STORED,

    -- Token allowance is fixed per plan tier: $20 (trial) / $350 (paid monthly).
    monthly_token_allowance_usd NUMERIC(10, 2) GENERATED ALWAYS AS (
        CASE WHEN plan_tier = 'paid_monthly' THEN 350.00 ELSE 20.00 END
    ) STORED,

    -- Raw (pre-markup) accumulated token spend for the current period.
    -- MUST be mutated via `SELECT ... FOR UPDATE` on this row (billing gate
    -- Section 2: "Atomic cost accumulation in PostgreSQL using SELECT FOR UPDATE").
    raw_token_spend_usd         NUMERIC(12, 4) NOT NULL DEFAULT 0,
    billed_overage_usd          NUMERIC(12, 4) NOT NULL DEFAULT 0,
    current_billing_period_start DATE NOT NULL DEFAULT date_trunc('month', now())::date,

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_trial_dates_present CHECK (
        plan_tier <> 'free_trial' OR trial_start_date IS NOT NULL
    ),
    CONSTRAINT chk_raw_spend_nonnegative CHECK (raw_token_spend_usd >= 0)
);

COMMENT ON TABLE tenants IS 'One row per Azure Marketplace SaaS subscription / customer tenant.';
COMMENT ON COLUMN tenants.raw_token_spend_usd IS 'Atomically accumulated raw token spend for the current trial/billing period; update under SELECT FOR UPDATE.';
COMMENT ON COLUMN tenants.swarm_status IS 'trial_expired = hard halt per billing gate when free_trial allowance is exceeded.';

CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_tenants_swarm_status ON tenants (swarm_status);

-- =============================================================================
-- 2. PROJECTS
-- Metadata, baselines (Aims/Goals/Objectives/Budget/Dates/Sponsor/PM),
-- lifecycle status, and EOM checkpoint day.
-- =============================================================================
CREATE TABLE projects (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                   UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,

    name                        TEXT NOT NULL,
    sharepoint_site_id           TEXT,
    sharepoint_site_url          TEXT,

    status                      project_status_enum NOT NULL DEFAULT 'new',

    -- Golden Thread baseline (07-maf-digital-pmo-sop.mdc: "Golden Thread
    -- alignment check"): Aims -> Goals -> Objectives must trace to scope.
    baseline_aims                TEXT,
    baseline_goals               JSONB NOT NULL DEFAULT '[]'::jsonb,
    baseline_objectives          JSONB NOT NULL DEFAULT '[]'::jsonb,
    baseline_budget              NUMERIC(14, 2),
    baseline_start_date          DATE,
    baseline_end_date            DATE,

    sponsor_name                 TEXT,
    sponsor_entra_id             UUID,
    project_manager_name         TEXT,
    project_manager_entra_id     UUID,

    -- Calendar day-of-month (1-31) of the current cycle's "last Friday of the
    -- month" EOM Financial Checkpoint (05-maf-cron-governance.mdc). Recomputed
    -- monthly by the governance sweep.
    eom_checkpoint_day           SMALLINT CHECK (eom_checkpoint_day BETWEEN 1 AND 31),

    golden_thread_last_verified_at TIMESTAMPTZ,

    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_projects_tenant_site UNIQUE (tenant_id, sharepoint_site_id)
);

COMMENT ON TABLE projects IS 'Project baselines and lifecycle state, ingested from a SharePoint site.';
COMMENT ON COLUMN projects.status IS 'new = Initiation Phase (cold start); initiated = Steady-State Monitoring.';
COMMENT ON COLUMN projects.eom_checkpoint_day IS 'Day-of-month of this cycle''s last-Friday EOM Financial Checkpoint.';

CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_projects_tenant_id ON projects (tenant_id);
CREATE INDEX idx_projects_status ON projects (status);

-- =============================================================================
-- 3. PMO_ARTIFACTS
-- Structured RAID logs (Risks, Actions, Issues, Assumptions, Dependencies,
-- Sprints, Decisions, Changes, Lessons) with deterministic primary keys.
-- =============================================================================
CREATE TABLE pmo_artifacts (
    -- Deterministic, application-generated key, e.g.
    -- 'ACTION-EOM-<hash>-2026-08' or 'ACTION-SPRINT-OVERDUE-<hash>'
    -- (05-maf-cron-governance.mdc). Deterministic keys make writeback
    -- idempotent via ON CONFLICT (id) DO NOTHING/UPDATE.
    id                          TEXT PRIMARY KEY,

    project_id                  UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    -- Denormalized for tenant-scoped queries/billing joins without a projects join.
    tenant_id                   UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,

    artifact_type                artifact_type_enum NOT NULL,
    title                        TEXT NOT NULL,
    description                  TEXT,

    -- Deliberately TEXT (not ENUM): status vocab differs per artifact_type
    -- (e.g. risk: open/mitigated/closed; sprint: planned/active/completed).
    status                       TEXT NOT NULL DEFAULT 'open',

    owner_entra_id               UUID,
    -- Which specialist agent (writeback/readonly/cron) authored this artifact,
    -- per the Scope column in 03-maf-writeback-agents.mdc.
    source_agent_key             TEXT NOT NULL,

    severity                     TEXT,
    raised_date                  DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date                     DATE,
    closed_at                    TIMESTAMPTZ,

    -- Optional cross-link, e.g. an Action raised against a Risk, or a Change
    -- superseding a prior Decision.
    related_artifact_id          TEXT REFERENCES pmo_artifacts (id) ON DELETE SET NULL,

    -- Type-specific structured body (e.g. RAID scoring, sprint dates, CR impact).
    payload                      JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE pmo_artifacts IS 'Unified RAID + Sprints/Decisions/Changes/Lessons artifact log with deterministic idempotent keys.';
COMMENT ON COLUMN pmo_artifacts.id IS 'Deterministic hash-based key generated by the producing agent for idempotent upserts.';

CREATE TRIGGER trg_pmo_artifacts_updated_at
    BEFORE UPDATE ON pmo_artifacts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_pmo_artifacts_project_type_status ON pmo_artifacts (project_id, artifact_type, status);
CREATE INDEX idx_pmo_artifacts_tenant_id ON pmo_artifacts (tenant_id);
CREATE INDEX idx_pmo_artifacts_owner_entra_id ON pmo_artifacts (owner_entra_id);
CREATE INDEX idx_pmo_artifacts_due_date ON pmo_artifacts (due_date) WHERE due_date IS NOT NULL;

-- =============================================================================
-- 4. DOCUMENT_CACHE
-- SHA-256 hashed SharePoint delta cache to prevent redundant parsing.
-- =============================================================================
CREATE TABLE document_cache (
    id                          BIGSERIAL PRIMARY KEY,
    project_id                   UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,

    -- SHA-256 hex digest of the extracted raw content. Two SharePoint items
    -- (or two delta revisions of the same item) that hash identically short-
    -- circuit re-parsing.
    content_hash                 CHAR(64) NOT NULL,

    sharepoint_drive_id           TEXT,
    sharepoint_item_id            TEXT NOT NULL,
    item_path                    TEXT,
    -- SharePoint delta query token captured alongside this cache entry, to
    -- resume Steady-State delta ingestion (07-maf-digital-pmo-sop.mdc, Section 1).
    delta_token                   TEXT,
    source_type                  TEXT NOT NULL DEFAULT 'document',

    raw_content                  TEXT,
    extracted_json                JSONB,

    sharepoint_last_modified_at    TIMESTAMPTZ,
    first_seen_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One live cache row per SharePoint item per project; re-caching the same
    -- item updates this row rather than inserting a duplicate.
    CONSTRAINT uq_document_cache_project_item UNIQUE (project_id, sharepoint_item_id)
);

COMMENT ON TABLE document_cache IS 'Content-addressed cache of extracted SharePoint document content, keyed by SHA-256 hash, to avoid redundant re-parsing on delta sync.';

CREATE TRIGGER trg_document_cache_updated_at
    BEFORE UPDATE ON document_cache
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_document_cache_content_hash ON document_cache (content_hash);
CREATE INDEX idx_document_cache_project_id ON document_cache (project_id);

-- =============================================================================
-- 5. AGENT_EXECUTIONS
-- Comprehensive audit log of every agent node invocation and its output.
-- =============================================================================
CREATE TABLE agent_executions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id                    UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    -- Nullable: tenant-wide governance sweeps are not scoped to one project.
    project_id                   UUID REFERENCES projects (id) ON DELETE CASCADE,

    agent_key                    TEXT NOT NULL,
    agent_tier                   agent_tier_enum NOT NULL,
    trigger_type                 trigger_type_enum NOT NULL,

    input_snapshot                JSONB,
    output                       JSONB,

    status                       execution_status_enum NOT NULL DEFAULT 'in_progress',
    -- Ties to the Token Loop Limit (06-maf-teams-interface-guardrails.mdc):
    -- max 3 schema self-correction attempts before hard fail.
    retry_count                  SMALLINT NOT NULL DEFAULT 0 CHECK (retry_count BETWEEN 0 AND 3),
    error_message                 TEXT,

    model_deployment              TEXT,

    started_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at                  TIMESTAMPTZ,
    duration_ms                   INTEGER,

    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE agent_executions IS 'Audit trail of every MAF agent node invocation: which agent, why it fired, and what it produced.';

CREATE INDEX idx_agent_executions_tenant_id ON agent_executions (tenant_id);
CREATE INDEX idx_agent_executions_project_id ON agent_executions (project_id);
CREATE INDEX idx_agent_executions_agent_key ON agent_executions (agent_key);
CREATE INDEX idx_agent_executions_status ON agent_executions (status);

-- =============================================================================
-- 6. TOKEN_LEDGER
-- Raw token usage and Azure Marketplace Metering emission audit trail.
-- =============================================================================
CREATE TABLE token_ledger (
    id                          BIGSERIAL PRIMARY KEY,

    tenant_id                    UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    agent_execution_id            UUID REFERENCES agent_executions (id) ON DELETE SET NULL,

    prompt_tokens                 INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens             INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    total_tokens                  INTEGER GENERATED ALWAYS AS (prompt_tokens + completion_tokens) STORED,

    raw_cost_usd                  NUMERIC(12, 6) NOT NULL CHECK (raw_cost_usd >= 0),
    -- 3x overage multiplier applied once a paid_monthly tenant's raw spend
    -- exceeds the $350 monthly allowance (02-maf-billing-gates.mdc, Section 1).
    overage_multiplier             NUMERIC(4, 2) NOT NULL DEFAULT 1.00 CHECK (overage_multiplier >= 1.00),
    billable_cost_usd              NUMERIC(12, 6) GENERATED ALWAYS AS (raw_cost_usd * overage_multiplier) STORED,
    is_overage                    BOOLEAN NOT NULL DEFAULT FALSE,

    azure_metering_emitted          BOOLEAN NOT NULL DEFAULT FALSE,
    azure_metering_emission_id       TEXT,
    azure_metering_emitted_at        TIMESTAMPTZ,

    billing_period                 DATE NOT NULL DEFAULT date_trunc('month', now())::date,

    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE token_ledger IS 'Per-call raw token usage, overage-adjusted billable cost, and Azure Marketplace Metering emission status.';

CREATE INDEX idx_token_ledger_tenant_id ON token_ledger (tenant_id);
CREATE INDEX idx_token_ledger_agent_execution_id ON token_ledger (agent_execution_id);
CREATE INDEX idx_token_ledger_billing_period ON token_ledger (tenant_id, billing_period);
CREATE INDEX idx_token_ledger_unmetered ON token_ledger (tenant_id) WHERE azure_metering_emitted = FALSE;

-- =============================================================================
-- 7. TASKS
-- Phase 7: Real Database Integration. First-class task/schedule entity backing
-- the Dynamic Chasing Engine (08-maf-dynamic-chasing-persona.mdc) and the PMP
-- Worker's progress writeback -- distinct from the RAID log in pmo_artifacts,
-- which has no 'task' artifact_type.
-- =============================================================================
CREATE TABLE tasks (
    -- Business key assigned by whatever ingests the task (e.g. 'TSK-001'),
    -- not a generated UUID -- keeps a single ID space with the strings the
    -- LLM workers already extract as `task_id` in TaskProgressPayload /
    -- BlockerPayload.
    id                          TEXT PRIMARY KEY,

    project_id                  UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    -- Denormalized for tenant-scoped queries without a projects join, same
    -- rationale as pmo_artifacts.tenant_id.
    tenant_id                   UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,

    task_name                   TEXT NOT NULL,
    -- No Entra Graph lookup in Phase 7: assignee_name is a plain display
    -- string captured at task-creation time; assignee_entra_id is carried
    -- alongside for future Graph-backed resolution.
    assignee_name                TEXT,
    assignee_entra_id             UUID,

    -- Deliberately TEXT (not ENUM), matching pmo_artifacts.status.
    status                       TEXT NOT NULL DEFAULT 'in_progress',
    percent_complete              SMALLINT NOT NULL DEFAULT 0 CHECK (percent_complete BETWEEN 0 AND 100),
    actual_hours_spent             NUMERIC(8, 2) NOT NULL DEFAULT 0,
    is_critical_path               BOOLEAN NOT NULL DEFAULT FALSE,
    critical_path_impact           SMALLINT NOT NULL DEFAULT 1 CHECK (critical_path_impact BETWEEN 1 AND 10),
    linked_risks_severity          SMALLINT NOT NULL DEFAULT 1 CHECK (linked_risks_severity BETWEEN 1 AND 10),
    status_summary                TEXT,

    deadline                     DATE,
    -- Dynamic Chasing Engine's 24h fatigue-cooldown anchor
    -- (chasing_engine.calculate_chasing_priorities). Stamped by
    -- `db_middleware.mark_task_contacted` whenever a chase message actually
    -- goes out -- NULL means "never contacted".
    last_contact_timestamp         TIMESTAMPTZ,

    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE tasks IS 'First-class task/schedule entity: Dynamic Chasing priorities + PMP Worker progress writeback.';
COMMENT ON COLUMN tasks.last_contact_timestamp IS 'Stamped on send of a chasing check-in; drives the 24h fatigue cooldown.';

CREATE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_tasks_project_id ON tasks (project_id);
CREATE INDEX idx_tasks_tenant_id ON tasks (tenant_id);
CREATE INDEX idx_tasks_deadline ON tasks (deadline) WHERE deadline IS NOT NULL;
