"""Microsoft Partner Center SaaS Fulfillment + Metering API v2 client.

Fulfillment calls stay a pure Microsoft-API client (contrast
`api/marketplace.py`, which owns the `tenants` upsert). Metering adds a
second surface: `submit_usage_batch` is HTTP-only;
`emit_unmetered_token_ledger` queries `token_ledger` and marks rows emitted.

Endpoint contract is the documented SaaS Fulfillment API v2 and Marketplace
Metering Service APIs -- not guessed paths. Corrections worth calling out:

  1. Token endpoint host is `login.microsoftonline.com`, not
     `login.microsoft.com`.
  2. "Resolve a subscription" is `POST /api/saas/subscriptions/resolve`
     with the purchase token in the `x-ms-marketplace-token` HEADER.
  3. Metering batches go to `POST /api/batchUsageEvent` (not
     `/api/services/metering/batches`, which is not a real Metering v2 route).

We authenticate as *our own* app (`MicrosoftAppId`/`MicrosoftAppPassword`)
against the well-known "Microsoft Commercial Marketplace" AAD resource.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, AsyncIterator, Optional
from uuid import UUID

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Well-known, stable AAD application (resource) ID for the Microsoft
# commercial marketplace SaaS Fulfillment APIs -- every ISV authenticates
# against THIS resource/scope, not their own app id or a customer's.
# Documented at https://learn.microsoft.com/en-us/partner-center/marketplace-offers/pc-saas-fulfillment-api-v2#authentication-flow
_MARKETPLACE_RESOURCE_ID = "20e940b3-4c77-4b0b-9a53-9e16a1b010a7"
_MARKETPLACE_SCOPE = f"{_MARKETPLACE_RESOURCE_ID}/.default"

_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_API_BASE = "https://marketplaceapi.microsoft.com/api/saas/subscriptions"
_METERING_BATCH_URL = "https://marketplaceapi.microsoft.com/api/batchUsageEvent"
_API_VERSION = "2018-08-31"
_METERING_BATCH_LIMIT = 25
_DEFAULT_METERING_DIMENSION = "token_compute_overage"

_HTTP_TIMEOUT = 30.0

logger = logging.getLogger(__name__)


class MarketplaceApiError(Exception):
    """Raised for any failed Partner Center SaaS Fulfillment API v2 call
    (token acquisition included). `status_code` is the HTTP status that
    caused it, when there was one -- callers (`api/marketplace.py`) use it
    to decide whether Microsoft's webhook retry should fire again.
    """

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# Process-local client-credentials token cache. One Azure AD app-only token
# per worker process, refreshed ~60s before real expiry -- avoids a token
# round trip on every single Fulfillment API call. Safe under FastAPI's
# single-threaded-per-worker asyncio event loop; multiple uvicorn workers
# each keep their own cache, which is harmless duplicate token requests, not
# a correctness issue.
_cached_token: Optional[str] = None
_cached_token_expires_at: float = 0.0


def _marketplace_aad_tenant() -> str:
    """Our own app's AAD tenant for this client-credentials request -- NOT a
    customer tenant (contrast `core/graph_client.py`). Falls back to
    'common' per this integration's spec, for a purely multi-tenant app
    registration with no fixed home tenant configured.
    """
    return os.environ.get("MicrosoftAppTenantId") or "common"


async def _get_access_token(http_client: httpx.AsyncClient) -> str:
    """Client-credentials AAD v2 access token scoped to the Marketplace
    Fulfillment API resource. Cached in-process; see module docstring.
    """
    global _cached_token, _cached_token_expires_at

    now = time.monotonic()
    if _cached_token is not None and now < _cached_token_expires_at:
        return _cached_token

    url = _TOKEN_URL_TEMPLATE.format(tenant=_marketplace_aad_tenant())
    response = await http_client.post(
        url,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["MicrosoftAppId"],
            "client_secret": os.environ["MicrosoftAppPassword"],
            "scope": _MARKETPLACE_SCOPE,
        },
    )
    if response.status_code != 200:
        raise MarketplaceApiError(
            f"Failed to acquire a Marketplace Fulfillment API access token: "
            f"{response.status_code} {response.text}",
            status_code=response.status_code,
        )

    body = response.json()
    token = body["access_token"]
    expires_in = int(body.get("expires_in", 3600))
    _cached_token = token
    # 60s safety margin so a token never expires mid-flight on a slow call.
    _cached_token_expires_at = now + max(expires_in - 60, 60)
    return token


@asynccontextmanager
async def _client_or(existing: Optional[httpx.AsyncClient]) -> AsyncIterator[httpx.AsyncClient]:
    """Use a caller-supplied `httpx.AsyncClient` (tests inject a mocked
    transport this way) or open a short-lived one -- these are infrequent,
    one-off landing-page/webhook calls, not a bulk loop like
    `sharepoint_sync.py`'s, so there's no benefit to a long-lived shared
    client here.
    """
    if existing is not None:
        yield existing
        return
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        yield client


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def _request(
    http_client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    marketplace_token: Optional[str] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Shared call shape for every Fulfillment API v2 endpoint: bearer token,
    `api-version` query param, and (for `resolve` only) the purchase token
    passed via the `x-ms-marketplace-token` header. Retries transport-level
    failures (DNS/connection resets) up to 3 times; a real 4xx/5xx response
    from Microsoft is NOT retried here -- it's raised immediately as
    `MarketplaceApiError` for the caller to decide what to do.
    """
    token = await _get_access_token(http_client)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if marketplace_token is not None:
        headers["x-ms-marketplace-token"] = marketplace_token

    response = await http_client.request(
        method,
        f"{_API_BASE}{path}",
        headers=headers,
        params={"api-version": _API_VERSION},
        json=json_body,
    )
    if response.status_code >= 400:
        raise MarketplaceApiError(
            f"{method} {path} failed: {response.status_code} {response.text}",
            status_code=response.status_code,
        )
    if not response.content:
        return {}
    return response.json()


