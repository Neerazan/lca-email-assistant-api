from supabase import create_client, Client
from utils.config import settings

# Use service role key on backend (bypasses RLS when needed)
supabase: Client = create_client(
    settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
)

# --- User operations ---


def get_user_by_id(user_id: str):
    response = supabase.table("users").select("*").eq("id", user_id).single().execute()
    return response.data


def create_user(
    user_id: str, email: str, full_name: str = None, avatar_url: str = None
):
    response = (
        supabase.table("users")
        .upsert(
            {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "avatar_url": avatar_url,
            }
        )
        .execute()
    )
    return response.data


# --- Token operations ---


def save_oauth_tokens(user_id: str, access_token: str, refresh_token: str, expires_at):
    response = (
        supabase.table("oauth_tokens")
        .upsert(
            {
                "user_id": user_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at.isoformat(),
                "updated_at": "now()",
            }
        )
        .execute()
    )
    return response.data


def get_oauth_tokens(user_id: str):
    response = (
        supabase.table("oauth_tokens")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return response.data


# --- Chat session operations ---


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


# --- Chat message operations ---


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
