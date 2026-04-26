#!/usr/bin/env python3
"""
Self-hosted UPI Payment Microservice for Hack Store Telegram Bot.

Real Gmail-IMAP-backed payment verification:
  - /login          : validates Gmail App Password by attempting an IMAP
                      connection. On success creates a real session token.
  - /generate_qr    : produces a real UPI deep-link QR (PNG) for the
                      configured UPI ID, amount and order id.
  - /verify_payment : connects to the admin's Gmail inbox via IMAP and
                      searches for a UPI / bank "credit" notification that
                      matches the order amount and order id. Returns the
                      UTR and transaction id when found.

Runs on http://localhost:8000 by default. Stores sessions and orders in
MongoDB (same database the bot uses).

Environment overrides:
  PAY_SVC_HOST          (default 0.0.0.0)
  PAY_SVC_PORT          (default 8000)
  PAY_SVC_PUBLIC_BASE   (default http://localhost:8000) — used in QR image URLs
  PAY_SVC_FERNET_KEY    (default derived from BOT_TOKEN) — encrypts app passwords
"""

import asyncio
import base64
import email
import hashlib
import imaplib
import io
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Optional

import qrcode
from aiohttp import web
from cryptography.fernet import Fernet, InvalidToken
from pymongo import ASCENDING, MongoClient

from config import BOT_TOKEN, MONGO_DB_NAME, MONGO_URI

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - payment_svc - %(levelname)s - %(message)s",
)
log = logging.getLogger("payment_svc")

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
HOST = os.environ.get("PAY_SVC_HOST", "0.0.0.0")
PORT = int(os.environ.get("PAY_SVC_PORT", "8000"))


def _autodetect_public_base() -> str:
    """Pick a sensible public base URL without admin configuration.

    Priority:
      1. PAY_SVC_PUBLIC_BASE                      (manual override)
      2. RENDER_EXTERNAL_URL                      (Render hosting)
      3. https://$RAILWAY_PUBLIC_DOMAIN           (Railway hosting)
      4. https://$FLY_APP_NAME.fly.dev            (Fly.io)
      5. https://$REPLIT_DEV_DOMAIN               (Replit dev preview)
      6. https://$REPL_SLUG.$REPL_OWNER.repl.co   (legacy Replit URL)
      7. http://localhost:<PORT>                  (last-resort fallback)
    """
    explicit = os.environ.get("PAY_SVC_PUBLIC_BASE", "").strip().rstrip("/")
    if explicit:
        return explicit

    render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render_url:
        return render_url

    railway = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip().rstrip("/")
    if railway:
        return f"https://{railway}" if not railway.startswith(("http://", "https://")) else railway

    fly = os.environ.get("FLY_APP_NAME", "").strip()
    if fly:
        return f"https://{fly}.fly.dev"

    replit_dev = os.environ.get("REPLIT_DEV_DOMAIN", "").strip().rstrip("/")
    if replit_dev:
        return f"https://{replit_dev}" if not replit_dev.startswith(("http://", "https://")) else replit_dev

    repl_slug = os.environ.get("REPL_SLUG", "").strip()
    repl_owner = os.environ.get("REPL_OWNER", "").strip()
    if repl_slug and repl_owner:
        return f"https://{repl_slug}.{repl_owner}.repl.co"

    return f"http://localhost:{PORT}"


PUBLIC_BASE = _autodetect_public_base()
QR_TTL_SECONDS = 5 * 60  # 5 minutes
SESSION_TTL_DAYS = 30
IST_TZ = timezone(timedelta(hours=5, minutes=30))

# ──────────────────────────────────────────────────────────────────────────────
# Encryption (Fernet) — protects app passwords stored in MongoDB
# ──────────────────────────────────────────────────────────────────────────────
def _derive_fernet_key() -> bytes:
    """Derive a stable Fernet key from BOT_TOKEN unless one is set in env."""
    explicit = os.environ.get("PAY_SVC_FERNET_KEY", "").strip()
    if explicit:
        try:
            Fernet(explicit.encode())
            return explicit.encode()
        except Exception:
            log.warning("PAY_SVC_FERNET_KEY invalid, deriving from BOT_TOKEN")
    digest = hashlib.sha256(("hack-store-payment-svc::" + BOT_TOKEN).encode()).digest()
    return base64.urlsafe_b64encode(digest)


