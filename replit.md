# Hack Store Telegram Bot - Mega Enterprise Ultimate Edition

## Overview
A fully-featured Telegram bot that serves as an automated digital storefront for selling digital products (keys, accounts, etc.).

## Tech Stack
- **Language:** Python 3.12
- **Library:** python-telegram-bot (v20+)
- **Database:** SQLite 3 (local file: `hack_store_enterprise.db`)
- **Async:** asyncio

## Project Structure
```
bot.py                    # Main bot script (all logic in one file)
hack_store_enterprise.db  # SQLite database (auto-created on first run)
bot_enterprise.log        # Log file (auto-created on first run)
```

## Running the Bot
```bash
python bot.py
```

## Key Features
- Admin panel for managing products, plans, keys, users, funds, tickets, and settings
- Phone number verification on start
- 15% auto-commission referral system
- Promo code system
- Digital key inventory
- Manual fund requests via UTR (Unique Transaction Reference)
- Ticket-based support system
- Top VIP users leaderboard

## Configuration
Bot token and admin IDs are hardcoded in `bot.py` at the top of the file under the "CORE CONFIGURATION" section.

## Deployment
- **Type:** VM (always running)
- **Run command:** `python bot.py`
