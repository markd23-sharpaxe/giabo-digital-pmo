"""Microsoft Partner Center SaaS Fulfillment API v2 client.

Pure Microsoft-API client, deliberately with no database/business-logic
knowledge (contrast `api/marketplace.py`, which owns the `tenants` upsert and
the `planId`/`saasSubscriptionStatus` -> `PlanTier`/`SwarmStatus` mapping) --
same separation `core/graph_client.py` draws for Microsoft Graph.

Endpoint contract is the documented SaaS Fulfillment API v2
(https://learn.microsoft.com/en-us/partner-center/marketplace-offers/pc-saas-fulfillment-api-v2),
not the exact shape in this project's own plan doc -- two corrections worth
calling out, since both would otherwise silently produce a client that talks
to nothing real:

  1. Token endpoint host is `login.microsoftonline.com`, not
     `login.microsoft.com` (the latter is a marketing/redirect domain, not
     the AAD token-issuing endpoint real client-credentials requests hit).
  2. "Resolve a subscription" is `POST /api/saas/subscriptions/resolve`
     with the purchase token in the `x-ms-marketplace-token` HEADER (not a
     GET with `?token=`, and not `/operations/v2/subscriptions/achieve`,
     which isn't a real Fulfillment API v2 route).

We authenticate as *our own* app (`MicrosoftAppId`/`MicrosoftAppPassword`,
the same Azure AD app registration already used for the Teams bot and
Microsoft Graph -- see `api/main.py`/`core/graph_client.py`) against the
well-known, stable "Microsoft Commercial Marketplace" AAD resource, not a
customer tenant -- contrast `core/graph_client.py`, which authenticates
*into* the customer's tenant.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

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
_API_VERSION = "2018-08-31"

_HTTP_TIMEOUT = 30.0


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
