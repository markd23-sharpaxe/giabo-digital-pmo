import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { config } from "dotenv";
import { judgeWithAzureRetry, requireAzureOpenAI } from "./azureJudge.ts";
import { insertEvalAudit, withEvalAuditClient } from "./pgAudit.ts";
import { goldMatch, simulateRole, type RoleSimulation } from "./simulateRole.ts";
import {
  BulkScenarioArraySchema,
  GIABO_ROLE_IDS,
  type FrameworkScenario,
  type JudgeVerdict,
} from "../types/evalSchema.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "../../..");
config({ path: join(repoRoot, ".env") });

const SAMPLE_SEED = 20260922;
const EXTRA_AZURE_SAMPLE = 50;
const CONCURRENCY = 4;

const JUDGE_SYSTEM = `You are the GIABO framework compliance judge.
Score whether the simulated agent followed the CITED GIABO invariant (the .mdc rule plus implementing file).
You do not receive gold expected labels. Use this rubric (each 0-100):
- reasoningCoherence: did the monologue explain the role's exact boundary?
- contextRetention: did it use the scenario input?
- toolSelectionCorrectness: did actualTool / actualNextNode match the cited invariant?
Set pass=true only if the agent respected the invariant. score is the mean of the three subscores.
Return JSON: {pass, score, reasoningCoherence, contextRetention, toolSelectionCorrectness, justification}.`;

type JudgeSource = "azure" | "deterministic";

type Row = {
  scenario: FrameworkScenario;
  simulation: RoleSimulation;
  goldMatch: boolean;
  verdict: JudgeVerdict;
  judgeSource: JudgeSource;
};

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

function deterministicVerdict(match: boolean): JudgeVerdict {
  return {
    pass: match,
    score: match ? 100 : 0,
    reasoningCoherence: match ? 100 : 0,
    contextRetention: match ? 100 : 0,
    toolSelectionCorrectness: match ? 100 : 0,
    justification: match
      ? "deterministic goldMatch; not Azure-judged. Simulated tool and baseline lock match expected GIABO invariant."
      : "deterministic goldMatch; not Azure-judged. Simulated tool or baseline write diverged from expected GIABO invariant.",
  };
}

function pickJudgeSample(scenarios: FrameworkScenario[]): Set<string> {
  const rng = mulberry32(SAMPLE_SEED);
  const ids = new Set<string>();
  for (let role = 1; role <= 27; role++) {
    const forRole = scenarios.filter((s) => s.roleIndex === role);
    const canonical = forRole.find((s) => !s.id.includes("__v")) ?? forRole[0];
    if (canonical) ids.add(canonical.id);
  }
  const remaining = scenarios.filter((s) => !ids.has(s.id));
  while (ids.size < 27 + EXTRA_AZURE_SAMPLE && remaining.length > 0) {
    const idx = Math.floor(rng() * remaining.length);
    const [picked] = remaining.splice(idx, 1);
    if (picked) ids.add(picked.id);
  }
  return ids;
}

async function mapPool<T>(items: T[], concurrency: number, fn: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  async function worker(): Promise<void> {
    while (next < items.length) {
      const index = next;
      next += 1;
      await fn(items[index]!);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => worker()));
}

function loadOrGenerateBulk(): FrameworkScenario[] {
  const path = join(here, "../datasets/bulkScenarios.json");
  if (!existsSync(path)) {
    const gen = spawnSync("npx", ["tsx", join(here, "../datasets/generateBulkScenarios.ts")], {
      cwd: repoRoot,
      stdio: "inherit",
    });
    if (gen.status !== 0) {
      throw new Error("bulk scenario generator failed");
    }
  }
  return BulkScenarioArraySchema.parse(JSON.parse(readFileSync(path, "utf8")));
}

