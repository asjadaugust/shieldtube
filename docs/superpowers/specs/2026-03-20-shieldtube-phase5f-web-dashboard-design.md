# Phase 5f: Web Dashboard — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft

---

## Goal

Browser-accessible dashboard for cache management and configuration, served by the backend.

**Success criteria:** Open `http://NAS_IP:8080/dashboard` → see cache status, manage videos, edit settings.

---

## Design

Single-page HTML served by FastAPI's `StaticFiles` or inline templates. No frontend framework — vanilla HTML/CSS/JS with fetch() calls to existing API.

### Pages

1. **Cache Overview** — Total size, per-video list with titles, sizes, last accessed. Delete button per video. Calls `GET /api/cache/status` and `DELETE /api/cache/{id}`.

2. **Pre-cache Rules** — Display current rules from `/api/precache/rules` (new endpoint). Add/remove rules. Writes to `config/precache_rules.json`.

3. **Download Queue** — Show active/queued downloads. Calls a new `GET /api/downloads/status` endpoint.

4. **System Status** — Backend version, uptime, OAuth token status, feed refresh times.

### Backend Additions

1. **`GET /api/precache/rules`** — Returns current pre-cache rules JSON.
2. **`POST /api/precache/rules`** — Overwrites precache_rules.json with new rules.
3. **`GET /api/downloads/status`** — Returns download queue state.
4. **`GET /api/system/status`** — Returns version, uptime, token status.
5. **Static file serving** — Mount `/dashboard` to serve HTML/CSS/JS from `backend/dashboard/`.

**Files:**

| File | Change |
|------|--------|
| `backend/dashboard/index.html` | New: single-page dashboard |
| `backend/dashboard/style.css` | New: dashboard styles |
| `backend/dashboard/app.js` | New: fetch-based API interactions |
| `backend/api/routers/dashboard.py` | New: precache rules CRUD, download status, system status |
| `backend/api/main.py` | Mount static files, register dashboard router |
| `backend/tests/test_dashboard.py` | New: API endpoint tests |

---

## What This Does NOT Include

- Authentication for dashboard access (LAN-only, same shared-secret as Shield app)
- Real-time WebSocket updates (polling is fine for single user)
- Mobile-optimized layout
