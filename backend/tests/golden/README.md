# Golden-file suite

`tests/` covers extraction, matching, and validation logic directly, by
constructing `ParsedDocument`/`BOMItem`/`ExtractedField` fixtures — it never
calls `unstructured.partition()` or the forjinn agent, so it runs in well
under a second with no torch/tesseract/poppler install and no network.

That's deliberately *not* the same as proving the pipeline still works on a
real document (`test_golden.py`, covering `MDP BOM.pdf` and `XL62339.pdf` so
far, out of the fuller set in `review/`) — this suite exercises the full
parsing stack (layout detection, OCR fallback, real table-structure
recognition) and the live forjinn agent's field mapping against actual
vendor phrasing rather than hand-written fixtures. A change to the agent's
prompt/response handling can pass every unit test in `tests/` and still
silently stop matching a real document's headers.

## Running it

Needs the full parsing stack (`pip install -r requirements.txt`, plus
`poppler`/`tesseract`) and `BOMCOC_FORJINN_API_URL` set to a reachable
forjinn flow — `pytest.importorskip("unstructured")` and a
`pytest.mark.skipif` on `settings.forjinn_api_url` at the top of
`test_golden.py` make both conditions skip cleanly (not fail) when unmet, so
the fast suite (`pytest` from `backend/`) stays fast/offline and CI without
network access or the heavy stack doesn't break:

```
cd backend
pip install -r requirements.txt   # unstructured, torch, transformers, ...
export BOMCOC_FORJINN_API_URL=https://forjinn.com/api/v1/prediction/<flow-id>
pytest tests/golden/
```

Each real forjinn call takes ~60-90s over a multi-page document — expect
this suite to take a few minutes, not the sub-second fast suite.

## What's asserted, and what deliberately isn't

The forjinn agent isn't temperature-0. Repeated live calls against the
*same* document, byte-for-byte, were observed in practice to vary on:
borderline presence-only judgment calls (e.g. whether a signature block
counted as solid evidence), and whether a secondary identifier (e.g. a COC's
manufacturer part number, already redundant with `description`) got echoed
as its own field or folded into the free text.

So this suite is exact only on fields with no legitimate reason to vary —
identifiers (`part_id`, `po_numbers`), and short numeric/categorical values
(`quantity`, `requirements` entries like `country_of_origin`/`grade`) — and
loose everywhere else: free-text `description` is checked by keyword, not
equality; presence-only fields (signature/seal/test_certificate/
import_documents/authorization_letter) aren't asserted at all; and fields
confirmed to flicker between calls (see `fixtures/xl62339_coc.json`'s
`optional_fields`) are checked only when the agent happens to include them.
A change here is either a real regression or a real (and worth knowing
about) shift in agent behavior — not run-to-run wording noise.

One known, real extraction-accuracy gap found while building this (not a
code bug, and not covered by an assertion): against `MDP BOM.pdf`, the agent
extracted `contract_date` as `28.03.2022` — that's actually the document's
internal *"R00 Approved Date"* from its revision-approval table, not a
contract/PO date; the document's own "Date :" field is blank and it has no
"PO Date" column. Worth a prompt fix on the forjinn side (out of this repo's
control), tracked here rather than silently asserted as correct.

## Adding another sample

1. Run `python scripts/parse_file.py "../review/<file>"` (or the snippet
   below) and inspect the output.
2. Hand-verify the extracted fields against the document's own text — don't
   trust the tool's own output as ground truth, that's circular. Quote the
   exact source phrasing you checked against in the fixture's `_note`.
3. Save the verified fields as `tests/golden/fixtures/<name>.json`, keeping
   volatile fields out of the strictly-asserted set (see above).
4. Add a test in `test_golden.py` that parses the real file, runs
   `extract_bom`/`extract_coc`, and asserts against the fixture.

```python
import asyncio
from app.parsing.unstructured_parser import parse_document
from app.services.semantic_extractor import extract_coc  # or extract_bom

doc = parse_document("../review/<file>", "<file>")
fields = asyncio.run(extract_coc(doc))
```
