"""Ingest `test_docs/` fixtures into the live `document_cache` (content-addressed).

Idempotent SHA-256 upsert keyed on `(project_id, sharepoint_item_id)` with
`sharepoint_item_id = "test_docs:<filename>"` and `source_type = "test_docs"`.
Does not call Microsoft Graph -- production ingest remains `core.sharepoint_sync`.

Resolves the live project as `Live Prod Project` (id
`22222222-2222-2222-2222-222222222222`) if that row exists, otherwise
`Project Delta`.

Run:
    .venv/bin/python upload_test_docs.py
    .venv/bin/python upload_test_docs.py --cleanup
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import DocumentCache, Project
from db.session import get_session
from maf_graph_state import BlackboardEvent, EventType, record_ingress_event

TEST_DOCS_DIR = Path(__file__).resolve().parent / "test_docs"
SOURCE_TYPE = "test_docs"
LIVE_PROD_PROJECT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
LIVE_PROD_PROJECT_NAME = "Live Prod Project"
FALLBACK_PROJECT_NAME = "Project Delta"

FAILURES: list[str] = []


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def _resolve_project() -> tuple[uuid.UUID, str]:
    from sqlalchemy.exc import OperationalError

    try:
        return _resolve_project_inner()
    except OperationalError as exc:
        print(
            "FAIL: cannot reach Azure Postgres (firewall / timeout). "
            f"Add this machine's public IP to the server firewall. Detail: {exc.orig}"
        )
        sys.exit(1)


def _resolve_project_inner() -> tuple[uuid.UUID, str]:
    with get_session() as session:
        live = session.get(Project, LIVE_PROD_PROJECT_ID)
        if live is not None:
            return live.id, live.name
        fallback = session.execute(select(Project).where(Project.name == FALLBACK_PROJECT_NAME)).scalar_one_or_none()
        if fallback is None:
            print(
                f"FAIL: neither {LIVE_PROD_PROJECT_NAME!r} nor {FALLBACK_PROJECT_NAME!r} exists in the live database."
            )
            sys.exit(1)
        return fallback.id, fallback.name


def _upsert_document_cache(
    session,
    *,
    project_id: uuid.UUID,
    sharepoint_item_id: str,
    item_path: str,
    content_hash: str,
    raw_content: str,
) -> bool:
    """Same content-addressed `(project_id, sharepoint_item_id)` upsert as
    `core.sharepoint_sync._upsert_document_cache`, without pulling in Graph."""
    stmt = pg_insert(DocumentCache).values(
        project_id=project_id,
        content_hash=content_hash,
        sharepoint_drive_id=None,
        sharepoint_item_id=sharepoint_item_id,
        item_path=item_path,
        delta_token=None,
        source_type=SOURCE_TYPE,
        raw_content=raw_content,
        sharepoint_last_modified_at=None,
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
    ).returning(DocumentCache.id, literal_column("(xmax = 0)").label("is_insert"))
    row = session.execute(stmt).mappings().one()
    return bool(row["is_insert"])


def _fixture_files() -> list[Path]:
    if not TEST_DOCS_DIR.is_dir():
        print(f"FAIL: {TEST_DOCS_DIR} does not exist.")
        sys.exit(1)
    files = sorted(p for p in TEST_DOCS_DIR.iterdir() if p.is_file() and not p.name.startswith("."))
    if not files:
        print(f"FAIL: {TEST_DOCS_DIR} is empty.")
        sys.exit(1)
    return files


def _ingest(project_id: uuid.UUID) -> None:
    _section("Ingest test_docs/ into document_cache")
    files = _fixture_files()
    with get_session() as session:
        for path in files:
            raw = path.read_bytes()
            content_hash = hashlib.sha256(raw).hexdigest()
            item_id = f"{SOURCE_TYPE}:{path.name}"
            is_insert = _upsert_document_cache(
                session,
                project_id=project_id,
                sharepoint_item_id=item_id,
                item_path=f"/test_docs/{path.name}",
                content_hash=content_hash,
                raw_content=raw.decode("utf-8", errors="replace"),
            )
            action = "inserted" if is_insert else "updated"
            print(f"  {path.name}: {action} hash={content_hash[:12]}... item_id={item_id}")
            _check(f"{path.name} upserted ({action})", True)
            record_ingress_event(
                str(project_id),
                BlackboardEvent(
                    event_type=EventType.DOCUMENT_INGESTED,
                    publisher="sharepoint_delta_ingestion",
                    project_id=str(project_id),
                    correlation_id=item_id,
                    payload={
                        "item_id": item_id,
                        "content_hash": content_hash,
                        "sharepoint_drive_id": None,
                        "item_path": f"/test_docs/{path.name}",
                        "source_type": SOURCE_TYPE,
                        "is_insert": is_insert,
                    },
                ),
            )

    with get_session() as session:
        count = session.execute(
            select(DocumentCache.id).where(
                DocumentCache.project_id == project_id,
                DocumentCache.source_type == SOURCE_TYPE,
            )
        ).all()
        _check(
            f"document_cache holds {len(files)} test_docs row(s) for this project",
            len(count) == len(files),
            f"got {len(count)}, expected {len(files)}",
        )


def _cleanup(project_id: uuid.UUID) -> None:
    _section("Cleanup: delete source_type=test_docs rows for this project")
    with get_session() as session:
        result = session.execute(
            sa_delete(DocumentCache).where(
                DocumentCache.project_id == project_id,
                DocumentCache.source_type == SOURCE_TYPE,
            )
        )
        print(f"  deleted {result.rowcount} row(s)")
        remaining = session.execute(
            select(DocumentCache.id).where(
                DocumentCache.project_id == project_id,
                DocumentCache.source_type == SOURCE_TYPE,
            )
        ).all()
        _check("no leftover test_docs rows", len(remaining) == 0, f"still {len(remaining)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert test_docs/ into document_cache.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete only source_type=test_docs rows for the resolved project, then exit.",
    )
    args = parser.parse_args()

    project_id, project_name = _resolve_project()
    print(f"Target project: {project_name!r} ({project_id})")

    if args.cleanup:
        _cleanup(project_id)
    else:
        _ingest(project_id)

    _section("Result")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS: test_docs ingest complete.")


if __name__ == "__main__":
    main()
