from __future__ import annotations

import asyncio
import shutil
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot

from automation.create_auth_state_runner import capture_and_validate_workspace
from automation.playwright_runner import PlaywrightWorkspaceValidationResult, validate_workspace_auth
from config import ChatGPTWorkspaceConfig
from db.base import ChatGPTWorkspaceStatus
from services.context import AppContext
from services.workspace_registry_service import (
    as_config,
    create_pending_workspace,
    get_workspace,
    mark_workspace_result,
    onboarding_profile_dir,
    storage_state_path,
)
from utils.logger import get_logger


@dataclass(slots=True)
class _OnboardingMeta:
    admin_id: int
    is_new_record: bool
    previous_status: ChatGPTWorkspaceStatus | None


_LOGGER = get_logger("services.chatgpt_workspace_onboarding")
_ONBOARDING_TASKS: dict[int, asyncio.Task[None]] = {}
_ONBOARDING_EVENTS: dict[int, asyncio.Event] = {}
_ONBOARDING_META: dict[int, _OnboardingMeta] = {}
_WORKSPACE_CHECK_TASKS: dict[int, asyncio.Task[None]] = {}


def onboarding_in_progress(workspace_db_id: int) -> bool:
    task = _ONBOARDING_TASKS.get(workspace_db_id)
    return task is not None and not task.done()


def workspace_check_in_progress(workspace_db_id: int) -> bool:
    task = _WORKSPACE_CHECK_TASKS.get(workspace_db_id)
    return task is not None and not task.done()


async def _notify(bot: Bot, admin_id: int, text: str) -> None:
    try:
        await bot.send_message(admin_id, text)
    except Exception:
        _LOGGER.exception("Failed to send workspace onboarding notification to %s", admin_id)


def _build_onboarding_config(record, settings) -> ChatGPTWorkspaceConfig:
    temp_profile = Path(record.temp_profile_dir) if record.temp_profile_dir else onboarding_profile_dir(settings, record.workspace_id)
    return ChatGPTWorkspaceConfig(
        id=record.workspace_id,
        name=record.workspace_name or record.workspace_id,
        workspace_url=record.workspace_url or "https://chatgpt.com/",
        profile_dir=temp_profile,
        storage_state_path=Path(record.storage_state_path) if record.storage_state_path else storage_state_path(settings, record.workspace_id),
        members_url=record.members_url,
        max_users=max(1, record.max_users or settings.chatgpt_workspace_member_limit),
        enabled=True,
        source="registry",
        db_id=record.id,
    )


def _validation_summary(result: PlaywrightWorkspaceValidationResult) -> str:
    if result.status == "active":
        return (
            "✅ Новый ChatGPT аккаунт успешно добавлен и готов к использованию.\n\n"
            f"ID: <code>{result.workspace_id or '-'}</code>\n"
            f"Название: <b>{result.workspace_name or '-'}</b>\n"
            f"Участников: <b>{result.member_count if result.member_count is not None else '-'}</b>"
        )
    return (
        "❌ Не удалось подключить новый аккаунт.\n"
        "Проверьте, завершён ли вход полностью, и попробуйте снова.\n\n"
        f"Ошибка: {result.error_message or 'Unknown error'}"
    )


async def start_workspace_onboarding(
    app: AppContext,
    bot: Bot,
    *,
    admin_id: int,
    workspace_db_id: int | None = None,
) -> int:
    async with app.session_factory() as session:
        record = await get_workspace(session, workspace_db_id) if workspace_db_id else None
        is_new_record = record is None
        previous_status = record.status if record is not None else None

        if record is None:
            record = await create_pending_workspace(
                session,
                settings=app.settings,
                created_by_admin_telegram_id=admin_id,
            )
        else:
            record.status = ChatGPTWorkspaceStatus.PENDING_SETUP
            record.last_error = None
            record.created_by_admin_telegram_id = admin_id
            record.temp_profile_dir = str(onboarding_profile_dir(app.settings, record.workspace_id))
            if not record.storage_state_path:
                record.storage_state_path = str(storage_state_path(app.settings, record.workspace_id))
        await session.commit()
        workspace_id = record.id

    active_task = _ONBOARDING_TASKS.get(workspace_id)
    if active_task is not None and not active_task.done():
        return workspace_id

    event = asyncio.Event()
    _ONBOARDING_EVENTS[workspace_id] = event
    _ONBOARDING_META[workspace_id] = _OnboardingMeta(
        admin_id=admin_id,
        is_new_record=is_new_record,
        previous_status=previous_status,
    )

    task = asyncio.create_task(_run_workspace_onboarding(app, bot, workspace_id))
    _ONBOARDING_TASKS[workspace_id] = task
    task.add_done_callback(lambda _: _ONBOARDING_TASKS.pop(workspace_id, None))
    task.add_done_callback(lambda _: _ONBOARDING_EVENTS.pop(workspace_id, None))
    task.add_done_callback(lambda _: _ONBOARDING_META.pop(workspace_id, None))
    return workspace_id


