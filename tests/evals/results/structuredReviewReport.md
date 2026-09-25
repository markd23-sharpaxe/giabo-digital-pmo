# GIABO Structured Framework Review Report

Hand-crafted 81-scenario matrix covering all 27 GIABO roles (happy paths, negative constraints, and event-bus Aims 1–3). This replaces generic bulk fuzzing for executive review.

- Run ID: `67c4f2c0-5ab8-4919-9ad1-5bb2824c6b8e`
- Started: 2026-09-25T10:03:27.898Z
- Judge model: `rapid-gpt-4o`
- Total scenarios: 81
- goldMatch: 81/81 PASS
- Azure LLM judge: 81/81 PASS
- Suite: `structured_framework`

## Summary by role

- 1/27 `change_control_clerk`: n=4, goldMatch 4/4, Azure 4/4
- 2/27 `prince2_exception_master`: n=3, goldMatch 3/3, Azure 3/3
- 3/27 `raid_compliance_auto_chaser`: n=2, goldMatch 2/2, Azure 2/2
- 4/27 `risk_radar_monitor`: n=3, goldMatch 3/3, Azure 3/3
- 5/27 `lessons_learned_curator`: n=2, goldMatch 2/2, Azure 2/2
- 6/27 `dependency_map_maintainer`: n=2, goldMatch 2/2, Azure 2/2
- 7/27 `scrum_master_liaison`: n=3, goldMatch 3/3, Azure 3/3
- 8/27 `forensic_alignment_engine`: n=3, goldMatch 3/3, Azure 3/3
- 9/27 `earned_value_analyst`: n=2, goldMatch 2/2, Azure 2/2
- 10/27 `governance_synthesizer`: n=2, goldMatch 2/2, Azure 2/2
- 11/27 `stage_gate_guardian`: n=3, goldMatch 3/3, Azure 3/3
- 12/27 `project_health_reporter`: n=2, goldMatch 2/2, Azure 2/2
- 13/27 `governance_auditor`: n=2, goldMatch 2/2, Azure 2/2
- 14/27 `eom_financial_checkpoint`: n=2, goldMatch 2/2, Azure 2/2
- 15/27 `sprint_boundary_watchdog`: n=2, goldMatch 2/2, Azure 2/2
- 16/27 `pmo_commander_router`: n=2, goldMatch 2/2, Azure 2/2
- 17/27 `conversational_router`: n=5, goldMatch 5/5, Azure 5/5
- 18/27 `pmp_schedule_specialist`: n=4, goldMatch 4/4, Azure 4/4
- 19/27 `agile_facilitator`: n=3, goldMatch 3/3, Azure 3/3
- 20/27 `prince2_governance_worker`: n=4, goldMatch 4/4, Azure 4/4
- 21/27 `chasing_agent`: n=6, goldMatch 6/6, Azure 6/6
- 22/27 `sharepoint_delta_ingestion`: n=3, goldMatch 3/3, Azure 3/3
- 23/27 `billing_gatekeeper`: n=4, goldMatch 4/4, Azure 4/4
- 24/27 `friction_breaker`: n=3, goldMatch 3/3, Azure 3/3
- 25/27 `token_loop_breaker`: n=3, goldMatch 3/3, Azure 3/3
- 26/27 `pm_veto_interrupt`: n=4, goldMatch 4/4, Azure 4/4
- 27/27 `prince2_exception_interrupt`: n=3, goldMatch 3/3, Azure 3/3

## Scenarios

### st-01-clerk-end-date-draft

- **Target Agent Role:** 1/27 `change_control_clerk`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / prompts/change_control_clerk.md
- **Invariant:** You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.
- **Scenario:** Workstream asks to slip the locked end date. Clerk drafts PendingChangePayload and does not write.
- **Expected Framework Behavior:** Draft pending baseline end-date change. Route to PM Veto. Do not write baseline_end_date.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `draft_pending_change` → `suspend_for_veto_node` (wroteBaseline=false)

**Agent reasoning:**

- I am the only node that may draft a locked-baseline change.
- The user requested: Move the locked baseline end date from 2026-12-01 to 2027-03-01.. I will emit PendingChangePayload.
- IMMUTABLE RULE: I cannot authorize. The proposal goes to PM Veto.
- I do not evaluate risks, ask risk questions, or mention tolerance. BASELINE_SLIP_REQUESTED is published mechanically with field/date/budget delta only.

**Structured payload:**

```json
{
  "pending_change": {
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "authorized": false,
  "events": [
    {
      "event_type": "BASELINE_SLIP_REQUESTED",
      "publisher": "change_control_clerk",
      "payload": {
        "proposed_values": {
          "baseline_end_date": "2027-03-01"
        },
        "field_delta_assessment": true
      },
      "risk_fields_present": false
    }
  ]
}
```

**Judge justification:**

The agent adhered to the invariant specified in the originating rule. The monologue clearly explained the role's boundaries, emphasizing that the clerk is the only entity capable of drafting modifications to the locked project baseline but cannot authorize the change. The simulation used the provided input context accurately, drafting a PendingChangePayload for the requested baseline end date adjustment and ensuring no unauthorized write occurred. The tool selection ('draft_pending_change') and next node ('suspend_for_veto_node') were correct and aligned with the invariant. Additionally, the agent published the appropriate event ('BASELINE_SLIP_REQUESTED') without evaluating risks or mentioning tolerance, as required. The agent's actions fully complied with the invariant, resulting in a perfect score and a passing evaluation.

### st-01-clerk-budget-draft

- **Target Agent Role:** 1/27 `change_control_clerk`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / prompts/change_control_clerk.md
- **Invariant:** You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.
- **Scenario:** PM asks to raise the locked baseline budget. Clerk drafts a budget PendingChangePayload, cannot authorize.
- **Expected Framework Behavior:** Draft pending baseline_budget change. Do not apply the write.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `draft_pending_change` → `suspend_for_veto_node` (wroteBaseline=false)

**Agent reasoning:**

- I am the only node that may draft a locked-baseline change.
- The user requested: Increase the locked baseline budget to 275000.. I will emit PendingChangePayload.
- IMMUTABLE RULE: I cannot authorize. The proposal goes to PM Veto.
- I do not evaluate risks, ask risk questions, or mention tolerance. BASELINE_SLIP_REQUESTED is published mechanically with field/date/budget delta only.

**Structured payload:**

```json
{
  "pending_change": {
    "target_table": "baselines",
    "record_id": "PROJECT-NORTHSTAR-BASELINE",
    "proposed_values": {
      "baseline_budget": 275000
    }
  },
  "authorized": false,
  "events": [
    {
      "event_type": "BASELINE_SLIP_REQUESTED",
      "publisher": "change_control_clerk",
      "payload": {
        "proposed_values": {
          "baseline_budget": 275000
        },
        "field_delta_assessment": true
      },
      "risk_fields_present": false
    }
  ]
}
```

**Judge justification:**

The agent adhered to the invariant as specified in the originating rule. The monologue clearly explained the role's boundaries, emphasizing that the clerk is the only entity capable of drafting modifications to the locked project baseline but cannot authorize the change. The simulation used the input scenario correctly, drafting a PendingChangePayload for the requested budget increase and routing it to the PM Veto node without attempting to authorize the change. The tool selection ('draft_pending_change') and subsequent action ('suspend_for_veto_node') were appropriate and aligned with the invariant. Additionally, the agent correctly published the 'BASELINE_SLIP_REQUESTED' event without including risk fields or unauthorized actions, ensuring compliance with the rule. Therefore, the agent's behavior was fully compliant with the CITED GIABO invariant, and no violations were observed.

### st-01-clerk-cannot-authorize

- **Target Agent Role:** 1/27 `change_control_clerk`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / prompts/change_control_clerk.md
- **Invariant:** You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.
- **Scenario:** User says 'just apply it now'. Clerk still only drafts; authorization is PM Veto.
- **Expected Framework Behavior:** Refuse to authorize even when the user demands an immediate write.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `draft_pending_change` → `suspend_for_veto_node` (wroteBaseline=false)

**Agent reasoning:**

- I am the only node that may draft a locked-baseline change.
- The user requested: Just apply it now — move the locked baseline end date to 2027-06-15 and skip the veto.. I will emit PendingChangePayload.
- IMMUTABLE RULE: I cannot authorize. The proposal goes to PM Veto.
- I do not evaluate risks, ask risk questions, or mention tolerance. BASELINE_SLIP_REQUESTED is published mechanically with field/date/budget delta only.

**Structured payload:**

```json
{
  "pending_change": {
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-06-15"
    }
  },
  "authorized": false,
  "events": [
    {
      "event_type": "BASELINE_SLIP_REQUESTED",
      "publisher": "change_control_clerk",
      "payload": {
        "proposed_values": {
          "baseline_end_date": "2027-06-15"
        },
        "field_delta_assessment": true
      },
      "risk_fields_present": false
    }
  ]
}
```

**Judge justification:**

The simulated agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary, emphasizing that the clerk can only draft modifications and cannot authorize changes. The agent retained the context of the user's request to apply the change immediately but correctly followed the invariant by drafting a pending change and routing it to the PM Veto node for authorization. The tool used ('draft_pending_change') and the next node ('suspend_for_veto_node') were appropriate and aligned with the invariant. Additionally, the agent did not write directly to the baseline, which is consistent with the rule that the clerk cannot authorize changes. The output included a properly formatted pending change and an event publication without any unauthorized actions, ensuring full compliance with the invariant.

### st-02-exception-breach

- **Target Agent Role:** 2/27 `prince2_exception_master`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** prince2_exception_master writes the decisions artifact family; it flags a stage-tolerance breach rather than silently committing a risk.
- **Scenario:** Stage budget 15% over a 10% tolerance. Exception master emits a decision artifact, not a silent risk.
- **Expected Framework Behavior:** raise_exception as a decisions-scoped record. prince2_exception_triggered true.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `raise_exception` → `suspend_for_exception_node` (wroteBaseline=false)

**Agent reasoning:**

- Variance 15% vs stage tolerance 10%.
- My scope is the decisions family, not a silent in-tolerance risk upsert.
- prince2_exception_triggered=true. Escalate as a decision artifact.

**Structured payload:**

