from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.errors import (
    NotFoundException,
    SecurityError,
    ValidationException,
    format_error_envelope,
    register_error_handlers,
)


def test_format_error_envelope() -> None:
    env = format_error_envelope(
        code="TEST_CODE",
        message="Test message",
        details={"foo": "bar"},
        request_id="req-123",
    )
    assert env == {
        "error": {
            "code": "TEST_CODE",
            "message": "Test message",
            "details": {"foo": "bar"},
            "request_id": "req-123",
        }
    }


def test_custom_app_exceptions() -> None:
    exc = NotFoundException("Missing item", {"id": 123})
    assert exc.code == "NOT_FOUND"
    assert exc.status_code == 404
    assert exc.details == {"id": 123}

    sec = SecurityError("Path traversal")
    assert sec.code == "FORBIDDEN"
    assert sec.status_code == 403

    val = ValidationException("Invalid field")
    assert val.code == "VALIDATION_ERROR"
    assert val.status_code == 422


def test_error_handlers_in_fastapi_app() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/not-found")
    def trigger_not_found() -> None:
        raise NotFoundException("Custom item not found")

    @app.get("/security-error")
    def trigger_security() -> None:
        raise SecurityError("Access denied")

    @app.get("/http-error-dict")
    def trigger_http_dict() -> None:
        raise HTTPException(
            status_code=400,
            detail={"code": "BAD_DATA", "message": "Custom bad request", "details": {"field": "x"}},
        )

    @app.get("/http-error-string")
    def trigger_http_str() -> None:
        raise HTTPException(status_code=404, detail="Raw 404 message")

    @app.get("/unhandled")
    def trigger_unhandled() -> None:
        raise RuntimeError("Unexpected failure")

    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/not-found")
    assert resp.status_code == 404
    data = resp.json()["error"]
    assert data["code"] == "NOT_FOUND"
    assert data["message"] == "Custom item not found"

    resp = client.get("/security-error")
    assert resp.status_code == 403
    data = resp.json()["error"]
    assert data["code"] == "FORBIDDEN"

    resp = client.get("/http-error-dict")
    assert resp.status_code == 400
    data = resp.json()["error"]
    assert data["code"] == "BAD_DATA"
    assert data["message"] == "Custom bad request"
    assert data["details"] == {"field": "x"}

    resp = client.get("/http-error-string")
    assert resp.status_code == 404
    data = resp.json()["error"]
    assert data["code"] == "NOT_FOUND"
    assert data["message"] == "Raw 404 message"

    resp = client.get("/unhandled")
    assert resp.status_code == 500
    data = resp.json()["error"]
    assert data["code"] == "INTERNAL_ERROR"
    assert data["message"] == "An unexpected error occurred"
