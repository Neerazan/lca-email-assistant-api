from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from middlewares.auth import AuthMiddleware
from routers import auth, chat
from utils.config import settings

app = FastAPI(title="AI Email Assistant", version="1.0.0")

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


@app.get("/")
def health_check():
    return {"status": "ok"}
