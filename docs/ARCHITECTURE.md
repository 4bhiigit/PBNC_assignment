# Architecture & System Design

This document details the design and internal mechanisms of the **Document Intelligence & Question Extraction Service**.

---

## 1. High-Level System Overview

The service processes examination papers and assessments (digital PDFs, scanned PDFs, single/multi-page images) into structured, question-level JSON schemas. It runs as an asynchronous pipeline with distinct web, background worker, database, and storage layers.

```mermaid
flowchart TD
    Client["HTTP Client / Frontend"] -->|REST API Requests| API["FastAPI Application"]
    API -->|JWT & Security Auth| Auth["Security & Auth Middleware"]
    API -->|Metadata / DB Ops| Postgres[(PostgreSQL 16)]
    API -->|Raw Document Streams| Storage["StorageBackend (LocalStorage)"]
    API -->|Enqueue Ingest Task| RedisQueue[(Redis 7 Broker)]

    subgraph Celery Workers
        Worker["Celery Worker Pool"]
        Worker -->|Ingest & Split| IngestStage["Ingest & Preprocessing"]
        IngestStage -->|Page Tasks| PageStage["Page Extraction (OCR / Rules / Gemini)"]
        PageStage -->|Finalize Task| FinStage["Stitching, Validation & Scoring"]
    end

    RedisQueue --> Worker
    Worker -->|Read Raw Assets| Storage
    Worker -->|Write Extracted Records & Assets| Postgres
    Worker -->|Publish Progress Events| Postgres
```

---

## 2. Component Architecture

### 2.1 API Layer (`app/api/v1/`)
- **FastAPI**: Asynchronous route handlers for document uploads, question queries, answer key management, document link reconciliation, and human review workflows.
- **Strict Owner Isolation**: Every query filters by `owner_id = current_user.id`. Foreign resource IDs return `404 Not Found` rather than `403 Forbidden` to eliminate ID enumeration vulnerabilities.
- **Immediate Response**: Document uploads stream to disk/storage, compute SHA-256 hashes, validate magic bytes, create the database record with status `queued`, enqueue a Celery task, and immediately respond with HTTP `202 Accepted`.
- **409 Conflict Protection**: Attempts to fetch extracted questions or export schemas while processing is ongoing return `409 DOCUMENT_NOT_READY`.

### 2.2 Worker Pipeline (`app/pipeline/` & `app/workers/`)
The processing pipeline executes across three ordered stages:

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI Router
    participant DB as PostgreSQL
    participant Redis as Redis Broker
    participant Celery as Celery Worker
    participant Ext as Extractor (Rules / Gemini)

    User->>API: POST /api/v1/documents (multipart/form-data)
    API->>API: Magic byte & extension validation
    API->>DB: INSERT Document (status=queued, stage=ingest)
    API->>Redis: enqueue process_document(document_id)
    API-->>User: HTTP 202 Accepted (id, status=queued)

    Redis->>Celery: process_document
    Celery->>DB: UPDATE Document (status=processing, stage=ingest)
    Celery->>Celery: Render page images, detect DPI, blur, orientation
    Celery->>DB: INSERT Pages (page_no, width, height, text_source)
    loop For each page
        Celery->>Redis: enqueue process_page(document_id, page_no)
    end

    loop Page Worker Execution
        Redis->>Celery: process_page
        Celery->>Ext: extract_page(PageContext)
        Ext-->>Celery: PageExtraction(items, answer_keys)
        Celery->>DB: Record processing event & page metrics
    end

    Celery->>Redis: enqueue finalize_document(document_id)
    Redis->>Celery: finalize_document
    Celery->>Celery: Stitch multi-page questions (join_stitched_text, heuristics)
    Celery->>Celery: Deduplicate headers, footers & crop figures
    Celery->>Celery: Match answer keys (embedded, separate, inline)
    Celery->>Celery: Compute confidence scores & quality flags
    Celery->>DB: INSERT Questions, Options, Assets, Warnings
    Celery->>DB: UPDATE Document (status=completed, stage=finalize, progress_pct=100)
