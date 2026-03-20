# Phase 2a: Backend Browse API — Implementation Plan

> **For agentic workers:** This plan uses Ralph Loop methodology with parallel sub-agents in git worktrees. Use `superpowers:dispatching-parallel-agents` to run Workstreams A, B, and C concurrently. Each agent iterates toward its completion promise.

**Goal:** Backend serves real YouTube feeds (Home, Subscriptions, Search) with locally cached thumbnails, authenticated via bootstrapped OAuth token.

**Architecture:** YouTube API v3 client with ETag caching → normalized video metadata in SQLite → thumbnail pipeline downloads images to local disk → feed endpoints assemble everything into JSON responses. Token bootstrap for dev, full OAuth device flow for production.

**Tech Stack:** Python 3.11+, FastAPI, aiosqlite, httpx, pydantic-settings (all already in requirements.txt)

---

## Execution Model

```
Task 0: Config + DB migration scaffolding (sequential)
        │
        ├── Workstream A: SQLite DB layer (worktree)
        ├── Workstream B: YouTube API client + auth manager (worktree)
        └── Workstream C: Thumbnail cache (worktree)
                │
        Task 4: Feed endpoints (sequential, integrates A+B+C)
        Task 5: Token bootstrap (sequential)
        Task 6: OAuth device flow (sequential)
```

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/db/__init__.py` | Package marker |
| `backend/db/database.py` | aiosqlite connection pool, migration runner, startup/shutdown |
| `backend/db/models.py` | Dataclasses: Video, FeedCache, Thumbnail, AuthToken |
| `backend/db/migrations/001_initial_schema.sql` | CREATE TABLE statements |
| `backend/db/repositories.py` | CRUD: VideoRepo, FeedCacheRepo, ThumbnailRepo, AuthTokenRepo |
| `backend/services/youtube_api.py` | YouTubeAPI class: get_home_feed, get_subscriptions, search, get_video_details |
| `backend/services/auth_manager.py` | AuthManager: load token, refresh, inject headers |
| `backend/services/thumbnail_cache.py` | ThumbnailCache: download, store, serve, fallback |
| `backend/api/routers/feed.py` | GET /api/feed/home, GET /api/feed/subscriptions |
| `backend/api/routers/search.py` | GET /api/search?q= |
| `backend/api/routers/auth.py` | GET /api/auth/login, GET /api/auth/callback |
| `backend/services/device_flow.py` | Google OAuth device flow: request code, poll token |

### Modified Files

| File | Changes |
|------|---------|
| `backend/config.py` | Add GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, YOUTUBE_ACCESS_TOKEN, YOUTUBE_REFRESH_TOKEN, THUMBNAIL_CONCURRENCY |
| `backend/api/main.py` | Register feed, search, auth routers; add lifespan for DB init/shutdown |

### Test Files

| File | Tests |
|------|-------|
| `backend/tests/test_database.py` | Migration runner, connection management |
| `backend/tests/test_repositories.py` | CRUD for all 4 repos |
| `backend/tests/test_youtube_api.py` | API methods, ETag caching (304 vs 200), error handling |
| `backend/tests/test_auth_manager.py` | Token load, refresh, header injection |
| `backend/tests/test_thumbnail_cache.py` | Download, idempotency, concurrency, fallback |
| `backend/tests/test_feed_endpoints.py` | Home, subscriptions integration |
| `backend/tests/test_search_endpoint.py` | Search integration |
| `backend/tests/test_device_flow.py` | Device code request, polling states, token storage |

---

## Task 0: Config + DB Migration Scaffolding (Sequential)

**Files:**
- Modify: `backend/config.py`
- Create: `backend/db/__init__.py`
- Create: `backend/db/migrations/001_initial_schema.sql`
- Create: `backend/db/database.py` (minimal — connection + migration runner only)

- [ ] **Step 1: Update config.py with new settings**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    cache_dir: str = "./cache"
    ffmpeg_threads: int = 2
    db_path: str = "./shieldtube.db"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Bootstrap token (alternative to device flow)
    youtube_access_token: str = ""
    youtube_refresh_token: str = ""

    # Thumbnail settings
    thumbnail_concurrency: int = 10

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 2: Create DB package and migration SQL**

```sql
-- backend/db/migrations/001_initial_schema.sql
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    view_count INTEGER,
    duration INTEGER,
    published_at TEXT,
    description TEXT,
    thumbnail_path TEXT,
    cached_video_path TEXT,
    cache_status TEXT DEFAULT 'none',
    last_accessed TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feed_cache (
    feed_type TEXT PRIMARY KEY,
    video_ids_json TEXT NOT NULL,
    etag TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thumbnails (
    video_id TEXT NOT NULL,
    resolution TEXT NOT NULL,
    local_path TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT,
    PRIMARY KEY (video_id, resolution)
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY DEFAULT 1,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type TEXT DEFAULT 'Bearer',
    expires_at TEXT,
    scopes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 3: Create minimal database.py (connection + migration)**

```python
# backend/db/database.py
import aiosqlite
from pathlib import Path

from backend.config import settings

_db: aiosqlite.Connection | None = None
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def get_db() -> aiosqlite.Connection:
    """Get the shared database connection."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def init_db() -> None:
    """Open connection and run migrations."""
    global _db
    _db = await aiosqlite.connect(settings.db_path)
    _db.row_factory = aiosqlite.Row
    await _run_migrations(_db)


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Run all SQL migration files in order."""
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = sql_file.read_text()
        await db.executescript(sql)
    await db.commit()
```

- [ ] **Step 4: Create __init__.py**

```bash
touch backend/db/__init__.py
mkdir -p backend/db/migrations
```

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/db/
git commit -m "chore: add Phase 2a config settings and DB migration scaffolding"
```

---

## Workstream A: SQLite DB Layer (Parallel — Worktree)

**Isolation:** Git worktree branched from Task 0 commit
**Completion Promise:** `DB LAYER COMPLETE`

### Agent Dispatch Prompt

```markdown
You are implementing the SQLite DB layer for ShieldTube Phase 2a.

**Read these files first:**
- `backend/db/database.py` — already has init_db, close_db, get_db, migration runner
- `backend/db/migrations/001_initial_schema.sql` — the schema
- `backend/config.py` — settings including db_path

**What to build (TDD):**

1. `backend/db/models.py` — Python dataclasses matching the SQL schema:
   - `Video(id, title, channel_name, channel_id, view_count, duration, published_at, description, thumbnail_path, cached_video_path, cache_status, last_accessed, created_at, updated_at)`
   - `FeedCache(feed_type, video_ids_json, etag, fetched_at)` — with a `video_ids` property that parses JSON
   - `Thumbnail(video_id, resolution, local_path, fetched_at, content_hash)`
   - `AuthToken(id, access_token, refresh_token, token_type, expires_at, scopes, created_at, updated_at)` — with an `is_expired` property
   - All fields use `str | None` for optional fields. Use `@dataclass` not pydantic.

2. `backend/db/repositories.py` — Async repository classes, each takes a `db: aiosqlite.Connection`:
   - `VideoRepo`:
     - `upsert(video: Video)` — INSERT OR REPLACE
     - `upsert_many(videos: list[Video])` — batch upsert
     - `upsert_many_from_dicts(videos: list[dict])` — convert dicts to Video objects and batch upsert (convenience for feed endpoints)
     - `get(video_id: str) -> Video | None`
     - `get_many(video_ids: list[str]) -> list[Video]` — preserves input order
   - `FeedCacheRepo`:
     - `get(feed_type: str) -> FeedCache | None`
     - `upsert(feed_cache: FeedCache)`
   - `ThumbnailRepo`:
     - `get(video_id: str, resolution: str) -> Thumbnail | None`
     - `upsert(thumbnail: Thumbnail)`
     - `get_cached_ids(video_ids: list[str], resolution: str) -> set[str]` — returns IDs that already have cached thumbnails
   - `AuthTokenRepo`:
     - `get() -> AuthToken | None` — always reads id=1
     - `upsert(token: AuthToken)` — always writes id=1

3. `backend/tests/test_database.py` — Test init_db creates tables, migration is idempotent
4. `backend/tests/test_repositories.py` — Test all CRUD operations with in-memory SQLite (`:memory:`)

**Success criteria:**
- `python -m pytest backend/tests/test_database.py backend/tests/test_repositories.py -v` — ALL pass
- Every repo method has at least one test
- `get_many` preserves input order
- `upsert` is idempotent (insert then update same ID)
- `get_cached_ids` correctly filters

**Constraints:**
- Use `aiosqlite.Row` for row_factory (already set in database.py)
- All repo methods are `async`
- Dataclasses use `from __future__ import annotations` for `str | None` syntax
- Commit after models, then after repositories+tests

Output <promise>DB LAYER COMPLETE</promise> when all tests pass.
```

---

## Workstream B: YouTube API Client + Auth Manager (Parallel — Worktree)

**Isolation:** Git worktree branched from Task 0 commit
**Completion Promise:** `YOUTUBE API CLIENT COMPLETE`

### Agent Dispatch Prompt

```markdown
You are implementing the YouTube API v3 client and auth manager for ShieldTube Phase 2a.

**Read these files first:**
- `backend/config.py` — settings including google_client_id, google_client_secret, youtube_access_token
- `backend/db/database.py` — get_db() returns aiosqlite connection

**What to build (TDD):**

1. `backend/services/auth_manager.py` — AuthManager class:
   - `__init__(self, db: aiosqlite.Connection)` — stores db reference
   - `async get_token(self) -> str` — loads access_token from auth_tokens table (id=1). If expired and refresh_token exists, refreshes via POST to `https://oauth2.googleapis.com/token`. Falls back to `settings.youtube_access_token` env var if DB is empty.
   - `async refresh_token(self, refresh_token: str) -> dict` — POSTs to Google token endpoint with grant_type=refresh_token, returns new access_token + expires_in.
   - `async get_auth_headers(self) -> dict` — returns `{"Authorization": f"Bearer {token}"}`.
   - Uses `httpx.AsyncClient` for HTTP calls.

2. `backend/services/youtube_api.py` — YouTubeAPI class:
   - `__init__(self, auth_manager: AuthManager, db: aiosqlite.Connection)` — stores references
   - `async get_home_feed(self, max_results: int = 20) -> tuple[list[dict], bool, str | None]`:
     - Returns `(videos, from_cache, cached_at)` — videos is list of dicts, from_cache is True if ETag cache hit, cached_at is ISO timestamp or None
     - Check FeedCacheRepo for feed_type="home", get ETag if exists
     - GET `https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,statistics&chart=mostPopular&regionCode=US&maxResults={max_results}`
     - Send `If-None-Match: {etag}` header if we have one
     - If 304: load cached video IDs from feed_cache, return `(videos, True, fetched_at)`
     - If 200: parse response, update feed_cache, return `(videos, False, None)`
   - `async get_subscriptions(self, max_results: int = 20) -> tuple[list[dict], bool, str | None]`:
     - GET `https://www.googleapis.com/youtube/v3/subscriptions?part=snippet&mine=true&maxResults=50`
     - Extract channel IDs
     - GET `https://www.googleapis.com/youtube/v3/activities?part=snippet,contentDetails&channelId={id}&publishedAfter={24h_ago}&maxResults={max_results}`
     - Collect video IDs from activities, call get_video_details()
   - `async search(self, query: str, max_results: int = 20) -> list[dict]`:
     - GET `https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&type=video&maxResults={max_results}`
     - Extract video IDs from results
     - Call get_video_details() for full metadata
   - `async get_video_details(self, video_ids: list[str]) -> list[dict]`:
     - GET `https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,statistics&id={comma_joined_ids}`
     - Parse into normalized video dicts: `{id, title, channel_name, channel_id, view_count, duration, published_at, description}`
     - Parse ISO 8601 duration (PT4M33S → 273 seconds)
   - All methods use `httpx.AsyncClient` with auth headers from AuthManager.

3. `backend/tests/test_auth_manager.py`:
   - Test get_token from DB
   - Test get_token falls back to env var
   - Test refresh_token calls Google endpoint
   - Test get_token auto-refreshes when expired
   - Mock httpx for all network calls

4. `backend/tests/test_youtube_api.py`:
   - Test get_home_feed parses YouTube response correctly
   - Test get_home_feed ETag cache hit (304 response)
   - Test get_video_details parses duration correctly
   - Test search calls get_video_details for enrichment
   - Mock httpx for all YouTube API calls with realistic fixtures

**Important: DB repositories are being built in parallel by another agent. You cannot import from `backend.db.repositories`. Instead, write your YouTube API methods to accept and return plain dicts. The integration with repositories happens in Task 4 (Feed endpoints). Your ETag caching should use the DB connection directly with raw SQL for now:**

```python
# For ETag reads:
row = await db.execute("SELECT etag, video_ids_json FROM feed_cache WHERE feed_type = ?", (feed_type,))
# For ETag writes:
await db.execute("INSERT OR REPLACE INTO feed_cache (feed_type, video_ids_json, etag, fetched_at) VALUES (?, ?, ?, ?)", ...)
```

**Success criteria:**
- `python -m pytest backend/tests/test_auth_manager.py backend/tests/test_youtube_api.py -v` — ALL pass
- ETag caching flow tested (304 and 200 paths)
- Duration parsing tested (PT4M33S, PT1H2M3S, PT30S)
- Token refresh flow tested
- All network calls mocked (no real YouTube API hits)

**Constraints:**
- Use `httpx.AsyncClient` (already in requirements.txt)
- Parse ISO 8601 duration manually (no external lib) — regex is fine
- Commit after auth_manager, then after youtube_api+tests

Output <promise>YOUTUBE API CLIENT COMPLETE</promise> when all tests pass.
```

---

## Workstream C: Thumbnail Cache (Parallel — Worktree)

**Isolation:** Git worktree branched from Task 0 commit
**Completion Promise:** `THUMBNAIL CACHE COMPLETE`

### Agent Dispatch Prompt

```markdown
You are implementing the thumbnail caching pipeline for ShieldTube Phase 2a.

**Read these files first:**
- `backend/config.py` — settings including cache_dir, thumbnail_concurrency
- `backend/db/database.py` — get_db() returns aiosqlite connection
- `backend/api/routers/video.py` — existing video router (you'll add thumbnail endpoint here or in a new file)

**What to build (TDD):**

1. `backend/services/thumbnail_cache.py` — ThumbnailCache class:
   - `__init__(self, db: aiosqlite.Connection)` — stores db ref
   - `async cache_thumbnails(self, videos: list[dict]) -> None`:
     - Input: list of video dicts with at least `id` and thumbnail URLs
     - Check which video IDs already have cached thumbnails (query thumbnails table)
     - For uncached videos, download `maxres` thumbnail (1280x720) from YouTube
     - YouTube thumbnail URL pattern: `https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg`
     - Fall back to `hqdefault.jpg` if maxres returns 404
     - Save to `{CACHE_DIR}/thumbnails/{video_id}_maxres.jpg`
     - Use `httpx.AsyncClient` with `asyncio.Semaphore(settings.thumbnail_concurrency)` for parallel downloads
     - Upsert into thumbnails table and update videos.thumbnail_path
     - Idempotent: skip videos that already have cached thumbnails
   - `async get_thumbnail_path(self, video_id: str, resolution: str = "maxres") -> Path | None`:
     - Query thumbnails table for local_path
     - Return Path if file exists, None otherwise
   - `get_youtube_thumbnail_url(self, video_id: str, resolution: str = "maxres") -> str`:
     - Returns the YouTube CDN URL for fallback redirect

2. `backend/api/routers/video.py` — Add thumbnail endpoint to existing router:
   - `GET /video/{video_id}/thumbnail` with optional `res` query param (default: "maxres")
   - If thumbnail cached locally: return `FileResponse` with content-type image/jpeg
   - If not cached: return `RedirectResponse(status_code=302)` to YouTube CDN URL

3. `backend/tests/test_thumbnail_cache.py`:
   - Test cache_thumbnails downloads and stores files
   - Test idempotency (second call skips already-cached)
   - Test maxres 404 fallback to hqdefault
   - Test concurrency limit (semaphore)
   - Test get_thumbnail_path returns None for uncached
   - Test thumbnail endpoint returns FileResponse for cached
   - Test thumbnail endpoint returns 302 redirect for uncached
   - Mock httpx for all downloads

**Important: DB repositories are built in parallel. Use raw SQL for DB operations:**
```python
# Check cached:
rows = await db.execute_fetchall("SELECT video_id FROM thumbnails WHERE video_id IN (...) AND resolution = ?", ...)
# Upsert thumbnail:
await db.execute("INSERT OR REPLACE INTO thumbnails (video_id, resolution, local_path, fetched_at) VALUES (?, ?, ?, ?)", ...)
# Update video:
await db.execute("UPDATE videos SET thumbnail_path = ? WHERE id = ?", ...)
```

**Success criteria:**
- `python -m pytest backend/tests/test_thumbnail_cache.py -v` — ALL pass
- Thumbnail files actually written to disk in tests (use tmp_path)
- Concurrency limited to settings.thumbnail_concurrency
- 302 fallback works for uncached thumbnails

**Constraints:**
- Use `asyncio.Semaphore` for concurrency control
- Use `hashlib.md5` for content_hash
- Thumbnail dir: `{CACHE_DIR}/thumbnails/`
- Commit after thumbnail_cache service, then after endpoint+tests

Output <promise>THUMBNAIL CACHE COMPLETE</promise> when all tests pass.
```

---

## Task 4: Feed Endpoints (Sequential — After Workstreams A+B+C)

**Depends on:** All three workstreams merged
**Files:**
- Create: `backend/api/routers/feed.py`
- Create: `backend/api/routers/search.py`
- Modify: `backend/api/main.py` — register new routers, add DB lifespan
- Create: `backend/tests/test_feed_endpoints.py`
- Create: `backend/tests/test_search_endpoint.py`

- [ ] **Step 1: Update main.py with lifespan and new routers**

```python
# backend/api/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

from backend.db.database import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(title="ShieldTube API", version="0.2.0", lifespan=lifespan)

from backend.api.routers import video, feed, search, auth  # noqa: E402

app.include_router(video.router, prefix="/api")
app.include_router(feed.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
```

- [ ] **Step 2: Write feed.py router**

```python
# backend/api/routers/feed.py
import asyncio
from fastapi import APIRouter

from backend.db.database import get_db
from backend.db.repositories import VideoRepo, FeedCacheRepo
from backend.services.youtube_api import YouTubeAPI
from backend.services.auth_manager import AuthManager
from backend.services.thumbnail_cache import ThumbnailCache

router = APIRouter()


async def _build_feed_response(feed_type: str, videos: list[dict], from_cache: bool, cached_at: str | None = None):
    """Build normalized feed response with local thumbnail URLs."""
    return {
        "feed_type": feed_type,
        "videos": [
            {
                "id": v["id"],
                "title": v["title"],
                "channel_name": v["channel_name"],
                "channel_id": v["channel_id"],
                "view_count": v.get("view_count"),
                "duration": v.get("duration"),
                "published_at": v.get("published_at"),
                "thumbnail_url": f"/api/video/{v['id']}/thumbnail?res=maxres",
            }
            for v in videos
        ],
        "cached_at": cached_at,
        "from_cache": from_cache,
    }


@router.get("/feed/home")
async def home_feed():
    db = await get_db()
    auth = AuthManager(db)
    api = YouTubeAPI(auth, db)
    thumb = ThumbnailCache(db)
    video_repo = VideoRepo(db)

    videos, from_cache, cached_at = await api.get_home_feed()

    if not from_cache:
        await video_repo.upsert_many_from_dicts(videos)
        asyncio.create_task(thumb.cache_thumbnails(videos))

    return await _build_feed_response("home", videos, from_cache, cached_at)


@router.get("/feed/subscriptions")
async def subscriptions_feed():
    db = await get_db()
    auth = AuthManager(db)
    api = YouTubeAPI(auth, db)
    thumb = ThumbnailCache(db)
    video_repo = VideoRepo(db)

    videos, from_cache, cached_at = await api.get_subscriptions()

    if not from_cache:
        await video_repo.upsert_many_from_dicts(videos)
        asyncio.create_task(thumb.cache_thumbnails(videos))

    return await _build_feed_response("subscriptions", videos, from_cache, cached_at)
```

- [ ] **Step 3: Write search.py router**

```python
# backend/api/routers/search.py
import asyncio
from fastapi import APIRouter, Query

from backend.db.database import get_db
from backend.db.repositories import VideoRepo
from backend.services.youtube_api import YouTubeAPI
from backend.services.auth_manager import AuthManager
from backend.services.thumbnail_cache import ThumbnailCache

router = APIRouter()


@router.get("/search")
async def search_videos(q: str = Query(..., min_length=1)):
    db = await get_db()
    auth = AuthManager(db)
    api = YouTubeAPI(auth, db)
    thumb = ThumbnailCache(db)
    video_repo = VideoRepo(db)

    videos = await api.search(q)
    await video_repo.upsert_many_from_dicts(videos)
    asyncio.create_task(thumb.cache_thumbnails(videos))

    return {
        "feed_type": f"search:{q}",
        "videos": [
            {
                "id": v["id"],
                "title": v["title"],
                "channel_name": v["channel_name"],
                "channel_id": v["channel_id"],
                "view_count": v.get("view_count"),
                "duration": v.get("duration"),
                "published_at": v.get("published_at"),
                "thumbnail_url": f"/api/video/{v['id']}/thumbnail?res=maxres",
            }
            for v in videos
        ],
        "cached_at": None,
        "from_cache": False,
    }
```

- [ ] **Step 4: Write tests for feed and search endpoints**

Mock the YouTubeAPI and ThumbnailCache at the router level. Test:
- Home feed returns correct JSON shape
- Subscriptions feed returns correct JSON shape
- Search requires `q` parameter (422 without it)
- Search returns correct JSON shape
- `thumbnail_url` uses local path pattern `/api/video/{id}/thumbnail?res=maxres`
- `from_cache` is True when ETag cache hits

- [ ] **Step 5: Run all tests**

Run: `python -m pytest backend/tests/ -v`
Expected: ALL pass (existing Phase 1 tests + new tests)

- [ ] **Step 6: Commit**

```bash
git add backend/api/
git commit -m "feat: add feed and search endpoints with YouTube API integration"
```

---

## Task 5: Token Bootstrap (Sequential)

**Files:**
- Modify: `backend/api/main.py` — add bootstrap logic to lifespan
- Create: `backend/tests/test_token_bootstrap.py`

- [ ] **Step 1: Add bootstrap to lifespan**

```python
# In backend/api/main.py lifespan, after init_db():
from backend.db.database import get_db
from backend.db.repositories import AuthTokenRepo
from backend.db.models import AuthToken
from backend.config import settings
from datetime import datetime, timezone

# Inside the lifespan function, between init_db() and yield:
    await init_db()
    # Bootstrap token from env var if DB is empty
    if settings.youtube_access_token:
        db = await get_db()
        repo = AuthTokenRepo(db)
        existing = await repo.get()
        if not existing:
            await repo.upsert(AuthToken(
                id=1,
                access_token=settings.youtube_access_token,
                refresh_token=settings.youtube_refresh_token or None,
                token_type="Bearer",
                expires_at=None,
                scopes="youtube.readonly youtube.force-ssl",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            ))
    yield
    await close_db()
```

- [ ] **Step 2: Write tests**

Test that:
- With `YOUTUBE_ACCESS_TOKEN` set and empty DB → token inserted
- With `YOUTUBE_ACCESS_TOKEN` set and existing token → no overwrite
- Without `YOUTUBE_ACCESS_TOKEN` → no insertion

- [ ] **Step 3: Commit**

```bash
git add backend/api/main.py backend/tests/test_token_bootstrap.py
git commit -m "feat: add OAuth token bootstrap from env var"
```

---

## Task 6: OAuth Device Flow (Sequential)

**Files:**
- Create: `backend/services/device_flow.py`
- Create: `backend/api/routers/auth.py`
- Create: `backend/tests/test_device_flow.py`

- [ ] **Step 1: Implement device flow service**

```python
# backend/services/device_flow.py
import httpx
from backend.config import settings

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "openid email https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube.force-ssl"


async def request_device_code() -> dict:
    """Request a device code from Google OAuth."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(DEVICE_CODE_URL, data={
            "client_id": settings.google_client_id,
            "scope": SCOPES,
        })
        resp.raise_for_status()
        return resp.json()


async def poll_for_token(device_code: str) -> dict:
    """Poll Google for token exchange. Returns status dict."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })

        data = resp.json()

        if "error" in data:
            return {"status": data["error"]}

        return {
            "status": "authorized",
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in"),
            "token_type": data.get("token_type", "Bearer"),
        }
```

- [ ] **Step 2: Implement auth router**

```python
# backend/api/routers/auth.py
from fastapi import APIRouter, Query
from datetime import datetime, timezone, timedelta

from backend.db.database import get_db
from backend.db.repositories import AuthTokenRepo
from backend.db.models import AuthToken
from backend.services.device_flow import request_device_code, poll_for_token

router = APIRouter()


@router.get("/auth/login")
async def auth_login():
    """Initiate OAuth device flow. Returns code for user to enter."""
    data = await request_device_code()
    return {
        "device_code": data["device_code"],
        "user_code": data["user_code"],
        "verification_url": data["verification_url"],
        "expires_in": data["expires_in"],
        "interval": data.get("interval", 5),
    }


@router.get("/auth/callback")
async def auth_callback(device_code: str = Query(...)):
    """Poll for token. Shield app calls this repeatedly until authorized."""
    result = await poll_for_token(device_code)

    if result["status"] == "authorized":
        db = await get_db()
        repo = AuthTokenRepo(db)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=result["expires_in"])).isoformat() if result.get("expires_in") else None

        await repo.upsert(AuthToken(
            id=1,
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token"),
            token_type=result.get("token_type", "Bearer"),
            expires_at=expires_at,
            scopes="youtube.readonly youtube.force-ssl openid email",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        ))

    return {"status": result["status"]}
```

- [ ] **Step 3: Write tests**

Mock `request_device_code` and `poll_for_token`. Test:
- `/api/auth/login` returns device_code, user_code, verification_url
- `/api/auth/callback?device_code=X` with authorized response → stores token in DB
- `/api/auth/callback?device_code=X` with pending response → returns `{"status": "authorization_pending"}`
- `/api/auth/callback?device_code=X` with error → returns `{"status": "access_denied"}`

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest backend/tests/ -v`
Expected: ALL pass

- [ ] **Step 5: Commit**

```bash
git add backend/services/device_flow.py backend/api/routers/auth.py backend/tests/test_device_flow.py
git commit -m "feat: add OAuth device flow for TV authentication"
```

---

## Smoke Test

After all tasks complete:

- [ ] **Step 1: Set bootstrap token in .env**

```bash
echo "YOUTUBE_ACCESS_TOKEN=ya29.your_token_here" >> .env
```

- [ ] **Step 2: Start server**

```bash
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8080
```

- [ ] **Step 3: Test endpoints**

```bash
# Home feed
curl http://localhost:8080/api/feed/home | python -m json.tool

# Search
curl "http://localhost:8080/api/search?q=python+tutorial" | python -m json.tool

# Thumbnail (should redirect or serve cached)
curl -I http://localhost:8080/api/video/dQw4w9WgXcQ/thumbnail

# Auth login (requires GOOGLE_CLIENT_ID set)
curl http://localhost:8080/api/auth/login
```

---

## Parallel Dispatch Summary

| Workstream | Worktree Branch | Completion Promise | Depends On |
|---|---|---|---|
| A: SQLite DB Layer | `ws/db-layer` | `DB LAYER COMPLETE` | Task 0 |
| B: YouTube API Client | `ws/youtube-api` | `YOUTUBE API CLIENT COMPLETE` | Task 0 |
| C: Thumbnail Cache | `ws/thumbnail-cache` | `THUMBNAIL CACHE COMPLETE` | Task 0 |
| Task 4: Feed Endpoints | main | N/A | A + B + C |
| Task 5: Token Bootstrap | main | N/A | Task 4 |
| Task 6: OAuth Device Flow | main | N/A | Task 5 |

**Orchestrator flow:**
1. Execute Task 0 (config + DB scaffolding) on main
2. Dispatch Workstreams A, B, C in parallel (separate worktrees)
3. As each completes → review → merge
4. Execute Tasks 4, 5, 6 sequentially on main
5. Run full test suite + smoke test
