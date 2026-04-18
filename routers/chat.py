from services.supabase import get_user_by_google_id, create_chat_session, get_user_sessions, save_message, get_session_messages, update_chat_session_title, delete_chat_session
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from langchain.agents.middleware import HumanInTheLoopMiddleware
from pydantic import BaseModel
from utils.config import settings
import json

from agent.tools import search_emails, get_email, get_thread, send_email, create_draft

router = APIRouter()


llm = ChatOpenAI(model="gpt-4.1-nano", streaming=True, api_key=settings.OPENAI_API_KEY)
tools = [search_emails, get_email, get_thread, send_email, create_draft]

# Persistent checkpointer — stores LangGraph state in Supabase PostgreSQL.
# Pool is opened and setup() called in main.py lifespan.
from psycopg_pool import AsyncConnectionPool

pool = AsyncConnectionPool(
    conninfo=settings.SUPABASE_DB_URL,
    kwargs={
        "autocommit": True,
        "prepare_threshold": None,
    },
    open=False,
)
checkpointer = AsyncPostgresSaver(pool)

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=(
        "You are an AI Email Assistant. You can search and retrieve the user's Gmail messages. "
        "IMPORTANT: When asked to provide details or read an email, you MUST output the FULL "
        "content of the email body exactly as provided by the tools. Do NOT summarize it or restrict "
        "yourself to the snippet. Extract and display the most important information if the text is huge, "
        "but prioritize showing the actual contents of the email body rather than just a View Link."
    ),
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "send_email": True,
                "create_draft": False,
                "get_email": False,
                "search_emails": False,
            },
        )
    ],
    checkpointer=checkpointer,
)


def _serialize_interrupt(interrupt_obj) -> dict:
    """Serialize a HITLRequest interrupt value into a JSON-safe dict."""
    value = getattr(interrupt_obj, "value", interrupt_obj)
    if not isinstance(value, dict):
        value = getattr(value, "__dict__", {})

    action_requests = []
    for ar in value.get("action_requests", []):
        if not isinstance(ar, dict):
            ar = getattr(ar, "__dict__", {})
        action_requests.append(
            {
                "action": ar.get("name", ""),
                "args": ar.get("args", {}),
                "description": ar.get("description", ""),
            }
        )

    review_configs = []
    for rc in value.get("review_configs", []):
        if not isinstance(rc, dict):
            rc = getattr(rc, "__dict__", {})
        review_configs.append(
            {
                "actionName": rc.get("action_name", ""),
                "allowedDecisions": list(rc.get("allowed_decisions", [])),
            }
        )

    return {
        "actionRequests": action_requests,
        "reviewConfigs": review_configs,
    }


class ChatRequest(BaseModel):
    message: str
    thread_id: str


class ResumeRequest(BaseModel):
    thread_id: str
    decisions: list[dict]  # e.g. [{"type": "approve"}]


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Streams the agent's response token-by-token as Server-Sent Events (SSE).
    Detects HITL interrupts and emits them for frontend approval.
    """

    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None

    async def event_generator():
        # Save the user's message to Supabase
        save_message(session_id=req.thread_id, role="user", content=req.message)

        # Check if this is the first message in the session to update the title
        session_msgs = get_session_messages(req.thread_id)
        if len(session_msgs) == 1:
            # Generate a simple title from the first message (e.g. first 5 words)
            words = req.message.split()
            new_title = " ".join(words[:5]) + ("..." if len(words) > 5 else "")
            update_chat_session_title(req.thread_id, new_title)

        inputs = {"messages": [HumanMessage(content=req.message)]}
        config = {
            "configurable": {
                "google_id": google_id,
                "thread_id": req.thread_id,
            }
        }

        assistant_response = ""

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

        # After streaming ends, save the full assistant response to Supabase
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

        # Resume the graph with the user's decision
        command = Command(resume={"decisions": req.decisions})

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
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

            elif kind == "on_tool_start":
                tool_name = event.get("name", "tool")
                yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"

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
    return [{"role": msg["role"], "content": msg["content"]} for msg in messages]

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a chat session."""
    user_payload = getattr(request.state, "user", None)
    if not user_payload:
        return {"success": False, "error": "Unauthorized"}
        
    delete_chat_session(session_id)
    return {"success": True}
