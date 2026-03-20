from fastapi import FastAPI

from backend.api.routers import video

app = FastAPI(title="ShieldTube API", version="0.1.0")
app.include_router(video.router, prefix="/api")