FERNET = Fernet(_derive_fernet_key())


def _enc(s: str) -> str:
    return FERNET.encrypt(s.encode()).decode()


def _dec(s: str) -> str:
    try:
        return FERNET.decrypt(s.encode()).decode()
    except (InvalidToken, Exception):
        return ""


# ──────────────────────────────────────────────────────────────────────────────
# MongoDB
# ──────────────────────────────────────────────────────────────────────────────
import dns.resolver  # noqa: E402

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ["8.8.8.8"]

_mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
_db = _mongo[MONGO_DB_NAME]
sessions_col = _db["payment_sessions"]
orders_col = _db["payment_orders"]

sessions_col.create_index([("session_token", ASCENDING)], unique=True)
sessions_col.create_index([("admin_id", ASCENDING)])
orders_col.create_index([("order_id", ASCENDING)], unique=True)
orders_col.create_index([("admin_id", ASCENDING)])

# In-memory QR PNG cache (order_id -> bytes). Survives until process restart.
_qr_cache: dict[str, bytes] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _ok(data: Optional[dict] = None, **extra) -> web.Response:
    payload = {"status": "ok"}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return web.json_response(payload)


def _success(data: dict) -> web.Response:
    return web.json_response({"status": "success", "data": data})


def _err(message: str, http_status: int = 200) -> web.Response:
    return web.json_response({"status": "error", "message": message}, status=http_status)


def _bearer_token(request: web.Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _get_session(token: str) -> Optional[dict]:
    if not token:
        return None
    return sessions_col.find_one({"session_token": token})


def _normalise_app_password(raw: str) -> str:
    """Gmail app passwords are 16 chars, often shown as 4×4 with spaces."""
    return re.sub(r"\s+", "", raw or "")


def _validate_mobile(m: str) -> bool:
    return bool(re.match(r"^\+?\d{10,13}$", (m or "").strip()))


def _validate_email(e: str) -> bool:
    e = (e or "").strip().lower()
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e))


def _now_ist_str() -> str:
    return datetime.now(IST_TZ).strftime("%Y-%m-%d %H:%M:%S IST")


# ──────────────────────────────────────────────────────────────────────────────
# IMAP — credential check + payment search
# ──────────────────────────────────────────────────────────────────────────────
def _imap_login_check(email_addr: str, app_password: str) -> tuple[bool, str]:
    """Try to log in to Gmail IMAP; return (ok, error_message)."""
    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    except Exception as e:
        return False, f"Cannot reach Gmail IMAP server: {e}"
    try:
        m.login(email_addr, app_password)
        try:
            m.logout()
        except Exception:
            pass
        return True, ""
    except imaplib.IMAP4.error as e:
        msg = str(e)
        if "Invalid credentials" in msg or "AUTHENTICATIONFAILED" in msg:
            return False, "Invalid Gmail address or App Password."
        return False, f"Gmail login failed: {msg}"
    except Exception as e:
        return False, f"Gmail login error: {e}"


# UPI / bank notification senders we look for. Add freely.
PAYMENT_SENDERS = (
    "fampay",
    "alerts@hdfcbank",
    "alerts@axisbank",
    "alerts@icicibank",
    "alerts@sbi",
    "no-reply@phonepe",
    "noreply@phonepe",
    "noreply@paytm",
    "no-reply@paytm",
    "noreply@google.com",
    "googleplay-noreply@google.com",
    "noreply@upi",
    "noreply@npci",
    "alerts@kotak",
    "alerts@yesbank",
    "creditalert",
    "txnalert",
    "donotreply@cashfree",
    "noreply@razorpay",
)

CREDIT_KEYWORDS = (
    "credited",
    "received",
    "money received",
    "payment received",
    "successfully credited",
    "credited to your",
    "has credited",
)

UTR_RE = re.compile(r"\b(?:UTR|RRN|Txn(?:\s*Id)?|Reference(?:\s*No)?|Ref\s*No)[:\s\-]+([A-Za-z0-9]{8,})", re.I)
AMOUNT_RE = re.compile(r"(?:Rs\.?|INR|₹)\s*([0-9]+(?:[,.][0-9]{1,2})?)", re.I)


