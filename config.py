from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional during compile-only checks
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent


def _load_env() -> None:
    env_path = BASE_DIR / ".env"
    if load_dotenv and env_path.exists():
        load_dotenv(env_path)


def _parse_admin_ids(value: str | None) -> list[int]:
    if not value:
        return []
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        result.append(int(item))
    return result


@dataclass(slots=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: list[int]
    support_url: str
    about_url: str
    review_url: str
    required_channel: str
    default_language: str = "ru"
    admin_language: str = "ru"
    trial_duration_days: int = 3
    payment_window_hours: int = 12

    @property
    def polling_lock_path(self) -> Path:
        return BASE_DIR / ".polling.lock"


def load_settings() -> Settings:
    _load_env()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")) or [7716923294],
        support_url=os.getenv("SUPPORT_URL", "https://t.me/subnowa_supportbot").strip(),
        about_url=os.getenv("ABOUT_URL", "https://subnowa.site").strip(),
        review_url=os.getenv("REVIEW_URL", "https://t.me/subbowaotzib").strip(),
        required_channel=os.getenv("REQUIRED_CHANNEL", "@UZB_TREND_MUCIQALAR_BASS_HIT").strip(),
        default_language=os.getenv("DEFAULT_LANGUAGE", "ru").strip() or "ru",
        admin_language="ru",
        trial_duration_days=int(os.getenv("TRIAL_DURATION_DAYS", "3")),
        payment_window_hours=int(os.getenv("PAYMENT_WINDOW_HOURS", "12")),
    )
