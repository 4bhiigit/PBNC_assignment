import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.link import (
    CreateLinkRequest,
    DocumentLinkResponse,
    ReconcileResponse,
)
from app.db.models.user import User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.link_service import (
    add_document_link,
    list_document_links,
    reconcile_document_answers,
    remove_document_link,
)

router = APIRouter(tags=["links"])


@router.post(
    "/documents/{document_id}/links",
    response_model=DocumentLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a link between documents",
    description="Creates a directed link between documents belonging to the authenticated user.",
)
async def create_link(
    document_id: uuid.UUID,
    payload: CreateLinkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentLinkResponse:
    return await add_document_link(
        db=db,
        from_document_id=document_id,
        to_document_id=payload.to_document_id,
        relation=payload.relation,
        owner_id=user.id,
    )


@router.get(
    "/documents/{document_id}/links",
    response_model=list[DocumentLinkResponse],
    summary="List links for a document",
    description="Returns all active relationships involving this document.",
)
async def list_links(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Sequence[DocumentLinkResponse]:
    return await list_document_links(db=db, document_id=document_id, owner_id=user.id)


@router.delete(
    "/documents/{document_id}/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a link between documents",
    description="Deletes a document link belonging to the user's document.",
)
async def delete_link(
    document_id: uuid.UUID,
    link_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await remove_document_link(
        db=db,
        document_id=document_id,
        link_id=link_id,
        owner_id=user.id,
    )


@router.post(
    "/documents/{document_id}/reconcile",
    response_model=ReconcileResponse,
    summary="Reconcile questions with linked answer keys",
    description=(
        "Re-runs answer matching using linked answer keys and same-doc " "keys under a Redis lock."
    ),
)
async def reconcile_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReconcileResponse:
    return await reconcile_document_answers(
        db=db,
        document_id=document_id,
        owner_id=user.id,
    )
