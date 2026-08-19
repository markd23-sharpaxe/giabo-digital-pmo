"""SQLAlchemy 2.0 ORM models and Pydantic v2 schemas for the Digital PMO swarm.

Mirrors `db/schema.sql` exactly. Column-for-column parity with that file is
intentional: this module is the Python-side source of truth used by Alembic
autogeneration, the MAF agent tools, and the FastAPI/Teams-bot request layer.

Layout:
    1. Python enums (shared by the ORM columns and the Pydantic schemas)
    2. SQLAlchemy declarative ORM models
    3. Pydantic v2 schemas (Base / Create / Read) per entity
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# =============================================================================
# 1. ENUMS
# =============================================================================


class PlanTier(str, enum.Enum):
    """Azure Marketplace plan tiers (02-maf-billing-gates.mdc, Section 1)."""

    FREE_TRIAL = "free_trial"
    PAID_MONTHLY = "paid_monthly"


class SwarmStatus(str, enum.Enum):
    """Billing-gate-driven execution state. TRIAL_EXPIRED is the hard halt."""

    PROVISIONING = "provisioning"
    ACTIVE = "active"
    TRIAL_EXPIRED = "trial_expired"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class ProjectStatus(str, enum.Enum):
    """New = Initiation Phase (cold start); Initiated = Steady-State Monitoring."""

    NEW = "new"
    INITIATED = "initiated"


class ArtifactType(str, enum.Enum):
    """The 9 RAID(+SDCL) artifact families (03-maf-writeback-agents.mdc)."""

    RISK = "risk"
    ACTION = "action"
    ISSUE = "issue"
    ASSUMPTION = "assumption"
    DEPENDENCY = "dependency"
    SPRINT = "sprint"
    DECISION = "decision"
    CHANGE = "change"
    LESSON = "lesson"


class AgentTier(str, enum.Enum):
    """Which agent tier produced an `agent_executions` row."""

    READONLY = "readonly"
    WRITEBACK = "writeback"
    CRON = "cron"


class TriggerType(str, enum.Enum):
    """What caused the agent node to fire."""

    DELTA_DISPATCH = "delta_dispatch"
    CRON_SWEEP = "cron_sweep"
    TEAMS_INTERACTION = "teams_interaction"
    MANUAL = "manual"


class ExecutionStatus(str, enum.Enum):
    """Outcome of an agent node execution, including the schema retry loop."""

    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SCHEMA_RETRY_EXHAUSTED = "schema_retry_exhausted"
    CIRCUIT_BROKEN = "circuit_broken"


# =============================================================================
# 2. SQLALCHEMY ORM MODELS
# =============================================================================


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """SQLAlchemy's Enum type binds using the Python member *name* by
    default (e.g. ``FREE_TRIAL``); our Postgres enum types store the lower-
    case `.value` strings (e.g. ``free_trial``) to match schema.sql exactly.
    `values_callable` makes SQLAlchemy send `.value` instead.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda obj: [member.value for member in obj])


