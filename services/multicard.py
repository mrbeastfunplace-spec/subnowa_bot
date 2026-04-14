from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from config import Settings


CBU_RATES_URL = "https://cbu.uz/oz/arkhiv-kursov-valyut/json/"
REQUEST_TIMEOUT = ClientTimeout(total=20)
RATE_CACHE_TTL = timedelta(minutes=15)
INVOICE_LIFETIME = timedelta(minutes=15)

_rate_cache_value: Decimal | None = None
_rate_cache_at: datetime | None = None


class MulticardError(RuntimeError):
    pass


@dataclass(slots=True)
class MulticardInvoice:
    invoice_id: str
    uuid: str
    checkout_url: str
    expiry_at: datetime | None
    raw: dict[str, Any]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_language(value: str | None) -> str:
    if value in {"ru", "uz", "en"}:
        return value
    return "ru"


def _parse_decimal(value: Any) -> Decimal:
    normalized = str(value or "").strip().replace(" ", "").replace(",", ".")
    return Decimal(normalized)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _payload_value(payload: dict[str, Any], key: str) -> str:
    if not isinstance(payload, dict):
        return ""

    direct = payload.get(key)
    if direct not in (None, ""):
        return str(direct).strip()

    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get(key)
        if nested not in (None, ""):
            return str(nested).strip()
        payment = data.get("payment")
        if isinstance(payment, dict):
            payment_value = payment.get(key)
            if payment_value not in (None, ""):
                return str(payment_value).strip()

    return ""


def _money_to_invoice_amount(value: Decimal | int | float | str) -> int:
    amount = Decimal(str(value))
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _error_details(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            details = error.get("details")
            if details:
                return str(details)
        message = payload.get("message")
        if message:
            return str(message)
    return "Unknown Multicard error"


def _text_error_details(body: str, *, status: int) -> str:
    text = (body or "").strip()
    if not text:
        return f"Multicard returned an empty response (HTTP {status})"
    compact = " ".join(text.split())
    if len(compact) > 300:
        compact = f"{compact[:297]}..."
    return f"Multicard returned a non-JSON response (HTTP {status}): {compact}"


async def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    async with ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.request(method, url, headers=headers, json=json_body) as response:
            body = await response.text()
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise MulticardError(_text_error_details(body, status=response.status)) from exc
            if response.status >= 400:
                raise MulticardError(_error_details(payload))
            return payload


async def authenticate(settings: Settings) -> str:
    payload = await _request_json(
        "POST",
        f"{settings.multicard_base_url}/auth",
        headers={"Content-Type": "application/json"},
        json_body={
            "application_id": settings.multicard_app_id,
            "secret": settings.multicard_secret,
        },
    )
    token = str(payload.get("token") or "").strip()
    if not token:
        raise MulticardError("Multicard token was not returned")
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Access-Token": token,
        "Content-Type": "application/json",
    }


def _resolve_expiry(payload: dict[str, Any]) -> datetime | None:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    for key in ("expiry_at", "expiry", "expires_at"):
        if key in data:
            parsed = _parse_datetime(data.get(key))
            if parsed is not None:
                return parsed
    payment = data.get("payment")
    if isinstance(payment, dict):
        for key in ("expiry_at", "expiry", "expires_at"):
            if key in payment:
                parsed = _parse_datetime(payment.get(key))
                if parsed is not None:
                    return parsed
    return _utc_now() + INVOICE_LIFETIME


async def create_invoice(
    settings: Settings,
    *,
    amount_uzs: Decimal | int | float | str,
    invoice_id: str,
    language: str,
    callback_url: str,
    return_url: str,
) -> MulticardInvoice:
    token = await authenticate(settings)
    payload = await _request_json(
        "POST",
        f"{settings.multicard_base_url}/api/payment/invoice",
        headers=_auth_headers(token),
        json_body={
            "store_id": settings.multicard_store_id,
            "amount": _money_to_invoice_amount(amount_uzs),
            "invoice_id": invoice_id,
            "lang": _normalize_language(language),
            "return_url": return_url,
            "callback_url": callback_url,
        },
    )
    if not payload.get("success"):
        raise MulticardError(_error_details(payload))
    data = payload.get("data") or {}
    checkout_url = str(data.get("checkout_url") or "").strip()
    invoice_uuid = str(data.get("uuid") or "").strip()
    returned_invoice_id = str(data.get("invoice_id") or invoice_id).strip()
    if not checkout_url or not invoice_uuid:
        raise MulticardError("Multicard invoice response is missing uuid or checkout_url")
    return MulticardInvoice(
        invoice_id=returned_invoice_id,
        uuid=invoice_uuid,
        checkout_url=checkout_url,
        expiry_at=_resolve_expiry(payload),
        raw=data,
    )


