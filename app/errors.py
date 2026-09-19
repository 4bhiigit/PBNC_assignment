from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import request_id_ctx


class AppException(Exception):
    """Base application exception returning the SPEC §13 error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: dict[str, Any] | None = None):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class UnauthenticatedException(AppException):
    def __init__(self, message: str = "Authentication credentials missing or invalid"):
        super().__init__(
            code="UNAUTHENTICATED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenException(AppException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ConflictException(AppException):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class DocumentNotReadyException(AppException):
    def __init__(
        self,
        message: str = "Document is still processing",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code="DOCUMENT_NOT_READY",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class FileTooLargeException(AppException):
    def __init__(
        self,
        message: str = "Uploaded file exceeds size limit",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code="FILE_TOO_LARGE",
            message=message,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details=details,
        )


class UnsupportedMediaTypeException(AppException):
    def __init__(
        self,
        message: str = "Unsupported media type",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code="UNSUPPORTED_MEDIA_TYPE",
            message=message,
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            details=details,
        )


class MalformedFileException(AppException):
    def __init__(
        self,
        message: str = "File is corrupt or cannot be parsed",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code="MALFORMED_FILE",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class PdfEncryptedException(AppException):
    def __init__(self, message: str = "Encrypted or password-protected PDFs are not supported"):
        super().__init__(
            code="PDF_ENCRYPTED",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class TooManyPagesException(AppException):
    def __init__(self, message: str = "Document page count exceeds maximum limit"):
        super().__init__(
            code="TOO_MANY_PAGES",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class RateLimitedException(AppException):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            code="RATE_LIMITED",
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class QueueUnavailableException(AppException):
    def __init__(self, message: str = "Processing queue is currently unavailable"):
        super().__init__(
            code="QUEUE_UNAVAILABLE",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def format_error_envelope(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id or request_id_ctx.get() or "unknown",
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_envelope(exc.code, exc.message, exc.details, req_id),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
        details = {"errors": exc.errors()}
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=format_error_envelope(
                "VALIDATION_ERROR", "Request validation failed", details, req_id
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
        code_map = {
            status.HTTP_401_UNAUTHORIZED: "UNAUTHENTICATED",
            status.HTTP_403_FORBIDDEN: "FORBIDDEN",
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_409_CONFLICT: "CONFLICT",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "FILE_TOO_LARGE",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
            status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
            status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
            status.HTTP_503_SERVICE_UNAVAILABLE: "QUEUE_UNAVAILABLE",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_envelope(code, str(exc.detail), {}, req_id),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=format_error_envelope(
                "INTERNAL_ERROR", "An unexpected error occurred", {}, req_id
            ),
        )
