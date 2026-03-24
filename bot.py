#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
====================================================================================================
🔥 HACK STORE TELEGRAM BOT - MEGA ENTERPRISE ULTIMATE EDITION (FIXED) 🔥
====================================================================================================
Features Included:
- Premium Custom Emoji Support via HTML ParseMode for all text messages.
- Advanced Inline Keyboard UI with Colored Button Indicators.
- Dynamic User Profile Menu fetching Real Telegram PFP (Profile Photo).
- Massive Admin Panel: Product, Plan, Key, User, Fund, Ticket, Settings.
- 15% Auto-Commission Referral System with Referral Stats & Share Button.
- Phone Number Verification on Start & Admin Alert System.
- Promo Code System (Create limited use promo codes for wallet rewards).
- Top VIP Users Leaderboard & Database Export.
- Massive, highly detailed pre-set product descriptions.
- [FIXED] "Baar-baar Verification" bug completely resolved.
- [NEW] "8 Level ID" Preset Product Description added.
-[NEW] Welcome Message Features made Bold & Highly Attractive (No monospace).
- [UPDATE] Global Single Download Link system with preview disabled, editable from Admin Settings.
====================================================================================================
"""

import asyncio
import logging
import sqlite3
import math
import threading
import warnings
import os
import traceback
import re
from urllib.parse import quote
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InputFile,
    LinkPreviewOptions
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)
from telegram.error import BadRequest, TelegramError

# ==============================================================================
# 0. SYSTEM INITIALIZATION & WARNING SUPPRESSION
# ==============================================================================
warnings.filterwarnings("ignore", category=UserWarning, module="telegram.ext.ConversationHandler")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_enterprise.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================================================
# 1. CORE CONFIGURATION & CUSTOM EMOJIS MAP
# ==============================================================================

BOT_TOKEN = "8010962908:AAGfNbBtK-p68QLCi_uuU9ozPk44Co5Qnoo"
ADMIN_IDS =[8127888290, 6197483321, 8386712809]

EMOJIS = {
    "store": ("🏪", "5920332557466997677"),
    "money": ("💰", "6089104607328342288"),
    "key": ("🔓", "5465443379917629504"),
    "stock": ("📦", "5884479287171485878"),
    "contact": ("📞", "6093587384954262033"),
    "admin": ("👑", "6195222374355311655"),
    "success": ("✅", "5316827280863934685"),
    "fail": ("❌", "4958526153955476488"),
    "warning": ("⚠️", "5447644880824181073"),
    "star": ("⭐️", "4994896443824145756"),
    "user": ("👤", "5316992572680320646"),
    "name_icon": ("👤", "5884366771913233289"),
    "link": ("🔗", "5316612764427367709"),
    "line": ("〰️", "5370897861103854382"),
    "cart": ("🛒", "5226656353744862682"),
    "rocket": ("🚀", "5316571734604790521"),
    "globe": ("🌐", "4956560549287560231"),
    "ticket": ("🎫", "5418010521309815154"),
    "sparkle": ("✨", "5325547803936572038"),
    "game": ("🎮", "5316728625465146646"),
    "card": ("💳", "6122745612984127728"),
    "time": ("⌛️", "5454415424319931791"),
    "search": ("🔍", "4958587679361991667"),
    "stats": ("📊", "4958506272551863292"),
    "bag": ("🛍", "5456343263340405032"),
    "settings": ("⚙️", "5316832430529722441"),
    "edit": ("✍️", "5197269100878907942"),
    "broadcast": ("📣", "4981464925743351837"),
    "bell": ("🔔", "6093852083788715042"),
    "gift": ("🎁", "6158727972816687974"),
    "trophy": ("🏆", "6124897773851513665"),
    "books": ("📚", "5373098009640836781"),
    "promo": ("🎟", "5377599075237502153"),
    "mobile": ("📱", "5260377786958227390"),
    "disk": ("📀", "5462956611033117422"),
    "tools": ("🛠", "5462921117423384478"),
    "angry": ("😡", "5240408207666455054"),
    "memo": ("📝", "5346077597287589711"),
    "pencil": ("✏️", "5395444784611480792"),
    "poop": ("💩", "6307831155521494118"),
    "dove": ("🕊️", "5316740183222140641"),
    "gold1": ("🥇", "5440539497383087970"),
    "gold2": ("🥇", "6195196054795721892"),
    "silver": ("🥈", "6192572461138057389"),
    "bronze": ("🥉", "6192885190591780669"),
    "medal": ("🏅", "5334644364280866007"),
    "shield": ("🛡", "5895483165182529286"),
    "fire": ("🔥", "6086954744268460848"),
    "apple": ("🍏", "5775870512127283512"),
    "siren": ("🚨", "5395695537687123235"),
    "loop": ("🔁", "6030657343744644592"),
    "back": ("🔙", "5253997076169115797"),
    "left": ("◀️", "5440509136259267820"),
    "right": ("➡️", "4956282853882069908"),
    "plus": ("➕", "4956507094124594921"),
    "refresh": ("🔄", "5769248574499983619"),
    "chat": ("💬", "6095865895169560113"),
    "outbox": ("📤", "6039573425268201570"),
    "down": ("👇", "6174939726307399019"),
    "1": ("1️⃣", "5316544002000958685"),
    "2": ("2️⃣", "5316673387890751150"),
    "3": ("3️⃣", "5316702039617583319"),
    "4": ("4️⃣", "5316540608976798560"),
}

def ce(name: str) -> str:
    """Returns HTML tag for premium custom emoji (for message text)."""
    if name in EMOJIS:
        fallback, em_id = EMOJIS[name]
        return f'<tg-emoji emoji-id="{em_id}">{fallback}</tg-emoji>'
    return "🔹"

def ce_button(name: str) -> str:
    """Returns fallback emoji character for buttons (standard emoji only)."""
    if name in EMOJIS:
        return EMOJIS[name][0]
    return "🔹"

def get_line(n=12):
    return ce('line') * n

# ------------------------------------------------------------------------------
# CONVERSATION STATES
# ------------------------------------------------------------------------------
(
    WAIT_FOR_BROADCAST, WAIT_FOR_UTR, WAIT_FOR_TICKET, WAIT_FOR_ADMIN_TICKET_REPLY,
    WAIT_FOR_NEW_PROD_NAME, WAIT_FOR_NEW_PROD_DESC, WAIT_FOR_CUSTOM_DESC, WAIT_FOR_PLAN_DUR, 
    WAIT_FOR_PLAN_PRICE, WAIT_FOR_ADD_KEYS, WAIT_FOR_SETTING_UPI, WAIT_FOR_SETTING_QR, 
    WAIT_FOR_SETTING_SUP, WAIT_FOR_BAN_USER, WAIT_FOR_UNBAN_USER, WAIT_FOR_SETTING_MSG, 
    WAIT_FOR_MANUAL_BAL_USER, WAIT_FOR_MANUAL_BAL_AMT, WAIT_FOR_PROMO_CODE, WAIT_FOR_PROMO_REWARD,
    WAIT_FOR_PROMO_USES, WAIT_FOR_USER_PROMO, WAIT_FOR_FAQ, WAIT_FOR_TOS, WAIT_FOR_EDIT_PROD_DESC,
    WAIT_FOR_PROD_LINK, WAIT_FOR_HOW_TO_TEXT, WAIT_FOR_HOW_TO_VIDEO,
    WAIT_FOR_SCREENSHOT, WAIT_FOR_QR_79, WAIT_FOR_QR_189, WAIT_FOR_QR_349
) = range(32)

# ==============================================================================
# 2. DATABASE MANAGER
# ==============================================================================

DB_FILE = "hack_store_enterprise.db"

class DatabaseManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.lock = threading.Lock()
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_file, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("""CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance INTEGER DEFAULT 0,
                joined_date TEXT,
                is_banned INTEGER DEFAULT 0,
                verified INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                referrer_id INTEGER DEFAULT NULL,
                total_referrals INTEGER DEFAULT 0,
                referral_earnings INTEGER DEFAULT 0,
                last_active TEXT
            )""")
            
            c.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in c.fetchall()]
            if 'verified' not in columns:
                c.execute("ALTER TABLE users ADD COLUMN verified INTEGER DEFAULT 0")
            if 'referrer_id' not in columns:
                c.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT NULL")
            if 'total_referrals' not in columns:
                c.execute("ALTER TABLE users ADD COLUMN total_referrals INTEGER DEFAULT 0")
            if 'referral_earnings' not in columns:
                c.execute("ALTER TABLE users ADD COLUMN referral_earnings INTEGER DEFAULT 0")
            if 'last_active' not in columns:
                c.execute("ALTER TABLE users ADD COLUMN last_active TEXT DEFAULT NULL")
            
            c.execute("""CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, description TEXT, is_active INTEGER DEFAULT 1, image_url TEXT DEFAULT NULL, download_link TEXT DEFAULT 'Link not set'
            )""")
            
            c.execute("PRAGMA table_info(products)")
            p_cols =[column[1] for column in c.fetchall()]
            if 'download_link' not in p_cols:
                c.execute("ALTER TABLE products ADD COLUMN download_link TEXT DEFAULT 'Link not set'")
            
            c.execute("""CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, duration TEXT, price INTEGER, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER, key_value TEXT UNIQUE, is_sold INTEGER DEFAULT 0, sold_to INTEGER, purchase_date TEXT, expiry_date TEXT, FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE, FOREIGN KEY(sold_to) REFERENCES users(user_id)
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id INTEGER, key_id INTEGER, amount INTEGER, purchase_date TEXT
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS fund_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount_requested INTEGER DEFAULT 0, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', request_date TEXT, resolved_date TEXT, photo_file_id TEXT, amount_selected INTEGER DEFAULT 0, FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            c.execute("PRAGMA table_info(fund_requests)")
            fr_cols = [col[1] for col in c.fetchall()]
            if 'photo_file_id' not in fr_cols:
                c.execute("ALTER TABLE fund_requests ADD COLUMN photo_file_id TEXT")
            if 'amount_selected' not in fr_cols:
                c.execute("ALTER TABLE fund_requests ADD COLUMN amount_selected INTEGER DEFAULT 0")
            c.execute("""CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, message TEXT, reply TEXT, status TEXT DEFAULT 'OPEN', created_at TEXT, resolved_at TEXT
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target TEXT, timestamp TEXT
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY, reward_paise INTEGER, max_uses INTEGER, current_uses INTEGER DEFAULT 0, created_at TEXT
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS redeemed_promos (
                user_id INTEGER, code TEXT, redeemed_at TEXT, PRIMARY KEY(user_id, code)
            )""")
            
            conn.commit()
            conn.close()
        
        self._seed_default_settings()

    def _seed_default_settings(self):
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            defaults = {
                'qr_image': None,
                'qr_79': None,
                'qr_189': None,
                'qr_349': None,
                'upi_id': 'admin@upi',
                'support_user': '@VIPxMODRETOX',
                'unauth_msg': f"<blockquote><b>{ce('angry')} Aukaat mein reh! {ce('fail')}</b></blockquote>\n\n<i>Jhaat bhar ka aadmi, ye command use karne ki koshish kaise kar raha hai?</i>\n\n<b>Chup chap normal menu use kar, tera baap baithe hain yaha control karne!</b> {ce('admin')}",
                'default_pfp': 'https://via.placeholder.com/300x300.png?text=NO+PROFILE+PIC',
                'maintenance_mode': '0',
                'global_channel_link': 'https://t.me/YourDownloadChannel',
                'faq_text': 'No FAQ set yet. Admin will update this soon.',
                'tos_text': 'No Terms of Service set yet. Admin will update this soon.',
                'how_to_text': f"<blockquote><b>{ce('books')} HOW TO USE BOT</b></blockquote>\n\n<i>Learn how to purchase, download, and use our premium tools.</i>",
                'how_to_video': 'https://t.me/YOUR_VIDEO_LINK_HERE'
            }
            for k, v in defaults.items():
                c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
            conn.commit()
            conn.close()

    def log_admin_action(self, admin_id: int, action: str, target: str):
        with self.lock:
            try:
                conn = self.get_connection()
                conn.execute("INSERT INTO admin_logs (admin_id, action, target, timestamp) VALUES (?, ?, ?, ?)", (admin_id, action, target, datetime.now().isoformat()))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Error logging admin action: {e}")

    def add_user(self, user_id: int, username: str, first_name: str, referrer_id: int = None) -> bool:
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            is_new = False
            if not user:
                c.execute("INSERT INTO users (user_id, username, first_name, joined_date, verified, referrer_id, last_active) VALUES (?, ?, ?, ?, 0, ?, ?)", 
                          (user_id, username, first_name, datetime.now().isoformat(), referrer_id, datetime.now().isoformat()))
                if referrer_id:
                    c.execute("UPDATE users SET total_referrals = total_referrals + 1 WHERE user_id=?", (referrer_id,))
                is_new = True
            else:
                c.execute("UPDATE users SET username=?, first_name=?, last_active=? WHERE user_id=?", (username, first_name, datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
            return is_new

    def get_user(self, user_id: int) -> dict:
        try:
            conn = self.get_connection()
            user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            conn.close()
            return dict(user) if user else {}
        except Exception as e:
            logger.error(f"DB Error getting user: {e}")
            return {}

    def update_balance(self, user_id: int, amount: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
            conn.commit()
            conn.close()

    def ban_user(self, user_id: int, state: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (state, user_id))
            conn.commit()
            conn.close()

    def verify_user(self, user_id: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute("UPDATE users SET verified=1 WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()

    def get_all_users_count(self):
        conn = self.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM users WHERE verified=1").fetchone()[0]
        conn.close()
        return count

    # Promo methods
    def create_promo(self, code: str, reward_paise: int, max_uses: int) -> bool:
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            existing = c.execute("SELECT code FROM promo_codes WHERE code=?", (code,)).fetchone()
            if existing:
                conn.close()
                return False
            c.execute("INSERT INTO promo_codes (code, reward_paise, max_uses, created_at) VALUES (?, ?, ?, ?)",
                      (code, reward_paise, max_uses, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True

    def redeem_promo(self, user_id: int, code: str) -> Tuple[bool, str, int]:
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            promo = c.execute("SELECT * FROM promo_codes WHERE code=?", (code,)).fetchone()
            if not promo:
                conn.close()
                return False, "Invalid Promo Code.", 0
            if promo['current_uses'] >= promo['max_uses']:
                conn.close()
                return False, "Promo Code has reached its maximum uses.", 0
            redeemed = c.execute("SELECT * FROM redeemed_promos WHERE user_id=? AND code=?", (user_id, code)).fetchone()
            if redeemed:
                conn.close()
                return False, "You have already redeemed this code.", 0
            reward = promo['reward_paise']
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id))
            c.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code=?", (code,))
            c.execute("INSERT INTO redeemed_promos (user_id, code, redeemed_at) VALUES (?, ?, ?)", (user_id, code, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True, "Success", reward

    def get_all_promos(self) -> List[dict]:
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM promo_codes ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in res]

    def delete_promo(self, code: str):
        with self.lock:
            conn = self.get_connection()
            conn.execute("DELETE FROM promo_codes WHERE code=?", (code,))
            conn.execute("DELETE FROM redeemed_promos WHERE code=?", (code,))
            conn.commit()
            conn.close()

    def get_unsold_keys_for_plan(self, plan_id: int, limit: int = 10, offset: int = 0) -> List[dict]:
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM keys WHERE plan_id=? AND is_sold=0 ORDER BY id ASC LIMIT ? OFFSET ?", (plan_id, limit, offset)).fetchall()
        conn.close()
        return [dict(r) for r in res]

    def get_unsold_keys_count_for_plan(self, plan_id: int) -> int:
        conn = self.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM keys WHERE plan_id=? AND is_sold=0", (plan_id,)).fetchone()[0]
        conn.close()
        return count

    def delete_unsold_keys_for_plan(self, plan_id: int) -> int:
        with self.lock:
            conn = self.get_connection()
            count = conn.execute("SELECT COUNT(*) FROM keys WHERE plan_id=? AND is_sold=0", (plan_id,)).fetchone()[0]
            conn.execute("DELETE FROM keys WHERE plan_id=? AND is_sold=0", (plan_id,))
            conn.commit()
            conn.close()
            return count

    def delete_single_key(self, key_id: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute("DELETE FROM keys WHERE id=? AND is_sold=0", (key_id,))
            conn.commit()
            conn.close()

    def get_all_users_list(self, offset: int = 0, limit: int = 8) -> List[dict]:
        conn = self.get_connection()
        res = conn.execute("SELECT user_id, first_name, username, balance, is_banned, total_spent, joined_date FROM users WHERE verified=1 ORDER BY joined_date DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        conn.close()
        return [dict(r) for r in res]

    def get_all_users_total(self) -> int:
        conn = self.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM users WHERE verified=1").fetchone()[0]
        conn.close()
        return count

    def get_leaderboard(self) -> List[dict]:
        conn = self.get_connection()
        res = conn.execute("SELECT first_name, total_spent FROM users WHERE verified=1 AND total_spent > 0 ORDER BY total_spent DESC LIMIT 10").fetchall()
        conn.close()
        return [dict(r) for r in res]

    # Product methods
    def get_active_products(self):
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM products WHERE is_active=1 ORDER BY name").fetchall()
        conn.close()
        return[dict(r) for r in res]
    
    def get_all_products(self):
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM products ORDER BY name").fetchall()
        conn.close()
        return [dict(r) for r in res]

    def get_product(self, prod_id: int):
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM products WHERE id=?", (prod_id,)).fetchone()
        conn.close()
        return dict(res) if res else {}

    def add_product(self, name: str, desc: str):
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO products (name, description) VALUES (?, ?)", (name, desc))
            last_id = c.lastrowid
            conn.commit()
            conn.close()
            return last_id

    def toggle_product(self, prod_id: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute("UPDATE products SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?", (prod_id,))
            conn.commit()
            conn.close()

    def delete_product(self, prod_id: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM products WHERE id=?", (prod_id,))
            conn.commit()
            conn.close()

    def update_product_description(self, prod_id: int, new_desc: str):
        with self.lock:
            conn = self.get_connection()
            conn.execute("UPDATE products SET description=? WHERE id=?", (new_desc, prod_id))
            conn.commit()
            conn.close()

    # Plan methods
    def get_plans(self, prod_id: int):
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM plans WHERE product_id=? ORDER BY price ASC", (prod_id,)).fetchall()
        conn.close()
        return[dict(r) for r in res]

    def get_plan(self, plan_id: int):
        conn = self.get_connection()
        res = conn.execute("SELECT p.*, pr.name as product_name FROM plans p JOIN products pr ON p.product_id = pr.id WHERE p.id=?", (plan_id,)).fetchone()
        conn.close()
        return dict(res) if res else {}

    def add_plan(self, prod_id: int, duration: str, price: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute("INSERT INTO plans (product_id, duration, price) VALUES (?, ?, ?)", (prod_id, duration, price))
            conn.commit()
            conn.close()

    def delete_plan(self, plan_id: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute("DELETE FROM plans WHERE id=?", (plan_id,))
            conn.commit()
            conn.close()

    # Key methods
    def add_keys(self, plan_id: int, keys: List[str]):
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            count = 0
            for k in keys:
                try:
                    c.execute("INSERT INTO keys (plan_id, key_value) VALUES (?, ?)", (plan_id, k))
                    count += 1
                except sqlite3.IntegrityError:
                    pass
            conn.commit()
            conn.close()
            return count

    def get_stock_summary(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT pr.name, pl.duration, COUNT(k.id) as count
            FROM products pr LEFT JOIN plans pl ON pr.id = pl.product_id LEFT JOIN keys k ON pl.id = k.plan_id AND k.is_sold = 0
            WHERE pr.is_active=1 GROUP BY pr.id, pl.id ORDER BY pr.name ASC, pl.price ASC
        """)
        summary = {}
        for row in c.fetchall():
            p_name = row['name']
            if p_name not in summary:
                summary[p_name] = []
            if row['duration']:
                summary[p_name].append({"duration": row['duration'], "count": row['count']})
        conn.close()
        return summary

    def purchase_key(self, user_id: int, plan_id: int) -> Tuple[bool, str, dict, int, int]:
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            
            user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not user:
                conn.close()
                return False, "User not found.", {}, 0, 0
            
            user_dict = dict(user)
            if user_dict.get('is_banned', 0):
                conn.close()
                return False, "You are banned.", {}, 0, 0
            
            plan = c.execute("SELECT p.*, pr.name as product_name FROM plans p JOIN products pr ON p.product_id = pr.id WHERE p.id=?", (plan_id,)).fetchone()
            if not plan:
                conn.close()
                return False, "Plan not found.", {}, 0, 0
            plan_dict = dict(plan)
            
            price = plan_dict['price']
            if user_dict['balance'] < price:
                conn.close()
                return False, f"Insufficient balance. Need ₹{price/100:.2f}", {}, 0, 0

            key_row = c.execute("SELECT id, key_value FROM keys WHERE plan_id=? AND is_sold=0 LIMIT 1", (plan_id,)).fetchone()
            if not key_row:
                conn.close()
                return False, "Out of stock for this plan.", {}, 0, 0
            key_dict = dict(key_row)

            days = 30
            try:
                days = int(''.join(filter(str.isdigit, plan_dict['duration'])))
            except: pass
            
            expiry_date = (datetime.now() + timedelta(days=days)).isoformat()
            purchase_date = datetime.now().isoformat()

            referrer_id = user_dict.get('referrer_id')
            commission = 0
            
            try:
                c.execute("UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE user_id=?", (price, price, user_id))
                
                if referrer_id:
                    commission = int(price * 0.15)
                    c.execute("UPDATE users SET balance = balance + ?, referral_earnings = referral_earnings + ? WHERE user_id=?", 
                              (commission, commission, referrer_id))

                c.execute("UPDATE keys SET is_sold=1, sold_to=?, purchase_date=?, expiry_date=? WHERE id=?", 
                          (user_id, purchase_date, expiry_date, key_dict['id']))
                
                c.execute("INSERT INTO purchases (user_id, plan_id, key_id, amount, purchase_date) VALUES (?, ?, ?, ?, ?)",
                          (user_id, plan_id, key_dict['id'], price, purchase_date))
                
                conn.commit()
                conn.close()
                info = {"key": key_dict['key_value'], "expiry": expiry_date, "product": plan_dict['product_name'], "duration": plan_dict['duration']}
                return True, "Success", info, referrer_id, commission
            except Exception as e:
                conn.rollback()
                conn.close()
                logger.error(f"Purchase Key Exception: {e}\n{traceback.format_exc()}")
                return False, f"Transaction error. Try again.", {}, 0, 0

    def get_user_keys(self, user_id: int, offset: int = 0, limit: int = 5):
        conn = self.get_connection()
        res = conn.execute("SELECT pr.name, pl.duration, k.key_value, k.expiry_date FROM keys k JOIN plans pl ON k.plan_id = pl.id JOIN products pr ON pl.product_id = pr.id WHERE k.sold_to=? ORDER BY k.purchase_date DESC LIMIT ? OFFSET ?", (user_id, limit, offset)).fetchall()
        conn.close()
        return[dict(r) for r in res]

    def get_user_keys_count(self, user_id: int):
        conn = self.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM keys WHERE sold_to=?", (user_id,)).fetchone()[0]
        conn.close()
        return count

    # Funds & Tickets
    def create_fund_request(self, user_id: int, photo_file_id: str, amount_selected: int) -> int:
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            unique_key = f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            c.execute("INSERT INTO fund_requests (user_id, utr, photo_file_id, amount_selected, request_date) VALUES (?, ?, ?, ?, ?)", 
                      (user_id, unique_key, photo_file_id, amount_selected, datetime.now().isoformat()))
            last_id = c.lastrowid
            conn.commit()
            conn.close()
            return last_id

    def get_pending_fund_requests(self):
        conn = self.get_connection()
        res = conn.execute("SELECT f.*, u.username, u.first_name FROM fund_requests f JOIN users u ON f.user_id = u.user_id WHERE f.status='PENDING' ORDER BY f.request_date ASC").fetchall()
        conn.close()
        return[dict(r) for r in res]

    def update_fund_request(self, req_id: int, status: str, amount: int = 0):
        with self.lock:
            conn = self.get_connection()
            conn.execute("UPDATE fund_requests SET status=?, amount_requested=?, resolved_date=? WHERE id=?", (status, amount, datetime.now().isoformat(), req_id))
            conn.commit()
            conn.close()

    def get_fund_request(self, req_id: int):
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM fund_requests WHERE id=?", (req_id,)).fetchone()
        conn.close()
        return dict(res) if res else {}

    def create_ticket(self, user_id: int, message: str):
        with self.lock:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO tickets (user_id, message, created_at) VALUES (?, ?, ?)", (user_id, message, datetime.now().isoformat()))
            last_id = c.lastrowid
            conn.commit()
            conn.close()
            return last_id

    def get_open_tickets(self):
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM tickets WHERE status='OPEN' ORDER BY created_at ASC").fetchall()
        conn.close()
        return[dict(r) for r in res]

    def reply_ticket(self, ticket_id: int, reply: str):
        with self.lock:
            conn = self.get_connection()
            conn.execute("UPDATE tickets SET reply=?, status='CLOSED', resolved_at=? WHERE id=?", (reply, datetime.now().isoformat(), ticket_id))
            user_id = conn.execute("SELECT user_id FROM tickets WHERE id=?", (ticket_id,)).fetchone()['user_id']
            conn.commit()
            conn.close()
            return user_id

    def get_setting(self, key: str, default: str = ""):
        conn = self.get_connection()
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row['value'] if row else default

    def set_setting(self, key: str, value: str):
        with self.lock:
            conn = self.get_connection()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            conn.close()

    def get_global_stats(self):
        conn = self.get_connection()
        c = conn.cursor()
        users = c.execute("SELECT COUNT(*) FROM users WHERE verified=1").fetchone()[0]
        revenue = c.execute("SELECT SUM(amount) FROM purchases").fetchone()[0] or 0
        sold_keys = c.execute("SELECT COUNT(*) FROM keys WHERE is_sold=1").fetchone()[0]
        avail_keys = c.execute("SELECT COUNT(*) FROM keys WHERE is_sold=0").fetchone()[0]
        conn.close()
        return users, revenue, sold_keys, avail_keys

db = DatabaseManager(DB_FILE)

# ------------------------------------------------------------------------------
# 3. PRESET DESCRIPTIONS 
# ------------------------------------------------------------------------------

def get_preset_desc(preset_id: str) -> str:
    line = get_line(14)
    if preset_id == "1":
        return (f"<blockquote><b>{ce('shield')} SAFE INJECTOR [ MAIN ID SAFE ]</b></blockquote>\n\n"
                f"<i>An ultimate tool engineered for main accounts with multi-layer encryption.</i>\n\n"
                f"<b>{ce('star')} Premium Features:</b>\n"
                f"<b>{ce('success')} 100% Anti-Ban & Anti-Blacklist Bypass</b>\n"
                f"<b>{ce('success')} ESP Line, Box, Skeleton & Distance</b>\n"
                f"<b>{ce('success')} Legit Smooth Aimbot & Auto-Headshot</b>\n"
                f"<b>{ce('success')} No Recoil & Weapon Modifiers</b>\n\n"
                f"<b>{ce('warning')} Requirements:</b>\n"
                f"<b>{ce('rocket')} Non-Root / Root both supported</b>\n"
                f"<b>{ce('rocket')} Android 9 to 14 Compatible</b>\n"
                f"<b>{ce('rocket')} 3GB+ RAM Recommended</b>\n\n"
                f"<i>Note: Play safe, do not get manual reports!</i>\n"
                f"{line}")
    elif preset_id == "2":
        return (f"<blockquote><b>{ce('fire')} BRUTAL MOD [ ROOT ONLY ]</b></blockquote>\n\n"
                f"<i>For aggressive players who want to dominate the lobby in seconds. Highly risky but extremely fun.</i>\n\n"
                f"<b>{ce('star')} Brutal Features:</b>\n"
                f"<b>{ce('success')} Deep Memory / Ptrace Injection</b>\n"
                f"<b>{ce('success')} Magic Bullet & 360 Bullet Track</b>\n"
                f"<b>{ce('success')} Flash Speed, High Damage & Fast Run</b>\n"
                f"<b>{ce('success')} Teleport & Car Fly (Risky)</b>\n\n"
                f"<b>{ce('warning')} Requirements & Warnings:</b>\n"
                f"<b>{ce('fail')} NOT safe for Main IDs (Smurf Only)</b>\n"
                f"<b>{ce('success')} Requires Magisk Root & Zygisk Hide</b>\n\n"
                f"<i>Note: 10-Year ban possible if overused!</i>\n"
                f"{line}")
    elif preset_id == "3":
        return (f"<blockquote><b>{ce('apple')} iOS eSign & Mod [ REVOKE FREE ]</b></blockquote>\n\n"
                f"<i>The ultimate iOS experience. Sideload our IPA directly without a computer.</i>\n\n"
                f"<b>{ce('star')} iOS Features:</b>\n"
                f"<b>{ce('success')} Premium Revoke-Free Certificate</b>\n"
                f"<b>{ce('success')} Built-in ESP, Radar & Triggerbot</b>\n"
                f"<b>{ce('success')} Silent Aim & Hardware Spoofer</b>\n"
                f"<b>{ce('success')} No Jailbreak Required at all!</b>\n\n"
                f"<b>{ce('warning')} Requirements:</b>\n"
                f"<b>{ce('success')} Supports iOS 14.0 to Latest 17.x</b>\n"
                f"<b>{ce('success')} DNS Anti-Revoke Profile Setup Needed</b>\n"
                f"{line}")
    elif preset_id == "4":
        return (f"<blockquote><b>{ce('name_icon')} 8 LEVEL ID [ HIGH QUALITY ]</b></blockquote>\n\n"
                f"<i>High quality 8 level accounts ready for immediate use.</i>\n\n"
                f"<b>{ce('star')} Account Details:</b>\n"
                f"<b>{ce('success')} Level 8+ Guaranteed</b>\n"
                f"<b>{ce('success')} Clean History, No Bans</b>\n"
                f"<b>{ce('success')} Full Access Provided</b>\n"
                f"<b>{ce('success')} Usable for Smurf / Main</b>\n\n"
                f"<b>{ce('warning')} Notice:</b>\n"
                f"<b>{ce('rocket')} Change password immediately after purchase</b>\n"
                f"<b>{ce('rocket')} Bind your own email/number</b>\n"
                f"{line}")
    elif preset_id == "5":
        return (f"<blockquote><b>{ce('mobile')} DRIP CLIENT [ NON ROOT ]</b></blockquote>\n\n"
                f"<i>Direct APK install & play. No injector, no root needed! Works on ALL Android devices.</i>\n\n"
                f"<b>{ce('star')} Features:</b>\n"
                f"<b>{ce('success')} Easy Installation (APK format)</b>\n"
                f"<b>{ce('success')} ESP Line, Box, Skeleton & Distance</b>\n"
                f"<b>{ce('success')} Legit Smooth Aimbot & Auto-Headshot</b>\n"
                f"<b>{ce('success')} No Recoil & Weapon Modifiers</b>\n\n"
                f"<b>{ce('warning')} Warning & Notice:</b>\n"
                f"<b>{ce('fail')} NOT 100% Anti-Ban & Anti-Blacklist.</b>\n"
                f"<b>{ce('rocket')} Play on secondary/smurf accounts only.</b>\n"
                f"<b>{ce('rocket')} We are not responsible for ID bans.</b>\n\n"
                f"<i>Note: Play safe, avoid manual reports!</i>\n"
                f"{line}")
    return "No description."


# ------------------------------------------------------------------------------
# 4. UI HELPERS & VERIFICATION
# ------------------------------------------------------------------------------

def verification_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Maintenance Mode Check
        is_maintenance = db.get_setting("maintenance_mode", "0")
        if is_maintenance == "1" and user_id not in ADMIN_IDS:
            msg = f"<blockquote><b>{ce('warning')} MAINTENANCE MODE ACTIVE</b></blockquote>\n\n<i>The bot is currently undergoing server upgrades. Please check back later.</i>"
            if update.callback_query:
                await update.callback_query.answer("Maintenance Mode", show_alert=True)
                await safe_edit_text(update, context, msg, None)
            else:
                await update.effective_message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

        # Admins bypass verification and ban checks
        if user_id in ADMIN_IDS:
            return await func(update, context, *args, **kwargs)

        user = db.get_user(user_id)
        if not user:
            await show_verification_prompt(update, context)
            return
        
        if not user.get('verified', 0):
            await show_verification_prompt(update, context)
            return
        if user.get('is_banned', 0):
            await update.effective_message.reply_text(f"<blockquote>{ce('poop')} <b>ACCOUNT BANNED</b>\nContact Admin to appeal.</blockquote>", parse_mode=ParseMode.HTML)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def show_verification_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("📱 Share Phone Number", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    text = (
        f"<blockquote><b>{ce('warning')} VERIFICATION REQUIRED {ce('warning')}</b></blockquote>\n\n"
        f"<i>To use Hack Store safely, please verify your account by sharing your phone number.</i>\n"
        f"<b>We use this to prevent spam and maintain a secure environment.</b>\n\n"
        f"{ce('down')} <b>Click the button below to verify:</b>"
    )
    if update.callback_query:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.effective_user.id
    
    # DB Fix: Ensure user exists before trying to verify
    db.add_user(user_id, update.effective_user.username, update.effective_user.first_name)
    
    user = db.get_user(user_id)
    if user and user.get('verified', 0):
        await update.message.reply_text(f"<blockquote>{ce('success')} You are already verified.</blockquote>", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
        try: await update.message.delete()
        except: pass
        return

    db.verify_user(user_id)

    try:
        phone_number = contact.phone_number
        first_name = contact.first_name
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        photo_id = photos.photos[0][-1].file_id if photos.total_count > 0 else db.get_setting("default_pfp")
        username = update.effective_user.username
        username_text = f"@{username}" if username else "N/A"
        
        admin_msg = (
            f"<blockquote><b>{ce('siren')} NEW VERIFIED USER {ce('siren')}</b></blockquote>\n\n"
            f"{ce('name_icon')} <b>Name:</b> <a href='tg://user?id={user_id}'>{first_name}</a>\n"
            f"{ce('link')} <b>Username:</b> {username_text}\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"{ce('contact')} <b>Phone:</b> <code>{phone_number}</code>\n"
            f"{get_line(12)}"
        )
        for admin in ADMIN_IDS:
            try: await context.bot.send_photo(chat_id=admin, photo=photo_id, caption=admin_msg, parse_mode=ParseMode.HTML)
            except: pass
    except Exception as e:
        logger.error(f"Error in contact_handler admin alert: {e}")

    try: await update.message.delete()
    except: pass

    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Verification successful! Welcome to Hack Store.</b></blockquote>", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
    
    user = db.get_user(user_id)
    bal = user.get('balance', 0) / 100
    welcome_text = (
        f"<blockquote><b>{ce('store')} WELCOME TO HACK STORE {ce('key')}</b></blockquote>\n\n"
        f"<i>Your ultimate destination for premium mods, cheats & clients!</i> {ce('globe')}\n"
        f"{get_line(12)}\n"
        f"<blockquote><b>{ce('rocket')} PREMIUM FEATURES:</b>\n"
        f"<b>{ce('success')} Instant Key Delivery</b>\n"
        f"<b>{ce('card')} Secure Payment System</b>\n"
        f"<b>{ce('success')} 100% Anti-Ban Support</b></blockquote>\n"
        f"{get_line(12)}\n\n"
        f"<blockquote><b>{ce('money')} Your Balance: ₹{bal:.2f}</b></blockquote>\n\n"
        f"<b>Select an option from the menu below:</b>"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)

# ----------------- KEYBOARDS (using standard emoji fallback) -----------------

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{ce_button('cart')} BUY HACK", callback_data="user_buy_hack"),
         InlineKeyboardButton(f"{ce_button('disk')} DOWNLOAD APK", callback_data="user_downloads")],[InlineKeyboardButton(f"{ce_button('card')} ADD FUND", callback_data="user_add_fund"),
         InlineKeyboardButton(f"{ce_button('money')} MY BALANCE", callback_data="user_balance")],[InlineKeyboardButton(f"{ce_button('key')} MY KEY", callback_data="user_my_keys_0"),
         InlineKeyboardButton(f"{ce_button('stock')} STOCK", callback_data="user_stock")],[InlineKeyboardButton(f"{ce_button('gift')} REFER & EARN", callback_data="user_referral"),
         InlineKeyboardButton(f"{ce_button('promo')} REDEEM PROMO", callback_data="user_promo")],[InlineKeyboardButton(f"{ce_button('trophy')} LEADERBOARD", callback_data="user_leaderboard"),
         InlineKeyboardButton(f"{ce_button('mobile')} HOW TO USE", callback_data="user_how_to")],[InlineKeyboardButton(f"{ce_button('books')} FAQ & TOS", callback_data="user_faq"),
         InlineKeyboardButton(f"{ce_button('user')} PROFILE", callback_data="user_profile")],[InlineKeyboardButton(f"{ce_button('contact')} SUPPORT", callback_data="user_contact")]
    ])

def back_kb(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data=callback_data)]])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{ce_button('fail')} Cancel Process", callback_data="cancel_conv")]])

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{ce_button('stats')} Dashboard", callback_data="admin_stats")],[InlineKeyboardButton(f"{ce_button('bag')} Products", callback_data="admin_products"),
         InlineKeyboardButton(f"{ce_button('key')} Keys", callback_data="admin_keys")],[InlineKeyboardButton(f"{ce_button('user')} Users", callback_data="admin_users"),
         InlineKeyboardButton(f"{ce_button('success')} Approve Funds", callback_data="admin_approvals")],[InlineKeyboardButton(f"{ce_button('promo')} Promos", callback_data="admin_promos"),
         InlineKeyboardButton(f"{ce_button('broadcast')} Broadcast", callback_data="admin_broadcast")],[InlineKeyboardButton(f"{ce_button('ticket')} Tickets", callback_data="admin_tickets"),
         InlineKeyboardButton(f"{ce_button('memo')} Content/Docs", callback_data="admin_faq")],[InlineKeyboardButton(f"{ce_button('disk')} Backup DB", callback_data="adm_export_db"),
         InlineKeyboardButton(f"{ce_button('tools')} Maintenance", callback_data="adm_maintenance")],[InlineKeyboardButton(f"{ce_button('settings')} Settings", callback_data="admin_settings")],[InlineKeyboardButton(f"{ce_button('back')} Exit Admin", callback_data="user_main")]
    ])

def pagination_kb(current_page: int, total_pages: int, prefix: str, back_cb: str) -> List[List[InlineKeyboardButton]]:
    buttons =[]
    nav =[]
    if current_page > 0: nav.append(InlineKeyboardButton(f"{ce_button('left')} Prev", callback_data=f"{prefix}_{current_page-1}"))
    nav.append(InlineKeyboardButton(f"Page {current_page+1}/{total_pages}", callback_data="ignore"))
    if current_page < total_pages - 1: nav.append(InlineKeyboardButton(f"Next {ce_button('right')}", callback_data=f"{prefix}_{current_page+1}"))
    if len(nav) > 1: buttons.append(nav)
    buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data=back_cb)])
    return buttons

async def safe_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup: InlineKeyboardMarkup, **kwargs):
    query = update.callback_query
    try:
        if query.message.photo or query.message.video or query.message.document:
            await query.message.delete()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, **kwargs)
        else:
            await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, **kwargs)
    except BadRequest as e:
        logger.warning(f"BadRequest in safe_edit_text: {e}")
        try:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, **kwargs)
        except Exception as ex:
            logger.error(f"Failed fallback in safe_edit_text: {ex}")

# ==============================================================================
# 5. USER HANDLERS
# ==============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referrer_id = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].replace("ref_", ""))
            if referrer_id == user.id: referrer_id = None
        except: pass

    is_new = db.add_user(user.id, user.username, user.first_name, referrer_id)
    if is_new and referrer_id:
        try:
            alert_text = (
                f"<blockquote><b>{ce('gift')} NEW REFERRAL ALERT!</b></blockquote>\n\n"
                f"User <a href='tg://user?id={user.id}'><b>{user.first_name}</b></a> has started the bot using your link!\n"
                f"<i>You will earn a <b>15% Commission</b> when they make their first purchase.</i>"
            )
            await context.bot.send_message(chat_id=referrer_id, text=alert_text, parse_mode=ParseMode.HTML)
        except: pass
            
    user_data = db.get_user(user.id)
    if user_data.get('is_banned', 0):
        await update.message.reply_text(f"<blockquote>{ce('fail')} <b>ACCOUNT BANNED</b>\nContact Admin.</blockquote>", parse_mode=ParseMode.HTML)
        return
    if not user_data.get('verified', 0):
        await show_verification_prompt(update, context)
        return

    is_maintenance = db.get_setting("maintenance_mode", "0")
    if is_maintenance == "1" and user.id not in ADMIN_IDS:
        msg = f"<blockquote><b>{ce('warning')} MAINTENANCE MODE ACTIVE</b></blockquote>\n\n<i>The bot is currently undergoing server upgrades. Please check back later.</i>"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    bal = user_data.get('balance', 0) / 100
    welcome_text = (
        f"<blockquote><b>{ce('store')} WELCOME TO HACK STORE {ce('key')}</b></blockquote>\n\n"
        f"<i>Your ultimate destination for premium mods, cheats & clients!</i> {ce('globe')}\n"
        f"{get_line(12)}\n"
        f"<blockquote><b>{ce('rocket')} PREMIUM FEATURES:</b>\n"
        f"<b>{ce('success')} Instant Key Delivery</b>\n"
        f"<b>{ce('card')} Secure Payment System</b>\n"
        f"<b>{ce('success')} 100% Anti-Ban Support</b></blockquote>\n"
        f"{get_line(12)}\n\n"
        f"<blockquote><b>{ce('money')} Your Balance: ₹{bal:.2f}</b></blockquote>\n\n"
        f"<b>Select an option from the menu below:</b>"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)

@verification_required
async def handle_user_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    try:
        if data == "user_main":
            await query.answer()
            user_data = db.get_user(user_id)
            bal = user_data.get('balance', 0) / 100
            welcome_text = (
                f"<blockquote><b>{ce('store')} WELCOME TO HACK STORE {ce('key')}</b></blockquote>\n\n"
                f"<i>Your ultimate destination for premium mods, cheats & clients!</i> {ce('globe')}\n"
                f"{get_line(12)}\n"
                f"<blockquote><b>{ce('rocket')} PREMIUM FEATURES:</b>\n"
                f"<b>{ce('success')} Instant Key Delivery</b>\n"
                f"<b>{ce('card')} Secure Payment System</b>\n"
                f"<b>{ce('success')} 100% Anti-Ban Support</b></blockquote>\n"
                f"{get_line(12)}\n\n"
                f"<blockquote><b>{ce('money')} Your Balance: ₹{bal:.2f}</b></blockquote>\n\n"
                f"<b>Select an option from the menu below:</b>"
            )
            await safe_edit_text(update, context, welcome_text, main_menu_kb())

        elif data == "user_buy_hack":
            await query.answer()
            products = db.get_active_products()
            if not products:
                await safe_edit_text(update, context, f"<blockquote>{ce('fail')} No products available at the moment.</blockquote>", back_kb("user_main"))
                return
            
            text = f"<blockquote><b>{ce('cart')} SELECT A HACK {ce('sparkle')}</b></blockquote>\n\n<i>Browse our exclusive collection below:</i>\n{get_line(12)}"
            buttons = [[InlineKeyboardButton(f"{ce_button('game')} {p['name']}", callback_data=f"buy_prod_{p['id']}")] for p in products]
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_main")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("buy_prod_"):
            await query.answer()
            prod_id = int(data.split("_")[2])
            prod = db.get_product(prod_id)
            plans = db.get_plans(prod_id)
            
            if not plans:
                await safe_edit_text(update, context, f"<blockquote>{ce('fail')} No active plans for <b>{prod.get('name', 'this product')}</b>.</blockquote>", back_kb("user_buy_hack"))
                return

            text = (
                f"<blockquote><b>{ce('game')} {prod['name']}</b></blockquote>\n\n"
                f"{prod['description']}\n\n"
                f"<i>{ce('time')} Choose your plan duration:</i>"
            )
            buttons = [[InlineKeyboardButton(f"{pl['duration']} - ₹{pl['price']/100:.2f}", callback_data=f"buy_plan_{pl['id']}")] for pl in plans]
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_buy_hack")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("buy_plan_"):
            await query.answer()
            plan_id = int(data.split("_")[2])
            plan = db.get_plan(plan_id)
            
            text = (
                f"<blockquote><b>{ce('cart')} CHECKOUT CONFIRMATION</b></blockquote>\n\n"
                f"<b>Product:</b> {plan['product_name']}\n"
                f"<b>Duration:</b> {plan['duration']}\n"
                f"<b>Price:</b> ₹{plan['price']/100:.2f}\n"
                f"{get_line(12)}\n"
                f"<i>Do you want to confirm this purchase?</i>"
            )
            buttons = [[InlineKeyboardButton(f"{ce_button('success')} YES, BUY NOW", callback_data=f"confirm_buy_{plan_id}")],[InlineKeyboardButton(f"{ce_button('fail')} CANCEL", callback_data=f"buy_prod_{plan['product_id']}")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("confirm_buy_"):
            plan_id = int(data.split("_")[2])
            success, msg, info, ref_id, comm = db.purchase_key(user_id, plan_id)
            
            if success:
                await query.answer("Purchase Successful! 🎉", show_alert=True)
                text = (
                    f"<blockquote><b>{ce('success')} PURCHASE SUCCESSFUL! {ce('star')}</b></blockquote>\n\n"
                    f"<b>Product:</b> {info['product']}\n"
                    f"<b>Duration:</b> {info['duration']}\n"
                    f"<b>Expiry:</b> {info['expiry'][:10]}\n"
                    f"{get_line(12)}\n"
                    f"<blockquote><b>{ce('key')} YOUR PREMIUM KEY:</b></blockquote>\n<code>{info['key']}</code>\n\n"
                    f"<i>Thank you for choosing Hack Store!</i>"
                )
                await safe_edit_text(update, context, text, back_kb("user_main"))
                
                if ref_id and comm > 0:
                    try:
                        ref_text = (
                            f"<blockquote><b>{ce('gift')} REFERRAL BONUS RECEIVED!</b></blockquote>\n\n"
                            f"Your referral just made a purchase. You earned a 15% commission of <b>₹{comm/100:.2f}</b> directly to your wallet!\n\n"
                            f"<i>Keep sharing your link to earn more!</i>"
                        )
                        await context.bot.send_message(chat_id=ref_id, text=ref_text, parse_mode=ParseMode.HTML)
                    except: pass
            else:
                await query.answer("Purchase Failed!", show_alert=True)
                text = f"<blockquote><b>{ce('fail')} PURCHASE FAILED</b></blockquote>\n\nReason: <b>{msg}</b>\n\n<i>Please add funds and try again.</i>"
                await safe_edit_text(update, context, text, back_kb("user_add_fund"))

        # --- DOWNLOADS MENU (Single Global Link) ---
        elif data == "user_downloads":
            await query.answer()
            channel_link = db.get_setting("global_channel_link", "https://t.me/YourDownloadChannel")
            
            text = (
                f"<blockquote><b>{ce('disk')} DOWNLOAD PREMIUM APK & FILES {ce('disk')}</b></blockquote>\n\n"
                f"<i>All our highly secured, premium, and updated files are securely hosted on our private channel!</i>\n"
                f"{get_line(12)}\n\n"
                f"<b>{ce('star')} WHAT YOU GET:</b>\n"
                f"<b>{ce('success')} Latest APK Updates</b>\n"
                f"<b>{ce('success')} 100% Virus Free & Secure</b>\n"
                f"<b>{ce('success')} All Configs & Scripts</b>\n"
                f"<b>{ce('success')} Complete Installation Guides</b>\n"
                f"{get_line(12)}\n\n"
                f"<b>{ce('warning')} INSTRUCTIONS:</b>\n"
                f"<b>{ce('1')} Click the button below to join the channel.</b>\n"
                f"<b>{ce('2')} Download the specific file you purchased.</b>\n"
                f"<b>{ce('3')} Use your premium key to activate.</b>\n\n"
                f"👇 <i>Tap the button below to access the Download Channel!</i>"
            )
            buttons = [[InlineKeyboardButton(f"{ce_button('outbox')} ACCESS DOWNLOAD CHANNEL", url=channel_link)],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_main")]
            ]
            await safe_edit_text(
                update, 
                context, 
                text, 
                InlineKeyboardMarkup(buttons),
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )

        # --- HOW TO USE ---
        elif data == "user_how_to":
            await query.answer()
            text = db.get_setting("how_to_text")
            vid = db.get_setting("how_to_video")
            
            buttons =[]
            if vid and vid.startswith("http"):
                buttons.append([InlineKeyboardButton(f"{ce_button('rocket')} Watch Tutorial Video", url=vid)])
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_main")])
            await safe_edit_text(
                update, 
                context, 
                text, 
                InlineKeyboardMarkup(buttons),
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )

        elif data == "user_add_fund":
            await query.answer()
            upi_id = db.get_setting("upi_id")
            text = (
                f"<blockquote><b>{ce('money')} ADD FUNDS TO WALLET {ce('card')}</b></blockquote>\n\n"
                f"<b>{ce('1')} Select the amount you want to pay.</b>\n"
                f"<b>{ce('2')} Scan the QR Code & pay via UPI.</b>\n"
                f"<b>{ce('3')} Send the payment screenshot.</b>\n"
                f"<b>{ce('4')} Admin will verify & credit your wallet.</b>\n"
                f"{get_line(12)}\n"
                f"<b>{ce('card')} UPI ID:</b> <code>{upi_id}</code>\n"
                f"{get_line(12)}\n"
                f"{ce('down')} <b>Select your payment amount:</b>"
            )
            buttons = [
                [InlineKeyboardButton(f"{ce_button('money')} ₹79 — Basic Plan", callback_data="pay_79"),
                 InlineKeyboardButton(f"{ce_button('star')} ₹189 — Pro Plan", callback_data="pay_189")],
                [InlineKeyboardButton(f"{ce_button('fire')} ₹349 — Premium Plan", callback_data="pay_349")],
                [InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_main")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data in ("pay_79", "pay_189", "pay_349"):
            await query.answer()
            amount_map = {"pay_79": (79, "qr_79"), "pay_189": (189, "qr_189"), "pay_349": (349, "qr_349")}
            amount_inr, qr_key = amount_map[data]
            qr_file_id = db.get_setting(qr_key)
            upi_id = db.get_setting("upi_id")
            context.user_data['pay_amount'] = amount_inr
            text = (
                f"<blockquote><b>{ce('card')} PAY ₹{amount_inr} — SCAN QR {ce('money')}</b></blockquote>\n\n"
                f"<b>{ce('1')} Scan the QR Code below.</b>\n"
                f"<b>{ce('2')} Pay exactly <b>₹{amount_inr}</b> via UPI.</b>\n"
                f"<b>{ce('3')} UPI ID:</b> <code>{upi_id}</code>\n"
                f"<b>{ce('4')} After paying, click <b>SEND SCREENSHOT</b> below.</b>\n"
                f"{get_line(12)}\n"
                f"<i>{ce('warning')} Do not close this chat after payment!</i>"
            )
            buttons = [
                [InlineKeyboardButton(f"{ce_button('success')} ✅ SEND PAYMENT SCREENSHOT", callback_data=f"submit_screenshot_{amount_inr}")],
                [InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_add_fund")]
            ]
            if qr_file_id and qr_file_id not in (None, "None", ""):
                try:
                    await query.message.delete()
                except: pass
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=qr_file_id,
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode=ParseMode.HTML
                )
            else:
                await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_balance":
            await query.answer()
            user_data = db.get_user(user_id)
            bal = user_data.get('balance', 0) / 100
            text = (
                f"<blockquote><b>{ce('card')} YOUR WALLET BALANCE</b></blockquote>\n\n"
                f"<b>Available Funds:</b> ₹{bal:.2f}\n"
                f"{get_line(12)}\n"
                f"<i>Want to buy something? Select BUY HACK!</i>"
            )
            await safe_edit_text(update, context, text, back_kb("user_main"))

        elif data == "user_referral":
            await query.answer()
            user_data = db.get_user(user_id)
            bot_info = await context.bot.get_me()
            
            ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
            share_msg = f"🔥 Join the Ultimate Hack Store! Get premium mods and scripts instantly. Use my link to start: {ref_link}"
            share_url = f"https://t.me/share/url?url={ref_link}&text={quote(share_msg)}"

            text = (
                f"<blockquote><b>{ce('gift')} HACK STORE REFERRAL PROGRAM {ce('gift')}</b></blockquote>\n\n"
                f"<i>Invite your friends and earn a massive <b>15% LIFETIME COMMISSION</b> on every purchase they make! The more you share, the more you earn.</i>\n"
                f"{get_line(12)}\n\n"
                f"<b>{ce('game')} How it works (Example):</b>\n"
                f"<b>{ce('1')} You share your link with a friend.</b>\n"
                f"<b>{ce('2')} Friend starts bot and buys a Hack for ₹1,000.</b>\n"
                f"<b>{ce('3')} You instantly get ₹150 in your wallet!</b>\n"
                f"<b>{ce('4')} Use your balance to buy keys for FREE!</b>\n\n"
                f"{get_line(12)}\n"
                f"<b>{ce('stats')} Your Referral Stats:</b>\n"
                f"<b>{ce('user')} Total Referrals:</b> {user_data.get('total_referrals', 0)}\n"
                f"<b>{ce('money')} Total Earnings:</b> ₹{user_data.get('referral_earnings', 0)/100:.2f}\n"
                f"{get_line(12)}\n\n"
                f"<b>{ce('link')} Your Personal Invite Link:</b>\n"
                f"<code>{ref_link}</code>\n\n"
                f"👇 <i>Click the button below to share directly with your friends!</i>"
            )
            buttons = [[InlineKeyboardButton(f"{ce_button('outbox')} SHARE & INVITE FRIENDS", url=share_url)],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_main")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_leaderboard":
            await query.answer()
            leaders = db.get_leaderboard()
            if not leaders:
                await safe_edit_text(update, context, f"<blockquote>{ce('warning')} No leaderboard data yet. Be the first to buy!</blockquote>", back_kb("user_main"))
                return
                
            text = f"<blockquote><b>{ce('trophy')} TOP VIP HACKERS {ce('trophy')}</b></blockquote>\n\n<i>Here are our top 10 most valuable users based on their purchases!</i>\n{get_line(12)}\n\n"
            
            medals =[ce('gold1'), ce('silver'), ce('bronze'), ce('medal'), ce('medal'), ce('medal'), ce('medal'), ce('medal'), ce('medal'), ce('medal')]
            for i, leader in enumerate(leaders):
                text += f"{medals[i]} <b>{leader['first_name']}</b> ➖ ₹{leader['total_spent']/100:.2f}\n"
            
            text += f"\n{get_line(12)}\n<i>Buy more to get your name on the Leaderboard!</i>"
            await safe_edit_text(update, context, text, back_kb("user_main"))

        elif data == "user_faq":
            await query.answer()
            faq = db.get_setting("faq_text")
            tos = db.get_setting("tos_text")
            text = (
                f"<blockquote><b>{ce('books')} FAQ & TERMS OF SERVICE</b></blockquote>\n\n"
                f"<b>🔹 FAQ:</b>\n<i>{faq}</i>\n\n"
                f"{get_line(12)}\n"
                f"<b>🔹 TERMS OF SERVICE:</b>\n<i>{tos}</i>\n\n"
                f"<i>By using this bot, you agree to these terms.</i>"
            )
            await safe_edit_text(update, context, text, back_kb("user_main"))

        elif data == "user_profile":
            await query.answer()
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_PHOTO)
            
            user_data = db.get_user(user_id)
            keys_count = db.get_user_keys_count(user_id)
            total_spent = user_data.get('total_spent', 0) / 100
            
            text = (
                f"<blockquote><b>{ce('user')} USER PROFILE {ce('user')}</b></blockquote>\n\n"
                f"<b>ID:</b> <code>{user_data.get('user_id')}</code>\n"
                f"<b>Name:</b> <b>{user_data.get('first_name')}</b>\n"
                f"<b>Username:</b> @{user_data.get('username') or 'N/A'}\n"
                f"<b>Joined:</b> <b>{user_data.get('joined_date', '')[:10]}</b>\n"
                f"{get_line(12)}\n"
                f"<b>{ce('money')} Balance:</b> ₹{user_data.get('balance', 0)/100:.2f}\n"
                f"<b>{ce('stats')} Spent:</b> ₹{total_spent:.2f}\n"
                f"<b>{ce('key')} Keys:</b> {keys_count}\n\n"
                f"<i>Note: Profile fetches your current Telegram Photo.</i>"
            )
            
            kb = back_kb("user_main")
            try:
                photos = await context.bot.get_user_profile_photos(user_id, limit=1)
                photo_id = photos.photos[0][-1].file_id if photos.total_count > 0 else db.get_setting("default_pfp")
                await query.message.delete()
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=photo_id, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Error fetching profile photo: {e}")
                await safe_edit_text(update, context, text, kb)

        elif data.startswith("user_my_keys_"):
            await query.answer()
            page = int(data.split("_")[3])
            limit = 5
            offset = page * limit
            total_keys = db.get_user_keys_count(user_id)
            keys = db.get_user_keys(user_id, offset, limit)

            if total_keys == 0:
                await safe_edit_text(update, context, f"<blockquote>{ce('fail')} You do not have any active keys.</blockquote>", back_kb("user_main"))
                return

            text = f"<blockquote><b>{ce('key')} YOUR PURCHASE HISTORY {ce('star')}</b></blockquote>\n\n"
            for k in keys:
                text += (f"🎮 <b>{k['name']}</b> ({k['duration']})\n"
                         f"<code>{k['key_value']}</code>\n"
                         f"⏳ <b>Expiry:</b> {k['expiry_date'][:10]}\n"
                         f"{get_line(10)}\n")
            
            total_pages = math.ceil(total_keys / limit)
            buttons = pagination_kb(page, total_pages, "user_my_keys", "user_main")
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_stock":
            await query.answer()
            products = db.get_active_products()
            if not products:
                await safe_edit_text(update, context, f"<blockquote>{ce('warning')} No stock available right now.</blockquote>", back_kb("user_main"))
                return

            text = f"<blockquote><b>{ce('search')} CURRENT STOCK STATUS {ce('stock')}</b></blockquote>\n\n<i>Click a plan to buy instantly!</i>\n{get_line(12)}\n"
            buttons = []
            for prod in products:
                plans = db.get_plans(prod['id'])
                for pl in plans:
                    conn = db.get_connection()
                    count = conn.execute("SELECT COUNT(*) FROM keys WHERE plan_id=? AND is_sold=0", (pl['id'],)).fetchone()[0]
                    conn.close()
                    stock_icon = ce_button('success') if count > 0 else ce_button('fail')
                    stock_label = f"{count} in stock" if count > 0 else "OUT OF STOCK"
                    text += f"{ce('game')} <b>{prod['name']}</b> — {pl['duration']} — ₹{pl['price']/100:.0f} [{stock_label}]\n"
                    if count > 0:
                        buttons.append([InlineKeyboardButton(
                            f"{stock_icon} {prod['name']} | {pl['duration']} | ₹{pl['price']/100:.0f}",
                            callback_data=f"buy_plan_{pl['id']}"
                        )])
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_main")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_contact":
            await query.answer()
            sup_user = db.get_setting("support_user")
            text = (
                f"<blockquote><b>{ce('contact')} NEED HELP? WE'RE HERE!</b></blockquote>\n\n"
                f"For direct support, questions, or issue resolution, contact our admin directly or open a support ticket below.\n\n"
                f"<b>{ce('admin')} Admin:</b> {sup_user}"
            )
            buttons = [[InlineKeyboardButton(f"{ce_button('ticket')} Open Support Ticket", callback_data="user_ticket")],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="user_main")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
            
    except Exception as e:
        logger.error(f"Error in user callbacks: {traceback.format_exc()}")


# ==============================================================================
# 6. ADMIN HANDLERS
# ==============================================================================

@verification_required
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        insult_raw = db.get_setting('unauth_msg')
        await update.message.reply_text(insult_raw, parse_mode=ParseMode.HTML)
        return
    await update.message.reply_text(f"<blockquote><b>{ce('admin')} ENTERPRISE ADMIN PANEL</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)

@verification_required
async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("Access Denied!", show_alert=True)
        return

    try:
        if data == "admin_main":
            await query.answer()
            await safe_edit_text(update, context, f"<blockquote><b>{ce('admin')} ENTERPRISE ADMIN PANEL</b></blockquote>", admin_menu_kb())

        elif data == "admin_stats":
            await query.answer()
            users, rev, sold, avail = db.get_global_stats()
            text = (
                f"<blockquote><b>{ce('stats')} ENTERPRISE DASHBOARD & STATS</b></blockquote>\n\n"
                f"<b>{ce('user')} Total Verified Users:</b> {users}\n"
                f"<b>{ce('money')} Total Revenue:</b> ₹{rev/100:.2f}\n"
                f"<b>{ce('key')} Total Keys Sold:</b> {sold}\n"
                f"<b>{ce('stock')} Keys In Stock:</b> {avail}\n"
                f"{get_line(12)}\n"
                f"<i>All activities are securely logged in the database.</i>"
            )
            await safe_edit_text(update, context, text, back_kb("admin_main"))

        # --- DB EXPORT & MAINTENANCE ---
        elif data == "adm_export_db":
            await query.answer("Preparing Database Export...")
            try:
                with open(DB_FILE, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=user_id, 
                        document=f, 
                        filename=f"hackstore_backup_{datetime.now().strftime('%Y%m%d')}.db",
                        caption=f"<blockquote><b>{ce('disk')} DATABASE BACKUP</b></blockquote>\n<i>Keep this file secure!</i>",
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                await safe_edit_text(update, context, f"Error exporting DB: {e}", back_kb("admin_main"))

        elif data == "adm_maintenance":
            await query.answer()
            current = db.get_setting("maintenance_mode", "0")
            new_mode = "0" if current == "1" else "1"
            db.set_setting("maintenance_mode", new_mode)
            db.log_admin_action(user_id, "Toggled Maintenance", f"New Status: {new_mode}")
            
            status = f"<b>{ce('fail')} ACTIVE (Users Blocked)</b>" if new_mode == "1" else f"<b>{ce('success')} INACTIVE (Users Allowed)</b>"
            text = f"<blockquote><b>{ce('tools')} MAINTENANCE MODE</b></blockquote>\n\nCurrent Status: {status}"
            buttons = [[InlineKeyboardButton(f"{ce_button('loop')} Toggle Mode", callback_data="adm_maintenance")],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # --- Product Management ---
        elif data == "admin_products":
            await query.answer()
            prods = db.get_all_products()
            text = f"<blockquote><b>{ce('bag')} MANAGE PRODUCTS</b></blockquote>\nSelect a product to edit or add a new one."
            buttons = [[InlineKeyboardButton(p['name'], callback_data=f"adm_prod_{p['id']}")] for p in prods]
            buttons.append([InlineKeyboardButton(f"{ce_button('plus')} Add New Product", callback_data="adm_add_prod")])
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_prod_"):
            await query.answer()
            p_id = int(data.split("_")[2])
            p = db.get_product(p_id)
            text = f"<blockquote><b>{ce('edit')} EDIT PRODUCT</b></blockquote>\n\n<b>Name:</b> {p['name']}\n<b>Active:</b> {'Yes ' + ce('success') if p['is_active'] else 'No ' + ce('fail')}\n\n{p['description']}"
            buttons = [[InlineKeyboardButton(f"{ce_button('pencil')} Edit Description", callback_data=f"adm_edit_desc_{p_id}")],[InlineKeyboardButton(f"{ce_button('loop')} Toggle Status", callback_data=f"adm_ptog_{p_id}")],[InlineKeyboardButton(f"{ce_button('bag')} Manage Plans", callback_data=f"adm_plans_{p_id}")],[InlineKeyboardButton(f"{ce_button('fail')} Delete Product", callback_data=f"adm_delprod_{p_id}")],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_products")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_ptog_"):
            p_id = int(data.split("_")[2])
            db.toggle_product(p_id)
            db.log_admin_action(user_id, "Toggled Product", f"PID: {p_id}")
            await query.answer("Status toggled!")
            p = db.get_product(p_id)
            text = f"<blockquote><b>{ce('edit')} EDIT PRODUCT</b></blockquote>\n\n<b>Name:</b> {p['name']}\n<b>Active:</b> {'Yes ' + ce('success') if p['is_active'] else 'No ' + ce('fail')}\n\n{p['description']}"
            buttons = [[InlineKeyboardButton(f"{ce_button('pencil')} Edit Description", callback_data=f"adm_edit_desc_{p_id}")],[InlineKeyboardButton(f"{ce_button('loop')} Toggle Status", callback_data=f"adm_ptog_{p_id}")],[InlineKeyboardButton(f"{ce_button('bag')} Manage Plans", callback_data=f"adm_plans_{p_id}")],[InlineKeyboardButton(f"{ce_button('fail')} Delete Product", callback_data=f"adm_delprod_{p_id}")],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_products")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_delprod_"):
            p_id = int(data.split("_")[2])
            text = f"<blockquote><b>{ce('warning')} Are you sure you want to delete this product?</b>\n\nThis will also delete all its plans and keys. This action cannot be undone.</blockquote>"
            buttons = [[InlineKeyboardButton(f"{ce_button('fail')} Yes, Delete", callback_data=f"adm_confirm_delprod_{p_id}")],[InlineKeyboardButton(f"{ce_button('back')} Cancel", callback_data=f"adm_prod_{p_id}")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_confirm_delprod_"):
            p_id = int(data.split("_")[3])
            db.delete_product(p_id)
            db.log_admin_action(user_id, "Deleted Product", f"PID: {p_id}")
            await query.answer("Product deleted successfully!")
            await safe_edit_text(update, context, f"<blockquote>{ce('success')} Product Deleted Successfully.</blockquote>", back_kb("admin_products"))

        # --- Plan Management ---
        elif data.startswith("adm_plans_"):
            await query.answer()
            p_id = int(data.split("_")[2])
            plans = db.get_plans(p_id)
            text = f"<blockquote><b>📋 MANAGE PLANS</b></blockquote>\n<i>Click a plan to delete it.</i>\n{get_line(12)}"
            buttons =[]
            for pl in plans:
                buttons.append([InlineKeyboardButton(f"{ce_button('fail')} {pl['duration']} - ₹{pl['price']/100:.2f}", callback_data=f"adm_plan_del_{pl['id']}")])
            buttons.append([InlineKeyboardButton(f"{ce_button('plus')} Add New Plan", callback_data=f"adm_add_plan_{p_id}")])
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data=f"adm_prod_{p_id}")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_plan_del_"):
            pl_id = int(data.split("_")[3])
            plan = db.get_plan(pl_id)
            if plan:
                text = f"<blockquote><b>{ce('warning')} Delete plan '{plan['duration']}'?</b>\n\nAll keys under this plan will also be deleted. This action cannot be undone.</blockquote>"
                buttons = [[InlineKeyboardButton(f"{ce_button('fail')} Yes, Delete", callback_data=f"adm_confirm_plandell_{pl_id}")],[InlineKeyboardButton(f"{ce_button('back')} Cancel", callback_data=f"adm_plans_{plan['product_id']}")]
                ]
                await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_confirm_plandell_"):
            pl_id = int(data.split("_")[3])
            plan = db.get_plan(pl_id)
            prod_id = plan.get('product_id') if plan else 0
            db.delete_plan(pl_id)
            db.log_admin_action(user_id, "Deleted Plan", f"PlanID: {pl_id}")
            await query.answer("Plan deleted!")
            await safe_edit_text(update, context, f"<blockquote>{ce('success')} Plan Deleted.</blockquote>", back_kb(f"adm_plans_{prod_id}"))

        # --- Key Management ---
        elif data == "admin_keys":
            await query.answer()
            prods = db.get_all_products()
            text = f"<blockquote><b>{ce('key')} MANAGE KEYS</b></blockquote>\n<i>Select a product to manage its keys.</i>"
            buttons = [[InlineKeyboardButton(f"{ce_button('game')} {p['name']}", callback_data=f"adm_kprod_{p['id']}")] for p in prods]
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_kprod_"):
            await query.answer()
            p_id = int(data.split("_")[2])
            prod = db.get_product(p_id)
            plans = db.get_plans(p_id)
            text = f"<blockquote><b>{ce('key')} {prod.get('name','Product')} — KEY PLANS</b></blockquote>\n<i>Add or manage keys per plan.</i>"
            buttons = []
            for pl in plans:
                cnt = db.get_unsold_keys_count_for_plan(pl['id'])
                buttons.append([
                    InlineKeyboardButton(f"{ce_button('plus')} Add | {pl['duration']} [{cnt} left]", callback_data=f"adm_kplan_{pl['id']}"),
                    InlineKeyboardButton(f"{ce_button('search')} View", callback_data=f"adm_viewkeys_{pl['id']}_0"),
                    InlineKeyboardButton(f"{ce_button('fail')} Clear", callback_data=f"adm_clearkeys_{pl['id']}")
                ])
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_keys")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_viewkeys_"):
            await query.answer()
            parts = data.split("_")
            pl_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 0
            limit = 8
            offset = page * limit
            plan = db.get_plan(pl_id)
            keys = db.get_unsold_keys_for_plan(pl_id, limit, offset)
            total = db.get_unsold_keys_count_for_plan(pl_id)
            total_pages = max(1, math.ceil(total / limit))
            text = (
                f"<blockquote><b>{ce('key')} KEYS — {plan.get('product_name','?')} | {plan.get('duration','?')}</b></blockquote>\n"
                f"<i>Showing unsold keys. Click to delete individual key.</i>\n"
                f"<b>Total unsold: {total}</b>\n{get_line(12)}\n"
            )
            for k in keys:
                text += f"<code>{k['key_value']}</code>\n"
            buttons_rows = []
            for k in keys:
                buttons_rows.append([InlineKeyboardButton(f"{ce_button('fail')} Del: {k['key_value'][:20]}...", callback_data=f"adm_delkey_{k['id']}_{pl_id}")])
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton(f"{ce_button('left')} Prev", callback_data=f"adm_viewkeys_{pl_id}_{page-1}"))
            nav.append(InlineKeyboardButton(f"Pg {page+1}/{total_pages}", callback_data="ignore"))
            if page < total_pages - 1:
                nav.append(InlineKeyboardButton(f"Next {ce_button('right')}", callback_data=f"adm_viewkeys_{pl_id}_{page+1}"))
            if nav:
                buttons_rows.append(nav)
            buttons_rows.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data=f"adm_kprod_{plan.get('product_id',0)}")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons_rows))

        elif data.startswith("adm_delkey_"):
            parts = data.split("_")
            key_id = int(parts[2])
            pl_id = int(parts[3])
            db.delete_single_key(key_id)
            db.log_admin_action(user_id, "Deleted Key", f"KeyID: {key_id}")
            await query.answer("Key deleted!", show_alert=False)
            page = 0
            plan = db.get_plan(pl_id)
            keys = db.get_unsold_keys_for_plan(pl_id, 8, 0)
            total = db.get_unsold_keys_count_for_plan(pl_id)
            total_pages = max(1, math.ceil(total / 8))
            text = (
                f"<blockquote><b>{ce('key')} KEYS — {plan.get('product_name','?')} | {plan.get('duration','?')}</b></blockquote>\n"
                f"<i>Key deleted. Remaining unsold: <b>{total}</b></i>\n{get_line(12)}\n"
            )
            for k in keys:
                text += f"<code>{k['key_value']}</code>\n"
            buttons_rows = []
            for k in keys:
                buttons_rows.append([InlineKeyboardButton(f"{ce_button('fail')} Del: {k['key_value'][:20]}...", callback_data=f"adm_delkey_{k['id']}_{pl_id}")])
            if total_pages > 1:
                buttons_rows.append([InlineKeyboardButton(f"Pg 1/{total_pages}", callback_data="ignore"), InlineKeyboardButton(f"Next {ce_button('right')}", callback_data=f"adm_viewkeys_{pl_id}_1")])
            buttons_rows.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data=f"adm_kprod_{plan.get('product_id',0)}")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons_rows))

        elif data.startswith("adm_clearkeys_"):
            await query.answer()
            pl_id = int(data.split("_")[2])
            plan = db.get_plan(pl_id)
            cnt = db.get_unsold_keys_count_for_plan(pl_id)
            text = (
                f"<blockquote><b>{ce('warning')} CLEAR ALL UNSOLD KEYS?</b></blockquote>\n\n"
                f"Plan: <b>{plan.get('product_name','?')} — {plan.get('duration','?')}</b>\n"
                f"This will delete <b>{cnt}</b> unsold keys. This cannot be undone!"
            )
            buttons = [
                [InlineKeyboardButton(f"{ce_button('fail')} Yes, Clear All {cnt} Keys", callback_data=f"adm_confirmclear_{pl_id}")],
                [InlineKeyboardButton(f"{ce_button('back')} Cancel", callback_data=f"adm_kprod_{plan.get('product_id',0)}")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_confirmclear_"):
            pl_id = int(data.split("_")[2])
            plan = db.get_plan(pl_id)
            deleted = db.delete_unsold_keys_for_plan(pl_id)
            db.log_admin_action(user_id, "Cleared All Keys", f"PlanID: {pl_id}, Count: {deleted}")
            await query.answer(f"Cleared {deleted} keys!", show_alert=True)
            await safe_edit_text(update, context, f"<blockquote>{ce('success')} <b>Cleared {deleted} unsold keys successfully.</b></blockquote>", back_kb(f"adm_kprod_{plan.get('product_id',0)}"))

        # --- Promo Codes Management ---
        elif data == "admin_promos":
            await query.answer()
            promos = db.get_all_promos()
            text = f"<blockquote><b>{ce('promo')} PROMO CODES</b></blockquote>\n<i>Click a promo to delete it.</i>\n{get_line(12)}\n"
            buttons = []
            if promos:
                for pr in promos:
                    used = pr['current_uses']
                    maxi = pr['max_uses']
                    reward = pr['reward_paise'] / 100
                    buttons.append([InlineKeyboardButton(
                        f"{ce_button('fail')} {pr['code']} | ₹{reward:.0f} | {used}/{maxi} uses",
                        callback_data=f"adm_del_promo_{pr['code']}"
                    )])
                    text += f"{ce('promo')} <code>{pr['code']}</code> — ₹{reward:.0f} — {used}/{maxi} uses\n"
            else:
                text += "<i>No promo codes yet. Create one below!</i>"
            buttons.append([InlineKeyboardButton(f"{ce_button('plus')} Create New Promo Code", callback_data="adm_create_promo")])
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_del_promo_"):
            await query.answer()
            code = data[len("adm_del_promo_"):]
            text = (
                f"<blockquote><b>{ce('warning')} DELETE PROMO CODE?</b></blockquote>\n\n"
                f"Code: <code>{code}</code>\n"
                f"<i>This will remove the promo and all redemption records.</i>"
            )
            buttons = [
                [InlineKeyboardButton(f"{ce_button('fail')} Yes, Delete", callback_data=f"adm_confirm_del_promo_{code}")],
                [InlineKeyboardButton(f"{ce_button('back')} Cancel", callback_data="admin_promos")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_confirm_del_promo_"):
            code = data[len("adm_confirm_del_promo_"):]
            db.delete_promo(code)
            db.log_admin_action(user_id, "Deleted Promo", f"Code: {code}")
            await query.answer("Promo deleted!", show_alert=True)
            promos = db.get_all_promos()
            text = f"<blockquote>{ce('success')} <b>Promo <code>{code}</code> deleted!</b></blockquote>\n{get_line(12)}\n"
            buttons = []
            for pr in promos:
                used = pr['current_uses']
                maxi = pr['max_uses']
                reward = pr['reward_paise'] / 100
                buttons.append([InlineKeyboardButton(f"{ce_button('fail')} {pr['code']} | ₹{reward:.0f} | {used}/{maxi} uses", callback_data=f"adm_del_promo_{pr['code']}")])
                text += f"{ce('promo')} <code>{pr['code']}</code> — ₹{reward:.0f} — {used}/{maxi} uses\n"
            if not promos:
                text += "<i>No promo codes remaining.</i>"
            buttons.append([InlineKeyboardButton(f"{ce_button('plus')} Create New Promo Code", callback_data="adm_create_promo")])
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # --- User Management ---
        elif data == "admin_users":
            await query.answer()
            total = db.get_all_users_total()
            text = f"<blockquote><b>{ce('user')} USER MANAGEMENT</b></blockquote>\n<b>Total Verified Users: {total}</b>\n{get_line(12)}\nChoose an action:"
            buttons = [
                [InlineKeyboardButton(f"{ce_button('search')} Browse All Users", callback_data="adm_browse_users_0")],
                [InlineKeyboardButton(f"{ce_button('money')} Add Balance", callback_data="adm_add_bal"),
                 InlineKeyboardButton(f"{ce_button('fail')} Ban User", callback_data="adm_ban_usr"),
                 InlineKeyboardButton(f"{ce_button('success')} Unban", callback_data="adm_unban_usr")],
                [InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_browse_users_"):
            await query.answer()
            page = int(data.split("_")[3])
            limit = 8
            offset = page * limit
            users = db.get_all_users_list(offset, limit)
            total = db.get_all_users_total()
            total_pages = max(1, math.ceil(total / limit))
            text = (
                f"<blockquote><b>{ce('user')} ALL USERS — Page {page+1}/{total_pages}</b></blockquote>\n"
                f"<i>Click a user to view details & actions.</i>\n{get_line(12)}\n"
            )
            buttons = []
            for u in users:
                ban_icon = ce_button('fail') if u['is_banned'] else ce_button('success')
                uname = f"@{u['username']}" if u['username'] else f"ID:{u['user_id']}"
                buttons.append([InlineKeyboardButton(
                    f"{ban_icon} {u['first_name']} | {uname} | ₹{u['balance']/100:.0f}",
                    callback_data=f"adm_user_detail_{u['user_id']}"
                )])
                text += f"{ban_icon} <b>{u['first_name']}</b> ({uname}) — ₹{u['balance']/100:.0f}\n"
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton(f"{ce_button('left')} Prev", callback_data=f"adm_browse_users_{page-1}"))
            nav.append(InlineKeyboardButton(f"Pg {page+1}/{total_pages}", callback_data="ignore"))
            if page < total_pages - 1:
                nav.append(InlineKeyboardButton(f"Next {ce_button('right')}", callback_data=f"adm_browse_users_{page+1}"))
            if nav:
                buttons.append(nav)
            buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_users")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_user_detail_"):
            await query.answer()
            uid = int(data.split("_")[3])
            u = db.get_user(uid)
            if not u:
                await safe_edit_text(update, context, f"<blockquote>{ce('fail')} User not found.</blockquote>", back_kb("admin_users"))
                return
            keys_count = db.get_user_keys_count(uid)
            ban_status = f"{ce('fail')} BANNED" if u.get('is_banned') else f"{ce('success')} ACTIVE"
            text = (
                f"<blockquote><b>{ce('user')} USER DETAILS</b></blockquote>\n\n"
                f"<b>ID:</b> <code>{uid}</code>\n"
                f"<b>Name:</b> {u.get('first_name','N/A')}\n"
                f"<b>Username:</b> @{u.get('username') or 'N/A'}\n"
                f"<b>Status:</b> {ban_status}\n"
                f"{get_line(12)}\n"
                f"<b>{ce('money')} Balance:</b> ₹{u.get('balance',0)/100:.2f}\n"
                f"<b>{ce('stats')} Spent:</b> ₹{u.get('total_spent',0)/100:.2f}\n"
                f"<b>{ce('key')} Keys:</b> {keys_count}\n"
                f"<b>{ce('gift')} Referrals:</b> {u.get('total_referrals',0)}\n"
                f"<b>{ce('time')} Joined:</b> {str(u.get('joined_date',''))[:10]}\n"
            )
            ban_btn = InlineKeyboardButton(f"{ce_button('success')} Unban", callback_data=f"adm_quickunban_{uid}") if u.get('is_banned') else InlineKeyboardButton(f"{ce_button('fail')} Ban", callback_data=f"adm_quickban_{uid}")
            buttons = [
                [ban_btn, InlineKeyboardButton(f"{ce_button('money')} Add Balance", callback_data=f"adm_quickbal_{uid}")],
                [InlineKeyboardButton(f"{ce_button('back')} Back to Users", callback_data="adm_browse_users_0")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_quickban_"):
            uid = int(data.split("_")[2])
            db.ban_user(uid, 1)
            db.log_admin_action(user_id, "Banned User", f"UID: {uid}")
            await query.answer(f"User {uid} BANNED!", show_alert=True)
            u = db.get_user(uid)
            keys_count = db.get_user_keys_count(uid)
            text = (
                f"<blockquote><b>{ce('user')} USER DETAILS</b></blockquote>\n\n"
                f"<b>ID:</b> <code>{uid}</code>\n"
                f"<b>Name:</b> {u.get('first_name','N/A')}\n"
                f"<b>Status:</b> {ce('fail')} BANNED\n"
                f"<b>{ce('money')} Balance:</b> ₹{u.get('balance',0)/100:.2f}\n"
                f"<b>{ce('key')} Keys:</b> {keys_count}"
            )
            buttons = [
                [InlineKeyboardButton(f"{ce_button('success')} Unban", callback_data=f"adm_quickunban_{uid}"),
                 InlineKeyboardButton(f"{ce_button('money')} Add Balance", callback_data=f"adm_quickbal_{uid}")],
                [InlineKeyboardButton(f"{ce_button('back')} Back to Users", callback_data="adm_browse_users_0")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_quickunban_"):
            uid = int(data.split("_")[2])
            db.ban_user(uid, 0)
            db.log_admin_action(user_id, "Unbanned User", f"UID: {uid}")
            await query.answer(f"User {uid} UNBANNED!", show_alert=True)
            u = db.get_user(uid)
            keys_count = db.get_user_keys_count(uid)
            text = (
                f"<blockquote><b>{ce('user')} USER DETAILS</b></blockquote>\n\n"
                f"<b>ID:</b> <code>{uid}</code>\n"
                f"<b>Name:</b> {u.get('first_name','N/A')}\n"
                f"<b>Status:</b> {ce('success')} ACTIVE\n"
                f"<b>{ce('money')} Balance:</b> ₹{u.get('balance',0)/100:.2f}\n"
                f"<b>{ce('key')} Keys:</b> {keys_count}"
            )
            buttons = [
                [InlineKeyboardButton(f"{ce_button('fail')} Ban", callback_data=f"adm_quickban_{uid}"),
                 InlineKeyboardButton(f"{ce_button('money')} Add Balance", callback_data=f"adm_quickbal_{uid}")],
                [InlineKeyboardButton(f"{ce_button('back')} Back to Users", callback_data="adm_browse_users_0")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_quickbal_"):
            await query.answer()
            uid = int(data.split("_")[2])
            context.user_data['quickbal_uid'] = uid
            u = db.get_user(uid)
            await safe_edit_text(
                update, context,
                f"<blockquote><b>{ce('money')} ADD BALANCE</b></blockquote>\n\n"
                f"User: <b>{u.get('first_name','?')}</b> (<code>{uid}</code>)\n"
                f"Current Balance: ₹{u.get('balance',0)/100:.2f}\n\n"
                f"<i>Type the amount in INR to add:</i>",
                cancel_kb()
            )
            context.user_data['quickbal_active'] = True

        # --- Settings Management ---
        elif data == "admin_settings":
            await query.answer()
            try:
                qr_url = db.get_setting("qr_image")
                qr_status = "Set" if qr_url and qr_url != "None" else "Not Set"
                upi = db.get_setting("upi_id")
                support = db.get_setting("support_user")
                dl_link = db.get_setting("global_channel_link", "Not Set")
                
                insult_raw = db.get_setting("unauth_msg", "")
                insult_clean = re.sub(r'<[^>]+>', '', insult_raw)
                insult_preview = insult_clean[:40] + "..." if len(insult_clean) > 40 else insult_clean
                
                qr79_status = "Set ✅" if db.get_setting("qr_79") not in (None, "None", "") else "Not Set ❌"
                qr189_status = "Set ✅" if db.get_setting("qr_189") not in (None, "None", "") else "Not Set ❌"
                qr349_status = "Set ✅" if db.get_setting("qr_349") not in (None, "None", "") else "Not Set ❌"
                text = (
                    f"<blockquote><b>{ce('settings')} STORE SETTINGS</b></blockquote>\n\n"
                    f"<code>UPI ID       : {upi}\n"
                    f"Support User : {support}\n"
                    f"QR ₹79       : {qr79_status}\n"
                    f"QR ₹189      : {qr189_status}\n"
                    f"QR ₹349      : {qr349_status}\n"
                    f"Download Link: {dl_link}</code>\n\n"
                    f"<b>Insult Msg:</b>\n<i>{insult_preview}</i>\n"
                    f"{get_line(12)}\n"
                    f"<i>Choose a setting to modify below:</i>"
                )
                buttons = [
                    [InlineKeyboardButton(f"{ce_button('pencil')} Edit UPI ID", callback_data="adm_set_upi"),
                     InlineKeyboardButton(f"{ce_button('pencil')} Edit Support User", callback_data="adm_set_sup")],
                    [InlineKeyboardButton(f"{ce_button('pencil')} QR ₹79", callback_data="adm_set_qr79"),
                     InlineKeyboardButton(f"{ce_button('pencil')} QR ₹189", callback_data="adm_set_qr189"),
                     InlineKeyboardButton(f"{ce_button('pencil')} QR ₹349", callback_data="adm_set_qr349")],
                    [InlineKeyboardButton(f"{ce_button('pencil')} Edit Insult Msg", callback_data="adm_set_msg")],
                    [InlineKeyboardButton(f"{ce_button('link')} Edit Download Channel", callback_data="adm_set_dl_link")],
                    [InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")]
                ]
                await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
                await safe_edit_text(update, context, f"<blockquote>{ce('fail')} Error loading settings. Check logs.</blockquote>", back_kb("admin_main"))

        # --- FAQ / TOS / HOWTO Edit ---
        elif data == "admin_faq":
            await query.answer()
            text = f"<blockquote><b>{ce('memo')} CONTENT MANAGEMENT</b></blockquote>\n\nUpdate the texts shown to users in the FAQ, TOS, and How To Use sections."
            buttons = [[InlineKeyboardButton(f"{ce_button('pencil')} Edit FAQ", callback_data="adm_edit_faq"), 
                 InlineKeyboardButton(f"{ce_button('pencil')} Edit TOS", callback_data="adm_edit_tos")],[InlineKeyboardButton(f"{ce_button('pencil')} Edit How-To Text", callback_data="adm_edit_howto_text"),
                 InlineKeyboardButton(f"{ce_button('link')} Edit How-To Video", callback_data="adm_edit_howto_vid")],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # --- Approvals (Funds) ---
        elif data == "admin_approvals":
            await query.answer()
            reqs = db.get_pending_fund_requests()
            if not reqs:
                await safe_edit_text(update, context, f"<blockquote>{ce('success')} No pending fund requests.</blockquote>", back_kb("admin_main"))
                return
            
            r = reqs[0]
            amt_sel = r.get('amount_selected', 0)
            amt_text = f"₹{amt_sel}" if amt_sel else "Unknown"
            text = (
                f"<blockquote><b>{ce('card')} PAYMENT SCREENSHOT REQUEST</b></blockquote>\n\n"
                f"<code>Req ID  : {r['id']}\n"
                f"User    : @{r.get('username')} ({r['user_id']})\n"
                f"Name    : {r.get('first_name')}\n"
                f"Amount  : {amt_text}\n"
                f"Date    : {r['request_date'][:19]}</code>\n"
                f"{get_line(12)}\n"
                f"<i>{ce('warning')} Check the screenshot above. Approve or Reject?</i>"
            )
            buttons = [
                [InlineKeyboardButton(f"{ce_button('success')} ✅ Approve ₹{amt_sel}", callback_data=f"adm_appr_{r['id']}"),
                 InlineKeyboardButton(f"{ce_button('fail')} ❌ Reject", callback_data=f"adm_rej_{r['id']}")],
                [InlineKeyboardButton(f"{ce_button('right')} Skip for now", callback_data="admin_main")]
            ]
            photo_id = r.get('photo_file_id')
            if photo_id:
                try:
                    await query.message.delete()
                except: pass
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo_id,
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode=ParseMode.HTML
                )
            else:
                await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_appr_"):
            await query.answer()
            req_id = int(data.split("_")[2])
            req = db.get_fund_request(req_id)
            amt_sel = req.get('amount_selected', 0)
            context.user_data['fund_req_id'] = req_id
            context.user_data['fund_preloaded_amt'] = amt_sel
            if amt_sel:
                hint = f"<blockquote>{ce('money')} User selected ₹{amt_sel}. Send amount in INR to credit (or just type <b>{amt_sel}</b> to confirm):</blockquote>"
            else:
                hint = f"<blockquote>{ce('money')} How much amount (in INR) to credit? Send number in chat.</blockquote>"
            await safe_edit_text(update, context, hint, cancel_kb())

        elif data.startswith("adm_rej_"):
            await query.answer()
            req_id = int(data.split("_")[2])
            r = db.get_fund_request(req_id)
            if r and r.get('status') == 'PENDING':
                db.update_fund_request(req_id, 'REJECTED')
                db.log_admin_action(user_id, "Rejected UTR", f"ReqID: {req_id}")
                try: await context.bot.send_message(r['user_id'], f"<blockquote>{ce('fail')} Your fund request with UTR <code>{r['utr']}</code> was rejected.</blockquote>", parse_mode=ParseMode.HTML)
                except: pass
            await safe_edit_text(update, context, "<blockquote>Request Rejected.</blockquote>", back_kb("admin_approvals"))

        # --- Support Tickets ---
        elif data == "admin_tickets":
            await query.answer()
            tkts = db.get_open_tickets()
            if not tkts:
                await safe_edit_text(update, context, f"<blockquote>{ce('success')} No open support tickets.</blockquote>", back_kb("admin_main"))
                return
            
            t = tkts[0]
            text = (
                f"<blockquote><b>{ce('ticket')} OPEN TICKET #{t['id']}</b></blockquote>\n\n"
                f"<b>User ID:</b> <code>{t['user_id']}</code>\n"
                f"<b>Message:</b>\n<i>{t['message']}</i>\n"
                f"{get_line(12)}"
            )
            buttons = [[InlineKeyboardButton(f"{ce_button('chat')} Reply & Close", callback_data=f"adm_tkt_{t['id']}")],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_main")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
            
    except Exception as e:
        logger.error(f"Error in handle_admin_callbacks: {traceback.format_exc()}")
        await query.answer("An internal error occurred.", show_alert=True)

# ==============================================================================
# 7. CONVERSATION RECEIVERS
# ==============================================================================

async def cancel_conv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels any ongoing process cleanly."""
    await update.callback_query.answer("Cancelled.")
    if update.effective_user.id in ADMIN_IDS:
        await safe_edit_text(update, context, "<blockquote>Process Cancelled.</blockquote>", admin_menu_kb())
    else:
        await safe_edit_text(update, context, "<blockquote>Process Cancelled.</blockquote>", main_menu_kb())
    context.user_data.clear()
    return ConversationHandler.END

# ----------------- USER CONVERSATIONS -----------------

@verification_required
async def prompt_utr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('warning')} Please type your 12-digit UTR/Reference number in the chat now.</b></blockquote>", cancel_kb())
    return WAIT_FOR_UTR

async def receive_utr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utr = update.message.text.strip()
    user_id = update.effective_user.id
    if len(utr) < 8:
        await update.message.reply_text(f"<blockquote>{ce('fail')} Invalid UTR. Please try again or cancel.</blockquote>", reply_markup=cancel_kb(), parse_mode=ParseMode.HTML)
        return WAIT_FOR_UTR
    amt = context.user_data.get('pay_amount', 0)
    req_id = db.create_fund_request(user_id, f"utr_{utr}", int(amt))
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Submitted Successfully!</b></blockquote>", reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)
    for admin in ADMIN_IDS:
        try: await context.bot.send_message(admin, f"<blockquote><b>{ce('bell')} NEW FUND REQUEST</b></blockquote>\nUser: {update.effective_user.username} (<code>{user_id}</code>)\nUTR: <code>{utr}</code>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{ce_button('success')} Review Now", callback_data="admin_approvals")]]))
        except: pass
    return ConversationHandler.END

@verification_required
async def prompt_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    try:
        amount_inr = int(data.split("_")[2])
    except:
        amount_inr = 0
    context.user_data['pay_amount'] = amount_inr
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('outbox')} SEND PAYMENT SCREENSHOT</b></blockquote>\n\n"
        f"<i>Please send your payment screenshot as a photo now.</i>\n"
        f"<b>Amount: ₹{amount_inr}</b>\n\n"
        f"<i>{ce('warning')} Admin will review and credit your wallet manually.</i>",
        cancel_kb()
    )
    return WAIT_FOR_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} Please send a <b>PHOTO</b> (screenshot), not a document or text.</blockquote>",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML
        )
        return WAIT_FOR_SCREENSHOT
    
    photo_file_id = update.message.photo[-1].file_id
    amount_inr = context.user_data.get('pay_amount', 0)
    amount_paise = int(amount_inr)
    
    req_id = db.create_fund_request(user_id, photo_file_id, amount_paise)
    
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>SCREENSHOT SUBMITTED!</b></blockquote>\n\n"
        f"<i>Your payment of ₹{amount_inr} is under review.\n"
        f"Admin will verify and credit your wallet shortly!</i>",
        reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML
    )
    
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    admin_caption = (
        f"<blockquote><b>{ce('bell')} NEW PAYMENT SCREENSHOT</b></blockquote>\n\n"
        f"<code>Req ID  : {req_id}\n"
        f"User    : @{username} ({user_id})\n"
        f"Name    : {first_name}\n"
        f"Amount  : ₹{amount_inr}</code>\n"
        f"{get_line(12)}\n"
        f"<i>Review screenshot above and approve or reject.</i>"
    )
    review_kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{ce_button('success')} Review Now", callback_data="admin_approvals")]])
    for admin in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin,
                photo=photo_file_id,
                caption=admin_caption,
                reply_markup=review_kb,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error forwarding screenshot to admin {admin}: {e}")
    
    context.user_data.clear()
    return ConversationHandler.END

@verification_required
async def prompt_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('ticket')} Type your message/issue below:</b></blockquote>", cancel_kb())
    return WAIT_FOR_TICKET

async def receive_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user_id = update.effective_user.id
    t_id = db.create_ticket(user_id, msg)
    await update.message.reply_text(f"<blockquote>{ce('success')} Ticket #{t_id} created successfully!</blockquote>", reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)
    for admin in ADMIN_IDS:
        try: await context.bot.send_message(admin, f"<blockquote><b>{ce('ticket')} NEW TICKET #{t_id}</b></blockquote>\nFrom: <code>{user_id}</code>\n\n<i>{msg}</i>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{ce_button('chat')} Reply", callback_data=f"adm_tkt_{t_id}")]]))
        except: pass
    return ConversationHandler.END

