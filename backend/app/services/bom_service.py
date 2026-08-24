import uuid

from app.parameters.extractor import extract_bom
from app.parameters.schema import BOM
from app.parameters.storage import get_next_bom_version, save_bom
from app.parsing.schema import ParsedDocument


def ingest_bom(project_id: str, document: ParsedDocument) -> BOM:
    """Supersedes any prior active BOM for the same project so the newest
    BOM becomes the reference, per the requirement that the BOM stays in
    scope 'until the next BOM'. Raises ValueError (via extract_bom) if the
    document has no BOM-shaped table — nothing is superseded in that case."""
    items = extract_bom(document)
    version, prior_active = get_next_bom_version(project_id)

    if prior_active is not None:
        prior_active.status = "superseded"
        save_bom(prior_active)

    bom = BOM(
        bom_id=str(uuid.uuid4()),
        project_id=project_id,
        parsed_document_id=document.document_id,
        filename=document.filename,
        version=version,
        status="active",
        items=items,
    )
    save_bom(bom)
    return bom
