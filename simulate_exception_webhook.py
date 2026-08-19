"""Simulates an external Teams Action.Submit webhook resuming a paused
`suspend_for_exception_node` -- proves the PRINCE2 Exception Interrupt
survives across two *independent process invocations*, backed by
`FileCheckpointStorage` on disk (not `InMemoryCheckpointStorage`, which would
not survive this process exiting).

A real Teams webhook handler would receive the Adaptive Card's Action.Submit
Activity, pull `decision` and `exception_id` out of its `value.action`
payload (`ui/exception_card.json`'s `data.decision` / `data.exception_id` --
the latter doubles as the pending request's `request_id`, see
`app_graph.SuspendForExceptionNode.suspend`), and call
`resume_after_exception`. This script does exactly that from the command
line instead of an HTTP endpoint.

Usage:
    # Run a turn elsewhere first so governance_worker flags a
    # prince2_exception_triggered risk and the graph pauses at
    # suspend_for_exception_node (writing a checkpoint to
    # DEFAULT_CHECKPOINT_DIR). Then:
    python simulate_exception_webhook.py --decision acknowledge
    python simulate_exception_webhook.py --checkpoint-id <id> --decision escalate_to_board
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Literal, Optional

from agent_framework import FileCheckpointStorage

from app_graph import (
    DEFAULT_CHECKPOINT_DIR,
    WORKFLOW_NAME,
    build_app_graph,
    build_default_agile_chat_agent,
    build_default_governance_chat_agent,
    build_default_pmp_chat_agent,
    build_default_router_chat_agent,
    default_checkpoint_storage,
    resume_after_exception,
)


async def _find_pending_request_id(storage: FileCheckpointStorage, checkpoint_id: str) -> str:
    checkpoint = await storage.load(checkpoint_id)
    if not checkpoint.pending_request_info_events:
        raise RuntimeError(f"Checkpoint {checkpoint_id} has no pending request-info events to resume.")
    # Only one of suspend_for_veto_node / suspend_for_exception_node can ever
    # be paused at a time -- they sit on mutually exclusive switch-case
    # branches from the Router, so there is always exactly one pending
    # request per checkpoint regardless of which interrupt raised it.
    return next(iter(checkpoint.pending_request_info_events))


async def main(checkpoint_id: Optional[str], decision: Literal["acknowledge", "escalate_to_board"]) -> None:
    storage = default_checkpoint_storage()

    if checkpoint_id is None:
        latest = await storage.get_latest(workflow_name=WORKFLOW_NAME)
        if latest is None:
            raise RuntimeError(
                f"No checkpoints found under {DEFAULT_CHECKPOINT_DIR} for workflow "
                f"'{WORKFLOW_NAME}'. Run a turn through governance_worker first with a "
                "prince2_exception_triggered risk so it pauses at suspend_for_exception_node."
            )
        checkpoint_id = latest.checkpoint_id

    request_id = await _find_pending_request_id(storage, checkpoint_id)

    # Rebuild the *same graph shape* the paused process used -- required for
    # the checkpoint's saved executor states/messages to resolve correctly.
    # None of these agents are called again on resume (only
    # suspend_for_exception_node's already-registered response handler
    # runs), so this is safe even without live Azure credentials.
    workflow = build_app_graph(
        build_default_router_chat_agent(),
        pmp_chat_agent=build_default_pmp_chat_agent(),
        agile_chat_agent=build_default_agile_chat_agent(),
        governance_chat_agent=build_default_governance_chat_agent(),
        checkpoint_storage=storage,
    )

    print(
        f"[simulate_exception_webhook] Resuming checkpoint={checkpoint_id} "
        f"request_id={request_id} decision={decision!r}"
    )
    output = await resume_after_exception(workflow, checkpoint_id, request_id, decision)
    print("[simulate_exception_webhook] Workflow output after resume:")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Simulate a Teams Action.Submit webhook delivering a PM's "
            "exception_decision to a paused GIABO PMO workflow."
        )
    )
    parser.add_argument(
        "--checkpoint-id",
        default=None,
        help="Checkpoint to resume. Defaults to the latest checkpoint for the graph's workflow name.",
    )
    parser.add_argument(
        "--decision",
        choices=["acknowledge", "escalate_to_board"],
        default="acknowledge",
        help="The simulated Action.Submit payload's exception_decision.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.checkpoint_id, args.decision))
