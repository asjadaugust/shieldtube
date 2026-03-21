# ShieldTube Mobile Companion PWA — Design Spec

**Date:** 2026-03-21
**Status:** Approved

## Overview

A mobile-optimized Progressive Web App served by the existing ShieldTube backend that enables remote browsing, casting to Shield TV, and recommendation training via swipe-to-rate. Accessible via Cloudflare Tunnel for out-of-home use.

## Why PWA Over Native App

- No separate build pipeline — served from the existing backend
- Works on any device with a browser (Android, iOS, laptop)
- Installable on Android home screen — native app feel
- Cloudflare Tunnel provides HTTPS automatically — no cert management for mobile
- The `/dashboard` static file serving already exists in the backend
- Ships as a single deployment alongside the existing API

## Architecture

```
Phone (anywhere) → Cloudflare Tunnel → NAS Backend → Shield TV
                                         ↓
                                    SQLite DB (watch signals,
                                    recommendations, ratings)
```

### Components

| Component | Location | Role |
|---|---|---|
| **Mobile PWA** | `backend/mobile/` (static files) | UI: browse, search, cast, rate, play |
| **Backend API** | existing endpoints + new `/api/rate` | Serves PWA + handles all data |
| **Cloudflare Tunnel** | `cloudflared` daemon on NAS | Exposes backend to internet securely |
| **Service Worker** | `backend/mobile/sw.js` | Offline caching, push notifications |

### Cloudflare Tunnel Setup

```bash
# One-time setup on the NAS
cloudflared tunnel create shieldtube
cloudflared tunnel route dns shieldtube shieldtube.yourdomain.com

# Config file: ~/.cloudflared/config.yml
tunnel: <tunnel-id>
credentials-file: ~/.cloudflared/credentials.json
ingress:
  - hostname: shieldtube.yourdomain.com
    service: https://localhost:9443
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```

The tunnel provides HTTPS automatically via Cloudflare's edge certificates. The `noTLSVerify` flag is needed because the backend uses a self-signed cert internally.

## Mobile UI Design

### NVIDIA Shield Theme (CSS)

```css
:root {
  --nvidia-green: #76B900;
  --nvidia-green-dark: #5A8C00;
  --bg-dark: #121212;
  --bg-card: #1E1E1E;
  --bg-surface: #1A1A1A;
  --text-primary: #FFFFFF;
  --text-secondary: #B0B0B0;
  --accent-red: #E94560;
}
```

### Screens

**1. Home (default) — Feed Tabs**
- Tabbed navigation: For You | Home | Subscriptions | History
- Video cards: thumbnail, title, channel, duration, view count
- Pull-to-refresh on each tab
- Infinite scroll for long feeds

**2. Search**
- Search bar at top
- Real-time results as user types (debounced 300ms)
- Same card layout as feeds

**3. Video Detail (bottom sheet)**
- Tap a card → slide-up bottom sheet
- Shows: large thumbnail, title, channel, description, duration
- Action buttons: Play on Phone | Cast to Shield | Rate | Download
- Shows cache status (pre-cached indicator)
- Shows SponsorBlock segments count

**4. Player (full-screen)**
- HTML5 video player with custom controls
- SponsorBlock auto-skip
- Chapter markers
- Speed control
- Subtitle selection
- Reports progress events (playing, paused, seeked, completed, abandoned)
- All progress data feeds the recommendation engine

**5. Rate / Train (swipe mode)**
- Swipe-to-rate interface for recommendation training
- Shows video thumbnail + title + channel
- Swipe right = interested, left = not interested, up = love
- Each interaction stored as a training signal
- Shows from: recommended feed + subscription uploads + trending
- Goal: rapid preference gathering without watching

**6. Settings**
- Backend URL (auto-configured via QR or manual)
- API secret
- Cache status overview
- Bandwidth throttle control
- Recommendation status (last run, model, count)

### Navigation

Bottom nav bar with 4 tabs:
```
[Home] [Search] [Train] [Settings]
```

## Training Enhancement

