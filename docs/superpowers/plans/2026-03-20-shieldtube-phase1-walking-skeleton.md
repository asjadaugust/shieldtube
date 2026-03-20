# Phase 1: Walking Skeleton — Implementation Plan

> **For agentic workers:** This plan uses Ralph Loop methodology with parallel sub-agents in git worktrees. Use `superpowers:dispatching-parallel-agents` to run Workstreams A and B concurrently. Each workstream runs in an isolated worktree via `superpowers:using-git-worktrees`. Each agent iterates toward its completion promise, seeing its own previous work in files.

**Goal:** A single hardcoded video plays on NVIDIA Shield TV via the backend, with HDR passthrough to LG OLED, in ≤ 5 seconds from click.

**Architecture:** Backend resolves stream via yt-dlp → FFmpeg muxes video+audio into MP4 with stream copy → serves via HTTP with range requests → Shield ExoPlayer plays from local URL.

**Tech Stack:** Python 3.11+, FastAPI, yt-dlp, FFmpeg 6.0+, aiosqlite, pydantic-settings | Kotlin, Leanback UI, ExoPlayer/Media3, Gradle

---

## Execution Model

```
                    ┌─────────────────────┐
                    │   Orchestrator      │
                    │   (this session)    │
                    └──────┬──────────────┘
                           │
              Task 0: Scaffolding (sequential)
                           │
              ┌────────────┴────────────┐
              │                         │
     ┌────────▼─────────┐    ┌─────────▼────────┐
     │  Workstream A     │    │  Workstream B     │
     │  Backend Engine   │    │  Shield App       │
     │  (worktree)       │    │  (worktree)       │
     │                   │    │                   │
     │  Ralph Loop:      │    │  Ralph Loop:      │
     │  iterate until    │    │  iterate until    │
     │  all tests pass   │    │  build succeeds   │
     │  + curl works     │    │  + app installs   │
     └────────┬──────────┘    └─────────┬─────────┘
              │                         │
              └────────────┬────────────┘
                           │
              Task C: Docker (sequential, after A)
                           │
              Task I: Merge + End-to-End Verify
```

**Parallel dispatch:** Workstreams A and B launch simultaneously in separate worktrees. No shared files — backend is Python, Shield app is Kotlin.

**Ralph Loop style:** Each agent gets a self-contained prompt with success criteria and a `<promise>` tag. The agent iterates: write code → run tests → see failures → fix → repeat until the promise condition is met.

**Review:** Orchestrator reviews each workstream on completion (spec compliance + code quality) before merging.

---

## File Structure

### Backend (`backend/`)

| File | Responsibility |
|------|---------------|
| `backend/api/__init__.py` | Package marker |
| `backend/api/main.py` | FastAPI app entry, router wiring |
| `backend/api/routers/__init__.py` | Package marker |
| `backend/api/routers/video.py` | `GET /api/video/{video_id}/stream` — resolve, mux, serve |
| `backend/services/__init__.py` | Package marker |
| `backend/services/stream_resolver.py` | yt-dlp: video ID → stream URLs |
| `backend/services/muxer.py` | FFmpeg subprocess: video+audio → MP4 |
| `backend/config.py` | Pydantic Settings for env vars |
| `backend/requirements.txt` | Python dependencies |
| `backend/Dockerfile` | Container image |
| `backend/tests/__init__.py` | Package marker |
| `backend/tests/conftest.py` | Shared fixtures (async client) |
| `backend/tests/test_stream_resolver.py` | yt-dlp unit tests |
| `backend/tests/test_muxer.py` | FFmpeg unit tests |
| `backend/tests/test_video_endpoint.py` | API integration tests |

### Shield App (`shield-app/`)

