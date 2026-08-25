#!/usr/bin/env python3
"""
Reseller API client for Hack Store.

Talks to the upstream reseller panel (adminpanels.shop/api/reseller_v1.php)
to automatically BUY keys when local manual stock runs out.

Usage:
    ok, key_or_error, raw = await buy_key(product_pid="133", duration="1 Day")
    # android_id is MANDATORY only for device-bound products (e.g. BALA MOD XYZ V1),
    # optional / not required for V2 products.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

import aiohttp

from config import RESELLER_API_KEY, RESELLER_API_URL, RESELLER_MASTER_KEY

log = logging.getLogger("reseller_api")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

TIMEOUT_SECONDS = 30


async def _get_cfg() -> Tuple[str, str, str]:
    """Resolve (url, api_key, master_key) from DB settings (owner-editable via
    /admin) falling back to config.py / environment defaults."""
    url, api_key, master = RESELLER_API_URL, RESELLER_API_KEY, RESELLER_MASTER_KEY
    try:
        from database import db_mgr
        url = await db_mgr.get_setting("reseller_api_url", url)
        api_key = await db_mgr.get_setting("reseller_api_key", api_key)
        master = await db_mgr.get_setting("reseller_master_key", master)
    except Exception as e:
        log.debug("Falling back to static reseller API config: %s", e)
    return url, api_key, master


def _extract_key(payload: Any) -> str:
    """Best-effort extraction of the purchased key from an API response."""
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for field in (
        "key", "license", "license_key", "activation_key", "token",
        "serial", "code", "product_key", "access_key", "result",
    ):
        val = data.get(field) if isinstance(data, dict) else None
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _is_success(payload: Dict[str, Any]) -> bool:
    status = str(payload.get("status", payload.get("success", ""))).lower()
    if status in ("1", "true", "ok", "success"):
        return True
    if status in ("0", "false", "error", "failed"):
        return False
    # No explicit status: success if we found a key and no error text
    err = str(payload.get("error", payload.get("message", ""))).lower()
    return not any(w in err for w in ("error", "fail", "invalid", "out of stock")) and bool(_extract_key(payload))


def _error_message(payload: Dict[str, Any], http_status: int) -> str:
    for field in ("message", "error", "msg", "reason"):
        val = payload.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return f"Reseller API error (HTTP {http_status})"


async def buy_key(
    product_pid: int | str,
    duration: str,
    android_id: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Buy one key from the reseller panel.

    Returns (ok, key_or_error_message, raw_response).
    """
    form = {
        "action": "buy",
        "product_id": str(product_pid),
        "duration": duration,
    }

    url, api_key, master = await _get_cfg()
    if not url or not api_key or not master:
        return False, "Reseller API not configured.", {}

    form["api_key"] = api_key
    if android_id:
        form["android_id"] = android_id

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "x-master-key": master,
        "User-Agent": USER_AGENT,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=form, headers=headers) as resp:
                text = await resp.text()
                try:
                    import json
                    payload = json.loads(text)
                    if not isinstance(payload, dict):
                        payload = {"raw": text}
                except Exception:
                    payload = {"raw": text}

        log.info("Reseller buy pid=%s dur=%s -> %s", product_pid, duration, str(payload)[:300])

        if _is_success(payload):
            key = _extract_key(payload)
            if key:
                return True, key, payload
            return False, "Reseller API returned no key.", payload
        return False, _error_message(payload, 200), payload

    except asyncio.TimeoutError:
        return False, "Reseller API timeout.", {}
    except Exception as e:
        log.error("Reseller API request failed: %s", e)
        return False, f"Reseller API request failed: {e}", {}
