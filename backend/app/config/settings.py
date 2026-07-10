"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "CryptoAlpha"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://cryptoalpha:cryptoalpha@localhost:5432/cryptoalpha"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key: str | None = None
    coingecko_timeout_seconds: float = 10.0
    coingecko_max_retries: int = 3
    binance_rest_base_url: str = "https://api.binance.com/api/v3"
    binance_websocket_base_url: str = "wss://stream.binance.com:9443/ws"
    binance_timeout_seconds: float = 10.0
    binance_max_retries: int = 3
    binance_websocket_reconnect_max_delay_seconds: float = 30.0
    coinmarketcap_base_url: str = "https://pro-api.coinmarketcap.com"
    coinmarketcap_api_key: str | None = None
    coinmarketcap_timeout_seconds: float = 10.0
    coinmarketcap_max_retries: int = 3


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance for the running process."""

    return Settings()
