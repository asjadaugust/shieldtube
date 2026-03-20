# Phase 2a: Backend Browse API — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 2: Browse Experience
**Depends on:** Phase 1 Walking Skeleton (complete)

---

## Goal

Backend serves real YouTube feeds (Home, Subscriptions, Search) with thumbnails from local cache, authenticated via a bootstrapped OAuth token. Shield app is not modified in this phase.

**Success criteria:** `curl` the Home feed endpoint → get video metadata with local thumbnail URLs → click a video → it plays (using Phase 1 stream endpoint).

---

## Architecture

```
Shield App (unchanged from Phase 1)
       │
       ▼
┌──────────────────────────────────────────────┐
│  FastAPI Backend                              │
│                                               │
│  /api/auth/login ──► OAuth Device Flow        │
│  /api/auth/callback                           │
│                                               │
│  /api/feed/home ──────►┐                      │
│  /api/feed/subscriptions►  YouTube API v3     │
│  /api/search?q= ──────►┘  (ETag cached)      │
│                             │                 │
│  /api/video/:id/thumbnail   │                 │
│         │                   ▼                 │
│         ▼              ┌─────────┐            │
│  Thumbnail Cache       │ SQLite  │            │
│  (local disk)          │ (aio)   │            │
│                        └─────────┘            │
│                                               │
│  Existing Phase 1:                            │
│  /api/video/:id/stream (yt-dlp + FFmpeg)      │
└──────────────────────────────────────────────┘
```

---

## Components

6 components, built in this order. Components 1-3 are independent and can be built in parallel. Components 4-6 integrate them sequentially.

### Component 1: SQLite Schema + DB Layer

**Purpose:** Persistent storage for video metadata, feed cache, thumbnails, and auth tokens.

**Files:**
- `backend/db/database.py` — aiosqlite connection management, migration runner
- `backend/db/models.py` — dataclasses for Video, FeedCache, Thumbnail, AuthToken
- `backend/db/migrations/001_initial_schema.sql` — schema creation
- `backend/db/repositories.py` — CRUD operations for each table

**Schema:**

