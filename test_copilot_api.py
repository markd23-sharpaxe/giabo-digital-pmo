"""Validation for the Microsoft 365 Copilot Declarative Agent API Bridge
(Declarative Agent Architecture Pivot).

Not a pytest suite (none is installed in this project's `.venv`) -- a
standalone, narratable script, same style as `test_live_agent_turn.py` /
`test_marketplace_integration.py`. Runs against the REAL live Azure Postgres
from `.env` and the FULL `api.main.app` (so the removed dashboard routes and
the surviving legal/marketplace routes are exercised through the actual
mounted app, not a bare router).

Creates one throwaway tenant/project/pmo_artifact/agent_execution, exercises
all three `api/copilot.py` operations end-to-end, and deletes everything it
created (cascade deletes handle the project, artifact, execution, and
framework-acceptance rows once the tenant is removed).

The caller is the throwaway company's Entra tenant id. Omitted project and
tenant ids resolve inside that company, not to whichever row was updated
last in the whole database.

Run:
    .venv/bin/python test_copilot_api.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.copilot import get_copilot_caller
from api.entra_auth import CopilotCaller
from db.models import (
    AgentExecution,
    AgentTier,
    ArtifactType,
    GraphAdminConsent,
    ExecutionStatus,
    PlanTier,
    PmoArtifact,
    Project,
    SwarmStatus,
    Tenant,
    TriggerType,
)
from db.session import get_session

FAILURES: list[str] = []

TEST_SUBSCRIPTION_ID = uuid.uuid4()
TEST_CUSTOMER_TENANT_ID = uuid.uuid4()
TEST_USER_OBJECT_ID = uuid.uuid4()
OTHER_USER_OBJECT_ID = uuid.uuid4()
TEST_ORG_NAME = "Copilot API Bridge Test Org"
CALLER = {"tid": TEST_CUSTOMER_TENANT_ID, "oid": TEST_USER_OBJECT_ID}

MANAGER = {
    "project_manager_name": "Ada Lovelace",
    "project_manager_email": "ada.lovelace@example.com",
}


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
        # Comment kept next to the status: this tenant is the signed-in
        # company, matched by azure_customer_tenant_id, not by being the
        # newest ACTIVE row in the database.
        session.add(tenant)
        session.flush()
        session.refresh(tenant)
        return tenant.id


def _cleanup_test_tenant(tenant_id: uuid.UUID) -> None:
    with get_session() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is not None:
            session.delete(tenant)


def _signed_in_caller() -> CopilotCaller:
    return CopilotCaller(
        entra_tenant_id=CALLER["tid"],
        entra_object_id=CALLER["oid"],
        display_name="Ada Lovelace",
        email="ada.lovelace@example.com",
    )


def _project_count(tenant_id: uuid.UUID) -> int:
    with get_session() as session:
        return session.execute(
            select(func.count()).select_from(Project).where(Project.tenant_id == tenant_id)
        ).scalar_one()


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
        "accept_framework": True,
        **MANAGER,
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
            _check("db row project manager name matches", row.project_manager_name == MANAGER["project_manager_name"])
            _check("db row project manager email matches", row.project_manager_email == MANAGER["project_manager_email"])
    _check("response records the project manager", body.get("project_manager_name") == MANAGER["project_manager_name"])
    _check("response records the project manager email", body.get("project_manager_email") == MANAGER["project_manager_email"])
    _check("response records framework acceptance", body.get("framework_accepted") is True)

    return project_id


def test_create_project_unknown_tenant(client: TestClient) -> None:
    _section("Part 1b: POST /api/projects/create -- another organization's tenant_id is refused")

    resp = client.post(
        "/api/projects/create",
        json={"tenant_id": str(uuid.uuid4()), "name": "Should Not Be Created", "accept_framework": True, **MANAGER},
    )
    _check("foreign tenant_id returns 403", resp.status_code == 403, resp.text[:300])


def test_framework_not_accepted_writes_nothing(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 1a: POST /api/projects/create -- framework not accepted")

    before = _project_count(tenant_id)
    resp = client.post("/api/projects/create", json={"name": "Should Not Land", **MANAGER})
    _check("missing framework acceptance returns 422", resp.status_code == 422, resp.text[:300])
    _check("rejected create writes no project", _project_count(tenant_id) == before)


def test_unsubscribed_company_writes_nothing(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 1a2: POST /api/projects/create -- company has no subscription")

    before = _project_count(tenant_id)
    CALLER["tid"] = uuid.uuid4()
    try:
        resp = client.post(
            "/api/projects/create",
            json={"name": "No Subscription", "accept_framework": True, **MANAGER},
        )
        _check("unsubscribed company returns 404", resp.status_code == 404, resp.text[:300])
        _check("unsubscribed create writes no project", _project_count(tenant_id) == before)
    finally:
        CALLER["tid"] = TEST_CUSTOMER_TENANT_ID


def test_other_user_must_accept(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 1e: a colleague in the same company must accept the framework")

    before = _project_count(tenant_id)
    CALLER["oid"] = OTHER_USER_OBJECT_ID
    try:
        resp = client.post("/api/projects/create", json={"name": "Colleague Project", **MANAGER})
        _check("a different user without acceptance returns 422", resp.status_code == 422, resp.text[:300])
        _check("the other user's rejection writes no project", _project_count(tenant_id) == before)
    finally:
        CALLER["oid"] = TEST_USER_OBJECT_ID


def test_setup_card_shows_framework() -> None:
    _section("Part 1f: project setup card shows the manager and framework acceptance")

    card = Path("appPackage/projectSetupCard.json").read_text()
    _check("setup card names the GIABO framework", "GIABO framework" in card)
    _check("setup card binds the project manager name", "project_manager_name" in card)
    _check("setup card binds the project manager email", "project_manager_email" in card)


def test_create_project_empty_name(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 1c: POST /api/projects/create -- empty name is rejected")

    resp = client.post(
        "/api/projects/create",
        json={"tenant_id": str(tenant_id), "name": "   ", "accept_framework": True, **MANAGER},
    )
    _check("empty name returns 422", resp.status_code == 422, resp.text[:300])


def test_create_project_default_tenant(client: TestClient, tenant_id: uuid.UUID) -> uuid.UUID | None:
    _section("Part 1d: POST /api/projects/create -- same person, second project, framework already accepted")

    resp = client.post("/api/projects/create", json={"name": "Copilot Zero-Config Test Project", **MANAGER})
    _check("create with omitted tenant_id returns 200", resp.status_code == 200, resp.text[:300])
    if resp.status_code != 200:
        return None

    body = resp.json()
    _check(
        "defaulted project's tenant_id is our freshest ACTIVE test tenant",
        body.get("tenant_id") == str(tenant_id),
        f"got tenant_id={body.get('tenant_id')!r}, expected {tenant_id}",
    )
    _check(
        "second project copies the mailbox from the first",
        body.get("digital_employee_email") == "ada@example.com",
    )
    return uuid.UUID(body["id"])


def test_first_project_requires_mailbox(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 1g: the first project for a person requires a team mailbox")

    before = _project_count(tenant_id)
    CALLER["oid"] = uuid.uuid4()
    try:
        resp = client.post(
            "/api/projects/create",
            json={"name": "No Mailbox Yet", "accept_framework": True, **MANAGER},
        )
        _check("first project without a mailbox returns 422", resp.status_code == 422, resp.text[:300])
        _check("missing mailbox writes no project", _project_count(tenant_id) == before)
    finally:
        CALLER["oid"] = TEST_USER_OBJECT_ID


def test_changed_mailbox_updates_existing_projects(client: TestClient, tenant_id: uuid.UUID) -> None:
    _section("Part 1h: a new mailbox replaces the saved one on every project for this person")

    resp = client.post(
        "/api/projects/create",
        json={"name": "Mailbox Change", "digital_employee_email": "pm@example.com", **MANAGER},
    )
    _check("changing the mailbox returns 200", resp.status_code == 200, resp.text[:300])
    if resp.status_code != 200:
        return

    with get_session() as session:
        emails = session.execute(
            select(Project.digital_employee_email).where(
                Project.tenant_id == tenant_id,
                Project.project_manager_entra_id == TEST_USER_OBJECT_ID,
            )
        ).scalars().all()
    _check("every project for this person uses the new mailbox", set(emails) == {"pm@example.com"}, emails)


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
    _check("telemetry returns the mailbox saved on the first project", body.get("team_mailbox") == "ada@example.com")
    _check("telemetry reports Microsoft access not yet approved", body.get("microsoft_access_approved") is False)
    _check("telemetry includes the approval link", "/admin-consent" in (body.get("microsoft_access_url") or ""))


def test_get_usage_telemetry_unknown_tenant(client: TestClient) -> None:
    _section("Part 3b: GET /api/usage/telemetry -- another organization's tenant_id is refused")

    resp = client.get("/api/usage/telemetry", params={"tenant_id": str(uuid.uuid4())})
    _check("foreign tenant_id returns 403", resp.status_code == 403, resp.text[:300])


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


def test_admin_consent(client: TestClient) -> None:
    _section("Part 4a: Microsoft admin consent link")

    start = client.get("/admin-consent", follow_redirects=False)
    location = start.headers.get("location", "")
    _check(
        "approval link redirects to Microsoft",
        start.status_code == 302 and "login.microsoftonline.com/organizations/v2.0/adminconsent" in location,
        location[:240],
    )
    _check(
        "redirect carries the callback address",
        "admin-consent/callback" in location or "admin-consent%2Fcallback" in location,
        location[:240],
    )

    denied = client.get(
        "/admin-consent/callback",
        params={"error": "access_denied", "error_description": "AADSTS90094: admin approval required"},
    )
    _check(
        "a person who cannot approve is told to send the link",
        denied.status_code == 200 and "Microsoft 365 administrator" in denied.text,
        denied.text[:240],
    )

    approved = client.get(
        "/admin-consent/callback",
        params={"admin_consent": "True", "tenant": str(TEST_CUSTOMER_TENANT_ID)},
    )
    _check(
        "administrator approval page confirms access",
        approved.status_code == 200 and "Access is approved" in approved.text,
        approved.text[:240],
    )

    telemetry = client.get("/api/usage/telemetry")
    body = telemetry.json() if telemetry.status_code == 200 else {}
    _check("telemetry records this company as approved", body.get("microsoft_access_approved") is True, telemetry.text[:240])

    manifest = Path("appPackage/manifest.json").read_text()
    _check("Teams package is tied to the Entra app", "webApplicationInfo" in manifest)

    with get_session() as session:
        row = session.get(GraphAdminConsent, TEST_CUSTOMER_TENANT_ID)
        if row is not None:
            session.delete(row)


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
    about_resp = client.get("/aboutus")
    _check("GET /aboutus returns 200", about_resp.status_code == 200, about_resp.text[:240])
    if about_resp.status_code == 200:
        about_body = about_resp.text
        _check("about page contains the hero title", "Moving Project Management from Typist to Chief of Staff" in about_body)
        _check("about page contains the waitlist button", "Get Early Access" in about_body)
        _check("about page names the founder", "Mark Durnin, Managing Director" in about_body)
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

    m.app.dependency_overrides[get_copilot_caller] = _signed_in_caller
    client = TestClient(m.app)

    tenant_id = _create_test_tenant()
    project_id: uuid.UUID | None = None
    default_project_id: uuid.UUID | None = None
    try:
        test_framework_not_accepted_writes_nothing(client, tenant_id)
        test_unsubscribed_company_writes_nothing(client, tenant_id)
        project_id = test_create_project(client, tenant_id)
        test_create_project_unknown_tenant(client)
        test_create_project_empty_name(client, tenant_id)
        test_setup_card_shows_framework()

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
        test_other_user_must_accept(client, tenant_id)
        test_first_project_requires_mailbox(client, tenant_id)
        default_project_id = test_create_project_default_tenant(client, tenant_id)
        if default_project_id is not None:
            test_get_project_brief_default_project(client, default_project_id, "Copilot Zero-Config Test Project")
        test_changed_mailbox_updates_existing_projects(client, tenant_id)

        test_get_usage_telemetry_default_tenant(client, tenant_id)

        test_admin_consent(client)
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
