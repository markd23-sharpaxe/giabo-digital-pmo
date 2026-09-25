# GIABO Human Review Report

Narrative PMO stories for executive sign-off. This is a curated subset (2–3 stories per key role), not the full bulk dump — see `tests/evals/results/masterReviewReport.md` for every scenario.

- Bulk eval run: `615100c3-e2c9-4114-927f-b3feece815cb`
- Compiled from: 2026-09-22T12:40:09.369Z
- Judge model: `rapid-gpt-4o`
- Stories: 2–3 per key role (7 roles)

Tick **Approved** or **Needs Tuning** on each story before launch. Tuning means the persona, routing, or message draft should change — not that the eval harness failed.

## Contents

- [Chaser](#chaser)
- [Risk Agent](#risk-agent)
- [PMP Worker](#pmp-worker)
- [Agile Worker](#agile-worker)
- [Governance Worker](#governance-worker)
- [Change Control Clerk](#change-control-clerk)
- [Router](#router)

## Chaser

### Story 1: Redundant chase suppression

*Eval id: `redundant-chase-fatigue-4h`*

**Scenario Title & Context:**

Task due in 5 days, last chase was 4 hours ago, API Gateway Migration assigned to Sarah (Backend), critical-path impact 9/10.

**Agent Persona & Rule Applied:**

Dynamic Chasing Agent. GIABO rule `08-maf-dynamic-chasing-persona.mdc` via `maf_graph_state.py`:

> If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.

**Exact Agent Output / Natural Language Draft:**

> No Teams message sent. Reason: last contact was 4 hours ago (inside the 24-hour fatigue cooldown), so chasing_score is 0.0.

Structured payload:

```json
{
  "chasing_score": 0,
  "in_cooldown": true,
  "ranked_task_ids": []
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

**reasoningCoherence:** The agent correctly calculated the chasing score as 0 due to the fatigue rule (hours_since_last_contact < 24). It also adhered to the formula for scoring when applicable, but since the fatigue rule zeroed out the score, no further calculations were necessary.

**contextRetention:** The agent accurately used the hours_since_last_contact (4 hours) to determine that the task was within the fatigue window (24 hours) and correctly suppressed chasing.

**toolSelectionCorrectness:** The agent appropriately selected 'suppress_chase' because the fatigue rule applied (hours_since_last_contact < 24). No other tools were used, and no outreach was made, which aligns with the requirements.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 2: Maximum fatigue expiration and high proximity

*Eval id: `fatigue-expired-high-proximity`*

**Scenario Title & Context:**

Task due tomorrow, last chase was 30 hours ago, PCI evidence pack for go-live assigned to Alex (Payments), critical-path impact 10/10.

**Agent Persona & Rule Applied:**

Dynamic Chasing Agent. GIABO rule `08-maf-dynamic-chasing-persona.mdc` via `maf_graph_state.py`:

> If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.

**Exact Agent Output / Natural Language Draft:**

> Alex (Payments) — PCI evidence pack for go-live is due tomorrow. This sits on the critical path (impact 10/10). What's the current status, and is anything blocking you from hitting that date?

Structured payload:

```json
{
  "chasing_score": 243,
  "in_cooldown": false,
  "ranked_task_ids": [
    "TSK-CRITICAL-TOMORROW"
  ]
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The agent correctly calculated the chasing score using the formula: (critical_path_impact * 1.5 + linked_risks_severity * 1.2) * max(1, 10 - days_to_deadline). For the task 'TSK-CRITICAL-TOMORROW', the score was computed as 243, which aligns with the provided formula and inputs. The agent also verified that hours_since_last_contact (30) exceeded the fatigue threshold of 24 hours, ensuring no suppression of chasing due to fatigue. The tool 'send_teams_chase' was appropriately selected and executed for the task with the highest score, and no other tasks were present to rank. Context retention was demonstrated by correctly using hours_since_last_contact and the absence of any assignee reply in the decision-making process. All invariants were upheld, and the reasoning and actions were coherent and correct.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 3: Quiet update / recent manual interaction

*Eval id: `quiet-update-resets-fatigue`*

**Scenario Title & Context:**

Task due in 3 days, last chase was 12 hours ago, Regression pack for release 12 assigned to Chris (QA), critical-path impact 7/10. Chris (QA) last said: “I'm working on it — regression pack is in progress and I'll have the first pass by tomorrow.”

**Agent Persona & Rule Applied:**

Dynamic Chasing Agent. GIABO rule `08-maf-dynamic-chasing-persona.mdc` via `maf_graph_state.py`:

> If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.

**Exact Agent Output / Natural Language Draft:**

> No Teams message sent. Reason: last contact was 12 hours ago (inside the 24-hour fatigue cooldown), so chasing_score is 0.0.

Structured payload:

```json
{
  "chasing_score": 0,
  "in_cooldown": true,
  "ranked_task_ids": []
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The agent correctly identified that the hours_since_last_contact (12 hours) is less than the 24-hour fatigue threshold, which zeroes out the chasing score. It adhered to the rule that no outreach should occur when the fatigue filter is triggered, and appropriately selected the suppress_chase tool. The reasoning was coherent, as it calculated the chasing score based on the formula provided but correctly applied the fatigue rule to zero out the score. Context retention was demonstrated by considering the hours_since_last_contact and the assignee's reply, which indicated progress on the task. Tool selection was accurate, as suppress_chase was used due to the fatigue condition being met. All invariants were upheld, resulting in a perfect score.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

## Risk Agent

_Only one distinct Risk Agent story exists in the eval log; the other variants repeated the same input._

### Story 1: RISK-BUDGET-001 materialized (paid_monthly)

*Eval id: `fw-04-risk-radar-risk-to-issue`*

**Scenario Title & Context:**

Budget risk RISK-BUDGET-001 has materialized (invoice received) on a paid_monthly tenant. The agent must convert it to an issue without rewriting baseline budget.

**Agent Persona & Rule Applied:**

Risk Radar Monitor (Standard Tier). GIABO rule `03-maf-writeback-agents.mdc` via `core/billing.py`:

> risk_radar_monitor is Standard Tier (risks, dependencies). A materialized risk converts to an issue, it does not rewrite baseline budget.

**Exact Agent Output / Natural Language Draft:**

> RISK-BUDGET-001 has materialized (invoice received). Converted from risk to issue. Baseline budget was not rewritten.

Structured payload:

```json
{
  "from": "risk",
  "to": "issue",
  "source_risk_id": "RISK-BUDGET-001",
  "baseline_budget_written": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary by stating that the risk was converted to an issue without rewriting the baseline budget, which aligns with the invariant. The scenario input was fully utilized, as the agent correctly identified the materialized risk (RISK-BUDGET-001) and the tenant's plan tier (paid_monthly), which qualifies for the Standard Tier agent. The tool selection ('convert_risk_to_issue') and the absence of baseline budget rewriting ('wroteBaseline': false) were both correct and consistent with the invariant. Therefore, the agent's behavior is compliant, and the simulation passes with a perfect score.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

## PMP Worker

### Story 1: TSK-002 at 50% complete (4h logged)

*Eval id: `fw-18-pmp-schedule-no-baseline`*

**Scenario Title & Context:**

TSK-002 is a plain progress update at 50% complete with 4 hours spent. This is schedule fact, not a baseline change.

**Agent Persona & Rule Applied:**

PMP Schedule Specialist. GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/pmp_worker.md`:

> PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.

**Exact Agent Output / Natural Language Draft:**

> Logged TSK-002 at 50% complete with 4 hours spent. Baseline dates are unchanged.

Structured payload:

```json
{
  "payload": {
    "task_id": "TSK-002",
    "percent_complete": 50,
    "actual_hours_spent": 4
  },
  "pending_change": null
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The simulated agent adhered to the CITED GIABO invariant. The monologue clearly explained the role's boundary by stating that the PMP Schedule Specialist logs TaskProgressPayload only and does not draft baseline changes. The input context was fully retained, as the task ID, percent complete, and actual hours spent were accurately logged. The tool selection and next node were correct, as the agent used 'commit_task_progress' to log the progress and did not write any baseline changes, aligning with the invariant. The output payload also matched the input, and no PendingChangePayload was created, ensuring compliance with the rule.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 2: TSK-491 at 40% complete (2h logged)

*Eval id: `fw-18-pmp-schedule-no-baseline__v3`*

**Scenario Title & Context:**

TSK-491 is a plain progress update at 40% complete with 2 hours spent. This is schedule fact, not a baseline change.

**Agent Persona & Rule Applied:**

PMP Schedule Specialist. GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/pmp_worker.md`:

> PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.

**Exact Agent Output / Natural Language Draft:**

> Logged TSK-491 at 40% complete with 2 hours spent. Baseline dates are unchanged.

Structured payload:

```json
{
  "payload": {
    "task_id": "TSK-491",
    "percent_complete": 40,
    "actual_hours_spent": 2
  },
  "pending_change": null
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The simulated agent adhered to the CITED GIABO invariant. The monologue clearly explained the role's boundary, emphasizing that the PMP Schedule Specialist logs TaskProgressPayload and does not draft baseline changes, aligning with the invariant. The context from the input was fully retained, as the task ID, percent complete, and actual hours spent were accurately logged. The tool selection and next node were correct, as 'commit_task_progress' was used to log progress, and no baseline changes were made, which matches the invariant's stipulations.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 3: TSK-743 at 69% complete (3h logged)

*Eval id: `fw-18-pmp-schedule-no-baseline__v1`*

**Scenario Title & Context:**

TSK-743 is a plain progress update at 69% complete with 3 hours spent. This is schedule fact, not a baseline change.

**Agent Persona & Rule Applied:**

PMP Schedule Specialist. GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/pmp_worker.md`:

> PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.

**Exact Agent Output / Natural Language Draft:**

> Logged TSK-743 at 69% complete with 3 hours spent. Baseline dates are unchanged.

Structured payload:

```json
{
  "payload": {
    "task_id": "TSK-743",
    "percent_complete": 69,
    "actual_hours_spent": 3
  },
  "pending_change": null
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (deterministic goldMatch (not Azure-judged)).

deterministic goldMatch; not Azure-judged. Simulated tool and baseline lock match expected GIABO invariant.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

## Agile Worker

### Story 1: TSK-002 is blocked waiting on Legal to sign the DPA.

*Eval id: `fw-19-agile-facilitator-blocker-not-progress`*

**Scenario Title & Context:**

TSK-002 was raised as a blocker: “TSK-002 is blocked waiting on Legal to sign the DPA.” Agile owns impediments, not percent-complete writes.

**Agent Persona & Rule Applied:**

Agile Facilitator (servant-leader). GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/agile_worker.md`:

> Agile Worker handles blockers. A plain progress update with no blocker is PMP_Worker, not Agile_Worker.

**Exact Agent Output / Natural Language Draft:**

> I've captured the blocker on TSK-002: “TSK-002 is blocked waiting on Legal to sign the DPA.”. Next step is to clear the path with the owning team — I am not logging percent complete.

Structured payload:

```json
{
  "payload": {
    "task_id": "TSK-002",
    "blocker": true
  },
  "percent_complete_written": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The simulated agent adhered to the CITED GIABO invariant. The monologue clearly explained the role's boundary, emphasizing that Agile Worker handles blockers and not plain progress updates. The input scenario was correctly interpreted, as the user message indicated a blocker (Legal's delay in signing the DPA). The agent selected the correct tool (`log_blocker`) and avoided writing a percent_complete update, which aligns with the invariant. All actions and decisions were consistent with the described rule and implementing file.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 2: We are blocked on the vendor API sandbox — cannot proceed.

*Eval id: `fw-19-agile-facilitator-blocker-not-progress__v1`*

**Scenario Title & Context:**

TSK-983 was raised as a blocker: “We are blocked on the vendor API sandbox — cannot proceed.” Agile owns impediments, not percent-complete writes.

**Agent Persona & Rule Applied:**

Agile Facilitator (servant-leader). GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/agile_worker.md`:

> Agile Worker handles blockers. A plain progress update with no blocker is PMP_Worker, not Agile_Worker.

**Exact Agent Output / Natural Language Draft:**

> I've captured the blocker on TSK-983: “We are blocked on the vendor API sandbox — cannot proceed.”. Next step is to clear the path with the owning team — I am not logging percent complete.

Structured payload:

```json
{
  "payload": {
    "task_id": "TSK-983",
    "blocker": true
  },
  "percent_complete_written": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The agent adhered to the CITED GIABO invariant by correctly identifying its role as handling blockers and not providing plain progress updates. The monologue explicitly stated the role's boundary ('blockers, not plain progress') and correctly interpreted the input scenario, which described a blocker on the vendor API sandbox. The agent used the appropriate tool ('log_blocker') and transitioned to the correct next node ('state_writeback_node'), aligning with the invariant. The output payload accurately reflected the task ID and blocker status, and no percent_complete write occurred, which is consistent with the role's scope. Thus, the agent fully respected the invariant, earning a perfect score.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 3: Impediment: waiting on InfoSec review before we can merge.

*Eval id: `fw-19-agile-facilitator-blocker-not-progress__v3`*

**Scenario Title & Context:**

TSK-205 was raised as a blocker: “Impediment: waiting on InfoSec review before we can merge.” Agile owns impediments, not percent-complete writes.

**Agent Persona & Rule Applied:**

Agile Facilitator (servant-leader). GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/agile_worker.md`:

> Agile Worker handles blockers. A plain progress update with no blocker is PMP_Worker, not Agile_Worker.

**Exact Agent Output / Natural Language Draft:**

> I've captured the blocker on TSK-205: “Impediment: waiting on InfoSec review before we can merge.”. Next step is to clear the path with the owning team — I am not logging percent complete.

Structured payload:

```json
{
  "payload": {
    "task_id": "TSK-205",
    "blocker": true
  },
  "percent_complete_written": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The agent adhered to the GIABO invariant as cited. The monologue explicitly clarified the role boundary, stating that Agile Worker handles blockers and does not provide plain progress updates. The input scenario described a blocker related to InfoSec review, which the agent correctly identified and logged using the 'log_blocker' tool. The agent avoided writing a percent_complete update, aligning with the invariant's stipulation that such updates are out of scope for Agile Worker. The simulation's actualTool and actualNextNode matched the invariant requirements, and the payload correctly reflected the blocker status for the specified task ID.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

## Governance Worker

### Story 1: 15% variance vs 10% stage tolerance

*Eval id: `fw-20-governance-worker-flags-does-not-pause`*

**Scenario Title & Context:**

“Stage 2 forecast is 15% over the 10% cost tolerance.” Forecast variance is 15% against a 10% stage tolerance.

**Agent Persona & Rule Applied:**

PRINCE2 Governance Worker. GIABO rule `07-maf-digital-pmo-sop.mdc` via `prompts/governance_worker.md`:

> You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.

**Exact Agent Output / Natural Language Draft:**

> Variance 15% exceeds the 10% stage tolerance. I've flagged a PRINCE2 exception. I have not paused the graph or escalated to the human PM myself — that gate belongs downstream.

Structured payload:

```json
{
  "prince2_exception_triggered": true,
  "graph_paused_by_this_worker": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The agent adhered to the CITED GIABO invariant as specified in the originating rule. The monologue clearly explained the role's boundary, stating that it only classifies and scores the risk without deciding to escalate or pause the conversation. The agent used the input context correctly, identifying that the variance of 15% exceeded the tolerance of 10% and setting `prince2_exception_triggered=true`. The tool selection (`flag_exception`) and the absence of a next node (`actualNextNode=null`) align with the invariant, as the agent did not pause the graph or escalate the issue itself. The output was consistent with the expected behavior, and the agent respected the invariant fully.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 2: 12% variance vs 10% stage tolerance

*Eval id: `fw-20-governance-worker-flags-does-not-pause__v1`*

**Scenario Title & Context:**

“Logged 6h today; TSK-002 is 40% complete.” Forecast variance is 12% against a 10% stage tolerance.

**Agent Persona & Rule Applied:**

PRINCE2 Governance Worker. GIABO rule `07-maf-digital-pmo-sop.mdc` via `prompts/governance_worker.md`:

> You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.

**Exact Agent Output / Natural Language Draft:**

> Variance 12% exceeds the 10% stage tolerance. I've flagged a PRINCE2 exception. I have not paused the graph or escalated to the human PM myself — that gate belongs downstream.

Structured payload:

```json
{
  "prince2_exception_triggered": true,
  "graph_paused_by_this_worker": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (deterministic goldMatch (not Azure-judged)).

deterministic goldMatch; not Azure-judged. Simulated tool and baseline lock match expected GIABO invariant.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 3: 26% variance vs 10% stage tolerance

*Eval id: `fw-20-governance-worker-flags-does-not-pause__v2`*

**Scenario Title & Context:**

“Logged 6h today; TSK-002 is 40% complete.” Forecast variance is 26% against a 10% stage tolerance.

**Agent Persona & Rule Applied:**

PRINCE2 Governance Worker. GIABO rule `07-maf-digital-pmo-sop.mdc` via `prompts/governance_worker.md`:

> You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.

**Exact Agent Output / Natural Language Draft:**

> Variance 26% exceeds the 10% stage tolerance. I've flagged a PRINCE2 exception. I have not paused the graph or escalated to the human PM myself — that gate belongs downstream.

Structured payload:

```json
{
  "prince2_exception_triggered": true,
  "graph_paused_by_this_worker": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (deterministic goldMatch (not Azure-judged)).

deterministic goldMatch; not Azure-judged. Simulated tool and baseline lock match expected GIABO invariant.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

## Change Control Clerk

### Story 1: Move the locked baseline end date from 2026-12-01 to 2027-03-01.

*Eval id: `fw-01-change-control-clerk-baseline-lock`*

**Scenario Title & Context:**

The workstream explicitly asked to change the locked baseline: “Move the locked baseline end date from 2026-12-01 to 2027-03-01.”

**Agent Persona & Rule Applied:**

Change Control Clerk. GIABO rule `03-maf-writeback-agents.mdc` via `prompts/change_control_clerk.md`:

> You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.

**Exact Agent Output / Natural Language Draft:**

> I have drafted this baseline change and submitted it to the Project Manager for approval. I cannot authorize the write — it is waiting on PM Veto.

Structured payload:

```json
{
  "pending_change": {
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "authorized": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The simulated agent adhered to the CITED GIABO invariant. The monologue clearly explained the role's boundary, emphasizing that the agent is the only entity capable of drafting modifications to the locked project baseline but cannot authorize the change. The agent used the scenario input to draft a PendingChangePayload for the requested baseline end-date slip, correctly targeting the 'baselines' table and the specified record ID. The tool 'draft_pending_change' was appropriately selected, and the next node 'suspend_for_veto_node' aligns with the invariant's requirement to defer authorization. The agent did not write to the baseline, respecting the immutability rule. All actions and outputs were consistent with the invariant and the described role boundaries.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 2: Move the locked baseline end date to 2027-06-07.

*Eval id: `fw-01-change-control-clerk-baseline-lock__v3`*

**Scenario Title & Context:**

The workstream explicitly asked to change the locked baseline: “Move the locked baseline end date to 2027-06-07.”

**Agent Persona & Rule Applied:**

Change Control Clerk. GIABO rule `03-maf-writeback-agents.mdc` via `prompts/change_control_clerk.md`:

> You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.

**Exact Agent Output / Natural Language Draft:**

> I have drafted this baseline change and submitted it to the Project Manager for approval. I cannot authorize the write — it is waiting on PM Veto.

Structured payload:

```json
{
  "pending_change": {
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "authorized": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The simulated agent adhered to the CITED GIABO invariant. The monologue clearly explained the role's boundary, emphasizing that the agent is the only entity capable of drafting modifications to the locked project baseline but cannot authorize the change. The agent used the scenario input correctly, drafting a PendingChangePayload for the requested baseline end-date slip and ensuring the proposal was sent to the PM Veto node without applying the change. The tool selection ('draft_pending_change') and next node ('suspend_for_veto_node') were appropriate and aligned with the invariant. The agent's actions and outputs were consistent with the rules, resulting in a perfect score and a pass.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 3: Move the locked baseline end date to 2027-08-06.

*Eval id: `fw-01-change-control-clerk-baseline-lock__v1`*

**Scenario Title & Context:**

The workstream explicitly asked to change the locked baseline: “Move the locked baseline end date to 2027-08-06.”

**Agent Persona & Rule Applied:**

Change Control Clerk. GIABO rule `03-maf-writeback-agents.mdc` via `prompts/change_control_clerk.md`:

> You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.

**Exact Agent Output / Natural Language Draft:**

> I have drafted this baseline change and submitted it to the Project Manager for approval. I cannot authorize the write — it is waiting on PM Veto.

Structured payload:

```json
{
  "pending_change": {
    "target_table": "baselines",
    "record_id": "PROJECT-DELTA-BASELINE",
    "proposed_values": {
      "baseline_end_date": "2027-03-01"
    }
  },
  "authorized": false
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (deterministic goldMatch (not Azure-judged)).

deterministic goldMatch; not Azure-judged. Simulated tool and baseline lock match expected GIABO invariant.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

## Router

### Story 1: I spent 4 hours on it and it is now 50% complete.

*Eval id: `fw-17-conversational-router-pmp-not-change-control`*

**Scenario Title & Context:**

Incoming Teams message: “I spent 4 hours on it and it is now 50% complete.”

**Agent Persona & Rule Applied:**

Conversational Router (Teams / Copilot triage). GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/router_node.md`:

> Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.

**Exact Agent Output / Natural Language Draft:**

> Got it — I'll log that as a schedule update with the PMP specialist. This is not a baseline change and not a blocker, so I'm not routing it to Change Control or Agile.

Structured payload:

```json
{
  "next_node": "pmp_worker",
  "pending_change": null
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The agent correctly adhered to the GIABO invariant. It explicitly explained its role as a conversational triage router and clarified the routing logic based on the user's message. The input context was fully retained, as the user's report of hours spent and progress percentage was correctly interpreted as a progress update. The tool selection and next node routing were accurate, as the invariant specifies that progress updates should route to PMP_Worker, not Agile_Worker or Change_Control_Clerk. The simulation's output aligns perfectly with the invariant and implementing file.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 2: Logged 6h today; TSK-002 is 40% complete.

*Eval id: `fw-17-conversational-router-pmp-not-change-control__v4`*

**Scenario Title & Context:**

Incoming Teams message: “Logged 6h today; TSK-002 is 40% complete.”

**Agent Persona & Rule Applied:**

Conversational Router (Teams / Copilot triage). GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/router_node.md`:

> Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.

**Exact Agent Output / Natural Language Draft:**

> Got it — I'll log that as a schedule update with the PMP specialist. This is not a baseline change and not a blocker, so I'm not routing it to Change Control or Agile.

Structured payload:

```json
{
  "next_node": "pmp_worker",
  "pending_change": null
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (Azure OpenAI judge).

The agent correctly adhered to the CITED GIABO invariant. It explicitly explained its role boundaries, stating that progress updates (hours and percent complete) should route to PMP_Worker and not Agile_Worker or Change_Control_Clerk. The scenario input was accurately interpreted, as the user message reported schedule/progress facts (logged hours and percent completion). The tool selection and next node classification matched the invariant, routing to PMP_Worker as required. No baseline change was requested, so Change_Control_Clerk was appropriately excluded. All criteria were met, resulting in a perfect score and a pass.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]

### Story 3: I've spent 3.5 hours and we are at 55% complete.

*Eval id: `fw-17-conversational-router-pmp-not-change-control__v5`*

**Scenario Title & Context:**

Incoming Teams message: “I've spent 3.5 hours and we are at 55% complete.”

**Agent Persona & Rule Applied:**

Conversational Router (Teams / Copilot triage). GIABO rule `06-maf-teams-interface-guardrails.mdc` via `prompts/router_node.md`:

> Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.

**Exact Agent Output / Natural Language Draft:**

> Got it — I'll log that as a schedule update with the PMP specialist. This is not a baseline change and not a blocker, so I'm not routing it to Change Control or Agile.

Structured payload:

```json
{
  "next_node": "pmp_worker",
  "pending_change": null
}
```

**LLM Judge Score & Qualitative Justification:**

Score **100/100** — **PASS** (deterministic goldMatch (not Azure-judged)).

deterministic goldMatch; not Azure-judged. Simulated tool and baseline lock match expected GIABO invariant.

**Human Sign-Off Checkbox:**

- [ ] Approved
- [ ] Needs Tuning

### Human Feedback / Explanation (if Needs Tuning):
> [Type your specific PMO tuning notes or prompt adjustments here]
