"""SharePoint document library delta sync (Phase: Graph Integration).

Syncs a project's SharePoint document libraries into the Phase 1
`document_cache` table (`db/schema.sql`), using Microsoft Graph's delta query
on each drive's root -- which transparently unifies the two ingestion
branches from 07-maf-digital-pmo-sop.mdc: calling delta with no resume token
IS the "Initiation Phase: full site ingestion" cold start, and calling it
with a saved token/link IS "Steady-State Monitoring: Delta ingestion".

Content handling is metadata-first: no document-parsing library
(python-docx/pypdf/etc.) is installed, so `extracted_json` is never
populated here. Every file within `max_file_bytes` gets a real
`sha256(raw_bytes)` `content_hash` (dedup value, per
`document_cache`'s comment); files whose name/MIME type look
text-representable additionally get `raw_content` populated. Oversized
files, and any `file`-faceted item Graph didn't hand us a download URL for,
are skipped entirely for that run (not written or overwritten) rather than
guessing at a hash for content we never read -- `document_cache.content_hash`
is `NOT NULL`, so we never write a row without one.

Delta resume tokens: `document_cache.delta_token` is a per-item column, but
Graph's delta cursor (`@odata.deltaLink`) is per-drive, not per-item. To
guarantee forward progress even on a run where nothing changed (so no real
item row gets touched/stamped), each drive gets one small sentinel/cursor row
-- `sharepoint_item_id = "__delta_cursor__:<drive_id>"`, `source_type =
"_delta_cursor"`, no content -- that's upserted with the latest deltaLink on
every run.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
from typing import Any, Optional

import httpx
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, text

try:  # pragma: no cover - exercised only when msgraph-sdk is installed
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except ImportError:  # pragma: no cover
    pg_insert = None  # type: ignore[assignment]

from core.graph_client import build_graph_client
from db.models import DocumentCache, Project
from db.session import get_session

logger = logging.getLogger(__name__)

# 10 MB default -- generous enough for most PMO artifacts (status reports,
# RAID exports, meeting notes) without risking a multi-hundred-MB video/CAD
# file blocking a background sync run. Overridable per-deployment.
DEFAULT_MAX_FILE_BYTES = int(os.environ.get("SHAREPOINT_SYNC_MAX_FILE_BYTES", str(10 * 1024 * 1024)))

_DELTA_CURSOR_PREFIX = "__delta_cursor__:"
_DELTA_CURSOR_SOURCE_TYPE = "_delta_cursor"

_TEXT_MIME_PREFIXES = ("text/",)
_TEXT_MIME_EXACT = frozenset({"application/json"})
_TEXT_EXTENSIONS = frozenset({".txt", ".md", ".csv", ".json", ".yaml", ".yml"})


class SyncStats(BaseModel):
    """Returned by `sync_project_documents` -- one run's summary."""

    drives_synced: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    skipped_folders: int = 0
    skipped_oversized: int = 0
    skipped_no_download_url: int = 0


def _delta_cursor_item_id(drive_id: str) -> str:
    return f"{_DELTA_CURSOR_PREFIX}{drive_id}"


def _is_text_like(name: str, mime_type: Optional[str]) -> bool:
    if mime_type and (mime_type.startswith(_TEXT_MIME_PREFIXES) or mime_type in _TEXT_MIME_EXACT):
        return True
    lowered = name.lower()
    return any(lowered.endswith(ext) for ext in _TEXT_EXTENSIONS)


async def _list_all_drives(graph_client: Any, site_id: str) -> list[Any]:
    """`GET /sites/{site_id}/drives`, following `@odata.nextLink` -- a site
    rarely has more than a handful of document libraries, but a large
    tenant's site could still paginate.
    """
    drives_builder = graph_client.sites.by_site_id(site_id).drives
    response = await drives_builder.get()
    drives: list[Any] = []
    while response is not None:
        drives.extend(response.value or [])
        next_link = response.odata_next_link
        if not next_link:
            break
        response = await drives_builder.with_url(next_link).get()
    return drives


