"""AuthManager — handles OAuth token storage, retrieval, and refresh."""

from datetime import datetime, timedelta, timezone

import aiosqlite
import httpx

from backend.config import settings
from backend.services.token_crypto import encrypt_token, decrypt_token


class AuthManager:
    """Manages OAuth tokens stored in the auth_tokens table (id=1)."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get_token(self) -> str:
        """Return a valid access token.

        Priority:
        1. DB row (id=1) that has not expired.
        2. DB row that is expired but has a refresh_token → refresh, update DB, return new.
        3. settings.youtube_access_token env var (bootstrap / dev).
        4. Raise ValueError.
        """
        row = await (
            await self._db.execute(
                "SELECT access_token, refresh_token, expires_at FROM auth_tokens WHERE id = 1"
            )
        ).fetchone()

        if row is not None:
            access_token = decrypt_token(row["access_token"])
            refresh_token = decrypt_token(row["refresh_token"]) if row["refresh_token"] else None
            expires_at_str = row["expires_at"]

            # Parse expiry — None means never-expires (unlikely but safe to treat as valid)
            if expires_at_str is None:
                return access_token

            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                # Ensure timezone-aware for comparison
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except ValueError:
                # Unparseable expiry — treat as expired and attempt refresh
                expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

            now = datetime.now(timezone.utc)

            if now < expires_at:
                # Token still valid
                return access_token

            # Token expired — try to refresh
            if refresh_token:
                token_data = await self.refresh_token_request(refresh_token)
                new_access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                new_expires_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                ).isoformat()

                await self._db.execute(
                    """UPDATE auth_tokens
                       SET access_token = ?, expires_at = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = 1""",
                    (encrypt_token(new_access_token), new_expires_at),
                )
                await self._db.commit()
                return new_access_token

        # Fall back to env var bootstrap token
        env_token = settings.youtube_access_token
        if env_token:
            return env_token

        raise ValueError("No OAuth token available")

    async def refresh_token_request(self, refresh_token: str) -> dict:
        """POST to Google's token endpoint and return the response dict.

        Returns at minimum: {"access_token": "...", "expires_in": 3600}
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_auth_headers(self) -> dict:
        """Return Authorization header dict with a valid Bearer token."""
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}
