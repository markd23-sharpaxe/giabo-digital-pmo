"""Phase 8: Microsoft Teams API Layer -- the Bot Framework `ActivityHandler`.

`app_graph.run_turn`/`resume_after_veto`/`resume_after_exception` take a full
`PMOState` (or a `checkpoint_id`/`request_id` pair) on every call and persist
nothing themselves -- the caller owns conversation continuity. This module is
that caller: it keeps two properties per Teams conversation in a
`botbuilder.core.ConversationState` (see `api/main.py` for the `MemoryStorage`
it's backed by):

    pmo_state          -- the running `PMOState` (as a dict), so
                           `message_history`/`vague_turns`/`billing_status`
                           survive across turns.
    pending_interrupt   -- a `PendingInterrupt` (as a dict) set whenever
                           `run_turn` pauses at `suspend_for_veto_node` /
                           `suspend_for_exception_node`, so the matching
                           Action.Submit can find the `checkpoint_id` to
                           resume -- nothing in the Adaptive Card payloads
                           themselves carries that (see `ui/pm_veto_card.json`
                           / `ui/exception_card.json`).
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from botbuilder.core import ActivityHandler, CardFactory, ConversationState, MessageFactory, TurnContext
from pydantic import BaseModel

from app_graph import (
    HardHaltMessage,
    PendingExceptionRequest,
    PendingVetoRequest,
    PMOState,
    resume_after_exception,
    resume_after_veto,
    run_turn,
)

logger = logging.getLogger(__name__)

_NO_REPLY_TEXT = "(No response text was produced for this turn.)"
_STALE_ACTION_TEXT = (
    "This action can no longer be processed -- it may already have been resolved, or this bot has "
    "restarted since the card was sent. Please ask for a fresh update."
)


class PendingInterrupt(BaseModel):
    """What `PMOBot` remembers per conversation while a turn is paused at
    `suspend_for_veto_node` / `suspend_for_exception_node`, so the matching
    Action.Submit (which only carries `decision` + `change_id`/`exception_id`,
    per `ui/pm_veto_card.json` / `ui/exception_card.json`) can be resumed.
    """

    kind: Literal["veto", "exception"]
    checkpoint_id: str
    request_id: str


def _extract_reply_text(result: dict) -> str:
    """`app_graph.py`'s worker/terminal nodes don't yet share one output key
    for user-facing text: `PMPWorker`/`AgileWorker`/`GovernanceWorker`/
    `StateWritebackNode` use `"reply"`; `BaselineCommitNode`/
    `ExceptionCommitNode`/`ChangeControlClerk` failures use `"message"`;
    `escalation_node`/`hard_fail_node`/`end_conversation` (still-unimplemented
    `WorkerExecutor` stubs, per their own docstrings) only carry `"reasoning"`.
    This tries all three, in that order, rather than papering over a crash.
    """
    for key in ("reply", "message", "reasoning"):
        value = result.get(key)
        if value:
            return str(value)
    return _NO_REPLY_TEXT


class PMOBot(ActivityHandler):
    """The GIABO Digital PMO Teams bot. One instance, shared across every
    conversation -- `self._workflow` is the single `app_graph.build_app_graph`
    result built once in `api/main.py`; per-conversation state lives in
    `conversation_state`, never on `self`.
    """

    def __init__(self, conversation_state: ConversationState, workflow: Any, checkpoint_storage: Any) -> None:
        super().__init__()
        self._conversation_state = conversation_state
        self._workflow = workflow
        self._checkpoint_storage = checkpoint_storage
        self._pmo_state_accessor = conversation_state.create_property("PmoState")
        self._pending_accessor = conversation_state.create_property("PendingInterrupt")

    async def on_turn(self, turn_context: TurnContext) -> None:
        await super().on_turn(turn_context)
        # Idiomatic Bot Framework pattern: persist whatever this turn's
        # handler wrote into either accessor, regardless of which branch ran.
        await self._conversation_state.save_changes(turn_context)

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity

        # Teams delivers Adaptive Card Action.Submit clicks as `message`
        # activities with a populated `value` (often alongside empty/absent
        # `text`) -- check this first.
        if activity.value:
            await self._handle_card_submission(turn_context, activity.value)
            return

        if not activity.text:
            return

        conversation_id = activity.conversation.id
        user_id = activity.from_property.id

        state = await self._load_pmo_state(turn_context, conversation_id, user_id)
        state.message_history.append({"role": "user", "content": activity.text})

        result = await run_turn(self._workflow, state, checkpoint_storage=self._checkpoint_storage)
        await self._send_result(turn_context, result, state)

    # -------------------------------------------------------------------
    # Normal chat
    # -------------------------------------------------------------------

    async def _load_pmo_state(self, turn_context: TurnContext, conversation_id: str, user_id: str) -> PMOState:
        state_dict = await self._pmo_state_accessor.get(turn_context, lambda: None)
        if state_dict:
            return PMOState(**state_dict)
        # First turn for this conversation -- `conversation.id` doubles as
        # `project_id` for now (no real tenant/project lookup against the
        # Phase 7 DB yet), and every new conversation starts on the trial gate.
        return PMOState(
            project_id=conversation_id,
            user_id=user_id,
            billing_status="active_trial",
        )

    async def _send_result(self, turn_context: TurnContext, result: Any, state: PMOState) -> None:
        if isinstance(result, PendingVetoRequest):
            await self._pending_accessor.set(
                turn_context,
                PendingInterrupt(
                    kind="veto", checkpoint_id=result.checkpoint_id, request_id=result.request_id
                ).model_dump(),
            )
            await turn_context.send_activity(MessageFactory.attachment(CardFactory.adaptive_card(result.card)))
            reply_text = "[Adaptive Card sent: PM Veto Authorization Required]"

        elif isinstance(result, PendingExceptionRequest):
            await self._pending_accessor.set(
                turn_context,
                PendingInterrupt(
                    kind="exception", checkpoint_id=result.checkpoint_id, request_id=result.request_id
                ).model_dump(),
            )
            await turn_context.send_activity(MessageFactory.attachment(CardFactory.adaptive_card(result.card)))
            reply_text = "[Adaptive Card sent: PRINCE2 Exception Raised]"

        elif isinstance(result, HardHaltMessage):
            reply_text = result.reason
            await turn_context.send_activity(reply_text)

        elif isinstance(result, dict):
            reply_text = _extract_reply_text(result)
            await turn_context.send_activity(reply_text)

        elif result is None:
            # Defensive: shouldn't happen in practice (every terminal node
            # yields/outputs something), but a turn producing nothing is not
            # an error worth surfacing to the Teams user.
            return

        else:
            reply_text = str(result)
            await turn_context.send_activity(reply_text)

        # `requires_pm_veto`/`pending_change`/`latest_*` are only ever
        # mutated on the graph's *internal* checkpointed copy of state (see
        # `SuspendForVetoNode`/`StateWritebackNode`), never on this bot-side
        # `state` -- so there's nothing to clear here even on the
        # Pending*Request branches above.
        state.message_history.append({"role": "assistant", "content": reply_text})
        await self._pmo_state_accessor.set(turn_context, state.model_dump())

    # -------------------------------------------------------------------
    # Adaptive Card Action.Submit
    # -------------------------------------------------------------------

    async def _handle_card_submission(self, turn_context: TurnContext, value: dict) -> None:
        action = value.get("action")

        if action == "pm_veto_decision":
            await self._resume_pending(
                turn_context,
                kind="veto",
                request_id_key="change_id",
                value=value,
                resume_fn=resume_after_veto,
            )
        elif action == "exception_decision":
            await self._resume_pending(
                turn_context,
                kind="exception",
                request_id_key="exception_id",
                value=value,
                resume_fn=resume_after_exception,
            )
        else:
            logger.warning("Unrecognized Adaptive Card action.value: %r", value)
            await turn_context.send_activity(f"Unrecognized card action: {action!r}.")

    async def _resume_pending(
        self,
        turn_context: TurnContext,
        *,
        kind: Literal["veto", "exception"],
        request_id_key: str,
        value: dict,
        resume_fn: Any,
    ) -> None:
        pending_dict = await self._pending_accessor.get(turn_context, lambda: None)
        pending: Optional[PendingInterrupt] = PendingInterrupt(**pending_dict) if pending_dict else None

        request_id = value.get(request_id_key)
        decision = value.get("decision", "")

        # Fail closed on a stale/duplicate/mismatched submission (e.g. a
        # double-click, or a card resurfaced after this bot restarted and
        # lost its MemoryStorage-backed pending_interrupt) rather than
        # silently resuming the wrong (or no longer pending) checkpoint.
        if pending is None or pending.kind != kind or pending.request_id != request_id:
            logger.warning(
                "Rejecting stale/mismatched %s Action.Submit: value=%r stored_pending=%r",
                kind,
                value,
                pending,
            )
            await turn_context.send_activity(_STALE_ACTION_TEXT)
            return

        # `resume_after_veto`/`resume_after_exception`'s underlying response
        # handlers (`SuspendForVetoNode.on_veto_decision` /
        # `SuspendForExceptionNode.on_exception_decision`) already fail
        # closed on an unrecognized `decision` string -- no extra validation
        # needed here.
        result = await resume_fn(self._workflow, pending.checkpoint_id, pending.request_id, decision)
        await self._pending_accessor.delete(turn_context)

        reply_text = _extract_reply_text(result) if isinstance(result, dict) else str(result)
        await turn_context.send_activity(reply_text)

        # The conversation's `pmo_state` (message_history etc.) is untouched
        # by a resume -- only append this exchange for continuity.
        state_dict = await self._pmo_state_accessor.get(turn_context, lambda: None)
        if state_dict:
            state = PMOState(**state_dict)
            state.message_history.append({"role": "assistant", "content": reply_text})
            await self._pmo_state_accessor.set(turn_context, state.model_dump())
