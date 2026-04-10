from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TextEntry
from utils.translations import pick_translation


SUPPORTED_LANGUAGES = {"ru", "uz", "en"}


def normalize_language(value: str | None, default: str = "ru") -> str:
    if value in SUPPORTED_LANGUAGES:
        return value
    return default


async def get_text(session: AsyncSession, code: str, language: str, fallback: str = "") -> str:
    language = normalize_language(language)
    entry = await session.scalar(select(TextEntry).where(TextEntry.code == code))
    if entry is None:
        return fallback
    return pick_translation(entry.translations, language, "value") or fallback


async def format_text(
    session: AsyncSession,
    code: str,
    language: str,
    fallback: str = "",
    **kwargs,
) -> str:
    raw = await get_text(session, code, language, fallback=fallback)
    try:
        return raw.format(**kwargs)
    except Exception:
        return raw
