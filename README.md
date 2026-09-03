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

**Parsing** (`unstructured.io`) is deterministic and local — no LLM in that loop, no
documents leave the machine.

**Extraction is semantic**, via a forjinn.com-hosted agent (Qwen-based;
`app/services/semantic_extractor.py` + `forjinn_client.py`). It replaced an earlier
rule-based layer (hand-maintained header-synonym dicts, priority-ordered column
matching, regex label:value/presence detection) that couldn't generalize past the vendor
phrasing it was written against. The agent is handed unstructured's already-structured
output (table rows, text elements, each with page/bbox) and asked directly which
canonical field each column/label/phrase means — see the system prompt this was built
against for the exact contract. If `BOMCOC_FORJINN_API_URL` is unset, extraction has
nothing to call and BOM/COC ingestion raises — there's no rule-based fallback anymore.

**Validation** is two-tier: **Tier 1 (rule-based)** always runs, checking format, presence,
dates, and exact/fuzzy matches against the BOM (`app/validation/rules.py`+`engine.py` —
untouched by the extraction rewrite). **Tier 2 (semantic, via the same forjinn agent)** is
optional — if `BOMCOC_FORJINN_API_URL` is set, the agent takes the extracted facts and
validates them holistically after a successful BOM match. If semantic validation is
unavailable or disabled, Tier 1 checks alone are sufficient for compliance review — it's
an enhancement, not a requirement. See `app/services/semantic_validator.py` for the
request/response contract — `_parse_agent_result`'s mapping of
`passes_compliance`/`reasoning`/`missing_or_conflicting_fields` is confirmed against a
real forjinn response.

**Parsing** (`app/parsing/`) — upload → `unstructured`'s `partition()` dispatcher →
typed elements (Title, NarrativeText, Table, etc.), tables kept as both plain text and
HTML. Strategy defaults to `auto`, with a fallback chain (`hi_res` → `ocr_only` →
`fast`) if a strategy fails — e.g. if the hi-res layout model can't be downloaded on an
offline VM.
- `POST /documents/parse` — parse any supported file (PDF, scanned PDF, image, DOCX,
  XLSX/XLS, CSV/TSV, TXT, HTML, EML/MSG); saves the raw upload to disk and the parsed
  output as a row in SQLite.
- `GET /documents`, `GET /documents/{document_id}` — list / fetch parsed output.

**Parameter extraction** (`app/services/semantic_extractor.py`, `app/parameters/`) — the
forjinn agent maps table columns/labels and prose to canonical fields (`part_id`,
`description`, `manufacturer`, `quantity`, `po_numbers`, signature/seal/test-certificate
presence, ...); `app/parameters/html_table.py` (stdlib-only, no guessing) turns
unstructured's table HTML into plain rows-of-cells for the agent's payload, and
`app/parameters/schema.py` defines the canonical field set both the agent and the
validation rules key off of. Domain judgment calls that used to be hardcoded (e.g. a
BOM's customer-catalog column outranking the manufacturer's own part number for
`part_id`) now live in the agent's system prompt instead of a priority list in code.
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

**Validation** (`app/validation/` + `app/services/semantic_validator.py`) — two-tier validation
per matched BOM line, run in sequence:
1. **Tier 1: Fast rule-based checks** — identity-field presence (PO or Serial Number required),
   match (PO Number, Part ID, Model, Serial Number — exact first, falling back to a
   formatting-only difference, then to a close-but-not-identical WARNING for likely typos),
   quantity match (a single COC no longer has to equal the BOM line's full quantity —
   partial shipments across multiple COCs are tracked cumulatively against the BOM's total,
   only failing once the running total is exceeded), fuzzy token-set match for free-text
   description, exact match for manufacturer/manufacturing year/warranty expiry, COC issue
   date on/after the BOM's contract date, presence checks (signature, seal, test certificate,
   authorization letter), and import documents required only when the BOM marks that item as
   imported.
