# Architecture Decision Records (ADR)

This document records the architectural and design decisions made during the development of the Document Intelligence & Question Extraction Service.

---

## ADR 1: Asynchronous Processing and Return Code

- **Status:** Accepted
- **Context:** Extracting structure, text, and answer keys from multi-page PDFs involves heavy OCR and AI inference that can take seconds to minutes. Synchronous HTTP responses would timeout client connections and tie up API server threads.
- **Decision:** All document submissions (`POST /api/v1/documents`) return `HTTP 202 Accepted` immediately with a JSON body containing `{id, status: "queued", links: {"status": ..., "self": ...}}`. Processing is delegated to Celery background workers.
- **Alternatives Considered:**
  - Synchronous execution: Rejected because exam papers up to 150 pages exceed any standard HTTP proxy timeout.
  - Webhook-only notification: Rejected because polling `/documents/{id}/status` provides a simple client experience without requiring client-side webhook infrastructure.
- **Consequences:** Clients poll `/status` or query final questions when status becomes `completed`. The API remains fast and horizontally scalable.

---

## ADR 2: Tenant Isolation and Foreign Resource Status Code (404 vs 403)

- **Status:** Accepted
- **Context:** The system is multi-tenant. A user must never observe or infer documents, questions, or assets uploaded by another user.
- **Decision:** Any request for an existing resource ID belonging to a different user returns `HTTP 404 Not Found`, identical to requesting a completely non-existent UUID.
- **Alternatives Considered:**
  - `HTTP 403 Forbidden`: Rejected because returning 403 reveals to an attacker that a UUID exists in the system (information leakage via enumeration).
- **Consequences:** All document-scoped routes use the shared dependency `get_owned_document()`. Administrative users with `role="admin"` are exempt and may inspect any document.

---

## ADR 3: Encrypted PDF and Embedded Content Handling

- **Status:** Accepted
- **Context:** Exam PDFs may occasionally be password-protected or contain embedded JavaScript, forms, or executable attachments.
- **Decision:**
  1. Encrypted PDFs are rejected immediately at upload validation with code `PDF_ENCRYPTED` (HTTP 422). The service does not attempt brute-force decryption or accept password parameters in the upload API.
  2. Embedded executable files or JS attachments in PDFs are ignored and never executed. Rasterization and text extraction operate strictly on visual page content via PyMuPDF rendering and Tesseract OCR.
- **Alternatives Considered:**
  - Accepting user passwords: Out of scope for this round; increases attack surface and key storage complexity.
- **Consequences:** Malicious or locked documents are stopped at the perimeter before entering the worker queues.

---

## ADR 4: Storage Abstraction and Owner-Sharded Local Storage

- **Status:** Accepted
- **Context:** Documents, rendered page images, and cropped figures must be stored securely and retrieved quickly by authenticated API endpoints without public directory exposure.
- **Decision:** Storage is accessed via the `StorageBackend` interface. The default implementation is `LocalStorage` on a mounted Docker volume. Storage keys follow `{owner_id}/{doc_id}.{ext}`. Path traversal is prevented by strictly asserting that resolved paths remain within the configured storage directory.
- **Alternatives Considered:**
  - Direct database BLOB storage: Rejected because large PDFs and high-DPI page renders degrade database performance.
  - S3 / MinIO only: Supported as an alternative backend, but local disk volume is the default to avoid unnecessary runtime dependencies on single-host deployments.
- **Consequences:** Storage is modular, safe against path traversal, and easily swappable with MinIO/S3 in clustered environments.
