# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ShieldTube is a self-hosted YouTube frontend for NVIDIA Shield TV. It authenticates with Google, mirrors the YouTube browse experience (Home, Subscriptions, Search, History), and plays videos natively on LG OLED TVs with HDR/Dolby Vision support via progressive downloading.

**Status:** Pre-development. Only the PRD exists at `docs/ShieldTube_PRD.md`.

## Architecture

Two independent codebases communicating via HTTP API:

- **`backend/`** — Python FastAPI async server (uvicorn). Handles OAuth, YouTube Data API v3 proxying, stream resolution (yt-dlp), FFmpeg muxing, progressive download management, thumbnail caching, SponsorBlock integration. SQLite (aiosqlite) for persistence.
- **`shield-app/`** — Kotlin Android TV app using Leanback UI + ExoPlayer. Thin client; all state lives on the backend.

### Playback Pipeline

User clicks thumbnail → backend resolves stream via yt-dlp → FFmpeg muxes video+audio → backend serves via HTTP with range-request support → ExoPlayer plays from local URL → download manager caches segments ahead of playback head.

### Key External Dependencies

- **YouTube Data API v3** — feeds, search, metadata (10,000 units/day free quota)
- **yt-dlp** — stream URL extraction (needs frequent updates)
- **FFmpeg 6.0+** — stream muxing (VP9/AV1/HDR10+ support)
- **ExoPlayer 2.19+** — Android playback with HDR10+/Dolby Vision
- **SponsorBlock API** — community-sourced sponsor segment skipping

## Build & Run Commands

### Backend (Python/FastAPI)

```bash
pip install -r backend/requirements.txt
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8080
pytest backend/                          # all tests
pytest backend/tests/test_auth.py        # single test file
pytest backend/tests/test_auth.py::test_device_flow -v  # single test
```

### Shield App (Kotlin/Android)

```bash
./gradlew build
./gradlew test
./gradlew installDebug                   # deploy to Shield device
```

### Docker

```bash
docker build -t shieldtube/api:latest backend/
docker-compose up -d
```

## Environment Variables

Required in `.env` (see `config/.env.example`):

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLIENT_ID` | OAuth app ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth app secret |
| `CACHE_MAX_SIZE_GB` | Cache limit (default: 500GB) |
| `FFMPEG_THREADS` | Parallelism — 2 for Synology NAS, higher for laptop |
| `BACKEND_HOST` | Server URL (e.g., `http://192.168.1.100:8080`) |

## API Endpoints

```
GET  /api/auth/login              # Initiate OAuth device flow
GET  /api/auth/callback           # Token exchange
GET  /api/feed/home               # YouTube Home feed
GET  /api/feed/subscriptions      # Subscriptions feed
GET  /api/feed/history            # Watch History
GET  /api/search?q=<query>        # Search proxy
GET  /api/video/:id/meta          # Video metadata
GET  /api/video/:id/stream        # Resolve stream URL
GET  /api/video/:id/thumbnail     # Cached thumbnail
POST /api/video/:id/download      # Queue for download
GET  /api/video/:id/progress      # Download progress (SSE/WebSocket)
GET  /api/cache/status            # Cache disk usage
DELETE /api/cache/:id             # Evict cached video
GET  /api/sponsorblock/:id        # SponsorBlock segments
```

## Design Constraints

- **Single user, single household.** No multi-user auth or RBAC.
- **Backend-driven state.** Shield app is a thin client; SQLite holds all state.
- **No transcoding.** Shield has hardware decoders — use FFmpeg stream copy only.
- **LAN-only by default.** Shared secret header authenticates requests.
- **Two hosting targets:** Synology NAS (always-on, weak CPU) and Lenovo laptop with WSL2 (powerful, temporary).

## Git Commit Authorship

When creating git commits, always use the repository's configured `user.name` and `user.email`. Never set `--author` or `GIT_AUTHOR_*` environment variables.

## Development Phases

1. **Walking Skeleton** — Single hardcoded video plays on Shield with HDR passthrough
2. **Browse Experience** — OAuth device flow, YouTube API integration, thumbnail caching
3. **Progressive Download** — Segmented downloads, range-request serving, watch history
4. **Polish** — SponsorBlock, chapters, pre-caching rules, cache management UI
5. **Extended** — Watch Later sync, subtitles, phone casting, web dashboard

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (90-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk vitest run          # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%)
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->