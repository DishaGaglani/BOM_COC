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

from pydantic import ValidationError

from app.parameters.html_table import parse_html_table
from app.parameters.schema import CANONICAL_FIELDS, BOMItem, ExtractedField
from app.services.forjinn_client import AgentResponseError, call_agent

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


# A single table exceeding this many rows (header included) gets split
# across multiple agent calls instead of sent whole — observed live against
# a genuine 40+-row COC table (xh02020.pdf): asked to extract "every row"
# from a table that large in one call, the agent silently gave up rather
# than partially completing (0 rows extracted first attempt; only the
# first 2 of ~40 on a second attempt after strengthening the prompt
# further). Deliberately NOT set lower than this: a live experiment at 10
# turned MDP BOM.pdf's extraction (2 of its 6 tables have 11/13 rows) from
# 1 already-reliable call into 5, and the whole run took ~30 minutes before
# hitting a transient network failure — more, smaller calls multiplies
# exposure to exactly that kind of transient failure without addressing it
# (see forjinn_client.call_agent's retry handling for the actual fix).
# Tables within this limit are entirely unaffected — they still go out in
# the single shared call exactly as before, so already-verified
# small/medium documents (MDP BOM.pdf's 6 modest tables, every golden
# fixture) see no behavior change.
MAX_TABLE_ROWS_PER_CALL = 20