| File | Responsibility |
|------|---------------|
| `shield-app/build.gradle.kts` | Root Gradle config |
| `shield-app/settings.gradle.kts` | Gradle settings |
| `shield-app/gradle.properties` | Gradle properties |
| `shield-app/app/build.gradle.kts` | App module: ExoPlayer + Leanback deps |
| `shield-app/app/src/main/AndroidManifest.xml` | Leanback declaration, network permission |
| `shield-app/app/src/main/java/com/shieldtube/MainActivity.kt` | Entry point, launches PlaybackFragment |
| `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt` | ExoPlayer with HDR passthrough |
| `shield-app/app/src/main/res/values/strings.xml` | App strings |

### Infrastructure

| File | Responsibility |
|------|---------------|
| `docker-compose.yml` | Service orchestration |
| `backend/Dockerfile` | Backend container image |
| `config/.env.example` | Environment variable template |

---

## Task 0: Project Scaffolding (Sequential Setup)

**Purpose:** Create directory structure and config files so parallel workstreams have a consistent foundation.

**Files:**
- Create: all `__init__.py` files, `backend/requirements.txt`, `backend/config.py`, `config/.env.example`

- [ ] **Step 1: Create backend directory structure**

```bash
mkdir -p backend/{api/routers,services,tests,db}
touch backend/{api,api/routers,services,tests}/__init__.py
```

- [ ] **Step 2: Write `backend/requirements.txt`**

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
yt-dlp>=2024.12.0
aiosqlite>=0.19.0
pydantic-settings>=2.1.0
httpx>=0.26.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 3: Write `backend/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    cache_dir: str = "./cache"
    ffmpeg_threads: int = 2

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 4: Write `config/.env.example`**

```
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8080
CACHE_DIR=./cache
FFMPEG_THREADS=2
```

- [ ] **Step 5: Commit scaffolding**

```bash
git add backend/ config/
git commit -m "chore: scaffold Phase 1 project structure"
```

---

## Workstream A: Backend Stream Engine (Parallel — Worktree)

**Isolation:** Git worktree branched from scaffolding commit
**Dispatched as:** Background agent with worktree isolation
**Completion Promise:** `BACKEND STREAM ENGINE COMPLETE`

### Agent Dispatch Prompt

```markdown
You are building the ShieldTube backend stream engine — Phase 1 walking skeleton.
Your job is to make a single YouTube video playable via HTTP with range-request support.

**Read these files first for project context:**
- `backend/config.py` — app settings
- `backend/requirements.txt` — dependencies
- `docs/ShieldTube_PRD.md` sections: Component 3 (Stream Resolution Engine), Component 4 (Progressive Download)

**What to build (TDD — failing test first, then implement):**

