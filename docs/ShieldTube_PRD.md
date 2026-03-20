# PRD: ShieldTube — A Self-Hosted YouTube Frontend for NVIDIA Shield

**Author:** Asjad  
**Status:** Draft  
**Last Updated:** March 13, 2026  
**Target Platform:** NVIDIA Shield TV → LG OLED TV  
**Backend Hosts:** Synology NAS *or* Lenovo Laptop (32GB RAM / 8GB VRAM / WSL2)

---

## The One-Liner

A self-hosted YouTube client that runs on NVIDIA Shield, authenticates with your Google account, mirrors the full YouTube browse experience (thumbnails, recommendations, subscriptions, history), and on click — downloads the video progressively and plays it natively on your LG OLED TV with full HDR/Dolby Vision support.

---

## Why This Exists

YouTube's native Shield app is a black box. You can't control quality fallback logic, you can't cache videos for flaky networks, you can't skip sponsor segments server-side, you can't integrate with your own media stack, and you're one policy change away from losing features. The ads are getting worse. The app is getting slower. The recommendations are increasingly adversarial.

**ShieldTube gives you back control.** Your network. Your cache. Your rules. YouTube's content.

### The Core Bet

Google's data (your account, your subscriptions, your watch history) is the hard part — and they expose it via APIs. The playback infrastructure is the part we *can* own.

---

## Non-Goals (What This Is NOT)

- **Not a YouTube ripper or piracy tool.** This is a personal-use frontend for content you'd watch anyway through your authenticated account. Think of it as a better remote control, not a download farm.
- **Not a recommendation engine replacement.** We *consume* YouTube's recommendation API. We don't build our own ML model.
- **Not a multi-user platform.** Single Google account. Single household. Single Shield device.
- **Not a mobile app.** Shield TV and your LG OLED. That's the scope.
- **Not a real-time transcoding stack.** The Shield has hardware decoders for basically everything. We lean on those.

---

## User Stories

### P0 — Must Ship

| # | As a user, I want to...                                                                 | So that...                                                |
|---|------------------------------------------------------------------------------------------|-----------------------------------------------------------|
| 1 | Sign in with my Google account on the Shield UI                                          | I see my personalized YouTube feed                        |
| 2 | Browse my Home feed with video thumbnails, titles, channel names, and view counts         | I can pick what to watch the same way I do on YouTube     |
| 3 | Click a thumbnail and have the video start playing within 3 seconds                       | Playback feels instant, not like a download-then-play     |
| 4 | Have the video play on my LG OLED at the best available quality (4K HDR/DV if available)  | I get the quality my TV can handle                        |
| 5 | Browse my Subscriptions feed                                                             | I can see new uploads from channels I follow              |
| 6 | Search for videos                                                                        | I can find specific content                               |
| 7 | See my Watch History                                                                     | I can resume or re-watch content                          |

### P1 — Should Ship

| # | As a user, I want to...                                                         | So that...                                           |
|---|----------------------------------------------------------------------------------|------------------------------------------------------|
| 8 | Have videos pre-cached on my NAS/laptop for channels I watch frequently          | Playback is instant even on slow internet days        |
| 9 | Skip sponsor segments automatically (SponsorBlock integration)                   | I don't waste time on in-video ads                    |
| 10| See chapter markers and skip between them                                        | I can navigate long-form content efficiently          |
| 11| Control playback with my Shield remote (play, pause, seek, speed)                | Standard TV remote UX works                           |
| 12| Queue videos for download in the background                                      | I can batch content for later viewing                 |

### P2 — Nice to Have

| # | As a user, I want to...                                                        | So that...                                        |
|---|---------------------------------------------------------------------------------|---------------------------------------------------|
| 13| Cast from my phone to ShieldTube                                                | I can browse on my phone and send to the TV        |
| 14| See comments on a video                                                         | I get the community context                        |
| 15| Get subtitle/CC support with selectable languages                                | I can watch foreign content                        |
| 16| Have a "Watch Later" queue synced with my YouTube account                        | My workflow across devices is preserved             |

---

## System Architecture

