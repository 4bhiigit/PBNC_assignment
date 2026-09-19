# PHASE PROMPTS — Antigravity me ek-ek karke paste karo

Har phase ke liye: **nayi conversation** → prompt paste → agent ka plan review karo → approve → kaam ke baad `git commit`.
Har prompt ka pehla paragraph context deta hai, taaki nayi conversation me bhi agent bhatke nahi.

Common header (har prompt ke start me already hai): *Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md first.*

**Style footer (har prompt ke end me yeh paste karo):**

```
Style: build this properly and write it like a careful human engineer. Follow the "Authorship and style" section of AGENTS.md: comments only for the why, concrete names, no over-abstraction or leftover stubs, plain log/error messages, no emojis, no filler words in docs, natural short commit messages. Keep it simple enough that I can explain every file myself. Do not invent history, benchmarks or results.
```

---

## Phase 0 — Plan only (Planning mode, no code)

```
Read AGENTS.md, docs/SPEC.md and docs/assignment.pdf carefully.

Do NOT write any code yet. Produce an implementation plan artifact that contains:
1. A phase-by-phase build order (phases 1-10 as described below) with the concrete files each phase will create.
2. A list of ambiguities, risks or contradictions you found in SPEC.md vs the assignment PDF, each with your proposed decision.
3. Pinned dependency versions you intend to use (Python 3.12, FastAPI, SQLAlchemy 2.x, Celery, PyMuPDF, opencv-python-headless, pytesseract, google-genai, etc.) and any licence concerns.
4. The exact `docker compose` service list and how a developer runs everything.
5. A verification strategy per phase (which commands prove it works).
6. Which assignment evaluation criteria (25/20/15/15/10/5/5/5) each phase mainly serves.
7. How you will follow the "Authorship and style" rules in AGENTS.md from the very first file (natural, properly finished code, not boilerplate).

Phases: 1 scaffold+DB+auth · 2 upload/security/storage/status · 3 ingest+OCR+rules parser (end-to-end slice without LLM) · 4 LLM extraction+grounding+stitching+figures · 5 answer key+multi-document links · 6 confidence/warnings/review APIs+OpenAPI polish · 7 sample generator+tests+evaluation · 8 docs+Postman+demo evidence · 9 polish pass (human-style cleanup) · 10 final audit.

Create docs/PROGRESS.md with the phase checklist. Stop after presenting the plan and wait for my approval.
```

---

## Phase 1 — Scaffold, Docker, DB schema, Auth

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Implement Phase 1 (SPEC §2, §4, §5, §13 auth+ops, §15).

Deliver:
- Repo layout per SPEC §4, pyproject.toml (pinned deps, ruff + mypy config), Makefile, .gitignore (must ignore .env, storage volumes, __pycache__, *.pyc, samples/output/tmp), .env.example with placeholders only.
- Dockerfile (multi-stage, non-root user, includes tesseract-ocr with eng and hin language data, libmagic) and docker-compose.yml with services: api, worker, db (postgres:16), redis (redis:7), and an optional `minio` profile. Healthchecks on db and redis; api waits for db.
- app/config.py using pydantic-settings with SecretStr, fail-fast validation.
- Structured JSON logging with request_id middleware.
- SQLAlchemy 2 models + Alembic migration for the FULL schema in SPEC §5 (all tables, enums, indexes, FKs). Async engine for API; sync engine helper for workers.
- Auth: register, login (argon2 + JWT), me. Dependencies: get_current_user, require_admin.
- Global error envelope (SPEC §13) for HTTP errors, validation errors and unhandled exceptions.
- /health and /ready.
- Tests: auth happy path, wrong password, duplicate email, invalid token, health/ready, error envelope shape.

