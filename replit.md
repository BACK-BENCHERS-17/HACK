# Hack Store Telegram Bot - Mega Enterprise Ultimate Edition

## Overview
A fully-featured Telegram bot that serves as an automated digital storefront for selling digital products (keys, accounts, etc.).

## Tech Stack
- **Language:** Python 3.12
- **Library:** python-telegram-bot (v22+)
- **Database:** SQLite 3 (local file: `hack_store_enterprise.db`)
- **Keep-alive:** Built-in HTTP server (for Render hosting)

## Project Structure
```
bot.py                    # Main bot script (all logic in one file)
requirements.txt          # Python dependencies
render.yaml               # Render hosting configuration
hack_store_enterprise.db  # SQLite database (auto-created on first run)
bot_enterprise.log        # Log file (auto-created on first run)
```

## Running the Bot
```bash
python bot.py
```

## Key Features
- **3 Separate QR Scanners** for ₹79, ₹189, ₹349 plans (set via Admin Settings)
- **Screenshot-based payments** — user pays and sends payment screenshot → forwarded to admin for approval
- **Stock menu with direct buy buttons** — click any available plan to buy instantly
- Admin panel for managing products, plans, keys, users, funds, tickets, and settings
- Phone number verification on start
- 15% auto-commission referral system
- Promo code system
- Digital key inventory
- Ticket-based support system
- Top VIP users leaderboard
- Keep-alive HTTP server on port 8080 (for Render.com)

## Payment Flow
1. User clicks "Add Funds"
2. Selects amount: ₹79, ₹189, or ₹349
3. Bot shows respective QR code scanner
4. User pays via UPI and clicks "Send Payment Screenshot"
5. User sends screenshot as a photo
6. Screenshot is forwarded to all admins with amount info
7. Admin clicks "Review Now" → sees screenshot → clicks Approve with pre-filled amount

## Admin Settings
- **QR ₹79** — Set the QR scanner image for ₹79 payments
- **QR ₹189** — Set the QR scanner image for ₹189 payments
- **QR ₹349** — Set the QR scanner image for ₹349 payments
- UPI ID, Support User, Download Channel, etc.

## Render Hosting
- Uses `render.yaml` for service configuration
- Keep-alive HTTP server runs on `PORT` env var (default 8080)
- Service type: `web` (prevents Render from sleeping)
- Build command: `pip install -r requirements.txt`
- Start command: `python bot.py`

## Configuration
Bot token and admin IDs are hardcoded in `bot.py` at the top of the file under the "CORE CONFIGURATION" section.
