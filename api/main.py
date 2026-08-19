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


class DefaultConfig:
    """Read by `ConfigurationBotFrameworkAuthentication`, which expects an
    object with exactly these attribute names (confirmed against the Bot
    Framework Python SDK's own samples/docs)."""

    PORT = int(os.environ.get("PORT", 3978))
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")
    APP_TYPE = os.environ.get("MicrosoftAppType", "MultiTenant")
    APP_TENANTID = os.environ.get("MicrosoftAppTenantId", "")


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


ADAPTER = CloudAdapter(ConfigurationBotFrameworkAuthentication(CONFIG))
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

    invoke_response = await ADAPTER.process_activity(auth_header, activity, BOT.on_turn)
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
