from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx

from backend.api.middleware import SharedSecretMiddleware
from backend.db.database import init_db, close_db, get_db
from backend.config import settings
from backend.services.download_manager import DownloadManager
from backend.services.download_queue import DownloadQueue
from backend.services.feed_refresher import FeedRefresher
from backend.services.ytdlp_updater import periodic_ytdlp_update


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Bootstrap token from env vars if DB is empty
    if settings.youtube_access_token:
        from backend.db.repositories import AuthTokenRepo
        from backend.db.models import AuthToken

        db = await get_db()
        repo = AuthTokenRepo(db)
        existing = await repo.get()
        if existing is None:
            await repo.upsert(AuthToken(
                id=1,
                access_token=settings.youtube_access_token,
                refresh_token=settings.youtube_refresh_token or None,
                token_type="Bearer",
                scopes="youtube.readonly youtube.force-ssl openid email",
            ))

    # Initialize download manager
    db = await get_db()
    app.state.download_manager = DownloadManager(db)

    # Initialize download queue for pre-caching
    queue = DownloadQueue(app.state.download_manager)
    await queue.start()
    app.state.download_queue = queue

    # Initialize feed background refresher
    refresher = FeedRefresher(db, download_queue=app.state.download_queue)
    await refresher.start()
    app.state.feed_refresher = refresher

    # Start periodic yt-dlp updater (weekly)
    import asyncio
    ytdlp_task = asyncio.create_task(periodic_ytdlp_update())
    app.state.ytdlp_update_task = ytdlp_task

    yield

    if hasattr(app.state, "ytdlp_update_task"):
        app.state.ytdlp_update_task.cancel()
    if hasattr(app.state, "feed_refresher"):
        await app.state.feed_refresher.stop()
    if hasattr(app.state, "download_queue"):
        await app.state.download_queue.stop()
    await close_db()


app = FastAPI(title="ShieldTube API", version="0.3.0", lifespan=lifespan)
app.add_middleware(SharedSecretMiddleware, secret=settings.api_secret)


@app.exception_handler(httpx.TimeoutException)
async def timeout_handler(request: Request, exc: httpx.TimeoutException):
    return JSONResponse(
        status_code=503,
        content={"error": "External service timeout", "retry_after": 5},
        headers={"Retry-After": "5"},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    if "token" in str(exc).lower() or "auth" in str(exc).lower():
        return JSONResponse(status_code=401, content={"error": str(exc)})
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    import logging
    logging.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


from backend.api.routers import video, feed, search, auth, watch, cache, cast, dashboard  # noqa: E402

app.include_router(video.router, prefix="/api")
app.include_router(feed.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(watch.router, prefix="/api")
app.include_router(cache.router, prefix="/api")
app.include_router(cast.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")

# Serve dashboard static files
_dashboard_dir = Path(__file__).parent.parent / "dashboard"
if _dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_dashboard_dir), html=True), name="dashboard")
