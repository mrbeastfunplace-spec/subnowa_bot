from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from db.base import ChatGPTWorkspaceStatus
from services.chatgpt_workspace_onboarding_service import (
    cancel_workspace_onboarding,
    confirm_workspace_onboarding,
    onboarding_in_progress,
    start_workspace_onboarding,
    start_workspace_validation,
    workspace_check_in_progress,
)
from services.context import AppContext
from services.workspace_registry_service import (
    get_workspace,
    list_registry_workspaces,
    set_workspace_enabled,
    workspace_status_label,
)
from utils.messages import answer_or_edit


def build_admin_workspace_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="admin_workspace")

    def _guard(callback: CallbackQuery) -> bool:
        return app.is_admin(callback.from_user.id)

    def _menu_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Добавить аккаунт ChatGPT", callback_data="admin:chatgpt_accounts:add")],
                [InlineKeyboardButton(text="Список аккаунтов ChatGPT", callback_data="admin:chatgpt_accounts:list")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:main")],
            ]
        )

    def _launch_markup(workspace_db_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Я завершил вход", callback_data=f"admin:chatgpt_accounts:confirm:{workspace_db_id}")],
                [InlineKeyboardButton(text="Список аккаунтов", callback_data="admin:chatgpt_accounts:list")],
            ]
        )

    def _confirm_success_markup(workspace_db_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Проверить", callback_data=f"admin:chatgpt_accounts:check:{workspace_db_id}")],
                [InlineKeyboardButton(text="Список аккаунтов", callback_data="admin:chatgpt_accounts:list")],
            ]
        )

    def _list_markup(items) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{item.workspace_id} | {workspace_status_label(item.status)}",
                    callback_data=f"admin:chatgpt_accounts:view:{item.id}",
                )
            ]
            for item in items
        ]
        rows.append([InlineKeyboardButton(text="Добавить аккаунт ChatGPT", callback_data="admin:chatgpt_accounts:add")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:chatgpt_accounts")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _detail_markup(workspace) -> InlineKeyboardMarkup:
        rows = [
            [InlineKeyboardButton(text="Проверить", callback_data=f"admin:chatgpt_accounts:check:{workspace.id}")],
            [InlineKeyboardButton(text="Обновить сессию", callback_data=f"admin:chatgpt_accounts:refresh:{workspace.id}")],
        ]
        if workspace.status == ChatGPTWorkspaceStatus.DISABLED:
            rows.append([InlineKeyboardButton(text="Включить", callback_data=f"admin:chatgpt_accounts:enable:{workspace.id}")])
        else:
            rows.append([InlineKeyboardButton(text="Отключить", callback_data=f"admin:chatgpt_accounts:disable:{workspace.id}")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:chatgpt_accounts:list")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _workspace_text(workspace) -> str:
        status = workspace_status_label(workspace.status)
        current_users = workspace.current_users_count if workspace.current_users_count is not None else "-"
        last_checked = workspace.last_checked_at.strftime("%Y-%m-%d %H:%M") if workspace.last_checked_at else "-"
        profile_dir = workspace.profile_dir or "-"
        workspace_url = workspace.workspace_url or "-"
        members_url = workspace.members_url or "-"
        notes = workspace.notes or "-"
        error_line = f"\nОшибка: {workspace.last_error}" if workspace.last_error else ""
        return (
            f"<b>{workspace.workspace_name or workspace.workspace_id}</b>\n\n"
            f"ID: <code>{workspace.workspace_id}</code>\n"
            f"Статус: <b>{status}</b>\n"
            f"Участников: <b>{current_users}</b>\n"
            f"ProfileDir: <code>{profile_dir}</code>\n"
            f"Workspace URL: <code>{workspace_url}</code>\n"
            f"Members URL: <code>{members_url}</code>\n"
            f"Последняя проверка: <b>{last_checked}</b>\n"
            f"Заметки: {notes}"
            f"{error_line}"
        )

    @router.callback_query(F.data == "admin:chatgpt_accounts")
    async def workspace_menu_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        await callback.answer()
        await answer_or_edit(
            callback,
            (
                "<b>ChatGPT аккаунты</b>\n\n"
                "Railway хранит профили и выполняет invite flow, но окно браузера на Railway не открывается. "
                "Авторизация нового аккаунта выполняется локально на вашем компьютере, после чего готовый persistent profile "
                "должен оказаться в Railway volume."
            ),
            reply_markup=_menu_markup(),
        )

    @router.callback_query(F.data == "admin:chatgpt_accounts:add")
    async def workspace_add_intro_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        await callback.answer()
        await answer_or_edit(
            callback,
            (
                "Создам запись для нового ChatGPT Business workspace и подготовлю путь профиля в Railway volume.\n\n"
                "Важно: авторизация выполняется локально на вашем компьютере. Бот не будет пытаться открыть браузер на Railway."
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Создать workspace", callback_data="admin:chatgpt_accounts:start")],
                    [InlineKeyboardButton(text="Отмена", callback_data="admin:chatgpt_accounts")],
                    [InlineKeyboardButton(text="Меню", callback_data="admin:main")],
                ]
            ),
        )

    @router.callback_query(F.data == "admin:chatgpt_accounts:start")
    async def workspace_start_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        workspace_db_id = await start_workspace_onboarding(
            app,
            bot,
            admin_id=callback.from_user.id,
        )
        async with app.session_factory() as session:
            workspace = await get_workspace(session, workspace_db_id)
        await callback.answer()
        profile_dir = workspace.profile_dir if workspace is not None else "-"
        workspace_code = workspace.workspace_id if workspace is not None else "-"
        await answer_or_edit(
            callback,
            (
                "Создан новый ChatGPT workspace record.\n\n"
                f"ID: <code>{workspace_code}</code>\n"
                f"ProfileDir: <code>{profile_dir}</code>\n"
                "Статус: <b>pending_setup</b>\n\n"
                "Авторизация выполняется локально на вашем компьютере.\n"
                "1. Войдите в нужный ChatGPT Business workspace локально.\n"
                "2. Сохраните persistent Chromium profile именно в этот каталог Railway volume.\n"
                "3. После загрузки профиля нажмите «Я завершил вход».\n"
                "4. Затем нажмите «Проверить», чтобы зафиксировать рабочий URL и проверить invite flow."
            ),
            reply_markup=_launch_markup(workspace_db_id),
        )

    @router.callback_query(F.data == "admin:chatgpt_accounts:list")
    async def workspace_list_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        async with app.session_factory() as session:
            items = await list_registry_workspaces(session)
        await callback.answer()
        if not items:
            await answer_or_edit(
                callback,
                "В workspace registry пока нет аккаунтов ChatGPT.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Добавить аккаунт ChatGPT", callback_data="admin:chatgpt_accounts:add")],
                        [InlineKeyboardButton(text="Назад", callback_data="admin:chatgpt_accounts")],
                    ]
                ),
            )
            return
        await answer_or_edit(
            callback,
            "<b>Список аккаунтов ChatGPT</b>\n\nВыберите аккаунт для просмотра деталей.",
            reply_markup=_list_markup(items),
        )

    @router.callback_query(F.data.startswith("admin:chatgpt_accounts:view:"))
    async def workspace_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        workspace_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            workspace = await get_workspace(session, workspace_id)
        await callback.answer()
        if workspace is None:
            await answer_or_edit(callback, "Аккаунт не найден.", reply_markup=_menu_markup())
            return
        suffix = []
        if onboarding_in_progress(workspace.id):
            suffix.append("Onboarding: in_progress")
        if workspace_check_in_progress(workspace.id):
            suffix.append("Check: in_progress")
        extra = ("\n" + "\n".join(suffix)) if suffix else ""
        await answer_or_edit(callback, _workspace_text(workspace) + extra, reply_markup=_detail_markup(workspace))

    @router.callback_query(F.data.startswith("admin:chatgpt_accounts:confirm:"))
    async def workspace_confirm_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        workspace_id = int(callback.data.split(":")[-1])
        result = await confirm_workspace_onboarding(app, workspace_db_id=workspace_id)
        await callback.answer("Проверяю загруженный профиль...")
        if not result.ok:
            await answer_or_edit(
                callback,
                (
                    f"{result.error_message or 'Профиль не найден.'}\n\n"
                    f"ProfileDir: <code>{result.profile_dir or '-'}</code>\n"
                    "Кнопка подтверждает только уже загруженный профиль. "
                    "Сначала выполните локальную авторизацию и перенесите persistent profile в Railway volume."
                ),
                reply_markup=_launch_markup(workspace_id),
            )
            return
        await answer_or_edit(
            callback,
            (
                "Профиль найден, workspace активирован.\n\n"
                f"ID: <code>{result.workspace_id or '-'}</code>\n"
                f"ProfileDir: <code>{result.profile_dir or '-'}</code>\n\n"
                "Следующий шаг: нажмите «Проверить», чтобы headless-проверка на Railway подтвердила авторизацию и "
                "зафиксировала рабочий URL для invite flow."
            ),
            reply_markup=_confirm_success_markup(workspace_id),
        )

    @router.callback_query(F.data.startswith("admin:chatgpt_accounts:cancel:"))
    async def workspace_cancel_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        workspace_id = int(callback.data.split(":")[-1])
        cancelled = await cancel_workspace_onboarding(
            app,
            workspace_db_id=workspace_id,
        )
        await callback.answer("Подключение отменено." if cancelled else "Активного onboarding-процесса нет.")
        await workspace_list_handler(callback)

    @router.callback_query(F.data.startswith("admin:chatgpt_accounts:refresh:"))
    async def workspace_refresh_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        workspace_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            workspace = await get_workspace(session, workspace_id)
        if workspace is None:
            await callback.answer()
            return
        launched_id = await start_workspace_onboarding(
            app,
            bot,
            admin_id=callback.from_user.id,
            workspace_db_id=workspace.id,
        )
        async with app.session_factory() as session:
            refreshed_workspace = await get_workspace(session, launched_id)
        await callback.answer()
        profile_dir = refreshed_workspace.profile_dir if refreshed_workspace is not None else "-"
        await answer_or_edit(
            callback,
            (
                "Workspace переведён в pending_setup для обновления сессии.\n\n"
                f"ProfileDir: <code>{profile_dir}</code>\n"
                "Railway не откроет браузер. Обновите авторизацию локально на вашем компьютере, "
                "перезапишите persistent profile в этот каталог и после этого нажмите «Я завершил вход»."
            ),
            reply_markup=_launch_markup(launched_id),
        )

    @router.callback_query(F.data.startswith("admin:chatgpt_accounts:check:"))
    async def workspace_check_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        workspace_id = int(callback.data.split(":")[-1])
        started = await start_workspace_validation(
            app,
            bot,
            admin_id=callback.from_user.id,
            workspace_db_id=workspace_id,
        )
        await callback.answer("Проверка запущена." if started else "Проверка уже выполняется.")
        if started:
            await answer_or_edit(
                callback,
                "Проверяю профиль на Railway. Результат пришлю отдельным сообщением.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Список аккаунтов", callback_data="admin:chatgpt_accounts:list")]]
                ),
            )

    @router.callback_query(F.data.startswith("admin:chatgpt_accounts:disable:"))
    async def workspace_disable_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        workspace_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            workspace = await get_workspace(session, workspace_id)
            if workspace is None:
                await callback.answer()
                return
            await set_workspace_enabled(session, workspace, enabled=False)
            await session.commit()
        await callback.answer("Аккаунт отключён.")
        await workspace_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:chatgpt_accounts:enable:"))
    async def workspace_enable_handler(callback: CallbackQuery) -> None:
        if not _guard(callback):
            await callback.answer()
            return
        workspace_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            workspace = await get_workspace(session, workspace_id)
            if workspace is None:
                await callback.answer()
                return
            await set_workspace_enabled(session, workspace, enabled=True)
            await session.commit()
        await callback.answer("Аккаунт включён.")
        await workspace_detail_handler(callback)

    return router