### New: Rating Endpoint

```
POST /api/video/{video_id}/rate
Body: { "rating": "interested" | "not_interested" | "love" }
```

Stored in a new `video_ratings` table:
```sql
CREATE TABLE IF NOT EXISTS video_ratings (
    video_id TEXT NOT NULL,
    rating TEXT NOT NULL,
    rated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id)
);
```

### How Ratings Feed the Recommender

The batch job reads `video_ratings` alongside `watch_history` and `watch_signals`:
- `love` → 2x weight on that video's embedding in the user profile
- `interested` → 1.5x weight (even without watching)
- `not_interested` → negative signal, candidate receives -0.3 penalty in scoring

This means the user can train the recommender **without watching videos** — just by swiping through thumbnails on their phone during commute, lunch break, etc.

### Enhanced Watch Signals from Phone

The phone player sends the same enriched progress events as the Shield TV:
```json
POST /api/video/{id}/progress
{
  "position_seconds": 120,
  "duration": 600,
  "event": "playing",
  "speed": 1.0
}
```

Phone viewing sessions contribute equally to the recommendation profile.

## Database Changes

### New Table

```sql
CREATE TABLE IF NOT EXISTS video_ratings (
    video_id TEXT PRIMARY KEY,
    rating TEXT NOT NULL,
    rated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Migration: `backend/db/migrations/006_video_ratings.sql`

### New API Endpoints

```
POST /api/video/{video_id}/rate        Rate a video (interested/not_interested/love)
GET  /api/video/{video_id}/rating      Get current rating for a video
GET  /api/ratings/recent               Get recent ratings (for training UI state)
```

## PWA Manifest

```json
{
  "name": "ShieldTube",
  "short_name": "ShieldTube",
  "description": "Remote control for ShieldTube",
  "start_url": "/mobile/",
  "display": "standalone",
  "background_color": "#121212",
  "theme_color": "#76B900",
  "icons": [
    { "src": "/mobile/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/mobile/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

## File Structure

```
backend/
  mobile/                          # Static files served at /mobile/
    index.html                     # SPA entry point
    manifest.json                  # PWA manifest
    sw.js                          # Service worker (offline + caching)
    css/
      theme.css                    # NVIDIA Shield theme
      app.css                      # Layout + components
    js/
      app.js                       # Main app logic, routing
      api.js                       # API client (fetch wrapper with auth)
      player.js                    # Video player with SponsorBlock
      swipe.js                     # Swipe-to-rate training UI
      components.js                # Video cards, bottom sheet, tabs
    icons/
      icon-192.png                 # PWA icon
      icon-512.png                 # PWA icon

  api/routers/
    rate.py                        # New: rating endpoints

  db/migrations/
    006_video_ratings.sql          # New: video_ratings table

  db/repositories.py               # Add: VideoRatingRepo
  db/models.py                     # Add: VideoRating dataclass
```

## Security

### Cloudflare Tunnel + API Secret

- Cloudflare Tunnel provides HTTPS and DDoS protection
- The `X-ShieldTube-Secret` header is still required for API calls
- The PWA stores the secret in `localStorage` after initial setup
- First-time setup: user enters the secret manually or scans a QR code from the Shield TV settings

### No Additional Auth Needed

The system is single-user. The API secret is the auth gate. Cloudflare Tunnel handles transport security. No user accounts, no sessions, no cookies.

## Cloudflare Tunnel Deployment

Add to `docker-compose.yml`:

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel run
    environment:
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN:-}
    restart: unless-stopped
    depends_on:
      - shieldtube-api
```

Or run standalone on the NAS:
```bash
cloudflared tunnel --url https://localhost:9443 --no-tls-verify
```

## Offline Support

The service worker caches:
- All static assets (HTML, CSS, JS, icons)
- Last fetched feed data (For You, Home, Subscriptions)
- Thumbnail images (LRU, max 50MB)

When offline:
- Feeds render from cache
- Search is disabled (shows "offline" message)
- Ratings/interactions are queued and synced when back online
- Player works for cached videos only
