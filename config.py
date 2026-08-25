import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

_admin_raw = os.environ.get("ADMIN_IDS", "8127888290,8396509436").strip()
ADMIN_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://bb:bb@cluster0.p68btnn.mongodb.net/?appName=Cluster0").strip()
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "hack_store_enterprise").strip()

# ── Reseller panel API (auto key purchase when manual stock runs out) ──
RESELLER_API_URL = os.environ.get("RESELLER_API_URL", "https://adminpanels.shop/api/reseller_v1.php").strip()
RESELLER_API_KEY = os.environ.get("RESELLER_API_KEY", "6d4e815c8bca8f1590249e1b79180df0").strip()
RESELLER_MASTER_KEY = os.environ.get("RESELLER_MASTER_KEY", "a7f3e8b2c9d1f4a6b8c2d5e9f1a3b6c8").strip()

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is required. "
        "Set it in your .env file or Render dashboard."
    )

if not ADMIN_IDS:
    raise RuntimeError(
        "ADMIN_IDS environment variable is required. "
        "Provide one or more Telegram user IDs as a comma-separated list, "
        "e.g. ADMIN_IDS=123456789,987654321"
    )
