# Mobile Companion PWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a mobile-optimized PWA served by the ShieldTube backend for remote browsing, casting, video playback, and recommendation training via swipe-to-rate.

**Architecture:** Static HTML/CSS/JS files served from `backend/mobile/`, using the existing REST API. Cloudflare Tunnel for remote HTTPS access. New `/api/rate` endpoint + migration for training data.

**Tech Stack:** Vanilla HTML/CSS/JS (no framework — keep it light), FastAPI (existing), Cloudflare Tunnel

**Spec:** `docs/superpowers/specs/2026-03-21-mobile-companion-pwa-design.md`

---

## File Map

| File | Responsibility |
|---|---|
| `backend/db/migrations/006_video_ratings.sql` | video_ratings table |
| `backend/db/models.py` | Add VideoRating dataclass |
| `backend/db/repositories.py` | Add VideoRatingRepo |
| `backend/api/routers/rate.py` | Rating endpoints |
| `backend/api/main.py` | Register rate router, mount mobile static files |
| `backend/mobile/index.html` | SPA shell |
| `backend/mobile/manifest.json` | PWA manifest |
| `backend/mobile/sw.js` | Service worker |
| `backend/mobile/css/theme.css` | NVIDIA Shield color variables |
| `backend/mobile/css/app.css` | Layout, components, responsive styles |
| `backend/mobile/js/api.js` | Fetch wrapper with auth header |
| `backend/mobile/js/app.js` | Router, tab navigation, initialization |
| `backend/mobile/js/components.js` | Video card, bottom sheet, feed rendering |
| `backend/mobile/js/player.js` | Video player with controls + SponsorBlock |
| `backend/mobile/js/swipe.js` | Swipe-to-rate training interface |

---

## Task 1: Database Migration + Rating Backend

**Files:**
- Create: `backend/db/migrations/006_video_ratings.sql`
- Modify: `backend/db/models.py`
- Modify: `backend/db/repositories.py`
- Create: `backend/api/routers/rate.py`
- Modify: `backend/api/main.py`

- [ ] Create migration:
```sql
CREATE TABLE IF NOT EXISTS video_ratings (
    video_id TEXT PRIMARY KEY,
    rating TEXT NOT NULL,
    rated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] Add `VideoRating` dataclass to models.py
- [ ] Add `VideoRatingRepo` to repositories.py with `upsert(video_id, rating)`, `get(video_id)`, `get_recent(limit)`
- [ ] Create rate.py router with `POST /video/{video_id}/rate`, `GET /video/{video_id}/rating`, `GET /ratings/recent`
- [ ] Register in main.py
- [ ] Commit

---

## Task 2: PWA Shell + Theme

**Files:**
- Create: `backend/mobile/index.html`
- Create: `backend/mobile/manifest.json`
- Create: `backend/mobile/css/theme.css`
- Create: `backend/mobile/css/app.css`
- Modify: `backend/api/main.py` (mount static files)

- [ ] Create `backend/mobile/` directory structure
- [ ] Create `index.html` — single-page app shell with bottom nav (Home, Search, Train, Settings), viewport meta for mobile, dark theme
- [ ] Create `manifest.json` — PWA manifest with NVIDIA green theme color, standalone display, icons
- [ ] Create `theme.css` — CSS custom properties matching the Shield TV colors
- [ ] Create `app.css` — mobile-first responsive layout: bottom nav, card grid, tabs, bottom sheet, scrolling
- [ ] Mount in main.py: `app.mount("/mobile", StaticFiles(directory="backend/mobile", html=True))`
- [ ] Commit

---

## Task 3: API Client + App Router

**Files:**
- Create: `backend/mobile/js/api.js`
- Create: `backend/mobile/js/app.js`

- [ ] Create `api.js` — fetch wrapper that adds `X-ShieldTube-Secret` from localStorage, handles errors, provides methods: `getFeed(type)`, `search(query)`, `getVideoMeta(id)`, `castToShield(id)`, `rateVideo(id, rating)`, `reportProgress(id, data)`
- [ ] Create `app.js` — hash-based router (#home, #search, #train, #settings), tab switching, initialization, first-run setup (prompt for API secret)
- [ ] Commit

---

## Task 4: Video Cards + Feed Display

**Files:**
- Create: `backend/mobile/js/components.js`

- [ ] Create `components.js` with:
  - `renderVideoCard(video)` — thumbnail, title, channel, duration badge, pre-cached indicator
  - `renderFeed(videos, container)` — grid of cards with lazy-loading thumbnails
  - `renderBottomSheet(video)` — slide-up detail panel with Play/Cast/Rate buttons
  - `renderTabs(tabs, activeTab, onSwitch)` — tab bar for feed switching
  - Pull-to-refresh handler
  - Infinite scroll handler
- [ ] Wire into app.js for Home screen (For You, Home, Subscriptions, History tabs)
- [ ] Commit

---

## Task 5: Video Player

**Files:**
- Create: `backend/mobile/js/player.js`

- [ ] Create `player.js` with:
  - Full-screen HTML5 video player
  - Custom controls overlay (play/pause, seek bar, time display, speed, subtitles, fullscreen)
  - SponsorBlock integration (fetch segments, auto-skip with toast)
  - Chapter markers on seek bar
  - Progress reporting (playing, paused, seeked, completed, abandoned events)
  - Speed control (0.5x to 2x)
  - Subtitle selection dropdown
  - Resume from last position (fetch from /api/video/{id}/meta)
- [ ] Commit

---

## Task 6: Swipe-to-Rate Training UI

**Files:**
- Create: `backend/mobile/js/swipe.js`

- [ ] Create `swipe.js` with:
  - Card stack UI showing video thumbnail + title + channel
  - Touch gesture handling: swipe right (interested), left (not interested), up (love)
  - Visual feedback: green glow right, red glow left, heart animation up
  - Counter showing how many rated this session
  - Fetches candidates from `/api/feed/recommended` + `/api/feed/subscriptions`
  - Each swipe calls `POST /api/video/{id}/rate`
  - Preloads next 5 cards for smooth experience
- [ ] Commit

---

## Task 7: Settings + Setup Screen

- [ ] Add settings screen to `app.js`:
  - First-run: prompt for backend URL + API secret (with "Test Connection" button)
  - Store in localStorage
  - Show: recommendation status, cache status, bandwidth control
  - Cast test button
  - Clear cache button
  - About section (version, backend URL)
- [ ] Commit

---

## Task 8: Service Worker + Icons

**Files:**
- Create: `backend/mobile/sw.js`
- Create: `backend/mobile/icons/` (generated SVG icons)

- [ ] Create `sw.js` — cache static assets on install, network-first for API calls, cache-first for thumbnails
- [ ] Create SVG-based icons (192x192, 512x512) with NVIDIA green shield + play triangle (matching the Android TV banner)
- [ ] Commit

---

## Task 9: Cloudflare Tunnel Setup

- [ ] Add cloudflared service to `docker-compose.yml`:
```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel run
    environment:
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN:-}
    restart: unless-stopped
    network_mode: "service:shieldtube-api"
```
- [ ] Add `CLOUDFLARE_TUNNEL_TOKEN` to .env.example documentation
- [ ] Update `docs/deployment/https-setup.md` with Cloudflare Tunnel instructions
- [ ] Commit

---

## Task 10: Integration Test

- [ ] Rebuild Docker, verify `/mobile/` serves the PWA
- [ ] Test on phone browser: browse feeds, search, play video, cast to Shield, swipe-to-rate
- [ ] Verify Cloudflare Tunnel connectivity (if token configured)
- [ ] Check backend logs for errors
- [ ] Commit any fixes
