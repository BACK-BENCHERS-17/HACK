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
from pymongo.errors import DuplicateKeyError

from config import BOT_TOKEN, MONGO_DB_NAME, MONGO_URI
from database import DatabaseManager

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
PORT = int(os.environ.get("PAY_SVC_PORT") or os.environ.get("PORT") or "8000")


def _autodetect_public_base() -> str:
    """Pick a sensible public base URL without admin configuration."""
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

db_mgr = DatabaseManager()
_mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
_db = _mongo[MONGO_DB_NAME]
sessions_col = _db["payment_sessions"]
orders_col = _db["payment_orders"]

sessions_col.create_index([("session_token", ASCENDING)], unique=True)
sessions_col.create_index([("admin_id", ASCENDING)])
orders_col.create_index([("order_id", ASCENDING)], unique=True)
orders_col.create_index([("admin_id", ASCENDING)])

try:
    orders_col.create_index([("utr", ASCENDING)], unique=True, sparse=True)
    orders_col.create_index([("transaction_id", ASCENDING)], unique=True, sparse=True)
except Exception as _e:
    log.warning("Could not create UTR/txn unique indexes: %s", _e)

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


async def _get_session(token: str) -> Optional[dict]:
    if not token:
        return None
    return await asyncio.to_thread(sessions_col.find_one, {"session_token": token})


def _normalise_app_password(raw: str) -> str:
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


PAYMENT_SENDERS = (
    "fampay",
    "fampay.in",
    "trans.alerts@fampay.in",
    "transactions@fampay.in",
    "noreply@fampay.in",
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
    "bharatpe",
    "juspay",
    "indusind",
    "iob.in",
    "pnb.co.in",
    "idfcfirstbank",
    "phonepe.com",
    "upi.org",
    "npci.org.in",
    "noreply@phonepe.com",
    "federalbank",
    "bankofbaroda",
    "centralbank",
    "onlinesbi",
    "unionbankofindia",
    "canarabank",
    "idbi",
    "indianbank",
    "ucombank",
    "rbl",
    "dbs",
    "sc.com",
    "hsbc",
    "citi",
    "payzapp",
    "bhima",
    "shriram",
    "equitas",
    "au-bank",
    "paytm.com",
    "amazon.com",
    "amazonpay",
    "jupiter.money",
    "fi.money",
    "nsdl",
    "equitasbank",
    "shivalikbank",
    "bandhanbank",
    "idfc",
    "tjsb",
    "svcbank",
    "cosmosbank",
    "saraswatbank",
    "abhyudaya",
    "citizencredit",
    "janabank",
    "suratpeoples",
    "utkarshbank",
    "esafbank",
    "fincarebank",
    "unitybank",
    "airtel",
    "jio",
    "mobikwik",
    "freecharge",
    "omni",
    "livquik",
    "pineperks",
    "slice",
    "uni",
    "postpe",
    "onecard",
    "dhani",
)

CREDIT_KEYWORDS = (
    "credited",
    "received",
    "money received",
    "payment received",
    "successfully credited",
    "credited to your",
    "has credited",
    "has been credited",
    "added to your account",
    "you have received",
    "money added",
    "payment of",
    "received a payment",
    "deposit",
    "txn successful",
    "transaction successful",
    "credited to your bank a/c",
    "amt received",
    "payment of rs",
    "transfer from",
    "transfer of",
    "credited with",
    "money in",
    "cash in",
    "added to your fampay",
    "fampay account",
    "new payment",
)

UTR_RE = re.compile(r"\b(?:UTR|RRN|UPI\s*Ref(?:erence)?(?:\s*No)?|Ref(?:\.?\s*No)?|Reference(?:\.?\s*No)?|Transaction\s*No)[:\s\-/]+([A-Za-z0-9]{8,})", re.I)
TXN_RE = re.compile(r"\b(?:Txn(?:\s*Id)?|Transaction(?:\s*Id)?|Reference(?:\s*No)?|Ref\s*No|Transaction\s*Ref)[:\s\-]+([A-Za-z0-9]{8,})", re.I)
AMOUNT_RE = re.compile(r"(?:Rs\.?|INR|₹|Amount|Amt)[:\s]*([0-9]+(?:[,.][0-9]{1,2})?)", re.I)
SENDER_RE = re.compile(
    r"(?:received\s+(?:money\s+)?from|^from|\bfrom)[:\s]+"
    r"([A-Z0-9][A-Za-z0-9][A-Za-z0-9 .'\-]{1,60}?)"
    r"(?:"
    r"\s*(?:\bvia\b|\bon\b|\bby\b|\busing\b|\bfor\b|\bthrough\b|UPI|@)"
    r"|\s*[•\-–|<\.,!₹]"
    r"|\s*[^\x00-\x7F]"
    r"|\s*\n"
    r"|\s*$"
    r")",
    re.I | re.M,
)


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
                text = text.replace("&nbsp;", " ")
                text = re.sub(r"<[^>]+>", " ", text)
            parts.append(text)
    else:
        try:
            payload = msg.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        text = _decode_part(payload, msg.get_content_charset())
        if (msg.get_content_type() or "").endswith("html"):
            text = text.replace("&nbsp;", " ")
            text = re.sub(r"<[^>]+>", " ", text)
        parts.append(text)
    body = " ".join(parts)
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


