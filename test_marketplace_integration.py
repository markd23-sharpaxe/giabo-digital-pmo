"""Validation for the Microsoft Partner Center SaaS Fulfillment API v2 integration.

Not a pytest suite (none is installed in this project's `.venv`) -- a
standalone, narratable script, same style as `test_live_agent_turn.py`.

Split into two halves, because only one half can honestly be exercised
against something real:

  1. `core/marketplace_client.py` request-shaping, against a mocked
     `httpx.MockTransport` -- there is no reachable sandbox for the real
     Partner Center Fulfillment API from here (unlike Azure OpenAI/Postgres,
     hitting it for real requires an actual completed Marketplace purchase
     transaction). This proves the URLs/methods/headers/body match the
     documented v2 contract, and that the token cache actually caches.
  2. `api/marketplace.py`'s landing + webhook handlers, end-to-end through
     FastAPI's `TestClient`, against the REAL live Azure Postgres from
     `.env` (`db.session.get_session` -- same database
     `test_live_agent_turn.py` already validated writeback against). Only
     `core.marketplace_client`'s Microsoft-facing calls are mocked; the
     `tenants` upsert itself is real. A throwaway tenant (random
     `azure_subscription_id`/`azure_customer_tenant_id`) is created and then
     deleted at the end so this script leaves the database exactly as it
     found it.

Run:
    .venv/bin/python test_marketplace_integration.py
"""

from __future__ import annotations

import sys
import uuid
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

load_dotenv()

import anyio
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

import core.marketplace_client as mc
from db.models import PlanTier, SwarmStatus, Tenant
from db.session import get_session

FAILURES: list[str] = []


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


# =============================================================================
# Part 1: core/marketplace_client.py request shaping (mocked transport)
# =============================================================================


def test_marketplace_client() -> None:
    _section("Part 1: core/marketplace_client.py -- mocked-transport request shaping")

    captured: list[httpx.Request] = []
    token_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        path = request.url.path

        if path.endswith("/oauth2/v2.0/token"):
            token_calls["count"] += 1
            return httpx.Response(200, json={"access_token": f"fake-token-{token_calls['count']}", "expires_in": 3600})
        if path == "/api/saas/subscriptions/resolve":
            return httpx.Response(
                200, json={"id": "sub-abc", "subscriptionName": "Contoso Sub", "offerId": "offer1", "planId": "plan-trial"}
            )
        if path == "/api/saas/subscriptions/sub-abc":
            return httpx.Response(
                200,
                json={
                    "id": "sub-abc",
                    "planId": "plan-trial",
                    "name": "Contoso",
                    "saasSubscriptionStatus": "PendingFulfillmentStart",
                    "beneficiary": {"tenantId": "11111111-1111-1111-1111-111111111111"},
                },
            )
        if path == "/api/saas/subscriptions/sub-abc/activate" and request.method == "POST":
            return httpx.Response(200, json={})
        if path == "/api/saas/subscriptions/sub-abc/operations/op-1":
            if request.method == "GET":
                return httpx.Response(200, json={"id": "op-1", "action": "ChangePlan"})
            if request.method == "PATCH":
                return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": f"unexpected {request.method} {path}"})

    transport = httpx.MockTransport(handler)

    async def _run() -> None:
        # Force a fresh token cache for this run regardless of prior state.
        mc._cached_token = None
        mc._cached_token_expires_at = 0.0

        async with httpx.AsyncClient(transport=transport, base_url="https://unused.invalid") as client:
            resolved = await mc.resolve_subscription_token("purchase-token-xyz", http_client=client)
            _check("resolve_subscription_token returns subscription id", resolved.get("id") == "sub-abc")

            subscription = await mc.get_subscription("sub-abc", http_client=client)
            _check(
                "get_subscription returns beneficiary tenant id",
                subscription.get("beneficiary", {}).get("tenantId") == "11111111-1111-1111-1111-111111111111",
            )

            await mc.activate_subscription("sub-abc", "plan-trial", http_client=client)
            operation = await mc.get_operation("sub-abc", "op-1", http_client=client)
            _check("get_operation returns the operation id", operation.get("id") == "op-1")

            await mc.update_operation_status("sub-abc", "op-1", "Success", http_client=client)

        _check("exactly one token request was made (cache hit for calls 2-5)", token_calls["count"] == 1)

        resolve_req = next(r for r in captured if r.url.path == "/api/saas/subscriptions/resolve")
        _check(
            "resolve request carries x-ms-marketplace-token header",
            resolve_req.headers.get("x-ms-marketplace-token") == "purchase-token-xyz",
        )
        _check(
            "resolve request carries a bearer token from the token endpoint",
            resolve_req.headers.get("authorization", "").startswith("Bearer fake-token-"),
        )
        _check("resolve request is a POST", resolve_req.method == "POST")
        _check("resolve request carries api-version query param", resolve_req.url.params.get("api-version") == "2018-08-31")

        get_sub_req = next(r for r in captured if r.url.path == "/api/saas/subscriptions/sub-abc" and r.method == "GET")
        _check("get_subscription request is a GET with no marketplace-token header", "x-ms-marketplace-token" not in get_sub_req.headers)

        activate_req = next(r for r in captured if r.url.path.endswith("/activate"))
        _check("activate request is a POST", activate_req.method == "POST")
        _check("activate request body carries planId", activate_req.content and b"plan-trial" in activate_req.content)

        patch_req = next(r for r in captured if r.method == "PATCH")
        _check("update_operation_status uses PATCH (matches the real API's outbound-ack verb)", patch_req.method == "PATCH")
        _check("PATCH body carries status=Success", b"Success" in (patch_req.content or b""))

        token_req = next(r for r in captured if r.url.path.endswith("/oauth2/v2.0/token"))
        _check(
            "token endpoint host is login.microsoftonline.com (not login.microsoft.com)",
            token_req.url.host == "login.microsoftonline.com",
        )
        _check(
            "token request scopes the well-known Marketplace resource id",
            b"20e940b3-4c77-4b0b-9a53-9e16a1b010a7" in (token_req.content or b""),
        )

    anyio.run(_run)


