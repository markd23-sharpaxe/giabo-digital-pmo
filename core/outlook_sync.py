"""Outlook inbox poller — emit EMAIL_RECEIVED onto the central event_bus.

Scans unread messages in `projects.digital_employee_email` via Microsoft Graph
(`Mail.ReadWrite` through the app-only `.default` token in
`core.graph_client.build_graph_client`). After a successful bus persist, the
message is marked read so the next poll does not re-emit it.

This is a callable helper + CLI, not a cron node. Matches SharePoint delta
sync: safe to invoke repeatedly; a run with no unread mail is a no-op.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any, Optional

from pydantic import BaseModel

from core.graph_client import build_graph_client
from db.models import Project
from db.session import get_session
from maf_graph_state import BlackboardEvent, EventType, record_ingress_event

logger = logging.getLogger(__name__)


class OutlookSyncStats(BaseModel):
    messages_seen: int = 0
    events_emitted: int = 0
    marked_read: int = 0
    persist_failed: int = 0


def _sender_address(message: Any) -> Optional[str]:
    sender = getattr(message, "from_", None) or getattr(message, "sender", None)
    email = getattr(getattr(sender, "email_address", None), "address", None)
    return email


async def _list_unread_inbox(graph_client: Any, mailbox: str) -> list[Any]:
    """GET /users/{mailbox}/mailFolders/inbox/messages?$filter=isRead eq false."""
    from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (
        MessagesRequestBuilder,
    )

    inbox = graph_client.users.by_user_id(mailbox).mail_folders.by_mail_folder_id("inbox").messages
    query = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
        filter="isRead eq false",
        select=["id", "subject", "from", "receivedDateTime", "bodyPreview"],
        top=50,
    )
    config = MessagesRequestBuilder.MessagesRequestBuilderGetRequestConfiguration(query_parameters=query)
    response = await inbox.get(request_configuration=config)
    messages: list[Any] = []
    while response is not None:
        messages.extend(response.value or [])
        next_link = getattr(response, "odata_next_link", None)
        if not next_link:
            break
        response = await inbox.with_url(next_link).get()
    return messages


async def _mark_message_read(graph_client: Any, mailbox: str, message_id: str) -> None:
    from msgraph.generated.models.message import Message

    patch = Message()
    patch.is_read = True
    await graph_client.users.by_user_id(mailbox).messages.by_message_id(message_id).patch(patch)


async def poll_project_inbox(project_id: str) -> OutlookSyncStats:
    """Emit EMAIL_RECEIVED for each unread inbox message, then mark them read."""
    stats = OutlookSyncStats()

    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"poll_project_inbox: no project found for project_id={project_id!r}")
        mailbox = project.digital_employee_email
        if not mailbox:
            raise ValueError(
                f"poll_project_inbox: project {project_id!r} has no digital_employee_email configured"
            )
        customer_tenant_id = str(project.tenant.azure_customer_tenant_id)

    graph_client = build_graph_client(customer_tenant_id)
    messages = await _list_unread_inbox(graph_client, mailbox)
    stats.messages_seen = len(messages)

    for message in messages:
        message_id = message.id
        event = BlackboardEvent(
            event_type=EventType.EMAIL_RECEIVED,
            publisher="outlook_inbox_ingestion",
            project_id=str(project_id),
            correlation_id=message_id,
            payload={
                "message_id": message_id,
                "subject": message.subject,
                "from": _sender_address(message),
                "received_at": (
                    message.received_date_time.isoformat() if message.received_date_time else None
                ),
                "body_preview": message.body_preview,
            },
        )
        if record_ingress_event(str(project_id), event):
            stats.events_emitted += 1
            try:
                await _mark_message_read(graph_client, mailbox, message_id)
                stats.marked_read += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("outlook_sync: failed to mark %s read: %s", message_id, exc)
        else:
            stats.persist_failed += 1
            logger.warning(
                "outlook_sync: skipped mark-read for %s because event_bus persist failed",
                message_id,
            )

    return stats


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Poll a project's digital-employee Outlook inbox onto event_bus."
    )
    parser.add_argument("--project-id", required=True, help="projects.id (UUID) to poll.")
    args = parser.parse_args()

    stats = asyncio.run(poll_project_inbox(args.project_id))
    print(stats.model_dump_json(indent=2))


if __name__ == "__main__":
    _main()
