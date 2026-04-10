from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TextEntry
from utils.translations import pick_translation


SUPPORTED_LANGUAGES = {"ru", "uz", "en"}
TG_EMOJI_RE = re.compile(r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>", re.DOTALL)


def normalize_language(value: str | None, default: str = "ru") -> str:
    if value in SUPPORTED_LANGUAGES:
        return value
    return default


def strip_tg_emoji_tags(value: str) -> str:
    return TG_EMOJI_RE.sub(r"\1", value)


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
        formatted = raw.format(**kwargs)
    except Exception:
        formatted = raw
    return strip_tg_emoji_tags(formatted)
