from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    OPENAI_API_KEY: str

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    SECRET_KEY: str
    ENCRYPTION_KEY: str  # Used for Fernet encryption of refresh tokens
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60         # 60 minutes
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    class Config:
        env_file = ".env"


settings = Settings()
