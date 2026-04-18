from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from automation.playwright_runner import PlaywrightInviteResult, invite_to_workspace
from db.base import ChatGPTWorkspaceStatus, OrderStatus
from services.context import AppContext
from services.legacy_ui import build_order_followup_markup, text as ui_text
from services.orders import change_status, get_order_by_id
from services.workspace_registry_service import get_workspace_by_code, list_active_workspace_configs, mark_workspace_result
from services.workspace_router import WorkspaceRouter
from utils.formatting import order_display_number
from utils.logger import get_logger


_ACTIVE_CHATGPT_RUNS: dict[int, asyncio.Task[None]] = {}
_LOGGER = get_logger("services.chatgpt_invite")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _admin_order_markup(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть заказ", callback_data=f"admin:order:{order_id}")]]
    )


async def _send_message_safe(
    bot: Bot,
    telegram_id: int | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if not telegram_id:
        return
    try:
        await bot.send_message(telegram_id, text, reply_markup=reply_markup)
    except Exception:
        _LOGGER.exception("Failed to send Telegram message to %s", telegram_id)


async def _notify_admins(bot: Bot, app: AppContext, text: str, order_id: int) -> None:
    markup = _admin_order_markup(order_id)
    for admin_id in app.settings.admin_ids:
        await _send_message_safe(bot, admin_id, text, reply_markup=markup)


def _followup_markup(app: AppContext, language: str, order_id: int, include_review: bool) -> InlineKeyboardMarkup:
    return build_order_followup_markup(
        language,
        order_id,
        app.settings.support_url,
        app.settings.review_url,
        include_review=include_review,
    )


def _merge_run(order, payload: dict) -> None:
    details = dict(order.details or {})
    chatgpt_data = dict(details.get("chatgpt_business") or {})
    runs = list(chatgpt_data.get("runs") or [])
    runs.append(payload)
    chatgpt_data["runs"] = runs[-20:]
    chatgpt_data["last_run"] = payload
    chatgpt_data["last_result"] = payload.get("result")
    chatgpt_data["last_error"] = payload.get("error_message")
    chatgpt_data["run_state"] = payload.get("run_state", "finished")
    details["chatgpt_business"] = chatgpt_data
    order.details = details


def _is_run_in_progress(order) -> bool:
    details = dict(order.details or {})
    chatgpt_data = dict(details.get("chatgpt_business") or {})
    return chatgpt_data.get("run_state") == "processing"


def _build_admin_message(order, result: PlaywrightInviteResult, final_status: OrderStatus) -> str:
    workspace_line = f"Workspace: {result.workspace_name or result.workspace_id or '-'}"
    error_line = f"\nОшибка: {escape(result.error_message)}" if result.error_message else ""
    if result.status == "invited":
        headline = "Заказ выполнен: invite отправлен"
    elif result.status == "already_invited":
        headline = "Заказ завершён: email уже был приглашён"
    elif final_status == OrderStatus.WAITING:
        headline = "Заказ переведён в ожидание: свободных мест нет"
    else:
        headline = "Заказ завершился ошибкой: нужен ручной просмотр"
    return (
        f"{headline}\n\n"
        f"Заказ: <code>{order_display_number(order)}</code>\n"
        f"Email: <code>{escape(str((order.details or {}).get('gmail', '-')))}</code>\n"
        f"{workspace_line}"
        f"{error_line}"
    )


async def start_chatgpt_business_order(
    app: AppContext,
    bot: Bot,
    order_id: int,
    changed_by_telegram_id: int,
) -> bool:
    active_task = _ACTIVE_CHATGPT_RUNS.get(order_id)
    if active_task is not None and not active_task.done():
        return False

    language = app.settings.default_language
    user_telegram_id: int | None = None
    async with app.session_factory() as session:
        order = await get_order_by_id(session, order_id)
        if order is None or order.workflow_type != "chatgpt_manual":
            return False
        if _is_run_in_progress(order):
            return False

        language = order.language or app.settings.default_language
        user_telegram_id = order.user.telegram_id if order.user else None
        if order.status != OrderStatus.PROCESSING:
            await change_status(
                session,
                order,
                OrderStatus.PROCESSING,
                changed_by_telegram_id=changed_by_telegram_id,
                note="chatgpt business automation started",
            )
        started_at = _utcnow()
        _merge_run(
            order,
            {
                "run_state": "processing",
                "result": "processing",
                "started_at": _isoformat(started_at),
                "order_id": order.id,
                "telegram_user_id": order.user.telegram_id if order.user else None,
                "customer_email": (order.details or {}).get("gmail"),
                "selected_product": order.product_code_snapshot,
                "workspace_id": None,
                "workspace_name": None,
                "member_count": None,
                "error_message": None,
            },
        )
        await session.commit()

    await _send_message_safe(
        bot,
        user_telegram_id,
        ui_text(language, "chatgpt_business_processing"),
    )

    task = asyncio.create_task(_run_chatgpt_business_order(app, bot, order_id, changed_by_telegram_id))
    _ACTIVE_CHATGPT_RUNS[order_id] = task
    task.add_done_callback(lambda _: _ACTIVE_CHATGPT_RUNS.pop(order_id, None))
    return True


async def _run_chatgpt_business_order(
    app: AppContext,
    bot: Bot,
    order_id: int,
    changed_by_telegram_id: int,
) -> None:
    started_at = _utcnow()
    async with app.session_factory() as session:
        order = await get_order_by_id(session, order_id)
        if order is None:
            return
        email = str((order.details or {}).get("gmail") or "").strip()
        if not email:
            result = PlaywrightInviteResult(
                status="unexpected_error",
                error_message="Customer email is missing for ChatGPT Business automation",
            )
        else:
            workspace_configs = await list_active_workspace_configs(session, app.settings)
            router = WorkspaceRouter(workspace_configs)
            result: PlaywrightInviteResult | None = None
            if not router.has_workspaces():
                result = PlaywrightInviteResult(
                    status="unexpected_error",
                    error_message="No ChatGPT Business workspaces are configured",
                )
            else:
                exhausted_workspace_ids: set[str] = set()
                for workspace in router.iter_workspaces(excluded_ids=exhausted_workspace_ids):
                    attempt_result = await invite_to_workspace(workspace, email, app.settings)
                    result = attempt_result
                    if attempt_result.status == "no_workspace_available":
                        exhausted_workspace_ids.add(workspace.id)
                        continue
                    break
                if result is None or (
                    result.status == "no_workspace_available"
                    and len(exhausted_workspace_ids) == len(router.iter_workspaces())
                ):
                    result = PlaywrightInviteResult(status="no_workspace_available")

    finished_at = _utcnow()

    async with app.session_factory() as session:
        order = await get_order_by_id(session, order_id)
        if order is None:
            return
        language = order.language or app.settings.default_language
        user_telegram_id = order.user.telegram_id if order.user else None

        if result.status in {"invited", "already_invited"}:
            final_status = OrderStatus.COMPLETED
            include_review = True
            user_text_key = (
                "chatgpt_business_invited"
                if result.status == "invited"
                else "chatgpt_business_already_invited"
            )
            note = f"chatgpt business automation: {result.status}"
        elif result.status == "no_workspace_available":
            final_status = OrderStatus.WAITING
            include_review = False
            user_text_key = "chatgpt_business_waiting"
            note = "chatgpt business automation waiting for free workspace"
        else:
            final_status = OrderStatus.FAILED
            include_review = False
            user_text_key = "chatgpt_business_failed"
            note = f"chatgpt business automation failed: {result.status}"

        await change_status(
            session,
            order,
            final_status,
            changed_by_telegram_id=changed_by_telegram_id,
            note=note,
        )
        run_payload = {
            "run_state": "finished",
            "result": result.status,
            "order_id": order.id,
            "telegram_user_id": order.user.telegram_id if order.user else None,
            "customer_email": (order.details or {}).get("gmail"),
            "selected_product": order.product_code_snapshot,
            "workspace_id": result.workspace_id,
            "workspace_name": result.workspace_name,
            "member_count": result.member_count,
            "error_message": result.error_message,
            "started_at": _isoformat(started_at),
            "finished_at": _isoformat(finished_at),
        }
        _merge_run(order, run_payload)

        registry_workspace = await get_workspace_by_code(session, result.workspace_id or "") if result.workspace_id else None
        if registry_workspace is not None:
            target_status = registry_workspace.status
            if result.status == "auth_failed":
                target_status = ChatGPTWorkspaceStatus.INVALID_AUTH
            elif result.status in {"invited", "already_invited", "no_workspace_available"}:
                target_status = ChatGPTWorkspaceStatus.ACTIVE
            await mark_workspace_result(
                session,
                registry_workspace,
                status=target_status,
                current_users_count=result.member_count,
                error_message=result.error_message,
            )

        await session.commit()

        _LOGGER.info(
            "ChatGPT Business automation result | order_id=%s user_id=%s email=%s product=%s workspace=%s result=%s error=%s started_at=%s finished_at=%s",
            order.id,
            order.user.telegram_id if order.user else None,
            (order.details or {}).get("gmail"),
            order.product_code_snapshot,
            result.workspace_name or result.workspace_id,
            result.status,
            result.error_message,
            _isoformat(started_at),
            _isoformat(finished_at),
        )

        await _send_message_safe(
            bot,
            user_telegram_id,
            ui_text(language, user_text_key),
            reply_markup=_followup_markup(app, language, order.id, include_review),
        )
        await _notify_admins(bot, app, _build_admin_message(order, result, final_status), order.id)
