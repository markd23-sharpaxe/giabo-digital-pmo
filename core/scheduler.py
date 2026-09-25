"""Morning Heartbeat -- in-process autonomous background scheduler.

Two daily jobs, started from FastAPI lifespan when
`ENABLE_BACKGROUND_SCHEDULER` is truthy:

  1. `run_daily_chasing_sweep` -- Dynamic Chasing Engine (chasing_engine.py)
     scores every active project's tasks and publishes CHASE_SENT /
     CHASE_SUPPRESSED onto that project's event bus.
  2. `run_cron_governance_sweeps` -- cron-only roles from
     DELTA_DISPATCH_EXCLUDED_AGENTS: governance auditor, last-Friday EOM
     checkpoint, and sprint-boundary watchdog. EOM / overdue-sprint writes
     use deterministic `pmo_artifacts` keys so re-runs are idempotent.

These jobs never go through the PMO Commander Router.
"""

from __future__ import annotations

import hashlib
import logging
import os
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from chasing_engine import score_active_tasks
from db.models import ArtifactType, PmoArtifact, Project, SwarmStatus, Tenant
from db.session import get_session
from db_middleware import mark_task_contacted
from maf_graph_state import BlackboardEvent, EventType, record_ingress_event

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}
_CLOSED_SPRINT_STATUSES = frozenset({"completed", "closed", "done", "cancelled"})

_scheduler: Optional[AsyncIOScheduler] = None


def scheduler_enabled() -> bool:
    return os.environ.get("ENABLE_BACKGROUND_SCHEDULER", "false").strip().lower() in _TRUTHY


def _timezone_name() -> str:
    return os.environ.get("SCHEDULER_TIMEZONE", "UTC").strip() or "UTC"


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("scheduler: invalid %s=%r; using %s", name, raw, default)
        return default


# =============================================================================
# Shared helpers
# =============================================================================


@dataclass
class SweepStats:
    projects: int = 0
    chase_sent: int = 0
    chase_suppressed: int = 0
    eom_written: int = 0
    sprint_overdue_written: int = 0
    audits: int = 0
    errors: list[str] = field(default_factory=list)


def last_friday_of_month(year: int, month: int) -> date:
    """Calendar date of the last Friday in `year`/`month` (EOM checkpoint)."""
    last_day = date(year, month, monthrange(year, month)[1])
    return last_day - timedelta(days=(last_day.weekday() - 4) % 7)


