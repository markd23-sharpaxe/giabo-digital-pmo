"""Scorecard audit of four GIABO Digital PMO reasoning invariants.

Not a pytest suite -- a standalone, narratable script matching
`test_live_agent_turn.py` / `test_copilot_api.py`. Hybrid by design:

    Cases 1 and 3 -- deterministic refusals (no Azure OpenAI). They prove
    the code path that must fire even if the LLM disagrees.
    Cases 2 and 4 -- live `build_app_graph()` turns against Azure OpenAI
    (same `.env` as `test_live_agent_turn.py`). Writebacks are patched so
    the live `tasks` / `pmo_artifacts` tables are not mutated.

Run:
    .venv/bin/python test_agent_reasoning_audit.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()

from agent_framework import FileCheckpointStorage

from app_graph import (  # noqa: E402
    CHECKPOINT_ALLOWED_TYPES,
    PendingExceptionRequest,
    PendingVetoRequest,
    RouterNode,
    RoutedMessage,
    build_app_graph,
    build_default_agile_chat_agent,
    build_default_change_control_chat_agent,
    build_default_governance_chat_agent,
    build_default_pmp_chat_agent,
    build_default_router_chat_agent,
    friction_breaker_fires,
    run_turn,
)
from chasing_engine import calculate_chasing_priorities
from maf_graph_state import ChasingWeight, PMOState, TriageRouterDecision

TEST_DOCS_DIR = Path(__file__).resolve().parent / "test_docs"
LIVE_PROD_PROJECT_ID = "22222222-2222-2222-2222-222222222222"
OPENAI_ENV_KEYS = ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME")

FAILURES: list[str] = []


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _scorecard(*, name: str, description: str, expected: str, actual: str, passed: bool) -> None:
    verdict = "PASS" if passed else "FAIL"
    print(f"\nTest Case Name: {name}")
    print(f"Description: {description}")
    print(f"Expected Action / Invariant Rule: {expected}")
    print(f"Actual Agent Behavior / State Output: {actual}")
    print(f"Verdict: {verdict}")
    if not passed:
        FAILURES.append(name)


def _read_doc(filename: str) -> str:
    return (TEST_DOCS_DIR / filename).read_text(encoding="utf-8")


def _missing_openai_env() -> list[str]:
    return [key for key in OPENAI_ENV_KEYS if not os.environ.get(key)]


def _writeback_patches():
    """No-op every Postgres write the live graph could reach."""
    return (
        patch("app_graph.commit_task_progress", return_value=True),
        patch("app_graph.commit_blocker", return_value=True),
        patch("app_graph.commit_risk_escalation", return_value=True),
        patch("app_graph.apply_baseline_change", return_value=True),
    )


def _build_live_graph(*, checkpoint_storage: FileCheckpointStorage):
    return build_app_graph(
        build_default_router_chat_agent(),
        change_control_chat_agent=build_default_change_control_chat_agent(),
        pmp_chat_agent=build_default_pmp_chat_agent(),
        agile_chat_agent=build_default_agile_chat_agent(),
        governance_chat_agent=build_default_governance_chat_agent(),
        checkpoint_storage=checkpoint_storage,
    )


def _new_checkpoint_storage() -> tuple[FileCheckpointStorage, str]:
    path = tempfile.mkdtemp(prefix="agent_reasoning_audit_")
    storage = FileCheckpointStorage(path, allowed_checkpoint_types=CHECKPOINT_ALLOWED_TYPES)
    return storage, path


def _pmo_state(*, user_message: str, vague_turns: int = 0) -> PMOState:
    return PMOState(
        project_id=LIVE_PROD_PROJECT_ID,
        user_id="agent-reasoning-audit",
        message_history=[{"role": "user", "content": user_message}],
        vague_turns=vague_turns,
        billing_status="active_paid",
    )


# =============================================================================
# Case 1 -- Dynamic Chasing Fatigue Cooldown (must NOT engage)
# =============================================================================


def case_1_fatigue_cooldown() -> None:
    name = "Dynamic Chasing Fatigue Cooldown"
    description = (
        "A high-impact critical-path task last contacted 2 hours ago must score "
        "0.0 and be omitted from outreach -- Immutable Principle 4 (no cron)."
    )
    expected = (
        "ChasingWeight.chasing_score == 0.0 when hours_since_last_contact < 24; "
        "calculate_chasing_priorities() omits the task (outreach skipped)."
    )

    try:
        fixture = json.loads(_read_doc("fatigue_task.json"))
        weight = ChasingWeight(
            task_id=fixture["task_id"],
            critical_path_impact=fixture["critical_path_impact"],
            linked_risks_severity=fixture["linked_risks_severity"],
            hours_since_last_contact=fixture["hours_since_last_contact"],
            days_to_deadline=fixture["days_to_deadline"],
        )
        score = weight.chasing_score

        now = datetime.now(timezone.utc)
        patched_row = {
            "task_id": fixture["task_id"],
            "assignee": fixture["assignee"],
            "task_name": fixture["task_name"],
            "critical_path_impact": fixture["critical_path_impact"],
            "linked_risks_severity": fixture["linked_risks_severity"],
            "deadline": (now + timedelta(days=fixture["days_to_deadline"])).isoformat(),
            "last_contact_timestamp": (now - timedelta(hours=fixture["hours_since_last_contact"])).isoformat(),
        }
        with patch("chasing_engine.get_active_tasks", return_value=[patched_row]):
            prioritized = calculate_chasing_priorities(LIVE_PROD_PROJECT_ID)

        omitted = all(row.get("task_id") != fixture["task_id"] for row in prioritized)
        passed = score == 0.0 and omitted
        actual = (
            f"chasing_score={score!r} (hours_since_last_contact="
            f"{fixture['hours_since_last_contact']}); "
            f"priorities returned {len(prioritized)} task(s); "
            f"TSK-FATIGUE omitted={omitted}"
        )
    except Exception as exc:  # noqa: BLE001 -- scorecard the failure, don't crash the suite
        passed = False
        actual = f"exception: {type(exc).__name__}: {exc}"

    _scorecard(name=name, description=description, expected=expected, actual=actual, passed=passed)


# =============================================================================
# Case 2 -- PRINCE2 Tolerance Breach (must engage)
# =============================================================================


async def case_2_prince2_exception() -> None:
    name = "PRINCE2 Tolerance Breach"
    description = (
        "A 15% stage budget/scope overrun must set prince2_exception_triggered "
        "and pause the graph at suspend_for_exception_node -- not a silent commit."
    )
    expected = (
        "RiskEscalationPayload.prince2_exception_triggered is True AND "
        "run_turn returns PendingExceptionRequest."
    )

    missing = _missing_openai_env()
    if missing:
        _scorecard(
            name=name,
            description=description,
            expected=expected,
            actual=f"skipped -- missing env vars: {', '.join(missing)}",
            passed=False,
        )
        return

    captured: dict = {}
    storage, ckpt_dir = _new_checkpoint_storage()
    try:
        from app_graph import render_exception_card as _original_render

        def _capture_card(exception_id, risk):
            captured["risk"] = risk
            return _original_render(exception_id, risk)

        user_message = _read_doc("budget_variance.md")
        state = _pmo_state(user_message=user_message)
        patches = _writeback_patches() + (patch("app_graph.render_exception_card", side_effect=_capture_card),)
        for p in patches:
            p.start()
        try:
            workflow = _build_live_graph(checkpoint_storage=storage)
            result = await run_turn(workflow, state, checkpoint_storage=storage)
        finally:
            for p in reversed(patches):
                p.stop()

        risk = captured.get("risk")
        exception_flag = bool(getattr(risk, "prince2_exception_triggered", False))
        is_pending = isinstance(result, PendingExceptionRequest)
        passed = exception_flag and is_pending
        actual = (
            f"run_turn returned {type(result).__name__}; "
            f"prince2_exception_triggered={exception_flag}; "
            f"risk_category={getattr(risk, 'risk_category', None)!r}; "
            f"severity={getattr(risk, 'severity', None)!r}; "
            f"description={getattr(risk, 'description', None)!r}"
        )
        if isinstance(result, dict):
            actual += f"; worker={result.get('worker')!r} status={result.get('status')!r}"
    except Exception as exc:  # noqa: BLE001
        passed = False
        actual = f"exception: {type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(ckpt_dir, ignore_errors=True)

    _scorecard(name=name, description=description, expected=expected, actual=actual, passed=passed)


# =============================================================================
# Case 3 -- Friction Breaker (must engage, override LLM)
# =============================================================================


async def case_3_friction_breaker() -> None:
    name = "Friction Breaker Override"
    description = (
        "vague_turns >= 2 forces escalation_node even when the LLM returns a "
        "deliberately wrong next_node='pmp_worker'."
    )
    expected = (
        "friction_breaker_fires(RoutedMessage) is True when vague_turns=2 "
        "despite TriageRouterDecision.next_node='pmp_worker'. Optional beat: "
        "RouterNode.route with update_vague_turns=True on incoming vague_turns=1 "
        "yields outgoing vague_turns=2 and the helper still fires."
    )

    try:
        wrong_decision = TriageRouterDecision(
            next_node="pmp_worker",
            reasoning="Deliberately wrong -- the LLM would send this to PMP.",
            update_vague_turns=False,
        )
        msg = RoutedMessage(
            state=_pmo_state(user_message=_read_doc("vague_reply.md"), vague_turns=2),
            decision=wrong_decision,
        )
        helper_true = friction_breaker_fires(msg) is True

        stub_decision = TriageRouterDecision(
            next_node="pmp_worker",
            reasoning="Deliberately wrong after a vague turn.",
            update_vague_turns=True,
        )
        class _StubAgent:
            async def run(self, *args, **kwargs):
                return SimpleNamespace(value=stub_decision)

        incoming = _pmo_state(user_message=_read_doc("vague_reply.md"), vague_turns=1)
        ctx = _CaptureCtx()
        await RouterNode(_StubAgent()).route(incoming, ctx)  # type: ignore[arg-type]
        routed = ctx.messages[0]
        second_beat = routed.state.vague_turns == 2 and friction_breaker_fires(routed) is True

        passed = helper_true and second_beat
        outgoing_next = routed.decision.next_node if routed.decision is not None else None
        actual = (
            f"helper_on_wrong_llm={helper_true}; "
            f"outgoing_vague_turns={routed.state.vague_turns}; "
            f"outgoing_next_node={outgoing_next!r}; "
            f"helper_after_router={friction_breaker_fires(routed)}"
        )
    except Exception as exc:  # noqa: BLE001
        passed = False
        actual = f"exception: {type(exc).__name__}: {exc}"

    _scorecard(name=name, description=description, expected=expected, actual=actual, passed=passed)


class _CaptureCtx:
    def __init__(self) -> None:
        self.messages: list[RoutedMessage] = []

    async def send_message(self, msg: RoutedMessage) -> None:
        self.messages.append(msg)


# =============================================================================
# Case 4 -- Precise Framework Routing (must NOT misbehave)
# =============================================================================


async def case_4_precise_pmp_routing() -> None:
    name = "Precise Framework Routing (PMP schedule update)"
    description = (
        "A precise hours/percent-complete report must land on pmp_worker, "
        "must not pause for PM veto, and must not draft a baseline override."
    )
    expected = (
        "run_turn result worker == 'pmp_worker'; result is not a "
        "PendingVetoRequest; pending_change stays None (Change Control Clerk "
        "did not run)."
    )

    missing = _missing_openai_env()
    if missing:
        _scorecard(
            name=name,
            description=description,
            expected=expected,
            actual=f"skipped -- missing env vars: {', '.join(missing)}",
            passed=False,
        )
        return

    storage, ckpt_dir = _new_checkpoint_storage()
    apply_calls: list[bool] = []

    def _noop_apply(*_args, **_kwargs) -> bool:
        apply_calls.append(True)
        return True

    try:
        user_message = _read_doc("schedule_update.md")
        state = _pmo_state(user_message=user_message)
        patches = (
            patch("app_graph.commit_task_progress", return_value=True),
            patch("app_graph.commit_blocker", return_value=True),
            patch("app_graph.commit_risk_escalation", return_value=True),
            patch("app_graph.apply_baseline_change", side_effect=_noop_apply),
        )
        for p in patches:
            p.start()
        try:
            workflow = _build_live_graph(checkpoint_storage=storage)
            result = await run_turn(workflow, state, checkpoint_storage=storage)
        finally:
            for p in reversed(patches):
                p.stop()

        not_veto = not isinstance(result, PendingVetoRequest)
        worker = result.get("worker") if isinstance(result, dict) else None
        pending_change = state.pending_change
        apply_called = bool(apply_calls)
        passed = (
            not_veto
            and isinstance(result, dict)
            and worker == "pmp_worker"
            and pending_change is None
            and not apply_called
        )
        actual = (
            f"run_turn returned {type(result).__name__}; worker={worker!r}; "
            f"status={result.get('status') if isinstance(result, dict) else None!r}; "
            f"pending_change={pending_change!r}; "
            f"apply_baseline_change called={apply_called}"
        )
        if isinstance(result, dict) and result.get("payload") is not None:
            payload = result["payload"]
            actual += (
                f"; payload.task_id={getattr(payload, 'task_id', None)!r} "
                f"percent_complete={getattr(payload, 'percent_complete', None)!r} "
                f"hours={getattr(payload, 'actual_hours_spent', None)!r}"
            )
    except Exception as exc:  # noqa: BLE001
        passed = False
        actual = f"exception: {type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(ckpt_dir, ignore_errors=True)

    _scorecard(name=name, description=description, expected=expected, actual=actual, passed=passed)


# =============================================================================
# Runner
# =============================================================================


async def _run() -> None:
    _section("Agent Reasoning Audit -- scorecard")
    print("Cases 1 and 3: deterministic (no Azure OpenAI).")
    print("Cases 2 and 4: live Azure OpenAI; Postgres writebacks patched.")

    _section("Case 1")
    case_1_fatigue_cooldown()

    _section("Case 2")
    await case_2_prince2_exception()

    _section("Case 3")
    await case_3_friction_breaker()

    _section("Case 4")
    await case_4_precise_pmp_routing()

    _section("Result")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} case(s) failed:")
        for name in FAILURES:
            print(f"  - {name}")
        sys.exit(1)
    print("PASS: all four reasoning-audit cases held.")


if __name__ == "__main__":
    asyncio.run(_run())