# =============================================================================
# Part 2: api/marketplace.py end-to-end (real Postgres, mocked Microsoft calls)
# =============================================================================

TEST_SUBSCRIPTION_ID = str(uuid.uuid4())
TEST_CUSTOMER_TENANT_ID = str(uuid.uuid4())


def _make_client() -> TestClient:
    import api.marketplace as mp

    app = FastAPI()
    app.include_router(mp.router)
    return TestClient(app)


def _load_test_tenant() -> Tenant | None:
    with get_session() as session:
        return session.execute(
            select(Tenant).where(Tenant.azure_subscription_id == uuid.UUID(TEST_SUBSCRIPTION_ID))
        ).scalar_one_or_none()


def _cleanup_test_tenant() -> None:
    with get_session() as session:
        tenant = session.execute(
            select(Tenant).where(Tenant.azure_subscription_id == uuid.UUID(TEST_SUBSCRIPTION_ID))
        ).scalar_one_or_none()
        if tenant is not None:
            session.delete(tenant)


def test_landing_new_free_trial_purchase(client: TestClient) -> None:
    _section("Part 2a: GET /marketplace/landing -- new Free Trial purchase")

    resolved = {"id": TEST_SUBSCRIPTION_ID, "subscriptionName": "Test Org", "offerId": "offer1", "planId": "free-trial-plan"}
    pending_sub = {
        "id": TEST_SUBSCRIPTION_ID,
        "planId": "free-trial-plan",
        "name": "Test Org",
        "saasSubscriptionStatus": "PendingFulfillmentStart",
        "beneficiary": {"tenantId": TEST_CUSTOMER_TENANT_ID},
    }
    active_sub = {**pending_sub, "saasSubscriptionStatus": "Subscribed"}

    with (
        patch("api.marketplace.resolve_subscription_token", AsyncMock(return_value=resolved)) as mock_resolve,
        patch("api.marketplace.get_subscription", AsyncMock(side_effect=[pending_sub, active_sub])) as mock_get,
        patch("api.marketplace.activate_subscription", AsyncMock(return_value=None)) as mock_activate,
    ):
        resp = client.get("/marketplace/landing", params={"token": "purchase-token-abc"})

    _check("landing returns 200", resp.status_code == 200, resp.text[:300])
    _check("landing page mentions the organization name", "Test Org" in resp.text)
    _check("landing page mentions the Free 14-Day Trial plan", "Free 14-Day Trial" in resp.text)
    mock_resolve.assert_awaited_once_with("purchase-token-abc")
    _check("get_subscription called twice (initial + post-activation re-fetch)", mock_get.await_count == 2)
    mock_activate.assert_awaited_once()
    _check(
        "activate_subscription called with the resolved planId",
        mock_activate.await_args.args[:2] == (TEST_SUBSCRIPTION_ID, "free-trial-plan"),
    )

    tenant = _load_test_tenant()
    _check("tenant row was created", tenant is not None)
    if tenant is not None:
        _check("tenant plan_tier == free_trial", tenant.plan_tier is PlanTier.FREE_TRIAL)
        _check("tenant swarm_status == active", tenant.swarm_status is SwarmStatus.ACTIVE)
        _check("tenant.azure_customer_tenant_id matches beneficiary.tenantId", str(tenant.azure_customer_tenant_id) == TEST_CUSTOMER_TENANT_ID)
        _check("tenant.trial_start_date was stamped", tenant.trial_start_date is not None)


