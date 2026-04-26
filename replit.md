# Hack Store Telegram Bot

## Overview
A Telegram bot built with Python 3.12 using `python-telegram-bot` v21.6 and MongoDB (via `pymongo`) for data storage. Originally designed for deployment on Render.com as a worker process; now configured to run on Replit.

## Project Structure
- `bot.py` — Main bot entry point with all handlers and logic
- `database.py` — MongoDB-backed `DatabaseManager` data layer
- `payment_service.py` — Self-hosted UPI payment microservice (aiohttp on `localhost:8000`). Validates Gmail App Passwords via real IMAP login, generates real UPI deep-link QR codes, and verifies payments by scanning the admin's Gmail inbox for UPI/bank credit notifications.
- `config.py` — Loads `BOT_TOKEN`, `ADMIN_IDS`, `MONGO_URI`, `MONGO_DB_NAME` from environment (with hardcoded fallbacks)
- `start.sh` — Production launcher that runs both `payment_service.py` and `bot.py` together
- `requirements.txt` — Python dependencies
- `Procfile`, `render.yaml`, `runtime.txt` — Original Render.com deployment files (kept for reference)

## Runtime
- Python 3.12 (Replit module). The original `runtime.txt` requested 3.11.9, but the project is compatible with 3.12.
- Dependencies: `python-telegram-bot==21.6`, `pymongo==4.10.1`, `dnspython==2.7.0`, `python-dotenv==1.0.1`, `aiohttp`, `cryptography`, `qrcode[pil]`.

## Replit Setup
- **Workflows**:
  - `Telegram Bot` (console) — runs `python bot.py`. Uses long-polling against the Telegram API; no listening port required.
  - `Payment Service` (console, port 8000) — runs `python payment_service.py`. Listens on `localhost:8000` for `/login`, `/generate_qr`, `/verify_payment`, `/health`, and serves QR PNGs at `/qr/<order_id>.png`.
- **Deployment**: Configured as a `vm` (Reserved VM) target launching `bash start.sh`, which spawns the payment service and the bot together.

## Payment Microservice (`payment_service.py`)
A self-hosted, **real** Gmail-IMAP-backed UPI payment service. No fake/mock — every step actually talks to Google.

- **`POST /login`** — body `{admin_id, mobile, email, otp}` (the `otp` field carries the 16-character Gmail App Password). The service performs a real IMAP login against `imap.gmail.com:993` to validate credentials. On success, returns a real `session_token` and stores the session (with the password Fernet-encrypted) in the `payment_sessions` MongoDB collection.
- **`POST /generate_qr`** — body `{admin_id, amount, order_id, upi_id, payee_name?}`, header `Authorization: Bearer <session_token>`. Builds a standard UPI deep link (`upi://pay?...`) and renders a real PNG QR code. Returns `qr_url` pointing to `/qr/<order_id>.png` plus `expires_at_ist`. Order is stored in `payment_orders`.
- **`POST /verify_payment`** — body `{admin_id, order_id}`, header `Authorization: Bearer <session_token>`. Connects to the admin's Gmail inbox via IMAP, scans recent messages from known UPI/bank senders (FamPay, HDFC, Axis, ICICI, SBI, Kotak, Yes, PhonePe, Paytm, Razorpay, Cashfree, Google Pay…) and looks for a "credited"/"received" notification matching either the order id or the amount. On match it extracts UTR/Txn ID and marks the order `PAID`.
- **`GET /qr/<order_id>.png`** — serves the rendered QR image (in-memory cache + DB fallback).
- **Encryption**: App passwords are encrypted with Fernet using a key derived from `BOT_TOKEN` (or override with `PAY_SVC_FERNET_KEY`).
- **Optional env**: `PAY_SVC_HOST`, `PAY_SVC_PORT`, `PAY_SVC_PUBLIC_BASE` (used in QR image URLs — set this to your public domain when deployed so QR images can be embedded by Telegram), `PAY_SVC_FERNET_KEY`.

## Environment Variables
The following are loaded from environment with fallbacks already hardcoded in `config.py`:
- `BOT_TOKEN` — Telegram bot token
- `ADMIN_IDS` — Comma-separated Telegram admin user IDs
- `MONGO_URI` — MongoDB connection string
- `MONGO_DB_NAME` — MongoDB database name (default: `hack_store_enterprise`)

To override the defaults in production, set these as Replit Secrets before publishing.

## Notes
- The standalone PyPI packages `bson` and `telegram` (v0.0.1) must NOT be installed — they conflict with `pymongo`'s built-in `bson` module and `python-telegram-bot`'s `telegram` package. `requirements.txt` is curated to avoid them.
