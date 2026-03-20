from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.db.database import init_db, close_db, get_db
from backend.config import settings
from backend.services.download_manager import DownloadManager
from backend.services.download_queue import DownloadQueue


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

    yield

    if hasattr(app.state, "download_queue"):
        await app.state.download_queue.stop()
    await close_db()


app = FastAPI(title="ShieldTube API", version="0.3.0", lifespan=lifespan)

from backend.api.routers import video, feed, search, auth, watch, cache  # noqa: E402

app.include_router(video.router, prefix="/api")
app.include_router(feed.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(watch.router, prefix="/api")
app.include_router(cache.router, prefix="/api")
