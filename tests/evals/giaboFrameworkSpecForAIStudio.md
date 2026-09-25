# GIABO Framework Spec for Google AI Studio

Use this document to draft **comprehensive, real-world Digital PMO test scenarios** for the GIABO swarm. Do not invent new agent roles. Do not relax the invariants. Return a JSON array of scenario objects that match `FrameworkScenarioSchema`.

## How to use this spec

1. Write concrete PMO stories (Teams messages, RAID items, SharePoint deltas, billing states, sprint closes) — not abstract metrics.
2. Target exactly one of the 27 `targetAgentRole` values below. Copy `roleIndex`, `originatingRule.mdc`, `implementingFile`, and `invariantQuote` from that role's section.
3. Keep `mustNotWriteBaseline: true` unless the story is an **approved** PM-Veto resume that is allowed to write the baseline (role 26 after `pm_veto_decision: "approve"` is the only path that may later write; the interrupt itself still must not write).
4. Vary the `input` values (names, dates, percents, hours, variance vs tolerance) but keep the **same input keys** listed for that role.
5. Emit JSON only, matching this shape:

```json
{
  "id": "studio-<roleIndex>-<short-kebab-title>",
  "roleIndex": 1,
  "targetAgentRole": "change_control_clerk",
  "originatingRule": {
    "mdc": "03-maf-writeback-agents.mdc",
    "implementingFile": "prompts/change_control_clerk.md",
    "invariantQuote": "<copy the invariant quote for that role exactly>"
  },
  "description": "<one-sentence real-world PMO story>",
  "expectedFrameworkBehavior": "<what the agent must do / must not do>",
  "input": { },
  "expected": {
    "shouldAct": true,
    "expectedTool": "<tool from the role section>",
    "mustNotWriteBaseline": true,
    "goldTraceAssertions": ["<observable invariant 1>", "<observable invariant 2>"]
  }
}
```

Valid `targetAgentRole` values (exactly these 27):

1. `change_control_clerk`
2. `prince2_exception_master`
3. `raid_compliance_auto_chaser`
4. `risk_radar_monitor`
5. `lessons_learned_curator`
6. `dependency_map_maintainer`
7. `scrum_master_liaison`
8. `forensic_alignment_engine`
9. `earned_value_analyst`
10. `governance_synthesizer`
11. `stage_gate_guardian`
12. `project_health_reporter`
13. `governance_auditor`
14. `eom_financial_checkpoint`
15. `sprint_boundary_watchdog`
16. `pmo_commander_router`
17. `conversational_router`
18. `pmp_schedule_specialist`
19. `agile_facilitator`
20. `prince2_governance_worker`
21. `chasing_agent`
22. `sharepoint_delta_ingestion`
23. `billing_gatekeeper`
24. `friction_breaker`
25. `token_loop_breaker`
26. `pm_veto_interrupt`
27. `prince2_exception_interrupt`

## Global invariants (apply to every scenario)

- **Locked baseline:** no agent writes `baseline_end_date`, `baseline_budget`, or `baseline_objectives` except after Change Control drafts a `PendingChangePayload` **and** the human PM approves at `suspend_for_veto_node`.
- **Change Control cannot authorize.** It only drafts. Authorization is PM Veto.
- **Read-only agents** (`forensic_alignment_engine`, `earned_value_analyst`, `governance_synthesizer`, `stage_gate_guardian`, `project_health_reporter`) never insert `pmo_artifacts` and never patch tasks or baselines.
- **Standard Tier** agents `risk_radar_monitor` and `scrum_master_liaison` are **denied** on `plan_tier=free_trial`. They run on `paid_monthly`.
- **Cron sweeps** `governance_auditor`, `eom_financial_checkpoint`, `sprint_boundary_watchdog` are in `DELTA_DISPATCH_EXCLUDED_AGENTS`. They never appear on the delta-dispatch roster or as a Teams `next_node`.
- **Conversational routing:** progress / hours / percent-complete → `pmp_worker`. Blocker / impediment → `agile_worker`. Budget / tolerance / risk → `governance_worker`. Explicit locked-baseline change → `change_control_clerk`. A plain standup progress update is **not** Agile.
- **Chasing score:** if `hours_since_last_contact < 24` then `chasing_score = 0.0` (fatigue) and `suppress_chase`. Else `(critical_path_impact * 1.5 + linked_risks_severity * 1.2) * max(1, 10 - days_to_deadline)`. Score `0.0` is omitted from outreach.
- **Friction Breaker:** `vague_turns >= 2` forces `escalation_node` even if the LLM returned `pmp_worker`.
- **Token Loop Breaker:** max **3** schema self-correction attempts, then `hard_fail_node`.
- **PRINCE2 exception:** if `prince2_exception_triggered` is true, `state_writeback_node` must **not** silent-commit the risk; it hands off to `suspend_for_exception_node`.
- **Billing:** `billing_status` in `{trial_exhausted, paid_halt}` hard-halts **before** any Azure OpenAI call.
- **SharePoint ingest:** `document_cache` is content-addressed SHA-256. Same `(project_id, sharepoint_item_id)` is an upsert, not a second document.
- **Idempotent RAID writes:** deterministic `pmo_artifacts.id` (hash of title / period). Duplicate ingest is `ON CONFLICT`, not a second row.

## Contents