@verification_required
async def prompt_user_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('promo')} Enter Promo Code:</b></blockquote>\n\n<i>Type the promotional code in chat.</i>", cancel_kb())
    return WAIT_FOR_USER_PROMO

async def receive_user_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    user_id = update.effective_user.id
    success, msg, amount = db.redeem_promo(user_id, code)
    if success:
        await update.message.reply_text(f"<blockquote>{ce('success')} <b>PROMO CODE REDEEMED!</b></blockquote>\n\n₹{amount/100:.2f} has been added to your wallet.", reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"<blockquote>{ce('fail')} <b>{msg}</b></blockquote>", reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

# ----------------- ADMIN CONVERSATIONS -----------------

async def prompt_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    t_id = int(update.callback_query.data.split("_")[2])
    context.user_data['reply_tkt_id'] = t_id
    await safe_edit_text(update, context, f"<blockquote><b>Type your reply for Ticket #{t_id} in chat:</b></blockquote>", cancel_kb())
    return WAIT_FOR_ADMIN_TICKET_REPLY

async def receive_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = update.message.text
    t_id = context.user_data['reply_tkt_id']
    u_id = db.reply_ticket(t_id, reply)
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Reply sent and ticket closed.</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    try: await context.bot.send_message(u_id, f"<blockquote><b>{ce('ticket')} ADMIN REPLY FOR TICKET #{t_id}</b></blockquote>\n\n<i>{reply}</i>", parse_mode=ParseMode.HTML)
    except: pass
    return ConversationHandler.END

async def prompt_add_prod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('bag')} Send the New Product NAME:</b></blockquote>", cancel_kb())
    return WAIT_FOR_NEW_PROD_NAME

