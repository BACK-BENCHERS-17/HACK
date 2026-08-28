#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hack Store Telegram Bot — MongoDB + Render edition.
Payment: FamPay SDK (PaymentManager) for UPI QR + Gmail IMAP verification.
"""

import asyncio
import base64
import html
import io
import logging
import math
import os
import re
import time
import traceback
import uuid
import warnings
from datetime import datetime, timedelta
from urllib.parse import quote

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    LinkPreviewOptions,
    WebAppInfo,
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import BadRequest, Conflict, NetworkError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)

from config import BOT_TOKEN, ADMIN_IDS
from database import DatabaseManager

# ── FamPay Payment SDK ──────────────────────────────────────────────────────
import sys
_sdk_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payment_template")
if os.path.isdir(_sdk_dir) and _sdk_dir not in sys.path:
    sys.path.insert(0, os.path.dirname(_sdk_dir))

try:
    from payment_template import PaymentManager
    from payment_template.exceptions import (
        ConfigurationError, DatabaseError as PMDatabaseError,
        GmailError, OrderNotFoundError, OrderStateError, VerificationError,
    )
    _PM_AVAILABLE = True
except ImportError as _pm_imp_err:
    _PM_AVAILABLE = False
    logger.warning(f"payment_template SDK not available: {_pm_imp_err} — QR/verify will use microservice fallback.")

_pm_singleton = None

def _get_pm():
    """Lazy singleton for the PaymentManager SDK."""
    global _pm_singleton
    if _pm_singleton is not None:
        return _pm_singleton
    if not _PM_AVAILABLE:
        return None
    try:
        _pm_singleton = PaymentManager()
        logger.info("PaymentManager SDK initialized successfully.")
        return _pm_singleton
    except Exception as e:
        logger.error(f"Failed to initialize PaymentManager: {e}")
        return None

# ==============================================================================
# 0. SYSTEM INITIALIZATION & LOGGING
# ==============================================================================
warnings.filterwarnings("ignore", category=UserWarning, module="telegram.ext.ConversationHandler")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ==============================================================================
# 1. CUSTOM EMOJI MAP & HELPERS
# ==============================================================================
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
    "pay": ("💸", "5433980745782759643"),
    "session": ("🔐", "5465443379917629504"),
    "pending": ("🕐", "5454415424319931791"),
}


def ce(name: str) -> str:
    if name in EMOJIS:
        fallback, em_id = EMOJIS[name]
        return f'<tg-emoji emoji-id="{em_id}">{fallback}</tg-emoji>'
    return "✨"


def ce_button(name: str) -> str:
    if name in EMOJIS:
        return EMOJIS[name][0]
    return "✨"


def get_line(n: int = 12) -> str:
    return ce("line") * n


# ==============================================================================
# 2. CONVERSATION STATES
# ==============================================================================
(
    WAIT_FOR_BROADCAST, WAIT_FOR_TICKET, WAIT_FOR_ADMIN_TICKET_REPLY,
    WAIT_FOR_NEW_PROD_NAME, WAIT_FOR_NEW_PROD_DESC, WAIT_FOR_CUSTOM_DESC, WAIT_FOR_PLAN_DUR,
    WAIT_FOR_PLAN_PRICE, WAIT_FOR_ADD_KEYS, WAIT_FOR_SETTING_UPI, WAIT_FOR_SETTING_QR,
    WAIT_FOR_SETTING_SUP, WAIT_FOR_BAN_USER, WAIT_FOR_UNBAN_USER, WAIT_FOR_SETTING_MSG,
    WAIT_FOR_MANUAL_BAL_USER, WAIT_FOR_MANUAL_BAL_AMT, WAIT_FOR_PROMO_CODE, WAIT_FOR_PROMO_REWARD,
    WAIT_FOR_PROMO_USES, WAIT_FOR_USER_PROMO, WAIT_FOR_FAQ, WAIT_FOR_TOS,
    WAIT_FOR_EDIT_PROD_DESC, WAIT_FOR_PROD_LINK, WAIT_FOR_HOW_TO_TEXT, WAIT_FOR_HOW_TO_VIDEO,
    WAIT_FOR_RESELLER_USER, WAIT_FOR_RESELLER_DAYS, WAIT_FOR_RESELLER_DISCOUNT,
    WAIT_FOR_ADD_FUND_AMT,
    WAIT_FOR_ADD_STAFF, WAIT_FOR_REM_STAFF,
) = range(33)


# ==============================================================================
# 3. DATABASE INSTANCE + DEFAULT SETTINGS SEED
# ==============================================================================
db = DatabaseManager()

DEFAULT_SETTINGS = {
    "qr_image": None,
    "upi_id": "",
    "support_user": "@YourSupportHandle",
    "unauth_msg": (
        f"<blockquote><b>{ce('angry')} Aukaat mein reh! {ce('fail')}</b></blockquote>\n\n"
        f"<i>Ye command sirf admin ke liye hai.</i>\n\n"
        f"<b>Chup chap normal menu use kar.</b> {ce('admin')}"
    ),
    "default_pfp": "https://via.placeholder.com/300x300.png?text=NO+PROFILE+PIC",
    "maintenance_mode": "0",
    "global_channel_link": "https://t.me/YourDownloadChannel",
    "faq_text": "No FAQ set yet. Admin will update this soon.",
    "tos_text": "No Terms of Service set yet. Admin will update this soon.",
    "how_to_text": (
        f"<blockquote><b>{ce('books')} HOW TO USE BOT</b></blockquote>\n\n"
        f"<i>Learn how to purchase, download, and use our premium tools.</i>"
    ),
    "how_to_video": "https://t.me/YOUR_VIDEO_LINK_HERE",
}

async def post_init(application: Application):
    await db.seed_default_settings(DEFAULT_SETTINGS)

# ==============================================================================
# 4. PRESET PRODUCT DESCRIPTIONS
# ==============================================================================
def get_preset_desc(preset_id: str) -> str:
    line = get_line(14)
    presets = {
        "1": (
            f"<blockquote><b>{ce('shield')} SAFE INJECTOR [ MAIN ID SAFE ]</b></blockquote>\n\n"
            f"<i>An ultimate tool engineered for main accounts with multi-layer encryption.</i>\n\n"
            f"<b>{ce('star')} Premium Features:</b>\n"
            f"<b>{ce('success')} 100% Anti-Ban &amp; Anti-Blacklist Bypass</b>\n"
            f"<b>{ce('success')} ESP Line, Box, Skeleton &amp; Distance</b>\n"
            f"<b>{ce('success')} Legit Smooth Aimbot &amp; Auto-Headshot</b>\n"
            f"<b>{ce('success')} No Recoil &amp; Weapon Modifiers</b>\n\n"
            f"<b>{ce('warning')} Requirements:</b>\n"
            f"<b>{ce('rocket')} Non-Root / Root both supported</b>\n"
            f"<b>{ce('rocket')} Android 9 to 14 Compatible</b>\n"
            f"<b>{ce('rocket')} 3GB+ RAM Recommended</b>\n\n"
            f"<i>Note: Play safe, do not get manual reports!</i>\n{line}"
        ),
        "2": (
            f"<blockquote><b>{ce('fire')} BRUTAL MOD [ ROOT ONLY ]</b></blockquote>\n\n"
            f"<i>For aggressive players who want to dominate the lobby in seconds.</i>\n\n"
            f"<b>{ce('star')} Brutal Features:</b>\n"
            f"<b>{ce('success')} Deep Memory / Ptrace Injection</b>\n"
            f"<b>{ce('success')} Magic Bullet &amp; 360 Bullet Track</b>\n"
            f"<b>{ce('success')} Flash Speed, High Damage &amp; Fast Run</b>\n"
            f"<b>{ce('success')} Teleport &amp; Car Fly (Risky)</b>\n\n"
            f"<b>{ce('warning')} Requirements &amp; Warnings:</b>\n"
            f"<b>{ce('fail')} NOT safe for Main IDs (Smurf Only)</b>\n"
            f"<b>{ce('success')} Requires Magisk Root &amp; Zygisk Hide</b>\n\n"
            f"<i>Note: Long ban possible if overused!</i>\n{line}"
        ),
        "3": (
            f"<blockquote><b>{ce('apple')} iOS eSign &amp; Mod [ REVOKE FREE ]</b></blockquote>\n\n"
            f"<i>The ultimate iOS experience. Sideload our IPA directly without a computer.</i>\n\n"
            f"<b>{ce('star')} iOS Features:</b>\n"
            f"<b>{ce('success')} Premium Revoke-Free Certificate</b>\n"
            f"<b>{ce('success')} Built-in ESP, Radar &amp; Triggerbot</b>\n"
            f"<b>{ce('success')} Silent Aim &amp; Hardware Spoofer</b>\n"
            f"<b>{ce('success')} No Jailbreak Required at all!</b>\n\n"
            f"<b>{ce('warning')} Requirements:</b>\n"
            f"<b>{ce('success')} Supports iOS 14.0 to Latest 17.x</b>\n"
            f"<b>{ce('success')} DNS Anti-Revoke Profile Setup Needed</b>\n{line}"
        ),
        "4": (
            f"<blockquote><b>{ce('name_icon')} 8 LEVEL ID [ HIGH QUALITY ]</b></blockquote>\n\n"
            f"<i>High quality 8 level accounts ready for immediate use.</i>\n\n"
            f"<b>{ce('star')} Account Details:</b>\n"
            f"<b>{ce('success')} Level 8+ Guaranteed</b>\n"
            f"<b>{ce('success')} Clean History, No Bans</b>\n"
            f"<b>{ce('success')} Full Access Provided</b>\n"
            f"<b>{ce('success')} Usable for Smurf / Main</b>\n\n"
            f"<b>{ce('warning')} Notice:</b>\n"
            f"<b>{ce('rocket')} Change password immediately after purchase</b>\n"
            f"<b>{ce('rocket')} Bind your own email/number</b>\n{line}"
        ),
        "5": (
            f"<blockquote><b>{ce('mobile')} DRIP CLIENT [ NON ROOT ]</b></blockquote>\n\n"
            f"<i>Direct APK install &amp; play. No injector, no root needed!</i>\n\n"
            f"<b>{ce('star')} Features:</b>\n"
            f"<b>{ce('success')} Easy Installation (APK format)</b>\n"
            f"<b>{ce('success')} ESP Line, Box, Skeleton &amp; Distance</b>\n"
            f"<b>{ce('success')} Legit Smooth Aimbot &amp; Auto-Headshot</b>\n"
            f"<b>{ce('success')} No Recoil &amp; Weapon Modifiers</b>\n\n"
            f"<b>{ce('warning')} Warning &amp; Notice:</b>\n"
            f"<b>{ce('fail')} NOT 100% Anti-Ban.</b>\n"
            f"<b>{ce('rocket')} Play on secondary/smurf accounts only.</b>\n\n"
            f"<i>Note: Play safe, avoid manual reports!</i>\n{line}"
        ),
    }
    return presets.get(preset_id, "No description.")


# ==============================================================================
# 5. PAYMENT MICROSERVICE CLIENT
# ==============================================================================
def generate_order_id(plan_id: int, user_id: int) -> str:
    """Generate a unique order ID."""
    unique = uuid.uuid4().hex[:8].upper()
    return f"HACK-{plan_id}-{user_id}-{unique}"


async def qr_expiration_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to delete an expired QR message and notify the user."""
    job = context.job
    chat_id = job.data["chat_id"]
    message_id = job.data["message_id"]
    order_id = job.data["order_id"]

    # Check if order was already PAID to avoid deleting valid success screens
    req = await db.get_fund_request_by_order(order_id)
    if req and req.get("status") == "PAID":
        return

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"<blockquote><b>{ce('warning')} QR CODE EXPIRED</b></blockquote>\n\n"
            f"The payment QR for Order ID <code>{order_id}</code> has expired (5 minute limit).\n"
            f"If you still wish to purchase, please generate a new QR code from the store."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Back to Store", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")
        ]])
    )


