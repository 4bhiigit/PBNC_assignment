import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from redis.asyncio import from_url as async_redis_from_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.link import DocumentLinkResponse, ReconcileResponse
from app.config import get_settings
from app.db.models.answer_key import AnswerKeyEntry
from app.db.models.question import Question
from app.db.repositories.document_repo import get_document_by_id_and_owner
from app.db.repositories.link_repository import (
    create_document_link,
    find_link,
    get_link_by_id,
    get_links_for_document,
)
from app.errors import ConflictException, NotFoundException, ValidationException
from app.pipeline.answer_key.match import match_question_answers

logger = logging.getLogger(__name__)

# Fallback in-memory lock for testing environments without Redis
_MEMORY_LOCKS: dict[str, asyncio.Lock] = {}


@asynccontextmanager
async def acquire_reconcile_lock(document_id: uuid.UUID) -> AsyncIterator[bool]:
    """Distributed lock for reconcile workflow using Redis with fallback to in-memory lock."""
    settings = get_settings()
    lock_key = f"lock:reconcile:{document_id}"
    token = str(uuid.uuid4())
    redis_client = None

    try:
        redis_client = async_redis_from_url(
            settings.redis_url, socket_timeout=2.0, socket_connect_timeout=2.0
        )
        # Attempt to acquire Redis lock with 15 second TTL
        acquired = await redis_client.set(lock_key, token, nx=True, ex=15)
        if not acquired:
            logger.warning("Reconcile lock already held for document %s", document_id)
            yield False
            return
        try:
            yield True
        finally:
            # Release Redis lock safely if token matches
            val = await redis_client.get(lock_key)
            if val and val.decode() == token:
                await redis_client.delete(lock_key)
    except Exception as exc:
        logger.debug("Redis lock unavailable (%s); using in-memory lock fallback", exc)
        if lock_key not in _MEMORY_LOCKS:
            _MEMORY_LOCKS[lock_key] = asyncio.Lock()
        async with _MEMORY_LOCKS[lock_key]:
            yield True
    finally:
        if redis_client:
            await redis_client.aclose()


async def add_document_link(
    db: AsyncSession,
    from_document_id: uuid.UUID,
    to_document_id: uuid.UUID,
    relation: str,
    owner_id: uuid.UUID,
    origin: str = "user",
) -> DocumentLinkResponse:
    """Creates a link between two documents owned by the same user.

    Strictly enforces tenant isolation: foreign documents return 404.
    """
    if from_document_id == to_document_id:
        raise ValidationException("Cannot link a document to itself")

    # Validate that both documents exist and belong to the same owner
    from_doc = await get_document_by_id_and_owner(db, from_document_id, owner_id)
    if not from_doc:
        raise NotFoundException(f"Document {from_document_id} not found")

    to_doc = await get_document_by_id_and_owner(db, to_document_id, owner_id)
    if not to_doc:
        raise NotFoundException(f"Document {to_document_id} not found")

    # Check for existing link
    existing = await find_link(db, from_document_id, to_document_id, relation)
    if existing:
        return DocumentLinkResponse.model_validate(existing)

    link = await create_document_link(
        db,
        from_id=from_document_id,
        to_id=to_document_id,
        relation=relation,
        origin=origin,
    )
    await db.commit()
    await db.refresh(link)

    # If relation is answer_key_for, trigger reconciliation on the question paper document
    if relation == "answer_key_for":
        # Identify which is the question doc and reconcile it
        is_key = from_doc.detected_role == "answer_key"
        target_doc_id = to_document_id if is_key else from_document_id
        try:
            await reconcile_document_answers(db, target_doc_id, owner_id)
        except Exception as exc:
            logger.warning("Auto-reconcile after link creation skipped or failed: %s", exc)

    return DocumentLinkResponse.model_validate(link)


