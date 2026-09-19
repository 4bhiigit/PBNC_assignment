import os

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from redis.asyncio import from_url as async_redis_from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.common import HealthResponse, ReadyResponse
from app.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["Ops"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness health check",
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness check for database, redis, and storage",
)
async def readiness_check(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    settings = get_settings()
    checks: dict[str, str] = {}
    all_ready = True

    # 1. Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {str(exc)[:60]}"
        all_ready = False

    # 2. Redis check
    try:
        redis_client = async_redis_from_url(
            settings.redis_url, socket_timeout=2.0, socket_connect_timeout=2.0
        )
        await redis_client.ping()
        await redis_client.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {str(exc)[:60]}"
        all_ready = False

    # 3. Storage check
    try:
        os.makedirs(settings.storage_path, exist_ok=True)
        checks["storage"] = "ok"
    except Exception as exc:
        checks["storage"] = f"error: {str(exc)[:60]}"
        all_ready = False

    response_body = ReadyResponse(
        status="ready" if all_ready else "degraded",
        checks=checks,
    ).model_dump()

    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=response_body)
