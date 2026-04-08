"""
Supabase service layer — all database operations.

Tables used:
  - users: identity + encrypted OAuth tokens (consolidated)
  - chat_sessions: conversation sessions per user
  - chat_messages: messages within sessions
"""

from supabase import create_client, Client
from utils.config import settings

# Use service role key on backend (bypasses RLS when needed)
supabase: Client = create_client(
    settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
)


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------


def get_user_by_google_id(google_id: str):
    """Fetch a user record by their Google ID (the 'sub' claim)."""
    response = (
        supabase.table("users")
        .select("*")
        .eq("google_id", google_id)
        .single()
        .execute()
    )
    return response.data


def get_user_by_id(user_id: str):
    """Fetch a user record by UUID primary key."""
    response = (
        supabase.table("users")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )
    return response.data


def upsert_user(
    google_id: str,
    email: str,
    full_name: str | None = None,
    avatar_url: str | None = None,
):
    """
    Create or update a user identified by google_id.
    Uses google_id as the conflict resolution key.
    """
    data = {
        "google_id": google_id,
        "email": email,
    }
    if full_name is not None:
        data["full_name"] = full_name
    if avatar_url is not None:
        data["avatar_url"] = avatar_url

    response = (
        supabase.table("users")
        .upsert(data, on_conflict="google_id")
        .execute()
    )
    return response.data


# ---------------------------------------------------------------------------
# Token operations (stored on the users table, not a separate table)
# ---------------------------------------------------------------------------


def save_user_tokens(
    google_id: str,
    access_token: str | None = None,
    refresh_token_encrypted: str | None = None,
):
    """
    Update OAuth tokens for a user.
    refresh_token_encrypted should already be Fernet-encrypted before calling this.
    """
    data: dict = {}
    if access_token is not None:
        data["access_token"] = access_token
    if refresh_token_encrypted is not None:
        data["refresh_token_encrypted"] = refresh_token_encrypted

    if not data:
        return None

    response = (
        supabase.table("users")
        .update(data)
        .eq("google_id", google_id)
        .execute()
    )
    return response.data


def get_user_tokens(google_id: str):
    """Retrieve the stored tokens for a user (refresh_token is encrypted)."""
    response = (
        supabase.table("users")
        .select("access_token, refresh_token_encrypted")
        .eq("google_id", google_id)
        .single()
        .execute()
    )
    return response.data


# ---------------------------------------------------------------------------
# Chat session operations
# ---------------------------------------------------------------------------


def create_chat_session(user_id: str, title: str = "New Chat"):
    response = (
        supabase.table("chat_sessions")
        .insert({"user_id": user_id, "title": title})
        .execute()
    )
    return response.data[0]


def get_user_sessions(user_id: str):
    response = (
        supabase.table("chat_sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


# ---------------------------------------------------------------------------
# Chat message operations
# ---------------------------------------------------------------------------


def save_message(session_id: str, role: str, content: str):
    response = (
        supabase.table("chat_messages")
        .insert({"session_id": session_id, "role": role, "content": content})
        .execute()
    )
    return response.data[0]


def get_session_messages(session_id: str):
    response = (
        supabase.table("chat_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    return response.data
