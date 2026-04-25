from datetime import datetime, timedelta, timezone
from typing import Any
import uuid



from supabase import create_client, Client
from storage3.exceptions import StorageApiError
from utils.config import settings

# Use service role key on backend (bypasses RLS when needed)
supabase: Client = create_client(
    settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
)


def is_valid_uuid(val: Any) -> bool:
    """Return True if val is a valid UUID string or object."""
    if not val:
        return False
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def sanitize_uuid(val: Any) -> str | None:
    """
    Normalize a potential UUID string.
    Returns None if the string is empty, 'null', 'undefined', or invalid.
    """
    if not val:
        return None
    s = str(val).strip().lower()
    if s in ("null", "undefined", "none", ""):
        return None
    if is_valid_uuid(val):
        return str(val)
    return None


# User operations
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
    uid = sanitize_uuid(user_id)
    if not uid:
        return None
    response = (
        supabase.table("users")
        .select("*")
        .eq("id", uid)
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


def delete_user(google_id: str):
    """
    Permanently delete a user record by their Google ID.
    """
    response = (
        supabase.table("users")
        .delete()
        .eq("google_id", google_id)
        .execute()
    )
    return response.data


# Token operations (stored on the users table, not a separate table)
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



# Chat session operations
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

def get_chat_session(session_id: str):
    sid = sanitize_uuid(session_id)
    if not sid:
        return None
    response = (
        supabase.table("chat_sessions")
        .select("*")
        .eq("id", sid)
        .single()
        .execute()
    )
    return response.data

def delete_chat_session(session_id: str):
    sid = sanitize_uuid(session_id)
    if not sid:
        return None
    response = (
        supabase.table("chat_sessions")
        .delete()
        .eq("id", sid)
        .execute()
    )
    return response.data

def update_chat_session_title(session_id: str, title: str):
    sid = sanitize_uuid(session_id)
    if not sid:
        return None
    response = (
        supabase.table("chat_sessions")
        .update({"title": title})
        .eq("id", sid)
        .execute()
    )
    return response.data


# Chat message operations
def save_message(session_id: str, role: str, content: str):
    sid = sanitize_uuid(session_id)
    if not sid:
        raise ValueError("Invalid session_id")
    response = (
        supabase.table("chat_messages")
        .insert({"session_id": sid, "role": role, "content": content})
        .execute()
    )
    return response.data[0]


def save_message_with_metadata(
    session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None
):
    sid = sanitize_uuid(session_id)
    if not sid:
        raise ValueError("Invalid session_id")
    response = (
        supabase.table("chat_messages")
        .insert(
            {
                "session_id": sid,
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
        )
        .execute()
    )
    return response.data[0]


def get_session_messages(session_id: str):
    sid = sanitize_uuid(session_id)
    if not sid:
        return []
    response = (
        supabase.table("chat_messages")
        .select("*")
        .eq("session_id", sid)
        .order("created_at")
        .execute()
    )
    return response.data


# Attachment operations
def create_attachment_record(
    user_id: str,
    thread_id: str | None,
    filename: str,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    storage_path: str,
):
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.ATTACHMENTS_TTL_HOURS)
    payload = {
        "user_id": user_id,
        "thread_id": sanitize_uuid(thread_id),
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "storage_path": storage_path,
        "storage_bucket": settings.SUPABASE_ATTACHMENTS_BUCKET,
        "expires_at": expires_at.isoformat(),
    }
    response = supabase.table("chat_attachments").insert(payload).execute()
    return response.data[0]


def get_attachment_by_id(attachment_id: str, user_id: str):
    # Validate UUID to prevent Postgres errors (e.g. invalid input syntax for type uuid)
    aid = sanitize_uuid(attachment_id)
    if not aid:
        return None

    response = (
        supabase.table("chat_attachments")
        .select("*")
        .eq("id", aid)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return response.data


def get_attachments_for_thread(user_id: str, thread_id: str | None = None):
    """
    Fetch attachments for a user.
    If thread_id is provided, filters by that thread.
    If thread_id is None, returns 'unbound' attachments.
    """
    query = (
        supabase.table("chat_attachments")
        .select("*")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
    )
    
    if thread_id == "all":
        # No additional filtering, returns all user attachments
        pass
    elif thread_id is None:
        query = query.is_("thread_id", "null")
    else:
        tid = sanitize_uuid(thread_id)
        if tid:
            query = query.eq("thread_id", tid)
        else:
            query = query.is_("thread_id", "null")

    response = query.execute()
    return response.data


def mark_attachment_deleted(attachment_id: str, user_id: str):
    aid = sanitize_uuid(attachment_id)
    if not aid:
        return
    response = (
        supabase.table("chat_attachments")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", aid)
        .eq("user_id", user_id)
        .execute()
    )
    return response.data


def link_attachments_to_thread(attachment_ids: list[str], user_id: str, thread_id: str):
    """
    Persistently link a list of attachments to a thread.
    Only links attachments that are currently 'unbound' (thread_id is null).
    """
    tid = sanitize_uuid(thread_id)
    if not tid or not attachment_ids:
        return
    
    valid_ids = [aid for aid in attachment_ids if is_valid_uuid(aid)]
    if not valid_ids:
        return

    try:
        supabase.table("chat_attachments") \
            .update({"thread_id": tid}) \
            .in_("id", valid_ids) \
            .eq("user_id", user_id) \
            .is_("thread_id", "null") \
            .execute()
    except Exception as exc:
        print(f"[WARN] supabase: failed to link attachments to thread: {exc}")


def get_expired_attachments():
    now_iso = datetime.now(timezone.utc).isoformat()
    response = (
        supabase.table("chat_attachments")
        .select("*")
        .lte("expires_at", now_iso)
        .is_("deleted_at", "null")
        .execute()
    )
    return response.data


def purge_attachment_record(attachment_id: str):
    response = supabase.table("chat_attachments").delete().eq("id", attachment_id).execute()
    return response.data


def upload_attachment_object(path: str, content: bytes, mime_type: str):
    return supabase.storage.from_(settings.SUPABASE_ATTACHMENTS_BUCKET).upload(
        path,
        content,
        {
            "content-type": mime_type,
            "upsert": "false",
        },
    )


def download_attachment_object(path: str):
    return supabase.storage.from_(settings.SUPABASE_ATTACHMENTS_BUCKET).download(path)


def delete_attachment_object(path: str):
    return supabase.storage.from_(settings.SUPABASE_ATTACHMENTS_BUCKET).remove([path])


def ensure_attachments_bucket_exists():
    """
    Ensure the configured attachments bucket exists.
    Creates a private bucket when missing.
    """
    bucket_name = settings.SUPABASE_ATTACHMENTS_BUCKET
    try:
        supabase.storage.get_bucket(bucket_name)
    except StorageApiError as exc:
        if "Bucket not found" not in str(exc):
            raise
        supabase.storage.create_bucket(
            bucket_name,
            options={"public": False, "file_size_limit": str(settings.ATTACHMENTS_MAX_FILE_SIZE_BYTES)},
        )
