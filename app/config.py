"""Application settings loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ----
    app_name: str = "Crypto News Analysis Engine"
    environment: str = "development"
    log_level: str = "INFO"

    # ---- MongoDB ----
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "crypto_news"

    # ---- AI ----
    ai_provider: str = "openai"  # openai | anthropic
    ai_output_language: str = "English"
    ai_max_tokens: int = 1500
    ai_temperature: float = 0.3
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"

    # ---- Crawler ----
    crawl_default_days: int = 7
    crawl_max_articles_per_site: int = 40
    crawl_request_timeout: float = 20.0
    crawl_concurrency: int = 3
    crawl_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    cryptopanic_api_token: str | None = None

    # ---- Startup ----
    seed_default_symbols: bool = True


@lru_cache
def get_settings() -> Settings:
    # 🔧 Cached so the .env file is parsed only once per process
    return Settings()
