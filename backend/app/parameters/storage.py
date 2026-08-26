import sqlite3

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
            # The (project_id, version) UNIQUE constraint (app/db.py) is
            # what actually closes the version-assignment race: two
            # concurrent uploads for the same project can still both read
            # the same "next version" via get_next_bom_version below, but
            # only one of their save_bom() calls can win — the loser gets
            # this, a clear signal to retry (which will then correctly see
            # the winner's version and move past it), instead of silently
            # overwriting the winner's BOM.
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
    """Returns (next_version, prior_active_bom_or_None). This read can
    still race with another caller's read of the same project (two
    concurrent uploads both computing the same next version) — closing that
    fully would mean collapsing the read-then-save_bom two-call pattern in
    bom_service.ingest_bom into one storage-layer transaction. What's
    guaranteed here is that the race can no longer end in silent data loss:
    see save_bom's UNIQUE(project_id, version) handling."""
    prior = get_active_bom(project_id)
    return ((prior.version + 1) if prior else 1), prior


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
