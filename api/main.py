"""Phase 8: Microsoft Teams API Layer -- the FastAPI server.

Wires the real `app_graph.build_app_graph` workflow (built once, at import
time, and reused across every Teams conversation -- `agent_framework`
`Workflow.run()` is safely re-entrant across turns, the same assumption
already relied on by `simulate_teams_webhook.py`/`simulate_exception_webhook.py`)
to Microsoft Teams via the Bot Framework Python SDK's `CloudAdapter`.

Local dev:
    uvicorn api.main:app --host 0.0.0.0 --port 3978 --reload

Then point the Bot Framework Emulator at http://localhost:3978/api/messages
(leave MicrosoftAppId/MicrosoftAppPassword blank in .env for anonymous/no-auth
local testing), or `ngrok http 3978` and put that HTTPS URL into an Azure Bot
Channels Registration's messaging endpoint to test against real Teams -- see
the Phase 8 plan for the full walkthrough.

Token validation notes (Azure Web Chat / Emulator 401s)
--------------------------------------------------------
Two independent things can make a request look "Unauthorized", and this
module now handles both without ever crashing the process or leaking a bare
500 to the channel:

1. Misconfiguration that would otherwise blow up at *import* time. The
   underlying SDK (`ConfigurationServiceClientCredentialFactory`) raises a
   bare `Exception` if `MicrosoftAppType=SingleTenant` /
   `UserAssignedMSI` is set but the companion `MicrosoftAppId` /
   `MicrosoftAppPassword` / `MicrosoftAppTenantId` fields are incomplete.
   `_build_adapter()` below catches that, logs a loud warning, and falls
   back to an anonymous (`MicrosoftAppId`/`MicrosoftAppPassword` blank,
   `MultiTenant`) configuration so local Emulator testing keeps working
   while the real credentials get fixed.
2. A genuinely unauthorized *request* (bad/missing/expired token, App ID
   mismatch, etc.), which the SDK signals by raising `PermissionError` out
   of `CloudAdapter.process_activity` -- confirmed against the installed
   `botframework-connector` source (`jwt_token_validation.py`,
   `channel_validation.py`, `emulator_validation.py` all raise
   `PermissionError`, never a subclass, for every auth failure mode). The
   `/api/messages` handler below now catches exactly that and returns a
   clean `401 JSONResponse` instead of an unhandled-exception 500.

One config gotcha that is *not* a code bug: once real
`MicrosoftAppId`/`MicrosoftAppPassword` are set (required for Azure Web Chat
/ Teams to authenticate at all), the plain Bot Framework Emulator must also
have that same App ID + password entered in its own connection settings --
otherwise the Emulator sends an unauthenticated request against a bot that
now requires authentication, and a 401 is the *correct* behavior, not a
misconfiguration. Leave both blank (in both places) for pure anonymous local
testing instead.

`MicrosoftAppType=MultiTenant` and a non-blank `MicrosoftAppTenantId` at the
same time is also flagged at startup: the SDK's own credential factory
silently ignores `MicrosoftAppTenantId` whenever the type isn't
`SingleTenant`/`UserAssignedMSI`, so that combination is almost always a
copy-paste leftover from switching app-registration types and is worth
double-checking against the actual Azure Bot resource.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import datetime, timezone

from botbuilder.core import ConversationState, MemoryStorage, TurnContext
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.schema import Activity, ActivityTypes
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from api.bot import PMOBot
from app_graph import (
    build_app_graph,
    build_default_agile_chat_agent,
    build_default_change_control_chat_agent,
    build_default_governance_chat_agent,
    build_default_pmp_chat_agent,
    build_default_router_chat_agent,
    default_checkpoint_storage,
)

logger = logging.getLogger(__name__)


_VALID_APP_TYPES = {"multitenant", "singletenant", "userassignedmsi"}


class DefaultConfig:
    """Read by `ConfigurationBotFrameworkAuthentication`, which expects an
    object with exactly these attribute names (confirmed against the Bot
    Framework Python SDK's own samples/docs).

    `TO_CHANNEL_FROM_BOT_LOGIN_URL`/`TO_CHANNEL_FROM_BOT_OAUTH_SCOPE` are
    read too (also by attribute name, via `getattr(..., None)` inside
    `ConfigurationBotFrameworkAuthentication.__init__`) -- they default to
    `None`, i.e. the SDK's normal behavior, but exist as an env-var escape
    hatch for the documented MultiTenant authority mismatch fix
    (https://aka.ms/bot-service-troubleshoot-authentication-problems)
    without needing another code change.
    """

    PORT = int(os.environ.get("PORT", 3978))
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")
    APP_TYPE = os.environ.get("MicrosoftAppType", "MultiTenant")
    APP_TENANTID = os.environ.get("MicrosoftAppTenantId", "")
    TO_CHANNEL_FROM_BOT_LOGIN_URL = os.environ.get("BotToChannelFromBotLoginUrl") or None
    TO_CHANNEL_FROM_BOT_OAUTH_SCOPE = os.environ.get("BotToChannelFromBotOAuthScope") or None


def _anonymous_fallback_config() -> DefaultConfig:
    """A `DefaultConfig`-shaped object with auth fully disabled.

    Used when the real configuration is broken in a way that would
    otherwise crash `ConfigurationServiceClientCredentialFactory` at import
    time (see `_build_adapter`). Real channels (Web Chat/Teams) won't
    authenticate against this, but the process stays up and the Emulator
    (with blank App ID/password) keeps working while the real config gets
    fixed.
    """
    fallback = DefaultConfig()
    fallback.APP_ID = ""
    fallback.APP_PASSWORD = ""
    fallback.APP_TYPE = "MultiTenant"
    fallback.APP_TENANTID = ""
    return fallback


def _validate_auth_config(config: DefaultConfig) -> None:
    """Log (never raise) on suspicious-but-not-necessarily-broken auth config.

    This is purely diagnostic -- it never mutates `config` -- so it can't
    itself introduce a fallback; `_build_adapter`'s try/except is what
    actually protects startup.
    """
    app_type = (config.APP_TYPE or "").strip().lower()

    if app_type not in _VALID_APP_TYPES:
        logger.warning(
            "MicrosoftAppType=%r is not one of %s; the SDK will treat it as "
            "MultiTenant.",
            config.APP_TYPE,
            sorted(_VALID_APP_TYPES),
        )

    if app_type == "multitenant" and config.APP_TENANTID:
        logger.warning(
            "MicrosoftAppType=MultiTenant but MicrosoftAppTenantId=%r is "
            "also set. The SDK's ConfigurationServiceClientCredentialFactory "
            "silently ignores MicrosoftAppTenantId for MultiTenant apps, so "
            "if your Azure Bot's App Registration is actually configured as "
            "single-tenant, incoming Web Chat/Teams tokens will fail "
            "validation with a PermissionError (surfaced by this API as a "
            "401, not a crash). Double check MicrosoftAppType against the "
            "App Registration's 'Supported account types' setting.",
            config.APP_TENANTID,
        )

    if app_type in ("singletenant", "userassignedmsi") and not config.APP_TENANTID:
        logger.warning(
            "MicrosoftAppType=%s requires MicrosoftAppTenantId; it is "
            "currently blank. Adapter construction will fall back to an "
            "anonymous configuration until this is fixed.",
            config.APP_TYPE,
        )

    if bool(config.APP_ID) != bool(config.APP_PASSWORD):
        logger.warning(
            "Exactly one of MicrosoftAppId/MicrosoftAppPassword is set "
            "(APP_ID=%s, APP_PASSWORD=%s). Both must be set together for "
            "authenticated channels, or both left blank for anonymous local "
            "testing.",
            bool(config.APP_ID),
            bool(config.APP_PASSWORD),
        )


CONFIG = DefaultConfig()


async def _on_turn_error(turn_context: TurnContext, error: Exception) -> None:
    logger.exception("[on_turn_error] unhandled error: %s", error)
    traceback.print_exc(file=sys.stderr)

    await turn_context.send_activity("The bot encountered an error processing that turn.")

    # Bot Framework Emulator convention: surface the raw error as a trace
    # activity so it shows up in the Emulator's log panel, not just stderr.
    if turn_context.activity.channel_id == "emulator":
        await turn_context.send_activity(
            Activity(
                label="TurnError",
                name="on_turn_error Trace",
                timestamp=datetime.now(timezone.utc),
                type=ActivityTypes.trace,
                value=str(error),
                value_type="https://www.botframework.com/schemas/error",
            )
        )


def _build_adapter(config: DefaultConfig) -> CloudAdapter:
    """Construct the CloudAdapter, falling back to an anonymous config
    rather than letting a broken `.env` crash the whole process at import
    time.

    `ConfigurationServiceClientCredentialFactory.__init__` (installed SDK,
    `botbuilder/integration/aiohttp/configuration_service_client_credential_factory.py`)
    raises a bare `Exception` -- not `PermissionError` -- when
    `MicrosoftAppType` is `SingleTenant`/`UserAssignedMSI` but the required
    companion fields (`APP_ID`/`APP_PASSWORD`/`APP_TENANTID`) are
    incomplete. Catching it here, instead of letting it propagate out of
    module import, is what actually keeps `uvicorn api.main:app` (and thus
    local Emulator testing) alive when the real credentials are wrong or
    still being provisioned.
    """
    _validate_auth_config(config)
    try:
        return CloudAdapter(ConfigurationBotFrameworkAuthentication(config))
    except Exception:  # noqa: BLE001 - deliberately broad; see docstring
        logger.exception(
            "Failed to build CloudAdapter from the configured "
            "MicrosoftAppType/MicrosoftAppId/MicrosoftAppPassword/"
            "MicrosoftAppTenantId. Falling back to an anonymous "
            "(auth-disabled) configuration -- Azure Web Chat and Teams will "
            "NOT authenticate until this is fixed, but local Emulator "
            "testing (with blank App ID/password) will keep working."
        )
        return CloudAdapter(
            ConfigurationBotFrameworkAuthentication(_anonymous_fallback_config())
        )


ADAPTER = _build_adapter(CONFIG)
ADAPTER.on_turn_error = _on_turn_error

# One shared workflow + checkpoint storage for the whole process, exactly the
# shape `build_app_graph`/`run_turn` already expect (see
# `simulate_teams_webhook.py`/`simulate_exception_webhook.py`, which rebuild
# the same graph shape against the same `FileCheckpointStorage` to resume a
# paused run from a second, independent process -- here it's one long-lived
# process instead of two short-lived scripts).
_checkpoint_storage = default_checkpoint_storage()
_workflow = build_app_graph(
    build_default_router_chat_agent(),
    change_control_chat_agent=build_default_change_control_chat_agent(),
    pmp_chat_agent=build_default_pmp_chat_agent(),
    agile_chat_agent=build_default_agile_chat_agent(),
    governance_chat_agent=build_default_governance_chat_agent(),
    checkpoint_storage=_checkpoint_storage,
)

# Dev-only: in-process, lost on restart and not shared across multiple
# instances. Swap for CosmosDbPartitionedStorage/Blob (or a Phase-7-Postgres-
# backed Storage) before any real deployment -- flagged in the Phase 8 plan.
CONVERSATION_STATE = ConversationState(MemoryStorage())

BOT = PMOBot(CONVERSATION_STATE, _workflow, _checkpoint_storage)

app = FastAPI(title="GIABO Digital PMO -- Teams Bot")


@app.post("/api/messages")
async def messages(request: Request):
    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    try:
        invoke_response = await ADAPTER.process_activity(auth_header, activity, BOT.on_turn)
    except PermissionError as exc:
        # Every auth failure path in the installed botframework-connector
        # (jwt_token_validation.py, channel_validation.py,
        # emulator_validation.py, ...) raises PermissionError, never a
        # subclass or a different type -- confirmed by grepping the
        # installed package. Without this handler, process_activity's
        # PermissionError propagates straight out of this route and
        # FastAPI turns it into an unhandled 500, which is strictly worse
        # than a clean 401 for both Azure Web Chat's own error reporting
        # and anyone tailing these logs.
        logger.warning(
            "Rejecting unauthorized activity from channel_id=%s: %s",
            getattr(activity, "channel_id", "?"),
            exc,
        )
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": str(exc)},
        )
    except Exception:  # noqa: BLE001 - last-resort safety net for this route
        logger.exception("Unhandled error while processing an incoming activity")
        return JSONResponse(
            status_code=500,
            content={"error": "InternalServerError"},
        )

    if invoke_response:
        return JSONResponse(content=invoke_response.body, status_code=invoke_response.status)
    return Response(status_code=201)


@app.get("/api/messages")
async def health() -> dict:
    # Azure App Service (and similar) liveness probes GET the messaging
    # endpoint before any real Activity POST arrives -- without this, they'd
    # see a 405 Method Not Allowed and could mark the app unhealthy.
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=CONFIG.PORT, reload=True)
