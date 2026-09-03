"""Field extraction from parsed documents via the semantic extraction agent.

The old rule-based extraction layer (formerly app/parameters/field_mapper.py,
presence_fields.py, table_extractor.py's header-guessing, table_headers.py,
synonyms.py) tried to approximate "does this column/label mean part_id" with
a hand-maintained synonym dict, a priority list for conflicting headers, and
several regexes for prose fallbacks — a pile of special cases that grew one
if/elif at a time for every new vendor phrasing and still couldn't actually
reason about meaning.

`unstructured` (see app/parsing/unstructured_parser.py) already turns a raw
document into structured elements and tables — that part was never the
problem. What those rules were really standing in for is a semantic judgment
call: given this table's columns/labels, and this document's text, which
canonical field is each one, and what's its value? That's exactly what the
extraction agent is for. This module builds the clean structured payload
from unstructured's output and hands it to the agent — no column-role
guessing or label synonym matching happens here anymore.

The agent is forjinn.com-hosted (Qwen-based) and also does semantic COC-vs-BOM
comparison — see services/semantic_validator.py — via the same
forjinn_client.call_agent transport, distinguished by the "task" field below.
"""

from typing import TYPE_CHECKING

from app.parameters.html_table import parse_html_table
from app.parameters.schema import CANONICAL_FIELDS, BOMItem, ExtractedField
from app.services.forjinn_client import call_agent

if TYPE_CHECKING:
    from app.parsing.schema import ParsedDocument


def _tables_as_rows(document: "ParsedDocument") -> list[dict]:
    """Every table on the document as id/page/bbox + raw rows-of-cells. No
    header-matching or column-role guessing — that judgment belongs to the
    agent, not to this module. `bbox` is carried through so a field the
    agent extracts from this table can echo it back (see module docstring
    on _call_agent) — unstructured doesn't give per-cell coordinates, so the
    whole table's box is the best available highlight region."""
    tables = []
    for table in document.tables:
        if not table.html:
            continue
        rows = parse_html_table(table.html)
        if not rows:
            continue
        tables.append({
            "table_id": table.element_id,
            "page_number": table.page_number,
            "bbox": table.bbox.model_dump() if table.bbox else None,
            "rows": rows,
        })
    return tables


def _elements_as_text(document: "ParsedDocument") -> list[dict]:
    """Every non-table text element as id/page/bbox + text, instead of one
    flattened full_text blob — so a field the agent pulls from prose (e.g.
    an inline "PO Number: ..." line or a signature/seal mention) can echo
    that element's bbox back, the same way table-sourced fields do."""
    return [
        {
            "element_id": el.element_id,
            "page_number": el.page_number,
            "bbox": el.bbox.model_dump() if el.bbox else None,
            "text": el.text,
        }
        for el in document.elements
        if el.type != "Table" and el.text
    ]


def build_extraction_payload(document: "ParsedDocument") -> dict:
    """The structured input handed to the extraction agent: unstructured's
    tables (as plain rows-of-cells, header row included) and text elements —
    each carrying its own id/page/bbox — plus the canonical field set values
    should be mapped onto. The agent should echo the source table's or
    element's bbox verbatim on any field it extracts from it, so highlighting
    downstream (see annotation/pdf_annotator.py) keeps working."""
    return {
        "filename": document.filename,
        "tables": _tables_as_rows(document),
        "elements": _elements_as_text(document),
        "canonical_fields": CANONICAL_FIELDS,
    }


def _coerce_str(value: object) -> str | None:
    """The extraction agent represents some canonical fields as native JSON
    types even though schema.BOMItem.requirements is dict[str, str] and
    ExtractedField.field_value/raw_label are str — e.g. it emits a real JSON
    boolean for `is_imported` (`false`, not `"false"`) since that's the
    field's natural shape, despite the prompt's example showing it quoted.
    pydantic doesn't coerce bool/int/float into str, so constructing the
    model directly from the agent's raw dict crashes intermittently,
    depending on whether a given response happens to include one of these.
    Booleans map to lowercase "true"/"false" (not Python's "True"/"False")
    since that's what a human reviewer expects to read."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


async def _call_agent(payload: dict) -> dict:
    """Sends payload to the forjinn agent with task="extract" and returns its
    structured response, expected to have the shape:
    {
      "bom_items": [
        {"part_id": ..., "description": ..., "manufacturer": ..., "model": ...,
         "quantity": ..., "po_number": ..., "requirements": {...}, "page_number": ...},
        ...
      ],
      "coc_fields": [
        {"field_name": ..., "field_value": ..., "page_number": ..., "bbox": ...,
         "raw_label": ..., "confidence": ...},
        ...
      ],
      "contract_date": str | None,  # BOM/project-level, see parameters.schema.BOM
    }

    `field_name` values must be members of app.parameters.schema.CANONICAL_FIELDS;
    `bom_items` become BOMItem instances and `coc_fields` become ExtractedField
    instances directly (see extract_bom/extract_coc below), so the response
    shape has to satisfy those pydantic models — this is the contract the
    forjinn agent needs to be built/prompted against.

    Raises ForjinnNotConfigured (via call_agent) if forjinn_api_url is unset —
    extraction has no rule-based fallback anymore, so that propagates up to
    the caller rather than being swallowed here.
    """
    return await call_agent({"task": "extract", **payload})


async def extract_bom(document: "ParsedDocument") -> tuple[list[BOMItem], str | None]:
    """Returns (line items, contract_date), both sourced from the agent's
    read of the document — see module docstring."""
    result = await _call_agent(build_extraction_payload(document))
    items = []
    for item in result.get("bom_items", []):
        fields = {k: v for k, v in item.items() if k != "item_id"}
        # See _coerce_str — the agent's requirements values aren't reliably
        # strings even though BOMItem.requirements is dict[str, str].
        fields["requirements"] = {
            key: _coerce_str(value)
            for key, value in (fields.get("requirements") or {}).items()
            if value is not None
        }
        items.append(BOMItem(item_id=item.get("item_id") or _new_item_id(), **fields))
    return items, result.get("contract_date")


async def extract_coc(document: "ParsedDocument") -> list[ExtractedField]:
    result = await _call_agent(build_extraction_payload(document))
    fields = []
    for raw in result.get("coc_fields", []):
        # field_value is required (not Optional) on ExtractedField — a field
        # with no usable value isn't evidence of anything, so it's dropped
        # rather than defaulting to "" (which would render as a false
        # positive presence checkmark downstream).
        field_value = _coerce_str(raw.get("field_value"))
        if not field_value:
            continue
        fields.append(ExtractedField(**{
            **raw,
            "field_value": field_value,
            "raw_label": _coerce_str(raw.get("raw_label")),
            # extraction_method is always "semantic" for everything this
            # pipeline produces (see ExtractionMethod in parameters/schema.py)
            # — set here rather than asking the agent to repeat a constant on
            # every field.
            "extraction_method": "semantic",
        }))
    return fields


def _new_item_id() -> str:
    import uuid

    return str(uuid.uuid4())
