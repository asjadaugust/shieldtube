import json
import time
from pathlib import Path
from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.config import settings
from backend.db.database import get_db
from backend.db.repositories import AuthTokenRepo

router = APIRouter()

_start_time = time.time()


@router.get("/system/status")
async def system_status(request: Request):
    """Return system info."""
    uptime_seconds = int(time.time() - _start_time)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60

    # Check auth status
    db = await get_db()
    token = await AuthTokenRepo(db).get()
    auth_status = "authenticated" if token and not token.is_expired else "not authenticated"

    # Check download queue
    queue = getattr(request.app.state, "download_queue", None)
    queue_size = queue.pending_count if queue else 0

    return {
        "version": "0.3.0",
        "uptime": f"{hours}h {minutes}m",
        "uptime_seconds": uptime_seconds,
        "auth_status": auth_status,
        "download_queue_size": queue_size,
        "cache_dir": settings.cache_dir,
    }


@router.get("/precache/rules")
async def get_precache_rules():
    """Return current pre-cache rules."""
    rules_path = Path("config/precache_rules.json")
    if not rules_path.exists():
        return {"precache_rules": []}
    return json.loads(rules_path.read_text())


class PrecacheRulesBody(BaseModel):
    precache_rules: list[dict]


@router.post("/precache/rules")
async def save_precache_rules(body: PrecacheRulesBody):
    """Overwrite pre-cache rules file."""
    rules_path = Path("config/precache_rules.json")
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(json.dumps({"precache_rules": body.precache_rules}, indent=2))
    return {"status": "saved", "count": len(body.precache_rules)}
