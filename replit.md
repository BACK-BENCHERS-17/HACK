# Hack Store Telegram Bot

## Overview
A Telegram bot built with Python 3.12 using `python-telegram-bot` v21.6 and MongoDB (via `pymongo`) for data storage. Originally designed for deployment on Render.com as a worker process; now configured to run on Replit.

## Project Structure
- `bot.py` — Main bot entry point with all handlers and logic
- `database.py` — MongoDB-backed `DatabaseManager` data layer
- `config.py` — Loads `BOT_TOKEN`, `ADMIN_IDS`, `MONGO_URI`, `MONGO_DB_NAME` from environment (with hardcoded fallbacks)
- `requirements.txt` — Python dependencies
- `Procfile`, `render.yaml`, `runtime.txt` — Original Render.com deployment files (kept for reference)

## Runtime
- Python 3.12 (Replit module). The original `runtime.txt` requested 3.11.9, but the project is compatible with 3.12.
- Dependencies: `python-telegram-bot==21.6`, `pymongo==4.10.1`, `dnspython==2.7.0`, `python-dotenv==1.0.1`, `aiohttp`.

## Replit Setup
- **Workflow**: `Telegram Bot` (console output) runs `python bot.py`. The bot uses long-polling against the Telegram API — no listening port required.
- **Deployment**: Configured as a `vm` (Reserved VM) target with `python bot.py` as the run command. This is the appropriate target for an always-on background bot.

## Environment Variables
The following are loaded from environment with fallbacks already hardcoded in `config.py`:
- `BOT_TOKEN` — Telegram bot token
- `ADMIN_IDS` — Comma-separated Telegram admin user IDs
- `MONGO_URI` — MongoDB connection string
- `MONGO_DB_NAME` — MongoDB database name (default: `hack_store_enterprise`)

To override the defaults in production, set these as Replit Secrets before publishing.

## Notes
- The standalone PyPI packages `bson` and `telegram` (v0.0.1) must NOT be installed — they conflict with `pymongo`'s built-in `bson` module and `python-telegram-bot`'s `telegram` package. `requirements.txt` is curated to avoid them.