2. **Tier 2: Semantic validation via forjinn** (optional, requires `BOMCOC_FORJINN_API_URL`
   set) — after a successful match, the same forjinn-hosted Qwen agent that does field
   extraction takes the extracted facts and validates them holistically: "does this COC
   actually demonstrate compliance with this BOM's requirements?" It can catch nuance that
   rigid rules miss (e.g. a typo in part number that's still obviously the same component in
   context, or a qualification that's valid but in a non-standard format). If semantic
   validation is disabled or unavailable, only Tier 1 checks run — the tool remains fully
   functional for compliance review, just with less semantic sophistication.

   Every result is PASS / FAIL / WARNING with a human-readable reason.
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
are atomic. BOM version assignment goes through `create_bom_version` (used by
`bom_service.ingest_bom`), which reads the current active BOM, supersedes it, computes
the next version, and inserts the new row all inside one `BEGIN IMMEDIATE` transaction —
a second concurrent upload for the same project blocks on the write lock instead of
reading the same "next version," so two concurrent uploads for one project now get
correct sequential versions rather than one merely failing safe. The `UNIQUE
(project_id, version)` constraint on `boms` remains as a safety net for any caller that
bypasses `create_bom_version`. Raw binary files (the original upload, the highlighted
PDF) stay on disk under `backend/storage/` — the parsing/annotation libraries need a
real file path, not a blob — everything else is in `backend/storage/bomcoc.db`.

**Security** (`app/auth.py`, `app/auth_core.py`, `app/parameters/file_signatures.py`) —
- Optional API key: unset by default (local dev stays friction-free); set
  `BOMCOC_API_KEY` and every `/api/*`/`/documents/*` route requires a matching
  `X-API-Key` header (`/health` always stays open). The frontend reads the matching
  `VITE_API_KEY` and attaches it to every request; the highlighted-PDF link is fetched
  as an authenticated blob rather than a plain `<a href>`, since a header can't be
  attached to a bare link.
- CORS is restricted to `settings.allowed_origins` (default
  `["http://localhost:5173"]`, overridable via `BOMCOC_ALLOWED_ORIGINS`) instead of `*`.
- Uploads are checked against a magic-byte signature table
  (`file_signatures.matches_signature`) in addition to the existing extension check, so
  a mislabeled or malicious file (e.g. HTML renamed to `.pdf`) is rejected with 400
  before it reaches `unstructured`.
- Parsing runs off the event loop with a timeout
  (`asyncio.wait_for(asyncio.to_thread(parse_document, ...), timeout=settings.parse_timeout_seconds)`,
  default 120s, returns 504 on timeout) — previously a blocking sync call directly
  inside an `async def` endpoint, so one slow parse stalled every other request too.

### Known gaps

- forjinn's response envelope is confirmed against real calls for both the "extract" and
  "validate" tasks (unwrapped JSON directly at the top level under a `"text"` key,
  itself a JSON *string* — `_unwrap_response` handles that; no `Authorization` header
  needed against the current flow). The agent isn't temperature-0: repeated live calls
  against the same document were observed to vary on borderline presence-only judgment
  calls (e.g. whether a signature block counted as solid evidence) and on whether a
  secondary identifier got echoed as its own field or folded into free text — see
  `backend/tests/golden/README.md`'s "What's asserted, and what deliberately isn't" for
  the full picture, and its "known, real extraction-accuracy gap" note on `contract_date`
  currently picking up a document's internal approval date on at least one real BOM.
- Extraction has no rule-based fallback — if forjinn is unreachable or misconfigured,
  BOM/COC ingestion fails outright rather than degrading to a lesser result.
- Golden-file tests against the real samples in `review/` now cover `MDP BOM.pdf` and
  `XL62339.pdf` (`backend/tests/golden/test_golden.py`) — the fuller set in `review/`
  (`49COC.pdf`, `COC LETTER MCB.pdf`, `xh02020.pdf`) isn't fixtured yet.

## Running locally (dev machine, without Docker)

Backend:
```
cd backend
python3 -m venv .venv && source .venv/bin/activate
# requires poppler and tesseract installed locally (brew install poppler tesseract on macOS)
# vendor/fake-pycrypto MUST install before requirements.txt on Python 3.11+ —
# see vendor/fake-pycrypto/README.md for why.
pip install ./vendor/fake-pycrypto
pip install -r requirements.txt
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

The `postgres` and `ollama` services from earlier architectures have both been removed —
persistence is SQLite (a file under the `backend` bind mount, so it survives container
restarts), and semantic extraction/validation calls out to forjinn.com (see
`BOMCOC_FORJINN_API_URL` in `docker-compose.yml`) instead of running a local model, so
there's no model-serving container to run here at all.
