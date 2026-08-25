"""Confidence heuristics for rule-based field extraction.

There's no model giving a real probability here (extraction is entirely
rule-based, per the current scope), except for one real signal:
unstructured's hi_res layout model DOES score how sure it is that a region
is actually a table (ParsedTable.confidence, from `detection_class_prob`).
Everywhere else, confidence is a fixed constant reflecting how much a
human should trust that *kind* of match relative to the others — used by
the validation engine to pick a winner when multiple extractions disagree
on the same canonical field (e.g. a PO number found both in a table cell
and in letterhead prose).

Ordering, highest to lowest trust:
  table (native format)  > table (hi_res-detected)  > inline label:value
  > PO-number prose fallback  > keyword presence check
"""

# xlsx/docx/csv tables are parsed structurally (no layout model involved,
# nothing to misdetect) — the only uncertainty left is the header-to-
# canonical-field synonym mapping, hence not a flat 1.0.
NATIVE_TABLE_CONFIDENCE = 0.95

# Fallback for a hi_res-detected table with no `detection_class_prob` in
# its metadata (shouldn't normally happen, but the field is Optional).
HI_RES_TABLE_DEFAULT_CONFIDENCE = 0.85

# A strict "<label>: <value>" match against a known synonym — more precise
# than the table's column-header interpretation, but the source isn't a
# structured cell, so it sits below both table tiers.
INLINE_LABEL_VALUE_CONFIDENCE = 0.75

# PO_NUMBER_RE matches loosely inside a sentence rather than a clean
# labeled line — weaker signal than a real label:value pair.
PO_FALLBACK_CONFIDENCE = 0.55

# A keyword found anywhere in the document's text is not the same as
# verifying a real signature/seal mark is present.
PRESENCE_CONFIDENCE = 0.5
