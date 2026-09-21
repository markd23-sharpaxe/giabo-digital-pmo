"""Microsoft Partner Center SaaS Fulfillment API v2 -- FastAPI router.

Two endpoints, both configured directly in Partner Center's "Technical
configuration" for this offer:

    GET  /marketplace/landing         Landing Page URL. Partner Center
                                       redirects a customer's browser here
                                       right after purchase (and again if
                                       they revisit "Manage" in Azure/
                                       Teams admin), with `?token=<opaque
                                       purchase token>`. Resolves +
                                       activates the subscription and
                                       upserts `tenants`.
    POST/PATCH /api/marketplace/webhook  Webhook URL. Microsoft calls this
                                       (documented as POST -- PATCH is also
                                       wired to the same handler per this
                                       integration's spec) on every
                                       subscribe/change-plan/suspend/
                                       reinstate/unsubscribe event, so
                                       `tenants.swarm_status`/`plan_tier`
                                       stay in sync without the customer
                                       ever visiting the landing page again.
                                       This is what makes `core.billing`'s
                                       Phase 2 gates (`check_credit_balance`
                                       halting on SUSPENDED/CANCELLED,
                                       `assert_pilot_feature_access` gating
                                       on `plan_tier`) reflect Microsoft's
                                       real, current billing state.

Business/DB logic (the `planId` -> `PlanTier` mapping, the
`saasSubscriptionStatus` -> `SwarmStatus` mapping, and the `tenants` upsert
itself) lives here, not in `core/marketplace_client.py` -- that module is a
pure Microsoft-API client with no database knowledge, mirroring the
`core/graph_client.py` / `core/sharepoint_sync.py` split.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.templates import templates
from core.marketplace_client import (
    MarketplaceApiError,
    activate_subscription,
    get_subscription,
    resolve_subscription_token,
    update_operation_status,
)
from db.models import PlanTier, SwarmStatus, Tenant
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# planId / saasSubscriptionStatus -> our own enums
# =============================================================================


def _map_plan_id_to_tier(plan_id: str) -> PlanTier:
    """Map a Partner Center `planId` (offer-specific, authored when the
    offer's plans were created) to our internal `PlanTier`.

    Configure the authoritative list via the `MARKETPLACE_TRIAL_PLAN_IDS`
    env var (comma-separated Partner Center plan IDs that are this offer's
    Free Trial plan(s)) once the real offer's plan IDs are known. Falls back
    to a `"trial" in plan_id` heuristic when that isn't set, purely so
    onboarding doesn't hard-fail before it's configured -- this heuristic is
    NOT something to rely on once real plan IDs exist.
    """
    configured = {p.strip() for p in os.environ.get("MARKETPLACE_TRIAL_PLAN_IDS", "").split(",") if p.strip()}
    if configured:
        return PlanTier.FREE_TRIAL if plan_id in configured else PlanTier.PAID_MONTHLY
    return PlanTier.FREE_TRIAL if "trial" in (plan_id or "").lower() else PlanTier.PAID_MONTHLY


# `saasSubscriptionStatus` values per the SaaS Fulfillment API v2 contract.
# Anything not in this map (a status Microsoft adds later, or an unexpected
# value) is deliberately left unmapped -- `_upsert_tenant_from_subscription`
# leaves `swarm_status` untouched rather than guess.
_SAAS_STATUS_TO_SWARM_STATUS: dict[str, SwarmStatus] = {
    "PendingFulfillmentStart": SwarmStatus.PROVISIONING,
    "Subscribed": SwarmStatus.ACTIVE,
    "Suspended": SwarmStatus.SUSPENDED,
    "Unsubscribed": SwarmStatus.CANCELLED,
}


def _upsert_tenant_from_subscription(session: Session, subscription: dict[str, Any]) -> Tenant:
    """Land Microsoft's authoritative `GET subscription` response onto our
    `tenants` row -- shared by both the landing page (first purchase) and
    the webhook (every later change/cancel event), since both ultimately
    need the same reconciliation.

    Looks up by `azure_subscription_id` (unique); creates a new tenant row
    on first purchase, otherwise updates the existing one in place.
    `trial_start_date` is set once, at creation, and never touched again --
    the 14-day trial window (`db/schema.sql`'s `trial_end_date` generated
    column) is anchored to first activation, not to any later resync.
    """
    subscription_id = subscription.get("id")
    if not subscription_id:
        raise MarketplaceApiError(f"Subscription payload missing 'id': {subscription!r}")

    beneficiary = subscription.get("beneficiary") or {}
    customer_tenant_id = beneficiary.get("tenantId")
    if not customer_tenant_id:
        raise MarketplaceApiError(f"Subscription {subscription_id} missing beneficiary.tenantId: {subscription!r}")

    plan_id = subscription.get("planId") or ""
    plan_tier = _map_plan_id_to_tier(plan_id)
    saas_status = subscription.get("saasSubscriptionStatus") or ""
    swarm_status = _SAAS_STATUS_TO_SWARM_STATUS.get(saas_status)
    # Marketplace-chosen display name at purchase time; not a guaranteed
    # "real" org name (we have no Graph access into the customer's tenant
    # yet), but the best available label until then.
    organization_name = subscription.get("name") or f"Tenant {customer_tenant_id}"

    tenant = session.execute(
        select(Tenant).where(Tenant.azure_subscription_id == UUID(str(subscription_id)))
    ).scalar_one_or_none()

    if tenant is None:
        tenant = Tenant(
            azure_subscription_id=UUID(str(subscription_id)),
            azure_customer_tenant_id=UUID(str(customer_tenant_id)),
            azure_plan_id=plan_id or None,
            organization_name=organization_name,
            plan_tier=plan_tier,
            swarm_status=swarm_status or SwarmStatus.PROVISIONING,
            trial_start_date=date.today() if plan_tier is PlanTier.FREE_TRIAL else None,
        )
        session.add(tenant)
        logger.info(
            "marketplace: onboarding new tenant for subscription_id=%s plan_tier=%s",
            subscription_id,
            plan_tier.value,
        )
    else:
        tenant.azure_customer_tenant_id = UUID(str(customer_tenant_id))
        tenant.azure_plan_id = plan_id or tenant.azure_plan_id
        tenant.organization_name = organization_name
        if tenant.plan_tier is not plan_tier:
            logger.info(
                "marketplace: tenant %s plan_tier %s -> %s", tenant.id, tenant.plan_tier.value, plan_tier.value
            )
        tenant.plan_tier = plan_tier
        if swarm_status is not None and tenant.swarm_status is not swarm_status:
            logger.info(
                "marketplace: tenant %s swarm_status %s -> %s",
                tenant.id,
                tenant.swarm_status.value,
                swarm_status.value,
            )
        if swarm_status is not None:
            tenant.swarm_status = swarm_status

    session.flush()
    return tenant


# =============================================================================
# GET /marketplace/landing
# =============================================================================


@router.get("/marketplace/landing")
async def marketplace_landing(
    request: Request,
    token: str = Query(..., description="Opaque purchase token Partner Center appends to the redirect."),
):
    """Partner Center's configured Landing Page URL.

    Flow: resolve the purchase token -> fetch the authoritative subscription
    -> upsert `tenants` -> activate if this is a brand-new purchase
    (`saasSubscriptionStatus == "PendingFulfillmentStart"`) -> re-fetch once
    more to confirm activation succeeded before telling the customer they're
    provisioned. Renders `templates/landing.html` for both the success and
    failure paths (a `success` flag in the context picks which card shows).
    """
    try:
        resolved = await resolve_subscription_token(token)
        subscription_id = str(resolved["id"])
        subscription = await get_subscription(subscription_id)

        with get_session() as session:
            tenant = _upsert_tenant_from_subscription(session, subscription)
            tenant_id, plan_tier = tenant.id, tenant.plan_tier

        if subscription.get("saasSubscriptionStatus") == "PendingFulfillmentStart":
            await activate_subscription(subscription_id, subscription.get("planId") or "")
            # Re-fetch (rather than assume) so `swarm_status` reflects what
            # Microsoft actually confirms, not what we hope just happened.
            subscription = await get_subscription(subscription_id)
            with get_session() as session:
                tenant = _upsert_tenant_from_subscription(session, subscription)

        organization_name, plan_tier = tenant.organization_name, tenant.plan_tier
        tenant_id = tenant.id

    except MarketplaceApiError as exc:
        logger.exception("marketplace landing: Fulfillment API call failed")
        return templates.TemplateResponse(
            request,
            "landing.html",
            {"success": False, "error_message": str(exc)[:200]},
            status_code=502,
        )
    except Exception:
        logger.exception("marketplace landing: unexpected error")
        return templates.TemplateResponse(
            request,
            "landing.html",
            {"success": False, "error_message": None},
            status_code=500,
        )

    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "success": True,
            "organization_name": organization_name,
            "plan_tier": plan_tier.value,
            "tenant_id": str(tenant_id),
        },
    )


# =============================================================================
# POST/PATCH /api/marketplace/webhook
# =============================================================================


class MarketplaceWebhookPayload(BaseModel):
    """Wire shape of Microsoft's webhook notification body.

    Field names are aliased to Microsoft's exact camelCase JSON keys
    (`ConfigDict(populate_by_name=True)` also allows constructing one by the
    snake_case attribute name directly, e.g. in tests).
    """

    model_config = ConfigDict(populate_by_name=True)

    operation_id: str = Field(alias="id")
    activity_id: Optional[str] = Field(default=None, alias="activityId")
    subscription_id: str = Field(alias="subscriptionId")
    plan_id: Optional[str] = Field(default=None, alias="planId")
    action: Literal["Unsubscribe", "ChangePlan", "ChangeQuantity", "Suspend", "Reinstate", "Renew", "Transfer"]
    status: Optional[str] = None
    time_stamp: Optional[str] = Field(default=None, alias="timeStamp")


async def _handle_marketplace_webhook(request: Request) -> JSONResponse:
    """Shared handler for both the `POST` and `PATCH` routes below.

    Re-syncs from a fresh `get_subscription` call rather than trusting the
    webhook body's fields directly (Microsoft's own guidance: treat the
    webhook as a "something changed" ping), then acknowledges back to
    Microsoft via `update_operation_status`.

    Response codes are chosen so Microsoft's own webhook retry behavior
    works *for* us: a transient Fulfillment API failure returns 5xx/502 (so
    Microsoft retries later); a permanently-unprocessable payload returns
    200 with an error flag in the body (retrying an unfixable payload
    forever helps no one, but it's logged loudly here for a human).
    """
    raw_body = await request.json()
    try:
        payload = MarketplaceWebhookPayload.model_validate(raw_body)
    except ValidationError:
        logger.exception("marketplace webhook: malformed payload: %r", raw_body)
        return JSONResponse(status_code=400, content={"error": "InvalidPayload"})

    logger.info(
        "marketplace webhook: action=%s subscription_id=%s operation_id=%s",
        payload.action,
        payload.subscription_id,
        payload.operation_id,
    )

    try:
        subscription = await get_subscription(payload.subscription_id)
    except MarketplaceApiError:
        logger.exception("marketplace webhook: failed to fetch subscription_id=%s", payload.subscription_id)
        return JSONResponse(status_code=502, content={"error": "MarketplaceApiUnavailable"})

    try:
        with get_session() as session:
            _upsert_tenant_from_subscription(session, subscription)
    except MarketplaceApiError:
        # Permanent data problem (e.g. malformed subscription), not something
        # Microsoft resending the same webhook will fix -- acknowledge so it
        # stops retrying, but this is logged loudly for a human to look at.
        logger.exception(
            "marketplace webhook: could not reconcile subscription_id=%s -- acknowledging anyway",
            payload.subscription_id,
        )
        return JSONResponse(status_code=200, content={"status": "acknowledged_with_errors"})
    except Exception:
        logger.exception("marketplace webhook: unexpected error reconciling subscription_id=%s", payload.subscription_id)
        return JSONResponse(status_code=500, content={"error": "InternalServerError"})

    try:
        await update_operation_status(payload.subscription_id, payload.operation_id, "Success")
    except MarketplaceApiError:
        # Best-effort: our own tenant state is already correctly updated
        # above, so a failure to acknowledge back to Microsoft shouldn't
        # turn into a 5xx that makes Microsoft retry a change we've already
        # applied.
        logger.warning(
            "marketplace webhook: failed to PATCH operation status for subscription_id=%s operation_id=%s "
            "(tenant state was still updated)",
            payload.subscription_id,
            payload.operation_id,
        )

    return JSONResponse(status_code=200, content={"status": "acknowledged"})


@router.post("/api/marketplace/webhook")
async def marketplace_webhook_post(request: Request) -> JSONResponse:
    return await _handle_marketplace_webhook(request)


@router.patch("/api/marketplace/webhook")
async def marketplace_webhook_patch(request: Request) -> JSONResponse:
    """Same handler as the `POST` route above. Microsoft's documented
    webhook call is a `POST`; `PATCH` is wired here too per this
    integration's explicit spec, in case a specific Partner Center
    configuration or API revision calls it that way instead.
    """
    return await _handle_marketplace_webhook(request)
