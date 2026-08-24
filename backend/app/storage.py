import json
import uuid
from pathlib import Path

from app.config import settings
from app.parsing.schema import ParsedDocument, ParsedDocumentSummary


def save_upload(filename: str, content: bytes) -> Path:
    ext = Path(filename).suffix
    dest = settings.upload_dir / f"{uuid.uuid4()}{ext}"
    dest.write_bytes(content)
    return dest


def save_parsed(document: ParsedDocument) -> Path:
    dest = settings.parsed_dir / f"{document.document_id}.json"
    dest.write_text(document.model_dump_json(indent=2))
    return dest


def load_parsed(document_id: str) -> ParsedDocument | None:
    path = settings.parsed_dir / f"{document_id}.json"
    if not path.exists():
        return None
    return ParsedDocument.model_validate_json(path.read_text())


def list_parsed() -> list[ParsedDocumentSummary]:
    summaries = []
    for path in sorted(settings.parsed_dir.glob("*.json")):
        data = json.loads(path.read_text())
        summaries.append(
            ParsedDocumentSummary(
                document_id=data["document_id"],
                filename=data["filename"],
                element_count=data["element_count"],
                table_count=data["table_count"],
                strategy_used=data["strategy_used"],
                parsed_at=data["parsed_at"],
            )
        )
    return sorted(summaries, key=lambda s: s.parsed_at, reverse=True)
