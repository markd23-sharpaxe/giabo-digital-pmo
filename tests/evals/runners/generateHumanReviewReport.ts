/**
 * Compile a narrative executive Human Review Report from bulk (and optional chaser) eval logs.
 * Does not re-run simulations or Azure judging.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { FrameworkScenario, GiaboRoleId, JudgeVerdict } from "../types/evalSchema.ts";
import type { RoleSimulation } from "./simulateRole.ts";

const here = dirname(fileURLToPath(import.meta.url));
const resultsDir = join(here, "../results");
const bulkLogPath = join(resultsDir, "bulkEvalLog.json");
const chaserLogPath = join(resultsDir, "chaserEvalLog.json");
const outPath = join(resultsDir, "humanReviewReport.md");

const MAX_STORIES = 3;

const KEY_ROLES: { label: string; roleId: GiaboRoleId; persona: string }[] = [
  { label: "Chaser", roleId: "chasing_agent", persona: "Dynamic Chasing Agent" },
  { label: "Risk Agent", roleId: "risk_radar_monitor", persona: "Risk Radar Monitor (Standard Tier)" },
  { label: "PMP Worker", roleId: "pmp_schedule_specialist", persona: "PMP Schedule Specialist" },
  { label: "Agile Worker", roleId: "agile_facilitator", persona: "Agile Facilitator (servant-leader)" },
  { label: "Governance Worker", roleId: "prince2_governance_worker", persona: "PRINCE2 Governance Worker" },
  { label: "Change Control Clerk", roleId: "change_control_clerk", persona: "Change Control Clerk" },
  { label: "Router", roleId: "conversational_router", persona: "Conversational Router (Teams / Copilot triage)" },
];

const CHASER_PREFERRED_IDS = [
  "redundant-chase-fatigue-4h",
  "fatigue-expired-high-proximity",
  "quiet-update-resets-fatigue",
  "priority-conflict-proximity-vs-impact",
  "floor-priority-far-deadline",
  "bulk-chaser-fatigue",
  "bulk-chaser-proximity",
  "bulk-chaser-expired-high",
  "bulk-chaser-quiet-update",
  "bulk-chaser-floor",
  "fw-21-chasing-agent-24h-fatigue",
];

const CHASER_RULE = {
  mdc: "08-maf-dynamic-chasing-persona.mdc",
  implementingFile: "maf_graph_state.py",
  invariantQuote:
    "If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.",
};

type StoryRow = {
  scenario: FrameworkScenario & { name?: string };
  simulation: RoleSimulation;
  verdict: JudgeVerdict;
  judgeSource: "azure" | "deterministic";
};

type BulkLog = {
  runId: string;
  startedAt: string;
  endedAt?: string;
  modelDeployment?: string;
  rows: StoryRow[];
};

type ChaserLogEntry = {
  scenario: {
    id: string;
    name: string;
    description: string;
    input: {
      project_id: string;
      tasks: Array<Record<string, unknown>>;
    };
    expected: Record<string, unknown>;
  };
  trace: { monologue: string[] };
  tools: Array<{ tool: string; taskId: string; arguments: Record<string, unknown> }>;
  verdict: JudgeVerdict;
};

type ChaserLog = {
  runId?: string;
  startedAt?: string;
  scenarios: ChaserLogEntry[];
};

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asBool(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function slug(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function duePhrase(days: number): string {
  if (days <= 0) return "due today";
  if (days === 1) return "due tomorrow";
  return `due in ${days} days`;
}

function contactPhrase(hours: number): string {
  if (hours < 48) return `${hours} hours ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

function classifyMessage(msg: string): string {
  const m = msg.toLowerCase();
  if (m.includes("baseline") || m.includes("change the locked")) return "baseline";
  if (m.includes("blocked") || m.includes("blocker") || m.includes("impediment")) return "blocker";
  if (m.includes("budget") || m.includes("tolerance") || m.includes("risk")) return "risk";
  if (m.includes("hour") || m.includes("%") || m.includes("complete")) return "progress";
  return msg ? "other" : "";
}

function firstTask(input: Record<string, unknown>): Record<string, unknown> {
  const tasks = input.tasks;
  if (Array.isArray(tasks) && tasks[0] && typeof tasks[0] === "object") {
    return { ...input, ...(tasks[0] as Record<string, unknown>) };
  }
  return input;
}

function contrastKey(row: StoryRow): string {
  const input = firstTask(row.scenario.input);
  const sim = row.simulation;
  const hours = asNumber(input.hours_since_last_contact);
  const days = asNumber(input.days_to_deadline);
  return [
    sim.actualTool,
    sim.actualNextNode ?? "",
    String(sim.output.in_cooldown ?? ""),
    String(sim.output.prince2_exception_triggered ?? ""),
    hours === undefined ? "" : hours < 24 ? "cooldown" : "eligible",
    days === undefined ? "" : days <= 2 ? "soon" : days >= 20 ? "far" : "mid",
    input.last_assignee_message ? "reply" : "",
    asString(input.plan_tier) ?? "",
    classifyMessage(asString(input.user_message) ?? asString(input.user_request) ?? ""),
  ].join("|");
}

function preferredIndex(id: string): number {
  const idx = CHASER_PREFERRED_IDS.indexOf(id);
  return idx === -1 ? 999 : idx;
}

function inputFingerprint(row: StoryRow): string {
  return JSON.stringify(row.scenario.input);
}

function pickStories(rows: StoryRow[], roleId: GiaboRoleId): StoryRow[] {
  if (rows.length === 0) return [];
  const ranked = [...rows].sort((a, b) => {
    if (roleId === "chasing_agent") {
      const pref = preferredIndex(a.scenario.id) - preferredIndex(b.scenario.id);
      if (pref !== 0) return pref;
    }
    const canon =
      Number(a.scenario.id.includes("__v")) - Number(b.scenario.id.includes("__v"));
    if (canon !== 0) return canon;
    const azure = Number(b.judgeSource === "azure") - Number(a.judgeSource === "azure");
    if (azure !== 0) return azure;
    return a.scenario.id.localeCompare(b.scenario.id);
  });

  const selected: StoryRow[] = [];
  const seenContrast = new Set<string>();
  const seenInput = new Set<string>();

  const tryAdd = (row: StoryRow, requireNewContrast: boolean): boolean => {
    if (selected.length >= MAX_STORIES) return false;
    const fp = inputFingerprint(row);
    if (seenInput.has(fp)) return false;
    const key = contrastKey(row);
    if (requireNewContrast && seenContrast.has(key) && selected.length > 0) return false;
    selected.push(row);
    seenContrast.add(key);
    seenInput.add(fp);
    return true;
  };

  for (const row of ranked) tryAdd(row, true);
  for (const row of ranked) tryAdd(row, false);
  return selected;
}

function qualitativeJustification(raw: string): string {
  const trimmed = raw.trim();
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (typeof parsed === "string") return parsed;
    if (parsed && typeof parsed === "object") {
      return Object.entries(parsed as Record<string, unknown>)
        .map(([key, value]) => `**${key}:** ${String(value)}`)
        .join("\n\n");
    }
  } catch {
    /* not JSON */
  }
  return trimmed;
}