PLAIN_AMOUNT_RE = re.compile(r"\b([0-9]+(?:[,.][0-9]{1,2})?)\b")

def _amount_matches(text: str, expected: float) -> bool:
    found = AMOUNT_RE.findall(text)
    if not found:
        found = PLAIN_AMOUNT_RE.findall(text)
    
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


def _find_folder_by_attribute(m, attr: str) -> Optional[str]:
    """Find a Gmail folder name by its attribute (e.g. \\All, \\Junk)."""
    try:
        typ, data = m.list()
        if typ != "OK":
            return None
        for line in data:
            # line is like: (\\HasNoChildren \\All) "/" "[Gmail]/All Mail"
            decoded = line.decode("utf-8", errors="replace")
            if attr.lower() in decoded.lower():
                # Extract the part inside the last set of double quotes
                parts = re.findall(r'"([^"]+)"', decoded)
                if parts:
                    return parts[-1]
    except Exception:
        pass
    return None


def _imap_find_payment(email_addr: str, app_password: str, order_id: str,
                       amount: float, order_created_ts: float,
                       used_utrs: Optional[set] = None) -> Optional[dict]:
    used_utrs = used_utrs or set()

    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        m.login(email_addr, app_password)
    except Exception as e:
        log.error("IMAP login failed: %s", e)
        return None

    folders_to_try = ["INBOX"]
    # Fallback to All Mail if INBOX search yields nothing
    all_mail = _find_folder_by_attribute(m, "\\All")
    if all_mail and all_mail not in folders_to_try:
        folders_to_try.append(all_mail)

    try:
        for folder in folders_to_try:
            log.info("Searching folder: %s for order=%s amount=%.2f", folder, order_id, amount)
            try:
                m.select(folder, readonly=True)
            except Exception:
                continue

            since_anchor = max(order_created_ts - 3600 * 8, 0)  # 8 hours ago for delayed emails
            since_date = datetime.fromtimestamp(since_anchor).strftime("%d-%b-%Y")
            
            typ, data = m.search(None, f'(SINCE "{since_date}")')
            if typ != "OK" or not data or not data[0]:
                log.info("No emails found in %s since %s", folder, since_date)
                continue

            ids = data[0].split()
            relevant_ids = ids[-200:] # Increased search range
            if not relevant_ids:
                continue

            # Bulk fetch headers to avoid timeouts
            id_list = ",".join(i.decode() for i in relevant_ids)
            typ, header_data = m.fetch(id_list, "(BODY[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ != "OK":
                continue

            headers_by_id = {}
            for item in header_data:
                if isinstance(item, tuple):
                    msg_id = item[0].split()[0]
                    headers_by_id[msg_id] = email.message_from_bytes(item[1])

            min_email_ts = order_created_ts - 300 # 5 minutes before order

            # Newest first
            for msg_id_bytes in reversed(relevant_ids):
                msg_id = msg_id_bytes # e.g. b'80'
                msg_headers = headers_by_id.get(msg_id)
                if not msg_headers:
                    continue

                sender = _decode_header_str(msg_headers.get("From", "")).lower()
                subject = _decode_header_str(msg_headers.get("Subject", ""))

                is_known_sender = any(s in sender for s in PAYMENT_SENDERS)
                
                try:
                    from email.utils import parsedate_to_datetime
                    email_dt = parsedate_to_datetime(msg_headers.get("Date", ""))
                    email_ts = email_dt.timestamp() if email_dt else 0.0
                except Exception:
                    email_ts = 0.0
                
                if email_ts and email_ts < min_email_ts:
                    if email_ts < min_email_ts - 3600: # Only skip if more than 1 hour old
                        continue

                # Basic filter passed, fetch full body
                typ, msg_data = m.fetch(msg_id_bytes, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                body = _email_text(msg)
                haystack = (subject + " " + body).lower()

                if not any(kw in haystack for kw in CREDIT_KEYWORDS):
                    continue

                unique_suffix = order_id[-8:].lower()
                order_match = (order_id.lower() in haystack) or (unique_suffix in haystack)
                amt_match = _amount_matches(subject + " " + body, amount)

                if is_known_sender:
                    if not (order_match or amt_match):
                        continue
                else:
                    if not (order_match and amt_match):
                        continue

                scan = subject + "\n" + body
                mu = UTR_RE.search(scan)
                mt = TXN_RE.search(scan)
                ms = SENDER_RE.search(scan)

                utr = (mu.group(1) if mu else "").strip()
                txn = (mt.group(1) if mt else "").strip() or utr
                sender_name = ""
                if ms:
                    sender_name = ms.group(1).strip()
                    sender_name = re.sub(r"^(your|the)\s+", "", sender_name, flags=re.I).strip(" .,'\"")

                if utr and utr in used_utrs:
                    continue
                if txn and txn in used_utrs:
                    continue

                payment_time_ist = ""
                try:
                    if email_ts:
                        payment_time_ist = datetime.fromtimestamp(
                            email_ts, IST_TZ).strftime("%d-%m-%Y %H:%M:%S")
                except Exception:
                    pass

                log.info("MATCH FOUND in %s: Order=%s UTR=%s Txn=%s Amt=%.2f", folder, order_id, utr, txn, amount)
                return {
                    "utr": utr or f"AUTO-{order_id[-8:]}",
                    "transaction_id": txn or msg.get("Message-Id", "").strip("<>") or f"AUTO-{order_id[-8:]}",
                    "sender_name": sender_name or "Unknown",
                    "sender": sender,
                    "subject": subject,
                    "payment_time_ist": payment_time_ist,
                    "email_ts": email_ts,
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
        f"upi://pay?pa={upi_id}"
        f"&pn={quote(payee_name)}"
        f"&am={amount:.2f}"
        "&cu=INR"
        f"&tn={quote(order_id)}"
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


async def index_handler(_request: web.Request) -> web.FileResponse:
    if os.path.exists("static/index.html"):
        return web.FileResponse("static/index.html")
    return web.Response(text="Hack Store Web App is coming soon!", content_type="text/html")


async def get_products(_request: web.Request) -> web.Response:
    products = await db_mgr.get_active_products()
    return _success(products)


async def get_plans(request: web.Request) -> web.Response:
    prod_id = request.match_info.get("prod_id")
    if not prod_id:
        return _err("Product ID required")
    plans = await db_mgr.get_plans(int(prod_id))
    return _success(plans)


async def get_user_profile(request: web.Request) -> web.Response:
    user_id = request.match_info.get("user_id")
    if not user_id:
        return _err("User ID required")
    user = await db_mgr.get_user(int(user_id))
    return _success(user)


async def get_user_keys(request: web.Request) -> web.Response:
    user_id = request.match_info.get("user_id")
    if not user_id:
        return _err("User ID required")
    keys = await db_mgr.get_user_keys(int(user_id), limit=100)
    return _success(keys)


async def login(request: web.Request) -> web.Response:
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
        return _err("App Password must be exactly 16 characters.")

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
    token = _bearer_token(request)
    sess = await _get_session(token)
    
    # Fallback for Web App: use the latest active session if no token provided
    if not sess:
        sess = await asyncio.to_thread(sessions_col.find_one, {}, sort=[("created_at", -1)])
        
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
        return _err("amount must be a number.")

    order_id = (body.get("order_id") or "").strip()
    if not order_id:
        return _err("order_id is required.")

    upi_id = (body.get("upi_id") or sess.get("upi_id") or "").strip()
    if not upi_id or "@" not in upi_id:
        return _err("upi_id is required.")

    payee_name = (body.get("payee_name") or "Hack Store").strip()[:40]

    await asyncio.to_thread(
        sessions_col.update_one,
        {"_id": sess["_id"]},
        {"$set": {"upi_id": upi_id, "payee_name": payee_name}},
    )

    upi_link = _build_upi_link(upi_id, payee_name, amount, order_id)
    png = _render_qr_png(upi_link)
    _qr_cache[order_id] = png

    expires_at = time.time() + QR_TTL_SECONDS
    await asyncio.to_thread(
        orders_col.update_one,
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

    qr_url = f"{PUBLIC_BASE}/qr/{order_id}.png"
    qr_b64 = base64.b64encode(png).decode("ascii")
    return _success({
        "qr_url": qr_url,
        "qr_b64": qr_b64,
        "upi_link": upi_link,
        "amount": amount,
        "order_id": order_id,
    })


async def serve_qr(request: web.Request) -> web.Response:
    order_id = request.match_info.get("order_id", "")
    png = _qr_cache.get(order_id)
    if not png:
        order = orders_col.find_one({"order_id": order_id})
        if not order:
            return web.Response(status=404, text="Not found")
        png = _render_qr_png(order["upi_link"])
        _qr_cache[order_id] = png
    return web.Response(body=png, content_type="image/png",
                        headers={"Cache-Control": "no-store"})


async def verify_payment(request: web.Request) -> web.Response:
    token = _bearer_token(request)
    sess = await _get_session(token)
    
    # Fallback for Web App
    if not sess:
        sess = await asyncio.to_thread(sessions_col.find_one, {}, sort=[("created_at", -1)])
        
    if not sess:
        return _err("Invalid or expired session. Please login again.")

    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body.")

    order_id = (body.get("order_id") or "").strip()
    if not order_id:
        return _err("order_id is required.")

    order = await asyncio.to_thread(orders_col.find_one, {"order_id": order_id, "admin_id": sess["admin_id"]})
    if not order:
        return _err("Order not found.")

    if time.time() > order.get("expires_at", 0) and order.get("status") != "PAID":
        return _err("Order has expired.")

    if order.get("status") == "PAID":
        return _success({
            "utr": order.get("utr", "N/A"),
            "transaction_id": order.get("transaction_id", "N/A"),
            "amount": order.get("amount", 0),
            "verified_at_ist": order.get("verified_at_ist", ""),
        })

    app_password = _dec(sess.get("app_password_enc", ""))
    if not app_password:
        return _err("Stored credentials are unreadable. Please login again.")

    def _collect_utrs():
        u = set()
        for prev in orders_col.find(
            {"admin_id": sess["admin_id"], "status": "PAID"},
            {"utr": 1, "transaction_id": 1, "_id": 0},
        ):
            if prev.get("utr"):
                u.add(str(prev["utr"]).strip())
            if prev.get("transaction_id"):
                u.add(str(prev["transaction_id"]).strip())
        return u

    used_utrs = await asyncio.to_thread(_collect_utrs)

    loop = asyncio.get_running_loop()
    match = await loop.run_in_executor(
        None,
        _imap_find_payment,
        sess["email"],
        app_password,
        order_id,
        float(order["amount"]),
        float(order.get("created_at", time.time() - 600)),
        used_utrs,
    )

    if not match:
        return _err("Payment not yet received.")

    utr = match["utr"]
    txn = match["transaction_id"]
    sender_name = match.get("sender_name", "Unknown")
    verified_at = _now_ist_str()
    payment_time_ist = (match.get("payment_time_ist")
                        or datetime.now(IST_TZ).strftime("%d-%m-%Y %H:%M:%S"))

    try:
        await asyncio.to_thread(
            orders_col.update_one,
            {"_id": order["_id"]},
            {"$set": {
                "status": "PAID",
                "utr": utr,
                "transaction_id": txn,
                "sender_name": sender_name,
                "verified_at": time.time(),
                "verified_at_ist": verified_at,
                "payment_time_ist": payment_time_ist,
                "matched_sender": match.get("sender", ""),
                "matched_subject": match.get("subject", ""),
            }},
        )
    except DuplicateKeyError:
        return _err("This payment reference has already been used.")

    return _success({
        "utr": utr,
        "transaction_id": txn,
        "sender_name": sender_name,
        "amount": float(order["amount"]),
        "verified_at_ist": verified_at,
        "payment_time_ist": payment_time_ist,
    })


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/health", health)
    app.router.add_post("/login", login)
    app.router.add_post("/logout", logout)
    app.router.add_post("/generate_qr", generate_qr)
    app.router.add_post("/verify_payment", verify_payment)
    app.router.add_get("/qr/{order_id}.png", serve_qr)

    # API routes for Web App
    app.router.add_get("/api/products", get_products)
    app.router.add_get("/api/plans/{prod_id}", get_plans)
    app.router.add_get("/api/user/{user_id}", get_user_profile)
    app.router.add_get("/api/user/{user_id}/keys", get_user_keys)

    # Static files
    if os.path.exists("static"):
        app.router.add_static("/static/", "static", name="static")

    return app


def main() -> None:
    log.info("Starting Hack Store Payment Microservice on %s:%d", HOST, PORT)
    web.run_app(make_app(), host=HOST, port=PORT, print=None)


if __name__ == "__main__":
    main()