1. `backend/services/stream_resolver.py`
   - Function `resolve_stream(video_id: str, prefer_hdr: bool = True) -> dict`
   - Uses yt-dlp to extract video+audio stream URLs
   - Format priority: VP9.2 (HDR) > VP9 > AV1 > H.264
   - Returns: `{"video_url": str, "audio_url": str, "duration": int, "title": str}`
   - Test file: `backend/tests/test_stream_resolver.py`
   - Mock yt-dlp in tests (don't hit YouTube)

2. `backend/services/muxer.py`
   - Function `mux_streams(video_url: str, audio_url: str, output_path: Path) -> Path`
   - Calls FFmpeg as subprocess with stream copy: `-c:v copy -c:a copy`
   - Uses `-movflags +faststart+frag_keyframe` for progressive playback
   - Raises `RuntimeError` on FFmpeg failure
   - Test file: `backend/tests/test_muxer.py`
   - Mock subprocess.run in tests

3. `backend/api/main.py` + `backend/api/routers/video.py`
   - FastAPI app with single endpoint: `GET /api/video/{video_id}/stream`
   - Resolves stream → muxes to cache → serves MP4
   - Full HTTP range-request support (Accept-Ranges, 206 Partial Content)
   - Caches muxed files to `{CACHE_DIR}/videos/{video_id}.mp4`
   - Test file: `backend/tests/test_video_endpoint.py`
   - Shared fixtures in `backend/tests/conftest.py` (httpx AsyncClient)

**Success criteria (ALL must pass):**
- `cd backend && python -m pytest tests/ -v` — ALL tests pass
- Server starts: `uvicorn backend.api.main:app --host 0.0.0.0 --port 8080`
- `curl -I http://localhost:8080/api/video/dQw4w9WgXcQ/stream` → 200 with `Accept-Ranges: bytes`
- `curl -H "Range: bytes=0-1023" -I http://localhost:8080/api/video/dQw4w9WgXcQ/stream` → 206

**Constraints:**
- No transcoding — FFmpeg stream copy only
- Cache dir from settings, not hardcoded
- < 500ms for stream URL resolution target
- Commit after each component (resolver, muxer, endpoint)

**Iterate until all tests pass. Output <promise>BACKEND STREAM ENGINE COMPLETE</promise> when done.**
```

### Task A1: Stream Resolver

**Files:**
- Create: `backend/services/stream_resolver.py`
- Create: `backend/tests/test_stream_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_stream_resolver.py
import pytest
from unittest.mock import patch, MagicMock

from backend.services.stream_resolver import resolve_stream


@pytest.fixture
def mock_yt_dlp_info():
    return {
        "requested_formats": [
            {
                "url": "https://rr1.example.com/video.webm",
                "ext": "webm",
                "vcodec": "vp9",
                "height": 2160,
            },
            {
                "url": "https://rr1.example.com/audio.webm",
                "ext": "webm",
                "acodec": "opus",
            },
        ],
        "duration": 212,
        "title": "Test Video",
        "id": "dQw4w9WgXcQ",
    }


def test_resolve_stream_returns_video_and_audio_urls(mock_yt_dlp_info):
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = resolve_stream("dQw4w9WgXcQ")

        assert result["video_url"] == "https://rr1.example.com/video.webm"
        assert result["audio_url"] == "https://rr1.example.com/audio.webm"
        assert result["duration"] == 212
        assert result["title"] == "Test Video"


def test_resolve_stream_prefers_hdr_format(mock_yt_dlp_info):
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", prefer_hdr=True)

        opts = mock_cls.call_args[0][0]
        assert "vp09.02" in opts["format"]


def test_resolve_stream_non_hdr_fallback(mock_yt_dlp_info):
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", prefer_hdr=False)

        opts = mock_cls.call_args[0][0]
        assert "vp09.02" not in opts["format"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_stream_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.stream_resolver'`

- [ ] **Step 3: Implement stream resolver**

```python
# backend/services/stream_resolver.py
import yt_dlp


def resolve_stream(video_id: str, prefer_hdr: bool = True) -> dict:
    """Resolve a YouTube video ID into separate video and audio stream URLs."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    if prefer_hdr:
        opts["format"] = (
            "bestvideo[vcodec=vp09.02][height<=2160]+bestaudio/"
            "bestvideo[vcodec^=vp9][height<=2160]+bestaudio/"
            "bestvideo[height<=2160]+bestaudio/best"
        )
    else:
        opts["format"] = (
            "bestvideo[ext=webm][vcodec^=vp9]+bestaudio[ext=webm]/"
            "bestvideo[height<=2160]+bestaudio/best"
        )

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}",
            download=False,
        )
        return {
            "video_url": info["requested_formats"][0]["url"],
            "audio_url": info["requested_formats"][1]["url"],
            "duration": info["duration"],
            "title": info["title"],
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_stream_resolver.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/stream_resolver.py backend/tests/test_stream_resolver.py
git commit -m "feat: add yt-dlp stream resolver with HDR format preference"
```

### Task A2: FFmpeg Muxer

**Files:**
- Create: `backend/services/muxer.py`
- Create: `backend/tests/test_muxer.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_muxer.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from backend.services.muxer import mux_streams


def test_mux_streams_calls_ffmpeg_with_stream_copy(tmp_path):
    output = tmp_path / "output.mp4"

    with patch("backend.services.muxer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = mux_streams(
            video_url="https://example.com/video.webm",
            audio_url="https://example.com/audio.webm",
            output_path=output,
        )

        args = mock_run.call_args[0][0]
        assert "ffmpeg" in args[0]
        # Stream copy — no transcoding
        idx_cv = args.index("-c:v")
        assert args[idx_cv + 1] == "copy"
        idx_ca = args.index("-c:a")
        assert args[idx_ca + 1] == "copy"
        # Faststart for progressive playback
        idx_mov = args.index("-movflags")
        assert "+faststart" in args[idx_mov + 1]
        assert result == output


def test_mux_streams_raises_on_ffmpeg_failure(tmp_path):
    output = tmp_path / "output.mp4"

    with patch("backend.services.muxer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="encoding error")

        with pytest.raises(RuntimeError, match="FFmpeg muxing failed"):
            mux_streams(
                video_url="https://example.com/video.webm",
                audio_url="https://example.com/audio.webm",
                output_path=output,
            )


def test_mux_streams_creates_parent_dirs(tmp_path):
    output = tmp_path / "nested" / "dir" / "output.mp4"

    with patch("backend.services.muxer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mux_streams("https://v.com/v.webm", "https://v.com/a.webm", output)

        assert output.parent.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_muxer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement muxer**

```python
# backend/services/muxer.py
import subprocess
from pathlib import Path


def mux_streams(video_url: str, audio_url: str, output_path: Path) -> Path:
    """Mux separate video+audio DASH streams into single MP4 via FFmpeg stream copy."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_url,
        "-i", audio_url,
        "-c:v", "copy",
        "-c:a", "copy",
        "-movflags", "+faststart+frag_keyframe",
        "-f", "mp4",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg muxing failed: {result.stderr}")

    return output_path
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_muxer.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/muxer.py backend/tests/test_muxer.py
git commit -m "feat: add FFmpeg stream-copy muxer with faststart"
```

### Task A3: Video Stream Endpoint

**Files:**
- Create: `backend/api/main.py`
- Create: `backend/api/routers/video.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_video_endpoint.py`

- [ ] **Step 1: Write shared test fixtures**

```python
# backend/tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport

from backend.api.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/test_video_endpoint.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_video_endpoint.py -v`
Expected: FAIL

- [ ] **Step 4: Implement FastAPI app and video router**

```python
# backend/api/main.py
from fastapi import FastAPI

from backend.api.routers import video

app = FastAPI(title="ShieldTube API", version="0.1.0")
app.include_router(video.router, prefix="/api")
```

```python
# backend/api/routers/video.py
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path

from backend.config import settings
from backend.services.stream_resolver import resolve_stream
from backend.services.muxer import mux_streams

router = APIRouter()


async def get_or_create_stream(video_id: str) -> Path:
    """Resolve, mux, and cache a video. Return path to cached MP4."""
    cache_path = Path(settings.cache_dir) / "videos" / f"{video_id}.mp4"

    if cache_path.exists():
        return cache_path

    stream_info = resolve_stream(video_id)
    mux_streams(
        video_url=stream_info["video_url"],
        audio_url=stream_info["audio_url"],
        output_path=cache_path,
    )
    return cache_path


@router.get("/video/{video_id}/stream")
async def stream_video(video_id: str, request: Request):
    """Serve video with HTTP range-request support."""
    video_path = await get_or_create_stream(video_id)
    file_size = video_path.stat().st_size

    range_header = request.headers.get("range")

    if range_header:
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        range_start = int(parts[0]) if parts[0] else 0
        range_end = int(parts[1]) if parts[1] else file_size - 1

        content_length = range_end - range_start + 1

        def iter_range():
            with open(video_path, "rb") as f:
                f.seek(range_start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_range(),
            status_code=206,
            headers={
                "Content-Range": f"bytes {range_start}-{range_end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": "video/mp4",
            },
        )

    return FileResponse(
        video_path,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )
```

- [ ] **Step 5: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/api/ backend/tests/conftest.py backend/tests/test_video_endpoint.py
git commit -m "feat: add video stream endpoint with HTTP range-request support"
```

### Task A4: Smoke Test

- [ ] **Step 1: Install deps and start server**

```bash
cd backend && pip install -r requirements.txt
uvicorn backend.api.main:app --host 0.0.0.0 --port 8080
```

- [ ] **Step 2: Verify with curl (separate terminal)**

```bash
# Full response
curl -I http://localhost:8080/api/video/dQw4w9WgXcQ/stream
# Expected: HTTP/1.1 200, Accept-Ranges: bytes, Content-Type: video/mp4

# Range request
curl -H "Range: bytes=0-1023" -I http://localhost:8080/api/video/dQw4w9WgXcQ/stream
# Expected: HTTP/1.1 206 Partial Content, Content-Range: bytes 0-1023/...
```

- [ ] **Step 3: Fix any issues, commit**

```bash
git add -u
git commit -m "fix: smoke test fixes for stream endpoint"
```

---

## Workstream B: Shield App Skeleton (Parallel — Worktree)

**Isolation:** Git worktree branched from scaffolding commit
**Dispatched as:** Background agent with worktree isolation
**Completion Promise:** `SHIELD APP SKELETON COMPLETE`

### Agent Dispatch Prompt

```markdown
You are building the ShieldTube Android TV app — Phase 1 walking skeleton.
Your job is to create a minimal Leanback app that plays a hardcoded video URL via ExoPlayer
with HDR passthrough.

**Read for context:**
- `docs/ShieldTube_PRD.md` sections: Component 1 (Android TV App), LG OLED Integration

**What to build:**

1. `shield-app/` Gradle project (Kotlin DSL)
   - Root `build.gradle.kts` + `settings.gradle.kts` + `gradle.properties`
   - App module `app/build.gradle.kts` with dependencies:
     - `androidx.leanback:leanback:1.0.0`
     - `androidx.media3:media3-exoplayer:1.2.1`
     - `androidx.media3:media3-ui:1.2.1`
   - Target/compile SDK 34, min SDK 31

2. `AndroidManifest.xml`
   - Declare `android.software.leanback` (required feature)
   - Declare `android.hardware.touchscreen` as NOT required
   - Internet permission
   - Banner icon (use placeholder)

3. `MainActivity.kt`
   - Launches PlaybackFragment immediately (no browse UI in Phase 1)
   - Full-screen, no action bar

4. `player/PlaybackFragment.kt`
   - ExoPlayer with `DefaultRenderersFactory` in `EXTENSION_RENDERER_MODE_ON`
   - HDR surface mode: set `SurfaceView` with `setSecure(false)`
   - Hardcoded URL: `http://192.168.1.100:8080/api/video/dQw4w9WgXcQ/stream`
   - Backend host as a `companion object` constant (easy to change)
   - Basic play/pause via D-pad center button

**Success criteria:**
- `./gradlew build` succeeds with no errors
- `./gradlew lint` has no errors (warnings OK)
- App declares correct Leanback features in manifest
- ExoPlayer configured for HDR passthrough

**Constraints:**
- Kotlin only (no Java)
- Media3 ExoPlayer (not legacy ExoPlayer)
- No browse/search UI yet — just the player
- Backend URL as a constant, not hardcoded in multiple places
- Commit after each component (gradle setup, manifest+activity, player)

**Iterate until the build succeeds. Output <promise>SHIELD APP SKELETON COMPLETE</promise> when done.**
```

### Task B1: Gradle Project Setup

**Files:**
- Create: `shield-app/build.gradle.kts`
- Create: `shield-app/settings.gradle.kts`
- Create: `shield-app/gradle.properties`
- Create: `shield-app/app/build.gradle.kts`

- [ ] **Step 1: Write root `build.gradle.kts`**

```kotlin
// shield-app/build.gradle.kts
plugins {
    id("com.android.application") version "8.2.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.22" apply false
}
```

- [ ] **Step 2: Write `settings.gradle.kts`**

```kotlin
// shield-app/settings.gradle.kts
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.STANDARD)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "ShieldTube"
include(":app")
```

- [ ] **Step 3: Write `gradle.properties`**

```properties
android.useAndroidX=true
kotlin.code.style=official
org.gradle.jvmargs=-Xmx2048m
```

- [ ] **Step 4: Write `app/build.gradle.kts`**

```kotlin
// shield-app/app/build.gradle.kts
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.shieldtube"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.shieldtube"
        minSdk = 31
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.leanback:leanback:1.0.0")

    // Media3 ExoPlayer
    implementation("androidx.media3:media3-exoplayer:1.2.1")
    implementation("androidx.media3:media3-ui:1.2.1")

    testImplementation("junit:junit:4.13.2")
}
```

- [ ] **Step 5: Verify build**

Run: `cd shield-app && ./gradlew build`
Expected: BUILD SUCCESSFUL

- [ ] **Step 6: Commit**

```bash
git add shield-app/
git commit -m "chore: scaffold Shield app Gradle project with ExoPlayer deps"
```

### Task B2: Manifest + MainActivity

**Files:**
- Create: `shield-app/app/src/main/AndroidManifest.xml`
- Create: `shield-app/app/src/main/java/com/shieldtube/MainActivity.kt`
- Create: `shield-app/app/src/main/res/values/strings.xml`

- [ ] **Step 1: Write AndroidManifest.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />

    <uses-feature
        android:name="android.software.leanback"
        android:required="true" />
    <uses-feature
        android:name="android.hardware.touchscreen"
        android:required="false" />

    <application
        android:allowBackup="true"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@style/Theme.Leanback">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:configChanges="orientation|screenSize|screenLayout|smallestScreenSize">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LEANBACK_LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

- [ ] **Step 2: Write strings.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">ShieldTube</string>
</resources>
```

- [ ] **Step 3: Write MainActivity.kt**

```kotlin
// shield-app/app/src/main/java/com/shieldtube/MainActivity.kt
package com.shieldtube

import android.os.Bundle
import androidx.fragment.app.FragmentActivity
import com.shieldtube.player.PlaybackFragment

class MainActivity : FragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) {
            supportFragmentManager.beginTransaction()
                .replace(android.R.id.content, PlaybackFragment())
                .commit()
        }
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add shield-app/app/src/main/
git commit -m "feat: add MainActivity with Leanback manifest"
```

### Task B3: PlaybackFragment with ExoPlayer HDR

**Files:**
- Create: `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt`

- [ ] **Step 1: Write PlaybackFragment**

```kotlin
// shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt
package com.shieldtube.player

import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

class PlaybackFragment : Fragment() {

    companion object {
        const val BACKEND_HOST = "http://192.168.1.100:8080"
        const val VIDEO_ID = "dQw4w9WgXcQ"
    }

    private var player: ExoPlayer? = null
    private var playerView: PlayerView? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        playerView = PlayerView(requireContext()).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        return playerView!!
    }

    override fun onStart() {
        super.onStart()
        initPlayer()
    }

    override fun onStop() {
        super.onStop()
        releasePlayer()
    }

    private fun initPlayer() {
        val renderersFactory = DefaultRenderersFactory(requireContext())
            .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON)

        player = ExoPlayer.Builder(requireContext(), renderersFactory)
            .build()
            .also { exoPlayer ->
                playerView?.player = exoPlayer

                val streamUrl = "$BACKEND_HOST/api/video/$VIDEO_ID/stream"
                val mediaItem = MediaItem.fromUri(Uri.parse(streamUrl))
                exoPlayer.setMediaItem(mediaItem)
                exoPlayer.playWhenReady = true
                exoPlayer.prepare()
            }
    }

    private fun releasePlayer() {
        player?.release()
        player = null
    }
}
```

- [ ] **Step 2: Verify build**

Run: `cd shield-app && ./gradlew build`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Commit**

```bash
git add shield-app/app/src/main/java/com/shieldtube/player/
git commit -m "feat: add ExoPlayer PlaybackFragment with HDR renderer"
```

---

## Task C: Docker Infrastructure (Sequential — After Workstream A)

**Depends on:** Workstream A merged
**Files:**
- Create: `backend/Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir yt-dlp

WORKDIR /app

# Copy backend into /app/backend/ so module path backend.api.main works
COPY requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . ./backend/

EXPOSE 8080
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Write docker-compose.yml**

```yaml
# docker-compose.yml
version: '3.8'
services:
  shieldtube-api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    volumes:
      - ./cache:/app/cache
    environment:
      - CACHE_DIR=/app/cache
      - FFMPEG_THREADS=${FFMPEG_THREADS:-2}
    restart: unless-stopped
```

- [ ] **Step 3: Test Docker build**

```bash
docker build -t shieldtube/api:latest backend/
docker-compose up -d
curl -I http://localhost:8080/docs
# Expected: HTTP/1.1 200 OK (Swagger UI)
docker-compose down
```

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile docker-compose.yml
git commit -m "feat: add Docker infrastructure for backend"
```

---

## Task I: Integration — Merge and Verify

### I1: Merge Worktrees

- [ ] **Step 1: Review Workstream A** (spec compliance + code quality)
- [ ] **Step 2: Merge Workstream A branch into main**
- [ ] **Step 3: Review Workstream B** (spec compliance + code quality)
- [ ] **Step 4: Merge Workstream B branch into main** (no conflicts — different directories)
- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -v
```

- [ ] **Step 6: Verify Shield app builds**

```bash
cd shield-app && ./gradlew build
```

- [ ] **Step 7: Commit merge if needed**

### I2: End-to-End Verification

- [ ] **Step 1: Start backend**

```bash
docker-compose up -d
```

- [ ] **Step 2: Install Shield app on device**

```bash
cd shield-app && ./gradlew installDebug
```

- [ ] **Step 3: Verify playback**

Open ShieldTube on Shield TV. Video should begin playing within 5 seconds.

**Check:**
- [ ] Video plays (not just audio)
- [ ] HDR metadata passthrough (TV should switch to HDR mode if video is HDR)
- [ ] Seek works (D-pad left/right)
- [ ] Play/pause works (D-pad center)

**PRD success criteria:** A video plays on the TV in ≤ 5 seconds from cold start.

- [ ] **Step 4: Commit any final fixes**

```bash
git add -u
git commit -m "feat: Phase 1 Walking Skeleton complete"
```

---

## Parallel Dispatch Summary

| Workstream | Agent Type | Worktree Branch | Completion Promise | Depends On |
|---|---|---|---|---|
| A: Backend Engine | Implementation | `ws/backend-stream-engine` | `BACKEND STREAM ENGINE COMPLETE` | Task 0 |
| B: Shield App | Implementation | `ws/shield-app-skeleton` | `SHIELD APP SKELETON COMPLETE` | Task 0 |
| C: Docker | Implementation | main | N/A | Workstream A |
| I: Integration | Orchestrator | main | N/A | A + B + C |

**Orchestrator flow:**
1. Execute Task 0 (scaffolding) on main
2. Dispatch Workstreams A and B in parallel (separate worktrees)
3. When A completes → review → merge → execute Task C
4. When B completes → review → merge
5. Execute Task I (end-to-end verification)
