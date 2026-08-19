"""Azure Marketplace billing & token-metering gates (02-maf-billing-gates.mdc).

All MAF agent node executions MUST pass through this 4-stage sequential
gate before invoking any Azure OpenAI model:

    1. assert_pilot_feature_access  -- is this agent allowed on this plan?
    2. check_pilot_project_limit    -- has the tenant hit its project cap?
    3. check_pilot_compute_cap      -- TOCTOU-safe spend-vs-allowance check + reservation
    4. check_credit_balance         -- can the tenant still transact at all?

Each stage raises a `BillingGateError` subclass on rejection; `run_billing_gates`
runs them in order and stops at the first failure. Setting the environment
variable `SWARM_ALL_AGENTS_ENABLED` (to any of "1"/"true"/"yes"/"on") bypasses
every stage, for internal test environments only.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import AgentTier, PlanTier, Project, SwarmStatus, Tenant

# =============================================================================
# Env override (02-maf-billing-gates.mdc, Section 2)
# =============================================================================

_TRUTHY = {"1", "true", "yes", "on"}


def all_agents_enabled() -> bool:
    """Mirrors `process.env.SWARM_ALL_AGENTS_ENABLED` from the pre-migration
    GIABO pipeline (01-maf-core-orchestrator.mdc). When set, every billing
    gate is bypassed -- internal test environments only, never production
    tenants.
    """
    return os.environ.get("SWARM_ALL_AGENTS_ENABLED", "").strip().lower() in _TRUTHY


# =============================================================================
# Agent feature-tier registry
#
# Source of truth for which agents may run for which plan tier. Populated
# directly from the Scope/tier annotations in 03-maf-writeback-agents.mdc;
# read-only agents (04-maf-readonly-agents.mdc) carry no tier restriction in
# that rule file, so they default to PILOT_ALLOWED. Cron agents
# (05-maf-cron-governance.mdc) never reach the delta-dispatch Router at all
# (see `core.state.DELTA_DISPATCH_EXCLUDED_AGENTS`) but still pass through
# these gates when the scheduler invokes them directly.
# =============================================================================


class FeatureTier(str, Enum):
    PILOT_ALLOWED = "pilot_allowed"
    STANDARD_TIER = "standard_tier"


@dataclass(frozen=True)
class AgentSpec:
    agent_tier: AgentTier
    feature_tier: FeatureTier
    scope: tuple[str, ...] = ()
    temperature: float = 0.20


AGENT_REGISTRY: dict[str, AgentSpec] = {
    # --- Write-back agents (03-maf-writeback-agents.mdc) ---
    "prince2_exception_master": AgentSpec(AgentTier.WRITEBACK, FeatureTier.PILOT_ALLOWED, ("decisions",), 0.10),
    "raid_compliance_auto_chaser": AgentSpec(
        AgentTier.WRITEBACK, FeatureTier.PILOT_ALLOWED, ("assumptionsIssues", "actions"), 0.30
    ),
    "risk_radar_monitor": AgentSpec(AgentTier.WRITEBACK, FeatureTier.STANDARD_TIER, ("risks", "dependencies"), 0.20),
    "change_control_clerk": AgentSpec(AgentTier.WRITEBACK, FeatureTier.PILOT_ALLOWED, ("changes",), 0.15),
    "lessons_learned_curator": AgentSpec(AgentTier.WRITEBACK, FeatureTier.PILOT_ALLOWED, ("lessons",), 0.30),
    "dependency_map_maintainer": AgentSpec(AgentTier.WRITEBACK, FeatureTier.PILOT_ALLOWED, ("dependencies",), 0.15),
    "scrum_master_liaison": AgentSpec(AgentTier.WRITEBACK, FeatureTier.STANDARD_TIER, ("sprints",), 0.15),
    # --- Read-only agents (04-maf-readonly-agents.mdc) ---
    "forensic_alignment_engine": AgentSpec(AgentTier.READONLY, FeatureTier.PILOT_ALLOWED, temperature=0.10),
    "earned_value_analyst": AgentSpec(AgentTier.READONLY, FeatureTier.PILOT_ALLOWED, temperature=0.10),
    "governance_synthesizer": AgentSpec(AgentTier.READONLY, FeatureTier.PILOT_ALLOWED, temperature=0.20),
    "stage_gate_guardian": AgentSpec(AgentTier.READONLY, FeatureTier.PILOT_ALLOWED, temperature=0.10),
    "project_health_reporter": AgentSpec(AgentTier.READONLY, FeatureTier.PILOT_ALLOWED, temperature=0.20),
    # --- Cron / governance sweeps (05-maf-cron-governance.mdc) ---
    # Excluded from delta dispatch, but still gated when the scheduler fires them.
    "governance_auditor": AgentSpec(AgentTier.CRON, FeatureTier.PILOT_ALLOWED),
    "eom_financial_checkpoint": AgentSpec(AgentTier.CRON, FeatureTier.PILOT_ALLOWED),
    "sprint_boundary_watchdog": AgentSpec(AgentTier.CRON, FeatureTier.PILOT_ALLOWED),
}

# free_trial pilots are capped at a single project; paid_monthly tenants get
# a generous multi-project ceiling to protect against runaway provisioning.
PILOT_PROJECT_LIMITS: dict[PlanTier, int] = {
    PlanTier.FREE_TRIAL: 1,
    PlanTier.PAID_MONTHLY: 25,
}

# $3.00 billed per $1.00 raw spend beyond the $350 monthly allowance (Section 1).
OVERAGE_MULTIPLIER = Decimal("3.00")


# =============================================================================
# Exceptions
# =============================================================================


class BillingGateError(Exception):
    """Base class for all billing-gate rejections.

    `halt=True` means the tenant's `swarm_status` has been (or should be)
    flipped to a terminal state -- callers must stop dispatching to this
    tenant entirely, not just retry this one node.
    """

    def __init__(
        self,
        message: str,
        *,
        gate: str,
        halt: bool = False,
        new_swarm_status: Optional[SwarmStatus] = None,
    ) -> None:
        super().__init__(message)
        self.gate = gate
        self.halt = halt
        self.new_swarm_status = new_swarm_status


class PilotFeatureAccessDeniedError(BillingGateError):
    pass


class PilotProjectLimitExceededError(BillingGateError):
    pass


class ComputeCapExceededError(BillingGateError):
    pass


class InsufficientCreditBalanceError(BillingGateError):
    pass


@dataclass
class BillingGateResult:
    """Outcome of a successful `run_billing_gates` call."""

    bypassed: bool = False
    is_overage: bool = False
    overage_multiplier: Decimal = Decimal("1.00")
    reserved_cost_usd: Decimal = Decimal("0")


# =============================================================================
# Stage 1: assertPilotFeatureAccess
# =============================================================================


def assert_pilot_feature_access(tenant: Tenant, agent_key: str) -> AgentSpec:
    """Reject execution if `agent_key` is Standard Tier and the tenant is
    still on `free_trial` (Pilot Allowed agents run on both plans).
    """
    spec = AGENT_REGISTRY.get(agent_key)
    if spec is None:
        # Fail closed: an agent absent from the registry has no known scope
        # or tier and must not be allowed to spend tokens.
        raise PilotFeatureAccessDeniedError(
            f"Unknown agent_key '{agent_key}' is not registered in AGENT_REGISTRY.",
            gate="assertPilotFeatureAccess",
        )
    if spec.feature_tier is FeatureTier.STANDARD_TIER and tenant.plan_tier is PlanTier.FREE_TRIAL:
        raise PilotFeatureAccessDeniedError(
            f"Agent '{agent_key}' is Standard Tier and requires plan_tier=paid_monthly "
            f"(tenant {tenant.id} is on free_trial).",
            gate="assertPilotFeatureAccess",
        )
    return spec


# =============================================================================
# Stage 2: checkPilotProjectLimit
# =============================================================================


def check_pilot_project_limit(session: Session, tenant: Tenant) -> None:
    """Reject execution if onboarding another/this project would exceed the
    plan's project ceiling."""
    limit = PILOT_PROJECT_LIMITS.get(tenant.plan_tier, PILOT_PROJECT_LIMITS[PlanTier.FREE_TRIAL])
    project_count = session.execute(
        select(func.count()).select_from(Project).where(Project.tenant_id == tenant.id)
    ).scalar_one()
    if project_count > limit:
        raise PilotProjectLimitExceededError(
            f"Tenant {tenant.id} has {project_count} project(s), above the "
            f"{tenant.plan_tier.value} plan limit of {limit}.",
            gate="checkPilotProjectLimit",
        )