class Tenant(Base):
    """One row per Azure Marketplace SaaS subscription / customer tenant."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    azure_subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    azure_customer_tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    azure_plan_id: Mapped[Optional[str]] = mapped_column(Text)
    organization_name: Mapped[str] = mapped_column(Text, nullable=False)

    plan_tier: Mapped[PlanTier] = mapped_column(
        _pg_enum(PlanTier, "plan_tier_enum"), nullable=False, default=PlanTier.FREE_TRIAL
    )
    swarm_status: Mapped[SwarmStatus] = mapped_column(
        _pg_enum(SwarmStatus, "swarm_status_enum"), nullable=False, default=SwarmStatus.PROVISIONING
    )

    trial_start_date: Mapped[Optional[date]] = mapped_column(Date)
    # Generated column, read-only from the ORM side; mirrors schema.sql exactly.
    trial_end_date: Mapped[Optional[date]] = mapped_column(Date, Computed("trial_start_date + 14", persisted=True))

    # Generated column derived from plan_tier ($20 trial / $350 paid) -- read-only.
    monthly_token_allowance_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        Computed("CASE WHEN plan_tier = 'paid_monthly' THEN 350.00 ELSE 20.00 END", persisted=True),
    )

    raw_token_spend_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    billed_overage_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    current_billing_period_start: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("date_trunc('month', now())::date")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    agent_executions: Mapped[list["AgentExecution"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    token_ledger_entries: Mapped[list["TokenLedgerEntry"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "plan_tier <> 'free_trial' OR trial_start_date IS NOT NULL",
            name="chk_trial_dates_present",
        ),
        CheckConstraint("raw_token_spend_usd >= 0", name="chk_raw_spend_nonnegative"),
    )


class Project(Base):
    """Project baselines and lifecycle state, ingested from a SharePoint site."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    sharepoint_site_id: Mapped[Optional[str]] = mapped_column(Text)
    sharepoint_site_url: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[ProjectStatus] = mapped_column(
        _pg_enum(ProjectStatus, "project_status_enum"), nullable=False, default=ProjectStatus.NEW
    )

    baseline_aims: Mapped[Optional[str]] = mapped_column(Text)
    baseline_goals: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    baseline_objectives: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    baseline_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    baseline_start_date: Mapped[Optional[date]] = mapped_column(Date)
    baseline_end_date: Mapped[Optional[date]] = mapped_column(Date)

    sponsor_name: Mapped[Optional[str]] = mapped_column(Text)
    sponsor_entra_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    project_manager_name: Mapped[Optional[str]] = mapped_column(Text)
    project_manager_entra_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    eom_checkpoint_day: Mapped[Optional[int]] = mapped_column(SmallInteger)
    golden_thread_last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="projects")
    artifacts: Mapped[list["PmoArtifact"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    document_cache_entries: Mapped[list["DocumentCache"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "sharepoint_site_id", name="uq_projects_tenant_site"),
        CheckConstraint("eom_checkpoint_day BETWEEN 1 AND 31", name="chk_eom_checkpoint_day_range"),
    )


class PmoArtifact(Base):
    """Unified RAID + Sprints/Decisions/Changes/Lessons artifact log.

    Primary key is a deterministic, application-generated string (e.g.
    ``ACTION-EOM-<hash>-2026-08``) so writebacks are idempotent via
    ``ON CONFLICT (id) DO NOTHING/UPDATE``.
    """

    __tablename__ = "pmo_artifacts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    artifact_type: Mapped[ArtifactType] = mapped_column(_pg_enum(ArtifactType, "artifact_type_enum"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Deliberately free-text: status vocab differs per artifact_type.
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")

    owner_entra_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    source_agent_key: Mapped[str] = mapped_column(Text, nullable=False)

    severity: Mapped[Optional[str]] = mapped_column(Text)
    raised_date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    related_artifact_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("pmo_artifacts.id", ondelete="SET NULL")
    )

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="artifacts")
    related_artifact: Mapped[Optional["PmoArtifact"]] = relationship(remote_side=[id])


class Task(Base):
    """First-class task/schedule entity (Phase 7). Backs the Dynamic Chasing
    Engine's priority scoring and the PMP Worker's progress writeback --
    distinct from the RAID log in `PmoArtifact`, which has no 'task' type.
    """

    __tablename__ = "tasks"

    # Business key (e.g. 'TSK-001'), not a generated UUID -- matches the
    # `task_id` strings LLM workers already extract in TaskProgressPayload /
    # BlockerPayload.
    id: Mapped[str] = mapped_column(Text, primary_key=True)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    assignee_name: Mapped[Optional[str]] = mapped_column(Text)
    assignee_entra_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    status: Mapped[str] = mapped_column(Text, nullable=False, default="in_progress")
    percent_complete: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    actual_hours_spent: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=Decimal("0"))
    is_critical_path: Mapped[bool] = mapped_column(nullable=False, default=False)
    critical_path_impact: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    linked_risks_severity: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status_summary: Mapped[Optional[str]] = mapped_column(Text)

    deadline: Mapped[Optional[date]] = mapped_column(Date)
    # Dynamic Chasing Engine's 24h fatigue-cooldown anchor; NULL = never contacted.
    last_contact_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="tasks")

    __table_args__ = (
        CheckConstraint("percent_complete BETWEEN 0 AND 100", name="chk_tasks_percent_complete_range"),
        CheckConstraint("critical_path_impact BETWEEN 1 AND 10", name="chk_tasks_critical_path_impact_range"),
        CheckConstraint("linked_risks_severity BETWEEN 1 AND 10", name="chk_tasks_linked_risks_severity_range"),
    )


