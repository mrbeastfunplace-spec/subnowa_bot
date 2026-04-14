from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiohttp import web
from aiogram import Bot

from db.base import OrderStatus
from services.context import AppContext
from services.multicard import (
    MulticardError,
    create_invoice,
    extract_remote_status,
    fetch_invoice,
    map_payment_status,
    verify_callback_signature,
)
from services.order_processing import mark_order_paid
from services.orders import (
    get_order_by_invoice_reference,
    get_order_by_number,
    update_payment_meta,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _response_texts(language: str) -> dict[str, str]:
    if language == "uz":
        return {
            "title": "To'lov holati",
            "ready": "Buyurtma bo'yicha ma'lumot yangilandi. Telegram botga qaytishingiz mumkin.",
            "pending": "Buyurtma hali kutilmoqda. To'lov holati bot ichida yangilanadi.",
            "paid": "To'lov qabul qilindi. Keyingi yangilanishlar Telegram bot orqali yuboriladi.",
            "failed": "To'lov yakunlanmadi yoki bekor qilindi. Xohlasangiz botdagi tugma orqali qayta urinib ko'ring.",
            "not_found": "Buyurtma topilmadi.",
            "invoice_error": "Multicard invoice yaratib bo'lmadi. Iltimos, keyinroq qayta urinib ko'ring.",
        }
    if language == "en":
        return {
            "title": "Payment status",
            "ready": "The order state was refreshed successfully. You can return to the Telegram bot.",
            "pending": "The order is still waiting for payment. The status will continue updating in the bot.",
            "paid": "Payment was received. Further updates will be sent in the Telegram bot.",
            "failed": "Payment was not completed or was canceled. You can retry from the bot.",
            "not_found": "Order not found.",
            "invoice_error": "Unable to create a Multicard invoice right now. Please try again a bit later.",
        }
    return {
        "title": "Статус оплаты",
        "ready": "Состояние заказа обновлено. Можно вернуться в Telegram-бот.",
        "pending": "Заказ всё ещё ожидает оплату. Статус продолжит обновляться внутри бота.",
        "paid": "Оплата получена. Дальнейшие обновления придут в Telegram-бот.",
        "failed": "Оплата не завершена или была отменена. Можно повторить попытку из бота.",
        "not_found": "Заказ не найден.",
        "invoice_error": "Не удалось создать счёт Multicard. Пожалуйста, попробуйте ещё раз чуть позже.",
    }


def _html_page(title: str, body: str) -> web.Response:
    html = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #f3f6f4 0%, #ffffff 100%);
      color: #122117;
    }}
    main {{
      max-width: 560px;
      margin: 0 auto;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    section {{
      width: 100%;
      background: #ffffff;
      border: 1px solid #dbe6dc;
      border-radius: 18px;
      padding: 24px;
      box-shadow: 0 18px 60px rgba(18, 33, 23, 0.08);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 24px;
    }}
    p {{
      margin: 0;
      line-height: 1.6;
      white-space: pre-line;
    }}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>{title}</h1>
      <p>{body}</p>
    </section>
  </main>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html", charset="utf-8")


def _client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip
    return (request.remote or "").strip()


def _callback_allowed(request: web.Request, payload: dict, app: AppContext) -> bool:
    if verify_callback_signature(payload, app.settings):
        return True
    return _client_ip(request) == app.settings.multicard_allowed_ip


def _append_query(url: str, **params: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _invoice_active(order) -> bool:
    if not order.checkout_url or not order.invoice_expiry_at:
        return False
    expiry_at = order.invoice_expiry_at
    if expiry_at.tzinfo is None:
        expiry_at = expiry_at.replace(tzinfo=timezone.utc)
    return expiry_at > _utc_now()


async def _apply_payment_update(
    session,
    app: AppContext,
    bot: Bot,
    order,
    payload: dict,
    *,
    source: str,
) -> str:
    remote_status = extract_remote_status(payload)
    mapped_status = map_payment_status(remote_status)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = {}
    invoice_id = str(payload.get("invoice_id") or data.get("invoice_id") or order.invoice_id or order.order_number).strip()
    invoice_uuid = str(payload.get("uuid") or data.get("uuid") or order.invoice_uuid or "").strip()
    checkout_url = str(payload.get("checkout_url") or data.get("checkout_url") or order.checkout_url or "").strip()
    payment_status = mapped_status or order.payment_status

    if order.status in {OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.COMPLETED} and payment_status == "failed":
        payment_status = order.payment_status or "paid"

    await update_payment_meta(
        session,
        order,
        payment_provider="multicard",
        payment_status=payment_status,
        invoice_id=invoice_id or None,
        invoice_uuid=invoice_uuid or None,
        checkout_url=checkout_url or None,
    )
    if mapped_status == "paid":
        await mark_order_paid(session, bot, app.settings, order, note=source)
        await session.commit()
    else:
        await session.commit()
    return mapped_status


async def start_checkout_server(app: AppContext, bot: Bot) -> web.AppRunner:
    http_app = web.Application()
    http_app["app_context"] = app
    http_app["bot"] = bot

    async def checkout_handler(request: web.Request) -> web.StreamResponse:
        app_context: AppContext = request.app["app_context"]
        order_number = request.match_info.get("order_number", "").strip()
        async with app_context.session_factory() as session:
            order = await get_order_by_number(session, order_number)
            if order is None:
                return _html_page(_response_texts("ru")["title"], _response_texts("ru")["not_found"])
            language = order.language or app_context.settings.default_language
            texts = _response_texts(language)

            if order.payment_status == "paid" or order.status in {OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.COMPLETED}:
                return _html_page(texts["title"], texts["paid"])

            if _invoice_active(order) and order.payment_status not in {"paid", "failed"}:
                raise web.HTTPFound(order.checkout_url)

            return_url = _append_query(app_context.settings.multicard_return_url, order=order.order_number)
            callback_url = _append_query(app_context.settings.multicard_callback_url, order=order.order_number)
            try:
                invoice = await create_invoice(
                    app_context.settings,
                    amount_uzs=order.amount,
                    invoice_id=order.order_number,
                    language=language,
                    callback_url=callback_url,
                    return_url=return_url,
                )
            except MulticardError:
                return _html_page(texts["title"], texts["invoice_error"])

            await update_payment_meta(
                session,
                order,
                payment_provider="multicard",
                payment_status="",
                invoice_id=invoice.invoice_id,
                invoice_uuid=invoice.uuid,
                checkout_url=invoice.checkout_url,
                invoice_expiry_at=invoice.expiry_at,
            )
            await session.commit()
        raise web.HTTPFound(invoice.checkout_url)

    async def callback_handler(request: web.Request) -> web.StreamResponse:
        app_context: AppContext = request.app["app_context"]
        bot_instance: Bot = request.app["bot"]
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"success": False, "message": "Invalid payload"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"success": False, "message": "Invalid payload"}, status=400)
        if not _callback_allowed(request, payload, app_context):
            return web.json_response({"success": False, "message": "Forbidden"}, status=403)

        reference = str(payload.get("uuid") or payload.get("invoice_id") or request.query.get("order") or "").strip()
        async with app_context.session_factory() as session:
            order = await get_order_by_invoice_reference(session, reference)
            if order is None and payload.get("invoice_id"):
                order = await get_order_by_number(session, str(payload.get("invoice_id")))
            if order is None and request.query.get("order"):
                order = await get_order_by_number(session, request.query["order"])
            if order is None:
                return web.json_response({"success": False, "message": "Order not found"}, status=404)
            await _apply_payment_update(
                session,
                app_context,
                bot_instance,
                order,
                payload,
                source=f"multicard:callback:{extract_remote_status(payload) or 'unknown'}",
            )

        return web.json_response({"success": True})

    async def return_handler(request: web.Request) -> web.StreamResponse:
        app_context: AppContext = request.app["app_context"]
        bot_instance: Bot = request.app["bot"]
        reference = (
            request.query.get("uuid")
            or request.query.get("invoice_uuid")
            or request.query.get("order")
            or request.query.get("invoice_id")
            or ""
        ).strip()
        async with app_context.session_factory() as session:
            order = await get_order_by_invoice_reference(session, reference)
            if order is None and reference:
                order = await get_order_by_number(session, reference)
            if order is None:
                return _html_page(_response_texts("ru")["title"], _response_texts("ru")["not_found"])

            language = order.language or app_context.settings.default_language
            texts = _response_texts(language)
            message = texts["paid"] if order.payment_status == "paid" else texts["pending"]

            if order.invoice_uuid:
                try:
                    payload = await fetch_invoice(app_context.settings, order.invoice_uuid)
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    mapped_status = await _apply_payment_update(
                        session,
                        app_context,
                        bot_instance,
                        order,
                        payload,
                        source=f"multicard:return:{extract_remote_status(payload) or 'unknown'}",
                    )
                    if mapped_status == "paid":
                        message = texts["paid"]
                    elif mapped_status == "failed":
                        message = texts["failed"]
                    else:
                        message = texts["ready"] if mapped_status == "processing" else texts["pending"]

        return _html_page(texts["title"], message)

    http_app.router.add_get("/checkout/{order_number}", checkout_handler)
    http_app.router.add_post("/callback", callback_handler)
    http_app.router.add_get("/return", return_handler)

    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, app.settings.http_host, app.settings.http_port)
    await site.start()
    return runner