function scenarioTitle(row: StoryRow): string {
  if (row.scenario.name) return row.scenario.name;
  const input = firstTask(row.scenario.input);
  const role = row.scenario.targetAgentRole;
  const taskName = asString(input.task_name);
  const days = asNumber(input.days_to_deadline);
  const hours = asNumber(input.hours_since_last_contact);
  if (taskName && days !== undefined && hours !== undefined) {
    return `${taskName}, ${duePhrase(days)}, last contact ${contactPhrase(hours)}`;
  }
  if (role === "pmp_schedule_specialist") {
    const taskId = asString(input.task_id) ?? "task";
    const pct = asNumber(input.percent_complete);
    const spent = asNumber(input.actual_hours_spent);
    return `${taskId}${pct !== undefined ? ` at ${pct}% complete` : ""}${spent !== undefined ? ` (${spent}h logged)` : ""}`;
  }
  if (role === "risk_radar_monitor") {
    const riskId = asString(input.risk_id) ?? "risk";
    const tier = asString(input.plan_tier);
    return `${riskId} materialized${tier ? ` (${tier})` : ""}`;
  }
  if (role === "prince2_governance_worker") {
    const variance = asNumber(input.variance_pct);
    const tolerance = asNumber(input.tolerance_pct);
    if (variance !== undefined && tolerance !== undefined) {
      return `${variance}% variance vs ${tolerance}% stage tolerance`;
    }
  }
  const msg = asString(input.user_message) ?? asString(input.user_request);
  if (msg) {
    const clipped = msg.length > 90 ? `${msg.slice(0, 87)}…` : msg;
    return clipped;
  }
  return row.scenario.description.replace(/\s+Variant \d+\.?$/, "");
}

