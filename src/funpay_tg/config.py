"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the FunPay Telegram bot.

    Loaded from environment variables (or `.env` file). Required values must
    be set for the bot to start; optional values fall back to sensible defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Telegram
    telegram_bot_token: SecretStr = Field(..., alias="TELEGRAM_BOT_TOKEN")
    telegram_admin_ids: list[int] = Field(default_factory=list, alias="TELEGRAM_ADMIN_IDS")

    # FunPay
    funpay_golden_key: SecretStr | None = Field(default=None, alias="FUNPAY_GOLDEN_KEY")
    funpay_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        alias="FUNPAY_USER_AGENT",
    )
    funpay_proxy: str | None = Field(default=None, alias="FUNPAY_PROXY")

    # AI
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # Storage / runtime
    db_path: Path = Field(default=Path("./data/bot.db"), alias="DB_PATH")
    media_dir: Path = Field(default=Path("./media"), alias="MEDIA_DIR")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("telegram_admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, str):
            return [int(p.strip()) for p in value.split(",") if p.strip()]
        raise ValueError("TELEGRAM_ADMIN_IDS must be a comma-separated list of ints")

    @field_validator("funpay_proxy", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def ensure_dirs(self) -> None:
        """Make sure all directories referenced by the config exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)


_cached: Settings | None = None


def get_settings() -> Settings:
    """Return cached settings instance (parsed once per process)."""
    global _cached
    if _cached is None:
        _cached = Settings()  # type: ignore[call-arg]
    return _cached