async def fetch_invoice(settings: Settings, uuid: str) -> dict[str, Any]:
    token = await authenticate(settings)
    payload = await _request_json(
        "GET",
        f"{settings.multicard_base_url}/payment/invoice/{uuid}",
        headers=_auth_headers(token),
    )
    if isinstance(payload, dict) and payload.get("success") is False:
        raise MulticardError(_error_details(payload))
    return payload


def extract_remote_status(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    for candidate in (payload.get("status"), payload.get("payment_status")):
        if candidate:
            return str(candidate).strip().lower()
    data = payload.get("data")
    if isinstance(data, dict):
        for candidate in (data.get("status"), data.get("payment_status")):
            if candidate:
                return str(candidate).strip().lower()
        payment = data.get("payment")
        if isinstance(payment, dict):
            candidate = payment.get("status")
            if candidate:
                return str(candidate).strip().lower()
    return ""


def map_payment_status(remote_status: str | None) -> str:
    value = (remote_status or "").strip().lower()
    if value == "success":
        return "paid"
    if value == "progress":
        return "processing"
    if value in {"error", "revert"}:
        return "failed"
    return value


def verify_success_signature(payload: dict[str, Any], settings: Settings) -> bool:
    store_id = _payload_value(payload, "store_id")
    invoice_id = _payload_value(payload, "invoice_id")
    amount = _payload_value(payload, "amount")
    sign = _payload_value(payload, "sign").lower()
    if not (store_id and invoice_id and amount and sign):
        return False
    expected = hashlib.md5(f"{store_id}{invoice_id}{amount}{settings.multicard_secret}".encode("utf-8")).hexdigest()
    return sign == expected.lower()


def verify_webhook_signature(payload: dict[str, Any], settings: Settings) -> bool:
    invoice_uuid = _payload_value(payload, "uuid")
    invoice_id = _payload_value(payload, "invoice_id")
    amount = _payload_value(payload, "amount")
    sign = _payload_value(payload, "sign").lower()
    if not (invoice_uuid and invoice_id and amount and sign):
        return False
    expected = hashlib.sha1(f"{invoice_uuid}{invoice_id}{amount}{settings.multicard_secret}".encode("utf-8")).hexdigest()
    return sign == expected.lower()


def verify_callback_signature(payload: dict[str, Any], settings: Settings) -> bool:
    return verify_webhook_signature(payload, settings) or verify_success_signature(payload, settings)


async def get_usd_uzs_rate() -> Decimal:
    global _rate_cache_at, _rate_cache_value

    now = _utc_now()
    if _rate_cache_value is not None and _rate_cache_at is not None and now - _rate_cache_at <= RATE_CACHE_TTL:
        return _rate_cache_value

    try:
        async with ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(CBU_RATES_URL) as response:
                payload = await response.json(content_type=None)
                if response.status >= 400:
                    raise MulticardError("Failed to fetch USD/UZS rate")
        if not isinstance(payload, list):
            raise MulticardError("Unexpected CBU response format")
        for row in payload:
            if not isinstance(row, dict):
                continue
            if str(row.get("Ccy") or "").strip().upper() != "USD":
                continue
            rate = _parse_decimal(row.get("Rate"))
            if rate > 0:
                _rate_cache_value = rate
                _rate_cache_at = now
                return rate
        raise MulticardError("USD rate was not found in CBU response")
    except Exception:
        if _rate_cache_value is not None:
            return _rate_cache_value
        raise


async def convert_uzs_to_usd(amount_uzs: Decimal | int | float | str) -> Decimal:
    rate = await get_usd_uzs_rate()
    amount = Decimal(str(amount_uzs))
    if rate <= 0:
        raise MulticardError("USD/UZS rate is invalid")
    return (amount / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
