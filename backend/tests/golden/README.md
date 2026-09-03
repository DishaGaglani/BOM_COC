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
*same* document, byte-for-byte, were observed in practice to vary on
borderline presence-only judgment calls (e.g. whether a signature block
counted as solid evidence) — this is still true after the 2026-09-03 prompt
fixes below and isn't something a prompt edit fully closes off, so it stays
deliberately unasserted.

So this suite is exact only on fields with no legitimate reason to vary —
identifiers (`part_id`, `po_numbers`), and short numeric/categorical values
(`quantity`, `requirements` entries like `country_of_origin`/`grade`) — and
loose everywhere else: free-text `description` is checked by keyword, not
equality; presence-only fields (signature/seal/test_certificate/
import_documents/authorization_letter) aren't asserted at all. A change here
is either a real regression or a real (and worth knowing about) shift in
agent behavior — not run-to-run wording noise. `test_golden.py` still
supports an `optional_fields` fixture key (checked only when the agent
happens to include the field) for any future field that turns out to need
it — none currently do.

Three extraction-accuracy gaps found while building this were fixed on
2026-09-03 by editing the forjinn agent's system prompt directly (outside
this repo — see `backend/forjinn_system_prompt*.txt` locally, gitignored):
- `contract_date` on `MDP BOM.pdf` was extracting as `28.03.2022` — the
  document's internal *"R00 Approved Date"* from its revision-approval
  table, not a contract/PO date (the document's own "Date :" field is
  blank and it has no "PO Date" column). The prompt now explicitly excludes
  revision/approval-table dates and returns `null` when no genuine
  PO/SO/contract date exists — confirmed fixed; `mdp_bom.json`'s fixture
  now asserts `contract_date: null` for real.
- `XL62339.pdf`'s COC `model` field flickered — sometimes folded into
  `description` only instead of also being emitted on its own. The prompt
  now explicitly requires emitting a distinct Part No./Model No. as `model`
  every time; confirmed 3/3 across repeated live calls after the fix.
  `xl62339_coc.json`'s fixture asserts it as a required field again.
- Side effect of the `contract_date` fix's own wording (mentioning
  `"SO.No: ..."` as an example): `MDP BOM.pdf`'s per-line `po_number` (which
  should stay empty — this document has no per-line PO numbers, only a
  document-level SO number) started leaking the SO number into `po_number`
  on ~1/3 of live calls, a regression not present before that edit. Not
  asserted by any fixture (`po_number` was never checked here), so it
  wasn't caught by this suite going green — found by separately spot-
  checking `po_number` after the first fix. A follow-up prompt clause
  explicitly telling the agent never to reuse the document-level SO.No as a
  line's `po_number` fixed it — confirmed clean across 5 further live calls.
  Worth remembering for future prompt edits: a fix for one field's accuracy
  can shift a *different*, previously-fine field's behavior, so a targeted
  before/after check on the specific field you changed isn't enough —
  spot-check nearby fields too.

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