async def resolve_subscription_token(
    marketplace_token: str, *, http_client: Optional[httpx.AsyncClient] = None
) -> dict[str, Any]:
    """`POST /resolve` -- exchange the opaque `?token=` query param Partner
    Center appends to the Landing Page URL redirect for the real
    `{id, subscriptionName, offerId, planId}` of the purchase.

    This token is short-lived and single-use -- calling this twice with the
    same token will fail on the second call, which is expected, not a bug.
    """
    async with _client_or(http_client) as client:
        body = await _request(client, "POST", "/resolve", marketplace_token=marketplace_token)
    if not body.get("id"):
        raise MarketplaceApiError(f"Resolve response missing subscription id: {body!r}")
    return body


async def get_subscription(subscription_id: str, *, http_client: Optional[httpx.AsyncClient] = None) -> dict[str, Any]:
    """`GET /{subscriptionId}` -- the authoritative current state of a
    subscription: `beneficiary.tenantId` (the customer's Azure AD tenant --
    maps to `tenants.azure_customer_tenant_id`), `planId`, and
    `saasSubscriptionStatus` (`PendingFulfillmentStart` / `Subscribed` /
    `Suspended` / `Unsubscribed`).

    Called both right after `resolve_subscription_token` (first purchase)
    and again on every webhook notification -- Microsoft's own guidance is
    to treat the webhook body as a "something changed" ping and re-fetch
    here rather than trust the webhook payload's fields directly.
    """
    async with _client_or(http_client) as client:
        return await _request(client, "GET", f"/{subscription_id}")