# =============================================================================
# Stage 3: checkPilotComputeCap (TOCTOU-safe)
# =============================================================================


def check_pilot_compute_cap(session: Session, tenant_id: uuid.UUID, estimated_cost_usd: Decimal) -> BillingGateResult:
    """Atomically check-and-reserve `estimated_cost_usd` against the tenant's allowance.

    Locks the tenant row with ``SELECT ... FOR UPDATE`` (Section 2: "Atomic
    cost accumulation in PostgreSQL using SELECT FOR UPDATE") so two
    concurrent agent-node executions can never both read a stale
    `raw_token_spend_usd`, each independently decide they fit under the cap,
    and jointly overshoot it -- the classic Time-Of-Check-to-Time-Of-Use race.

    The estimated cost is added to `raw_token_spend_usd` *before* the row
    lock is released (i.e. before the caller commits), which reserves the
    budget atomically with the check. Callers MUST commit (or roll back)
    promptly after this call to release the lock, and should call
    `reconcile_actual_cost` once the real token usage is known so the
    reservation converges on the true spend.
    """
    tenant = session.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update()).scalar_one()

    if tenant.plan_tier is PlanTier.FREE_TRIAL:
        today = date.today()
        trial_expired_by_date = tenant.trial_end_date is not None and today > tenant.trial_end_date
        trial_expired_by_spend = (tenant.raw_token_spend_usd + estimated_cost_usd) > tenant.monthly_token_allowance_usd

        if trial_expired_by_date or trial_expired_by_spend:
            tenant.swarm_status = SwarmStatus.TRIAL_EXPIRED
            session.flush()
            reason = "14-day trial window elapsed" if trial_expired_by_date else "$20.00 token allowance exceeded"
            raise ComputeCapExceededError(
                f"Tenant {tenant_id} free_trial hard halt: {reason}.",
                gate="checkPilotComputeCap",
                halt=True,
                new_swarm_status=SwarmStatus.TRIAL_EXPIRED,
            )

        tenant.raw_token_spend_usd += estimated_cost_usd
        session.flush()
        return BillingGateResult(reserved_cost_usd=estimated_cost_usd)

    # paid_monthly never hard-halts on spend; it flips into 3x overage once
    # the $350 monthly allowance is exceeded.
    projected_spend = tenant.raw_token_spend_usd + estimated_cost_usd
    is_overage = projected_spend > tenant.monthly_token_allowance_usd
    overage_multiplier = OVERAGE_MULTIPLIER if is_overage else Decimal("1.00")

    tenant.raw_token_spend_usd = projected_spend
    if is_overage:
        overage_amount = min(estimated_cost_usd, projected_spend - tenant.monthly_token_allowance_usd)
        tenant.billed_overage_usd += overage_amount * OVERAGE_MULTIPLIER
    session.flush()

    return BillingGateResult(
        is_overage=is_overage,
        overage_multiplier=overage_multiplier,
        reserved_cost_usd=estimated_cost_usd,
    )


