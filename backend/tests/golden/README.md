# Golden-file suite (not yet implemented)

`tests/` covers extraction, matching, and validation logic directly, by
constructing `ParsedDocument`/`BOMItem`/`ExtractedField` fixtures — it never
calls `unstructured.partition()`, so it runs in well under a second with no
torch/tesseract/poppler install.

That's deliberately *not* the same as proving the pipeline still works on
the real samples in `review/` (`49COC.pdf`, `COC LETTER MCB.pdf`, `MDP
BOM.pdf`, `XL62339.pdf`, `xh02020.pdf`) — those exercise the full parsing
stack: layout detection, OCR fallback, real table-structure recognition,
and the header synonyms/regexes against actual vendor phrasing rather than
hand-written fixtures. A change to `synonyms.py`, `table_headers.py`, or the
extraction regexes can pass every unit test here and still silently stop
matching a real document's headers.

## To build this

1. Install the full stack: `pip install -r requirements.txt` (pulls in
   `unstructured`, `torch`, `transformers`; also needs `poppler` and
   `tesseract` — see the main README).
2. For each sample, run `python scripts/parse_file.py "../review/<file>"`,
   inspect the output, and hand-verify the extracted fields are actually
   correct (don't trust the tool's own output as ground truth — that's
   circular).
3. Save the verified expected fields as a fixture (e.g.
   `tests/golden/fixtures/49coc.json`) and add a test that parses the real
   file, runs `extract_coc`, and asserts against it.
4. Mark these tests to skip cleanly when `unstructured` isn't importable, so
   `pytest` (the fast suite) still runs without the heavy stack installed:
   `pytest.importorskip("unstructured")` at the top of the module.