```

---

## 3. Extraction Engines

The system implements a pluggable `Extractor` interface with two primary implementations:

1. **`RulesExtractor` (`app/pipeline/extractors/rules.py`)**:
   - Operates 100% locally and offline without external API dependencies.
   - Utilizes deterministic regular expressions for numbered lists (`1.`, `(1)`, `Q.1`, `[1]`, roman numerals, Hindi numerals).
   - Detects multi-column and inline option patterns (`(A)`, `(B)`, `(C)`, `(D)`).
   - Detects inline answer markers (`Ans: (b)`, `Answer - A`).

2. **`GeminiExtractor` (`app/pipeline/extractors/gemini.py`)**:
   - Uses `google-genai` SDK with strict Pydantic structured output models (`PageExtractionModel`).
   - Grounding validation: Runs fuzzy matching via `rapidfuzz` against the raw OCR/text layer. If grounding score falls below 0.60, questions are flagged with `LOW_GROUNDING`.
   - Fallback protection: If Gemini returns 429 quota exhaustion or network timeout, the pipeline falls back to `RulesExtractor` and attaches the `LLM_FALLBACK_USED` flag.

---

## 4. Multi-Page Question Stitching

Exam questions frequently break across page boundaries (e.g., question text and options A/B on page 1, options C/D on page 2).

```mermaid
stateDiagram-v2
    [*] --> StartPage
    StartPage --> CheckFirstItem: Top of Page
    CheckFirstItem --> LeadingFragment: Starts on previous page / No number / Option continuation
    LeadingFragment --> MergePendingQuestion: Active pending question in buffer
    MergePendingQuestion --> AppendOptionsAndText: De-hyphenate text & merge options (A..D)
    LeadingFragment --> OrphanFragment: No active question in buffer
    OrphanFragment --> FlagOrphan: Flag ORPHAN_FRAGMENT
    CheckFirstItem --> NormalQuestion: Has question number
    NormalQuestion --> BufferQuestion: Store in buffer
    BufferQuestion --> CheckTrailingItem: Bottom of Page
    CheckTrailingItem --> IncompleteMCQ: Has 1-3 options or unfinished punctuation
    IncompleteMCQ --> MarkContinuesNextPage: Set CONTINUES_NEXT_PAGE
    CheckTrailingItem --> CompleteQuestion: Normal termination
    CompleteQuestion --> OutputQuestion: Commit to result list
```

### De-hyphenation & Stitching Rules
- **Text Merging**: When `text_a` ends with a trailing hyphen (`"elec-"`) and `text_b` starts with letters (`"tricity"`), `join_stitched_text` removes the hyphen to restore `"electricity"`.
- **Option Merging**: Continuation options on following pages are normalized into sequential labels (`A`, `B`, `C`, `D`) without duplicating letters.
- **Confidence Propagation**: Stitched questions take the minimum OCR confidence across all source pages.

---

## 5. Answer Key Detection & Multi-Document Reconciliation

### 5.1 Embedded Answer Keys
If an answer key table appears at the start or end of a question paper (e.g. `paper_with_key_at_end.pdf`), the parser extracts question-answer pairs and reconciles them during finalization.

### 5.2 Standalone Answer Key Documents (`document_links`)
When answer keys are uploaded as separate PDF documents:
1. User creates a link via `POST /api/v1/documents/{id}/links` with `link_type="answer_key_for"`.
2. Reconciliation worker fetches questions from the question paper and keys from the answer document.
3. Matching assigns status:
   - `matched`: Exactly one valid option matches the key.
   - `ambiguous`: Key maps to multiple candidate options.
   - `conflict`: Inline document answer disagrees with separate answer key.
   - `not_found`: Question has no matching key in the key document.
   - `invalid`: Key references an option letter not present in the question (e.g., key says `Z` for 4-option MCQ).

---

## 6. Confidence Scoring Engine & Quality Flag Catalog

Question confidence scores are computed mathematically per SPEC §10:

$$\text{Confidence} = 0.40 \cdot C_{\text{ocr}} + 0.30 \cdot C_{\text{grounding}} + 0.20 \cdot C_{\text{seq}} + 0.10 \cdot C_{\text{llm}} - \sum \text{Penalties}$$

### Quality Flags and Severity:
- **Critical Flags** (forces status to `needs_review` regardless of numeric score):
  - `OCR_LOW_CONFIDENCE`, `MISSING_NUMBER`, `DUPLICATE_NUMBER`, `MCQ_OPTIONS_LT_2`, `ANSWER_KEY_CONFLICT`, `UNGROUNDED_EXTRACTION`.
- **Warning Flags** (deducts 0.05 to 0.15 confidence):
  - `CROSS_PAGE_STITCHED`, `STITCH_UNCERTAIN`, `SEQUENCE_GAP`, `ORPHAN_FRAGMENT`, `BLURRY_IMAGE`, `IMAGE_ROTATED`, `IMAGE_SKEWED`.

---

## 7. Human Review & Audit Trail

```mermaid
flowchart LR
    Queued["Status: queued"] --> Processing["Status: processing"]
    Processing --> Extracted["Status: extracted"]
    Processing --> NeedsReview["Status: needs_review"]

    NeedsReview -->|PATCH /questions/{id}| Edited["Status: edited"]
    NeedsReview -->|POST /questions/{id}/review (accept)| Approved["Status: approved"]
    NeedsReview -->|POST /questions/{id}/review (reject)| Rejected["Status: rejected"]
    Edited --> Approved

    subgraph Audit Trail
        Edited -.->|Snapshot before & after| Revisions[(question_revisions)]
    end
```

Every modification through `PATCH /api/v1/questions/{id}` captures:
- Revision number increment.
- Full `previous_state` snapshot JSON.
- Full `new_state` snapshot JSON.
- User ID and UTC timestamp.
