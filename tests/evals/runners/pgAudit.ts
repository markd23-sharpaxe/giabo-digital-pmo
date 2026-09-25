import { randomUUID } from "node:crypto";
import pg from "pg";

export const EVAL_AUDIT_TABLE_SQL = `
CREATE TABLE IF NOT EXISTS eval_audit_logs (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                          UUID NOT NULL,
    suite                           TEXT NOT NULL,
    scenario_id                     TEXT NOT NULL,
    target_agent_role               TEXT,
    originating_rule                TEXT,
    pass                            BOOLEAN NOT NULL,
    score                           NUMERIC(5, 2) NOT NULL,
    reasoning_coherence             NUMERIC(5, 2) NOT NULL,
    context_retention               NUMERIC(5, 2) NOT NULL,
    tool_selection_correctness      NUMERIC(5, 2) NOT NULL,
    justification                   TEXT NOT NULL,
    actual_tool                     TEXT,
    gold_expected                   JSONB,
    reasoning_trace                 JSONB NOT NULL,
    tool_log                        JSONB NOT NULL,
    judge_verdict                   JSONB NOT NULL,
    model_deployment                TEXT,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);
`;

export type EvalAuditInsert = {
  runId: string;
  suite: string;
  scenarioId: string;
  targetAgentRole?: string;
  originatingRule?: string;
  pass: boolean;
  score: number;
  reasoningCoherence: number;
  contextRetention: number;
  toolSelectionCorrectness: number;
  justification: string;
  actualTool?: string;
  goldExpected: unknown;
  reasoningTrace: unknown;
  toolLog: unknown;
  judgeVerdict: unknown;
  modelDeployment?: string;
};

export function nodePgUrl(databaseUrl: string): string {
  return databaseUrl.replace(/^postgresql\+psycopg:\/\//, "postgresql://");
}

export async function withEvalAuditClient<T>(fn: (client: pg.Client) => Promise<T>): Promise<T> {
  const raw = process.env.DATABASE_URL;
  if (!raw) {
    throw new Error("DATABASE_URL is not set");
  }
  const client = new pg.Client({
    connectionString: nodePgUrl(raw),
    ssl: { rejectUnauthorized: false },
  });
  await client.connect();
  try {
    await client.query(EVAL_AUDIT_TABLE_SQL);
    return await fn(client);
  } finally {
    await client.end();
  }
}

export async function insertEvalAudit(client: pg.Client, row: EvalAuditInsert): Promise<void> {
  await client.query(
    `INSERT INTO eval_audit_logs (
        id, run_id, suite, scenario_id, target_agent_role, originating_rule,
        pass, score, reasoning_coherence, context_retention, tool_selection_correctness,
        justification, actual_tool, gold_expected, reasoning_trace, tool_log,
        judge_verdict, model_deployment
     ) VALUES (
        $1,$2,$3,$4,$5,$6,
        $7,$8,$9,$10,$11,
        $12,$13,$14::jsonb,$15::jsonb,$16::jsonb,
        $17::jsonb,$18
     )`,
    [
      randomUUID(),
      row.runId,
      row.suite,
      row.scenarioId,
      row.targetAgentRole ?? null,
      row.originatingRule ?? null,
      row.pass,
      row.score,
      row.reasoningCoherence,
      row.contextRetention,
      row.toolSelectionCorrectness,
      row.justification,
      row.actualTool ?? null,
      JSON.stringify(row.goldExpected),
      JSON.stringify(row.reasoningTrace),
      JSON.stringify(row.toolLog),
      JSON.stringify(row.judgeVerdict),
      row.modelDeployment ?? null,
    ],
  );
}
