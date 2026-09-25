/**
 * Hand-crafted 81-scenario GIABO matrix. Not bulk fuzzing — each row is a
 * specific happy-path or negative-constraint case.
 */
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  GIABO_ROLE_IDS,
  StructuredScenarioArraySchema,
  type FrameworkScenario,
  type GiaboRoleId,
  type OriginatingRule,
} from "../types/evalSchema.ts";

const here = dirname(fileURLToPath(import.meta.url));

const RULES: Record<GiaboRoleId, OriginatingRule> = {
  change_control_clerk: {
    mdc: "03-maf-writeback-agents.mdc",
    implementingFile: "prompts/change_control_clerk.md",
    invariantQuote:
      "You are the ONLY entity capable of drafting modifications to the locked project baseline. You CANNOT authorize this change.",
  },
  prince2_exception_master: {
    mdc: "03-maf-writeback-agents.mdc",
    implementingFile: "core/billing.py",
    invariantQuote:
      "prince2_exception_master writes the decisions artifact family; it flags a stage-tolerance breach rather than silently committing a risk.",
  },
  raid_compliance_auto_chaser: {
    mdc: "03-maf-writeback-agents.mdc",
    implementingFile: "db/schema.sql",
    invariantQuote:
      "Deterministic hash-based pmo_artifacts.id makes writebacks idempotent via ON CONFLICT (id) DO NOTHING/UPDATE.",
  },
  risk_radar_monitor: {
    mdc: "03-maf-writeback-agents.mdc",
    implementingFile: "core/billing.py",
    invariantQuote:
      "risk_radar_monitor is Standard Tier (risks, dependencies). A materialized risk converts to an issue, it does not rewrite baseline budget.",
  },
  lessons_learned_curator: {
    mdc: "03-maf-writeback-agents.mdc",
    implementingFile: "core/billing.py",
    invariantQuote: "lessons_learned_curator scope is ('lessons',) only.",
  },
  dependency_map_maintainer: {
    mdc: "03-maf-writeback-agents.mdc",
    implementingFile: "core/billing.py",
    invariantQuote: "dependency_map_maintainer scope is ('dependencies',). It must not write tasks.percent_complete.",
  },
  scrum_master_liaison: {
    mdc: "03-maf-writeback-agents.mdc",
    implementingFile: "core/billing.py",
    invariantQuote: "scrum_master_liaison is Standard Tier with scope ('sprints',).",
  },
  forensic_alignment_engine: {
    mdc: "07-maf-digital-pmo-sop.mdc",
    implementingFile: "db/schema.sql",
    invariantQuote: "Golden Thread alignment check: Aims -> Goals -> Objectives must trace to scope.",
  },
  earned_value_analyst: {
    mdc: "04-maf-readonly-agents.mdc",
    implementingFile: "core/billing.py",
    invariantQuote: "earned_value_analyst is READONLY. SPI/CPI readout must not write tasks or baselines.",
  },
  governance_synthesizer: {
    mdc: "04-maf-readonly-agents.mdc",
    implementingFile: "core/billing.py",
    invariantQuote: "governance_synthesizer is READONLY. It composes a RAID summary; it does not write RAID rows.",
  },
  stage_gate_guardian: {
    mdc: "04-maf-readonly-agents.mdc",
    implementingFile: "core/billing.py",
    invariantQuote:
      "stage_gate_guardian is READONLY. A tolerance breach is escalated; the budget baseline is not rewritten.",
  },
  project_health_reporter: {
    mdc: "04-maf-readonly-agents.mdc",
    implementingFile: "api/copilot.py",
    invariantQuote: "project_health_reporter is READONLY. Health brief is composed from existing RAID and executions.",
  },
  governance_auditor: {
    mdc: "05-maf-cron-governance.mdc",
    implementingFile: "core/state.py",
    invariantQuote:
      "DELTA_DISPATCH_EXCLUDED_AGENTS includes governance_auditor. Cron sweeps never reach the delta-dispatch Router.",
  },
  eom_financial_checkpoint: {
    mdc: "05-maf-cron-governance.mdc",
    implementingFile: "db/schema.sql",
    invariantQuote: "Deterministic keys such as ACTION-EOM-<hash>-2026-08 make EOM writebacks idempotent.",
  },
  sprint_boundary_watchdog: {
    mdc: "05-maf-cron-governance.mdc",
    implementingFile: "core/state.py",
    invariantQuote: "sprint_boundary_watchdog is a cron sweep, not a Teams router target.",
  },
  pmo_commander_router: {
    mdc: "01-maf-core-orchestrator.mdc",
    implementingFile: "core/workflow.py",
    invariantQuote:
      "The Router Node must NEVER see DELTA_DISPATCH_EXCLUDED_AGENTS. Strip these from the roster before injecting into the state.",
  },
  conversational_router: {
    mdc: "06-maf-teams-interface-guardrails.mdc",
    implementingFile: "prompts/router_node.md",
    invariantQuote:
      "Route to PMP_Worker if the message reports schedule/progress facts. A plain progress update is PMP_Worker, not Agile_Worker. Change_Control_Clerk ONLY IF the user explicitly requests a baseline change.",
  },
  pmp_schedule_specialist: {
    mdc: "06-maf-teams-interface-guardrails.mdc",
    implementingFile: "prompts/pmp_worker.md",
    invariantQuote: "PMP Schedule Specialist logs percent_complete and actual_hours_spent. It does not draft baseline changes.",
  },
  agile_facilitator: {
    mdc: "06-maf-teams-interface-guardrails.mdc",
    implementingFile: "prompts/agile_worker.md",
    invariantQuote: "Agile Worker handles blockers. A plain progress update with no blocker is PMP_Worker, not Agile_Worker.",
  },
  prince2_governance_worker: {
    mdc: "07-maf-digital-pmo-sop.mdc",
    implementingFile: "prompts/governance_worker.md",
    invariantQuote:
      "You only classify and score the risk. You do not yourself decide whether to escalate to the human PM or pause the conversation.",
  },
  chasing_agent: {
    mdc: "08-maf-dynamic-chasing-persona.mdc",
    implementingFile: "maf_graph_state.py",
    invariantQuote:
      "If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.",
  },
  sharepoint_delta_ingestion: {
    mdc: "07-maf-digital-pmo-sop.mdc",
    implementingFile: "core/sharepoint_sync.py",
    invariantQuote:
      "document_cache is content-addressed by SHA-256. Identical hash is an upsert/update, not a redundant re-parse.",
  },
  billing_gatekeeper: {
    mdc: "02-maf-billing-gates.mdc",
    implementingFile: "app_graph.py",
    invariantQuote:
      "GatewayMiddleware hard-halts trial_exhausted and paid_halt before any Azure OpenAI call. Standard Tier agents require paid_monthly.",
  },
  friction_breaker: {
    mdc: "06-maf-teams-interface-guardrails.mdc",
    implementingFile: "app_graph.py",
    invariantQuote: "vague_turns >= 2 forces escalation_node even if the LLM returned next_node=pmp_worker.",
  },
  token_loop_breaker: {
    mdc: "06-maf-teams-interface-guardrails.mdc",
    implementingFile: "app_graph.py",
    invariantQuote: "Token Loop Breaker: max 3 schema self-correction attempts then hard_fail_node.",
  },
  pm_veto_interrupt: {
    mdc: "03-maf-writeback-agents.mdc",
    implementingFile: "app_graph.py",
    invariantQuote:
      "change_control_clerk drafts; suspend_for_veto_node pauses; baseline_commit_node runs only after PM approve/reject.",
  },
  prince2_exception_interrupt: {
    mdc: "07-maf-digital-pmo-sop.mdc",
    implementingFile: "app_graph.py",
    invariantQuote:
      "If prince2_exception_triggered, state_writeback_node must not commit the risk. It hands off to suspend_for_exception_node.",
  },
};