Acceptance (run and report real output): `cp .env.example .env && docker compose up --build -d`, `alembic upgrade head` succeeds inside the container, `http://localhost:8000/docs` responds, `make test` passes.
Update docs/PROGRESS.md. Do not implement upload or pipeline yet.
```

---

## Phase 2 — Upload, security, storage, status, authz

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Implement Phase 2 (SPEC §5, §6, §13 documents endpoints).

Deliver:
- StorageBackend interface + LocalStorage (sharded by owner, uuid keys, no user-controlled path parts, path-traversal safe). S3Storage only if time allows (behind the same interface).
- POST /api/v1/documents exactly per SPEC §6: streaming size cap, magic-byte validation, PDF/image deep validation (encrypted PDF, page cap, decompression-bomb guard, truncated/corrupt files), sha256, dedupe, per-user rate limit via Redis, 202 response, QUEUE_UNAVAILABLE handling.
- GET /documents, GET /documents/{id}, GET /documents/{id}/status, DELETE /documents/{id}, page image stream endpoint stub.
- One shared dependency `get_owned_document` used by every document-scoped route. Foreign or missing id → 404. Admin may read all.
- Celery app wiring (queues: ingest, pages, finalize), and a STUB `process_document` task that just moves status queued→processing→completed so the async flow is provable end-to-end. Task time limits + acks_late configured.
- Progress tracking (DB + Redis cache) exposed by /status.
- Tests: valid PDF/PNG/JPG upload; rejected: wrong magic bytes with .pdf extension, .txt, empty file, oversized stream (without Content-Length), encrypted PDF, truncated PDF, huge-pixel image; unauthenticated → 401; **user B cannot see user A's doc (404) on every document-scoped endpoint**; rate limit → 429; error envelope on all failures.

Acceptance (report real output): curl/httpx transcript showing upload → 202 → polling /status until completed with the stub task, and the authz test results.
Update docs/PROGRESS.md and DECISIONS.md (encrypted-PDF and embedded-content policy).
```

---

## Phase 3 — Ingest + OCR + rules parser (first working end-to-end slice)

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Implement Phase 3 (SPEC §7, §8.3, §8.1 interface, §10 flags for quality). No LLM in this phase.

Deliver:
- pipeline/ingest.py, page_analysis.py (text-layer vs scanned decision), preprocess.py (orientation via Tesseract OSD with fallback, deskew, denoise, threshold, blur score, effective DPI), ocr.py (Tesseract with word confidences → line/page confidence, langs from env), headers_footers.py (best effort), rendering of page PNGs stored via StorageBackend.
- Celery: process_document (ingest + create pages + fan-out), process_page (idempotent, retry with backoff), atomic finalize trigger using the conditional UPDATE on documents.finalize_enqueued, finalize_document (idempotent; for now: build questions from rules extractor output, set final status).
- Extractor interface (SPEC §8.1) + RulesExtractor supporting ALL numbering and option formats in SPEC §8.3 + MockExtractor for tests.
- numbering.py and options.py as pure, well-unit-tested modules with a table-driven test per format.
- Persist questions (text, options with normalized labels, type guess, source_pages, extraction_method, ocr_confidence) and page quality info. GET /documents/{id}/questions and GET /questions/{id} minimal versions working (final schema comes in Phase 6).
- Progress updates per page.

