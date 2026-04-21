from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    ENVIRONMENT: str = "development" # "development" or "production"
    LOG_DIR: str = "logs"

    OPENAI_API_KEY: str

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_DB_URL: str  # Direct PostgreSQL connection string for LangGraph checkpointer
    SUPABASE_ATTACHMENTS_BUCKET: str = "chat-attachments"

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    OPENAI_API_KEY: str
    TAVILY_API_KEY: str

    SECRET_KEY: str
    ENCRYPTION_KEY: str  # Used for Fernet encryption of refresh tokens
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60         # 60 minutes
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    ATTACHMENTS_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024
    ATTACHMENTS_MAX_FILES_PER_MESSAGE: int = 5
    ATTACHMENTS_TTL_HOURS: int = 24 * 7

    class Config:
        env_file = ".env"


settings = Settings()