### High-Level Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    YOUR LOCAL NETWORK                         │
│                                                              │
│  ┌─────────────┐         ┌──────────────────────────────┐    │
│  │ NVIDIA      │  HTTP   │  BACKEND SERVER               │    │
│  │ SHIELD TV   │◄───────►│  (Synology NAS or Lenovo/WSL2)│    │
│  │             │         │                               │    │
│  │ Leanback UI │         │  ┌─────────────────────────┐  │    │
│  │ (Android TV │         │  │ ShieldTube API Server    │  │    │
│  │  App)       │         │  │ (Node.js / FastAPI)      │  │    │
│  │             │         │  ├─────────────────────────┤  │    │
│  └──────┬──────┘         │  │ YouTube Data API v3     │  │    │
│         │                │  │ (feeds, search, meta)    │  │    │
│         │ HDMI 2.1       │  ├─────────────────────────┤  │    │
│  ┌──────▼──────┐         │  │ yt-dlp Stream Engine     │  │    │
│  │ LG OLED TV  │         │  │ (download + segment)     │  │    │
│  │ (Display)   │         │  ├─────────────────────────┤  │    │
│  └─────────────┘         │  │ Media Cache (local disk) │  │    │
│                          │  │ + SQLite metadata DB     │  │    │
│                          │  └─────────────────────────┘  │    │
│                          └──────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS (outbound only)
                                    ▼
                          ┌──────────────────┐
                          │  YouTube / Google │
                          │  APIs + CDN       │
                          └──────────────────┘
```

### Component Breakdown

#### 1. ShieldTube Android TV App (Frontend)

**Runtime:** Android TV (Leanback UI library)  
**Language:** Kotlin  
**Role:** Thin client. All intelligence lives on the backend.

The app is a browsing and playback shell. It calls the backend API for everything: feeds, thumbnails, search results, stream URLs. The app itself never talks to YouTube directly — the backend is the single gateway.

**Key modules:**

- **BrowseFragment (Leanback):** Renders rows of cards — Home, Subscriptions, Trending, Watch History. Each card shows a thumbnail (loaded via Glide/Coil from cached backend URLs), title, channel, view count, and duration badge.
- **SearchFragment:** Voice and text search. Query goes to the backend, which proxies to YouTube Data API v3.
- **PlaybackFragment:** ExoPlayer-based. Receives an HLS/DASH manifest URL or a direct MP4 stream URL from the backend. Handles adaptive bitrate, HDR metadata passthrough, and Dolby Vision profile switching.
- **OAuth Flow:** Android TV OAuth 2.0 device flow (TV shows a code, you authorize on your phone/laptop). Token stored in Android Keystore, refreshed server-side.
- **Remote Control Mapping:** D-pad navigation, play/pause/seek mapped to Shield remote and CEC (so your LG OLED remote works too).

**Why Leanback and not a web app?** Two reasons: (a) ExoPlayer gives you hardware-accelerated HDR playback with proper HDMI metadata signaling — a browser can't do this reliably on Shield, and (b) Leanback gives you native D-pad navigation, focus management, and the 10-foot UI patterns users expect on a TV.

#### 2. ShieldTube Backend API Server

**Runtime:** Node.js (Express/Fastify) or Python (FastAPI) — your call  
**Role:** The brain. Handles auth, API proxying, stream resolution, caching, and download orchestration.

**API Surface:**

```
GET  /api/auth/login          → Initiate Google OAuth device flow
GET  /api/auth/callback       → Handle token exchange
GET  /api/feed/home            → Proxied YouTube Home feed
GET  /api/feed/subscriptions   → Proxied Subscriptions feed
GET  /api/feed/history         → Watch History
GET  /api/search?q=<query>     → Search proxy
GET  /api/video/:id/meta       → Video metadata (title, desc, chapters, etc.)
GET  /api/video/:id/stream     → Resolve best stream URL (via yt-dlp)
GET  /api/video/:id/thumbnail  → Cached thumbnail (proxied + resized)
POST /api/video/:id/download   → Queue background download
GET  /api/video/:id/progress   → Download progress (SSE or WebSocket)
GET  /api/cache/status          → Cache disk usage and video list
DELETE /api/cache/:id           → Evict a cached video
GET  /api/sponsorblock/:id     → SponsorBlock segment data
```

**Authentication architecture:**

```
┌────────────┐    device code    ┌────────────┐   authorize   ┌─────────┐
│ Shield App │──────────────────►│  Backend   │◄─────────────│  User's  │
│            │                   │  Server    │   (phone/     │  Phone   │
│ shows code │◄──────────────────│            │    laptop)    └─────────┘
│ on TV      │   polling for     │ stores     │
│            │   token           │ OAuth      │
│            │                   │ tokens in  │
│            │   token granted   │ encrypted  │
│            │◄──────────────────│ SQLite     │
└────────────┘                   └────────────┘
```

We use Google's **OAuth 2.0 Device Flow** (RFC 8628). This is the same flow YouTube uses on smart TVs. The Shield app displays a short code, the user visits `google.com/device` on their phone, enters the code, and grants permissions. The backend receives and stores the access + refresh tokens. All subsequent YouTube API calls are made server-side with the user's token.

**Required Google API Scopes:**

- `youtube.readonly` — feed, subscriptions, search, history
- `youtube.force-ssl` — required for Data API v3
- `userinfo.email` — account identification

#### 3. Stream Resolution Engine (yt-dlp)

**This is the critical path.** When the user clicks a thumbnail, the backend must resolve the video into a playable stream in under 1 second.

**Flow:**

```
User clicks thumbnail
        │
        ▼