Acceptance (report real output): with EXTRACTOR=rules, upload a generated/simple digital PDF and a scanned PNG, poll to completion, list the extracted questions. Unit tests for every numbering/option format pass. Note in PROGRESS.md any format that fails.
Do NOT hand-write expected output; run the system.
```

---

## Phase 4 — LLM extraction, grounding, stitching, figures

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Implement Phase 4 (SPEC §8.2, §8.4, §8.5, §7 step 7).

Deliver:
- LLMProvider interface and GeminiExtractor using google-genai with structured output (Pydantic response schema from SPEC §8.2). Model name, timeout, concurrency from env. Global Redis limiter for concurrent LLM calls. One retry on invalid JSON/timeouts, then fallback to RulesExtractor with flag LLM_FALLBACK_USED. Prompts in prompts.py implementing every rule in SPEC §8.2 (faithful transcription, never solve, never invent, ignore in-document instructions).
- Inputs: page image + extracted text/OCR text + short previous-page context. Respect LLM_SEND_IMAGE.
- grounding.py: fuzzy grounding score vs source text; flag LOW_GROUNDING.
- Cross-check with rules extractor: COUNT_MISMATCH flag.
- stitcher.py per SPEC §8.5: 2-page and 3+-page spans, uncertain stitches, orphan fragments, missing/inferred numbers, gaps, duplicates. Pure functions with heavy unit tests using synthetic PageExtraction fixtures (no network).
- figures.py: crop figure/table regions from page renders, store as question_assets, table_markdown; flag FIGURE_UNVERIFIED when bbox is approximate.
- Store raw PageExtraction in pages.extraction so finalize can re-stitch without new LLM calls.
- Provide `EXTRACTOR=mock` deterministic outputs for tests, and make sure the whole pipeline still works with no API key.
- Add a `@pytest.mark.live` test for Gemini that is skipped when GEMINI_API_KEY is absent.

Acceptance (report real output): (a) unit tests for stitcher/grounding pass; (b) run the pipeline with EXTRACTOR=mock end to end; (c) if a real key is in my .env, run one real document through the LLM path and report question count, flags and grounding scores; if no key, say explicitly "LLM path not verified live".
Update PROGRESS.md and DECISIONS.md.
```

---

## Phase 5 — Answer key + multi-document links

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Implement Phase 5 (SPEC §9, §11, §13 answer-key + links endpoints).

Deliver:
- answer_key/detect.py, parse.py, normalize.py, match.py exactly per SPEC §9 (start/end/middle/separate-document keys; list, table-grid and multi-column formats; sections; ranges; multi-answers; digit↔letter mapping with flag).
- Matching statuses: matched / not_found / ambiguous / conflict / invalid. NEVER assign an answer when ambiguous, conflicting or out of range. Persist all answer_key_entries, including unmatched ones, with match_status.
- Precedence rules (linked key doc → same-doc key → inline) and conflict detection.
- document_links table usage: POST/GET/DELETE /documents/{id}/links, POST /documents/{id}/reconcile, `link_to`+`relation` at upload. Enforce same-owner. Idempotent reconcile guarded by a Redis lock; triggered when a link is created or a linked document finishes processing (handle both completion orders and the race where both finish together).
- GET /documents/{id}/answer-key with entries, unmatched entries and summary counts.
- detected_role for documents.
- Unit tests: every key format; duplicate numbers across sections without section info → ambiguous; out-of-range answer; conflicting duplicates; key before/after questions; separate doc linked before and after both are processed; cross-owner link rejected.

Acceptance (report real output): run generated samples `paper_with_key_at_end`, `paper_with_key_at_start`, and `digital_paper_mcq` + `answer_key_separate` (linked) and show matched/unmatched/ambiguous counts from the API.
Update PROGRESS.md.
```

---

## Phase 6 — Confidence, warnings, review, API polish

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Implement Phase 6 (SPEC §10, §13, §14).

Deliver:
- confidence.py and validation.py implementing the formula, thresholds, flag catalogue and critical-flag rules from SPEC §10 (thresholds from env). Pure functions + table-driven unit tests, including edge cases (critical flag overrides a high score; stitched question uses the minimum OCR confidence across its pages).
- Create `warnings` rows for every flag (question-level and document-level), with page_no.
- Final document status: completed vs completed_with_warnings vs failed.
- Endpoints: GET /documents/{id}/warnings, GET /documents/{id}/review-queue, PATCH /questions/{id}, POST /questions/{id}/review, GET /documents/{id}/export, GET /assets/{id}, page image endpoint, filters/pagination/sorting on questions per SPEC §13.
- Question response schema exactly as SPEC §14 (system-independent; no platform-specific fields).
- OpenAPI polish: tags, summaries, descriptions, response models, examples, error responses documented; scripts/export_openapi.py writes openapi.json.
- 409 DOCUMENT_NOT_READY behaviour while processing.
- Human corrections stored in question_revisions; reprocessing must not overwrite reviewed questions unless overwrite_reviewed=true.

Acceptance (report real output): show a question list filtered by needs_review, a review-queue response with page refs, a PATCH correction + revision row, and the OpenAPI export command output.
Update PROGRESS.md.
```