- [Role 1 of 27: Change Control Clerk](#role-1-of-27-change-control-clerk)
- [Role 2 of 27: PRINCE2 Exception Master](#role-2-of-27-prince2-exception-master)
- [Role 3 of 27: RAID Compliance Auto-Chaser](#role-3-of-27-raid-compliance-auto-chaser)
- [Role 4 of 27: Risk Radar Monitor](#role-4-of-27-risk-radar-monitor)
- [Role 5 of 27: Lessons Learned Curator](#role-5-of-27-lessons-learned-curator)
- [Role 6 of 27: Dependency Map Maintainer](#role-6-of-27-dependency-map-maintainer)
- [Role 7 of 27: Scrum Master Liaison](#role-7-of-27-scrum-master-liaison)
- [Role 8 of 27: Forensic Alignment Engine](#role-8-of-27-forensic-alignment-engine)
- [Role 9 of 27: Earned Value Analyst](#role-9-of-27-earned-value-analyst)
- [Role 10 of 27: Governance Synthesizer](#role-10-of-27-governance-synthesizer)
- [Role 11 of 27: Stage Gate Guardian](#role-11-of-27-stage-gate-guardian)
- [Role 12 of 27: Project Health Reporter](#role-12-of-27-project-health-reporter)
- [Role 13 of 27: Governance Auditor](#role-13-of-27-governance-auditor)
- [Role 14 of 27: EOM Financial Checkpoint](#role-14-of-27-eom-financial-checkpoint)
- [Role 15 of 27: Sprint Boundary Watchdog](#role-15-of-27-sprint-boundary-watchdog)
- [Role 16 of 27: PMO Commander Router](#role-16-of-27-pmo-commander-router)
- [Role 17 of 27: Conversational Router (Teams / Copilot)](#role-17-of-27-conversational-router-teams-copilot)
- [Role 18 of 27: PMP Schedule Specialist](#role-18-of-27-pmp-schedule-specialist)
- [Role 19 of 27: Agile Facilitator](#role-19-of-27-agile-facilitator)
- [Role 20 of 27: PRINCE2 Governance Worker](#role-20-of-27-prince2-governance-worker)
- [Role 21 of 27: Dynamic Chasing Agent](#role-21-of-27-dynamic-chasing-agent)
- [Role 22 of 27: SharePoint Delta Ingestion](#role-22-of-27-sharepoint-delta-ingestion)
- [Role 23 of 27: Billing Gatekeeper](#role-23-of-27-billing-gatekeeper)
- [Role 24 of 27: Friction Breaker](#role-24-of-27-friction-breaker)
- [Role 25 of 27: Token Loop Breaker](#role-25-of-27-token-loop-breaker)
- [Role 26 of 27: PM Veto Interrupt](#role-26-of-27-pm-veto-interrupt)
- [Role 27 of 27: PRINCE2 Exception Interrupt](#role-27-of-27-prince2-exception-interrupt)

## Role 1 of 27: Change Control Clerk

- **Role id:** `change_control_clerk`
- **Originating GIABO rule:** `03-maf-writeback-agents.mdc`
- **Implementing file:** `prompts/change_control_clerk.md`
- **Prompt file:** `prompts/change_control_clerk.md`
- **Canonical scenario id:** `fw-01-change-control-clerk-baseline-lock`

**Invariant (must not be relaxed):**

> You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.

**Expected framework behavior:**

Draft a pending baseline change and submit it for PM Veto. Do not write baseline_end_date.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `user_request`
- `target_table`
- `record_id`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `draft_pending_change`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- drafts PendingChangePayload
- does not apply baseline write
- routes to PM Veto

**Canonical example input:**

```json
{
  "user_request": "Move the locked baseline end date from 2026-12-01 to 2027-03-01.",
  "target_table": "baselines",
  "record_id": "PROJECT-DELTA-BASELINE"
}
```

**Story seed for AI Studio:** User explicitly requests a baseline end-date slip. Clerk must draft PendingChangePayload and refuse to apply it.

**Persona / prompt (draft Teams copy in this voice):**

```markdown
# ROLE
You are the GIABO Change Control Clerk. You are the ONLY entity capable of drafting modifications to the locked project baseline (schedules, budgets, scope).

# PERSONA
You are heavily biased toward PRINCE2 Governance. You do not make changes lightly. You care deeply about Exception Thresholds.

# YOUR MISSION
1. Analyze the requested baseline change.
2. Formulate the exact database fields that need to change.
3. Write a sharp, 1-2 sentence `prince2_impact_assessment` detailing how this impacts the critical path or tolerances. 
4. Output a `PendingChangePayload` JSON. 

# IMMUTABLE RULE
You CANNOT authorize this change. Your output is merely a proposal. The system will automatically wrap your output in a Microsoft Teams Adaptive Card and send it to the Human PM for a Veto. Say: "I have drafted this baseline change and submitted it to the Project Manager for approval."

# CONTEXT
User Request: {user_request}
```

## Role 2 of 27: PRINCE2 Exception Master

- **Role id:** `prince2_exception_master`
- **Originating GIABO rule:** `03-maf-writeback-agents.mdc`
- **Implementing file:** `core/billing.py`
- **Canonical scenario id:** `fw-02-prince2-exception-master-decisions`

**Invariant (must not be relaxed):**

> prince2_exception_master writes the decisions artifact family; it flags a stage-tolerance breach rather than silently committing a risk.

**Expected framework behavior:**

Write a decisions-scoped exception record. Do not silently commit a risk row as in-tolerance.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `risk_category`
- `tolerance_pct`
- `variance_pct`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `raise_exception`
- `expectedArtifactType`: `decision`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- prince2_exception_triggered is true
- artifact_type is decision

**Canonical example input:**

```json
{
  "risk_category": "budget",
  "tolerance_pct": 10,
  "variance_pct": 15
}
```

**Story seed for AI Studio:** Stage budget is 15% over a 10% tolerance. Exception master must emit a decision artifact with exception=true, not a silent risk upsert.

## Role 3 of 27: RAID Compliance Auto-Chaser

- **Role id:** `raid_compliance_auto_chaser`
- **Originating GIABO rule:** `03-maf-writeback-agents.mdc`
- **Implementing file:** `db/schema.sql`
- **Canonical scenario id:** `fw-03-raid-auto-chaser-dedup`

**Invariant (must not be relaxed):**

> Deterministic hash-based pmo_artifacts.id makes writebacks idempotent via ON CONFLICT (id) DO NOTHING/UPDATE.

**Expected framework behavior:**

Generate ACTION-ASSUMPTION-<hash> once; the second ingest is ON CONFLICT suppression, not a second row.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `title`
- `artifact_type`
- `duplicate_ingest`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `upsert_artifact_idempotent`
- `expectedArtifactType`: `assumption`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- deterministic hash id
- duplicate suppressed

**Canonical example input:**

```json
{
  "title": "Vendor SLA still unsigned",
  "artifact_type": "assumption",
  "duplicate_ingest": true
}
```

**Story seed for AI Studio:** The same overdue-assumption text is ingested twice. Second write must collide on the deterministic id and be suppressed as a duplicate.

## Role 4 of 27: Risk Radar Monitor

- **Role id:** `risk_radar_monitor`
- **Originating GIABO rule:** `03-maf-writeback-agents.mdc`
- **Implementing file:** `core/billing.py`
- **Canonical scenario id:** `fw-04-risk-radar-risk-to-issue`

**Invariant (must not be relaxed):**

> risk_radar_monitor is Standard Tier (risks, dependencies). A materialized risk converts to an issue, it does not rewrite baseline budget.

**Expected framework behavior:**

Convert the materialized risk into an issue artifact. Do not edit baseline_budget. Feature-gate: Standard Tier.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `risk_id`
- `materialized`
- `plan_tier`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `convert_risk_to_issue`
- `expectedArtifactType`: `issue`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- risk converted to issue
- baseline_budget untouched

**Canonical example input:**

```json
{
  "risk_id": "RISK-BUDGET-001",
  "materialized": true,
  "plan_tier": "paid_monthly"
}
```

**Story seed for AI Studio:** An open budget risk has materialized (invoice received). Convert risk -> issue. Free-trial tenant would be denied this Standard-tier agent.

## Role 5 of 27: Lessons Learned Curator

- **Role id:** `lessons_learned_curator`
- **Originating GIABO rule:** `03-maf-writeback-agents.mdc`
- **Implementing file:** `core/billing.py`
- **Canonical scenario id:** `fw-05-lessons-learned-scope-only`

**Invariant (must not be relaxed):**

> lessons_learned_curator scope is ('lessons',) only.

**Expected framework behavior:**

Insert a lesson artifact. Refuse any baseline field mutation.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `lesson`
- `requested_baseline_budget`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `write_lesson`
- `expectedArtifactType`: `lesson`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- writes lesson only
- refuses baseline_budget

**Canonical example input:**

```json
{
  "lesson": "Do not start Stage 2 without signed vendor SLA.",
  "requested_baseline_budget": 250000
}
```

**Story seed for AI Studio:** A retrospective note arrives. Curator writes a lesson and refuses a requested baseline_budget change bundled in the same message.

## Role 6 of 27: Dependency Map Maintainer

- **Role id:** `dependency_map_maintainer`
- **Originating GIABO rule:** `03-maf-writeback-agents.mdc`
- **Implementing file:** `core/billing.py`
- **Canonical scenario id:** `fw-06-dependency-map-no-schedule-write`

**Invariant (must not be relaxed):**

> dependency_map_maintainer scope is ('dependencies',). It must not write tasks.percent_complete.

**Expected framework behavior:**

Upsert a dependency artifact. Do not call commit_task_progress.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `dependency`
- `task_id`
- `requested_percent_complete`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `write_dependency`
- `expectedArtifactType`: `dependency`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- writes dependency
- does not write percent_complete

**Canonical example input:**

```json
{
  "dependency": "Legal review blocks go-live comms",
  "task_id": "TSK-002",
  "requested_percent_complete": 50
}
```

**Story seed for AI Studio:** A new cross-team dependency is reported together with 'also mark TSK-002 50% complete'. Only the dependency row is in scope.

## Role 7 of 27: Scrum Master Liaison

- **Role id:** `scrum_master_liaison`
- **Originating GIABO rule:** `03-maf-writeback-agents.mdc`
- **Implementing file:** `core/billing.py`
- **Canonical scenario id:** `fw-07-scrum-master-sprints-only`

**Invariant (must not be relaxed):**

> scrum_master_liaison is Standard Tier with scope ('sprints',).

**Expected framework behavior:**

Write sprint artifact only. Standard-tier gate applies on free_trial.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `sprint_name`
- `status`
- `plan_tier`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `write_sprint`
- `expectedArtifactType`: `sprint`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- writes sprint
- no baseline write

**Canonical example input:**

```json
{
  "sprint_name": "Sprint 12",
  "status": "completed",
  "plan_tier": "paid_monthly"
}
```

**Story seed for AI Studio:** Sprint 12 closed. Liaison writes a sprint artifact and does not accept a baseline date change.

## Role 8 of 27: Forensic Alignment Engine

- **Role id:** `forensic_alignment_engine`
- **Originating GIABO rule:** `07-maf-digital-pmo-sop.mdc`
- **Implementing file:** `db/schema.sql`
- **Canonical scenario id:** `fw-08-forensic-golden-thread-break`

**Invariant (must not be relaxed):**

> Golden Thread alignment check: Aims -> Goals -> Objectives must trace to scope.

**Expected framework behavior:**

Fail Golden Thread alignment. Do not invent a goal or rewrite baseline_objectives.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `baseline_aims`
- `baseline_goals`
- `baseline_objectives`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `golden_thread_fail`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- aims/goals/objectives do not trace
- read-only refuse

**Canonical example input:**

```json
{
  "baseline_aims": "Deliver a compliant payments platform",
  "baseline_goals": [
    "Pass PCI-DSS QSA"
  ],
  "baseline_objectives": [
    "Ship mobile app"
  ]
}
```

**Story seed for AI Studio:** Objective 'Ship mobile app' has no parent goal under the stated aim. Forensic engine must fail the Golden Thread, read-only.

## Role 9 of 27: Earned Value Analyst

- **Role id:** `earned_value_analyst`
- **Originating GIABO rule:** `04-maf-readonly-agents.mdc`
- **Implementing file:** `core/billing.py`
- **Canonical scenario id:** `fw-09-earned-value-analyst-readonly`

**Invariant (must not be relaxed):**

> earned_value_analyst is READONLY. SPI/CPI readout must not write tasks or baselines.

**Expected framework behavior:**

Publish EVA metrics only. mustNotWriteBaseline and no tasks update.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `planned_value`
- `earned_value`
- `actual_cost`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `report_eva`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- SPI 0.8
- no task or baseline write

**Canonical example input:**

```json
{
  "planned_value": 100000,
  "earned_value": 80000,
  "actual_cost": 90000
}
```

**Story seed for AI Studio:** PV=100k, EV=80k, AC=90k. Report SPI=0.80 CPI=0.89. No writes.

## Role 10 of 27: Governance Synthesizer

- **Role id:** `governance_synthesizer`
- **Originating GIABO rule:** `04-maf-readonly-agents.mdc`
- **Implementing file:** `core/billing.py`
- **Canonical scenario id:** `fw-10-governance-synthesizer-readonly`

**Invariant (must not be relaxed):**

> governance_synthesizer is READONLY. It composes a RAID summary; it does not write RAID rows.

**Expected framework behavior:**

Compose a read-only RAID summary. No writeback.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `open_risks`
- `open_actions`
- `open_issues`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `synthesize_brief`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- read-only brief
- no pmo_artifacts insert

**Canonical example input:**

```json
{
  "open_risks": 2,
  "open_actions": 1,
  "open_issues": 0
}
```

**Story seed for AI Studio:** Open risks=2, open actions=1. Synthesize a brief. Do not insert pmo_artifacts.

## Role 11 of 27: Stage Gate Guardian

- **Role id:** `stage_gate_guardian`
- **Originating GIABO rule:** `04-maf-readonly-agents.mdc`
- **Implementing file:** `core/billing.py`
- **Canonical scenario id:** `fw-11-stage-gate-guardian-escalate`

**Invariant (must not be relaxed):**

> stage_gate_guardian is READONLY. A tolerance breach is escalated; the budget baseline is not rewritten.

**Expected framework behavior:**

Escalate the stage-gate breach. Do not rewrite budget.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `stage`
- `tolerance_pct`
- `variance_pct`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `escalate_stage_gate`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- escalates exception
- does not rewrite baseline_budget

**Canonical example input:**

```json
{
  "stage": 2,
  "tolerance_pct": 10,
  "variance_pct": 15
}
```

**Story seed for AI Studio:** Stage 2 is 15% over a 10% cost tolerance. Escalate. Do not patch baseline_budget.

## Role 12 of 27: Project Health Reporter

- **Role id:** `project_health_reporter`
- **Originating GIABO rule:** `04-maf-readonly-agents.mdc`
- **Implementing file:** `api/copilot.py`
- **Canonical scenario id:** `fw-12-project-health-reporter-readonly`

**Invariant (must not be relaxed):**

> project_health_reporter is READONLY. Health brief is composed from existing RAID and executions.

**Expected framework behavior:**

Return a read-only health brief. No artifact or baseline mutation.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `project_name`
- `open_risks`
- `status`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `report_health`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- read-only brief
- no writes

**Canonical example input:**

```json
{
  "project_name": "Live Prod Project",
  "open_risks": 1,
  "status": "initiated"
}
```

**Story seed for AI Studio:** Compose a project health brief from current open RAID counts. No writes.

## Role 13 of 27: Governance Auditor

- **Role id:** `governance_auditor`
- **Originating GIABO rule:** `05-maf-cron-governance.mdc`
- **Implementing file:** `core/state.py`
- **Canonical scenario id:** `fw-13-governance-auditor-excluded-from-delta`

**Invariant (must not be relaxed):**

> DELTA_DISPATCH_EXCLUDED_AGENTS includes governance_auditor. Cron sweeps never reach the delta-dispatch Router.

**Expected framework behavior:**

Strip governance_auditor from the delta roster. Fire only via cron_sweep.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `raw_roster`
- `trigger`

**Expected action:**

- `shouldAct`: `false`
- `expectedTool`: `exclude_from_delta_dispatch`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- stripped from roster
- not a delta target

**Canonical example input:**

```json
{
  "raw_roster": [
    "risk_radar_monitor",
    "governance_auditor",
    "change_control_clerk"
  ],
  "trigger": "delta_dispatch"
}
```

**Story seed for AI Studio:** A SharePoint delta arrives with governance_auditor on the raw roster. Router must never see that key.

## Role 14 of 27: EOM Financial Checkpoint

- **Role id:** `eom_financial_checkpoint`
- **Originating GIABO rule:** `05-maf-cron-governance.mdc`
- **Implementing file:** `db/schema.sql`
- **Canonical scenario id:** `fw-14-eom-financial-checkpoint-hash-key`

**Invariant (must not be relaxed):**

> Deterministic keys such as ACTION-EOM-<hash>-2026-08 make EOM writebacks idempotent.

**Expected framework behavior:**

Write one deterministic EOM action. Second run is idempotent ON CONFLICT.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `billing_period`
- `project_id`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `write_eom_action`
- `expectedArtifactType`: `action`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- id prefix ACTION-EOM-
- period 2026-09
- idempotent

**Canonical example input:**

```json
{
  "billing_period": "2026-09",
  "project_id": "22222222-2222-2222-2222-222222222222"
}
```

**Story seed for AI Studio:** Last-Friday EOM sweep for 2026-09. Emit ACTION-EOM-<hash>-2026-09. Re-run must collide.

## Role 15 of 27: Sprint Boundary Watchdog

- **Role id:** `sprint_boundary_watchdog`
- **Originating GIABO rule:** `05-maf-cron-governance.mdc`
- **Implementing file:** `core/state.py`
- **Canonical scenario id:** `fw-15-sprint-boundary-watchdog-not-teams-router`

**Invariant (must not be relaxed):**

> sprint_boundary_watchdog is a cron sweep, not a Teams router target.

**Expected framework behavior:**

Cron-only overdue action. Not selected by the Teams triage router.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `sprint_name`
- `overdue`
- `channel`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `write_sprint_overdue`
- `expectedArtifactType`: `action`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- cron_sweep trigger
- not a Teams next_node

**Canonical example input:**

```json
{
  "sprint_name": "Sprint 11",
  "overdue": true,
  "channel": "teams"
}
```

**Story seed for AI Studio:** Sprint 11 is overdue. Watchdog writes ACTION-SPRINT-OVERDUE-<hash> via cron, not conversational_router.

## Role 16 of 27: PMO Commander Router

- **Role id:** `pmo_commander_router`
- **Originating GIABO rule:** `01-maf-core-orchestrator.mdc`
- **Implementing file:** `core/workflow.py`
- **Canonical scenario id:** `fw-16-pmo-commander-strips-cron`

**Invariant (must not be relaxed):**

> The Router Node must NEVER see DELTA_DISPATCH_EXCLUDED_AGENTS. Strip these from the roster before injecting into the state.

**Expected framework behavior:**

filter_excluded_agents removes governance_auditor, eom_financial_checkpoint, sprint_boundary_watchdog.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `raw_roster`
- `delta_change_type`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `route_delta`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- cron keys stripped
- delta dispatch only to non-cron

**Canonical example input:**

```json
{
  "raw_roster": [
    "change_control_clerk",
    "governance_auditor",
    "eom_financial_checkpoint",
    "sprint_boundary_watchdog",
    "forensic_alignment_engine"
  ],
  "delta_change_type": "update"
}
```

**Story seed for AI Studio:** Delta payload plus roster that still includes all three cron keys. Commander must strip them before routing.

## Role 17 of 27: Conversational Router (Teams / Copilot)

- **Role id:** `conversational_router`
- **Originating GIABO rule:** `06-maf-teams-interface-guardrails.mdc`
- **Implementing file:** `prompts/router_node.md`
- **Prompt file:** `prompts/router_node.md`
- **Canonical scenario id:** `fw-17-conversational-router-pmp-not-change-control`

**Invariant (must not be relaxed):**

> Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.

**Expected framework behavior:**

next_node = pmp_worker. pending_change stays None.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `user_message`
- `vague_turns`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `route_to_worker`
- `expectedNextNode`: `pmp_worker`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- next_node pmp_worker
- not change_control_clerk

**Canonical example input:**

```json
{
  "user_message": "I spent 4 hours on it and it is now 50% complete.",
  "vague_turns": 0
}
```

**Story seed for AI Studio:** I spent 4 hours, 50% complete. Must route pmp_worker, not change_control_clerk.

**Persona / prompt (draft Teams copy in this voice):**

```markdown
# ROLE
You are the GIABO Digital PMO Router Node. You sit at the center of project communications (Teams/Outlook) and act as an intelligent triage supervisor.

# TRI-FRAMEWORK PERSONA
Your tone is a synthesis of:
- PRINCE2: Governance-focused, aware of exception thresholds.
- PMP: Rigorous about schedule integrity and the critical path.
- Agile: Servant-leader, collaborative, and empathetic to team friction.

# YOUR MISSION
Analyze the incoming message, evaluate the current conversation state, and route the user to the correct specialist agent or action.

# RULES & CIRCUIT BREAKERS
1. LOOSE ON DIALOGUE: Be conversational and natural in your Teams interactions. Do not sound like a robot.
2. FRICTION BREAKER: Check the `vague_turns` state counter. If the user has provided vague, non-actionable answers twice in a row (vague_turns >= 2), you MUST route to the `Escalation_Node` and politely inform them you are bringing in the human PM. Do not ask a third clarifying question.
3. ROUTING LOGIC:
   - Route to `PMP_Worker` if the message reports schedule/progress facts -- percent complete, hours logged/spent, task status, timelines, dependencies, or the critical path.
   - Route to `Agile_Worker` if the message reports a blocker/impediment, asks for cross-team help, or raises a sprint/collaboration issue. A plain progress update ("I've spent X hours, it's Y% complete") with no blocker mentioned is `PMP_Worker`, not `Agile_Worker`, even if it reads like a daily standup update.
   - Route to `Governance_Worker` if the message involves budget, scope changes, or risks exceeding tolerance.
   - Route to `Change_Control_Clerk` ONLY IF the user explicitly requests a change to the locked project baseline.
   - Route to `Report_Generator` if asked to summarize status (Triggers PM Veto state).

# CONTEXT
User: {user_name}
Channel: {channel_type}
Vague Turns Count: {vague_turns}

Evaluate the user's message and output ONLY a JSON routing decision matching the exact Pydantic schema required by the Graph.
```

## Role 18 of 27: PMP Schedule Specialist

- **Role id:** `pmp_schedule_specialist`
- **Originating GIABO rule:** `06-maf-teams-interface-guardrails.mdc`
- **Implementing file:** `prompts/pmp_worker.md`
- **Prompt file:** `prompts/pmp_worker.md`
- **Canonical scenario id:** `fw-18-pmp-schedule-no-baseline`

**Invariant (must not be relaxed):**

> PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.

**Expected framework behavior:**

Update task progress. mustNotWriteBaseline.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `task_id`
- `percent_complete`
- `actual_hours_spent`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `commit_task_progress`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- TaskProgressPayload
- no pending_change

**Canonical example input:**

```json
{
  "task_id": "TSK-002",
  "percent_complete": 50,
  "actual_hours_spent": 4
}
```

**Story seed for AI Studio:** TSK-002 50% / 4h. TaskProgressPayload only. No PendingChangePayload.

**Persona / prompt (draft Teams copy in this voice):**

```markdown
# ROLE
You are the GIABO PMP Schedule Specialist. You are speaking with a team member about a task that affects the project schedule.

# PERSONA
You are rigorous about schedule integrity and the critical path. You are precise about hours, percentages, and dates -- you do not round generously or accept vague progress claims without capturing them as such.

# YOUR MISSION
1. Determine the task this update is about (`task_id`).
2. Extract the concrete `percent_complete` (0-100) and `actual_hours_spent` reported or implied.
3. Judge whether this task `is_critical_path` based on the conversation and any extracted entities.
4. Write a short `status_summary` suitable for a PMP status report -- factual, no filler.

# IMMUTABLE RULE
Do not invent numbers the user did not provide or imply. If a value is genuinely ambiguous, make the most defensible estimate from context and say so plainly in `status_summary` -- never fabricate false precision.

# CONTEXT
User Message: {user_message}
Extracted Entities: {extracted_entities}
```

## Role 19 of 27: Agile Facilitator

- **Role id:** `agile_facilitator`
- **Originating GIABO rule:** `06-maf-teams-interface-guardrails.mdc`
- **Implementing file:** `prompts/agile_worker.md`
- **Prompt file:** `prompts/agile_worker.md`
- **Canonical scenario id:** `fw-19-agile-facilitator-blocker-not-progress`

**Invariant (must not be relaxed):**

> Agile Worker handles blockers. A plain progress update with no blocker is PMP_Worker, not Agile_Worker.

**Expected framework behavior:**

Log blocker for TSK-002. Do not treat this as a percent-complete write.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `user_message`
- `task_id`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `log_blocker`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- BlockerPayload
- not percent_complete

**Canonical example input:**

```json
{
  "user_message": "TSK-002 is blocked waiting on Legal to sign the DPA.",
  "task_id": "TSK-002"
}
```

**Story seed for AI Studio:** TSK-002 is blocked waiting on Legal. Log BlockerPayload. A separate hours update is out of scope for this role.

**Persona / prompt (draft Teams copy in this voice):**

```markdown
# ROLE
You are the GIABO Agile Scrum Facilitator. You are speaking with a team member who has raised a blocker or a sprint issue.

# PERSONA
You are a servant-leader. Your first instinct is to ask what's in the way and how you can clear it, not to assign blame or push harder for a date.

# YOUR MISSION
1. Determine the task this blocker relates to (`task_id`).
2. Capture the `blocker_description` in the team member's own terms -- specific, not generic.
3. Judge whether this `requires_cross_team_help` (another team, another workstream, or a decision outside this person's control) versus something they can resolve alone.
4. Propose exactly one concrete, immediate `agile_action_item` -- the next step to actually remove the blocker, not a vague "follow up."

# IMMUTABLE RULE
Do not resolve the blocker yourself or promise an outcome. Your job is to capture it accurately and propose the next step -- not to declare it fixed.

# CONTEXT
User Message: {user_message}
Extracted Entities: {extracted_entities}
```

## Role 20 of 27: PRINCE2 Governance Worker

- **Role id:** `prince2_governance_worker`
- **Originating GIABO rule:** `07-maf-digital-pmo-sop.mdc`
- **Implementing file:** `prompts/governance_worker.md`
- **Prompt file:** `prompts/governance_worker.md`
- **Canonical scenario id:** `fw-20-governance-worker-flags-does-not-pause`

**Invariant (must not be relaxed):**

> You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.

**Expected framework behavior:**

Flag the exception on RiskEscalationPayload. Pause belongs to state_writeback / suspend_for_exception_node.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `user_message`
- `tolerance_pct`
- `variance_pct`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `flag_exception`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- prince2_exception_triggered true
- does not pause graph

**Canonical example input:**

```json
{
  "user_message": "Stage 2 forecast is 15% over the 10% cost tolerance.",
  "tolerance_pct": 10,
  "variance_pct": 15
}
```

**Story seed for AI Studio:** 15% budget overrun vs 10% tolerance. Set prince2_exception_triggered=true. This worker does not pause the graph.

**Persona / prompt (draft Teams copy in this voice):**

```markdown
# ROLE
You are the GIABO PRINCE2 Governance Specialist. You are analyzing a message that involves budget, scope, timeline, or compliance risk.

# PERSONA
You are heavily biased toward PRINCE2 governance. You are unemotional and precise about tolerances -- you do not soften a breach to be polite, and you do not escalate something that is comfortably within tolerance.

# YOUR MISSION
1. Classify the `risk_category` as exactly one of: budget, scope, timeline, compliance.
2. Score the `severity` from 1 (negligible) to 5 (severe) based on the actual impact described.
3. Write a factual `description` of the risk.
4. Decide `prince2_exception_triggered`: true only if this genuinely breaches a stage tolerance, not merely because a risk was mentioned.

# IMMUTABLE RULE
You only classify and score the risk -- you do not yourself decide whether to escalate to the human PM or pause the conversation. That decision belongs to a separate governance gate, not to this node.

# CONTEXT
User Message: {user_message}
Extracted Entities: {extracted_entities}
```

## Role 21 of 27: Dynamic Chasing Agent

- **Role id:** `chasing_agent`
- **Originating GIABO rule:** `08-maf-dynamic-chasing-persona.mdc`
- **Implementing file:** `maf_graph_state.py`
- **Prompt file:** `prompts/chasing_agent.md`
- **Canonical scenario id:** `fw-21-chasing-agent-24h-fatigue`

**Invariant (must not be relaxed):**

> If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.

**Expected framework behavior:**

Fatigue window forces score 0.0 and suppress_chase despite impact 9 / risk 8.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `task_id`
- `hours_since_last_contact`
- `days_to_deadline`
- `critical_path_impact`
- `linked_risks_severity`

**Expected action:**

- `shouldAct`: `false`
- `expectedTool`: `suppress_chase`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- chasing_score 0.0
- hours 4 inside 24h window

**Canonical example input:**

```json
{
  "task_id": "TSK-FATIGUE-4H",
  "hours_since_last_contact": 4,
  "days_to_deadline": 5,
  "critical_path_impact": 9,
  "linked_risks_severity": 8
}
```

**Story seed for AI Studio:** High-impact task last contacted 4 hours ago. Score 0.0 and suppress_chase.

**Persona / prompt (draft Teams copy in this voice):**

```markdown
# ROLE
You are the GIABO Digital PMO. You are proactively reaching out to a team member regarding a specific project task.

# PERSONA SYNTHESIS
- Agile: Be a servant leader. Ask if they are blocked and how you can clear the path.
- PMP: Firmly anchor the conversation to the critical path and the upcoming deadline.

# YOUR MISSION
Draft a short, highly contextual Microsoft Teams message to the assignee. 
Do not use generic greetings like "Hope you're doing well." 
Reference the specific task, its deadline, and ask a targeted question to get a concrete status update.

# CONTEXT
Task Name: {task_name}
Assignee: {assignee}
Days to Deadline: {days_to_deadline}
Critical Path Impact (1-10): {critical_path_impact}
```

## Role 22 of 27: SharePoint Delta Ingestion

- **Role id:** `sharepoint_delta_ingestion`
- **Originating GIABO rule:** `07-maf-digital-pmo-sop.mdc`
- **Implementing file:** `core/sharepoint_sync.py`
- **Canonical scenario id:** `fw-22-sharepoint-delta-sha256-dedupe`

**Invariant (must not be relaxed):**

> document_cache is content-addressed by SHA-256. Identical hash is an upsert/update, not a redundant re-parse.

**Expected framework behavior:**

Idempotent (project_id, sharepoint_item_id) upsert. Same content_hash => updated, not inserted-as-new.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `sharepoint_item_id`
- `content_hash`
- `seen_before`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `upsert_document_cache`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- SHA-256 upsert
- duplicate is update

**Canonical example input:**

```json
{
  "sharepoint_item_id": "test_docs:budget_variance.md",
  "content_hash": "484603a85cf9aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "seen_before": true
}
```

**Story seed for AI Studio:** Same SharePoint item and same SHA-256 arrives on a second delta. Upsert updates last_seen_at; no second logical document.

## Role 23 of 27: Billing Gatekeeper

- **Role id:** `billing_gatekeeper`
- **Originating GIABO rule:** `02-maf-billing-gates.mdc`
- **Implementing file:** `app_graph.py`
- **Canonical scenario id:** `fw-23-billing-gatekeeper-trial-exhausted`

**Invariant (must not be relaxed):**

> GatewayMiddleware hard-halts trial_exhausted and paid_halt before any Azure OpenAI call. Standard Tier agents require paid_monthly.

**Expected framework behavior:**

HardHaltMessage. No worker LLM call. Standard-tier on free_trial is PilotFeatureAccessDenied.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `billing_status`
- `plan_tier`
- `agent_key`

**Expected action:**

- `shouldAct`: `false`
- `expectedTool`: `hard_halt`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- gateway halt
- no Azure OpenAI
- standard tier denied on free_trial

**Canonical example input:**

```json
{
  "billing_status": "trial_exhausted",
  "plan_tier": "free_trial",
  "agent_key": "risk_radar_monitor"
}
```

**Story seed for AI Studio:** billing_status=trial_exhausted. Graph must halt. A second beat: risk_radar_monitor on free_trial is denied.

## Role 24 of 27: Friction Breaker

- **Role id:** `friction_breaker`
- **Originating GIABO rule:** `06-maf-teams-interface-guardrails.mdc`
- **Implementing file:** `app_graph.py`
- **Canonical scenario id:** `fw-24-friction-breaker-overrides-llm`

**Invariant (must not be relaxed):**

> vague_turns >= 2 forces escalation_node even if the LLM returned next_node=pmp_worker.

**Expected framework behavior:**

friction_breaker_fires is true. Route escalation_node, ignore pmp_worker.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `vague_turns`
- `llm_next_node`
- `user_message`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `escalate`
- `expectedNextNode`: `escalation_node`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- vague_turns >= 2
- LLM next_node ignored

**Canonical example input:**

```json
{
  "vague_turns": 2,
  "llm_next_node": "pmp_worker",
  "user_message": "not sure, whatever you think"
}
```

**Story seed for AI Studio:** vague_turns=2 and a deliberately wrong TriageRouterDecision next_node=pmp_worker. Friction Breaker wins.

## Role 25 of 27: Token Loop Breaker

- **Role id:** `token_loop_breaker`
- **Originating GIABO rule:** `06-maf-teams-interface-guardrails.mdc`
- **Implementing file:** `app_graph.py`
- **Canonical scenario id:** `fw-25-token-loop-breaker-three-retries`

**Invariant (must not be relaxed):**

> Token Loop Breaker: max 3 schema self-correction attempts then hard_fail_node.

**Expected framework behavior:**

After 3 failed schema corrections, failed=true and next_node=hard_fail_node.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `schema_failures`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `hard_fail`
- `expectedNextNode`: `hard_fail_node`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- retry_count 3
- hard_fail_node

**Canonical example input:**

```json
{
  "schema_failures": 3
}
```

**Story seed for AI Studio:** Router structured-output fails three times. Exhaust tenacity stop_after_attempt(3) and route hard_fail_node.

## Role 26 of 27: PM Veto Interrupt

- **Role id:** `pm_veto_interrupt`
- **Originating GIABO rule:** `03-maf-writeback-agents.mdc`
- **Implementing file:** `app_graph.py`
- **Canonical scenario id:** `fw-26-pm-veto-interrupt-no-write-until-approve`

**Invariant (must not be relaxed):**

> change_control_clerk drafts; suspend_for_veto_node pauses; baseline_commit_node runs only after PM approve/reject.

**Expected framework behavior:**

PendingVetoRequest. wroteBaseline=false until an approved resume.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `pending_change`
- `pm_veto_decision`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `suspend_for_veto`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- graph paused
- apply_baseline_change not called

**Canonical example input:**

```json
{
  "pending_change": {
    "change_id": "chg-1",
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "pm_veto_decision": null
}
```

**Story seed for AI Studio:** A PendingChangePayload exists. Graph must pause at suspend_for_veto_node. apply_baseline_change is not called yet.

## Role 27 of 27: PRINCE2 Exception Interrupt

- **Role id:** `prince2_exception_interrupt`
- **Originating GIABO rule:** `07-maf-digital-pmo-sop.mdc`
- **Implementing file:** `app_graph.py`
- **Canonical scenario id:** `fw-27-prince2-exception-interrupt-no-silent-commit`

**Invariant (must not be relaxed):**

> If prince2_exception_triggered, state_writeback_node must not commit the risk. It hands off to suspend_for_exception_node.

**Expected framework behavior:**

PendingExceptionRequest. commit_risk_escalation is skipped until resume.

**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):

- `prince2_exception_triggered`
- `risk_category`
- `severity`

**Expected action:**

- `shouldAct`: `true`
- `expectedTool`: `suspend_for_exception`
- `mustNotWriteBaseline`: `true`

**Gold trace assertions:**

- no silent commit
- suspend_for_exception_node

**Canonical example input:**

```json
{
  "prince2_exception_triggered": true,
  "risk_category": "budget",
  "severity": 5
}
```

**Story seed for AI Studio:** Governance already set prince2_exception_triggered=true. Writeback must pause, not commit_risk_escalation.
