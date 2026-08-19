"""Phase 2/3/5/6: MAF Execution Graph for the Teams/Outlook conversational triage layer.

Supervisor-Worker topology, built on the real `agent_framework` (MAF)
`WorkflowBuilder`/`Executor` primitives (the SDK the rest of this project
already standardizes on -- see `core/workflow.py` -- so this graph does not
pull in a second, competing graph library such as LangGraph):

    Gateway Middleware (billing halt check)
        -> Router Node (Supervisor; structured JSON decision, Friction Breaker)
            -> switch-case fan-out, in priority order:
                1. hard_fail_node        (Token Loop Breaker exhausted retries)
                2. escalation_node       (Friction Breaker: vague_turns >= 2)
                3. pmp_worker / agile_worker / governance_worker
                   (per the LLM's TriageRouterDecision.next_node; real
                   Tri-Framework Specialist executors as of Phase 5 -- each
                   calls Azure OpenAI with its own prompt + Pydantic
                   `response_format`, then mutates PMOState.latest_*)
                4. change_control_clerk  (real, Phase 3)
                5. end_conversation      (default)

Phase 3 adds the Change Control Clerk's baseline-write authority and the
PM Veto Adaptive Card human-in-the-loop gate:

    change_control_clerk (drafts a PendingChangePayload proposal)
        -> suspend_for_veto_node (PM Veto Interrupt: pauses the graph via MAF's
           native `ctx.request_info` human-in-the-loop mechanism; a checkpoint
           is written to disk so a *separate process* -- an external Teams
           Action.Submit webhook, simulated here by `simulate_teams_webhook.py`
           -- can resume it later by calling `resume_after_veto`)
        -> baseline_commit_node (runs after resume; commits or rejects)

Phase 6 adds the Database Writeback + PRINCE2 Exception Interrupt chain
after each Tri-Framework specialist worker finishes:

    pmp_worker / agile_worker / governance_worker
        -> state_writeback_node (commits latest_task_progress/latest_blocker
           outright; for latest_risk_escalation, commits directly unless
           prince2_exception_triggered is set)
            -> [only if an exception was raised] suspend_for_exception_node
               (PRINCE2 Exception Interrupt: pauses via `ctx.request_info`,
               resumed out of process by `simulate_exception_webhook.py`
               calling `resume_after_exception`)
                -> exception_commit_node (runs after resume; finalizes the
                   risk commit and clears state)

Strictly acyclic by design: state_writeback_node is visited exactly once per
turn; the exception path hands off to exception_commit_node rather than
looping back.

Phase 7 (Real Database Integration) swaps `state_writeback_node`'s and
`baseline_commit_node`'s mock DB writes for real ones against the Phase 1
Postgres schema (`db_middleware.commit_task_progress` / `commit_blocker` /
`commit_risk_escalation` / `apply_baseline_change`, all backed by
`db.session.get_session`).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal, Optional, TypeVar
from uuid import uuid4

from agent_framework import (
    Agent,
    Case,
    CheckpointStorage,
    Default,
    Executor,
    FileCheckpointStorage,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowRunState,
    handler,
    response_handler,
)
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt
from typing_extensions import Never

from db_middleware import (
    BaselineChangeRejectedError,
    apply_baseline_change,
    commit_blocker,
    commit_risk_escalation,
    commit_task_progress,
)
from maf_graph_state import (
    BlockerPayload,
    PendingChangePayload,
    PMOState,
    RiskEscalationPayload,
    TaskProgressPayload,
    TriageRouterDecision,
)
from ui.cards import render_exception_card, render_pm_veto_card

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "router_node.md"
_CHANGE_CONTROL_PROMPT_PATH = Path(__file__).parent / "prompts" / "change_control_clerk.md"
_PMP_PROMPT_PATH = Path(__file__).parent / "prompts" / "pmp_worker.md"
_AGILE_PROMPT_PATH = Path(__file__).parent / "prompts" / "agile_worker.md"
_GOVERNANCE_PROMPT_PATH = Path(__file__).parent / "prompts" / "governance_worker.md"

# billing_status values that must hard-halt the graph before any Azure OpenAI
# call is made (02-maf-billing-gates.mdc). `active_trial` / `active_paid` pass.
_HALTED_BILLING_STATUSES = {"trial_exhausted", "paid_halt"}

# Stable workflow identity: required so a *second process* (e.g.
# `simulate_teams_webhook.py`) rebuilding this same graph resolves to the same
# checkpoint namespace as the process that paused it.
WORKFLOW_NAME = "giabo_pmo_triage"
DEFAULT_CHECKPOINT_DIR = Path(__file__).parent / ".checkpoints"

# Pydantic models that can appear in in-flight messages/state at a checkpoint
# boundary. `FileCheckpointStorage` pickles anything that isn't a JSON
# primitive and refuses to *unpickle* it again unless its `module:qualname`
# is explicitly allow-listed here -- a deserialization safety measure.
CHECKPOINT_ALLOWED_TYPES = [
    "maf_graph_state:PMOState",
    "maf_graph_state:TriageRouterDecision",
    "maf_graph_state:PendingChangePayload",
    "maf_graph_state:TaskProgressPayload",
    "maf_graph_state:BlockerPayload",
    "maf_graph_state:RiskEscalationPayload",
    "app_graph:HardHaltMessage",
    "app_graph:RoutedMessage",
    "app_graph:ChangeControlOutput",
    "app_graph:BaselineCommitInput",
    "app_graph:WorkerTurnOutput",
    "app_graph:ExceptionInterruptOutput",
    "app_graph:ExceptionCommitInput",
]


def default_checkpoint_storage() -> FileCheckpointStorage:
    """The `FileCheckpointStorage` `build_app_graph`/`run_turn` use when no
    `checkpoint_storage` is supplied. Exposed so `simulate_teams_webhook.py`
    (a separate process) can point at the identical directory *and*
    allow-list, matching exactly what wrote the checkpoint it is resuming.
    """
    return FileCheckpointStorage(str(DEFAULT_CHECKPOINT_DIR), allowed_checkpoint_types=CHECKPOINT_ALLOWED_TYPES)


# =============================================================================
# Requirement 1: read PMOState / TriageRouterDecision from maf_graph_state.py
# (imported above -- re-exported here for convenience)
# =============================================================================

__all__ = [
    "PMOState",
    "TriageRouterDecision",
    "HardHaltMessage",
    "RoutedMessage",
    "ChangeControlOutput",
    "BaselineCommitInput",
    "PendingVetoRequest",
    "WorkerTurnOutput",
    "ExceptionInterruptOutput",
    "ExceptionCommitInput",
    "PendingExceptionRequest",
    "GatewayMiddleware",
    "RouterNode",
    "router_node",
    "ChangeControlClerk",
    "SuspendForVetoNode",
    "BaselineCommitNode",
    "PMPWorker",
    "AgileWorker",
    "GovernanceWorker",
    "WorkerValidationError",
    "pmp_worker",
    "agile_worker",
    "governance_worker",
    "StateWritebackNode",
    "SuspendForExceptionNode",
    "ExceptionCommitNode",
    "WorkerExecutor",
    "WORKFLOW_NAME",
    "DEFAULT_CHECKPOINT_DIR",
    "CHECKPOINT_ALLOWED_TYPES",
    "default_checkpoint_storage",
    "build_app_graph",
    "run_turn",
    "resume_after_veto",
    "resume_after_exception",
    "build_default_router_chat_agent",
    "build_default_change_control_chat_agent",
    "build_default_pmp_chat_agent",
    "build_default_agile_chat_agent",
    "build_default_governance_chat_agent",
]


class HardHaltMessage(BaseModel):
    """Terminal output when the Gateway Middleware blocks execution."""

    state: PMOState
    reason: str


class RoutedMessage(BaseModel):
    """Single message envelope the Router sends downstream.

    Kept as one message type (rather than a Router-decision-only message)
    so the switch-case edge group below can evaluate the Friction Breaker
    and the Token Loop Breaker's failure path with the exact same routing
    mechanism used for the LLM's own `next_node` choice.
    """

    state: PMOState
    decision: Optional[TriageRouterDecision] = None
    failed: bool = False
    error: Optional[str] = None


# =============================================================================
# Requirement 2: Entrypoint / Gateway Middleware -- billing halt check
# =============================================================================


class GatewayMiddleware(Executor):
    """Checks `PMOState.billing_status` before anything else runs.

    This is the conversational-graph counterpart of `core.billing`'s
    sequential gates: cheap, synchronous, and BEFORE any Azure OpenAI call.
    For the full atomic spend/overage accounting (TOCTOU-safe accumulation,
    Standard Tier feature gating, project limits) see `core.billing.run_billing_gates`,
    which should populate `billing_status` upstream of this node.
    """

    def __init__(self, *, id: str = "gateway_middleware") -> None:
        super().__init__(id=id)

    @handler
    async def check(self, state: PMOState, ctx: WorkflowContext[PMOState, HardHaltMessage]) -> None:
        if state.billing_status in _HALTED_BILLING_STATUSES:
            await ctx.yield_output(
                HardHaltMessage(
                    state=state,
                    reason=(
                        "Your 14-day trial's token allowance has been used up."
                        if state.billing_status == "trial_exhausted"
                        else "Billing is on hold for this workspace."
                    ),
                )
            )
            return
        await ctx.send_message(state)


# =============================================================================
# Requirement 5 (moved up): Token Loop Breaker -- tenacity-wrapped LLM calls
# =============================================================================


class RouterValidationError(Exception):
    """Raised when the Router's structured-output call returns nothing
    tenacity can hand back as a valid `TriageRouterDecision` -- triggers a
    retry, and after 3 attempts, the hard_fail_node path."""


class ChangeControlValidationError(Exception):
    """Raised when the Change Control Clerk's structured-output call returns
    nothing tenacity can hand back as a valid `PendingChangePayload` --
    triggers a retry, and after 3 attempts, a terminal failure output."""


class WorkerValidationError(Exception):
    """Token Loop Breaker for the Tri-Framework specialists (PMP / Agile /
    Governance): raised when one of their structured-output calls returns
    nothing tenacity can hand back as a valid payload -- triggers a retry,
    and after 3 attempts, a terminal failure output for that turn.

    One shared exception class (not `PMPValidationError` /
    `AgileValidationError` / `GovernanceValidationError`) since all three
    workers make the same shaped call against a different payload type --
    the message carries `worker_name` for whichever one actually failed.
    """


def _render_prompt(*, user_name: str, channel_type: str, vague_turns: int) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{user_name}", user_name)
        .replace("{channel_type}", channel_type)
        .replace("{vague_turns}", str(vague_turns))
    )


def _render_change_control_prompt(*, user_request: str) -> str:
    template = _CHANGE_CONTROL_PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{user_request}", user_request)


def _render_worker_prompt(prompt_path: Path, *, user_message: str, extracted_entities: Optional[dict]) -> str:
    """Shared renderer for the three Tri-Framework specialist prompts
    (`pmp_worker.md` / `agile_worker.md` / `governance_worker.md`): all use
    the same two `# CONTEXT` placeholders. This is the first real consumer
    of `TriageRouterDecision.extracted_entities` -- defined in Phase 2, unread
    until now.
    """
    template = prompt_path.read_text(encoding="utf-8")
    entities_text = json.dumps(extracted_entities) if extracted_entities else "None provided"
    return template.replace("{user_message}", user_message).replace("{extracted_entities}", entities_text)


@retry(stop=stop_after_attempt(3), reraise=True)
async def _get_routing_decision(chat_agent: Agent, prompt: str, user_message: str) -> TriageRouterDecision:
    """The Token Loop Breaker (06-maf-teams-interface-guardrails.mdc):
    max 3 schema self-correction attempts before hard fail. `reraise=True`
    surfaces the final `RouterValidationError` to the caller instead of
    tenacity's own `RetryError`, so `RouterNode.route` can route it cleanly
    to `hard_fail_node`.
    """
    full_message = f"{prompt}\n\n# INCOMING MESSAGE\n{user_message}"
    response = await chat_agent.run(full_message, options={"response_format": TriageRouterDecision})
    if response.value is None:
        raise RouterValidationError("Router did not return output matching the TriageRouterDecision schema.")
    return response.value


@retry(stop=stop_after_attempt(3), reraise=True)
async def _get_pending_change_payload(chat_agent: Agent, prompt: str) -> PendingChangePayload:
    """Same Token Loop Breaker pattern as `_get_routing_decision`, applied to
    the Change Control Clerk's own structured-output call."""
    response = await chat_agent.run(prompt, options={"response_format": PendingChangePayload})
    if response.value is None:
        raise ChangeControlValidationError(
            "Change Control Clerk did not return output matching the PendingChangePayload schema."
        )
    return response.value


