import os
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool
from utils.config import settings

# Create a dedicated pool for the store to avoid circular imports, 
# or use a global one. For simplicity, we use a global store object here.

DATABASE_URL = settings.SUPABASE_DB_URL

# We'll initialize the pool and store in a way that can be managed by the FastAPI lifespan
store_pool = AsyncConnectionPool(
    conninfo=DATABASE_URL,
    kwargs={
        "autocommit": True,
        "prepare_threshold": None,
    },
    open=False,
)

store = AsyncPostgresStore(store_pool)

async def get_store() -> AsyncPostgresStore:
    return store

async def save_memory(user_id: str, key: str, value: dict):
    s = await get_store()
    await s.aput(
        namespace=("memories", user_id),
        key=key,
        value=value
    )

async def get_memories(user_id: str) -> list:
    s = await get_store()
    return await s.asearch(("memories", user_id))

async def delete_memory(user_id: str, key: str):
    s = await get_store()
    await s.adelete(
        namespace=("memories", user_id),
        key=key
    )

async def reset_memories(user_id: str):
    s = await get_store()
    memories = await s.asearch(("memories", user_id))
    for memory in memories:
        await s.adelete(
            namespace=("memories", user_id),
            key=memory.key
        )
