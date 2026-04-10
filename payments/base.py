from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PaymentProvider:
    provider_type: str

    def render_instructions(self, template: str, credentials: str) -> str:
        try:
            return (template or "").format(credentials=credentials)
        except Exception:
            return template or credentials
