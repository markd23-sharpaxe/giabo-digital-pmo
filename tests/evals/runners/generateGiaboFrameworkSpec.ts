/**
 * Compile the 27-role GIABO framework spec for Google AI Studio scenario drafting.
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  FrameworkScenarioArraySchema,
  GIABO_ROLE_IDS,
  type FrameworkScenario,
  type GiaboRoleId,
} from "../types/evalSchema.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "../../..");
const scenariosPath = join(here, "../datasets/giaboFrameworkScenarios.json");
const outPath = join(here, "../giaboFrameworkSpecForAIStudio.md");

const ROLE_DISPLAY: Record<GiaboRoleId, string> = {
  change_control_clerk: "Change Control Clerk",
  prince2_exception_master: "PRINCE2 Exception Master",
  raid_compliance_auto_chaser: "RAID Compliance Auto-Chaser",
  risk_radar_monitor: "Risk Radar Monitor",
  lessons_learned_curator: "Lessons Learned Curator",
  dependency_map_maintainer: "Dependency Map Maintainer",
  scrum_master_liaison: "Scrum Master Liaison",
  forensic_alignment_engine: "Forensic Alignment Engine",
  earned_value_analyst: "Earned Value Analyst",
  governance_synthesizer: "Governance Synthesizer",
  stage_gate_guardian: "Stage Gate Guardian",
  project_health_reporter: "Project Health Reporter",
  governance_auditor: "Governance Auditor",
  eom_financial_checkpoint: "EOM Financial Checkpoint",
  sprint_boundary_watchdog: "Sprint Boundary Watchdog",
  pmo_commander_router: "PMO Commander Router",
  conversational_router: "Conversational Router (Teams / Copilot)",
  pmp_schedule_specialist: "PMP Schedule Specialist",
  agile_facilitator: "Agile Facilitator",
  prince2_governance_worker: "PRINCE2 Governance Worker",
  chasing_agent: "Dynamic Chasing Agent",
  sharepoint_delta_ingestion: "SharePoint Delta Ingestion",
  billing_gatekeeper: "Billing Gatekeeper",
  friction_breaker: "Friction Breaker",
  token_loop_breaker: "Token Loop Breaker",
  pm_veto_interrupt: "PM Veto Interrupt",
  prince2_exception_interrupt: "PRINCE2 Exception Interrupt",
};

const ROLE_PROMPTS: Partial<Record<GiaboRoleId, string>> = {
  change_control_clerk: "prompts/change_control_clerk.md",
  conversational_router: "prompts/router_node.md",
  pmp_schedule_specialist: "prompts/pmp_worker.md",
  agile_facilitator: "prompts/agile_worker.md",
  prince2_governance_worker: "prompts/governance_worker.md",
  chasing_agent: "prompts/chasing_agent.md",
};

const JSON_SCHEMA_EXAMPLE = `{
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
}`;

function loadPrompt(relPath: string): string | null {
  const abs = join(repoRoot, relPath);
  if (!existsSync(abs)) return null;
  return readFileSync(abs, "utf8").trimEnd();
}

function inputKeys(input: Record<string, unknown>): string[] {
  return Object.keys(input);
}

function renderRole(scenario: FrameworkScenario): string {
  const role = scenario.targetAgentRole;
  const display = ROLE_DISPLAY[role];
  const promptRel = ROLE_PROMPTS[role];
  const promptBody = promptRel ? loadPrompt(promptRel) : null;
  const exp = scenario.expected;
  const lines: string[] = [
    `## Role ${scenario.roleIndex} of 27: ${display}`,
    "",
    `- **Role id:** \`${role}\``,
    `- **Originating GIABO rule:** \`${scenario.originatingRule.mdc}\``,
    `- **Implementing file:** \`${scenario.originatingRule.implementingFile}\``,
    promptRel ? `- **Prompt file:** \`${promptRel}\`` : null,
    `- **Canonical scenario id:** \`${scenario.id}\``,
    "",
    "**Invariant (must not be relaxed):**",
    "",
    `> ${scenario.originatingRule.invariantQuote}`,
    "",
    "**Expected framework behavior:**",
    "",
    scenario.expectedFrameworkBehavior,
    "",
    "**Strict input keys** (every scenario for this role must supply these; extra narrative fields are allowed if they do not contradict them):",
    "",
    ...inputKeys(scenario.input).map((key) => `- \`${key}\``),
    "",
    "**Expected action:**",
    "",
    `- \`shouldAct\`: \`${exp.shouldAct}\``,
    exp.expectedTool ? `- \`expectedTool\`: \`${exp.expectedTool}\`` : null,
    exp.expectedNextNode ? `- \`expectedNextNode\`: \`${exp.expectedNextNode}\`` : null,
    exp.expectedArtifactType ? `- \`expectedArtifactType\`: \`${exp.expectedArtifactType}\`` : null,
    `- \`mustNotWriteBaseline\`: \`${exp.mustNotWriteBaseline}\``,
    "",
    "**Gold trace assertions:**",
    "",
    ...exp.goldTraceAssertions.map((a) => `- ${a}`),
    "",
    "**Canonical example input:**",
    "",
    "```json",
    JSON.stringify(scenario.input, null, 2),
    "```",
    "",
    `**Story seed for AI Studio:** ${scenario.description}`,
    "",
  ].filter((line): line is string => line !== null);

  if (promptBody && promptRel) {
    lines.push(
      "**Persona / prompt (draft Teams copy in this voice):**",
      "",
      "```markdown",
      promptBody,
      "```",
      "",
    );
  }
  return lines.join("\n");
}

function roleAnchor(scenario: FrameworkScenario): string {
  const display = ROLE_DISPLAY[scenario.targetAgentRole]
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `role-${scenario.roleIndex}-of-27-${display}`;
}

function compileSpec(scenarios: FrameworkScenario[]): string {
  const byIndex = [...scenarios].sort((a, b) => a.roleIndex - b.roleIndex);
  const toc = byIndex.map(
    (s) => `- [Role ${s.roleIndex} of 27: ${ROLE_DISPLAY[s.targetAgentRole]}](#${roleAnchor(s)})`,
  );

  return [
    "# GIABO Framework Spec for Google AI Studio",
    "",
    "Use this document to draft **comprehensive, real-world Digital PMO test scenarios** for the GIABO swarm. Do not invent new agent roles. Do not relax the invariants. Return a JSON array of scenario objects that match `FrameworkScenarioSchema`.",
    "",
    "## How to use this spec",
    "",
    "1. Write concrete PMO stories (Teams messages, RAID items, SharePoint deltas, billing states, sprint closes) — not abstract metrics.",
    "2. Target exactly one of the 27 `targetAgentRole` values below. Copy `roleIndex`, `originatingRule.mdc`, `implementingFile`, and `invariantQuote` from that role's section.",
    "3. Keep `mustNotWriteBaseline: true` unless the story is an **approved** PM-Veto resume that is allowed to write the baseline (role 26 after `pm_veto_decision: \"approve\"` is the only path that may later write; the interrupt itself still must not write).",
    "4. Vary the `input` values (names, dates, percents, hours, variance vs tolerance) but keep the **same input keys** listed for that role.",
    "5. Emit JSON only, matching this shape:",
    "",
    "```json",
    JSON_SCHEMA_EXAMPLE,
    "```",
    "",
    "Valid `targetAgentRole` values (exactly these 27):",
    "",
    ...GIABO_ROLE_IDS.map((id, i) => `${i + 1}. \`${id}\``),
    "",
    "## Global invariants (apply to every scenario)",
    "",
    "- **Locked baseline:** no agent writes `baseline_end_date`, `baseline_budget`, or `baseline_objectives` except after Change Control drafts a `PendingChangePayload` **and** the human PM approves at `suspend_for_veto_node`.",
    "- **Change Control cannot authorize.** It only drafts. Authorization is PM Veto.",
    "- **Read-only agents** (`forensic_alignment_engine`, `earned_value_analyst`, `governance_synthesizer`, `stage_gate_guardian`, `project_health_reporter`) never insert `pmo_artifacts` and never patch tasks or baselines.",
    "- **Standard Tier** agents `risk_radar_monitor` and `scrum_master_liaison` are **denied** on `plan_tier=free_trial`. They run on `paid_monthly`.",
    "- **Cron sweeps** `governance_auditor`, `eom_financial_checkpoint`, `sprint_boundary_watchdog` are in `DELTA_DISPATCH_EXCLUDED_AGENTS`. They never appear on the delta-dispatch roster or as a Teams `next_node`.",
    "- **Conversational routing:** progress / hours / percent-complete → `pmp_worker`. Blocker / impediment → `agile_worker`. Budget / tolerance / risk → `governance_worker`. Explicit locked-baseline change → `change_control_clerk`. A plain standup progress update is **not** Agile.",
    "- **Chasing score:** if `hours_since_last_contact < 24` then `chasing_score = 0.0` (fatigue) and `suppress_chase`. Else `(critical_path_impact * 1.5 + linked_risks_severity * 1.2) * max(1, 10 - days_to_deadline)`. Score `0.0` is omitted from outreach.",
    "- **Friction Breaker:** `vague_turns >= 2` forces `escalation_node` even if the LLM returned `pmp_worker`.",
    "- **Token Loop Breaker:** max **3** schema self-correction attempts, then `hard_fail_node`.",
    "- **PRINCE2 exception:** if `prince2_exception_triggered` is true, `state_writeback_node` must **not** silent-commit the risk; it hands off to `suspend_for_exception_node`.",
    "- **Billing:** `billing_status` in `{trial_exhausted, paid_halt}` hard-halts **before** any Azure OpenAI call.",
    "- **SharePoint ingest:** `document_cache` is content-addressed SHA-256. Same `(project_id, sharepoint_item_id)` is an upsert, not a second document.",
    "- **Idempotent RAID writes:** deterministic `pmo_artifacts.id` (hash of title / period). Duplicate ingest is `ON CONFLICT`, not a second row.",
    "",
    "## Contents",
    "",
    ...toc,
    "",
    ...byIndex.map(renderRole),
  ].join("\n");
}

function main(): void {
  const scenarios = FrameworkScenarioArraySchema.parse(
    JSON.parse(readFileSync(scenariosPath, "utf8")),
  );
  const markdown = `${compileSpec(scenarios).trimEnd()}\n`;
  writeFileSync(outPath, markdown, "utf8");
  console.log(`Wrote ${outPath} (${scenarios.length} roles)`);
}

main();
