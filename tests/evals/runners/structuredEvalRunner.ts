/**
 * Structured 81-scenario GIABO matrix runner.
 * Simulates every role, Azure-judges each trace reference-free, writes
 * structuredReviewReport.md + structuredEvalLog.json, and audits Postgres.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { config } from "dotenv";
import { judgeWithAzureRetry, requireAzureOpenAI } from "./azureJudge.ts";
import { insertEvalAudit, withEvalAuditClient } from "./pgAudit.ts";
import { goldMatch, simulateRole, type RoleSimulation } from "./simulateRole.ts";
import {
  GIABO_ROLE_IDS,
  StructuredScenarioArraySchema,
  type FrameworkScenario,
  type JudgeVerdict,
} from "../types/evalSchema.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "../../..");
config({ path: join(repoRoot, ".env") });

const CONCURRENCY = 4;

const JUDGE_SYSTEM = `You are the GIABO framework compliance judge.
Score whether the simulated agent followed the CITED GIABO invariant (the .mdc rule plus implementing file).
You do not receive gold expected labels. Use this rubric (each 0-100):
- reasoningCoherence: did the monologue explain the role's exact boundary?
- contextRetention: did it use the scenario input?
- toolSelectionCorrectness: did actualTool / actualNextNode match the cited invariant?
Negative constraints ARE compliance: within-tolerance means do not raise an exception; a blocker/impediment routes to Agile not PMP; a clean roster with no cron keys is dispatched as-is after a no-op strip; a Standard-tier deny on free_trial is correct; clerk drafting a slip without risk language is correct; a proactive governance wake that does not edit the pending baseline is correct; fatigue suppressing a chase after CRITICAL_PATH_SLIPPED is correct; append_event rejecting an illegal publisher/event-type pair is correct; a veto reject that publishes BASELINE_CHANGE_REJECTED without clerk auto-redraft is correct.
Set pass=true only if the agent respected the invariant. score is the mean of the three subscores.
Return JSON: {pass, score, reasoningCoherence, contextRetention, toolSelectionCorrectness, justification}.`;

type Row = {
  scenario: FrameworkScenario;
  simulation: RoleSimulation;
  goldMatch: boolean;
  verdict: JudgeVerdict;
};

async function mapPool<T>(items: T[], concurrency: number, fn: (item: T) => Promise<void>): Promise<void> {
  let cursor = 0;
  const workers = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor++;
      const item = items[index];
      if (item) await fn(item);
    }
  });
  await Promise.all(workers);
}

function compileReport(runId: string, startedAt: string, modelDeployment: string, rows: Row[]): string {
  const goldPass = rows.filter((r) => r.goldMatch).length;
  const judgePass = rows.filter((r) => r.verdict.pass).length;
  const lines: string[] = [
    "# GIABO Structured Framework Review Report",
    "",
    "Hand-crafted 81-scenario matrix covering all 27 GIABO roles (happy paths, negative constraints, and event-bus Aims 1–3). This replaces generic bulk fuzzing for executive review.",
    "",
    `- Run ID: \`${runId}\``,
    `- Started: ${startedAt}`,
    `- Judge model: \`${modelDeployment}\``,
    `- Total scenarios: ${rows.length}`,
    `- goldMatch: ${goldPass}/${rows.length} PASS`,
    `- Azure LLM judge: ${judgePass}/${rows.length} PASS`,
    `- Suite: \`structured_framework\``,
    "",
    "## Summary by role",
    "",
  ];

  for (let i = 0; i < GIABO_ROLE_IDS.length; i++) {
    const role = GIABO_ROLE_IDS[i]!;
    const roleRows = rows.filter((r) => r.scenario.targetAgentRole === role);
    const g = roleRows.filter((r) => r.goldMatch).length;
    const j = roleRows.filter((r) => r.verdict.pass).length;
    lines.push(
      `- ${i + 1}/27 \`${role}\`: n=${roleRows.length}, goldMatch ${g}/${roleRows.length}, Azure ${j}/${roleRows.length}`,
    );
  }

  lines.push("", "## Scenarios", "");

  for (const row of rows) {
    const rule = `${row.scenario.originatingRule.mdc} / ${row.scenario.originatingRule.implementingFile}`;
    lines.push(
      `### ${row.scenario.id}`,
      "",
      `- **Target Agent Role:** ${row.scenario.roleIndex}/27 \`${row.scenario.targetAgentRole}\``,
      `- **Originating GIABO Rule:** ${rule}`,
      `- **Invariant:** ${row.scenario.originatingRule.invariantQuote}`,
      `- **Scenario:** ${row.scenario.description}`,
      `- **Expected Framework Behavior:** ${row.scenario.expectedFrameworkBehavior}`,
      `- **goldMatch:** ${row.goldMatch ? "PASS" : "FAIL"}`,
      `- **LLM Judge Score:** ${row.verdict.score} **${row.verdict.pass ? "PASS" : "FAIL"}**`,
      `- **Actual tool / next node:** \`${row.simulation.actualTool}\`${row.simulation.actualNextNode ? ` → \`${row.simulation.actualNextNode}\`` : ""} (wroteBaseline=${row.simulation.wroteBaseline})`,
      "",
      "**Agent reasoning:**",
      "",
      ...row.simulation.monologue.map((m) => `- ${m}`),
      "",
      "**Structured payload:**",
      "",
      "```json",
      JSON.stringify(row.simulation.output, null, 2),
      "```",
      "",
      "**Judge justification:**",
      "",
      row.verdict.justification,
      "",
    );
  }
  return `${lines.join("\n")}\n`;
}

async function main(): Promise<void> {
  const datasetPath = join(here, "../datasets/structuredGiaboScenarios.json");
  const scenarios = StructuredScenarioArraySchema.parse(JSON.parse(readFileSync(datasetPath, "utf8")));
  console.log(`Validated ${scenarios.length} structured scenarios (all ${GIABO_ROLE_IDS.length} roles present).`);

  const { client, deployment } = requireAzureOpenAI();
  const runId = randomUUID();
  const startedAt = new Date().toISOString();

  const rows: Row[] = scenarios.map((scenario) => {
    const simulation = simulateRole(scenario);
    return {
      scenario,
      simulation,
      goldMatch: goldMatch(scenario, simulation),
      verdict: {
        pass: false,
        score: 0,
        reasoningCoherence: 0,
        contextRetention: 0,
        toolSelectionCorrectness: 0,
        justification: "pending Azure judge",
      },
    };
  });

  const goldFailPre = rows.filter((r) => !r.goldMatch);
  if (goldFailPre.length) {
    console.error(`goldMatch failed before judge (${goldFailPre.length}):`);
    for (const row of goldFailPre) {
      console.error(
        `  ${row.scenario.id} expectedTool=${row.scenario.expected.expectedTool} actual=${row.simulation.actualTool} next=${row.simulation.actualNextNode}`,
      );
    }
  }

  await mapPool(rows, CONCURRENCY, async (row) => {
    try {
      row.verdict = await judgeWithAzureRetry(client, deployment, JUDGE_SYSTEM, {
        originatingRule: row.scenario.originatingRule,
        description: row.scenario.description,
        input: row.scenario.input,
        simulation: row.simulation,
      });
    } catch (err) {
      row.verdict = {
        pass: false,
        score: 0,
        reasoningCoherence: 0,
        contextRetention: 0,
        toolSelectionCorrectness: 0,
        justification: `Azure judge error after retries: ${err instanceof Error ? err.message : String(err)}`,
      };
    }
    console.log(
      `[${row.scenario.roleIndex}/27] ${row.scenario.id} gold=${row.goldMatch ? "PASS" : "FAIL"} judge=${row.verdict.pass ? "PASS" : "FAIL"} score=${row.verdict.score}`,
    );
  });

  await withEvalAuditClient(async (pgClient) => {
    for (const row of rows) {
      await insertEvalAudit(pgClient, {
        runId,
        suite: "structured_framework",
        scenarioId: row.scenario.id,
        targetAgentRole: `${row.scenario.roleIndex}/27 ${row.scenario.targetAgentRole}`,
        originatingRule: `${row.scenario.originatingRule.mdc} :: ${row.scenario.originatingRule.implementingFile}`,
        pass: row.verdict.pass,
        score: row.verdict.score,
        reasoningCoherence: row.verdict.reasoningCoherence,
        contextRetention: row.verdict.contextRetention,
        toolSelectionCorrectness: row.verdict.toolSelectionCorrectness,
        justification: row.verdict.justification,
        actualTool: row.simulation.actualTool,
        goldExpected: row.scenario.expected,
        reasoningTrace: { monologue: row.simulation.monologue, output: row.simulation.output },
        toolLog: [
          {
            tool: row.simulation.actualTool,
            taskId: row.scenario.id,
            arguments: row.simulation.output,
            timestamp: new Date().toISOString(),
          },
        ],
        judgeVerdict: { ...row.verdict, goldMatch: row.goldMatch },
        modelDeployment: deployment,
      });
    }
  });

  const outDir = join(here, "../results");
  mkdirSync(outDir, { recursive: true });
  writeFileSync(
    join(outDir, "structuredEvalLog.json"),
    JSON.stringify({ runId, startedAt, endedAt: new Date().toISOString(), modelDeployment: deployment, rows }, null, 2),
    "utf8",
  );
  const reportPath = join(outDir, "structuredReviewReport.md");
  writeFileSync(reportPath, compileReport(runId, startedAt, deployment, rows), "utf8");

  const goldFail = rows.filter((r) => !r.goldMatch);
  const judgeFail = rows.filter((r) => !r.verdict.pass);
  console.log(`Wrote ${reportPath}`);
  console.log(`goldMatch fail=${goldFail.length} azure fail=${judgeFail.length} total=${rows.length}`);
  if (goldFail.length || judgeFail.length) {
    process.exit(1);
  }
  console.log("PASS: structured eval complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
