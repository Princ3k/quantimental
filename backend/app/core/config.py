"""
Application configuration.

All settings are read from environment variables (or a local .env file) exactly
once and cached. Nothing in the app should call os.getenv directly — going
through Settings keeps the full list of knobs discoverable in one place and
gives every one of them a documented default.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---- Application ----------------------------------------------------
    PROJECT_NAME: str = "Quantimental API"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ---- CORS -----------------------------------------------------------
    # Comma-separated list. Defaults cover local development only; production
    # origins must be set explicitly so a deploy can't accidentally ship a
    # permissive policy.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---- Database -------------------------------------------------------
    # Optional on purpose: the signal engine works entirely from live market
    # data. Postgres is only needed for the news archive and batch pipeline,
    # so the API must start and serve signals without it.
    DATABASE_URL: Optional[str] = None

    # ---- Kafka (optional, for the async sentiment pipeline) -------------
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_SENTIMENT_RAW: str = "sentiment.raw_events"
    KAFKA_TOPIC_SENTIMENT_SCORED: str = "sentiment.scored_events"

    # ---- External data providers (all optional) -------------------------
    # Missing keys disable the corresponding source rather than breaking a
    # request; see LiveSignalService for the degradation path.
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    REDDIT_USERNAME: Optional[str] = None
    REDDIT_PASSWORD: Optional[str] = None
    ALPHA_VANTAGE_API_KEY: Optional[str] = None
    MARKETAUX_API_KEY: Optional[str] = None
    TWITTER_API_KEY: Optional[str] = None
    # Which reseller the key came from: "twitterapi.io" or "scrapebadger".
    # They are different companies, and each rejects the other's keys with a
    # bare 401. See TWITTER_PROVIDERS in the sentiment fetcher.
    TWITTER_API_PROVIDER: Optional[str] = None
    HF_TOKEN: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None

    # EDGAR asks for a contact address in the User-Agent so they can reach
    # whoever is generating the traffic, and throttles what it cannot trace.
    # Not a credential — it is published with every request we make.
    SEC_CONTACT_EMAIL: Optional[str] = None

    # Error reporting. No DSN means the SDK never starts, which is what keeps
    # local runs and the test suite from reporting anywhere.
    SENTRY_DSN: Optional[str] = None
    SENTRY_ENVIRONMENT: str = "production"
    SENTRY_TRACES_SAMPLE_RATE: float = Field(0.0, ge=0.0, le=1.0)
    # Groq retires hosted models fairly often (llama-3.1-8b-instant, which this
    # project originally pinned, has already gone). Keeping it in config means
    # the next retirement is an environment change, not a code change.
    # Check the current catalogue at https://console.groq.com/docs/models
    GROQ_MODEL: str = "qwen/qwen3.8-27b"

    # ---- Tuning ---------------------------------------------------------
    TECHNICAL_WEIGHT: float = Field(0.45, ge=0.0, le=1.0)
    SENTIMENT_WEIGHT: float = Field(0.55, ge=0.0, le=1.0)

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        level = value.upper()
        if level not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return level

    @property
    def cors_origins(self) -> list[str]:
        """CORS_ORIGINS parsed into a list, ignoring blanks and stray spaces."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def database_configured(self) -> bool:
        """True when a database URL is present, so callers can degrade cleanly."""
        return bool(self.DATABASE_URL)

    @property
    def async_database_url(self) -> Optional[str]:
        """DATABASE_URL normalised to the asyncpg driver."""
        if not self.DATABASE_URL:
            return None
        url = self.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            return url
        # Railway and Heroku still hand out postgres:// URLs, which SQLAlchemy
        # 2.x rejects outright.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def sync_database_url(self) -> Optional[str]:
        """DATABASE_URL normalised to the psycopg2 driver, for Alembic."""
        if not self.DATABASE_URL:
            return None
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()