```sql
CREATE TABLE videos (
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

CREATE TABLE feed_cache (
    feed_type TEXT PRIMARY KEY,
    video_ids_json TEXT NOT NULL,
    etag TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE thumbnails (
    video_id TEXT NOT NULL,
    resolution TEXT NOT NULL,
    local_path TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT,
    PRIMARY KEY (video_id, resolution)
);

CREATE TABLE auth_tokens (
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

**Design decisions:**
- Single-user: `auth_tokens` has only one row (`id=1`).
- `feed_cache.feed_type` uses format `home`, `subscriptions`, `search:{query}` for search cache keying.
- `video_ids_json` stores display order as a JSON array of video IDs, referencing the `videos` table.
- All timestamps are ISO 8601 strings (SQLite has no native datetime).
- `cache_status` enum: `none`, `downloading`, `cached`, `error`.

### Component 2: YouTube API v3 Client

**Purpose:** Async wrapper around YouTube Data API v3 with ETag caching and `part` parameter batching.

**Files:**
- `backend/services/youtube_api.py` — YouTubeAPI class with all API methods
- `backend/services/auth_manager.py` — token loading, refresh, header injection

**Methods:**
- `get_home_feed(max_results=20)` — Uses `videos.list` with `chart=mostPopular` and `regionCode`. Returns video list. Cost: 1 unit per call. Note: YouTube does not expose its personalized Home feed algorithm via the Data API; `mostPopular` is the closest approximation.
- `get_subscriptions(max_results=20)` — Uses `subscriptions.list` to get channel IDs, then `activities.list` with `publishedAfter` filter for recent uploads. Cost: 2 units per call.
- `search(query, max_results=20)` — Uses `search.list`. Cost: 100 units per call.
- `get_video_details(video_ids: list[str])` — Uses `videos.list` with comma-joined IDs. Fetches `snippet,contentDetails,statistics` in one call (batched `part` parameter). Cost: 1 unit per call regardless of how many IDs (up to 50).

**ETag caching:**
- Before each API call, check `feed_cache` for an existing ETag for this feed type.
- If found, send `If-None-Match: {etag}` header.
- If YouTube returns 304 Not Modified: return cached feed from SQLite at zero quota cost.
- If YouTube returns 200: parse response, update `feed_cache` with new ETag, upsert `videos` table.

**Auth:**
- `auth_manager.py` loads token from SQLite `auth_tokens` table or falls back to `YOUTUBE_ACCESS_TOKEN` env var (bootstrap mode).
- If `expires_at` is past and `refresh_token` exists, refresh automatically via Google OAuth token endpoint.
- Injects `Authorization: Bearer {token}` header on every API call.

**Quota awareness:**
- Each method documents its quota cost.
- No quota tracking counter in this phase (deferred to Phase 4).

### Component 3: Thumbnail Caching Pipeline

**Purpose:** Download and locally cache video thumbnails for fast LAN serving.

**Files:**
- `backend/services/thumbnail_cache.py` — download, store, serve thumbnails

**Behavior:**
- `cache_thumbnails(videos: list[Video])` — Background-downloads thumbnails for a list of videos. Downloads `maxres` (1280x720) for browse grids. Stores at `{CACHE_DIR}/thumbnails/{video_id}_maxres.jpg`.
- Uses `httpx.AsyncClient` for parallel downloads (up to 10 concurrent).
- Upserts `thumbnails` table with local path and content hash.
- Updates `videos.thumbnail_path` with the local path.
- Idempotent: skips videos that already have cached thumbnails (checks `thumbnails` table).

**Serving:**
- Thumbnail endpoint: `GET /api/video/{video_id}/thumbnail?res=maxres`
- Returns `FileResponse` with appropriate `Content-Type` and cache headers.
- If thumbnail not cached yet, returns 302 redirect to YouTube CDN URL as fallback.

### Component 4: Feed Endpoints

**Purpose:** HTTP endpoints that tie together YouTube API client, SQLite, and thumbnail caching.

**Files:**
- `backend/api/routers/feed.py` — feed endpoints
- `backend/api/routers/search.py` — search endpoint

**Endpoints:**

`GET /api/feed/home`
1. Call `youtube_api.get_home_feed()` (ETag-cached).
2. If fresh data: upsert videos into SQLite, trigger `cache_thumbnails()` in background.
3. Return normalized JSON with local thumbnail URLs.

`GET /api/feed/subscriptions`
1. Call `youtube_api.get_subscriptions()` (ETag-cached).
2. Same upsert + thumbnail caching flow.
3. Return normalized JSON.

`GET /api/search?q={query}`
1. Call `youtube_api.search(query)`.
2. Call `youtube_api.get_video_details()` for full metadata (search results are sparse).
3. Upsert + thumbnail cache.
4. Return normalized JSON.

**Response format:**

```json
{
  "feed_type": "home",
  "videos": [
    {
      "id": "dQw4w9WgXcQ",
      "title": "Never Gonna Give You Up",
      "channel_name": "Rick Astley",
      "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
      "view_count": 1500000000,
      "duration": 212,
      "published_at": "2009-10-25T06:57:33Z",
      "thumbnail_url": "/api/video/dQw4w9WgXcQ/thumbnail?res=maxres"
    }
  ],
  "cached_at": "2026-03-20T14:30:00Z",
  "from_cache": false
}
```

### Component 5: Token Bootstrap

**Purpose:** Allow development and testing with a manually-obtained OAuth token before the device flow is built.

**Files:**
- Modify: `backend/config.py` — add `YOUTUBE_ACCESS_TOKEN`, `YOUTUBE_REFRESH_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` settings

**Behavior:**
- On first startup, if `YOUTUBE_ACCESS_TOKEN` env var is set and `auth_tokens` table is empty, insert the token into SQLite.
- `auth_manager.py` always reads from SQLite. The env var is a one-time bootstrap only.
- Supports refresh via `YOUTUBE_REFRESH_TOKEN` + `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`.

**How to obtain a bootstrap token:**
1. Go to [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)
2. Authorize scopes: `youtube.readonly`, `youtube.force-ssl`
3. Exchange for access + refresh tokens
4. Set in `.env`: `YOUTUBE_ACCESS_TOKEN=...` and `YOUTUBE_REFRESH_TOKEN=...`

### Component 6: OAuth Device Flow

**Purpose:** Production auth for TV devices. User sees a code on screen, authorizes on phone.

**Files:**
- `backend/api/routers/auth.py` — auth endpoints
- `backend/services/device_flow.py` — Google OAuth device flow implementation

**Endpoints:**

`GET /api/auth/login`
1. POST to `https://oauth2.googleapis.com/device/code` with client_id and scopes.
2. Return `{ "device_code": "...", "user_code": "ABCD-EFGH", "verification_url": "https://www.google.com/device", "expires_in": 1800, "interval": 5 }`.

