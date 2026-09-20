# Architecture Decision Records (ADRs)

This document records the architectural and design decisions made for the Document Intelligence & Question Extraction Service.

---

## ADR-001: Asynchronous Task Processing with Celery and Redis

### Context
Processing examination PDFs and multi-page scans requires resource-heavy operations: PDF rendering, image deskewing, Tesseract OCR, LLM API calls, and multi-page stitching. FastAPI's built-in `BackgroundTasks` executes in-process on the asyncio threadpool. Under high upload concurrency or CPU-bound OCR workloads, in-process tasks block event loops, risk worker starvation, and do not persist jobs across process restarts.

### Decision
I chose **Celery** with **Redis 7** as the task queue broker and result backend. Tasks are decomposed into three dedicated queues (`ingest`, `pages`, `finalize`) with `task_acks_late=True` and `task_reject_on_worker_lost=True`.

### Alternatives Considered
1. **FastAPI BackgroundTasks**: Simpler to run without separate worker containers, but lacks retries, rate-limiting, persistent queues, distributed execution, and time-limit enforcement.
2. **ARQ / SAQ (asyncio-native queues)**: Lightweight, but Celery provides mature routing, per-task time limits (`task_soft_time_limit`), and separate concurrency pools for CPU-bound OCR tasks.

### Consequences
- **Positive**: Complete decoupling of API and worker compute. Workers can be scaled independently. Upload requests return HTTP 202 in < 20ms.
- **Trade-off**: Requires running Redis and Celery worker processes alongside the API service.

---

## ADR-002: Pluggable Hybrid Extraction with Rules-First Offline Capability

### Context
The service must function in air-gapped or keyless environments (`EXTRACTOR=rules` + local Tesseract) while providing high-accuracy structured extraction when modern multimodal LLMs (`EXTRACTOR=hybrid` or `EXTRACTOR=llm`) are configured.

### Decision
I implemented an abstract `Extractor` interface with two production implementations: `RulesExtractor` and `GeminiExtractor`. When `EXTRACTOR=hybrid`, the pipeline calls `GeminiExtractor` and automatically falls back to `RulesExtractor` if the LLM encounters rate limits (HTTP 429), timeouts, or unparseable output, marking the question with `LLM_FALLBACK_USED`.

### Alternatives Considered
1. **LLM-only pipeline**: Fails completely in offline environments and incurs significant API latency and costs.
2. **Rules-only pipeline**: Free and fast, but struggles with heavily corrupted layouts or non-standard exam typography.

### Consequences
- **Positive**: 100% test suite reliability offline; graceful degradation under external API failure.
- **Trade-off**: Requires maintaining both regex parsers and Pydantic structured output schemas.

---

## ADR-003: LLM Hallucination Prevention via RapidFuzz Fuzzy Grounding

### Context
Generative LLMs may occasionally rephrase, hallucinate, or alter technical question wording when transcribing text from document pages.

### Decision
I implemented a post-extraction grounding verification stage using `rapidfuzz.fuzz.token_set_ratio`. Every question text and option string returned by an LLM is fuzzy-matched against the raw page text layer / OCR tokens. If the grounding score is below `0.60`, the question is flagged with `LOW_GROUNDING`, penalizing its confidence score and notifying human reviewers.

### Alternatives Considered
1. **Exact Substring Matching**: Too strict; fails on trivial OCR noise, whitespace variations, or ligature conversions (e.g., `fi`, `fl`).
2. **Semantic Embedding Similarity**: Too slow and can score hallucinated rephrasings with high similarity even when the original text is absent.

### Consequences
- **Positive**: Fast, deterministic verification with zero external network overhead.
- **Trade-off**: OCR spelling corruptions can occasionally trigger grounding warnings on otherwise valid questions.

---

## ADR-004: Strict Tenant Isolation with 404 Status for Foreign Resource IDs

### Context
In multi-tenant APIs, returning HTTP `403 Forbidden` when a user queries another user's resource ID reveals that the resource exists (ID enumeration / oracle attack).

### Decision
Every database query in the service filters by both resource ID and `owner_id = current_user.id`. If a record exists but belongs to another tenant, the API returns HTTP `404 Not Found` with code `DOCUMENT_NOT_FOUND` or `QUESTION_NOT_FOUND`.

### Alternatives Considered
1. **HTTP 403 Forbidden**: Standard HTTP status, but confirms the existence of private user documents to unauthorized callers.

### Consequences
- **Positive**: Prevents resource enumeration and information disclosure.
- **Trade-off**: Requires developers debugging permissions to check ownership explicitly in database logs.

---

## ADR-005: Answer Extraction Integrity — Never Generate by Solving

### Context
A core project constraint is that answer keys must only be extracted from the document itself (answer key tables, inline answers). An extraction system must never use an LLM to solve the question.

### Decision
The extraction pipeline strictly searches for textual answer markers in the document (`Ans: (B)`, `Answer Key`, `Official Solutions`) and maps them to options. If no answer is present in the document or linked key files, the question answer status is marked as `not_found`. It is never synthesized by generative completion.

### Alternatives Considered
1. **LLM Zero-Shot Answering**: Hallucinates solutions, masks document errors, and violates the evaluation integrity of test extraction systems.

### Consequences
- **Positive**: Ensures complete integrity and transparency of extracted educational materials.
- **Trade-off**: Incomplete documents will have questions marked `not_found`, requiring manual human key entry.

---

## ADR-006: Storage Architecture and Path Traversal Hardening

### Context
Uploaded documents and extracted image assets must be persisted reliably without exposing local file system structures or allowing path traversal attacks via uploaded file names.

### Decision
I designed the `StorageBackend` abstraction (`LocalStorage`) where files are keyed strictly by `f"{owner_id}/{doc_id}"` or `f"{owner_id}/{doc_id}/assets/{asset_id}.png"`. Original filenames are stored as metadata in PostgreSQL and never used as disk filesystem paths.

### Alternatives Considered
1. **Storing files using original uploaded filenames**: Subject to directory traversal (`../../etc/passwd`) and collision bugs.

### Consequences
- **Positive**: Immune to filename-based traversal exploits; naturally shards files by tenant.
