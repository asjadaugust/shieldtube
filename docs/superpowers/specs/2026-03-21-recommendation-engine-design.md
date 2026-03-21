# ShieldTube Recommendation Engine — Design Spec

**Date:** 2026-03-21
**Status:** Approved

## Overview

A recommendation system for ShieldTube that uses local watch history to surface personalized video suggestions, pre-download likely-to-watch videos, and fall back to heuristics when the ML engine is unavailable.

## Architecture

Three components, cleanly separated by deployment target:

| Component | Runs On | Role |
|---|---|---|
| **Recommendation Batch Job** (`rec-engine/`) | Lenovo laptop (WSL2) | Compute embeddings, score candidates, trigger pre-downloads |
| **ShieldTube Backend** (existing) | Synology NAS (Docker) | Serve recommendations, manage download queue, heuristic fallback |
| **Shield TV App** (existing) | NVIDIA Shield TV | Display "For You" row, send enriched watch signals, cache UI state |

### Data Flow

```
Laptop (batch job, every 4-5h)
  ├── GET /api/feed/history           → read watch history
  ├── GET /api/recommendations/status → check staleness
  ├── Fetch candidate videos          → YouTube API (related, trending, subs)
  ├── Compute embeddings              → adaptive model selection
  ├── Score candidates                → cosine similarity + composite scoring
  ├── POST /api/recommendations/sync  → write ranked results to NAS DB
  └── POST /api/download/enqueue-batch → trigger pre-downloads

NAS Backend (always on)
  ├── GET /api/feed/recommended       → serve ML or heuristic recommendations
  ├── Download queue                  → bandwidth-throttled pre-caching
  └── Watch signal aggregation        → enrich progress data into metrics

Shield TV App
  ├── "For You" row in BrowseFragment → renders recommendations
  ├── Pre-cached indicator            → icon on cached video cards
  ├── Enriched progress reports       → event type, playback speed
  └── SharedPreferences cache         → instant UI on launch
```

### Deployment Constraints

**Synology NAS:**
- No ML libraries (no torch, sentence-transformers)
- Docker image stays slim
- Max 1-2 concurrent FFmpeg download jobs
- Bandwidth throttling must be CPU-light

**Laptop:**
- Runs batch job via CLI (manual or cron)
- Adaptive model selection based on available RAM
- Connects to NAS backend via HTTPS API

**Shield TV:**
- Sends enriched watch signals (event, speed)
- Caches last recommendation list in SharedPreferences
- Shows pre-cached status on video cards

## Embedding Pipeline

### Adaptive Model Selection

Configuration (`rec-engine/config.yaml`):

```yaml
models:
  preferred: "all-mpnet-base-v2"     # ~500MB, best quality
  fallback:
    - "all-MiniLM-L12-v2"           # ~120MB, good quality
    - "all-MiniLM-L6-v2"            # ~80MB, fastest
  auto_fallback: true
ram_threshold_mb: 500                # minimum free RAM to keep available
```

At startup: check free system RAM, pick the largest model that fits under `free_ram - ram_threshold_mb`. Walk down the fallback list if the preferred model doesn't fit.

### Video Embedding

Each video is embedded from concatenated text:

```
"{title} | {channel_name} | {description_first_200_chars}"
```

Tags are omitted — fetching them requires an extra YouTube API call per video (`snippet.tags`), which consumes significant quota. Title + channel + description provide sufficient semantic signal.

Two pools of videos are embedded:

