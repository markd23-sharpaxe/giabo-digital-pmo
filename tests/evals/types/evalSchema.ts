/**
 * Strict Zod contracts for the GIABO PMO Chaser Agent synthetic eval suite.
 *
 * Score formula (mirrors maf_graph_state.ChasingWeight.chasing_score):
 *   if hours_since_last_contact < 24: 0.0  (24h fatigue cooldown)
 *   else: (impact * 1.5 + risk * 1.2) * max(1, 10 - days_to_deadline)
 *
 * chasing_engine.calculate_chasing_priorities omits score == 0.0, then sorts
 * remaining tasks descending by chasing_score.
 */
import { z } from "zod";

export const FATIGUE_WINDOW_HOURS = 24 as const;

export const ChaseToolSchema = z.enum(["send_teams_chase", "suppress_chase"]);
export type ChaseTool = z.infer<typeof ChaseToolSchema>;

export const TaskInputSchema = z.object({
  task_id: z.string().min(1),
  assignee: z.string().min(1),
  task_name: z.string().min(1),
  hours_since_last_contact: z.number().int().nonnegative(),
  days_to_deadline: z.number().int(),
  critical_path_impact: z.number().int().min(1).max(10),
  linked_risks_severity: z.number().int().min(1).max(10),
  last_assignee_message: z.string().min(1).optional(),
});
export type TaskInput = z.infer<typeof TaskInputSchema>;

export const ExpectedBehaviorSchema = z.object({
  shouldChase: z.boolean(),
  expectedAction: ChaseToolSchema,
  expectedTool: ChaseToolSchema,
  expectedRankedTaskIds: z.array(z.string().min(1)),
  expectedChasingScores: z.record(z.string().min(1), z.number()),
});
export type ExpectedBehavior = z.infer<typeof ExpectedBehaviorSchema>;

export const ScenarioSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  description: z.string().min(1),
  input: z.object({
    project_id: z.string().min(1),
    tasks: z.array(TaskInputSchema).min(1),
  }),
  expected: ExpectedBehaviorSchema,
});
export type Scenario = z.infer<typeof ScenarioSchema>;

export const ScenarioArraySchema = z.array(ScenarioSchema).length(5);
export type ScenarioArray = z.infer<typeof ScenarioArraySchema>;

export const FatigueCheckSchema = z.object({
  hoursSinceLastContact: z.number().int().nonnegative(),
  windowHours: z.literal(FATIGUE_WINDOW_HOURS),
  inCooldown: z.boolean(),
});
export type FatigueCheck = z.infer<typeof FatigueCheckSchema>;

export const PerTaskReasoningSchema = z.object({
  taskId: z.string().min(1),
  fatigueCheck: FatigueCheckSchema,
  computedChasingScore: z.number().nonnegative(),
});
export type PerTaskReasoning = z.infer<typeof PerTaskReasoningSchema>;

export const ReasoningTraceSchema = z.object({
  scenarioId: z.string().min(1),
  monologue: z.array(z.string()),
  fatigueCheck: FatigueCheckSchema,
  computedChasingScore: z.number().nonnegative(),
  perTask: z.array(PerTaskReasoningSchema).optional(),
});
export type ReasoningTrace = z.infer<typeof ReasoningTraceSchema>;

export const ToolExecutionLogSchema = z.object({
  tool: ChaseToolSchema,
  taskId: z.string().min(1),
  arguments: z.record(z.string(), z.unknown()),
  timestamp: z.string().datetime(),
});
export type ToolExecutionLog = z.infer<typeof ToolExecutionLogSchema>;

export const JudgeVerdictSchema = z.object({
  pass: z.boolean(),
  score: z.number().min(0).max(100),
  reasoningCoherence: z.number().min(0).max(100),
  contextRetention: z.number().min(0).max(100),
  toolSelectionCorrectness: z.number().min(0).max(100),
  justification: z.string().min(1),
});
export type JudgeVerdict = z.infer<typeof JudgeVerdictSchema>;

export const GIABO_ROLE_IDS = [
  "change_control_clerk",
  "prince2_exception_master",
  "raid_compliance_auto_chaser",
  "risk_radar_monitor",
  "lessons_learned_curator",
  "dependency_map_maintainer",
  "scrum_master_liaison",
  "forensic_alignment_engine",
  "earned_value_analyst",
  "governance_synthesizer",
  "stage_gate_guardian",
  "project_health_reporter",
  "governance_auditor",
  "eom_financial_checkpoint",
  "sprint_boundary_watchdog",
  "pmo_commander_router",
  "conversational_router",
  "pmp_schedule_specialist",
  "agile_facilitator",
  "prince2_governance_worker",
  "chasing_agent",
  "sharepoint_delta_ingestion",
  "billing_gatekeeper",
  "friction_breaker",
  "token_loop_breaker",
  "pm_veto_interrupt",
  "prince2_exception_interrupt",
] as const;

