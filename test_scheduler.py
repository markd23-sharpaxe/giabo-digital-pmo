"""Morning Heartbeat scheduler checks (helpers + isolated DB jobs).

Does not start the in-process AsyncIOScheduler against the whole tenant
roster. Job tests pass `project_ids=` so live projects are never chased.

Run:
    .venv/bin/python test_scheduler.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

import anyio
from sqlalchemy import delete, select

from core.scheduler import (
    deterministic_artifact_id,
    last_friday_of_month,
    run_cron_governance_sweeps,
    run_daily_chasing_sweep,
    scheduler_enabled,
)
from db.models import (
    ArtifactType,
    EventBusRow,
    PlanTier,
    PmoArtifact,
    Project,
    ProjectStatus,
    SwarmStatus,
    Task,
    Tenant,
)
from db.session import get_session

FAILURES: list[str] = []


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def test_helpers() -> None:
    _section("Part 1: calendar + deterministic keys")
    _check("last Friday of Sep 2026 is 2026-09-25", last_friday_of_month(2026, 9) == date(2026, 9, 25))
    _check("last Friday of Aug 2026 is 2026-08-28", last_friday_of_month(2026, 8) == date(2026, 8, 28))
    eom_id = deterministic_artifact_id("ACTION-EOM", "eom-demo-2026-09", "2026-09")
    _check("EOM id has ACTION-EOM- prefix", eom_id.startswith("ACTION-EOM-"))
    _check("EOM id ends with the billing period", eom_id.endswith("-2026-09"))
    _check(
        "EOM id is stable across calls",
        eom_id == deterministic_artifact_id("ACTION-EOM", "eom-demo-2026-09", "2026-09"),
    )
    sprint_id = deterministic_artifact_id("ACTION-SPRINT-OVERDUE", "Sprint 11")
    _check("sprint overdue id has ACTION-SPRINT-OVERDUE- prefix", sprint_id.startswith("ACTION-SPRINT-OVERDUE-"))
    _check("scheduler defaults to disabled", scheduler_enabled() is False or os.environ.get("ENABLE_BACKGROUND_SCHEDULER", "").lower() in {"1", "true", "yes", "on"})


def _seed() -> tuple[uuid.UUID, uuid.UUID, str, str]:
    tenant_id = uuid.uuid4()
    project_id = uuid.uuid4()
    sent_task = f"TSK-HB-SENT-{uuid.uuid4().hex[:8]}"
    quiet_task = f"TSK-HB-QUIET-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    with get_session() as session:
        tenant = Tenant(
            id=tenant_id,
            azure_subscription_id=uuid.uuid4(),
            azure_customer_tenant_id=uuid.uuid4(),
            organization_name="Heartbeat Test Org",
            plan_tier=PlanTier.FREE_TRIAL,
            trial_start_date=date.today(),
            swarm_status=SwarmStatus.ACTIVE,
        )
        session.add(tenant)
        session.flush()
        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Heartbeat Test Project",
            status=ProjectStatus.INITIATED,
        )
        session.add(project)
        session.add(
            Task(
                id=sent_task,
                project_id=project_id,
                tenant_id=tenant_id,
                task_name="Chase me",
                assignee_name="Dana",
                status="in_progress",
                critical_path_impact=8,
                linked_risks_severity=7,
                deadline=(now + timedelta(days=2)).date(),
                last_contact_timestamp=now - timedelta(days=3),
                actual_hours_spent=Decimal("0"),
            )
        )
        session.add(
            Task(
                id=quiet_task,
                project_id=project_id,
                tenant_id=tenant_id,
                task_name="Leave me",
                assignee_name="Lee",
                status="in_progress",
                critical_path_impact=8,
                linked_risks_severity=7,
                deadline=(now + timedelta(days=2)).date(),
                last_contact_timestamp=now - timedelta(hours=2),
                actual_hours_spent=Decimal("0"),
            )
        )
        session.add(
            PmoArtifact(
                id=f"SPRINT-HB-{uuid.uuid4().hex[:8]}",
                project_id=project_id,
                tenant_id=tenant_id,
                artifact_type=ArtifactType.SPRINT,
                title="Sprint 11",
                source_agent_key="scrum_master_liaison",
                status="active",
                due_date=date.today() - timedelta(days=2),
                payload={"sprint_name": "Sprint 11"},
            )
        )
    return tenant_id, project_id, sent_task, quiet_task


def _cleanup(tenant_id: uuid.UUID, project_id: uuid.UUID) -> None:
    with get_session() as session:
        session.execute(delete(EventBusRow).where(EventBusRow.project_id == str(project_id)))
        tenant = session.get(Tenant, tenant_id)
        if tenant is not None:
            session.delete(tenant)


def test_jobs() -> None:
    _section("Part 2: isolated chasing + governance jobs")
    tenant_id, project_id, sent_task, quiet_task = _seed()
    try:
        async def _chase():
            return await run_daily_chasing_sweep(project_ids=[str(project_id)])

        chase = anyio.run(_chase)
        _check("chasing sweep saw the test project", chase.projects == 1, str(chase.projects))
        _check("one CHASE_SENT", chase.chase_sent == 1, str(chase.chase_sent))
        _check("one CHASE_SUPPRESSED", chase.chase_suppressed == 1, str(chase.chase_suppressed))

        with get_session() as session:
            events = session.execute(
                select(EventBusRow).where(EventBusRow.project_id == str(project_id))
            ).scalars().all()
            types = {row.event_type for row in events}
            _check("event bus has CHASE_SENT", "CHASE_SENT" in types)
            _check("event bus has CHASE_SUPPRESSED", "CHASE_SUPPRESSED" in types)
            _check("chase publisher is chasing_agent", all(row.publisher == "chasing_agent" for row in events if row.event_type.startswith("CHASE_")))
            contacted = session.get(Task, sent_task)
            _check("sent task last_contact was stamped", contacted is not None and contacted.last_contact_timestamp is not None)
            quiet = session.get(Task, quiet_task)
            _check(
                "suppressed task last_contact was not refreshed past the 2h window",
                quiet is not None and quiet.last_contact_timestamp is not None
                and (datetime.now(timezone.utc) - quiet.last_contact_timestamp).total_seconds() > 60 * 60,
            )

        async def _gov():
            return await run_cron_governance_sweeps(today=date(2026, 9, 25), project_ids=[str(project_id)])

        gov = anyio.run(_gov)
        _check("governance sweep audited the test project", gov.audits == 1)
        _check("EOM action written on last Friday", gov.eom_written == 1, str(gov.eom_written))
        _check("sprint overdue action written", gov.sprint_overdue_written == 1, str(gov.sprint_overdue_written))

        expected_eom = deterministic_artifact_id("ACTION-EOM", f"eom-{project_id}-2026-09", "2026-09")
        expected_sprint = deterministic_artifact_id("ACTION-SPRINT-OVERDUE", "Sprint 11")
        with get_session() as session:
            eom = session.get(PmoArtifact, expected_eom)
            sprint_action = session.get(PmoArtifact, expected_sprint)
            _check("EOM artifact id matches ACTION-EOM-<hash>-2026-09", eom is not None and eom.id == expected_eom)
            _check("sprint overdue artifact id matches ACTION-SPRINT-OVERDUE-<hash>", sprint_action is not None)
            project = session.get(Project, project_id)
            _check(
                "governance auditor stamped golden_thread_last_verified_at",
                project is not None and project.golden_thread_last_verified_at is not None,
            )
            _check("eom_checkpoint_day set to last Friday (25)", project is not None and project.eom_checkpoint_day == 25)

        async def _gov_again():
            return await run_cron_governance_sweeps(today=date(2026, 9, 25), project_ids=[str(project_id)])

        again = anyio.run(_gov_again)
        _check("second EOM run is idempotent (0 new rows)", again.eom_written == 0, str(again.eom_written))
        _check("second sprint overdue run is idempotent", again.sprint_overdue_written == 0, str(again.sprint_overdue_written))
    finally:
        _cleanup(tenant_id, project_id)


def main() -> int:
    test_helpers()
    test_jobs()
    print(f"\n{'=' * 78}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("All scheduler checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
