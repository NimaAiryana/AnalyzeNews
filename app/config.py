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

    # ---- AI (Google Gemini / Google AI Studio) ----
    ai_output_language: str = "English"
    gemini_api_key: str | None = None
    # 🎯 Two models analyse in parallel; Pro also produces the final combined verdict
    gemini_pro_model: str = "gemini-3.1-pro-preview"
    gemini_flash_model: str = "gemini-3-flash-preview"
    gemini_temperature: float = 1.0
    gemini_top_p: float = 0.95
    gemini_max_output_tokens: int = 65536
    gemini_thinking_level: str = "HIGH"  # HIGH | MEDIUM | LOW | MINIMAL | "" to disable
    gemini_use_google_search: bool = True
    # 🔄 Transient-failure handling (e.g. 429 / 5xx): retry, then fall back to Flash
    gemini_max_retries: int = 3
    gemini_retry_delay_seconds: float = 2.0

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
