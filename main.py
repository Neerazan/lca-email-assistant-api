from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from middlewares.auth import AuthMiddleware
from routers import auth, chat, preferences
from services.store import store_pool, store
from utils.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run setup tasks before the app starts serving requests."""
    # Open the connection pool and create checkpoint tables in PostgreSQL
    await chat.pool.open()
    await chat.checkpointer.setup()
    
    # Store setup
    await store_pool.open()
    await store.setup()
    
    print("[INFO] PostgresSaver and AsyncPostgresStore ready")
    yield
    # Cleanup: close the connection pool
    await chat.pool.close()
    await store_pool.close()


app = FastAPI(title="AI Email Assistant", version="1.0.0", lifespan=lifespan)

# Note: Middlewares are executed in reverse order of how they are added.
# If we add CORS last, it executes first on incoming requests.
app.add_middleware(AuthMiddleware)

# CORS — allow your frontend to talk to this backend
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


@app.get("/")
def health_check():
    return {"status": "ok"}
