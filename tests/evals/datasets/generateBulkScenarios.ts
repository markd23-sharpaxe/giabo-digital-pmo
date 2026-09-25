/**
 * Seeded expander: 27 GIABO templates x 8 variants + 5 chaser edges as chasing_agent rows.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  BulkScenarioArraySchema,
  FrameworkScenarioArraySchema,
  type FrameworkScenario,
} from "../types/evalSchema.ts";

const here = dirname(fileURLToPath(import.meta.url));
const SEED = 20260922;
const VARIANTS_PER_ROLE = 8;

const ASSIGNEES = ["Sarah (Backend)", "Priya (Platform)", "Jonah (Infra)", "Alex (Payments)", "Mina (Design)", "Chris (QA)"];
const TASK_NAMES = [
  "API Gateway Migration",
  "Cut over production DNS",
  "PCI evidence pack for go-live",
  "Regression pack for release 12",
  "Vendor contract redlines",
  "Data-room index rebuild",
];
const SPRINTS = ["Sprint 9", "Sprint 11", "Sprint 12", "Sprint 14"];
const PROJECTS = ["Live Prod Project", "Project Delta", "Northstar Payments", "Harbour CRM"];
const TITLES = [
  "Vendor SLA still unsigned",
  "QSA evidence pack incomplete",
  "Board pack missing RAID appendix",
  "Dependency on Legal DPA",
];
const PROGRESS = [
  "I spent 4 hours on it and it is now 50% complete.",
  "Logged 6h today; TSK-002 is 40% complete.",
  "I've spent 3.5 hours and we are at 55% complete.",
];
const BLOCKERS = [
  "TSK-002 is blocked waiting on Legal to sign the DPA.",
  "We are blocked on the vendor API sandbox — cannot proceed.",
  "Impediment: waiting on InfoSec review before we can merge.",
];
const VAGUE = [
  "not sure, whatever you think",
  "idk, maybe later?",
  "hmm not really sure what you need from me",
];
const REPLIES = [
  "I'm working on it — first pass by tomorrow.",
  "Still on it, no blockers, will update after standup.",
  "Have it in progress; will ping when the draft is ready.",
];
const LESSONS = [
  "Do not start Stage 2 without signed vendor SLA.",
  "Always freeze scope before the EOM checkpoint.",
  "Golden Thread objectives must name a parent goal.",
];
const DEPS = [
  "Legal review blocks go-live comms",
  "InfoSec sign-off blocks production DNS cutover",
  "QSA visit blocks PCI evidence pack",
];

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(rng: () => number, items: T[]): T {
  return items[Math.floor(rng() * items.length)]!;
}

function intBetween(rng: () => number, min: number, max: number): number {
  return min + Math.floor(rng() * (max - min + 1));
}

function mutateHours(rng: () => number, hours: number): number {
  return hours < 24 ? intBetween(rng, 1, 23) : intBetween(rng, 24, 96);
}

function mutateVariance(rng: () => number, variance: number, tolerance: number): number {
  if (variance > tolerance) return tolerance + intBetween(rng, 1, 20);
  if (variance < tolerance) return Math.max(0, tolerance - intBetween(rng, 1, Math.max(1, tolerance)));
  return variance;
}

function mutateInput(input: Record<string, unknown>, rng: () => number): Record<string, unknown> {
  const next: Record<string, unknown> = { ...input };
  if (typeof next.hours_since_last_contact === "number") {
    next.hours_since_last_contact = mutateHours(rng, next.hours_since_last_contact);
  }
  if (typeof next.days_to_deadline === "number") {
    const days = next.days_to_deadline;
    next.days_to_deadline = days <= 2 ? intBetween(rng, 0, 2) : days >= 20 ? intBetween(rng, 20, 45) : intBetween(rng, 3, 12);
  }
  if (typeof next.critical_path_impact === "number") {
    const impact = next.critical_path_impact;
    next.critical_path_impact = impact >= 8 ? intBetween(rng, 8, 10) : impact <= 2 ? intBetween(rng, 1, 2) : intBetween(rng, 3, 7);
  }
  if (typeof next.linked_risks_severity === "number") {
    const risk = next.linked_risks_severity;
    next.linked_risks_severity = risk >= 8 ? intBetween(rng, 8, 10) : risk <= 2 ? intBetween(rng, 1, 2) : intBetween(rng, 3, 7);
  }
  if (typeof next.variance_pct === "number" && typeof next.tolerance_pct === "number") {
    next.variance_pct = mutateVariance(rng, next.variance_pct, next.tolerance_pct);
  }
  if (typeof next.vague_turns === "number") {
    next.vague_turns = next.vague_turns >= 2 ? intBetween(rng, 2, 5) : 0;
  }
  if (typeof next.schema_failures === "number" && next.schema_failures >= 3) {
    next.schema_failures = intBetween(rng, 3, 5);
  }
  if (next.billing_status === "trial_exhausted" || next.billing_status === "paid_halt") {
    next.billing_status = pick(rng, ["trial_exhausted", "paid_halt"]);
  }
  if (typeof next.user_message === "string") {
    const msg = next.user_message.toLowerCase();
    if (msg.includes("blocked") || msg.includes("blocker") || msg.includes("impediment")) next.user_message = pick(rng, BLOCKERS);
    else if (msg.includes("not sure") || msg.includes("whatever")) next.user_message = pick(rng, VAGUE);
    else if (msg.includes("hour") || msg.includes("complete") || msg.includes("%")) next.user_message = pick(rng, PROGRESS);
  }
  if (typeof next.user_request === "string" && next.user_request.toLowerCase().includes("baseline")) {
    const date = `2027-0${intBetween(rng, 1, 9)}-0${intBetween(rng, 1, 9)}`;
    next.user_request = `Move the locked baseline end date to ${date}.`;
  }
  if (typeof next.title === "string") next.title = pick(rng, TITLES);
  if (typeof next.lesson === "string") next.lesson = pick(rng, LESSONS);
  if (typeof next.dependency === "string") next.dependency = pick(rng, DEPS);
  if (typeof next.sprint_name === "string") next.sprint_name = pick(rng, SPRINTS);
  if (typeof next.project_name === "string") next.project_name = pick(rng, PROJECTS);
  if (typeof next.task_name === "string") next.task_name = pick(rng, TASK_NAMES);
  if (typeof next.assignee === "string") next.assignee = pick(rng, ASSIGNEES);
  if (typeof next.task_id === "string") next.task_id = `TSK-${intBetween(rng, 100, 999)}`;
  if (typeof next.last_assignee_message === "string") next.last_assignee_message = pick(rng, REPLIES);
  if (typeof next.percent_complete === "number") next.percent_complete = intBetween(rng, 20, 80);
  if (typeof next.actual_hours_spent === "number") next.actual_hours_spent = intBetween(rng, 1, 10);
  if (typeof next.severity === "number") next.severity = intBetween(rng, 4, 5);
  if (Array.isArray(next.baseline_objectives)) {
    next.baseline_objectives = [pick(rng, ["Ship mobile app", "Launch partner portal", "Open a consumer waitlist"])];
  }
  return next;
}

function variantOf(template: FrameworkScenario, variantIndex: number, rng: () => number): FrameworkScenario {
  if (variantIndex === 0) return template;
  const input = mutateInput({ ...template.input }, rng);
  return {
    ...template,
    id: `${template.id}__v${variantIndex}`,
    description: `${template.description} Variant ${variantIndex}.`,
    input,
  };
}

function chaserAsFramework(
  id: string,
  description: string,
  hours: number,
  days: number,
  impact: number,
  risk: number,
  extra: Record<string, unknown>,
  rng: () => number,
): FrameworkScenario {
  const h = mutateHours(rng, hours);
  const suppress = h < 24;
  const taskId = `TSK-${intBetween(rng, 200, 899)}`;
  return {
    id,
    roleIndex: 21,
    targetAgentRole: "chasing_agent",
    originatingRule: {
      mdc: "08-maf-dynamic-chasing-persona.mdc",
      implementingFile: "maf_graph_state.py",
      invariantQuote:
        "If hours_since_last_contact < 24: chasing_score = 0.0 (fatigue cooldown). calculate_chasing_priorities omits score == 0.0.",
    },
    description,
    expectedFrameworkBehavior: suppress
      ? "Fatigue window forces score 0.0 and suppress_chase."
      : "Outside fatigue window: send_teams_chase using proximity-weighted score.",
    input: {
      task_id: taskId,
      hours_since_last_contact: h,
      days_to_deadline: days <= 2 ? intBetween(rng, 0, 2) : days,
      critical_path_impact: impact,
      linked_risks_severity: risk,
      assignee: pick(rng, ASSIGNEES),
      task_name: pick(rng, TASK_NAMES),
      ...extra,
    },
    expected: {
      shouldAct: !suppress,
      expectedTool: suppress ? "suppress_chase" : "send_teams_chase",
      mustNotWriteBaseline: true,
      goldTraceAssertions: [suppress ? "chasing_score 0.0" : "chase eligible"],
    },
  };
}

function main(): void {
  const rng = mulberry32(SEED);
  const templates = FrameworkScenarioArraySchema.parse(
    JSON.parse(readFileSync(join(here, "giaboFrameworkScenarios.json"), "utf8")),
  );

  const bulk: FrameworkScenario[] = [];
  for (const template of templates) {
    for (let v = 0; v < VARIANTS_PER_ROLE; v++) {
      bulk.push(variantOf(template, v, rng));
    }
  }

  bulk.push(
    chaserAsFramework("bulk-chaser-fatigue", "Chaser edge: inside 24h fatigue.", 4, 5, 9, 8, {}, rng),
    chaserAsFramework("bulk-chaser-proximity", "Chaser edge: due soon, high impact, fatigue expired.", 48, 1, 9, 8, {}, rng),
    chaserAsFramework("bulk-chaser-expired-high", "Chaser edge: 30h since contact, due tomorrow.", 30, 1, 10, 10, {}, rng),
    chaserAsFramework("bulk-chaser-floor", "Chaser edge: far deadline floor weights, fatigue expired.", 48, 30, 1, 1, {}, rng),
    chaserAsFramework(
      "bulk-chaser-quiet-update",
      "Chaser edge: assignee replied recently; fatigue reset.",
      12,
      3,
      7,
      6,
      { last_assignee_message: pick(rng, REPLIES) },
      rng,
    ),
  );

  const parsed = BulkScenarioArraySchema.parse(bulk);
  const outPath = join(here, "bulkScenarios.json");
  writeFileSync(outPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
  console.log(`PASS: wrote ${parsed.length} bulk scenarios to ${outPath}`);
}

main();
