from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from utils.security import verify_access_token

# Define routes that don't need authentication
PUBLIC_PATHS = [
    "/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/google/code",
    "/auth/refresh",
    "/auth/logout",
]


class AuthMiddleware:
    """
    Pure ASGI auth middleware.

    Unlike BaseHTTPMiddleware this does NOT buffer StreamingResponse bodies,
    which is essential for SSE / token-by-token streaming to work.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Allow OPTIONS requests for CORS
        method = scope.get("method", "")
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Check if the path is in the PUBLIC_PATHS
        path = scope.get("path", "")
        if path in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        # Parse headers from the raw ASGI scope
        headers = dict(
            (k.decode("latin-1").lower(), v.decode("latin-1"))
            for k, v in scope.get("headers", [])
        )
        auth_header = headers.get("authorization", "")

        if not auth_header or not auth_header.startswith("Bearer "):
            response = JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid authentication token"},
            )
            await response(scope, receive, send)
            return

        token = auth_header.split(" ", 1)[1]
        try:
            payload = verify_access_token(token)
        except Exception:
            response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )
            await response(scope, receive, send)
            return

        # Attach user payload to scope["state"] so request.state.user works
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["user"] = payload

        await self.app(scope, receive, send)
