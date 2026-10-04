# Hack Store Telegram Bot

## Overview
A Telegram bot built with Python 3.12 using `python-telegram-bot` v21.6 and MongoDB (via `pymongo`) for data storage. Originally designed for deployment on Render.com as a worker process; now configured to run on Replit.

## Project Structure
- `bot.py` — Main bot entry point with all handlers and logic
- `database.py` — MongoDB-backed `DatabaseManager` data layer
- `payment_template/` — In-process UPI QR and FamApp/FamPay Gmail-IMAP verification SDK.
- `config.py` — Loads `BOT_TOKEN`, `ADMIN_IDS`, `MONGO_URI`, `MONGO_DB_NAME` from environment (with hardcoded fallbacks)
- `start.sh` — Production launcher for `bot.py`; payment verification runs in-process.
- `requirements.txt` — Python dependencies
- `render.yaml` — Render Web Service configuration, with `/healthz` on `PORT`.
- `Procfile`, `runtime.txt` — Worker launch and Python runtime defaults.

## Runtime
- Python 3.12 (Replit module). The original `runtime.txt` requested 3.11.9, but the project is compatible with 3.12.
- Dependencies: `python-telegram-bot==21.6`, `pymongo==4.10.1`, `dnspython==2.7.0`, `python-dotenv==1.0.1`, `aiohttp`, `cryptography`, `qrcode[pil]`.

## Replit Setup
- **Workflow**: `Telegram Bot` (console) — runs `python bot.py`. Uses long-polling against the Telegram API; no listening port is required.
- **Deployment**: Configured as a `vm` (Reserved VM) target launching `bash start.sh`.
- If `PORT` is supplied, the bot also serves `/healthz` and `/readyz`. Updated
  instances sharing the same Mongo database use a `bot_runtime` lease to keep
  only one Telegram poller active. See `README.md` for Render deployment details.

## PaymentManager SDK (`payment_template/`)
The bot uses a self-hosted, **real** Gmail-IMAP-backed UPI payment manager. No fake/mock — every verification talks to Google and records the order/log in MongoDB.

- The bot calls `PaymentManager.create(...)` to build an in-memory UPI QR and store an `orders` document, then stores the matching `fund_requests` document in the same database.
- `PaymentManager.verify(order_id)` scans Gmail IMAP off the Telegram event loop, accepts incoming FamApp/FamPay credit alerts matching the purpose and amount, extracts UTR/transaction details, and stores a `verification_logs` document.
- Both SDK orders and bot fund requests use the same MongoDB URI/database aliases (`MONGO_URI`/`MONGODB_URI` and `MONGO_DB_NAME`/`DB_NAME`).

### UTR replay protection (anti-fraud)

Old UTRs cannot be reused to claim free keys. The defence has four layers:

1. **Email-date check** — a message must not predate the order and fallback amount-only matching is limited to ten minutes after order creation.
2. **Unique verification logs** — one Gmail message ID can be used only once.
3. **Bot-side reference check** — UTRs and transaction IDs already attached to another `fund_requests` document are rejected.
4. **Conditional fulfillment claim** — only a PENDING request can move to PROCESSING, so repeated callbacks cannot issue another key or wallet credit.

### Admin payment notification

On a successful key delivery the bot sends every admin the order, amount, UTR, transaction ID, sender, payment time, delivered key, and expiry. A separate message is shown when payment is received but stock is unavailable.

## Environment Variables
The following are loaded from environment with fallbacks already hardcoded in `config.py`:
- `BOT_TOKEN` — Telegram bot token
- `ADMIN_IDS` — Comma-separated Telegram admin user IDs
- `MONGO_URI` or `MONGODB_URI` — MongoDB connection string
- `MONGO_DB_NAME` or `DB_NAME` — MongoDB database name (default: `hack_store_enterprise`)
- `DEFAULT_UPI_ID` / `DEFAULT_PAYEE_NAME` — environment defaults; the admin UPI setting in MongoDB is used for generated orders.
- `IMAP_USERNAME` / `IMAP_APP_PASSWORD` — Gmail account and Google app password used for FamApp/FamPay credit alerts.
- `IMAP_SENDER_FILTER` — IMAP sender search text (default: `fam`).

To override the defaults in production, set these as Replit Secrets before publishing.

## Products & Plans (manual only)
- Plans are **manual mode only**: keys are delivered from the local `keys` stock added by the admin (**/admin → Products → Add Keys**). There is no auto-buy / reseller panel API anymore.
- If a plan runs out of stock, users simply see "Out of stock" until the admin adds more keys.

## Notes
- The standalone PyPI packages `bson` and `telegram` (v0.0.1) must NOT be installed — they conflict with `pymongo`'s built-in `bson` module and `python-telegram-bot`'s `telegram` package. `requirements.txt` is curated to avoid them.