async def receive_prod_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_prod_name'] = update.message.text.strip()
    text = (
        f"<blockquote><b>{ce('edit')} Select a Description Preset for your product:</b></blockquote>\n\n"
        f"<i>Choose a beautiful preset description or type your own custom one!</i>"
    )
    buttons = [[InlineKeyboardButton(f"{ce_button('shield')} Safe / Main ID", callback_data="desc_preset_1")],[InlineKeyboardButton(f"{ce_button('fire')} Brutal / Root", callback_data="desc_preset_2")],[InlineKeyboardButton(f"{ce_button('apple')} iOS / eSign", callback_data="desc_preset_3")],[InlineKeyboardButton(f"{ce_button('name_icon')} 8 Level ID", callback_data="desc_preset_4")],[InlineKeyboardButton(f"{ce_button('mobile')} Drip Client (Non Root)", callback_data="desc_preset_5")],[InlineKeyboardButton(f"{ce_button('pencil')} Type Custom Description", callback_data="desc_custom")],[InlineKeyboardButton(f"{ce_button('fail')} Cancel", callback_data="cancel_conv")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    return WAIT_FOR_NEW_PROD_DESC

async def receive_prod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    if data == "desc_custom":
        await safe_edit_text(update, context, f"<blockquote><b>{ce('edit')} Type your Custom Description now (Use HTML tags like <b> or <i>):</b></blockquote>", cancel_kb())
        return WAIT_FOR_CUSTOM_DESC
    elif data.startswith("desc_preset_"):
        preset_id = data.split("_")[2]
        desc = get_preset_desc(preset_id)
        name = context.user_data.get('new_prod_name')
        db.add_product(name, desc)
        db.log_admin_action(update.effective_user.id, "Added Product", f"Name: {name}")
        await safe_edit_text(update, context, f"<blockquote>{ce('success')} <b>Product '{name}' Added Successfully!</b></blockquote>", admin_menu_kb())
        context.user_data.clear()
        return ConversationHandler.END

async def receive_custom_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = f"<blockquote><b>{update.message.text.strip()}</b></blockquote>"
    name = context.user_data.get('new_prod_name')
    db.add_product(name, desc)
    db.log_admin_action(update.effective_user.id, "Added Product", f"Name: {name}")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Product '{name}' Added Successfully!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    context.user_data.clear()
    return ConversationHandler.END

@verification_required
async def prompt_edit_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    p_id = int(update.callback_query.data.split("_")[3])
    context.user_data['editing_prod_id'] = p_id
    
    text = (
        f"<blockquote><b>{ce('edit')} Update Description:</b></blockquote>\n\n"
        f"<i>Choose a beautiful preset description or type your own!</i>"
    )
    buttons = [[InlineKeyboardButton(f"{ce_button('shield')} Safe / Main ID", callback_data="edit_preset_1")],[InlineKeyboardButton(f"{ce_button('fire')} Brutal / Root", callback_data="edit_preset_2")],[InlineKeyboardButton(f"{ce_button('apple')} iOS / eSign", callback_data="edit_preset_3")],[InlineKeyboardButton(f"{ce_button('name_icon')} 8 Level ID", callback_data="edit_preset_4")],[InlineKeyboardButton(f"{ce_button('mobile')} Drip Client (Non Root)", callback_data="edit_preset_5")],[InlineKeyboardButton(f"{ce_button('pencil')} Type Custom", callback_data="edit_custom")],[InlineKeyboardButton(f"{ce_button('fail')} Cancel", callback_data="cancel_conv")]
    ]
    await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
    return WAIT_FOR_EDIT_PROD_DESC

async def receive_edit_prod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prod_id = context.user_data.get('editing_prod_id')
    if not prod_id:
        await update.message.reply_text("Error: No product in editing state.", reply_markup=admin_menu_kb())
        return ConversationHandler.END

    if update.callback_query:
        await update.callback_query.answer()
        data = update.callback_query.data
        if data == "edit_custom":
            await safe_edit_text(update, context, f"<blockquote><b>{ce('pencil')} Type your Custom Description now (HTML allowed):</b></blockquote>", cancel_kb())
            return WAIT_FOR_EDIT_PROD_DESC
        elif data.startswith("edit_preset_"):
            preset_id = data.split("_")[2]
            desc = get_preset_desc(preset_id)
            db.update_product_description(prod_id, desc)
            db.log_admin_action(update.effective_user.id, "Edited Product Description", f"PID: {prod_id}")
            
            p = db.get_product(prod_id)
            text = f"<blockquote>{ce('success')} <b>Description Updated!</b></blockquote>\n\n<b>Name:</b> {p['name']}\n<b>Active:</b> {'Yes ' + ce('success') if p['is_active'] else 'No ' + ce('fail')}\n\n{p['description']}"
            buttons = [[InlineKeyboardButton(f"{ce_button('pencil')} Edit Description", callback_data=f"adm_edit_desc_{prod_id}")],[InlineKeyboardButton(f"{ce_button('loop')} Toggle Status", callback_data=f"adm_ptog_{prod_id}")],[InlineKeyboardButton(f"{ce_button('bag')} Manage Plans", callback_data=f"adm_plans_{prod_id}")],[InlineKeyboardButton(f"{ce_button('fail')} Delete Product", callback_data=f"adm_delprod_{prod_id}")],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_products")]]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
            context.user_data.clear()
            return ConversationHandler.END
    else:
        new_desc = f"<blockquote><b>{update.message.text}</b></blockquote>"
        db.update_product_description(prod_id, new_desc)
        db.log_admin_action(update.effective_user.id, "Edited Product Description", f"PID: {prod_id}")
        
        p = db.get_product(prod_id)
        text = f"<blockquote>{ce('success')} <b>Description Updated!</b></blockquote>\n\n<b>Name:</b> {p['name']}\n<b>Active:</b> {'Yes ' + ce('success') if p['is_active'] else 'No ' + ce('fail')}\n\n{p['description']}"
        buttons = [[InlineKeyboardButton(f"{ce_button('pencil')} Edit Description", callback_data=f"adm_edit_desc_{prod_id}")],[InlineKeyboardButton(f"{ce_button('loop')} Toggle Status", callback_data=f"adm_ptog_{prod_id}")],[InlineKeyboardButton(f"{ce_button('bag')} Manage Plans", callback_data=f"adm_plans_{prod_id}")],[InlineKeyboardButton(f"{ce_button('fail')} Delete Product", callback_data=f"adm_delprod_{prod_id}")],[InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_products")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        context.user_data.clear()
        return ConversationHandler.END

@verification_required
async def prompt_set_dl_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('link')} Send the new Download Channel Link:</b></blockquote>", cancel_kb())
    return WAIT_FOR_PROD_LINK

async def receive_set_dl_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting('global_channel_link', update.message.text.strip())
    db.log_admin_action(update.effective_user.id, "Changed Download Link", "Setting Updated")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Download Channel Link Updated!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def prompt_add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    p_id = int(update.callback_query.data.split("_")[3])
    context.user_data['add_plan_pid'] = p_id
    await safe_edit_text(update, context, f"<blockquote><b>{ce('time')} Send duration string (e.g. 7 Days or 1 Month):</b></blockquote>", cancel_kb())
    return WAIT_FOR_PLAN_DUR

async def receive_plan_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_plan_dur'] = update.message.text.strip()
    await update.message.reply_text(f"<blockquote><b>{ce('money')} Send price in INR (e.g. 150 for ₹150):</b></blockquote>", reply_markup=cancel_kb(), parse_mode=ParseMode.HTML)
    return WAIT_FOR_PLAN_PRICE

async def receive_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(float(update.message.text.strip()) * 100)
        prod_id = context.user_data['add_plan_pid']
        db.add_plan(prod_id, context.user_data['add_plan_dur'], price)
        db.log_admin_action(update.effective_user.id, "Added Plan", f"PID: {prod_id}")
        
        plans = db.get_plans(prod_id)
        text = f"<blockquote>{ce('success')} <b>Plan Added Successfully!</b></blockquote>\n\n<blockquote><b>📋 MANAGE PLANS</b></blockquote>\n<i>Click a plan to delete it. Add another below.</i>\n{get_line(12)}"
        buttons = []
        for pl in plans:
            buttons.append([InlineKeyboardButton(f"{ce_button('fail')} {pl['duration']} - ₹{pl['price']/100:.2f}", callback_data=f"adm_plan_del_{pl['id']}")])
        buttons.append([InlineKeyboardButton(f"{ce_button('plus')} Add New Plan", callback_data=f"adm_add_plan_{prod_id}")])
        buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back to Product", callback_data=f"adm_prod_{prod_id}")])
        
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text("Invalid Price.", reply_markup=admin_menu_kb())
        context.user_data.clear()
        return ConversationHandler.END

async def prompt_add_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    pl_id = int(update.callback_query.data.split("_")[2])
    context.user_data['add_key_plan'] = pl_id
    await safe_edit_text(update, context, f"<blockquote><b>{ce('key')} Send keys separated by newline (one key per line):</b></blockquote>", cancel_kb())
    return WAIT_FOR_ADD_KEYS

async def receive_add_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keys =[k.strip() for k in update.message.text.split('\n') if k.strip()]
    count = db.add_keys(context.user_data['add_key_plan'], keys)
    db.log_admin_action(update.effective_user.id, "Added Keys", f"Count: {count}")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Successfully added {count} unique keys!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    context.user_data.clear()
    return ConversationHandler.END

# Promos
async def prompt_create_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('promo')} Send the new Promo Code (e.g. VIP2026):</b></blockquote>", cancel_kb())
    return WAIT_FOR_PROMO_CODE

async def receive_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['promo_code'] = update.message.text.strip().upper()
    await update.message.reply_text(f"<blockquote><b>{ce('money')} Send reward amount in INR (e.g. 50):</b></blockquote>", reply_markup=cancel_kb(), parse_mode=ParseMode.HTML)
    return WAIT_FOR_PROMO_REWARD

async def receive_promo_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['promo_reward'] = int(float(update.message.text.strip()) * 100)
        await update.message.reply_text(f"<blockquote><b>{ce('user')} Send max uses (e.g. 100 for 100 users):</b></blockquote>", reply_markup=cancel_kb(), parse_mode=ParseMode.HTML)
        return WAIT_FOR_PROMO_USES
    except:
        await update.message.reply_text("Invalid amount.", reply_markup=admin_menu_kb())
        return ConversationHandler.END

async def receive_promo_uses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uses = int(update.message.text.strip())
        code = context.user_data['promo_code']
        reward = context.user_data['promo_reward']
        if db.create_promo(code, reward, uses):
            await update.message.reply_text(f"<blockquote>{ce('success')} <b>Promo Code <code>{code}</code> Created!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"<blockquote>{ce('fail')} <b>Code already exists!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text("Invalid number.", reply_markup=admin_menu_kb())
    context.user_data.clear()
    return ConversationHandler.END

# FAQ & TOS & HOWTO
async def prompt_edit_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('memo')} Send the new FAQ Text (HTML supported):</b></blockquote>", cancel_kb())
    return WAIT_FOR_FAQ

async def receive_edit_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting("faq_text", update.message.text)
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>FAQ Updated Successfully!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def prompt_edit_tos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('memo')} Send the new Terms of Service (TOS) Text:</b></blockquote>", cancel_kb())
    return WAIT_FOR_TOS

async def receive_edit_tos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting("tos_text", update.message.text)
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>TOS Updated Successfully!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def prompt_edit_howto_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('memo')} Send the new HOW TO USE Text (HTML supported):</b></blockquote>", cancel_kb())
    return WAIT_FOR_HOW_TO_TEXT

async def receive_howto_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting("how_to_text", update.message.text)
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>How To Use Text Updated Successfully!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def prompt_edit_howto_vid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('link')} Send the new HOW TO USE Video URL:</b></blockquote>", cancel_kb())
    return WAIT_FOR_HOW_TO_VIDEO

