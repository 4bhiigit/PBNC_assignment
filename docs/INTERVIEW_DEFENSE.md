# Technical Defense & Architecture Viva Notes

This document provides concise, concrete answers to 10 key architectural questions about the Document Intelligence & Question Extraction Service.

---

### 1. Why use an asynchronous job queue (Celery + Redis) instead of processing uploads synchronously in FastAPI?

**Answer:**
Examination papers typically range from 5 to 50+ pages. Rendering high-DPI page images, performing image deskew/denoise, running Tesseract OCR, executing LLM extraction calls with structured output validation, and fuzzy grounding matching takes between 1.5 to 15 seconds per page.
If handled synchronously in the HTTP request:
1. Web clients and reverse proxies (like Nginx, Cloudflare, or browser timeouts) would drop HTTP connections after 30–60 seconds.
2. FastAPI worker threads would become saturated, blocking concurrent user requests and health checks.
3. Server failures or restarts midway through processing would lose the entire document state without retry capabilities.

With Celery and Redis:
- The `POST /api/v1/documents` endpoint streams the upload, sniffs magic bytes, writes raw bytes to owner-sharded storage, enqueues an ingest task, and returns `HTTP 202 Accepted` in <50ms.
- Celery splits the document into independent page tasks (`process_page`), running in parallel across worker processes.
- An atomic conditional database latch (`finalize_enqueued=True`) triggers the `finalize_document` task once all pages finish, ensuring clean completion and idempotency.

---

### 2. How is multi-tenant isolation enforced, and why return 404 instead of 403 on foreign resource IDs?

**Answer:**
Every table (`documents`, `pages`, `questions`, `document_links`, `warnings`, `question_revisions`) has an `owner_id` (UUID foreign key referencing `users.id`) or is foreign-key linked to a document owned by the user.
In API dependencies and service queries:
1. All queries filter explicitly by `owner_id == current_user.id`.
2. If a user attempts to request `/api/v1/documents/{foreign_uuid}` or `/api/v1/questions/{foreign_uuid}`, the query returns `None`, and the API raises `HTTP 404 Not Found` with error code `DOCUMENT_NOT_FOUND` or `QUESTION_NOT_FOUND`.

**Why 404 over 403:**
Returning `HTTP 403 Forbidden` leaks information: it confirms to an attacker that the targeted UUID exists in the system. Returning `HTTP 404 Not Found` makes foreign resources completely indistinguishable from non-existent UUIDs, preventing ID enumeration and reconnaissance attacks.

---

### 3. How does the system extract questions across page boundaries (cross-page stitching)?

**Answer:**
Page-level extractors work on single page images/text and output a stream of `ExtractedItem` candidates. Often, a question starts on page $N$ (e.g. question prompt and options A and B) and finishes on page $N+1$ (options C and D, or explanatory text).
The `stitch_document_extractions` pipeline:
1. Identifies continuation cues:
   - Trailing items on page $N$ marked `continues_on_next_page=True` (e.g. incomplete option list, incomplete sentence ending without punctuation, or question prompt without options).
   - Leading items on page $N+1$ that lack a question number (`number_raw == None`) or start with continuation option labels (e.g. `(C)`, `(c)`, `(iii)`).
2. Merges text fragments, removing artificial page-break line breaks and de-hyphenating split words (e.g., `tem-` at page bottom + `perature` at page top becomes `temperature`).
3. Appends remaining options and merges source page references into a sorted unique list (e.g., `source_pages=[1, 2]`).
4. Tags stitched questions with the `CROSS_PAGE_STITCHED` quality flag so reviewers know the item crossed a page boundary.

---

### 4. How does the system handle answer keys without hallucinating answers?

**Answer:**
Per core integrity constraints, the service **never generates answers by solving questions**. Answers must come strictly from the document:
1. **Inline Answers**: Parsed directly from the question block (e.g., `Ans: (b)` or `Correct Option: C`).
2. **Embedded Answer Keys**: Detected on answer key pages within the same document (e.g., `1-A 2-C 3-D` or grid tables) via `parse_answer_key_text`.
3. **Linked Answer Key Documents**: Linked via `POST /api/v1/documents/{id}/links` with `relation="answer_key_for"`.

The matching engine reconciles numbers and sections:
- If an exact single matching option label exists $\rightarrow$ `status="matched"`.
- If no answer is present in document or linked key $\rightarrow$ `status="not_found"`.
- If multiple conflicting answers exist between inline and answer key $\rightarrow$ `status="conflict"`.
- If an answer key references a question number not present in the question paper $\rightarrow$ `status="invalid"` and flagged.

---

### 5. What is the confidence score formula and how are the weights justified?

**Answer:**
Confidence is calculated per question using four orthogonal metrics:
$$\text{Confidence} = 0.30 \cdot S_{\text{ocr}} + 0.35 \cdot S_{\text{grounding}} + 0.20 \cdot S_{\text{sequence}} + 0.15 \cdot S_{\text{model}}$$

