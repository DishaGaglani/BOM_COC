from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import BOM
from app.schemas.api import BOMOut
from app.services.bom_service import ingest_bom

router = APIRouter(prefix="/api/boms", tags=["bom"])


@router.get("", response_model=list[BOMOut])
def list_boms(db: Session = Depends(get_db)):
    return db.query(BOM).order_by(BOM.uploaded_at.desc()).all()


@router.post("", response_model=BOMOut)
def upload_bom(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        bom = ingest_bom(db, project_id, file.filename, file.file)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return bom


@router.get("/{bom_id}", response_model=BOMOut)
def get_bom(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(BOM).filter(BOM.bom_id == bom_id).first()
    if not bom:
        raise HTTPException(status_code=404, detail="BOM not found")
    return bom


@router.get("/by-project/{project_id}/active", response_model=BOMOut)
def get_active_bom(project_id: str, db: Session = Depends(get_db)):
    bom = (
        db.query(BOM)
        .filter(BOM.project_id == project_id, BOM.status == "active")
        .order_by(BOM.version.desc())
        .first()
    )
    if not bom:
        raise HTTPException(status_code=404, detail="No active BOM for this project")
    return bom