async def activate_subscription(
    subscription_id: str,
    plan_id: str,
    *,
    quantity: Optional[int] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> None:
    """`POST /{subscriptionId}/activate` -- completes provisioning for a
    subscription whose `saasSubscriptionStatus` is `PendingFulfillmentStart`.
    Must be called exactly once per new purchase; calling it again once the
    subscription is already `Subscribed` is a documented no-op-or-error on
    Microsoft's side, so callers (`api/marketplace.py`) only call this when
    the status actually warrants it.
    """
    body: dict[str, Any] = {"planId": plan_id}
    if quantity is not None:
        body["quantity"] = str(quantity)
    async with _client_or(http_client) as client:
        await _request(client, "POST", f"/{subscription_id}/activate", json_body=body)


async def get_operation(
    subscription_id: str, operation_id: str, *, http_client: Optional[httpx.AsyncClient] = None
) -> dict[str, Any]:
    """`GET /{subscriptionId}/operations/{operationId}` -- full detail on a
    single change/cancel operation a webhook notification referenced by
    `id`/`activityId`. Optional to call (the webhook body plus a fresh
    `get_subscription` is usually enough), but the documented, most-correct
    way to confirm exactly what Microsoft is asking us to acknowledge.
    """
    async with _client_or(http_client) as client:
        return await _request(client, "GET", f"/{subscription_id}/operations/{operation_id}")


async def update_operation_status(
    subscription_id: str,
    operation_id: str,
    status: str,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
) -> None:
    """`PATCH /{subscriptionId}/operations/{operationId}` -- reports back to
    Microsoft that we finished handling a webhook-notified operation.
    `status` is `"Success"` or `"Failure"` per the documented contract.

    This is where PATCH genuinely appears in the real API surface -- our
    *inbound* webhook receiver (`api/marketplace.py`) is a Microsoft-to-us
    POST (Microsoft's documented webhook verb), while this is the matching
    *outbound* us-to-Microsoft PATCH that closes the loop on that
    notification.
    """
    async with _client_or(http_client) as client:
        await _request(
            client,
            "PATCH",
            f"/{subscription_id}/operations/{operation_id}",
            json_body={"status": status},
        )


# =============================================================================
# Marketplace Metering Service v2 -- batch usage events
# =============================================================================


def _metering_dimension() -> str:
    return os.environ.get("MARKETPLACE_METERING_DIMENSION", _DEFAULT_METERING_DIMENSION).strip() or _DEFAULT_METERING_DIMENSION


@dataclass
class MeteringEmitResult:
    """Outcome of one `emit_unmetered_token_ledger` run."""

    events_submitted: int = 0
    rows_emitted: int = 0
    rows_skipped: int = 0
    batches: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class _UsageBucket:
    resource_id: str
    plan_id: str
    effective_start: datetime
    quantity: Decimal
    row_ids: list[int]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp_usage_hour(created_at: datetime, now_utc: datetime) -> datetime:
    """Hour bucket for `effectiveStartTime`, clamped into Microsoft's 24h window."""
    created = _as_utc(created_at).replace(minute=0, second=0, microsecond=0)
    clamp_hour = (now_utc - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
    return created if created >= clamp_hour else clamp_hour


def _usage_event_payload(bucket: _UsageBucket, dimension: str) -> dict[str, Any]:
    return {
        "resourceId": bucket.resource_id,
        "quantity": float(bucket.quantity),
        "dimension": dimension,
        "effectiveStartTime": bucket.effective_start.strftime("%Y-%m-%dT%H:%M:%S"),
        "planId": bucket.plan_id,
    }


def _chunks(items: list[_UsageBucket], size: int) -> list[list[_UsageBucket]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def _post_usage_batch(http_client: httpx.AsyncClient, events: list[dict[str, Any]]) -> dict[str, Any]:
    token = await _get_access_token(http_client)
    response = await http_client.post(
        _METERING_BATCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        params={"api-version": _API_VERSION},
        json={"request": events},
    )
    if response.status_code >= 400:
        raise MarketplaceApiError(
            f"POST /api/batchUsageEvent failed: {response.status_code} {response.text}",
            status_code=response.status_code,
        )
    if not response.content:
        return {}
    return response.json()


async def submit_usage_batch(
    events: list[dict[str, Any]],
    *,
    http_client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    """`POST /api/batchUsageEvent` -- emit up to 25 usage events.

    Each event must include `resourceId`, `quantity`, `dimension`,
    `effectiveStartTime`, and `planId` per the Metering Service v2 contract.
    """
    if not events:
        return {"count": 0, "result": []}
    if len(events) > _METERING_BATCH_LIMIT:
        raise MarketplaceApiError(
            f"Metering batch exceeds the Microsoft limit of {_METERING_BATCH_LIMIT} events "
            f"({len(events)} given).",
        )
    async with _client_or(http_client) as client:
        return await _post_usage_batch(client, events)


def _ledger_billable(entry: Any) -> Decimal:
    if getattr(entry, "billable_cost_usd", None) is not None:
        return Decimal(entry.billable_cost_usd)
    return Decimal(entry.raw_cost_usd) * Decimal(entry.overage_multiplier)


def _aggregate_unmetered_rows(
    session: Any,
    now_utc: datetime,
    tenant_id: Optional[UUID] = None,
) -> tuple[list[_UsageBucket], int]:
    """Group unmetered ledger rows by subscription + UTC hour. Returns
    (buckets, skipped_row_count).
    """
    from sqlalchemy import select

    from db.models import Tenant, TokenLedgerEntry

    stmt = (
        select(TokenLedgerEntry, Tenant)
        .join(Tenant, TokenLedgerEntry.tenant_id == Tenant.id)
        .where(TokenLedgerEntry.azure_metering_emitted.is_(False))
        .order_by(TokenLedgerEntry.id)
    )
    if tenant_id is not None:
        stmt = stmt.where(TokenLedgerEntry.tenant_id == tenant_id)
    rows = session.execute(stmt).all()

    buckets: dict[tuple[str, str, datetime], _UsageBucket] = {}
    skipped = 0
    for entry, tenant in rows:
        plan_id = (tenant.azure_plan_id or "").strip()
        if not plan_id or tenant.azure_subscription_id is None:
            skipped += 1
            continue
        quantity = _ledger_billable(entry)
        if quantity <= 0:
            skipped += 1
            continue
        hour = _clamp_usage_hour(entry.created_at, now_utc)
        resource_id = str(tenant.azure_subscription_id)
        key = (resource_id, plan_id, hour)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _UsageBucket(
                resource_id=resource_id,
                plan_id=plan_id,
                effective_start=hour,
                quantity=Decimal("0"),
                row_ids=[],
            )
            buckets[key] = bucket
        bucket.quantity += quantity
        bucket.row_ids.append(entry.id)
    return list(buckets.values()), skipped


def _mark_rows_emitted(session: Any, row_ids: list[int], emission_id: Optional[str], emitted_at: datetime) -> int:
    from sqlalchemy import select

    from db.models import TokenLedgerEntry

    if not row_ids:
        return 0
    entries = session.execute(select(TokenLedgerEntry).where(TokenLedgerEntry.id.in_(row_ids))).scalars().all()
    for entry in entries:
        entry.azure_metering_emitted = True
        entry.azure_metering_emission_id = emission_id
        entry.azure_metering_emitted_at = emitted_at
    return len(entries)


def _batch_result_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items = body.get("result")
    if items is None:
        items = body.get("results")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _event_succeeded(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").lower()
    return status in {"accepted", "duplicate"}


async def emit_unmetered_token_ledger(
    *,
    http_client: Optional[httpx.AsyncClient] = None,
    now_utc: Optional[datetime] = None,
    tenant_id: Optional[UUID] = None,
) -> MeteringEmitResult:
    """Query unmetered `token_ledger` rows, POST them as usage batches, and
    mark accepted/duplicate source rows `azure_metering_emitted = TRUE`.
    """
    from db.session import get_session

    result = MeteringEmitResult()
    now = now_utc or datetime.now(timezone.utc)
    dimension = _metering_dimension()

    with get_session() as session:
        buckets, skipped = _aggregate_unmetered_rows(session, now, tenant_id=tenant_id)
        result.rows_skipped = skipped
        if not buckets:
            return result

        emitted_at = datetime.now(timezone.utc)
        for chunk in _chunks(buckets, _METERING_BATCH_LIMIT):
            events = [_usage_event_payload(bucket, dimension) for bucket in chunk]
            result.batches += 1
            result.events_submitted += len(events)
            try:
                body = await submit_usage_batch(events, http_client=http_client)
            except MarketplaceApiError as exc:
                logger.warning("marketplace metering batch failed: %s", exc)
                result.errors.append(str(exc))
                continue

            items = _batch_result_items(body)
            if not items and not result.errors:
                # 200 with an empty result list still means Microsoft accepted the batch.
                for bucket in chunk:
                    result.rows_emitted += _mark_rows_emitted(session, bucket.row_ids, None, emitted_at)
                continue

            by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
            for item in items:
                key = (
                    str(item.get("resourceId") or ""),
                    str(item.get("planId") or ""),
                    str(item.get("effectiveStartTime") or ""),
                )
                by_key[key] = item

            for bucket, event in zip(chunk, events):
                item = by_key.get((event["resourceId"], event["planId"], event["effectiveStartTime"]))
                if item is None:
                    # Per-event results omitted or unmatched -- treat HTTP 200 as success.
                    if not items:
                        result.rows_emitted += _mark_rows_emitted(session, bucket.row_ids, None, emitted_at)
                    continue
                if not _event_succeeded(item):
                    logger.warning(
                        "marketplace metering event not accepted: status=%s resourceId=%s",
                        item.get("status"),
                        event["resourceId"],
                    )
                    continue
                emission_id = item.get("usageEventId")
                result.rows_emitted += _mark_rows_emitted(
                    session,
                    bucket.row_ids,
                    str(emission_id) if emission_id else None,
                    emitted_at,
                )

    return result


def _main() -> None:
    import argparse
    import asyncio

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Emit unmetered token_ledger rows to the Azure Marketplace Metering Service."
    )
    parser.parse_args()
    stats = asyncio.run(emit_unmetered_token_ledger())
    print(
        f"events_submitted={stats.events_submitted} rows_emitted={stats.rows_emitted} "
        f"rows_skipped={stats.rows_skipped} batches={stats.batches} errors={len(stats.errors)}"
    )


if __name__ == "__main__":
    _main()
