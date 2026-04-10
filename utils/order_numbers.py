from __future__ import annotations

import random
import string


def generate_order_number(prefix: str = "SN") -> str:
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}-{code}"
