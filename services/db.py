from psycopg_pool import AsyncConnectionPool
from utils.config import settings

# Create a single shared connection pool for the entire application.
# This prevents exhausting the Supabase connection limit.
# In Session mode, Supabase has a limited number of max clients.
# Multiple connection pools multiply the number of connections.
# By sharing one pool across LangGraph components (checkpointer and store),
# we minimize our connection footprint.

shared_pool = AsyncConnectionPool(
    conninfo=settings.SUPABASE_DB_URL,
    kwargs={
        "autocommit": True,
        "prepare_threshold": None,
    },
    open=False,
    min_size=1,   # Keep minimum connections low
    max_size=4,   # Cap the max connections to avoid exhausting Supabase limits
)