async def receive_howto_vid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting("how_to_video", update.message.text.strip())
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>How To Use Video Link Updated Successfully!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

# Basic Settings
@verification_required
async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('broadcast')} Send the message you want to broadcast:</b></blockquote>", cancel_kb())
    return WAIT_FOR_BROADCAST

async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    conn = db.get_connection()
    users = conn.execute("SELECT user_id FROM users WHERE verified=1").fetchall()
    conn.close()
    sent, failed = 0, 0
    await update.message.reply_text("Broadcast started... (This may take a moment).")
    for u in users:
        try:
            await context.bot.send_message(u['user_id'], msg, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except: failed += 1
    db.log_admin_action(update.effective_user.id, "Broadcast", f"Sent: {sent}, Failed: {failed}")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Broadcast Finished.</b>\nSent: {sent}\nFailed: {failed}</blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@verification_required
async def prompt_set_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, "<blockquote><b>Send the new UPI ID in chat:</b></blockquote>", cancel_kb())
    return WAIT_FOR_SETTING_UPI

async def receive_set_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting('upi_id', update.message.text.strip())
    db.log_admin_action(update.effective_user.id, "Changed UPI", "Setting Updated")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>UPI ID Updated!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@verification_required
async def prompt_set_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, "<blockquote><b>Please send the QR code as a PHOTO (not a link).</b></blockquote>", cancel_kb())
    return WAIT_FOR_SETTING_QR

