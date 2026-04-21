"""FastAPI router for the AI email assistant chat endpoints."""
from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field

from agent.prompt_builder import build_prompt_parts
from agent.setup import agent
from agent.utils import _serialize_interrupt
from services.attachment_extractor import load_and_extract_attachments
from services.supabase import (
    create_chat_session,
    delete_chat_session,
    get_attachments_for_thread,
    get_chat_session,
    get_session_messages,
    get_user_by_google_id,
    get_user_sessions,
    link_attachments_to_thread,
    save_message,
    save_message_with_metadata,
    update_chat_session_title,
)
from utils.config import settings

router = APIRouter()

title_llm = ChatOpenAI(
    model="gpt-4.1-nano",
    temperature=0,
    api_key=settings.OPENAI_API_KEY,
)


class AttachmentRef(BaseModel):
    attachment_id: str
    filename: str | None = None
    mime_type: str | None = None


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    attachments: list[AttachmentRef] = Field(default_factory=list)


class ResumeRequest(BaseModel):
    thread_id: str
    decisions: list[dict]


# SSE Helpers
def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _safe_stream_error() -> str:
    return (
        "I ran into an unexpected error while processing that request. "
        "Please try again."
    )


# Langgraph Config
def _get_langgraph_config(google_id: str | None, thread_id: str) -> dict:
    return {"configurable": {"google_id": google_id, "thread_id": thread_id}}


async def _get_history_from_state(config: dict) -> list:
    """
    Fetch the current message list from the LangGraph checkpointer state.
    Used by build_prompt_parts to trim + filter before each turn.
    Returns an empty list if the state is unavailable (e.g. first turn).
    """
    try:
        state = await agent.aget_state(config)
        return state.values.get("messages", [])
    except Exception as exc:
        print(f"[WARN] chat: could not fetch history from checkpointer: {exc}")
        return []


# Shared streaming generator

# Internal sentinel key used to pass the accumulated response through the
# generator without breaking the SSE byte stream.
_SENTINEL_KEY = "_assistant_response"


