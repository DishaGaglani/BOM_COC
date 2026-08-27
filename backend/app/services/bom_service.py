import uuid

from app.parameters.extractor import extract_bom
from app.parameters.field_mapper import extract_inline_fields
from app.parameters.schema import BOM
from app.parameters.storage import create_bom_version
from app.parsing.schema import ParsedDocument


def _resolve_contract_date(document: ParsedDocument, items: list, explicit: str | None) -> str | None:
    if explicit:
        return explicit

    # Most commonly appears as inline letterhead/header text (e.g. "SO.No:
    # ..." style blocks), not as an item-table column.
    inline_fields = extract_inline_fields(document.elements)
    contract_date_field = next((f for f in inline_fields if f.field_name == "contract_date"), None)
    if contract_date_field:
        return contract_date_field.field_value

    # Fallback: some BOMs carry a "PO Date" column on the item table itself
    # instead. A BOM has one contract, so the first row's value stands in
    # for the whole document.
    for item in items:
        if "contract_date" in item.requirements:
            return item.requirements["contract_date"]

    return None


def ingest_bom(project_id: str, document: ParsedDocument, contract_date: str | None = None) -> BOM:
    """Supersedes any prior active BOM for the same project so the newest
    BOM becomes the reference, per the requirement that the BOM stays in
    scope 'until the next BOM'. Raises ValueError (via extract_bom) if the
    document has no BOM-shaped table — nothing is superseded in that case.
    Version assignment, superseding the prior active BOM, and inserting the
    new one all happen atomically in create_bom_version, so two concurrent
    uploads for the same project can't both land on the same version."""
    items = extract_bom(document)
    resolved_contract_date = _resolve_contract_date(document, items, contract_date)

    def build(version: int) -> BOM:
        return BOM(
            bom_id=str(uuid.uuid4()),
            project_id=project_id,
            parsed_document_id=document.document_id,
            filename=document.filename,
            version=version,
            status="active",
            items=items,
            contract_date=resolved_contract_date,
        )

    return create_bom_version(project_id, build)
