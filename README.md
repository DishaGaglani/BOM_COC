# COC Review Tool — BOM/COC Semantic Validation

Phase 1 MVP implementation of the architecture in `AI_BOM_COC_Semantic_Validation_Architecture.docx`,
built against the requirements in the L&T requirements email.

## Stack

- Backend: FastAPI + SQLAlchemy + Postgres
- Extraction: pdfplumber (native tables/text) + Tesseract OCR (scanned fallback)
- Semantic extraction/mapping: local Ollama model (no external API calls)
- Frontend: React + TypeScript + Vite
- PDF annotation: PyMuPDF

## What's implemented (Phase 1)

- BOM/Traceability Matrix upload → table parsing → persistent BOM + BOM_ITEMS,
  with the newest BOM per project superseding the previous one.
- COC upload (single or batch) → OCR/table extraction → rule-based + local-LLM
  field extraction → merge (rule-based wins for critical identifiers).
- Validation: document-type check, PO/Serial identity-field presence,
  PO Number, Part ID, Model, Serial Number, Quantity-vs-BOM — each PASS/FAIL/WARNING.
- Coordinate-aware highlighting of extracted fields on the original COC PDF,
  color-coded by status.
- Validation report (expected vs actual vs status vs reason) per COC.

## Not yet implemented (Phase 2, per the architecture doc's phased plan)

YOM, warranty expiry, COC issue date vs contract date, signature/seal
detection, test certificates, import documents, authorization/linking
letters, confidence-based human-in-the-loop review, batch/version dashboard.

## Running locally (dev machine, without Docker)

Backend:
```
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# requires a running Postgres reachable at DATABASE_URL, and tesseract-ocr installed locally
alembic revision --autogenerate -m "init" && alembic upgrade head
uvicorn app.main:app --reload
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

Then pull the local model into the Ollama container once:
```
docker exec -it <ollama_container_name> ollama pull llama3.1:8b
```

Adjust `OLLAMA_MODEL` in `docker-compose.yml` if the VM's specs call for a
smaller/quantized model.

## Known gap

Extraction (`app/extraction`, `app/services/bom_parser.py`) and the
terminology synonym map (`app/normalization/synonyms.py`) were built against
the field list in the requirements doc, not against real sample BOM/COC
files — none were available in this session. Expect to tune table-header
detection and the synonym map once real documents are supplied.
