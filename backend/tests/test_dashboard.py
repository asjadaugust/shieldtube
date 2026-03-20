"""Tests for dashboard API endpoints: system status, precache rules, static files."""
from __future__ import annotations

import json
import pytest
import aiosqlite
from pathlib import Path
from unittest.mock import patch

from httpx import AsyncClient, ASGITransport

from backend.api.main import app
from backend.api.routers import dashboard as dashboard_module  # ensure module is imported for patching
from backend.db.database import _run_migrations

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def dashboard_client(tmp_path):
    """Set up in-memory DB, patched settings, and test client."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)

    async def mock_get_db():
        return conn

    async def mock_init_db():
        pass

    async def mock_close_db():
        pass

    with patch("backend.db.database.get_db", mock_get_db), \
         patch("backend.db.database.init_db", mock_init_db), \
         patch("backend.db.database.close_db", mock_close_db), \
         patch("backend.api.routers.dashboard.get_db", mock_get_db), \
         patch("backend.config.settings") as mock_config_settings:
        mock_config_settings.cache_dir = str(tmp_path)
        mock_config_settings.youtube_access_token = ""
        mock_config_settings.download_wait_timeout = 30

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield conn, client, tmp_path

    await conn.close()


async def test_system_status_returns_version_and_uptime(dashboard_client):
    """GET /api/system/status returns version and uptime fields."""
    conn, client, tmp_path = dashboard_client

    resp = await client.get("/api/system/status")
    assert resp.status_code == 200

    data = resp.json()
    assert data["version"] == "0.3.0"
    assert "uptime" in data
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], int)
    assert data["uptime_seconds"] >= 0
    # uptime format: Xh Ym
    assert "h" in data["uptime"]
    assert "m" in data["uptime"]


async def test_system_status_auth_not_authenticated(dashboard_client):
    """GET /api/system/status shows 'not authenticated' when no token in DB."""
    conn, client, tmp_path = dashboard_client

    resp = await client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["auth_status"] == "not authenticated"


async def test_system_status_includes_queue_size(dashboard_client):
    """GET /api/system/status returns download_queue_size field."""
    conn, client, tmp_path = dashboard_client

    resp = await client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "download_queue_size" in data
    assert isinstance(data["download_queue_size"], int)


async def test_get_precache_rules_returns_json(dashboard_client, tmp_path):
    """GET /api/precache/rules returns JSON (empty list when no file)."""
    conn, client, _ = dashboard_client

    # Point Path resolution to a non-existent file inside tmp_path
    rules_path = tmp_path / "config" / "precache_rules.json"

    with patch("backend.api.routers.dashboard.Path", return_value=rules_path):
        resp = await client.get("/api/precache/rules")

    assert resp.status_code == 200
    data = resp.json()
    assert "precache_rules" in data
    assert data["precache_rules"] == []


async def test_get_precache_rules_returns_existing_rules(dashboard_client, tmp_path):
    """GET /api/precache/rules returns rules from existing config file."""
    conn, client, _ = dashboard_client

    rules_dir = tmp_path / "config"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "precache_rules.json"
    rules_content = {
        "precache_rules": [
            {"type": "channel", "channel_id": "UCtest123", "max_videos": 5, "quality": "auto", "trigger": "on_upload"}
        ]
    }
    rules_file.write_text(json.dumps(rules_content))

    with patch("backend.api.routers.dashboard.Path", return_value=rules_file):
        resp = await client.get("/api/precache/rules")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["precache_rules"]) == 1
    assert data["precache_rules"][0]["channel_id"] == "UCtest123"


async def test_save_precache_rules(dashboard_client, tmp_path):
    """POST /api/precache/rules saves rules to file and returns count."""
    conn, client, _ = dashboard_client

    rules_dir = tmp_path / "config"
    rules_file = rules_dir / "precache_rules.json"

    with patch("backend.api.routers.dashboard.Path", return_value=rules_file):
        payload = {
            "precache_rules": [
                {"type": "channel", "channel_id": "UCtest456", "max_videos": 3, "quality": "1080p", "trigger": "on_upload"},
                {"type": "channel", "channel_id": "UCtest789", "max_videos": 10, "quality": "auto", "trigger": "on_upload"},
            ]
        }
        resp = await client.post(
            "/api/precache/rules",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "saved"
    assert data["count"] == 2


async def test_save_precache_rules_empty_list(dashboard_client, tmp_path):
    """POST /api/precache/rules with empty list saves successfully."""
    conn, client, _ = dashboard_client

    rules_dir = tmp_path / "config"
    rules_file = rules_dir / "precache_rules.json"

    with patch("backend.api.routers.dashboard.Path", return_value=rules_file):
        resp = await client.post(
            "/api/precache/rules",
            json={"precache_rules": []},
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "saved"
    assert data["count"] == 0


async def test_dashboard_serves_html(dashboard_client):
    """GET /dashboard/ serves the HTML dashboard."""
    conn, client, _ = dashboard_client

    resp = await client.get("/dashboard/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    content = resp.text
    assert "ShieldTube" in content
    assert "Cache Management" in content
    assert "Pre-cache Rules" in content