async def _fetch_all_delta_items(
    graph_client: Any, drive_id: str, resume_link: Optional[str]
) -> tuple[list[Any], Optional[str]]:
    """Page through `/drives/{drive_id}/root/delta` (resuming from
    `resume_link` if given -- a cold start, no prior sentinel row, uses
    `None`) until Graph hands back `@odata.deltaLink`, i.e. "you're caught
    up". Returns every changed `DriveItem` across all pages plus that final
    deltaLink to persist for next time.

    Accumulates in memory rather than streaming/yielding: this is a
    background sync job, not a latency-sensitive request path, and a single
    drive's delta page count is bounded by how much changed since the last
    run -- unbounded only on the very first (cold-start) run against an
    enormous drive, which is an intentional, documented limitation (see
    module docstring) rather than something worth a generator-based rewrite
    up front.
    """
    item_builder = graph_client.drives.by_drive_id(drive_id).items.by_drive_item_id("root")
    response = await (item_builder.delta.with_url(resume_link).get() if resume_link else item_builder.delta.get())

    items: list[Any] = []
    final_delta_link: Optional[str] = None
    while response is not None:
        items.extend(response.value or [])
        if response.odata_delta_link:
            final_delta_link = response.odata_delta_link
            break
        next_link = response.odata_next_link
        if not next_link:
            break
        response = await item_builder.delta.with_url(next_link).get()

    return items, final_delta_link


async def _download_and_classify(
    http_client: httpx.AsyncClient, item: Any, max_file_bytes: int
) -> Optional[tuple[str, Optional[str], str]]:
    """Returns `(content_hash, raw_content_or_None, source_type)`, or `None`
    if this item shouldn't be cached this run (oversized, or Graph gave us no
    download URL -- e.g. a malware-blocked file). Caller is responsible for
    bumping the matching skip counter on `None`.
    """
    size = item.size or 0
    if size > max_file_bytes:
        return None

    download_url = (item.additional_data or {}).get("@microsoft.graph.downloadUrl")
    if not download_url:
        return None

    response = await http_client.get(download_url)
    response.raise_for_status()
    raw_bytes = response.content
    content_hash = hashlib.sha256(raw_bytes).hexdigest()

    mime_type = item.file.mime_type if item.file else None
    if _is_text_like(item.name or "", mime_type):
        return content_hash, raw_bytes.decode("utf-8", errors="replace"), "document"
    return content_hash, None, "binary"


def _upsert_document_cache(
    session: Any,
    *,
    project_id: str,
    sharepoint_item_id: str,
    sharepoint_drive_id: Optional[str],
    item_path: Optional[str],
    delta_token: Optional[str],
    source_type: str,
    content_hash: str,
    raw_content: Optional[str],
    sharepoint_last_modified_at: Any = None,
) -> bool:
    """Upserts one `document_cache` row keyed on the table's
    `(project_id, sharepoint_item_id)` unique constraint. Returns whether
    this was an INSERT (`True`) or an UPDATE (`False`), via Postgres's
    `xmax = 0` trick, so the caller can attribute it to `SyncStats`'
    `items_created` vs `items_updated` without a separate SELECT.

    Deliberately omits `first_seen_at` from the `DO UPDATE SET` clause so a
    re-synced item keeps its original first-seen timestamp.
    """
    stmt = pg_insert(DocumentCache).values(
        project_id=project_id,
        content_hash=content_hash,
        sharepoint_drive_id=sharepoint_drive_id,
        sharepoint_item_id=sharepoint_item_id,
        item_path=item_path,
        delta_token=delta_token,
        source_type=source_type,
        raw_content=raw_content,
        sharepoint_last_modified_at=sharepoint_last_modified_at,
        last_seen_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "sharepoint_item_id"],
        set_={
            "content_hash": stmt.excluded.content_hash,
            "sharepoint_drive_id": stmt.excluded.sharepoint_drive_id,
            "item_path": stmt.excluded.item_path,
            "delta_token": stmt.excluded.delta_token,
            "source_type": stmt.excluded.source_type,
            "raw_content": stmt.excluded.raw_content,
            "sharepoint_last_modified_at": stmt.excluded.sharepoint_last_modified_at,
            "last_seen_at": func.now(),
        },
    ).returning(DocumentCache.id, text("(xmax = 0) AS is_insert"))

    row = session.execute(stmt).mappings().one()
    return bool(row["is_insert"])


def _delete_document_cache_row(session: Any, *, project_id: str, sharepoint_item_id: str) -> bool:
    result = session.execute(
        sa_delete(DocumentCache).where(
            DocumentCache.project_id == project_id,
            DocumentCache.sharepoint_item_id == sharepoint_item_id,
        )
    )
    return result.rowcount > 0