_WorkerPayloadT = TypeVar("_WorkerPayloadT", bound=BaseModel)


@retry(stop=stop_after_attempt(3), reraise=True)
async def _get_worker_payload(
    chat_agent: Agent,
    prompt: str,
    payload_type: type[_WorkerPayloadT],
    *,
    worker_name: str,
) -> _WorkerPayloadT:
    """Same Token Loop Breaker pattern as `_get_routing_decision` /
    `_get_pending_change_payload`, generalized across the three
    Tri-Framework specialists' payload types."""
    response = await chat_agent.run(prompt, options={"response_format": payload_type})
    if response.value is None:
        raise WorkerValidationError(f"{worker_name} did not return output matching the {payload_type.__name__} schema.")
    return response.value


# =============================================================================
# Requirement 3 + 4: the Router Node -- structured routing + Friction Breaker
# =============================================================================


class RouterNode(Executor):
    """The Supervisor. Calls Azure OpenAI with `prompts/router_node.md` as the
    system prompt, constrained to the `TriageRouterDecision` JSON schema.

    The Friction Breaker itself (requirement 4: force `escalation_node` when
    `vague_turns >= 2`, regardless of what the LLM decided) is NOT applied
    here -- it is applied as a routing *edge* condition in `build_app_graph`,
    exactly as the requirement specifies ("Implement the Friction Breaker in
    the routing edge"). This node's only job is to update the counter from
    `TriageRouterDecision.update_vague_turns` and forward the result.
    """

    def __init__(self, chat_agent: Agent, *, id: str = "router_node") -> None:
        super().__init__(id=id)
        self._chat_agent = chat_agent

    @handler
    async def route(self, state: PMOState, ctx: WorkflowContext[RoutedMessage]) -> None:
        user_message = state.message_history[-1].get("content", "") if state.message_history else ""
        prompt = _render_prompt(
            user_name=state.user_id,
            channel_type="teams",
            vague_turns=state.vague_turns,
        )

        try:
            decision = await _get_routing_decision(self._chat_agent, prompt, user_message)
        except Exception as exc:  # noqa: BLE001 - Token Loop Breaker exhausted; route, don't crash the graph
            await ctx.send_message(RoutedMessage(state=state, failed=True, error=str(exc)))
            return

        new_vague_turns = state.vague_turns + 1 if decision.update_vague_turns else 0
        updated_state = state.model_copy(update={"vague_turns": new_vague_turns})

        await ctx.send_message(RoutedMessage(state=updated_state, decision=decision))


