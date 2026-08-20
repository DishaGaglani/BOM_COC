from sqlalchemy.orm import Session

from app.db.models import BOM, BOMItem, BOMStatus
from app.services.bom_parser import parse_bom_tables
from app.services.storage import save_upload
from app.validation.normalize import parse_quantity


def ingest_bom(db: Session, project_id: str, filename: str, file_obj) -> BOM:
    """Uploads and parses a BOM/Traceability Matrix (architecture doc
    section 6: persistent BOM repository). Supersedes any prior active BOM
    for the same project so the newest BOM becomes the reference, per the
    requirement that the BOM stays in scope 'until the next BOM'."""
    path = save_upload("bom", filename, file_obj)

    prior_active = (
        db.query(BOM)
        .filter(BOM.project_id == project_id, BOM.status == BOMStatus.ACTIVE)
        .order_by(BOM.version.desc())
        .first()
    )
    next_version = (prior_active.version + 1) if prior_active else 1
    if prior_active:
        prior_active.status = BOMStatus.SUPERSEDED

    bom = BOM(project_id=project_id, filename=filename, version=next_version, status=BOMStatus.ACTIVE)
    db.add(bom)
    db.flush()  # assigns bom.bom_id

    rows = parse_bom_tables(path)
    for row in rows:
        db.add(
            BOMItem(
                bom_id=bom.bom_id,
                part_id=row.get("part_id"),
                description=row.get("description"),
                manufacturer=row.get("manufacturer"),
                model=row.get("model"),
                quantity=parse_quantity(row.get("quantity")) if row.get("quantity") else None,
                po_number=row.get("po_numbers"),
                requirements={k: v for k, v in row.items() if k not in {"part_id", "description", "manufacturer", "model", "quantity", "po_numbers"}},
            )
        )

    db.commit()
    db.refresh(bom)
    return bom
