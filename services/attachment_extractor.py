"""
services/attachment_extractor.py
---------------------------------
Downloads and processes uploaded attachments so the LLM can understand
their contents regardless of file type.

Handling strategy per MIME type:
  - PDF              → text extraction via pdfplumber
  - DOCX / DOC       → text extraction via docx2txt
  - XLSX / XLS       → row extraction via openpyxl
  - CSV              → parsed via csv module
  - Plain text / MD  → UTF-8 decode
  - Images           → base64-encoded for LLM vision blocks (jpeg, png, gif, webp)
  - Others           → gracefully marked UNKNOWN; still attachable to emails by ID

Dependencies (add to requirements.txt):
    pdfplumber
    docx2txt
    openpyxl
"""

from __future__ import annotations

import base64
import csv
import io
from dataclasses import dataclass
from enum import Enum

import docx2txt
import openpyxl
import pdfplumber

from services.attachments import LoadedAttachment, load_attachments_for_user


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class AttachmentKind(str, Enum):
    TEXT = "text"  # Extracted readable text  → inject into system prompt
    IMAGE = (
        "image"  # Raw image bytes           → inject as vision block in HumanMessage
    )
    UNKNOWN = "unknown"  # Unsupported / failed      → note by filename + ID only


@dataclass
class ExtractedAttachment:
    attachment_id: str
    filename: str
    mime_type: str
    size_bytes: int
    kind: AttachmentKind
    # TEXT kind
    text_content: str | None = None
    # IMAGE kind
    image_base64: str | None = None
    image_media_type: str | None = None  # e.g. "image/png"


# ---------------------------------------------------------------------------
# MIME type sets
# ---------------------------------------------------------------------------

_IMAGE_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }
)

_DOCX_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }
)

_XLSX_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_text_from_attachment(loaded: LoadedAttachment) -> ExtractedAttachment:
    """
    Given a LoadedAttachment (raw bytes already downloaded from Supabase Storage),
    extract its content into a form the LLM can consume.

    - Images   → base64-encoded vision block
    - Text-based files → extracted readable text
    - Unsupported → UNKNOWN kind (still attachable by ID)
    """
    mime = (loaded.mime_type or "").lower().strip()

    # ── Images ──────────────────────────────────────────────────────────────
    if mime in _IMAGE_MIME_TYPES:
        return ExtractedAttachment(
            attachment_id=loaded.attachment_id,
            filename=loaded.filename,
            mime_type=mime,
            size_bytes=loaded.size_bytes,
            kind=AttachmentKind.IMAGE,
            image_base64=base64.b64encode(loaded.content).decode("utf-8"),
            image_media_type=mime,
        )

    # ── Text-based ───────────────────────────────────────────────────────────
    text: str | None = None
    try:
        if mime == "application/pdf":
            text = _extract_pdf(loaded.content)

        elif mime in _DOCX_MIME_TYPES:
            text = _extract_docx(loaded.content)

        elif mime in _XLSX_MIME_TYPES:
            text = _extract_xlsx(loaded.content)

        elif mime == "text/csv":
            text = _extract_csv(loaded.content)

        elif mime.startswith("text/"):
            # Covers text/plain, text/markdown, text/html, etc.
            text = loaded.content.decode("utf-8", errors="replace")

    except Exception as exc:
        print(
            f"[WARN] attachment_extractor: failed to extract '{loaded.filename}': {exc}"
        )
        text = None

    if text is not None:
        return ExtractedAttachment(
            attachment_id=loaded.attachment_id,
            filename=loaded.filename,
            mime_type=mime,
            size_bytes=loaded.size_bytes,
            kind=AttachmentKind.TEXT,
            text_content=text,
        )

    # ── Unsupported / extraction failed ─────────────────────────────────────
    print(
        f"[WARN] attachment_extractor: no extraction strategy for "
        f"mime_type='{mime}' file='{loaded.filename}' — marking as UNKNOWN"
    )
    return ExtractedAttachment(
        attachment_id=loaded.attachment_id,
        filename=loaded.filename,
        mime_type=mime,
        size_bytes=loaded.size_bytes,
        kind=AttachmentKind.UNKNOWN,
    )


def load_and_extract_attachments(
    attachment_ids: list[str],
    user_id: str,
    thread_id: str | None = None,
) -> list[ExtractedAttachment]:
    """
    Downloads attachments from Supabase Storage then extracts their content.

    Raises ValueError (propagated from load_attachments_for_user) if any
    attachment is missing, soft-deleted, expired, or belongs to a different thread.
    """
    loaded_list = load_attachments_for_user(
        attachment_ids=attachment_ids,
        user_id=user_id,
        thread_id=thread_id,
    )
    return [extract_text_from_attachment(item) for item in loaded_list]


# ---------------------------------------------------------------------------
# Private extractors
# ---------------------------------------------------------------------------


def _extract_pdf(raw_bytes: bytes) -> str:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text.strip())
    return "\n\n".join(parts)


def _extract_docx(raw_bytes: bytes) -> str:
    return docx2txt.process(io.BytesIO(raw_bytes))


def _extract_xlsx(raw_bytes: bytes) -> str:
    wb = openpyxl.load_workbook(
        io.BytesIO(raw_bytes),
        read_only=True,
        data_only=True,
    )
    sheet_parts: list[str] = []
    for sheet in wb.worksheets:
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c.strip() for c in cells):
                rows.append("\t".join(cells))
        if rows:
            sheet_parts.append(f"[Sheet: {sheet.title}]\n" + "\n".join(rows))
    return "\n\n".join(sheet_parts)


def _extract_csv(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = ["\t".join(row) for row in reader if any(cell.strip() for cell in row)]
    return "\n".join(rows)
