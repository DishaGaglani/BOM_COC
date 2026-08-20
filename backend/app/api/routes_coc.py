from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import COC, BOM
from app.schemas.api import COCOut, ReportOut
from app.services.coc_service import ingest_and_validate_coc
from app.services.report_service import build_validation_report
from app.services.storage import path_for
import os

router = APIRouter(prefix="/api", tags=["coc"])


@router.get("/boms/{bom_id}/cocs", response_model=list[COCOut])
def list_cocs(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(BOM).filter(BOM.bom_id == bom_id).first()
    if not bom:
        raise HTTPException(status_code=404, detail="BOM not found")
    return db.query(COC).filter(COC.bom_id == bom_id).order_by(COC.uploaded_at.desc()).all()


@router.post("/boms/{bom_id}/cocs", response_model=list[COCOut])
def upload_cocs(
    bom_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Accepts one or more COC files (batch) per the requirement that COCs
    can be uploaded one-by-one or in batches."""
    bom = db.query(BOM).filter(BOM.bom_id == bom_id).first()
    if not bom:
        raise HTTPException(status_code=404, detail="BOM not found")

    results = []
    for file in files:
        coc = ingest_and_validate_coc(db, bom_id, file.filename, file.file)
        results.append(coc)
    return results


@router.get("/cocs/{coc_id}", response_model=COCOut)
def get_coc(coc_id: str, db: Session = Depends(get_db)):
    coc = db.query(COC).filter(COC.coc_id == coc_id).first()
    if not coc:
        raise HTTPException(status_code=404, detail="COC not found")
    return coc


@router.get("/cocs/{coc_id}/report", response_model=ReportOut)
def get_report(coc_id: str, db: Session = Depends(get_db)):
    coc = db.query(COC).filter(COC.coc_id == coc_id).first()
    if not coc:
        raise HTTPException(status_code=404, detail="COC not found")
    return build_validation_report(db, coc_id)


@router.get("/cocs/{coc_id}/highlighted-pdf")
def get_highlighted_pdf(coc_id: str, db: Session = Depends(get_db)):
    coc = db.query(COC).filter(COC.coc_id == coc_id).first()
    if not coc:
        raise HTTPException(status_code=404, detail="COC not found")

    path = path_for("highlighted", f"{coc_id}.pdf")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Highlighted PDF not yet generated")

    return FileResponse(path, media_type="application/pdf", filename=f"{coc.filename}_highlighted.pdf")
