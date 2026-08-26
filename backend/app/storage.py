import uuid
from pathlib import Path

from app.config import settings
from app.db import connect
from app.parsing.schema import ParsedDocument, ParsedDocumentSummary


def save_upload(filename: str, content: bytes) -> Path:
    ext = Path(filename).suffix
    dest = settings.upload_dir / f"{uuid.uuid4()}{ext}"
    dest.write_bytes(content)
    return dest


def save_parsed(document: ParsedDocument) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO parsed_documents
                (document_id, filename, element_count, table_count, strategy_used, parsed_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                filename = excluded.filename,
                element_count = excluded.element_count,
                table_count = excluded.table_count,
                strategy_used = excluded.strategy_used,
                parsed_at = excluded.parsed_at,
                data = excluded.data
            """,
            (
                document.document_id,
                document.filename,
                document.element_count,
                document.table_count,
                document.strategy_used,
                document.parsed_at.isoformat(),
                document.model_dump_json(),
            ),
        )


def load_parsed(document_id: str) -> ParsedDocument | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT data FROM parsed_documents WHERE document_id = ?", (document_id,)
        ).fetchone()
    return ParsedDocument.model_validate_json(row["data"]) if row else None


def list_parsed() -> list[ParsedDocumentSummary]:
    # Selects only the summary columns rather than every row's full `data`
    # blob — the old glob-and-parse-every-file version had to deserialize
    # each document in full just to list them.
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT document_id, filename, element_count, table_count, strategy_used, parsed_at
            FROM parsed_documents
            ORDER BY parsed_at DESC
            """
        ).fetchall()
    return [
        ParsedDocumentSummary(
            document_id=row["document_id"],
            filename=row["filename"],
            element_count=row["element_count"],
            table_count=row["table_count"],
            strategy_used=row["strategy_used"],
            parsed_at=row["parsed_at"],
        )
        for row in rows
    ]
