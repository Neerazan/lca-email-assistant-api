from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain.agents.middleware import HumanInTheLoopMiddleware

from utils.config import settings
from agent.tools import (
    search_emails,
    get_email,
    get_thread,
    send_email,
    create_draft,
    save_memory_tool,
    delete_memory_tool,
)
from services.store import store
from services.db import shared_pool

llm = ChatOpenAI(model="gpt-4.1-nano", streaming=True, api_key=settings.OPENAI_API_KEY)
tools = [
    search_emails,
    get_email,
    get_thread,
    send_email,
    create_draft,
    save_memory_tool,
    delete_memory_tool,
]

# Persistent checkpointer — stores LangGraph state in Supabase PostgreSQL.
# Pool is opened and setup() called in main.py lifespan.
checkpointer = AsyncPostgresSaver(shared_pool)

agent = create_agent(
    model=llm,
    tools=tools,
    # We leave system_prompt None here and inject it dynamically in the routes
    system_prompt=None,
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
    store=store
)
