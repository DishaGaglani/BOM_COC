from sqlalchemy.orm import Session

from app.db.models import COC


def build_validation_report(db: Session, coc_id: str) -> dict:
    """Builds the validation-report-style table from architecture doc
    section 14: parameter, BOM/expected, COC/actual, status, reason."""
    coc = db.query(COC).filter(COC.coc_id == coc_id).one()

    rows = [
        {
            "parameter": v.parameter,
            "expected": v.expected_value,
            "actual": v.actual_value,
            "status": v.status.value,
            "reason": v.reason,
        }
        for v in coc.validations
    ]

    statuses = [r["status"] for r in rows]
    overall = "FAIL" if "FAIL" in statuses else ("WARNING" if "WARNING" in statuses else "PASS")

    return {
        "coc_id": coc.coc_id,
        "filename": coc.filename,
        "overall_status": overall,
        "rows": rows,
    }
