import pytest
from unittest.mock import patch
from pathlib import Path

pytestmark = pytest.mark.asyncio


async def test_stream_endpoint_returns_video(client, tmp_path):
    fake_video = tmp_path / "dQw4w9WgXcQ.mp4"
    fake_video.write_bytes(b"\x00" * 2048)

    with patch("backend.api.routers.video.get_or_create_stream") as mock:
        mock.return_value = fake_video
        response = await client.get("/api/video/dQw4w9WgXcQ/stream")

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"


async def test_stream_endpoint_range_request(client, tmp_path):
    fake_video = tmp_path / "dQw4w9WgXcQ.mp4"
    fake_video.write_bytes(b"\x00" * 2048)

    with patch("backend.api.routers.video.get_or_create_stream") as mock:
        mock.return_value = fake_video
        response = await client.get(
            "/api/video/dQw4w9WgXcQ/stream",
            headers={"Range": "bytes=0-1023"},
        )

    assert response.status_code == 206
    assert "content-range" in response.headers
    assert response.headers["content-range"] == "bytes 0-1023/2048"
    assert len(response.content) == 1024


async def test_stream_endpoint_range_request_suffix(client, tmp_path):
    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"\x00" * 2048)

    with patch("backend.api.routers.video.get_or_create_stream") as mock:
        mock.return_value = fake_video
        response = await client.get(
            "/api/video/test/stream",
            headers={"Range": "bytes=1024-"},
        )

    assert response.status_code == 206
    assert len(response.content) == 1024
