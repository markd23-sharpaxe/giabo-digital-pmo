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

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional, List, Dict, Any, FrozenSet
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# ROUTER SCHEMA
# ---------------------------------------------------------
class ExtractedEntity(BaseModel):
    """One key/value pair the Router pulled out of the user's message (e.g.
    key='task_id', value='TSK-002'). A `List[ExtractedEntity]`, not a
    `Dict[str, Any]` -- Azure OpenAI's strict structured-output mode rejects
    genuinely open-ended objects (verified live: 'additionalProperties is
    required to be supplied and to be false' on a bare `Dict[str, Any]`
    field, since strict mode can't validate arbitrary/unknown key names).
    A list of well-defined `{key, value}` objects is fully strict-schema
    compatible and round-trips to a dict just as easily downstream
    (`app_graph._render_worker_prompt`).
    """

    key: str
    value: str


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
    extracted_entities: Optional[List[ExtractedEntity]] = None
    wake_reason: Optional[Literal["user_message", "event_bus"]] = None


# ---------------------------------------------------------
# CHANGE CONTROL / PM VETO SCHEMA
# ---------------------------------------------------------
class PendingChangePayload(BaseModel):
    change_id: str = Field(description="Unique UUID for this proposed change")
    target_table: Literal["tasks", "baselines", "budgets"]
    record_id: str
    proposed_values: Dict[str, Any]
    prince2_impact_assessment: str = Field(
        description="A 1-2 sentence field/date/budget delta of what changes on the locked baseline. No risk analysis."
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
class EventType(str, Enum):
    """Closed blackboard event set. Agents must not invent types."""

    BASELINE_SLIP_REQUESTED = "BASELINE_SLIP_REQUESTED"
    BASELINE_CHANGE_APPROVED = "BASELINE_CHANGE_APPROVED"
    BASELINE_CHANGE_REJECTED = "BASELINE_CHANGE_REJECTED"
    TASK_PROGRESS_LOGGED = "TASK_PROGRESS_LOGGED"
    CRITICAL_PATH_SLIPPED = "CRITICAL_PATH_SLIPPED"
    BLOCKER_LOGGED = "BLOCKER_LOGGED"
    RISK_FLAGGED = "RISK_FLAGGED"
    TOLERANCE_BREACHED = "TOLERANCE_BREACHED"
    EXCEPTION_SUSPENDED = "EXCEPTION_SUSPENDED"
    EXCEPTION_RESOLVED = "EXCEPTION_RESOLVED"
    CHASE_SENT = "CHASE_SENT"
    CHASE_SUPPRESSED = "CHASE_SUPPRESSED"
    RAID_ARTIFACT_WRITTEN = "RAID_ARTIFACT_WRITTEN"
    DOCUMENT_INGESTED = "DOCUMENT_INGESTED"
    TEAMS_MESSAGE_RECEIVED = "TEAMS_MESSAGE_RECEIVED"
    EMAIL_RECEIVED = "EMAIL_RECEIVED"


EVENT_BUS_MAX = 100

# Aim 1 / Aim 2: only these publishers may emit each type. Hard-fail otherwise.
LEGAL_PUBLISHERS: Dict[EventType, FrozenSet[str]] = {
    EventType.BASELINE_SLIP_REQUESTED: frozenset({"change_control_clerk"}),
    EventType.BASELINE_CHANGE_APPROVED: frozenset({"baseline_commit_node"}),
    EventType.BASELINE_CHANGE_REJECTED: frozenset({"baseline_commit_node"}),
    EventType.TASK_PROGRESS_LOGGED: frozenset({"pmp_worker", "pmp_schedule_specialist"}),
    EventType.CRITICAL_PATH_SLIPPED: frozenset({"pmp_worker", "pmp_schedule_specialist"}),
    EventType.BLOCKER_LOGGED: frozenset({"agile_worker", "agile_facilitator"}),
    EventType.RISK_FLAGGED: frozenset({"governance_worker", "prince2_governance_worker"}),
    EventType.TOLERANCE_BREACHED: frozenset(
        {"state_writeback_node", "governance_worker", "prince2_governance_worker"}
    ),
    EventType.EXCEPTION_SUSPENDED: frozenset({"state_writeback_node", "suspend_for_exception_node"}),
    EventType.EXCEPTION_RESOLVED: frozenset({"exception_commit_node"}),
    EventType.CHASE_SENT: frozenset({"chasing_agent"}),
    EventType.CHASE_SUPPRESSED: frozenset({"chasing_agent"}),
    EventType.RAID_ARTIFACT_WRITTEN: frozenset(
        {
            "risk_radar_monitor",
            "raid_compliance_auto_chaser",
            "lessons_learned_curator",
            "dependency_map_maintainer",
            "scrum_master_liaison",
            "eom_financial_checkpoint",
            "sprint_boundary_watchdog",
        }
    ),
    EventType.DOCUMENT_INGESTED: frozenset({"sharepoint_delta_ingestion"}),
    EventType.TEAMS_MESSAGE_RECEIVED: frozenset({"teams_bot"}),
    EventType.EMAIL_RECEIVED: frozenset({"outlook_inbox_ingestion"}),
}

_BASELINE_SLIP_FORBIDDEN_PAYLOAD_KEYS = frozenset({"risk_category", "severity", "questions"})


class IllegalEventPublishError(ValueError):
    """Raised when a publisher attempts an event type it is not allowed to emit."""


class BlackboardEvent(BaseModel):
    """One append-only row on the conversational blackboard."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: EventType
    publisher: str
    project_id: str
    correlation_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    consumed_by: List[str] = Field(default_factory=list)


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

    # Universal blackboard (Aim 1–3). Append-only; capped at EVENT_BUS_MAX.
    event_bus: List[BlackboardEvent] = Field(default_factory=list)
    wake_reason: Optional[Literal["user_message", "event_bus"]] = None
    proactive_target: Optional[str] = None


def append_event(state: "PMOState", event: BlackboardEvent) -> "PMOState":
    """Append `event` to `state.event_bus` or hard-fail on an illegal pair.

    Aim 1: only `change_control_clerk` may publish BASELINE_SLIP_REQUESTED,
    and that payload must not carry risk fields.
    Aim 2: proactive agents cannot publish BASELINE_* draft/decision events.
    """
    allowed = LEGAL_PUBLISHERS.get(event.event_type)
    if allowed is None or event.publisher not in allowed:
        raise IllegalEventPublishError(
            f"Publisher {event.publisher!r} cannot emit {event.event_type.value}."
        )
    if event.event_type == EventType.BASELINE_SLIP_REQUESTED:
        illegal = _BASELINE_SLIP_FORBIDDEN_PAYLOAD_KEYS.intersection(event.payload)
        if illegal:
            raise IllegalEventPublishError(
                f"BASELINE_SLIP_REQUESTED payload must not contain risk fields: {sorted(illegal)}"
            )
    bus = [*state.event_bus, event]
    if len(bus) > EVENT_BUS_MAX:
        bus = bus[-EVENT_BUS_MAX:]
    return state.model_copy(update={"event_bus": bus})


def persist_blackboard_event(event: BlackboardEvent) -> bool:
    """Best-effort Postgres write so sibling runs and ingress can see the event.

    Returns True on a successful merge. Failures are warning-logged (never
    silent debug) so missing `event_bus` / DATABASE_URL is visible.
    """
    try:
        from db.models import EventBusRow
        from db.session import get_session

        with get_session() as session:
            session.merge(
                EventBusRow(
                    event_id=event.event_id,
                    project_id=event.project_id,
                    event_type=event.event_type.value,
                    publisher=event.publisher,
                    correlation_id=event.correlation_id,
                    payload=event.payload,
                    consumed_by=event.consumed_by,
                    occurred_at=event.occurred_at,
                )
            )
            session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 - bus persist must never fail a turn
        logger.warning("event_bus persist failed for %s/%s: %s", event.event_type.value, event.event_id, exc)
        return False


def record_ingress_event(project_id: str, event: BlackboardEvent) -> bool:
    """Validate `event` through `append_event` and persist it to Postgres.

    Ingress paths (SharePoint, Teams, Outlook) have no conversational
    PMOState; a scratch state is used only for the allow-list gate.
    Returns True when the Postgres write succeeded.
    """
    if event.project_id != project_id:
        event = event.model_copy(update={"project_id": str(project_id)})
    scratch = PMOState(project_id=str(project_id), user_id="ingress", billing_status="active_trial")
    append_event(scratch, event)
    return persist_blackboard_event(event)


def mark_event_consumed(state: "PMOState", event_id: str, agent: str) -> "PMOState":
    """Record that `agent` has woken on `event_id` (one-wake loop breaker)."""
    updated: List[BlackboardEvent] = []
    for item in state.event_bus:
        if item.event_id == event_id and agent not in item.consumed_by:
            updated.append(item.model_copy(update={"consumed_by": [*item.consumed_by, agent]}))
        else:
            updated.append(item)
    return state.model_copy(update={"event_bus": updated})


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