Shield App → GET /api/video/:id/stream
        │
        ▼
Backend checks cache:
  ├─ HIT  → Return local file URL (HTTP range-request capable)
  └─ MISS → yt-dlp resolves stream URLs from YouTube
              │
              ▼
        Select best format:
          Priority: VP9.2 (HDR) > VP9 > AV1 > H.264
          Audio:    Opus > AAC
          Quality:  4K > 1440p > 1080p (match TV capability)
              │
              ▼
        Two strategies (configurable):
          │
          ├─ PROXY MODE (default, low latency):
          │    Backend proxies the YouTube CDN stream
          │    to the Shield. Starts a background download
          │    simultaneously. Shield gets bytes immediately.
          │
          └─ DOWNLOAD-FIRST MODE (for pre-caching):
               yt-dlp downloads full file to local cache.
               Serves via local HTTP once enough is buffered.
```

**yt-dlp integration details:**

```python
# Stream URL resolution (< 500ms target)
import yt_dlp

def resolve_stream(video_id: str, prefer_hdr: bool = True) -> dict:
    opts = {
        'format': 'bestvideo[ext=webm][vcodec^=vp9]+bestaudio[ext=webm]/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'cookiefile': '/path/to/cookies.txt',  # From authenticated browser
    }
    
    if prefer_hdr:
        opts['format'] = (
            'bestvideo[vcodec=vp09.02][height<=2160]+bestaudio/  '
            'bestvideo[vcodec^=vp9][height<=2160]+bestaudio/'
            'bestvideo[height<=2160]+bestaudio/best'
        )
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f'https://www.youtube.com/watch?v={video_id}',
            download=False
        )
        return {
            'video_url': info['requested_formats'][0]['url'],
            'audio_url': info['requested_formats'][1]['url'],
            'duration': info['duration'],
            'title': info['title'],
            'formats': info['formats'],  # For fallback
        }
