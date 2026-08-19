"""Database connection & session management (Phase 7: Real Database Integration).

Synchronous SQLAlchemy `Session`, mirroring the style `core/billing.py` already
uses (functions take a `session: Session` parameter) rather than an async
driver -- this keeps every MAF executor's blocking DB call consistent with
`chasing_engine.py`'s existing sync-call-inside-`async def` pattern, and avoids
adding `asyncpg` alongside the `psycopg[binary]` driver already pinned in
`requirements.txt`.

Usage:
    from db.session import get_session

    with get_session() as session:
        ...
    # commits on clean exit, rolls back and re-raises on exception, always closes.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# `pool_pre_ping` guards against Azure Postgres silently dropping idle
# connections (common on flexible-server SKUs) -- a stale connection is
# detected and transparently replaced before it's handed to a caller, instead
# of surfacing as a confusing mid-transaction `OperationalError`.
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

# `expire_on_commit=False` so ORM objects returned from a `with get_session()`
# block stay readable after the block exits (and thus after `commit()` has
# already run) -- callers frequently build a plain dict/return value from an
# object right at the end of the block.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    """The one place a `db_middleware.py` function acquires a `Session`.

    Commits on a clean exit (releasing any row locks -- see
    `core.billing.check_pilot_compute_cap`'s `SELECT ... FOR UPDATE` note),
    rolls back and re-raises on any exception, and always closes -- so no
    caller can leak a connection back to the pool.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
