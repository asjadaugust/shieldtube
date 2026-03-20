"""Tests for AuthManager — written TDD-style (failing first, then implemented)."""
import pytest
import aiosqlite
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend.db.database import _run_migrations
from backend.services.auth_manager import AuthManager


# ---------------------------------------------------------------------------
# Shared DB fixture (in-memory SQLite with schema)
# ---------------------------------------------------------------------------

@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future_expires_at(seconds: int = 3600) -> str:
    """Return an ISO-8601 string that expires `seconds` from now."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _past_expires_at(seconds: int = 60) -> str:
    """Return an ISO-8601 string that expired `seconds` ago."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


async def _insert_token(
    db: aiosqlite.Connection,
    access_token: str = "db-access-token",
    refresh_token: str | None = "db-refresh-token",
    expires_at: str | None = None,
) -> None:
    if expires_at is None:
        expires_at = _future_expires_at()
    await db.execute(
        "INSERT INTO auth_tokens (id, access_token, refresh_token, expires_at) VALUES (1, ?, ?, ?)",
        (access_token, refresh_token, expires_at),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_token_from_db_when_valid(db):
    """Returns access_token directly from DB when it has not expired."""
    await _insert_token(db, access_token="valid-db-token")
    manager = AuthManager(db)
    token = await manager.get_token()
    assert token == "valid-db-token"


@pytest.mark.asyncio
async def test_get_token_falls_back_to_env_when_db_empty(db):
    """Falls back to settings.youtube_access_token when auth_tokens is empty."""
    manager = AuthManager(db)
    with patch("backend.services.auth_manager.settings") as mock_settings:
        mock_settings.youtube_access_token = "env-token"
        token = await manager.get_token()
    assert token == "env-token"


@pytest.mark.asyncio
async def test_get_token_raises_when_no_token_available(db):
    """Raises ValueError when DB is empty and env var is also empty."""
    manager = AuthManager(db)
    with patch("backend.services.auth_manager.settings") as mock_settings:
        mock_settings.youtube_access_token = ""
        with pytest.raises(ValueError, match="No OAuth token available"):
            await manager.get_token()


@pytest.mark.asyncio
async def test_refresh_token_request_calls_google(db):
    """refresh_token_request() POSTs to Google and returns parsed JSON."""
    manager = AuthManager(db)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new-access-token",
        "expires_in": 3600,
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("backend.services.auth_manager.httpx.AsyncClient", return_value=mock_client):
        with patch("backend.services.auth_manager.settings") as mock_settings:
            mock_settings.google_client_id = "client-id"
            mock_settings.google_client_secret = "client-secret"
            result = await manager.refresh_token_request("my-refresh-token")

    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert "https://oauth2.googleapis.com/token" in call_kwargs[0]
    assert result["access_token"] == "new-access-token"
    assert result["expires_in"] == 3600


@pytest.mark.asyncio
async def test_get_token_auto_refreshes_when_expired(db):
    """When the stored token is expired, a new one is fetched and the DB is updated."""
    await _insert_token(
        db,
        access_token="old-access-token",
        refresh_token="my-refresh-token",
        expires_at=_past_expires_at(),
    )

    manager = AuthManager(db)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "refreshed-access-token",
        "expires_in": 3600,
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("backend.services.auth_manager.httpx.AsyncClient", return_value=mock_client):
        with patch("backend.services.auth_manager.settings") as mock_settings:
            mock_settings.google_client_id = "client-id"
            mock_settings.google_client_secret = "client-secret"
            token = await manager.get_token()

    assert token == "refreshed-access-token"

    # Verify DB was updated
    row = await (
        await db.execute("SELECT access_token FROM auth_tokens WHERE id = 1")
    ).fetchone()
    assert row["access_token"] == "refreshed-access-token"


@pytest.mark.asyncio
async def test_get_auth_headers_returns_bearer(db):
    """get_auth_headers() wraps the token in a Bearer Authorization header."""
    await _insert_token(db, access_token="header-token")
    manager = AuthManager(db)
    headers = await manager.get_auth_headers()
    assert headers == {"Authorization": "Bearer header-token"}
