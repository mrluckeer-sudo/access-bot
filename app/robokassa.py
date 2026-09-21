"""Проверка подписей Robokassa (MD5)."""

from __future__ import annotations

import hashlib
from typing import Mapping


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest().upper()


def _shp_suffix(params: Mapping[str, str]) -> str:
    """Shp_* параметры в алфавитном порядке: :Shp_key=value"""
    shp = {k: v for k, v in params.items() if k.lower().startswith("shp_")}
    if not shp:
        return ""
    parts = [f"{k}={shp[k]}" for k in sorted(shp.keys(), key=str.lower)]
    return ":" + ":".join(parts)


def verify_result_signature(
    out_sum: str,
    inv_id: str,
    signature: str,
    password2: str,
    extra: Mapping[str, str] | None = None,
) -> bool:
    base = f"{out_sum}:{inv_id}:{password2}"
    expected = _md5(base + _shp_suffix(extra or {}))
    return expected == signature.upper()


def verify_success_signature(
    out_sum: str,
    inv_id: str,
    signature: str,
    password1: str,
    extra: Mapping[str, str] | None = None,
) -> bool:
    base = f"{out_sum}:{inv_id}:{password1}"
    expected = _md5(base + _shp_suffix(extra or {}))
    return expected == signature.upper()


def payment_signature(
    merchant_login: str,
    out_sum: str,
    inv_id: int,
    password1: str,
) -> str:
    return _md5(f"{merchant_login}:{out_sum}:{inv_id}:{password1}")