def reconcile_actual_cost(
    session: Session,
    tenant_id: uuid.UUID,
    estimated_cost_usd: Decimal,
    actual_cost_usd: Decimal,
) -> None:
    """Correct the reservation made by `check_pilot_compute_cap` once the
    real token usage (and thus real cost) of the completed LLM call is
    known. Also lock-protected so it composes safely with concurrent gate
    checks on the same tenant.
    """
    delta = actual_cost_usd - estimated_cost_usd
    if delta == 0:
        return
    tenant = session.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update()).scalar_one()
    tenant.raw_token_spend_usd += delta
    session.flush()


# =============================================================================
# Stage 4: checkCreditBalance
# =============================================================================

_HALTED_STATUSES = {SwarmStatus.TRIAL_EXPIRED, SwarmStatus.SUSPENDED, SwarmStatus.CANCELLED}


def check_credit_balance(tenant: Tenant) -> None:
    """Final circuit breaker: even if compute-cap accounting passed, a tenant
    whose `swarm_status` has been halted (trial expired, payment suspended,
    subscription cancelled) must never reach an Azure OpenAI call.
    """
    if tenant.swarm_status in _HALTED_STATUSES:
        raise InsufficientCreditBalanceError(
            f"Tenant {tenant.id} swarm_status='{tenant.swarm_status.value}' blocks execution.",
            gate="checkCreditBalance",
            halt=True,
        )


# =============================================================================
# Orchestration entrypoint
# =============================================================================


def run_billing_gates(
    session: Session,
    tenant_id: uuid.UUID,
    agent_key: str,
    estimated_cost_usd: Decimal,
) -> BillingGateResult:
    """Run all 4 gates in sequence for one agent-node execution.

    Raises the first `BillingGateError` encountered. On success, the caller
    is responsible for committing `session` promptly (to release the
    `checkPilotComputeCap` row lock) before invoking the Azure OpenAI model.
    """
    if all_agents_enabled():
        return BillingGateResult(bypassed=True)

    tenant = session.execute(select(Tenant).where(Tenant.id == tenant_id)).scalar_one()

    # Stage 1
    assert_pilot_feature_access(tenant, agent_key)
    # Stage 2
    check_pilot_project_limit(session, tenant)
    # Stage 3 (re-selects + row-locks `tenant` internally; same identity-mapped
    # object, so mutations below are visible on `tenant` without a re-fetch)
    result = check_pilot_compute_cap(session, tenant_id, estimated_cost_usd)
    # Stage 4
    check_credit_balance(tenant)

    return result
