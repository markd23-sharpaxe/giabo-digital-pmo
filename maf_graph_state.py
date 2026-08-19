"""Execution-graph state & Pydantic schemas for the Teams/Outlook conversational
triage graph (Phase 2: MAF Execution Graph and Router Node Prompts; Phase 3:
Change Control Clerk + PM Veto Interrupt).

"Loose on Dialogue, Strict on State": `PMOState` is the only thing that
survives between turns and is what the `app_graph.py` graph mutates; the
Router's own reasoning is disposable per-turn output constrained to
`TriageRouterDecision`'s schema.

Note: this is a *separate* state/graph from `core/state.py`'s `SwarmState`,
which drives the SharePoint delta-dispatch RAID graph (01-maf-core-orchestrator.mdc).
This module models the other channel named in 07-maf-digital-pmo-sop.mdc's
"Multi-Channel Execution": live Teams/Outlook conversation triage.
"""

from typing import Literal, Optional, List, Dict, Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------
# ROUTER SCHEMA
# ---------------------------------------------------------
class TriageRouterDecision(BaseModel):
    next_node: Literal[
        "pmp_worker",
        "agile_worker",
        "governance_worker",
        "change_control_clerk",
        "escalation_node",
        "end_conversation",
    ]
    reasoning: str
    update_vague_turns: bool
    extracted_entities: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------
# CHANGE CONTROL / PM VETO SCHEMA
# ---------------------------------------------------------
class PendingChangePayload(BaseModel):
    change_id: str = Field(description="Unique UUID for this proposed change")
    target_table: Literal["tasks", "baselines", "budgets"]
    record_id: str
    proposed_values: Dict[str, Any]
    prince2_impact_assessment: str = Field(
        description="A brief explanation of how this affects tolerances/critical path."
    )


# ---------------------------------------------------------
# TRI-FRAMEWORK SPECIALIST SCHEMAS
# ---------------------------------------------------------
class TaskProgressPayload(BaseModel):
    task_id: str
    percent_complete: int = Field(ge=0, le=100)
    actual_hours_spent: float
    is_critical_path: bool
    status_summary: str = Field(description="A brief summary for the PMP status report.")


class BlockerPayload(BaseModel):
    task_id: str
    blocker_description: str
    requires_cross_team_help: bool
    agile_action_item: str = Field(description="The next immediate step to unblock the team.")


class RiskEscalationPayload(BaseModel):
    risk_category: Literal["budget", "scope", "timeline", "compliance"]
    severity: int = Field(ge=1, le=5)
    description: str
    prince2_exception_triggered: bool = Field(description="True if this breaches a stage tolerance.")


# ---------------------------------------------------------
# STRICT STATE SCHEMA (Database / Graph State)
# ---------------------------------------------------------
class PMOState(BaseModel):
    project_id: str
    user_id: str
    message_history: List[dict] = Field(default_factory=list)
    vague_turns: int = Field(default=0)
    billing_status: Literal["active_trial", "trial_exhausted", "active_paid", "paid_halt"]

    # PM Veto State
    requires_pm_veto: bool = Field(default=False)
    pending_change: Optional[PendingChangePayload] = None
    pm_veto_decision: Optional[Literal["approved", "rejected"]] = None

    # Tri-Framework Specialist State -- latest payload per worker type. Not an
    # accumulating history: there's no writeback agent consuming these yet
    # (03-maf-writeback-agents.mdc), so each is overwritten by that worker's
    # next turn until one exists.
    latest_task_progress: Optional[TaskProgressPayload] = None
    latest_blocker: Optional[BlockerPayload] = None
    latest_risk_escalation: Optional[RiskEscalationPayload] = None

    # PRINCE2 Exception Interrupt State -- set once a human PM resolves an
    # exception raised by `state_writeback_node`/`suspend_for_exception_node`.
    exception_decision: Optional[Literal["acknowledge", "escalate_to_board"]] = None


# ---------------------------------------------------------
# DYNAMIC CHASING WEIGHT SCHEMA
# ---------------------------------------------------------
class ChasingWeight(BaseModel):
    task_id: str
    critical_path_impact: int = Field(ge=1, le=10)
    linked_risks_severity: int = Field(ge=1, le=10)
    hours_since_last_contact: int
    days_to_deadline: int

    @property
    def chasing_score(self) -> float:
        # Immutable Principle 4: Dynamic Chasing (No Cron)
        # Fatigue Cooldown (24h)
        if self.hours_since_last_contact < 24:
            return 0.0

        proximity_multiplier = max(1, (10 - self.days_to_deadline))
        base_score = (self.critical_path_impact * 1.5) + (self.linked_risks_severity * 1.2)
        return base_score * proximity_multiplier
