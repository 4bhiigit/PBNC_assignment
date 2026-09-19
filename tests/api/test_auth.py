import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login_happy_path(client: AsyncClient) -> None:
    # 1. Register
    register_payload = {
        "email": "student@example.com",
        "password": "SecurePassword123!",
    }
    reg_res = await client.post("/api/v1/auth/register", json=register_payload)
    assert reg_res.status_code == 201
    user_data = reg_res.json()
    assert user_data["email"] == "student@example.com"
    assert user_data["role"] == "user"
    assert "id" in user_data

    # 2. Login
    login_payload = {
        "email": "student@example.com",
        "password": "SecurePassword123!",
    }
    login_res = await client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    token = token_data["access_token"]

    # 3. Access /me endpoint with Bearer token
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == "student@example.com"
    assert me_data["id"] == user_data["id"]


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(client: AsyncClient) -> None:
    payload = {
        "email": "duplicate@example.com",
        "password": "ValidPassword999",
    }
    first_res = await client.post("/api/v1/auth/register", json=payload)
    assert first_res.status_code == 201

    second_res = await client.post("/api/v1/auth/register", json=payload)
    assert second_res.status_code == 409
    error_data = second_res.json()
    assert error_data["error"]["code"] == "CONFLICT"
    assert "exists" in error_data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_login_wrong_password_fails(client: AsyncClient) -> None:
    reg_payload = {
        "email": "auth_test@example.com",
        "password": "CorrectPassword123",
    }
    await client.post("/api/v1/auth/register", json=reg_payload)

    wrong_login = {
        "email": "auth_test@example.com",
        "password": "WrongPassword456",
    }
    res = await client.post("/api/v1/auth/login", json=wrong_login)
    assert res.status_code == 401
    error_data = res.json()
    assert error_data["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_get_me_unauthorized_cases(client: AsyncClient) -> None:
    # Missing authorization header
    res_no_header = await client.get("/api/v1/auth/me")
    assert res_no_header.status_code == 401
    assert res_no_header.json()["error"]["code"] == "UNAUTHENTICATED"

    # Malformed token
    res_bad_token = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert res_bad_token.status_code == 401
    assert res_bad_token.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_validation_error_uses_envelope(client: AsyncClient) -> None:
    # Password too short (requires min 8 characters)
    invalid_payload = {
        "email": "not-a-valid-email",
        "password": "short",
    }
    res = await client.post("/api/v1/auth/register", json=invalid_payload)
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "errors" in data["error"]["details"]
