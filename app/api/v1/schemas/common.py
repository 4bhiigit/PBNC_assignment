from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(
        ...,
        description="Machine-readable error code",
        examples=["FILE_TOO_LARGE"],
    )
    message: str = Field(
        ...,
        description="Human-readable description",
        examples=["File size exceeds 25 MB limit"],
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured context",
    )
    request_id: str = Field(
        ...,
        description="Unique request tracing ID",
        examples=["req_01hz8k9..."],
    )


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str = Field("ok", examples=["ok"])
    version: str = Field("0.1.0", examples=["0.1.0"])


class ReadyResponse(BaseModel):
    status: str = Field("ready", examples=["ready"])
    checks: dict[str, str] = Field(
        ...,
        examples=[{"database": "ok", "redis": "ok", "storage": "ok"}],
    )
