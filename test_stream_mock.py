import asyncio
from unittest.mock import patch
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.types import Command
import agent.tools as atools
from routers.chat import agent

async def test_stream():
    inputs = {"messages": [
        HumanMessage(content="Send an email to test@example.com with subject 'Hello' saying 'Test'"),
        AIMessage(content="", tool_calls=[{'name': 'send_email', 'args': {'message': 'Test', 'to': 'test@example.com', 'subject': 'Hello'}, 'id': 'call_123', 'type': 'tool_call'}]),
        ToolMessage(content="Message sent successfully. Message Id: r84ujv58934j", name="send_email", tool_call_id="call_123")
    ]}
    config = {
        "configurable": {
            "google_id": "111375799035658249111",
            "thread_id": "debug-thread-mock",
        }
    }
    
    print("Invoking agent directly to see next action...")
    try:
        async for event in agent.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                pass
            elif kind == "on_tool_start":
                print(f"Agent decided to run tool: {event.get('name')}")
    except Exception as e:
        print("Stream error:", e)

if __name__ == "__main__":
    asyncio.run(test_stream())
