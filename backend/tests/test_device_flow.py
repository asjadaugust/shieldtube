"""Tests for OAuth device flow endpoints and service layer."""
from __future__ import annotations

import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from backend.db.database import _run_migrations
from backend.db.repositories import AuthTokenRepo

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def mem_db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def client(mem_db):
    """AsyncClient wired to the FastAPI app with in-memory DB."""
    from backend.api.main import app

    async def _fake_get_db():
        return mem_db

    with (
        patch("backend.db.database.init_db", new_callable=AsyncMock),
        patch("backend.db.database.close_db", new_callable=AsyncMock),
        patch("backend.api.routers.auth.get_db", new=_fake_get_db),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# /api/auth/login tests
# ---------------------------------------------------------------------------

class TestAuthLogin:
    async def test_login_returns_device_code_fields(self, client):
        """GET /api/auth/login returns all required fields for TV display."""
        mock_response = {
            "device_code": "4/devcode_abc123",
            "user_code": "ABCD-1234",
            "verification_url": "https://google.com/device",
            "expires_in": 1800,
            "interval": 5,
        }
        with patch(
            "backend.api.routers.auth.request_device_code",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = await client.get("/api/auth/login")

        assert response.status_code == 200
        data = response.json()
        assert data["device_code"] == "4/devcode_abc123"
        assert data["user_code"] == "ABCD-1234"
        assert data["verification_url"] == "https://google.com/device"
        assert data["expires_in"] == 1800
        assert data["interval"] == 5

    async def test_login_defaults_interval_to_5_when_missing(self, client):
        """Interval defaults to 5 if Google doesn't return it."""
        mock_response = {
            "device_code": "4/devcode_xyz",
            "user_code": "EFGH-5678",
            "verification_url": "https://google.com/device",
            "expires_in": 1800,
            # interval not present
        }
        with patch(
            "backend.api.routers.auth.request_device_code",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = await client.get("/api/auth/login")

        assert response.status_code == 200
        assert response.json()["interval"] == 5


# ---------------------------------------------------------------------------
# /api/auth/callback tests
# ---------------------------------------------------------------------------

class TestAuthCallback:
    async def test_callback_authorized_stores_token(self, client, mem_db):
        """Authorized response stores the token in DB and returns status."""
        mock_result = {
            "status": "authorized",
            "access_token": "ya29.new_access_token",
            "refresh_token": "1//refresh_token_abc",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        with patch(
            "backend.api.routers.auth.poll_for_token",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.get(
                "/api/auth/callback",
                params={"device_code": "4/devcode_abc123"},
            )

        assert response.status_code == 200
        assert response.json() == {"status": "authorized"}

        # Verify token was persisted to DB
        repo = AuthTokenRepo(mem_db)
        token = await repo.get()
        assert token is not None
        assert token.access_token == "ya29.new_access_token"
        assert token.refresh_token == "1//refresh_token_abc"
        assert token.token_type == "Bearer"
        assert token.scopes == "youtube.readonly youtube.force-ssl openid email"
        assert token.expires_at is not None

    async def test_callback_authorized_sets_expires_at(self, client, mem_db):
        """expires_at is calculated from expires_in and stored as ISO string."""
        mock_result = {
            "status": "authorized",
            "access_token": "ya29.token",
            "refresh_token": None,
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        with patch(
            "backend.api.routers.auth.poll_for_token",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await client.get(
                "/api/auth/callback",
                params={"device_code": "4/devcode_abc123"},
            )

        repo = AuthTokenRepo(mem_db)
        token = await repo.get()
        # expires_at should be a non-empty ISO datetime string
        assert token.expires_at is not None
        assert "T" in token.expires_at  # basic ISO 8601 check

    async def test_callback_pending_returns_status(self, client, mem_db):
        """authorization_pending response returns correct status without storing."""
        mock_result = {"status": "authorization_pending"}
        with patch(
            "backend.api.routers.auth.poll_for_token",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.get(
                "/api/auth/callback",
                params={"device_code": "4/devcode_abc123"},
            )

        assert response.status_code == 200
        assert response.json() == {"status": "authorization_pending"}

        # No token should be stored
        repo = AuthTokenRepo(mem_db)
        assert await repo.get() is None

    async def test_callback_access_denied_returns_status(self, client, mem_db):
        """access_denied response returns correct status without storing."""
        mock_result = {"status": "access_denied"}
        with patch(
            "backend.api.routers.auth.poll_for_token",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.get(
                "/api/auth/callback",
                params={"device_code": "4/denied_code"},
            )

        assert response.status_code == 200
        assert response.json() == {"status": "access_denied"}

        # No token should be stored
        repo = AuthTokenRepo(mem_db)
        assert await repo.get() is None

    async def test_callback_expired_code_returns_status(self, client, mem_db):
        """expired_token error returns correct status."""
        mock_result = {"status": "expired_token"}
        with patch(
            "backend.api.routers.auth.poll_for_token",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.get(
                "/api/auth/callback",
                params={"device_code": "4/expired_code"},
            )

        assert response.status_code == 200
        assert response.json() == {"status": "expired_token"}

    async def test_callback_missing_device_code_returns_422(self, client):
        """Missing required device_code query param returns 422."""
        response = await client.get("/api/auth/callback")
        assert response.status_code == 422

    async def test_callback_overwrites_existing_token(self, client, mem_db):
        """A second authorized callback replaces the existing token."""
        # First authorization
        mock_result_1 = {
            "status": "authorized",
            "access_token": "ya29.first_token",
            "refresh_token": "refresh_first",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        with patch(
            "backend.api.routers.auth.poll_for_token",
            new_callable=AsyncMock,
            return_value=mock_result_1,
        ):
            await client.get(
                "/api/auth/callback",
                params={"device_code": "4/first_code"},
            )

        # Second authorization
        mock_result_2 = {
            "status": "authorized",
            "access_token": "ya29.second_token",
            "refresh_token": "refresh_second",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        with patch(
            "backend.api.routers.auth.poll_for_token",
            new_callable=AsyncMock,
            return_value=mock_result_2,
        ):
            await client.get(
                "/api/auth/callback",
                params={"device_code": "4/second_code"},
            )

        repo = AuthTokenRepo(mem_db)
        token = await repo.get()
        assert token.access_token == "ya29.second_token"


# ---------------------------------------------------------------------------
# Service layer unit tests
# ---------------------------------------------------------------------------

class TestDeviceFlowService:
    async def test_request_device_code_calls_correct_url(self):
        """request_device_code POSTs to the correct Google endpoint."""
        from unittest.mock import MagicMock
        from backend.services.device_flow import request_device_code, DEVICE_CODE_URL

        mock_response_data = {
            "device_code": "4/devcode",
            "user_code": "XXXX-YYYY",
            "verification_url": "https://google.com/device",
            "expires_in": 1800,
            "interval": 5,
        }

        with patch("backend.services.device_flow.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            # httpx Response.json() is synchronous — use MagicMock
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response_data
            mock_resp.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await request_device_code()

        assert result == mock_response_data
        call_args = mock_client.post.call_args
        assert call_args[0][0] == DEVICE_CODE_URL

    async def test_poll_for_token_returns_authorized_on_success(self):
        """poll_for_token returns authorized dict when Google returns tokens."""
        from unittest.mock import MagicMock
        from backend.services.device_flow import poll_for_token

        google_response = {
            "access_token": "ya29.token",
            "refresh_token": "1//refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("backend.services.device_flow.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.json.return_value = google_response
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await poll_for_token("4/devcode")

        assert result["status"] == "authorized"
        assert result["access_token"] == "ya29.token"
        assert result["refresh_token"] == "1//refresh"
        assert result["expires_in"] == 3600

    async def test_poll_for_token_returns_error_status(self):
        """poll_for_token maps error field to status key."""
        from unittest.mock import MagicMock
        from backend.services.device_flow import poll_for_token

        google_response = {"error": "authorization_pending"}

        with patch("backend.services.device_flow.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.json.return_value = google_response
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await poll_for_token("4/devcode")

        assert result == {"status": "authorization_pending"}

    async def test_poll_for_token_access_denied(self):
        """poll_for_token returns access_denied status."""
        from unittest.mock import MagicMock
        from backend.services.device_flow import poll_for_token

        google_response = {"error": "access_denied"}

        with patch("backend.services.device_flow.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.json.return_value = google_response
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await poll_for_token("4/denied")

        assert result == {"status": "access_denied"}
