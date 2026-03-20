"""Tests for OAuth token bootstrap from environment variables."""
from __future__ import annotations

import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch

from backend.db.database import _run_migrations
from backend.db.repositories import AuthTokenRepo
from backend.db.models import AuthToken

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def mem_db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


async def _run_bootstrap(mem_db, access_token: str, refresh_token: str = ""):
    """Run only the bootstrap portion of the lifespan against a given DB.

    Reproduces the logic in backend/api/main.py lifespan without starting
    the full ASGI app.
    """
    from backend.config import settings

    # Patch settings values and get_db to use the in-memory connection
    async def _fake_get_db():
        return mem_db

    with (
        patch.object(settings, "youtube_access_token", access_token),
        patch.object(settings, "youtube_refresh_token", refresh_token),
        patch("backend.api.main.get_db", new=_fake_get_db),
    ):
        # Re-import to pick up patched settings inside main module
        import backend.api.main as main_module

        # Execute only the bootstrap block (mirrors lifespan logic)
        if settings.youtube_access_token:
            db = await main_module.get_db()
            repo = AuthTokenRepo(db)
            existing = await repo.get()
            if existing is None:
                await repo.upsert(AuthToken(
                    id=1,
                    access_token=settings.youtube_access_token,
                    refresh_token=settings.youtube_refresh_token or None,
                    token_type="Bearer",
                    scopes="youtube.readonly youtube.force-ssl openid email",
                ))


class TestTokenBootstrap:
    async def test_bootstrap_inserts_token_when_db_empty(self, mem_db):
        """When youtube_access_token is set and DB has no token, token is inserted."""
        repo = AuthTokenRepo(mem_db)

        # Verify DB is empty
        assert await repo.get() is None

        await _run_bootstrap(mem_db, access_token="test_access_token_abc")

        token = await repo.get()
        assert token is not None
        assert token.access_token == "test_access_token_abc"
        assert token.token_type == "Bearer"
        assert token.scopes == "youtube.readonly youtube.force-ssl openid email"

    async def test_bootstrap_does_not_overwrite_existing_token(self, mem_db):
        """When a token already exists in DB, bootstrap must not overwrite it."""
        repo = AuthTokenRepo(mem_db)

        # Pre-seed the DB with an existing token
        existing_token = AuthToken(
            id=1,
            access_token="existing_token_xyz",
            refresh_token="existing_refresh",
            token_type="Bearer",
            scopes="youtube.readonly",
        )
        await repo.upsert(existing_token)

        # Run bootstrap with a different access token
        await _run_bootstrap(mem_db, access_token="new_env_token_abc")

        # The original token must still be present
        token = await repo.get()
        assert token is not None
        assert token.access_token == "existing_token_xyz"

    async def test_bootstrap_skipped_when_no_access_token(self, mem_db):
        """When youtube_access_token is empty, nothing is inserted."""
        repo = AuthTokenRepo(mem_db)
        assert await repo.get() is None

        # Run with empty access token
        await _run_bootstrap(mem_db, access_token="")

        assert await repo.get() is None

    async def test_bootstrap_stores_refresh_token(self, mem_db):
        """Refresh token from env vars is stored alongside access token."""
        repo = AuthTokenRepo(mem_db)

        await _run_bootstrap(
            mem_db,
            access_token="access_abc",
            refresh_token="refresh_xyz",
        )

        token = await repo.get()
        assert token is not None
        assert token.refresh_token == "refresh_xyz"

    async def test_bootstrap_empty_refresh_token_stored_as_none(self, mem_db):
        """Empty refresh token string is normalized to None in the DB."""
        repo = AuthTokenRepo(mem_db)

        await _run_bootstrap(mem_db, access_token="access_abc", refresh_token="")

        token = await repo.get()
        assert token is not None
        # Empty string is coerced to None in bootstrap logic
        assert token.refresh_token is None

    async def test_full_app_bootstrap_via_lifespan(self, mem_db):
        """Bootstrap runs correctly when the lifespan context manager is entered."""
        from backend.api.main import lifespan, app
        from backend.config import settings as real_settings
        from fastapi import FastAPI

        async def _fake_get_db():
            return mem_db

        with (
            patch.object(real_settings, "youtube_access_token", "lifespan_token"),
            patch.object(real_settings, "youtube_refresh_token", "lifespan_refresh"),
            patch("backend.db.database.init_db", new_callable=AsyncMock),
            patch("backend.db.database.close_db", new_callable=AsyncMock),
            patch("backend.api.main.get_db", new=_fake_get_db),
        ):
            # Directly invoke the lifespan context manager (bypasses ASGI transport
            # which does not send lifespan events)
            async with lifespan(app):
                repo = AuthTokenRepo(mem_db)
                token = await repo.get()
                assert token is not None
                assert token.access_token == "lifespan_token"
