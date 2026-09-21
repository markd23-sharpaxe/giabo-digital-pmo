"""Microsoft 365 Copilot Declarative Agent API Bridge (Declarative Agent
Architecture Pivot).

FastAPI routes called directly by the `ai-plugin.json` API-plugin manifest's
`OpenApi` runtime, per `appPackage/openapi.yaml` -- this is the entire
interactive surface for creating and inspecting projects now that the
standalone Jinja2 marketing homepage/tenant dashboard (formerly `api/web.py`)
is gone. `POST /api/projects/create`'s response is what
`appPackage/projectSetupCard.json` data-binds against via the plugin's
`response_semantics.static_template`; that card's own `Action.Execute` button
calls `GET /api/projects/brief` again through the same plugin runtime --
no Bot Framework invoke-activity code is involved anywhere in this file.

No authentication. `tenant_id`/`project_id` are optional everywhere (the
same "capability ID" trust model `api/marketplace.py`'s tenant upsert and
the (now-removed) dashboard already relied on, just now zero-config by
default): when a caller -- in practice, the M365 Copilot declarative agent,
which should never have to ask a chat user for a raw UUID -- omits one,
`_resolve_default_tenant`/`_resolve_default_project` below fall back to the
most recently active tenant/project in the live database. An explicit ID
still always wins and is still 404'd if it doesn't exist; only the *absence*
of an ID triggers the fallback. Real Microsoft Entra ID SSO (so "most
recently active" could become "the caller's own tenant") is a documented
follow-up, not in this pivot's scope.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import AgentExecution, ArtifactType, PmoArtifact, Project, ProjectStatus, SwarmStatus, Tenant
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# =============================================================================
# Zero-config auto-resolution helpers
#
# Used by every operation below whenever tenant_id/project_id is omitted --
# a Copilot chat user saying "set up a project" or "what's my usage" has no
# reason to know (or be asked for) a raw UUID.
# =============================================================================


def _resolve_default_tenant(session: Session) -> Tenant:
    """The most recently active tenant, i.e. the ACTIVE tenant with the
    newest `updated_at`. Deliberately excludes provisioning/trial_expired/
    suspended/cancelled tenants -- defaulting a Copilot action onto a tenant
    that can't actually use the swarm right now would be more confusing
    than just asking for an id.
    """
    tenant = (
        session.execute(
            select(Tenant).where(Tenant.swarm_status == SwarmStatus.ACTIVE).order_by(Tenant.updated_at.desc()).limit(1)
        )
        .scalars()
        .first()
    )
    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="No tenant_id was given and no active tenant exists to default to. Please provide a tenant_id.",
        )
    return tenant


def _resolve_default_project(session: Session) -> Project:
    """The most recently active project, i.e. the project with the newest
    `updated_at` across all tenants. Unlike tenants, `Project` has no
    active/inactive status field (only `new`/`initiated`), so "most
    recently active" here means "most recently touched", full stop.
    """
    project = session.execute(select(Project).order_by(Project.updated_at.desc()).limit(1)).scalars().first()
    if project is None:
        raise HTTPException(
            status_code=404,
            detail="No project_id was given and no project exists to default to. Please provide a project_id.",
        )
    return project


# =============================================================================
# POST /api/projects/create
# =============================================================================


class ProjectCreateRequest(BaseModel):
    tenant_id: Optional[UUID] = Field(
        default=None, description="Omit to default to the most recently active tenant."
    )
    name: str
    sharepoint_site_id: Optional[str] = None
    digital_employee_name: Optional[str] = None
    digital_employee_email: Optional[str] = None


class ProjectCreateResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    status: str
    sharepoint_site_id: Optional[str] = None
    digital_employee_name: Optional[str] = None
    digital_employee_email: Optional[str] = None
    created_at: datetime


@router.post("/projects/create", response_model=ProjectCreateResponse)
async def create_project(payload: ProjectCreateRequest) -> ProjectCreateResponse:
    """Creates a new project scoped to `tenant_id`. If `tenant_id` is
    omitted, defaults to the most recently active tenant. 404s if an
    explicitly-given `tenant_id` doesn't exist, or if it was omitted and no
    active tenant exists to default to -- either way, never silently
    creates an orphaned project.
    """
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name must not be empty")

    with get_session() as session:
        if payload.tenant_id is not None:
            tenant = session.get(Tenant, payload.tenant_id)
            if tenant is None:
                raise HTTPException(status_code=404, detail=f"tenant_id {payload.tenant_id} not found")
        else:
            tenant = _resolve_default_tenant(session)

        project = Project(
            tenant_id=tenant.id,
            name=name,
            sharepoint_site_id=(payload.sharepoint_site_id or None),
            digital_employee_name=(payload.digital_employee_name or None),
            digital_employee_email=(payload.digital_employee_email or None),
            status=ProjectStatus.NEW,
        )
        session.add(project)
        session.flush()
        # `id`/`created_at` are server-generated (gen_random_uuid()/now());
        # explicitly refresh rather than trust the in-memory object, since
        # whether the ORM auto-populates server_default columns after an
        # INSERT depends on dialect/version RETURNING behavior we shouldn't
        # rely on implicitly for a value returned straight to the caller.
        session.refresh(project)

        response = ProjectCreateResponse(
            id=project.id,
            tenant_id=project.tenant_id,
            name=project.name,
            status=project.status.value,
            sharepoint_site_id=project.sharepoint_site_id,
            digital_employee_name=project.digital_employee_name,
            digital_employee_email=project.digital_employee_email,
            created_at=project.created_at,
        )

    logger.info("copilot api: created project %s for tenant_id=%s", response.id, response.tenant_id)
    return response


# =============================================================================
# GET /api/projects/brief
# =============================================================================

# "actions parsed, risks flagged" per the request -- deliberately narrower
# than the full RAID+SDCL family (issues/assumptions/dependencies/sprints/
# decisions/changes/lessons also live in pmo_artifacts, but aren't asked for
# in this brief).
_BRIEF_ARTIFACT_LIMIT = 20
_BRIEF_EXECUTION_LIMIT = 10


class ProjectBriefResponse(BaseModel):
    project_id: UUID
    project_name: str
    markdown: str = Field(description="Structured markdown roll-up of risks, actions, and the swarm audit log.")


def _format_artifact_line(artifact: PmoArtifact) -> str:
    severity = f"[{artifact.severity}] " if artifact.severity else ""
    due = f" (due {artifact.due_date.isoformat()})" if artifact.due_date else ""
    description = artifact.description or "No description provided."
    return f"- {severity}**{artifact.title}** -- {description}{due}"


def _format_execution_line(execution: AgentExecution) -> str:
    when = execution.started_at.strftime("%Y-%m-%d %H:%M UTC") if execution.started_at else "unknown time"
    return f"- `{when}` **{execution.agent_key}** ({execution.agent_tier.value}) -> {execution.status.value}"


@router.get("/projects/brief", response_model=ProjectBriefResponse)
async def get_project_brief(
    project_id: Optional[UUID] = Query(
        default=None, description="Omit to default to the most recently active project."
    ),
) -> ProjectBriefResponse:
    """Structured markdown governance brief: open risks, open actions, and
    the most recent swarm agent-execution audit log entries for this
    project. Returned as a `markdown` string field -- Copilot renders it
    directly as the chat response.

    `project_id` is a query parameter, not a path segment, specifically so
    it can be optional -- the OpenAPI 3.0 spec mandates `required: true`
    for every path parameter, which would make an "omit to auto-resolve"
    contract impossible to express if this stayed `/projects/{project_id}/brief`.
    """
    with get_session() as session:
        if project_id is not None:
            project = session.get(Project, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail=f"project {project_id} not found")
        else:
            project = _resolve_default_project(session)

        resolved_project_id = project.id

        risks = (
            session.execute(
                select(PmoArtifact)
                .where(PmoArtifact.project_id == resolved_project_id, PmoArtifact.artifact_type == ArtifactType.RISK)
                .order_by(PmoArtifact.raised_date.desc())
                .limit(_BRIEF_ARTIFACT_LIMIT)
            )
            .scalars()
            .all()
        )
        actions = (
            session.execute(
                select(PmoArtifact)
                .where(PmoArtifact.project_id == resolved_project_id, PmoArtifact.artifact_type == ArtifactType.ACTION)
                .order_by(PmoArtifact.raised_date.desc())
                .limit(_BRIEF_ARTIFACT_LIMIT)
            )
            .scalars()
            .all()
        )
        executions = (
            session.execute(
                select(AgentExecution)
                .where(AgentExecution.project_id == resolved_project_id)
                .order_by(AgentExecution.started_at.desc())
                .limit(_BRIEF_EXECUTION_LIMIT)
            )
            .scalars()
            .all()
        )

        project_name = project.name
        project_status = project.status.value

    risk_lines = "\n".join(_format_artifact_line(a) for a in risks) or "_No open risks._"
    action_lines = "\n".join(_format_artifact_line(a) for a in actions) or "_No open actions._"
    execution_lines = "\n".join(_format_execution_line(e) for e in executions) or "_No agent activity recorded yet._"

    markdown = (
        f"# Project Brief: {project_name}\n\n"
        f"**Status:** {project_status}\n\n"
        f"## Risks\n{risk_lines}\n\n"
        f"## Actions\n{action_lines}\n\n"
        f"## Swarm Audit Log (most recent {_BRIEF_EXECUTION_LIMIT})\n{execution_lines}\n"
    )

    return ProjectBriefResponse(project_id=resolved_project_id, project_name=project_name, markdown=markdown)


# =============================================================================
# GET /api/usage/telemetry
# =============================================================================


class UsageTelemetryResponse(BaseModel):
    tenant_id: UUID
    organization_name: str
    plan_tier: str
    swarm_status: str
    active_project_count: int
    raw_token_spend_usd: Decimal
    monthly_token_allowance_usd: Decimal
    billed_overage_usd: Decimal
    is_overage: bool
    trial_end_date: Optional[date] = None


@router.get("/usage/telemetry", response_model=UsageTelemetryResponse)
async def get_usage_telemetry(
    tenant_id: Optional[UUID] = Query(
        default=None, description="Omit to default to the most recently active tenant."
    ),
) -> UsageTelemetryResponse:
    """Plan tier, swarm health, active project count, and metered
    token/overage tracking -- the same figures the (now-removed) dashboard
    showed, backing `core.billing`'s Phase 2 gates. If `tenant_id` is
    omitted, defaults to the most recently active tenant.
    """
    with get_session() as session:
        if tenant_id is not None:
            tenant = session.get(Tenant, tenant_id)
            if tenant is None:
                raise HTTPException(status_code=404, detail=f"tenant_id {tenant_id} not found")
        else:
            tenant = _resolve_default_tenant(session)

        active_project_count = session.execute(
            select(func.count()).select_from(Project).where(Project.tenant_id == tenant.id)
        ).scalar_one()

        allowance = tenant.monthly_token_allowance_usd or Decimal("0")
        spend = tenant.raw_token_spend_usd or Decimal("0")

        return UsageTelemetryResponse(
            tenant_id=tenant.id,
            organization_name=tenant.organization_name,
            plan_tier=tenant.plan_tier.value,
            swarm_status=tenant.swarm_status.value,
            active_project_count=active_project_count,
            raw_token_spend_usd=spend,
            monthly_token_allowance_usd=allowance,
            billed_overage_usd=tenant.billed_overage_usd or Decimal("0"),
            is_overage=spend > allowance,
            trial_end_date=tenant.trial_end_date,
        )