class DocumentCache(Base):
    """Content-addressed cache of extracted SharePoint content, keyed by SHA-256."""

    __tablename__ = "document_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)

    sharepoint_drive_id: Mapped[Optional[str]] = mapped_column(Text)
    sharepoint_item_id: Mapped[str] = mapped_column(Text, nullable=False)
    item_path: Mapped[Optional[str]] = mapped_column(Text)
    delta_token: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text, nullable=False, default="document")

    raw_content: Mapped[Optional[str]] = mapped_column(Text)
    extracted_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    sharepoint_last_modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="document_cache_entries")

    __table_args__ = (
        UniqueConstraint("project_id", "sharepoint_item_id", name="uq_document_cache_project_item"),
    )


class AgentExecution(Base):
    """Audit trail of every MAF agent node invocation."""

    __tablename__ = "agent_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )

    agent_key: Mapped[str] = mapped_column(Text, nullable=False)
    agent_tier: Mapped[AgentTier] = mapped_column(_pg_enum(AgentTier, "agent_tier_enum"), nullable=False)
    trigger_type: Mapped[TriggerType] = mapped_column(_pg_enum(TriggerType, "trigger_type_enum"), nullable=False)

    input_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    output: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    status: Mapped[ExecutionStatus] = mapped_column(
        _pg_enum(ExecutionStatus, "execution_status_enum"), nullable=False, default=ExecutionStatus.IN_PROGRESS
    )
    # Ties to the Token Loop Limit: max 3 schema self-correction attempts.
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    model_deployment: Mapped[Optional[str]] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="agent_executions")
    token_ledger_entries: Mapped[list["TokenLedgerEntry"]] = relationship(back_populates="agent_execution")

    __table_args__ = (
        CheckConstraint("retry_count BETWEEN 0 AND 3", name="chk_retry_count_range"),
    )


class TokenLedgerEntry(Base):
    """Per-call raw token usage, overage-adjusted cost, and metering emission status."""

    __tablename__ = "token_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_executions.id", ondelete="SET NULL")
    )

    prompt_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    # Generated column, read-only from the ORM side; mirrors schema.sql exactly.
    total_tokens: Mapped[Optional[int]] = mapped_column(Computed("prompt_tokens + completion_tokens", persisted=True))

    raw_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    # 3x overage multiplier once a paid_monthly tenant exceeds the $350 allowance.
    overage_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("1.00"))
    # Generated column, read-only from the ORM side; mirrors schema.sql exactly.
    billable_cost_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6), Computed("raw_cost_usd * overage_multiplier", persisted=True)
    )
    is_overage: Mapped[bool] = mapped_column(nullable=False, default=False)

    azure_metering_emitted: Mapped[bool] = mapped_column(nullable=False, default=False)
    azure_metering_emission_id: Mapped[Optional[str]] = mapped_column(Text)
    azure_metering_emitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    billing_period: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("date_trunc('month', now())::date")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="token_ledger_entries")
    agent_execution: Mapped[Optional["AgentExecution"]] = relationship(back_populates="token_ledger_entries")

    __table_args__ = (
        CheckConstraint("prompt_tokens >= 0", name="chk_prompt_tokens_nonnegative"),
        CheckConstraint("completion_tokens >= 0", name="chk_completion_tokens_nonnegative"),
        CheckConstraint("raw_cost_usd >= 0", name="chk_raw_cost_nonnegative"),
        CheckConstraint("overage_multiplier >= 1.00", name="chk_overage_multiplier_min"),
    )


# =============================================================================
# 3. PYDANTIC V2 SCHEMAS
#
# Convention per entity: `<Entity>Base` (shared fields) -> `<Entity>Create`
# (input payload) -> `<Entity>Read` (output payload, adds server-owned fields
# and `from_attributes=True` so it can be built directly from the ORM object).
# =============================================================================


class TenantBase(BaseModel):
    azure_subscription_id: uuid.UUID
    azure_customer_tenant_id: uuid.UUID
    azure_plan_id: Optional[str] = None
    organization_name: str
    plan_tier: PlanTier = PlanTier.FREE_TRIAL
    trial_start_date: Optional[date] = None


class TenantCreate(TenantBase):
    pass


