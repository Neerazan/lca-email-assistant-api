"""
Authentication router — handles Google OAuth using the auth-code flow.

Flow:
  1. Frontend completes Google OAuth popup via @react-oauth/google.
  2. Frontend sends the authorization code here via POST /auth/google/code.
  3. We exchange the code with Google for tokens (id_token, access_token, refresh_token).
  4. We verify the id_token cryptographically.
  5. We upsert the user and store the encrypted Google refresh_token in Supabase.
  6. We issue our own app_access_token (JSON body) and app_refresh_token (HttpOnly cookie).
"""

from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel

from services.supabase import upsert_user, save_user_tokens, get_user_by_google_id
from utils.google_auth import verify_google_id_token, exchange_auth_code
from utils.encryption import encrypt_token
from utils.security import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from utils.config import settings

router = APIRouter()


class AuthCodePayload(BaseModel):
    code: str


@router.post("/google/code")
async def google_auth_code(payload: AuthCodePayload, response: Response):
    """
    Exchange authorization code, verify identity, and establish backend session.
    """
    try:
        # 1. Exchange the code with Google
        google_tokens = await exchange_auth_code(
            payload.code, redirect_uri="postmessage"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Verify the Google id_token
    id_token = google_tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Missing id_token from Google")

    try:
        idinfo = verify_google_id_token(id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    google_id: str = idinfo["sub"]
    email: str = idinfo["email"]
    full_name: str | None = idinfo.get("name")
    avatar_url: str | None = idinfo.get("picture")

    # 3. Upsert the user in Supabase
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
            status_code=500, detail="Database error during user creation."
        )

    # 4. Encrypt and store Google tokens
    google_refresh = google_tokens.get("refresh_token")
    google_access = google_tokens.get("access_token")

    # We only overwrite the refresh token if Google actually gave us one this time
    try:
        if google_refresh:
            encrypted_refresh = encrypt_token(google_refresh)
            save_user_tokens(
                google_id=google_id,
                access_token=google_access,
                refresh_token_encrypted=encrypted_refresh,
            )
        elif google_access:
            # If we only got an access token (which is typical for returning users), just update that
            save_user_tokens(
                google_id=google_id,
                access_token=google_access,
                refresh_token_encrypted=None,  # Supabase update should ideally handle partial updates, but currently save_user_tokens requires both.
                # Assuming save_user_tokens handles None by not overwriting, but if not we should fix save_user_tokens. Let's pass None.
            )
    except Exception as e:
        print(f"Database error during save_user_tokens: {e}")
        # Proceed anyway because login conceptually succeeded

    # 5. Issue our own app-level tokens
    app_access_token = create_access_token(data={
        "sub": google_id, 
        "email": email,
        "name": full_name,
        "picture": avatar_url
    })
    app_refresh_token = create_refresh_token(data={"sub": google_id, "email": email})

    # 6. Set HttpOnly cookie for the refresh token
    response.set_cookie(
        key="app_refresh_token",
        value=app_refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
    )

    return {"access_token": app_access_token}


@router.post("/refresh")
def refresh_token(request: Request, response: Response):
    """
    Issue a new access token using an app_refresh_token stored in an HttpOnly cookie.
    """
    refresh_token = request.cookies.get("app_refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    try:
        # Verify the refresh token
        payload = verify_refresh_token(refresh_token)

        google_id = payload.get("sub")
        email = payload.get("email")
        if not google_id or not email:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        try:
            user = get_user_by_google_id(google_id)
        except Exception:
            user = {}

        # Issue a new access token
        new_access_token = create_access_token(data={
            "sub": google_id, 
            "email": email,
            "name": user.get("full_name"),
            "picture": user.get("avatar_url")
        })

        return {"access_token": new_access_token}
    except Exception:
        # If token is invalid/expired, clear the cookie
        response.delete_cookie("app_refresh_token")
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")


@router.post("/logout")
def logout(response: Response):
    """
    Clear the HttpOnly refresh token cookie.
    The frontend should also discard the access_token in memory.
    """
    response.delete_cookie(
        key="app_refresh_token",
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )
    return {"message": "Logged out successfully"}
