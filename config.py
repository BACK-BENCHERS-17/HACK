import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

_admin_raw = os.environ.get("ADMIN_IDS", "").strip()
ADMIN_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]

MONGO_URI = os.environ.get("MONGO_URI", "").strip()
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "hack_store").strip()

# ── Payment SDK config (read from env, can be overridden via /admin) ──
DEFAULT_UPI_ID = os.environ.get("DEFAULT_UPI_ID", "").strip()
DEFAULT_PAYEE_NAME = os.environ.get("DEFAULT_PAYEE_NAME", "").strip()
PURPOSE_PREFIX = os.environ.get("PURPOSE_PREFIX", "HS").strip().upper()
BRAND_NAME = os.environ.get("BRAND_NAME", "Hack Store").strip()

# ── Gmail IMAP (for PaymentManager SDK email verification) ──
IMAP_USERNAME = os.environ.get("IMAP_USERNAME", "").strip()
IMAP_APP_PASSWORD = os.environ.get("IMAP_APP_PASSWORD", "").strip()
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com").strip() or "imap.gmail.com"
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993") or "993")
IMAP_MAILBOX = os.environ.get("IMAP_MAILBOX", "INBOX").strip() or "INBOX"
IMAP_SENDER_FILTER = os.environ.get("IMAP_SENDER_FILTER", "no-reply@famapp.in").strip()
GMAIL_LOOKBACK_HOURS = int(os.environ.get("GMAIL_LOOKBACK_HOURS", "12") or "12")
ORDER_EXPIRY_MINUTES = int(os.environ.get("ORDER_EXPIRY_MINUTES", "15") or "15")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required.")

if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS environment variable is required.")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is required.")