function scenarioContext(row: StoryRow): string {
  const input = firstTask(row.scenario.input);
  const role = row.scenario.targetAgentRole;
  const taskName = asString(input.task_name);
  const assignee = asString(input.assignee);
  const taskId = asString(input.task_id);
  const days = asNumber(input.days_to_deadline);
  const hours = asNumber(input.hours_since_last_contact);
  const impact = asNumber(input.critical_path_impact);
  const reply = asString(input.last_assignee_message);
  const userMessage = asString(input.user_message);
  const userRequest = asString(input.user_request);

  if (role === "chasing_agent" && days !== undefined && hours !== undefined) {
    const who = assignee ?? "the assignee";
    const what = taskName ?? taskId ?? "the task";
    const impactBit =
      impact !== undefined ? `, critical-path impact ${impact}/10` : "";
    const replyBit = reply ? ` ${who} last said: “${reply}”` : "";
    return `Task ${duePhrase(days)}, last chase was ${contactPhrase(hours)}, ${what} assigned to ${who}${impactBit}.${replyBit}`;
  }

  if (role === "risk_radar_monitor") {
    const riskId = asString(input.risk_id) ?? "the open risk";
    const tier = asString(input.plan_tier) ?? "unknown";
    return `Budget risk ${riskId} has materialized (invoice received) on a ${tier} tenant. The agent must convert it to an issue without rewriting baseline budget.`;
  }

  if (role === "pmp_schedule_specialist") {
    const pct = asNumber(input.percent_complete);
    const spent = asNumber(input.actual_hours_spent);
    return `${taskId ?? "The task"} is a plain progress update${pct !== undefined ? ` at ${pct}% complete` : ""}${spent !== undefined ? ` with ${spent} hours spent` : ""}. This is schedule fact, not a baseline change.`;
  }

  if (role === "agile_facilitator") {
    return `${taskId ?? "A task"} was raised as a blocker${userMessage ? `: “${userMessage}”` : "."} Agile owns impediments, not percent-complete writes.`;
  }

  if (role === "prince2_governance_worker") {
    const variance = asNumber(input.variance_pct);
    const tolerance = asNumber(input.tolerance_pct);
    const lead = userMessage ? `“${userMessage}” ` : "";
    if (variance !== undefined && tolerance !== undefined) {
      return `${lead}Forecast variance is ${variance}% against a ${tolerance}% stage tolerance.`;
    }
    return row.scenario.description;
  }

  if (role === "change_control_clerk") {
    return userRequest
      ? `The workstream explicitly asked to change the locked baseline: “${userRequest}”`
      : "The workstream explicitly requested a locked-baseline change.";
  }

  if (role === "conversational_router") {
    return userMessage
      ? `Incoming Teams message: “${userMessage}”`
      : "Incoming Teams message needs specialist routing.";
  }

  return row.scenario.description;
}

function chaserDraft(row: StoryRow): string {
  const input = firstTask(row.scenario.input);
  const tool = row.simulation.actualTool;
  const hours = asNumber(input.hours_since_last_contact);
  const days = asNumber(input.days_to_deadline) ?? 0;
  const impact = asNumber(input.critical_path_impact);
  const assignee = asString(input.assignee) ?? "the assignee";
  const taskName = asString(input.task_name) ?? asString(input.task_id) ?? "the task";
  const score = asNumber(row.simulation.output.chasing_score);
  const inCooldown = asBool(row.simulation.output.in_cooldown) ?? (hours !== undefined && hours < 24);

  if (tool === "suppress_chase" || inCooldown) {
    const reason = inCooldown
      ? `last contact was ${hours ?? "?"} hours ago (inside the 24-hour fatigue cooldown), so chasing_score is 0.0`
      : `chasing_score is ${score ?? 0} and the task was omitted from outreach`;
    return `No Teams message sent. Reason: ${reason}.`;
  }

  const impactBit = impact !== undefined ? ` This sits on the critical path (impact ${impact}/10).` : "";
  return `${assignee} — ${taskName} is ${duePhrase(days)}.${impactBit} What's the current status, and is anything blocking you from hitting that date?`;
}

