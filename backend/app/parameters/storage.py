import sqlite3
from typing import Callable

from app.db import connect
from app.parameters.schema import BOM, COC


def save_bom(bom: BOM) -> None:
    with connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO boms (bom_id, project_id, version, status, uploaded_at, data)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(bom_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    version = excluded.version,
                    status = excluded.status,
                    uploaded_at = excluded.uploaded_at,
                    data = excluded.data
                """,
                (
                    bom.bom_id,
                    bom.project_id,
                    bom.version,
                    bom.status,
                    bom.uploaded_at.isoformat(),
                    bom.model_dump_json(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            # The (project_id, version) UNIQUE constraint (app/db.py) is a
            # safety net for any caller that assigns a version outside of
            # create_bom_version's atomic transaction (below) and ends up
            # colliding with another one — a clear, retryable failure
            # instead of silently overwriting the winner's BOM. The actual
            # write path (bom_service.ingest_bom) goes through
            # create_bom_version, which prevents the collision from
            # happening at all rather than just catching it here.
            raise ValueError(
                f"BOM version conflict for project '{bom.project_id}' (version {bom.version}) — "
                "another BOM upload for this project completed at the same moment. Please retry."
            ) from exc


def load_bom(bom_id: str) -> BOM | None:
    with connect() as conn:
        row = conn.execute("SELECT data FROM boms WHERE bom_id = ?", (bom_id,)).fetchone()
    return BOM.model_validate_json(row["data"]) if row else None


def list_boms() -> list[BOM]:
    with connect() as conn:
        rows = conn.execute("SELECT data FROM boms ORDER BY uploaded_at DESC").fetchall()
    return [BOM.model_validate_json(row["data"]) for row in rows]


def get_active_bom(project_id: str) -> BOM | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT data FROM boms WHERE project_id = ? AND status = 'active' ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    return BOM.model_validate_json(row["data"]) if row else None


def get_next_bom_version(project_id: str) -> tuple[int, BOM | None]:
    """Read-only preview of (next_version, prior_active_bom_or_None) — NOT
    used for the actual write path any more (see create_bom_version below),
    since this read alone can race with another caller's read of the same
    project. Kept for read-only introspection / tests."""
    prior = get_active_bom(project_id)
    return ((prior.version + 1) if prior else 1), prior


def create_bom_version(project_id: str, build_bom: "Callable[[int], BOM]") -> BOM:
    """Atomically assigns the next version for `project_id`, marks any
    prior active BOM as superseded, and inserts the new BOM built by
    `build_bom(next_version)` — all inside one `BEGIN IMMEDIATE` transaction.
    That's what actually closes the version-assignment race:
    get_next_bom_version() + save_bom() as two separate calls (the old
    bom_service.ingest_bom shape) could still have two concurrent uploads
    for the same project both read the same "next version" before either
    wrote — save_bom's UNIQUE(project_id, version) constraint turned that
    into a safe, retryable failure but didn't prevent it. BEGIN IMMEDIATE
    acquires the write lock up front, so a second concurrent call for the
    same project blocks until this transaction commits, then correctly
    computes the version after it — both calls succeed, with sequential
    versions, instead of one failing."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT data FROM boms WHERE project_id = ? AND status = 'active' ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        prior = BOM.model_validate_json(row["data"]) if row else None
        next_version = (prior.version + 1) if prior else 1

        if prior is not None:
            prior.status = "superseded"
            conn.execute(
                "UPDATE boms SET status = ?, data = ? WHERE bom_id = ?",
                (prior.status, prior.model_dump_json(), prior.bom_id),
            )

        new_bom = build_bom(next_version)
        conn.execute(
            "INSERT INTO boms (bom_id, project_id, version, status, uploaded_at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                new_bom.bom_id,
                new_bom.project_id,
                new_bom.version,
                new_bom.status,
                new_bom.uploaded_at.isoformat(),
                new_bom.model_dump_json(),
            ),
        )
        return new_bom


def save_coc(coc: COC) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO cocs (coc_id, bom_id, matched_item_id, uploaded_at, data)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(coc_id) DO UPDATE SET
                bom_id = excluded.bom_id,
                matched_item_id = excluded.matched_item_id,
                uploaded_at = excluded.uploaded_at,
                data = excluded.data
            """,
            (coc.coc_id, coc.bom_id, coc.matched_item_id, coc.uploaded_at.isoformat(), coc.model_dump_json()),
        )


def load_coc(coc_id: str) -> COC | None:
    with connect() as conn:
        row = conn.execute("SELECT data FROM cocs WHERE coc_id = ?", (coc_id,)).fetchone()
    return COC.model_validate_json(row["data"]) if row else None


def list_cocs_for_bom(bom_id: str) -> list[COC]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT data FROM cocs WHERE bom_id = ? ORDER BY uploaded_at DESC", (bom_id,)
        ).fetchall()
    return [COC.model_validate_json(row["data"]) for row in rows]
