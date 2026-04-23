import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from middlewares.auth import AuthMiddleware
from routers import attachments, auth, chat, preferences
from services.store import store
from services.db import shared_pool
from utils.config import settings
from utils.logger import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run setup tasks before the app starts serving requests."""
    # Open the shared connection pool
    await shared_pool.open()

    # Create checkpoint tables in PostgreSQL
    from agent.setup import checkpointer

    await checkpointer.setup()

    # Store setup
    await store.setup()

    print("[INFO] PostgresSaver and AsyncPostgresStore ready")
    yield
    # Cleanup: close the shared connection pool
    await shared_pool.close()
    logging.info("Application shutdown complete")


# Configure logging
logger = setup_logging()

app = FastAPI(title="AI Email Assistant", version="1.0.0", lifespan=lifespan)


# ── Pure ASGI logging middleware ──────────────────────────────────────────────
# Unlike @app.middleware("http") (which uses BaseHTTPMiddleware internally and
# buffers StreamingResponse bodies), this passes SSE streams through untouched.

_STREAMING_PATHS = {"/chat/stream", "/chat/resume"}


class LogRequestsMiddleware:
    """Log request method, path and timing without buffering responses."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        start = time.time()

        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        elapsed_ms = (time.time() - start) * 1000
        logger.info(
            f"{method} {path} - Status: {status_code} - Time: {elapsed_ms:.2f}ms"
        )


app.add_middleware(LogRequestsMiddleware)

# Note: Middlewares are executed in reverse order of how they are added.
# If we add CORS last, it executes first on incoming requests.
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(preferences.router, prefix="/preferences", tags=["preferences"])
app.include_router(attachments.router, prefix="/attachments", tags=["attachments"])


@app.get("/")
def health_check():
    return {"status": "ok"}
