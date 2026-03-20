# ShieldTube Technical Skills Breakdown

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md)

---

## Purpose

This document identifies every technical discipline required to build ShieldTube, organized by system layer to mirror the PRD architecture. Each discipline includes a description of why it's needed and a reference to the relevant PRD section.

ShieldTube is a self-hosted YouTube frontend for NVIDIA Shield TV with two independent codebases:

- **Shield App** — Kotlin Android TV client (Leanback UI + ExoPlayer)
- **Backend** — Python FastAPI async server (yt-dlp, FFmpeg, SQLite)

---

## Layer 1: Shield App (Android TV Frontend)

The thin client that runs on NVIDIA Shield TV. Handles browsing, playback, and user interaction — all intelligence lives on the backend.

| # | Discipline | Why It's Needed | PRD Reference |
|---|---|---|---|
| 1 | **Kotlin** | Primary language for the entire Shield app | Shield App section |
| 2 | **Android TV / Leanback UI** | BrowseFragment, SearchFragment, SettingsFragment — the 10-foot UI framework with D-pad focus management and card-row layouts | Component 1 |
| 3 | **ExoPlayer** | Hardware-accelerated video playback, adaptive bitrate, HTTP range-request consumption, HDR metadata passthrough (HDR10+, Dolby Vision Profile 5/8) | PlaybackFragment, LG OLED section |
| 4 | **Retrofit / HTTP client** | `ShieldTubeApi.kt` — typed API calls to the backend for feeds, streams, search | API client module |
| 5 | **Glide or Coil** | Image loading with disk caching for thumbnail grids (double-layer cache: backend + Shield) | Thumbnail pipeline |
| 6 | **OAuth 2.0 Device Flow (Android)** | TV-friendly auth: display code on screen, poll backend for token, store in Android Keystore | Auth section |
| 7 | **HDMI-CEC / remote input handling** | Map D-pad, play/pause/seek to Shield remote + LG Magic Remote via CEC | Remote Control Mapping |
| 8 | **Android Keystore** | Secure storage for OAuth tokens on-device | Security model |

---

## Layer 2: Backend API (Python/FastAPI)

The brain of the system. Handles auth, API proxying, stream resolution, caching, and download orchestration.

| # | Discipline | Why It's Needed | PRD Reference |
|---|---|---|---|
| 9 | **Python 3.11+ async** | Core language; async/await throughout for non-blocking I/O | Tech Stack |
| 10 | **FastAPI + uvicorn** | Async HTTP framework for the full API surface; path operations, dependency injection, request validation | API Surface |
| 11 | **aiosqlite** | Async SQLite access for metadata, feed cache, watch history, token storage | Database schema |
| 12 | **SQLite schema design** | 4 tables (videos, feed_cache, thumbnails, watch_history) with JSON columns, ETags, and efficient queries | Component 5 |
| 13 | **Google OAuth 2.0 Device Flow (server-side)** | Token exchange, encrypted storage, refresh token rotation — server holds the tokens, not the client | Auth architecture |
| 14 | **YouTube Data API v3** | Feed, subscriptions, search, history — understanding quota costs, ETag caching, batch `part` parameters, RSS fallback | API Rate Limits section |
| 15 | **HTTP range-request serving** | Serve partially-downloaded files with `Accept-Ranges: bytes` and correct `Content-Length` so ExoPlayer can seek | Component 4 |
| 16 | **SSE / WebSocket** | Real-time download progress reporting to Shield app | `/api/video/:id/progress` |
| 17 | **SponsorBlock API integration** | HTTP client to fetch community-sourced sponsor segments by video ID | Component listing |
| 18 | **Chapter markers** | Parse YouTube chapter data from video metadata, store in `chapters_json`, transmit via `/api/video/:id/meta`, render as timeline markers in playback UI | User Story #10, Phase 4 |
| 19 | **Playback position tracking** | Record watch progress (`position_seconds`, `completed`) in `watch_history` table, sync on app open, enable resume-from-last-position | Phase 3, watch_history schema |

---

## Layer 3: Stream Engine (yt-dlp + FFmpeg)

The critical path — resolves YouTube videos into playable streams and manages progressive downloads.

