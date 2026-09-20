import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.document import (
    DocumentDetailResponse,
    DocumentExportResponse,
    DocumentListResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    PageListResponse,
)
from app.api.v1.schemas.question import ReviewQueueResponse
from app.api.v1.schemas.warning import WarningListResponse
from app.core.ratelimit import check_rate_limit
from app.core.storage import get_storage
from app.db.models.document import Document
from app.db.models.document_link import DocumentLink
from app.db.models.page import Page
from app.db.models.user import User
from app.db.repositories.document_repo import (
    find_duplicate_document,
    get_document_by_id,
)
from app.db.session import get_db
from app.deps import get_current_user, get_owned_document
from app.errors import DocumentNotReadyException, NotFoundException
from app.services.document_service import (
    build_document_detail_response,
    delete_document_record,
    get_document_status_response,
    list_user_documents,
)
from app.services.review_service import (
    build_document_export_response,
    build_page_quality_list,
    get_document_review_queue,
    get_document_warnings_response,
)
from app.services.upload_service import (
    store_and_enqueue_document,
    stream_and_validate_upload,
)
from app.workers.tasks import process_document

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a new document for asynchronous processing",
)
async def upload_document(
    file: UploadFile = File(...),
    role_hint: str | None = Form(default=None),
    link_to: uuid.UUID | None = Form(default=None),
    relation: str | None = Form(default=None),
    force: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    # 1. Enforce per-user rate limit
    await check_rate_limit(str(current_user.id), action="upload")

    # 2. Stream and validate file (magic bytes, encryption, bomb guard, page limit)
    validation = await stream_and_validate_upload(file)

    # 3. Check deduplication per user
    if not force:
        duplicate = await find_duplicate_document(db, current_user.id, validation.sha256)
        if duplicate:
            return DocumentUploadResponse(
                id=duplicate.id,
                status=duplicate.status,
                links={
                    "status": f"/api/v1/documents/{duplicate.id}/status",
                    "self": f"/api/v1/documents/{duplicate.id}",
                },
            )

    # 4. Create document record
    doc_id = uuid.uuid4()
    storage_key = await store_and_enqueue_document(current_user.id, validation, doc_id)

    new_doc = Document(
        id=doc_id,
        owner_id=current_user.id,
        original_filename=validation.filename,
        storage_key=storage_key,
        mime_type=validation.mime_type,
        size_bytes=validation.size_bytes,
        sha256=validation.sha256,
        page_count=validation.page_count,
        role_hint=role_hint,
        status="queued",
        stage="ingest",
        progress_pct=0,
        pages_done=0,
    )
    db.add(new_doc)

    # 5. Handle initial linking if requested
    if link_to and relation:
        target_doc = await get_document_by_id(db, link_to)
        if not target_doc or (
            current_user.role != "admin" and target_doc.owner_id != current_user.id
        ):
            raise NotFoundException("Target document for relationship link not found")

        doc_link = DocumentLink(
            from_document_id=doc_id,
            to_document_id=link_to,
            relation=relation,
            origin="user",
        )
        db.add(doc_link)

    await db.commit()

    return DocumentUploadResponse(
        id=doc_id,
        status="queued",
        links={
            "status": f"/api/v1/documents/{doc_id}/status",
            "self": f"/api/v1/documents/{doc_id}",
        },
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents owned by the current user",
)
async def list_documents(
    status: str | None = Query(default=None, description="Filter by status"),
    role: str | None = Query(default=None, description="Filter by detected role"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    return await list_user_documents(
        db=db,
        owner_id=current_user.id,
        status=status,
        role=role,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{id}",
    response_model=DocumentDetailResponse,
    summary="Get document details and question summary counts",
)
async def get_document(
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> DocumentDetailResponse:
    return await build_document_detail_response(db, doc)


@router.get(
    "/{id}/status",
    response_model=DocumentStatusResponse,
    summary="Get cheap lightweight processing status and progress",
)
async def get_document_status(
    doc: Document = Depends(get_owned_document),
) -> DocumentStatusResponse:
    return await get_document_status_response(doc)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and all derived assets and records",
)
async def delete_document(
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await delete_document_record(db, doc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{id}/reprocess",
    response_model=DocumentStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger reprocessing of document pipeline",
)
async def reprocess_document(
    overwrite_reviewed: bool = Query(
        default=False,
        description="Whether to overwrite human reviewed questions during reprocessing",
    ),
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> DocumentStatusResponse:
    """Re-enqueues document processing. Respects reviewed questions if overwrite is False."""
    doc.status = "queued"
    doc.stage = "ingest"
    doc.progress_pct = 0
    doc.finalize_enqueued = False
    doc.error_code = None
    doc.error_message = None
    await db.commit()

    # Pass reprocess options through Celery task
    process_document.delay(str(doc.id))

    return await get_document_status_response(doc)


@router.get(
    "/{id}/pages",
    response_model=PageListResponse,
    summary="Get list of pages with OCR quality info and flags",
)
async def get_document_pages(
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> PageListResponse:
    items = await build_page_quality_list(db, doc.id)
    return PageListResponse(items=items, total=len(items))


@router.get(
    "/{id}/pages/{page_no}/image",
    summary="Stream rendered page image for reviewers",
)
async def get_page_image(
    page_no: int,
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    query = select(Page).where(Page.document_id == doc.id, Page.page_no == page_no)
    result = await db.execute(query)
    page = result.scalar_one_or_none()

    if not page or not page.image_key:
        raise NotFoundException(f"Rendered image for page {page_no} is not available")

    storage = get_storage()
    stream = storage.get_stream(page.image_key)
    return StreamingResponse(stream, media_type="image/png")


@router.get(
    "/{id}/warnings",
    response_model=WarningListResponse,
    summary="List extraction and quality warnings for a document",
)
async def get_document_warnings(
    severity: str | None = Query(None, description="Filter by severity: info, warning, critical"),
    code: str | None = Query(None, description="Filter by flag code"),
    resolved: bool | None = Query(None, description="Filter by resolved status"),
    question_id: uuid.UUID | None = Query(None, description="Filter by question id"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> WarningListResponse:
    if doc.status in ("queued", "processing"):
        raise DocumentNotReadyException(
            message=f"Document {doc.id} is still processing",
            details={"status": doc.status, "stage": doc.stage, "progress_pct": doc.progress_pct},
        )

    return await get_document_warnings_response(
        db=db,
        doc_id=doc.id,
        severity=severity,
        code=code,
        resolved=resolved,
        question_id=question_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{id}/review-queue",
    response_model=ReviewQueueResponse,
    summary="Get questions requiring human review ordered by lowest confidence",
)
async def get_document_review_queue_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueResponse:
    if doc.status in ("queued", "processing"):
        raise DocumentNotReadyException(
            message=f"Document {doc.id} is still processing",
            details={"status": doc.status, "stage": doc.stage, "progress_pct": doc.progress_pct},
        )

    return await get_document_review_queue(
        db=db, doc_id=doc.id, limit=limit, offset=offset
    )


@router.get(
    "/{id}/export",
    response_model=DocumentExportResponse,
    summary="Export full structured JSON with questions, answers, and warnings",
)
async def export_document(
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> DocumentExportResponse:
    if doc.status in ("queued", "processing"):
        raise DocumentNotReadyException(
            message=f"Document {doc.id} is still processing",
            details={"status": doc.status, "stage": doc.stage, "progress_pct": doc.progress_pct},
        )

    return await build_document_export_response(db, doc)
