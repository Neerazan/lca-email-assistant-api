import asyncio
import json
from fastapi.testclient import TestClient
from main import app

# Bypass auth middleware temporarily for testing
# We'll just mock the user payload in the router by mocking request.state.user
from fastapi import Request
from middlewares.auth import AuthMiddleware


class MockAuthMiddleware(AuthMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = {
            "sub": "116527582531398863619"
        }  # Dummy google ID, assuming it's a string
        return await call_next(request)


# Actually, the middleware is already added to app. Instead of modifying app, we can just send the request
# But we need a valid JWT. Wait, let's just make a script that calls the event generator directly without HTTP.

from routers.chat import agent, _serialize_interrupt
from langchain_core.messages import HumanMessage


async def test_stream():
    inputs = {
        "messages": [
            HumanMessage(
                content="Send an email to test@example.com with subject 'Hello' saying 'Test'"
            )
        ]
    }
    config = {
        "configurable": {
            "google_id": "test_google_id",
            "thread_id": "debug-thread-1",
        }
    }

    print("Starting stream...")
    try:
        async for event in agent.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]
            print(f"Event: {kind}, name={event.get('name')}")

            if kind == "on_on_interrupt":
                print("Got on_interrupt event!", event)
    except Exception as e:
        print("Error during stream:", e)

    print("Stream finished, checking state...")
    try:
        state = await agent.aget_state(config)
        print("Tasks:", state.tasks)
        if state.tasks:
            for task in state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    for intr in task.interrupts:
                        print("Interrupt value:", intr.value)

                        # Now try resuming
                        print("Resuming...")
                        from langgraph.types import Command

                        command = Command(resume={"decisions": [{"type": "approve"}]})

                        async for event in agent.astream_events(
                            command, config=config, version="v2"
                        ):
                            print(
                                f"Resume Event: {event['event']}, name={event.get('name')}"
                            )

    except Exception as e:
        print("Error getting state:", e)


if __name__ == "__main__":
    asyncio.run(test_stream())
