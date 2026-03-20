# ShieldTube

A self-hosted YouTube frontend for NVIDIA Shield TV. Authenticates with your Google account, mirrors the full YouTube browse experience, and plays videos natively on your LG OLED TV with HDR/Dolby Vision support via progressive downloading.

Your network. Your cache. Your rules. YouTube's content.

---

## Table of Contents

- [Why ShieldTube](#why-shieldtube)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Security](#security)
- [Deployment](#deployment)
- [Development](#development)
- [Project Structure](#project-structure)
- [License](#license)

---

## Why ShieldTube

YouTube's native Shield app is a black box. You can't control quality fallback logic, cache videos for flaky networks, skip sponsor segments server-side, or integrate with your own media stack. The ads are getting worse. The app is getting slower.

ShieldTube gives you back control:

- **No ads.** SponsorBlock integration skips sponsor segments automatically.
- **Full HDR.** ExoPlayer with hardware decoding passes HDR10+/Dolby Vision metadata directly to your display.
- **Offline-first.** Pre-cache videos from your favorite channels on your NAS for instant playback.
- **Your data stays yours.** Self-hosted, LAN-only, single-user. Nothing leaves your network except YouTube API calls.

---

## Features

### Browsing
- Home feed, Subscriptions, Watch Later — mirrored from your YouTube account
- Full-text search with thumbnail previews
- Watch history with resume position tracking

### Playback
- Progressive download with instant playback start (< 3 seconds)
- HDR10+ and Dolby Vision passthrough via ExoPlayer
- Quality selection (Auto/4K HDR/4K/1080p/720p)
- Playback speed controls (0.5x - 2.0x)
- Chapter markers with D-pad navigation (long-press left/right)
- SponsorBlock auto-skip (sponsor, intro, outro segments)
- Subtitle/CC selection with multiple languages

### Infrastructure
- Background download queue with pre-caching rules
- Thumbnail caching with content-hash deduplication
- Web dashboard for system monitoring and cache management
- Phone-to-TV casting (browse on phone, play on Shield)
- Periodic yt-dlp auto-updates (weekly)
- OAuth token encryption at rest (Fernet)
- Shared-secret API authentication
- HTTPS with self-signed certificates
- GitHub Actions CI pipeline

---

## Architecture

```
                    YOUR LOCAL NETWORK
    ┌───────────────────────────────────────────────────┐
    │                                                   │
    │  ┌──────────────┐    HTTPS    ┌────────────────┐  │
    │  │ NVIDIA       │◄──────────►│ Backend Server  │  │
    │  │ Shield TV    │            │ (FastAPI/Python) │  │
    │  │              │            │                  │  │
    │  │ Leanback UI  │            │ YouTube API v3   │  │
    │  │ + ExoPlayer  │            │ yt-dlp + FFmpeg  │  │
    │  └──────┬───────┘            │ SQLite + Cache   │  │
    │         │ HDMI 2.1           └────────┬─────────┘  │
    │  ┌──────▼───────┐                     │            │
    │  │ LG OLED TV   │                     │ HTTPS      │
    │  │ (Display)    │                     ▼            │
    │  └──────────────┘            YouTube / Google      │
    │                              APIs + CDN            │
    └───────────────────────────────────────────────────┘
```

**Two independent codebases communicating via HTTP API:**

| Component | Stack | Role |
|-----------|-------|------|
| `backend/` | Python 3.11, FastAPI, SQLite, yt-dlp, FFmpeg | The brain. Handles auth, API proxying, stream resolution, caching, downloads. |
| `shield-app/` | Kotlin, Android TV Leanback, ExoPlayer | Thin client. Browses feeds, plays video. All state lives on the backend. |

### Playback Pipeline

```
User clicks thumbnail
    → Backend resolves stream via yt-dlp
    → FFmpeg muxes video + audio (stream copy, no transcode)
    → Backend serves via HTTP with range-request support
    → ExoPlayer plays from local URL
    → Download manager caches segments ahead of playback
```

---

## Prerequisites

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Backend runtime |
| FFmpeg | 6.0+ | Stream muxing (VP9/AV1/HDR10+ support) |
| Android SDK | API 31+ | Shield app build |
| JDK | 17 | Kotlin compilation |
| Google OAuth credentials | — | YouTube Data API access |

**Hardware targets:**
- **Synology NAS** — always-on, low-power (set `FFMPEG_THREADS=2`)
- **Laptop/Desktop with WSL2** — powerful, temporary sessions (higher thread count)

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-username/shieldtube.git
cd shieldtube
pip install -r backend/requirements.txt
```

### 2. Configure environment

```bash
cp config/.env.example .env
```

Edit `.env` with your credentials (see [Configuration](#configuration)).

### 3. Generate TLS certificate

```bash
bash config/generate-cert.sh
```

### 4. Start the backend

```bash
uvicorn backend.api.main:app \
    --host 0.0.0.0 --port 8443 \
    --ssl-keyfile config/certs/key.pem \
    --ssl-certfile config/certs/cert.pem
```

### 5. Build and deploy the Shield app

```bash
cd shield-app
./gradlew installDebug    # with Shield connected via ADB
```

### 6. Verify

```bash
# Should return the dashboard
curl -k https://localhost:8443/dashboard/

# Should return 401 (if API_SECRET is set)
curl -k https://localhost:8443/api/feed/home

# Should return feed data
curl -k -H "X-ShieldTube-Secret: your-secret" https://localhost:8443/api/feed/home
```

---

## Configuration

### Environment Variables

Create a `.env` file in the project root (see `config/.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | — | OAuth app ID from [Google Cloud Console](https://console.cloud.google.com/) |
| `GOOGLE_CLIENT_SECRET` | Yes | — | OAuth app secret |
| `BACKEND_HOST` | No | `0.0.0.0` | Server bind address |
| `BACKEND_PORT` | No | `8080` | Server port (HTTPS uses 8443) |
| `CACHE_DIR` | No | `./cache` | Video cache directory |
| `FFMPEG_THREADS` | No | `2` | FFmpeg parallelism (2 for NAS, higher for laptop) |
| `API_SECRET` | No | — | Shared secret for API auth. Empty = dev mode (no auth). |
| `TOKEN_ENCRYPTION_KEY` | No | — | Fernet key for encrypting OAuth tokens in SQLite. |
| `YOUTUBE_ACCESS_TOKEN` | No | — | Bootstrap token (alternative to device flow) |
| `YOUTUBE_REFRESH_TOKEN` | No | — | Bootstrap refresh token |

### Generating a Token Encryption Key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **YouTube Data API v3**
4. Create OAuth 2.0 credentials (Application type: **TVs and Limited Input devices**)
5. Add scopes: `youtube.readonly`, `youtube.force-ssl`, `openid`, `email`
6. Copy `Client ID` and `Client Secret` into your `.env`

### Shield App Configuration

Set the backend URL and API secret in `shield-app/gradle.properties`:

```properties
API_SECRET=your-shared-secret
```

The backend host is configured in:
- `shield-app/.../api/ApiClient.kt` — `BASE_URL`
- `shield-app/.../player/PlaybackFragment.kt` — `BACKEND_HOST`

---

## API Reference

All endpoints require the `X-ShieldTube-Secret` header when `API_SECRET` is configured.

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/auth/login` | Initiate OAuth device flow (exempt from auth) |
| `GET` | `/api/auth/callback` | Token exchange (exempt from auth) |

### Feeds

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/feed/home` | YouTube Home feed |
| `GET` | `/api/feed/subscriptions` | Subscriptions feed |
| `GET` | `/api/feed/history` | Watch history |
| `GET` | `/api/feed/watch-later` | Watch Later queue |

### Video

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/video/:id/meta` | Video metadata, chapters, resume position |
| `GET` | `/api/video/:id/stream` | Resolve and serve stream (`?quality=4K_HDR`) |
| `GET` | `/api/video/:id/thumbnail` | Cached thumbnail |
| `GET` | `/api/video/:id/formats` | Available quality formats |
| `GET` | `/api/video/:id/subtitles` | Available subtitle tracks |
| `GET` | `/api/video/:id/subtitles/:lang` | Subtitle file (WebVTT) |
| `POST` | `/api/video/:id/download` | Queue for background download |
| `GET` | `/api/video/:id/progress` | Download progress |
| `POST` | `/api/video/:id/progress` | Report playback position |

### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/search?q=<query>` | Search YouTube |

### Cache

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/cache/status` | Cache disk usage |
| `DELETE` | `/api/cache/:id` | Evict cached video |

### SponsorBlock

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sponsorblock/:id` | Community-sourced sponsor segments |

### Cast

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/cast/play` | Send video to Shield from phone |
| `GET` | `/api/cast/now-playing` | Current cast state |

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/dashboard/` | Web dashboard (exempt from auth) |
| `GET` | `/api/dashboard/status` | System status JSON |
| `GET` | `/api/dashboard/precache-rules` | Pre-cache rule list |
| `POST` | `/api/dashboard/precache-rules` | Create pre-cache rule |

---

## Security

### Shared-Secret Authentication

All API requests must include the `X-ShieldTube-Secret` header matching the `API_SECRET` environment variable. Exempt paths: `/docs`, `/dashboard/*`, `/api/auth/login`, `/api/auth/callback`.

When `API_SECRET` is empty, authentication is disabled (dev mode).

### Token Encryption

OAuth access and refresh tokens are encrypted at rest using Fernet symmetric encryption when `TOKEN_ENCRYPTION_KEY` is configured. Graceful fallback handles pre-encryption plaintext tokens during migration.

### HTTPS

The backend serves over HTTPS using a self-signed certificate. Generate one with:

```bash
bash config/generate-cert.sh
```

The Shield app's `network_security_config.xml` trusts user-installed CAs, allowing the self-signed cert. See [docs/deployment/https-setup.md](docs/deployment/https-setup.md) for details.

### Design Constraints

- **Single user, single household.** No multi-user auth or RBAC.
- **LAN-only by default.** Not designed for internet exposure.
- **No transcoding.** Shield has hardware decoders — FFmpeg uses stream copy only.

---

## Deployment

### Docker

```bash
# Generate TLS cert first
bash config/generate-cert.sh

# Build and run
docker-compose up -d
```

The API serves on `https://localhost:8443`.

```yaml
# docker-compose.yml mounts:
# - ./cache:/app/cache          (video cache)
# - ./config/certs:/app/config/certs:ro  (TLS certificates)
```

### Docker Build Only

```bash
docker build -t shieldtube/api:latest backend/
```

### Manual

```bash
pip install -r backend/requirements.txt
uvicorn backend.api.main:app \
    --host 0.0.0.0 --port 8443 \
    --ssl-keyfile config/certs/key.pem \
    --ssl-certfile config/certs/cert.pem
```

---

## Development

### Backend

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run with hot reload (HTTP, no TLS)
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8080

# Run all tests (234 tests)
pytest backend/tests/ -v

# Run a specific test file
pytest backend/tests/test_auth.py

# Run a single test
pytest backend/tests/test_auth.py::test_device_flow -v
```

### Shield App

```bash
cd shield-app

# Build
./gradlew build

# Run tests
./gradlew test

# Deploy to Shield (connected via ADB)
./gradlew installDebug
```

### CI

GitHub Actions runs on every push and PR to `main`:
- **backend-tests:** Python 3.11, pytest
- **android-build:** JDK 17, Gradle build

---

## Project Structure

```
shieldtube/
├── backend/
│   ├── api/
│   │   ├── main.py                 # FastAPI app, lifespan, middleware
│   │   ├── middleware.py           # Shared-secret auth middleware
│   │   └── routers/
│   │       ├── auth.py             # OAuth device flow
│   │       ├── feed.py             # Home, Subscriptions, History
│   │       ├── video.py            # Stream, metadata, thumbnails
│   │       ├── search.py           # YouTube search proxy
│   │       ├── cache.py            # Cache management
│   │       ├── watch.py            # Watch history & progress
│   │       ├── cast.py             # Phone-to-TV casting
│   │       └── dashboard.py        # Dashboard API
│   ├── db/
│   │   ├── database.py             # SQLite init & connection
│   │   ├── models.py               # Data models
│   │   └── repositories.py         # Async CRUD with encryption
│   ├── services/
│   │   ├── auth_manager.py         # OAuth token management
│   │   ├── download_manager.py     # Progressive download engine
│   │   ├── download_queue.py       # Background download queue
│   │   ├── feed_refresher.py       # Periodic feed updates
│   │   ├── stream_resolver.py      # yt-dlp stream extraction
│   │   ├── token_crypto.py         # Fernet token encryption
│   │   └── ytdlp_updater.py        # Weekly yt-dlp auto-update
│   ├── dashboard/                  # Web dashboard (HTML/CSS/JS)
│   ├── tests/                      # 234 pytest tests
│   ├── Dockerfile
│   └── requirements.txt
├── shield-app/
│   ├── app/src/main/java/com/shieldtube/
│   │   ├── api/
│   │   │   ├── ApiClient.kt        # Retrofit + OkHttp with auth
│   │   │   ├── ShieldTubeApi.kt    # API interface
│   │   │   └── models.kt           # Data classes
│   │   ├── player/
│   │   │   ├── PlaybackFragment.kt # ExoPlayer with HDR, chapters, SponsorBlock
│   │   │   └── ChapterNavigator.kt # Pure Kotlin chapter navigation
│   │   └── ui/
│   │       ├── BrowseFragment.kt   # Leanback browse (Home/Subs/Watch Later)
│   │       ├── CardPresenter.kt    # Video card rendering
│   │       └── SearchFragment.kt   # Voice & text search
│   └── app/src/test/               # Unit tests (JUnit, Robolectric)
├── config/
│   ├── .env.example                # Environment template
│   └── generate-cert.sh            # Self-signed TLS cert generator
├── docs/
│   ├── ShieldTube_PRD.md           # Product Requirements Document
│   └── deployment/
│       └── https-setup.md          # HTTPS setup guide
├── .github/workflows/test.yml     # CI pipeline
├── docker-compose.yml
└── CLAUDE.md                       # AI assistant instructions
```

---

## Key External Dependencies

| Dependency | Purpose | Notes |
|------------|---------|-------|
| [YouTube Data API v3](https://developers.google.com/youtube/v3) | Feeds, search, metadata | 10,000 units/day free quota |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Stream URL extraction | Auto-updated weekly; pinned to 2025.01.15 |
| [FFmpeg 6.0+](https://ffmpeg.org/) | Stream muxing | VP9/AV1/HDR10+ support, stream copy only |
| [ExoPlayer (Media3)](https://developer.android.com/media/media3) | Android playback | HDR10+/Dolby Vision passthrough |
| [SponsorBlock](https://sponsor.ajay.app/) | Sponsor segment skipping | Community-sourced, free API |

---

## Remote Control

The Shield app maps D-pad controls for 10-foot UI navigation:

| Action | Control |
|--------|---------|
| Browse feeds | D-pad up/down/left/right |
| Select video | D-pad center / Enter |
| Play/Pause | D-pad center |
| Seek | D-pad left/right |
| Next chapter | Long-press D-pad right |
| Previous chapter | Long-press D-pad left |
| Subtitles | Long-press D-pad down |
| Speed control | Long-press D-pad up |
| Quality selection | Menu button |
| Back | Back button |
| Search | Search icon on browse screen |

---

## License

This project is for personal use. Not affiliated with Google or YouTube.