`GET /api/auth/callback?device_code={device_code}`
1. Poll `https://oauth2.googleapis.com/token` with the provided device_code.
2. Handle states: `authorization_pending`, `slow_down`, `access_denied`, `expired_token`.
3. On success: store access_token + refresh_token in `auth_tokens` table.
4. Return `{ "status": "authorized" }` or `{ "status": "pending" }`.

**Required scopes:** `youtube.readonly`, `youtube.force-ssl`, `openid`, `email`

---

## New Config Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `GOOGLE_CLIENT_ID` | OAuth app ID from Google Cloud Console | Yes (for device flow and token refresh) |
| `GOOGLE_CLIENT_SECRET` | OAuth app secret | Yes (for device flow and token refresh) |
| `YOUTUBE_ACCESS_TOKEN` | Bootstrap token from OAuth Playground | No (alternative to device flow) |
| `YOUTUBE_REFRESH_TOKEN` | Bootstrap refresh token | No (enables token refresh in bootstrap mode) |
| `YOUTUBE_API_KEY` | API key for unauthenticated fallback | No (future use) |
| `THUMBNAIL_CONCURRENCY` | Max parallel thumbnail downloads | No (default: 10) |

---

## Parallel Workstream Strategy

Same as Phase 1: parallel worktree agents for independent components.

```
Task 0: Config + DB migration setup (sequential)
        │
        ├── Workstream A: SQLite DB layer (worktree)
        ├── Workstream B: YouTube API client (worktree)
        └── Workstream C: Thumbnail cache (worktree)
                │
        Task 4: Feed endpoints (sequential, integrates A+B+C)
        Task 5: Token bootstrap (sequential)
        Task 6: OAuth device flow (sequential)
```

Components 1-3 touch entirely different files and have no shared dependencies beyond the DB schema (which is set up in Task 0).

---

## Testing Strategy

- **Component 1 (DB):** Test CRUD operations with in-memory SQLite.
- **Component 2 (YouTube API):** Mock httpx responses with recorded YouTube API fixtures. Test ETag caching flow (304 vs 200). Test token refresh.
- **Component 3 (Thumbnails):** Mock httpx for downloads. Test idempotency, concurrent download limits, fallback redirect.
- **Component 4 (Feed endpoints):** Integration tests with mocked YouTube API + real SQLite. Verify response format, caching behavior, thumbnail URL generation.
- **Component 5 (Bootstrap):** Test env var → SQLite insertion. Test refresh flow.
- **Component 6 (Device flow):** Mock Google OAuth endpoints. Test polling states, token storage, error handling.

---

## What This Phase Does NOT Include

- Shield app changes (deferred to Phase 2b)
- Watch history or playback position tracking (Phase 3)
- RSS fallback for subscriptions (Phase 4)
- Quota tracking counter (Phase 4)
- Feed background refresh (Phase 4)
- Token encryption at rest (Phase 4 — Security layer)