1. **Watched videos** — everything in `watch_history`, used to build the user profile.
2. **Candidate videos** — fresh videos from subscriptions, trending, and yt-dlp's `--flat-playlist` related video extraction seeded with the user's top 10 most-watched videos. This drives discovery. (Note: YouTube Data API's `relatedToVideoId` parameter is deprecated; yt-dlp provides related videos reliably.)

Embeddings are cached in a **local SQLite database** on the laptop (`rec-engine/embeddings.db`), not on the NAS. This avoids needing an API endpoint for raw embedding sync and keeps the NAS schema simple. Only new/unseen videos are embedded on each run. When the model changes between runs (e.g. different RAM available), all cached embeddings are invalidated and recomputed since dimensions differ across models.

### User Profile Vector

Weighted average of watched video embeddings:

```
profile = sum(weight_i * embedding_i) / sum(weight_i)
```

Per-video weights:
- **completion_rate** (0.0-1.0) — 90%+ watched gets full weight
- **recency_decay** — exponential decay, half-life 7 days
- **rewatch_bonus** — 1.5x multiplier if watched multiple times
- **engagement_quality** — derived from watch signals (speed, pauses, abandonment)

Produces a single 384-dim vector (MiniLM) or 768-dim (mpnet) representing user preferences.

### Candidate Scoring

Each candidate gets a composite score:

```
score = (0.6 * cosine_similarity(candidate_embedding, profile_vector))
      + (0.2 * channel_affinity)
      + (0.1 * freshness)
      + (0.1 * popularity_signal)
```

Where:
- **channel_affinity** — fraction of that channel's videos the user has watched and completed
- **freshness** — decay from publish date, half-life 48 hours
- **popularity_signal** — normalized log(view_count), light tiebreaker

Top N candidates (configurable, default 100) are written to the `recommendations` table.

## Pre-Download & Bandwidth Management

### Download Triggering

After scoring, the batch job calls:

```
POST /api/download/enqueue-batch
Body: { videos: [{id, score}], threshold: 0.7 }
```

The backend diffs against already-cached videos and enqueues new ones above the threshold into the existing `DownloadQueue`, ordered by score descending.

### Bandwidth Throttling

The NAS monitors network usage and adjusts download speed dynamically:

- **Idle network** — download at full speed
- **Active usage detected** — throttle to a configured ceiling (default 5 Mbps)
- **Detection** — configurable fixed rate limit with a toggle endpoint (`PUT /api/download/bandwidth`). The Docker container cannot reliably observe host network traffic via `/proc/net/dev` (it sees the container's virtual interface only). Instead, use a simple approach: default to a conservative rate (e.g. 10 Mbps), allow the user to adjust via API or config, and optionally set a schedule (e.g. full speed overnight, throttled during day).

Implementation:
- Max 1-2 concurrent FFmpeg mux jobs on Synology
- Python asyncio token-bucket rate limiter wrapping download streams
- Highest-score videos download first

### Refresh Cycle

- Batch job runs every 4-5 hours (cron or manual)
- Each run: fetch new candidates, embed only new videos, recompute profile, re-score, write diff
- Pre-download queue: only enqueue videos not already cached or in-progress

### Cache Lifecycle

```
score > threshold        → enqueue download
download complete        → set cache_status="pre-cached", cached_at=now in videos table
video watched            → keep cached, boost future recommendations
unwatched 7+ days after cached_at → eligible for eviction
cache full               → evict lowest-score unwatched videos first (join recommendations.score
                           with videos.cache_status and watch_history.watched_at)
```

### Timestamp Handling

The batch job sends its local timestamp in the sync payload, but the NAS records `run_at` using its own clock at receipt time. This avoids clock-skew issues between laptop and NAS for staleness calculations.

## Heuristic Fallback

When the batch job hasn't run in >5 hours, the backend generates recommendations from pure SQL with zero ML dependencies.

### Query Logic

1. Find user's top channels by watch count and completion rate
2. From subscription feed videos, rank by:
   - Channel affinity (is it from a top channel?)
   - Freshness (hours since publish)
   - Completion history (has user finished similar-length videos?)
3. Exclude already-watched videos
4. Return top 50

### Activation Rules

The `/api/feed/recommended` endpoint:

| Condition | Behavior |
|---|---|
| ML recommendations < 3 hours old | Serve 100% ML |
| ML recommendations 3-5 hours old | Blend 70% ML + 30% heuristic |
| ML recommendations > 5 hours old | Serve 100% heuristic |
| No ML recommendations exist | Serve 100% heuristic |

Response includes `"source": "ml"`, `"heuristic"`, or `"blended"`.

## Enriched Watch Signals

### Enhanced Progress Reporting

The app sends enriched data on the existing progress endpoint:

```json
{
  "position_seconds": 120,
  "duration": 600,
  "event": "playing",
  "speed": 1.0
}
```

New fields are optional for backwards compatibility:
- **event** — `playing`, `paused`, `seeked`, `completed`, `abandoned`
- **speed** — current playback speed multiplier

### Derived Metrics

The backend computes and stores in `watch_signals` **in real-time** as progress reports arrive (not as a batch-job artifact). This ensures the heuristic fallback has access to engagement data even when the laptop hasn't run:

| Signal | Computation | Recommender Use |
|---|---|---|
| `completion_rate` | final position / duration | Core weight for profile vector |
| `pause_count` | count of `paused` events | Engagement indicator |
| `seek_forward_count` | count of forward seeks | Low interest signal |
| `avg_playback_speed` | weighted average of speed reports | 2x = consuming, 1x = savoring |
| `time_of_day` | hour of `watched_at` | Temporal preference patterns |
| `abandoned_at_pct` | abandon position / duration | Where interest dropped |

## Database Schema Changes

### New Tables

**On the NAS (migration `005_recommendations.sql`):**

```sql
-- Tracks batch job runs for staleness detection and atomic swaps
CREATE TABLE IF NOT EXISTS recommendation_runs (
    run_id TEXT PRIMARY KEY,
    run_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,            -- 'ml' or 'heuristic'
    model_name TEXT,
    video_count INTEGER DEFAULT 0
);

-- Ranked recommendations, keyed by run for atomic replacement
CREATE TABLE IF NOT EXISTS recommendations (
    video_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    score REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'ml',
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, run_id),
    FOREIGN KEY (run_id) REFERENCES recommendation_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_recommendations_score ON recommendations(run_id, score DESC);

-- Per-session watch engagement signals (not per-video — preserves rewatch data)
CREATE TABLE IF NOT EXISTS watch_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    session_start TEXT NOT NULL,      -- ISO timestamp of when playback started
    completion_rate REAL DEFAULT 0,
    pause_count INTEGER DEFAULT 0,
    seek_forward_count INTEGER DEFAULT 0,
    avg_playback_speed REAL DEFAULT 1.0,
    time_of_day INTEGER,              -- hour 0-23
    abandoned_at_pct REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_watch_signals_video ON watch_signals(video_id);

-- Track when videos were pre-cached for eviction lifecycle
ALTER TABLE videos ADD COLUMN cached_at TEXT;
```

**On the laptop (local `rec-engine/embeddings.db`):**

```sql
CREATE TABLE IF NOT EXISTS embeddings (
    video_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The `embeddings` table lives locally on the laptop to avoid needing an API endpoint for raw embedding sync. When the model changes, all rows are invalidated.

### New API Endpoints

```
GET  /api/feed/recommended           Serve recommendations (ML or heuristic)
POST /api/recommendations/sync       Batch job writes scored recommendations
GET  /api/recommendations/status     Last updated, source, count, staleness
POST /api/download/enqueue-batch     Batch job triggers pre-downloads
GET  /api/download/bandwidth         Current speed + throttle state
PUT  /api/download/bandwidth         Adjust throttle ceiling
```

### Modified Endpoints

```
POST /api/video/{id}/progress        Accept optional event, speed fields (backend Pydantic model
                                     adds event: str | None = None, speed: float | None = None;
                                     Kotlin ProgressBody adds nullable event: String?, speed: Float?)
GET  /api/video/{id}/meta            Include pre_cached boolean
```

### Authentication

All batch job API calls (`/api/recommendations/sync`, `/api/download/enqueue-batch`) must include the `X-ShieldTube-Secret` header. The CLI accepts `--api-secret` or reads from `SHIELDTUBE_API_SECRET` env var. These endpoints are NOT added to the middleware exempt list.

## App UI Changes

### BrowseFragment

New row order:

```
For You          ← Recommendations (ML or heuristic)
Home             ← Trending/popular
Subscriptions    ← Channel uploads
Watch Later      ← YouTube playlist
```

"For You" loads from `/api/feed/recommended`. Cached in a local JSON file (`getFilesDir()/recommended_cache.json`) for instant rendering on launch. SharedPreferences is avoided for large lists — file-based cache handles 100+ video entries without performance issues.

### CardPresenter

Pre-cached videos show a small filled-circle icon in the bottom-right corner of the thumbnail. No text, just a visual hint that the video will play instantly.

### Response Format

```json
{
  "feed_type": "recommended",
  "videos": [...],
  "source": "ml",
  "freshness": "2h ago",
  "from_cache": false
}
```

Same `FeedResponse` shape with `source` and `freshness` added. Each video in the list includes a `pre_cached: boolean` field so CardPresenter can show the cached indicator without extra API calls. App shows "Based on your viewing" subtitle when source is `ml`.

## Batch Job CLI

```bash
# Full run (reads API secret from env or --api-secret flag)
export SHIELDTUBE_API_SECRET="your-secret"
python -m rec_engine run --nas-url https://192.168.0.26:9443

# Embed only
python -m rec_engine embed --nas-url https://192.168.0.26:9443

# Check status
python -m rec_engine status --nas-url https://192.168.0.26:9443

# Override model
python -m rec_engine run --model all-mpnet-base-v2 --nas-url https://192.168.0.26:9443

# Explicit API secret
python -m rec_engine run --nas-url https://192.168.0.26:9443 --api-secret "your-secret"
```

## PRD Update Required

The PRD (`docs/ShieldTube_PRD.md`) currently states: "Not a recommendation engine replacement. We consume YouTube's recommendation API. We don't build our own ML model." This spec supersedes that non-goal. The PRD should be updated to reflect the new scope: "Local recommendation engine supplements YouTube's feeds using watch history embeddings. ML inference runs on the laptop, not the NAS."

## File Structure

```
rec-engine/
  ├── __main__.py          # CLI entry point
  ├── config.yaml          # Model preferences, thresholds
  ├── embedder.py          # Model loading, adaptive selection, embedding
  ├── scorer.py            # Profile building, candidate scoring
  ├── candidates.py        # Candidate fetching (yt-dlp related, subs, trending)
  ├── sync.py              # API client for NAS backend (includes auth header)
  ├── embeddings.db        # Local SQLite — cached embeddings (gitignored)
  └── requirements.txt     # sentence-transformers, httpx, pyyaml, yt-dlp

backend/
  ├── api/routers/
  │   └── recommend.py     # New: /api/feed/recommended, /api/recommendations/*
  ├── services/
  │   ├── heuristic_rec.py # New: SQL-based fallback recommender
  │   ├── bandwidth.py     # New: configurable download rate limiting
  │   └── watch_signal_aggregator.py  # New: real-time signal computation from progress events
  └── db/migrations/
      └── 005_recommendations.sql  # New tables (recommendations, recommendation_runs,
                                   #             watch_signals, videos.cached_at)
```