async def _stream_agent_events(inputs_or_command, config: dict):
    """
    Shared async generator that streams token and tool_call SSE events
    from the agent for both /stream and /resume endpoints.

    Yields:
        - SSE-formatted strings for "token" and "tool_call" events.
        - A final JSON sentinel string {"_assistant_response": "<full text>"}
          so the caller can capture the accumulated response without a
          separate variable or callback.

    Raises any exception from agent.astream_events so the caller can handle it.
    """
    assistant_response = ""
    try:
        async for event in agent.astream_events(
            inputs_or_command, config=config, version="v2"
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                token = event["data"]["chunk"].content
                if isinstance(token, str) and token:
                    assistant_response += token
                    yield _sse_event({"type": "token", "token": token})

            elif kind == "on_tool_start":
                tool_name = event.get("name", "tool")
                yield _sse_event({"type": "tool_call", "tool": tool_name})

    finally:
        # Always yield the sentinel so the caller can capture the response
        yield json.dumps({_SENTINEL_KEY: assistant_response})


async def _collect_stream(
    inputs_or_command,
    config: dict,
):
    """
    Drives _stream_agent_events and separates SSE chunks from the sentinel.

    Returns:
        sse_chunks        — list of SSE strings ready to yield to the client
        assistant_response — the full accumulated assistant text
    """
    sse_chunks: list[str] = []
    assistant_response = ""

    async for chunk in _stream_agent_events(inputs_or_command, config):
        try:
            parsed = json.loads(chunk)
            if _SENTINEL_KEY in parsed:
                assistant_response = parsed[_SENTINEL_KEY]
                continue
        except (json.JSONDecodeError, TypeError):
            pass
        sse_chunks.append(chunk)

    return sse_chunks, assistant_response


# HITL interrupt helper
def _extract_interrupt_events(state_tasks) -> list[str]:
    """
    Inspect LangGraph state tasks for HITL interrupts.
    Returns a list of SSE interrupt event strings, or an empty list if none.
    """
    events: list[str] = []
    for task in state_tasks or []:
        if hasattr(task, "interrupts") and task.interrupts:
            for intr in task.interrupts:
                events.append(
                    _sse_event(
                        {"type": "interrupt", "value": _serialize_interrupt(intr)}
                    )
                )
    return events


# Session title generation
def _normalize_title(raw_title: str) -> str:
    text = (raw_title or "").strip().strip("\"'")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[.!?,;:]+$", "", text)
    words = text.split()
    return " ".join(words[:6]) if words else "New Chat"


async def _generate_and_store_session_title(
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """
    Lazily generate a descriptive session title for 'New Chat' sessions.
    Fires as a background task — failure is logged but never raises.
    """
    try:
        session = get_chat_session(session_id)
        if not session or (session.get("title") or "").strip() != "New Chat":
            return

        # Truncate the assistant message preview to keep the prompt short
        assistant_preview = assistant_message.strip()[:300]

        prompt = (
            "Generate a short, specific title (max 6 words) for this email assistant conversation.\n"
            "Rules:\n"
            "  - Describe the actual task, not the medium (e.g. 'Draft apology to client',"
            " 'Find unpaid invoice emails', 'Reply to job offer')\n"
            "  - No punctuation at the end\n"
            "  - No quotes\n"
            "  - No filler phrases like 'Chat about', 'Help with', or 'Discuss'\n\n"
            f'User: "{user_message.strip()}"\n'
            f'Assistant: "{assistant_preview}"\n\n'
            "Output only the title, nothing else."
        )
        result = await title_llm.ainvoke(prompt)
        title = _normalize_title(getattr(result, "content", "") or "")
        if title and title != "New Chat":
            update_chat_session_title(session_id, title)
    except Exception as exc:
        print(
            f"[ERROR] chat: title generation failed for session_id={session_id}: {exc}"
        )


# POST /stream
@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Streams the agent's response token-by-token as Server-Sent Events (SSE).

    Pipeline per turn:
      1. Authenticate user
      2. Download + extract attachment content
           - text files  → injected into system prompt as <uploaded_files>
           - images      → passed as vision blocks in HumanMessage
           - unknown     → noted by ID only (still attachable)
      3. Fetch message history from LangGraph checkpointer state
      4. Build fresh system message, trimmed history, and human content blocks
      5. Persist user message to Supabase
      6. Stream agent events (tokens + tool calls)
      7. Persist assistant response; fire title generation if first exchange
      8. Check LangGraph state for HITL interrupts
      9. Emit "done" or "interrupt" SSE event
    """
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None

    async def event_generator():

        # ── 1. Auth ──────────────────────────────────────────────────────────
        user = get_user_by_google_id(google_id) if google_id else None
        if not user:
            yield _sse_event({"type": "error", "error": "Unauthorized"})
            yield _sse_event({"type": "done"})
            return

        config = _get_langgraph_config(google_id, req.thread_id)

        # ── 2. Extract attachments (New + Existing in thread) ────────────────
        extracted_attachments = []
        try:
            # Fetch all attachments already linked to this thread
            existing_attachments = get_attachments_for_thread(
                user_id=user["id"], thread_id=req.thread_id
            )
            existing_ids = [a["id"] for a in existing_attachments]

            # Combine with new IDs from the request
            req_ids = [a.attachment_id for a in req.attachments]
            all_ids = list(dict.fromkeys(existing_ids + req_ids))

            if all_ids:
                extracted_attachments = load_and_extract_attachments(
                    attachment_ids=all_ids,
                    user_id=user["id"],
                    thread_id=req.thread_id,
                )

                # LINK new attachments to this thread in the database
                # so they are remembered in future turns.
                if req_ids:
                    link_attachments_to_thread(
                        attachment_ids=req_ids,
                        user_id=user["id"],
                        thread_id=req.thread_id,
                    )
        except Exception as exc:
            # Soft fail for attachment extraction unless they were critical
            print(f"[WARN] chat: attachment extraction failed: {exc}")
            # If the user explicitly passed new attachments and they failed, we should error
            if req.attachments:
                yield _sse_event({"type": "error", "error": f"Attachment error: {exc}"})
                yield _sse_event({"type": "done"})
                return

        # ── 3. Fetch history from checkpointer ───────────────────────────────
        history = await _get_history_from_state(config)

        # ── 4. Build prompt parts ────────────────────────────────────────────
        #   system_msg     = fully rendered SystemMessage
        #   human_content  = [text block, ...image vision blocks]
        #   trimmed_history = previous messages, filtered + trimmed safely
        system_msg, human_content, trimmed_history = await build_prompt_parts(
            user_id=user["id"],
            human_text=req.message,
            extracted_attachments=extracted_attachments,
            message_history=history,
        )

        # ── 5. Persist user message ──────────────────────────────────────────
        save_message_with_metadata(
            session_id=req.thread_id,
            role="user",
            content=req.message,
            metadata={
                "attachments": [
                    {
                        "id": a.attachment_id,
                        "filename": a.filename,
                        "mime_type": a.mime_type,
                        "size_bytes": a.size_bytes,
                    }
                    for a in extracted_attachments
                ]
            },
        )

        # Build LangGraph inputs: fresh system + trimmed history + new human turn
        inputs = {
            "messages": [
                system_msg,
                *trimmed_history,
                HumanMessage(content=human_content),
            ]
        }

        # ── 6. Stream agent ──────────────────────────────────────────────────
        assistant_response = ""
        stream_error = False
        try:
            sse_chunks, assistant_response = await _collect_stream(inputs, config)
            for chunk in sse_chunks:
                yield chunk

        except Exception as exc:
            print(f"[ERROR] chat /stream failed for thread_id={req.thread_id}: {exc}")
            stream_error = True
            if not assistant_response:
                fallback = _safe_stream_error()
                assistant_response = fallback
                yield _sse_event({"type": "token", "token": fallback})
            yield _sse_event({"type": "error", "error": "Chat stream failed"})
            yield _sse_event({"type": "done"})

        finally:
            # ── 7. Persist assistant response ────────────────────────────────
            if assistant_response:
                try:
                    save_message(
                        session_id=req.thread_id,
                        role="assistant",
                        content=assistant_response,
                    )
                    session_msgs = get_session_messages(req.thread_id)
                    if len(session_msgs) <= 2:
                        asyncio.create_task(
                            _generate_and_store_session_title(
                                session_id=req.thread_id,
                                user_message=req.message,
                                assistant_message=assistant_response,
                            )
                        )
                except Exception as exc:
                    print(
                        f"[ERROR] chat: failed to persist assistant message "
                        f"for thread_id={req.thread_id}: {exc}"
                    )

        if stream_error:
            return

        # ── 8 & 9. Check for HITL interrupt ─────────────────────────────────
        try:
            state = await agent.aget_state(config)
        except Exception as exc:
            print(
                f"[ERROR] chat: failed to fetch state for thread_id={req.thread_id}: {exc}"
            )
            yield _sse_event({"type": "error", "error": "Failed to read chat state"})
            yield _sse_event({"type": "done"})
            return

        interrupt_events = _extract_interrupt_events(state.tasks)
        if interrupt_events:
            for event in interrupt_events:
                yield event
            # Do NOT emit "done" — the frontend must wait for /resume
            return

        yield _sse_event({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# POST /resume
@router.post("/resume")
async def chat_resume(req: ResumeRequest, request: Request):
    """
    Resumes the agent after a HITL interrupt with the user's approval decision.
    Streams the remaining response as SSE.

    A fresh system message is always re-injected so user preferences are
    never stale after a resume (e.g. if they changed settings mid-session).
    """
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None

    async def event_generator():

        # ── Auth ─────────────────────────────────────────────────────────────
        user = get_user_by_google_id(google_id) if google_id else None
        if not user:
            yield _sse_event({"type": "error", "error": "Unauthorized"})
            yield _sse_event({"type": "done"})
            return

        config = _get_langgraph_config(google_id, req.thread_id)

        # ── 2. Re-fetch all thread attachments for prompt context ────────────
        extracted_attachments = []
        try:
            existing_attachments = get_attachments_for_thread(
                user_id=user["id"], thread_id=req.thread_id
            )
            if existing_attachments:
                extracted_attachments = load_and_extract_attachments(
                    attachment_ids=[a["id"] for a in existing_attachments],
                    user_id=user["id"],
                    thread_id=req.thread_id,
                )
        except Exception as exc:
            print(f"[WARN] chat /resume: failed to restore attachment context: {exc}")

        # Fresh system prompt including attachment metadata
        system_msg, _, _ = await build_prompt_parts(
            user_id=user["id"],
            human_text="",
            extracted_attachments=extracted_attachments,
        )

        command = Command(
            resume={"decisions": req.decisions},
            update={"messages": [system_msg]},
        )

        # ── Stream resumed agent ─────────────────────────────────────────────
        assistant_response = ""
        stream_error = False
        try:
            sse_chunks, assistant_response = await _collect_stream(command, config)
            for chunk in sse_chunks:
                yield chunk

        except Exception as exc:
            print(f"[ERROR] chat /resume failed for thread_id={req.thread_id}: {exc}")
            stream_error = True
            if not assistant_response:
                fallback = _safe_stream_error()
                assistant_response = fallback
                yield _sse_event({"type": "token", "token": fallback})
            yield _sse_event({"type": "error", "error": "Chat resume failed"})
            yield _sse_event({"type": "done"})

        finally:
            # Persist whatever the agent produced before or after the error
            if assistant_response:
                try:
                    save_message(
                        session_id=req.thread_id,
                        role="assistant",
                        content=assistant_response,
                    )
                except Exception as exc:
                    print(
                        f"[ERROR] chat: failed to persist resumed assistant message "
                        f"for thread_id={req.thread_id}: {exc}"
                    )

        if stream_error:
            return

        # ── Check for chained interrupts ─────────────────────────────────────
        # The agent may chain multiple send_email calls; each needs approval.
        try:
            state = await agent.aget_state(config)
        except Exception as exc:
            print(
                f"[ERROR] chat: failed to fetch resumed state "
                f"for thread_id={req.thread_id}: {exc}"
            )
            yield _sse_event({"type": "error", "error": "Failed to read chat state"})
            yield _sse_event({"type": "done"})
            return

        interrupt_events = _extract_interrupt_events(state.tasks)
        if interrupt_events:
            for event in interrupt_events:
                yield event
            return

        yield _sse_event({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Session endpoints
@router.get("/sessions")
def get_sessions(request: Request):
    """Returns all chat sessions for the authenticated user."""
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None
    if not google_id:
        return []
    user = get_user_by_google_id(google_id=google_id)
    return get_user_sessions(user["id"]) if user else []


@router.post("/sessions")
async def create_session(request: Request):
    """Create a new chat session."""
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None
    user = get_user_by_google_id(google_id)
    return create_chat_session(user["id"], title="New Chat")


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, request: Request):
    """Return all messages for a specific session."""
    if not getattr(request.state, "user", None):
        return []
    return [
        {
            "role": msg["role"],
            "content": msg["content"],
            "metadata": msg.get("metadata", {}),
        }
        for msg in get_session_messages(session_id)
    ]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a chat session."""
    if not getattr(request.state, "user", None):
        return {"success": False, "error": "Unauthorized"}
    delete_chat_session(session_id)
    return {"success": True}