# ==============================================================================
# 6. UI HELPERS & VERIFICATION DECORATOR
# ==============================================================================
def verification_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id

        is_maintenance = await db.get_setting("maintenance_mode", "0")
        if is_maintenance == "1" and user_id not in ADMIN_IDS:
            msg = (
                f"<blockquote><b>{ce('warning')} MAINTENANCE MODE ACTIVE</b></blockquote>\n\n"
                f"<i>The bot is currently undergoing server upgrades. Please check back later.</i>"
            )
            if update.callback_query:
                await update.callback_query.answer("Maintenance Mode", show_alert=True)
                await safe_edit_text(update, context, msg, None)
            else:
                await update.effective_message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

        # Super Admins bypass everything
        if user_id in ADMIN_IDS:
            return await func(update, context, *args, **kwargs)

        user = await db.get_user(user_id)
        if not user:
            await show_verification_prompt(update, context)
            return
        if not user.get("verified", 0):
            await show_verification_prompt(update, context)
            return
        if user.get("is_banned", 0):
            await update.effective_message.reply_text(
                f"<blockquote>{ce('poop')} <b>ACCOUNT BANNED</b>\nContact Admin to appeal.</blockquote>",
                parse_mode=ParseMode.HTML,
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def staff_required(func):
    """Decorator to restrict access to Admins or Staff."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id in ADMIN_IDS:
            return await func(update, context, *args, **kwargs)
        
        if await db.is_staff(user_id):
            return await func(update, context, *args, **kwargs)
            
        await update.effective_message.reply_text(
            f"<blockquote><b>{ce('angry')} ACCESS DENIED!</b></blockquote>\n\n"
            f"<i>This command is only for Staff or Admins.</i>",
            parse_mode=ParseMode.HTML
        )
        return
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
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=text,
            reply_markup=reply_markup, parse_mode=ParseMode.HTML,
        )
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.effective_user.id

    await db.add_user(user_id, update.effective_user.username, update.effective_user.first_name)

    user = await db.get_user(user_id)
    if user and user.get("verified", 0):
        await update.message.reply_text(
            f"<blockquote>{ce('success')} You are already verified.</blockquote>",
            reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML,
        )
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    await db.verify_user(user_id)

    try:
        phone_number = contact.phone_number
        first_name = contact.first_name
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        photo_id = (
            photos.photos[0][-1].file_id if photos.total_count > 0
            else await db.get_setting("default_pfp")
        )
        username = update.effective_user.username
        username_text = f"@{username}" if username else "N/A"

        admin_msg = (
            f"<blockquote><b>{ce('siren')} NEW VERIFIED USER {ce('siren')}</b></blockquote>\n\n"
            f"{ce('name_icon')} <b>Name:</b> <a href='tg://user?id={user_id}'>{first_name}</a>\n"
            f"{ce('link')} <b>Username:</b> {username_text}\n"
            f"{ce('memo')} <b>User ID:</b> <code>{user_id}</code>\n"
            f"{ce('contact')} <b>Phone:</b> <code>{phone_number}</code>\n"
            f"{get_line(12)}"
        )
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_photo(
                    chat_id=admin, photo=photo_id, caption=admin_msg, parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Error in contact_handler admin alert: {e}")

    try:
        await update.message.delete()
    except Exception:
        pass

    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Verification successful! Welcome to Hack Store.</b></blockquote>",
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML,
    )

    user = await db.get_user(user_id)
    bal = user.get("balance", 0) / 100
    welcome_text = _welcome_text(bal)
    await update.message.reply_text(welcome_text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)


def _welcome_text(bal: float) -> str:
    return (
        f"<blockquote><b>{ce('store')} WELCOME TO HACK STORE {ce('key')}</b></blockquote>\n\n"
        f"<i>Your ultimate destination for premium mods, cheats &amp; clients!</i> {ce('globe')}\n"
        f"{get_line(12)}\n"
        f"<blockquote><b>{ce('rocket')} PREMIUM FEATURES:</b>\n"
        f"<b>{ce('success')} Instant Key Delivery</b>\n"
        f"<b>{ce('card')} Secure Auto-Payment System</b>\n"
        f"<b>{ce('success')} 100% Anti-Ban Support</b></blockquote>\n"
        f"{get_line(12)}\n\n"
        f"<blockquote><b>{ce('money')} Your Balance: ₹{bal:.2f}</b></blockquote>\n\n"
        f"<b>Select an option from the menu below:</b>"
    )


# ==============================================================================
# 7. KEYBOARDS
# ==============================================================================
def _get_keypad_kb(current_val: str):
    """Generate numeric keypad buttons for custom amount entry."""
    kb = [
        [InlineKeyboardButton("1", callback_data="kp_1", style="default"), 
         InlineKeyboardButton("2", callback_data="kp_2", style="default"), 
         InlineKeyboardButton("3", callback_data="kp_3", style="default")],
        [InlineKeyboardButton("4", callback_data="kp_4", style="default"), 
         InlineKeyboardButton("5", callback_data="kp_5", style="default"), 
         InlineKeyboardButton("6", callback_data="kp_6", style="default")],
        [InlineKeyboardButton("7", callback_data="kp_7", style="default"), 
         InlineKeyboardButton("8", callback_data="kp_8", style="default"), 
         InlineKeyboardButton("9", callback_data="kp_9", style="default")],
        [InlineKeyboardButton(f"{ce_button('fail')} Clear", callback_data="kp_clear", style="danger"), 
         InlineKeyboardButton("0", callback_data="kp_0", style="default"), 
         InlineKeyboardButton(f"{ce_button('success')} Confirm", callback_data="kp_ok", style="success")],
        [InlineKeyboardButton("Back", callback_data="user_add_funds", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")]
    ]
    return kb


def main_menu_kb(web_app_url: str = None) -> InlineKeyboardMarkup:
    buttons = []
    
    # Add Web Store button if URL is provided (Telegram requires HTTPS for WebApp buttons)
    if web_app_url and web_app_url.startswith("https://"):
        buttons.append([InlineKeyboardButton("OPEN WEB STORE", web_app=WebAppInfo(url=web_app_url), icon_custom_emoji_id=EMOJIS["rocket"][1], style="primary")])

    buttons.extend([
        [InlineKeyboardButton("BUY HACK", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["cart"][1], style="primary"),
         InlineKeyboardButton("DOWNLOAD APK", callback_data="user_downloads", icon_custom_emoji_id=EMOJIS["disk"][1], style="primary")],
        [InlineKeyboardButton("ADD FUND", callback_data="user_add_funds", icon_custom_emoji_id=EMOJIS["money"][1], style="success"),
         InlineKeyboardButton("MY KEY", callback_data="user_my_keys_0", icon_custom_emoji_id=EMOJIS["key"][1], style="primary")],
        [InlineKeyboardButton("STOCK", callback_data="user_stock", icon_custom_emoji_id=EMOJIS["stock"][1], style="primary"),
         InlineKeyboardButton("PROFILE", callback_data="user_profile", icon_custom_emoji_id=EMOJIS["user"][1], style="primary")],
        [InlineKeyboardButton("HOW TO USE", callback_data="user_how_to", icon_custom_emoji_id=EMOJIS["mobile"][1], style="primary"),
         InlineKeyboardButton("SUPPORT", callback_data="user_contact", icon_custom_emoji_id=EMOJIS["contact"][1], style="primary")],
    ])
    return InlineKeyboardMarkup(buttons)


def back_kb(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=callback_data, icon_custom_emoji_id=EMOJIS["back"][1], style="danger")]])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Cancel Process", callback_data="cancel_conv", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")]])


async def admin_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    is_super = user_id in ADMIN_IDS
    
    buttons = []
    
    # Dashboard / Stats
    buttons.append([InlineKeyboardButton("Dashboard", callback_data="admin_stats", icon_custom_emoji_id=EMOJIS["stats"][1], style="primary")])
    
    if is_super:
        # Full Admin Options
        buttons.append([
            InlineKeyboardButton("Products", callback_data="admin_products", icon_custom_emoji_id=EMOJIS["bag"][1], style="primary"),
            InlineKeyboardButton("Keys", callback_data="admin_keys", icon_custom_emoji_id=EMOJIS["key"][1], style="primary")
        ])
        buttons.append([
            InlineKeyboardButton("Users", callback_data="admin_users", icon_custom_emoji_id=EMOJIS["user"][1], style="primary"),
            InlineKeyboardButton("Pending Payments", callback_data="admin_pending_payments", icon_custom_emoji_id=EMOJIS["pending"][1], style="primary")
        ])
    
    # Staff/Admin Broadcast
    buttons.append([
        InlineKeyboardButton("Broadcast", callback_data="admin_broadcast", icon_custom_emoji_id=EMOJIS["broadcast"][1], style="primary"),
        InlineKeyboardButton("Resellers", callback_data="admin_resellers", icon_custom_emoji_id=EMOJIS["shield"][1], style="primary") if is_super else InlineKeyboardButton("Tickets", callback_data="admin_tickets", icon_custom_emoji_id=EMOJIS["chat"][1], style="primary")
    ])

    if is_super:
        buttons.append([
            InlineKeyboardButton("Tickets", callback_data="admin_tickets", icon_custom_emoji_id=EMOJIS["chat"][1], style="primary"),
            InlineKeyboardButton("Settings", callback_data="admin_settings", icon_custom_emoji_id=EMOJIS["settings"][1], style="primary")
        ])
        buttons.append([
            InlineKeyboardButton("Staff Mgmt", callback_data="admin_staff_list", icon_custom_emoji_id=EMOJIS["admin"][1], style="primary"),
            InlineKeyboardButton("Maintenance", callback_data="adm_maintenance", icon_custom_emoji_id=EMOJIS["tools"][1], style="primary")
        ])
        buttons.append([
            InlineKeyboardButton("Backup DB", callback_data="adm_export_db", icon_custom_emoji_id=EMOJIS["disk"][1], style="primary")
        ])
    
    buttons.append([InlineKeyboardButton("Exit Admin", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
    
    return InlineKeyboardMarkup(buttons)


def pagination_kb(current_page: int, total_pages: int, prefix: str, back_cb: str):
    buttons = []
    nav = []
    if current_page > 0:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"{prefix}_{current_page-1}", icon_custom_emoji_id=EMOJIS["left"][1], style="default"))
    nav.append(InlineKeyboardButton(f"Page {current_page+1}/{total_pages}", callback_data="ignore", icon_custom_emoji_id=EMOJIS["memo"][1], style="default"))
    if current_page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next", callback_data=f"{prefix}_{current_page+1}", icon_custom_emoji_id=EMOJIS["right"][1], style="default"))
    if len(nav) > 1:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("Back", callback_data=back_cb, icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
    return buttons


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Helper to broadcast notifications to all configured ADMIN_IDS."""
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin_id}: {e}")


async def safe_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         text: str, reply_markup, **kwargs):
    query = update.callback_query
    try:
        if query.message.photo or query.message.video or query.message.document:
            await query.message.delete()
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=text,
                reply_markup=reply_markup, parse_mode=ParseMode.HTML, **kwargs,
            )
        else:
            await query.edit_message_text(
                text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, **kwargs,
            )
    except BadRequest as e:
        logger.warning(f"BadRequest in safe_edit_text: {e}")
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=text,
                reply_markup=reply_markup, parse_mode=ParseMode.HTML, **kwargs,
            )
        except Exception as ex:
            logger.error(f"Failed fallback in safe_edit_text: {ex}")


