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
from services.auth_helpers import get_current_user_id, verify_attachment_ownership
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
    user_id = get_current_user_id(request)

    try:
        content = await file.read()
        content_size = len(content)
        mime_type = file.content_type or "application/octet-stream"
        safe_name = _sanitize_filename(file.filename or "attachment")
        _assert_allowed_upload(safe_name, mime_type, content_size)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] upload_attachment: read/validate failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    # Sanitize thread_id
    from services.supabase import sanitize_uuid

    tid = sanitize_uuid(thread_id)

    try:
        # Only enforce the strict 5-file limit if we are already in a specific thread.
        # This prevents 'stale' unbound files from blocking a fresh chat session.
        if tid:
            existing_files = get_attachments_for_thread(user_id, tid)
            if len(existing_files) >= settings.ATTACHMENTS_MAX_FILES_PER_MESSAGE:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Attachment limit reached for this thread. "
                        f"Max allowed is {settings.ATTACHMENTS_MAX_FILES_PER_MESSAGE}."
                    ),
                )
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[ERROR] upload_attachment: failed to fetch existing files: {exc}")
        _raise_if_missing_attachments_table(exc)
        raise

    checksum = hashlib.sha256(content).hexdigest()
    extension = os.path.splitext(safe_name)[1]
    object_name = f"{user_id}/{tid or 'unbound'}/{uuid4().hex}{extension}"

    try:
        ensure_attachments_bucket_exists()
        upload_attachment_object(object_name, content, mime_type)
    except Exception as exc:
        print(f"[ERROR] upload_attachment: storage upload failed: {exc}")
        _raise_if_missing_attachments_bucket(exc)
        raise

    try:
        record = create_attachment_record(
            user_id=user_id,
            thread_id=tid,
            filename=safe_name,
            mime_type=mime_type,
            size_bytes=content_size,
            sha256=checksum,
            storage_path=object_name,
        )
    except Exception as exc:
        print(f"[ERROR] upload_attachment: failed to create record: {exc}")
        # Cleanup storage if record creation fails
        try:
            delete_attachment_object(object_name)
        except:
            pass
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
    user_id = get_current_user_id(request)
    try:
        # If thread_id is None, we default to 'all' for this endpoint
        tid = thread_id if thread_id is not None else "all"
        return get_attachments_for_thread(user_id, tid)
    except Exception as exc:
        _raise_if_missing_attachments_table(exc)
        raise


@router.delete("/{attachment_id}")
async def delete_attachment(attachment_id: str, request: Request):
    user_id = get_current_user_id(request)
    try:
        attachment = verify_attachment_ownership(attachment_id, user_id)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        _raise_if_missing_attachments_table(exc)
        raise

    delete_attachment_object(attachment["storage_path"])
    mark_attachment_deleted(attachment_id=attachment_id, user_id=user_id)
    return {"success": True, "id": attachment_id}