function naturalLanguageDraft(row: StoryRow): string {
  const input = firstTask(row.scenario.input);
  const role = row.scenario.targetAgentRole;
  const next = row.simulation.actualNextNode;
  const out = row.simulation.output;

  if (role === "chasing_agent") return chaserDraft(row);

  if (role === "risk_radar_monitor") {
    if (row.simulation.actualTool === "pilot_feature_denied" || asBool(out.denied)) {
      return "Risk Radar is Standard Tier. This free-trial tenant is denied access — no risk-to-issue conversion ran, and baseline budget was not rewritten.";
    }
    const riskId = asString(input.risk_id) ?? "the risk";
    return `${riskId} has materialized (invoice received). Converted from risk to issue. Baseline budget was not rewritten.`;
  }

  if (role === "pmp_schedule_specialist") {
    const taskId = asString(input.task_id) ?? "the task";
    const pct = asNumber(input.percent_complete);
    const spent = asNumber(input.actual_hours_spent);
    const pctBit = pct !== undefined ? ` at ${pct}% complete` : "";
    const hoursBit = spent !== undefined ? ` with ${spent} hours spent` : "";
    return `Logged ${taskId}${pctBit}${hoursBit}. Baseline dates are unchanged.`;
  }

  if (role === "agile_facilitator") {
    const taskId = asString(input.task_id) ?? "the task";
    const msg = asString(input.user_message) ?? "the reported impediment";
    return `I've captured the blocker on ${taskId}: “${msg}”. Next step is to clear the path with the owning team — I am not logging percent complete.`;
  }

  if (role === "prince2_governance_worker") {
    const variance = asNumber(input.variance_pct);
    const tolerance = asNumber(input.tolerance_pct);
    const triggered = asBool(out.prince2_exception_triggered);
    if (triggered) {
      return `Variance ${variance}% exceeds the ${tolerance}% stage tolerance. I've flagged a PRINCE2 exception. I have not paused the graph or escalated to the human PM myself — that gate belongs downstream.`;
    }
    return `Variance ${variance}% is within the ${tolerance}% stage tolerance. No PRINCE2 exception flagged. I have not paused the graph.`;
  }

  if (role === "change_control_clerk") {
    return "I have drafted this baseline change and submitted it to the Project Manager for approval. I cannot authorize the write — it is waiting on PM Veto.";
  }

  if (role === "conversational_router") {
    const node = next ?? asString(out.next_node) ?? "end_conversation";
    if (node === "pmp_worker") {
      return "Got it — I'll log that as a schedule update with the PMP specialist. This is not a baseline change and not a blocker, so I'm not routing it to Change Control or Agile.";
    }
    if (node === "agile_worker") {
      return "I've got a blocker here — routing you to the Agile facilitator so we can clear the path. This is not a percent-complete write.";
    }
    if (node === "governance_worker") {
      return "This looks like a tolerance / risk question. Routing to the Governance worker to classify and score it — I am not changing the baseline.";
    }
    if (node === "change_control_clerk") {
      return "You asked to change the locked baseline. Routing to the Change Control Clerk to draft a proposal for PM Veto — nothing is written yet.";
    }
    return `Routed to ${node}. No baseline write.`;
  }

  return row.simulation.monologue.join(" ");
}

function renderStory(roleLabel: string, persona: string, row: StoryRow, index: number): string {
  const rule = row.scenario.originatingRule;
  const title = scenarioTitle(row);
  const context = scenarioContext(row);
  const draft = naturalLanguageDraft(row);
  const justification = qualitativeJustification(row.verdict.justification);
  const passLabel = row.verdict.pass ? "PASS" : "FAIL";
  const source =
    row.judgeSource === "azure" ? "Azure OpenAI judge" : "deterministic goldMatch (not Azure-judged)";

  return [
    `### Story ${index}: ${title}`,
    "",
    `*Eval id: \`${row.scenario.id}\`*`,
    "",
    "**Scenario Title & Context:**",
    "",
    context,
    "",
    "**Agent Persona & Rule Applied:**",
    "",
    `${persona}. GIABO rule \`${rule.mdc}\` via \`${rule.implementingFile}\`:`,
    "",
    `> ${rule.invariantQuote}`,
    "",
    "**Exact Agent Output / Natural Language Draft:**",
    "",
    `> ${draft}`,
    "",
    "Structured payload:",
    "",
    "```json",
    JSON.stringify(row.simulation.output, null, 2),
    "```",
    "",
    "**LLM Judge Score & Qualitative Justification:**",
    "",
    `Score **${row.verdict.score}/100** — **${passLabel}** (${source}).`,
    "",
    justification,
    "",
    "**Human Sign-Off Checkbox:**",
    "",
    "- [ ] Approved",
    "- [ ] Needs Tuning",
    "",
    "### Human Feedback / Explanation (if Needs Tuning):",
    "> [Type your specific PMO tuning notes or prompt adjustments here]",
    "",
  ].join("\n");
}

