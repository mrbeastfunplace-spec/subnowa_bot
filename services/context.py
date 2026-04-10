from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import Settings


@dataclass(slots=True)
class AppContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.settings.admin_ids
