"""Tests for shared-secret API auth middleware."""

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from backend.api.middleware import SharedSecretMiddleware


def _make_app(secret: str = "test-secret") -> FastAPI:
    app = FastAPI()
    app.add_middleware(SharedSecretMiddleware, secret=secret)

    @app.get("/api/feed/home")
    async def home():
        return {"ok": True}

    @app.get("/api/auth/login")
    async def login():
        return {"ok": True}

    @app.get("/dashboard/index.html")
    async def dashboard():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_missing_header_returns_401():
    app = _make_app("my-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/feed/home")
    assert resp.status_code == 401
    assert "Unauthorized" in resp.json()["error"]


@pytest.mark.asyncio
async def test_correct_header_returns_200():
    app = _make_app("my-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/feed/home", headers={"X-ShieldTube-Secret": "my-secret"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_wrong_header_returns_401():
    app = _make_app("my-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/feed/home", headers={"X-ShieldTube-Secret": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_exempt_path_no_header_returns_200():
    app = _make_app("my-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/login")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_empty_secret_passthrough():
    app = _make_app("")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/feed/home")
    assert resp.status_code == 200
