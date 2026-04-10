from __future__ import annotations

from collections.abc import Iterable


def pick_translation(items: Iterable[object], language: str, field: str, fallback_language: str = "ru") -> str:
    current_value = ""
    fallback_value = ""
    for item in items:
        lang = getattr(item, "language", None)
        lang_value = getattr(lang, "value", lang)
        if lang_value == language:
            current_value = getattr(item, field, "") or ""
            if current_value:
                return current_value
        if lang_value == fallback_language:
            fallback_value = getattr(item, field, "") or ""
    return fallback_value or current_value
