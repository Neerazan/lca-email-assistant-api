from starlette import middleware
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel
from utils.config import settings
import json

router = APIRouter()


# ── Simple test tool ──────────────────────────────────────────────
@tool
def get_weather(place: str) -> str:
    """Return the weather status of any place or city."""
    return f"Currently the weather of {place} is sunny and 25°C."


# ── Build a lightweight ReAct agent ──────────────────────────────
llm = ChatOpenAI(model="gpt-4.1-nano", streaming=True, api_key=settings.OPENAI_API_KEY)

agent = create_react_agent(
    model=llm,
    tools=[get_weather],
    prompt="You are a general chatbot. You can also fetch weather information using your tool.",
)


# ── Request body ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str


# ── Streaming endpoint ───────────────────────────────────────────
@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """
    Streams the agent's response token-by-token as Server-Sent Events (SSE).
    Only AI text tokens are forwarded; tool calls are handled silently.
    """

    async def event_generator():
        inputs = {"messages": [HumanMessage(content=req.message)]}

        async for event in agent.astream_events(inputs, version="v2"):
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
