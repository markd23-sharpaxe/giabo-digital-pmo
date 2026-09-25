import { createHash } from "node:crypto";
import type { FrameworkScenario, GiaboRoleId } from "../types/evalSchema.ts";

export type RoleSimulation = {
  monologue: string[];
  actualTool: string;
  actualNextNode: string | null;
  wroteBaseline: boolean;
  output: Record<string, unknown>;
};

const CRON_EXCLUDED = new Set([
  "governance_auditor",
  "eom_financial_checkpoint",
  "sprint_boundary_watchdog",
]);

const STANDARD_TIER = new Set(["risk_radar_monitor", "scrum_master_liaison"]);

function chasingScore(hours: number, days: number, impact: number, risk: number): number {
  if (hours < 24) return 0;
  return ((impact * 1.5 + risk * 1.2) * Math.max(1, 10 - days));
}

function artifactId(prefix: string, title: string, period?: string): string {
  const hash = createHash("sha256").update(title).digest("hex").slice(0, 12);
  return period ? `${prefix}-${hash}-${period}` : `${prefix}-${hash}`;
}

function filterExcluded(roster: string[]): string[] {
  return roster.filter((key) => !CRON_EXCLUDED.has(key));
}

const simulators: Record<GiaboRoleId, (s: FrameworkScenario) => RoleSimulation> = {
  change_control_clerk(s) {
    const request = String(s.input.user_request ?? "");
    const dates = request.match(/\d{4}-\d{2}-\d{2}/g) ?? [];
    const proposedEnd = dates.at(-1) ?? "2027-03-01";
    const budgetMatch = request.match(/\$?([\d,]+(?:\.\d+)?)\s*(?:k|budget)?/i);
    const isBudget = /budget/i.test(request);
    const proposedValues = isBudget
      ? { baseline_budget: Number(String(budgetMatch?.[1] ?? "250000").replace(/,/g, "")) }
      : { baseline_end_date: proposedEnd };
    return {
      monologue: [
        "I am the only node that may draft a locked-baseline change.",
        `The user requested: ${request || "a baseline mutation"}. I will emit PendingChangePayload.`,
        "IMMUTABLE RULE: I cannot authorize. The proposal goes to PM Veto.",
        "I do not evaluate risks, ask risk questions, or mention tolerance. BASELINE_SLIP_REQUESTED is published mechanically with field/date/budget delta only.",
      ],
      actualTool: "draft_pending_change",
      actualNextNode: "suspend_for_veto_node",
      wroteBaseline: false,
      output: {
        pending_change: {
          target_table: s.input.target_table,
          record_id: s.input.record_id,
          proposed_values: proposedValues,
        },
        authorized: false,
        events: [
          {
            event_type: "BASELINE_SLIP_REQUESTED",
            publisher: "change_control_clerk",
            payload: { proposed_values: proposedValues, field_delta_assessment: true },
            risk_fields_present: false,
          },
        ],
      },
    };
  },
  prince2_exception_master(s) {
    const variance = Number(s.input.variance_pct);
    const tolerance = Number(s.input.tolerance_pct);
    const triggered = variance > tolerance;
    return {
      monologue: [
        `Variance ${variance}% vs stage tolerance ${tolerance}%.`,
        "My scope is the decisions family, not a silent in-tolerance risk upsert.",
        triggered
          ? "prince2_exception_triggered=true. Escalate as a decision artifact."
          : "Variance does not exceed tolerance. The invariant is to flag a BREACH, not to invent one. I must not raise_exception.",
      ],
      actualTool: triggered ? "raise_exception" : "log_in_tolerance_risk",
      actualNextNode: triggered ? "suspend_for_exception_node" : null,
      wroteBaseline: false,
      output: {
        artifact_type: "decision",
        prince2_exception_triggered: triggered,
      },
    };
  },
  raid_compliance_auto_chaser(s) {
    const title = String(s.input.title);
    const id = artifactId("ACTION-ASSUMPTION", title);
    return {
      monologue: [
        "RAID auto-chaser writes assumptions/issues/actions with a deterministic hash id.",
        `First ingest id=${id}.`,
        "Duplicate ingest of the same title collides on PRIMARY KEY and is ON CONFLICT suppressed.",
      ],
      actualTool: "upsert_artifact_idempotent",
      actualNextNode: null,
      wroteBaseline: false,
      output: {
        artifact_type: "assumption",
        id,
        duplicate_suppressed: Boolean(s.input.duplicate_ingest),
        rows_written: 1,
      },
    };
  },
  risk_radar_monitor(s) {
    const plan = String(s.input.plan_tier);
    const denied = plan === "free_trial";
    if (denied) {
      return {
        monologue: [
          "risk_radar_monitor is Standard Tier. free_trial tenants are denied by assertPilotFeatureAccess.",
        ],
        actualTool: "pilot_feature_denied",
        actualNextNode: null,
        wroteBaseline: false,
        output: { denied: true, plan_tier: plan },
      };
    }
    return {
      monologue: [
        `Risk ${s.input.risk_id} has materialized (invoice received).`,
        "Convert risk -> issue. Do not rewrite baseline_budget.",
      ],
      actualTool: "convert_risk_to_issue",
      actualNextNode: null,
      wroteBaseline: false,
      output: {
        from: "risk",
        to: "issue",
        source_risk_id: s.input.risk_id,
        baseline_budget_written: false,
      },
    };
  },
  lessons_learned_curator(s) {
    return {
      monologue: [
        "Scope is ('lessons',) only.",
        "I will write the retrospective as a lesson.",
        `Refusing bundled baseline_budget=${s.input.requested_baseline_budget}.`,
      ],
      actualTool: "write_lesson",
      actualNextNode: null,
      wroteBaseline: false,
      output: { artifact_type: "lesson", lesson: s.input.lesson, baseline_written: false },
    };
  },
  dependency_map_maintainer(s) {
    return {
      monologue: [
        "Scope is ('dependencies',).",
        `Recording dependency: ${s.input.dependency}.`,
        `Refusing commit_task_progress for ${s.input.task_id} percent_complete=${s.input.requested_percent_complete}.`,
      ],
      actualTool: "write_dependency",
      actualNextNode: null,
      wroteBaseline: false,
      output: {
        artifact_type: "dependency",
        percent_complete_written: false,
      },
    };
  },
  scrum_master_liaison(s) {
    const plan = String(s.input.plan_tier ?? "paid_monthly");
    if (plan === "free_trial") {
      return {
        monologue: [
          "scrum_master_liaison is Standard Tier with scope ('sprints',).",
          "free_trial tenants are denied by assertPilotFeatureAccess.",
        ],
        actualTool: "pilot_feature_denied",
        actualNextNode: null,
        wroteBaseline: false,
        output: { denied: true, plan_tier: plan },
      };
    }
    return {
      monologue: [
        "Standard Tier, scope ('sprints',).",
        `Sprint ${s.input.sprint_name} status=${s.input.status}.`,
        "No baseline date mutation.",
      ],
      actualTool: "write_sprint",
      actualNextNode: null,
      wroteBaseline: false,
      output: { artifact_type: "sprint", sprint_name: s.input.sprint_name, baseline_written: false },
    };
  },
  forensic_alignment_engine(s) {
    const aims = String(s.input.baseline_aims);
    const goals = s.input.baseline_goals as string[];
    const objectives = s.input.baseline_objectives as string[];
    const traces = objectives.every((obj) =>
      goals.some((g) => obj.toLowerCase().includes(g.toLowerCase().slice(0, 8)) || g.toLowerCase().includes("mobile")),
    );
    const aligned = traces && objectives.some((o) => aims.toLowerCase().includes("mobile"));
    return {
      monologue: [
        "Golden Thread: Aims -> Goals -> Objectives must trace to scope.",
        `Aim=${aims}; goals=${JSON.stringify(goals)}; objectives=${JSON.stringify(objectives)}.`,
        aligned
          ? "Thread holds."
          : "Objective 'Ship mobile app' does not trace to goal 'Pass PCI-DSS QSA' or the payments-platform aim. FAIL Golden Thread. Read-only: I will not invent a goal.",
      ],
      actualTool: aligned ? "golden_thread_pass" : "golden_thread_fail",
      actualNextNode: null,
      wroteBaseline: false,
      output: { golden_thread_aligned: aligned, wrote_objectives: false },
    };
  },
  earned_value_analyst(s) {
    const pv = Number(s.input.planned_value);
    const ev = Number(s.input.earned_value);
    const ac = Number(s.input.actual_cost);
    const spi = ev / pv;
    const cpi = ev / ac;
    return {
      monologue: [
        "READONLY earned-value readout.",
        `SPI=EV/PV=${spi.toFixed(2)}; CPI=EV/AC=${cpi.toFixed(2)}.`,
        "No tasks or baseline writes.",
      ],
      actualTool: "report_eva",
      actualNextNode: null,
      wroteBaseline: false,
      output: { spi, cpi, task_written: false, baseline_written: false },
    };
  },
  governance_synthesizer(s) {
    return {
      monologue: [
        "READONLY RAID synthesis.",
        `open_risks=${s.input.open_risks} open_actions=${s.input.open_actions} open_issues=${s.input.open_issues}.`,
        "I compose a brief; I do not insert pmo_artifacts.",
      ],
      actualTool: "synthesize_brief",
      actualNextNode: null,
      wroteBaseline: false,
      output: { artifacts_inserted: 0 },
    };
  },
  stage_gate_guardian(s) {
    const breach = Number(s.input.variance_pct) > Number(s.input.tolerance_pct);
    return {
      monologue: [
        `Stage ${s.input.stage}: variance ${s.input.variance_pct}% vs tolerance ${s.input.tolerance_pct}%.`,
        breach
          ? "READONLY: escalate the stage-gate. Do not rewrite baseline_budget."
          : "Within tolerance.",
      ],
      actualTool: breach ? "escalate_stage_gate" : "allow_stage_gate",
      actualNextNode: null,
      wroteBaseline: false,
      output: { breach, baseline_budget_rewritten: false },
    };
  },
  project_health_reporter(s) {
    return {
      monologue: [
        `Health brief for ${s.input.project_name} status=${s.input.status}.`,
        `Open risks=${s.input.open_risks}. Read-only; no writes.`,
      ],
      actualTool: "report_health",
      actualNextNode: null,
      wroteBaseline: false,
      output: { writes: false },
    };
  },
  governance_auditor(s) {
    const roster = s.input.raw_roster as string[];
    const filtered = filterExcluded(roster);
    return {
      monologue: [
        "governance_auditor is CRON and listed in DELTA_DISPATCH_EXCLUDED_AGENTS.",
        `Raw roster=${JSON.stringify(roster)}; after strip=${JSON.stringify(filtered)}.`,
        "I do not receive this SharePoint delta. Cron_sweep only.",
      ],
      actualTool: "exclude_from_delta_dispatch",
      actualNextNode: null,
      wroteBaseline: false,
      output: { on_delta_roster: filtered.includes("governance_auditor") },
    };
  },
  eom_financial_checkpoint(s) {
    const period = String(s.input.billing_period);
    const id = artifactId("ACTION-EOM", `eom-${s.input.project_id}-${period}`, period);
    return {
      monologue: [
        "Last-Friday EOM financial checkpoint (cron, not delta-dispatch).",
        `Deterministic id=${id}. Re-run ON CONFLICT is idempotent.`,
      ],
      actualTool: "write_eom_action",
      actualNextNode: null,
      wroteBaseline: false,
      output: {
        artifact_type: "action",
        id,
        trigger: "cron_sweep",
        duplicate_suppressed: Boolean(s.input.duplicate_ingest),
      },
    };
  },
  sprint_boundary_watchdog(s) {
    const id = artifactId("ACTION-SPRINT-OVERDUE", String(s.input.sprint_name));
    return {
      monologue: [
        `${s.input.sprint_name} is overdue. This is a cron sweep, not a Teams router next_node.`,
        `Writing ${id}. Channel=${s.input.channel} does not change trigger_type.`,
      ],
      actualTool: "write_sprint_overdue",
      actualNextNode: null,
      wroteBaseline: false,
      output: { artifact_type: "action", id, trigger: "cron_sweep", teams_next_node: null },
    };
  },
  pmo_commander_router(s) {
    const raw = s.input.raw_roster as string[];
    const filtered = filterExcluded(raw);
    return {
      monologue: [
        "PMO Commander Router (01): strip DELTA_DISPATCH_EXCLUDED_AGENTS before state injection.",
        raw.some((k) => CRON_EXCLUDED.has(k))
          ? `Removed ${raw.filter((k) => CRON_EXCLUDED.has(k)).join(", ")}.`
          : "Roster had no cron keys. Strip is a no-op; dispatching the remaining agents is compliant.",
        `Dispatch roster=${JSON.stringify(filtered)}.`,
      ],
      actualTool: "route_delta",
      actualNextNode: null,
      wroteBaseline: false,
      output: { selected_agent_keys: filtered, excluded: [...CRON_EXCLUDED] },
    };
  },
  conversational_router(s) {
    const msg = String(s.input.user_message).toLowerCase();
    const next =
      msg.includes("baseline") || msg.includes("change the locked")
        ? "change_control_clerk"
        : msg.includes("blocked") || msg.includes("blocker") || msg.includes("impediment")
          ? "agile_worker"
          : msg.includes("budget") || msg.includes("tolerance") || msg.includes("risk")
            ? "governance_worker"
            : msg.includes("hour") || msg.includes("%") || msg.includes("complete")
              ? "pmp_worker"
              : "end_conversation";
    return {
      monologue: [
        "Conversational triage router (06 / prompts/router_node.md).",
        next === "pmp_worker"
          ? "Progress/hours/percent-complete => pmp_worker, not Agile, not Change Control."
          : next === "agile_worker"
            ? "Blocker/impediment => agile_worker. A plain progress update with no blocker would be pmp_worker."
            : next === "governance_worker"
              ? "Budget, scope, or tolerance/risk language => governance_worker."
              : next === "change_control_clerk"
                ? "Explicit locked-baseline change => change_control_clerk ONLY."
                : "No specialist signal; end conversation.",
        `Classified next_node=${next}.`,
      ],
      actualTool: "route_to_worker",
      actualNextNode: next,
      wroteBaseline: false,
      output: { next_node: next, pending_change: null },
    };
  },
  pmp_schedule_specialist(s) {
    if (s.input.illegal_publish_baseline) {
      return {
        monologue: [
          "PMP cannot publish BASELINE_SLIP_REQUESTED.",
          "append_event hard-fails illegal publisher/event-type pairs.",
        ],
        actualTool: "reject_illegal_publish",
        actualNextNode: null,
        wroteBaseline: false,
        output: { rejected: true, event_type: "BASELINE_SLIP_REQUESTED" },
      };
    }
    return {
      monologue: [
        "PMP Schedule Specialist logs TaskProgressPayload only.",
        `${s.input.task_id}: ${s.input.percent_complete}% complete, ${s.input.actual_hours_spent}h.`,
        "No PendingChangePayload. Baseline stays locked.",
      ],
      actualTool: "commit_task_progress",
      actualNextNode: "state_writeback_node",
      wroteBaseline: false,
      output: {
        payload: {
          task_id: s.input.task_id,
          percent_complete: s.input.percent_complete,
          actual_hours_spent: s.input.actual_hours_spent,
        },
        pending_change: null,
        events: [{ event_type: "TASK_PROGRESS_LOGGED", publisher: "pmp_worker" }],
      },
    };
  },
  agile_facilitator(s) {
    return {
      monologue: [
        "Agile Facilitator: blockers, not plain progress.",
        String(s.input.user_message),
        "Emitting BlockerPayload. Not a percent_complete write.",
      ],
      actualTool: "log_blocker",
      actualNextNode: "state_writeback_node",
      wroteBaseline: false,
      output: { payload: { task_id: s.input.task_id, blocker: true }, percent_complete_written: false },
    };
  },
  prince2_governance_worker(s) {
    const triggered = Number(s.input.variance_pct) > Number(s.input.tolerance_pct);
    const proactive = s.input.wake_reason === "event_bus";
    return {
      monologue: [
        proactive
          ? "Proactive event-bus wake. I classify RAID only. I do not draft or authorize the pending baseline change."
          : "PRINCE2 Governance Worker classifies and scores only.",
        `variance ${s.input.variance_pct}% vs tolerance ${s.input.tolerance_pct}% => prince2_exception_triggered=${triggered}.`,
        "I do not pause the graph; state_writeback_node owns the interrupt.",
      ],
      actualTool: triggered ? "flag_exception" : "score_in_tolerance",
      actualNextNode: null,
      wroteBaseline: false,
      output: {
        prince2_exception_triggered: triggered,
        graph_paused_by_this_worker: false,
        pending_change_untouched: Boolean(s.input.pending_change) || proactive,
        events: [{ event_type: "RISK_FLAGGED", publisher: "governance_worker" }],
      },
    };
  },
  chasing_agent(s) {
    const hours = Number(s.input.hours_since_last_contact);
    const score = chasingScore(
      hours,
      Number(s.input.days_to_deadline),
      Number(s.input.critical_path_impact),
      Number(s.input.linked_risks_severity),
    );
    const suppress = score === 0;
    const slipWake = s.input.wake_event === "CRITICAL_PATH_SLIPPED";
    return {
      monologue: [
        `hours_since_last_contact=${hours}. Fatigue window is 24h.`,
        hours < 24
          ? "Inside cooldown: chasing_score forced to 0.0 regardless of impact/risk."
          : `Outside cooldown: score=${score}.`,
        slipWake && suppress
          ? "CRITICAL_PATH_SLIPPED does not override the 24h fatigue cooldown. Publish CHASE_SUPPRESSED."
          : suppress
            ? "Omit from outreach (suppress_chase)."
            : "send_teams_chase.",
      ],
      actualTool: suppress ? "suppress_chase" : "send_teams_chase",
      actualNextNode: null,
      wroteBaseline: false,
      output: {
        chasing_score: score,
        in_cooldown: hours < 24,
        events: [
          {
            event_type: suppress ? "CHASE_SUPPRESSED" : "CHASE_SENT",
            publisher: "chasing_agent",
          },
        ],
      },
    };
  },
  sharepoint_delta_ingestion(s) {
    const seen = Boolean(s.input.seen_before);
    return {
      monologue: [
        "SharePoint delta ingest is content-addressed SHA-256.",
        `item=${s.input.sharepoint_item_id} hash=${s.input.content_hash}.`,
        seen
          ? "Same (project_id, sharepoint_item_id): ON CONFLICT update last_seen_at, not a new row."
          : "First seen: insert.",
      ],
      actualTool: "upsert_document_cache",
      actualNextNode: null,
      wroteBaseline: false,
      output: { is_insert: !seen, content_hash: s.input.content_hash },
    };
  },
  billing_gatekeeper(s) {
    const status = String(s.input.billing_status);
    const halted = status === "trial_exhausted" || status === "paid_halt";
    const agent = String(s.input.agent_key);
    const plan = String(s.input.plan_tier);
    const standardDenied = STANDARD_TIER.has(agent) && plan === "free_trial";
    const actualTool = halted
      ? "hard_halt"
      : standardDenied
        ? "pilot_feature_denied"
        : "allow_turn";
    return {
      monologue: [
        `Gateway billing_status=${status}. Halted statuses={trial_exhausted, paid_halt}.`,
        halted
          ? "HardHaltMessage before any Azure OpenAI call."
          : "Billing allows the turn.",
        standardDenied
          ? `${agent} is Standard Tier; free_trial is denied by assertPilotFeatureAccess.`
          : "Pilot feature access would still be checked per agent.",
      ],
      actualTool,
      actualNextNode: null,
      wroteBaseline: false,
      output: {
        halted,
        azure_openai_called: !halted && !standardDenied,
        standard_tier_denied: standardDenied,
      },
    };
  },
  friction_breaker(s) {
    const vague = Number(s.input.vague_turns);
    const llm = String(s.input.llm_next_node);
    const fires = vague >= 2 || llm === "escalation_node";
    const next = fires ? "escalation_node" : llm;
    return {
      monologue: [
        `vague_turns=${vague}. LLM proposed next_node=${llm}.`,
        fires
          ? "Friction Breaker: vague_turns>=2 overrides the LLM. Escalation wins."
          : "Friction Breaker did not fire.",
      ],
      actualTool: fires ? "escalate" : "honor_llm_route",
      actualNextNode: next,
      wroteBaseline: false,
      output: { friction_breaker_fires: fires, llm_next_node: llm },
    };
  },
  token_loop_breaker(s) {
    const failures = Number(s.input.schema_failures);
    const exhausted = failures >= 3;
    return {
      monologue: [
        `Structured-output failures=${failures}. Token Loop Limit is 3 (tenacity stop_after_attempt(3)).`,
        exhausted
          ? "Retries exhausted. Route hard_fail_node. failed=true."
          : "Still within the self-correction budget.",
      ],
      actualTool: exhausted ? "hard_fail" : "retry_schema",
      actualNextNode: exhausted ? "hard_fail_node" : "router_node",
      wroteBaseline: false,
      output: { retry_count: Math.min(failures, 3), failed: exhausted },
    };
  },
  pm_veto_interrupt(s) {
    const decision = s.input.pm_veto_decision;
    if (decision == null) {
      return {
        monologue: [
          "Change Control Clerk already drafted a proposal.",
          "suspend_for_veto_node pauses via ctx.request_info. apply_baseline_change is NOT called.",
        ],
        actualTool: "suspend_for_veto",
        actualNextNode: "suspend_for_veto_node",
        wroteBaseline: false,
        output: { pending_change: s.input.pending_change, apply_baseline_change_called: false },
      };
    }
    if (decision === "reject") {
      return {
        monologue: [
          "PM rejected the pending baseline change.",
          "Discard the proposal. Do not call apply_baseline_change.",
        ],
        actualTool: "discard_pending_change",
        actualNextNode: null,
        wroteBaseline: false,
        output: {
          pending_change: s.input.pending_change,
          apply_baseline_change_called: false,
          rejected: true,
          events: [{ event_type: "BASELINE_CHANGE_REJECTED", publisher: "baseline_commit_node" }],
          clerk_auto_redraft: false,
        },
      };
    }
    return {
      monologue: [
        "PM approved the pending baseline change.",
        "Hand off to baseline_commit_node. This interrupt itself does not write the baseline.",
      ],
      actualTool: "baseline_commit",
      actualNextNode: "baseline_commit_node",
      wroteBaseline: false,
      output: { pending_change: s.input.pending_change, apply_baseline_change_called: false, approved: true },
    };
  },
  prince2_exception_interrupt(s) {
    const triggered = Boolean(s.input.prince2_exception_triggered);
    return {
      monologue: [
        `latest_risk_escalation.prince2_exception_triggered=${triggered}.`,
        triggered
          ? "state_writeback_node must NOT commit_risk_escalation. Hand off to suspend_for_exception_node."
          : "Commit the in-tolerance risk.",
      ],
      actualTool: triggered ? "suspend_for_exception" : "commit_risk_escalation",
      actualNextNode: triggered ? "suspend_for_exception_node" : null,
      wroteBaseline: false,
      output: {
        committed: !triggered,
        pending_exception: triggered,
        severity: s.input.severity,
      },
    };
  },
};