def _chunk_table_rows(rows: list[list[str]]) -> list[list[list[str]]]:
    """Splits one table's rows into pieces of at most MAX_TABLE_ROWS_PER_CALL,
    each piece re-including rows[0] so a later piece isn't sent to the agent
    as headerless data (rows[0] usually is the header; even when it isn't,
    repeating it is harmless — the agent decides what it means, same as any
    other row). A table within the limit returns unchanged as its only
    piece — this is the branch every already-tested document takes."""
    if len(rows) <= MAX_TABLE_ROWS_PER_CALL or len(rows) <= 1:
        return [rows]
    header, data = rows[0], rows[1:]
    chunk_size = MAX_TABLE_ROWS_PER_CALL - 1  # reserve one slot for the repeated header
    return [[header] + data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


def _table_call_groups(document: "ParsedDocument") -> list[list[dict]]:
    """Groups this document's tables into agent-call batches. Every table
    that fits within MAX_TABLE_ROWS_PER_CALL is bundled into one shared
    call — today's behavior, unchanged, since combining several small
    tables into one call has never shown this failure mode (MDP BOM.pdf's
    6 tables total ~21 line items and passes the golden suite reliably as a
    single call). Only a table that alone exceeds the limit — the one
    scenario actually observed to make the agent give up — is pulled out
    into its own additional call(s), one per chunk, each labeled with a
    suffixed table_id so overlapping bboxes from the same source table
    don't get confused for different tables downstream."""
    small_tables: list[dict] = []
    extra_groups: list[list[dict]] = []

    for table in _tables_as_rows(document):
        pieces = _chunk_table_rows(table["rows"])
        if len(pieces) == 1:
            small_tables.append(table)
            continue
        for i, piece in enumerate(pieces, start=1):
            extra_groups.append([{**table, "table_id": f"{table['table_id']}#chunk{i}", "rows": piece}])

    groups = ([small_tables] if small_tables else []) + extra_groups
    return groups or [[]]  # always at least one call, even for a prose-only document with no tables


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


def build_extraction_payload(document: "ParsedDocument", tables: list[dict]) -> dict:
    """The structured input handed to the extraction agent for one call:
    `tables` (one batch from _table_call_groups — usually every table on
    the document, but a lone oversized table's own chunk when one didn't
    fit) plus the document's text elements — each carrying its own
    id/page/bbox — plus the canonical field set values should be mapped
    onto. The agent should echo the source table's or element's bbox
    verbatim on any field it extracts from it, so highlighting downstream
    (see annotation/pdf_annotator.py) keeps working."""
    return {
        "filename": document.filename,
        "tables": tables,
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


def _summarize_validation_error(exc: ValidationError) -> str:
    """A one-line, non-leaky summary of a pydantic ValidationError, for
    AgentResponseError messages — the raw exception text is a multi-line
    dump with a docs URL that's not useful to an API caller, and
    _coerce_str already handles the one type mismatch that's actually
    common (bool/number where a string was expected), so anything that
    still lands here is a genuinely unexpected shape worth naming plainly."""
    return "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors())


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

    Raises ForjinnNotConfigured (via call_agent) if forjinn_api_url is unset,
    httpx.HTTPError on a transport/status failure, or AgentResponseError (via
    extract_bom/extract_coc below) if the response doesn't match the
    contract above — extraction has no rule-based fallback anymore, so all
    of these propagate up to the caller (see main.py's error handling)
    rather than being swallowed here.
    """
    return await call_agent({"task": "extract", **payload})


def _coerce_bom_item(item: dict) -> BOMItem:
    fields = {k: v for k, v in item.items() if k != "item_id"}
    # See _coerce_str — the agent's requirements values aren't reliably
    # strings even though BOMItem.requirements is dict[str, str].
    fields["requirements"] = {
        key: _coerce_str(value)
        for key, value in (fields.get("requirements") or {}).items()
        if value is not None
    }
    try:
        return BOMItem(item_id=item.get("item_id") or _new_item_id(), **fields)
    except ValidationError as exc:
        raise AgentResponseError(
            f"extraction agent returned a BOM line item (part_id={fields.get('part_id')!r}) "
            f"that doesn't match the expected shape: {_summarize_validation_error(exc)}"
        ) from exc


def _coerce_extracted_field(raw: dict) -> "ExtractedField | None":
    # field_value is required (not Optional) on ExtractedField — a field
    # with no usable value isn't evidence of anything, so it's dropped
    # rather than defaulting to "" (which would render as a false positive
    # presence checkmark downstream).
    field_value = _coerce_str(raw.get("field_value"))
    if not field_value:
        return None
    try:
        return ExtractedField(**{
            **raw,
            "field_value": field_value,
            "raw_label": _coerce_str(raw.get("raw_label")),
            # extraction_method is always "semantic" for everything this
            # pipeline produces (see ExtractionMethod in parameters/schema.py)
            # — set here rather than asking the agent to repeat a constant on
            # every field.
            "extraction_method": "semantic",
        })
    except ValidationError as exc:
        raise AgentResponseError(
            f"extraction agent returned a COC field (field_name={raw.get('field_name')!r}) "
            f"that doesn't match the expected shape: {_summarize_validation_error(exc)}"
        ) from exc


async def extract_bom(document: "ParsedDocument") -> tuple[list[BOMItem], str | None]:
    """Returns (line items, contract_date), both sourced from the agent's
    read of the document — see module docstring. A document whose tables
    don't all fit in one call (see _table_call_groups/MAX_TABLE_ROWS_PER_CALL)
    is sent across multiple sequential agent calls instead, one per group,
    with every call's bom_items concatenated into the final result — a
    document under the limit still makes exactly the one call it always
    did."""
    items: list[BOMItem] = []
    contract_date: str | None = None
    for tables_group in _table_call_groups(document):
        result = await _call_agent(build_extraction_payload(document, tables_group))
        items.extend(_coerce_bom_item(item) for item in result.get("bom_items", []))
        if contract_date is None:
            contract_date = result.get("contract_date")
    return items, contract_date


async def extract_coc(document: "ParsedDocument") -> list[ExtractedField]:
    """See extract_bom — same multi-call-and-merge behavior for a document
    whose tables exceed one call's row budget."""
    fields: list[ExtractedField] = []
    for tables_group in _table_call_groups(document):
        result = await _call_agent(build_extraction_payload(document, tables_group))
        fields.extend(f for raw in result.get("coc_fields", []) if (f := _coerce_extracted_field(raw)) is not None)
    return fields


def _new_item_id() -> str:
    import uuid

    return str(uuid.uuid4())
