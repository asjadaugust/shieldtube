from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.db.database import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(title="ShieldTube API", version="0.2.0", lifespan=lifespan)

from backend.api.routers import video, feed, search  # noqa: E402

app.include_router(video.router, prefix="/api")
app.include_router(feed.router, prefix="/api")
app.include_router(search.router, prefix="/api")
