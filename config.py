import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

_admin_raw = os.environ.get("ADMIN_IDS", "").strip()
ADMIN_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]

# Both names have been used by deployed versions of the store.  Keep one
# canonical value in the application so the bot and PaymentManager always use
# the same MongoDB database.
MONGO_URI = (os.environ.get("MONGO_URI") or os.environ.get("MONGODB_URI") or "").strip()
MONGO_DB_NAME = (
    os.environ.get("MONGO_DB_NAME")
    or os.environ.get("DB_NAME")
    or "hack_store_enterprise"
).strip()

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
# Search broadly enough to cover the sender aliases used by FamApp/FamPay;
# message content still has to pass the incoming-credit checks.
IMAP_SENDER_FILTER = os.environ.get("IMAP_SENDER_FILTER", "fam").strip()
GMAIL_LOOKBACK_HOURS = int(os.environ.get("GMAIL_LOOKBACK_HOURS", "12") or "12")
ORDER_EXPIRY_MINUTES = int(os.environ.get("ORDER_EXPIRY_MINUTES", "15") or "15")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required.")

if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS environment variable is required.")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is required.")
