"""Deterministic invariants for the Universal Blackboard Event Bus.

No Azure OpenAI. Proves Aim 1–3 gates that must fire even if an LLM disagrees.

    Aim 1: only change_control_clerk may publish BASELINE_SLIP_REQUESTED,
           and that payload cannot carry risk fields.
    Aim 2: proactive agents cannot draft/publish baseline events.
    Aim 3: EVENT_SUBSCRIPTIONS never wake the clerk; sibling follow-up
           does not resume a paused veto checkpoint.

Run:
    .venv/bin/python test_event_bus.py
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()

from app_graph import EVENT_SUBSCRIPTIONS, next_proactive_target
from maf_graph_state import (
    BlackboardEvent,
    EventType,
    IllegalEventPublishError,
    PMOState,
    append_event,
    mark_event_consumed,
)


def _state() -> PMOState:
    return PMOState(
        project_id="proj-event-bus",
        user_id="tester",
        billing_status="active_trial",
    )


def _event(event_type: EventType, publisher: str, **payload) -> BlackboardEvent:
    return BlackboardEvent(
        event_type=event_type,
        publisher=publisher,
        project_id="proj-event-bus",
        correlation_id="chg-1",
        payload=payload,
    )


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    if not ok:
        raise SystemExit(1)


def main() -> None:
    clerk_slip = append_event(
        _state(),
        _event(
            EventType.BASELINE_SLIP_REQUESTED,
            "change_control_clerk",
            change_id="chg-1",
            proposed_values={"baseline_end_date": "2027-04-01"},
        ),
    )
    check(
        "Aim 1: clerk may publish BASELINE_SLIP_REQUESTED",
        clerk_slip.event_bus[-1].event_type == EventType.BASELINE_SLIP_REQUESTED,
    )

    try:
        append_event(
            _state(),
            _event(
                EventType.BASELINE_SLIP_REQUESTED,
                "change_control_clerk",
                risk_category="timeline",
                severity=4,
            ),
        )
        check("Aim 1: clerk slip payload rejects risk fields", False)
    except IllegalEventPublishError as exc:
        check("Aim 1: clerk slip payload rejects risk fields", "risk" in str(exc).lower())

    try:
        append_event(
            _state(),
            _event(EventType.BASELINE_SLIP_REQUESTED, "pmp_worker"),
        )
        check("Aim 2: PMP cannot publish BASELINE_SLIP_REQUESTED", False)
    except IllegalEventPublishError:
        check("Aim 2: PMP cannot publish BASELINE_SLIP_REQUESTED", True)

    try:
        append_event(
            _state(),
            _event(EventType.BASELINE_SLIP_REQUESTED, "governance_worker"),
        )
        check("Aim 2: governance cannot publish BASELINE_SLIP_REQUESTED", False)
    except IllegalEventPublishError:
        check("Aim 2: governance cannot publish BASELINE_SLIP_REQUESTED", True)

    clerk_targets = [target for target in EVENT_SUBSCRIPTIONS.values() if target == "change_control_clerk"]
    check("Aim 3: EVENT_SUBSCRIPTIONS never wakes the clerk", clerk_targets == [])

    match = next_proactive_target(clerk_slip)
    check(
        "Aim 3: unread slip wakes governance_worker",
        match is not None and match[1] == "governance_worker",
    )

    event, target = match
    consumed = mark_event_consumed(clerk_slip, event.event_id, target)
    check(
        "Aim 3: consumed event is not re-woken",
        next_proactive_target(consumed) is None,
    )

    ingress_ok = [
        (EventType.DOCUMENT_INGESTED, "sharepoint_delta_ingestion", {"item_id": "01ITEM", "content_hash": "abc123"}),
        (EventType.TEAMS_MESSAGE_RECEIVED, "teams_bot", {"text": "hello", "user_id": "u1"}),
        (EventType.EMAIL_RECEIVED, "outlook_inbox_ingestion", {"message_id": "AAMk", "subject": "status"}),
    ]
    for event_type, publisher, payload in ingress_ok:
        updated = append_event(_state(), _event(event_type, publisher, **payload))
        check(
            f"Ingress: {publisher} may publish {event_type.value}",
            updated.event_bus[-1].event_type == event_type,
        )
        if event_type == EventType.DOCUMENT_INGESTED:
            check(
                "SharePoint DOCUMENT_INGESTED carries item_id + content_hash",
                updated.event_bus[-1].payload.get("item_id") == "01ITEM"
                and updated.event_bus[-1].payload.get("content_hash") == "abc123",
            )

    for event_type, _legal, payload in ingress_ok:
        for illegal in ("change_control_clerk", "pmp_worker", "governance_worker"):
            try:
                append_event(_state(), _event(event_type, illegal, **payload))
                check(f"Ingress: {illegal} cannot publish {event_type.value}", False)
            except IllegalEventPublishError:
                check(f"Ingress: {illegal} cannot publish {event_type.value}", True)

    ingress_types = {
        EventType.DOCUMENT_INGESTED,
        EventType.TEAMS_MESSAGE_RECEIVED,
        EventType.EMAIL_RECEIVED,
    }
    subscribed_ingress = [etype for etype in EVENT_SUBSCRIPTIONS if etype in ingress_types]
    check("Ingress types are not in EVENT_SUBSCRIPTIONS", subscribed_ingress == [])

    print("PASS: event-bus Aims 1–3 hold.")
    print("PASS: ingress publishers and non-subscription hold.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] unexpected error: {exc}", file=sys.stderr)
        raise