async def receive_set_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file_id = photo.file_id
    db.set_setting('qr_image', file_id)
    db.log_admin_action(update.effective_user.id, "Changed QR Image", "Setting Updated")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>QR Image Updated!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@verification_required
async def prompt_set_qr79(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('card')} Send the QR Code image for <b>₹79</b> as a PHOTO:</b></blockquote>", cancel_kb())
    return WAIT_FOR_QR_79

async def receive_set_qr79(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    db.set_setting('qr_79', photo.file_id)
    db.log_admin_action(update.effective_user.id, "Changed QR ₹79", "Setting Updated")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>QR Code for ₹79 Updated!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@verification_required
async def prompt_set_qr189(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('card')} Send the QR Code image for <b>₹189</b> as a PHOTO:</b></blockquote>", cancel_kb())
    return WAIT_FOR_QR_189

async def receive_set_qr189(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    db.set_setting('qr_189', photo.file_id)
    db.log_admin_action(update.effective_user.id, "Changed QR ₹189", "Setting Updated")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>QR Code for ₹189 Updated!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@verification_required
async def prompt_set_qr349(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, f"<blockquote><b>{ce('card')} Send the QR Code image for <b>₹349</b> as a PHOTO:</b></blockquote>", cancel_kb())
    return WAIT_FOR_QR_349

async def receive_set_qr349(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    db.set_setting('qr_349', photo.file_id)
    db.log_admin_action(update.effective_user.id, "Changed QR ₹349", "Setting Updated")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>QR Code for ₹349 Updated!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@verification_required
async def prompt_set_sup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, "<blockquote><b>Send the new Support Username (e.g. @YourAdmin):</b></blockquote>", cancel_kb())
    return WAIT_FOR_SETTING_SUP

async def receive_set_sup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting('support_user', update.message.text.strip())
    db.log_admin_action(update.effective_user.id, "Changed Support User", "Setting Updated")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Support Username Updated!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@verification_required
async def prompt_set_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, "<blockquote><b>Send new Unauthorized Action Alert (Insult Message):</b></blockquote>", cancel_kb())
    return WAIT_FOR_SETTING_MSG

async def receive_set_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting('unauth_msg', update.message.text.strip())
    db.log_admin_action(update.effective_user.id, "Changed Insult Msg", "Setting Updated")
    await update.message.reply_text(f"<blockquote>{ce('success')} <b>Insult Message Updated!</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@verification_required
async def prompt_manual_bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, "<blockquote><b>Send the Telegram User ID to add funds to:</b></blockquote>", cancel_kb())
    return WAIT_FOR_MANUAL_BAL_USER

async def receive_manual_bal_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        if not db.get_user(uid):
            await update.message.reply_text("User not found in DB.", reply_markup=admin_menu_kb())
            return ConversationHandler.END
        context.user_data['man_bal_uid'] = uid
        await update.message.reply_text("<blockquote><b>Send amount in INR to add (e.g. 500):</b></blockquote>", reply_markup=cancel_kb(), parse_mode=ParseMode.HTML)
        return WAIT_FOR_MANUAL_BAL_AMT
    except:
        await update.message.reply_text("Invalid ID.", reply_markup=admin_menu_kb())
        return ConversationHandler.END

async def receive_manual_bal_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text.strip())
        paise = int(amt * 100)
        uid = context.user_data['man_bal_uid']
        db.update_balance(uid, paise)
        db.log_admin_action(update.effective_user.id, "Manual Balance Add", f"UID: {uid}, Amt: {amt}")
        await update.message.reply_text(f"<blockquote>{ce('success')} <b>Added ₹{amt} to User {uid}.</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
        try: await context.bot.send_message(uid, f"<blockquote>{ce('success')} <b>FUNDS ADDED!</b></blockquote>\n\n₹{amt:.2f} was added to your wallet by admin.", parse_mode=ParseMode.HTML)
        except: pass
    except:
        await update.message.reply_text("Invalid amount.", reply_markup=admin_menu_kb())
    return ConversationHandler.END

@verification_required
async def prompt_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, "<blockquote><b>Send the Telegram User ID to BAN:</b></blockquote>", cancel_kb())
    return WAIT_FOR_BAN_USER

