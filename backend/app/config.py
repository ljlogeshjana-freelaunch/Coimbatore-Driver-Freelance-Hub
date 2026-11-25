from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./local.db"
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    supabase_issuer: str = ""
    cors_origins: str = "http://localhost:5173"
    admin_email: str = "ljlogeshjana@gmail.com"
    resend_api_key: str = ""
    email_from: str = ""
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"
    port: int = 8000
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