class TenantRead(TenantBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    swarm_status: SwarmStatus
    trial_end_date: Optional[date] = None
    monthly_token_allowance_usd: Optional[Decimal] = None
    raw_token_spend_usd: Decimal
    billed_overage_usd: Decimal
    current_billing_period_start: date
    created_at: datetime
    updated_at: datetime


class ProjectBase(BaseModel):
    tenant_id: uuid.UUID
    name: str
    sharepoint_site_id: Optional[str] = None
    sharepoint_site_url: Optional[str] = None
    baseline_aims: Optional[str] = None
    baseline_goals: list[Any] = Field(default_factory=list)
    baseline_objectives: list[Any] = Field(default_factory=list)
    baseline_budget: Optional[Decimal] = None
    baseline_start_date: Optional[date] = None
    baseline_end_date: Optional[date] = None
    sponsor_name: Optional[str] = None
    sponsor_entra_id: Optional[uuid.UUID] = None
    project_manager_name: Optional[str] = None
    project_manager_entra_id: Optional[uuid.UUID] = None
    eom_checkpoint_day: Optional[int] = Field(default=None, ge=1, le=31)


class ProjectCreate(ProjectBase):
    status: ProjectStatus = ProjectStatus.NEW


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ProjectStatus
    golden_thread_last_verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PmoArtifactBase(BaseModel):
    project_id: uuid.UUID
    tenant_id: uuid.UUID
    artifact_type: ArtifactType
    title: str
    description: Optional[str] = None
    status: str = "open"
    owner_entra_id: Optional[uuid.UUID] = None
    source_agent_key: str
    severity: Optional[str] = None
    due_date: Optional[date] = None
    related_artifact_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class PmoArtifactCreate(PmoArtifactBase):
    # Deterministic key supplied by the producing agent, e.g.
    # "ACTION-EOM-<hash>-2026-08".
    id: str
    raised_date: date = Field(default_factory=date.today)


class PmoArtifactRead(PmoArtifactBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    raised_date: date
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TaskBase(BaseModel):
    project_id: uuid.UUID
    tenant_id: uuid.UUID
    task_name: str
    assignee_name: Optional[str] = None
    assignee_entra_id: Optional[uuid.UUID] = None
    status: str = "in_progress"
    percent_complete: int = Field(default=0, ge=0, le=100)
    actual_hours_spent: Decimal = Field(default=Decimal("0"))
    is_critical_path: bool = False
    critical_path_impact: int = Field(default=1, ge=1, le=10)
    linked_risks_severity: int = Field(default=1, ge=1, le=10)
    status_summary: Optional[str] = None
    deadline: Optional[date] = None
    last_contact_timestamp: Optional[datetime] = None


class TaskCreate(TaskBase):
    # Business key supplied by the caller, e.g. "TSK-001".
    id: str


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class DocumentCacheBase(BaseModel):
    project_id: uuid.UUID
    content_hash: str = Field(min_length=64, max_length=64)
    sharepoint_drive_id: Optional[str] = None
    sharepoint_item_id: str
    item_path: Optional[str] = None
    delta_token: Optional[str] = None
    source_type: str = "document"
    raw_content: Optional[str] = None
    extracted_json: Optional[dict[str, Any]] = None
    sharepoint_last_modified_at: Optional[datetime] = None


class DocumentCacheCreate(DocumentCacheBase):
    pass


class DocumentCacheRead(DocumentCacheBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class AgentExecutionBase(BaseModel):
    tenant_id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    agent_key: str
    agent_tier: AgentTier
    trigger_type: TriggerType
    input_snapshot: Optional[dict[str, Any]] = None
    model_deployment: Optional[str] = None


class AgentExecutionCreate(AgentExecutionBase):
    pass


class AgentExecutionRead(AgentExecutionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    output: Optional[dict[str, Any]] = None
    status: ExecutionStatus
    retry_count: int = Field(ge=0, le=3)
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: datetime


class TokenLedgerEntryBase(BaseModel):
    tenant_id: uuid.UUID
    agent_execution_id: Optional[uuid.UUID] = None
    prompt_tokens: int = Field(ge=0, default=0)
    completion_tokens: int = Field(ge=0, default=0)
    raw_cost_usd: Decimal = Field(ge=0)
    overage_multiplier: Decimal = Field(ge=Decimal("1.00"), default=Decimal("1.00"))
    is_overage: bool = False


class TokenLedgerEntryCreate(TokenLedgerEntryBase):
    pass


class TokenLedgerEntryRead(TokenLedgerEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    total_tokens: Optional[int] = None
    billable_cost_usd: Optional[Decimal] = None
    azure_metering_emitted: bool
    azure_metering_emission_id: Optional[str] = None
    azure_metering_emitted_at: Optional[datetime] = None
    billing_period: date
    created_at: datetime