function chaserEntriesToRows(log: ChaserLog): StoryRow[] {
  return log.scenarios.map((entry) => {
    const primary = entry.scenario.input.tasks[0] ?? {};
    const send = entry.tools.find((t) => t.tool === "send_teams_chase") ?? entry.tools[0];
    const suppressAll = entry.tools.length > 0 && entry.tools.every((t) => t.tool === "suppress_chase");
    const actualTool = suppressAll ? "suppress_chase" : (send?.tool ?? "send_teams_chase");
    const score = asNumber(send?.arguments.chasing_score);
    const hours = asNumber(primary.hours_since_last_contact);
    return {
      scenario: {
        id: entry.scenario.id,
        roleIndex: 21,
        targetAgentRole: "chasing_agent",
        originatingRule: CHASER_RULE,
        description: entry.scenario.description,
        expectedFrameworkBehavior: String(entry.scenario.expected.expectedAction ?? ""),
        input: {
          ...primary,
          tasks: entry.scenario.input.tasks,
        },
        expected: {
          shouldAct: actualTool === "send_teams_chase",
          expectedTool: String(entry.scenario.expected.expectedTool ?? actualTool),
          mustNotWriteBaseline: true,
          goldTraceAssertions: ["chaser eval"],
        },
        name: entry.scenario.name,
      },
      simulation: {
        monologue: entry.trace.monologue,
        actualTool,
        actualNextNode: null,
        wroteBaseline: false,
        output: {
          chasing_score: score,
          in_cooldown: hours !== undefined ? hours < 24 : false,
          ranked_task_ids: entry.tools
            .filter((t) => t.tool === "send_teams_chase")
            .map((t) => t.taskId),
        },
      },
      verdict: entry.verdict,
      judgeSource: "azure",
    };
  });
}

function loadBulkLog(): BulkLog {
  if (!existsSync(bulkLogPath)) {
    throw new Error(
      `Missing ${bulkLogPath}. Run \`npm run eval:bulk\` first, then retry \`npm run eval:human-report\`.`,
    );
  }
  return JSON.parse(readFileSync(bulkLogPath, "utf8")) as BulkLog;
}

function loadChaserRows(): StoryRow[] {
  if (!existsSync(chaserLogPath)) return [];
  const log = JSON.parse(readFileSync(chaserLogPath, "utf8")) as ChaserLog;
  if (!Array.isArray(log.scenarios) || log.scenarios.length === 0) return [];
  return chaserEntriesToRows(log);
}

function compileReport(bulk: BulkLog, chaserRows: StoryRow[]): string {
  const lines: string[] = [
    "# GIABO Human Review Report",
    "",
    "Narrative PMO stories for executive sign-off. This is a curated subset (2–3 stories per key role), not the full bulk dump — see `tests/evals/results/masterReviewReport.md` for every scenario.",
    "",
    `- Bulk eval run: \`${bulk.runId}\``,
    `- Compiled from: ${bulk.startedAt}`,
    bulk.modelDeployment ? `- Judge model: \`${bulk.modelDeployment}\`` : null,
    `- Stories: 2–3 per key role (${KEY_ROLES.length} roles)`,
    "",
    "Tick **Approved** or **Needs Tuning** on each story before launch. Tuning means the persona, routing, or message draft should change — not that the eval harness failed.",
    "",
    "## Contents",
    "",
    ...KEY_ROLES.map((role) => `- [${role.label}](#${slug(role.label)})`),
    "",
  ].filter((line): line is string => line !== null);

  for (const role of KEY_ROLES) {
    const pool =
      role.roleId === "chasing_agent" && chaserRows.length > 0
        ? chaserRows
        : bulk.rows.filter((row) => row.scenario.targetAgentRole === role.roleId);
    const stories = pickStories(pool, role.roleId);
    lines.push(`## ${role.label}`, "");
    if (stories.length === 0) {
      lines.push(`_No eval rows found for \`${role.roleId}\`._`, "");
      continue;
    }
    if (stories.length === 1) {
      lines.push(
        `_Only one distinct ${role.label} story exists in the eval log; the other variants repeated the same input._`,
        "",
      );
    }
    stories.forEach((story, i) => {
      lines.push(renderStory(role.label, role.persona, story, i + 1));
    });
  }

  return `${lines.join("\n").trimEnd()}\n`;
}

function main(): void {
  const bulk = loadBulkLog();
  const chaserRows = loadChaserRows();
  mkdirSync(resultsDir, { recursive: true });
  const markdown = compileReport(bulk, chaserRows);
  writeFileSync(outPath, markdown, "utf8");
  const roleCounts = KEY_ROLES.map((role) => {
    const pool =
      role.roleId === "chasing_agent" && chaserRows.length > 0
        ? chaserRows
        : bulk.rows.filter((row) => row.scenario.targetAgentRole === role.roleId);
    return `${role.label}=${pickStories(pool, role.roleId).length}`;
  });
  console.log(`Wrote ${outPath}`);
  console.log(`Stories: ${roleCounts.join(", ")}`);
}

main();
