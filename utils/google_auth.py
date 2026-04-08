"""
Google OAuth utilities:
  - Verify Google id_tokens using Google's public keys
  - Refresh access_tokens using a stored refresh_token
"""

import httpx
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from utils.config import settings


def verify_google_id_token(token: str) -> dict:
    """
    Verify a Google id_token using Google's public certificates.

    Returns the decoded payload containing:
      - sub: Google user ID
      - email: user email
      - name: full name (optional)
      - picture: avatar URL (optional)

    Raises ValueError if the token is invalid or expired.
    """
    try:
        idinfo = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )

        # Ensure the token was issued by Google
        if idinfo.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise ValueError("Invalid issuer")

        return idinfo

    except Exception as exc:
        raise ValueError(f"Invalid Google id_token: {exc}") from exc


async def refresh_google_access_token(refresh_token: str) -> dict:
    """
    Use a refresh_token to obtain a new access_token from Google.

    Returns a dict with:
      - access_token: new access token
      - expires_in: seconds until expiry
      - token_type: "Bearer"
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

    if resp.status_code != 200:
        raise ValueError(f"Failed to refresh token: {resp.text}")

    return resp.json()
