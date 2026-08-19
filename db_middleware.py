"""Database middleware for the GIABO Digital PMO swarm.

Phase 4/6 scoped this module as pure mocks (`*_mock` functions, still kept
below for offline/unit-test use). Phase 7 (Real Database Integration) adds
the real functions that `chasing_engine.py` and `app_graph.py` now call,
backed by `db.session.get_session()` and the Phase 7 `tasks` table +
Phase 1's `pmo_artifacts` RAID log.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select, update

from db.models import ArtifactType, PmoArtifact, Project, Task
from db.session import get_session

# =============================================================================
# Phase 7: Real Database Integration
# =============================================================================

# Sentinels for tasks with no deadline / never contacted, so
# `chasing_engine.calculate_chasing_priorities`'s `datetime.fromisoformat`
# math never crashes on a NULL column and never mistakes "unknown" for
# "urgent"/"fatigued".
_NO_DEADLINE_HORIZON_DAYS = 365
_NEVER_CONTACTED_HORIZON_DAYS = 3650


class BaselineChangeRejectedError(ValueError):
    """Raised by `apply_baseline_change` when `proposed_values` contains a
    key outside the target table's column allow-list, the row doesn't exist,
    or there's nothing to commit. Fails closed: never builds SQL from an
    unvalidated column name.
    """


def get_active_tasks(project_id: str) -> list[dict]:
    """Real replacement for `get_active_tasks_mock`. Returns the same dict
    shape (`task_id`, `assignee`, `task_name`, `critical_path_impact`,
    `linked_risks_severity`, `deadline`, `last_contact_timestamp` as ISO
    strings) so `chasing_engine.calculate_chasing_priorities` doesn't need to
    change its parsing.
    """
    now = datetime.now(timezone.utc)
    no_deadline_default = now + timedelta(days=_NO_DEADLINE_HORIZON_DAYS)
    never_contacted_default = now - timedelta(days=_NEVER_CONTACTED_HORIZON_DAYS)

    with get_session() as session:
        rows = session.execute(
            select(Task).where(Task.project_id == project_id, Task.status != "closed")
        ).scalars().all()

        tasks: list[dict] = []
        for row in rows:
            if row.deadline is not None:
                # `deadline` is a DATE column -- combine with UTC midnight so
                # the resulting ISO string carries a timezone. Without a tz,
                # `datetime.fromisoformat` in chasing_engine.py would return a
                # naive datetime, and subtracting it from `now` (tz-aware)
                # raises TypeError.
                deadline_dt = datetime.combine(row.deadline, datetime.min.time(), tzinfo=timezone.utc)
            else:
                deadline_dt = no_deadline_default
            last_contact_dt = row.last_contact_timestamp or never_contacted_default

            tasks.append(
                {
                    "task_id": row.id,
                    "assignee": row.assignee_name or "Unassigned",
                    "task_name": row.task_name,
                    "critical_path_impact": row.critical_path_impact,
                    "linked_risks_severity": row.linked_risks_severity,
                    "deadline": deadline_dt.isoformat(),
                    "last_contact_timestamp": last_contact_dt.isoformat(),
                }
            )
        return tasks


def mark_task_contacted(task_id: str, project_id: str) -> bool:
    """Stamps `tasks.last_contact_timestamp = now()` for one task. Called by
    `chasing_graph.py`'s `node_draft_messages` immediately after a chase
    message is successfully drafted/sent -- without this, the 24h fatigue
    cooldown in `ChasingWeight.chasing_score` would never re-engage, since
    nothing else ever updates this column.
    """
    with get_session() as session:
        result = session.execute(
            update(Task)
            .where(Task.id == task_id, Task.project_id == project_id)
            .values(last_contact_timestamp=datetime.now(timezone.utc))
        )
        if result.rowcount == 0:
            print(f"mark_task_contacted: no task found for task_id={task_id!r} project_id={project_id!r}")
            return False
        print(f"DB Write Success: last_contact_timestamp -> {task_id}")
        return True


def commit_task_progress(project_id: str, source_agent_key: str, payload: dict) -> bool:
    """Real replacement for `commit_task_progress_mock`. Updates the `tasks`
    row's schedule-facing columns from a PMP Worker's `TaskProgressPayload`.

    `source_agent_key` isn't persisted here -- `tasks` (unlike
    `pmo_artifacts`) has no `source_agent_key` column -- but is accepted so
    the call site's signature matches `commit_blocker`/`commit_risk_escalation`
    and is available if/when this writes an `agent_executions` audit row too.
    """
    with get_session() as session:
        result = session.execute(
            update(Task)
            .where(Task.id == payload["task_id"], Task.project_id == project_id)
            .values(
                percent_complete=payload["percent_complete"],
                actual_hours_spent=payload["actual_hours_spent"],
                is_critical_path=payload["is_critical_path"],
                status_summary=payload["status_summary"],
            )
        )
        if result.rowcount == 0:
            print(
                f"commit_task_progress: no task found for task_id={payload.get('task_id')!r} "
                f"project_id={project_id!r}"
            )
            return False
        print(f"DB Write Success: task_progress -> {payload['task_id']} (source_agent_key={source_agent_key})")
        return True


def commit_blocker(project_id: str, source_agent_key: str, payload: dict) -> bool:
    """Real replacement for `commit_blocker_mock`. Phase 1 has no dedicated
    Blocker table -- an Agile Worker's `BlockerPayload` is inserted into the
    RAID log (`pmo_artifacts`) as `artifact_type='issue'`, which is exactly
    what a blocker is in RAID terms.
    """
    task_id = payload.get("task_id", "UNKNOWN")
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            print(f"commit_blocker: no project found for project_id={project_id!r}")
            return False

        artifact = PmoArtifact(
            id=f"ISSUE-BLOCKER-{task_id}-{uuid4().hex[:8]}",
            project_id=project.id,
            tenant_id=project.tenant_id,
            artifact_type=ArtifactType.ISSUE,
            title=f"Blocker: {task_id}",
            description=payload.get("blocker_description"),
            source_agent_key=source_agent_key,
            payload={
                "task_id": task_id,
                "requires_cross_team_help": payload.get("requires_cross_team_help"),
                "agile_action_item": payload.get("agile_action_item"),
            },
        )
        session.add(artifact)

    print(f"DB Write Success: blocker -> {task_id}")
    return True


def commit_risk_escalation(project_id: str, source_agent_key: str, payload: dict) -> bool:
    """Real replacement for `commit_risk_escalation_mock`. A Governance
    Worker's `RiskEscalationPayload` maps directly onto `pmo_artifacts`
    `artifact_type='risk'`.
    """
    risk_category = payload.get("risk_category", "risk")
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            print(f"commit_risk_escalation: no project found for project_id={project_id!r}")
            return False

        artifact = PmoArtifact(
            id=f"RISK-{risk_category.upper()}-{uuid4().hex[:8]}",
            project_id=project.id,
            tenant_id=project.tenant_id,
            artifact_type=ArtifactType.RISK,
            title=f"{risk_category.title()} Risk",
            description=payload.get("description"),
            severity=str(payload.get("severity")),
            source_agent_key=source_agent_key,
            payload={
                "risk_category": risk_category,
                "prince2_exception_triggered": payload.get("prince2_exception_triggered"),
            },
        )
        session.add(artifact)

    print(f"DB Write Success: risk_escalation -> {risk_category}")
    return True


# Per-`target_table` column allow-lists for `apply_baseline_change`. Never
# interpolate `proposed_values` keys into SQL -- every key MUST be checked
# against one of these sets first.
_TASK_COLUMNS = frozenset(
    {
        "task_name",
        "assignee_name",
        "assignee_entra_id",
        "status",
        "percent_complete",
        "actual_hours_spent",
        "is_critical_path",
        "critical_path_impact",
        "linked_risks_severity",
        "deadline",
        "status_summary",
    }
)
_BASELINE_COLUMNS = frozenset(
    {"baseline_aims", "baseline_goals", "baseline_objectives", "baseline_start_date", "baseline_end_date"}
)
_BUDGET_COLUMNS = frozenset({"baseline_budget"})

# target_table -> (ORM model updated, allowed proposed_values keys)
_TARGET_TABLE_CONFIG: dict[str, tuple[Any, frozenset]] = {
    "tasks": (Task, _TASK_COLUMNS),
    "baselines": (Project, _BASELINE_COLUMNS),
    "budgets": (Project, _BUDGET_COLUMNS),
}


def apply_baseline_change(
    target_table: Literal["tasks", "baselines", "budgets"],
    record_id: str,
    proposed_values: dict,
    *,
    project_id: str,
) -> dict:
    """Generic writeback for a PM-approved `PendingChangePayload` (Phase 3's
    `baseline_commit_node`). Replaces `mock_commit_baseline_change`.

    `target_table="tasks"` updates the Phase 7 `tasks` row (`record_id` is its
    `id`); `"baselines"`/`"budgets"` both update the owning `projects` row
    (`record_id` is the project's own `id` -- there's no separate baselines
    or budgets table, those are just columns on `projects`).

    Security-critical: every key in `proposed_values` is checked against a
    hardcoded per-`target_table` allow-list *before* any SQL is built --
    `proposed_values` is Router-model/LLM-influenced data (from
    `PendingChangePayload`), so its keys must never be trusted enough to
    interpolate as column identifiers.

    Callers are responsible for passing values already shaped to match the
    target column's Python type (e.g. `datetime.date` for `deadline`, not an
    arbitrary string) -- this function does not attempt type coercion beyond
    what SQLAlchemy's normal parameter binding provides.
    """
    if target_table not in _TARGET_TABLE_CONFIG:
        raise BaselineChangeRejectedError(f"Unknown target_table={target_table!r}.")

    model, allowed_columns = _TARGET_TABLE_CONFIG[target_table]
    disallowed = set(proposed_values) - allowed_columns
    if disallowed:
        raise BaselineChangeRejectedError(
            f"proposed_values contains disallowed column(s) {sorted(disallowed)} for "
            f"target_table={target_table!r}; allowed: {sorted(allowed_columns)}."
        )
    if not proposed_values:
        raise BaselineChangeRejectedError("proposed_values is empty; nothing to commit.")

    with get_session() as session:
        if target_table == "tasks":
            stmt = update(Task).where(Task.id == record_id, Task.project_id == project_id).values(**proposed_values)
        else:
            # "baselines" / "budgets" both target `projects`; record_id IS the
            # project's own id, so this also double-checks record_id and
            # project_id agree (a mismatch yields zero rows -> rejected below).
            stmt = update(Project).where(Project.id == record_id, Project.id == project_id).values(**proposed_values)

        result = session.execute(stmt)
        if result.rowcount == 0:
            raise BaselineChangeRejectedError(
                f"No {target_table} row matched record_id={record_id!r} for project_id={project_id!r}; "
                "no change was committed."
            )

    print(f"DB Write Success: baseline_change -> {target_table}:{record_id}")
    return {
        "committed": True,
        "target_table": target_table,
        "record_id": record_id,
        "proposed_values": proposed_values,
    }


# =============================================================================
# Phase 4/6 mocks -- kept for offline/unit-test use, no longer called by
# app_graph.py / chasing_engine.py once Phase 7 wiring lands.
# =============================================================================


def commit_task_progress_mock(payload: dict) -> bool:
    """Mock DB write for a PMP Worker's `TaskProgressPayload`. Phase 6 scopes
    this as a mock; the real write goes through the writeback-agent contract
    in `03-maf-writeback-agents.mdc` against `db.models`.
    """
    print(f"Mock DB Write Success: task_progress -> {payload.get('task_id')}")
    return True


def commit_blocker_mock(payload: dict) -> bool:
    """Mock DB write for an Agile Worker's `BlockerPayload`."""
    print(f"Mock DB Write Success: blocker -> {payload.get('task_id')}")
    return True