```

**Why yt-dlp instead of YouTube's IFrame/Player API?** The IFrame API doesn't give you stream URLs — it gives you an embedded player. We need raw stream URLs so ExoPlayer can handle hardware decoding, HDR metadata, and adaptive bitrate on the Shield's Tegra X1+ chip. yt-dlp extracts direct CDN URLs that ExoPlayer can consume.

**Cookie authentication:** yt-dlp uses exported browser cookies to access age-restricted and membership content. This runs through the same Google account as the OAuth token.

#### 4. Progressive Download + Playback Engine

This is what makes the "click and play" experience feel instant despite downloading.

**Strategy: Segmented Download with HTTP Range Requests**

```
┌──────────────────────────────────────────────────────────┐
│  Backend Download Manager                                 │
│                                                          │
│  Video: "How to Build a PC" (45 min, 2.1 GB)            │
│                                                          │
│  Segments:                                                │
│  [████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 28%       │
│   ▲                                                      │
│   └─ Downloaded so far (589 MB)                          │
│                                                          │
│  Playback position: 00:03:22 (segment 4 of 45)          │
│  Buffer ahead: 2 minutes                                  │
│  Download speed: 48 MB/s (local) / 12 MB/s (YouTube)    │
│                                                          │
│  Priority: Download segments around playback head first   │
│  Then: Fill forward. Then: Fill backward.                 │
└──────────────────────────────────────────────────────────┘
```

**How it works:**

1. **On click:** Backend resolves stream URL (< 1s). Immediately starts downloading the first 10MB (enough for ~30s of 4K video).
2. **Simultaneously:** Backend returns a local HTTP URL to the Shield app pointing at the partially-downloaded file.
3. **ExoPlayer** opens the local URL with range-request support. The backend's HTTP server responds with `Accept-Ranges: bytes` and `Content-Length` of the full file.
4. **As playback progresses:** The download manager prioritizes segments just ahead of the playback position. If the user seeks, the download manager reprioritizes.
5. **On completion:** Full file is cached on disk. Next play is pure local.

**Muxing strategy:** YouTube serves video and audio as separate streams (DASH). The backend muxes them on-the-fly using FFmpeg into a single MP4/MKV container that ExoPlayer can handle:

```bash
ffmpeg -i video_stream.webm -i audio_stream.webm \
  -c:v copy -c:a copy \
  -movflags +faststart+frag_keyframe \
  -f mp4 pipe:1
```

The `-movflags +faststart` is critical — it moves the moov atom to the beginning of the file so ExoPlayer can start playback before the download completes.

#### 5. Thumbnail + Metadata Cache Layer

**Problem:** YouTube's Home feed returns ~20-40 video recommendations. Each has a thumbnail, channel avatar, title, view count, and duration. Loading all of this on every feed refresh is slow and wastes bandwidth.

**Solution:** Aggressive local caching with background refresh.

```
┌─────────────────────────────────────────────────┐
│  SQLite Metadata DB                              │
│                                                  │
│  videos:                                         │
│    id, title, channel_name, channel_id,          │
│    view_count, duration, published_at,           │
│    thumbnail_path, description, chapters_json,   │
│    cached_video_path, cache_status,              │
│    last_accessed, sponsor_segments_json           │
│                                                  │
│  feed_cache:                                     │
│    feed_type (home/subs/trending),               │
│    video_ids_json, fetched_at, etag              │
│                                                  │
│  thumbnails:                                     │
│    video_id, resolution, local_path,             │
│    fetched_at, content_hash                      │
│                                                  │
│  watch_history:                                  │
│    video_id, watched_at, position_seconds,       │
│    completed                                     │
└─────────────────────────────────────────────────┘
```

**Thumbnail pipeline:**

1. YouTube Data API returns thumbnail URLs at multiple resolutions (`default`, `medium`, `high`, `standard`, `maxres`).
2. Backend downloads `maxres` (1280×720) for the browse grid and `high` (480×360) for search results.
3. Images are stored locally: `/cache/thumbnails/{video_id}_{resolution}.jpg`
4. Backend serves them via `/api/video/:id/thumbnail?res=maxres`
5. Shield app uses Glide/Coil with disk caching on the Shield itself (double-layer cache).

**Feed refresh cadence:**

- Home feed: Refresh every 15 minutes in background, serve stale immediately on open.
- Subscriptions: Refresh every 5 minutes (uses `activities` endpoint with `publishedAfter` filter for efficiency).
- History: Sync every 30 minutes or on app open.

#### 6. Media Cache Manager

**Storage locations (configurable):**

| Host                  | Path                               | Capacity        |
|-----------------------|------------------------------------|-----------------|
| Synology NAS          | `/volume1/shieldtube/cache/`       | Limited by NAS  |
| Lenovo Laptop (WSL2)  | `/mnt/d/shieldtube/cache/`         | Limited by disk |

**Eviction policy:** LRU with a configurable max cache size (default: 500GB). Videos unwatched for 30 days are evicted first. Favorited/pinned videos are never evicted.

**Pre-caching rules (P1 feature):**

```json
{
  "precache_rules": [
    {
      "type": "channel",
      "channel_id": "UC...",
      "max_videos": 5,
      "quality": "1080p",
      "trigger": "on_upload"
    },
    {
      "type": "playlist",
      "playlist_id": "PL...",
      "quality": "4K_HDR",
      "trigger": "nightly"
    }
  ]
}
```

---

## Host Environment Setup

### Option A: Synology NAS

**Pros:** Always on, low power, NAS-grade storage, Docker support.  
**Cons:** Weak CPU (no hardware transcoding for muxing), limited RAM.

```yaml
# docker-compose.yml (Synology)
version: '3.8'
services:
  shieldtube-api:
    image: shieldtube/api:latest
    ports:
      - "8080:8080"
    volumes:
      - /volume1/shieldtube/cache:/app/cache
      - /volume1/shieldtube/db:/app/db
      - /volume1/shieldtube/config:/app/config
    environment:
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - CACHE_MAX_SIZE_GB=500
      - FFMPEG_THREADS=2
    restart: unless-stopped

  shieldtube-downloader:
    image: shieldtube/downloader:latest
    volumes:
      - /volume1/shieldtube/cache:/app/cache
      - /volume1/shieldtube/db:/app/db
    depends_on:
      - shieldtube-api
    restart: unless-stopped
```

### Option B: Lenovo Laptop via WSL2

**Pros:** 32GB RAM, 8GB VRAM (GPU-accelerated FFmpeg muxing), faster yt-dlp extraction.  
**Cons:** Not always-on (unless you configure it to be), power consumption, fan noise.

```bash
# WSL2 Setup
wsl --install -d Ubuntu-24.04

# Inside WSL2:
sudo apt update && sudo apt install -y ffmpeg python3-pip nodejs npm
pip3 install yt-dlp fastapi uvicorn aiohttp aiosqlite
npm install -g pm2

# GPU passthrough for FFmpeg (NVENC muxing)
# Requires NVIDIA CUDA driver for WSL2
nvidia-smi  # Verify GPU visibility in WSL2

# Network: WSL2 needs port forwarding for Shield to reach it
# Add to Windows PowerShell (run as admin):
netsh interface portproxy add v4tov4 \
  listenport=8080 listenaddress=0.0.0.0 \
  connectport=8080 connectaddress=$(wsl hostname -I)
```

**Recommendation:** Start with the Lenovo laptop for development and testing. Once stable, deploy to Synology for production (always-on). Keep the laptop as a fallback for GPU-accelerated tasks.

---

## LG OLED Integration

The Shield connects to your LG OLED via HDMI 2.1. ShieldTube doesn't talk to the TV directly — it talks to the Shield, and the Shield handles display output. But there are TV-specific considerations:

**HDR/Dolby Vision passthrough:**

- Shield must be set to "Match content color space" in Display settings.
- ExoPlayer must signal HDR metadata via `MediaCodec` surface with `HDR_STATIC_INFO` or `HDR10_PLUS_INFO`.
- For Dolby Vision content (Profile 5/8), the Shield handles the RPU layer natively.

**CEC (HDMI-CEC) remote control:**

- LG's Magic Remote sends CEC commands to the Shield.
- ShieldTube's Leanback UI responds to standard CEC: D-pad, Enter, Back, Play/Pause.
- Volume is handled by the TV's ARC/eARC — ShieldTube doesn't touch audio routing.

**Resolution and refresh rate:**

- Shield auto-negotiates with the TV via EDID. ShieldTube tells ExoPlayer to request the best available format but lets the Shield handle the final display mode switching.
- For 24fps content (movies): Shield's "Match content frame rate" handles the switch. ShieldTube should tag content with its native framerate.

---

## API Rate Limits and Quotas

**YouTube Data API v3** has a daily quota of **10,000 units** (free tier). Each operation costs differently:

| Operation              | Cost   | Calls/day at 10K quota |
|------------------------|--------|------------------------|
| search.list            | 100    | 100                    |
| videos.list            | 1      | 10,000                 |
| channels.list          | 1      | 10,000                 |
| activities.list        | 1      | 10,000                 |
| playlistItems.list     | 1      | 10,000                 |

**Mitigation strategies:**

- **Batch requests:** YouTube API supports `part` parameter — fetch `snippet,contentDetails,statistics` in one call instead of three.
- **ETag caching:** YouTube API returns ETags. If the feed hasn't changed, the API returns 304 and costs 0 quota.
- **Subscriptions via RSS:** YouTube channel RSS feeds (`https://www.youtube.com/feeds/videos.xml?channel_id=X`) are free and don't count against quota. Use these for subscription polling.
- **Fallback to yt-dlp scraping:** If quota is exhausted, yt-dlp can extract feed data (slower, but zero API cost).
- **Apply for higher quota:** Google grants increased quotas for legitimate API projects. Apply via Google Cloud Console.

---

## Security Model

| Threat                          | Mitigation                                                                 |
|---------------------------------|---------------------------------------------------------------------------|
| OAuth token theft               | Stored in encrypted SQLite with OS-level file permissions. Refresh token encrypted at rest. |
| Man-in-the-middle on LAN        | Backend serves over HTTPS (self-signed cert, pinned in Shield app).        |
| yt-dlp cookie leakage           | Cookie file is 600 permissions, read only by the API process.              |
| Unauthorized LAN access         | API requires a shared secret header (configured during Shield app setup).  |
| YouTube API key exposure         | API key stored in environment variables, never in client code.             |
| Google account suspension risk   | Rate-limit yt-dlp calls. Use official API where possible. Respect robots.txt. |

---

## Milestone Plan

### Phase 1: Walking Skeleton (Weeks 1–3)

**Goal:** Click a hardcoded video ID on the Shield, it plays on the TV.

- [ ] Backend: FastAPI server with single endpoint `/api/video/:id/stream`
- [ ] Backend: yt-dlp resolves stream, FFmpeg muxes, serves via HTTP
- [ ] Shield: Minimal Android TV app with ExoPlayer, plays a single URL
- [ ] Infra: Docker container running on Lenovo/WSL2
- [ ] Verify: HDR passthrough to LG OLED works

**Success criteria:** A video plays on the TV in ≤ 5 seconds from cold start.

### Phase 2: Browse Experience (Weeks 4–6)

**Goal:** Real YouTube feed with thumbnails, click to play.

- [ ] Backend: Google OAuth device flow integration
- [ ] Backend: YouTube Data API v3 — Home feed, Subscriptions, Search
- [ ] Backend: Thumbnail caching pipeline
- [ ] Shield: Leanback BrowseFragment with card rows
- [ ] Shield: Glide image loading for thumbnails
- [ ] Shield: SearchFragment with voice input
- [ ] DB: SQLite schema for metadata and feed cache

**Success criteria:** Open app → see your real YouTube Home feed → click → it plays.

### Phase 3: Progressive Download (Weeks 7–9)

**Goal:** Instant-feeling playback with background caching.

- [ ] Backend: Segmented download manager with priority queue
- [ ] Backend: HTTP range-request server for partial files
- [ ] Backend: Background download worker (separate process/container)
- [ ] Shield: Playback progress reporting back to backend
- [ ] Shield: Resume from last position
- [ ] DB: Watch history and position tracking

**Success criteria:** Click-to-first-frame in ≤ 3 seconds. Seek works on partially-downloaded files.

### Phase 4: Polish + P1 Features (Weeks 10–13)

**Goal:** Daily-driver quality.

- [ ] SponsorBlock integration (skip segments automatically)
- [ ] Chapter markers in playback UI
- [ ] Pre-caching rules (auto-download from favorite channels)
- [ ] Cache management UI (on Shield + web dashboard)
- [ ] Feed background refresh with push notifications
- [ ] Synology NAS deployment and testing
- [ ] Error handling, retry logic, offline graceful degradation

**Success criteria:** You stop opening the YouTube app entirely.

### Phase 5: Extended Features (Weeks 14+)

- [ ] Watch Later queue sync
- [ ] Subtitle/CC support
- [ ] Phone → Shield casting (simple HTTP-based)
- [ ] Playback speed controls
- [ ] Multiple quality presets per video
- [ ] Web dashboard for cache management and configuration

---

## Tech Stack Summary

| Layer            | Technology                              | Why                                              |
|------------------|-----------------------------------------|--------------------------------------------------|
| Shield App       | Kotlin + Leanback + ExoPlayer           | Native Android TV. HDR passthrough. D-pad UX.     |
| Backend API      | Python (FastAPI) + uvicorn              | Async, fast, easy yt-dlp integration.             |
| Stream Engine    | yt-dlp + FFmpeg                         | Best YouTube extraction library. FFmpeg for mux.  |
| Database         | SQLite (aiosqlite)                      | Zero-config, embedded, plenty fast for single-user.|
| Cache Storage    | Local filesystem (NAS or laptop)        | Simple. HTTP range-request serving.               |
| Thumbnails       | Glide (Shield) + local HTTP cache       | Two-layer: backend disk + Shield memory.          |
| Auth             | Google OAuth 2.0 Device Flow            | Standard TV auth pattern. User approves on phone. |
| Containerization | Docker + Docker Compose                 | Portable between Synology and WSL2.               |
| Process Manager  | PM2 (dev) / Docker restart policies     | Keep services alive.                              |
| Sponsor Skip     | SponsorBlock API                        | Community-sourced. Free. Excellent coverage.       |

---

## Risks and Open Questions

### High Risk

| Risk                                                         | Impact   | Mitigation                                                         |
|--------------------------------------------------------------|----------|--------------------------------------------------------------------|
| Google blocks yt-dlp extraction for authenticated accounts    | Critical | Maintain cookie rotation. Fall back to lower quality. Watch yt-dlp GitHub for patches. |
| YouTube Data API quota exhaustion                             | High     | RSS fallback for subscriptions. ETag caching. Apply for quota increase. |
| ExoPlayer can't handle muxed-on-the-fly streams              | High     | Pre-mux a small buffer before serving. Test extensively in Phase 1. |

### Medium Risk

| Risk                                                         | Impact   | Mitigation                                                   |
|--------------------------------------------------------------|----------|--------------------------------------------------------------|
| WSL2 networking flakiness (port forwarding drops)             | Medium   | Use `wsl-vpnkit` or switch to Synology for production.        |
| Synology CPU too weak for FFmpeg muxing                       | Medium   | Use stream copy (no transcode). Offload to GPU laptop if needed. |
| LG OLED HDMI handshake issues with HDR switching              | Medium   | Lock Shield to a single output mode. Test per-TV model.       |

### Open Questions

1. **Should we use Invidious/Piped as an intermediary API instead of direct YouTube Data API?** Pro: no quota limits. Con: reliability depends on community instances.
2. **Can we get YouTube Music integration through the same auth flow?** Separate scope, separate API, but potentially same OAuth token.
3. **Is DASH manifest proxying viable for ExoPlayer instead of muxing?** Would avoid the FFmpeg step entirely if ExoPlayer can handle split video/audio DASH.
4. **Should we build a web UI (React) alongside the Shield app?** Could run in a browser on the TV directly, but loses HDR and remote UX.

---

## Appendix A: Key Dependencies and Versions

| Dependency     | Minimum Version | Notes                                                 |
|----------------|-----------------|-------------------------------------------------------|
| yt-dlp         | 2024.12+        | Frequent updates needed for YouTube changes            |
| FFmpeg         | 6.0+            | Needs `faststart` movflag, VP9/AV1 decode             |
| ExoPlayer      | 2.19+           | HDR10+ and Dolby Vision support                        |
| Android TV     | API 31+         | Leanback library compatibility                         |
| Python         | 3.11+           | Async improvements                                     |
| Node.js        | 20 LTS          | If choosing Node backend                               |
| Docker         | 24+             | Compose V2                                             |
| SQLite         | 3.40+           | JSON functions for metadata queries                    |

## Appendix B: Directory Structure

```
shieldtube/
├── backend/
│   ├── api/
│   │   ├── main.py                 # FastAPI app entry
│   │   ├── routers/
│   │   │   ├── auth.py             # OAuth device flow
│   │   │   ├── feed.py             # Home, Subs, History
│   │   │   ├── search.py           # Search proxy
│   │   │   ├── video.py            # Stream resolution + meta
│   │   │   └── cache.py            # Cache management
│   │   ├── services/
│   │   │   ├── youtube_api.py      # Data API v3 wrapper
│   │   │   ├── stream_resolver.py  # yt-dlp integration
│   │   │   ├── download_manager.py # Progressive download
│   │   │   ├── muxer.py            # FFmpeg mux pipeline
│   │   │   ├── thumbnail_cache.py  # Image fetch + store
│   │   │   └── sponsorblock.py     # SponsorBlock API
│   │   ├── db/
│   │   │   ├── models.py           # SQLite schema
│   │   │   └── migrations/
│   │   └── config.py               # Environment config
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
├── shield-app/
│   ├── app/src/main/
│   │   ├── java/com/shieldtube/
│   │   │   ├── MainActivity.kt
│   │   │   ├── ui/
│   │   │   │   ├── BrowseFragment.kt
│   │   │   │   ├── PlaybackFragment.kt
│   │   │   │   ├── SearchFragment.kt
│   │   │   │   └── SettingsFragment.kt
│   │   │   ├── api/
│   │   │   │   └── ShieldTubeApi.kt   # Retrofit client
│   │   │   ├── player/
│   │   │   │   └── HDRPlaybackEngine.kt
│   │   │   └── auth/
│   │   │       └── DeviceFlowAuth.kt
│   │   └── res/
│   └── build.gradle.kts
├── config/
│   ├── precache_rules.json
│   └── .env.example
└── docs/
    └── PRD.md                      # You are here
```

---

*Ship Phase 1. Validate the HDR pipeline. Everything else is details.*
