"""Typed workflow state for the Digital PMO MAF directed graph.

Implements the State Management requirement of 01-maf-core-orchestrator.mdc:
a single typed State object is threaded through the workflow graph, holding
`delta_payload`, `active_agent_roster`, and an accumulating array of
`outputs`, plus the tenant billing metadata needed by the sequential
billing gates (02-maf-billing-gates.mdc) before any node invokes an Azure
OpenAI model.

`SwarmState` instances are immutable (Pydantic v2 models); executors that
need to "mutate" state should build a new instance via `with_output(...)`
or `model_copy(update=...)` and send that onward via `ctx.send_message()`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from db.models import PlanTier, SwarmStatus

# Agents that the Router Node must NEVER see and that never receive a delta
# dispatch (01-maf-core-orchestrator.mdc, "Excluded Agents"). These are the
# cron/governance sweeps that "bypass the orchestrator graph and run
# deterministically on schedule" (05-maf-cron-governance.mdc) -- they are
# triggered directly by the scheduler, never by the delta-dispatch Router.
DELTA_DISPATCH_EXCLUDED_AGENTS: frozenset[str] = frozenset(
    {
        "governance_auditor",
        "eom_financial_checkpoint",
        "sprint_boundary_watchdog",
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeltaPayload(BaseModel):
    """The SharePoint delta injected into the MAF State (01-maf-core-orchestrator.mdc).

    `extra="allow"` because the raw Graph/SharePoint delta shape varies by
    drive item type (document, list item, page); downstream specialist
    agents read whichever fields their scope cares about.
    """

    model_config = ConfigDict(extra="allow")

    delta_token: Optional[str] = None
    change_type: str = Field(default="update", description="'create' | 'update' | 'delete'")
    site_id: Optional[str] = None
    drive_item_id: Optional[str] = None
    item_path: Optional[str] = None
    content_hash: Optional[str] = None
    raw_content: Optional[str] = None
    extracted_json: Optional[dict[str, Any]] = None
    received_at: datetime = Field(default_factory=_utcnow)


class TenantBillingMetadata(BaseModel):
    """Snapshot of the tenant fields the billing gates evaluate (02-maf-billing-gates.mdc).

    This is a point-in-time copy carried in the graph's State; the gates in
    `core/billing.py` always re-read (and row-lock) the authoritative
    `tenants` row before making a halt/allow decision -- this snapshot is
    for routing/UX context only (e.g. deciding which agents are even
    eligible before spending a DB round trip).
    """

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    plan_tier: PlanTier
    swarm_status: SwarmStatus
    trial_start_date: Optional[date] = None
    trial_end_date: Optional[date] = None
    monthly_token_allowance_usd: Decimal
    raw_token_spend_usd: Decimal
    billed_overage_usd: Decimal
    current_billing_period_start: date


class AgentExecutionOutput(BaseModel):
    """One entry in the State's accumulating `execution_outputs` array."""

    agent_key: str
    execution_id: Optional[uuid.UUID] = None
    status: str = "success"
    output: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    emitted_at: datetime = Field(default_factory=_utcnow)


class SwarmState(BaseModel):
    """The typed State object threaded through the MAF directed graph.

    Holds exactly what 01-maf-core-orchestrator.mdc requires -- `delta_payload`,
    `active_agent_roster`, and an array of `outputs` -- plus `project_id` and
    `tenant_billing` so the Router Node and billing gates never need a second
    lookup mid-graph.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    delta_payload: DeltaPayload
    active_agent_roster: list[str] = Field(default_factory=list)
    execution_outputs: list[AgentExecutionOutput] = Field(default_factory=list)
    tenant_billing: TenantBillingMetadata

    @field_validator("active_agent_roster")
    @classmethod
    def _reject_excluded_agents(cls, roster: list[str]) -> list[str]:
        """Defense in depth: the roster injected into State must already be
        stripped of DELTA_DISPATCH_EXCLUDED_AGENTS by whoever constructs it
        (see `core.workflow.filter_excluded_agents`). This validator makes
        that invariant impossible to violate silently.
        """
        leaked = DELTA_DISPATCH_EXCLUDED_AGENTS.intersection(roster)
        if leaked:
            raise ValueError(
                f"DELTA_DISPATCH_EXCLUDED_AGENTS leaked into active_agent_roster: {sorted(leaked)}"
            )
        return roster

    def with_output(self, output: AgentExecutionOutput) -> "SwarmState":
        """Return a new State with `output` appended to `execution_outputs`."""
        return self.model_copy(update={"execution_outputs": [*self.execution_outputs, output]})

    def with_outputs(self, outputs: list[AgentExecutionOutput]) -> "SwarmState":
        """Return a new State with multiple outputs appended at once (e.g. after
        a parallel specialist-dispatch superstep completes)."""
        if not outputs:
            return self
        return self.model_copy(update={"execution_outputs": [*self.execution_outputs, *outputs]})
