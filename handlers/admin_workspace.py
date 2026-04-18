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
    short_storage_reference,
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
                [InlineKeyboardButton(text="Отменить", callback_data=f"admin:chatgpt_accounts:cancel:{workspace_db_id}")],
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
        notes = workspace.notes or "-"
        error_line = f"\nОшибка: {workspace.last_error}" if workspace.last_error else ""
        return (
            f"<b>{workspace.workspace_name or workspace.workspace_id}</b>\n\n"
            f"ID: <code>{workspace.workspace_id}</code>\n"
            f"Статус: <b>{status}</b>\n"
            f"Участников: <b>{current_users}</b>\n"
            f"StorageState: <code>{short_storage_reference(workspace.storage_state_path)}</code>\n"
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
                "Здесь можно запустить полуавтоматическое подключение нового ChatGPT Business аккаунта, "
                "проверить текущие сессии и обновить авторизацию."
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
                "Подготовьте новый ChatGPT Business аккаунт для входа.\n"
                "Когда будете готовы пройти авторизацию и 2FA, нажмите 'Начать подключение'."
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Начать подключение", callback_data="admin:chatgpt_accounts:start")],
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
        await callback.answer()
        await answer_or_edit(
            callback,
            (
                "⚙️ Запущено подключение нового аккаунта.\n"
                "Пожалуйста, выполните вход в открывшемся окне браузера и завершите авторизацию."
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
        confirmed = confirm_workspace_onboarding(workspace_id)
        await callback.answer("Проверяю сессию..." if confirmed else "Onboarding уже завершён или не запущен.")
        if confirmed:
            await answer_or_edit(
                callback,
                "Проверяю сохранённую сессию. Как только валидация закончится, пришлю отдельное сообщение.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Список аккаунтов", callback_data="admin:chatgpt_accounts:list")]]
                ),
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
        await callback.answer("Подключение отменено." if cancelled else "Onboarding не найден.")
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
        await callback.answer()
        await answer_or_edit(
            callback,
            (
                "⚙️ Запущено обновление сессии аккаунта.\n"
                "Войдите в браузере, завершите авторизацию и затем нажмите 'Я завершил вход'."
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
                "Проверяю аккаунт. Результат пришлю отдельным сообщением.",
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
