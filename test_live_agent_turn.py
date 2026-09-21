"""End-to-end live smoke test: real MAF graph execution + real Azure Postgres writeback.

Not a pytest suite -- a standalone, narratable script you run directly with
the project's `.venv` interpreter. It proves the full path that matters for
this project actually works against live infrastructure, not mocks:

    Teams-shaped user message
        -> app_graph.build_app_graph() (real Azure OpenAI calls: router_node
           then pmp_worker, per prompts/router_node.md + prompts/pmp_worker.md)
        -> state_writeback_node (real db_middleware.commit_task_progress)
        -> live `tasks` row in Azure Postgres, verified by a fresh read-back

Requires (loaded from `.env` via `python-dotenv`, exactly like the manual
`db.session` smoke tests already run from the terminal during Phase 7):
    AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_DEPLOYMENT_NAME
    DATABASE_URL
And live data:
    A `projects` row named 'Project Delta'.
    A `tasks` row with id='TSK-002' whose project_id belongs to that project
    (this script warns loudly, rather than failing silently, if it doesn't --
    see `_load_project_delta`/the mismatch check before running the turn).

Run:
    .venv/bin/python test_live_agent_turn.py
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402  (after load_dotenv, before anything reads env vars)

from app_graph import (  # noqa: E402
    PendingExceptionRequest,
    PendingVetoRequest,
    HardHaltMessage,
    build_app_graph,
    build_default_agile_chat_agent,
    build_default_change_control_chat_agent,
    build_default_governance_chat_agent,
    build_default_pmp_chat_agent,
    build_default_router_chat_agent,
    run_turn,
)
from db.models import Project, Task  # noqa: E402
from db.session import get_session  # noqa: E402
from maf_graph_state import PMOState  # noqa: E402

PROJECT_NAME = "Project Delta"
TASK_ID = "TSK-002"
USER_MESSAGE = "I am updating task TSK-002, I've spent 4 hours on it and it is now 50% complete."

# What we expect to see after the turn -- used for the final assertions, not
# just printed for information.
EXPECTED_PERCENT_COMPLETE = 50
EXPECTED_ACTUAL_HOURS_SPENT = 4.0


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _load_project_delta() -> tuple[str, str]:
    """Requirement 3: look up 'Project Delta' by name and return its real
    (project_id, tenant_id) as strings -- no hardcoded UUIDs anywhere in this
    script."""
    with get_session() as session:
        project = session.execute(select(Project).where(Project.name == PROJECT_NAME)).scalar_one_or_none()
        if project is None:
            print(f"FAIL: no project named {PROJECT_NAME!r} found in the live database.")
            sys.exit(1)
        project_id, tenant_id = str(project.id), str(project.tenant_id)

    print(f"Found {PROJECT_NAME!r}: project_id={project_id} tenant_id={tenant_id}")
    return project_id, tenant_id


def _load_task_snapshot(task_id: str) -> dict | None:
    """One fresh read of `tasks` by primary key -- used both before (baseline)
    and after (verification) the turn. Returns None if the task doesn't exist."""
    with get_session() as session:
        task = session.get(Task, task_id)
        if task is None:
            return None
        return {
            "id": task.id,
            "project_id": str(task.project_id),
            "task_name": task.task_name,
            "percent_complete": task.percent_complete,
            "actual_hours_spent": float(task.actual_hours_spent),
            "status_summary": task.status_summary,
        }


async def _run() -> None:
    _section("1. Load environment (.env via python-dotenv)")
    print("AZURE_OPENAI_ENDPOINT / DATABASE_URL loaded:", bool(True))  # load_dotenv() already ran at import time

    _section("2. Instantiate the real MAF app graph (build_app_graph, default chat agents)")
    workflow = build_app_graph(
        build_default_router_chat_agent(),
        change_control_chat_agent=build_default_change_control_chat_agent(),
        pmp_chat_agent=build_default_pmp_chat_agent(),
        agile_chat_agent=build_default_agile_chat_agent(),
        governance_chat_agent=build_default_governance_chat_agent(),
    )
    print("Workflow built:", workflow)

    _section(f"3. Resolve {PROJECT_NAME!r} -> real project_id / tenant_id")
    project_id, tenant_id = _load_project_delta()

    _section(f"3b. Baseline read of task {TASK_ID!r} (before the turn)")
    before = _load_task_snapshot(TASK_ID)
    if before is None:
        print(f"FAIL: no task {TASK_ID!r} found in the live database at all.")
        sys.exit(1)
    print("Before:", before)
    if before["project_id"] != project_id:
        print(
            f"WARNING: task {TASK_ID!r} belongs to project_id={before['project_id']!r}, "
            f"not {PROJECT_NAME!r}'s project_id={project_id!r}. commit_task_progress's "
            f"UPDATE ... WHERE project_id=... will match zero rows if this is really a "
            f"mismatch -- continuing anyway so the failure (if any) shows up below."
        )

    _section("4. Initialize PMOState with the user's message")
    state = PMOState(
        project_id=project_id,
        user_id="live-smoke-test-user",
        message_history=[{"role": "user", "content": USER_MESSAGE}],
        billing_status="active_paid",
    )
    print("PMOState:", state.model_dump())

    _section("5. Execute the turn (app_graph.run_turn -- real Azure OpenAI calls)")
    result = await run_turn(workflow, state)
    print("run_turn() returned:", type(result).__name__)
    print(result)

    if isinstance(result, HardHaltMessage):
        print(f"FAIL: graph halted before doing anything: {result.reason}")
        sys.exit(1)
    if isinstance(result, (PendingVetoRequest, PendingExceptionRequest)):
        print(
            "FAIL: turn paused for human-in-the-loop approval instead of "
            "completing a plain task-progress update -- the Router likely "
            "misclassified this message. No DB writeback happened yet."
        )
        sys.exit(1)

    _section(f"6. Verification read of task {TASK_ID!r} (after the turn)")
    after = _load_task_snapshot(TASK_ID)
    print("After: ", after)

    _section("Result")
    ok = (
        isinstance(result, dict)
        and result.get("status") == "committed"
        and result.get("committed", {}).get("task_progress") is True
        and after is not None
        and after["percent_complete"] == EXPECTED_PERCENT_COMPLETE
        and after["actual_hours_spent"] == EXPECTED_ACTUAL_HOURS_SPENT
    )
    if ok:
        print(
            f"PASS: {TASK_ID} is now {after['percent_complete']}% complete with "
            f"{after['actual_hours_spent']}h logged -- PMP Worker -> state_writeback_node "
            f"-> commit_task_progress round-tripped through live Azure Postgres."
        )
    else:
        print(
            "FAIL: turn completed but the live database does not reflect the expected "
            f"percent_complete={EXPECTED_PERCENT_COMPLETE} / "
            f"actual_hours_spent={EXPECTED_ACTUAL_HOURS_SPENT}. See 'Before'/'After' above."
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_run())
