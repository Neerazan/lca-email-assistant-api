from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_URL: str
    FRONTEND_URL: str
    OPENAI_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    SECRET_KEY: str

    class Config:
        env_file = ".env"


settings = Settings()
