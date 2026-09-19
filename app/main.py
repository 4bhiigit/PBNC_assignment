import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.config import get_settings
from app.errors import register_error_handlers
from app.logging import request_id_ctx, setup_logging

settings = get_settings()
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup initialization
    yield
    # Shutdown cleanup


app = FastAPI(
    title="Document Intelligence & Question Extraction Service",
    description=(
        "Asynchronous document processing service for question paper " "and answer key extraction."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Cross-Origin Resource Sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    incoming_request_id = request.headers.get("X-Request-ID")
    req_id = incoming_request_id or f"req_{uuid.uuid4().hex[:16]}"

    # Store in contextvar for structured logging and request state for error handlers
    token = request_id_ctx.set(req_id)
    request.state.request_id = req_id

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return cast(Response, response)
    finally:
        request_id_ctx.reset(token)


# Register SPEC §13 compliant error envelope handlers
register_error_handlers(app)

# Include API routers
app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
