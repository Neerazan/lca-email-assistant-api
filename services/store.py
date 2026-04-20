import os
from langgraph.store.postgres import AsyncPostgresStore
from services.db import shared_pool

# Create a global store object using the shared connection pool
store = AsyncPostgresStore(shared_pool)

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