def router_node(chat_agent: Agent, *, id: str = "router_node") -> RouterNode:
    """Factory for the Router Node executor (requirement 3)."""
    return RouterNode(chat_agent, id=id)


# =============================================================================
# Phase 3: Change Control Clerk -- the only node with baseline-write authority
# (it never actually writes; see the IMMUTABLE RULE in change_control_clerk.md)
# =============================================================================


class ChangeControlOutput(BaseModel):
    """`change_control_clerk`'s output: a drafted, unauthorized baseline-change
    proposal, on its way to the PM Veto Interrupt."""

    state: PMOState
    pending_change: PendingChangePayload
    message: str


class BaselineCommitInput(BaseModel):
    """What `suspend_for_veto_node` hands to `baseline_commit_node` once the
    PM's decision has come back and been applied to `state.pm_veto_decision`."""

    state: PMOState
    pending_change: PendingChangePayload


class PendingVetoRequest(BaseModel):
    """Returned by `run_turn` when a turn pauses at `suspend_for_veto_node`.

    Carries everything an external system (a Teams bot handler, or today,
    a human operator driving `simulate_teams_webhook.py`) needs to post the
    Adaptive Card and, later, resume the paused workflow.
    """

    checkpoint_id: str
    request_id: str
    card: dict


class ChangeControlClerk(Executor):
    """Drafts baseline-change proposals from `prompts/change_control_clerk.md`,
    constrained to the `PendingChangePayload` JSON schema. It cannot authorize
    its own proposal -- its only path forward is `suspend_for_veto_node`.
    """

    def __init__(self, chat_agent: Agent, *, id: str = "change_control_clerk") -> None:
        super().__init__(id=id)
        self._chat_agent = chat_agent

    @handler
    async def draft_change(self, message: RoutedMessage, ctx: WorkflowContext[ChangeControlOutput, dict]) -> None:
        user_request = (
            message.state.message_history[-1].get("content", "") if message.state.message_history else ""
        )
        prompt = _render_change_control_prompt(user_request=user_request)

        try:
            payload = await _get_pending_change_payload(self._chat_agent, prompt)
        except Exception as exc:  # noqa: BLE001 - Token Loop Breaker exhausted; terminate, don't crash the graph
            await ctx.yield_output(
                {
                    "worker": self.id,
                    "project_id": message.state.project_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            return

        updated_state = message.state.model_copy(update={"requires_pm_veto": True, "pending_change": payload})
        await ctx.send_message(
            ChangeControlOutput(
                state=updated_state,
                pending_change=payload,
                message=(
                    "I have drafted this baseline change and submitted it to the "
                    "Project Manager for approval."
                ),
            )
        )


# =============================================================================
# Phase 3: PM Veto Interrupt -- MAF's native human-in-the-loop pause/resume
# =============================================================================


class SuspendForVetoNode(Executor):
    """The PM Veto Interrupt. Pauses the graph via MAF's native human-in-the-loop
    mechanism (`ctx.request_info`) rather than a bespoke polling loop: the
    workflow run returns to its caller in `IDLE_WITH_PENDING_REQUESTS` and,
    because `build_app_graph` configures `checkpoint_storage`, a checkpoint is
    written to disk automatically at the end of the superstep. Resume happens
    out of process, whenever the Teams Action.Submit webhook (simulated by
    `simulate_teams_webhook.py`) calls `resume_after_veto`.

    Uses `response_type=str`, not `Literal["approved", "rejected"]`: the
    installed agent_framework's request/response type matcher calls
    `isinstance()` on the response type, which raises `TypeError` for
    `typing.Literal`. The two allowed values are validated by hand below
    instead, defaulting fail-closed (PRINCE2: no ambiguous baseline writes).
    """

    def __init__(self, *, id: str = "suspend_for_veto_node") -> None:
        super().__init__(id=id)

    @handler
    async def suspend(self, message: ChangeControlOutput, ctx: WorkflowContext) -> None:
        await ctx.request_info(
            request_data=message,
            response_type=str,
            request_id=message.pending_change.change_id,
        )

    @response_handler
    async def on_veto_decision(
        self,
        original_request: ChangeControlOutput,
        response: str,
        ctx: WorkflowContext[BaselineCommitInput],
    ) -> None:
        if response not in ("approved", "rejected"):
            logger.warning(
                "suspend_for_veto_node received an unrecognized pm_veto_decision %r for change_id=%s; "
                "defaulting to 'rejected' (fail-closed).",
                response,
                original_request.pending_change.change_id,
            )
        decision: Literal["approved", "rejected"] = response if response == "approved" else "rejected"

        updated_state = original_request.state.model_copy(update={"pm_veto_decision": decision})
        await ctx.send_message(
            BaselineCommitInput(state=updated_state, pending_change=original_request.pending_change)
        )


# =============================================================================
# Phase 3: baseline_commit_node -- runs after the graph resumes
# =============================================================================


class BaselineCommitNode(Executor):
    """Runs after the graph resumes from the PM Veto Interrupt. Branches on
    `state.pm_veto_decision` (set by `SuspendForVetoNode.on_veto_decision`)."""

    def __init__(self, *, id: str = "baseline_commit_node") -> None:
        super().__init__(id=id)

    @handler
    async def commit(self, message: BaselineCommitInput, ctx: WorkflowContext[Never, dict]) -> None:
        cleared_state = message.state.model_copy(
            update={"requires_pm_veto": False, "pending_change": None, "pm_veto_decision": None}
        )

        if message.state.pm_veto_decision == "approved":
            try:
                committed = apply_baseline_change(
                    target_table=message.pending_change.target_table,
                    record_id=message.pending_change.record_id,
                    proposed_values=message.pending_change.proposed_values,
                    project_id=cleared_state.project_id,
                )
            except BaselineChangeRejectedError as exc:
                # Fail closed: an allow-list violation, an empty
                # proposed_values, or a record_id that doesn't match this
                # project must never look like a silent no-op success.
                logger.error("baseline_commit_node: apply_baseline_change rejected the change: %s", exc)
                await ctx.yield_output(
                    {
                        "worker": self.id,
                        "project_id": cleared_state.project_id,
                        "status": "failed",
                        "error": str(exc),
                        "message": (
                            "The Project Manager approved the change, but the database write was "
                            "rejected. No change was made."
                        ),
                    }
                )
                return

            await ctx.yield_output(
                {
                    "worker": self.id,
                    "project_id": cleared_state.project_id,
                    "status": "committed",
                    "committed_change": committed,
                    "message": "The Project Manager approved the change. It has been committed to the baseline.",
                }
            )
            return

        print("Change Rejected")
        await ctx.yield_output(
            {
                "worker": self.id,
                "project_id": cleared_state.project_id,
                "status": "rejected",
                "message": "The Project Manager rejected the proposed baseline change. No write was made.",
            }
        )


# =============================================================================
# Phase 6: Database Writeback -- StateWritebackNode + PRINCE2 Exception
# Interrupt (SuspendForExceptionNode -> ExceptionCommitNode). Strictly
# acyclic: StateWritebackNode is visited exactly once per turn; the
# exception path hands off to ExceptionCommitNode rather than looping back.
# =============================================================================


class WorkerTurnOutput(BaseModel):
    """What `pmp_worker` / `agile_worker` / `governance_worker` now send to
    `state_writeback_node` instead of terminally yielding. Carries the exact
    same output dict each worker already builds (`worker`, `project_id`,
    `status`, `payload`, `reply`), plus the state it just mutated.
    """

    state: PMOState
    worker_output: dict


class ExceptionInterruptOutput(BaseModel):
    """`state_writeback_node`'s output when it detects an unresolved PRINCE2
    exception: on its way to the Exception Interrupt, analogous to
    `ChangeControlOutput` on its way to the PM Veto Interrupt.

    `exception_id` is minted here (`RiskEscalationPayload` has no ID field of
    its own) and doubles as both `ctx.request_info`'s `request_id` and the
    Adaptive Card's Action.Submit correlator (`ui/exception_card.json`).
    """

    state: PMOState
    worker_output: dict
    exception_id: str


class ExceptionCommitInput(BaseModel):
    """What `suspend_for_exception_node` hands to `exception_commit_node`
    once the PM's decision has come back and been applied to
    `state.exception_decision`."""

    state: PMOState
    worker_output: dict


class PendingExceptionRequest(BaseModel):
    """Returned by `run_turn` when a turn pauses at `suspend_for_exception_node`.

    Same shape as `PendingVetoRequest` -- everything an external system (or,
    today, `simulate_exception_webhook.py`) needs to post the Adaptive Card
    and resume the paused workflow.
    """

    checkpoint_id: str
    request_id: str
    card: dict


class StateWritebackNode(Executor):
    """Runs exactly once per turn, immediately after whichever specialist
    worker ran. Commits `latest_task_progress` / `latest_blocker` outright;
    for `latest_risk_escalation`, either commits it directly (no PRINCE2
    exception) or hands off to `suspend_for_exception_node` (exception
    triggered) -- never both, and never revisited afterward.
    """

    def __init__(self, *, id: str = "state_writeback_node") -> None:
        super().__init__(id=id)

    @handler
    async def writeback(self, message: WorkerTurnOutput, ctx: WorkflowContext[ExceptionInterruptOutput, dict]) -> None:
        state = message.state
        risk = state.latest_risk_escalation

        if risk is not None and risk.prince2_exception_triggered:
            await ctx.send_message(
                ExceptionInterruptOutput(
                    state=state,
                    worker_output=message.worker_output,
                    exception_id=str(uuid4()),
                )
            )
            return

        source_agent_key = message.worker_output.get("worker", self.id)

        committed: dict[str, bool] = {}
        if state.latest_task_progress is not None:
            committed["task_progress"] = commit_task_progress(
                state.project_id, source_agent_key, state.latest_task_progress.model_dump()
            )
        if state.latest_blocker is not None:
            committed["blocker"] = commit_blocker(
                state.project_id, source_agent_key, state.latest_blocker.model_dump()
            )
        if risk is not None:  # present but not exception-triggered, per the guard above
            committed["risk_escalation"] = commit_risk_escalation(
                state.project_id, source_agent_key, risk.model_dump()
            )

        cleared_state = state.model_copy(
            update={"latest_task_progress": None, "latest_blocker": None, "latest_risk_escalation": None}
        )
        await ctx.yield_output(
            {
                **message.worker_output,
                "project_id": cleared_state.project_id,
                "status": "committed",
                "committed": committed,
            }
        )


class SuspendForExceptionNode(Executor):
    """The PRINCE2 Exception Interrupt. Structurally identical to
    `SuspendForVetoNode`: pauses the graph via `ctx.request_info`, a
    checkpoint is written to disk, and resume happens out of process via
    `simulate_exception_webhook.py` calling `resume_after_exception`.

    Same `response_type=str` + hand-validated `Literal` workaround as
    `SuspendForVetoNode` (`isinstance()` can't handle `typing.Literal` in the
    installed `agent_framework`). Fail-closed default flips polarity from
    the Veto flow: an unrecognized response defaults to `"escalate_to_board"`
    (more scrutiny), not `"acknowledge"` (less).
    """

    def __init__(self, *, id: str = "suspend_for_exception_node") -> None:
        super().__init__(id=id)

    @handler
    async def suspend(self, message: ExceptionInterruptOutput, ctx: WorkflowContext) -> None:
        await ctx.request_info(request_data=message, response_type=str, request_id=message.exception_id)

    @response_handler
    async def on_exception_decision(
        self,
        original_request: ExceptionInterruptOutput,
        response: str,
        ctx: WorkflowContext[ExceptionCommitInput],
    ) -> None:
        if response not in ("acknowledge", "escalate_to_board"):
            logger.warning(
                "suspend_for_exception_node received an unrecognized exception_decision %r for exception_id=%s; "
                "defaulting to 'escalate_to_board' (fail-closed).",
                response,
                original_request.exception_id,
            )
        decision: Literal["acknowledge", "escalate_to_board"] = (
            response if response in ("acknowledge", "escalate_to_board") else "escalate_to_board"
        )

        updated_state = original_request.state.model_copy(update={"exception_decision": decision})
        await ctx.send_message(
            ExceptionCommitInput(state=updated_state, worker_output=original_request.worker_output)
        )


class ExceptionCommitNode(Executor):
    """Runs after the graph resumes from the Exception Interrupt. Finalizes
    the risk commit, clears state, and yields the final turn output --
    mirroring `BaselineCommitNode`'s role in the PM Veto chain."""

    def __init__(self, *, id: str = "exception_commit_node") -> None:
        super().__init__(id=id)

    @handler
    async def commit(self, message: ExceptionCommitInput, ctx: WorkflowContext[Never, dict]) -> None:
        state = message.state
        risk = state.latest_risk_escalation
        if risk is not None:
            source_agent_key = message.worker_output.get("worker", self.id)
            commit_risk_escalation(state.project_id, source_agent_key, risk.model_dump())

        cleared_state = state.model_copy(update={"latest_risk_escalation": None, "exception_decision": None})

        output = {
            **message.worker_output,
            "project_id": cleared_state.project_id,
            "status": "committed",
            "committed": {"risk_escalation": True},
        }
        if state.exception_decision == "escalate_to_board":
            output["reply"] = output.get("reply", "") + " This has been escalated to the Board for review."
        await ctx.yield_output(output)


# =============================================================================
# Requirement 6 (Phase 5): Tri-Framework Specialist Nodes
# =============================================================================


def _format_pmp_reply(payload: TaskProgressPayload) -> str:
    """Deterministic "Loose on Dialogue, Strict on State" reply -- built from
    the strict payload's own fields rather than a second LLM call, so the
    confirmation text can never drift from what was actually logged."""
    critical_path_note = " This task is on the critical path." if payload.is_critical_path else ""
    return (
        f"Logged: {payload.task_id} is {payload.percent_complete}% complete "
        f"({payload.actual_hours_spent}h spent).{critical_path_note} {payload.status_summary}"
    )


def _format_agile_reply(payload: BlockerPayload) -> str:
    help_note = " I'll pull in another team to help." if payload.requires_cross_team_help else ""
    return (
        f"Got it -- {payload.task_id} is blocked: {payload.blocker_description}.{help_note} "
        f"Next step: {payload.agile_action_item}"
    )


def _format_governance_reply(payload: RiskEscalationPayload) -> str:
    exception_note = (
        " This breaches stage tolerance -- flagging for PM review."
        if payload.prince2_exception_triggered
        else " This is within tolerance for now."
    )
    return (
        f"Logged a {payload.risk_category} risk (severity {payload.severity}/5): "
        f"{payload.description}.{exception_note}"
    )


class PMPWorker(Executor):
    """PMP Schedule Specialist -- critical path, task durations, hours, and
    percent complete. Calls Azure OpenAI with `prompts/pmp_worker.md` and
    `response_format=TaskProgressPayload`, then mutates
    `PMOState.latest_task_progress`.
    """

    def __init__(self, chat_agent: Agent, *, id: str = "pmp_worker") -> None:
        super().__init__(id=id)
        self._chat_agent = chat_agent

    @handler
    async def handle(self, message: RoutedMessage, ctx: WorkflowContext[WorkerTurnOutput, dict]) -> None:
        user_message = message.state.message_history[-1].get("content", "") if message.state.message_history else ""
        prompt = _render_worker_prompt(
            _PMP_PROMPT_PATH,
            user_message=user_message,
            extracted_entities=message.decision.extracted_entities if message.decision else None,
        )
        try:
            payload = await _get_worker_payload(self._chat_agent, prompt, TaskProgressPayload, worker_name="PMP Worker")
        except Exception as exc:
            await ctx.yield_output(
                {"worker": self.id, "project_id": message.state.project_id, "status": "failed", "error": str(exc)}
            )
            return

        updated_state = message.state.model_copy(update={"latest_task_progress": payload})
        # Phase 6: no longer terminal -- state_writeback_node commits this
        # payload to the DB and clears it before the turn actually ends.
        await ctx.send_message(
            WorkerTurnOutput(
                state=updated_state,
                worker_output={
                    "worker": self.id,
                    "project_id": updated_state.project_id,
                    "status": "updated",
                    "payload": payload,
                    "reply": _format_pmp_reply(payload),
                },
            )
        )


class AgileWorker(Executor):
    """Agile Scrum Facilitator -- blockers, cross-team help, and the next
    concrete action item. Calls Azure OpenAI with `prompts/agile_worker.md`
    and `response_format=BlockerPayload`, then mutates
    `PMOState.latest_blocker`.
    """

    def __init__(self, chat_agent: Agent, *, id: str = "agile_worker") -> None:
        super().__init__(id=id)
        self._chat_agent = chat_agent

    @handler
    async def handle(self, message: RoutedMessage, ctx: WorkflowContext[WorkerTurnOutput, dict]) -> None:
        user_message = message.state.message_history[-1].get("content", "") if message.state.message_history else ""
        prompt = _render_worker_prompt(
            _AGILE_PROMPT_PATH,
            user_message=user_message,
            extracted_entities=message.decision.extracted_entities if message.decision else None,
        )
        try:
            payload = await _get_worker_payload(self._chat_agent, prompt, BlockerPayload, worker_name="Agile Worker")
        except Exception as exc:
            await ctx.yield_output(
                {"worker": self.id, "project_id": message.state.project_id, "status": "failed", "error": str(exc)}
            )
            return

        updated_state = message.state.model_copy(update={"latest_blocker": payload})
        # Phase 6: no longer terminal -- state_writeback_node commits this
        # payload to the DB and clears it before the turn actually ends.
        await ctx.send_message(
            WorkerTurnOutput(
                state=updated_state,
                worker_output={
                    "worker": self.id,
                    "project_id": updated_state.project_id,
                    "status": "updated",
                    "payload": payload,
                    "reply": _format_agile_reply(payload),
                },
            )
        )


class GovernanceWorker(Executor):
    """PRINCE2 Governance Specialist -- risk category, severity, and stage
    tolerance checks. Calls Azure OpenAI with `prompts/governance_worker.md`
    and `response_format=RiskEscalationPayload`, then mutates
    `PMOState.latest_risk_escalation`.

    Only *flags* `prince2_exception_triggered`; it is `state_writeback_node`
    (Phase 6) that decides whether that flag actually triggers the PRINCE2
    Exception Interrupt (`suspend_for_exception_node`).
    """

    def __init__(self, chat_agent: Agent, *, id: str = "governance_worker") -> None:
        super().__init__(id=id)
        self._chat_agent = chat_agent

    @handler
    async def handle(self, message: RoutedMessage, ctx: WorkflowContext[WorkerTurnOutput, dict]) -> None:
        user_message = message.state.message_history[-1].get("content", "") if message.state.message_history else ""
        prompt = _render_worker_prompt(
            _GOVERNANCE_PROMPT_PATH,
            user_message=user_message,
            extracted_entities=message.decision.extracted_entities if message.decision else None,
        )
        try:
            payload = await _get_worker_payload(
                self._chat_agent, prompt, RiskEscalationPayload, worker_name="Governance Worker"
            )
        except Exception as exc:
            await ctx.yield_output(
                {"worker": self.id, "project_id": message.state.project_id, "status": "failed", "error": str(exc)}
            )
            return

        updated_state = message.state.model_copy(update={"latest_risk_escalation": payload})
        # Phase 6: no longer terminal -- state_writeback_node either commits
        # this payload directly or, if it breaches PRINCE2 tolerance, routes
        # to the Exception Interrupt before committing.
        await ctx.send_message(
            WorkerTurnOutput(
                state=updated_state,
                worker_output={
                    "worker": self.id,
                    "project_id": updated_state.project_id,
                    "status": "updated",
                    "payload": payload,
                    "reply": _format_governance_reply(payload),
                },
            )
        )


def pmp_worker(chat_agent: Agent, *, id: str = "pmp_worker") -> PMPWorker:
    """PMP Schedule Worker -- critical path, task durations, dependencies."""
    return PMPWorker(chat_agent, id=id)


def agile_worker(chat_agent: Agent, *, id: str = "agile_worker") -> AgileWorker:
    """Agile Scrum Worker -- daily blockers, task progress, team collaboration."""
    return AgileWorker(chat_agent, id=id)


def governance_worker(chat_agent: Agent, *, id: str = "governance_worker") -> GovernanceWorker:
    """PRINCE2 Governance Worker -- risk escalation, budget tolerances, exceptions."""
    return GovernanceWorker(chat_agent, id=id)


# =============================================================================
# Requirement 6: remaining placeholder worker nodes (Phase 4)
# =============================================================================


class WorkerExecutor(Executor):
    """Placeholder for a specialist worker. A future phase replaces `handle`
    with real logic; for now it just yields a stub acknowledgement so the
    graph is structurally runnable end-to-end.
    """

    @handler
    async def handle(self, message: RoutedMessage, ctx: WorkflowContext[Never, dict]) -> None:
        await ctx.yield_output(
            {
                "worker": self.id,
                "project_id": message.state.project_id,
                "next_node": message.decision.next_node if message.decision else None,
                "reasoning": message.decision.reasoning if message.decision else message.error,
                "requires_pm_veto": message.state.requires_pm_veto,
                "status": "not_implemented",
            }
        )


def escalation_node(*, id: str = "escalation_node") -> WorkerExecutor:
    """Friction Breaker target: hands the conversation to the human PM. (Phase 4)"""
    return WorkerExecutor(id=id)


def hard_fail_node(*, id: str = "hard_fail_node") -> WorkerExecutor:
    """Token Loop Breaker target: 3 failed schema self-corrections. (Phase 4)"""
    return WorkerExecutor(id=id)


def end_conversation(*, id: str = "end_conversation") -> WorkerExecutor:
    """Default terminal node when no worker is relevant to this turn."""
    return WorkerExecutor(id=id)


# =============================================================================
# Graph assembly
# =============================================================================


def build_app_graph(
    chat_agent: Agent,
    *,
    change_control_chat_agent: Optional[Agent] = None,
    pmp_chat_agent: Optional[Agent] = None,
    agile_chat_agent: Optional[Agent] = None,
    governance_chat_agent: Optional[Agent] = None,
    checkpoint_storage: Optional[CheckpointStorage] = None,
):
    """Wire the Supervisor-Worker topology described in Phase 2, plus Phase 3's
    Change Control Clerk / PM Veto Interrupt / baseline commit chain.

    Router -> switch-case edge group, evaluated in order (first match wins):
        1. Token Loop Breaker failure -> hard_fail_node
        2. Friction Breaker (vague_turns >= 2) -> escalation_node, overriding
           whatever the LLM decided (requirement 4)
        3. the LLM's own `TriageRouterDecision.next_node`
        4. default -> end_conversation

    change_control_clerk -> suspend_for_veto_node -> baseline_commit_node is a
    fixed chain (not a switch-case): the Change Control Clerk always drafts a
    proposal, that proposal is always vetoed by a human PM, and the outcome is
    always committed or rejected.

    `checkpoint_storage` defaults to a `FileCheckpointStorage` under
    `DEFAULT_CHECKPOINT_DIR` -- file-based (not in-memory) specifically so a
    *second, independent process* (`simulate_teams_webhook.py`, and later a
    real Teams webhook handler) can resume a paused run.
    """
    gateway = GatewayMiddleware()
    router = router_node(chat_agent)

    pmp = pmp_worker(pmp_chat_agent or chat_agent)
    agile = agile_worker(agile_chat_agent or chat_agent)
    governance = governance_worker(governance_chat_agent or chat_agent)
    change_control = ChangeControlClerk(change_control_chat_agent or chat_agent)
    suspend_for_veto = SuspendForVetoNode()
    baseline_commit = BaselineCommitNode()
    state_writeback = StateWritebackNode()
    suspend_for_exception = SuspendForExceptionNode()
    exception_commit = ExceptionCommitNode()
    escalation = escalation_node()
    hard_fail = hard_fail_node()
    end_conv = end_conversation()

    builder = WorkflowBuilder(
        start_executor=gateway,
        name=WORKFLOW_NAME,
        checkpoint_storage=checkpoint_storage or default_checkpoint_storage(),
    )
    builder.add_edge(gateway, router)
    builder.add_switch_case_edge_group(
        router,
        [
            Case(condition=lambda msg: msg.failed, target=hard_fail),
            # Friction Breaker (requirement 4) OR the LLM independently chose
            # escalation_node itself -- both land here. Each switch-case target
            # must be unique, so this single Case covers both triggers; the
            # `vague_turns >= 2` half is evaluated first and overrides whatever
            # `next_node` the LLM picked, exactly as required.
            Case(
                condition=lambda msg: msg.state.vague_turns >= 2
                or (msg.decision is not None and msg.decision.next_node == "escalation_node"),
                target=escalation,
            ),
            Case(condition=lambda msg: msg.decision.next_node == "pmp_worker", target=pmp),
            Case(condition=lambda msg: msg.decision.next_node == "agile_worker", target=agile),
            Case(condition=lambda msg: msg.decision.next_node == "governance_worker", target=governance),
            Case(condition=lambda msg: msg.decision.next_node == "change_control_clerk", target=change_control),
            Default(target=end_conv),
        ],
    )
    builder.add_edge(change_control, suspend_for_veto)
    builder.add_edge(suspend_for_veto, baseline_commit)

    # Phase 6: Database Writeback + PRINCE2 Exception Interrupt. Strictly
    # acyclic -- state_writeback_node is visited exactly once per turn; the
    # exception path hands off to exception_commit_node rather than looping
    # back (see the Phase 6 plan's approved modification).
    builder.add_edge(pmp, state_writeback)
    builder.add_edge(agile, state_writeback)
    builder.add_edge(governance, state_writeback)
    builder.add_edge(state_writeback, suspend_for_exception)
    builder.add_edge(suspend_for_exception, exception_commit)
    return builder.build()


async def run_turn(
    workflow: Any,
    state: PMOState,
    *,
    checkpoint_storage: Optional[CheckpointStorage] = None,
) -> Any:
    """Run one conversational turn.

    Returns whatever the graph produced:
    - a `HardHaltMessage` from the Gateway,
    - a worker's stub/real output dict,
    - when `change_control_clerk` drafted a proposal and the graph paused at
      `suspend_for_veto_node`, a `PendingVetoRequest` with the checkpoint to
      resume later (via `resume_after_veto`) and the Adaptive Card to post,
    - or, when `state_writeback_node` detected a PRINCE2 exception and the
      graph paused at `suspend_for_exception_node`, a `PendingExceptionRequest`
      with the checkpoint to resume later (via `resume_after_exception`) and
      the Adaptive Card to post.

    `checkpoint_storage` should be the same instance (or point at the same
    `storage_path`) passed to `build_app_graph`, so the paused checkpoint can
    be looked up by `WORKFLOW_NAME`.
    """
    events = await workflow.run(state)

    if events.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
        storage = checkpoint_storage or default_checkpoint_storage()
        checkpoint = await storage.get_latest(workflow_name=WORKFLOW_NAME)
        request_event = events.get_request_info_events()[-1]
        pending_data = request_event.data

        if isinstance(pending_data, ChangeControlOutput):
            return PendingVetoRequest(
                checkpoint_id=checkpoint.checkpoint_id if checkpoint else "",
                request_id=request_event.request_id,
                card=render_pm_veto_card(pending_data.pending_change),
            )
        if isinstance(pending_data, ExceptionInterruptOutput):
            return PendingExceptionRequest(
                checkpoint_id=checkpoint.checkpoint_id if checkpoint else "",
                request_id=request_event.request_id,
                card=render_exception_card(pending_data.exception_id, pending_data.state.latest_risk_escalation),
            )
        raise RuntimeError(f"run_turn: unhandled pending request-info payload type: {type(pending_data)!r}")

    outputs = events.get_outputs()
    return outputs[0] if outputs else None


async def resume_after_veto(
    workflow: Any,
    checkpoint_id: str,
    request_id: str,
    decision: Literal["approved", "rejected"],
) -> Any:
    """Resume a workflow paused at `suspend_for_veto_node`.

    This is the exact call a real Teams Action.Submit webhook handler would
    make once it has parsed the card's `data.change_id` (used as the
    `request_id`, see `SuspendForVetoNode.suspend`) and `data.decision` out of
    the incoming Activity. `simulate_teams_webhook.py` calls this directly to
    prove the pause/resume flow without standing up a real webhook.
    """
    events = await workflow.run(checkpoint_id=checkpoint_id, responses={request_id: decision})
    outputs = events.get_outputs()
    return outputs[0] if outputs else None


async def resume_after_exception(
    workflow: Any,
    checkpoint_id: str,
    request_id: str,
    decision: Literal["acknowledge", "escalate_to_board"],
) -> Any:
    """Resume a workflow paused at `suspend_for_exception_node`.

    This is the exact call a real Teams Action.Submit webhook handler would
    make once it has parsed the card's `data.exception_id` (used as the
    `request_id`, see `SuspendForExceptionNode.suspend`) and `data.decision`
    out of the incoming Activity. `simulate_exception_webhook.py` calls this
    directly to prove the pause/resume flow without standing up a real webhook.
    """
    events = await workflow.run(checkpoint_id=checkpoint_id, responses={request_id: decision})
    outputs = events.get_outputs()
    return outputs[0] if outputs else None


def build_default_router_chat_agent(*, temperature: float = 0.30) -> Agent:
    """Build the Router's `Agent` from the `AZURE_OPENAI_*` env vars already
    used elsewhere in this project (see `.env` and `core/workflow.py`).
    Slightly warmer temperature than the delta-dispatch Router
    (`core.workflow.build_default_chat_agent`) to support "Loose on Dialogue."
    """
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    return Agent(
        client=client,
        name="GIABORouterNode",
        default_options={"temperature": temperature},
    )


def build_default_change_control_chat_agent(*, temperature: float = 0.10) -> Agent:
    """Build the Change Control Clerk's `Agent`. Low temperature -- PRINCE2
    rigor, not conversational warmth (unlike the Router's `Agent`)."""
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    return Agent(
        client=client,
        name="GIABOChangeControlClerk",
        default_options={"temperature": temperature},
    )


def build_default_pmp_chat_agent(*, temperature: float = 0.15) -> Agent:
    """Build the PMP Worker's `Agent`. Low-ish temperature for schedule
    rigor -- not as strict as Governance, but not conversational either."""
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    return Agent(
        client=client,
        name="GIABOPMPWorker",
        default_options={"temperature": temperature},
    )


def build_default_agile_chat_agent(*, temperature: float = 0.35) -> Agent:
    """Build the Agile Worker's `Agent`. Warmer temperature -- servant-leader
    conversational tone, closer to the Router's than to Governance's."""
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    return Agent(
        client=client,
        name="GIABOAgileWorker",
        default_options={"temperature": temperature},
    )


def build_default_governance_chat_agent(*, temperature: float = 0.10) -> Agent:
    """Build the Governance Worker's `Agent`. Low temperature -- PRINCE2
    rigor, matching the Change Control Clerk's."""
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    return Agent(
        client=client,
        name="GIABOGovernanceWorker",
        default_options={"temperature": temperature},
    )
