"""Tests for yt-dlp auto-updater."""

from unittest.mock import patch, MagicMock

import pytest

from backend.services.ytdlp_updater import check_and_update_ytdlp


@pytest.mark.asyncio
async def test_update_runs_subprocess():
    mock_result = MagicMock()
    mock_result.stdout = "Successfully installed yt-dlp-2025.01.15"
    mock_result.stderr = ""

    with patch("backend.services.ytdlp_updater.subprocess.run", return_value=mock_result) as mock_run:
        output = await check_and_update_ytdlp()
        assert "Successfully installed" in output
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_update_graceful_failure():
    with patch(
        "backend.services.ytdlp_updater.subprocess.run",
        side_effect=Exception("pip not found"),
    ):
        output = await check_and_update_ytdlp()
        assert "pip not found" in output