def confirm_workspace_onboarding(workspace_db_id: int) -> bool:
    event = _ONBOARDING_EVENTS.get(workspace_db_id)
    if event is None:
        return False
    event.set()
    return True


async def cancel_workspace_onboarding(app: AppContext, *, workspace_db_id: int) -> bool:
    task = _ONBOARDING_TASKS.get(workspace_db_id)
    if task is None or task.done():
        return False
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    return True


async def _restore_cancelled_workspace(app: AppContext, workspace_db_id: int) -> None:
    meta = _ONBOARDING_META.get(workspace_db_id)
    async with app.session_factory() as session:
        record = await get_workspace(session, workspace_db_id)
        if record is None:
            return

        storage_path = Path(record.storage_state_path) if record.storage_state_path else None
        if meta and meta.is_new_record and (storage_path is None or not storage_path.exists()):
            await session.delete(record)
            await session.commit()
            return

        if meta and meta.previous_status is not None:
            record.status = meta.previous_status
        else:
            record.status = ChatGPTWorkspaceStatus.INVALID_AUTH
        record.last_error = "Onboarding cancelled by admin"
        await session.commit()


async def _run_workspace_onboarding(app: AppContext, bot: Bot, workspace_db_id: int) -> None:
    meta = _ONBOARDING_META.get(workspace_db_id)
    async with app.session_factory() as session:
        record = await get_workspace(session, workspace_db_id)
        if record is None:
            return
        workspace = _build_onboarding_config(record, app.settings)

    temp_profile_dir = workspace.profile_dir
    event = _ONBOARDING_EVENTS[workspace_db_id]

    try:
        result = await capture_and_validate_workspace(
            workspace,
            app.settings,
            confirmation_event=event,
        )
    except asyncio.CancelledError:
        await _restore_cancelled_workspace(app, workspace_db_id)
        if meta is not None:
            await _notify(bot, meta.admin_id, "Подключение аккаунта ChatGPT отменено.")
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        _LOGGER.exception("Workspace onboarding failed for %s", workspace_db_id)
        result = PlaywrightWorkspaceValidationResult(
            status="failed",
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            error_message=str(exc),
        )
    finally:
        if temp_profile_dir is not None:
            shutil.rmtree(temp_profile_dir, ignore_errors=True)

    async with app.session_factory() as session:
        record = await get_workspace(session, workspace_db_id)
        if record is None:
            return
        target_status = ChatGPTWorkspaceStatus.ACTIVE if result.status == "active" else ChatGPTWorkspaceStatus.INVALID_AUTH
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

    if meta is not None:
        await _notify(bot, meta.admin_id, _validation_summary(result))


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
        target_status = ChatGPTWorkspaceStatus.ACTIVE if result.status == "active" else ChatGPTWorkspaceStatus.INVALID_AUTH
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

    if result.status == "active":
        await _notify(
            bot,
            admin_id,
            (
                "✅ Проверка аккаунта прошла успешно.\n\n"
                f"ID: <code>{result.workspace_id or '-'}</code>\n"
                f"Название: <b>{result.workspace_name or '-'}</b>\n"
                f"Участников: <b>{result.member_count if result.member_count is not None else '-'}</b>"
            ),
        )
    else:
        await _notify(
            bot,
            admin_id,
            (
                "❌ Проверка аккаунта не пройдена.\n\n"
                f"ID: <code>{result.workspace_id or '-'}</code>\n"
                f"Ошибка: {result.error_message or 'Unknown error'}"
            ),
        )