def deterministic_artifact_id(prefix: str, seed: str, period: Optional[str] = None) -> str:
    """Match the GIABO eval helper: sha256(seed)[:12] after the prefix."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}-{period}" if period else f"{prefix}-{digest}"


def list_active_projects() -> list[Project]:
    """Projects whose tenant is ACTIVE -- the Morning Heartbeat roster."""
    with get_session() as session:
        rows = session.execute(
            select(Project)
            .join(Tenant, Project.tenant_id == Tenant.id)
            .where(Tenant.swarm_status == SwarmStatus.ACTIVE)
            .order_by(Project.created_at.asc())
        ).scalars().all()
        for row in rows:
            session.expunge(row)
        return rows


def _publish_chase_event(
    project_id: str,
    event_type: EventType,
    task: dict,
) -> None:
    record_ingress_event(
        project_id,
        BlackboardEvent(
            event_type=event_type,
            publisher="chasing_agent",
            project_id=project_id,
            correlation_id=task["task_id"],
            payload={
                "task_id": task["task_id"],
                "hours_since_last_contact": task.get("hours_since_last_contact"),
                "chasing_score": task.get("chasing_score"),
            },
        ),
    )


def _upsert_action(
    *,
    artifact_id: str,
    project: Project,
    title: str,
    description: str,
    source_agent_key: str,
    payload: dict,
) -> bool:
    """Insert a deterministic action row. Returns True when a new row was written."""
    with get_session() as session:
        if session.get(PmoArtifact, artifact_id) is not None:
            return False
        stmt = (
            insert(PmoArtifact)
            .values(
                id=artifact_id,
                project_id=project.id,
                tenant_id=project.tenant_id,
                artifact_type=ArtifactType.ACTION,
                title=title,
                description=description,
                source_agent_key=source_agent_key,
                status="open",
                payload=payload,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        session.execute(stmt)
        return True


def _publish_raid_written(project_id: str, publisher: str, artifact_id: str) -> None:
    record_ingress_event(
        str(project_id),
        BlackboardEvent(
            event_type=EventType.RAID_ARTIFACT_WRITTEN,
            publisher=publisher,
            project_id=str(project_id),
            correlation_id=artifact_id,
            payload={"artifact_id": artifact_id},
        ),
    )


# =============================================================================
# Job 1 -- Daily Chasing Sweep
# =============================================================================


async def run_daily_chasing_sweep(*, project_ids: Optional[list[str]] = None) -> SweepStats:
    """Score every active project and emit chase / suppress events."""
    stats = SweepStats()
    try:
        projects = list_active_projects()
        if project_ids is not None:
            wanted = {str(pid) for pid in project_ids}
            projects = [project for project in projects if str(project.id) in wanted]
    except Exception as exc:  # noqa: BLE001 - a DB blip must not kill the scheduler
        logger.exception("daily chasing sweep: failed to load projects")
        stats.errors.append(str(exc))
        return stats

    stats.projects = len(projects)
    for project in projects:
        project_id = str(project.id)
        try:
            prioritized, suppressed = score_active_tasks(project_id)
            for task in suppressed:
                _publish_chase_event(project_id, EventType.CHASE_SUPPRESSED, task)
                stats.chase_suppressed += 1
            for task in prioritized:
                _publish_chase_event(project_id, EventType.CHASE_SENT, task)
                try:
                    mark_task_contacted(task["task_id"], project_id)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "daily chasing sweep: failed to stamp last_contact for %s",
                        task.get("task_id"),
                    )
                stats.chase_sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("daily chasing sweep failed for project %s", project_id)
            stats.errors.append(f"{project_id}: {exc}")

    logger.info(
        "daily chasing sweep: projects=%s sent=%s suppressed=%s errors=%s",
        stats.projects,
        stats.chase_sent,
        stats.chase_suppressed,
        len(stats.errors),
    )
    return stats


# =============================================================================
# Job 2 -- Cron Governance Sweeps
# =============================================================================


def _run_governance_auditor(project: Project, today: date) -> None:
    """Scheduled Golden Thread stamp -- cron only, no RAID writeback."""
    with get_session() as session:
        row = session.get(Project, project.id)
        if row is None:
            return
        row.golden_thread_last_verified_at = datetime.now(timezone.utc)
        friday = last_friday_of_month(today.year, today.month)
        row.eom_checkpoint_day = friday.day


def _run_eom_checkpoint(project: Project, today: date) -> bool:
    friday = last_friday_of_month(today.year, today.month)
    if today != friday:
        return False
    period = today.strftime("%Y-%m")
    seed = f"eom-{project.id}-{period}"
    artifact_id = deterministic_artifact_id("ACTION-EOM", seed, period)
    written = _upsert_action(
        artifact_id=artifact_id,
        project=project,
        title=f"End-of-month financial checkpoint {period}",
        description=(
            f"Last-Friday EOM checkpoint for {project.name} ({period}). "
            "Deterministic key; re-run is a no-op."
        ),
        source_agent_key="eom_financial_checkpoint",
        payload={"period": period, "trigger": "cron_sweep", "eom_checkpoint_day": friday.day},
    )
    if written:
        _publish_raid_written(str(project.id), "eom_financial_checkpoint", artifact_id)
    return written


def _run_sprint_watchdog(project: Project, today: date) -> int:
    written = 0
    with get_session() as session:
        sprints = session.execute(
            select(PmoArtifact).where(
                PmoArtifact.project_id == project.id,
                PmoArtifact.artifact_type == ArtifactType.SPRINT,
                PmoArtifact.due_date.is_not(None),
                PmoArtifact.due_date < today,
            )
        ).scalars().all()
        overdue = [row for row in sprints if (row.status or "").lower() not in _CLOSED_SPRINT_STATUSES]

    for sprint in overdue:
        seed = sprint.title
        artifact_id = deterministic_artifact_id("ACTION-SPRINT-OVERDUE", seed)
        inserted = _upsert_action(
            artifact_id=artifact_id,
            project=project,
            title=f"Sprint overdue: {sprint.title}",
            description=f"{sprint.title} passed its due date ({sprint.due_date}) and is still open.",
            source_agent_key="sprint_boundary_watchdog",
            payload={
                "sprint_id": sprint.id,
                "sprint_name": sprint.title,
                "due_date": sprint.due_date.isoformat() if sprint.due_date else None,
                "trigger": "cron_sweep",
            },
        )
        if inserted:
            _publish_raid_written(str(project.id), "sprint_boundary_watchdog", artifact_id)
            written += 1
    return written


async def run_cron_governance_sweeps(
    *,
    today: Optional[date] = None,
    project_ids: Optional[list[str]] = None,
) -> SweepStats:
    """Governance auditor + last-Friday EOM + overdue-sprint watchdog."""
    stats = SweepStats()
    day = today or datetime.now(timezone.utc).date()
    try:
        projects = list_active_projects()
        if project_ids is not None:
            wanted = {str(pid) for pid in project_ids}
            projects = [project for project in projects if str(project.id) in wanted]
    except Exception as exc:  # noqa: BLE001
        logger.exception("cron governance sweep: failed to load projects")
        stats.errors.append(str(exc))
        return stats

    stats.projects = len(projects)
    for project in projects:
        try:
            _run_governance_auditor(project, day)
            stats.audits += 1
            if _run_eom_checkpoint(project, day):
                stats.eom_written += 1
            stats.sprint_overdue_written += _run_sprint_watchdog(project, day)
        except Exception as exc:  # noqa: BLE001
            logger.exception("cron governance sweep failed for project %s", project.id)
            stats.errors.append(f"{project.id}: {exc}")

    logger.info(
        "cron governance sweep: projects=%s audits=%s eom=%s sprint_overdue=%s errors=%s",
        stats.projects,
        stats.audits,
        stats.eom_written,
        stats.sprint_overdue_written,
        len(stats.errors),
    )
    return stats


# =============================================================================
# Lifespan
# =============================================================================


def start_background_scheduler() -> Optional[AsyncIOScheduler]:
    """Build and start the AsyncIOScheduler. No-op when the env toggle is off."""
    global _scheduler
    if not scheduler_enabled():
        logger.info("Morning Heartbeat disabled (ENABLE_BACKGROUND_SCHEDULER is not true).")
        return None
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    tz = _timezone_name()
    chasing_hour = _int_env("SCHEDULER_CHASING_HOUR", 7)
    governance_hour = _int_env("SCHEDULER_GOVERNANCE_HOUR", 7)
    governance_minute = _int_env("SCHEDULER_GOVERNANCE_MINUTE", 30)

    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(
        run_daily_chasing_sweep,
        CronTrigger(hour=chasing_hour, minute=0, timezone=tz),
        id="daily_chasing_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_cron_governance_sweeps,
        CronTrigger(hour=governance_hour, minute=governance_minute, timezone=tz),
        id="cron_governance_sweeps",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Morning Heartbeat started (chasing %02d:00, governance %02d:%02d, tz=%s).",
        chasing_hour,
        governance_hour,
        governance_minute,
        tz,
    )
    return scheduler


async def shutdown_background_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Morning Heartbeat shut down.")
    _scheduler = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler
