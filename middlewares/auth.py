from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
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

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow OPTIONS requests for CORS
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check if the path is in the PUBLIC_PATHS
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
            
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid authentication token"}
            )
            
        token = auth_header.split(" ")[1]
        try:
            # We can attach the payload to request.state.user
            payload = verify_access_token(token)
            request.state.user = payload
        except Exception:
            # verify_access_token raises HTTPException, returning a 401 response instead
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"}
            )

        return await call_next(request)