async def receive_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text)
        db.ban_user(uid, 1)
        db.log_admin_action(update.effective_user.id, "Banned User", f"UID: {uid}")
        await update.message.reply_text(f"<blockquote>{ce('success')} <b>User <code>{uid}</code> is now BANNED.</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text("Invalid ID.", reply_markup=admin_menu_kb())
    return ConversationHandler.END

@verification_required
async def prompt_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(update, context, "<blockquote><b>Send the Telegram User ID to UNBAN:</b></blockquote>", cancel_kb())
    return WAIT_FOR_UNBAN_USER

async def receive_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text)
        db.ban_user(uid, 0)
        db.log_admin_action(update.effective_user.id, "Unbanned User", f"UID: {uid}")
        await update.message.reply_text(f"<blockquote>{ce('success')} <b>User <code>{uid}</code> is now UNBANNED.</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text("Invalid ID.", reply_markup=admin_menu_kb())
    return ConversationHandler.END

# ----------------- DYNAMIC CATCH-ALL (Fund Approvals & Quick Balance) -----------------
async def global_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('fund_req_id'):
        try:
            amt_inr = float(update.message.text)
            amt_paise = int(amt_inr * 100)
            req_id = context.user_data.pop('fund_req_id')
            context.user_data.pop('fund_preloaded_amt', None)
            req = db.get_fund_request(req_id)
            db.update_fund_request(req_id, 'APPROVED', amt_paise)
            db.update_balance(req.get('user_id'), amt_paise)
            db.log_admin_action(update.effective_user.id, "Approved Payment", f"ReqID: {req_id}, Amt: {amt_inr}")
            await update.message.reply_text(f"<blockquote>{ce('success')} <b>Approved and added ₹{amt_inr:.2f} to user.</b></blockquote>", reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML)
            try: await context.bot.send_message(req.get('user_id'), f"<blockquote>{ce('success')} <b>PAYMENT APPROVED!</b></blockquote>\n\n₹{amt_inr:.2f} added to your wallet. {ce('money')}", parse_mode=ParseMode.HTML)
            except: pass
        except Exception as e:
            logger.error(f"Global text handler error: {traceback.format_exc()}")
            await update.message.reply_text("Invalid amount. Request aborted.", reply_markup=admin_menu_kb())
    elif context.user_data.get('quickbal_active'):
        try:
            amt_inr = float(update.message.text)
            amt_paise = int(amt_inr * 100)
            uid = context.user_data.pop('quickbal_uid')
            context.user_data.pop('quickbal_active', None)
            db.update_balance(uid, amt_paise)
            db.log_admin_action(update.effective_user.id, "Quick Balance Add", f"UID: {uid}, Amt: {amt_inr}")
            u = db.get_user(uid)
            await update.message.reply_text(
                f"<blockquote>{ce('success')} <b>Added ₹{amt_inr:.2f} to user <code>{uid}</code>.</b></blockquote>\n"
                f"New balance: ₹{u.get('balance',0)/100:.2f}",
                reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML
            )
            try: await context.bot.send_message(uid, f"<blockquote>{ce('success')} <b>BALANCE ADDED!</b></blockquote>\n\n₹{amt_inr:.2f} has been added to your wallet by Admin. {ce('money')}", parse_mode=ParseMode.HTML)
            except: pass
        except Exception as e:
            logger.error(f"Quick balance handler error: {e}")
            context.user_data.pop('quickbal_active', None)
            await update.message.reply_text("Invalid amount.", reply_markup=admin_menu_kb())


# ==============================================================================
# 9. MAIN APPLICATION BUILDER & EXECUTION
# ==============================================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))

    # --- ADMIN CONVERSATION HANDLER ---
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_broadcast, pattern="^admin_broadcast$"),
            CallbackQueryHandler(prompt_set_upi, pattern="^adm_set_upi$"),
            CallbackQueryHandler(prompt_set_qr, pattern="^adm_set_qr$"),
            CallbackQueryHandler(prompt_set_qr79, pattern="^adm_set_qr79$"),
            CallbackQueryHandler(prompt_set_qr189, pattern="^adm_set_qr189$"),
            CallbackQueryHandler(prompt_set_qr349, pattern="^adm_set_qr349$"),
            CallbackQueryHandler(prompt_set_sup, pattern="^adm_set_sup$"),
            CallbackQueryHandler(prompt_set_msg, pattern="^adm_set_msg$"),
            CallbackQueryHandler(prompt_ban, pattern="^adm_ban_usr$"),
            CallbackQueryHandler(prompt_unban, pattern="^adm_unban_usr$"),
            CallbackQueryHandler(prompt_manual_bal, pattern="^adm_add_bal$"),
            CallbackQueryHandler(prompt_add_prod, pattern="^adm_add_prod$"),
            CallbackQueryHandler(prompt_add_plan, pattern="^adm_add_plan_"),
            CallbackQueryHandler(prompt_add_keys, pattern="^adm_kplan_"),
            CallbackQueryHandler(prompt_ticket_reply, pattern="^adm_tkt_"),
            CallbackQueryHandler(prompt_create_promo, pattern="^adm_create_promo$"),
            CallbackQueryHandler(prompt_edit_faq, pattern="^adm_edit_faq$"),
            CallbackQueryHandler(prompt_edit_tos, pattern="^adm_edit_tos$"),
            CallbackQueryHandler(prompt_edit_desc, pattern="^adm_edit_desc_"),
            CallbackQueryHandler(prompt_set_dl_link, pattern="^adm_set_dl_link$"),
            CallbackQueryHandler(prompt_edit_howto_text, pattern="^adm_edit_howto_text$"),
            CallbackQueryHandler(prompt_edit_howto_vid, pattern="^adm_edit_howto_vid$"),
        ],
        states={
            WAIT_FOR_BROADCAST:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast)],
            WAIT_FOR_SETTING_UPI:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_upi)],
            WAIT_FOR_SETTING_QR:[MessageHandler(filters.PHOTO, receive_set_qr)],
            WAIT_FOR_QR_79:[MessageHandler(filters.PHOTO, receive_set_qr79)],
            WAIT_FOR_QR_189:[MessageHandler(filters.PHOTO, receive_set_qr189)],
            WAIT_FOR_QR_349:[MessageHandler(filters.PHOTO, receive_set_qr349)],
            WAIT_FOR_SETTING_SUP:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_sup)],
            WAIT_FOR_SETTING_MSG:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_msg)],
            WAIT_FOR_BAN_USER:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban)],
            WAIT_FOR_UNBAN_USER:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_unban)],
            WAIT_FOR_MANUAL_BAL_USER:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_manual_bal_user)],
            WAIT_FOR_MANUAL_BAL_AMT:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_manual_bal_amt)],
            WAIT_FOR_NEW_PROD_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prod_name)],
            WAIT_FOR_NEW_PROD_DESC:[CallbackQueryHandler(receive_prod_desc, pattern="^desc_")],
            WAIT_FOR_CUSTOM_DESC:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_desc)],
            WAIT_FOR_EDIT_PROD_DESC:[
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_prod_desc),
                CallbackQueryHandler(receive_edit_prod_desc, pattern="^edit_")
            ],
            WAIT_FOR_PROD_LINK:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_dl_link)],
            WAIT_FOR_PLAN_DUR:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_dur)],
            WAIT_FOR_PLAN_PRICE:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_price)],
            WAIT_FOR_ADD_KEYS:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_keys)],
            WAIT_FOR_ADMIN_TICKET_REPLY:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ticket_reply)],
            WAIT_FOR_PROMO_CODE:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_promo_code)],
            WAIT_FOR_PROMO_REWARD:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_promo_reward)],
            WAIT_FOR_PROMO_USES:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_promo_uses)],
            WAIT_FOR_FAQ:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_faq)],
            WAIT_FOR_TOS:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_tos)],
            WAIT_FOR_HOW_TO_TEXT:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_howto_text)],
            WAIT_FOR_HOW_TO_VIDEO:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_howto_vid)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv_callback, pattern="^cancel_conv$")],
        per_message=False,
        allow_reentry=True
    )
    app.add_handler(admin_conv)

    # --- USER CONVERSATION HANDLER ---
    user_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_utr, pattern="^submit_utr$"),
            CallbackQueryHandler(prompt_screenshot, pattern="^submit_screenshot_"),
            CallbackQueryHandler(prompt_ticket, pattern="^user_ticket$"),
            CallbackQueryHandler(prompt_user_promo, pattern="^user_promo$"),
        ],
        states={
            WAIT_FOR_UTR:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_utr)],
            WAIT_FOR_SCREENSHOT:[
                MessageHandler(filters.PHOTO, receive_screenshot),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_screenshot),
            ],
            WAIT_FOR_TICKET:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ticket)],
            WAIT_FOR_USER_PROMO:[MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_promo)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv_callback, pattern="^cancel_conv$")],
        per_message=False,
        allow_reentry=True
    )
    app.add_handler(user_conv)
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_handler))
    app.add_handler(CallbackQueryHandler(handle_user_callbacks, pattern="^user_|^buy_|^confirm_buy_|^submit_utr$|^pay_|^submit_screenshot_"))
    app.add_handler(CallbackQueryHandler(handle_admin_callbacks, pattern="^admin_|^adm_"))

    print("🔥 Bot is successfully starting... (Mega Enterprise Edition V11) 🔥")

    port = int(os.environ.get("PORT", 8080))

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is alive!")
        def log_message(self, format, *args):
            pass

    def run_health_server():
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"Keep-alive server started on port {port}")
        server.serve_forever()

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    app.run_polling()

if __name__ == "__main__":
    main()