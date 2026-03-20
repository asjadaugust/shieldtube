"""Shared-secret authentication middleware for ShieldTube API."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


EXEMPT_PREFIXES = (
    "/docs",
    "/openapi.json",
    "/redoc",
    "/dashboard",
    "/api/auth/login",
    "/api/auth/callback",
)


class SharedSecretMiddleware(BaseHTTPMiddleware):
    """Reject requests missing or mismatching X-ShieldTube-Secret header.

    If ``secret`` is empty, all requests pass through (dev mode).
    """

    def __init__(self, app, secret: str = ""):
        super().__init__(app)
        self.secret = secret

    async def dispatch(self, request: Request, call_next):
        if not self.secret:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
            return await call_next(request)

        provided = request.headers.get("X-ShieldTube-Secret", "")
        if provided != self.secret:
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized: invalid or missing API secret"},
            )

        return await call_next(request)