def commit_risk_escalation_mock(payload: dict) -> bool:
    """Mock DB write for a Governance Worker's `RiskEscalationPayload`."""
    print(f"Mock DB Write Success: risk_escalation -> {payload.get('risk_category')}")
    return True


def get_active_tasks_mock() -> list[dict]:
    """
    Returns mock tasks.
    Task 1: High critical path, but contacted 2 hours ago (Should be filtered out by 24h fatigue).
    Task 2: Medium impact, due in 2 days, contacted 3 days ago (High score).
    Task 3: Low impact, due in 15 days, never contacted (Low score).
    """
    now = datetime.now(timezone.utc)
    return [
        {
            "task_id": "TSK-001", "assignee": "Sarah (Backend)", "task_name": "API Gateway Migration",
            "critical_path_impact": 9, "linked_risks_severity": 8,
            "deadline": (now + timedelta(days=5)).isoformat(),
            "last_contact_timestamp": (now - timedelta(hours=2)).isoformat()
        },
        {
            "task_id": "TSK-002", "assignee": "David (Frontend)", "task_name": "Auth Token Refresh Bug",
            "critical_path_impact": 6, "linked_risks_severity": 5,
            "deadline": (now + timedelta(days=2)).isoformat(),
            "last_contact_timestamp": (now - timedelta(days=3)).isoformat()
        },
        {
            "task_id": "TSK-003", "assignee": "Alex (Design)", "task_name": "Figma Handoff - V2",
            "critical_path_impact": 2, "linked_risks_severity": 1,
            "deadline": (now + timedelta(days=15)).isoformat(),
            "last_contact_timestamp": (now - timedelta(days=10)).isoformat()
        }
    ]
