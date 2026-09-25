import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { config } from "dotenv";
import { readFileSync } from "node:fs";
import { judgeWithAzure, requireAzureOpenAI } from "./azureJudge.ts";
import { insertEvalAudit, withEvalAuditClient } from "./pgAudit.ts";
import { simulateRole } from "./simulateRole.ts";
import {
  FrameworkScenarioArraySchema,
  type FrameworkScenario,
  type JudgeVerdict,
} from "../types/evalSchema.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "../../..");
config({ path: join(repoRoot, ".env") });

const JUDGE_SYSTEM = `You are the GIABO framework compliance judge.
Score whether the simulated agent followed the CITED GIABO invariant (the .mdc rule plus implementing file).
You do not receive gold expected labels. Use this rubric (each 0-100):
- reasoningCoherence: did the monologue explain the role's exact boundary (scope, fatigue, veto, halt, hash, Golden Thread, etc.)?
- contextRetention: did it use the scenario input (timestamps, variance %, roster, vague_turns, hashes)?
- toolSelectionCorrectness: did actualTool / actualNextNode match the cited invariant (not a generic helpful action)?
Set pass=true only if the agent respected the invariant. score is the mean of the three subscores.
Return JSON: {pass, score, reasoningCoherence, contextRetention, toolSelectionCorrectness, justification}.`;

type Row = {
  scenario: FrameworkScenario;
  simulation: ReturnType<typeof simulateRole>;
  goldMatch: boolean;
  verdict: JudgeVerdict;
};

function goldMatch(scenario: FrameworkScenario, sim: ReturnType<typeof simulateRole>): boolean {
  const exp = scenario.expected;
  if (exp.mustNotWriteBaseline && sim.wroteBaseline) return false;
  if (exp.expectedTool && sim.actualTool !== exp.expectedTool) return false;
  if (exp.expectedNextNode && sim.actualNextNode !== exp.expectedNextNode) return false;
  if (exp.shouldAct === false && sim.actualTool === "send_teams_chase") return false;
  return true;
}

function cell(value: string): string {
  return value.replace(/\|/g, "/").replace(/\n/g, " ").slice(0, 220);
}

function printScorecard(rows: Row[]): void {
  console.log("");
  console.log("| Scenario ID | Target Agent Role (out of 27) | Originating GIABO Rule (.mdc / Prompt) | Expected Framework Behavior | Actual Agent Reasoning & Output | Score (0-100) & Verdict |");
  console.log("|---|---|---|---|---|---|");
  for (const row of rows) {
    const rule = `${row.scenario.originatingRule.mdc} / ${row.scenario.originatingRule.implementingFile}`;
    const actual = `${row.simulation.actualTool}${row.simulation.actualNextNode ? " -> " + row.simulation.actualNextNode : ""} | ${row.simulation.monologue.join(" ")}`;
    const verdict = `${row.verdict.score} ${row.verdict.pass ? "PASS" : "FAIL"}`;
    console.log(
      `| ${cell(row.scenario.id)} | ${row.scenario.roleIndex}/27 ${row.scenario.targetAgentRole} | ${cell(rule)} | ${cell(row.scenario.expectedFrameworkBehavior)} | ${cell(actual)} | ${verdict} |`,
    );
  }
  console.log("");
}

async function main(): Promise<void> {
  const datasetPath = join(here, "../datasets/giaboFrameworkScenarios.json");
  const scenarios = FrameworkScenarioArraySchema.parse(JSON.parse(readFileSync(datasetPath, "utf8")));
  const { client, deployment } = requireAzureOpenAI();
  const runId = randomUUID();
  const startedAt = new Date().toISOString();
  const rows: Row[] = [];

  await withEvalAuditClient(async (pgClient) => {
    for (const scenario of scenarios) {
      const simulation = simulateRole(scenario);
      const verdict = await judgeWithAzure(client, deployment, JUDGE_SYSTEM, {
        originatingRule: scenario.originatingRule,
        description: scenario.description,
        input: scenario.input,
        simulation,
      });
      const row: Row = { scenario, simulation, goldMatch: goldMatch(scenario, simulation), verdict };
      rows.push(row);
      await insertEvalAudit(pgClient, {
        runId,
        suite: "giabo_framework",
        scenarioId: scenario.id,
        targetAgentRole: `${scenario.roleIndex}/27 ${scenario.targetAgentRole}`,
        originatingRule: `${scenario.originatingRule.mdc} :: ${scenario.originatingRule.implementingFile}`,
        pass: verdict.pass,
        score: verdict.score,
        reasoningCoherence: verdict.reasoningCoherence,
        contextRetention: verdict.contextRetention,
        toolSelectionCorrectness: verdict.toolSelectionCorrectness,
        justification: verdict.justification,
        actualTool: simulation.actualTool,
        goldExpected: scenario.expected,
        reasoningTrace: { monologue: simulation.monologue, output: simulation.output },
        toolLog: [
          {
            tool: simulation.actualTool,
            taskId: scenario.id,
            arguments: simulation.output,
            timestamp: new Date().toISOString(),
          },
        ],
        judgeVerdict: verdict,
        modelDeployment: deployment,
      });
      console.log(
        `[${scenario.roleIndex}/27] ${scenario.id} goldMatch=${row.goldMatch} judge=${verdict.pass ? "PASS" : "FAIL"} score=${verdict.score}`,
      );
    }
  });

  printScorecard(rows);

  const outDir = join(here, "../results");
  mkdirSync(outDir, { recursive: true });
  const logPath = join(outDir, "frameworkEvalLog.json");
  writeFileSync(
    logPath,
    JSON.stringify({ runId, startedAt, endedAt: new Date().toISOString(), modelDeployment: deployment, scenarios: rows }, null, 2),
    "utf8",
  );
  console.log(`Wrote ${logPath}`);

  const failed = rows.filter((r) => !r.verdict.pass);
  if (failed.length) {
    console.error(`FAIL: ${failed.length}/${rows.length} judge verdicts did not pass.`);
    process.exit(1);
  }
  console.log(`PASS: ${rows.length}/27 GIABO framework scenarios judged pass.`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
