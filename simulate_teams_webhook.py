"""Simulates an external Teams Action.Submit webhook resuming a paused
`suspend_for_veto_node` -- proves the PM Veto Interrupt survives across two
*independent process invocations*, backed by `FileCheckpointStorage` on disk
(not `InMemoryCheckpointStorage`, which would not survive this process exiting).

A real Teams webhook handler would receive the Adaptive Card's Action.Submit
Activity, pull `decision` and `change_id` out of its `value.action` payload
(`ui/pm_veto_card.json`'s `data.decision` / `data.change_id` -- the latter
doubles as the pending request's `request_id`, see
`app_graph.SuspendForVetoNode.suspend`), and call `resume_after_veto`. This
script does exactly that from the command line instead of an HTTP endpoint.

Usage:
    # Run a turn elsewhere first so change_control_clerk drafts a proposal
    # and the graph pauses at suspend_for_veto_node (writing a checkpoint to
    # DEFAULT_CHECKPOINT_DIR). Then:
    python simulate_teams_webhook.py --decision approved
    python simulate_teams_webhook.py --checkpoint-id <id> --decision rejected
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
    build_default_change_control_chat_agent,
    build_default_router_chat_agent,
    default_checkpoint_storage,
    resume_after_veto,
)


async def _find_pending_request_id(storage: FileCheckpointStorage, checkpoint_id: str) -> str:
    checkpoint = await storage.load(checkpoint_id)
    if not checkpoint.pending_request_info_events:
        raise RuntimeError(f"Checkpoint {checkpoint_id} has no pending request-info events to resume.")
    # This graph only ever has one pending request at a time (suspend_for_veto_node).
    return next(iter(checkpoint.pending_request_info_events))


async def main(checkpoint_id: Optional[str], decision: Literal["approved", "rejected"]) -> None:
    storage = default_checkpoint_storage()

    if checkpoint_id is None:
        latest = await storage.get_latest(workflow_name=WORKFLOW_NAME)
        if latest is None:
            raise RuntimeError(
                f"No checkpoints found under {DEFAULT_CHECKPOINT_DIR} for workflow "
                f"'{WORKFLOW_NAME}'. Run a turn through change_control_clerk first so "
                "it pauses at suspend_for_veto_node."
            )
        checkpoint_id = latest.checkpoint_id

    request_id = await _find_pending_request_id(storage, checkpoint_id)

    # Rebuild the *same graph shape* the paused process used -- required for
    # the checkpoint's saved executor states/messages to resolve correctly.
    # The Router's and Change Control Clerk's agents are never called again
    # on resume (only suspend_for_veto_node's already-registered response
    # handler runs), so this is safe even without live Azure credentials.
    workflow = build_app_graph(
        build_default_router_chat_agent(),
        change_control_chat_agent=build_default_change_control_chat_agent(),
        checkpoint_storage=storage,
    )

    print(f"[simulate_teams_webhook] Resuming checkpoint={checkpoint_id} request_id={request_id} decision={decision!r}")
    output = await resume_after_veto(workflow, checkpoint_id, request_id, decision)
    print("[simulate_teams_webhook] Workflow output after resume:")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Simulate a Teams Action.Submit webhook delivering a PM's "
            "pm_veto_decision to a paused GIABO PMO workflow."
        )
    )
    parser.add_argument(
        "--checkpoint-id",
        default=None,
        help="Checkpoint to resume. Defaults to the latest checkpoint for the graph's workflow name.",
    )
    parser.add_argument(
        "--decision",
        choices=["approved", "rejected"],
        default="approved",
        help="The simulated Action.Submit payload's pm_veto_decision.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.checkpoint_id, args.decision))