async def _process_drive_item(
    session: Any,
    http_client: httpx.AsyncClient,
    *,
    project_id: str,
    drive_id: str,
    item: Any,
    max_file_bytes: int,
    delta_token: Optional[str],
    stats: SyncStats,
) -> None:
    if item.deleted is not None:
        if _delete_document_cache_row(session, project_id=project_id, sharepoint_item_id=item.id):
            stats.items_deleted += 1
        return

    if item.folder is not None:
        stats.skipped_folders += 1
        return

    if item.file is None:
        # Not a plain file (e.g. a list-item-only entry with no file
        # content) -- nothing for this cache to hold.
        return

    classified = await _download_and_classify(http_client, item, max_file_bytes)
    if classified is None:
        size = item.size or 0
        if size > max_file_bytes:
            stats.skipped_oversized += 1
        else:
            stats.skipped_no_download_url += 1
        return
    content_hash, raw_content, source_type = classified

    item_path = None
    if item.parent_reference is not None and item.parent_reference.path:
        item_path = f"{item.parent_reference.path}/{item.name}"

    is_insert = _upsert_document_cache(
        session,
        project_id=project_id,
        sharepoint_item_id=item.id,
        sharepoint_drive_id=drive_id,
        item_path=item_path,
        delta_token=delta_token,
        source_type=source_type,
        content_hash=content_hash,
        raw_content=raw_content,
        sharepoint_last_modified_at=item.last_modified_date_time,
    )
    if is_insert:
        stats.items_created += 1
    else:
        stats.items_updated += 1


async def _sync_drive(
    graph_client: Any,
    http_client: httpx.AsyncClient,
    *,
    project_id: str,
    drive_id: str,
    max_file_bytes: int,
    stats: SyncStats,
) -> None:
    cursor_item_id = _delta_cursor_item_id(drive_id)
    with get_session() as session:
        resume_link = session.execute(
            select(DocumentCache.delta_token).where(
                DocumentCache.project_id == project_id,
                DocumentCache.sharepoint_item_id == cursor_item_id,
            )
        ).scalar_one_or_none()

    drive_items, final_delta_link = await _fetch_all_delta_items(graph_client, drive_id, resume_link)

    with get_session() as session:
        for item in drive_items:
            await _process_drive_item(
                session,
                http_client,
                project_id=project_id,
                drive_id=drive_id,
                item=item,
                max_file_bytes=max_file_bytes,
                delta_token=final_delta_link,
                stats=stats,
            )

        if final_delta_link:
            # Always stamped, even when `drive_items` was empty -- this is
            # the only thing guaranteeing next run's resume point advances on
            # a zero-change sync (see module docstring).
            _upsert_document_cache(
                session,
                project_id=project_id,
                sharepoint_item_id=cursor_item_id,
                sharepoint_drive_id=drive_id,
                item_path=None,
                delta_token=final_delta_link,
                source_type=_DELTA_CURSOR_SOURCE_TYPE,
                content_hash=hashlib.sha256(final_delta_link.encode()).hexdigest(),
                raw_content=None,
            )
        else:
            logger.warning(
                "sync_project_documents: drive %s never returned an @odata.deltaLink "
                "(unexpectedly large first page?) -- resume cursor NOT advanced this run.",
                drive_id,
            )


async def sync_project_documents(project_id: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> SyncStats:
    """Sync every document library (drive) on `project_id`'s SharePoint site
    into `document_cache`. Safe to call repeatedly/on a schedule -- a run
    with no upstream changes is a cheap no-op past the initial delta call.
    """
    stats = SyncStats()

    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"sync_project_documents: no project found for project_id={project_id!r}")
        if not project.sharepoint_site_id:
            raise ValueError(f"sync_project_documents: project {project_id!r} has no sharepoint_site_id configured")
        site_id = project.sharepoint_site_id
        customer_tenant_id = str(project.tenant.azure_customer_tenant_id)

    graph_client = build_graph_client(customer_tenant_id)
    drives = await _list_all_drives(graph_client, site_id)

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        for drive in drives:
            await _sync_drive(
                graph_client,
                http_client,
                project_id=project_id,
                drive_id=drive.id,
                max_file_bytes=max_file_bytes,
                stats=stats,
            )
            stats.drives_synced += 1

    return stats


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Sync a project's SharePoint document libraries into document_cache.")
    parser.add_argument("--project-id", required=True, help="projects.id (UUID) to sync.")
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_MAX_FILE_BYTES,
        help=f"Files larger than this are skipped this run (default {DEFAULT_MAX_FILE_BYTES}).",
    )
    args = parser.parse_args()

    stats = asyncio.run(sync_project_documents(args.project_id, max_file_bytes=args.max_file_bytes))
    print(stats.model_dump_json(indent=2))


if __name__ == "__main__":
    _main()
