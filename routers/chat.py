from services.supabase import (
    create_chat_session,
    delete_chat_session,
    get_attachment_by_id,
    get_session_messages,
    get_user_by_google_id,
    get_user_sessions,
    save_message,
    save_message_with_metadata,
    update_chat_session_title,
)
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command
from pydantic import BaseModel, Field
import json

from agent.prompt_builder import build_system_prompt
from agent.setup import agent
from agent.utils import _serialize_interrupt

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    attachments: list["AttachmentRef"] = Field(default_factory=list)


class AttachmentRef(BaseModel):
    attachment_id: str
    filename: str | None = None
    mime_type: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    decisions: list[dict]  # e.g. [{"type": "approve"}]


def _format_attachments_for_prompt(attachments: list[dict]) -> str:
    if not attachments:
        return ""
    lines = [
        f"- {item['id']}: {item['filename']} ({item['mime_type']}, {item['size_bytes']} bytes)"
        for item in attachments
    ]
    return (
        "The user uploaded these files and you can attach them by ID in email tools.\n"
        + "\n".join(lines)
    )


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Streams the agent's response token-by-token as Server-Sent Events (SSE).
    Detects HITL interrupts and emits them for frontend approval.
    """

    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None

    async def event_generator():
        user = get_user_by_google_id(google_id) if google_id else None
        if not user:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Unauthorized'})}\n\n"
            return

        uploaded_attachments: list[dict] = []
        for attachment in req.attachments:
            record = get_attachment_by_id(attachment.attachment_id, user["id"])
            if not record:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "error": f"Attachment not found: {attachment.attachment_id}",
                        }
                    )
                    + "\n\n"
                )
                return
            if record.get("thread_id") and record.get("thread_id") != req.thread_id:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "error": f"Attachment not linked to this thread: {attachment.attachment_id}",
                        }
                    )
                    + "\n\n"
                )
                return
            uploaded_attachments.append(record)

        # Save the user's message to Supabase
        save_message_with_metadata(
            session_id=req.thread_id,
            role="user",
            content=req.message,
            metadata={
                "attachments": [
                    {
                        "id": a["id"],
                        "filename": a["filename"],
                        "mime_type": a["mime_type"],
                        "size_bytes": a["size_bytes"],
                    }
                    for a in uploaded_attachments
                ]
            },
        )

        # Check if this is the first message in the session to update the title
        session_msgs = get_session_messages(req.thread_id)
        if len(session_msgs) == 1:
            # Generate a simple title from the first message (e.g. first 5 words)
            words = req.message.split()
            new_title = " ".join(words[:5]) + ("..." if len(words) > 5 else "")
            update_chat_session_title(req.thread_id, new_title)

        prompt_text = await build_system_prompt(user["id"])
        attachment_context = _format_attachments_for_prompt(uploaded_attachments)
        if attachment_context:
            prompt_text = f"{prompt_text}\n\n{attachment_context}"
        system_message = SystemMessage(content=prompt_text, id="system_prompt")

        inputs = {"messages": [system_message, HumanMessage(content=req.message)]}
        config = {
            "configurable": {
                "google_id": google_id,
                "thread_id": req.thread_id,
            }
        }

        assistant_response = ""

        try:
            print(f"[DEBUG] Starting astream_events for thread_id={req.thread_id}")
            async for event in agent.astream_events(inputs, config=config, version="v2"):
                kind = event["event"]
                print(f"[DEBUG] Event: {kind}, name={event.get('name', 'N/A')}")

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    token = chunk.content
                    if isinstance(token, str) and token:
                        assistant_response += token
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"
        finally:
            # After streaming ends (or is cancelled), save the full assistant response to Supabase
            if assistant_response:
                save_message(
                    session_id=req.thread_id,
                    role="assistant",
                    content=assistant_response,
                )

        print("[DEBUG] astream_events loop finished, checking state...")
        # After streaming ends, check if the graph paused due to an interrupt
        state = await agent.aget_state(config)
        print(f"[DEBUG] state.next = {state.next}")
        print(f"[DEBUG] state.tasks = {state.tasks}")
        if state.tasks:
            for task in state.tasks:
                print(
                    f"[DEBUG] task = {task}, has interrupts = {hasattr(task, 'interrupts')}"
                )
                if hasattr(task, "interrupts") and task.interrupts:
                    for intr in task.interrupts:
                        print(f"[DEBUG] interrupt value = {intr.value}")
                        payload = _serialize_interrupt(intr)
                        print(f"[DEBUG] Emitting interrupt payload: {payload}")
                        yield f"data: {json.dumps({'type': 'interrupt', 'value': payload})}\n\n"
                    return  # Stop — wait for /resume

        print("[DEBUG] No interrupts found, emitting done")
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/resume")
async def chat_resume(req: ResumeRequest, request: Request):
    """
    Resumes the agent after a HITL interrupt with the user's decision.
    Streams the remaining response as SSE.
    """

    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None

    async def event_generator():
        config = {
            "configurable": {
                "google_id": google_id,
                "thread_id": req.thread_id,
            }
        }

        print(
            f"[DEBUG] /resume called with thread_id={req.thread_id}, decisions={req.decisions}"
        )

        # Fetch dynamic system prompt
        user = get_user_by_google_id(google_id)
        prompt_text = await build_system_prompt(user["id"])
        system_message = SystemMessage(content=prompt_text, id="system_prompt")

        # Resume the graph with the user's decision
        command = Command(
            resume={"decisions": req.decisions},
            update={"messages": [system_message]}
        )

        assistant_response = ""

        try:
            async for event in agent.astream_events(
                command,
                config=config,
                version="v2",
            ):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    token = chunk.content
                    if isinstance(token, str) and token:
                        assistant_response += token
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"
        finally:
            if assistant_response:
                save_message(
                    session_id=req.thread_id,
                    role="assistant",
                    content=assistant_response,
                )

        # Check for further interrupts (e.g. if agent chains multiple send_email calls)
        state = await agent.aget_state(config)
        if state.tasks:
            for task in state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    for intr in task.interrupts:
                        payload = _serialize_interrupt(intr)
                        yield f"data: {json.dumps({'type': 'interrupt', 'value': payload})}\n\n"
                    return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sessions")
def get_sessions(request: Request):
    """Returns all chat sessions for a authenticated user."""
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None
    if not google_id:
        return []

    user = get_user_by_google_id(google_id=google_id)
    if not user:
        return []

    session = get_user_sessions(user['id'])
    return session


@router.post("/sessions")
async def create_session(request: Request):
    """Create a new chat session."""
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None

    user = get_user_by_google_id(google_id)
    session = create_chat_session(user["id"], title="New Chat")
    return session

@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, request: Request):
    """Return all messages for a specific session."""
    user_payload = getattr(request.state, "user", None)
    if not user_payload:
        return []
        
    messages = get_session_messages(session_id)
    # Format messages for the frontend
    return [
        {
            "role": msg["role"],
            "content": msg["content"],
            "metadata": msg.get("metadata", {}),
        }
        for msg in messages
    ]

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a chat session."""
    user_payload = getattr(request.state, "user", None)
    if not user_payload:
        return {"success": False, "error": "Unauthorized"}
        
    delete_chat_session(session_id)
    return {"success": True}
