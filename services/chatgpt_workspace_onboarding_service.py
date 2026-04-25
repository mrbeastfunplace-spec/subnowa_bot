from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import Bot

from automation.playwright_runner import PlaywrightWorkspaceValidationResult, validate_workspace_auth
from db.base import ChatGPTWorkspaceStatus
from services.context import AppContext
from services.workspace_registry_service import (
    as_config,
    create_pending_workspace,
    get_workspace,
    mark_workspace_result,
    profile_dir,
    workspace_profile_path,
    workspace_profile_ready,
)
from utils.logger import get_logger


@dataclass(slots=True)
class WorkspaceOnboardingConfirmResult:
    ok: bool
    workspace_db_id: int | None = None
    workspace_id: str | None = None
    profile_dir: str | None = None
    error_message: str | None = None


_LOGGER = get_logger("services.chatgpt_workspace_onboarding")
_WORKSPACE_CHECK_TASKS: dict[int, asyncio.Task[None]] = {}


def onboarding_in_progress(workspace_db_id: int) -> bool:
    return False


def workspace_check_in_progress(workspace_db_id: int) -> bool:
    task = _WORKSPACE_CHECK_TASKS.get(workspace_db_id)
    return task is not None and not task.done()


async def _notify(bot: Bot, admin_id: int, text: str) -> None:
    try:
        await bot.send_message(admin_id, text)
    except Exception:
        _LOGGER.exception("Failed to send workspace onboarding notification to %s", admin_id)


def _validation_summary(result: PlaywrightWorkspaceValidationResult) -> str:
    if result.status == "active":
        return (
            "Проверка профиля завершилась успешно.\n\n"
            f"ID: <code>{result.workspace_id or '-'}</code>\n"
            f"Название: <b>{result.workspace_name or '-'}</b>\n"
            f"Участников: <b>{result.member_count if result.member_count is not None else '-'}</b>"
        )
    return (
        "Проверка профиля не пройдена.\n\n"
        f"ID: <code>{result.workspace_id or '-'}</code>\n"
        f"Ошибка: {result.error_message or 'Unknown error'}"
    )


async def start_workspace_onboarding(
    app: AppContext,
    bot: Bot,
    *,
    admin_id: int,
    workspace_db_id: int | None = None,
) -> int:
    del bot
    async with app.session_factory() as session:
        record = await get_workspace(session, workspace_db_id) if workspace_db_id else None
        if record is None:
            record = await create_pending_workspace(
                session,
                settings=app.settings,
                created_by_admin_telegram_id=admin_id,
            )
        else:
            if not (record.profile_dir or "").strip():
                record.profile_dir = str(profile_dir(app.settings, record.workspace_id))
            if not (record.workspace_url or "").strip() or record.workspace_url.strip() == "https://chatgpt.com/":
                record.workspace_url = "https://chatgpt.com/admin"
            record.status = ChatGPTWorkspaceStatus.PENDING_SETUP
            record.last_error = None
            record.created_by_admin_telegram_id = admin_id
        await session.commit()
        return record.id


async def confirm_workspace_onboarding(
    app: AppContext,
    *,
    workspace_db_id: int,
) -> WorkspaceOnboardingConfirmResult:
    async with app.session_factory() as session:
        record = await get_workspace(session, workspace_db_id)
        if record is None:
            return WorkspaceOnboardingConfirmResult(
                ok=False,
                error_message="Аккаунт ChatGPT не найден.",
            )

        if not (record.profile_dir or "").strip():
            record.profile_dir = str(profile_dir(app.settings, record.workspace_id))

        profile_path = workspace_profile_path(record)
        profile_path_str = str(profile_path) if profile_path is not None else None
        if not workspace_profile_ready(profile_path):
            record.status = ChatGPTWorkspaceStatus.PENDING_SETUP
            record.last_error = (
                f"Profile dir was not found or is empty: {profile_path_str or '-'}"
            )
            await session.commit()
            return WorkspaceOnboardingConfirmResult(
                ok=False,
                workspace_db_id=record.id,
                workspace_id=record.workspace_id,
                profile_dir=profile_path_str,
                error_message="Профиль не найден в Railway volume. Сначала загрузите локально авторизованный профиль.",
            )

        if not (record.workspace_url or "").strip() or record.workspace_url.strip() == "https://chatgpt.com/":
            record.workspace_url = "https://chatgpt.com/admin"
        record.status = ChatGPTWorkspaceStatus.ACTIVE
        record.last_error = None
        await session.commit()
        return WorkspaceOnboardingConfirmResult(
            ok=True,
            workspace_db_id=record.id,
            workspace_id=record.workspace_id,
            profile_dir=profile_path_str,
        )


async def cancel_workspace_onboarding(app: AppContext, *, workspace_db_id: int) -> bool:
    del app, workspace_db_id
    return False


async def start_workspace_validation(
    app: AppContext,
    bot: Bot,
    *,
    admin_id: int,
    workspace_db_id: int,
) -> bool:
    active_task = _WORKSPACE_CHECK_TASKS.get(workspace_db_id)
    if active_task is not None and not active_task.done():
        return False

    task = asyncio.create_task(_run_workspace_validation(app, bot, admin_id, workspace_db_id))
    _WORKSPACE_CHECK_TASKS[workspace_db_id] = task
    task.add_done_callback(lambda _: _WORKSPACE_CHECK_TASKS.pop(workspace_db_id, None))
    return True


async def _run_workspace_validation(app: AppContext, bot: Bot, admin_id: int, workspace_db_id: int) -> None:
    async with app.session_factory() as session:
        record = await get_workspace(session, workspace_db_id)
        if record is None:
            return
        workspace = as_config(record)

    result = await validate_workspace_auth(workspace, app.settings)

    async with app.session_factory() as session:
        record = await get_workspace(session, workspace_db_id)
        if record is None:
            return
        if result.status == "active":
            target_status = ChatGPTWorkspaceStatus.ACTIVE
        elif result.status == "invalid_auth":
            target_status = ChatGPTWorkspaceStatus.INVALID_AUTH
        else:
            target_status = record.status
        await mark_workspace_result(
            session,
            record,
            status=target_status,
            workspace_name=result.workspace_name,
            workspace_url_value=result.workspace_url,
            members_url=result.members_url,
            current_users_count=result.member_count,
            error_message=result.error_message,
        )
        await session.commit()

    await _notify(bot, admin_id, _validation_summary(result))
