"""
Application configuration via Pydantic Settings.

All configuration is read from environment variables (or a .env file in
development). In production (Docker Swarm), inject secrets via
`docker secret` and reference them with Docker's secrets bind-mount pattern,
or use `docker service update --env-add`.

Never hardcode credentials here. The .env.example file documents every
required variable.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object. Instantiated once per process via `get_settings()`.

    All fields have sane defaults where possible. Fields without defaults
    must be set in the environment before the application starts.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Chatwoot ---
    CHATWOOT_URL: str = Field(
        default="http://localhost:3000",
        description="Base URL of the Chatwoot instance (no trailing slash).",
    )
    CHATWOOT_API_TOKEN: str = Field(
        default="",
        description="Chatwoot user access token with agent permissions.",
    )
    CHATWOOT_ACCOUNT_ID: int = Field(
        default=1,
        description="Chatwoot account ID (visible in Settings > Account).",
    )

    # --- Evolution API (WhatsApp) ---
    EVOLUTION_URL: str = Field(
        default="http://localhost:8080",
        description="Base URL of the Evolution API instance.",
    )
    EVOLUTION_API_KEY: str = Field(
        default="",
        description="Global API key for Evolution API.",
    )
    EVOLUTION_INSTANCE: str = Field(
        default="default",
        description="Evolution API instance name configured for this bot.",
    )

    # --- OpenAI ---
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key. Required when AGENT_TYPE=faq.",
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4.1",
        description="OpenAI chat model to use. gpt-4.1 is recommended for production.",
    )

    # --- Infrastructure ---
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL used for webhook dedup and notify flood guard.",
    )
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/chatbot",
        description="Async SQLAlchemy database URL. Not used by the base template "
                    "but consumed by custom agents that persist conversation state.",
    )

    # --- Bot ---
    ADMIN_PHONE: str = Field(
        default="",
        description="WhatsApp phone number (E.164 without +) to receive error alerts. "
                    "Leave empty to disable admin notifications.",
    )
    AGENT_TYPE: str = Field(
        default="faq",
        description="Which agent class to load. Options: 'faq', 'echo'. "
                    "Add your own by registering it in app/webhook/chatwoot.py.",
    )
    AGENT_CITY: str = Field(
        default="Município",
        description="Municipality name shown in the agent's system prompt.",
    )
    FAQ_PATH: str = Field(
        default="agents/faq/faq_data.yaml",
        description="Path to the FAQ YAML data file, relative to the working directory.",
    )

    # --- Security ---
    WEBHOOK_SECRET: str = Field(
        default="",
        description="Optional HMAC-SHA256 secret for verifying Chatwoot webhook signatures. "
                    "Leave empty to skip signature validation (not recommended for production).",
    )

    # --- Observability ---
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Root log level: DEBUG, INFO, WARNING, ERROR.",
    )
    JSON_LOGS: bool = Field(
        default=False,
        description="Set to true in production to emit JSON logs for log aggregators.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    Cached so environment variables are read exactly once. In tests,
    call `get_settings.cache_clear()` before patching env vars.
    """
    return Settings()


# Module-level alias for convenience: `from app.core.config import settings`
settings: Settings = get_settings()
