"""Проверка уведомлений CloudPayments (HMAC-SHA256 + Base64)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


def verify_notification_hmac(raw_body: bytes, signature: str | None, api_secret: str) -> bool:
    """Content-HMAC = Base64(HMAC_SHA256(api_secret, raw_body))."""
    if not signature or not api_secret:
        return False
    expected = base64.b64encode(
        hmac.new(api_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(expected, signature.strip())


def parse_data_json(data_field: str | None) -> dict[str, Any]:
    if not data_field:
        return {}
    try:
        parsed = json.loads(data_field)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def resolve_inv_id(invoice_id: str | None, transaction_id: str | None) -> int | None:
    """
    Tilda обычно передаёт числовой InvoiceId.
    Если нет — берём TransactionId CloudPayments (всегда уникален).
    """
    for raw in (invoice_id, transaction_id):
        value = (raw or "").strip()
        if value.isdigit():
            return int(value)
    return None