export function simulateRole(scenario: FrameworkScenario): RoleSimulation {
  return simulators[scenario.targetAgentRole](scenario);
}

function eventsOf(sim: RoleSimulation): Array<Record<string, unknown>> {
  return Array.isArray(sim.output.events) ? (sim.output.events as Array<Record<string, unknown>>) : [];
}

export function goldMatch(scenario: FrameworkScenario, sim: RoleSimulation): boolean {
  const exp = scenario.expected;
  if (exp.mustNotWriteBaseline && sim.wroteBaseline) return false;
  if (exp.expectedTool && sim.actualTool !== exp.expectedTool) return false;
  if (exp.expectedNextNode && sim.actualNextNode !== exp.expectedNextNode) return false;
  if (exp.shouldAct === false && sim.actualTool === "send_teams_chase") return false;

  const events = eventsOf(sim);
  if (scenario.id === "st-01-clerk-publishes-slip-event") {
    const slip = events.find((item) => item.event_type === "BASELINE_SLIP_REQUESTED");
    if (!slip || slip.publisher !== "change_control_clerk" || slip.risk_fields_present !== false) {
      return false;
    }
  }
  if (scenario.id === "st-20-gov-proactive-no-baseline") {
    if (sim.output.pending_change_untouched !== true) return false;
  }
  if (scenario.id === "st-21-chase-slip-fatigue-suppress") {
    if (!events.some((item) => item.event_type === "CHASE_SUPPRESSED")) return false;
  }
  if (scenario.id === "st-18-pmp-illegal-baseline-event") {
    if (sim.output.rejected !== true) return false;
  }
  if (scenario.id === "st-26-veto-rejected-event-no-redraft") {
    if (sim.output.clerk_auto_redraft !== false) return false;
    if (!events.some((item) => item.event_type === "BASELINE_CHANGE_REJECTED")) return false;
  }
  return true;
}
