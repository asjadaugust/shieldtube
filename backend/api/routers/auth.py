from fastapi import APIRouter, Query
from datetime import datetime, timezone, timedelta
from backend.db.database import get_db
from backend.db.repositories import AuthTokenRepo
from backend.db.models import AuthToken
from backend.services.device_flow import request_device_code, poll_for_token

router = APIRouter()


@router.get("/auth/login")
async def auth_login():
    data = await request_device_code()
    return {
        "device_code": data["device_code"],
        "user_code": data["user_code"],
        "verification_url": data["verification_url"],
        "expires_in": data["expires_in"],
        "interval": data.get("interval", 5),
    }


@router.get("/auth/callback")
async def auth_callback(device_code: str = Query(...)):
    result = await poll_for_token(device_code)
    if result["status"] == "authorized":
        db = await get_db()
        repo = AuthTokenRepo(db)
        now = datetime.now(timezone.utc)
        expires_at = None
        if result.get("expires_in"):
            expires_at = (now + timedelta(seconds=result["expires_in"])).isoformat()
        await repo.upsert(AuthToken(
            id=1,
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token"),
            token_type=result.get("token_type", "Bearer"),
            expires_at=expires_at,
            scopes="youtube.readonly youtube.force-ssl openid email",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        ))
    return {"status": result["status"]}
