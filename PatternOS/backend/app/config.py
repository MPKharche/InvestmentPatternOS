"""
Central config — reads from .env at PatternOS root.
Import settings from here everywhere; never read os.environ directly.
"""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "patternos"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""

    # OpenRouter
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_REASONING_MODEL: str = "anthropic/claude-haiku-4-5"        # rulebook, audits
    LLM_CHAT_MODEL: str = "google/gemini-2.5-flash-preview"        # greetings, conversation
    LLM_SCREENING_MODEL: str = "google/gemini-2.5-flash-preview"   # scan-loop scoring
    LLM_FALLBACK_MODEL: str = "anthropic/claude-haiku-4-5"         # auto-retry fallback

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # App
    APP_ENV: str = "development"
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 3000
    SIGNAL_CONFIDENCE_THRESHOLD: float = 70.0
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
