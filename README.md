# COC Review Tool — BOM/COC Semantic Validation

Rebuilding on the architecture in `AI_BOM_COC_Semantic_Validation_Architecture.docx`,
built against the requirements in the L&T requirements email.

## Stack

- Backend: FastAPI
- Document parsing: [unstructured](https://unstructured.io) (local, open-source library —
  no documents leave the machine), covering scanned/native PDFs, images, Word, Excel,
  CSV/TSV, plain text, HTML, and email formats.
- Frontend: React + TypeScript + Vite

## Current state (rewrite in progress)

The previous backend (pdfplumber/Tesseract extraction, rule-based + Ollama field
extraction, validation engine, Postgres persistence) has been removed and is being
rebuilt from scratch: parsing first, then rule-based parameter extraction, matching
the two boxes before the LLM comparison stage in the architecture diagram.

**Parsing** (`app/parsing/`) — upload → `unstructured`'s `partition()` dispatcher →
typed elements (Title, NarrativeText, Table, etc.), tables kept as both plain text and
HTML. Strategy defaults to `auto`, with a fallback chain (`hi_res` → `ocr_only` →
`fast`) if a strategy fails — e.g. if the hi-res layout model can't be downloaded on an
offline VM.
- `POST /documents/parse` — parse any supported file (PDF, scanned PDF, image, DOCX,
  XLSX/XLS, CSV/TSV, TXT, HTML, EML/MSG); saves the upload and the parsed JSON.
- `GET /documents`, `GET /documents/{document_id}` — list / fetch parsed output.

**Parameter extraction** (`app/parameters/`) — rule-based only (no LLM yet): table
header → canonical field mapping (`synonyms.py`, `table_headers.py` — carried over from
the original build, already validated against real L&T BOM/COC samples), inline
label:value text, a PO-number prose fallback, and presence-only compliance markers
(signature/seal/test certificate mentions).
- `POST /bom/upload` — parses a BOM and extracts line items (one dict of canonical
  fields per table row: `part_id`, `description`, `manufacturer`, `quantity`, ...).
  Requires a detected table; raises if none is found; no "ground truth"/versioning
  semantics yet — that's a later, comparison-stage concern.
  `GET /bom`, `GET /bom/{document_id}`.
- `POST /coc/upload` — accepts one or more files (`files=@a.pdf -F files=@b.pdf`),
  extracts a flat field list per COC (table + inline + presence, all kept — nothing
  arbitrates conflicting values yet since there's no LLM in the loop).
  `GET /coc`, `GET /coc/{document_id}`.

Not yet implemented: passing BOM/COC parameters to the local Gemma model on the VM for
comparison, PDF highlighting, validation PASS/FAIL/WARNING results, and the frontend
integration (the old BOM/COC upload UI in `frontend/` still points at the removed
endpoints and needs to be rewired once the pipeline's shape settles further).

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

## Running on the target VM (Docker)

```
docker compose up --build
```

The `postgres` and `ollama` services from the previous architecture were removed along
with the old backend; re-add persistence and the Gemma-serving service once the
parsed-output → LLM pipeline is built.
