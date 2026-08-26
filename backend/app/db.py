"""SQLite-backed storage for structured records (parsed-document metadata,
BOMs, COCs) — replaces the earlier one-JSON-file-per-record layout under
storage/{parsed,bom,coc}/. That scheme had two real problems: writes
weren't atomic (path.write_text can leave a corrupt file on a crash
mid-write), and BOM version assignment (get_next_bom_version, in
app/parameters/storage.py) was read-then-write with no locking — two
concurrent uploads for the same project could both compute "next version =
3" and one would silently clobber the other's supersede.

Records are still stored as a single JSON blob per row (the `data` column)
rather than a normalized relational schema — this moves the same JSON
documents behind SQLite instead of the filesystem so writes are atomic and
version assignment can be constrained by the database, not just trusted to
the caller. A handful of columns sit alongside `data` purely to make the
query patterns storage.py already had (list by project, filter by bom_id,
order by upload time) indexed instead of a full directory scan +
parse-every-file.

Raw binary files (the original upload, the highlighted PDF output) stay on
disk — see app/storage.py — since unstructured and PyMuPDF need a real file
path to work with, not a blob.
"""

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS parsed_documents (
    document_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    element_count INTEGER NOT NULL,
    table_count INTEGER NOT NULL,
    strategy_used TEXT NOT NULL,
    parsed_at TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS boms (
    bom_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    data TEXT NOT NULL,
    -- Turns a version collision from two concurrent uploads for the same
    -- project into a loud, retryable IntegrityError instead of one
    -- silently overwriting the other — see parameters/storage.py:save_bom.
    UNIQUE (project_id, version)
);
CREATE INDEX IF NOT EXISTS idx_boms_project_status ON boms (project_id, status);

CREATE TABLE IF NOT EXISTS cocs (
    coc_id TEXT PRIMARY KEY,
    bom_id TEXT NOT NULL,
    matched_item_id TEXT,
    uploaded_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cocs_bom ON cocs (bom_id);
CREATE INDEX IF NOT EXISTS idx_cocs_bom_item ON cocs (bom_id, matched_item_id);
"""


@contextmanager
def connect() -> "Iterator[sqlite3.Connection]":
    """One short-lived connection per call — mirrors the previous
    one-file-per-operation pattern rather than holding a connection open
    across requests. Commits on clean exit, rolls back on any exception, so
    every caller gets an all-or-nothing write without having to manage a
    transaction itself. WAL mode lets reads proceed without blocking behind
    a concurrent writer."""
    conn = sqlite3.connect(str(settings.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)


init_db()