async def list_document_links(
    db: AsyncSession,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Sequence[DocumentLinkResponse]:
    """Lists all links for a given document."""
    doc = await get_document_by_id_and_owner(db, document_id, owner_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")

    links = await get_links_for_document(db, document_id)
    return [DocumentLinkResponse.model_validate(lnk) for lnk in links]


async def remove_document_link(
    db: AsyncSession,
    document_id: uuid.UUID,
    link_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> None:
    """Deletes a link belonging to the user's document."""
    doc = await get_document_by_id_and_owner(db, document_id, owner_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")

    link = await get_link_by_id(db, link_id)
    if not link:
        raise NotFoundException(f"Link {link_id} not found")

    if link.from_document_id != document_id and link.to_document_id != document_id:
        raise NotFoundException(f"Link {link_id} not found for document {document_id}")

    await db.delete(link)
    await db.commit()


async def reconcile_document_answers(
    db: AsyncSession,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> ReconcileResponse:
    """Re-matches document questions against linked answer keys with Redis distributed lock."""
    doc = await get_document_by_id_and_owner(db, document_id, owner_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")

    async with acquire_reconcile_lock(document_id) as lock_acquired:
        if not lock_acquired:
            raise ConflictException("Document is currently being reconciled")

        # Find linked documents that are answer keys for this document
        links = await get_links_for_document(db, document_id)
        linked_doc_ids: set[uuid.UUID] = set()

        for lnk in links:
            if lnk.relation == "answer_key_for":
                if lnk.to_document_id == document_id:
                    linked_doc_ids.add(lnk.from_document_id)
                elif lnk.from_document_id == document_id:
                    linked_doc_ids.add(lnk.to_document_id)

        # Load linked answer key entries
        linked_entries_query = select(AnswerKeyEntry).where(
            AnswerKeyEntry.document_id.in_(linked_doc_ids)
        )
        linked_entries = (await db.execute(linked_entries_query)).scalars().all()
        linked_entries_dicts = [
            {
                "id": e.id,
                "document_id": e.document_id,
                "page_no": e.page_no,
                "section": e.section,
                "number_norm": e.number_norm,
                "answer_raw": e.answer_raw,
                "answer_value": e.answer_value,
                "parse_confidence": e.parse_confidence,
            }
            for e in linked_entries
        ]

        # Load same-document answer key entries
        same_doc_query = select(AnswerKeyEntry).where(AnswerKeyEntry.document_id == document_id)
        same_doc_entries = (await db.execute(same_doc_query)).scalars().all()
        same_doc_entries_dicts = [
            {
                "id": e.id,
                "document_id": e.document_id,
                "page_no": e.page_no,
                "section": e.section,
                "number_norm": e.number_norm,
                "answer_raw": e.answer_raw,
                "answer_value": e.answer_value,
                "parse_confidence": e.parse_confidence,
            }
            for e in same_doc_entries
        ]

        # Load questions for this document
        questions_query = (
            select(Question)
            .where(Question.document_id == document_id)
            .order_by(Question.sequence.asc())
        )
        questions = (await db.execute(questions_query)).scalars().all()
        questions_dicts = [
            {
                "id": q.id,
                "number_norm": q.number_norm,
                "section": q.section,
                "options": q.options,
                "inline_answer_raw": (
                    q.answer_raw if q.answer_source.get("kind") == "inline" else None
                ),
                "source_pages": q.source_pages,
            }
            for q in questions
        ]

        # Run pure matching algorithm
        match_results, entry_statuses = match_question_answers(
            questions=questions_dicts,
            document_id=document_id,
            same_doc_entries=same_doc_entries_dicts,
            linked_doc_entries=linked_entries_dicts,
        )

        # Update questions in DB
        result_map = {r.question_id: r for r in match_results}
        matched_count = 0

        for q in questions:
            res = result_map.get(q.id)
            if not res:
                continue

            q.answer_status = res.answer_status
            q.answer_value = res.answer_value
            q.answer_raw = res.answer_raw
            q.answer_source = res.answer_source
            q.answer_confidence = res.answer_confidence

            if res.answer_status == "matched":
                matched_count += 1

            # Update flags
            existing_codes = {f.get("code") for f in (q.flags or []) if isinstance(f, dict)}
            for flg in res.flags_to_add:
                if flg not in existing_codes:
                    sev = "critical" if flg == "ANSWER_OUT_OF_RANGE" else "warning"
                    q.flags.append({"code": flg, "severity": sev, "message": f"Answer flag: {flg}"})

        # Update answer key entry statuses
        all_key_entries = list(same_doc_entries) + list(linked_entries)
        for e in all_key_entries:
            if e.id in entry_statuses:
                e.match_status = entry_statuses[e.id]

        await db.commit()

        return ReconcileResponse(
            document_id=document_id,
            status="completed",
            questions_matched=matched_count,
            questions_total=len(questions),
        )
