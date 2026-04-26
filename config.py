import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8652333340:AAFvRnoKxfk4ICAqz3ga1SkkOoJvebniprM").strip()

_admin_raw = os.environ.get("ADMIN_IDS", "8127888290,8396509436").strip()
ADMIN_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://bb:bb@cluster0.p68btnn.mongodb.net/?appName=Cluster0").strip()
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "hack_store_enterprise").strip()

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
