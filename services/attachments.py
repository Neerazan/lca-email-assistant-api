from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from services.supabase import download_attachment_object, get_attachment_by_id


@dataclass
class LoadedAttachment:
    attachment_id: str
    filename: str
    mime_type: str
    size_bytes: int
    content: bytes


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        value = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return value < datetime.now(timezone.utc)


def load_attachments_for_user(
    attachment_ids: list[str], user_id: str, thread_id: str | None = None
) -> list[LoadedAttachment]:
    loaded: list[LoadedAttachment] = []
    for attachment_id in attachment_ids:
        item = get_attachment_by_id(attachment_id=attachment_id, user_id=user_id)
        if not item:
            raise ValueError(f"Attachment not found: {attachment_id}")
        if item.get("deleted_at"):
            raise ValueError(f"Attachment is deleted: {attachment_id}")
        if _is_expired(item.get("expires_at")):
            raise ValueError(f"Attachment is expired: {attachment_id}")
        if thread_id and item.get("thread_id") and item["thread_id"] != thread_id:
            raise ValueError(f"Attachment {attachment_id} is not linked to this thread")

        content = download_attachment_object(item["storage_path"])
        loaded.append(
            LoadedAttachment(
                attachment_id=item["id"],
                filename=item["filename"],
                mime_type=item["mime_type"],
                size_bytes=item["size_bytes"],
                content=content,
            )
        )
    return loaded
