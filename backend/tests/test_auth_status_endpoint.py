"""Tests for /api/auth/status — verifies the endpoint returns correct
authenticated state based on actual token validity, not row existence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.database import _run_migrations

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future_expires_at(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _past_expires_at(seconds: int = 60) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


async def _insert_token(
    db: aiosqlite.Connection,
    access_token: str = "test-access-token",
    refresh_token: str | None = None,
    expires_at: str | None = None,
) -> None:
    await db.execute(
        "INSERT INTO auth_tokens (id, access_token, refresh_token, expires_at) VALUES (1, ?, ?, ?)",
        (access_token, refresh_token, expires_at),
    )
    await db.commit()


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
    from backend.api.main import app

    async def _fake_get_db():
        return mem_db

    with (
        patch("backend.db.database.init_db", new_callable=AsyncMock),
        patch("backend.db.database.close_db", new_callable=AsyncMock),
        patch("backend.api.routers.auth.get_db", new=_fake_get_db),
        patch("backend.services.auth_manager.settings") as mock_settings,
    ):
        mock_settings.youtube_access_token = ""
        mock_settings.youtube_refresh_token = ""
        mock_settings.google_client_id = ""
        mock_settings.google_client_secret = ""
        mock_settings.token_encryption_key = ""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_auth_status_false_when_no_token(client):
    """Empty DB → authenticated must be false."""
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": False}


async def test_auth_status_true_when_valid_token(client, mem_db):
    """Valid, non-expired token in DB → authenticated must be true."""
    await _insert_token(mem_db, expires_at=_future_expires_at())
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True}


async def test_auth_status_false_when_expired_no_refresh(client, mem_db):
    """Expired token with no refresh_token → authenticated must be false."""
    await _insert_token(
        mem_db,
        access_token="expired-token",
        refresh_token=None,
        expires_at=_past_expires_at(),
    )
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": False}


async def test_auth_status_false_when_null_expires_at_no_refresh(client, mem_db):
    """Token with expires_at=NULL and no refresh_token → authenticated must be false.
    This is the bootstrap-token edge case."""
    await _insert_token(
        mem_db,
        access_token="bootstrap-token",
        refresh_token=None,
        expires_at=None,  # NULL — no expiry recorded
    )
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": False}
