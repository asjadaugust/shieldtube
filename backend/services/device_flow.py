import httpx
from backend.config import settings

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "openid email https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube.force-ssl"


async def request_device_code() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(DEVICE_CODE_URL, data={
            "client_id": settings.google_client_id,
            "scope": SCOPES,
        })
        resp.raise_for_status()
        return resp.json()


async def poll_for_token(device_code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
        data = resp.json()
        if "error" in data:
            return {"status": data["error"]}
        return {
            "status": "authorized",
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in"),
            "token_type": data.get("token_type", "Bearer"),
        }
