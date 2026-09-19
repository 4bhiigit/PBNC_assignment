# Project Progress Tracker

Tracking execution of Document Intelligence & Question Extraction Service across Phases 0 to 10.

---

## Phase Checklist

- [x] **Phase 0: Plan & Architecture Alignment**
  - [x] Review AGENTS.md, SPEC.md, START_HERE.md, PHASE_PROMPTS.md
  - [x] Draft Phase 0 Implementation Plan artifact
  - [x] Setup docs/ directory and progress tracker
  - [x] User review and plan approval

- [x] **Phase 1: Scaffold, Docker, DB Schema, Auth**
  - [x] Repo structure (`app/`, `tests/`, `scripts/`, `docs/`)
  - [x] `pyproject.toml`, pinned dependencies, ruff & mypy setup
  - [x] `Dockerfile` (multi-stage, non-root, Tesseract eng+hin, libmagic) & `docker-compose.yml`
  - [x] `app/config.py` with `pydantic-settings` & `SecretStr`
  - [x] Structured JSON logging with `request_id` context
  - [x] SQLAlchemy 2.x async models + Alembic migrations for all SPEC §5 tables
  - [x] Auth endpoints (register, login with argon2 + JWT, me) & dependencies
  - [x] Global error envelope and `/health`, `/ready` endpoints
  - [x] Phase 1 test suite & verification (8 passed in 2.75s, ruff clean, mypy clean)

- [x] **Phase 2: Upload, Security, Storage, Status, Authz**
  - [x] `StorageBackend` abstraction + `LocalStorage` (owner-sharded, uuid keys)
  - [x] `POST /api/v1/documents` streaming upload & deep security validation
  - [x] Shared `get_owned_document` dependency (foreign ID -> 404)
  - [x] Redis upload rate limiting per user
  - [x] Document lifecycle endpoints (GET list, GET by ID, GET status, DELETE)
  - [x] Celery app configuration (queues: ingest, pages, finalize) & stub async task
  - [x] Phase 2 test suite & verification (23 passed in 11.58s, ruff clean, mypy clean)

- [x] **Phase 3: Ingest + OCR + Rules Parser (Offline End-to-End Slice)**
  - [x] `pipeline/ingest.py`, `page_analysis.py` (text layer vs scanned)
  - [x] `pipeline/preprocess.py` (OSD orientation, deskew, denoise, blur score, DPI)
  - [x] `pipeline/ocr.py` (Tesseract word-level confidences, page aggregation)
  - [x] `pipeline/headers_footers.py` (repeated line stripping)
  - [x] Extractor interface + `RulesExtractor` + `MockExtractor`
  - [x] Pure regex parsers for question numbers and option formats
  - [x] Celery worker pipeline execution (`process_document` -> `process_page` -> `finalize_document`)
  - [x] Phase 3 test suite & verification (94 passed in 40.90s, ruff clean, mypy clean)

- [ ] **Phase 4: LLM Extraction, Grounding, Stitching, Figures**
  - [ ] `LLMProvider` interface + `GeminiExtractor` (`google-genai`, structured Pydantic schema)
  - [ ] Fallback handling to `RulesExtractor` on failure/timeout (`LLM_FALLBACK_USED`)
  - [ ] `grounding.py` fuzzy grounding check (`rapidfuzz`) & `LOW_GROUNDING` flag
  - [ ] Rules vs LLM cross-check (`COUNT_MISMATCH`)
  - [ ] `stitcher.py` (multi-page question stitching, heuristics, orphan fragments)
  - [ ] `figures.py` (crop figure/table bounding boxes, store as `question_assets`)
  - [ ] Phase 4 test suite & verification

- [ ] **Phase 5: Answer Key & Multi-Document Links**
  - [ ] `answer_key/` (detect, parse, normalize, match)
  - [ ] Match statuses (`matched`, `not_found`, `ambiguous`, `conflict`, `invalid`)
  - [ ] `document_links` table & relationships (`answer_key_for`, `continuation_of`, `related`)
  - [ ] Link reconcile workflow with Redis distributed lock
  - [ ] Answer key endpoints & summary counts
  - [ ] Phase 5 test suite & verification

- [ ] **Phase 6: Confidence, Warnings, Review, API Polish**
  - [ ] Confidence formula implementation & configurable thresholds
  - [ ] Flag catalog & critical flag rules forcing `needs_review`
  - [ ] Warnings recording with page references
  - [ ] Human review endpoints (`PATCH /questions/{id}`, `POST /questions/{id}/review`)
  - [ ] Audit trail in `question_revisions`
  - [ ] Filtered questions API, review queue, export endpoint
  - [ ] OpenAPI documentation & schema export
  - [ ] Phase 6 test suite & verification

- [ ] **Phase 7: Sample Documents, Tests, Evaluation**
  - [ ] `scripts/generate_samples.py` (digital, spanning, answer keys, scanned, corrupted)
  - [ ] Full test suite execution & coverage report
  - [ ] `scripts/evaluate.py` comparing output against ground-truth JSON
  - [ ] Real evaluation metrics saved to `docs/demo_evidence/evaluation.md`

- [ ] **Phase 8: Documentation, Postman, Demo Evidence**
  - [ ] `README.md` (quick start, architecture overview, configuration, test instructions)
  - [ ] `docs/ARCHITECTURE.md` with Mermaid diagrams & walkthrough
  - [ ] `docs/DECISIONS.md` ADR entries for key technical trade-offs
  - [ ] `docs/AI_DISCLOSURE.md` (tools used during dev & runtime)
  - [ ] Postman collection & environment in `docs/postman/`
  - [ ] `scripts/run_demo.py` executing 10 live scenarios & generating `DEMO_REPORT.md`
  - [ ] Phase 8 verification

- [ ] **Phase 9: Polish Pass (Human-Style Cleanup)**
  - [ ] Codebase audit (remove dead code, redundant comments, generic names)
  - [ ] Documentation audit (plain tone, no filler words, accurate claims)
  - [ ] Verification of test suite and demo runner post-cleanup
  - [ ] Interview defense preparation notes (10 key architecture questions)

- [ ] **Phase 10: Final Audit (Fresh Clone Test)**
  - [ ] Clean directory clone & setup test
  - [ ] Secrets audit across repository & commit history
  - [ ] Requirements verification matrix against SPEC §19
  - [ ] Security audit against assignment §9
  - [ ] Final checklist artifact (`docs/FINAL_CHECKLIST.md`) & 15-question viva notes

---

## Current Status
- **Current Phase:** Phase 3 Completed -> Ready for Phase 4 (LLM Extraction, Grounding, Stitching, Figures)
- **Active Task:** Phase 4 planning and implementation
- **Verification:**
  - Tests: `uv run pytest tests` (94 passed in 40.90s across auth, upload, storage, numbering, options, page analysis, rules extraction, and full end-to-end async worker pipelines)
  - Linter: `uv run ruff check app tests` (0 errors)
  - Formatter: `uv run ruff format --check app tests` (68 files verified)
  - Typecheck: `uv run mypy app` (0 issues across 57 source files)
  - Security & Secrets: `.env` untracked in `.gitignore`, `.env.example` verified with placeholders only
- **Blockers / Approvals Needed:** None
