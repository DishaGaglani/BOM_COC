# COC Review Tool — BOM/COC Semantic Validation

Checks a Certificate of Conformance (COC) against a project's Bill of Materials (BOM):
extracts structured fields from both, matches each COC to a BOM line item, runs
pass/fail/warning checks field-by-field, and produces a highlighted PDF + report.
Built against the architecture in `AI_BOM_COC_Semantic_Validation_Architecture.docx`
and the requirements in the L&T requirements email.

## Stack

- Backend: FastAPI, SQLite (`backend/storage/bomcoc.db`, via the stdlib `sqlite3` — no
  extra dependency)
- Document parsing: [unstructured](https://unstructured.io) (local, open-source library —
  no documents leave the machine), covering scanned/native PDFs, images, Word, Excel,
  CSV/TSV, plain text, HTML, and email formats.
- Frontend: React + TypeScript + Vite

## Current state

Extraction and validation are entirely **rule-based** — there is no LLM in the loop yet.
The architecture doc calls for a local Gemma model (served via Ollama) to arbitrate
ambiguous/conflicting extractions; that stage, and the Postgres persistence layer it
implies, haven't been built. Both were removed from `docker-compose.yml` during the
unstructured.io rewrite and are re-added once that pipeline exists.

**Parsing** (`app/parsing/`) — upload → `unstructured`'s `partition()` dispatcher →
typed elements (Title, NarrativeText, Table, etc.), tables kept as both plain text and
HTML. Strategy defaults to `auto`, with a fallback chain (`hi_res` → `ocr_only` →
`fast`) if a strategy fails — e.g. if the hi-res layout model can't be downloaded on an
offline VM.
- `POST /documents/parse` — parse any supported file (PDF, scanned PDF, image, DOCX,
  XLSX/XLS, CSV/TSV, TXT, HTML, EML/MSG); saves the raw upload to disk and the parsed
  output as a row in SQLite.
- `GET /documents`, `GET /documents/{document_id}` — list / fetch parsed output.

