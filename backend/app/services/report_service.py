from app.parameters.schema import COC, Report, ReportRow
from app.validation.matching import overall_status


def build_validation_report(coc: COC) -> Report:
    rows = [
        ReportRow(parameter=v.parameter, expected=v.expected_value, actual=v.actual_value, status=v.status, reason=v.reason)
        for v in coc.validations
    ]
    return Report(
        coc_id=coc.coc_id,
        filename=coc.filename,
        overall_status=overall_status([r.status for r in rows]),
        rows=rows,
    )
