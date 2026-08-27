import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.auth import require_api_key
from app.config import settings
from app.parameters.file_signatures import matches_signature
from app.parameters.schema import BOM, COC, Report
from app.parameters.storage import (
    get_active_bom,
    list_boms,
    list_cocs_for_bom,
    load_bom,
    load_coc,
)
from app.parsing.schema import ParsedDocument, ParsedDocumentSummary
from app.parsing.unstructured_parser import SUPPORTED_EXTENSIONS, parse_document
from app.services.bom_service import ingest_bom
from app.services.coc_service import ingest_and_validate_coc
from app.services.report_service import build_validation_report
from app.storage import list_parsed, load_parsed, save_parsed, save_upload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BOM/COC Semantic Validation Service", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Every /documents/* and /api/* route requires X-API-Key when settings.api_key
# is set (no-op otherwise) — see app/auth.py. /health stays open for
# container/LB health checks regardless of auth config.
router = APIRouter(dependencies=[Depends(require_api_key)])


async def _receive_and_parse(file: UploadFile, strategy: str | None) -> tuple[ParsedDocument, Path]:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB > {settings.max_upload_mb} MB limit).",
        )

    if not matches_signature(ext, content):
        raise HTTPException(
            status_code=400,
            detail=f"File content doesn't match its extension ('{ext}') — refusing to parse.",
        )

    stored_path = save_upload(file.filename or "upload", content)

    try:
        document = await asyncio.wait_for(
            asyncio.to_thread(parse_document, stored_path, file.filename or stored_path.name, strategy=strategy),
            timeout=settings.parse_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        logger.exception("Timed out parsing %s", file.filename)
        raise HTTPException(
            status_code=504,
            detail=f"Parsing timed out after {settings.parse_timeout_seconds}s",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to parse %s", file.filename)
        raise HTTPException(status_code=422, detail=f"Failed to parse document: {exc}") from exc

    save_parsed(document)
    logger.info(
        "Parsed %s -> %d elements (%d tables) via strategy=%s",
        file.filename,
        document.element_count,
        document.table_count,
        document.strategy_used,
    )
    return document, stored_path


# --- Generic parsing (debugging/low-level access to the unstructured.io stage) ---


@router.post("/documents/parse", response_model=ParsedDocument)
async def parse_uploaded_document(file: UploadFile, strategy: str | None = None) -> ParsedDocument:
    document, _ = await _receive_and_parse(file, strategy)
    return document


@router.get("/documents", response_model=list[ParsedDocumentSummary])
def list_documents() -> list[ParsedDocumentSummary]:
    return list_parsed()


@router.get("/documents/{document_id}", response_model=ParsedDocument)
def get_document(document_id: str) -> ParsedDocument:
    document = load_parsed(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


# --- BOM: parsed, extracted, and stored as the per-project ground truth ---


@router.get("/api/boms", response_model=list[BOM])
def api_list_boms() -> list[BOM]:
    return list_boms()


@router.post("/api/boms", response_model=BOM)
async def api_upload_bom(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    contract_date: str | None = Form(None),
    strategy: str | None = None,
) -> BOM:
    document, _ = await _receive_and_parse(file, strategy)
    try:
        bom = ingest_bom(project_id, document, contract_date=contract_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info(
        "Ingested BOM %s (project=%s, version=%d, contract_date=%s) -> %d items",
        bom.filename, project_id, bom.version, bom.contract_date, len(bom.items),
    )
    return bom


@router.get("/api/boms/by-project/{project_id}/active", response_model=BOM)
def api_get_active_bom(project_id: str) -> BOM:
    bom = get_active_bom(project_id)
    if bom is None:
        raise HTTPException(status_code=404, detail="No active BOM for this project")
    return bom


@router.get("/api/boms/{bom_id}", response_model=BOM)
def api_get_bom(bom_id: str) -> BOM:
    bom = load_bom(bom_id)
    if bom is None:
        raise HTTPException(status_code=404, detail="BOM not found")
    return bom


# --- COC: parsed, extracted, matched against the BOM, and validated ---


@router.get("/api/boms/{bom_id}/cocs", response_model=list[COC])
def api_list_cocs(bom_id: str) -> list[COC]:
    if load_bom(bom_id) is None:
        raise HTTPException(status_code=404, detail="BOM not found")
    return list_cocs_for_bom(bom_id)


@router.post("/api/boms/{bom_id}/cocs", response_model=list[COC])
async def api_upload_cocs(
    bom_id: str, files: list[UploadFile] = File(...), strategy: str | None = None
) -> list[COC]:
    """Accepts one or more COC files (batch), per the requirement that COCs
    can be uploaded one-by-one or in batches."""
    bom = load_bom(bom_id)
    if bom is None:
        raise HTTPException(status_code=404, detail="BOM not found")

    records: list[COC] = []
    for file in files:
        document, stored_path = await _receive_and_parse(file, strategy)
        coc = await ingest_and_validate_coc(bom, document, stored_path)
        logger.info("Validated COC %s -> %d fields, %d validations", coc.filename, len(coc.fields), len(coc.validations))
        records.append(coc)

    return records


@router.get("/api/cocs/{coc_id}", response_model=COC)
def api_get_coc(coc_id: str) -> COC:
    coc = load_coc(coc_id)
    if coc is None:
        raise HTTPException(status_code=404, detail="COC not found")
    return coc


@router.get("/api/cocs/{coc_id}/report", response_model=Report)
def api_get_report(coc_id: str) -> Report:
    coc = load_coc(coc_id)
    if coc is None:
        raise HTTPException(status_code=404, detail="COC not found")
    return build_validation_report(coc)


@router.get("/api/cocs/{coc_id}/highlighted-pdf")
def api_get_highlighted_pdf(coc_id: str) -> FileResponse:
    coc = load_coc(coc_id)
    if coc is None:
        raise HTTPException(status_code=404, detail="COC not found")

    path = settings.highlighted_dir / f"{coc_id}.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Highlighted PDF not found")

    return FileResponse(path, media_type="application/pdf", filename=f"{coc.filename}_highlighted.pdf")


app.include_router(router)