def test_landing_marketplace_api_failure(client: TestClient) -> None:
    _section("Part 2b: GET /marketplace/landing -- Marketplace API failure renders a friendly error page")

    with patch(
        "api.marketplace.resolve_subscription_token",
        AsyncMock(side_effect=mc.MarketplaceApiError("boom: token already used", status_code=400)),
    ):
        resp = client.get("/marketplace/landing", params={"token": "stale-token"})

    _check("failed resolve returns 502, not a raw 500 stack trace", resp.status_code == 502)
    _check("error page does not leak an unhandled traceback", "Traceback" not in resp.text)


def test_webhook_change_plan_to_paid(client: TestClient) -> None:
    _section("Part 2c: POST /api/marketplace/webhook -- ChangePlan free_trial -> paid_monthly")

    updated_sub = {
        "id": TEST_SUBSCRIPTION_ID,
        "planId": "paid-monthly-plan",
        "name": "Test Org",
        "saasSubscriptionStatus": "Subscribed",
        "beneficiary": {"tenantId": TEST_CUSTOMER_TENANT_ID},
    }
    payload = {
        "id": "op-change-1",
        "activityId": "op-change-1",
        "subscriptionId": TEST_SUBSCRIPTION_ID,
        "planId": "paid-monthly-plan",
        "action": "ChangePlan",
        "status": "InProgress",
        "timeStamp": "2026-09-18T00:00:00Z",
    }

    with (
        patch("api.marketplace.get_subscription", AsyncMock(return_value=updated_sub)),
        patch("api.marketplace.update_operation_status", AsyncMock(return_value=None)) as mock_update,
    ):
        resp = client.post("/api/marketplace/webhook", json=payload)

    _check("webhook POST returns 200", resp.status_code == 200, resp.text)
    mock_update.assert_awaited_once_with(TEST_SUBSCRIPTION_ID, "op-change-1", "Success")

    tenant = _load_test_tenant()
    _check("tenant plan_tier updated to paid_monthly", tenant is not None and tenant.plan_tier is PlanTier.PAID_MONTHLY)


def test_webhook_unsubscribe_via_patch_alias(client: TestClient) -> None:
    _section("Part 2d: PATCH /api/marketplace/webhook (alias route) -- Unsubscribe -> cancelled")

    cancelled_sub = {
        "id": TEST_SUBSCRIPTION_ID,
        "planId": "paid-monthly-plan",
        "name": "Test Org",
        "saasSubscriptionStatus": "Unsubscribed",
        "beneficiary": {"tenantId": TEST_CUSTOMER_TENANT_ID},
    }
    payload = {
        "id": "op-cancel-1",
        "activityId": "op-cancel-1",
        "subscriptionId": TEST_SUBSCRIPTION_ID,
        "action": "Unsubscribe",
        "status": "InProgress",
    }

    with (
        patch("api.marketplace.get_subscription", AsyncMock(return_value=cancelled_sub)),
        patch("api.marketplace.update_operation_status", AsyncMock(return_value=None)),
    ):
        resp = client.patch("/api/marketplace/webhook", json=payload)

    _check("webhook PATCH alias returns 200", resp.status_code == 200, resp.text)
    tenant = _load_test_tenant()
    _check("tenant swarm_status updated to cancelled", tenant is not None and tenant.swarm_status is SwarmStatus.CANCELLED)


def test_webhook_malformed_payload(client: TestClient) -> None:
    _section("Part 2e: POST /api/marketplace/webhook -- malformed payload is rejected, not 500'd")

    resp = client.post("/api/marketplace/webhook", json={"nonsense": True})
    _check("malformed payload returns 400", resp.status_code == 400)


def test_webhook_marketplace_api_failure_returns_502(client: TestClient) -> None:
    _section("Part 2f: POST /api/marketplace/webhook -- Marketplace API failure returns 502 (Microsoft should retry)")

    payload = {
        "id": "op-fail-1",
        "activityId": "op-fail-1",
        "subscriptionId": TEST_SUBSCRIPTION_ID,
        "action": "Renew",
        "status": "InProgress",
    }
    with patch(
        "api.marketplace.get_subscription",
        AsyncMock(side_effect=mc.MarketplaceApiError("transient 503", status_code=503)),
    ):
        resp = client.post("/api/marketplace/webhook", json=payload)

    _check("transient Marketplace API failure returns 502", resp.status_code == 502)


def main() -> None:
    test_marketplace_client()

    client = _make_client()
    try:
        test_landing_new_free_trial_purchase(client)
        test_landing_marketplace_api_failure(client)
        test_webhook_change_plan_to_paid(client)
        test_webhook_unsubscribe_via_patch_alias(client)
        test_webhook_malformed_payload(client)
        test_webhook_marketplace_api_failure_returns_502(client)
    finally:
        _section("Cleanup: deleting the throwaway test tenant from the live database")
        _cleanup_test_tenant()
        remaining = _load_test_tenant()
        _check("test tenant removed from the live database", remaining is None)

    _section("Result")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS: all marketplace integration checks passed.")


if __name__ == "__main__":
    main()