| # | Discipline | Why It's Needed | PRD Reference |
|---|---|---|---|
| 20 | **yt-dlp Python API** | Stream URL extraction in <500ms; format selection (VP9.2 HDR > VP9 > AV1 > H.264), cookie authentication, error handling | Component 3, code sample |
| 21 | **FFmpeg CLI / piping** | On-the-fly muxing of separate video+audio DASH streams into single MP4/MKV with `-movflags +faststart+frag_keyframe` for progressive playback | Muxing strategy |
| 22 | **Video codec knowledge** | VP9, VP9.2 (HDR), AV1, H.264 — understanding format hierarchies, HDR metadata (HDR10, HDR10+, Dolby Vision), container formats (WebM, MP4, MKV) | Format selection logic |
| 23 | **Progressive download architecture** | Segmented downloading, playback-head-aware prioritization, seek-triggered reprioritization, background download worker as separate container | Component 4, docker-compose |

---

## Layer 4: Infrastructure & DevOps

Deployment, hosting, and operational concerns across both target environments.

| # | Discipline | Why It's Needed | PRD Reference |
|---|---|---|---|
| 24 | **Docker + Docker Compose** | Containerize API server + downloader worker; portable between Synology NAS and WSL2 | Host Environment |
| 25 | **WSL2 networking** | Port forwarding (`netsh portproxy`), NVIDIA CUDA passthrough for potential hardware-accelerated operations (primary muxing uses stream copy, no GPU required), `wsl-vpnkit` fallback | Option B setup |
| 26 | **Synology NAS deployment** | Docker on Synology, volume mounts, resource constraints (2 FFmpeg threads), always-on config | Option A setup |
| 27 | **Process management** | PM2 for dev, Docker restart policies for prod — keep services alive | Tech Stack |
| 28 | **Filesystem / cache management** | Local disk cache with configurable paths, LRU eviction, pinned videos, disk usage monitoring | Component 6 |
| 29 | **Pre-caching rules engine** | Configurable channel-based and playlist-based auto-download triggers (on_upload, nightly), quality presets per rule — JSON-driven rule schema | Component 6, User Story #8 |

---

## Layer 5: Security & Auth

Threat mitigations specific to a LAN-hosted media server handling OAuth tokens and cookies.

| # | Discipline | Why It's Needed | PRD Reference |
|---|---|---|---|
| 30 | **TLS / self-signed certificates** | HTTPS on LAN with cert pinning in the Shield app | Security Model |
| 31 | **Encrypted storage** | OAuth tokens encrypted at rest in SQLite with OS-level file permissions | Security Model |
| 32 | **Shared-secret authentication** | API header-based auth for LAN access control | Security Model |
| 33 | **Cookie security** | yt-dlp cookie file with 600 permissions, process-isolated access | Security Model |

---

## Layer 6: Cross-cutting

Disciplines that span multiple layers and are prerequisites for the system to function end-to-end.

| # | Discipline | Why It's Needed | PRD Reference |
|---|---|---|---|
| 34 | **HTTP protocol fundamentals** | Range requests, ETags, 304 responses, content negotiation — used everywhere between Shield<->Backend and Backend<->YouTube | Throughout |
| 35 | **HDMI 2.1 / HDR pipeline** | Understanding EDID negotiation, color space matching, frame rate matching, Dolby Vision profiles — the Phase 1 validation gate | LG OLED Integration |

---

## Summary

| Layer | Disciplines | Count |
|---|---|---|
| Shield App (Android TV Frontend) | Kotlin, Leanback UI, ExoPlayer, Retrofit, Glide/Coil, OAuth Device Flow, HDMI-CEC, Android Keystore | 8 |
| Backend API (Python/FastAPI) | Python async, FastAPI, aiosqlite, SQLite schema, OAuth server-side, YouTube API v3, Range requests, SSE/WebSocket, SponsorBlock, Chapters, Playback position | 11 |
| Stream Engine (yt-dlp + FFmpeg) | yt-dlp API, FFmpeg CLI, Video codecs, Progressive download | 4 |
| Infrastructure & DevOps | Docker, WSL2 networking, Synology deployment, Process management, Cache management, Pre-caching rules | 6 |
| Security & Auth | TLS/certs, Encrypted storage, Shared-secret auth, Cookie security | 4 |
| Cross-cutting | HTTP fundamentals, HDMI 2.1/HDR pipeline | 2 |
| **Total** | | **35** |

> **Note:** The original brainstorming design identified 28 disciplines. Through detailed enumeration and spec review, 7 additional disciplines emerged: some from separating concerns that were initially grouped (Android Keystore, Cookie security), others from PRD features not represented in the original pass (Chapter markers, Playback position tracking, Pre-caching rules engine). All 35 map directly to PRD requirements.