1. **OCR Quality ($S_{\text{ocr}}$, 30%)**: Average word-level confidence from Tesseract (1.0 for digital text layer). If the OCR is garbled, downstream extraction is suspect.
2. **Grounding Score ($S_{\text{grounding}}$, 35%)**: Token-set fuzzy matching ratio between the extracted question/option text and the raw source text using RapidFuzz. This directly catches LLM hallucinations or text alterations.
3. **Sequence Consistency ($S_{\text{sequence}}$, 20%)**: Checks whether the question number follows monotonically from previous questions within the section ($N = N_{\text{prev}} + 1$). Catches missed questions or duplicate numbering.
4. **Model/Parser Confidence ($S_{\text{model}}$, 15%)**: Self-reported probability from the extractor (or 1.0 for clean deterministic regex rule matches).

Questions with confidence $\ge 0.85$ and no critical flags are marked `extracted`. Questions with confidence $< 0.85$ or any critical flag (e.g., `DUPLICATE_NUMBER`, `COUNT_MISMATCH`, `MISSING_OPTIONS`) are routed to `needs_review`.

---

### 6. Why use RapidFuzz fuzzy token grounding rather than exact substring search?

**Answer:**
Exact substring matching fails frequently on real OCR output due to:
- Minor character misrecognitions (e.g., `O` vs `0`, `l` vs `1`, `rn` vs `m`).
- Whitespace variations (multiple spaces, tabs, line breaks introduced by two-column layouts).
- Punctuation differences (smart quotes `”` vs standard `"`, em-dash vs hyphen).

RapidFuzz's `token_set_ratio` decomposes text into normalized token sets and measures overlap. It tolerates word reordering due to multi-column OCR while heavily penalizing hallucinated words or substituted scientific values.

---

### 7. How does the system function without an external AI key (Offline-First)?

**Answer:**
The service defines an `Extractor` abstraction with three concrete implementations:
1. `RulesExtractor`: 100% offline, deterministic regex state machine. Parses Roman numerals, bracketed numbers, alphabetic options, tabular grids, and section headers without network calls or GPU.
2. `GeminiExtractor`: Calls Google Gemini (`gemini-3.6-flash`) with structured JSON schema output and multimodal image input.
3. `MockExtractor`: Deterministic fixture for fast unit testing.

Under `EXTRACTOR=rules`, the entire pipeline runs locally with PyMuPDF and Tesseract. In `EXTRACTOR=hybrid`, the system attempts Gemini first; if a timeout, rate limit (HTTP 429), or network error occurs, it falls back to `RulesExtractor` and attaches the `LLM_FALLBACK_USED` flag.

---

### 8. What is the Human Review & Audit Trail mechanism?

**Answer:**
When an educator or reviewer inspects a flagged question via `GET /api/v1/documents/{id}/review-queue`:
1. They can edit fields via `PATCH /api/v1/questions/{id}` (e.g. fixing text, adding a missing option, or changing the section).
2. The service takes a snapshot of the current state and writes an immutable record to `question_revisions` containing `(question_id, revision_no, changed_by, snapshot, created_at)`.
3. The question is then approved or rejected via `POST /api/v1/questions/{id}/review` with action notes.
4. All revisions remain queryable and exportable, guaranteeing regulatory compliance and traceability.

---

### 9. How are security risks (malicious uploads, zip bombs, prompt injections) mitigated?

**Answer:**
1. **Magic-Byte Sniffing**: Uses `puremagic` to verify file headers. An executable `.exe` renamed to `.pdf` is rejected with `INVALID_FILE_TYPE`.
2. **Decompression Bomb Defense**: Configures Pillow `MAX_IMAGE_PIXELS = 89_478_485` and validates PDF decompression limits before rasterization.
3. **Encrypted File Rejection**: Checks PyMuPDF `doc.is_encrypted` and rejects with `FILE_ENCRYPTED`.
4. **Prompt Injection Mitigation**: Document text is treated as untrusted data. When calling LLMs, user document content is placed exclusively in a delimited user content block, never inside system instructions. LLM responses are strictly validated against a Pydantic schema; free-form instructions embedded in examination questions cannot alter pipeline execution.

---

### 10. How does the system ensure idempotent task execution in Celery?

**Answer:**
Celery workers may retry tasks upon worker crashes or network interruptions. If tasks are not idempotent, questions could be duplicated or answer keys double-counted.
Idempotency is achieved by:
1. **Delete-and-Reinsert per Stage**:
   - `process_document`: Clears existing `pages` for the document before re-inserting.
   - `finalize_document`: Clears existing `questions`, `answer_keys`, and `warnings` for the document before re-inserting stitched questions and parsed keys.
2. **Atomic Finalization Latch**: `process_page` uses a conditional SQL update (`UPDATE documents SET finalize_enqueued = TRUE WHERE id = :id AND finalize_enqueued = FALSE`) so that `finalize_document` is triggered exactly once when the last page completes.
