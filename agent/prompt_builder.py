"""
agent/prompt_builder.py
------------------------
Builds structured prompts for the email assistant agent and prepares
safe message history for each LangGraph turn.
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
    filter_messages,
    trim_messages,
)
from langchain_openai import ChatOpenAI

from services.attachment_extractor import AttachmentKind, ExtractedAttachment
from services.preferences import get_user_preferences
from services.store import get_memories
from utils.config import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_TEXT_CHARS = 12_000
_MAX_HISTORY_TOKENS = 28_000

_token_counter = ChatOpenAI(
    model="gpt-4.1-nano",
    api_key=settings.OPENAI_API_KEY,
)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
You are an AI email assistant for {full_name}. You have full access to their Gmail.

CORE PRINCIPLES:
- BE EXTREMELY CONCISE. Minimize conversational filler, pleasantries, and introductory phrases.
- ACTION-ORIENTED. Provide the requested data directly. Do not ask "What would you like to do next?" or "Would you like me to [action]?" unless there is a genuine, non-obvious ambiguity.
- NO BOILERPLATE. Never add trailing questions like "Would you like to review?" or "Anything else?" after fulfilling a request. Assume the user will provide the next instruction.

RULES — follow these exactly:
- Execute tasks immediately and silently. Never say "please hold on", "one moment", or announce that you are about to do something — just do it.
- After creating a draft, always display the full email (To, Subject, Body) right away.
- Never ask about tone, style, length, or formality — use the user's saved preferences.
- Never ask for the recipient if one is mentioned in relationships or custom instructions.
- ask_clarifying_questions is currently: {ask_clarifying_questions}. If False, NEVER ask any clarifying question — proceed with reasonable assumptions always.
- Only ask ONE clarifying question if a critical piece of information is truly missing and cannot be guessed at all (e.g. two equally possible recipients).
- Default action is: {default_action}. Only call send_email when the user explicitly says "send" or "send it" or "yes send it".
- If the user has already said "send it" or "yes send it", treat that as confirmation and send immediately. Do NOT ask "please confirm" again.
- Always respond in: {language}

USER PREFERENCES:
- Tone: {tone}
- Email length: {length}
- Relationships: {relationships}
- Signature: {signature}
- Custom instructions: {custom_instructions}

OUTPUT FORMATTING:
- For email lists: Use a clean, scannable format (e.g., bullet points or a table). Include Subject, Sender, and a brief snippet.
- For email details: Show To, Subject, and Body clearly. Use horizontal rules to separate multiple emails.

TOOLS:
- search_emails: search Gmail. Use first when no message ID is known.
- get_email: fetch full email by Gmail message ID only.
- get_thread: fetch full thread by Gmail thread ID.
- send_email: send immediately. User must have explicitly said "send" in this conversation.
- create_draft: save as draft. This is the default.
- save_memory: save a durable fact about the user for future sessions.
- delete_memory: remove an outdated memory by its exact key.

{memory_section}

{attachment_section}
"""