def _decode_part(raw: bytes, charset: Optional[str]) -> str:
    for enc in (charset, "utf-8", "latin-1"):
        if not enc:
            continue
        try:
            return raw.decode(enc, errors="replace")
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _email_text(msg: email.message.Message) -> str:
    """Extract plain-text body from an email message (HTML stripped of tags)."""
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype not in ("text/plain", "text/html"):
                continue
            try:
                payload = part.get_payload(decode=True) or b""
            except Exception:
                continue
            text = _decode_part(payload, part.get_content_charset())
            if ctype == "text/html":
                text = re.sub(r"<[^>]+>", " ", text)
            parts.append(text)
    else:
        try:
            payload = msg.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        text = _decode_part(payload, msg.get_content_charset())
        if (msg.get_content_type() or "").endswith("html"):
            text = re.sub(r"<[^>]+>", " ", text)
        parts.append(text)
    body = " ".join(parts)
    # collapse whitespace + decode subject too
    return re.sub(r"\s+", " ", body)


def _decode_header_str(raw: Optional[str]) -> str:
    if not raw:
        return ""
    chunks = decode_header(raw)
    out = []
    for piece, enc in chunks:
        if isinstance(piece, bytes):
            try:
                out.append(piece.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(piece.decode("utf-8", errors="replace"))
        else:
            out.append(piece)
    return "".join(out)


def _amount_matches(text: str, expected: float) -> bool:
    """True if text contains the expected amount (with rupees-or-paise tolerance)."""
    found = AMOUNT_RE.findall(text)
    if not found:
        return False
    targets = {f"{expected:.2f}", f"{expected:.0f}", f"{int(expected)}"}
    for raw in found:
        norm = raw.replace(",", "")
        try:
            val = float(norm)
        except ValueError:
            continue
        if abs(val - expected) < 0.01:
            return True
        if f"{val:.2f}" in targets:
            return True
    return False


def _imap_find_payment(email_addr: str, app_password: str, order_id: str,
                       amount: float, since_ts: float) -> Optional[dict]:
    """Search Gmail inbox for a credit notification matching the order.

    Returns dict {utr, transaction_id, sender, subject} on match, else None.
    """
    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    except Exception as e:
        log.error("IMAP connect failed: %s", e)
        return None

    try:
        m.login(email_addr, app_password)
    except Exception as e:
        log.error("IMAP login failed during verify: %s", e)
        try:
            m.logout()
        except Exception:
            pass
        return None

    try:
        m.select("INBOX")
        # Search since the order was created (UTC date)
        since_date = datetime.fromtimestamp(max(since_ts - 86400, 0)).strftime("%d-%b-%Y")
        typ, data = m.search(None, f'(SINCE "{since_date}")')
        if typ != "OK" or not data or not data[0]:
            return None

        ids = data[0].split()
        # Newest first, cap to last 80 messages for speed
        for msg_id in reversed(ids[-80:]):
            typ, msg_data = m.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender = _decode_header_str(msg.get("From", "")).lower()
            subject = _decode_header_str(msg.get("Subject", ""))

            # Sender filter
            if not any(s in sender for s in PAYMENT_SENDERS):
                continue

            body = _email_text(msg)
            haystack = (subject + " " + body).lower()

            # Must be a credit / payment received email
            if not any(kw in haystack for kw in CREDIT_KEYWORDS):
                continue

            # Match either by order_id present in body OR by exact amount
            order_match = order_id.lower() in haystack
            amt_match = _amount_matches(subject + " " + body, amount)

            if not (order_match or amt_match):
                continue

            # Pull UTR / Txn Id
            utr = ""
            txn = ""
            mu = UTR_RE.search(body) or UTR_RE.search(subject)
            if mu:
                utr = mu.group(1)
                txn = mu.group(1)

            return {
                "utr": utr or "AUTO-VERIFIED",
                "transaction_id": txn or msg.get("Message-Id", "").strip("<>") or "AUTO-VERIFIED",
                "sender": sender,
                "subject": subject,
            }
    finally:
        try:
            m.logout()
        except Exception:
            pass

    return None


# ──────────────────────────────────────────────────────────────────────────────
# QR rendering
# ──────────────────────────────────────────────────────────────────────────────
def _build_upi_link(upi_id: str, payee_name: str, amount: float, order_id: str) -> str:
    from urllib.parse import quote
    return (
        "upi://pay?"
        f"pa={quote(upi_id)}"
        f"&pn={quote(payee_name)}"
        f"&am={amount:.2f}"
        "&cu=INR"
        f"&tn={quote(order_id)}"
        f"&tr={quote(order_id)}"
    )


def _render_qr_png(payload: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────
async def health(_request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "service": "hack-store-payment-svc",
        "time": _now_ist_str(),
        "public_base": PUBLIC_BASE,
        "auto_detected": not bool(os.environ.get("PAY_SVC_PUBLIC_BASE", "").strip()),
    })


async def login(request: web.Request) -> web.Response:
    """
    POST /login
    body: {admin_id, mobile, email, otp}
        - "otp" carries the Gmail App Password (the bot's UI labels it
          'Verification Code / App Password').
    """
    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body.")

    admin_id = body.get("admin_id")
    mobile = (body.get("mobile") or "").strip()
    email_addr = (body.get("email") or "").strip().lower()
    app_password_raw = body.get("otp") or body.get("app_password") or ""
    app_password = _normalise_app_password(app_password_raw)

    if not isinstance(admin_id, int):
        try:
            admin_id = int(admin_id)
        except Exception:
            return _err("admin_id must be an integer.")

    if not _validate_mobile(mobile):
        return _err("Invalid mobile number.")
    if not _validate_email(email_addr):
        return _err("Invalid email address.")
    if len(app_password) != 16 or not re.match(r"^[A-Za-z0-9]+$", app_password):
        return _err("App Password must be exactly 16 characters (Google App Password format).")

    # Real check against Gmail IMAP — runs in a thread to avoid blocking event loop.
    loop = asyncio.get_running_loop()
    ok, err = await loop.run_in_executor(None, _imap_login_check, email_addr, app_password)
    if not ok:
        return _err(err or "Gmail login failed.")

    token = secrets.token_urlsafe(32)
    sessions_col.update_one(
        {"admin_id": admin_id},
        {"$set": {
            "admin_id": admin_id,
            "session_token": token,
            "mobile": mobile,
            "email": email_addr,
            "app_password_enc": _enc(app_password),
            "created_at": time.time(),
            "expires_at": time.time() + SESSION_TTL_DAYS * 86400,
        }},
        upsert=True,
    )
    log.info("Login OK for admin_id=%s email=%s", admin_id, email_addr)
    return web.json_response({
        "status": "ok",
        "session_token": token,
        "expires_in_days": SESSION_TTL_DAYS,
        "email": email_addr,
        "mobile": mobile,
    })


async def logout(request: web.Request) -> web.Response:
    token = _bearer_token(request)
    if token:
        sessions_col.delete_one({"session_token": token})
    return _ok()


async def generate_qr(request: web.Request) -> web.Response:
    """
    POST /generate_qr
    body: {admin_id, amount, order_id, upi_id?, payee_name?}
        - If upi_id is omitted, the most-recently-stored UPI ID for the
          admin is reused.
    """
    token = _bearer_token(request)
    sess = _get_session(token)
    if not sess:
        return _err("Invalid or expired session. Please login again.")

    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body.")

    admin_id = body.get("admin_id") or sess["admin_id"]
    try:
        admin_id = int(admin_id)
    except Exception:
        return _err("admin_id must be an integer.")

    if admin_id != sess["admin_id"]:
        return _err("admin_id does not match session.")

    try:
        amount = float(body.get("amount"))
    except Exception:
        return _err("amount must be a number (rupees).")
    if amount <= 0:
        return _err("amount must be > 0.")

    order_id = (body.get("order_id") or "").strip()
    if not order_id:
        return _err("order_id is required.")

    upi_id = (body.get("upi_id") or sess.get("upi_id") or "").strip()
    if not upi_id or "@" not in upi_id:
        return _err("upi_id is required (format: name@bank).")

    payee_name = (body.get("payee_name") or "Hack Store").strip()[:40]

    # Persist upi_id back onto the session for re-use
    sessions_col.update_one(
        {"_id": sess["_id"]},
        {"$set": {"upi_id": upi_id, "payee_name": payee_name}},
    )

    upi_link = _build_upi_link(upi_id, payee_name, amount, order_id)
    png = _render_qr_png(upi_link)
    _qr_cache[order_id] = png

    expires_at = time.time() + QR_TTL_SECONDS
    orders_col.update_one(
        {"order_id": order_id},
        {"$set": {
            "order_id": order_id,
            "admin_id": admin_id,
            "upi_id": upi_id,
            "payee_name": payee_name,
            "amount": amount,
            "upi_link": upi_link,
            "status": "PENDING",
            "created_at": time.time(),
            "expires_at": expires_at,
        }},
        upsert=True,
    )

    expires_at_ist = datetime.fromtimestamp(expires_at, IST_TZ).strftime("%H:%M IST")
    qr_url = f"{PUBLIC_BASE}/qr/{order_id}.png"
    qr_b64 = base64.b64encode(png).decode("ascii")
    log.info("QR generated for order=%s amount=%.2f upi=%s", order_id, amount, upi_id)
    return _success({
        "qr_url": qr_url,
        "qr_b64": qr_b64,
        "upi_link": upi_link,
        "amount": amount,
        "order_id": order_id,
        "expires_at_ist": expires_at_ist,
    })


async def serve_qr(request: web.Request) -> web.Response:
    order_id = request.match_info.get("order_id", "")
    png = _qr_cache.get(order_id)
    if not png:
        # rebuild from DB if cache was cleared (process restart)
        order = orders_col.find_one({"order_id": order_id})
        if not order:
            return web.Response(status=404, text="Not found")
        png = _render_qr_png(order["upi_link"])
        _qr_cache[order_id] = png
    return web.Response(body=png, content_type="image/png",
                        headers={"Cache-Control": "no-store"})


async def verify_payment(request: web.Request) -> web.Response:
    """
    POST /verify_payment
    body: {admin_id, order_id}
    """
    token = _bearer_token(request)
    sess = _get_session(token)
    if not sess:
        return _err("Invalid or expired session. Please login again.")

    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body.")

    order_id = (body.get("order_id") or "").strip()
    if not order_id:
        return _err("order_id is required.")

    order = orders_col.find_one({"order_id": order_id, "admin_id": sess["admin_id"]})
    if not order:
        return _err("Order not found.")

    # Already verified earlier → return cached result
    if order.get("status") == "PAID":
        return _success({
            "utr": order.get("utr", "N/A"),
            "transaction_id": order.get("transaction_id", "N/A"),
            "amount": order.get("amount", 0),
            "verified_at_ist": order.get("verified_at_ist", ""),
            "cached": True,
        })

    app_password = _dec(sess.get("app_password_enc", ""))
    if not app_password:
        return _err("Stored credentials are unreadable. Please login again.")

    loop = asyncio.get_running_loop()
    match = await loop.run_in_executor(
        None,
        _imap_find_payment,
        sess["email"],
        app_password,
        order_id,
        float(order["amount"]),
        float(order.get("created_at", time.time() - 3600)),
    )

    if not match:
        return _err("Payment not yet received.")

    utr = match["utr"]
    txn = match["transaction_id"]
    verified_at = _now_ist_str()
    orders_col.update_one(
        {"_id": order["_id"]},
        {"$set": {
            "status": "PAID",
            "utr": utr,
            "transaction_id": txn,
            "verified_at": time.time(),
            "verified_at_ist": verified_at,
            "matched_sender": match.get("sender", ""),
            "matched_subject": match.get("subject", ""),
        }},
    )
    log.info("Verified order=%s utr=%s sender=%s",
             order_id, utr, match.get("sender", ""))
    return _success({
        "utr": utr,
        "transaction_id": txn,
        "amount": float(order["amount"]),
        "verified_at_ist": verified_at,
    })


# ──────────────────────────────────────────────────────────────────────────────
# App factory + main
# ──────────────────────────────────────────────────────────────────────────────
def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/login", login)
    app.router.add_post("/logout", logout)
    app.router.add_post("/generate_qr", generate_qr)
    app.router.add_post("/verify_payment", verify_payment)
    app.router.add_get("/qr/{order_id}.png", serve_qr)
    return app


def main() -> None:
    log.info("Starting Hack Store Payment Microservice on %s:%d", HOST, PORT)
    log.info("Public base for QR URLs: %s", PUBLIC_BASE)
    web.run_app(make_app(), host=HOST, port=PORT, print=None)


if __name__ == "__main__":
    main()
