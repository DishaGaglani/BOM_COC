"""Fixture builders shared across the test suite. Kept deliberately simple —
these construct the schema objects directly (an ExtractedField, a BOMItem, a
synthetic ParsedDocument built from a raw HTML table string) rather than
running real files through `unstructured`, so the whole suite runs in
milliseconds with no torch/OCR dependency. See tests/golden/README.md for
the complementary real-document suite this doesn't replace.
"""

import uuid

from app.parameters.schema import BOMItem, ExtractedField
from app.parsing.schema import ParsedDocument, ParsedElement, ParsedTable


def make_field(field_name: str, field_value: str, confidence: float = 1.0, **kwargs) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        field_value=field_value,
        extraction_method=kwargs.pop("extraction_method", "semantic"),
        confidence=confidence,
        **kwargs,
    )


def make_bom_item(
    part_id: str | None = None,
    po_number: str | None = None,
    quantity: float | None = None,
    **kwargs,
) -> BOMItem:
    return BOMItem(
        item_id=str(uuid.uuid4()),
        part_id=part_id,
        po_number=po_number,
        quantity=quantity,
        **kwargs,
    )


def html_table(rows: list[list[str]]) -> str:
    """Builds the flat <table><tr><td>...</td></tr></table> markup that
    parse_html_table expects — the same shape unstructured's own table HTML
    takes (see html_table.py's docstring)."""
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table>{body}</table>"


def make_parsed_document(
    *,
    table_rows: list[list[str]] | None = None,
    text_elements: list[str] | None = None,
    filename: str = "test.pdf",
) -> ParsedDocument:
    """A ParsedDocument with one table (if table_rows given) built from
    plain rows-of-cells, plus a handful of free-text elements — enough to
    drive extract_bom / extract_coc without touching unstructured."""
    elements: list[ParsedElement] = []
    tables: list[ParsedTable] = []

    if table_rows is not None:
        html = html_table(table_rows)
        text = "\n".join(" | ".join(row) for row in table_rows)
        tables.append(ParsedTable(element_id=str(uuid.uuid4()), page_number=1, html=html, text=text))
        elements.append(ParsedElement(element_id=str(uuid.uuid4()), type="Table", text=text, html=html, page_number=1))

    for line in text_elements or []:
        elements.append(ParsedElement(element_id=str(uuid.uuid4()), type="NarrativeText", text=line, page_number=1))

    full_text = "\n".join(el.text for el in elements)
    return ParsedDocument(
        document_id=str(uuid.uuid4()),
        filename=filename,
        original_extension=".pdf",
        stored_path=f"/tmp/{filename}",
        strategy_used="fast",
        element_count=len(elements),
        table_count=len(tables),
        elements=elements,
        tables=tables,
        full_text=full_text,
    )


def make_multi_table_document(
    table_row_sets: list[list[list[str]]],
    *,
    filename: str = "test.pdf",
) -> ParsedDocument:
    """Like make_parsed_document, but with several separate table elements
    in document order — for exercising multi-page table continuation, where
    unstructured splits one logical table into multiple ParsedTable entries
    (e.g. one per page) instead of a single table with every row."""
    tables: list[ParsedTable] = []
    elements: list[ParsedElement] = []

    for page, rows in enumerate(table_row_sets, start=1):
        html = html_table(rows)
        text = "\n".join(" | ".join(row) for row in rows)
        tables.append(ParsedTable(element_id=str(uuid.uuid4()), page_number=page, html=html, text=text))
        elements.append(ParsedElement(element_id=str(uuid.uuid4()), type="Table", text=text, html=html, page_number=page))

    full_text = "\n".join(el.text for el in elements)
    return ParsedDocument(
        document_id=str(uuid.uuid4()),
        filename=filename,
        original_extension=".pdf",
        stored_path=f"/tmp/{filename}",
        strategy_used="fast",
        element_count=len(elements),
        table_count=len(tables),
        elements=elements,
        tables=tables,
        full_text=full_text,
    )