function compileReport(runId: string, startedAt: string, rows: Row[]): string {
  const goldPass = rows.filter((r) => r.goldMatch).length;
  const azureRows = rows.filter((r) => r.judgeSource === "azure");
  const azurePass = azureRows.filter((r) => r.verdict.pass).length;
  const lines: string[] = [
    "# GIABO Bulk Eval Master Review Report",
    "",
    `- Run ID: \`${runId}\``,
    `- Started: ${startedAt}`,
    `- Total scenarios: ${rows.length}`,
    `- goldMatch: ${goldPass}/${rows.length} PASS`,
    `- Azure-judged sample: ${azurePass}/${azureRows.length} PASS (${azureRows.length} sampled)`,
    "",
    "## Summary by role",
    "",
  ];
  for (let i = 0; i < GIABO_ROLE_IDS.length; i++) {
    const role = GIABO_ROLE_IDS[i]!;
    const roleRows = rows.filter((r) => r.scenario.targetAgentRole === role);
    const g = roleRows.filter((r) => r.goldMatch).length;
    const a = roleRows.filter((r) => r.judgeSource === "azure");
    const ap = a.filter((r) => r.verdict.pass).length;
    lines.push(
      `- ${i + 1}/27 \`${role}\`: n=${roleRows.length}, goldMatch ${g}/${roleRows.length}, Azure ${ap}/${a.length}`,
    );
  }
  lines.push("", "## Scenarios", "");
  for (const row of rows) {
    const rule = `${row.scenario.originatingRule.mdc} / ${row.scenario.originatingRule.implementingFile}`;
    const actual = [
      `tool: ${row.simulation.actualTool}`,
      row.simulation.actualNextNode ? `next_node: ${row.simulation.actualNextNode}` : null,
      `wroteBaseline: ${row.simulation.wroteBaseline}`,
      "",
      row.simulation.monologue.map((m) => `- ${m}`).join("\n"),
      "",
      "```json",
      JSON.stringify(row.simulation.output, null, 2),
      "```",
    ]
      .filter(Boolean)
      .join("\n");
    lines.push(
      `### ${row.scenario.id}`,
      "",
      `- **Scenario ID:** ${row.scenario.id}`,
      `- **Target Agent Role (1–27):** ${row.scenario.roleIndex}/27 \`${row.scenario.targetAgentRole}\``,
      `- **Originating GIABO Rule (.mdc / Prompt):** ${rule}`,
      `- **Expected Framework Behavior:** ${row.scenario.expectedFrameworkBehavior}`,
      `- **goldMatch:** ${row.goldMatch ? "PASS" : "FAIL"}`,
      `- **LLM Judge Score (0-100) & Justification (PASS / FAIL):** ${row.verdict.score} **${row.verdict.pass ? "PASS" : "FAIL"}** (judgeSource: ${row.judgeSource})`,
      "",
      row.verdict.justification,
      "",
      "#### Exact Input (Transcript / Task State / Prompt)",
      "",
      "```json",
      JSON.stringify(row.scenario.input, null, 2),
      "```",
      "",
      "#### Actual Agent Reasoning & Output",
      "",
      actual,
      "",
    );
  }
  return `${lines.join("\n")}\n`;
}

async function main(): Promise<void> {
  const scenarios = loadOrGenerateBulk();
  const azureIds = pickJudgeSample(scenarios);
  const { client, deployment } = requireAzureOpenAI();
  const runId = randomUUID();
  const startedAt = new Date().toISOString();
  const rows: Row[] = scenarios.map((scenario) => {
    const simulation = simulateRole(scenario);
    const match = goldMatch(scenario, simulation);
    return {
      scenario,
      simulation,
      goldMatch: match,
      verdict: deterministicVerdict(match),
      judgeSource: "deterministic" as const,
    };
  });

  const toJudge = rows.filter((r) => azureIds.has(r.scenario.id));
  console.log(`Simulated ${rows.length}. Azure-judging ${toJudge.length} (27 canonical + extras).`);

  await mapPool(toJudge, CONCURRENCY, async (row) => {
    try {
      row.verdict = await judgeWithAzureRetry(client, deployment, JUDGE_SYSTEM, {
        originatingRule: row.scenario.originatingRule,
        description: row.scenario.description,
        input: row.scenario.input,
        simulation: row.simulation,
      });
      row.judgeSource = "azure";
    } catch (err) {
      row.verdict = {
        pass: false,
        score: 0,
        reasoningCoherence: 0,
        contextRetention: 0,
        toolSelectionCorrectness: 0,
        justification: `Azure judge error after retries: ${err instanceof Error ? err.message : String(err)}`,
      };
      row.judgeSource = "azure";
    }
    console.log(
      `[azure ${row.scenario.roleIndex}/27] ${row.scenario.id} ${row.verdict.pass ? "PASS" : "FAIL"} score=${row.verdict.score}`,
    );
  });

  await withEvalAuditClient(async (pgClient) => {
    for (const row of rows) {
      await insertEvalAudit(pgClient, {
        runId,
        suite: "giabo_bulk",
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
        judgeVerdict: { ...row.verdict, judgeSource: row.judgeSource, goldMatch: row.goldMatch },
        modelDeployment: deployment,
      });
    }
  });

  const outDir = join(here, "../results");
  mkdirSync(outDir, { recursive: true });
  writeFileSync(
    join(outDir, "bulkEvalLog.json"),
    JSON.stringify({ runId, startedAt, endedAt: new Date().toISOString(), modelDeployment: deployment, rows }, null, 2),
    "utf8",
  );
  const reportPath = join(outDir, "masterReviewReport.md");
  writeFileSync(reportPath, compileReport(runId, startedAt, rows), "utf8");

  const goldFail = rows.filter((r) => !r.goldMatch);
  const azureFail = rows.filter((r) => r.judgeSource === "azure" && !r.verdict.pass);
  console.log(`Wrote ${reportPath}`);
  console.log(`goldMatch fail=${goldFail.length} azure fail=${azureFail.length} total=${rows.length}`);
  if (goldFail.length || azureFail.length) {
    process.exit(1);
  }
  console.log("PASS: bulk eval complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
