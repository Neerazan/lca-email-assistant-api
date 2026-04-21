from psycopg_pool import AsyncConnectionPool
from utils.config import settings

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
