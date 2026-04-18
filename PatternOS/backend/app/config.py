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
    LLM_REASONING_MODEL: str = "x-ai/grok-4.1-fast"               # rulebook, audits (OpenRouter)
    LLM_CHAT_MODEL: str = "x-ai/grok-4.1-fast"                    # studio chat + vision
    LLM_SCREENING_MODEL: str = "x-ai/grok-4.1-fast"                # scan-loop scoring
    LLM_FALLBACK_MODEL: str = "deepseek/deepseek-v3.2"            # fallback on primary errors
    LLM_DISABLED: bool = False

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_MODE: str = "disabled"  # disabled|polling
    TELEGRAM_ALERTS_ENABLED: bool = True
    TELEGRAM_ALLOWED_CHAT_IDS: str = ""  # comma-separated chat ids; default TELEGRAM_CHAT_ID if empty
    TELEGRAM_ALLOWED_USERNAMES: str = ""  # comma-separated usernames; optional
    TELEGRAM_ALERT_MAX_ATTEMPTS: int = 10

    # App
    APP_ENV: str = "development"
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 3000
    SIGNAL_CONFIDENCE_THRESHOLD: float = 70.0

    # Indicators engine (auto prefers TA-Lib if installed)
    INDICATOR_ENGINE: str = "auto"  # auto|ta|talib

    # Optional: SearxNG + Crawl4AI for pre-inbox signal equity review (see deploy/docker-compose.enrichment.yml)
    SEARXNG_BASE_URL: str = ""
    CRAWL4AI_BASE_URL: str = ""
    SIGNAL_DEEP_REVIEW_ENABLED: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    # Mutual Funds ingestion safety toggles
    MF_INGESTION_ENABLED: bool = True
    MF_BACKFILL_ENABLED: bool = False
    MF_HOLDINGS_ENABLED: bool = True
    MF_LINK_CHECK_ENABLED: bool = False
    MF_LINK_CHECK_DAILY_CAP: int = 200

    # Conservative rate limits (requests/min) to avoid IP blocks
    MF_MAX_RPM_MFDATA_STANDARD: int = 60
    MF_MAX_RPM_MFDATA_NAV: int = 120
    MF_MAX_RPM_MFDATA_ANALYTICS: int = 15
    MF_MAX_RPM_MFAPI: int = 20

    # Request hygiene
    MF_HTTP_USER_AGENT: str = "PatternOS/0.1 (+https://localhost; contact=admin@localhost)"
    MF_HTTP_CONNECT_TIMEOUT_S: float = 5.0
    MF_HTTP_READ_TIMEOUT_S: float = 20.0

    # Circuit breaker
    MF_PROVIDER_FAIL_THRESHOLD: int = 5
    MF_PROVIDER_PAUSE_MIN_MINUTES: int = 30
    MF_PROVIDER_PAUSE_MAX_MINUTES: int = 60

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def telegram_allowed_chat_ids(self) -> set[str]:
        if self.TELEGRAM_ALLOWED_CHAT_IDS.strip():
            return {c.strip() for c in self.TELEGRAM_ALLOWED_CHAT_IDS.split(",") if c.strip()}
        return {self.TELEGRAM_CHAT_ID.strip()} if self.TELEGRAM_CHAT_ID.strip() else set()

    @property
    def telegram_allowed_usernames(self) -> set[str]:
        return {u.strip().lstrip("@") for u in self.TELEGRAM_ALLOWED_USERNAMES.split(",") if u.strip()}

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