# ==============================================================================
# 8. USER HANDLERS
# ==============================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referrer_id = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].replace("ref_", ""))
            if referrer_id == user.id:
                referrer_id = None
        except Exception:
            pass

    is_new = await db.add_user(user.id, user.username, user.first_name, referrer_id)
    if is_new and referrer_id:
        try:
            alert_text = (
                f"<blockquote><b>{ce('gift')} NEW REFERRAL ALERT!</b></blockquote>\n\n"
                f"User <a href='tg://user?id={user.id}'><b>{user.first_name}</b></a> joined via your link!\n"
                f"<i>You earn <b>15% Commission</b> on their first purchase.</i>"
            )
            await context.bot.send_message(chat_id=referrer_id, text=alert_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    user_data = await db.get_user(user.id)
    if user_data.get("is_banned", 0):
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>ACCOUNT BANNED</b>\nContact Admin.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    if not user_data.get("verified", 0):
        await show_verification_prompt(update, context)
        return

    is_maintenance = await db.get_setting("maintenance_mode", "0")
    if is_maintenance == "1" and user.id not in ADMIN_IDS:
        await update.message.reply_text(
            f"<blockquote><b>{ce('warning')} MAINTENANCE MODE ACTIVE</b></blockquote>\n\n"
            f"<i>The bot is currently undergoing server upgrades. Please check back later.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    bal = user_data.get("balance", 0) / 100
    await update.message.reply_text(_welcome_text(bal), reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)


@verification_required
async def handle_user_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    try:
        # ── Main menu ──────────────────────────────────────────────────────────
        if data == "user_main":
            await query.answer()
            user_data = await db.get_user(user_id)
            bal = user_data.get("balance", 0) / 100
            await safe_edit_text(update, context, _welcome_text(bal), main_menu_kb())

        # ── Buy Hack ───────────────────────────────────────────────────────────
        elif data == "user_buy_hack":
            await query.answer()
            products = await db.get_active_products()
            if not products:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} No products available at the moment.</blockquote>",
                    back_kb("user_main"),
                )
                return
            text = (
                f"<blockquote><b>{ce('cart')} SELECT A HACK {ce('sparkle')}</b></blockquote>\n\n"
                f"<i>Browse our exclusive collection below:</i>\n{get_line(12)}"
            )
            buttons = [
                [InlineKeyboardButton(p['name'], callback_data=f"buy_prod_{p['id']}", icon_custom_emoji_id=EMOJIS["game"][1], style="primary")]
                for p in products
            ]
            buttons.append([InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])

            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("buy_prod_"):
            await query.answer()
            prod_id = int(data.split("_")[2])
            prod = await db.get_product(prod_id)
            plans = await db.get_plans(prod_id)
            if not plans:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} No active plans for <b>{prod.get('name', 'this product')}</b>.</blockquote>",
                    back_kb("user_buy_hack"),
                )
                return
            text = (
                f"<blockquote><b>{ce('game')} {prod['name']}</b></blockquote>\n\n"
                f"{prod['description']}\n\n"
                f"<i>{ce('time')} Choose your plan duration:</i>"
            )
            buttons = []
            for pl in plans:
                stock = await db.get_available_key_count(pl['id'])
                if stock > 0:
                    btn_text = f"{pl['duration']} — ₹{pl['price']/100:.2f}"
                    btn_cb = f"buy_plan_{pl['id']}"
                    icon_id = EMOJIS["star"][1]
                else:
                    btn_text = f"{pl['duration']} — SOLD OUT"
                    btn_cb = "ignore"
                    icon_id = EMOJIS["fail"][1]
                buttons.append([InlineKeyboardButton(btn_text, callback_data=btn_cb, icon_custom_emoji_id=icon_id, style="primary")])
            buttons.append([InlineKeyboardButton("Back", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("buy_plan_"):
            await query.answer()
            plan_id = int(data.split("_")[2])
            plan = await db.get_plan(plan_id)
            
            # Check for reseller discount
            original_price = plan['price']
            final_price = original_price
            discount_text = ""
            is_reseller, discount_perc = await db.is_active_reseller(user_id)
            
            if is_reseller:
                final_price = original_price * (1 - (discount_perc / 100))
                discount_text = f"<i>({ce('gift')} Reseller Discount: {discount_perc}% applied)</i>\n"

            text = (
                f"<blockquote><b>{ce('cart')} PURCHASE CONFIRMATION</b></blockquote>\n\n"
                f"<b>Product:</b> {plan['product_name']}\n"
                f"<b>Duration:</b> {plan['duration']}\n"
                f"<b>Price:</b> ₹{final_price/100:.2f} <s>₹{original_price/100:.2f}</s>\n"
                f"{discount_text}"
                f"{get_line(12)}\n"
                f"<i>Click below to generate your unique payment QR code (valid 5 min).</i>"
            )
            buttons = []
            user_data = await db.get_user(user_id)
            user_bal = user_data.get("balance", 0)
            
            if user_bal >= final_price:
                buttons.append([InlineKeyboardButton("PAY VIA WALLET BALANCE", callback_data=f"pay_bal_{plan_id}", icon_custom_emoji_id=EMOJIS["money"][1], style="success")])
            
            buttons.append([InlineKeyboardButton("GENERATE PAYMENT QR", callback_data=f"gen_qr_{plan_id}", icon_custom_emoji_id=EMOJIS["pay"][1], style="primary")])
            buttons.append([InlineKeyboardButton("CANCEL", callback_data=f"buy_prod_{plan['product_id']}", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")])
            
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Generate QR (PaymentManager SDK preferred, microservice fallback) ──
        elif data.startswith("gen_qr_"):
            await query.answer("Generating QR…")
            plan_id = int(data.split("_")[2])
            plan = await db.get_plan(plan_id)

            admin_upi = await db.get_setting("upi_id", "")
            if not admin_upi or "@" not in admin_upi:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} <b>UPI ID is not configured.</b>\n"
                    f"Admin must set a valid UPI ID in the Admin Panel first.</blockquote>",
                    back_kb("user_buy_hack"),
                )
                return

            # Check for reseller discount
            price_paise = float(plan['price'])
            is_reseller, discount_perc = await db.is_active_reseller(user_id)
            if is_reseller:
                price_paise = price_paise * (1 - (discount_perc / 100))

            price_inr = price_paise / 100
            payee = await db.get_setting("global_brand_name", "Hack Store") or "Hack Store"

            # ── Try PaymentManager SDK first ──────────────────────────────────
            pm = _get_pm()
            if pm:
                try:
                    # Ensure env vars are set for the SDK
                    _env_map = {
                        "DEFAULT_UPI_ID": admin_upi,
                        "DEFAULT_PAYEE_NAME": payee,
                    }
                    for k, v in _env_map.items():
                        if v:
                            os.environ[k] = v

                    order = await asyncio.to_thread(pm.create, user_id=user_id, amount=price_inr)
                    order_id = order.id
                    expires_at = order.expires_at.strftime("%d %b %Y, %I:%M %p IST")

                    # Store fund_request in DB with PENDING status (Paise)
                    await db.create_fund_request_with_order(user_id, order_id, plan_id, price_paise)

                    # Use PM's branded QR image (bytes)
                    qr_photo = io.BytesIO(order.qr_image)
                    qr_photo.name = f"{order_id}.png"

                    caption = (
                        f"<blockquote><b>{ce('card')} SCAN &amp; PAY ₹{price_inr:.2f}</b></blockquote>\n\n"
                        f"<b>{ce('1')} Scan the QR code below with any UPI app.</b>\n"
                        f"<b>{ce('2')} Pay exactly ₹{price_inr:.2f}.</b>\n"
                        f"<b>{ce('3')} After payment, click <u>I'VE PAID</u> below.</b>\n\n"
                        f"<i>{ce('warning')} QR expires at: <b>{expires_at}</b></i>\n"
                        f"<i>{ce('success')} Key will be delivered automatically after verification.</i>\n\n"
                        f"<code>Order ID: {order_id}</code>"
                    )
                    buttons = [
                        [InlineKeyboardButton("I'VE PAID", callback_data=f"verify_pay_{order_id}", icon_custom_emoji_id=EMOJIS["success"][1], style="success")],
                        [InlineKeyboardButton("Generate New QR", callback_data=f"gen_qr_{plan_id}", icon_custom_emoji_id=EMOJIS["refresh"][1], style="primary")],
                        [InlineKeyboardButton("Cancel", callback_data=f"buy_plan_{plan_id}", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
                    ]
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    msg = await context.bot.send_photo(
                        chat_id=user_id,
                        photo=qr_photo,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(buttons),
                        parse_mode=ParseMode.HTML,
                    )

                    # Schedule expiration job (15 minutes = 900 seconds).
                    context.job_queue.run_once(
                        qr_expiration_job,
                        when=900,
                        data={"chat_id": user_id, "message_id": msg.message_id, "order_id": order_id},
                    )
                    return

                except Exception as pm_err:
                    logger.error(f"PaymentManager create failed, falling back to microservice: {pm_err}")
                    # Fall through to microservice fallback below


        # ── Verify payment (user clicks I'VE PAID) ────────────────────────────
        elif data.startswith("verify_pay_"):
            await query.answer("Verifying payment…", show_alert=False)
            order_id  = data[len("verify_pay_"):]

            # ── Try PaymentManager SDK first ──────────────────────────────────
            pm = _get_pm()
            if pm:
                try:
                    result = await asyncio.to_thread(pm.verify, order_id)
                    logger.info(f"PM verify result for order={order_id}: verified={result.get('verified')} status={result.get('status')}")

                    if result.get("verified") and result.get("status") == "verified":
                        # Payment verified via PM — proceed with key delivery
                        utr = result.get("utr", "N/A")
                        txn_id = result.get("transaction_id", utr)
                        sender_name = result.get("sender_name", "Unknown")
                        paid_amount = result.get("amount", 0)
                        payment_time = result.get("payment_time_ist", "")

                        req = await db.get_fund_request_by_order(order_id)
                        if not req:
                            await query.answer("Order not found. Contact support.", show_alert=True)
                            return

                        # Anti-replay: if this UTR is already attached to a different order
                        if utr and utr != "N/A" and await db.is_utr_already_used(utr, except_order_id=order_id):
                            await db.update_fund_request_by_order(order_id, "REJECTED_DUPLICATE_UTR",
                                    utr=utr, transaction_id=txn_id, sender_name=sender_name,
                                    payment_time=payment_time)
                            await safe_edit_text(update, context,
                                f"<blockquote>{ce('fail')} <b>This payment reference (UTR) "
                                f"has already been used to claim a key.</b>\n\n"
                                f"<code>{order_id}</code></blockquote>", back_kb("user_main"))
                            return

                        # Handle balance top-up (FUND order)
                        if order_id.startswith("FUND"):
                            await db.update_fund_request_by_order(order_id, "APPROVED",
                                    utr=utr, transaction_id=txn_id, sender_name=sender_name,
                                    payment_time=payment_time)
                            fund_amt = float(req.get("amount_requested", 0)) / 100
                            await safe_edit_text(update, context,
                                f"<blockquote>{ce('success')} <b>FUNDS ADDED SUCCESSFULLY!</b></blockquote>\n\n"
                                f"₹{fund_amt:.2f} has been added to your wallet.\n"
                                f"<b>New Balance:</b> ₹{((await db.get_user(user_id)).get('balance', 0)/100):.2f}",
                                main_menu_kb())
                            return

                        # Check if key was already delivered by microservice fallback
                        if result.get("delivered_key"):
                            info = {
                                "key": result.get("delivered_key"),
                                "product": result.get("product_info", "Premium Hack").split(" - ")[0],
                                "duration": result.get("product_info", "N/A").split(" - ")[-1],
                                "expiry": (datetime.now() + timedelta(days=30)).isoformat()
                            }
                            success = True
                        else:
                            # Deliver key automatically via bot DB
                            success, msg, info = await db.purchase_key_automated(user_id, req["plan_id"])

                        if success:
                            await db.update_fund_request_by_order(order_id, "APPROVED",
                                    utr=utr, transaction_id=txn_id, sender_name=sender_name,
                                    payment_time=payment_time, key_value=info.get("key"))
                            key_text = (
                                f"<blockquote><b>{ce('success')} PAYMENT VERIFIED! {ce('star')}</b></blockquote>\n\n"
                                f"<b>Transaction ID:</b> <code>{txn_id}</code>\n"
                                f"<b>UTR:</b> <code>{utr}</code>\n"
                                f"{get_line(12)}\n"
                                f"<b>Product:</b> {info['product']}\n"
                                f"<b>Duration:</b> {info['duration']}\n"
                                f"<b>Expiry:</b> {info['expiry'][:10]}\n\n"
                                f"<blockquote><b>{ce('key')} YOUR PREMIUM KEY:</b></blockquote>\n"
                                f"<code>{info['key']}</code>\n\n"
                                f"<i>Thank you for your purchase! Enjoy! {ce('fire')}</i>"
                            )
                            try: await query.message.delete()
                            except Exception: pass
                            await context.bot.send_message(chat_id=user_id, text=key_text,
                                reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)

                            user_obj = await db.get_user(user_id)
                            uname = (user_obj.get("username") or "").lstrip("@")
                            fname = user_obj.get("first_name") or ""
                            plan_obj = await db.get_plan(req["plan_id"]) or {}
                            expected_amount = plan_obj.get("price", 0)
                            await notify_admins(context, (
                                f"<blockquote><b>{ce('success')} AUTO PAYMENT SUCCESS — KEY DELIVERED</b></blockquote>\n"
                                f"{get_line(12)}\n"
                                f"<b>User:</b> <code>{user_id}</code> ({fname} @{uname})\n"
                                f"<b>Order:</b> <code>{order_id}</code>\n"
                                f"<b>Amount:</b> ₹{expected_amount/100:.2f}\n"
                                f"<b>UTR:</b> <code>{utr}</code>\n"
                                f"<b>Txn ID:</b> <code>{txn_id}</code>\n"
                                f"<b>Sender:</b> {html.escape(str(sender_name))}\n"
                                f"<b>Delivered Key:</b> <code>{info['key']}</code>"))
                        else:
                            await db.update_fund_request_by_order(order_id, "PAID_NO_STOCK",
                                    utr=utr, transaction_id=txn_id, sender_name=sender_name,
                                    payment_time=payment_time)
                            await safe_edit_text(update, context,
                                f"<blockquote>{ce('warning')} <b>Payment received but key delivery failed: {msg}</b>\n"
                                f"Please contact support with Order ID: <code>{order_id}</code></blockquote>",
                                back_kb("user_main"))
                        return

                    elif result.get("status") in ("expired", "cancelled"):
                        _pm_orders.pop(order_id, None)
                        await query.answer(f"Order {result['status']}. Use /pay again.", show_alert=True)
                        return
                    else:
                        # Not verified yet — show popup alert so QR stays visible
                        msg = result.get("message", "UPI payments may take up to 2 minutes.")
                        if "not found" in msg.lower() or "no matching" in msg.lower():
                            msg = "Please wait a moment and try again. UPI payments may take up to 2 minutes."
                        elif "expired" in msg.lower():
                            msg = "This QR/order has expired. Please generate a new QR from the store."
                        alert = f"❌ Payment Not Received Yet\n\n{msg}\n\nOrder ID: {order_id}"[:200]
                        try:
                            await query.answer(alert, show_alert=True)
                        except Exception:
                            pass
                        return

                except Exception as pm_err:
                    logger.error(f"PM verify failed, falling back to microservice: {pm_err}")
                    # Fall through to microservice fallback


        # ── Downloads ─────────────────────────────────────────────────────────
        elif data == "user_downloads":
            await query.answer()
            channel_link = await db.get_setting("global_channel_link", "https://t.me/YourDownloadChannel")
            text = (
                f"<blockquote><b>{ce('disk')} DOWNLOAD PREMIUM APK &amp; FILES {ce('disk')}</b></blockquote>\n\n"
                f"<i>All our highly secured, premium, and updated files are securely hosted on our private channel!</i>\n"
                f"{get_line(12)}\n\n"
                f"<b>{ce('star')} WHAT YOU GET:</b>\n"
                f"<b>{ce('success')} Latest APK Updates</b>\n"
                f"<b>{ce('success')} 100% Virus Free &amp; Secure</b>\n"
                f"<b>{ce('success')} All Configs &amp; Scripts</b>\n"
                f"<b>{ce('success')} Complete Installation Guides</b>\n"
                f"{get_line(12)}\n\n"
                f"👇 <i>Tap the button below to access the Download Channel!</i>"
            )
            buttons = [
                [InlineKeyboardButton("ACCESS DOWNLOAD CHANNEL", url=channel_link, style="primary", icon_custom_emoji_id=EMOJIS["outbox"][1])],
                [InlineKeyboardButton("BUY HACK", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["cart"][1], style="primary")],
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons),
                                 link_preview_options=LinkPreviewOptions(is_disabled=True))

        elif data == "user_how_to":
            await query.answer()
            text = await db.get_setting("how_to_text")
            vid = await db.get_setting("how_to_video")
            buttons = []
            if vid and vid.startswith("http"):
                buttons.append([InlineKeyboardButton("Watch Tutorial Video", url=vid, style="primary", icon_custom_emoji_id=EMOJIS["rocket"][1])])
            
            buttons.append([InlineKeyboardButton("BUY HACK", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["cart"][1], style="primary")])
            buttons.append([InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons),
                                 link_preview_options=LinkPreviewOptions(is_disabled=True))

        elif data == "user_balance":
            await query.answer()
            user_data = await db.get_user(user_id)
            bal = user_data.get("balance", 0) / 100
            text = (
                f"<blockquote><b>{ce('card')} YOUR WALLET BALANCE</b></blockquote>\n\n"
                f"<b>Available Funds:</b> ₹{bal:.2f}\n"
                f"{get_line(12)}\n"
                f"<i>Ready to get some hacks or need more funds?</i>"
            )
            buttons = [
                [InlineKeyboardButton("BUY HACK", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["cart"][1], style="primary"),
                 InlineKeyboardButton("ADD FUND", callback_data="user_add_funds", icon_custom_emoji_id=EMOJIS["money"][1], style="success")],
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_referral":
            await query.answer()
            user_data = await db.get_user(user_id)
            bot_info = await context.bot.get_me()
            ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
            share_msg = (
                f"{ce('fire')} Join the Ultimate Hack Store! Get premium mods and scripts instantly. "
                f"Use my link to start: {ref_link}"
            )
            share_url = f"https://t.me/share/url?url={ref_link}&text={quote(share_msg)}"
            text = (
                f"<blockquote><b>{ce('gift')} HACK STORE REFERRAL PROGRAM {ce('gift')}</b></blockquote>\n\n"
                f"<i>Invite your friends and earn a massive <b>15% LIFETIME COMMISSION</b> on every purchase!</i>\n"
                f"{get_line(12)}\n\n"
                f"<b>{ce('stats')} Your Referral Stats:</b>\n"
                f"<b>{ce('user')} Total Referrals:</b> {user_data.get('total_referrals', 0)}\n"
                f"<b>{ce('money')} Total Earnings:</b> ₹{user_data.get('referral_earnings', 0)/100:.2f}\n"
                f"{get_line(12)}\n\n"
                f"<b>{ce('link')} Your Personal Invite Link:</b>\n"
                f"<code>{ref_link}</code>\n\n"
                f"👇 <i>Click the button below to share with your friends!</i>"
            )
            buttons = [
                [InlineKeyboardButton("SHARE & INVITE FRIENDS", url=share_url, style="primary", icon_custom_emoji_id=EMOJIS["outbox"][1])],
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_leaderboard":
            await query.answer()
            leaders = await db.get_leaderboard()
            if not leaders:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('warning')} No leaderboard data yet. Be the first to buy!</blockquote>",
                    back_kb("user_main"),
                )
                return
            text = (
                f"<blockquote><b>{ce('trophy')} TOP VIP HACKERS {ce('trophy')}</b></blockquote>\n\n"
                f"<i>Top 10 users based on purchases!</i>\n{get_line(12)}\n\n"
            )
            medals = [ce('gold1'), ce('silver'), ce('bronze')] + [ce('medal')] * 7
            for i, leader in enumerate(leaders):
                text += f"{medals[i]} <b>{leader['first_name']}</b> ➖ ₹{leader['total_spent']/100:.2f}\n"
            text += f"\n{get_line(12)}\n<i>Buy more to get on the Leaderboard!</i>"
            buttons = [
                [InlineKeyboardButton("BUY HACK", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["cart"][1], style="primary")],
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_faq":
            await query.answer()
            faq = await db.get_setting("faq_text")
            tos = await db.get_setting("tos_text")
            text = (
                f"<blockquote><b>{ce('books')} FAQ &amp; TERMS OF SERVICE</b></blockquote>\n\n"
                f"<b>{ce('sparkle')} FAQ:</b>\n<i>{faq}</i>\n\n"
                f"{get_line(12)}\n"
                f"<b>{ce('sparkle')} TERMS OF SERVICE:</b>\n<i>{tos}</i>\n\n"
                f"<i>By using this bot, you agree to these terms.</i>"
            )
            buttons = [
                [InlineKeyboardButton("SUPPORT", callback_data="user_contact", icon_custom_emoji_id=EMOJIS["contact"][1], style="primary")],
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_profile":
            await query.answer()
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_PHOTO)
            user_data = await db.get_user(user_id)
            keys_count = await db.get_user_keys_count(user_id)
            total_spent = user_data.get("total_spent", 0) / 100
            text = (
                f"<blockquote><b>{ce('user')} USER PROFILE {ce('user')}</b></blockquote>\n\n"
                f"<b>ID:</b> <code>{user_data.get('user_id')}</code>\n"
                f"<b>Name:</b> <b>{user_data.get('first_name')}</b>\n"
                f"<b>Username:</b> @{user_data.get('username') or 'N/A'}\n"
                f"<b>Joined:</b> <b>{(user_data.get('joined_date') or '')[:10]}</b>\n"
                f"{get_line(12)}\n"
                f"<b>{ce('money')} Balance:</b> ₹{user_data.get('balance', 0)/100:.2f}\n"
                f"<b>{ce('stats')} Spent:</b> ₹{total_spent:.2f}\n"
                f"<b>{ce('key')} Keys:</b> {keys_count}\n\n"
                f"<i>Note: Profile fetches your current Telegram Photo.</i>"
            )
            buttons = [
                [InlineKeyboardButton("MY KEYS", callback_data="user_my_keys_0", icon_custom_emoji_id=EMOJIS["key"][1], style="primary"),
                 InlineKeyboardButton("ADD FUND", callback_data="user_add_funds", icon_custom_emoji_id=EMOJIS["money"][1], style="success")],
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            kb = InlineKeyboardMarkup(buttons)
            try:
                photos = await context.bot.get_user_profile_photos(user_id, limit=1)
                photo_id = (
                    photos.photos[0][-1].file_id if photos.total_count > 0
                    else await db.get_setting("default_pfp")
                )
                await query.message.delete()
                await context.bot.send_photo(
                    chat_id=query.message.chat_id, photo=photo_id,
                    caption=text, reply_markup=kb, parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.error(f"Error fetching profile photo: {e}")
                await safe_edit_text(update, context, text, kb)

        elif data.startswith("user_my_keys_"):
            await query.answer()
            page = int(data.split("_")[3])
            limit = 5
            offset = page * limit
            total_keys = await db.get_user_keys_count(user_id)
            keys = await db.get_user_keys(user_id, offset, limit)
            if total_keys == 0:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} You do not have any active keys.</blockquote>",
                    back_kb("user_main"),
                )
                return
            text = f"<blockquote><b>{ce('key')} YOUR PURCHASE HISTORY {ce('star')}</b></blockquote>\n\n"
            for k in keys:
                text += (
                    f"{ce('game')} <b>{k['name']}</b> ({k['duration']})\n"
                    f"<code>{k['key_value']}</code>\n"
                    f"{ce('time')} <b>Expiry:</b> {k['expiry_date'][:10]}\n"
                    f"{get_line(10)}\n"
                )
            total_pages = max(1, math.ceil(total_keys / limit))
            buttons = pagination_kb(page, total_pages, "user_my_keys", "user_main")
            # Add Buy Hack to the loop
            buttons.insert(-1, [InlineKeyboardButton("BUY MORE HACKS", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["cart"][1], style="primary")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_stock":
            await query.answer()
            summary = await db.get_stock_summary()
            if not summary:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('warning')} No stock available right now.</blockquote>",
                    back_kb("user_main"),
                )
                return
            text = f"<blockquote><b>{ce('search')} CURRENT STOCK STATUS {ce('stock')}</b></blockquote>\n\n"
            for prod_name, plans in summary.items():
                text += f"<b>{ce('game')} {prod_name}</b>\n"
                for pl in plans:
                    text += f"  ├ {ce('key')} <b>{pl['duration']}: {pl['count']} keys</b>\n"
                text += "\n"
            buttons = [
                [InlineKeyboardButton("BUY HACK", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["cart"][1], style="primary")],
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_add_funds":
            await prompt_add_funds(update, context)
            return

        elif data.startswith("add_f_"):
            if data == "add_f_manual":
                # Initialize keypad with 0
                text = f"<blockquote><b>{ce('money')} ENTER CUSTOM AMOUNT</b></blockquote>\n\nAmount: <b>₹0</b>\n\n<i>Use the keypad below to enter amount.</i>"
                buttons = _get_keypad_kb("0")
                await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
                return

            # Predefined amount
            amt = float(data.split("_")[2])
            await query.answer(f"Preparing QR for ₹{amt}…")
            await _process_add_fund(update, context, amt)
            return

        elif data.startswith("kp_"):
            val = data.split("_")[1]
            current = str(context.user_data.get("kp_val", "0"))
            
            if val == "clear":
                new_val = "0"
            elif val == "ok":
                amt = float(current)
                if amt < 1:
                    await query.answer("Minimum amount is ₹1", show_alert=True)
                    return
                await query.answer(f"Confirming ₹{amt}…")
                context.user_data["kp_val"] = "0" # reset for next time
                await _process_add_fund(update, context, amt)
                return
            else:
                if current == "0":
                    new_val = val
                else:
                    if len(current) < 6: # Max 6 digits
                        new_val = current + val
                    else:
                        new_val = current
                        await query.answer("Max limit reached!")

            context.user_data["kp_val"] = new_val
            text = f"<blockquote><b>{ce('money')} ENTER CUSTOM AMOUNT</b></blockquote>\n\nAmount: <b>₹{new_val}</b>\n\n<i>Use the keypad below to enter amount.</i>"
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(_get_keypad_kb(new_val)))
            return

        # ── Pay via Balance ────────────────────────────────────────────────────
        elif data.startswith("pay_bal_"):
            plan_id = int(data.split("_")[2])
            plan = await db.get_plan(plan_id)
            user_data = await db.get_user(user_id)
            
            # Recalculate price for security
            price = float(plan['price'])
            is_reseller, discount_perc = await db.is_active_reseller(user_id)
            if is_reseller:
                price = price * (1 - (discount_perc / 100))
            
            if user_data.get("balance", 0) < price:
                await query.answer("Insufficient balance!", show_alert=True)
                return
            
            await query.answer("Processing payment…", show_alert=False)
            
            # Deduct balance
            await db.update_balance(user_id, -int(price))
            
            # Process automated key delivery
            success, msg, delivery_data = await db.purchase_key_automated(user_id, plan_id)
            
            if success:
                # Update total spent
                await asyncio.to_thread(db.db.users.update_one, {"_id": user_id}, {"$inc": {"total_spent": int(price)}})
                
                text = (
                    f"<blockquote>{ce('success')} <b>PAYMENT SUCCESSFUL!</b></blockquote>\n\n"
                    f"₹{price/100:.2f} has been deducted from your wallet.\n\n"
                    f"<b>{ce('game')} Product:</b> {delivery_data['product']}\n"
                    f"<b>{ce('time')} Duration:</b> {delivery_data['duration']}\n"
                    f"<b>{ce('key')} Your Key:</b> <code>{delivery_data['key']}</code>\n"
                    f"<b>{ce('calendar')} Expiry:</b> {delivery_data['expiry'][:16].replace('T', ' ')}\n\n"
                    f"<i>{ce('rocket')} Thank you for choosing Hack Store!</i>"
                )
                await safe_edit_text(update, context, text, main_menu_kb())
                
                # Notify Admins
                user_obj = await db.get_user(user_id)
                uname = (user_obj.get("username") or "").lstrip("@")
                fname = user_obj.get("first_name") or ""
                await notify_admins(context, (
                    f"<blockquote><b>{ce('money')} NEW WALLET PURCHASE</b></blockquote>\n"
                    f"<b>{ce('user')} User:</b> <code>{user_id}</code> ({fname} @{uname})\n"
                    f"<b>{ce('bag')} Product:</b> {delivery_data['product']} ({delivery_data['duration']})\n"
                    f"<b>{ce('money')} Amount:</b> ₹{price/100:.2f}\n"
                    f"<b>{ce('key')} Key Delivered:</b> <code>{delivery_data['key']}</code>"
                ))
            else:
                # Refund balance if key delivery fails
                await db.update_balance(user_id, int(price))
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} <b>PURCHASE FAILED</b></blockquote>\n\n"
                    f"Error: {msg}\nYour balance has been refunded. Please contact support.",
                    main_menu_kb()
                )
            return

        elif data == "user_contact":
            await query.answer()
            sup_user = await db.get_setting("support_user")
            text = (
                f"<blockquote><b>{ce('contact')} NEED HELP? WE'RE HERE!</b></blockquote>\n\n"
                f"For direct support, questions, or issue resolution, contact our admin or open a ticket.\n\n"
                f"<b>{ce('admin')} Admin:</b> {sup_user}"
            )
            buttons = [
                [InlineKeyboardButton("Open Support Ticket", callback_data="user_ticket", style="primary", icon_custom_emoji_id=EMOJIS["ticket"][1])],
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

    except Exception:
        logger.error(f"Error in user callbacks: {traceback.format_exc()}")


# ==============================================================================
# 9. ADMIN HANDLERS
# ==============================================================================
@staff_required
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    kb = await admin_menu_kb(user_id)
    await update.message.reply_text(
        f"<blockquote><b>{ce('admin')} ENTERPRISE ADMIN PANEL</b></blockquote>",
        reply_markup=kb, parse_mode=ParseMode.HTML,
    )


@staff_required
async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # Super Admin Only actions
    super_only = [
        "admin_products", "admin_keys", "admin_users", "admin_pending_payments",
        "admin_resellers", "admin_settings", "adm_maintenance", "admin_svc_session",
        "adm_export_db", "admin_staff_list",
    ]
    
    if any(data.startswith(s) for s in super_only) and user_id not in ADMIN_IDS:
        await query.answer("Super Admin Only!", show_alert=True)
        return

    try:
        if data == "admin_main":
            await query.answer()
            kb = await admin_menu_kb(user_id)
            await safe_edit_text(
                update, context,
                f"<blockquote><b>{ce('admin')} ENTERPRISE ADMIN PANEL</b></blockquote>",
                kb,
            )

        # ── Staff Management ──────────────────────────────────────────────────
        elif data == "admin_staff_list":
            await query.answer()
            staff = await db.get_all_staff()
            text = f"<blockquote><b>{ce('admin')} STAFF MANAGEMENT</b></blockquote>\n\n"
            if not staff:
                text += "<i>No staff members added yet.</i>"
            else:
                for s in staff:
                    uname = f"@{s.get('username')}" if s.get('username') else "N/A"
                    text += f"• <b>{s.get('first_name')}</b> ({uname})\n  └ ID: <code>{s['_id']}</code>\n"
            
            buttons = [
                [InlineKeyboardButton("ADD STAFF", callback_data="adm_add_staff")],
                [InlineKeyboardButton("REMOVE STAFF", callback_data="adm_rem_staff")],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")]
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Dashboard ─────────────────────────────────────────────────────────
        elif data == "admin_stats":
            await query.answer()
            users, rev, sold, avail = await db.get_global_stats()
            text = (
                f"<blockquote><b>{ce('stats')} ENTERPRISE DASHBOARD &amp; STATS</b></blockquote>\n\n"
                f"<b>{ce('user')} Total Verified Users:</b> {users}\n"
                f"<b>{ce('money')} Total Revenue:</b> ₹{rev/100:.2f}\n"
                f"<b>{ce('key')} Total Keys Sold:</b> {sold}\n"
                f"<b>{ce('stock')} Keys In Stock:</b> {avail}\n"
                f"{get_line(12)}\n"
                f"<i>All activities are securely logged in the database.</i>"
            )
            await safe_edit_text(update, context, text, back_kb("admin_main"))

        # ── Pending Payments Panel ──────────────────────────────────────
        elif data == "admin_pending_payments":
            await query.answer()
            pending = await db.get_pending_fund_requests()
            if not pending:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('success')} No pending payment requests.</blockquote>",
                    back_kb("admin_main"),
                )
                return

            text = (
                f"<blockquote><b>{ce('pending')} PENDING PAYMENTS ({len(pending)})</b></blockquote>\n\n"
            )
            for r in pending[:10]:  # show up to 10
                text += (
                    f"<code>{r.get('order_id', r.get('id', 'N/A'))}</code>\n"
                    f"  User: <code>{r['user_id']}</code> | ₹{r.get('amount', 0)/100:.2f}\n"
                    f"  Date: {str(r.get('request_date', ''))[:16]}\n\n"
                )
            buttons = [
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Resellers ─────────────────────────────────────────────────────────
        elif data == "admin_resellers":
            await query.answer()
            resellers = await db.get_resellers()
            text = (
                f"<blockquote><b>{ce('shield')} RESELLER MANAGEMENT</b></blockquote>\n\n"
                f"Manage your bot resellers and their special discounts here.\n"
                f"{get_line(12)}\n\n"
            )
            
            if not resellers:
                text += "<i>No resellers currently added.</i>"
            else:
                text += f"<b>Current Resellers ({len(resellers)}):</b>\n"
                for r in resellers:
                    expiry = r.get("reseller_expiry", "N/A")[:10]
                    discount = r.get("reseller_discount", 0.0)
                    uname = r.get("username") or r.get("first_name", "User")
                    text += f"• <b>{uname}</b> (<code>{r['_id']}</code>)\n  ├ Discount: {discount}%\n  └ Exp: {expiry}\n"

            buttons = [
                [InlineKeyboardButton("Add/Edit Reseller", callback_data="adm_reseller_add", style="primary", icon_custom_emoji_id=EMOJIS["plus"][1])],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Resellers ─────────────────────────────────────────────────────────
        elif data == "admin_resellers":
            await query.answer()
            resellers = await db.get_resellers()
            text = (
                f"<blockquote><b>{ce('shield')} RESELLER MANAGEMENT</b></blockquote>\n\n"
                f"Manage your bot resellers and their special discounts here.\n"
                f"{get_line(12)}\n\n"
            )
            
            if not resellers:
                text += "<i>No resellers currently added.</i>"
            else:
                text += f"<b>Current Resellers ({len(resellers)}):</b>\n"
                for r in resellers:
                    expiry = r.get("reseller_expiry", "N/A")[:10]
                    discount = r.get("reseller_discount", 0.0)
                    uname = r.get("username") or r.get("first_name", "User")
                    text += f"• <b>{uname}</b> (<code>{r['_id']}</code>)\n  ├ Discount: {discount}%\n  └ Exp: {expiry}\n"

            buttons = [
                [InlineKeyboardButton("Add/Edit Reseller", callback_data="adm_reseller_add", style="primary", icon_custom_emoji_id=EMOJIS["plus"][1])],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))


        # ── Backup DB ──────────────────────────────────────────────────────────
        elif data == "adm_export_db":
            await query.answer("Preparing Database Export…")
            try:
                data_bytes = await db.export_database()
                buf = io.BytesIO(data_bytes)
                buf.name = f"hackstore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                await context.bot.send_document(
                    chat_id=user_id, document=buf, filename=buf.name,
                    caption=(
                        f"<blockquote><b>{ce('disk')} DATABASE BACKUP</b></blockquote>\n"
                        f"<i>Keep this file secure!</i>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                await safe_edit_text(update, context, f"Error exporting DB: {e}", back_kb("admin_main"))

        # ── Maintenance ────────────────────────────────────────────────────────
        elif data == "adm_maintenance":
            await query.answer()
            current = await db.get_setting("maintenance_mode", "0")
            new_mode = "0" if current == "1" else "1"
            await db.set_setting("maintenance_mode", new_mode)
            await db.log_admin_action(user_id, "Toggled Maintenance", f"New Status: {new_mode}")
            status = (
                f"<b>{ce('fail')} ACTIVE (Users Blocked)</b>"
                if new_mode == "1"
                else f"<b>{ce('success')} INACTIVE (Users Allowed)</b>"
            )
            text = f"<blockquote><b>{ce('tools')} MAINTENANCE MODE</b></blockquote>\n\nCurrent Status: {status}"
            buttons = [
                [InlineKeyboardButton("Toggle Mode", callback_data="adm_maintenance", style="danger", icon_custom_emoji_id=EMOJIS["loop"][1])],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Products ───────────────────────────────────────────────────────────
        elif data == "admin_products":
            await query.answer()
            prods = await db.get_all_products()
            text = (
                f"<blockquote><b>{ce('bag')} MANAGE PRODUCTS</b></blockquote>\n"
                f"Select a product to edit or add a new one."
            )
            buttons = [[InlineKeyboardButton(p['name'], callback_data=f"adm_prod_{p['id']}", icon_custom_emoji_id=EMOJIS["bag"][1], style="primary")] for p in prods]
            buttons.append([InlineKeyboardButton("Add New Product", callback_data="adm_add_prod", icon_custom_emoji_id=EMOJIS["plus"][1], style="success")])
            buttons.append([InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_prod_"):
            await query.answer()
            p_id = int(data.split("_")[2])
            p = await db.get_product(p_id)
            text = (
                f"<blockquote><b>{ce('edit')} EDIT PRODUCT</b></blockquote>\n\n"
                f"<b>Name:</b> {p['name']}\n"
                f"<b>Active:</b> {'Yes ' + ce('success') if p.get('is_active') else 'No ' + ce('fail')}\n\n"
                f"{p.get('description', '')}"
            )
            buttons = [
                [InlineKeyboardButton("Edit Description", callback_data=f"adm_edit_desc_{p_id}", icon_custom_emoji_id=EMOJIS["pencil"][1], style="primary")],
                [InlineKeyboardButton("Toggle Status", callback_data=f"adm_ptog_{p_id}", icon_custom_emoji_id=EMOJIS["loop"][1], style="primary")],
                [InlineKeyboardButton("Manage Plans", callback_data=f"adm_plans_{p_id}", icon_custom_emoji_id=EMOJIS["bag"][1], style="primary")],
                [InlineKeyboardButton("Delete Product", callback_data=f"adm_delprod_{p_id}", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")],
                [InlineKeyboardButton("Back", callback_data="admin_products", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_ptog_"):
            p_id = int(data.split("_")[2])
            await db.toggle_product(p_id)
            await db.log_admin_action(user_id, "Toggled Product", f"PID: {p_id}")
            await query.answer("Status toggled!")
            p = await db.get_product(p_id)
            text = (
                f"<blockquote><b>{ce('edit')} EDIT PRODUCT</b></blockquote>\n\n"
                f"<b>Name:</b> {p['name']}\n"
                f"<b>Active:</b> {'Yes ' + ce('success') if p.get('is_active') else 'No ' + ce('fail')}\n\n"
                f"{p.get('description', '')}"
            )
            buttons = [
                [InlineKeyboardButton("Edit Description", callback_data=f"adm_edit_desc_{p_id}", icon_custom_emoji_id=EMOJIS["pencil"][1], style="primary")],
                [InlineKeyboardButton("Toggle Status", callback_data=f"adm_ptog_{p_id}", icon_custom_emoji_id=EMOJIS["loop"][1], style="primary")],
                [InlineKeyboardButton("Manage Plans", callback_data=f"adm_plans_{p_id}", icon_custom_emoji_id=EMOJIS["bag"][1], style="primary")],
                [InlineKeyboardButton("Delete Product", callback_data=f"adm_delprod_{p_id}", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")],
                [InlineKeyboardButton("Back", callback_data="admin_products", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_delprod_"):
            p_id = int(data.split("_")[2])
            text = (
                f"<blockquote><b>{ce('warning')} Are you sure you want to delete this product?</b>\n\n"
                f"This will also delete all its plans and keys. Cannot be undone.</blockquote>"
            )
            buttons = [
                [InlineKeyboardButton("Yes, Delete", callback_data=f"adm_confirm_delprod_{p_id}", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")],
                [InlineKeyboardButton("Cancel", callback_data=f"adm_prod_{p_id}", icon_custom_emoji_id=EMOJIS["back"][1], style="primary")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_confirm_delprod_"):
            p_id = int(data.split("_")[3])
            await db.delete_product(p_id)
            await db.log_admin_action(user_id, "Deleted Product", f"PID: {p_id}")
            await query.answer("Product deleted successfully!")
            await safe_edit_text(
                update, context,
                f"<blockquote>{ce('success')} Product Deleted Successfully.</blockquote>",
                back_kb("admin_products"),
            )

        elif data.startswith("adm_plans_"):
            await query.answer()
            p_id = int(data.split("_")[2])
            plans = await db.get_plans(p_id)
            text = (
                f"<blockquote><b>📋 MANAGE PLANS</b></blockquote>\n"
                f"<i>Click a plan to delete it.</i>\n{get_line(12)}"
            )
            buttons = []
            for pl in plans:
                buttons.append([InlineKeyboardButton(
                    f"{pl['duration']} — ₹{pl['price']/100:.2f}",
                    callback_data=f"adm_plan_del_{pl['id']}",
                    icon_custom_emoji_id=EMOJIS["fail"][1],
                    style="danger"
                )])
            buttons.append([InlineKeyboardButton("Add New Plan", callback_data=f"adm_add_plan_{p_id}", icon_custom_emoji_id=EMOJIS["plus"][1], style="success")])
            buttons.append([InlineKeyboardButton("Back", callback_data=f"adm_prod_{p_id}", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_plan_del_"):
            pl_id = int(data.split("_")[3])
            plan = await db.get_plan(pl_id)
            if plan:
                text = (
                    f"<blockquote><b>{ce('warning')} Delete plan '{plan['duration']}'?</b>\n\n"
                    f"All keys under this plan will also be deleted.</blockquote>"
                )
                buttons = [
                    [InlineKeyboardButton("Yes, Delete", callback_data=f"adm_confirm_plandell_{pl_id}", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")],
                    [InlineKeyboardButton("Cancel", callback_data=f"adm_plans_{plan['product_id']}", icon_custom_emoji_id=EMOJIS["back"][1], style="primary")],
                ]
                await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_confirm_plandell_"):
            pl_id = int(data.split("_")[3])
            plan = await db.get_plan(pl_id)
            prod_id = plan.get("product_id") if plan else 0
            await db.delete_plan(pl_id)
            await db.log_admin_action(user_id, "Deleted Plan", f"PlanID: {pl_id}")
            await query.answer("Plan deleted!")
            await safe_edit_text(
                update, context,
                f"<blockquote>{ce('success')} Plan Deleted.</blockquote>",
                back_kb(f"adm_plans_{prod_id}"),
            )

        # ── Keys ───────────────────────────────────────────────────────────────
        elif data == "admin_keys":
            await query.answer()
            prods = await db.get_active_products()
            text = f"<blockquote><b>{ce('key')} MANAGE KEYS</b></blockquote>\nSelect a product to add bulk keys."
            buttons = [[InlineKeyboardButton(p["name"], callback_data=f"adm_kprod_{p['id']}", style="primary")] for p in prods]
            buttons.append([InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_kprod_"):
            await query.answer()
            p_id = int(data.split("_")[2])
            plans = await db.get_plans(p_id)
            text = f"<blockquote><b>{ce('key')} SELECT PLAN TO ADD KEYS</b></blockquote>"
            buttons = [[InlineKeyboardButton(pl["duration"], callback_data=f"adm_kplan_{pl['id']}", style="primary")] for pl in plans]
            buttons.append([InlineKeyboardButton("Back", callback_data="admin_keys", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Promos ─────────────────────────────────────────────────────────────
        elif data == "admin_promos":
            await query.answer()
            text = (
                f"<blockquote><b>{ce('promo')} PROMO CODES MANAGEMENT</b></blockquote>\n\n"
                f"Generate limited usage promo codes for your users!"
            )
            buttons = [
                [InlineKeyboardButton("Create Promo Code", callback_data="adm_create_promo", style="success", icon_custom_emoji_id=EMOJIS["plus"][1])],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Users ──────────────────────────────────────────────────────────────
        elif data == "admin_users":
            await query.answer()
            text = (
                f"<blockquote><b>{ce('user')} USER MANAGEMENT</b></blockquote>\n\n"
                f"Choose an action below:"
            )
            buttons = [
                [InlineKeyboardButton("Add Manual Balance", callback_data="adm_add_bal", style="primary", icon_custom_emoji_id=EMOJIS["money"][1])],
                [InlineKeyboardButton("Ban User", callback_data="adm_ban_usr", style="danger", icon_custom_emoji_id=EMOJIS["fail"][1]),
                 InlineKeyboardButton("Unban User", callback_data="adm_unban_usr", style="success", icon_custom_emoji_id=EMOJIS["success"][1])],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Settings ───────────────────────────────────────────────────────────
        elif data == "admin_settings":
            await query.answer()
            try:
                qr_url = await db.get_setting("qr_image")
                qr_status = "Set" if qr_url and qr_url != "None" else "Not Set"
                upi = await db.get_setting("upi_id")
                support = await db.get_setting("support_user")
                dl_link = await db.get_setting("global_channel_link", "Not Set")
                insult_raw = await db.get_setting("unauth_msg", "")
                insult_clean = re.sub(r"<[^>]+>", "", insult_raw)
                insult_preview = insult_clean[:40] + "..." if len(insult_clean) > 40 else insult_clean
                text = (
                    f"<blockquote><b>{ce('settings')} STORE SETTINGS</b></blockquote>\n\n"
                    f"<code>UPI ID       : {upi}\n"
                    f"Support User : {support}\n"
                    f"QR Code      : {qr_status}\n"
                    f"Download Link: {dl_link}</code>\n\n"
                    f"<b>Insult Msg:</b>\n<i>{insult_preview}</i>\n"
                    f"{get_line(12)}\n"
                    f"<i>Choose a setting to modify below:</i>"
                )
                buttons = [
                    [InlineKeyboardButton("Edit UPI ID", callback_data="adm_set_upi", style="primary", icon_custom_emoji_id=EMOJIS["pencil"][1]),
                     InlineKeyboardButton("Edit Support User", callback_data="adm_set_sup", style="primary", icon_custom_emoji_id=EMOJIS["pencil"][1])],
                    [InlineKeyboardButton("Edit QR Image", callback_data="adm_set_qr", style="primary", icon_custom_emoji_id=EMOJIS["pencil"][1]),
                     InlineKeyboardButton("Edit Insult Msg", callback_data="adm_set_msg", style="primary", icon_custom_emoji_id=EMOJIS["pencil"][1])],
                    [InlineKeyboardButton("Edit Download Channel", callback_data="adm_set_dl_link", style="primary", icon_custom_emoji_id=EMOJIS["link"][1])],
                    [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
                ]
                await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} Error loading settings. Check logs.</blockquote>",
                    back_kb("admin_main"),
                )

        elif data == "admin_faq":
            await query.answer()
            text = (
                f"<blockquote><b>{ce('memo')} CONTENT MANAGEMENT</b></blockquote>\n\n"
                f"Update the texts shown to users in the FAQ, TOS, and How To Use sections."
            )
            buttons = [
                [InlineKeyboardButton("Edit FAQ", callback_data="adm_edit_faq", style="primary", icon_custom_emoji_id=EMOJIS["pencil"][1]),
                 InlineKeyboardButton("Edit TOS", callback_data="adm_edit_tos", style="primary", icon_custom_emoji_id=EMOJIS["pencil"][1])],
                [InlineKeyboardButton("Edit How-To Text", callback_data="adm_edit_howto_text", style="primary", icon_custom_emoji_id=EMOJIS["pencil"][1]),
                 InlineKeyboardButton("Edit How-To Video", callback_data="adm_edit_howto_vid", style="primary", icon_custom_emoji_id=EMOJIS["link"][1])],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Tickets ────────────────────────────────────────────────────────────
        elif data == "admin_tickets":
            await query.answer()
            tkts = await db.get_open_tickets()
            if not tkts:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('success')} No open support tickets.</blockquote>",
                    back_kb("admin_main"),
                )
                return
            t = tkts[0]
            text = (
                f"<blockquote><b>{ce('ticket')} OPEN TICKET #{t['id']}</b></blockquote>\n\n"
                f"<b>User ID:</b> <code>{t['user_id']}</code>\n"
                f"<b>Message:</b>\n<i>{t['message']}</i>\n"
                f"{get_line(12)}"
            )
            buttons = [
                [InlineKeyboardButton("Reply & Close", callback_data=f"adm_tkt_{t['id']}", style="success", icon_custom_emoji_id=EMOJIS["chat"][1])],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

    except Exception:
        logger.error(f"Error in handle_admin_callbacks: {traceback.format_exc()}")
        try:
            await query.answer("An internal error occurred.", show_alert=True)
        except Exception:
            pass


# ==============================================================================
# 10. CONVERSATION HANDLERS
# ==============================================================================
async def cancel_conv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Cancelled.")
    if update.effective_user.id in ADMIN_IDS:
        await safe_edit_text(update, context, "<blockquote>Process Cancelled.</blockquote>", await admin_menu_kb(update.effective_user.id))
    else:
        await safe_edit_text(update, context, "<blockquote>Process Cancelled.</blockquote>", main_menu_kb())
    context.user_data.clear()
    return ConversationHandler.END


async def admin_nav_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ends a stale/pending admin conversation when the owner taps any admin
    navigation button, then re-dispatches the tap to the admin router so the
    button works on the first press instead of being swallowed."""
    context.user_data.clear()
    await handle_admin_callbacks(update, context)
    return ConversationHandler.END




# ── Reseller Input Handlers ───────────────────────────────────────────────────
async def receive_reseller_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_doc = await db.find_user_by_id_or_username(query)
    
    if not user_doc:
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>User not found!</b></blockquote>\n\n"
            f"Please ensure the user has started the bot and check the ID/Username.",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
        )
        return WAIT_FOR_RESELLER_USER
    
    context.user_data["target_reseller_id"] = user_doc["_id"]
    await update.message.reply_text(
        f"<blockquote><b>{ce('shield')} USER FOUND: {user_doc.get('first_name', 'User')}</b></blockquote>\n\n"
        f"How many <b>DAYS</b> should this user remain a reseller?\n"
        f"<i>Enter 0 to remove reseller status.</i>",
        reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
    )
    return WAIT_FOR_RESELLER_DAYS


async def receive_reseller_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(update.message.text.strip())
        if days < 0: raise ValueError
    except:
        await update.message.reply_text("Please enter a valid number of days.", reply_markup=cancel_kb())
        return WAIT_FOR_RESELLER_DAYS

    if days == 0:
        uid = context.user_data.get("target_reseller_id")
        await db.remove_reseller(uid)
        await db.log_admin_action(update.effective_user.id, "Removed Reseller", f"UID: {uid}")
        await update.message.reply_text(f"<blockquote>{ce('success')} Reseller status removed.</blockquote>", 
                                       reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML)
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data["reseller_days"] = days
    await update.message.reply_text(
        f"<blockquote><b>{ce('money')} DISCOUNT PERCENTAGE</b></blockquote>\n\n"
        f"Enter the discount percentage for this reseller (e.g. <code>10</code> for 10% off).",
        reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
    )
    return WAIT_FOR_RESELLER_DISCOUNT


async def receive_reseller_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        discount = float(update.message.text.strip())
        if not (0 <= discount <= 100): raise ValueError
    except:
        await update.message.reply_text("Please enter a valid discount (0-100).", reply_markup=cancel_kb())
        return WAIT_FOR_RESELLER_DISCOUNT

    uid = context.user_data.get("target_reseller_id")
    days = context.user_data.get("reseller_days")
    
    await db.set_reseller(uid, days, discount)
    await db.log_admin_action(update.effective_user.id, "Added/Updated Reseller", f"UID: {uid}, Days: {days}, Disc: {discount}%")
    
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Reseller Setup Complete!</b></blockquote>\n\n"
        f"User <code>{uid}</code> is now a reseller for {days} days with {discount}% discount.",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    context.user_data.clear()
    return ConversationHandler.END

    context.user_data.clear()
    return ConversationHandler.END


# ── NEW: Edit microservice URL ─────────────────────────────────────────────────




# ── Staff Input Handlers ───────────────────────────────────────────────────────
@staff_required
async def prompt_add_staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('admin')} ADD NEW STAFF MEMBER</b></blockquote>\n\n"
        f"Send the <b>User ID</b> or <b>@Username</b> of the person you want to make a staff member.\n\n"
        f"<i>Staff can only broadcast and manage tickets.</i>",
        cancel_kb(),
    )
    return WAIT_FOR_ADD_STAFF


@staff_required
async def receive_add_staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_str = update.message.text.strip()
    user = await db.find_user_by_id_or_username(query_str)
    
    if not user:
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>User not found in database!</b></blockquote>\n\n"
            f"Please ensure the user has started the bot and is verified.",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML
        )
        return WAIT_FOR_ADD_STAFF

    uid = user["_id"]
    name = user.get("first_name", "User")
    
    await db.add_staff(uid)
    await db.log_admin_action(update.effective_user.id, "Add Staff", f"UID: {uid} ({name})")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Staff Member Added!</b></blockquote>\n\n"
        f"<b>Name:</b> {name}\n"
        f"<b>ID:</b> <code>{uid}</code>\n\n"
        f"This user can now access restricted admin features.",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


@staff_required
async def prompt_rem_staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('admin')} REMOVE STAFF MEMBER</b></blockquote>\n\n"
        f"Send the <b>User ID</b> or <b>@Username</b> of the person you want to remove from staff.",
        cancel_kb(),
    )
    return WAIT_FOR_REM_STAFF


@staff_required
async def receive_rem_staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_str = update.message.text.strip()
    user = await db.find_user_by_id_or_username(query_str)

    if not user:
        # Fallback to direct ID removal if user not in DB anymore
        if query_str.isdigit():
            uid = int(query_str)
            await db.remove_staff(uid)
            await db.log_admin_action(update.effective_user.id, "Remove Staff", f"UID: {uid}")
            await update.message.reply_text(
                f"<blockquote>{ce('success')} <b>Staff ID {uid} removed.</b></blockquote>",
                reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END
            
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>User not found!</b></blockquote>",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML
        )
        return WAIT_FOR_REM_STAFF

    uid = user["_id"]
    name = user.get("first_name", "User")
    
    await db.remove_staff(uid)
    await db.log_admin_action(update.effective_user.id, "Remove Staff", f"UID: {uid} ({name})")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Staff Member Removed!</b></blockquote>\n\n"
        f"<b>Name:</b> {name}\n"
        f"<b>ID:</b> <code>{uid}</code>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── User conversations ─────────────────────────────────────────────────────────
@verification_required
async def prompt_add_funds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    text = (
        f"<blockquote><b>{ce('money')} ADD FUNDS TO WALLET</b></blockquote>\n\n"
        f"Choose a quick amount to add or type a custom one below.\n\n"
        f"<i>{ce('rocket')} Predefined amounts are faster to process!</i>"
    )
    buttons = [
        [InlineKeyboardButton("₹100", callback_data="add_f_100", style="primary"),
         InlineKeyboardButton("₹200", callback_data="add_f_200", style="primary")],
        [InlineKeyboardButton("₹500", callback_data="add_f_500", style="primary"),
         InlineKeyboardButton("₹1000", callback_data="add_f_1000", style="primary")],
        [InlineKeyboardButton("Type Custom Amount", callback_data="add_f_manual", style="primary", icon_custom_emoji_id=EMOJIS["pencil"][1])],
        [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
    ]
    await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
    return ConversationHandler.END # We will handle buttons via callback query


@verification_required
async def prompt_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('ticket')} Type your message/issue below:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_TICKET


async def receive_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user_id = update.effective_user.id
    t_id = await db.create_ticket(user_id, msg)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} Ticket #{t_id} created successfully!</blockquote>",
        reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML,
    )
    for admin in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin,
                f"<blockquote><b>{ce('ticket')} NEW TICKET #{t_id}</b></blockquote>\n"
                f"From: <code>{user_id}</code>\n\n<i>{msg}</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "Reply", callback_data=f"adm_tkt_{t_id}", icon_custom_emoji_id=EMOJIS["chat"][1], style="success"
                )]]),
            )
        except Exception:
            pass
    return ConversationHandler.END


@verification_required
async def prompt_user_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('promo')} Enter Promo Code:</b></blockquote>\n\n"
        f"<i>Type the promotional code in chat.</i>",
        cancel_kb(),
    )
    return WAIT_FOR_USER_PROMO


async def receive_user_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    user_id = update.effective_user.id
    success, msg, amount = await db.redeem_promo(user_id, code)
    if success:
        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>PROMO CODE REDEEMED!</b></blockquote>\n\n"
            f"₹{amount/100:.2f} has been added to your wallet.",
            reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML,
        )
        # Notify Admins
        user_obj = await db.get_user(user_id)
        uname = (user_obj.get("username") or "").lstrip("@")
        fname = user_obj.get("first_name") or ""
        await notify_admins(context, (
            f"<blockquote><b>{ce('gift')} PROMO CODE REDEEMED</b></blockquote>\n"
            f"<b>User:</b> <code>{user_id}</code> ({fname} @{uname})\n"
            f"<b>Code:</b> <code>{code}</code>\n"
            f"<b>Reward:</b> ₹{amount/100:.2f}"
        ))
    else:
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>{msg}</b></blockquote>",
            reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML,
        )
    return ConversationHandler.END


async def _process_add_fund(update: Update, context: ContextTypes.DEFAULT_TYPE, amt: float):
    user_id = update.effective_user.id
    admin_upi = await db.get_setting("upi_id", "")

    if not admin_upi:
        text = (
            f"<blockquote>{ce('fail')} <b>UPI ID not configured by admin.</b>\n"
            f"Please contact support or try again later.</blockquote>"
        )
        if update.callback_query:
            await safe_edit_text(update, context, text, main_menu_kb())
        else:
            await update.message.reply_text(text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)
        return

    payee = await db.get_setting("global_brand_name", "Hack Store") or "Hack Store"
    chat_id = update.effective_chat.id

    # ── Try PaymentManager SDK first ──────────────────────────────────────
    pm = _get_pm()
    if pm:
        try:
            _env_map = {"DEFAULT_UPI_ID": admin_upi, "DEFAULT_PAYEE_NAME": payee}
            for k, v in _env_map.items():
                if v: os.environ[k] = v

            order = await asyncio.to_thread(pm.create, user_id=user_id, amount=amt)
            order_id = order.id
            expires_at = order.expires_at.strftime("%d %b %Y, %I:%M %p IST")

            await db.create_fund_request_with_order(user_id, order_id, None, amt * 100)

            qr_photo = io.BytesIO(order.qr_image)
            qr_photo.name = f"{order_id}.png"

            caption = (
                f"<blockquote><b>{ce('money')} ADD FUNDS — ₹{amt:.2f}</b></blockquote>\n\n"
                f"Scan the QR below to add money to your wallet.\n\n"
                f"<i>{ce('warning')} QR expires at: <b>{expires_at}</b></i>\n"
                f"<code>Order ID: {order_id}</code>"
            )
            buttons = [
                [InlineKeyboardButton("I'VE PAID", callback_data=f"verify_pay_{order_id}", icon_custom_emoji_id=EMOJIS["success"][1], style="success")],
                [InlineKeyboardButton("Cancel", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]

            if update.callback_query:
                try: await update.callback_query.message.delete()
                except: pass

            msg = await context.bot.send_photo(
                chat_id=chat_id, photo=qr_photo, caption=caption,
                reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML,
            )
            context.job_queue.run_once(
                qr_expiration_job, when=900,
                data={"chat_id": chat_id, "message_id": msg.message_id, "order_id": order_id},
            )
            return

        except Exception as pm_err:
            logger.error(f"PaymentManager create failed for fund: {pm_err}")

    # PM not available or failed — show error to user
    err_text = (
        f"<blockquote>{ce('fail')} <b>QR generation failed.</b>\n"
        f"Please contact support or try again later.</blockquote>"
    )
    if update.callback_query:
        await safe_edit_text(update, context, err_text, main_menu_kb())
    else:
        await update.message.reply_text(err_text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)



async def receive_add_fund_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text.strip())
        if amt < 1: raise ValueError
    except:
        await update.message.reply_text("Please enter a valid amount (minimum ₹1).", reply_markup=cancel_kb())
        return WAIT_FOR_ADD_FUND_AMT

    await _process_add_fund(update, context, amt)
    return ConversationHandler.END


# ── Admin conversations ────────────────────────────────────────────────────────
async def prompt_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    t_id = int(update.callback_query.data.split("_")[2])
    context.user_data["reply_tkt_id"] = t_id
    await safe_edit_text(
        update, context,
        f"<blockquote><b>Type your reply for Ticket #{t_id} in chat:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_ADMIN_TICKET_REPLY


async def receive_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = update.message.text
    t_id = context.user_data["reply_tkt_id"]
    u_id = await db.reply_ticket(t_id, reply)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Reply sent and ticket closed.</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    try:
        await context.bot.send_message(
            u_id,
            f"<blockquote><b>{ce('ticket')} ADMIN REPLY FOR TICKET #{t_id}</b></blockquote>\n\n<i>{reply}</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    return ConversationHandler.END


async def prompt_add_prod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('bag')} Send the New Product NAME:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_NEW_PROD_NAME


async def receive_prod_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prod_name"] = update.message.text.strip()
    text = (
        f"<blockquote><b>{ce('edit')} Select a Description Preset:</b></blockquote>\n\n"
        f"<i>Choose a beautiful preset description or type your own!</i>"
    )
    buttons = [
        [InlineKeyboardButton("Safe / Main ID", callback_data="desc_preset_1", icon_custom_emoji_id=EMOJIS["shield"][1], style="primary")],
        [InlineKeyboardButton("Brutal / Root", callback_data="desc_preset_2", icon_custom_emoji_id=EMOJIS["fire"][1], style="primary")],
        [InlineKeyboardButton("iOS / eSign", callback_data="desc_preset_3", icon_custom_emoji_id=EMOJIS["apple"][1], style="primary")],
        [InlineKeyboardButton("8 Level ID", callback_data="desc_preset_4", icon_custom_emoji_id=EMOJIS["name_icon"][1], style="primary")],
        [InlineKeyboardButton("Drip Client (Non Root)", callback_data="desc_preset_5", icon_custom_emoji_id=EMOJIS["mobile"][1], style="primary")],
        [InlineKeyboardButton("Type Custom Description", callback_data="desc_custom", icon_custom_emoji_id=EMOJIS["pencil"][1], style="primary")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_conv", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    return WAIT_FOR_NEW_PROD_DESC


async def receive_prod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    cb_data = update.callback_query.data
    if cb_data == "desc_custom":
        await safe_edit_text(
            update, context,
            f"<blockquote><b>{ce('edit')} Type your Custom Description (HTML allowed):</b></blockquote>",
            cancel_kb(),
        )
        return WAIT_FOR_CUSTOM_DESC
    elif cb_data.startswith("desc_preset_"):
        preset_id = cb_data.split("_")[2]
        desc = get_preset_desc(preset_id)
        name = context.user_data.get("new_prod_name")
        await db.add_product(name, desc)
        await db.log_admin_action(update.effective_user.id, "Added Product", f"Name: {name}")
        await safe_edit_text(
            update, context,
            f"<blockquote>{ce('success')} <b>Product '{name}' Added Successfully!</b></blockquote>",
            await admin_menu_kb(update.effective_user.id),
        )
        context.user_data.clear()
        return ConversationHandler.END


async def receive_custom_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = f"<blockquote><b>{update.message.text.strip()}</b></blockquote>"
    name = context.user_data.get("new_prod_name")
    await db.add_product(name, desc)
    await db.log_admin_action(update.effective_user.id, "Added Product", f"Name: {name}")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Product '{name}' Added Successfully!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    context.user_data.clear()
    return ConversationHandler.END


@verification_required
async def prompt_edit_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    p_id = int(update.callback_query.data.split("_")[3])
    context.user_data["editing_prod_id"] = p_id
    text = (
        f"<blockquote><b>{ce('edit')} Update Description:</b></blockquote>\n\n"
        f"<i>Choose a preset or type custom!</i>"
    )
    buttons = [
        [InlineKeyboardButton("Safe / Main ID", callback_data="edit_preset_1", icon_custom_emoji_id=EMOJIS["shield"][1], style="primary")],
        [InlineKeyboardButton("Brutal / Root", callback_data="edit_preset_2", icon_custom_emoji_id=EMOJIS["fire"][1], style="primary")],
        [InlineKeyboardButton("iOS / eSign", callback_data="edit_preset_3", icon_custom_emoji_id=EMOJIS["apple"][1], style="primary")],
        [InlineKeyboardButton("8 Level ID", callback_data="edit_preset_4", icon_custom_emoji_id=EMOJIS["name_icon"][1], style="primary")],
        [InlineKeyboardButton("Drip Client (Non Root)", callback_data="edit_preset_5", icon_custom_emoji_id=EMOJIS["mobile"][1], style="primary")],
        [InlineKeyboardButton("Type Custom", callback_data="edit_custom", icon_custom_emoji_id=EMOJIS["pencil"][1], style="primary")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_conv", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")],
    ]
    await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
    return WAIT_FOR_EDIT_PROD_DESC


async def receive_edit_prod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prod_id = context.user_data.get("editing_prod_id")
    if not prod_id:
        if update.message:
            await update.message.reply_text("Error: No product in editing state.", reply_markup=await admin_menu_kb(update.effective_user.id))
        return ConversationHandler.END

    def _prod_buttons(pid):
        return [
            [InlineKeyboardButton("Edit Description", callback_data=f"adm_edit_desc_{pid}", icon_custom_emoji_id=EMOJIS["pencil"][1], style="primary")],
            [InlineKeyboardButton("Toggle Status", callback_data=f"adm_ptog_{pid}", icon_custom_emoji_id=EMOJIS["loop"][1], style="primary")],
            [InlineKeyboardButton("Manage Plans", callback_data=f"adm_plans_{pid}", icon_custom_emoji_id=EMOJIS["bag"][1], style="primary")],
            [InlineKeyboardButton("Delete Product", callback_data=f"adm_delprod_{pid}", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")],
            [InlineKeyboardButton("Back", callback_data="admin_products", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
        ]

    if update.callback_query:
        await update.callback_query.answer()
        cb_data = update.callback_query.data
        if cb_data == "edit_custom":
            await safe_edit_text(
                update, context,
                f"<blockquote><b>{ce('pencil')} Type your Custom Description (HTML allowed):</b></blockquote>",
                cancel_kb(),
            )
            return WAIT_FOR_EDIT_PROD_DESC
        elif cb_data.startswith("edit_preset_"):
            preset_id = cb_data.split("_")[2]
            desc = get_preset_desc(preset_id)
            await db.update_product_description(prod_id, desc)
            await db.log_admin_action(update.effective_user.id, "Edited Product Description", f"PID: {prod_id}")
            p = await db.get_product(prod_id)
            text = (
                f"<blockquote>{ce('success')} <b>Description Updated!</b></blockquote>\n\n"
                f"<b>Name:</b> {p['name']}\n"
                f"<b>Active:</b> {'Yes ' + ce('success') if p.get('is_active') else 'No ' + ce('fail')}\n\n"
                f"{p.get('description', '')}"
            )
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(_prod_buttons(prod_id)))
            context.user_data.clear()
            return ConversationHandler.END
    else:
        new_desc = f"<blockquote><b>{update.message.text}</b></blockquote>"
        await db.update_product_description(prod_id, new_desc)
        await db.log_admin_action(update.effective_user.id, "Edited Product Description", f"PID: {prod_id}")
        p = await db.get_product(prod_id)
        text = (
            f"<blockquote>{ce('success')} <b>Description Updated!</b></blockquote>\n\n"
            f"<b>Name:</b> {p['name']}\n"
            f"<b>Active:</b> {'Yes ' + ce('success') if p.get('is_active') else 'No ' + ce('fail')}\n\n"
            f"{p.get('description', '')}"
        )
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(_prod_buttons(prod_id)), parse_mode=ParseMode.HTML)
        context.user_data.clear()
        return ConversationHandler.END


@verification_required
async def prompt_set_dl_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('link')} Send the new Download Channel Link:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_PROD_LINK


async def receive_set_dl_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_setting("global_channel_link", update.message.text.strip())
    await db.log_admin_action(update.effective_user.id, "Changed Download Link", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Download Channel Link Updated!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def prompt_add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    p_id = int(update.callback_query.data.split("_")[3])
    context.user_data["add_plan_pid"] = p_id
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('time')} Send duration string (e.g. 7 Days or 1 Month):</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_PLAN_DUR


async def receive_plan_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["add_plan_dur"] = update.message.text.strip()
    await update.message.reply_text(
        f"<blockquote><b>{ce('money')} Send price in INR (e.g. 150 for ₹150):</b></blockquote>",
        reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
    )
    return WAIT_FOR_PLAN_PRICE


async def _finish_plan_add(update: Update, context: ContextTypes.DEFAULT_TYPE, mode_note: str):
    """Shared: log action + render the Manage Plans screen after a plan is added."""
    prod_id = context.user_data.get("add_plan_pid")
    await db.log_admin_action(update.effective_user.id, "Added Plan", f"PID: {prod_id} ({mode_note})")
    plans = await db.get_plans(prod_id)
    text = (
        f"<blockquote>{ce('success')} <b>Plan Added Successfully!</b></blockquote>\n\n"
        f"<blockquote><b>📋 MANAGE PLANS</b></blockquote>\n"
        f"<i>Click a plan to delete it. Add another below.</i>\n{get_line(12)}"
    )
    buttons = []
    for pl in plans:
        buttons.append([InlineKeyboardButton(
            f"{pl['duration']} — ₹{pl['price']/100:.2f}",
            callback_data=f"adm_plan_del_{pl['id']}",
            icon_custom_emoji_id=EMOJIS["fail"][1],
            style="danger"
        )])
    buttons.append([InlineKeyboardButton("Add New Plan", callback_data=f"adm_add_plan_{prod_id}", icon_custom_emoji_id=EMOJIS["plus"][1], style="success")])
    buttons.append([InlineKeyboardButton("Back to Product", callback_data=f"adm_prod_{prod_id}", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)


async def receive_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(float(update.message.text.strip()) * 100)
        context.user_data["add_plan_price"] = price
    except Exception:
        await update.message.reply_text("Invalid Price. Send a number (e.g. 150):", reply_markup=cancel_kb())
        return WAIT_FOR_PLAN_PRICE
    # ── Manual mode: plan saved directly, keys delivered from local stock ──
    prod_id = context.user_data.get("add_plan_pid")
    await db.add_plan(prod_id, context.user_data.get("add_plan_dur", ""), context.user_data.pop("add_plan_price", 0))
    await _finish_plan_add(update, context, "Manual")
    context.user_data.clear()
    return ConversationHandler.END


async def prompt_add_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    pl_id = int(update.callback_query.data.split("_")[2])
    context.user_data["add_key_plan"] = pl_id
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('key')} Send keys separated by newline (one key per line):</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_ADD_KEYS


async def receive_add_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keys = [k.strip() for k in update.message.text.split("\n") if k.strip()]
    count = await db.add_keys(context.user_data["add_key_plan"], keys)
    await db.log_admin_action(update.effective_user.id, "Added Keys", f"Count: {count}")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Successfully added {count} unique keys!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def prompt_create_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('promo')} Send the new Promo Code (e.g. VIP2026):</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_PROMO_CODE


async def receive_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["promo_code"] = update.message.text.strip().upper()
    await update.message.reply_text(
        f"<blockquote><b>{ce('money')} Send reward amount in INR (e.g. 50):</b></blockquote>",
        reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
    )
    return WAIT_FOR_PROMO_REWARD


async def receive_promo_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["promo_reward"] = int(float(update.message.text.strip()) * 100)
        await update.message.reply_text(
            f"<blockquote><b>{ce('user')} Send max uses (e.g. 100 for 100 users):</b></blockquote>",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
        )
        return WAIT_FOR_PROMO_USES
    except Exception:
        await update.message.reply_text("Invalid amount.", reply_markup=await admin_menu_kb(update.effective_user.id))
        return ConversationHandler.END


async def receive_promo_uses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uses = int(update.message.text.strip())
        code = context.user_data["promo_code"]
        reward = context.user_data["promo_reward"]
        if await db.create_promo(code, reward, uses):
            await update.message.reply_text(
                f"<blockquote>{ce('success')} <b>Promo Code <code>{code}</code> Created!</b></blockquote>",
                reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(
                f"<blockquote>{ce('fail')} <b>Code already exists!</b></blockquote>",
                reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
            )
    except Exception:
        await update.message.reply_text("Invalid number.", reply_markup=await admin_menu_kb(update.effective_user.id))
    context.user_data.clear()
    return ConversationHandler.END


async def prompt_edit_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('memo')} Send the new FAQ Text (HTML supported):</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_FAQ


async def receive_edit_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_setting("faq_text", update.message.text)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>FAQ Updated Successfully!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def prompt_edit_tos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('memo')} Send the new Terms of Service (TOS) Text:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_TOS


async def receive_edit_tos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_setting("tos_text", update.message.text)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>TOS Updated Successfully!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def prompt_edit_howto_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('memo')} Send the new HOW TO USE Text (HTML supported):</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_HOW_TO_TEXT


async def receive_howto_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_setting("how_to_text", update.message.text)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>How To Use Text Updated Successfully!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def prompt_edit_howto_vid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('link')} Send the new HOW TO USE Video URL:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_HOW_TO_VIDEO


async def receive_howto_vid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_setting("how_to_video", update.message.text.strip())
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>How To Use Video Link Updated Successfully!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


@staff_required
async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('broadcast')} Send any message to broadcast (Text, Photo, Video, Sticker, GIF, etc.):</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_BROADCAST


@staff_required
async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return ConversationHandler.END

    user_ids = await db.get_all_verified_user_ids()
    total = len(user_ids)
    if total == 0:
        await msg.reply_text(f"{ce('fail')} No verified users to broadcast to.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    sent, failed, blocked = 0, 0, 0
    last_error = "None"
    status_msg = await msg.reply_text(f"{ce('broadcast')} <b>Broadcast starting for {total} users...</b>", parse_mode=ParseMode.HTML)
    
    # Ultra-safe forward detection
    is_forwarded = False
    try:
        if getattr(msg, 'forward_origin', None) or getattr(msg, 'forward_from', None) or \
           getattr(msg, 'forward_from_chat', None) or getattr(msg, 'forward_date', None):
            is_forwarded = True
    except Exception:
        is_forwarded = False
    
    start_time = time.time()
    
    for i, uid in enumerate(user_ids):
        success = False
        try:
            if is_forwarded:
                try:
                    await context.bot.forward_message(chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
                    success = True
                except Exception as e:
                    err_s = str(e).lower()
                    if any(x in err_s for x in ["forbidden", "deactivated", "blocked", "voice_messages_forbidden"]):
                        blocked += 1
                        continue
                    try:
                        await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
                        success = True
                    except Exception as e2:
                        err_s2 = str(e2).lower()
                        if any(x in err_s2 for x in ["forbidden", "deactivated", "blocked", "voice_messages_forbidden"]):
                            blocked += 1
                        else:
                            last_error = f"Fwd: {str(e)} | Copy: {str(e2)}"
            else:
                try:
                    await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
                    success = True
                except Exception as e:
                    err_s = str(e).lower()
                    if any(x in err_s for x in ["forbidden", "deactivated", "blocked", "voice_messages_forbidden"]):
                        blocked += 1
                    else:
                        last_error = f"Copy: {str(e)}"

            if success:
                sent += 1
            else:
                # If not a known block/forbidden error, count as failed
                curr_err = str(last_error).lower()
                if not any(x in curr_err for x in ["forbidden", "deactivated", "blocked", "voice_messages_forbidden"]):
                    failed += 1
        except Exception as e:
            err_s = str(e).lower()
            if any(x in err_s for x in ["forbidden", "deactivated", "blocked", "voice_messages_forbidden"]):
                blocked += 1
            else:
                last_error = f"Outer: {str(e)}"
                failed += 1
        
        # Update progress every 5 users
        if (i + 1) % 5 == 0 or (i + 1) == total:
            elapsed = time.time() - start_time
            try:
                await status_msg.edit_text(
                    f"{ce('broadcast')} <b>Broadcast in progress...</b>\n\n"
                    f"{ce('success')} <b>Sent:</b> {sent}\n"
                    f"{ce('fail')} <b>Failed:</b> {failed}\n"
                    f"{ce('poop')} <b>Blocked/Deleted:</b> {blocked}\n"
                    f"{ce('stats')} <b>Progress:</b> {i+1}/{total}\n"
                    f"{ce('time')} <b>Elapsed:</b> {int(elapsed)}s",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
        
        await asyncio.sleep(0.08)

    await db.log_admin_action(update.effective_user.id, "Broadcast", f"Sent: {sent}, Failed: {failed}, Blocked: {blocked}")
    
    final_text = (
        f"<blockquote>{ce('success')} <b>Broadcast Finished.</b>\n\n"
        f"{ce('success')} <b>Successfully Sent:</b> {sent}\n"
        f"{ce('fail')} <b>Failed (Error):</b> {failed}\n"
        f"{ce('poop')} <b>Blocked/Deleted:</b> {blocked}\n"
        f"{ce('user')} <b>Total Target:</b> {total}</blockquote>"
    )
    if failed > 0:
        final_text += f"\n\n<b>LAST TECHNICAL ERROR:</b>\n<code>{last_error[:200]}</code>"

    await status_msg.edit_text(
        final_text,
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


@verification_required
async def prompt_set_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        "<blockquote><b>Send the new UPI ID in chat:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_SETTING_UPI


async def receive_set_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_setting("upi_id", update.message.text.strip())
    await db.log_admin_action(update.effective_user.id, "Changed UPI", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>UPI ID Updated!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


@verification_required
async def prompt_set_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        "<blockquote><b>Please send the QR code as a PHOTO (not a link).</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_SETTING_QR


async def receive_set_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file_id = photo.file_id
    await db.set_setting("qr_image", file_id)
    await db.log_admin_action(update.effective_user.id, "Changed QR Image", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>QR Image Updated!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


@verification_required
async def prompt_set_sup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        "<blockquote><b>Send the new Support Username (e.g. @YourAdmin):</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_SETTING_SUP


async def receive_set_sup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_setting("support_user", update.message.text.strip())
    await db.log_admin_action(update.effective_user.id, "Changed Support User", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Support Username Updated!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


@verification_required
async def prompt_set_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        "<blockquote><b>Send new Unauthorized Action Alert (Insult Message):</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_SETTING_MSG


async def receive_set_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.set_setting("unauth_msg", update.message.text.strip())
    await db.log_admin_action(update.effective_user.id, "Changed Insult Msg", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Insult Message Updated!</b></blockquote>",
        reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


@verification_required
async def prompt_manual_bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        "<blockquote><b>Send the Telegram User ID to add funds to:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_MANUAL_BAL_USER


@verification_required
async def prompt_reseller_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('shield')} ADD/EDIT RESELLER</b></blockquote>\n\n"
        f"Please send the <b>User ID</b> or <b>@Username</b> of the user you want to make a reseller.",
        cancel_kb()
    )
    return WAIT_FOR_RESELLER_USER


async def receive_manual_bal_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        if not await db.get_user(uid):
            await update.message.reply_text("User not found in DB.", reply_markup=await admin_menu_kb(update.effective_user.id))
            return ConversationHandler.END
        context.user_data["man_bal_uid"] = uid
        await update.message.reply_text(
            "<blockquote><b>Send amount in INR to add (e.g. 500):</b></blockquote>",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
        )
        return WAIT_FOR_MANUAL_BAL_AMT
    except Exception:
        await update.message.reply_text("Invalid ID.", reply_markup=await admin_menu_kb(update.effective_user.id))
        return ConversationHandler.END


async def receive_manual_bal_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text.strip())
        paise = int(amt * 100)
        uid = context.user_data["man_bal_uid"]
        await db.update_balance(uid, paise)
        await db.log_admin_action(update.effective_user.id, "Manual Balance Add", f"UID: {uid}, Amt: {amt}")
        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>Added ₹{amt} to User {uid}.</b></blockquote>",
            reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
        )
        try:
            await context.bot.send_message(
                uid,
                f"<blockquote>{ce('success')} <b>FUNDS ADDED!</b></blockquote>\n\n"
                f"₹{amt:.2f} was added to your wallet by admin.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    except Exception:
        await update.message.reply_text("Invalid amount.", reply_markup=await admin_menu_kb(update.effective_user.id))
    return ConversationHandler.END


@verification_required
async def prompt_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        "<blockquote><b>Send the Telegram User ID to BAN:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_BAN_USER


async def receive_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text)
        await db.ban_user(uid, 1)
        await db.log_admin_action(update.effective_user.id, "Banned User", f"UID: {uid}")
        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>User <code>{uid}</code> is now BANNED.</b></blockquote>",
            reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
        )
    except Exception:
        await update.message.reply_text("Invalid ID.", reply_markup=await admin_menu_kb(update.effective_user.id))
    return ConversationHandler.END


@verification_required
async def prompt_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        "<blockquote><b>Send the Telegram User ID to UNBAN:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_UNBAN_USER


async def receive_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text)
        await db.ban_user(uid, 0)
        await db.log_admin_action(update.effective_user.id, "Unbanned User", f"UID: {uid}")
        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>User <code>{uid}</code> is now UNBANNED.</b></blockquote>",
            reply_markup=await admin_menu_kb(update.effective_user.id), parse_mode=ParseMode.HTML,
        )
    except Exception:
        await update.message.reply_text("Invalid ID.", reply_markup=await admin_menu_kb(update.effective_user.id))
    return ConversationHandler.END


# ==============================================================================
# 11. MAIN APPLICATION BUILDER & EXECUTION
# ==============================================================================
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))

    # ── Admin conversation handler ─────────────────────────────────────────────
    admin_conv = ConversationHandler(
        entry_points=[
            # Payment service login
            # Broadcast & Settings
            CallbackQueryHandler(prompt_broadcast, pattern="^admin_broadcast$"),
            CallbackQueryHandler(prompt_add_staff, pattern="^adm_add_staff$"),
            CallbackQueryHandler(prompt_rem_staff, pattern="^adm_rem_staff$"),
            CallbackQueryHandler(prompt_set_upi, pattern="^adm_set_upi$"),
            CallbackQueryHandler(prompt_set_qr, pattern="^adm_set_qr$"),
            CallbackQueryHandler(prompt_set_sup, pattern="^adm_set_sup$"),
            CallbackQueryHandler(prompt_set_msg, pattern="^adm_set_msg$"),
            CallbackQueryHandler(prompt_set_dl_link, pattern="^adm_set_dl_link$"),
            # Users
            CallbackQueryHandler(prompt_ban, pattern="^adm_ban_usr$"),
            CallbackQueryHandler(prompt_unban, pattern="^adm_unban_usr$"),
            CallbackQueryHandler(prompt_manual_bal, pattern="^adm_add_bal$"),
            # Resellers
            CallbackQueryHandler(prompt_reseller_add, pattern="^adm_reseller_add$"),
            # Products
            CallbackQueryHandler(prompt_add_prod, pattern="^adm_add_prod$"),
            CallbackQueryHandler(prompt_add_plan, pattern="^adm_add_plan_"),
            CallbackQueryHandler(prompt_add_keys, pattern="^adm_kplan_"),
            CallbackQueryHandler(prompt_edit_desc, pattern="^adm_edit_desc_"),
            # Tickets
            CallbackQueryHandler(prompt_ticket_reply, pattern="^adm_tkt_"),
            # Promos
            CallbackQueryHandler(prompt_create_promo, pattern="^adm_create_promo$"),
            # Content
            CallbackQueryHandler(prompt_edit_faq, pattern="^adm_edit_faq$"),
            CallbackQueryHandler(prompt_edit_tos, pattern="^adm_edit_tos$"),
            CallbackQueryHandler(prompt_edit_howto_text, pattern="^adm_edit_howto_text$"),
            CallbackQueryHandler(prompt_edit_howto_vid, pattern="^adm_edit_howto_vid$"),
        ],
        states={
            WAIT_FOR_BROADCAST:       [MessageHandler(~filters.COMMAND, receive_broadcast)],
            WAIT_FOR_SETTING_UPI:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_upi)],
            WAIT_FOR_SETTING_QR:      [MessageHandler(filters.PHOTO, receive_set_qr)],
            WAIT_FOR_SETTING_SUP:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_sup)],
            WAIT_FOR_SETTING_MSG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_msg)],
            WAIT_FOR_PROD_LINK:       [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_dl_link)],
            WAIT_FOR_ADD_STAFF:       [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_staff)],
            WAIT_FOR_REM_STAFF:       [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rem_staff)],
            WAIT_FOR_BAN_USER:        [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban)],
            WAIT_FOR_UNBAN_USER:      [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_unban)],
            WAIT_FOR_MANUAL_BAL_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_manual_bal_user)],
            WAIT_FOR_MANUAL_BAL_AMT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_manual_bal_amt)],
            WAIT_FOR_NEW_PROD_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prod_name)],
            WAIT_FOR_NEW_PROD_DESC:   [CallbackQueryHandler(receive_prod_desc, pattern="^desc_")],
            WAIT_FOR_CUSTOM_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_desc)],
            WAIT_FOR_EDIT_PROD_DESC:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_prod_desc),
                CallbackQueryHandler(receive_edit_prod_desc, pattern="^edit_"),
            ],
            WAIT_FOR_PLAN_DUR:        [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_dur)],
            WAIT_FOR_PLAN_PRICE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_price)],
            WAIT_FOR_ADD_KEYS:        [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_keys)],
            WAIT_FOR_ADMIN_TICKET_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ticket_reply)],
            WAIT_FOR_PROMO_CODE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_promo_code)],
            WAIT_FOR_PROMO_REWARD:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_promo_reward)],
            WAIT_FOR_PROMO_USES:      [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_promo_uses)],
            WAIT_FOR_FAQ:             [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_faq)],
            WAIT_FOR_TOS:             [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_tos)],
            WAIT_FOR_HOW_TO_TEXT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_howto_text)],
            WAIT_FOR_HOW_TO_VIDEO:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_howto_vid)],
            # Reseller
            WAIT_FOR_RESELLER_USER:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reseller_user)],
            WAIT_FOR_RESELLER_DAYS:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reseller_days)],
            WAIT_FOR_RESELLER_DISCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reseller_discount)],

        },
        fallbacks=[
            CallbackQueryHandler(cancel_conv_callback, pattern="^cancel_conv$"),
            CallbackQueryHandler(admin_nav_fallback, pattern="^(admin_|adm_)"),
        ],
        per_message=False,
        allow_reentry=True,
    )
    app.add_handler(admin_conv)

    # ── User conversation handler ──────────────────────────────────────────────
    user_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_ticket, pattern="^user_ticket$"),
            CallbackQueryHandler(prompt_user_promo, pattern="^user_promo$"),
            CallbackQueryHandler(prompt_add_funds, pattern="^user_add_funds$"),
        ],
        states={
            WAIT_FOR_TICKET:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ticket)],
            WAIT_FOR_USER_PROMO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_promo)],
            WAIT_FOR_ADD_FUND_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_fund_amt)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv_callback, pattern="^cancel_conv$")],
        per_message=False,
        allow_reentry=True,
    )
    app.add_handler(user_conv)

    # ── Callback routers ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(
        handle_user_callbacks,
        pattern="^(user_|buy_|gen_qr_|verify_pay_|confirm_buy_|add_f_|kp_|pay_bal_)",
    ))

    app.add_handler(CallbackQueryHandler(
        handle_admin_callbacks,
        pattern="^(admin_|adm_)",
    ))

    logger.info("🔥 Bot is starting (MongoDB + Render + Self-hosted Payment Service) 🔥")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    # Retry-guard: during Render deploys the old instance can still be polling
    # while the new one starts, causing a transient getUpdates Conflict.
    # Retry with backoff instead of crashing; give up eventually so Render's
    # own restart logic takes over if a real duplicate instance exists.
    MAX_POLL_RETRIES = 6
    retry_delay = 15
    for attempt in range(1, MAX_POLL_RETRIES + 1):
        try:
            main()
            break  # Clean shutdown — don't restart.
        except Conflict:
            logger.warning(
                f"Conflict: another bot instance is polling this token "
                f"(attempt {attempt}/{MAX_POLL_RETRIES}). Retrying in {retry_delay}s..."
            )
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        except NetworkError as e:
            logger.warning(f"NetworkError while polling: {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        except Exception:
            logger.error("FATAL ERROR DURING STARTUP:")
            logger.error(traceback.format_exc())
            # Force flush logs
            import sys
            sys.stderr.flush()
            sys.stdout.flush()
            raise
