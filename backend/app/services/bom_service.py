import uuid

from app.parameters.extractor import extract_bom
from app.parameters.schema import BOM
from app.parameters.storage import create_bom_version
from app.parsing.schema import ParsedDocument


async def ingest_bom(project_id: str, document: ParsedDocument, contract_date: str | None = None) -> BOM:
    """Supersedes any prior active BOM for the same project so the newest
    BOM becomes the reference, per the requirement that the BOM stays in
    scope 'until the next BOM'. Raises ValueError (via extract_bom) if the
    document has no BOM-shaped table — nothing is superseded in that case.
    Version assignment, superseding the prior active BOM, and inserting the
    new one all happen atomically in create_bom_version, so two concurrent
    uploads for the same project can't both land on the same version."""
    items, extracted_contract_date = await extract_bom(document)
    resolved_contract_date = contract_date or extracted_contract_date

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
