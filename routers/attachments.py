import hashlib
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from postgrest.exceptions import APIError

from services.supabase import (
    create_attachment_record,
    delete_attachment_object,
    ensure_attachments_bucket_exists,
    get_attachment_by_id,
    get_attachments_for_thread,
    get_user_by_google_id,
    mark_attachment_deleted,
    upload_attachment_object,
)
from utils.config import settings
from storage3.exceptions import StorageApiError

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/json",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png",
    "image/jpeg",
}
MAX_FILE_SIZE = settings.ATTACHMENTS_MAX_FILE_SIZE_BYTES


def _raise_if_missing_attachments_table(exc: Exception) -> None:
    if isinstance(exc, APIError) and "PGRST205" in str(exc):
        raise HTTPException(
            status_code=503,
            detail=(
                "Attachment database table is missing. "
                "Run migration scripts/003_add_chat_attachments.sql in Supabase SQL Editor."
            ),
        ) from exc


def _raise_if_missing_attachments_bucket(exc: Exception) -> None:
    if isinstance(exc, StorageApiError) and "Bucket not found" in str(exc):
        raise HTTPException(
            status_code=503,
            detail=(
                "Attachments storage bucket is missing. "
                f"Create a private bucket named '{settings.SUPABASE_ATTACHMENTS_BUCKET}' in Supabase Storage."
            ),
        ) from exc


def _sanitize_filename(filename: str) -> str:
    clean = re.sub(r"[^\w.\- ]+", "_", filename).strip()
    return clean or "attachment"


def _assert_allowed_upload(file_name: str, mime_type: str, content_size: int) -> None:
    if not file_name:
        raise HTTPException(status_code=400, detail="Filename is required.")
    if content_size <= 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if content_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds size limit of {MAX_FILE_SIZE} bytes.",
        )
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {mime_type}",
        )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/upload")
async def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    thread_id: str | None = Form(default=None),
):
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    content = await file.read()
    content_size = len(content)
    mime_type = file.content_type or "application/octet-stream"
    safe_name = _sanitize_filename(file.filename or "attachment")
    _assert_allowed_upload(safe_name, mime_type, content_size)

    try:
        existing_files = get_attachments_for_thread(user["id"], thread_id)
    except Exception as exc:
        _raise_if_missing_attachments_table(exc)
        raise
    if len(existing_files) >= settings.ATTACHMENTS_MAX_FILES_PER_MESSAGE:
        raise HTTPException(
            status_code=400,
            detail=(
                "Attachment limit reached for this thread. "
                f"Max allowed is {settings.ATTACHMENTS_MAX_FILES_PER_MESSAGE}."
            ),
        )

    checksum = hashlib.sha256(content).hexdigest()
    extension = os.path.splitext(safe_name)[1]
    object_name = f"{user['id']}/{thread_id or 'unbound'}/{uuid4().hex}{extension}"
    try:
        ensure_attachments_bucket_exists()
        upload_attachment_object(object_name, content, mime_type)
    except Exception as exc:
        _raise_if_missing_attachments_bucket(exc)
        raise

    try:
        record = create_attachment_record(
            user_id=user["id"],
            thread_id=thread_id,
            filename=safe_name,
            mime_type=mime_type,
            size_bytes=content_size,
            sha256=checksum,
            storage_path=object_name,
        )
    except Exception as exc:
        _raise_if_missing_attachments_table(exc)
        raise
    return {
        "id": record["id"],
        "filename": record["filename"],
        "mime_type": record["mime_type"],
        "size_bytes": record["size_bytes"],
        "thread_id": record["thread_id"],
        "created_at": record["created_at"],
        "uploaded_at": _utcnow_iso(),
    }


@router.get("")
async def list_attachments(request: Request, thread_id: str | None = None):
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return get_attachments_for_thread(user["id"], thread_id)
    except Exception as exc:
        _raise_if_missing_attachments_table(exc)
        raise


@router.delete("/{attachment_id}")
async def delete_attachment(attachment_id: str, request: Request):
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        attachment = get_attachment_by_id(attachment_id=attachment_id, user_id=user["id"])
    except Exception as exc:
        _raise_if_missing_attachments_table(exc)
        raise
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    delete_attachment_object(attachment["storage_path"])
    mark_attachment_deleted(attachment_id=attachment_id, user_id=user["id"])
    return {"success": True, "id": attachment_id}
