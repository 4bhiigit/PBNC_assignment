# Document Intelligence & Question Extraction Service

An asynchronous, multi-tenant microservice for extracting, structuring, and verifying questions, options, figures, and answer keys from examination documents (digital PDFs, scanned PDFs, single and multi-page images).

Built with Python 3.12, FastAPI, PostgreSQL 16, Redis 7, Celery, SQLAlchemy 2.0 (async), PyMuPDF, OpenCV, Tesseract OCR, RapidFuzz, and optional Google Gemini multimodal structured extraction.

---

## 1. Key Capabilities

- **Asynchronous Ingestion**: Streaming upload returns HTTP 202 immediately. Background Celery workers process ingestion, page rendering, OCR, and extraction across dedicated queues.
- **Offline-First or AI-Augmented**: Runs 100% locally with `EXTRACTOR=rules` and local Tesseract, or with `EXTRACTOR=hybrid` to leverage Gemini multimodal structured outputs with automatic rule fallback on quota/timeout errors.
- **Cross-Page Question Stitching**: Automatically detects questions spanning 2 or 3 pages, de-hyphenates split words, normalizes continuation options (`(C)`, `(D)`), and maintains multi-page source references (`source_pages=[1, 2]`).
- **Answer Key Extraction & Link Reconciliation**: Automatically parses embedded answer keys, inline answer notations (`Ans: (b)`), or links separate answer key PDFs via `document_links` with distributed reconciliation.
- **Confidence Scoring & Flag Engine**: Computes composite confidence scores (OCR quality, fuzzy grounding score, sequence consistency, LLM confidence) and emits quality flags across critical and warning severities.
- **Human Review & Audit Trail**: Endpoints for updating questions with automatic revision snapshot recording (`question_revisions`), review approvals/rejections, and structured export conforming to SPEC §14.
- **Strict Tenant Isolation**: All resources are scoped by `owner_id`. Foreign resource IDs return `404 Not Found` rather than `403 Forbidden` to prevent ID enumeration.

---

## 2. Quick Start (Docker Compose)

The service can be launched with Docker Compose on any clean machine:

```bash
# 1. Clone repository
git clone <repo-url>
cd <repo-folder>

# 2. Configure environment
cp .env.example .env

# 3. Start PostgreSQL, Redis, FastAPI web service, and Celery worker
docker compose up -d --build

# 4. Check system health
curl -f http://localhost:8000/health
curl -f http://localhost:8000/ready
```

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

---

## 3. Local Development Setup

To run the service locally with `uv`:

```powershell
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env

# 3. Apply database migrations
uv run alembic upgrade head

# 4. Run API server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Run Celery worker (in separate terminal)
uv run celery -A app.workers.celery_app.celery worker -l INFO -Q ingest,pages,finalize -c 2
```

---

## 4. Configuration Reference

All settings are managed via environment variables and validated with `pydantic-settings` in `app/config.py`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/doc_intel` | Async PostgreSQL connection string for FastAPI. |
| `SYNC_DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/doc_intel` | Sync PostgreSQL connection string for Celery workers. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis instance for rate limiting and Celery results. |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Redis queue broker for Celery tasks. |
| `JWT_SECRET_KEY` | *(SecretStr placeholder)* | HMAC key for signing authentication tokens. |
| `EXTRACTOR` | `rules` | Extraction engine: `rules`, `hybrid`, `llm`, or `mock`. |
| `GEMINI_API_KEY` | *(Optional)* | Google Gemini API key for hybrid / LLM extraction. |
| `STORAGE_BACKEND` | `local` | Storage backend (`local`). |
| `STORAGE_PATH` | `./data/storage` | Local directory for raw uploads and rendered assets. |
| `MAX_UPLOAD_SIZE_BYTES` | `52428800` (50 MB) | Maximum upload file size. |

---

## 5. API Endpoints

### Authentication
- `POST /api/v1/auth/register` — Register a new tenant account.
- `POST /api/v1/auth/login` — Authenticate and receive JWT bearer token.
- `GET /api/v1/auth/me` — Current user profile.

### Document Management
- `POST /api/v1/documents` — Upload document (returns HTTP 202 Accepted with document ID).
- `GET /api/v1/documents` — List uploaded documents with pagination and status filters.
- `GET /api/v1/documents/{id}` — Document metadata, page count, and role.
- `GET /api/v1/documents/{id}/status` — Real-time processing progress, current stage, and error messages.
- `GET /api/v1/documents/{id}/pages/{page_no}/image` — Stream rendered PNG page image.
- `DELETE /api/v1/documents/{id}` — Delete document, pages, extracted questions, and stored assets.

### Questions & Review
- `GET /api/v1/documents/{id}/questions` — List extracted questions with filtering by section, type, status, and min confidence.
- `GET /api/v1/documents/{id}/review-queue` — Filter questions flagged with `status=needs_review`.
- `GET /api/v1/documents/{id}/warnings` — Document quality warnings with page references.
- `GET /api/v1/documents/{id}/export` — Export final question paper JSON conforming to SPEC §14.
- `GET /api/v1/questions/{id}` — Detailed question schema with options, bounding boxes, and answer status.
- `PATCH /api/v1/questions/{id}` — Edit question content (creates a recorded revision snapshot).
- `POST /api/v1/questions/{id}/review` — Approve or reject question status.

### Answer Keys & Multi-Document Links
- `GET /api/v1/documents/{id}/answer-keys` — List answer key entries associated with document.
- `POST /api/v1/documents/{id}/links` — Create relationship link between documents (`answer_key_for`).
- `POST /api/v1/documents/{id}/reconcile` — Execute answer key reconciliation across linked documents.

---

## 6. Testing & Evaluation

### Run Test Suite
```powershell
# Run all unit and integration tests (171 tests)
uv run pytest

# Run with test coverage report
uv run pytest --cov=app --cov-report=term-missing
```

### Run Pipeline Evaluation
Generate all synthetic evaluation papers and benchmark extraction accuracy against ground-truth JSON files:
```powershell
uv run python scripts/generate_samples.py
uv run python scripts/evaluate.py
```
Evaluation metrics are recorded in `docs/demo_evidence/evaluation.md`.

### Run Interactive Demo Runner
Execute all 10 standard end-to-end user workflows:
```powershell
uv run python scripts/run_demo.py
```
Demo output and artifacts are written to `samples/output/` and `docs/demo_evidence/DEMO_REPORT.md`.

---

## 7. Security & File Safety

1. **Magic-Byte MIME Verification**: Uploaded streams are validated using puremagic byte sniffing. Files claiming to be PDF or image but containing executable or shell scripts are rejected with HTTP 400.
2. **Decompression Bomb Protection**: Pillow image allocations are restricted (`MAX_IMAGE_PIXELS = 100_000_000`) to prevent memory exhaustion from zip-bomb/pixel-bomb files.
3. **Password-Protected File Detection**: Encrypted PDFs are identified and rejected cleanly with error code `FILE_ENCRYPTED`.
4. **Structured JSON Logging**: Request IDs, document IDs, and task IDs are correlated across log lines without logging sensitive authentication tokens or raw file content.