export const GiaboRoleIdSchema = z.enum(GIABO_ROLE_IDS);
export type GiaboRoleId = z.infer<typeof GiaboRoleIdSchema>;

export const OriginatingRuleSchema = z.object({
  mdc: z.string().min(1),
  implementingFile: z.string().min(1),
  invariantQuote: z.string().min(1),
});
export type OriginatingRule = z.infer<typeof OriginatingRuleSchema>;

export const FrameworkExpectedSchema = z.object({
  shouldAct: z.boolean(),
  expectedTool: z.string().min(1).optional(),
  expectedNextNode: z.string().min(1).optional(),
  expectedArtifactType: z.string().min(1).optional(),
  mustNotWriteBaseline: z.boolean(),
  goldTraceAssertions: z.array(z.string().min(1)).min(1),
});
export type FrameworkExpected = z.infer<typeof FrameworkExpectedSchema>;

export const FrameworkScenarioSchema = z.object({
  id: z.string().min(1),
  roleIndex: z.number().int().min(1).max(27),
  targetAgentRole: GiaboRoleIdSchema,
  originatingRule: OriginatingRuleSchema,
  description: z.string().min(1),
  expectedFrameworkBehavior: z.string().min(1),
  input: z.record(z.string(), z.unknown()),
  expected: FrameworkExpectedSchema,
});
export type FrameworkScenario = z.infer<typeof FrameworkScenarioSchema>;

export const FrameworkScenarioArraySchema = z
  .array(FrameworkScenarioSchema)
  .length(27)
  .superRefine((scenarios, ctx) => {
    const roles = scenarios.map((s) => s.targetAgentRole);
    if (new Set(roles).size !== GIABO_ROLE_IDS.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `targetAgentRole must list each of the ${GIABO_ROLE_IDS.length} GIABO roles exactly once`,
      });
    }
    const missing = GIABO_ROLE_IDS.filter((role) => !roles.includes(role));
    if (missing.length > 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `missing roles: ${missing.join(", ")}`,
      });
    }
    const indexes = scenarios.map((s) => s.roleIndex).sort((a, b) => a - b);
    const expectedIndexes = GIABO_ROLE_IDS.map((_, i) => i + 1);
    if (indexes.join(",") !== expectedIndexes.join(",")) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "roleIndex must be the unique set 1..27",
      });
    }
  });
export type FrameworkScenarioArray = z.infer<typeof FrameworkScenarioArraySchema>;

export const BulkScenarioArraySchema = z
  .array(FrameworkScenarioSchema)
  .min(200)
  .superRefine((scenarios, ctx) => {
    const present = new Set(scenarios.map((s) => s.targetAgentRole));
    const missing = GIABO_ROLE_IDS.filter((role) => !present.has(role));
    if (missing.length > 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `bulk dataset missing roles: ${missing.join(", ")}`,
      });
    }
  });
export type BulkScenarioArray = z.infer<typeof BulkScenarioArraySchema>;

export const STRUCTURED_SCENARIO_COUNT = 81 as const;

export const StructuredScenarioSchema = FrameworkScenarioSchema;
export type StructuredScenario = z.infer<typeof StructuredScenarioSchema>;

export const StructuredScenarioArraySchema = z
  .array(StructuredScenarioSchema)
  .length(STRUCTURED_SCENARIO_COUNT)
  .superRefine((scenarios, ctx) => {
    const ids = scenarios.map((s) => s.id);
    if (new Set(ids).size !== ids.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "structured scenario ids must be unique",
      });
    }
    const present = new Set(scenarios.map((s) => s.targetAgentRole));
    const missing = GIABO_ROLE_IDS.filter((role) => !present.has(role));
    if (missing.length > 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `structured dataset missing roles: ${missing.join(", ")}`,
      });
    }
    scenarios.forEach((scenario, index) => {
      const expectedIndex = GIABO_ROLE_IDS.indexOf(scenario.targetAgentRole) + 1;
      if (scenario.roleIndex !== expectedIndex) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `scenarios[${index}] (${scenario.id}): roleIndex ${scenario.roleIndex} does not match ${scenario.targetAgentRole} (expected ${expectedIndex})`,
        });
      }
    });
  });
export type StructuredScenarioArray = z.infer<typeof StructuredScenarioArraySchema>;