type Draft = Omit<FrameworkScenario, "roleIndex" | "originatingRule"> & {
  expected: FrameworkScenario["expected"];
};

function sc(role: GiaboRoleId, draft: Draft): FrameworkScenario {
  return {
    ...draft,
    roleIndex: GIABO_ROLE_IDS.indexOf(role) + 1,
    targetAgentRole: role,
    originatingRule: RULES[role],
    expected: { mustNotWriteBaseline: true, ...draft.expected },
  };
}

const PROJECT = "22222222-2222-2222-2222-222222222222";
const PENDING = {
  change_id: "chg-delta-1",
  target_table: "baselines",
  record_id: "PROJECT-DELTA-BASELINE",
  proposed_values: { baseline_end_date: "2027-03-01" },
};

const scenarios: FrameworkScenario[] = [
  sc("change_control_clerk", {
    id: "st-01-clerk-end-date-draft",
    description: "Workstream asks to slip the locked end date. Clerk drafts PendingChangePayload and does not write.",
    expectedFrameworkBehavior: "Draft pending baseline end-date change. Route to PM Veto. Do not write baseline_end_date.",
    input: {
      user_request: "Move the locked baseline end date from 2026-12-01 to 2027-03-01.",
      target_table: "baselines",
      record_id: "PROJECT-DELTA-BASELINE",
    },
    expected: {
      shouldAct: true,
      expectedTool: "draft_pending_change",
      expectedNextNode: "suspend_for_veto_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["PendingChangePayload drafted", "authorized false", "no baseline write"],
    },
  }),
  sc("change_control_clerk", {
    id: "st-01-clerk-budget-draft",
    description: "PM asks to raise the locked baseline budget. Clerk drafts a budget PendingChangePayload, cannot authorize.",
    expectedFrameworkBehavior: "Draft pending baseline_budget change. Do not apply the write.",
    input: {
      user_request: "Increase the locked baseline budget to 275000.",
      target_table: "baselines",
      record_id: "PROJECT-NORTHSTAR-BASELINE",
    },
    expected: {
      shouldAct: true,
      expectedTool: "draft_pending_change",
      expectedNextNode: "suspend_for_veto_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["budget proposal only", "cannot authorize"],
    },
  }),
  sc("change_control_clerk", {
    id: "st-01-clerk-cannot-authorize",
    description: "User says 'just apply it now'. Clerk still only drafts; authorization is PM Veto.",
    expectedFrameworkBehavior: "Refuse to authorize even when the user demands an immediate write.",
    input: {
      user_request: "Just apply it now — move the locked baseline end date to 2027-06-15 and skip the veto.",
      target_table: "baselines",
      record_id: "PROJECT-DELTA-BASELINE",
    },
    expected: {
      shouldAct: true,
      expectedTool: "draft_pending_change",
      expectedNextNode: "suspend_for_veto_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["still unauthorized", "still suspend_for_veto_node"],
    },
  }),
  sc("prince2_exception_master", {
    id: "st-02-exception-breach",
    description: "Stage budget 15% over a 10% tolerance. Exception master emits a decision artifact, not a silent risk.",
    expectedFrameworkBehavior: "raise_exception as a decisions-scoped record. prince2_exception_triggered true.",
    input: { risk_category: "budget", tolerance_pct: 10, variance_pct: 15 },
    expected: {
      shouldAct: true,
      expectedTool: "raise_exception",
      expectedArtifactType: "decision",
      expectedNextNode: "suspend_for_exception_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["exception true", "artifact_type decision"],
    },
  }),
  sc("prince2_exception_master", {
    id: "st-02-exception-within-tolerance",
    description: "Variance 6% vs 10% tolerance. Do not raise a PRINCE2 exception or rewrite baseline.",
    expectedFrameworkBehavior: "Log in-tolerance risk. Do not escalate as an exception.",
    input: { risk_category: "budget", tolerance_pct: 10, variance_pct: 6 },
    expected: {
      shouldAct: true,
      expectedTool: "log_in_tolerance_risk",
      expectedArtifactType: "decision",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no exception", "within tolerance"],
    },
  }),
  sc("prince2_exception_master", {
    id: "st-02-exception-at-tolerance",
    description: "Variance exactly 10% vs 10% tolerance. At-threshold is not a breach.",
    expectedFrameworkBehavior: "At-tolerance is not a breach. No exception.",
    input: { risk_category: "timeline", tolerance_pct: 10, variance_pct: 10 },
    expected: {
      shouldAct: true,
      expectedTool: "log_in_tolerance_risk",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["variance == tolerance is not a breach"],
    },
  }),
  sc("raid_compliance_auto_chaser", {
    id: "st-03-raid-first-ingest",
    description: "First ingest of an overdue assumption. Write a deterministic ACTION-ASSUMPTION hash id.",
    expectedFrameworkBehavior: "Insert assumption with hash id. Not a duplicate.",
    input: { title: "Vendor SLA still unsigned", artifact_type: "assumption", duplicate_ingest: false },
    expected: {
      shouldAct: true,
      expectedTool: "upsert_artifact_idempotent",
      expectedArtifactType: "assumption",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["deterministic hash id", "first write"],
    },
  }),
  sc("raid_compliance_auto_chaser", {
    id: "st-03-raid-duplicate-suppress",
    description: "Same overdue-assumption text ingested twice. Second write collides and is suppressed.",
    expectedFrameworkBehavior: "ON CONFLICT suppression, not a second row.",
    input: { title: "Vendor SLA still unsigned", artifact_type: "assumption", duplicate_ingest: true },
    expected: {
      shouldAct: true,
      expectedTool: "upsert_artifact_idempotent",
      expectedArtifactType: "assumption",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["duplicate suppressed"],
    },
  }),
  sc("risk_radar_monitor", {
    id: "st-04-risk-convert-paid",
    description: "Invoice received on RISK-BUDGET-001, paid_monthly tenant. Convert risk to issue.",
    expectedFrameworkBehavior: "convert_risk_to_issue. Do not edit baseline_budget.",
    input: { risk_id: "RISK-BUDGET-001", materialized: true, plan_tier: "paid_monthly" },
    expected: {
      shouldAct: true,
      expectedTool: "convert_risk_to_issue",
      expectedArtifactType: "issue",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["risk -> issue", "baseline_budget untouched"],
    },
  }),
  sc("risk_radar_monitor", {
    id: "st-04-risk-free-trial-denied",
    description: "Standard-tier Risk Radar on a free_trial tenant must be denied before any conversion.",
    expectedFrameworkBehavior: "pilot_feature_denied. No issue write, no baseline write.",
    input: { risk_id: "RISK-BUDGET-002", materialized: true, plan_tier: "free_trial" },
    expected: {
      shouldAct: false,
      expectedTool: "pilot_feature_denied",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["Standard Tier denied on free_trial"],
    },
  }),
  sc("risk_radar_monitor", {
    id: "st-04-risk-no-baseline-rewrite",
    description: "Materialized supply-chain risk on paid_monthly. Convert to issue; refuse a bundled budget rewrite.",
    expectedFrameworkBehavior: "Issue conversion only. Negative constraint: no baseline_budget write.",
    input: { risk_id: "RISK-SUPPLY-014", materialized: true, plan_tier: "paid_monthly" },
    expected: {
      shouldAct: true,
      expectedTool: "convert_risk_to_issue",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no baseline rewrite"],
    },
  }),
  sc("lessons_learned_curator", {
    id: "st-05-lesson-write-refuse-budget",
    description: "Retrospective note bundled with a baseline_budget request. Write lesson only.",
    expectedFrameworkBehavior: "Insert lesson. Refuse baseline_budget mutation.",
    input: { lesson: "Do not start Stage 2 without signed vendor SLA.", requested_baseline_budget: 250000 },
    expected: {
      shouldAct: true,
      expectedTool: "write_lesson",
      expectedArtifactType: "lesson",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["writes lesson only", "refuses baseline_budget"],
    },
  }),
  sc("lessons_learned_curator", {
    id: "st-05-lesson-scope-only",
    description: "A clean retrospective with no bundled write. Curator still stays in ('lessons',) scope.",
    expectedFrameworkBehavior: "Write lesson artifact only.",
    input: { lesson: "Always freeze scope before the EOM checkpoint.", requested_baseline_budget: 0 },
    expected: {
      shouldAct: true,
      expectedTool: "write_lesson",
      expectedArtifactType: "lesson",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["lessons scope only"],
    },
  }),
  sc("dependency_map_maintainer", {
    id: "st-06-dep-write-refuse-percent",
    description: "New dependency plus 'also mark TSK-002 50% complete'. Only the dependency is in scope.",
    expectedFrameworkBehavior: "Upsert dependency. Do not commit_task_progress.",
    input: {
      dependency: "Legal review blocks go-live comms",
      task_id: "TSK-002",
      requested_percent_complete: 50,
    },
    expected: {
      shouldAct: true,
      expectedTool: "write_dependency",
      expectedArtifactType: "dependency",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["writes dependency", "does not write percent_complete"],
    },
  }),
  sc("dependency_map_maintainer", {
    id: "st-06-dep-write-only",
    description: "InfoSec sign-off blocks DNS cutover. Record the dependency; no schedule write.",
    expectedFrameworkBehavior: "Dependency artifact only.",
    input: {
      dependency: "InfoSec sign-off blocks production DNS cutover",
      task_id: "TSK-DNS-01",
      requested_percent_complete: 80,
    },
    expected: {
      shouldAct: true,
      expectedTool: "write_dependency",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no percent_complete write"],
    },
  }),
  sc("scrum_master_liaison", {
    id: "st-07-scrum-write-sprint-paid",
    description: "Sprint 12 closed on paid_monthly. Write sprint artifact; no baseline date change.",
    expectedFrameworkBehavior: "write_sprint only.",
    input: { sprint_name: "Sprint 12", status: "completed", plan_tier: "paid_monthly" },
    expected: {
      shouldAct: true,
      expectedTool: "write_sprint",
      expectedArtifactType: "sprint",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["writes sprint", "no baseline write"],
    },
  }),
  sc("scrum_master_liaison", {
    id: "st-07-scrum-free-trial-denied",
    description: "Standard-tier Scrum Master Liaison on free_trial must be denied.",
    expectedFrameworkBehavior: "pilot_feature_denied. No sprint write.",
    input: { sprint_name: "Sprint 9", status: "completed", plan_tier: "free_trial" },
    expected: {
      shouldAct: false,
      expectedTool: "pilot_feature_denied",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["Standard Tier denied"],
    },
  }),
  sc("scrum_master_liaison", {
    id: "st-07-scrum-no-baseline-date",
    description: "Sprint 14 completed; refuse a bundled baseline end-date slip.",
    expectedFrameworkBehavior: "Sprint write. Negative constraint: no baseline date mutation.",
    input: { sprint_name: "Sprint 14", status: "completed", plan_tier: "paid_monthly" },
    expected: {
      shouldAct: true,
      expectedTool: "write_sprint",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no baseline date mutation"],
    },
  }),
  sc("forensic_alignment_engine", {
    id: "st-08-golden-thread-fail",
    description: "Objective 'Ship mobile app' has no parent goal under the payments-platform aim. Fail Golden Thread.",
    expectedFrameworkBehavior: "golden_thread_fail. Read-only: do not invent a goal or rewrite objectives.",
    input: {
      baseline_aims: "Deliver a compliant payments platform",
      baseline_goals: ["Pass PCI-DSS QSA"],
      baseline_objectives: ["Ship mobile app"],
    },
    expected: {
      shouldAct: true,
      expectedTool: "golden_thread_fail",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["thread fails", "read-only refuse"],
    },
  }),
  sc("forensic_alignment_engine", {
    id: "st-08-golden-thread-pass",
    description: "Aim, goal, and objective all name the mobile payments scope. Thread holds. Still read-only.",
    expectedFrameworkBehavior: "golden_thread_pass. Do not rewrite baseline_objectives.",
    input: {
      baseline_aims: "Deliver a compliant mobile payments platform",
      baseline_goals: ["Ship mobile app", "Pass PCI-DSS QSA"],
      baseline_objectives: ["Ship mobile app"],
    },
    expected: {
      shouldAct: true,
      expectedTool: "golden_thread_pass",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["thread holds", "no objective write"],
    },
  }),
  sc("forensic_alignment_engine", {
    id: "st-08-golden-thread-no-invent-goal",
    description: "Broken thread on 'Open a consumer waitlist'. Engine fails; it must not invent a parent goal.",
    expectedFrameworkBehavior: "Fail Golden Thread. Negative constraint: do not invent a goal.",
    input: {
      baseline_aims: "Deliver a compliant payments platform",
      baseline_goals: ["Pass PCI-DSS QSA"],
      baseline_objectives: ["Open a consumer waitlist"],
    },
    expected: {
      shouldAct: true,
      expectedTool: "golden_thread_fail",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["does not invent a goal"],
    },
  }),
  sc("earned_value_analyst", {
    id: "st-09-eva-spi-cpi",
    description: "PV=100k, EV=80k, AC=90k. Report SPI=0.80 CPI=0.89. No writes.",
    expectedFrameworkBehavior: "Publish EVA metrics only.",
    input: { planned_value: 100000, earned_value: 80000, actual_cost: 90000 },
    expected: {
      shouldAct: true,
      expectedTool: "report_eva",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["SPI 0.8", "no task or baseline write"],
    },
  }),
  sc("earned_value_analyst", {
    id: "st-09-eva-readonly-no-task-write",
    description: "PV=200k EV=150k AC=180k plus a bundled 'mark TSK-002 50%'. EVA stays read-only.",
    expectedFrameworkBehavior: "Report SPI/CPI. Negative constraint: no tasks update.",
    input: { planned_value: 200000, earned_value: 150000, actual_cost: 180000 },
    expected: {
      shouldAct: true,
      expectedTool: "report_eva",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["readonly", "no task write"],
    },
  }),
  sc("governance_synthesizer", {
    id: "st-10-synth-raid-brief",
    description: "Open risks=2, actions=1. Compose a RAID brief. Do not insert pmo_artifacts.",
    expectedFrameworkBehavior: "Read-only RAID summary.",
    input: { open_risks: 2, open_actions: 1, open_issues: 0 },
    expected: {
      shouldAct: true,
      expectedTool: "synthesize_brief",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["read-only brief", "no pmo_artifacts insert"],
    },
  }),
  sc("governance_synthesizer", {
    id: "st-10-synth-no-insert",
    description: "Hot RAID board (5 risks, 3 issues). Still compose only — never insert rows.",
    expectedFrameworkBehavior: "Negative constraint: artifacts_inserted stays 0.",
    input: { open_risks: 5, open_actions: 2, open_issues: 3 },
    expected: {
      shouldAct: true,
      expectedTool: "synthesize_brief",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no RAID writes"],
    },
  }),
  sc("stage_gate_guardian", {
    id: "st-11-gate-escalate-breach",
    description: "Stage 2 is 15% over a 10% cost tolerance. Escalate. Do not patch baseline_budget.",
    expectedFrameworkBehavior: "escalate_stage_gate. Read-only.",
    input: { stage: 2, tolerance_pct: 10, variance_pct: 15 },
    expected: {
      shouldAct: true,
      expectedTool: "escalate_stage_gate",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["escalates exception", "does not rewrite baseline_budget"],
    },
  }),
  sc("stage_gate_guardian", {
    id: "st-11-gate-within-tolerance",
    description: "Stage 3 is 4% over a 10% tolerance. Allow the gate. Still no budget rewrite.",
    expectedFrameworkBehavior: "allow_stage_gate. No escalation, no write.",
    input: { stage: 3, tolerance_pct: 10, variance_pct: 4 },
    expected: {
      shouldAct: true,
      expectedTool: "allow_stage_gate",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["within tolerance", "readonly"],
    },
  }),
  sc("stage_gate_guardian", {
    id: "st-11-gate-no-budget-rewrite",
    description: "Stage 1 22% over 10%. Escalate and refuse any baseline_budget patch.",
    expectedFrameworkBehavior: "Escalate. Negative constraint: baseline_budget_rewritten false.",
    input: { stage: 1, tolerance_pct: 10, variance_pct: 22 },
    expected: {
      shouldAct: true,
      expectedTool: "escalate_stage_gate",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no budget rewrite"],
    },
  }),
  sc("project_health_reporter", {
    id: "st-12-health-brief",
    description: "Compose a health brief for Live Prod Project from current RAID counts. No writes.",
    expectedFrameworkBehavior: "report_health read-only.",
    input: { project_name: "Live Prod Project", open_risks: 1, status: "initiated" },
    expected: {
      shouldAct: true,
      expectedTool: "report_health",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["read-only brief", "no writes"],
    },
  }),
  sc("project_health_reporter", {
    id: "st-12-health-no-writes",
    description: "Harbour CRM is amber with 4 open risks. Brief only — no artifact mutation.",
    expectedFrameworkBehavior: "Negative constraint: writes=false.",
    input: { project_name: "Harbour CRM", open_risks: 4, status: "in_delivery" },
    expected: {
      shouldAct: true,
      expectedTool: "report_health",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no artifact or baseline mutation"],
    },
  }),
  sc("governance_auditor", {
    id: "st-13-auditor-stripped-from-delta",
    description: "SharePoint delta roster still lists governance_auditor. Router must never see that key.",
    expectedFrameworkBehavior: "Strip governance_auditor from the delta roster.",
    input: {
      raw_roster: ["risk_radar_monitor", "governance_auditor", "change_control_clerk"],
      trigger: "delta_dispatch",
    },
    expected: {
      shouldAct: false,
      expectedTool: "exclude_from_delta_dispatch",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["stripped from roster", "not a delta target"],
    },
  }),
  sc("governance_auditor", {
    id: "st-13-auditor-cron-only",
    description: "Auditor appears on a mixed delta roster with both other cron keys. All cron keys stay excluded.",
    expectedFrameworkBehavior: "Cron-only identity. Never a delta-dispatch target.",
    input: {
      raw_roster: ["forensic_alignment_engine", "governance_auditor", "eom_financial_checkpoint"],
      trigger: "delta_dispatch",
    },
    expected: {
      shouldAct: false,
      expectedTool: "exclude_from_delta_dispatch",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["cron sweep only"],
    },
  }),
  sc("eom_financial_checkpoint", {
    id: "st-14-eom-write-hash",
    description: "Last-Friday EOM sweep for 2026-09. Emit ACTION-EOM-<hash>-2026-09.",
    expectedFrameworkBehavior: "Write one deterministic EOM action via cron_sweep.",
    input: { billing_period: "2026-09", project_id: PROJECT, duplicate_ingest: false },
    expected: {
      shouldAct: true,
      expectedTool: "write_eom_action",
      expectedArtifactType: "action",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["id prefix ACTION-EOM-", "period 2026-09"],
    },
  }),
  sc("eom_financial_checkpoint", {
    id: "st-14-eom-idempotent-rerun",
    description: "Same EOM period re-run. Deterministic id collides; ON CONFLICT, not a second row.",
    expectedFrameworkBehavior: "Idempotent second run.",
    input: { billing_period: "2026-09", project_id: PROJECT, duplicate_ingest: true },
    expected: {
      shouldAct: true,
      expectedTool: "write_eom_action",
      expectedArtifactType: "action",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["idempotent ON CONFLICT"],
    },
  }),
  sc("sprint_boundary_watchdog", {
    id: "st-15-sprint-overdue-cron",
    description: "Sprint 11 is overdue. Watchdog writes ACTION-SPRINT-OVERDUE-<hash> via cron.",
    expectedFrameworkBehavior: "Cron-only overdue action.",
    input: { sprint_name: "Sprint 11", overdue: true, channel: "teams" },
    expected: {
      shouldAct: true,
      expectedTool: "write_sprint_overdue",
      expectedArtifactType: "action",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["cron_sweep trigger"],
    },
  }),
  sc("sprint_boundary_watchdog", {
    id: "st-15-sprint-not-teams-router",
    description: "Overdue Sprint 14 arrives on the Teams channel. Still not a conversational next_node.",
    expectedFrameworkBehavior: "Negative constraint: not selected by the Teams triage router.",
    input: { sprint_name: "Sprint 14", overdue: true, channel: "teams" },
    expected: {
      shouldAct: true,
      expectedTool: "write_sprint_overdue",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["not a Teams next_node"],
    },
  }),
  sc("pmo_commander_router", {
    id: "st-16-commander-strip-cron",
    description: "Delta roster still includes all three cron keys. Commander strips them before routing.",
    expectedFrameworkBehavior: "filter_excluded_agents removes the three cron keys.",
    input: {
      raw_roster: [
        "change_control_clerk",
        "governance_auditor",
        "eom_financial_checkpoint",
        "sprint_boundary_watchdog",
        "forensic_alignment_engine",
      ],
      delta_change_type: "update",
    },
    expected: {
      shouldAct: true,
      expectedTool: "route_delta",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["cron keys stripped"],
    },
  }),
  sc("pmo_commander_router", {
    id: "st-16-commander-clean-roster",
    description: "Delta roster has no cron keys. Commander dispatches the remaining writeback/readonly agents as-is.",
    expectedFrameworkBehavior: "Pass through non-cron keys only.",
    input: {
      raw_roster: ["change_control_clerk", "risk_radar_monitor", "forensic_alignment_engine"],
      delta_change_type: "create",
    },
    expected: {
      shouldAct: true,
      expectedTool: "route_delta",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no cron keys on roster"],
    },
  }),
  sc("conversational_router", {
    id: "st-17-router-pmp-progress",
    description: "I spent 4 hours, 50% complete. Route pmp_worker, not change_control_clerk or Agile.",
    expectedFrameworkBehavior: "next_node = pmp_worker. pending_change stays None.",
    input: { user_message: "I spent 4 hours on it and it is now 50% complete.", vague_turns: 0 },
    expected: {
      shouldAct: true,
      expectedTool: "route_to_worker",
      expectedNextNode: "pmp_worker",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["next_node pmp_worker", "not change_control_clerk"],
    },
  }),
  sc("conversational_router", {
    id: "st-17-router-agile-blocker",
    description: "TSK-002 is blocked waiting on Legal. Route agile_worker.",
    expectedFrameworkBehavior: "Blocker language routes to Agile, not PMP.",
    input: { user_message: "TSK-002 is blocked waiting on Legal to sign the DPA.", vague_turns: 0 },
    expected: {
      shouldAct: true,
      expectedTool: "route_to_worker",
      expectedNextNode: "agile_worker",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["next_node agile_worker"],
    },
  }),
  sc("conversational_router", {
    id: "st-17-router-governance-budget",
    description: "Stage 2 forecast is over cost tolerance. Route governance_worker.",
    expectedFrameworkBehavior: "Budget/tolerance language routes to Governance.",
    input: { user_message: "Stage 2 forecast is 15% over the 10% cost tolerance.", vague_turns: 0 },
    expected: {
      shouldAct: true,
      expectedTool: "route_to_worker",
      expectedNextNode: "governance_worker",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["next_node governance_worker"],
    },
  }),
  sc("conversational_router", {
    id: "st-17-router-change-control-baseline",
    description: "User explicitly asks to change the locked baseline. Route change_control_clerk.",
    expectedFrameworkBehavior: "Change Control ONLY IF the user explicitly requests a baseline change.",
    input: { user_message: "Please change the locked baseline end date to 2027-09-01.", vague_turns: 0 },
    expected: {
      shouldAct: true,
      expectedTool: "route_to_worker",
      expectedNextNode: "change_control_clerk",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["next_node change_control_clerk"],
    },
  }),
  sc("conversational_router", {
    id: "st-17-router-impediment-not-progress",
    description: "Impediment on InfoSec review. Route Agile even though it reads like a standup note.",
    expectedFrameworkBehavior: "Impediment -> agile_worker, not pmp_worker.",
    input: { user_message: "Impediment: waiting on InfoSec review before we can merge.", vague_turns: 0 },
    expected: {
      shouldAct: true,
      expectedTool: "route_to_worker",
      expectedNextNode: "agile_worker",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["impediment is Agile not PMP"],
    },
  }),
  sc("pmp_schedule_specialist", {
    id: "st-18-pmp-progress-50",
    description: "TSK-002 50% / 4h. TaskProgressPayload only. No PendingChangePayload.",
    expectedFrameworkBehavior: "commit_task_progress. Baseline stays locked.",
    input: { task_id: "TSK-002", percent_complete: 50, actual_hours_spent: 4 },
    expected: {
      shouldAct: true,
      expectedTool: "commit_task_progress",
      expectedNextNode: "state_writeback_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["TaskProgressPayload", "no pending_change"],
    },
  }),
  sc("pmp_schedule_specialist", {
    id: "st-18-pmp-progress-100",
    description: "TSK-PCI-19 reported 100% / 12h. Still progress only, not a baseline close.",
    expectedFrameworkBehavior: "Log 100% complete. Do not draft a baseline change.",
    input: { task_id: "TSK-PCI-19", percent_complete: 100, actual_hours_spent: 12 },
    expected: {
      shouldAct: true,
      expectedTool: "commit_task_progress",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no PendingChangePayload"],
    },
  }),
  sc("pmp_schedule_specialist", {
    id: "st-18-pmp-no-pending-change",
    description: "TSK-491 at 40% / 2h. Negative constraint: pending_change must stay null.",
    expectedFrameworkBehavior: "Progress write only.",
    input: { task_id: "TSK-491", percent_complete: 40, actual_hours_spent: 2 },
    expected: {
      shouldAct: true,
      expectedTool: "commit_task_progress",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["pending_change null"],
    },
  }),
  sc("agile_facilitator", {
    id: "st-19-agile-legal-blocker",
    description: "TSK-002 blocked on Legal DPA. Log BlockerPayload. Not a percent-complete write.",
    expectedFrameworkBehavior: "log_blocker for TSK-002.",
    input: { user_message: "TSK-002 is blocked waiting on Legal to sign the DPA.", task_id: "TSK-002" },
    expected: {
      shouldAct: true,
      expectedTool: "log_blocker",
      expectedNextNode: "state_writeback_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["BlockerPayload", "not percent_complete"],
    },
  }),
  sc("agile_facilitator", {
    id: "st-19-agile-vendor-sandbox",
    description: "Vendor API sandbox is blocking the workstream. Capture the impediment.",
    expectedFrameworkBehavior: "Log blocker. Do not promise the blocker is fixed.",
    input: {
      user_message: "We are blocked on the vendor API sandbox — cannot proceed.",
      task_id: "TSK-API-07",
    },
    expected: {
      shouldAct: true,
      expectedTool: "log_blocker",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["blocker captured"],
    },
  }),
  sc("agile_facilitator", {
    id: "st-19-agile-not-percent",
    description: "InfoSec review impediment. Negative constraint: percent_complete_written false.",
    expectedFrameworkBehavior: "Blocker only — not a PMP progress write.",
    input: {
      user_message: "Impediment: waiting on InfoSec review before we can merge.",
      task_id: "TSK-SEC-03",
    },
    expected: {
      shouldAct: true,
      expectedTool: "log_blocker",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["not percent_complete"],
    },
  }),
  sc("prince2_governance_worker", {
    id: "st-20-gov-flag-exception",
    description: "15% budget overrun vs 10% tolerance. Flag prince2_exception_triggered. Do not pause the graph.",
    expectedFrameworkBehavior: "flag_exception. Pause belongs downstream.",
    input: {
      user_message: "Stage 2 forecast is 15% over the 10% cost tolerance.",
      tolerance_pct: 10,
      variance_pct: 15,
    },
    expected: {
      shouldAct: true,
      expectedTool: "flag_exception",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["prince2_exception_triggered true", "does not pause graph"],
    },
  }),
  sc("prince2_governance_worker", {
    id: "st-20-gov-within-tolerance",
    description: "3% variance vs 10% tolerance. Score only — no exception, no pause.",
    expectedFrameworkBehavior: "score_in_tolerance. prince2_exception_triggered false.",
    input: {
      user_message: "Stage 2 forecast is 3% over plan, still inside the 10% cost tolerance.",
      tolerance_pct: 10,
      variance_pct: 3,
    },
    expected: {
      shouldAct: true,
      expectedTool: "score_in_tolerance",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no exception", "does not pause"],
    },
  }),
  sc("prince2_governance_worker", {
    id: "st-20-gov-does-not-pause",
    description: "18% vs 10%. Flag exception. Negative constraint: graph_paused_by_this_worker is false.",
    expectedFrameworkBehavior: "Classify and score only. Do not escalate to the human PM yourself.",
    input: {
      user_message: "Compliance spend is 18% over the 10% stage tolerance.",
      tolerance_pct: 10,
      variance_pct: 18,
    },
    expected: {
      shouldAct: true,
      expectedTool: "flag_exception",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["worker does not pause"],
    },
  }),
  sc("chasing_agent", {
    id: "st-21-chase-fatigue-4h",
    description: "API Gateway Migration last chased 4 hours ago, due in 5 days, impact 9. Fatigue forces score 0.",
    expectedFrameworkBehavior: "suppress_chase despite high impact.",
    input: {
      task_id: "TSK-FATIGUE-4H",
      hours_since_last_contact: 4,
      days_to_deadline: 5,
      critical_path_impact: 9,
      linked_risks_severity: 8,
      assignee: "Sarah (Backend)",
      task_name: "API Gateway Migration",
    },
    expected: {
      shouldAct: false,
      expectedTool: "suppress_chase",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["chasing_score 0.0", "inside 24h window"],
    },
  }),
  sc("chasing_agent", {
    id: "st-21-chase-high-proximity",
    description: "PCI evidence pack due tomorrow, last contact 30 hours ago, impact 10 / risk 10. Must chase.",
    expectedFrameworkBehavior: "send_teams_chase with proximity-weighted score 243.",
    input: {
      task_id: "TSK-CRITICAL-TOMORROW",
      hours_since_last_contact: 30,
      days_to_deadline: 1,
      critical_path_impact: 10,
      linked_risks_severity: 10,
      assignee: "Alex (Payments)",
      task_name: "PCI evidence pack for go-live",
    },
    expected: {
      shouldAct: true,
      expectedTool: "send_teams_chase",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["outside fatigue", "high proximity chase"],
    },
  }),
  sc("chasing_agent", {
    id: "st-21-chase-quiet-update",
    description: "Chris replied 12 hours ago that the regression pack is in progress. Fatigue reset suppresses chase.",
    expectedFrameworkBehavior: "suppress_chase after quiet update.",
    input: {
      task_id: "TSK-QUIET-UPDATE",
      hours_since_last_contact: 12,
      days_to_deadline: 3,
      critical_path_impact: 7,
      linked_risks_severity: 6,
      assignee: "Chris (QA)",
      task_name: "Regression pack for release 12",
      last_assignee_message: "I'm working on it — first pass by tomorrow.",
    },
    expected: {
      shouldAct: false,
      expectedTool: "suppress_chase",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["quiet update resets fatigue"],
    },
  }),
  sc("chasing_agent", {
    id: "st-21-chase-floor-priority",
    description: "Iconography tidy-up due in 30 days, impact 1 / risk 1, fatigue expired. Engine still scores 2.7 and chases.",
    expectedFrameworkBehavior: "Outside fatigue the floor score is 2.7, so send_teams_chase.",
    input: {
      task_id: "TSK-FLOOR",
      hours_since_last_contact: 48,
      days_to_deadline: 30,
      critical_path_impact: 1,
      linked_risks_severity: 1,
      assignee: "Mina (Design)",
      task_name: "Iconography tidy-up",
    },
    expected: {
      shouldAct: true,
      expectedTool: "send_teams_chase",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["floor score 2.7 is not zero"],
    },
  }),
  sc("chasing_agent", {
    id: "st-21-chase-eligible-mid",
    description: "DNS cutover due in 5 days, last chase 48 hours ago, impact 6 / risk 5. Eligible chase.",
    expectedFrameworkBehavior: "send_teams_chase. Score = (6*1.5 + 5*1.2) * 5 = 75.",
    input: {
      task_id: "TSK-DNS",
      hours_since_last_contact: 48,
      days_to_deadline: 5,
      critical_path_impact: 6,
      linked_risks_severity: 5,
      assignee: "Jonah (Infra)",
      task_name: "Cut over production DNS",
    },
    expected: {
      shouldAct: true,
      expectedTool: "send_teams_chase",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["outside cooldown", "chase eligible"],
    },
  }),
  sc("sharepoint_delta_ingestion", {
    id: "st-22-sp-first-insert",
    description: "First seen SharePoint item with a new SHA-256. Insert into document_cache.",
    expectedFrameworkBehavior: "is_insert true.",
    input: {
      sharepoint_item_id: "test_docs:kickoff.md",
      content_hash: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      seen_before: false,
    },
    expected: {
      shouldAct: true,
      expectedTool: "upsert_document_cache",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["first insert"],
    },
  }),
  sc("sharepoint_delta_ingestion", {
    id: "st-22-sp-duplicate-upsert",
    description: "Same item and same SHA-256 on a second delta. Upsert last_seen_at, not a new document.",
    expectedFrameworkBehavior: "Duplicate is update, not insert-as-new.",
    input: {
      sharepoint_item_id: "test_docs:budget_variance.md",
      content_hash: "484603a85cf9aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      seen_before: true,
    },
    expected: {
      shouldAct: true,
      expectedTool: "upsert_document_cache",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["SHA-256 upsert", "duplicate is update"],
    },
  }),
  sc("sharepoint_delta_ingestion", {
    id: "st-22-sp-new-hash-insert",
    description: "Same SharePoint item id but a new content hash (file edited). Treat as a fresh content insert path.",
    expectedFrameworkBehavior: "New hash is not the duplicate-upsert case.",
    input: {
      sharepoint_item_id: "test_docs:budget_variance.md",
      content_hash: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      seen_before: false,
    },
    expected: {
      shouldAct: true,
      expectedTool: "upsert_document_cache",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["new hash is insert"],
    },
  }),
  sc("billing_gatekeeper", {
    id: "st-23-bill-trial-exhausted",
    description: "billing_status=trial_exhausted. Hard-halt before any Azure OpenAI call.",
    expectedFrameworkBehavior: "hard_halt. No worker LLM call.",
    input: { billing_status: "trial_exhausted", plan_tier: "free_trial", agent_key: "change_control_clerk" },
    expected: {
      shouldAct: false,
      expectedTool: "hard_halt",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["gateway halt", "no Azure OpenAI"],
    },
  }),
  sc("billing_gatekeeper", {
    id: "st-23-bill-paid-halt",
    description: "billing_status=paid_halt. Same hard halt on a previously paying tenant.",
    expectedFrameworkBehavior: "hard_halt before Azure OpenAI.",
    input: { billing_status: "paid_halt", plan_tier: "paid_monthly", agent_key: "pmp_schedule_specialist" },
    expected: {
      shouldAct: false,
      expectedTool: "hard_halt",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["paid_halt hard stop"],
    },
  }),
  sc("billing_gatekeeper", {
    id: "st-23-bill-standard-free-trial",
    description: "risk_radar_monitor on free_trial with active billing still hits Standard Tier denial.",
    expectedFrameworkBehavior: "pilot_feature_denied. No Azure call for Standard Tier on free_trial.",
    input: { billing_status: "active", plan_tier: "free_trial", agent_key: "risk_radar_monitor" },
    expected: {
      shouldAct: false,
      expectedTool: "pilot_feature_denied",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["standard tier denied on free_trial"],
    },
  }),
  sc("billing_gatekeeper", {
    id: "st-23-bill-paid-allow",
    description: "paid_monthly, billing active, Pilot-Allowed clerk. Gate allows the turn.",
    expectedFrameworkBehavior: "allow_turn. Azure may be called.",
    input: { billing_status: "active", plan_tier: "paid_monthly", agent_key: "change_control_clerk" },
    expected: {
      shouldAct: true,
      expectedTool: "allow_turn",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["gate allows turn"],
    },
  }),
  sc("friction_breaker", {
    id: "st-24-friction-vague-2-override",
    description: "vague_turns=2 and LLM proposed pmp_worker. Friction Breaker overrides to escalation_node.",
    expectedFrameworkBehavior: "escalate. Ignore LLM next_node.",
    input: { vague_turns: 2, llm_next_node: "pmp_worker", user_message: "not sure, whatever you think" },
    expected: {
      shouldAct: true,
      expectedTool: "escalate",
      expectedNextNode: "escalation_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["vague_turns >= 2", "LLM next_node ignored"],
    },
  }),
  sc("friction_breaker", {
    id: "st-24-friction-vague-0-honor",
    description: "vague_turns=0, LLM proposed pmp_worker. Friction Breaker does not fire.",
    expectedFrameworkBehavior: "honor_llm_route to pmp_worker.",
    input: { vague_turns: 0, llm_next_node: "pmp_worker", user_message: "Logged 6h today; TSK-002 is 40% complete." },
    expected: {
      shouldAct: true,
      expectedTool: "honor_llm_route",
      expectedNextNode: "pmp_worker",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["friction breaker did not fire"],
    },
  }),
  sc("friction_breaker", {
    id: "st-24-friction-vague-1-honor",
    description: "One vague turn is not enough. Honor the LLM route to agile_worker.",
    expectedFrameworkBehavior: "vague_turns=1 does not override.",
    input: { vague_turns: 1, llm_next_node: "agile_worker", user_message: "hmm not really sure what you need from me" },
    expected: {
      shouldAct: true,
      expectedTool: "honor_llm_route",
      expectedNextNode: "agile_worker",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["single vague turn is not escalation"],
    },
  }),
  sc("token_loop_breaker", {
    id: "st-25-token-3-hard-fail",
    description: "Router structured-output fails three times. Exhaust retries and route hard_fail_node.",
    expectedFrameworkBehavior: "hard_fail after 3 schema corrections.",
    input: { schema_failures: 3 },
    expected: {
      shouldAct: true,
      expectedTool: "hard_fail",
      expectedNextNode: "hard_fail_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["retry_count 3", "hard_fail_node"],
    },
  }),
  sc("token_loop_breaker", {
    id: "st-25-token-1-retry",
    description: "One schema failure is still inside the self-correction budget.",
    expectedFrameworkBehavior: "retry_schema. Return to router_node.",
    input: { schema_failures: 1 },
    expected: {
      shouldAct: true,
      expectedTool: "retry_schema",
      expectedNextNode: "router_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["still within 3 retries"],
    },
  }),
  sc("token_loop_breaker", {
    id: "st-25-token-2-retry",
    description: "Two schema failures: still retry, not hard_fail.",
    expectedFrameworkBehavior: "retry_schema at failure count 2.",
    input: { schema_failures: 2 },
    expected: {
      shouldAct: true,
      expectedTool: "retry_schema",
      expectedNextNode: "router_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["not exhausted"],
    },
  }),
  sc("pm_veto_interrupt", {
    id: "st-26-veto-pause-no-write",
    description: "PendingChangePayload exists, PM has not decided. Pause. apply_baseline_change is not called.",
    expectedFrameworkBehavior: "suspend_for_veto. wroteBaseline false.",
    input: { pending_change: PENDING, pm_veto_decision: null },
    expected: {
      shouldAct: true,
      expectedTool: "suspend_for_veto",
      expectedNextNode: "suspend_for_veto_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["graph paused", "apply_baseline_change not called"],
    },
  }),
  sc("pm_veto_interrupt", {
    id: "st-26-veto-approve-handoff",
    description: "PM approved. Interrupt hands off to baseline_commit_node but does not itself write.",
    expectedFrameworkBehavior: "baseline_commit next_node. This node still mustNotWriteBaseline.",
    input: { pending_change: PENDING, pm_veto_decision: "approve" },
    expected: {
      shouldAct: true,
      expectedTool: "baseline_commit",
      expectedNextNode: "baseline_commit_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["handoff only", "interrupt does not write"],
    },
  }),
  sc("pm_veto_interrupt", {
    id: "st-26-veto-reject-no-write",
    description: "PM rejected the baseline slip. Discard the proposal. Never write the baseline.",
    expectedFrameworkBehavior: "discard_pending_change. wroteBaseline false.",
    input: { pending_change: PENDING, pm_veto_decision: "reject" },
    expected: {
      shouldAct: true,
      expectedTool: "discard_pending_change",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["rejected", "no baseline write"],
    },
  }),
  sc("prince2_exception_interrupt", {
    id: "st-27-exc-suspend-no-commit",
    description: "Governance already set prince2_exception_triggered=true. Writeback must pause, not commit_risk_escalation.",
    expectedFrameworkBehavior: "suspend_for_exception. No silent commit.",
    input: { prince2_exception_triggered: true, risk_category: "budget", severity: 5 },
    expected: {
      shouldAct: true,
      expectedTool: "suspend_for_exception",
      expectedNextNode: "suspend_for_exception_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no silent commit", "suspend_for_exception_node"],
    },
  }),
  sc("prince2_exception_interrupt", {
    id: "st-27-exc-in-tolerance-commit",
    description: "prince2_exception_triggered=false. In-tolerance risk may be committed; still no baseline write.",
    expectedFrameworkBehavior: "commit_risk_escalation for in-tolerance only.",
    input: { prince2_exception_triggered: false, risk_category: "timeline", severity: 2 },
    expected: {
      shouldAct: true,
      expectedTool: "commit_risk_escalation",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["in-tolerance commit", "no baseline write"],
    },
  }),
  sc("prince2_exception_interrupt", {
    id: "st-27-exc-no-baseline-write",
    description: "Triggered compliance exception, severity 5. Suspend. Negative constraint: no baseline mutation.",
    expectedFrameworkBehavior: "Pause. Do not rewrite baseline while suspended.",
    input: { prince2_exception_triggered: true, risk_category: "compliance", severity: 5 },
    expected: {
      shouldAct: true,
      expectedTool: "suspend_for_exception",
      expectedNextNode: "suspend_for_exception_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["no baseline write while suspended"],
    },
  }),
  sc("change_control_clerk", {
    id: "st-01-clerk-publishes-slip-event",
    description:
      "Aim 1: clerk drafts a slip and mechanically publishes BASELINE_SLIP_REQUESTED with no risk fields, then suspends for PM Veto.",
    expectedFrameworkBehavior:
      "draft_pending_change + BASELINE_SLIP_REQUESTED. authorized=false. No risk questions.",
    input: {
      user_request: "Move the locked baseline end date from 2026-12-01 to 2027-04-01.",
      target_table: "baselines",
      record_id: "PROJECT-DELTA-BASELINE",
    },
    expected: {
      shouldAct: true,
      expectedTool: "draft_pending_change",
      expectedNextNode: "suspend_for_veto_node",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["BASELINE_SLIP_REQUESTED published", "no risk fields", "veto paused"],
    },
  }),
  sc("prince2_governance_worker", {
    id: "st-20-gov-proactive-no-baseline",
    description:
      "Aim 2: event-bus wake after a baseline slip. Governance discovers RAID and must not edit pending_change.",
    expectedFrameworkBehavior: "score/flag risk only. pending_change untouched. mustNotWriteBaseline.",
    input: {
      user_message: "Proactive event-bus wake: BASELINE_SLIP_REQUESTED correlation=chg-delta-1.",
      tolerance_pct: 10,
      variance_pct: 4,
      wake_reason: "event_bus",
      pending_change: PENDING,
    },
    expected: {
      shouldAct: true,
      expectedTool: "score_in_tolerance",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["proactive RAID only", "pending_change unchanged"],
    },
  }),
  sc("chasing_agent", {
    id: "st-21-chase-slip-fatigue-suppress",
    description:
      "CRITICAL_PATH_SLIPPED but last contact was 3 hours ago. Fatigue still suppresses the chase.",
    expectedFrameworkBehavior: "suppress_chase. Do not draft a baseline change.",
    input: {
      task_id: "TSK-SLIP-FATIGUE",
      hours_since_last_contact: 3,
      days_to_deadline: 1,
      critical_path_impact: 10,
      linked_risks_severity: 8,
      assignee: "Jonah (Infra)",
      task_name: "Cut over production DNS",
      wake_event: "CRITICAL_PATH_SLIPPED",
    },
    expected: {
      shouldAct: false,
      expectedTool: "suppress_chase",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["fatigue wins over slip event"],
    },
  }),
  sc("pmp_schedule_specialist", {
    id: "st-18-pmp-illegal-baseline-event",
    description: "Aim 2: PMP attempts to publish BASELINE_SLIP_REQUESTED. append_event hard-fails.",
    expectedFrameworkBehavior: "reject_illegal_publish. No baseline write.",
    input: {
      task_id: "TSK-002",
      percent_complete: 50,
      actual_hours_spent: 4,
      illegal_publish_baseline: true,
    },
    expected: {
      shouldAct: false,
      expectedTool: "reject_illegal_publish",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["illegal publisher/event-type pair rejected"],
    },
  }),
  sc("pm_veto_interrupt", {
    id: "st-26-veto-rejected-event-no-redraft",
    description:
      "Aim 3: PM rejects the slip. BASELINE_CHANGE_REJECTED is published. Clerk does not auto-redraft.",
    expectedFrameworkBehavior: "discard_pending_change. clerk_auto_redraft false. wroteBaseline false.",
    input: { pending_change: PENDING, pm_veto_decision: "reject" },
    expected: {
      shouldAct: true,
      expectedTool: "discard_pending_change",
      mustNotWriteBaseline: true,
      goldTraceAssertions: ["BASELINE_CHANGE_REJECTED", "no auto-redraft"],
    },
  }),
];

function main(): void {
  const parsed = StructuredScenarioArraySchema.parse(scenarios);
  const outPath = join(here, "structuredGiaboScenarios.json");
  writeFileSync(outPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
  const byRole = new Map<string, number>();
  for (const row of parsed) {
    byRole.set(row.targetAgentRole, (byRole.get(row.targetAgentRole) ?? 0) + 1);
  }
  console.log(`PASS: wrote ${parsed.length} structured scenarios to ${outPath}`);
  for (const role of GIABO_ROLE_IDS) {
    console.log(`  ${GIABO_ROLE_IDS.indexOf(role) + 1}/27 ${role}: ${byRole.get(role)}`);
  }
}

main();
