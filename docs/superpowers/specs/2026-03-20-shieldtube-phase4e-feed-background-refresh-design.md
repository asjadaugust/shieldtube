# Phase 4e: Feed Background Refresh — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 4: Polish + P1 Features

---

## Goal

Background task refreshes feeds on a schedule so they're pre-loaded when the user opens the app.

**Success criteria:** Start backend → feeds refresh automatically in background → open app → Home feed loads instantly from cache.

---

## Design

Single asyncio periodic task in the FastAPI lifespan. Two refresh intervals matching the PRD:

- **Home feed:** every 15 minutes
- **Subscriptions:** every 5 minutes

**Implementation:**

```python
# backend/services/feed_refresher.py
async def start_feed_refresher(app):
    """Background task that periodically refreshes feeds."""
    task = asyncio.create_task(_refresh_loop(app))
    app.state.feed_refresher = task

async def _refresh_loop(app):
    home_interval = 900   # 15 minutes
    subs_interval = 300   # 5 minutes
    last_home = 0
    last_subs = 0

    while True:
        await asyncio.sleep(60)  # Check every minute
        now = time.time()

        if now - last_home >= home_interval:
            # Refresh home feed via YouTubeAPI
            last_home = now

        if now - last_subs >= subs_interval:
            # Refresh subscriptions feed
            last_subs = now
```

- Reuses existing `YouTubeAPI.get_home_feed()` and `get_subscriptions()` which already handle ETag caching
- Upserts video metadata and triggers thumbnail caching (same as endpoint flow)
- Also triggers pre-cache rule check on fresh data
- All errors caught and logged — never crash the refresh loop

**Files:**

| File | Change |
|------|--------|
| `backend/services/feed_refresher.py` | New: periodic refresh loop |
| `backend/api/main.py` | Start/stop refresher in lifespan |
| `backend/tests/test_feed_refresher.py` | New: tests with mocked API |

---

## What This Phase Does NOT Include

- Push notifications to Shield app
- Configurable refresh intervals (hardcoded for now)
- Feed refresh status API
