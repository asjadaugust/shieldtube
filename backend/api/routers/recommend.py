"""Recommendation endpoints: serve, sync, and status."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.db.database import get_db
from backend.db.repositories import RecommendationRepo, VideoRepo
from backend.db.models import Recommendation, RecommendationRun, Video

router = APIRouter()

STALENESS_ML_ONLY = timedelta(hours=3)
STALENESS_BLENDED = timedelta(hours=5)


class SyncVideoItem(BaseModel):
    id: str
    score: float
    reason: str | None = None
    title: str = ""
    channel_name: str = ""
    channel_id: str = ""
    view_count: int | None = None
    duration: int | None = None
    published_at: str | None = None


class SyncPayload(BaseModel):
    run_id: str
    model_name: str | None = None
    videos: list[SyncVideoItem]


@router.get("/feed/recommended")
async def get_recommended_feed():
    db = await get_db()
    rec_repo = RecommendationRepo(db)
    latest_run = await rec_repo.get_latest_run()

    now = datetime.now(timezone.utc)
    ml_recs = []
    source = "heuristic"

    if latest_run:
        run_at = datetime.fromisoformat(latest_run.run_at)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        age = now - run_at

        if age < STALENESS_ML_ONLY:
            ml_recs = await rec_repo.get_recommendations(limit=50)
            source = "ml"
        elif age < STALENESS_BLENDED:
            ml_recs = await rec_repo.get_recommendations(limit=35)
            source = "blended"

    heuristic_recs = []
    if source in ("heuristic", "blended"):
        from backend.services.heuristic_rec import HeuristicRecommender
        heuristic = HeuristicRecommender(db)
        limit = 50 if source == "heuristic" else 15
        heuristic_recs = await heuristic.get_recommendations(limit=limit)

    # Merge: ML first, then heuristic (deduplicated)
    seen_ids = set()
    videos = []
    for rec in ml_recs:
        seen_ids.add(rec.video_id)
        videos.append({
            "id": rec.video_id, "title": "", "channel_name": "", "channel_id": "",
            "view_count": None, "duration": None, "published_at": None,
            "thumbnail_url": f"/api/video/{rec.video_id}/thumbnail?res=maxres",
            "score": rec.score, "pre_cached": False,
        })
    for rec in heuristic_recs:
        if rec["id"] not in seen_ids:
            seen_ids.add(rec["id"])
            videos.append({
                "id": rec["id"], "title": rec["title"],
                "channel_name": rec["channel_name"], "channel_id": rec["channel_id"],
                "view_count": rec["view_count"], "duration": rec["duration"],
                "published_at": rec["published_at"],
                "thumbnail_url": f"/api/video/{rec['id']}/thumbnail?res=maxres",
                "score": rec.get("score", 0), "pre_cached": False,
            })

    # Enrich ML recs with video metadata from DB
    if ml_recs:
        video_repo = VideoRepo(db)
        ml_ids = [r.video_id for r in ml_recs]
        db_videos = await video_repo.get_many(ml_ids)
        db_map = {v.id: v for v in db_videos}
        for v in videos:
            if v["id"] in db_map:
                dbv = db_map[v["id"]]
                v["title"] = dbv.title
                v["channel_name"] = dbv.channel_name
                v["channel_id"] = dbv.channel_id
                v["view_count"] = dbv.view_count
                v["duration"] = dbv.duration
                v["published_at"] = dbv.published_at
                v["pre_cached"] = dbv.cache_status == "pre-cached"

    freshness = None
    if latest_run:
        run_at = datetime.fromisoformat(latest_run.run_at)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        delta = now - run_at
        hours = int(delta.total_seconds() // 3600)
        freshness = f"{hours}h ago" if hours > 0 else "just now"

    return {
        "feed_type": "recommended",
        "videos": videos,
        "source": source,
        "freshness": freshness,
        "from_cache": False,
    }


@router.get("/recommendations/status")
async def get_recommendations_status():
    db = await get_db()
    rec_repo = RecommendationRepo(db)
    latest_run = await rec_repo.get_latest_run()
    if latest_run is None:
        return {"last_updated": None, "source": None, "count": 0, "model": None}
    return {
        "last_updated": latest_run.run_at,
        "source": latest_run.source,
        "count": latest_run.video_count,
        "model": latest_run.model_name,
    }


@router.post("/recommendations/sync")
async def sync_recommendations(payload: SyncPayload):
    db = await get_db()
    rec_repo = RecommendationRepo(db)

    run = RecommendationRun(
        run_id=payload.run_id,
        run_at=datetime.now(timezone.utc).isoformat(),
        source="ml",
        model_name=payload.model_name,
        video_count=len(payload.videos),
    )
    await rec_repo.upsert_run(run)

    recs = [
        Recommendation(
            video_id=v.id, run_id=payload.run_id,
            score=v.score, source="ml", reason=v.reason,
        )
        for v in payload.videos
    ]
    await rec_repo.upsert_recommendations(payload.run_id, recs)

    # Persist video metadata so the feed endpoint can serve full cards
    video_repo = VideoRepo(db)
    for v in payload.videos:
        if v.title:
            await video_repo.upsert(Video(
                id=v.id, title=v.title, channel_name=v.channel_name,
                channel_id=v.channel_id, view_count=v.view_count,
                duration=v.duration, published_at=v.published_at,
            ))

    return {"status": "ok", "count": len(recs)}


class EnqueueBatchPayload(BaseModel):
    videos: list[SyncVideoItem]
    threshold: float = 0.7


@router.post("/download/enqueue-batch")
async def enqueue_batch_download(payload: EnqueueBatchPayload, request: Request):
    queue = getattr(request.app.state, "download_queue", None)
    if queue is None:
        return {"status": "error", "message": "Download queue not available"}

    db = await get_db()
    video_repo = VideoRepo(db)

    above_threshold = [v for v in payload.videos if v.score >= payload.threshold]
    above_threshold.sort(key=lambda v: v.score, reverse=True)

    enqueued = []
    for v in above_threshold:
        existing = await video_repo.get(v.id)
        if existing and existing.cache_status in ("cached", "pre-cached"):
            continue
        await queue.enqueue(v.id)
        enqueued.append(v.id)

    return {"status": "ok", "enqueued": len(enqueued), "video_ids": enqueued}


class BandwidthUpdate(BaseModel):
    rate_mbps: float


@router.get("/download/bandwidth")
async def get_bandwidth(request: Request):
    bw = getattr(request.app.state, "bandwidth_manager", None)
    if bw is None:
        return {"rate_mbps": 0}
    return bw.status()


@router.put("/download/bandwidth")
async def set_bandwidth(body: BandwidthUpdate, request: Request):
    bw = getattr(request.app.state, "bandwidth_manager", None)
    if bw is None:
        return {"status": "error", "message": "Bandwidth manager not available"}
    bw.rate_mbps = body.rate_mbps
    return {"status": "ok", "rate_mbps": bw.rate_mbps}
