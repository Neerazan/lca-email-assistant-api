from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from utils.config import settings
import json

from agent.tools import list_user_emails, get_user_email_details

router = APIRouter()


# ── Build a lightweight ReAct agent ──────────────────────────────
llm = ChatOpenAI(model="gpt-4.1-nano", streaming=True, api_key=settings.OPENAI_API_KEY)

# Use our new tools along with the test tool
agent = create_react_agent(
    model=llm,
    tools=[list_user_emails, get_user_email_details],
    prompt=(
        "You are an AI Email Assistant. You can search and retrieve the user's Gmail messages. "
        "IMPORTANT: When asked to provide details or read an email, you MUST output the FULL "
        "content of the email body exactly as provided by the tools. Do NOT summarize it or restrict "
        "yourself to the snippet. Extract and display the most important information if the text is huge, "
        "but prioritize showing the actual contents of the email body rather than just a View Link."
    ),
    checkpointer=InMemorySaver(),
)


# ── Request body ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str


# ── Streaming endpoint ───────────────────────────────────────────
@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Streams the agent's response token-by-token as Server-Sent Events (SSE).
    Only AI text tokens are forwarded; tool calls are handled silently.
    """

    # Extract the authenticated user's google_id from the request state
    user_payload = getattr(request.state, "user", None)
    google_id = user_payload.get("sub") if user_payload else None

    async def event_generator():
        inputs = {"messages": [HumanMessage(content=req.message)]}

        # Inject the google_id into the LangChain RunnableConfig
        config = {"configurable": {"google_id": google_id, "thread_id": "1"}}

        async for event in agent.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]

            # Stream LLM text tokens
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                token = chunk.content

                if isinstance(token, str) and token:
                    yield f"data: {json.dumps({'token': token})}\n\n"

            # Stream tool calls
            elif kind == "on_tool_start":
                tool_name = event.get("name", "tool")
                yield f"data: {json.dumps({'tool_call': tool_name})}\n\n"

        # Signal the client that the stream is done
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Placeholder for session management ───────────────────────────
@router.get("/sessions")
def get_sessions():
    return []