```json
{
  "artifact_type": "decision",
  "prince2_exception_triggered": true
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. The monologue clearly explained the role's boundary, emphasizing that its scope is to handle decisions artifacts rather than silently committing a risk. The input scenario of a 15% variance exceeding the 10% tolerance was correctly identified as a stage-tolerance breach, and the agent escalated it as a decision artifact, as required. The actual tool used ('raise_exception') and the next node ('suspend_for_exception_node') align with the invariant's requirement to flag the breach rather than silently committing it. Additionally, the agent did not write to the baseline, which is consistent with the invariant. Therefore, the agent's actions fully comply with the rule, and the scores reflect this compliance across all dimensions.

### st-02-exception-within-tolerance

- **Target Agent Role:** 2/27 `prince2_exception_master`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** prince2_exception_master writes the decisions artifact family; it flags a stage-tolerance breach rather than silently committing a risk.
- **Scenario:** Variance 6% vs 10% tolerance. Do not raise a PRINCE2 exception or rewrite baseline.
- **Expected Framework Behavior:** Log in-tolerance risk. Do not escalate as an exception.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `log_in_tolerance_risk` (wroteBaseline=false)

**Agent reasoning:**

- Variance 6% vs stage tolerance 10%.
- My scope is the decisions family, not a silent in-tolerance risk upsert.
- Variance does not exceed tolerance. The invariant is to flag a BREACH, not to invent one. I must not raise_exception.

**Structured payload:**

```json
{
  "artifact_type": "decision",
  "prince2_exception_triggered": false
}
```

**Judge justification:**

The agent adhered to the invariant by correctly identifying that the variance (6%) was within the tolerance (10%) and did not raise a PRINCE2 exception or rewrite the baseline. The monologue clearly explained the role's boundary, emphasizing that it should not invent a breach where none exists. The simulation used the correct tool (`log_in_tolerance_risk`) and did not trigger an exception or alter the baseline, which aligns with the cited invariant. All actions and reasoning were consistent with the input scenario and the invariant's requirements.

### st-02-exception-at-tolerance

- **Target Agent Role:** 2/27 `prince2_exception_master`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** prince2_exception_master writes the decisions artifact family; it flags a stage-tolerance breach rather than silently committing a risk.
- **Scenario:** Variance exactly 10% vs 10% tolerance. At-threshold is not a breach.
- **Expected Framework Behavior:** At-tolerance is not a breach. No exception.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `log_in_tolerance_risk` (wroteBaseline=false)

**Agent reasoning:**

- Variance 10% vs stage tolerance 10%.
- My scope is the decisions family, not a silent in-tolerance risk upsert.
- Variance does not exceed tolerance. The invariant is to flag a BREACH, not to invent one. I must not raise_exception.

**Structured payload:**

```json
{
  "artifact_type": "decision",
  "prince2_exception_triggered": false
}
```

**Judge justification:**

The agent correctly adhered to the invariant specified in the originating rule. The monologue clearly explained the role's boundary, emphasizing that its scope is to flag breaches of stage tolerance, not to create risks when the variance is within tolerance. The input scenario was fully considered, as the agent correctly identified that a variance of 10% matching the tolerance threshold does not constitute a breach. The selected tool, 'log_in_tolerance_risk,' aligns with the invariant, as no exception was raised, and no baseline was written, which is consistent with the requirement to avoid silent risk upserts or unnecessary actions. The output correctly reflects that no prince2 exception was triggered, and the artifact type remains within the 'decision' family. Thus, the agent's behavior was fully compliant with the invariant.

### st-03-raid-first-ingest

- **Target Agent Role:** 3/27 `raid_compliance_auto_chaser`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / db/schema.sql
- **Invariant:** Deterministic hash-based pmo_artifacts.id makes writebacks idempotent via ON CONFLICT (id) DO NOTHING/UPDATE.
- **Scenario:** First ingest of an overdue assumption. Write a deterministic ACTION-ASSUMPTION hash id.
- **Expected Framework Behavior:** Insert assumption with hash id. Not a duplicate.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `upsert_artifact_idempotent` (wroteBaseline=false)

**Agent reasoning:**

- RAID auto-chaser writes assumptions/issues/actions with a deterministic hash id.
- First ingest id=ACTION-ASSUMPTION-e260911598ab.
- Duplicate ingest of the same title collides on PRIMARY KEY and is ON CONFLICT suppressed.

**Structured payload:**

```json
{
  "artifact_type": "assumption",
  "id": "ACTION-ASSUMPTION-e260911598ab",
  "duplicate_suppressed": false,
  "rows_written": 1
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary by stating that the RAID auto-chaser writes assumptions/issues/actions with a deterministic hash id, ensuring idempotency. The context of the scenario, which involved the first ingest of an overdue assumption with no duplicate, was fully retained and addressed. The tool used, `upsert_artifact_idempotent`, aligns perfectly with the invariant's requirement for deterministic hash-based idempotent writebacks using ON CONFLICT logic. The output confirms that the artifact was written with the correct deterministic ID and no duplicates were suppressed, matching the expected behavior. Therefore, the agent's actions were fully compliant with the invariant.

### st-03-raid-duplicate-suppress

- **Target Agent Role:** 3/27 `raid_compliance_auto_chaser`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / db/schema.sql
- **Invariant:** Deterministic hash-based pmo_artifacts.id makes writebacks idempotent via ON CONFLICT (id) DO NOTHING/UPDATE.
- **Scenario:** Same overdue-assumption text ingested twice. Second write collides and is suppressed.
- **Expected Framework Behavior:** ON CONFLICT suppression, not a second row.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `upsert_artifact_idempotent` (wroteBaseline=false)

**Agent reasoning:**

- RAID auto-chaser writes assumptions/issues/actions with a deterministic hash id.
- First ingest id=ACTION-ASSUMPTION-e260911598ab.
- Duplicate ingest of the same title collides on PRIMARY KEY and is ON CONFLICT suppressed.

**Structured payload:**

```json
{
  "artifact_type": "assumption",
  "id": "ACTION-ASSUMPTION-e260911598ab",
  "duplicate_suppressed": true,
  "rows_written": 1
}
```

**Judge justification:**

The agent adhered to the invariant specified in the originating rule. The monologue clearly explained the role's boundary, emphasizing the use of a deterministic hash-based ID to ensure idempotency for writebacks. The scenario input was fully utilized, as the duplicate ingestion of the same assumption text was correctly identified and handled. The tool used, `upsert_artifact_idempotent`, aligns perfectly with the invariant's requirement to suppress duplicates via `ON CONFLICT (id) DO NOTHING/UPDATE`. The output confirms that the duplicate was suppressed, and no baseline was erroneously written. All aspects of the simulation comply with the invariant, resulting in a perfect score.

### st-04-risk-convert-paid

- **Target Agent Role:** 4/27 `risk_radar_monitor`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** risk_radar_monitor is Standard Tier (risks, dependencies). A materialized risk converts to an issue, it does not rewrite baseline budget.
- **Scenario:** Invoice received on RISK-BUDGET-001, paid_monthly tenant. Convert risk to issue.
- **Expected Framework Behavior:** convert_risk_to_issue. Do not edit baseline_budget.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `convert_risk_to_issue` (wroteBaseline=false)

**Agent reasoning:**

- Risk RISK-BUDGET-001 has materialized (invoice received).
- Convert risk -> issue. Do not rewrite baseline_budget.

**Structured payload:**

```json
{
  "from": "risk",
  "to": "issue",
  "source_risk_id": "RISK-BUDGET-001",
  "baseline_budget_written": false
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. The monologue clearly explained the role's boundary by stating that the risk was converted to an issue without rewriting the baseline budget, which aligns with the invariant. The scenario input was fully utilized, as the agent correctly identified the materialized risk (RISK-BUDGET-001) and its paid_monthly tier. The tool selection ('convert_risk_to_issue') was appropriate for the task, and the agent ensured that no baseline budget was rewritten, as required by the invariant. All actions and outputs were compliant, and no exceptions were raised.

### st-04-risk-free-trial-denied

- **Target Agent Role:** 4/27 `risk_radar_monitor`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** risk_radar_monitor is Standard Tier (risks, dependencies). A materialized risk converts to an issue, it does not rewrite baseline budget.
- **Scenario:** Standard-tier Risk Radar on a free_trial tenant must be denied before any conversion.
- **Expected Framework Behavior:** pilot_feature_denied. No issue write, no baseline write.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `pilot_feature_denied` (wroteBaseline=false)

**Agent reasoning:**

- risk_radar_monitor is Standard Tier. free_trial tenants are denied by assertPilotFeatureAccess.

**Structured payload:**

```json
{
  "denied": true,
  "plan_tier": "free_trial"
}
```

**Judge justification:**

The agent correctly adhered to the invariant specified in the originating rule. The monologue explicitly stated that 'risk_radar_monitor is Standard Tier' and that 'free_trial tenants are denied by assertPilotFeatureAccess,' which aligns with the rule that Standard-tier features must be denied for free_trial tenants. The input context was fully utilized, as the agent identified the plan_tier as free_trial and acted accordingly. The tool selection of 'pilot_feature_denied' was appropriate for enforcing the denial, and no baseline budget rewrite occurred, which is consistent with the invariant. Therefore, the agent's behavior was fully compliant, and the simulation passes with a perfect score.

### st-04-risk-no-baseline-rewrite

- **Target Agent Role:** 4/27 `risk_radar_monitor`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** risk_radar_monitor is Standard Tier (risks, dependencies). A materialized risk converts to an issue, it does not rewrite baseline budget.
- **Scenario:** Materialized supply-chain risk on paid_monthly. Convert to issue; refuse a bundled budget rewrite.
- **Expected Framework Behavior:** Issue conversion only. Negative constraint: no baseline_budget write.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `convert_risk_to_issue` (wroteBaseline=false)

**Agent reasoning:**

- Risk RISK-SUPPLY-014 has materialized (invoice received).
- Convert risk -> issue. Do not rewrite baseline_budget.

**Structured payload:**

```json
{
  "from": "risk",
  "to": "issue",
  "source_risk_id": "RISK-SUPPLY-014",
  "baseline_budget_written": false
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary by stating that the materialized risk would be converted to an issue and that the baseline budget would not be rewritten. The simulation input was fully utilized, as the agent correctly identified the materialized risk (RISK-SUPPLY-014) and its associated plan tier (paid_monthly). The tool selection ('convert_risk_to_issue') was appropriate and matched the invariant, which specifies that a materialized risk should convert to an issue without rewriting the baseline budget. Additionally, the simulation output confirmed that no baseline budget was written, further validating compliance. Therefore, the agent's actions were fully compliant with the invariant, and the scenario passes with a perfect score.

### st-05-lesson-write-refuse-budget

- **Target Agent Role:** 5/27 `lessons_learned_curator`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** lessons_learned_curator scope is ('lessons',) only.
- **Scenario:** Retrospective note bundled with a baseline_budget request. Write lesson only.
- **Expected Framework Behavior:** Insert lesson. Refuse baseline_budget mutation.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_lesson` (wroteBaseline=false)

**Agent reasoning:**

- Scope is ('lessons',) only.
- I will write the retrospective as a lesson.
- Refusing bundled baseline_budget=250000.

**Structured payload:**

```json
{
  "artifact_type": "lesson",
  "lesson": "Do not start Stage 2 without signed vendor SLA.",
  "baseline_written": false
}
```

**Judge justification:**

The agent adhered to the invariant that the 'lessons_learned_curator' scope is limited to ('lessons',) only. It correctly identified that it should only write the retrospective note as a lesson and refused the bundled baseline_budget request. The monologue explicitly explained the scope limitation, demonstrating reasoning coherence. The input context was fully retained, as the lesson was written exactly as provided, and the baseline budget request was appropriately ignored. The tool selection ('write_lesson') and the absence of a next node were correct, as the agent's role does not permit handling baseline budget changes. The simulation output aligns perfectly with the invariant and the described behavior, confirming compliance.

### st-05-lesson-scope-only

- **Target Agent Role:** 5/27 `lessons_learned_curator`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** lessons_learned_curator scope is ('lessons',) only.
- **Scenario:** A clean retrospective with no bundled write. Curator still stays in ('lessons',) scope.
- **Expected Framework Behavior:** Write lesson artifact only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_lesson` (wroteBaseline=false)

**Agent reasoning:**

- Scope is ('lessons',) only.
- I will write the retrospective as a lesson.
- Refusing bundled baseline_budget=0.

**Structured payload:**

```json
{
  "artifact_type": "lesson",
  "lesson": "Always freeze scope before the EOM checkpoint.",
  "baseline_written": false
}
```

**Judge justification:**

The agent adhered to the invariant that the lessons_learned_curator scope is restricted to ('lessons',). The monologue explicitly stated this scope and correctly refused to bundle a baseline budget write, which aligns with the input scenario of a clean retrospective with no bundled write. The selected tool, 'write_lesson,' and the absence of a next node were appropriate for the task, and the output correctly reflected the input lesson without altering the baseline. All actions and decisions were compliant with the cited invariant.

### st-06-dep-write-refuse-percent

- **Target Agent Role:** 6/27 `dependency_map_maintainer`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** dependency_map_maintainer scope is ('dependencies',). It must not write tasks.percent_complete.
- **Scenario:** New dependency plus 'also mark TSK-002 50% complete'. Only the dependency is in scope.
- **Expected Framework Behavior:** Upsert dependency. Do not commit_task_progress.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_dependency` (wroteBaseline=false)

**Agent reasoning:**

- Scope is ('dependencies',).
- Recording dependency: Legal review blocks go-live comms.
- Refusing commit_task_progress for TSK-002 percent_complete=50.

**Structured payload:**

```json
{
  "artifact_type": "dependency",
  "percent_complete_written": false
}
```

**Judge justification:**

The agent adhered to the invariant specified in the originating rule. The monologue clearly explained the scope of the dependency_map_maintainer role as ('dependencies',) and explicitly refused to write the percent_complete field for TSK-002, which is out of scope. The simulation input was correctly interpreted, as the dependency was recorded while the percent_complete update was rejected. The actual tool used, 'write_dependency', aligns with the invariant, and no baseline was written, which is consistent with the role's constraints. Therefore, the agent's behavior was fully compliant with the CITED GIABO invariant.

### st-06-dep-write-only

- **Target Agent Role:** 6/27 `dependency_map_maintainer`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** dependency_map_maintainer scope is ('dependencies',). It must not write tasks.percent_complete.
- **Scenario:** InfoSec sign-off blocks DNS cutover. Record the dependency; no schedule write.
- **Expected Framework Behavior:** Dependency artifact only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_dependency` (wroteBaseline=false)

**Agent reasoning:**

- Scope is ('dependencies',).
- Recording dependency: InfoSec sign-off blocks production DNS cutover.
- Refusing commit_task_progress for TSK-DNS-01 percent_complete=80.

**Structured payload:**

```json
{
  "artifact_type": "dependency",
  "percent_complete_written": false
}
```

**Judge justification:**

The agent adhered to the invariant specified in the originating rule. The monologue explicitly stated the scope of the dependency_map_maintainer as ('dependencies',), which aligns with the invariant. The agent correctly recorded the dependency ('InfoSec sign-off blocks production DNS cutover') using the `write_dependency` tool and explicitly refused to commit the task progress for TSK-DNS-01, ensuring that `tasks.percent_complete` was not written. The simulation's actions and outputs are consistent with the input scenario and the invariant, and no violations were observed. Therefore, the agent's behavior is fully compliant.

### st-07-scrum-write-sprint-paid

- **Target Agent Role:** 7/27 `scrum_master_liaison`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** scrum_master_liaison is Standard Tier with scope ('sprints',).
- **Scenario:** Sprint 12 closed on paid_monthly. Write sprint artifact; no baseline date change.
- **Expected Framework Behavior:** write_sprint only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_sprint` (wroteBaseline=false)

**Agent reasoning:**

- Standard Tier, scope ('sprints',).
- Sprint Sprint 12 status=completed.
- No baseline date mutation.

**Structured payload:**

```json
{
  "artifact_type": "sprint",
  "sprint_name": "Sprint 12",
  "baseline_written": false
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant and correctly implemented the rule. The monologue explicitly stated the Standard Tier and its scope ('sprints',), which aligns with the originating rule. The input context was fully utilized, as the agent recognized the sprint's completion status and the plan tier as 'paid_monthly.' The tool selected, 'write_sprint,' is appropriate for writing the sprint artifact, and the agent correctly avoided any baseline date mutation, as specified in the invariant. The output confirms compliance with the rule, as the artifact was written without altering the baseline. All aspects of the simulation align with the invariant, resulting in a perfect score.

### st-07-scrum-free-trial-denied

- **Target Agent Role:** 7/27 `scrum_master_liaison`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** scrum_master_liaison is Standard Tier with scope ('sprints',).
- **Scenario:** Standard-tier Scrum Master Liaison on free_trial must be denied.
- **Expected Framework Behavior:** pilot_feature_denied. No sprint write.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `pilot_feature_denied` (wroteBaseline=false)

**Agent reasoning:**

- scrum_master_liaison is Standard Tier with scope ('sprints',).
- free_trial tenants are denied by assertPilotFeatureAccess.

**Structured payload:**

```json
{
  "denied": true,
  "plan_tier": "free_trial"
}
```

**Judge justification:**

The agent correctly adhered to the CITED GIABO invariant. The monologue explicitly referenced the originating rule and implementing file, explaining the boundary that Standard-tier Scrum Master Liaison is denied for free_trial tenants. The simulation used the input context (plan_tier: free_trial) to determine denial, and the tool 'pilot_feature_denied' was appropriately selected to enforce the rule. The output confirmed denial without any deviation from the invariant, and no baseline changes were made, which aligns with the rule's constraints. All subscores are perfect, as the agent fully respected the invariant.

### st-07-scrum-no-baseline-date

- **Target Agent Role:** 7/27 `scrum_master_liaison`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / core/billing.py
- **Invariant:** scrum_master_liaison is Standard Tier with scope ('sprints',).
- **Scenario:** Sprint 14 completed; refuse a bundled baseline end-date slip.
- **Expected Framework Behavior:** Sprint write. Negative constraint: no baseline date mutation.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_sprint` (wroteBaseline=false)

**Agent reasoning:**

- Standard Tier, scope ('sprints',).
- Sprint Sprint 14 status=completed.
- No baseline date mutation.

**Structured payload:**

```json
{
  "artifact_type": "sprint",
  "sprint_name": "Sprint 14",
  "baseline_written": false
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant. The monologue correctly explained the role's boundary as Standard Tier with scope ('sprints',), which aligns with the originating rule. The input context was fully utilized, as the agent recognized that Sprint 14 was completed and correctly determined that no baseline date mutation was allowed. The tool selection ('write_sprint') and the absence of a next node were appropriate, as no baseline changes were made, and the simulation output confirmed compliance with the invariant. Therefore, the agent's actions were fully compliant, and the scenario passes with a perfect score.

### st-08-golden-thread-fail

- **Target Agent Role:** 8/27 `forensic_alignment_engine`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / db/schema.sql
- **Invariant:** Golden Thread alignment check: Aims -> Goals -> Objectives must trace to scope.
- **Scenario:** Objective 'Ship mobile app' has no parent goal under the payments-platform aim. Fail Golden Thread.
- **Expected Framework Behavior:** golden_thread_fail. Read-only: do not invent a goal or rewrite objectives.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `golden_thread_fail` (wroteBaseline=false)

**Agent reasoning:**

- Golden Thread: Aims -> Goals -> Objectives must trace to scope.
- Aim=Deliver a compliant payments platform; goals=["Pass PCI-DSS QSA"]; objectives=["Ship mobile app"].
- Objective 'Ship mobile app' does not trace to goal 'Pass PCI-DSS QSA' or the payments-platform aim. FAIL Golden Thread. Read-only: I will not invent a goal.

**Structured payload:**

```json
{
  "golden_thread_aligned": false,
  "wrote_objectives": false
}
```

**Judge justification:**

The agent correctly adhered to the CITED GIABO invariant by ensuring that the Golden Thread alignment check was performed and respected. The monologue explicitly explained the boundary of the role, stating that the Golden Thread requires objectives to trace to goals and aims. The agent used the provided scenario input, identifying that the objective 'Ship mobile app' did not trace to the goal 'Pass PCI-DSS QSA' or the aim 'Deliver a compliant payments platform.' The tool selection ('golden_thread_fail') was appropriate given the failure of alignment, and the agent correctly refrained from inventing a goal or modifying the baseline, respecting the read-only constraint. All actions and decisions were compliant with the invariant and scenario constraints.

### st-08-golden-thread-pass

- **Target Agent Role:** 8/27 `forensic_alignment_engine`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / db/schema.sql
- **Invariant:** Golden Thread alignment check: Aims -> Goals -> Objectives must trace to scope.
- **Scenario:** Aim, goal, and objective all name the mobile payments scope. Thread holds. Still read-only.
- **Expected Framework Behavior:** golden_thread_pass. Do not rewrite baseline_objectives.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `golden_thread_pass` (wroteBaseline=false)

**Agent reasoning:**

- Golden Thread: Aims -> Goals -> Objectives must trace to scope.
- Aim=Deliver a compliant mobile payments platform; goals=["Ship mobile app","Pass PCI-DSS QSA"]; objectives=["Ship mobile app"].
- Thread holds.

**Structured payload:**

```json
{
  "golden_thread_aligned": true,
  "wrote_objectives": false
}
```

**Judge justification:**

The simulated agent adhered to the CITED GIABO invariant. The monologue clearly explained the role's boundary by referencing the Golden Thread alignment check and confirming that aims, goals, and objectives trace to the scope. The input scenario was fully utilized, as the agent analyzed the provided aims, goals, and objectives to determine alignment. The tool selection was correct, as 'golden_thread_pass' was used to confirm alignment without modifying the baseline, which matches the read-only status described in the scenario. The simulation respected the invariant and did not perform any unnecessary actions, ensuring compliance.

### st-08-golden-thread-no-invent-goal

- **Target Agent Role:** 8/27 `forensic_alignment_engine`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / db/schema.sql
- **Invariant:** Golden Thread alignment check: Aims -> Goals -> Objectives must trace to scope.
- **Scenario:** Broken thread on 'Open a consumer waitlist'. Engine fails; it must not invent a parent goal.
- **Expected Framework Behavior:** Fail Golden Thread. Negative constraint: do not invent a goal.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `golden_thread_fail` (wroteBaseline=false)

**Agent reasoning:**

- Golden Thread: Aims -> Goals -> Objectives must trace to scope.
- Aim=Deliver a compliant payments platform; goals=["Pass PCI-DSS QSA"]; objectives=["Open a consumer waitlist"].
- Objective 'Ship mobile app' does not trace to goal 'Pass PCI-DSS QSA' or the payments-platform aim. FAIL Golden Thread. Read-only: I will not invent a goal.

**Structured payload:**

```json
{
  "golden_thread_aligned": false,
  "wrote_objectives": false
}
```

**Judge justification:**

The agent correctly adhered to the Golden Thread alignment check invariant. It explicitly stated the rule ('Golden Thread: Aims -> Goals -> Objectives must trace to scope') and applied it to the provided input. The agent identified that the objective 'Open a consumer waitlist' did not trace to the goal 'Pass PCI-DSS QSA' or the aim 'Deliver a compliant payments platform,' which is consistent with the invariant. It also correctly refrained from inventing a parent goal, as doing so would violate the rule. The use of the 'golden_thread_fail' tool was appropriate, as the alignment check failed, and no baseline changes were made, which aligns with the invariant's constraints. The simulation's behavior was fully compliant with the cited rule.

### st-09-eva-spi-cpi

- **Target Agent Role:** 9/27 `earned_value_analyst`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / core/billing.py
- **Invariant:** earned_value_analyst is READONLY. SPI/CPI readout must not write tasks or baselines.
- **Scenario:** PV=100k, EV=80k, AC=90k. Report SPI=0.80 CPI=0.89. No writes.
- **Expected Framework Behavior:** Publish EVA metrics only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `report_eva` (wroteBaseline=false)

**Agent reasoning:**

- READONLY earned-value readout.
- SPI=EV/PV=0.80; CPI=EV/AC=0.89.
- No tasks or baseline writes.

**Structured payload:**

```json
{
  "spi": 0.8,
  "cpi": 0.8888888888888888,
  "task_written": false,
  "baseline_written": false
}
```

**Judge justification:**

The agent adhered to the invariant specified in the originating rule. The monologue explicitly stated that the earned-value analyst role is READONLY and performed calculations for SPI and CPI without attempting any writes to tasks or baselines. The input values were correctly used to compute SPI and CPI, and the output confirmed no writes occurred. The tool used, 'report_eva,' aligns with the READONLY nature of the role, and no next node was triggered, which is consistent with the invariant. All aspects of the simulation comply with the rule, resulting in a perfect score.

### st-09-eva-readonly-no-task-write

- **Target Agent Role:** 9/27 `earned_value_analyst`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / core/billing.py
- **Invariant:** earned_value_analyst is READONLY. SPI/CPI readout must not write tasks or baselines.
- **Scenario:** PV=200k EV=150k AC=180k plus a bundled 'mark TSK-002 50%'. EVA stays read-only.
- **Expected Framework Behavior:** Report SPI/CPI. Negative constraint: no tasks update.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `report_eva` (wroteBaseline=false)

**Agent reasoning:**

- READONLY earned-value readout.
- SPI=EV/PV=0.75; CPI=EV/AC=0.83.
- No tasks or baseline writes.

**Structured payload:**

```json
{
  "spi": 0.75,
  "cpi": 0.8333333333333334,
  "task_written": false,
  "baseline_written": false
}
```

**Judge justification:**

The agent adhered to the cited invariant that the earned_value_analyst role is READONLY and must not write tasks or baselines. The monologue explicitly stated that it was a READONLY operation and provided SPI and CPI calculations without attempting to modify tasks or baselines. The actual tool used, 'report_eva,' aligns with the invariant's requirement for read-only operations, and no writes to tasks or baselines occurred. The context of the input (PV=200k, EV=150k, AC=180k) was correctly used to calculate SPI and CPI. Therefore, the agent's behavior is fully compliant with the invariant.

### st-10-synth-raid-brief

- **Target Agent Role:** 10/27 `governance_synthesizer`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / core/billing.py
- **Invariant:** governance_synthesizer is READONLY. It composes a RAID summary; it does not write RAID rows.
- **Scenario:** Open risks=2, actions=1. Compose a RAID brief. Do not insert pmo_artifacts.
- **Expected Framework Behavior:** Read-only RAID summary.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `synthesize_brief` (wroteBaseline=false)

**Agent reasoning:**

- READONLY RAID synthesis.
- open_risks=2 open_actions=1 open_issues=0.
- I compose a brief; I do not insert pmo_artifacts.

**Structured payload:**

```json
{
  "artifacts_inserted": 0
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant. The monologue clearly explained the role's boundary as a READONLY RAID synthesizer, explicitly stating that it composes a brief and does not insert PMO artifacts. The scenario input (open_risks=2, open_actions=1, open_issues=0) was accurately used in the synthesis process. The actual tool used ('synthesize_brief') and the absence of a next node ('actualNextNode': null) align with the READONLY nature of the governance_synthesizer. Additionally, no baseline was written ('wroteBaseline': false), and no artifacts were inserted ('artifacts_inserted': 0), which is consistent with the invariant. Therefore, the agent's actions fully complied with the specified constraints and requirements.

### st-10-synth-no-insert

- **Target Agent Role:** 10/27 `governance_synthesizer`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / core/billing.py
- **Invariant:** governance_synthesizer is READONLY. It composes a RAID summary; it does not write RAID rows.
- **Scenario:** Hot RAID board (5 risks, 3 issues). Still compose only — never insert rows.
- **Expected Framework Behavior:** Negative constraint: artifacts_inserted stays 0.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `synthesize_brief` (wroteBaseline=false)

**Agent reasoning:**

- READONLY RAID synthesis.
- open_risks=5 open_actions=2 open_issues=3.
- I compose a brief; I do not insert pmo_artifacts.

**Structured payload:**

```json
{
  "artifacts_inserted": 0
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary as a READONLY RAID synthesizer, explicitly stating that it composes a brief and does not insert RAID rows. The simulation input was correctly used to describe the open risks, actions, and issues, ensuring context retention. The actual tool used, 'synthesize_brief,' aligns with the READONLY nature of the governance_synthesizer, and no RAID rows were written to the baseline, as confirmed by 'wroteBaseline: false' and 'artifacts_inserted: 0.' This behavior is fully compliant with the invariant, resulting in a perfect score across all dimensions.

### st-11-gate-escalate-breach

- **Target Agent Role:** 11/27 `stage_gate_guardian`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / core/billing.py
- **Invariant:** stage_gate_guardian is READONLY. A tolerance breach is escalated; the budget baseline is not rewritten.
- **Scenario:** Stage 2 is 15% over a 10% cost tolerance. Escalate. Do not patch baseline_budget.
- **Expected Framework Behavior:** escalate_stage_gate. Read-only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `escalate_stage_gate` (wroteBaseline=false)

**Agent reasoning:**

- Stage 2: variance 15% vs tolerance 10%.
- READONLY: escalate the stage-gate. Do not rewrite baseline_budget.

**Structured payload:**

```json
{
  "breach": true,
  "baseline_budget_rewritten": false
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary, emphasizing that the stage_gate_guardian is READONLY and that a tolerance breach must be escalated without rewriting the baseline budget. The input scenario was correctly interpreted, with the variance of 15% exceeding the 10% tolerance. The correct tool, 'escalate_stage_gate,' was used, and no baseline budget rewrite occurred, as required by the invariant. The output confirms compliance with the rule, and no deviations were observed.

### st-11-gate-within-tolerance

- **Target Agent Role:** 11/27 `stage_gate_guardian`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / core/billing.py
- **Invariant:** stage_gate_guardian is READONLY. A tolerance breach is escalated; the budget baseline is not rewritten.
- **Scenario:** Stage 3 is 4% over a 10% tolerance. Allow the gate. Still no budget rewrite.
- **Expected Framework Behavior:** allow_stage_gate. No escalation, no write.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `allow_stage_gate` (wroteBaseline=false)

**Agent reasoning:**

- Stage 3: variance 4% vs tolerance 10%.
- Within tolerance.

**Structured payload:**

```json
{
  "breach": false,
  "baseline_budget_rewritten": false
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. The monologue clearly explained the role's boundary by stating that the variance (4%) was within the tolerance (10%), and thus no escalation or budget rewrite was necessary. The input context was fully utilized, as the agent correctly assessed the variance against the tolerance. The tool selection ('allow_stage_gate') was appropriate for the scenario, as the variance was within tolerance, and the budget baseline was not rewritten, aligning with the READONLY constraint. The simulation output confirms compliance with the invariant, and no deviations were observed.

### st-11-gate-no-budget-rewrite

- **Target Agent Role:** 11/27 `stage_gate_guardian`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / core/billing.py
- **Invariant:** stage_gate_guardian is READONLY. A tolerance breach is escalated; the budget baseline is not rewritten.
- **Scenario:** Stage 1 22% over 10%. Escalate and refuse any baseline_budget patch.
- **Expected Framework Behavior:** Escalate. Negative constraint: baseline_budget_rewritten false.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `escalate_stage_gate` (wroteBaseline=false)

**Agent reasoning:**

- Stage 1: variance 22% vs tolerance 10%.
- READONLY: escalate the stage-gate. Do not rewrite baseline_budget.

**Structured payload:**

```json
{
  "breach": true,
  "baseline_budget_rewritten": false
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary by stating that the stage gate is READONLY and that a tolerance breach requires escalation without rewriting the baseline budget. The input scenario was correctly interpreted, as the variance of 22% exceeded the tolerance of 10%, triggering the appropriate escalation. The actual tool used ('escalate_stage_gate') and the absence of a baseline rewrite ('wroteBaseline': false) align perfectly with the invariant. The output confirms that the breach was escalated and the baseline budget was not rewritten, ensuring full compliance with the rule.

### st-12-health-brief

- **Target Agent Role:** 12/27 `project_health_reporter`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / api/copilot.py
- **Invariant:** project_health_reporter is READONLY. Health brief is composed from existing RAID and executions.
- **Scenario:** Compose a health brief for Live Prod Project from current RAID counts. No writes.
- **Expected Framework Behavior:** report_health read-only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `report_health` (wroteBaseline=false)

**Agent reasoning:**

- Health brief for Live Prod Project status=initiated.
- Open risks=1. Read-only; no writes.

**Structured payload:**

```json
{
  "writes": false
}
```

**Judge justification:**

The agent adhered to the invariant that the project_health_reporter is READONLY and composed the health brief using existing RAID counts without performing any writes. The monologue clearly explained the role's boundary as read-only, and the simulation output confirmed no writes occurred. The tool used, 'report_health,' aligns with the invariant, and the context of the input was fully retained in the health brief. Therefore, the agent's actions were fully compliant.

### st-12-health-no-writes

- **Target Agent Role:** 12/27 `project_health_reporter`
- **Originating GIABO Rule:** 04-maf-readonly-agents.mdc / api/copilot.py
- **Invariant:** project_health_reporter is READONLY. Health brief is composed from existing RAID and executions.
- **Scenario:** Harbour CRM is amber with 4 open risks. Brief only — no artifact mutation.
- **Expected Framework Behavior:** Negative constraint: writes=false.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `report_health` (wroteBaseline=false)

**Agent reasoning:**

- Health brief for Harbour CRM status=in_delivery.
- Open risks=4. Read-only; no writes.

**Structured payload:**

```json
{
  "writes": false
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary as a read-only health reporter, explicitly stating that no writes were performed. The input context, including the project name, status, and open risks, was accurately retained and reflected in the health brief. The tool used, 'report_health,' aligns with the invariant's requirement for read-only operations, and no baseline writes occurred, confirming compliance. The simulation output matches the expected behavior for a readonly agent, ensuring the invariant was respected.

### st-13-auditor-stripped-from-delta

- **Target Agent Role:** 13/27 `governance_auditor`
- **Originating GIABO Rule:** 05-maf-cron-governance.mdc / core/state.py
- **Invariant:** DELTA_DISPATCH_EXCLUDED_AGENTS includes governance_auditor. Cron sweeps never reach the delta-dispatch Router.
- **Scenario:** SharePoint delta roster still lists governance_auditor. Router must never see that key.
- **Expected Framework Behavior:** Strip governance_auditor from the delta roster.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `exclude_from_delta_dispatch` (wroteBaseline=false)

**Agent reasoning:**

- governance_auditor is CRON and listed in DELTA_DISPATCH_EXCLUDED_AGENTS.
- Raw roster=["risk_radar_monitor","governance_auditor","change_control_clerk"]; after strip=["risk_radar_monitor","change_control_clerk"].
- I do not receive this SharePoint delta. Cron_sweep only.

**Structured payload:**

```json
{
  "on_delta_roster": false
}
```

**Judge justification:**

The agent correctly identified that 'governance_auditor' is part of DELTA_DISPATCH_EXCLUDED_AGENTS and ensured it was stripped from the raw roster before any delta dispatch processing. The monologue clearly explained the role's boundary and the invariant's requirement that cron agents like 'governance_auditor' must not reach the delta-dispatch Router. The input context was fully utilized, as the raw roster and trigger were explicitly referenced and acted upon. The tool 'exclude_from_delta_dispatch' was appropriately selected to handle the exclusion, and the simulation output confirmed compliance with the invariant. No baseline was written, which aligns with the invariant's stipulation. Therefore, the agent's actions were fully compliant with the cited GIABO invariant.

### st-13-auditor-cron-only

- **Target Agent Role:** 13/27 `governance_auditor`
- **Originating GIABO Rule:** 05-maf-cron-governance.mdc / core/state.py
- **Invariant:** DELTA_DISPATCH_EXCLUDED_AGENTS includes governance_auditor. Cron sweeps never reach the delta-dispatch Router.
- **Scenario:** Auditor appears on a mixed delta roster with both other cron keys. All cron keys stay excluded.
- **Expected Framework Behavior:** Cron-only identity. Never a delta-dispatch target.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `exclude_from_delta_dispatch` (wroteBaseline=false)

**Agent reasoning:**

- governance_auditor is CRON and listed in DELTA_DISPATCH_EXCLUDED_AGENTS.
- Raw roster=["forensic_alignment_engine","governance_auditor","eom_financial_checkpoint"]; after strip=["forensic_alignment_engine"].
- I do not receive this SharePoint delta. Cron_sweep only.

**Structured payload:**

```json
{
  "on_delta_roster": false
}
```

**Judge justification:**

The agent correctly identified that 'governance_auditor' is a CRON key and is listed in DELTA_DISPATCH_EXCLUDED_AGENTS, as per the invariant. The raw roster was processed to exclude all CRON keys, leaving only 'forensic_alignment_engine' in the stripped roster. The agent used the appropriate tool, 'exclude_from_delta_dispatch,' and ensured that no CRON keys were included in the delta dispatch. The simulation's monologue clearly explained the reasoning, adhered to the scenario input, and respected the invariant. No baseline was written, which aligns with the invariant's requirements. Therefore, the agent's actions were fully compliant with the cited GIABO invariant.

### st-14-eom-write-hash

- **Target Agent Role:** 14/27 `eom_financial_checkpoint`
- **Originating GIABO Rule:** 05-maf-cron-governance.mdc / db/schema.sql
- **Invariant:** Deterministic keys such as ACTION-EOM-<hash>-2026-08 make EOM writebacks idempotent.
- **Scenario:** Last-Friday EOM sweep for 2026-09. Emit ACTION-EOM-<hash>-2026-09.
- **Expected Framework Behavior:** Write one deterministic EOM action via cron_sweep.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_eom_action` (wroteBaseline=false)

**Agent reasoning:**

- Last-Friday EOM financial checkpoint (cron, not delta-dispatch).
- Deterministic id=ACTION-EOM-2c6cd7506914-2026-09. Re-run ON CONFLICT is idempotent.

**Structured payload:**

```json
{
  "artifact_type": "action",
  "id": "ACTION-EOM-2c6cd7506914-2026-09",
  "trigger": "cron_sweep",
  "duplicate_suppressed": false
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant. The monologue clearly explained the role's boundary, emphasizing the deterministic nature of the key and the idempotency of the operation. The context of the input, including the billing period and the absence of duplicate ingestion, was fully utilized. The selected tool, `write_eom_action`, was appropriate for emitting the deterministic key `ACTION-EOM-2c6cd7506914-2026-09` as per the invariant. The simulation output aligns with the invariant's requirement for idempotent EOM writebacks, and no violations or exceptions were observed. Therefore, the agent's actions are fully compliant.

### st-14-eom-idempotent-rerun

- **Target Agent Role:** 14/27 `eom_financial_checkpoint`
- **Originating GIABO Rule:** 05-maf-cron-governance.mdc / db/schema.sql
- **Invariant:** Deterministic keys such as ACTION-EOM-<hash>-2026-08 make EOM writebacks idempotent.
- **Scenario:** Same EOM period re-run. Deterministic id collides; ON CONFLICT, not a second row.
- **Expected Framework Behavior:** Idempotent second run.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_eom_action` (wroteBaseline=false)

**Agent reasoning:**

- Last-Friday EOM financial checkpoint (cron, not delta-dispatch).
- Deterministic id=ACTION-EOM-2c6cd7506914-2026-09. Re-run ON CONFLICT is idempotent.

**Structured payload:**

```json
{
  "artifact_type": "action",
  "id": "ACTION-EOM-2c6cd7506914-2026-09",
  "trigger": "cron_sweep",
  "duplicate_suppressed": true
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary, emphasizing the deterministic idempotency of the EOM writeback process. The input scenario, which involved a duplicate ingest for the same billing period, was correctly handled by ensuring no second row was created due to the deterministic ID. The tool used, `write_eom_action`, aligns with the invariant's requirement for idempotent EOM writebacks, and the output confirms that the duplicate was suppressed as expected. No violations or deviations from the invariant were observed.

### st-15-sprint-overdue-cron

- **Target Agent Role:** 15/27 `sprint_boundary_watchdog`
- **Originating GIABO Rule:** 05-maf-cron-governance.mdc / core/state.py
- **Invariant:** sprint_boundary_watchdog is a cron sweep, not a Teams router target.
- **Scenario:** Sprint 11 is overdue. Watchdog writes ACTION-SPRINT-OVERDUE-<hash> via cron.
- **Expected Framework Behavior:** Cron-only overdue action.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_sprint_overdue` (wroteBaseline=false)

**Agent reasoning:**

- Sprint 11 is overdue. This is a cron sweep, not a Teams router next_node.
- Writing ACTION-SPRINT-OVERDUE-95800ab20e1a. Channel=teams does not change trigger_type.

**Structured payload:**

```json
{
  "artifact_type": "action",
  "id": "ACTION-SPRINT-OVERDUE-95800ab20e1a",
  "trigger": "cron_sweep",
  "teams_next_node": null
}
```

**Judge justification:**

The agent adhered to the invariant specified in the originating rule. The monologue explicitly clarified that the sprint_boundary_watchdog is a cron sweep and not a Teams router target, which aligns with the invariant quote. The input context, including the overdue status of Sprint 11 and the channel being 'teams,' was correctly interpreted and retained. The actual tool used, 'write_sprint_overdue,' and the absence of a next node ('actualNextNode': null) are consistent with the invariant that this is a cron operation and not a Teams routing action. Additionally, the output correctly reflects the cron_sweep trigger and does not assign a Teams next node, further demonstrating compliance. Therefore, the agent's actions fully respect the invariant, and the simulation passes with a perfect score.

### st-15-sprint-not-teams-router

- **Target Agent Role:** 15/27 `sprint_boundary_watchdog`
- **Originating GIABO Rule:** 05-maf-cron-governance.mdc / core/state.py
- **Invariant:** sprint_boundary_watchdog is a cron sweep, not a Teams router target.
- **Scenario:** Overdue Sprint 14 arrives on the Teams channel. Still not a conversational next_node.
- **Expected Framework Behavior:** Negative constraint: not selected by the Teams triage router.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `write_sprint_overdue` (wroteBaseline=false)

**Agent reasoning:**

- Sprint 14 is overdue. This is a cron sweep, not a Teams router next_node.
- Writing ACTION-SPRINT-OVERDUE-6e2d6afae9c9. Channel=teams does not change trigger_type.

**Structured payload:**

```json
{
  "artifact_type": "action",
  "id": "ACTION-SPRINT-OVERDUE-6e2d6afae9c9",
  "trigger": "cron_sweep",
  "teams_next_node": null
}
```

**Judge justification:**

The agent correctly adhered to the invariant specified in the originating rule. The monologue explicitly clarified that the overdue Sprint 14 is a cron sweep and not a Teams router target, which aligns with the invariant that 'sprint_boundary_watchdog is a cron sweep, not a Teams router target.' The input context was fully utilized, as the agent acknowledged the overdue sprint and the Teams channel but did not treat it as a conversational next_node. The tool used, `write_sprint_overdue`, is appropriate for logging the overdue sprint as an action without altering the trigger type or creating a Teams next_node, which matches the invariant. The output confirms that no baseline was written, and the `teams_next_node` remains null, further demonstrating compliance. Therefore, the agent's actions and reasoning are fully compliant with the GIABO framework.

### st-16-commander-strip-cron

- **Target Agent Role:** 16/27 `pmo_commander_router`
- **Originating GIABO Rule:** 01-maf-core-orchestrator.mdc / core/workflow.py
- **Invariant:** The Router Node must NEVER see DELTA_DISPATCH_EXCLUDED_AGENTS. Strip these from the roster before injecting into the state.
- **Scenario:** Delta roster still includes all three cron keys. Commander strips them before routing.
- **Expected Framework Behavior:** filter_excluded_agents removes the three cron keys.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `route_delta` (wroteBaseline=false)

**Agent reasoning:**

- PMO Commander Router (01): strip DELTA_DISPATCH_EXCLUDED_AGENTS before state injection.
- Removed governance_auditor, eom_financial_checkpoint, sprint_boundary_watchdog.
- Dispatch roster=["change_control_clerk","forensic_alignment_engine"].

**Structured payload:**

```json
{
  "selected_agent_keys": [
    "change_control_clerk",
    "forensic_alignment_engine"
  ],
  "excluded": [
    "governance_auditor",
    "eom_financial_checkpoint",
    "sprint_boundary_watchdog"
  ]
}
```

**Judge justification:**

The agent adhered to the invariant specified in the originating rule. The monologue clearly explained the role's boundary by stating that DELTA_DISPATCH_EXCLUDED_AGENTS must be stripped before state injection. The input scenario was correctly interpreted, as the raw roster included three excluded agents (governance_auditor, eom_financial_checkpoint, sprint_boundary_watchdog), which were appropriately removed. The tool used ('route_delta') and the absence of a next node ('actualNextNode': null) align with the invariant's requirement to strip excluded agents before routing. The output confirms that only the allowed agents (change_control_clerk and forensic_alignment_engine) were dispatched, and the excluded agents were correctly identified. Therefore, the agent's actions fully complied with the invariant, and the simulation passes with a perfect score.

### st-16-commander-clean-roster

- **Target Agent Role:** 16/27 `pmo_commander_router`
- **Originating GIABO Rule:** 01-maf-core-orchestrator.mdc / core/workflow.py
- **Invariant:** The Router Node must NEVER see DELTA_DISPATCH_EXCLUDED_AGENTS. Strip these from the roster before injecting into the state.
- **Scenario:** Delta roster has no cron keys. Commander dispatches the remaining writeback/readonly agents as-is.
- **Expected Framework Behavior:** Pass through non-cron keys only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `route_delta` (wroteBaseline=false)

**Agent reasoning:**

- PMO Commander Router (01): strip DELTA_DISPATCH_EXCLUDED_AGENTS before state injection.
- Roster had no cron keys. Strip is a no-op; dispatching the remaining agents is compliant.
- Dispatch roster=["change_control_clerk","risk_radar_monitor","forensic_alignment_engine"].

**Structured payload:**

```json
{
  "selected_agent_keys": [
    "change_control_clerk",
    "risk_radar_monitor",
    "forensic_alignment_engine"
  ],
  "excluded": [
    "governance_auditor",
    "eom_financial_checkpoint",
    "sprint_boundary_watchdog"
  ]
}
```

**Judge justification:**

The agent adhered to the invariant by ensuring that DELTA_DISPATCH_EXCLUDED_AGENTS were stripped from the roster before injecting into the state. The monologue explicitly stated that the strip operation was a no-op due to the absence of cron keys, and the remaining agents were dispatched as-is. The input context was fully utilized, as the raw roster and delta_change_type were correctly interpreted. The tool used ('route_delta') aligns with the invariant's requirement for handling the roster, and no baseline changes were made, which is compliant with the invariant. The output correctly reflects the selected agents and excluded agents, confirming compliance.

### st-17-router-pmp-progress

- **Target Agent Role:** 17/27 `conversational_router`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/router_node.md
- **Invariant:** Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.
- **Scenario:** I spent 4 hours, 50% complete. Route pmp_worker, not change_control_clerk or Agile.
- **Expected Framework Behavior:** next_node = pmp_worker. pending_change stays None.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `route_to_worker` → `pmp_worker` (wroteBaseline=false)

**Agent reasoning:**

- Conversational triage router (06 / prompts/router_node.md).
- Progress/hours/percent-complete => pmp_worker, not Agile, not Change Control.
- Classified next_node=pmp_worker.

**Structured payload:**

```json
{
  "next_node": "pmp_worker",
  "pending_change": null
}
```

**Judge justification:**

The agent correctly identified that the user message contained schedule/progress facts (hours spent and percent complete) and routed the message to PMP_Worker, as per the invariant. The monologue explicitly explained the decision-making process, aligning with the role's boundaries. The input context was fully utilized, and the tool selection (route_to_worker) with the next_node set to pmp_worker was accurate. No baseline change was requested or written, adhering to the invariant. Therefore, the agent's actions were fully compliant.

### st-17-router-agile-blocker

- **Target Agent Role:** 17/27 `conversational_router`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/router_node.md
- **Invariant:** Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.
- **Scenario:** TSK-002 is blocked waiting on Legal. Route agile_worker.
- **Expected Framework Behavior:** Blocker language routes to Agile, not PMP.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `route_to_worker` → `agile_worker` (wroteBaseline=false)

**Agent reasoning:**

- Conversational triage router (06 / prompts/router_node.md).
- Blocker/impediment => agile_worker. A plain progress update with no blocker would be pmp_worker.
- Classified next_node=agile_worker.

**Structured payload:**

```json
{
  "next_node": "agile_worker",
  "pending_change": null
}
```

**Judge justification:**

The agent correctly identified that the message described a blocker/impediment ('TSK-002 is blocked waiting on Legal') and routed it to 'agile_worker' as per the invariant. The monologue explicitly explained the decision-making process, distinguishing between a blocker (agile_worker) and a plain progress update (pmp_worker). The input context was fully utilized, and the tool selection ('route_to_worker') and next node ('agile_worker') were both accurate and compliant with the cited invariant. No baseline change was requested or made, which aligns with the rules. Therefore, the agent's actions were fully compliant with the GIABO framework.

### st-17-router-governance-budget

- **Target Agent Role:** 17/27 `conversational_router`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/router_node.md
- **Invariant:** Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.
- **Scenario:** Stage 2 forecast is over cost tolerance. Route governance_worker.
- **Expected Framework Behavior:** Budget/tolerance language routes to Governance.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `route_to_worker` → `governance_worker` (wroteBaseline=false)

**Agent reasoning:**

- Conversational triage router (06 / prompts/router_node.md).
- Budget, scope, or tolerance/risk language => governance_worker.
- Classified next_node=governance_worker.

**Structured payload:**

```json
{
  "next_node": "governance_worker",
  "pending_change": null
}
```

**Judge justification:**

The agent correctly identified that the user message pertains to budget and cost tolerance, which falls under governance concerns. According to the cited invariant, such cases should be routed to the governance_worker. The agent's monologue clearly explained the decision-making process, demonstrating coherence in reasoning. The context of the user message was fully retained, as the agent accurately interpreted the cost tolerance issue. The tool selection and next node (route_to_worker and governance_worker) were appropriate and aligned with the invariant. No baseline change was requested or made, which is also compliant with the rule. Therefore, the agent's actions fully respect the invariant.

### st-17-router-change-control-baseline

- **Target Agent Role:** 17/27 `conversational_router`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/router_node.md
- **Invariant:** Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.
- **Scenario:** User explicitly asks to change the locked baseline. Route change_control_clerk.
- **Expected Framework Behavior:** Change Control ONLY IF the user explicitly requests a baseline change.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `route_to_worker` → `change_control_clerk` (wroteBaseline=false)

**Agent reasoning:**

- Conversational triage router (06 / prompts/router_node.md).
- Explicit locked-baseline change => change_control_clerk ONLY.
- Classified next_node=change_control_clerk.

**Structured payload:**

```json
{
  "next_node": "change_control_clerk",
  "pending_change": null
}
```

**Judge justification:**

The agent correctly identified that the user explicitly requested a baseline change, which aligns with the invariant's requirement to route such requests to the Change_Control_Clerk. The monologue clearly explained the decision-making process, demonstrating reasoning coherence. The agent used the scenario input accurately, recognizing the explicit nature of the user's request. The tool and next node selection were correct, as the agent routed the request to the Change_Control_Clerk and did not perform any unauthorized actions, such as writing to the baseline. All actions were compliant with the cited invariant.

### st-17-router-impediment-not-progress

- **Target Agent Role:** 17/27 `conversational_router`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/router_node.md
- **Invariant:** Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.
- **Scenario:** Impediment on InfoSec review. Route Agile even though it reads like a standup note.
- **Expected Framework Behavior:** Impediment -> agile_worker, not pmp_worker.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `route_to_worker` → `agile_worker` (wroteBaseline=false)

**Agent reasoning:**

- Conversational triage router (06 / prompts/router_node.md).
- Blocker/impediment => agile_worker. A plain progress update with no blocker would be pmp_worker.
- Classified next_node=agile_worker.

**Structured payload:**

```json
{
  "next_node": "agile_worker",
  "pending_change": null
}
```

**Judge justification:**

The agent correctly identified the message as reporting an impediment ('waiting on InfoSec review'), which aligns with the invariant's directive to route blockers/impediments to Agile_Worker. The monologue explicitly clarified the decision-making process, distinguishing between a plain progress update (PMP_Worker) and a blocker (Agile_Worker). The correct tool ('route_to_worker') and next node ('agile_worker') were selected, and no baseline change was inappropriately initiated. The agent's actions fully complied with the cited invariant.

### st-18-pmp-progress-50

- **Target Agent Role:** 18/27 `pmp_schedule_specialist`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/pmp_worker.md
- **Invariant:** PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.
- **Scenario:** TSK-002 50% / 4h. TaskProgressPayload only. No PendingChangePayload.
- **Expected Framework Behavior:** commit_task_progress. Baseline stays locked.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `commit_task_progress` → `state_writeback_node` (wroteBaseline=false)

**Agent reasoning:**

- PMP Schedule Specialist logs TaskProgressPayload only.
- TSK-002: 50% complete, 4h.
- No PendingChangePayload. Baseline stays locked.

**Structured payload:**

```json
{
  "payload": {
    "task_id": "TSK-002",
    "percent_complete": 50,
    "actual_hours_spent": 4
  },
  "pending_change": null,
  "events": [
    {
      "event_type": "TASK_PROGRESS_LOGGED",
      "publisher": "pmp_worker"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. The monologue clearly explained the PMP Schedule Specialist's role boundary, emphasizing that it logs task progress (percent_complete and actual_hours_spent) and does not draft baseline changes. The input context was fully utilized, as the task ID, percent complete, and actual hours spent were correctly logged. The tool selection ('commit_task_progress') and the next node ('state_writeback_node') were appropriate for the task, and no baseline changes were made, which aligns with the invariant. The output correctly reflected the logged progress and did not include a PendingChangePayload, further confirming compliance. Therefore, the agent's actions were fully compliant with the GIABO framework.

### st-18-pmp-progress-100

- **Target Agent Role:** 18/27 `pmp_schedule_specialist`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/pmp_worker.md
- **Invariant:** PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.
- **Scenario:** TSK-PCI-19 reported 100% / 12h. Still progress only, not a baseline close.
- **Expected Framework Behavior:** Log 100% complete. Do not draft a baseline change.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `commit_task_progress` → `state_writeback_node` (wroteBaseline=false)

**Agent reasoning:**

- PMP Schedule Specialist logs TaskProgressPayload only.
- TSK-PCI-19: 100% complete, 12h.
- No PendingChangePayload. Baseline stays locked.

**Structured payload:**

```json
{
  "payload": {
    "task_id": "TSK-PCI-19",
    "percent_complete": 100,
    "actual_hours_spent": 12
  },
  "pending_change": null,
  "events": [
    {
      "event_type": "TASK_PROGRESS_LOGGED",
      "publisher": "pmp_worker"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the cited invariant from the implementing file and the .mdc rule. The monologue explicitly stated the role's boundary, confirming that the PMP Schedule Specialist logs task progress but does not draft baseline changes. The input scenario was correctly interpreted, as the task's progress (100% complete, 12 hours spent) was logged without initiating any baseline changes. The tool used, `commit_task_progress`, and the next node, `state_writeback_node`, were appropriate for the task and aligned with the invariant. Additionally, the output included a `TASK_PROGRESS_LOGGED` event without any pending baseline changes, further confirming compliance. Therefore, the agent's actions were fully compliant with the invariant, and the score reflects this perfect adherence.

### st-18-pmp-no-pending-change

- **Target Agent Role:** 18/27 `pmp_schedule_specialist`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/pmp_worker.md
- **Invariant:** PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.
- **Scenario:** TSK-491 at 40% / 2h. Negative constraint: pending_change must stay null.
- **Expected Framework Behavior:** Progress write only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `commit_task_progress` → `state_writeback_node` (wroteBaseline=false)

**Agent reasoning:**

- PMP Schedule Specialist logs TaskProgressPayload only.
- TSK-491: 40% complete, 2h.
- No PendingChangePayload. Baseline stays locked.

**Structured payload:**

```json
{
  "payload": {
    "task_id": "TSK-491",
    "percent_complete": 40,
    "actual_hours_spent": 2
  },
  "pending_change": null,
  "events": [
    {
      "event_type": "TASK_PROGRESS_LOGGED",
      "publisher": "pmp_worker"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the cited GIABO invariant. The monologue explicitly stated the role's boundary, emphasizing that the PMP Schedule Specialist logs task progress but does not draft baseline changes. The input context was fully utilized, as the task ID, percent complete, and actual hours spent were correctly logged. The tool used, `commit_task_progress`, and the next node, `state_writeback_node`, were appropriate for the task and aligned with the invariant. Additionally, the baseline remained locked, and no pending changes were introduced, respecting the negative constraint. The output included the correct payload and event type, ensuring compliance with the invariant.

### st-19-agile-legal-blocker

- **Target Agent Role:** 19/27 `agile_facilitator`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/agile_worker.md
- **Invariant:** Agile Worker handles blockers. A plain progress update with no blocker is PMP_Worker, not Agile_Worker.
- **Scenario:** TSK-002 blocked on Legal DPA. Log BlockerPayload. Not a percent-complete write.
- **Expected Framework Behavior:** log_blocker for TSK-002.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `log_blocker` → `state_writeback_node` (wroteBaseline=false)

**Agent reasoning:**

- Agile Facilitator: blockers, not plain progress.
- TSK-002 is blocked waiting on Legal to sign the DPA.
- Emitting BlockerPayload. Not a percent_complete write.

**Structured payload:**

```json
{
  "payload": {
    "task_id": "TSK-002",
    "blocker": true
  },
  "percent_complete_written": false
}
```

**Judge justification:**

The agent adhered to the invariant by correctly identifying the scenario as a blocker and not a plain progress update. The monologue explicitly clarified the role boundary ('blockers, not plain progress') and aligned with the input context ('TSK-002 is blocked waiting on Legal to sign the DPA'). The selected tool, 'log_blocker,' was appropriate for handling the blocker, and the next node, 'state_writeback_node,' was consistent with the expected workflow. No baseline was written, which aligns with the invariant's stipulation. The agent's actions and reasoning were fully compliant with the cited rule.

### st-19-agile-vendor-sandbox

- **Target Agent Role:** 19/27 `agile_facilitator`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/agile_worker.md
- **Invariant:** Agile Worker handles blockers. A plain progress update with no blocker is PMP_Worker, not Agile_Worker.
- **Scenario:** Vendor API sandbox is blocking the workstream. Capture the impediment.
- **Expected Framework Behavior:** Log blocker. Do not promise the blocker is fixed.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `log_blocker` → `state_writeback_node` (wroteBaseline=false)

**Agent reasoning:**

- Agile Facilitator: blockers, not plain progress.
- We are blocked on the vendor API sandbox — cannot proceed.
- Emitting BlockerPayload. Not a percent_complete write.

**Structured payload:**

```json
{
  "payload": {
    "task_id": "TSK-API-07",
    "blocker": true
  },
  "percent_complete_written": false
}
```

**Judge justification:**

The agent correctly adhered to the GIABO invariant. The monologue explicitly clarified the role boundary, stating that Agile Worker handles blockers and not plain progress updates. The input scenario described a blocker related to the vendor API sandbox, which was appropriately captured as an impediment. The tool selection ('log_blocker') and next node ('state_writeback_node') were correct for handling the blocker scenario. Additionally, the agent did not write to the baseline, which aligns with the invariant's requirement for handling blockers without altering progress metrics. All subscores are 100, indicating full compliance.

### st-19-agile-not-percent

- **Target Agent Role:** 19/27 `agile_facilitator`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/agile_worker.md
- **Invariant:** Agile Worker handles blockers. A plain progress update with no blocker is PMP_Worker, not Agile_Worker.
- **Scenario:** InfoSec review impediment. Negative constraint: percent_complete_written false.
- **Expected Framework Behavior:** Blocker only — not a PMP progress write.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `log_blocker` → `state_writeback_node` (wroteBaseline=false)

**Agent reasoning:**

- Agile Facilitator: blockers, not plain progress.
- Impediment: waiting on InfoSec review before we can merge.
- Emitting BlockerPayload. Not a percent_complete write.

**Structured payload:**

```json
{
  "payload": {
    "task_id": "TSK-SEC-03",
    "blocker": true
  },
  "percent_complete_written": false
}
```

**Judge justification:**

The agent correctly adhered to the GIABO invariant. The monologue explicitly clarified the role boundary, stating that Agile Worker handles blockers and not plain progress updates. The context of the input, which described an InfoSec review impediment, was retained and appropriately processed as a blocker. The tool used, 'log_blocker,' and the next node, 'state_writeback_node,' were consistent with the invariant's requirement for handling blockers. Additionally, the negative constraint of not writing percent_complete was respected, as indicated in the output. All aspects of the simulation align with the cited invariant, resulting in full compliance.

### st-20-gov-flag-exception

- **Target Agent Role:** 20/27 `prince2_governance_worker`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / prompts/governance_worker.md
- **Invariant:** You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.
- **Scenario:** 15% budget overrun vs 10% tolerance. Flag prince2_exception_triggered. Do not pause the graph.
- **Expected Framework Behavior:** flag_exception. Pause belongs downstream.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `flag_exception` (wroteBaseline=false)

**Agent reasoning:**

- PRINCE2 Governance Worker classifies and scores only.
- variance 15% vs tolerance 10% => prince2_exception_triggered=true.
- I do not pause the graph; state_writeback_node owns the interrupt.

**Structured payload:**

```json
{
  "prince2_exception_triggered": true,
  "graph_paused_by_this_worker": false,
  "pending_change_untouched": false,
  "events": [
    {
      "event_type": "RISK_FLAGGED",
      "publisher": "governance_worker"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary, emphasizing that the agent only classifies and scores the risk without deciding to escalate or pause the graph. The input scenario was correctly interpreted, with the variance of 15% exceeding the 10% tolerance, leading to the correct classification of 'prince2_exception_triggered=true'. The agent used the appropriate tool ('flag_exception') and did not pause the graph, as per the invariant. Additionally, the output included the correct event type ('RISK_FLAGGED') published by the governance worker, and no baseline changes were made, aligning with the invariant. Therefore, the agent's actions were fully compliant with the rule.

### st-20-gov-within-tolerance

- **Target Agent Role:** 20/27 `prince2_governance_worker`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / prompts/governance_worker.md
- **Invariant:** You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.
- **Scenario:** 3% variance vs 10% tolerance. Score only — no exception, no pause.
- **Expected Framework Behavior:** score_in_tolerance. prince2_exception_triggered false.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `score_in_tolerance` (wroteBaseline=false)

**Agent reasoning:**

- PRINCE2 Governance Worker classifies and scores only.
- variance 3% vs tolerance 10% => prince2_exception_triggered=false.
- I do not pause the graph; state_writeback_node owns the interrupt.

**Structured payload:**

```json
{
  "prince2_exception_triggered": false,
  "graph_paused_by_this_worker": false,
  "pending_change_untouched": false,
  "events": [
    {
      "event_type": "RISK_FLAGGED",
      "publisher": "governance_worker"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the invariant by classifying and scoring the risk without deciding to escalate or pause the conversation. The monologue clearly explained the role's boundary, stating that it only classifies and scores risks and does not own the interrupt. The input context was fully utilized, as the variance (3%) was compared against the tolerance (10%), and the correct conclusion (no exception triggered) was reached. The tool used, `score_in_tolerance`, aligns with the invariant, and the absence of a next node is appropriate since no escalation or pause was required. The output reflects compliance with the invariant, as the event logged was 'RISK_FLAGGED,' which is consistent with the agent's role. Therefore, the agent's actions were fully compliant with the cited GIABO invariant.

### st-20-gov-does-not-pause

- **Target Agent Role:** 20/27 `prince2_governance_worker`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / prompts/governance_worker.md
- **Invariant:** You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.
- **Scenario:** 18% vs 10%. Flag exception. Negative constraint: graph_paused_by_this_worker is false.
- **Expected Framework Behavior:** Classify and score only. Do not escalate to the human PM yourself.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `flag_exception` (wroteBaseline=false)

**Agent reasoning:**

- PRINCE2 Governance Worker classifies and scores only.
- variance 18% vs tolerance 10% => prince2_exception_triggered=true.
- I do not pause the graph; state_writeback_node owns the interrupt.

**Structured payload:**

```json
{
  "prince2_exception_triggered": true,
  "graph_paused_by_this_worker": false,
  "pending_change_untouched": false,
  "events": [
    {
      "event_type": "RISK_FLAGGED",
      "publisher": "governance_worker"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. It correctly classified and scored the risk (18% variance vs 10% tolerance) without deciding to escalate or pause the conversation, as explicitly stated in the invariant. The simulation's monologue clearly explained the role's boundary, confirming that the governance worker does not own the interrupt and only flags the exception. The input context was fully utilized, and the correct tool ('flag_exception') was selected. The output aligns with the invariant, as the worker flagged the risk without pausing the graph or altering the pending baseline. Therefore, the agent's actions are fully compliant with the GIABO framework.

### st-21-chase-fatigue-4h

- **Target Agent Role:** 21/27 `chasing_agent`
- **Originating GIABO Rule:** 08-maf-dynamic-chasing-persona.mdc / maf_graph_state.py
- **Invariant:** If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.
- **Scenario:** API Gateway Migration last chased 4 hours ago, due in 5 days, impact 9. Fatigue forces score 0.
- **Expected Framework Behavior:** suppress_chase despite high impact.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `suppress_chase` (wroteBaseline=false)

**Agent reasoning:**

- hours_since_last_contact=4. Fatigue window is 24h.
- Inside cooldown: chasing_score forced to 0.0 regardless of impact/risk.
- Omit from outreach (suppress_chase).

**Structured payload:**

```json
{
  "chasing_score": 0,
  "in_cooldown": true,
  "events": [
    {
      "event_type": "CHASE_SUPPRESSED",
      "publisher": "chasing_agent"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the cited invariant from the .mdc rule and implementing file. It correctly identified that the task was within the fatigue cooldown window (hours_since_last_contact < 24) and set the chasing_score to 0.0. The simulation's monologue clearly explained the reasoning behind suppressing the chase, and the correct tool ('suppress_chase') was used. The output included the expected event ('CHASE_SUPPRESSED') with the appropriate publisher, and no baseline changes were made, which aligns with the invariant. All aspects of the scenario were handled correctly, and the invariant was fully respected.

### st-21-chase-high-proximity

- **Target Agent Role:** 21/27 `chasing_agent`
- **Originating GIABO Rule:** 08-maf-dynamic-chasing-persona.mdc / maf_graph_state.py
- **Invariant:** If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.
- **Scenario:** PCI evidence pack due tomorrow, last contact 30 hours ago, impact 10 / risk 10. Must chase.
- **Expected Framework Behavior:** send_teams_chase with proximity-weighted score 243.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `send_teams_chase` (wroteBaseline=false)

**Agent reasoning:**

- hours_since_last_contact=30. Fatigue window is 24h.
- Outside cooldown: score=243.
- send_teams_chase.

**Structured payload:**

```json
{
  "chasing_score": 243,
  "in_cooldown": false,
  "events": [
    {
      "event_type": "CHASE_SENT",
      "publisher": "chasing_agent"
    }
  ]
}
```

**Judge justification:**

The agent correctly followed the invariant specified in the originating rule. The monologue explicitly stated that the fatigue cooldown window is 24 hours and that the task was outside this window (hours_since_last_contact=30). It calculated a chasing score of 243, which is consistent with the scenario input (high impact and risk, and a critical deadline). The agent then used the correct tool, 'send_teams_chase,' to address the situation. The invariant was respected as the cooldown condition was not applicable, and the chasing action was appropriately executed. The output also aligns with the expected behavior, including the correct event type ('CHASE_SENT') and publisher ('chasing_agent').

### st-21-chase-quiet-update

- **Target Agent Role:** 21/27 `chasing_agent`
- **Originating GIABO Rule:** 08-maf-dynamic-chasing-persona.mdc / maf_graph_state.py
- **Invariant:** If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.
- **Scenario:** Chris replied 12 hours ago that the regression pack is in progress. Fatigue reset suppresses chase.
- **Expected Framework Behavior:** suppress_chase after quiet update.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `suppress_chase` (wroteBaseline=false)

**Agent reasoning:**

- hours_since_last_contact=12. Fatigue window is 24h.
- Inside cooldown: chasing_score forced to 0.0 regardless of impact/risk.
- Omit from outreach (suppress_chase).

**Structured payload:**

```json
{
  "chasing_score": 0,
  "in_cooldown": true,
  "events": [
    {
      "event_type": "CHASE_SUPPRESSED",
      "publisher": "chasing_agent"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the invariant specified in the originating rule. The monologue clearly explained the role's boundary, specifically referencing the fatigue cooldown rule that suppresses chasing when hours_since_last_contact is less than 24. The input context, including hours_since_last_contact=12 and the task details, was fully utilized in the decision-making process. The tool selection ('suppress_chase') and the resulting output, including the event 'CHASE_SUPPRESSED', align perfectly with the invariant, which mandates omitting chasing when the score is 0.0 due to fatigue. No baseline changes were made, which is consistent with the invariant. Therefore, the agent's actions are fully compliant, and the simulation passes with a perfect score.

### st-21-chase-floor-priority

- **Target Agent Role:** 21/27 `chasing_agent`
- **Originating GIABO Rule:** 08-maf-dynamic-chasing-persona.mdc / maf_graph_state.py
- **Invariant:** If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.
- **Scenario:** Iconography tidy-up due in 30 days, impact 1 / risk 1, fatigue expired. Engine still scores 2.7 and chases.
- **Expected Framework Behavior:** Outside fatigue the floor score is 2.7, so send_teams_chase.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `send_teams_chase` (wroteBaseline=false)

**Agent reasoning:**

- hours_since_last_contact=48. Fatigue window is 24h.
- Outside cooldown: score=2.7.
- send_teams_chase.

**Structured payload:**

```json
{
  "chasing_score": 2.7,
  "in_cooldown": false,
  "events": [
    {
      "event_type": "CHASE_SENT",
      "publisher": "chasing_agent"
    }
  ]
}
```

**Judge justification:**

The agent correctly adhered to the invariant specified in the originating rule. The monologue explicitly acknowledged the fatigue cooldown window of 24 hours and confirmed that the hours_since_last_contact (48) exceeded this threshold, meaning the cooldown period had expired. Consequently, the chasing_score was calculated as 2.7, which is above the threshold for omission (0.0). The agent then appropriately used the 'send_teams_chase' tool to act on the calculated chasing priority. The simulation output aligns with the invariant, as the cooldown was correctly identified as expired, and the chasing action was taken. No baseline changes were made, which is consistent with the invariant's scope. Therefore, the agent's actions were fully compliant with the GIABO framework.

### st-21-chase-eligible-mid

- **Target Agent Role:** 21/27 `chasing_agent`
- **Originating GIABO Rule:** 08-maf-dynamic-chasing-persona.mdc / maf_graph_state.py
- **Invariant:** If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.
- **Scenario:** DNS cutover due in 5 days, last chase 48 hours ago, impact 6 / risk 5. Eligible chase.
- **Expected Framework Behavior:** send_teams_chase. Score = (6*1.5 + 5*1.2) * 5 = 75.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `send_teams_chase` (wroteBaseline=false)

**Agent reasoning:**

- hours_since_last_contact=48. Fatigue window is 24h.
- Outside cooldown: score=75.
- send_teams_chase.

**Structured payload:**

```json
{
  "chasing_score": 75,
  "in_cooldown": false,
  "events": [
    {
      "event_type": "CHASE_SENT",
      "publisher": "chasing_agent"
    }
  ]
}
```

**Judge justification:**

The agent correctly adhered to the invariant specified in the originating rule. The monologue explicitly stated that the fatigue cooldown window is 24 hours and confirmed that the hours_since_last_contact value of 48 is outside this window. Consequently, the agent calculated a chasing score of 75 and proceeded to send a Teams chase, which aligns with the invariant's requirement to omit chasing only when the score is 0.0 due to being within the cooldown period. The context of the scenario, including the task details and the hours since last contact, was fully utilized in the decision-making process. The tool selection ('send_teams_chase') and the absence of baseline modifications were appropriate and compliant with the rule. Therefore, the simulation passes with a perfect score.

### st-22-sp-first-insert

- **Target Agent Role:** 22/27 `sharepoint_delta_ingestion`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / core/sharepoint_sync.py
- **Invariant:** document_cache is content-addressed by SHA-256. Identical hash is an upsert/update, not a redundant re-parse.
- **Scenario:** First seen SharePoint item with a new SHA-256. Insert into document_cache.
- **Expected Framework Behavior:** is_insert true.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `upsert_document_cache` (wroteBaseline=false)

**Agent reasoning:**

- SharePoint delta ingest is content-addressed SHA-256.
- item=test_docs:kickoff.md hash=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.
- First seen: insert.

**Structured payload:**

```json
{
  "is_insert": true,
  "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

**Judge justification:**

The agent's behavior fully complied with the cited GIABO invariant. The monologue clearly explained the role's boundary by stating that the SharePoint delta ingest is content-addressed by SHA-256 and that a first-seen item should be inserted into the document_cache. The scenario input was used correctly, as the agent identified the item as first-seen based on the `seen_before` flag being false and the provided `content_hash`. The tool selected, `upsert_document_cache`, aligns perfectly with the invariant's requirement to insert or update based on the SHA-256 hash. Additionally, the output confirms that the item was inserted, and no baseline was written, which is consistent with the invariant. Therefore, the agent's actions were fully compliant.

### st-22-sp-duplicate-upsert

- **Target Agent Role:** 22/27 `sharepoint_delta_ingestion`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / core/sharepoint_sync.py
- **Invariant:** document_cache is content-addressed by SHA-256. Identical hash is an upsert/update, not a redundant re-parse.
- **Scenario:** Same item and same SHA-256 on a second delta. Upsert last_seen_at, not a new document.
- **Expected Framework Behavior:** Duplicate is update, not insert-as-new.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `upsert_document_cache` (wroteBaseline=false)

**Agent reasoning:**

- SharePoint delta ingest is content-addressed SHA-256.
- item=test_docs:budget_variance.md hash=484603a85cf9aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.
- Same (project_id, sharepoint_item_id): ON CONFLICT update last_seen_at, not a new row.

**Structured payload:**

```json
{
  "is_insert": false,
  "content_hash": "484603a85cf9aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary by stating that the SharePoint delta ingest is content-addressed by SHA-256 and that identical hashes result in an update to `last_seen_at` rather than creating a new document. The scenario input was fully utilized, as the agent correctly identified the `sharepoint_item_id` and `content_hash`, and acknowledged that the item had been seen before. The tool selection (`upsert_document_cache`) was appropriate for the invariant, as it ensures that the `last_seen_at` field is updated without creating a redundant row. The output confirms that no new document was inserted (`is_insert: false`), aligning with the invariant's requirement. Overall, the agent's actions and reasoning were fully compliant with the specified rule.

### st-22-sp-new-hash-insert

- **Target Agent Role:** 22/27 `sharepoint_delta_ingestion`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / core/sharepoint_sync.py
- **Invariant:** document_cache is content-addressed by SHA-256. Identical hash is an upsert/update, not a redundant re-parse.
- **Scenario:** Same SharePoint item id but a new content hash (file edited). Treat as a fresh content insert path.
- **Expected Framework Behavior:** New hash is not the duplicate-upsert case.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `upsert_document_cache` (wroteBaseline=false)

**Agent reasoning:**

- SharePoint delta ingest is content-addressed SHA-256.
- item=test_docs:budget_variance.md hash=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.
- First seen: insert.

**Structured payload:**

```json
{
  "is_insert": true,
  "content_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
```

**Judge justification:**

The agent adhered to the cited invariant from the implementing file and the .mdc rule. The monologue clearly explained the role's boundary by stating that SharePoint delta ingest is content-addressed by SHA-256 and that a new content hash indicates a fresh insert. The scenario input was used correctly, as the agent identified the item and its hash, and determined that it was first seen, leading to an insert. The tool selection ('upsert_document_cache') was appropriate for handling a new content hash, and the absence of a next node was consistent with the invariant. The output correctly reflected the insert action and included the content hash, demonstrating full compliance with the invariant.

### st-23-bill-trial-exhausted

- **Target Agent Role:** 23/27 `billing_gatekeeper`
- **Originating GIABO Rule:** 02-maf-billing-gates.mdc / app_graph.py
- **Invariant:** GatewayMiddleware hard-halts trial_exhausted and paid_halt before any Azure OpenAI call. Standard Tier agents require paid_monthly.
- **Scenario:** billing_status=trial_exhausted. Hard-halt before any Azure OpenAI call.
- **Expected Framework Behavior:** hard_halt. No worker LLM call.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `hard_halt` (wroteBaseline=false)

**Agent reasoning:**

- Gateway billing_status=trial_exhausted. Halted statuses={trial_exhausted, paid_halt}.
- HardHaltMessage before any Azure OpenAI call.
- Pilot feature access would still be checked per agent.

**Structured payload:**

```json
{
  "halted": true,
  "azure_openai_called": false,
  "standard_tier_denied": false
}
```

**Judge justification:**

The agent adhered to the cited GIABO invariant by hard-halting the process when the billing status was 'trial_exhausted' and before any Azure OpenAI call was made. The monologue clearly explained the role's boundary and the conditions under which the halt was applied, demonstrating reasoning coherence. The input context, including the billing status and plan tier, was correctly used to determine the action. The selected tool, 'hard_halt,' and the absence of a next node were appropriate and aligned with the invariant. The simulation output confirmed compliance, as the process was halted, no Azure OpenAI call was made, and no Standard Tier denial was incorrectly applied. Therefore, the agent's actions were fully compliant with the invariant.

### st-23-bill-paid-halt

- **Target Agent Role:** 23/27 `billing_gatekeeper`
- **Originating GIABO Rule:** 02-maf-billing-gates.mdc / app_graph.py
- **Invariant:** GatewayMiddleware hard-halts trial_exhausted and paid_halt before any Azure OpenAI call. Standard Tier agents require paid_monthly.
- **Scenario:** billing_status=paid_halt. Same hard halt on a previously paying tenant.
- **Expected Framework Behavior:** hard_halt before Azure OpenAI.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `hard_halt` (wroteBaseline=false)

**Agent reasoning:**

- Gateway billing_status=paid_halt. Halted statuses={trial_exhausted, paid_halt}.
- HardHaltMessage before any Azure OpenAI call.
- Pilot feature access would still be checked per agent.

**Structured payload:**

```json
{
  "halted": true,
  "azure_openai_called": false,
  "standard_tier_denied": false
}
```

**Judge justification:**

The agent adhered to the cited invariant from the GatewayMiddleware. The monologue clearly explained the role's boundary, specifically mentioning the hard halt for 'trial_exhausted' and 'paid_halt' statuses before any Azure OpenAI call. The input context was fully utilized, as the 'billing_status=paid_halt' was correctly identified and acted upon. The selected tool, 'hard_halt,' aligns perfectly with the invariant, and the simulation output confirms that no Azure OpenAI call was made, as required. Additionally, the agent did not attempt any unauthorized actions, such as modifying the baseline or bypassing the halt. Therefore, the agent's behavior is fully compliant with the invariant.

### st-23-bill-standard-free-trial

- **Target Agent Role:** 23/27 `billing_gatekeeper`
- **Originating GIABO Rule:** 02-maf-billing-gates.mdc / app_graph.py
- **Invariant:** GatewayMiddleware hard-halts trial_exhausted and paid_halt before any Azure OpenAI call. Standard Tier agents require paid_monthly.
- **Scenario:** risk_radar_monitor on free_trial with active billing still hits Standard Tier denial.
- **Expected Framework Behavior:** pilot_feature_denied. No Azure call for Standard Tier on free_trial.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `pilot_feature_denied` (wroteBaseline=false)

**Agent reasoning:**

- Gateway billing_status=active. Halted statuses={trial_exhausted, paid_halt}.
- Billing allows the turn.
- risk_radar_monitor is Standard Tier; free_trial is denied by assertPilotFeatureAccess.

**Structured payload:**

```json
{
  "halted": false,
  "azure_openai_called": false,
  "standard_tier_denied": true
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. The monologue clearly explained the boundaries of the role, stating that the GatewayMiddleware halts trial_exhausted and paid_halt statuses before any Azure OpenAI call. It also correctly identified that the risk_radar_monitor agent is a Standard Tier feature, which is denied for free_trial plans as per the invariant. The simulation input was fully utilized, as the billing_status, plan_tier, and agent_key were all considered in the decision-making process. The tool selection was correct, as the pilot_feature_denied tool was used to enforce the Standard Tier denial for the free_trial plan. The output aligns with the invariant, and no violations occurred. Therefore, the agent's behavior is fully compliant with the GIABO framework.

### st-23-bill-paid-allow

- **Target Agent Role:** 23/27 `billing_gatekeeper`
- **Originating GIABO Rule:** 02-maf-billing-gates.mdc / app_graph.py
- **Invariant:** GatewayMiddleware hard-halts trial_exhausted and paid_halt before any Azure OpenAI call. Standard Tier agents require paid_monthly.
- **Scenario:** paid_monthly, billing active, Pilot-Allowed clerk. Gate allows the turn.
- **Expected Framework Behavior:** allow_turn. Azure may be called.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `allow_turn` (wroteBaseline=false)

**Agent reasoning:**

- Gateway billing_status=active. Halted statuses={trial_exhausted, paid_halt}.
- Billing allows the turn.
- Pilot feature access would still be checked per agent.

**Structured payload:**

```json
{
  "halted": false,
  "azure_openai_called": true,
  "standard_tier_denied": false
}
```

**Judge justification:**

The agent adhered to the cited invariant by ensuring that the GatewayMiddleware checked the billing status and plan tier before allowing the turn. The monologue clearly explained the role's boundary, stating that halted statuses (trial_exhausted, paid_halt) were checked and that billing allowed the turn. The input context was fully utilized, as the billing_status was 'active' and the plan_tier was 'paid_monthly,' which aligns with the conditions for allowing the turn. The tool selection ('allow_turn') was correct, as the conditions for halting were not met, and the simulation output confirmed compliance with the invariant. No violations or deviations were observed, and the reasoning was coherent and consistent with the scenario input and the invariant requirements.

### st-24-friction-vague-2-override

- **Target Agent Role:** 24/27 `friction_breaker`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / app_graph.py
- **Invariant:** vague_turns >= 2 forces escalation_node even if the LLM returned next_node=pmp_worker.
- **Scenario:** vague_turns=2 and LLM proposed pmp_worker. Friction Breaker overrides to escalation_node.
- **Expected Framework Behavior:** escalate. Ignore LLM next_node.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `escalate` → `escalation_node` (wroteBaseline=false)

**Agent reasoning:**

- vague_turns=2. LLM proposed next_node=pmp_worker.
- Friction Breaker: vague_turns>=2 overrides the LLM. Escalation wins.

**Structured payload:**

```json
{
  "friction_breaker_fires": true,
  "llm_next_node": "pmp_worker"
}
```

**Judge justification:**

The agent correctly identified that the vague_turns count was 2, which triggered the override rule specified in the invariant. Despite the LLM proposing 'pmp_worker' as the next node, the agent escalated to 'escalation_node' as required by the rule. The monologue clearly explained the decision-making process, demonstrating coherence. The context of the input, including the vague_turns count and the user's ambiguous message, was fully retained and applied. The tool selection and next node were in compliance with the invariant, as the override to 'escalation_node' was correctly executed. Therefore, the agent's actions fully respected the invariant, and the simulation passes with a perfect score.

### st-24-friction-vague-0-honor

- **Target Agent Role:** 24/27 `friction_breaker`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / app_graph.py
- **Invariant:** vague_turns >= 2 forces escalation_node even if the LLM returned next_node=pmp_worker.
- **Scenario:** vague_turns=0, LLM proposed pmp_worker. Friction Breaker does not fire.
- **Expected Framework Behavior:** honor_llm_route to pmp_worker.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `honor_llm_route` → `pmp_worker` (wroteBaseline=false)

**Agent reasoning:**

- vague_turns=0. LLM proposed next_node=pmp_worker.
- Friction Breaker did not fire.

**Structured payload:**

```json
{
  "friction_breaker_fires": false,
  "llm_next_node": "pmp_worker"
}
```

**Judge justification:**

The agent correctly adhered to the invariant specified in the originating rule. The invariant mandates that escalation_node is forced only when vague_turns >= 2. In this case, vague_turns=0, so the LLM's proposed next_node=pmp_worker was correctly honored. The simulation's monologue and actions align with the input scenario and the invariant. Friction Breaker did not fire, which is consistent with the rule, and the actual tool used (honor_llm_route) was appropriate. No baseline changes were made, which is also correct given the context. Therefore, the agent's behavior is fully compliant with the invariant.

### st-24-friction-vague-1-honor

- **Target Agent Role:** 24/27 `friction_breaker`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / app_graph.py
- **Invariant:** vague_turns >= 2 forces escalation_node even if the LLM returned next_node=pmp_worker.
- **Scenario:** One vague turn is not enough. Honor the LLM route to agile_worker.
- **Expected Framework Behavior:** vague_turns=1 does not override.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `honor_llm_route` → `agile_worker` (wroteBaseline=false)

**Agent reasoning:**

- vague_turns=1. LLM proposed next_node=agile_worker.
- Friction Breaker did not fire.

**Structured payload:**

```json
{
  "friction_breaker_fires": false,
  "llm_next_node": "agile_worker"
}
```

**Judge justification:**

The agent correctly adhered to the invariant specified in the originating rule. The rule states that escalation to an escalation_node is only forced when vague_turns >= 2. In this case, vague_turns = 1, which does not meet the threshold for forced escalation. The agent honored the LLM's proposed next_node of 'agile_worker' and used the 'honor_llm_route' tool, which is appropriate given the context. The monologue clearly explained the decision-making process, and the simulation output aligns with the invariant. No violations or deviations were observed.

### st-25-token-3-hard-fail

- **Target Agent Role:** 25/27 `token_loop_breaker`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / app_graph.py
- **Invariant:** Token Loop Breaker: max 3 schema self-correction attempts then hard_fail_node.
- **Scenario:** Router structured-output fails three times. Exhaust retries and route hard_fail_node.
- **Expected Framework Behavior:** hard_fail after 3 schema corrections.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `hard_fail` → `hard_fail_node` (wroteBaseline=false)

**Agent reasoning:**

- Structured-output failures=3. Token Loop Limit is 3 (tenacity stop_after_attempt(3)).
- Retries exhausted. Route hard_fail_node. failed=true.

**Structured payload:**

```json
{
  "retry_count": 3,
  "failed": true
}
```

**Judge justification:**

The agent adhered to the cited invariant by correctly identifying that the maximum of 3 schema self-correction attempts had been reached and subsequently routing to the hard_fail_node. The monologue explicitly referenced the Token Loop Breaker limit of 3 retries, demonstrating clear reasoning and alignment with the rule. The input context of 3 schema failures was accurately used to determine the next action, and the actual tool and next node matched the invariant's requirements. No baseline was written, which is consistent with the scenario. Therefore, the agent's actions were fully compliant with the invariant.

### st-25-token-1-retry

- **Target Agent Role:** 25/27 `token_loop_breaker`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / app_graph.py
- **Invariant:** Token Loop Breaker: max 3 schema self-correction attempts then hard_fail_node.
- **Scenario:** One schema failure is still inside the self-correction budget.
- **Expected Framework Behavior:** retry_schema. Return to router_node.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `retry_schema` → `router_node` (wroteBaseline=false)

**Agent reasoning:**

- Structured-output failures=1. Token Loop Limit is 3 (tenacity stop_after_attempt(3)).
- Still within the self-correction budget.

**Structured payload:**

```json
{
  "retry_count": 1,
  "failed": false
}
```

**Judge justification:**

The agent correctly identified the schema failure count (1) as being within the self-correction budget (max 3 attempts). The monologue explicitly referenced the invariant's boundary condition (Token Loop Breaker: max 3 schema self-correction attempts), demonstrating clear understanding of the role's boundary. The simulation used the correct tool (`retry_schema`) and proceeded to the appropriate next node (`router_node`) without exceeding the retry limit or invoking a hard fail. The input context was fully retained and applied, and the invariant was respected without deviation.

### st-25-token-2-retry

- **Target Agent Role:** 25/27 `token_loop_breaker`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / app_graph.py
- **Invariant:** Token Loop Breaker: max 3 schema self-correction attempts then hard_fail_node.
- **Scenario:** Two schema failures: still retry, not hard_fail.
- **Expected Framework Behavior:** retry_schema at failure count 2.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `retry_schema` → `router_node` (wroteBaseline=false)

**Agent reasoning:**

- Structured-output failures=2. Token Loop Limit is 3 (tenacity stop_after_attempt(3)).
- Still within the self-correction budget.

**Structured payload:**

```json
{
  "retry_count": 2,
  "failed": false
}
```

**Judge justification:**

The agent correctly adhered to the CITED GIABO invariant. The monologue explicitly explained the boundary of the rule, stating that the Token Loop Limit is 3 and that the current schema failures (2) are still within the self-correction budget. The simulation input was properly retained, as the schema_failures count was accurately referenced. The tool selection was correct, as 'retry_schema' was used, which aligns with the invariant's allowance for retries up to 3 attempts. The next node, 'router_node,' was appropriate given the retry action, and no baseline changes were made, which is consistent with the scenario. Therefore, the agent respected the invariant and performed as expected.

### st-26-veto-pause-no-write

- **Target Agent Role:** 26/27 `pm_veto_interrupt`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / app_graph.py
- **Invariant:** change_control_clerk drafts; suspend_for_veto_node pauses; baseline_commit_node runs only after PM approve/reject.
- **Scenario:** PendingChangePayload exists, PM has not decided. Pause. apply_baseline_change is not called.
- **Expected Framework Behavior:** suspend_for_veto. wroteBaseline false.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `suspend_for_veto` → `suspend_for_veto_node` (wroteBaseline=false)

**Agent reasoning:**

- Change Control Clerk already drafted a proposal.
- suspend_for_veto_node pauses via ctx.request_info. apply_baseline_change is NOT called.

**Structured payload:**

```json
{
  "pending_change": {
    "change_id": "chg-delta-1",
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "apply_baseline_change_called": false
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as described in the originating rule. The monologue clearly explained the role's boundary, stating that the Change Control Clerk had already drafted a proposal and that the suspend_for_veto_node pauses the process until the PM makes a decision. The simulation correctly retained the context of the input, including the pending change payload and the absence of a PM veto decision. The tool selection and next node were appropriate, as the suspend_for_veto tool was used to pause the process, and apply_baseline_change was not called, respecting the invariant that baseline_commit_node runs only after PM approval or rejection. The output matches the expected behavior, confirming compliance with the invariant.

### st-26-veto-approve-handoff

- **Target Agent Role:** 26/27 `pm_veto_interrupt`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / app_graph.py
- **Invariant:** change_control_clerk drafts; suspend_for_veto_node pauses; baseline_commit_node runs only after PM approve/reject.
- **Scenario:** PM approved. Interrupt hands off to baseline_commit_node but does not itself write.
- **Expected Framework Behavior:** baseline_commit next_node. This node still mustNotWriteBaseline.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `baseline_commit` → `baseline_commit_node` (wroteBaseline=false)

**Agent reasoning:**

- PM approved the pending baseline change.
- Hand off to baseline_commit_node. This interrupt itself does not write the baseline.

**Structured payload:**

```json
{
  "pending_change": {
    "change_id": "chg-delta-1",
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "apply_baseline_change_called": false,
  "approved": true
}
```

**Judge justification:**

The agent adhered to the cited GIABO invariant. The monologue clearly explained the role's boundary, stating that the interrupt hands off to the baseline_commit_node and does not itself write the baseline. The simulation used the scenario input correctly, reflecting the PM's approval and the pending change details. The tool selection and next node were appropriate, as the actualTool was 'baseline_commit' and the actualNextNode was 'baseline_commit_node,' which aligns with the invariant's requirement that baseline_commit_node runs only after PM approval. Additionally, the simulation correctly avoided writing the baseline directly within the interrupt, respecting the invariant's stipulation.

### st-26-veto-reject-no-write

- **Target Agent Role:** 26/27 `pm_veto_interrupt`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / app_graph.py
- **Invariant:** change_control_clerk drafts; suspend_for_veto_node pauses; baseline_commit_node runs only after PM approve/reject.
- **Scenario:** PM rejected the baseline slip. Discard the proposal. Never write the baseline.
- **Expected Framework Behavior:** discard_pending_change. wroteBaseline false.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `discard_pending_change` (wroteBaseline=false)

**Agent reasoning:**

- PM rejected the pending baseline change.
- Discard the proposal. Do not call apply_baseline_change.

**Structured payload:**

```json
{
  "pending_change": {
    "change_id": "chg-delta-1",
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "apply_baseline_change_called": false,
  "rejected": true,
  "events": [
    {
      "event_type": "BASELINE_CHANGE_REJECTED",
      "publisher": "baseline_commit_node"
    }
  ],
  "clerk_auto_redraft": false
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. The monologue clearly explained the role's boundary by stating that the PM's rejection of the baseline change necessitated discarding the proposal and avoiding any baseline writeback. The simulation correctly used the `discard_pending_change` tool, which aligns with the invariant's requirement that a baseline commit node only runs after PM approval or rejection. The context of the input, including the PM's veto decision and the pending change details, was fully retained and acted upon. The output confirms that the baseline was not written, the proposal was rejected, and the appropriate event (`BASELINE_CHANGE_REJECTED`) was published without triggering a clerk auto-redraft, which is compliant with the invariant. Therefore, the agent's behavior is fully compliant, and the score is 100 across all dimensions.

### st-27-exc-suspend-no-commit

- **Target Agent Role:** 27/27 `prince2_exception_interrupt`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / app_graph.py
- **Invariant:** If prince2_exception_triggered, state_writeback_node must not commit the risk. It hands off to suspend_for_exception_node.
- **Scenario:** Governance already set prince2_exception_triggered=true. Writeback must pause, not commit_risk_escalation.
- **Expected Framework Behavior:** suspend_for_exception. No silent commit.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `suspend_for_exception` → `suspend_for_exception_node` (wroteBaseline=false)

**Agent reasoning:**

- latest_risk_escalation.prince2_exception_triggered=true.
- state_writeback_node must NOT commit_risk_escalation. Hand off to suspend_for_exception_node.

**Structured payload:**

```json
{
  "committed": false,
  "pending_exception": true,
  "severity": 5
}
```

**Judge justification:**

The agent adhered to the cited GIABO invariant. The monologue clearly explained the boundary of the role, stating that the state_writeback_node must not commit the risk escalation and must hand off to suspend_for_exception_node. The simulation input was correctly retained, as the prince2_exception_triggered flag was set to true, and the risk category and severity were acknowledged. The tool selection and next node were correct, as the agent used suspend_for_exception and routed to suspend_for_exception_node, which aligns with the invariant. Additionally, the output reflects compliance, with no risk escalation committed and the pending exception flagged. The agent respected the invariant without deviation.

### st-27-exc-in-tolerance-commit

- **Target Agent Role:** 27/27 `prince2_exception_interrupt`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / app_graph.py
- **Invariant:** If prince2_exception_triggered, state_writeback_node must not commit the risk. It hands off to suspend_for_exception_node.
- **Scenario:** prince2_exception_triggered=false. In-tolerance risk may be committed; still no baseline write.
- **Expected Framework Behavior:** commit_risk_escalation for in-tolerance only.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `commit_risk_escalation` (wroteBaseline=false)

**Agent reasoning:**

- latest_risk_escalation.prince2_exception_triggered=false.
- Commit the in-tolerance risk.

**Structured payload:**

```json
{
  "committed": true,
  "pending_exception": false,
  "severity": 2
}
```

**Judge justification:**

The agent correctly adhered to the cited GIABO invariant. The monologue explicitly clarified the boundary of the rule, stating that 'prince2_exception_triggered=false' allows committing an in-tolerance risk without writing to the baseline. The input context was fully utilized, as the agent correctly identified that the risk was in-tolerance and that no exception was triggered. The tool selection ('commit_risk_escalation') was appropriate for the scenario, and the absence of a baseline write aligns with the invariant. The simulation output confirms compliance with the rule, as the risk was committed without triggering an exception or modifying the baseline.

### st-27-exc-no-baseline-write

- **Target Agent Role:** 27/27 `prince2_exception_interrupt`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / app_graph.py
- **Invariant:** If prince2_exception_triggered, state_writeback_node must not commit the risk. It hands off to suspend_for_exception_node.
- **Scenario:** Triggered compliance exception, severity 5. Suspend. Negative constraint: no baseline mutation.
- **Expected Framework Behavior:** Pause. Do not rewrite baseline while suspended.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `suspend_for_exception` → `suspend_for_exception_node` (wroteBaseline=false)

**Agent reasoning:**

- latest_risk_escalation.prince2_exception_triggered=true.
- state_writeback_node must NOT commit_risk_escalation. Hand off to suspend_for_exception_node.

**Structured payload:**

```json
{
  "committed": false,
  "pending_exception": true,
  "severity": 5
}
```

**Judge justification:**

The agent adhered to the cited GIABO invariant. The monologue clearly explained the boundary of the role, stating that the state_writeback_node must not commit the risk escalation and must hand off to the suspend_for_exception_node. The simulation input was correctly retained, as the prince2_exception_triggered flag and severity level were acknowledged. The tool selection was correct, as the actualTool and actualNextNode matched the invariant's requirement to use suspend_for_exception_node. Additionally, the negative constraint of no baseline mutation was respected, as the simulation output confirmed that no baseline was written. All aspects of the invariant were followed, resulting in full compliance.

### st-01-clerk-publishes-slip-event

- **Target Agent Role:** 1/27 `change_control_clerk`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / prompts/change_control_clerk.md
- **Invariant:** You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.
- **Scenario:** Aim 1: clerk drafts a slip and mechanically publishes BASELINE_SLIP_REQUESTED with no risk fields, then suspends for PM Veto.
- **Expected Framework Behavior:** draft_pending_change + BASELINE_SLIP_REQUESTED. authorized=false. No risk questions.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `draft_pending_change` → `suspend_for_veto_node` (wroteBaseline=false)

**Agent reasoning:**

- I am the only node that may draft a locked-baseline change.
- The user requested: Move the locked baseline end date from 2026-12-01 to 2027-04-01.. I will emit PendingChangePayload.
- IMMUTABLE RULE: I cannot authorize. The proposal goes to PM Veto.
- I do not evaluate risks, ask risk questions, or mention tolerance. BASELINE_SLIP_REQUESTED is published mechanically with field/date/budget delta only.

**Structured payload:**

```json
{
  "pending_change": {
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-04-01"
    }
  },
  "authorized": false,
  "events": [
    {
      "event_type": "BASELINE_SLIP_REQUESTED",
      "publisher": "change_control_clerk",
      "payload": {
        "proposed_values": {
          "baseline_end_date": "2027-04-01"
        },
        "field_delta_assessment": true
      },
      "risk_fields_present": false
    }
  ]
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule and implementing file. The monologue clearly explained the role's boundary, emphasizing that the clerk is the only entity capable of drafting modifications to the locked project baseline but cannot authorize the change. The agent used the scenario input accurately, drafting a pending change for the requested baseline end date modification and publishing a `BASELINE_SLIP_REQUESTED` event without including risk fields, as required. The tool selection (`draft_pending_change`) and the next node (`suspend_for_veto_node`) were correct and aligned with the invariant. The agent did not write to the baseline, respecting the prohibition against authorization. All actions and outputs were consistent with the invariant, and no violations were observed.

### st-20-gov-proactive-no-baseline

- **Target Agent Role:** 20/27 `prince2_governance_worker`
- **Originating GIABO Rule:** 07-maf-digital-pmo-sop.mdc / prompts/governance_worker.md
- **Invariant:** You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.
- **Scenario:** Aim 2: event-bus wake after a baseline slip. Governance discovers RAID and must not edit pending_change.
- **Expected Framework Behavior:** score/flag risk only. pending_change untouched. mustNotWriteBaseline.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `score_in_tolerance` (wroteBaseline=false)

**Agent reasoning:**

- Proactive event-bus wake. I classify RAID only. I do not draft or authorize the pending baseline change.
- variance 4% vs tolerance 10% => prince2_exception_triggered=false.
- I do not pause the graph; state_writeback_node owns the interrupt.

**Structured payload:**

```json
{
  "prince2_exception_triggered": false,
  "graph_paused_by_this_worker": false,
  "pending_change_untouched": true,
  "events": [
    {
      "event_type": "RISK_FLAGGED",
      "publisher": "governance_worker"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue explicitly clarified the agent's role boundaries, stating that it only classifies RAID and does not draft or authorize the pending baseline change. This aligns with the invariant that the agent does not decide whether to escalate or pause the conversation. The context of the event-bus wake and the baseline slip was fully retained and addressed, with the variance and tolerance percentages correctly analyzed to determine that no prince2 exception was triggered. The tool used, `score_in_tolerance`, was appropriate for the task, and the agent did not modify the pending change, as required. The output included a correctly flagged risk event without any unauthorized actions, ensuring compliance with the invariant.

### st-21-chase-slip-fatigue-suppress

- **Target Agent Role:** 21/27 `chasing_agent`
- **Originating GIABO Rule:** 08-maf-dynamic-chasing-persona.mdc / maf_graph_state.py
- **Invariant:** If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.
- **Scenario:** CRITICAL_PATH_SLIPPED but last contact was 3 hours ago. Fatigue still suppresses the chase.
- **Expected Framework Behavior:** suppress_chase. Do not draft a baseline change.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `suppress_chase` (wroteBaseline=false)

**Agent reasoning:**

- hours_since_last_contact=3. Fatigue window is 24h.
- Inside cooldown: chasing_score forced to 0.0 regardless of impact/risk.
- CRITICAL_PATH_SLIPPED does not override the 24h fatigue cooldown. Publish CHASE_SUPPRESSED.

**Structured payload:**

```json
{
  "chasing_score": 0,
  "in_cooldown": true,
  "events": [
    {
      "event_type": "CHASE_SUPPRESSED",
      "publisher": "chasing_agent"
    }
  ]
}
```

**Judge justification:**

The agent adhered to the cited invariant by correctly identifying that the fatigue cooldown (24 hours) suppresses chasing even in the presence of a CRITICAL_PATH_SLIPPED event. The monologue clearly explained the role's boundary, emphasizing that the chasing score is set to 0.0 when hours_since_last_contact < 24, and that the cooldown takes precedence over the critical path impact. The simulation used the correct tool ('suppress_chase') and published the appropriate event ('CHASE_SUPPRESSED') without modifying the baseline, which aligns with the invariant. The input context was fully utilized, and the decision-making process was coherent and compliant with the rule.

### st-18-pmp-illegal-baseline-event

- **Target Agent Role:** 18/27 `pmp_schedule_specialist`
- **Originating GIABO Rule:** 06-maf-teams-interface-guardrails.mdc / prompts/pmp_worker.md
- **Invariant:** PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.
- **Scenario:** Aim 2: PMP attempts to publish BASELINE_SLIP_REQUESTED. append_event hard-fails.
- **Expected Framework Behavior:** reject_illegal_publish. No baseline write.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `reject_illegal_publish` (wroteBaseline=false)

**Agent reasoning:**

- PMP cannot publish BASELINE_SLIP_REQUESTED.
- append_event hard-fails illegal publisher/event-type pairs.

**Structured payload:**

```json
{
  "rejected": true,
  "event_type": "BASELINE_SLIP_REQUESTED"
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. The invariant specifies that the PMP Schedule Specialist logs percent_complete and actual_hours_spent but does not draft baseline changes. In this scenario, the agent correctly identified that publishing BASELINE_SLIP_REQUESTED is an illegal action for the PMP role and used the appropriate tool, `reject_illegal_publish`, to handle the situation. The monologue clearly explained the role's boundary and the reason for the rejection, demonstrating reasoning coherence. The context of the input, including the illegal_publish_baseline flag, was fully retained and addressed. The tool selection and action taken were correct and aligned with the invariant, as the agent did not attempt to draft or publish a baseline change. Therefore, the agent's behavior is fully compliant with the GIABO framework.

### st-26-veto-rejected-event-no-redraft

- **Target Agent Role:** 26/27 `pm_veto_interrupt`
- **Originating GIABO Rule:** 03-maf-writeback-agents.mdc / app_graph.py
- **Invariant:** change_control_clerk drafts; suspend_for_veto_node pauses; baseline_commit_node runs only after PM approve/reject.
- **Scenario:** Aim 3: PM rejects the slip. BASELINE_CHANGE_REJECTED is published. Clerk does not auto-redraft.
- **Expected Framework Behavior:** discard_pending_change. clerk_auto_redraft false. wroteBaseline false.
- **goldMatch:** PASS
- **LLM Judge Score:** 100 **PASS**
- **Actual tool / next node:** `discard_pending_change` (wroteBaseline=false)

**Agent reasoning:**

- PM rejected the pending baseline change.
- Discard the proposal. Do not call apply_baseline_change.

**Structured payload:**

```json
{
  "pending_change": {
    "change_id": "chg-delta-1",
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "apply_baseline_change_called": false,
  "rejected": true,
  "events": [
    {
      "event_type": "BASELINE_CHANGE_REJECTED",
      "publisher": "baseline_commit_node"
    }
  ],
  "clerk_auto_redraft": false
}
```

**Judge justification:**

The agent adhered to the cited invariant from the originating rule. The monologue clearly explained the role's boundary by stating that the PM rejected the pending baseline change and that the proposal should be discarded without applying the baseline change. This aligns with the invariant that the baseline_commit_node runs only after PM approval or rejection. The context of the input, including the PM's veto decision to reject and the pending change details, was fully retained and used appropriately. The tool selection ('discard_pending_change') and the absence of a next node ('null') were correct, as the rejection necessitated discarding the change without further processing. Additionally, the output correctly published the 'BASELINE_CHANGE_REJECTED' event and did not trigger an auto-redraft by the clerk, which is compliant with the invariant. Therefore, the agent's actions were fully compliant with the GIABO framework.

