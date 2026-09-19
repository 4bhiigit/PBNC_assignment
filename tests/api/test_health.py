import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_readiness_check_returns_checks(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code in [200, 503]
    data = response.json()
    assert "checks" in data
    assert "database" in data["checks"]
    assert "redis" in data["checks"]
    assert "storage" in data["checks"]


@pytest.mark.asyncio
async def test_non_existent_route_returns_spec_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    error = data["error"]
    assert error["code"] == "NOT_FOUND"
    assert "message" in error
    assert "request_id" in error
    assert "details" in error
