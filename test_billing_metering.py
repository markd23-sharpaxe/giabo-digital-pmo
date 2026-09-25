"""Billing markup (2.50x) and Marketplace metering-batch verification.

Standalone narratable script (no pytest), same style as
`test_marketplace_integration.py`. Computation checks need no network;
compute-cap + emit tests use the live Azure Postgres from `.env` and mock
Microsoft's Metering API.

Run:
    .venv/bin/python test_billing_metering.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

load_dotenv()

import anyio
import httpx

import core.marketplace_client as mc
from core.billing import (
    OVERAGE_MULTIPLIER,
    billable_cost_usd,
    check_pilot_compute_cap,
    reconcile_actual_cost,
)
from db.models import PlanTier, SwarmStatus, Tenant, TokenLedgerEntry
from db.session import get_session

FAILURES: list[str] = []

TEST_PLAN_ID = "free-monthly"
FROZEN_NOW = datetime(2026, 9, 25, 14, 30, tzinfo=timezone.utc)
CREATED_AT = datetime(2026, 9, 25, 13, 15, tzinfo=timezone.utc)
EXPECTED_HOUR = "2026-09-25T13:00:00"


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def _create_tenant(*, with_plan: bool = True) -> uuid.UUID:
    with get_session() as session:
        tenant = Tenant(
            azure_subscription_id=uuid.uuid4(),
            azure_customer_tenant_id=uuid.uuid4(),
            azure_plan_id=TEST_PLAN_ID if with_plan else None,
            organization_name="Metering Test Org",
            plan_tier=PlanTier.FREE_TRIAL,
            trial_start_date=date.today(),
            swarm_status=SwarmStatus.ACTIVE,
            raw_token_spend_usd=Decimal("50.00"),
            billed_overage_usd=Decimal("0"),
        )
        session.add(tenant)
        session.flush()
        session.refresh(tenant)
        return tenant.id


def _cleanup_tenant(tenant_id: uuid.UUID) -> None:
    with get_session() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is not None:
            session.delete(tenant)


def _insert_ledger_rows(tenant_id: uuid.UUID, raw_costs: list[Decimal]) -> list[int]:
    ids: list[int] = []
    with get_session() as session:
        for raw in raw_costs:
            entry = TokenLedgerEntry(
                tenant_id=tenant_id,
                prompt_tokens=100,
                completion_tokens=50,
                raw_cost_usd=raw,
                overage_multiplier=OVERAGE_MULTIPLIER,
                is_overage=True,
                azure_metering_emitted=False,
                created_at=CREATED_AT,
            )
            session.add(entry)
            session.flush()
            session.refresh(entry)
            ids.append(entry.id)
    return ids


def test_multiplier_math() -> None:
    _section("Part 1: 2.50x billable markup")
    _check("OVERAGE_MULTIPLIER is 2.50", OVERAGE_MULTIPLIER == Decimal("2.50"))
    _check(
        "billable_cost_usd(0.40) == 1.00  ($1 charged per $0.40 raw)",
        billable_cost_usd(Decimal("0.40")) == Decimal("1.00"),
    )
    _check(
        "billable_cost_usd(1.00) == 2.50",
        billable_cost_usd(Decimal("1.00")) == Decimal("2.50"),
    )


def test_compute_cap_no_halt() -> None:
    _section("Part 2: check_pilot_compute_cap meters all spend and does not halt")
    tenant_id = _create_tenant()
    try:
        with get_session() as session:
            result = check_pilot_compute_cap(session, tenant_id, Decimal("0.40"))
            tenant = session.get(Tenant, tenant_id)
            _check("compute cap does not raise on spend well above $20", True)
            _check("reserved_cost_usd is the raw estimate", result.reserved_cost_usd == Decimal("0.40"))
            _check("overage_multiplier is always 2.50", result.overage_multiplier == Decimal("2.50"))
            _check("is_overage is True (all usage is metered)", result.is_overage is True)
            assert tenant is not None
            _check(
                "raw_token_spend_usd increased by the raw estimate (50.00 + 0.40)",
                tenant.raw_token_spend_usd == Decimal("50.40"),
                str(tenant.raw_token_spend_usd),
            )
            _check(
                "billed_overage_usd increased by raw * 2.50 (1.00)",
                tenant.billed_overage_usd == Decimal("1.00"),
                str(tenant.billed_overage_usd),
            )
            _check(
                "swarm_status stays ACTIVE (no trial hard-halt)",
                tenant.swarm_status is SwarmStatus.ACTIVE,
            )

            reconcile_actual_cost(session, tenant_id, Decimal("0.40"), Decimal("0.80"))
            tenant = session.get(Tenant, tenant_id)
            assert tenant is not None
            _check(
                "reconcile adjusts raw by the delta (50.40 + 0.40 = 50.80)",
                tenant.raw_token_spend_usd == Decimal("50.80"),
                str(tenant.raw_token_spend_usd),
            )
            _check(
                "reconcile adjusts billed by delta * 2.50 (1.00 + 1.00 = 2.00)",
                tenant.billed_overage_usd == Decimal("2.00"),
                str(tenant.billed_overage_usd),
            )
    finally:
        _cleanup_tenant(tenant_id)


def test_submit_usage_batch_url() -> None:
    _section("Part 3: submit_usage_batch hits /api/batchUsageEvent")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "meter-token", "expires_in": 3600})
        if request.url.path == "/api/batchUsageEvent":
            return httpx.Response(200, json={"count": 1, "result": [{"status": "Accepted", "usageEventId": "evt-1"}]})
        return httpx.Response(404, json={"error": f"unexpected {request.method} {request.url.path}"})

    async def _run() -> None:
        mc._cached_token = None
        mc._cached_token_expires_at = 0.0
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="https://unused.invalid") as client:
            body = await mc.submit_usage_batch(
                [
                    {
                        "resourceId": "11111111-1111-1111-1111-111111111111",
                        "quantity": 1.0,
                        "dimension": "token_compute_overage",
                        "effectiveStartTime": EXPECTED_HOUR,
                        "planId": TEST_PLAN_ID,
                    }
                ],
                http_client=client,
            )
        _check("submit_usage_batch returns Accepted", body.get("result", [{}])[0].get("status") == "Accepted")
        batch_req = next(r for r in captured if r.url.path == "/api/batchUsageEvent")
        _check("metering request is POST /api/batchUsageEvent", batch_req.method == "POST")
        _check("metering request carries api-version=2018-08-31", batch_req.url.params.get("api-version") == "2018-08-31")
        _check("metering request host is marketplaceapi.microsoft.com", batch_req.url.host == "marketplaceapi.microsoft.com")
        _check("batch body wraps events in request[]", b'"request"' in (batch_req.content or b""))

    anyio.run(_run)


def test_emit_success_marks_rows() -> None:
    _section("Part 4: emit_unmetered_token_ledger marks accepted rows")
    tenant_id = _create_tenant()
    row_ids: list[int] = []
    try:
        row_ids = _insert_ledger_rows(tenant_id, [Decimal("0.20"), Decimal("0.20")])
        with get_session() as session:
            tenant = session.get(Tenant, tenant_id)
            assert tenant is not None
            resource_id = str(tenant.azure_subscription_id)

        accepted = {
            "count": 1,
            "result": [
                {
                    "status": "Accepted",
                    "usageEventId": "evt-success-1",
                    "resourceId": resource_id,
                    "planId": TEST_PLAN_ID,
                    "effectiveStartTime": EXPECTED_HOUR,
                    "quantity": 1.0,
                    "dimension": "token_compute_overage",
                }
            ],
        }

        async def _run() -> mc.MeteringEmitResult:
            with patch("core.marketplace_client.submit_usage_batch", new_callable=AsyncMock) as mock_submit:
                mock_submit.return_value = accepted
                result = await mc.emit_unmetered_token_ledger(now_utc=FROZEN_NOW, tenant_id=tenant_id)
                _check("one metering event submitted", mock_submit.await_count == 1)
                events = mock_submit.await_args.args[0]
                _check("batch contains a single aggregated event", len(events) == 1)
                event = events[0]
                _check("resourceId is the SaaS subscription id", event["resourceId"] == resource_id)
                _check("planId is the tenant azure_plan_id", event["planId"] == TEST_PLAN_ID)
                _check("dimension is token_compute_overage", event["dimension"] == "token_compute_overage")
                _check("effectiveStartTime is the UTC hour bucket", event["effectiveStartTime"] == EXPECTED_HOUR)
                _check(
                    "quantity is the sum of billable costs (0.20*2.50 + 0.20*2.50 = 1.00)",
                    event["quantity"] == 1.0,
                    str(event["quantity"]),
                )
                return result

        result = anyio.run(_run)
        _check("rows_emitted == 2", result.rows_emitted == 2, str(result.rows_emitted))
        _check("no emit errors", result.errors == [])

        with get_session() as session:
            rows = [session.get(TokenLedgerEntry, rid) for rid in row_ids]
            _check("both ledger rows marked azure_metering_emitted", all(r is not None and r.azure_metering_emitted for r in rows))
            _check(
                "emission id stored from Microsoft usageEventId",
                all(r is not None and r.azure_metering_emission_id == "evt-success-1" for r in rows),
            )
    finally:
        _cleanup_tenant(tenant_id)


def test_emit_http_400_leaves_flags_false() -> None:
    _section("Part 5: HTTP 400 leaves azure_metering_emitted false")
    tenant_id = _create_tenant()
    row_ids: list[int] = []
    try:
        row_ids = _insert_ledger_rows(tenant_id, [Decimal("0.40")])

        async def _run() -> mc.MeteringEmitResult:
            with patch("core.marketplace_client.submit_usage_batch", new_callable=AsyncMock) as mock_submit:
                mock_submit.side_effect = mc.MarketplaceApiError("metering rejected", status_code=400)
                return await mc.emit_unmetered_token_ledger(now_utc=FROZEN_NOW, tenant_id=tenant_id)

        result = anyio.run(_run)
        _check("emit recorded the Marketplace error", bool(result.errors))
        _check("rows_emitted stays 0 on HTTP 400", result.rows_emitted == 0)

        with get_session() as session:
            row = session.get(TokenLedgerEntry, row_ids[0])
            _check("ledger row remains unmetered after HTTP 400", row is not None and row.azure_metering_emitted is False)
    finally:
        _cleanup_tenant(tenant_id)


def main() -> int:
    test_multiplier_math()
    test_compute_cap_no_halt()
    test_submit_usage_batch_url()
    test_emit_success_marks_rows()
    test_emit_http_400_leaves_flags_false()

    print(f"\n{'=' * 78}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("All billing/metering checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
