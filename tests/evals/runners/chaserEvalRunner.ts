import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { config } from "dotenv";
import { judgeWithAzure, requireAzureOpenAI } from "./azureJudge.ts";
import { insertEvalAudit, withEvalAuditClient } from "./pgAudit.ts";
import {
  FATIGUE_WINDOW_HOURS,
  ScenarioArraySchema,
  type Scenario,
  type ReasoningTrace,
  type ToolExecutionLog,
  type JudgeVerdict,
} from "../types/evalSchema.ts";

const here = dirname(fileURLToPath(import.meta.url));
config({ path: join(here, "../../..", ".env") });

const JUDGE_SYSTEM = `You are the GIABO Chaser Agent judge.
Rubric (0-100 each), reference-free (you are not given gold labels):
- reasoningCoherence: did the agent state impact*1.5 + risk*1.2 times max(1, 10-days), and the 24h zero-out?
- contextRetention: did it use hours_since_last_contact and any assignee reply?
- toolSelectionCorrectness: suppress_chase iff hours<24 / score 0; else send_teams_chase; rank remaining by score desc.
pass=true only if those invariants hold. score is the mean of the three. Return JSON matching {pass, score, reasoningCoherence, contextRetention, toolSelectionCorrectness, justification}.`;

function chasingScore(hours: number, days: number, impact: number, risk: number): number {
  if (hours < FATIGUE_WINDOW_HOURS) return 0;
  const raw = (impact * 1.5 + risk * 1.2) * Math.max(1, 10 - days);
  return Math.round(raw * 10) / 10;
}

function simulateChaser(scenario: Scenario): { trace: ReasoningTrace; tools: ToolExecutionLog[] } {
  const perTask = scenario.input.tasks.map((task) => {
    const score = chasingScore(
      task.hours_since_last_contact,
      task.days_to_deadline,
      task.critical_path_impact,
      task.linked_risks_severity,
    );
    const inCooldown = task.hours_since_last_contact < FATIGUE_WINDOW_HOURS;
    return {
      taskId: task.task_id,
      fatigueCheck: {
        hoursSinceLastContact: task.hours_since_last_contact,
        windowHours: FATIGUE_WINDOW_HOURS,
        inCooldown,
      },
      computedChasingScore: score,
      last_assignee_message: task.last_assignee_message,
    };
  });
  const ranked = [...perTask].filter((t) => t.computedChasingScore > 0).sort((a, b) => b.computedChasingScore - a.computedChasingScore);
  const headline = perTask[0];
  const monologue = [
    "Dynamic chasing: if hours_since_last_contact < 24, score is 0.0 (fatigue).",
    "Else score = (critical_path_impact * 1.5 + linked_risks_severity * 1.2) * max(1, 10 - days_to_deadline).",
    ...perTask.map(
      (t) =>
        `${t.taskId}: hours=${t.fatigueCheck.hoursSinceLastContact} cooldown=${t.fatigueCheck.inCooldown} score=${t.computedChasingScore}` +
        (t.last_assignee_message ? ` last_reply=${t.last_assignee_message}` : ""),
    ),
    ranked.length
      ? `Chase order: ${ranked.map((t) => t.taskId).join(" > ")}`
      : "No tasks survive the fatigue filter; suppress all outreach.",
  ];
  const now = new Date().toISOString();
  const tools: ToolExecutionLog[] = perTask.map((t) => ({
    tool: t.computedChasingScore === 0 ? "suppress_chase" : "send_teams_chase",
    taskId: t.taskId,
    arguments: { chasing_score: t.computedChasingScore },
    timestamp: now,
  }));
  return {
    trace: {
      scenarioId: scenario.id,
      monologue,
      fatigueCheck: headline.fatigueCheck,
      computedChasingScore: headline.computedChasingScore,
      perTask: perTask.map(({ last_assignee_message: _, ...rest }) => rest),
    },
    tools,
  };
}

async function main(): Promise<void> {
  const scenarios = ScenarioArraySchema.parse(
    JSON.parse(readFileSync(join(here, "../datasets/chaserScenarios.json"), "utf8")),
  );
  const { client, deployment } = requireAzureOpenAI();
  const runId = randomUUID();
  const startedAt = new Date().toISOString();
  const results: { scenario: Scenario; trace: ReasoningTrace; tools: ToolExecutionLog[]; verdict: JudgeVerdict }[] = [];

  await withEvalAuditClient(async (pgClient) => {
    for (const scenario of scenarios) {
      const { trace, tools } = simulateChaser(scenario);
      const verdict = await judgeWithAzure(client, deployment, JUDGE_SYSTEM, {
        input: scenario.input,
        trace,
        tools,
      });
      results.push({ scenario, trace, tools, verdict });
      await insertEvalAudit(pgClient, {
        runId,
        suite: "chaser",
        scenarioId: scenario.id,
        targetAgentRole: "21/27 chasing_agent",
        originatingRule: "08-maf-dynamic-chasing-persona.mdc :: maf_graph_state.py",
        pass: verdict.pass,
        score: verdict.score,
        reasoningCoherence: verdict.reasoningCoherence,
        contextRetention: verdict.contextRetention,
        toolSelectionCorrectness: verdict.toolSelectionCorrectness,
        justification: verdict.justification,
        actualTool: tools[0]?.tool,
        goldExpected: scenario.expected,
        reasoningTrace: trace,
        toolLog: tools,
        judgeVerdict: verdict,
        modelDeployment: deployment,
      });
      console.log(`${scenario.id}: ${verdict.pass ? "PASS" : "FAIL"} score=${verdict.score} tool=${tools[0]?.tool}`);
    }
  });

  const outDir = join(here, "../results");
  mkdirSync(outDir, { recursive: true });
  writeFileSync(
    join(outDir, "chaserEvalLog.json"),
    JSON.stringify({ runId, startedAt, endedAt: new Date().toISOString(), modelDeployment: deployment, scenarios: results }, null, 2),
    "utf8",
  );
  const failed = results.filter((r) => !r.verdict.pass);
  if (failed.length) {
    console.error(`FAIL: ${failed.length}/${results.length} chaser judge verdicts failed.`);
    process.exit(1);
  }
  console.log("PASS: all chaser eval scenarios judged pass.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