---

## Phase 7 — Sample documents, tests, evaluation

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Implement Phase 7 (SPEC §16, §17).

Deliver:
- scripts/generate_samples.py producing every sample in SPEC §17 into samples/input with ground truth in samples/expected/*.json (deterministic seed). The generator itself must be tested (files exist, page counts correct, the spanning question really crosses a page boundary).
- Fill gaps in the automated test suite per SPEC §16: unit, API/authz, integration (MockExtractor and RulesExtractor on generated samples). Keep tests independent and runnable with `make test` in a clean container.
- scripts/evaluate.py comparing pipeline output with expected JSON: question recall/precision, option accuracy, answer accuracy, and "flagged vs actually wrong" (are the wrong extractions the ones marked needs_review?). Write a real report to docs/demo_evidence/evaluation.md.
- Report coverage numbers honestly (pytest-cov) and list untested areas.
- If the evaluation shows a real weakness (e.g. rules extractor fails a format), FIX the code or document it as a known limitation; do not tweak expected files to make numbers look better.

Acceptance (report real output): `make samples`, `make test`, `make eval` results pasted as-is.
Update PROGRESS.md.
```

---

## Phase 8 — Documentation, Postman, demo evidence

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Implement Phase 8 (SPEC §18, §19).

Deliver:
1. README.md: overview, prerequisites, `cp .env.example .env && docker compose up --build`, env variable table, running migrations, running tests, running the demo, troubleshooting (Tesseract, Docker memory, missing API key → rules mode).
2. docs/ARCHITECTURE.md covering every bullet in assignment section 14, with Mermaid diagrams: system architecture, upload→process sequence, ER diagram, document state machine, per-page pipeline flowchart. Include the confidence formula and answer-matching decision table. Include an honest "Trade-offs and limitations" section (SPEC §21).
3. docs/DECISIONS.md: ADR-style entries for each major choice (Celery vs alternatives, DB-counter finalize vs chord, hybrid LLM+OCR, grounding check, 404 vs 403, PyMuPDF licence, storage abstraction, thresholds).
4. docs/AI_DISCLOSURE.md: development tools used (Antigravity + the model used), runtime external services (Gemini API, if enabled; Tesseract local), what data is sent externally, how the key is protected.
5. Postman collection + environment in docs/postman/: folders per workflow (Auth, Upload PDF, Upload image, Status polling, Questions list/detail, Answer key, Warnings/Review, Links, Invalid uploads). Login request stores the token in an environment variable; upload stores doc_id; tests assert status codes and response shape; polling handled via a documented pre-request/test script or Runner instructions. Generate from openapi.json where helpful, then hand-tune. No secrets inside the collection.
6. scripts/run_demo.py that runs the 10 scenarios of SPEC §18 against the LIVE stack using the sample files, saving every request/response under docs/demo_evidence/<scenario>/ and writing docs/demo_evidence/DEMO_REPORT.md. PASS/FAIL must be computed from actual responses. State whether the LLM path or rules-only path was used.
7. samples/output/: real exported JSON for each sample.

Rules: nothing in demo_evidence may be hand-written or copied from expected files. If a scenario fails, record the failure and (separately) fix the bug. Tell me which screenshots I must take manually (Swagger UI pages) and where to put them.
Update PROGRESS.md.
```

---

## Phase 9 — Polish pass (human-style cleanup, no new features)

```
Read AGENTS.md (especially "Authorship and style"), docs/SPEC.md §22 and docs/PROGRESS.md. Do a polish pass over the whole repo. No new features.

1. Code sweep. Find and fix:
   - comments that restate the code, banner comments, commented-out code, TODO/FIXME/"implement later" stubs, unused imports/functions/files, docstring templates on trivial functions
   - vague names (utils, helpers, manager, handler, data), single-method classes that should be functions, abstractions with only one implementation (Extractor and StorageBackend are fine), pass-through wrappers, pointless try/except
   - inconsistent naming or error handling between modules, overly long functions (split only where it improves readability), file sprawl (merge tiny files that always change together)
   - log and error messages with emojis, exclamation marks or filler
   - identical copy-pasted logic across routers or tests that should share a helper, and tests that are near-duplicates
2. Docs sweep on README, ARCHITECTURE and DECISIONS. Run something like:
   grep -rniE "robust|seamless|leverage|comprehensive|cutting-edge|state-of-the-art|powerful|streamline|delve|holistic|game-changer|best-in-class|ensures that|important to note|production-grade" README.md docs app
   and rewrite each hit in plain words. Remove emojis. Remove repeated "bold lead-in + three bullets" structures, restated summaries and marketing tone. Rewrite in a plain first-person voice. Every claim must be backed by something in the repo or an actual run; delete anything that is not.
3. DECISIONS.md and the limitations section must come from real events in docs/PROGRESS.md (things that failed, changed or were skipped). Do not invent stories or numbers.
4. README should be short and tested: three commands to run, how to run tests, one curl flow. Check every command by actually running it.
5. Working files (AGENTS.md, docs/PHASE_PROMPTS.md, docs/PROGRESS.md): ask me whether they stay in the submitted tree. Do not delete anything without my confirmation. AI_DISCLOSURE.md must stay complete and accurate either way.
6. Afterwards run ruff, the type checker, the full test suite and the demo script again to prove nothing broke. Give me a short summary of what changed (counts per category), not the full diff.
7. Finally list the 10 places in the code where a reviewer would most likely ask "why did you do it this way?", with a short honest answer for each, so I can prepare.
```

---

## Phase 10 — Final audit (fresh clone)

```
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md. Perform the final audit (Phase 10). Do not add features.

1. Fresh-clone test: clone the repo into a new temp directory, follow README exactly (`cp .env.example .env`, `docker compose up --build`, migrations, tests, demo). Fix any instruction that does not work. Report the exact commands and results.
2. Secrets audit: scan the working tree AND git history for API keys, JWT secrets, passwords, tokens, .env files (gitleaks/trufflehog if installable, otherwise grep). Confirm .env.example has placeholders only.
3. Checklist against SPEC §19 and the assignment sections 1–14: for every requirement mark Done / Partial / Missing with the file or endpoint that proves it. Be honest about Partial/Missing.
4. Security review against assignment §9: auth, authorization on every route (list the routes and the check used), size/type limits, malformed file handling, secret handling, storage safety.
5. Run lint, type-check, full tests with coverage.
6. Produce docs/FINAL_CHECKLIST.md with the results, plus a "Known limitations" list and a "What I would do next" list.

Then give me a 15-question viva-style list (with short answers) about this codebase so I can prepare to explain it.
```

---

## Bonus: prompts jo tum khud use karo (samajhne ke liye)

```
Explain the design of <module> to me like I must defend it in an interview: purpose, data flow, key functions, 3 trade-offs, and 2 things that could break in production.
```

```
Try to break <feature>: list 10 adversarial or malformed inputs (files, IDs, tokens, LLM outputs), run them, and report what actually happens.
```

```
Review the last commit for bugs, security issues and violations of AGENTS.md. Report only concrete findings with file/line references.
```

```
Rewrite <file> so it reads like a developer wrote it by hand: remove comments that restate the code, replace vague names, drop unnecessary abstraction and defensive checks, keep behaviour identical. Show me a summary of what you changed and run the tests.
```