**Parameter extraction** (`app/parameters/`) — rule-based only: table header → canonical
field mapping (`synonyms.py`, `table_headers.py` — validated against real L&T BOM/COC
samples), inline label:value text, a PO-number prose fallback, and presence-only
compliance markers (signature/seal/test certificate mentions). Each extraction carries a
confidence score (`confidence.py`) reflecting how much that extraction method should be
trusted — used to pick a winner when the same canonical field is extracted more than
once with conflicting values.
- `POST /api/boms` — parses a BOM and extracts line items (one dict of canonical fields
  per table row: `part_id`, `description`, `manufacturer`, `quantity`, `po_number`, ...).
  Requires a detected table; raises if none is found. Superseds any prior active BOM for
  the same `project_id`, so the newest BOM becomes the reference ("BOM stays in scope
  until the next BOM"). `contract_date` (used to validate COC issue dates) is taken from
  an explicit form field, else inline letterhead text, else a "PO Date" table column.
  `GET /api/boms`, `GET /api/boms/{bom_id}`, `GET /api/boms/by-project/{project_id}/active`.
- `POST /api/boms/{bom_id}/cocs` — accepts one or more COC files (batch upload),
  extracts a flat field list per COC (table + inline + presence, all kept), matches it to
  a BOM line item, and runs full validation against it.
  `GET /api/boms/{bom_id}/cocs`, `GET /api/cocs/{coc_id}`.

**Matching** (`app/validation/matching.py`) — a COC is matched against BOM lines in tiers,
most specific first: Part ID + PO Number together, then Part ID alone, then PO Number
alone. Each tier compares alphanumeric-only (formatting noise like `PO-45892` vs
`PO45892` vs `PO 45892` doesn't stop a match). Real BOMs often carry more than one line
for the same part (separate lots/deliveries), so a tier matching more than one line falls
back to quantity as a tiebreaker before giving up. If a tier still can't be narrowed to
one line, the match is reported `ambiguous` (distinct from `unmatched` — no BOM line
looks like this COC at all) rather than silently validating against an arbitrarily-picked
line. A logical BOM/COC table that `unstructured` splits across a page break into
separate table elements is reassembled — a header-less fragment whose row width fits the
immediately preceding table's columns is treated as that table's continuation, one page
ahead only.

**Validation** (`app/validation/`) — per matched BOM line: identity-field presence (PO or
Serial Number required), match (PO Number, Part ID, Model, Serial Number — exact first,
falling back to a formatting-only difference, then to a close-but-not-identical WARNING
for likely typos), quantity match (a single COC no longer has to equal the BOM line's
full quantity — partial shipments across multiple COCs are tracked cumulatively against
the BOM's total, only failing once the running total is exceeded), fuzzy token-set match
for free-text description, exact match for manufacturer/manufacturing year/warranty
expiry, COC issue date on/after the BOM's contract date, presence checks (signature,
seal, test certificate, authorization letter), and import documents required only when
the BOM marks that item as imported. Every result is PASS / FAIL / WARNING with a
human-readable reason.
- `GET /api/cocs/{coc_id}/report` — parameter-by-parameter validation report.
- `GET /api/cocs/{coc_id}/highlighted-pdf` — the COC with each validated field
  highlighted on the page (via `app/annotation/pdf_annotator.py`), tagged by status. Built
  best-effort: a failure here (malformed bbox, corrupt/encrypted source PDF) is logged and
  degrades to a 404 on this endpoint rather than losing the COC's validation result, which
  is already saved by this point.

**Frontend** (`frontend/`) — wired to the current API: upload/list BOMs, upload COCs
against a selected BOM, and view PASS/FAIL/WARNING results per certificate
(`BomLibrary`, `BomUpload`, `CocUpload`, `ValidationReport`, `StatusBadge`).

**Storage** (`app/db.py`, `app/storage.py`, `app/parameters/storage.py`) — structured
records (parsed-document metadata, BOMs, COCs) live in SQLite, one JSON blob per row
plus a few indexed columns for the query patterns each caller actually needs (list by
project, filter COCs by `bom_id`, order by upload time) — not a normalized relational
redesign, just the same JSON documents behind SQLite instead of loose files, so writes
are atomic and a `UNIQUE (project_id, version)` constraint on `boms` makes a version
collision from two concurrent BOM uploads for the same project a loud, retryable
`ValueError` instead of one silently overwriting the other. Raw binary files (the
original upload, the highlighted PDF) stay on disk under `backend/storage/` — the
parsing/annotation libraries need a real file path, not a blob — everything else is in
`backend/storage/bomcoc.db`.

### Known gaps

- No LLM/semantic comparison stage (per the architecture doc) — everything today is
  deterministic rules + confidence heuristics, no arbitration beyond "highest confidence
  wins" on conflicting extractions.
- The BOM version-assignment race isn't fully closed, only made safe: `get_next_bom_version`
  and the eventual `save_bom` are still two separate calls (`bom_service.ingest_bom`), so
  two concurrent uploads for the same project can still both read the same "next version"
  before either writes — the loser now gets a clear, retryable error instead of silently
  overwriting the winner, but closing the race itself would mean collapsing that two-call
  pattern into one storage-layer transaction.
- The frontend header text ("Runs on this machine — Postgres + local Ollama") predates
  the rewrite and doesn't reflect the current stack — cosmetic cleanup pending.
- Golden-file tests against the real samples in `review/` (through the actual
  `unstructured` pipeline, not just fixtures) aren't built yet — see
  `backend/tests/golden/README.md`.

## Running locally (dev machine, without Docker)

Backend:
```
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# requires poppler and tesseract installed locally (brew install poppler tesseract on macOS)
uvicorn app.main:app --reload
```

Try it without the API, directly against a sample file:
```
python scripts/parse_file.py "../review/49COC.pdf"
```

Frontend:
```
cd frontend
npm install
npm run dev
```

## Running tests

The unit/component suite (`backend/tests/`) covers extraction, matching, and validation
logic directly — no `unstructured`/torch install needed:
```
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
See `backend/tests/golden/README.md` for the (not yet built) real-document suite that
exercises the actual parsing pipeline against the samples in `review/`.

## Running on the target VM (Docker)

```
docker compose up --build
```

The `postgres` and `ollama` services from the previous architecture were removed along
with the old backend. Persistence is now SQLite (a file under the `backend` bind mount,
so it survives container restarts same as before) — no separate DB service needed; only
the Gemma-serving service remains to be re-added, once the parsed-output → LLM pipeline
is built.
