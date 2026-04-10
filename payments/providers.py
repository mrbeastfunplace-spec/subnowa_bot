from __future__ import annotations

from payments.base import PaymentProvider


PROVIDERS = {
    "click": PaymentProvider(provider_type="click"),
    "card": PaymentProvider(provider_type="card"),
    "crypto": PaymentProvider(provider_type="crypto"),
    "other": PaymentProvider(provider_type="other"),
}


def get_provider(provider_type: str) -> PaymentProvider:
    return PROVIDERS.get(provider_type, PROVIDERS["other"])