_FALLBACK_SYSTEM = """\
You are an AI email assistant. You have full access to the user's Gmail.
Execute tasks immediately — never announce what you are about to do, just do it.
After creating a draft, always display the full email right away.
Default to create_draft. Only call send_email when the user explicitly says "send".
If the user says "yes send it" or "send it", that is confirmation — send without asking again.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def build_prompt_parts(
    user_id: str,
    human_text: str,
    prefs: dict | None = None,
    extracted_attachments: list[ExtractedAttachment] | None = None,
    message_history: list[BaseMessage] | None = None,
) -> tuple[SystemMessage, list[dict], list[BaseMessage]]:
    """
    Build all inputs needed for one LangGraph agent turn.

    Returns a 3-tuple:
        system_msg      — Fully rendered SystemMessage.
        human_content   — Content block list for HumanMessage.
        trimmed_history — Filtered + trimmed prior messages.
    """
    attachments = extracted_attachments or []

    text_attachments = [a for a in attachments if a.kind == AttachmentKind.TEXT]
    image_attachments = [a for a in attachments if a.kind == AttachmentKind.IMAGE]
    unknown_attachments = [a for a in attachments if a.kind == AttachmentKind.UNKNOWN]

    system_msg = await _render_system_message(
        user_id, prefs, text_attachments, unknown_attachments
    )
    human_content = _build_human_content(human_text, image_attachments)
    safe_history = _prepare_history(message_history or [])

    return system_msg, human_content, safe_history


# ---------------------------------------------------------------------------
# System message rendering
# ---------------------------------------------------------------------------


async def _render_system_message(
    user_id: str,
    prefs: dict | None,
    text_attachments: list[ExtractedAttachment],
    unknown_attachments: list[ExtractedAttachment],
) -> SystemMessage:
    if prefs is None:
        prefs = get_user_preferences(user_id)

    if not prefs:
        return SystemMessage(content=_FALLBACK_SYSTEM, id="system_prompt")

    memory_section = await _build_memory_section(user_id, prefs)
    attachment_section = _build_text_attachment_section(
        text_attachments, unknown_attachments
    )

    content = _SYSTEM_TEMPLATE.format(
        full_name=prefs.get("full_name", "the user"),
        language=prefs.get("language", "en"),
        tone=prefs.get("tone", "formal"),
        length=prefs.get("length", "medium"),
        default_action=prefs.get("default_action", "draft"),
        ask_clarifying_questions=prefs.get("ask_clarifying_questions", True),
        relationships=prefs.get("relationships", "None specified"),
        signature=prefs.get("signature", ""),
        custom_instructions=prefs.get("custom_instructions", "None"),
        memory_section=memory_section,
        attachment_section=attachment_section,
    )

    return SystemMessage(content=content, id="system_prompt")


async def _build_memory_section(user_id: str, prefs: dict) -> str:
    if not prefs.get("ai_memory_enabled", True):
        return ""

    memories = await get_memories(user_id)
    if not memories:
        return ""

    lines = "\n".join(
        f"  - [{m.key}]: {m.value.get('memory')}"
        for m in memories
        if isinstance(m.value, dict) and "memory" in m.value
    )
    return f"SAVED MEMORIES:\n{lines}"


def _build_text_attachment_section(
    text_attachments: list[ExtractedAttachment],
    unknown_attachments: list[ExtractedAttachment],
) -> str:
    if not text_attachments and not unknown_attachments:
        return ""

    parts: list[str] = ["UPLOADED FILES:"]

    for att in text_attachments:
        content = att.text_content or ""
        if len(content) > _MAX_TEXT_CHARS:
            content = (
                content[:_MAX_TEXT_CHARS]
                + f"\n... [truncated at {_MAX_TEXT_CHARS} chars]"
            )
        parts.append(
            f'[id="{att.attachment_id}" name="{att.filename}" type="{att.mime_type}"]\n'
            f"{content}"
        )

    for att in unknown_attachments:
        parts.append(
            f'[id="{att.attachment_id}" name="{att.filename}" type="{att.mime_type}"]\n'
            f"[Content could not be extracted. You can still attach it using its ID.]"
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Human message content builder
# ---------------------------------------------------------------------------


def _build_human_content(
    human_text: str,
    image_attachments: list[ExtractedAttachment],
) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": human_text}]

    for att in image_attachments:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{att.image_media_type};base64,{att.image_base64}",
                    "detail": "high",
                },
            }
        )
        content.append(
            {
                "type": "text",
                "text": (
                    f"[Image — Name: {att.filename} | "
                    f"Attachment ID: {att.attachment_id} | Type: {att.mime_type}]"
                ),
            }
        )

    return content


# ---------------------------------------------------------------------------
# Message history: filter + trim
# ---------------------------------------------------------------------------


def _prepare_history(history: list[BaseMessage]) -> list[BaseMessage]:
    """
    Filter stale system messages and trim to context window limit.
    Fails open — returns full filtered history if trim fails.
    """
    if not history:
        return []

    filtered = filter_messages(history, include_types=["human", "ai", "tool"])
    if not filtered:
        return []

    try:
        trimmed = trim_messages(
            filtered,
            max_tokens=_MAX_HISTORY_TOKENS,
            token_counter=_token_counter,
            strategy="last",
            start_on="human",
            include_system=False,
            allow_partial=False,
        )
    except Exception as exc:
        print(f"[WARN] prompt_builder: trim_messages failed, using full history: {exc}")
        trimmed = filtered

    # Strip unanswered tool_calls from last AIMessage to avoid OpenAI rejection
    if trimmed and isinstance(trimmed[-1], AIMessage) and trimmed[-1].tool_calls:
        has_tool_response = any(isinstance(m, ToolMessage) for m in trimmed)
        if not has_tool_response:
            print(
                "[INFO] prompt_builder: stripping unanswered tool_calls from last AIMessage"
            )
            last_msg = trimmed[-1]
            trimmed[-1] = AIMessage(
                content=last_msg.content,
                additional_kwargs={
                    k: v
                    for k, v in last_msg.additional_kwargs.items()
                    if k != "tool_calls"
                },
                id=last_msg.id,
            )

    return trimmed
