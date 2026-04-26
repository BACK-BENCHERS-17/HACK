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

### UTR replay protection (anti-fraud)

Old UTRs cannot be reused to claim free keys. The defence has four layers:

1. **Email-date check** — `_imap_find_payment` rejects any email whose `Date:` header is older than `order.created_at - 120s`. An old payment email therefore cannot satisfy a fresh order.
2. **Used-UTR blocklist (in-memory)** — before scanning, `verify_payment` builds a `set` of every UTR / transaction-id already attached to that admin's other `PAID` orders and passes it to the IMAP scanner; matching emails whose UTR is in the set are skipped.
3. **Unique sparse Mongo indexes** — both `payment_orders.utr` and `payment_orders.transaction_id` (in the payment service DB) and `fund_requests.utr` / `fund_requests.order_id` (in the bot DB) are `unique=True, sparse=True`. A duplicate UTR write raises `DuplicateKeyError` and the user receives a clear "already used" message.
4. **Bot-side recheck** — after the service confirms a payment, `bot.py` calls `db.is_utr_already_used(utr, except_order_id=…)` against its own `fund_requests` collection. On a hit, no key is delivered and a `🚨 UTR REPLAY BLOCKED` alert is sent to all admins with full user / order / UTR details.

### Admin payment notification

On a successful key delivery the bot sends every admin a detailed message with: user id + first name + @username, order id, amount, product + duration, UTR, transaction id, sender name, payee UPI id, payment time (IST), delivered key value, and key expiry. A separate alert is fired when payment was received but key delivery failed (out of stock).
- **`GET /qr/<order_id>.png`** — serves the rendered QR image (in-memory cache + DB fallback).
- **Encryption**: App passwords are encrypted with Fernet using a key derived from `BOT_TOKEN` (or override with `PAY_SVC_FERNET_KEY`).
- **Public base URL auto-detection** — `PUBLIC_BASE` is picked automatically (in this priority order):
  1. `PAY_SVC_PUBLIC_BASE` (manual override)
  2. `RENDER_EXTERNAL_URL` (Render hosting)
  3. `https://$RAILWAY_PUBLIC_DOMAIN` (Railway)
  4. `https://$FLY_APP_NAME.fly.dev` (Fly.io)
  5. `https://$REPLIT_DEV_DOMAIN` (Replit dev preview)
  6. `https://$REPL_SLUG.$REPL_OWNER.repl.co` (legacy Replit)
  7. `http://localhost:<PORT>` (last-resort fallback)

  The bot bypasses URL dependence entirely by sending QR PNG bytes directly to Telegram (the microservice returns base64-encoded image data alongside the URL).
- **Optional env**: `PAY_SVC_HOST`, `PAY_SVC_PORT`, `PAY_SVC_PUBLIC_BASE`, `PAY_SVC_FERNET_KEY`.

## Environment Variables
The following are loaded from environment with fallbacks already hardcoded in `config.py`:
- `BOT_TOKEN` — Telegram bot token
- `ADMIN_IDS` — Comma-separated Telegram admin user IDs
- `MONGO_URI` — MongoDB connection string
- `MONGO_DB_NAME` — MongoDB database name (default: `hack_store_enterprise`)

To override the defaults in production, set these as Replit Secrets before publishing.

## Notes
- The standalone PyPI packages `bson` and `telegram` (v0.0.1) must NOT be installed — they conflict with `pymongo`'s built-in `bson` module and `python-telegram-bot`'s `telegram` package. `requirements.txt` is curated to avoid them.
