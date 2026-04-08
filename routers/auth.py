"""
Authentication router — handles Google OAuth token exchange.

Flow:
  1. Frontend completes Google OAuth via NextAuth
  2. Frontend's Next.js server sends tokens here via POST /auth/google
  3. We verify the id_token cryptographically (Google public keys)
  4. We upsert the user in Supabase
  5. We encrypt and store the refresh_token
  6. We return our own app_token (JWT) for subsequent API calls
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.supabase import upsert_user, save_user_tokens
from utils.google_auth import verify_google_id_token
from utils.encryption import encrypt_token
from utils.security import create_access_token

router = APIRouter()


class GoogleAuthPayload(BaseModel):
    id_token: str
    access_token: str | None = None
    refresh_token: str | None = None


@router.post("/google")
async def google_auth(payload: GoogleAuthPayload):
    """
    Verify Google identity and establish backend session.

    Security:
      - Identity is verified via id_token (cryptographic, not a network call)
      - refresh_token is encrypted before storage
      - Returns an app_token (our own JWT) — frontend uses this for all API calls
    """

    # 1. Verify the Google id_token using Google's public certificates
    try:
        idinfo = verify_google_id_token(payload.id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    google_id: str = idinfo["sub"]
    email: str = idinfo["email"]
    full_name: str | None = idinfo.get("name")
    avatar_url: str | None = idinfo.get("picture")

    # 2. Upsert the user in Supabase
    try:
        upsert_user(
            google_id=google_id,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
        )
    except Exception as e:
        print(f"Database error during upsert_user: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: missing columns? Did you run the migration? {type(e).__name__}"
        )

    # 3. Encrypt and store tokens
    encrypted_refresh = (
        encrypt_token(payload.refresh_token) if payload.refresh_token else None
    )

    try:
        save_user_tokens(
            google_id=google_id,
            access_token=payload.access_token,
            refresh_token_encrypted=encrypted_refresh,
        )
    except Exception as e:
        print(f"Database error during save_user_tokens: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error while saving tokens: {type(e).__name__}"
        )

    # 4. Issue our own app-level JWT
    app_token = create_access_token(
        data={"sub": google_id, "email": email}
    )

    return {"app_token": app_token}


@router.post("/logout")
def logout():
    """
    JWT is stateless — the client simply discards the token.
    Extend this with a token blocklist if revocation is needed.
    """
    return {"message": "Logged out successfully"}
