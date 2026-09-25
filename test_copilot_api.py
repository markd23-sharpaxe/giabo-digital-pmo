"""Validation for the Microsoft 365 Copilot Declarative Agent API Bridge
(Declarative Agent Architecture Pivot).

Not a pytest suite (none is installed in this project's `.venv`) -- a
standalone, narratable script, same style as `test_live_agent_turn.py` /
`test_marketplace_integration.py`. Runs against the REAL live Azure Postgres
from `.env` and the FULL `api.main.app` (so the removed dashboard routes and
the surviving legal/marketplace routes are exercised through the actual
mounted app, not a bare router).

Creates one throwaway tenant/project/pmo_artifact/agent_execution, exercises
all three `api/copilot.py` operations end-to-end -- both with explicit ids
and with them omitted (the zero-config auto-resolution path) -- and deletes
everything it created (cascade deletes handle the project/artifact/execution
rows once the tenant is removed).

The throwaway tenant is created with `swarm_status=ACTIVE` and, being
created fresh by this script run, has the newest `updated_at` of any ACTIVE
tenant in the database at the time these tests run; likewise, each project
this script creates is briefly the most-recently-touched project overall.
That is what makes the "omit the id" assertions below deterministic against
a live, shared database rather than a mocked/local one -- see
`api/copilot.py`'s `_resolve_default_tenant`/`_resolve_default_project`.

Run:
    .venv/bin/python test_copilot_api.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient
from sqlalchemy import select

from db.models import (
    AgentExecution,
    AgentTier,
    ArtifactType,
    ExecutionStatus,
    PlanTier,
    PmoArtifact,
    SwarmStatus,
    Tenant,
    TriggerType,
)
from db.session import get_session

FAILURES: list[str] = []

TEST_SUBSCRIPTION_ID = uuid.uuid4()
TEST_CUSTOMER_TENANT_ID = uuid.uuid4()
TEST_ORG_NAME = "Copilot API Bridge Test Org"


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


# =============================================================================
# Fixture setup / teardown -- a throwaway tenant in the real database
# =============================================================================


def _create_test_tenant() -> uuid.UUID:
    with get_session() as session:
        tenant = Tenant(
            azure_subscription_id=TEST_SUBSCRIPTION_ID,
            azure_customer_tenant_id=TEST_CUSTOMER_TENANT_ID,
            organization_name=TEST_ORG_NAME,
            plan_tier=PlanTier.FREE_TRIAL,
            trial_start_date=date.today(),
            # Explicit ACTIVE (the ORM default is PROVISIONING) -- required
            # for this to be a candidate for _resolve_default_tenant's
            # "most recently active tenant" fallback at all.
            swarm_status=SwarmStatus.ACTIVE,
        )
        session.add(tenant)
        session.flush()
        session.refresh(tenant)
        return tenant.id


def _cleanup_test_tenant(tenant_id: uuid.UUID) -> None:
    with get_session() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is not None:
            session.delete(tenant)


def _load_test_tenant(tenant_id: uuid.UUID) -> Tenant | None:
    with get_session() as session:
        return session.get(Tenant, tenant_id)


# =============================================================================
# Part 1: POST /api/projects/create
# =============================================================================


def test_create_project(client: TestClient, tenant_id: uuid.UUID) -> uuid.UUID | None:
    _section("Part 1: POST /api/projects/create")

    payload = {
        "tenant_id": str(tenant_id),
        "name": "Copilot Pivot Test Project",
        "sharepoint_site_id": "site-copilot-test-001",
        "digital_employee_name": "Ada",
        "digital_employee_email": "ada@example.com",
    }
    resp = client.post("/api/projects/create", json=payload)
    _check("create returns 200", resp.status_code == 200, resp.text[:300])
    if resp.status_code != 200:
        return None

    body = resp.json()
    _check("response name matches request", body.get("name") == payload["name"])
    _check("response status is 'new'", body.get("status") == "new")
    _check("response sharepoint_site_id matches", body.get("sharepoint_site_id") == payload["sharepoint_site_id"])
    _check("response digital_employee_name matches", body.get("digital_employee_name") == payload["digital_employee_name"])
    _check("response digital_employee_email matches", body.get("digital_employee_email") == payload["digital_employee_email"])
    _check("response has a created_at timestamp", bool(body.get("created_at")))

    project_id = uuid.UUID(body["id"])

    with get_session() as session:
        from db.models import Project

        row = session.get(Project, project_id)
        _check("project row landed in Postgres", row is not None)
        if row is not None:
            _check("db row name matches", row.name == payload["name"])
            _check("db row sharepoint_site_id matches", row.sharepoint_site_id == payload["sharepoint_site_id"])
            _check("db row digital_employee_name matches", row.digital_employee_name == payload["digital_employee_name"])
            _check("db row digital_employee_email matches", row.digital_employee_email == payload["digital_employee_email"])
            _check("db row tenant_id matches", row.tenant_id == tenant_id)

    return project_id


def test_create_project_unknown_tenant(client: TestClient) -> None:
    _section("Part 1b: POST /api/projects/create -- unknown tenant_id 404s")

    resp = client.post(
        "/api/projects/create",
        json={"tenant_id": str(uuid.uuid4()), "name": "Should Not Be Created"},
    )
    _check("unknown tenant_id returns 404", resp.status_code == 404, resp.text[:300])


def test_create_project_empty_name(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 1c: POST /api/projects/create -- empty name is rejected")

    resp = client.post("/api/projects/create", json={"tenant_id": str(tenant_id), "name": "   "})
    _check("empty name returns 422", resp.status_code == 422, resp.text[:300])


def test_create_project_default_tenant(client: TestClient, tenant_id: uuid.UUID) -> uuid.UUID | None:
    _section("Part 1d: POST /api/projects/create -- tenant_id omitted defaults to most recently active tenant")

    resp = client.post("/api/projects/create", json={"name": "Copilot Zero-Config Test Project"})
    _check("create with omitted tenant_id returns 200", resp.status_code == 200, resp.text[:300])
    if resp.status_code != 200:
        return None

    body = resp.json()
    _check(
        "defaulted project's tenant_id is our freshest ACTIVE test tenant",
        body.get("tenant_id") == str(tenant_id),
        f"got tenant_id={body.get('tenant_id')!r}, expected {tenant_id}",
    )
    return uuid.UUID(body["id"])


# =============================================================================
# Part 2: GET /api/projects/brief
# =============================================================================


def _seed_brief_fixtures(project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    with get_session() as session:
        session.add(
            PmoArtifact(
                id=f"RISK-COPILOT-TEST-{uuid.uuid4().hex[:8]}",
                project_id=project_id,
                tenant_id=tenant_id,
                artifact_type=ArtifactType.RISK,
                title="Budget overrun risk",
                description="Vendor costs trending 15% over baseline.",
                severity="high",
                due_date=date.today() + timedelta(days=14),
                source_agent_key="governance_worker",
            )
        )
        session.add(
            PmoArtifact(
                id=f"ACTION-COPILOT-TEST-{uuid.uuid4().hex[:8]}",
                project_id=project_id,
                tenant_id=tenant_id,
                artifact_type=ArtifactType.ACTION,
                title="Follow up with vendor on invoice discrepancy",
                description="Confirm the Q3 invoice matches the signed SOW.",
                source_agent_key="pmp_worker",
            )
        )
        session.add(
            AgentExecution(
                tenant_id=tenant_id,
                project_id=project_id,
                agent_key="pmp_worker",
                agent_tier=AgentTier.WRITEBACK,
                trigger_type=TriggerType.TEAMS_INTERACTION,
                status=ExecutionStatus.SUCCESS,
            )
        )


def test_get_project_brief(client: TestClient, project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    _section("Part 2: GET /api/projects/brief (explicit project_id)")

    _seed_brief_fixtures(project_id, tenant_id)

    resp = client.get("/api/projects/brief", params={"project_id": str(project_id)})
    _check("brief returns 200", resp.status_code == 200, resp.text[:300])
    if resp.status_code != 200:
        return

    body = resp.json()
    markdown = body.get("markdown", "")
    _check("brief project_name matches", body.get("project_name") == "Copilot Pivot Test Project")
    _check("markdown contains the project name header", "Copilot Pivot Test Project" in markdown)
    _check("markdown has a Risks section", "## Risks" in markdown)
    _check("markdown has an Actions section", "## Actions" in markdown)
    _check("markdown has a Swarm Audit Log section", "## Swarm Audit Log" in markdown)
    _check("markdown mentions the seeded risk title", "Budget overrun risk" in markdown)
    _check("markdown mentions the seeded action title", "Follow up with vendor on invoice discrepancy" in markdown)
    _check("markdown mentions the seeded agent_key", "pmp_worker" in markdown)


def test_get_project_brief_unknown_project(client: TestClient) -> None:
    _section("Part 2b: GET /api/projects/brief -- unknown project_id 404s")

    resp = client.get("/api/projects/brief", params={"project_id": str(uuid.uuid4())})
    _check("unknown project_id returns 404", resp.status_code == 404, resp.text[:300])


def test_get_project_brief_default_project(client: TestClient, expected_project_id: uuid.UUID, expected_project_name: str) -> None:
    _section("Part 2c: GET /api/projects/brief -- project_id omitted defaults to most recently active project")

    resp = client.get("/api/projects/brief")
    _check("brief with omitted project_id returns 200", resp.status_code == 200, resp.text[:300])
    if resp.status_code != 200:
        return

    body = resp.json()
    _check(
        "defaulted brief resolves to the freshest project (the one just created above)",
        body.get("project_id") == str(expected_project_id),
        f"got project_id={body.get('project_id')!r}, expected {expected_project_id}",
    )
    _check("defaulted brief's project_name matches", body.get("project_name") == expected_project_name)


# =============================================================================
# Part 3: GET /api/usage/telemetry
# =============================================================================


def test_get_usage_telemetry(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 3: GET /api/usage/telemetry")

    resp = client.get("/api/usage/telemetry", params={"tenant_id": str(tenant_id)})
    _check("telemetry returns 200", resp.status_code == 200, resp.text[:300])
    if resp.status_code != 200:
        return

    body = resp.json()
    tenant = _load_test_tenant(tenant_id)
    _check("telemetry organization_name matches", body.get("organization_name") == TEST_ORG_NAME)
    _check("telemetry plan_tier == free_trial", body.get("plan_tier") == "free_trial")
    _check("telemetry swarm_status matches db", tenant is not None and body.get("swarm_status") == tenant.swarm_status.value)
    _check("telemetry active_project_count == 1 (the one project created above)", body.get("active_project_count") == 1)
    _check("telemetry trial_end_date is populated", bool(body.get("trial_end_date")))
    _check("telemetry is_overage is False for a fresh trial tenant", body.get("is_overage") is False)


def test_get_usage_telemetry_unknown_tenant(client: TestClient) -> None:
    _section("Part 3b: GET /api/usage/telemetry -- unknown tenant_id 404s")

    resp = client.get("/api/usage/telemetry", params={"tenant_id": str(uuid.uuid4())})
    _check("unknown tenant_id returns 404", resp.status_code == 404, resp.text[:300])


def test_get_usage_telemetry_default_tenant(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 3c: GET /api/usage/telemetry -- tenant_id omitted defaults to most recently active tenant")

    resp = client.get("/api/usage/telemetry")
    _check("telemetry with omitted tenant_id returns 200", resp.status_code == 200, resp.text[:300])
    if resp.status_code != 200:
        return

    body = resp.json()
    _check(
        "defaulted telemetry resolves to our freshest ACTIVE test tenant",
        body.get("tenant_id") == str(tenant_id),
        f"got tenant_id={body.get('tenant_id')!r}, expected {tenant_id}",
    )
    _check("defaulted telemetry organization_name matches", body.get("organization_name") == TEST_ORG_NAME)


# =============================================================================
# Part 4: cleanup surface -- dashboard routes gone, legal/marketplace routes survive
# =============================================================================


def test_dashboard_routes_removed_legal_routes_survive(client: TestClient) -> None:
    _section("Part 4: dashboard routes removed; legal + marketplace routes survive")

    home_resp = client.get("/")
    _check("GET / returns 200 (public marketing homepage)", home_resp.status_code == 200)
    if home_resp.status_code == 200:
        _check("homepage links the official RVP logo", "/static/images/logo.png" in home_resp.text)
        _check("homepage names the Digital PMO employee", "Digital PMO" in home_resp.text)
        _check("homepage links the Agent Handbook", 'href="/guide"' in home_resp.text)
    _check("GET /dashboard is now 404 (tenant dashboard removed)", client.get("/dashboard").status_code == 404)
    _check(
        "GET /dashboard/{tenant_id} is now 404 (tenant dashboard removed)",
        client.get(f"/dashboard/{uuid.uuid4()}").status_code == 404,
    )

    privacy_resp = client.get("/privacy")
    terms_resp = client.get("/terms")
    guide_resp = client.get("/guide")
    _check("GET /privacy still returns 200 (Partner Center + manifest.json require this)", privacy_resp.status_code == 200)
    _check("GET /terms still returns 200 (Partner Center + manifest.json require this)", terms_resp.status_code == 200)
    _check("GET /guide returns 200 (Agent Handbook)", guide_resp.status_code == 200)
    if guide_resp.status_code == 200:
        body = guide_resp.text
        _check("guide contains Welcome heading", "Welcome &amp; Overview" in body or "Welcome & Overview" in body)
        _check("guide contains Swarm Capabilities heading", "Swarm Capabilities" in body)
        _check("guide contains Conversational Syntax heading", "Conversational Syntax" in body)
        _check("guide contains Project Tuning heading", "Project Tuning" in body)
        _check("guide nav links to Agent Handbook", "Agent Handbook" in body)

    landing_resp = client.get("/marketplace/landing", params={"token": "not-a-real-token"})
    _check(
        "GET /marketplace/landing still resolves (renders an error page for a bogus token rather than 404ing)",
        landing_resp.status_code in (200, 502),
        f"got {landing_resp.status_code}",
    )


def main() -> None:
    import api.main as m

    client = TestClient(m.app)

    tenant_id = _create_test_tenant()
    project_id: uuid.UUID | None = None
    default_project_id: uuid.UUID | None = None
    try:
        project_id = test_create_project(client, tenant_id)
        test_create_project_unknown_tenant(client)
        test_create_project_empty_name(client, tenant_id)

        if project_id is not None:
            test_get_project_brief(client, project_id, tenant_id)
        test_get_project_brief_unknown_project(client)

        # Runs with exactly one project on the test tenant so far -- must
        # stay before test_create_project_default_tenant below, which adds
        # a second project and would otherwise break this test's
        # active_project_count == 1 assertion.
        test_get_usage_telemetry(client, tenant_id)
        test_get_usage_telemetry_unknown_tenant(client)

        # Must run after the explicit-tenant_id project creation above and
        # before the default-project brief check below: this is the
        # freshest project (by updated_at) once it's created, which is
        # exactly what makes the *next* check's "omit project_id" fallback
        # deterministic.
        default_project_id = test_create_project_default_tenant(client, tenant_id)
        if default_project_id is not None:
            test_get_project_brief_default_project(client, default_project_id, "Copilot Zero-Config Test Project")

        test_get_usage_telemetry_default_tenant(client, tenant_id)

        test_dashboard_routes_removed_legal_routes_survive(client)
    finally:
        _section("Cleanup: deleting the throwaway test tenant (cascades project/artifacts/executions)")
        _cleanup_test_tenant(tenant_id)
        remaining = _load_test_tenant(tenant_id)
        _check("test tenant removed from the live database", remaining is None)

    _section("Result")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS: all Copilot API Bridge checks passed.")


if __name__ == "__main__":
    main()
