#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hack Store Telegram Bot — MongoDB + Render edition.
Payment: Self-hosted UPI microservice (aiohttp).
"""

import asyncio
import io
import logging
import math
import re
import time
import traceback
import uuid
import warnings
from datetime import datetime
from urllib.parse import quote

import aiohttp

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    LinkPreviewOptions,
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import BadRequest
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
    return "🔹"


def ce_button(name: str) -> str:
    if name in EMOJIS:
        return EMOJIS[name][0]
    return "🔹"


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
    # NEW: Payment service login states
    WAIT_FOR_SVC_MOBILE, WAIT_FOR_SVC_EMAIL, WAIT_FOR_SVC_OTP,
    # NEW: Microservice URL setting
    WAIT_FOR_SVC_URL,
) = range(31)


# ==============================================================================
# 3. DATABASE INSTANCE + DEFAULT SETTINGS SEED
# ==============================================================================
db = DatabaseManager()

DEFAULT_SETTINGS = {
    "qr_image": None,
    "upi_id": "admin@upi",
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
    # NEW: Payment microservice settings
    "payment_svc_url": "http://localhost:8000",
    "payment_svc_token": "",       # session token from /login
    "payment_svc_mobile": "",      # stored for re-login display
    "payment_svc_email": "",       # stored for re-login display
}
db.seed_default_settings(DEFAULT_SETTINGS)


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
async def svc_login(svc_url: str, admin_id: int, mobile: str, email: str, otp: str) -> dict:
    """Call POST /login on the payment microservice."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"admin_id": admin_id, "mobile": mobile, "email": email, "otp": otp}
            async with session.post(f"{svc_url}/login", json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def svc_generate_qr(svc_url: str, token: str, amount: float,
                          order_id: str, upi_id: str, payee_name: str = "Hack Store") -> dict:
    """Call POST /generate_qr on the payment microservice."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "amount": amount,
                "order_id": order_id,
                "upi_id": upi_id,
                "payee_name": payee_name,
            }
            async with session.post(f"{svc_url}/generate_qr", json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def svc_verify_payment(svc_url: str, token: str, order_id: str) -> dict:
    """Call POST /verify_payment on the payment microservice."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token}"}
            payload = {"order_id": order_id}
            async with session.post(f"{svc_url}/verify_payment", json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


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
    req = db.get_fund_request_by_order(order_id)
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

        is_maintenance = db.get_setting("maintenance_mode", "0")
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

        if user_id in ADMIN_IDS:
            return await func(update, context, *args, **kwargs)

        user = db.get_user(user_id)
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

    db.add_user(user_id, update.effective_user.username, update.effective_user.first_name)

    user = db.get_user(user_id)
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

    db.verify_user(user_id)

    try:
        phone_number = contact.phone_number
        first_name = contact.first_name
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        photo_id = (
            photos.photos[0][-1].file_id if photos.total_count > 0
            else db.get_setting("default_pfp")
        )
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

    user = db.get_user(user_id)
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
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("BUY HACK", callback_data="user_buy_hack", icon_custom_emoji_id=EMOJIS["cart"][1], style="primary"),
         InlineKeyboardButton("DOWNLOAD APK", callback_data="user_downloads", icon_custom_emoji_id=EMOJIS["disk"][1], style="primary")],
        [InlineKeyboardButton("MY KEY", callback_data="user_my_keys_0", icon_custom_emoji_id=EMOJIS["key"][1], style="primary"),
         InlineKeyboardButton("STOCK", callback_data="user_stock", icon_custom_emoji_id=EMOJIS["stock"][1], style="primary")],
        [InlineKeyboardButton("PROFILE", callback_data="user_profile", icon_custom_emoji_id=EMOJIS["user"][1], style="primary"),
         InlineKeyboardButton("HOW TO USE", callback_data="user_how_to", icon_custom_emoji_id=EMOJIS["mobile"][1], style="primary")],
        [InlineKeyboardButton("SUPPORT", callback_data="user_contact", icon_custom_emoji_id=EMOJIS["contact"][1], style="primary")],
    ])


def back_kb(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=callback_data, icon_custom_emoji_id=EMOJIS["back"][1], style="danger")]])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Cancel Process", callback_data="cancel_conv", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")]])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Dashboard", callback_data="admin_stats", icon_custom_emoji_id=EMOJIS["stats"][1], style="primary")],
        [InlineKeyboardButton("Products", callback_data="admin_products", icon_custom_emoji_id=EMOJIS["bag"][1], style="primary"),
         InlineKeyboardButton("Keys", callback_data="admin_keys", icon_custom_emoji_id=EMOJIS["key"][1], style="primary")],
        [InlineKeyboardButton("Users", callback_data="admin_users", icon_custom_emoji_id=EMOJIS["user"][1], style="primary"),
         InlineKeyboardButton("Pending Payments", callback_data="admin_pending_payments", icon_custom_emoji_id=EMOJIS["pending"][1], style="primary")],
        [InlineKeyboardButton("Broadcast", callback_data="admin_broadcast", icon_custom_emoji_id=EMOJIS["broadcast"][1], style="primary"),
         InlineKeyboardButton("Tickets", callback_data="admin_tickets", icon_custom_emoji_id=EMOJIS["chat"][1], style="primary")],
        [InlineKeyboardButton("Settings", callback_data="admin_settings", icon_custom_emoji_id=EMOJIS["settings"][1], style="primary"),
         InlineKeyboardButton("Maintenance", callback_data="adm_maintenance", icon_custom_emoji_id=EMOJIS["tools"][1], style="primary")],
        [InlineKeyboardButton("UPI Session", callback_data="admin_svc_session", icon_custom_emoji_id=EMOJIS["session"][1], style="primary"),
         InlineKeyboardButton("Backup DB", callback_data="adm_export_db", icon_custom_emoji_id=EMOJIS["disk"][1], style="primary")],
        [InlineKeyboardButton("Exit Admin", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
    ])


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

    is_new = db.add_user(user.id, user.username, user.first_name, referrer_id)
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

    user_data = db.get_user(user.id)
    if user_data.get("is_banned", 0):
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>ACCOUNT BANNED</b>\nContact Admin.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    if not user_data.get("verified", 0):
        await show_verification_prompt(update, context)
        return

    is_maintenance = db.get_setting("maintenance_mode", "0")
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
            user_data = db.get_user(user_id)
            bal = user_data.get("balance", 0) / 100
            await safe_edit_text(update, context, _welcome_text(bal), main_menu_kb())

        # ── Buy Hack ───────────────────────────────────────────────────────────
        elif data == "user_buy_hack":
            await query.answer()
            products = db.get_active_products()
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
            prod = db.get_product(prod_id)
            plans = db.get_plans(prod_id)
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
                stock = db.get_available_key_count(pl['id'])
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
            plan = db.get_plan(plan_id)
            text = (
                f"<blockquote><b>{ce('cart')} PURCHASE CONFIRMATION</b></blockquote>\n\n"
                f"<b>Product:</b> {plan['product_name']}\n"
                f"<b>Duration:</b> {plan['duration']}\n"
                f"<b>Price:</b> ₹{plan['price']/100:.2f}\n"
                f"{get_line(12)}\n"
                f"<i>Click below to generate your unique payment QR code (valid 5 min).</i>"
            )
            buttons = [
                [InlineKeyboardButton("GENERATE PAYMENT QR", callback_data=f"gen_qr_{plan_id}", icon_custom_emoji_id=EMOJIS["pay"][1], style="primary")],
                [InlineKeyboardButton("CANCEL", callback_data=f"buy_prod_{plan['product_id']}", icon_custom_emoji_id=EMOJIS["fail"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        # ── Generate QR via microservice ───────────────────────────────────────
        elif data.startswith("gen_qr_"):
            await query.answer("Generating QR…")
            plan_id = int(data.split("_")[2])
            plan = db.get_plan(plan_id)
            price = plan['price'] / 100

            svc_url   = db.get_setting("payment_svc_url", "http://localhost:8000")
            svc_token = db.get_setting("payment_svc_token", "")
            admin_upi = db.get_setting("upi_id", "")

            if not svc_token:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} <b>Payment service not configured.</b>\n"
                    f"Please ask admin to login to the UPI session first.</blockquote>",
                    back_kb("user_buy_hack"),
                )
                return

            if not admin_upi or "@" not in admin_upi:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} <b>UPI ID is not configured.</b>\n"
                    f"Admin must set a valid UPI ID in the Admin Panel first.</blockquote>",
                    back_kb("user_buy_hack"),
                )
                return

            order_id = generate_order_id(plan_id, user_id)
            # Store fund_request in DB with PENDING status
            db.create_fund_request_with_order(user_id, order_id, plan_id, plan['price'])

            # Call microservice
            payee = db.get_setting("global_brand_name", "Hack Store") or "Hack Store"
            result = await svc_generate_qr(svc_url, svc_token, price, order_id, admin_upi, payee)

            if result.get("status") != "success":
                err = result.get("message", "Unknown error")
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} <b>QR generation failed:</b> {err}\n\n"
                    f"Please contact support.</blockquote>",
                    back_kb("user_buy_hack"),
                )
                return

            qr_data    = result["data"]
            qr_url     = qr_data.get("qr_url", "")
            qr_b64     = qr_data.get("qr_b64", "")
            expires_at = qr_data.get("expires_at_ist", "5 minutes")

            # Prefer raw bytes (works without any public URL — the microservice
            # may be on localhost or behind a private network).
            try:
                import base64 as _b64
                qr_photo = io.BytesIO(_b64.b64decode(qr_b64)) if qr_b64 else qr_url
                if isinstance(qr_photo, io.BytesIO):
                    qr_photo.name = f"{order_id}.png"
            except Exception:
                qr_photo = qr_url

            caption = (
                f"<blockquote><b>{ce('card')} SCAN &amp; PAY ₹{price:.2f}</b></blockquote>\n\n"
                f"<b>{ce('1')} Scan the QR code below with any UPI app.</b>\n"
                f"<b>{ce('2')} Pay exactly ₹{price:.2f}.</b>\n"
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

            # Schedule expiration job (5 minutes = 300 seconds)
            context.job_queue.run_once(
                qr_expiration_job,
                when=300,
                data={
                    "chat_id": user_id,
                    "message_id": msg.message_id,
                    "order_id": order_id
                }
            )

        # ── Verify payment (user clicks I'VE PAID) ────────────────────────────
        elif data.startswith("verify_pay_"):
            await query.answer("Verifying payment…", show_alert=False)
            order_id  = data[len("verify_pay_"):]
            svc_url   = db.get_setting("payment_svc_url", "http://localhost:8000")
            svc_token = db.get_setting("payment_svc_token", "")

            result = await svc_verify_payment(svc_url, svc_token, order_id)

            if result.get("status") == "success":
                pay_data = result["data"]
                utr = pay_data.get("utr", "N/A")
                txn_id = pay_data.get("transaction_id", "N/A")
                sender_name = pay_data.get("sender_name", "Unknown")
                paid_amount = pay_data.get("amount", 0)
                payment_time = pay_data.get("payment_time_ist", "")
                upi_id_paid = pay_data.get("upi_id", "")

                # Get fund_request to find plan_id
                req = db.get_fund_request_by_order(order_id)
                if not req:
                    await query.answer("Order not found. Contact support.", show_alert=True)
                    return

                # Anti-replay: if this UTR is already attached to a different
                # order in our own DB, refuse delivery and alert admins.
                if utr and utr != "N/A" and db.is_utr_already_used(utr, except_order_id=order_id):
                    db.update_fund_request_by_order(order_id, "REJECTED_DUPLICATE_UTR",
                                                   utr=utr, transaction_id=txn_id,
                                                   sender_name=sender_name,
                                                   payment_time=payment_time)
                    await safe_edit_text(
                        update, context,
                        f"<blockquote>{ce('fail')} <b>This payment reference (UTR) "
                        f"has already been used to claim a key.</b>\n\n"
                        f"Each payment can be used only once. If this is a "
                        f"genuine new payment, please contact support with the "
                        f"order ID below.\n\n<code>{order_id}</code></blockquote>",
                        back_kb("user_main"),
                    )
                    # Loud alert to admins about replay attempt
                    user_obj = db.get_user(user_id)
                    uname = (user_obj.get("username") or "").lstrip("@")
                    fname = user_obj.get("first_name") or ""
                    for admin in ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin,
                                text=(
                                    f"<blockquote><b>{ce('siren')} UTR REPLAY BLOCKED</b></blockquote>\n"
                                    f"<b>User:</b> <code>{user_id}</code> "
                                    f"({fname} @{uname})\n"
                                    f"<b>Order:</b> <code>{order_id}</code>\n"
                                    f"<b>Tried UTR:</b> <code>{utr}</code>\n"
                                    f"<b>Txn:</b> <code>{txn_id}</code>\n"
                                    f"<b>Sender:</b> {sender_name}\n"
                                    f"<i>This UTR was already used by another "
                                    f"order. No key was delivered.</i>"
                                ),
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception:
                            pass
                    return

                # Deliver key automatically
                success, msg, info = db.purchase_key_automated(user_id, req["plan_id"])
                if success:
                    db.update_fund_request_by_order(
                        order_id, "APPROVED",
                        utr=utr, transaction_id=txn_id,
                        sender_name=sender_name, payment_time=payment_time,
                        key_value=info.get("key"),
                    )

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
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await context.bot.send_message(
                        chat_id=user_id, text=key_text,
                        reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML,
                    )

                    # Detailed admin notification
                    user_obj = db.get_user(user_id)
                    uname = (user_obj.get("username") or "").lstrip("@")
                    fname = user_obj.get("first_name") or ""
                    plan_obj = db.get_plan(req["plan_id"]) or {}
                    expected_amount = plan_obj.get("price", paid_amount)
                    for admin in ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin,
                                text=(
                                    f"<blockquote><b>{ce('success')} AUTO PAYMENT SUCCESS — KEY DELIVERED</b></blockquote>\n"
                                    f"{get_line(12)}\n"
                                    f"<b>{ce('user')} User:</b> <code>{user_id}</code> "
                                    f"({fname} @{uname})\n"
                                    f"<b>{ce('card')} Order:</b> <code>{order_id}</code>\n"
                                    f"<b>{ce('money')} Amount:</b> ₹{expected_amount}\n"
                                    f"<b>{ce('bag')} Product:</b> {info['product']} — {info['duration']}\n"
                                    f"{get_line(12)}\n"
                                    f"<b>UTR:</b> <code>{utr}</code>\n"
                                    f"<b>Txn ID:</b> <code>{txn_id}</code>\n"
                                    f"<b>Sender:</b> {sender_name}\n"
                                    f"<b>Paid To UPI:</b> <code>{upi_id_paid}</code>\n"
                                    f"<b>Payment Time:</b> {payment_time}\n"
                                    f"{get_line(12)}\n"
                                    f"<b>{ce('key')} Delivered Key:</b>\n<code>{info['key']}</code>\n"
                                    f"<b>{ce('time')} Expiry:</b> {info['expiry'][:10]}"
                                ),
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception:
                            pass
                else:
                    # Payment verified but key delivery failed (out of stock etc.)
                    db.update_fund_request_by_order(
                        order_id, "PAID_NO_STOCK",
                        utr=utr, transaction_id=txn_id,
                        sender_name=sender_name, payment_time=payment_time,
                    )
                    await safe_edit_text(
                        update, context,
                        f"<blockquote>{ce('warning')} <b>Payment received but key delivery failed: {msg}</b>\n\n"
                        f"Please contact support with your Order ID:\n<code>{order_id}</code></blockquote>",
                        back_kb("user_main"),
                    )
                    # Urgent admin alert — money received, no key delivered
                    user_obj = db.get_user(user_id)
                    uname = (user_obj.get("username") or "").lstrip("@")
                    fname = user_obj.get("first_name") or ""
                    for admin in ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin,
                                text=(
                                    f"<blockquote><b>{ce('siren')} PAYMENT RECEIVED — DELIVERY FAILED</b></blockquote>\n"
                                    f"<b>Reason:</b> {msg}\n"
                                    f"{get_line(12)}\n"
                                    f"<b>User:</b> <code>{user_id}</code> "
                                    f"({fname} @{uname})\n"
                                    f"<b>Order:</b> <code>{order_id}</code>\n"
                                    f"<b>Amount:</b> ₹{paid_amount}\n"
                                    f"<b>UTR:</b> <code>{utr}</code>\n"
                                    f"<b>Txn:</b> <code>{txn_id}</code>\n"
                                    f"<b>Sender:</b> {sender_name}\n"
                                    f"<b>Paid To UPI:</b> <code>{upi_id_paid}</code>\n"
                                    f"<b>Time:</b> {payment_time}\n"
                                    f"<i>Please refund or top-up stock and "
                                    f"deliver manually.</i>"
                                ),
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception:
                            pass
            elif "already been used" in (result.get("message") or "").lower():
                # Service-side replay rejection
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('fail')} <b>This payment reference has "
                    f"already been used.</b>\n\nPlease make a fresh payment "
                    f"to claim a new key.\n\n<b>Order:</b> <code>{order_id}</code></blockquote>",
                    back_kb("user_main"),
                )
            else:
                # Not paid yet
                buttons = [
                    [InlineKeyboardButton("Try Again", callback_data=f"verify_pay_{order_id}", icon_custom_emoji_id=EMOJIS["refresh"][1], style="primary")],
                    [InlineKeyboardButton("Back to Menu", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
                ]
                await safe_edit_text(
                    update, context,
                    f"<blockquote><b>{ce('fail')} Payment Not Received Yet</b></blockquote>\n\n"
                    f"<i>Please wait a moment and try again. UPI payments may take up to 2 minutes.</i>\n\n"
                    f"<b>Order ID:</b> <code>{order_id}</code>",
                    InlineKeyboardMarkup(buttons),
                )

        # ── Downloads ─────────────────────────────────────────────────────────
        elif data == "user_downloads":
            await query.answer()
            channel_link = db.get_setting("global_channel_link", "https://t.me/YourDownloadChannel")
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
                [InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons),
                                 link_preview_options=LinkPreviewOptions(is_disabled=True))

        elif data == "user_how_to":
            await query.answer()
            text = db.get_setting("how_to_text")
            vid = db.get_setting("how_to_video")
            buttons = []
            if vid and vid.startswith("http"):
                buttons.append([InlineKeyboardButton("Watch Tutorial Video", url=vid, style="primary", icon_custom_emoji_id=EMOJIS["rocket"][1])])
            buttons.append([InlineKeyboardButton("Back", callback_data="user_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons),
                                 link_preview_options=LinkPreviewOptions(is_disabled=True))

        elif data == "user_balance":
            await query.answer()
            user_data = db.get_user(user_id)
            bal = user_data.get("balance", 0) / 100
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
            share_msg = (
                f"🔥 Join the Ultimate Hack Store! Get premium mods and scripts instantly. "
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
            leaders = db.get_leaderboard()
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
            await safe_edit_text(update, context, text, back_kb("user_main"))

        elif data == "user_faq":
            await query.answer()
            faq = db.get_setting("faq_text")
            tos = db.get_setting("tos_text")
            text = (
                f"<blockquote><b>{ce('books')} FAQ &amp; TERMS OF SERVICE</b></blockquote>\n\n"
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
            kb = back_kb("user_main")
            try:
                photos = await context.bot.get_user_profile_photos(user_id, limit=1)
                photo_id = (
                    photos.photos[0][-1].file_id if photos.total_count > 0
                    else db.get_setting("default_pfp")
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
            total_keys = db.get_user_keys_count(user_id)
            keys = db.get_user_keys(user_id, offset, limit)
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
                    f"🎮 <b>{k['name']}</b> ({k['duration']})\n"
                    f"<code>{k['key_value']}</code>\n"
                    f"⏳ <b>Expiry:</b> {k['expiry_date'][:10]}\n"
                    f"{get_line(10)}\n"
                )
            total_pages = max(1, math.ceil(total_keys / limit))
            buttons = pagination_kb(page, total_pages, "user_my_keys", "user_main")
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "user_stock":
            await query.answer()
            summary = db.get_stock_summary()
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
                    text += f"  ├ <b>{pl['duration']}: {pl['count']} keys</b>\n"
                text += "\n"
            await safe_edit_text(update, context, text, back_kb("user_main"))

        elif data == "user_contact":
            await query.answer()
            sup_user = db.get_setting("support_user")
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
@verification_required
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        insult_raw = db.get_setting("unauth_msg")
        await update.message.reply_text(insult_raw, parse_mode=ParseMode.HTML)
        return
    await update.message.reply_text(
        f"<blockquote><b>{ce('admin')} ENTERPRISE ADMIN PANEL</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
    )


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
            await safe_edit_text(
                update, context,
                f"<blockquote><b>{ce('admin')} ENTERPRISE ADMIN PANEL</b></blockquote>",
                admin_menu_kb(),
            )

        # ── Dashboard ─────────────────────────────────────────────────────────
        elif data == "admin_stats":
            await query.answer()
            users, rev, sold, avail = db.get_global_stats()
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

        # ── UPI Session Management ─────────────────────────────────────────────
        elif data == "admin_svc_session":
            await query.answer()
            token = db.get_setting("payment_svc_token", "")
            svc_url = db.get_setting("payment_svc_url", "http://localhost:8000")
            mobile  = db.get_setting("payment_svc_mobile", "Not set")
            email   = db.get_setting("payment_svc_email", "Not set")
            is_active = bool(token)

            # Probe the microservice for its auto-detected public base + health
            svc_alive = False
            public_base = "—"
            auto_flag = ""
            try:
                async with aiohttp.ClientSession() as _s:
                    async with _s.get(f"{svc_url}/health",
                                      timeout=aiohttp.ClientTimeout(total=4)) as _r:
                        if _r.status == 200:
                            _j = await _r.json()
                            svc_alive = _j.get("status") == "ok"
                            public_base = _j.get("public_base", "—")
                            auto_flag = " (auto-detected)" if _j.get("auto_detected") else ""
            except Exception:
                pass

            status_icon = ce('success') if is_active else ce('fail')
            status_text = "ACTIVE" if is_active else "NOT LOGGED IN"
            svc_icon = ce('success') if svc_alive else ce('fail')
            svc_label = "ONLINE" if svc_alive else "OFFLINE"

            text = (
                f"<blockquote><b>{ce('session')} UPI PAYMENT SESSION</b></blockquote>\n\n"
                f"<b>Login Status:</b> {status_icon} <b>{status_text}</b>\n"
                f"<b>Service Health:</b> {svc_icon} <b>{svc_label}</b>\n"
                f"<b>Internal URL:</b> <code>{svc_url}</code>\n"
                f"<b>Public URL{auto_flag}:</b>\n<code>{public_base}</code>\n"
                f"<b>Mobile:</b> <code>{mobile}</code>\n"
                f"<b>Email:</b> <code>{email}</code>\n"
                f"{get_line(12)}\n"
                f"<i>Login with your Gmail App Password to start accepting automated UPI payments.</i>"
            )
            buttons = []
            if is_active:
                buttons.append([InlineKeyboardButton("Re-Login", callback_data="adm_svc_login_start", style="primary", icon_custom_emoji_id=EMOJIS["refresh"][1])])
                buttons.append([InlineKeyboardButton("Logout", callback_data="adm_svc_logout", style="danger", icon_custom_emoji_id=EMOJIS["fail"][1])])
            else:
                buttons.append([InlineKeyboardButton("Login to Service", callback_data="adm_svc_login_start", style="success", icon_custom_emoji_id=EMOJIS["success"][1])])
            buttons.append([InlineKeyboardButton("Edit Service URL", callback_data="adm_set_svc_url", style="primary", icon_custom_emoji_id=EMOJIS["link"][1])])
            buttons.append([InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "adm_svc_logout":
            await query.answer()
            db.set_setting("payment_svc_token", "")
            await safe_edit_text(
                update, context,
                f"<blockquote>{ce('success')} <b>Logged out from payment service.</b></blockquote>",
                back_kb("admin_svc_session"),
            )

        # ── Pending Payments Panel ─────────────────────────────────────────────
        elif data == "admin_pending_payments":
            await query.answer()
            pending = db.get_pending_fund_requests()
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
                [InlineKeyboardButton("Re-verify All Pending", callback_data="adm_reverify_all", style="primary", icon_custom_emoji_id=EMOJIS["refresh"][1])],
                [InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")],
            ]
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data == "adm_reverify_all":
            await query.answer("Re-verifying all pending payments…", show_alert=True)
            pending = db.get_pending_fund_requests()
            if not pending:
                await safe_edit_text(
                    update, context,
                    f"<blockquote>{ce('success')} No pending payments to verify.</blockquote>",
                    back_kb("admin_main"),
                )
                return

            svc_url  = db.get_setting("payment_svc_url", "http://localhost:8000")
            svc_token = db.get_setting("payment_svc_token", "")
            admin_id  = ADMIN_IDS[0] if ADMIN_IDS else 0

            delivered, failed, not_paid = 0, 0, 0

            for req in pending:
                order_id = req.get("order_id")
                if not order_id:
                    continue
                result = await svc_verify_payment(svc_url, svc_token, admin_id, order_id)
                if result.get("status") == "success":
                    pay_data = result["data"]
                    utr = pay_data.get("utr", "N/A")
                    txn_id = pay_data.get("transaction_id", "N/A")
                    sender_name = pay_data.get("sender_name", "Unknown")
                    payment_time = pay_data.get("payment_time_ist", "")

                    # Anti-replay check before delivery
                    if utr and utr != "N/A" and db.is_utr_already_used(utr, except_order_id=order_id):
                        db.update_fund_request_by_order(
                            order_id, "REJECTED_DUPLICATE_UTR",
                            utr=utr, transaction_id=txn_id,
                            sender_name=sender_name, payment_time=payment_time,
                        )
                        failed += 1
                        await asyncio.sleep(0.3)
                        continue

                    success, msg, info = db.purchase_key_automated(req["user_id"], req["plan_id"])
                    if success:
                        db.update_fund_request_by_order(
                            order_id, "APPROVED",
                            utr=utr, transaction_id=txn_id,
                            sender_name=sender_name, payment_time=payment_time,
                            key_value=info.get("key"),
                        )
                        delivered += 1
                        try:
                            await context.bot.send_message(
                                chat_id=req["user_id"],
                                text=(
                                    f"<blockquote><b>{ce('success')} PAYMENT VERIFIED! {ce('star')}</b></blockquote>\n\n"
                                    f"<b>UTR:</b> <code>{utr}</code>\n"
                                    f"{get_line(12)}\n"
                                    f"<b>Product:</b> {info['product']}\n"
                                    f"<b>Duration:</b> {info['duration']}\n"
                                    f"<b>Expiry:</b> {info['expiry'][:10]}\n\n"
                                    f"<blockquote><b>{ce('key')} YOUR PREMIUM KEY:</b></blockquote>\n"
                                    f"<code>{info['key']}</code>\n\n"
                                    f"<i>Thank you for your patience! {ce('fire')}</i>"
                                ),
                                parse_mode=ParseMode.HTML,
                                reply_markup=main_menu_kb(),
                            )
                        except Exception:
                            pass
                    else:
                        db.update_fund_request_by_order(
                            order_id, "PAID_NO_STOCK",
                            utr=utr, transaction_id=txn_id,
                            sender_name=sender_name, payment_time=payment_time,
                        )
                        failed += 1
                else:
                    not_paid += 1
                await asyncio.sleep(0.3)  # rate limit

            await safe_edit_text(
                update, context,
                f"<blockquote><b>{ce('stats')} RE-VERIFY RESULTS</b></blockquote>\n\n"
                f"<b>{ce('success')} Keys Delivered:</b> {delivered}\n"
                f"<b>{ce('fail')} Delivery Failed (no stock):</b> {failed}\n"
                f"<b>{ce('warning')} Payment Not Received:</b> {not_paid}",
                back_kb("admin_pending_payments"),
            )

        # ── Backup DB ──────────────────────────────────────────────────────────
        elif data == "adm_export_db":
            await query.answer("Preparing Database Export…")
            try:
                data_bytes = db.export_database()
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
            current = db.get_setting("maintenance_mode", "0")
            new_mode = "0" if current == "1" else "1"
            db.set_setting("maintenance_mode", new_mode)
            db.log_admin_action(user_id, "Toggled Maintenance", f"New Status: {new_mode}")
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
            prods = db.get_all_products()
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
            p = db.get_product(p_id)
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
            db.toggle_product(p_id)
            db.log_admin_action(user_id, "Toggled Product", f"PID: {p_id}")
            await query.answer("Status toggled!")
            p = db.get_product(p_id)
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
            db.delete_product(p_id)
            db.log_admin_action(user_id, "Deleted Product", f"PID: {p_id}")
            await query.answer("Product deleted successfully!")
            await safe_edit_text(
                update, context,
                f"<blockquote>{ce('success')} Product Deleted Successfully.</blockquote>",
                back_kb("admin_products"),
            )

        elif data.startswith("adm_plans_"):
            await query.answer()
            p_id = int(data.split("_")[2])
            plans = db.get_plans(p_id)
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
            plan = db.get_plan(pl_id)
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
            plan = db.get_plan(pl_id)
            prod_id = plan.get("product_id") if plan else 0
            db.delete_plan(pl_id)
            db.log_admin_action(user_id, "Deleted Plan", f"PlanID: {pl_id}")
            await query.answer("Plan deleted!")
            await safe_edit_text(
                update, context,
                f"<blockquote>{ce('success')} Plan Deleted.</blockquote>",
                back_kb(f"adm_plans_{prod_id}"),
            )

        # ── Keys ───────────────────────────────────────────────────────────────
        elif data == "admin_keys":
            await query.answer()
            prods = db.get_active_products()
            text = f"<blockquote><b>{ce('key')} MANAGE KEYS</b></blockquote>\nSelect a product to add bulk keys."
            buttons = [[InlineKeyboardButton(p["name"], callback_data=f"adm_kprod_{p['id']}", style="primary")] for p in prods]
            buttons.append([InlineKeyboardButton("Back", callback_data="admin_main", icon_custom_emoji_id=EMOJIS["back"][1], style="danger")])
            await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))

        elif data.startswith("adm_kprod_"):
            await query.answer()
            p_id = int(data.split("_")[2])
            plans = db.get_plans(p_id)
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
                qr_url = db.get_setting("qr_image")
                qr_status = "Set" if qr_url and qr_url != "None" else "Not Set"
                upi = db.get_setting("upi_id")
                support = db.get_setting("support_user")
                dl_link = db.get_setting("global_channel_link", "Not Set")
                insult_raw = db.get_setting("unauth_msg", "")
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
            tkts = db.get_open_tickets()
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
        await safe_edit_text(update, context, "<blockquote>Process Cancelled.</blockquote>", admin_menu_kb())
    else:
        await safe_edit_text(update, context, "<blockquote>Process Cancelled.</blockquote>", main_menu_kb())
    context.user_data.clear()
    return ConversationHandler.END


# ── NEW: Payment Service Login Flow ───────────────────────────────────────────
async def prompt_svc_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: ask for mobile number."""
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('session')} STEP 1/3 — Mobile Number</b></blockquote>\n\n"
        f"<i>Enter the mobile number registered with your UPI / FamPay account.</i>\n\n"
        f"<b>Examples:</b> <code>9876543210</code> or <code>+919876543210</code>",
        cancel_kb(),
    )
    return WAIT_FOR_SVC_MOBILE


async def receive_svc_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mobile = update.message.text.strip()
    if not re.match(r"^\+?\d{10,13}$", mobile):
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} Invalid mobile number. "
            f"Please enter a 10-digit number (e.g. <code>9876543210</code>).</blockquote>",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
        )
        return WAIT_FOR_SVC_MOBILE
    context.user_data["svc_mobile"] = mobile
    await update.message.reply_text(
        f"<blockquote><b>{ce('session')} STEP 2/3 — Gmail Address</b></blockquote>\n\n"
        f"<i>Enter the Gmail address that receives your UPI payment notifications.</i>\n\n"
        f"<b>Example:</b> <code>yourname@gmail.com</code>\n"
        f"<i>{ce('warning')} You'll need its <b>App Password</b> in the next step.</i>",
        reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
    )
    return WAIT_FOR_SVC_EMAIL


async def receive_svc_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} Invalid email address. Please try again.</blockquote>",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
        )
        return WAIT_FOR_SVC_EMAIL
    context.user_data["svc_email"] = email
    await update.message.reply_text(
        f"<blockquote><b>{ce('session')} STEP 3/3 — Gmail App Password</b></blockquote>\n\n"
        f"<i>Paste the <b>16-character Gmail App Password</b> for the email above.</i>\n\n"
        f"<b>Format:</b> <code>xxxx xxxx xxxx xxxx</code> (spaces are ignored)\n\n"
        f"<b>How to get one:</b>\n"
        f"<b>1.</b> Enable 2-Step Verification on your Google account.\n"
        f"<b>2.</b> Go to <i>Google Account → Security → App Passwords</i>.\n"
        f"<b>3.</b> Create a new password named <code>Hack Store</code> and paste it here.\n\n"
        f"<i>{ce('warning')} The password is stored encrypted and is used only to read "
        f"UPI payment notifications from your inbox.</i>",
        reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
    )
    return WAIT_FOR_SVC_OTP


async def receive_svc_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    app_password = re.sub(r"\s+", "", raw)
    if len(app_password) != 16 or not re.match(r"^[A-Za-z0-9]+$", app_password):
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>Invalid App Password!</b>\n\n"
            f"It must be exactly <b>16 characters</b> (letters/digits, spaces ignored).\n"
            f"Generate one at <i>Google Account → Security → App Passwords</i> "
            f"and paste it again.</blockquote>",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
        )
        return WAIT_FOR_SVC_OTP

    mobile = context.user_data.get("svc_mobile", "")
    email  = context.user_data.get("svc_email", "")
    svc_url = db.get_setting("payment_svc_url", "http://localhost:8000")
    admin_id = update.effective_user.id

    await update.message.reply_text(
        f"<blockquote>{ce('refresh')} Logging in to Gmail / payment service…</blockquote>",
        parse_mode=ParseMode.HTML,
    )

    # Try to delete the message containing the app password for safety
    try:
        await update.message.delete()
    except Exception:
        pass

    result = await svc_login(svc_url, admin_id, mobile, email, app_password)

    if result.get("status") == "ok":
        token = result.get("session_token", "")
        db.set_setting("payment_svc_token", token)
        db.set_setting("payment_svc_mobile", mobile)
        db.set_setting("payment_svc_email", email)
        db.log_admin_action(admin_id, "Payment Service Login", f"Mobile: {mobile}")

        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>Payment service login successful!</b></blockquote>\n\n"
            f"<i>Automated UPI payments are now active.</i>",
            reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
        )
    else:
        err = result.get("message", "Login failed. Check credentials and OTP.")
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>Login Failed:</b> {err}\n\n"
            f"Please try again from Admin Panel → UPI Session.</blockquote>",
            reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
        )

    context.user_data.clear()
    return ConversationHandler.END


# ── NEW: Edit microservice URL ─────────────────────────────────────────────────
async def prompt_set_svc_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('link')} Send the Microservice Base URL:</b></blockquote>\n\n"
        f"<i>Example: <code>http://localhost:8000</code> or <code>https://your-server.com</code></i>",
        cancel_kb(),
    )
    return WAIT_FOR_SVC_URL


async def receive_set_svc_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip().rstrip("/")
    db.set_setting("payment_svc_url", url)
    db.log_admin_action(update.effective_user.id, "Changed Microservice URL", url)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Microservice URL Updated!</b>\n\n<code>{url}</code></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── User conversations ─────────────────────────────────────────────────────────
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
    t_id = db.create_ticket(user_id, msg)
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
                    f"{ce_button('chat')} Reply", callback_data=f"adm_tkt_{t_id}"
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
    success, msg, amount = db.redeem_promo(user_id, code)
    if success:
        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>PROMO CODE REDEEMED!</b></blockquote>\n\n"
            f"₹{amount/100:.2f} has been added to your wallet.",
            reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"<blockquote>{ce('fail')} <b>{msg}</b></blockquote>",
            reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML,
        )
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
    u_id = db.reply_ticket(t_id, reply)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Reply sent and ticket closed.</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
        db.add_product(name, desc)
        db.log_admin_action(update.effective_user.id, "Added Product", f"Name: {name}")
        await safe_edit_text(
            update, context,
            f"<blockquote>{ce('success')} <b>Product '{name}' Added Successfully!</b></blockquote>",
            admin_menu_kb(),
        )
        context.user_data.clear()
        return ConversationHandler.END


async def receive_custom_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = f"<blockquote><b>{update.message.text.strip()}</b></blockquote>"
    name = context.user_data.get("new_prod_name")
    db.add_product(name, desc)
    db.log_admin_action(update.effective_user.id, "Added Product", f"Name: {name}")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Product '{name}' Added Successfully!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
        [InlineKeyboardButton(f"{ce_button('shield')} Safe / Main ID", callback_data="edit_preset_1")],
        [InlineKeyboardButton(f"{ce_button('fire')} Brutal / Root", callback_data="edit_preset_2")],
        [InlineKeyboardButton(f"{ce_button('apple')} iOS / eSign", callback_data="edit_preset_3")],
        [InlineKeyboardButton(f"{ce_button('name_icon')} 8 Level ID", callback_data="edit_preset_4")],
        [InlineKeyboardButton(f"{ce_button('mobile')} Drip Client (Non Root)", callback_data="edit_preset_5")],
        [InlineKeyboardButton(f"{ce_button('pencil')} Type Custom", callback_data="edit_custom")],
        [InlineKeyboardButton(f"{ce_button('fail')} Cancel", callback_data="cancel_conv")],
    ]
    await safe_edit_text(update, context, text, InlineKeyboardMarkup(buttons))
    return WAIT_FOR_EDIT_PROD_DESC


async def receive_edit_prod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prod_id = context.user_data.get("editing_prod_id")
    if not prod_id:
        if update.message:
            await update.message.reply_text("Error: No product in editing state.", reply_markup=admin_menu_kb())
        return ConversationHandler.END

    def _prod_buttons(pid):
        return [
            [InlineKeyboardButton(f"{ce_button('pencil')} Edit Description", callback_data=f"adm_edit_desc_{pid}")],
            [InlineKeyboardButton(f"{ce_button('loop')} Toggle Status", callback_data=f"adm_ptog_{pid}")],
            [InlineKeyboardButton(f"{ce_button('bag')} Manage Plans", callback_data=f"adm_plans_{pid}")],
            [InlineKeyboardButton(f"{ce_button('fail')} Delete Product", callback_data=f"adm_delprod_{pid}")],
            [InlineKeyboardButton(f"{ce_button('back')} Back", callback_data="admin_products")],
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
            db.update_product_description(prod_id, desc)
            db.log_admin_action(update.effective_user.id, "Edited Product Description", f"PID: {prod_id}")
            p = db.get_product(prod_id)
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
        db.update_product_description(prod_id, new_desc)
        db.log_admin_action(update.effective_user.id, "Edited Product Description", f"PID: {prod_id}")
        p = db.get_product(prod_id)
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
    db.set_setting("global_channel_link", update.message.text.strip())
    db.log_admin_action(update.effective_user.id, "Changed Download Link", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Download Channel Link Updated!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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


async def receive_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(float(update.message.text.strip()) * 100)
        prod_id = context.user_data["add_plan_pid"]
        db.add_plan(prod_id, context.user_data["add_plan_dur"], price)
        db.log_admin_action(update.effective_user.id, "Added Plan", f"PID: {prod_id}")
        plans = db.get_plans(prod_id)
        text = (
            f"<blockquote>{ce('success')} <b>Plan Added Successfully!</b></blockquote>\n\n"
            f"<blockquote><b>📋 MANAGE PLANS</b></blockquote>\n"
            f"<i>Click a plan to delete it. Add another below.</i>\n{get_line(12)}"
        )
        buttons = []
        for pl in plans:
            buttons.append([InlineKeyboardButton(
                f"{ce_button('fail')} {pl['duration']} — ₹{pl['price']/100:.2f}",
                callback_data=f"adm_plan_del_{pl['id']}",
            )])
        buttons.append([InlineKeyboardButton(f"{ce_button('plus')} Add New Plan", callback_data=f"adm_add_plan_{prod_id}")])
        buttons.append([InlineKeyboardButton(f"{ce_button('back')} Back to Product", callback_data=f"adm_prod_{prod_id}")])
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text("Invalid Price.", reply_markup=admin_menu_kb())
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
    count = db.add_keys(context.user_data["add_key_plan"], keys)
    db.log_admin_action(update.effective_user.id, "Added Keys", f"Count: {count}")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Successfully added {count} unique keys!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
        await update.message.reply_text("Invalid amount.", reply_markup=admin_menu_kb())
        return ConversationHandler.END


async def receive_promo_uses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uses = int(update.message.text.strip())
        code = context.user_data["promo_code"]
        reward = context.user_data["promo_reward"]
        if db.create_promo(code, reward, uses):
            await update.message.reply_text(
                f"<blockquote>{ce('success')} <b>Promo Code <code>{code}</code> Created!</b></blockquote>",
                reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(
                f"<blockquote>{ce('fail')} <b>Code already exists!</b></blockquote>",
                reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
            )
    except Exception:
        await update.message.reply_text("Invalid number.", reply_markup=admin_menu_kb())
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
    db.set_setting("faq_text", update.message.text)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>FAQ Updated Successfully!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
    db.set_setting("tos_text", update.message.text)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>TOS Updated Successfully!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
    db.set_setting("how_to_text", update.message.text)
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>How To Use Text Updated Successfully!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
    db.set_setting("how_to_video", update.message.text.strip())
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>How To Use Video Link Updated Successfully!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


@verification_required
async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_text(
        update, context,
        f"<blockquote><b>{ce('broadcast')} Send the message you want to broadcast:</b></blockquote>",
        cancel_kb(),
    )
    return WAIT_FOR_BROADCAST


async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user_ids = db.get_all_verified_user_ids()
    sent, failed = 0, 0
    await update.message.reply_text("Broadcast started… (This may take a moment).")
    for uid in user_ids:
        try:
            await context.bot.send_message(uid, msg, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    db.log_admin_action(update.effective_user.id, "Broadcast", f"Sent: {sent}, Failed: {failed}")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Broadcast Finished.</b>\nSent: {sent}\nFailed: {failed}</blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
    db.set_setting("upi_id", update.message.text.strip())
    db.log_admin_action(update.effective_user.id, "Changed UPI", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>UPI ID Updated!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
    db.set_setting("qr_image", file_id)
    db.log_admin_action(update.effective_user.id, "Changed QR Image", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>QR Image Updated!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
    db.set_setting("support_user", update.message.text.strip())
    db.log_admin_action(update.effective_user.id, "Changed Support User", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Support Username Updated!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
    db.set_setting("unauth_msg", update.message.text.strip())
    db.log_admin_action(update.effective_user.id, "Changed Insult Msg", "Setting Updated")
    await update.message.reply_text(
        f"<blockquote>{ce('success')} <b>Insult Message Updated!</b></blockquote>",
        reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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


async def receive_manual_bal_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        if not db.get_user(uid):
            await update.message.reply_text("User not found in DB.", reply_markup=admin_menu_kb())
            return ConversationHandler.END
        context.user_data["man_bal_uid"] = uid
        await update.message.reply_text(
            "<blockquote><b>Send amount in INR to add (e.g. 500):</b></blockquote>",
            reply_markup=cancel_kb(), parse_mode=ParseMode.HTML,
        )
        return WAIT_FOR_MANUAL_BAL_AMT
    except Exception:
        await update.message.reply_text("Invalid ID.", reply_markup=admin_menu_kb())
        return ConversationHandler.END


async def receive_manual_bal_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text.strip())
        paise = int(amt * 100)
        uid = context.user_data["man_bal_uid"]
        db.update_balance(uid, paise)
        db.log_admin_action(update.effective_user.id, "Manual Balance Add", f"UID: {uid}, Amt: {amt}")
        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>Added ₹{amt} to User {uid}.</b></blockquote>",
            reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
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
        await update.message.reply_text("Invalid amount.", reply_markup=admin_menu_kb())
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
        db.ban_user(uid, 1)
        db.log_admin_action(update.effective_user.id, "Banned User", f"UID: {uid}")
        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>User <code>{uid}</code> is now BANNED.</b></blockquote>",
            reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
        )
    except Exception:
        await update.message.reply_text("Invalid ID.", reply_markup=admin_menu_kb())
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
        db.ban_user(uid, 0)
        db.log_admin_action(update.effective_user.id, "Unbanned User", f"UID: {uid}")
        await update.message.reply_text(
            f"<blockquote>{ce('success')} <b>User <code>{uid}</code> is now UNBANNED.</b></blockquote>",
            reply_markup=admin_menu_kb(), parse_mode=ParseMode.HTML,
        )
    except Exception:
        await update.message.reply_text("Invalid ID.", reply_markup=admin_menu_kb())
    return ConversationHandler.END


# ==============================================================================
# 11. MAIN APPLICATION BUILDER & EXECUTION
# ==============================================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))

    # ── Admin conversation handler ─────────────────────────────────────────────
    admin_conv = ConversationHandler(
        entry_points=[
            # Payment service login
            CallbackQueryHandler(prompt_svc_login, pattern="^adm_svc_login_start$"),
            CallbackQueryHandler(prompt_set_svc_url, pattern="^adm_set_svc_url$"),
            # Broadcast & Settings
            CallbackQueryHandler(prompt_broadcast, pattern="^admin_broadcast$"),
            CallbackQueryHandler(prompt_set_upi, pattern="^adm_set_upi$"),
            CallbackQueryHandler(prompt_set_qr, pattern="^adm_set_qr$"),
            CallbackQueryHandler(prompt_set_sup, pattern="^adm_set_sup$"),
            CallbackQueryHandler(prompt_set_msg, pattern="^adm_set_msg$"),
            CallbackQueryHandler(prompt_set_dl_link, pattern="^adm_set_dl_link$"),
            # Users
            CallbackQueryHandler(prompt_ban, pattern="^adm_ban_usr$"),
            CallbackQueryHandler(prompt_unban, pattern="^adm_unban_usr$"),
            CallbackQueryHandler(prompt_manual_bal, pattern="^adm_add_bal$"),
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
            WAIT_FOR_SVC_MOBILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_svc_mobile)],
            WAIT_FOR_SVC_EMAIL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_svc_email)],
            WAIT_FOR_SVC_OTP:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_svc_otp)],
            WAIT_FOR_SVC_URL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_svc_url)],
            WAIT_FOR_BROADCAST:       [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast)],
            WAIT_FOR_SETTING_UPI:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_upi)],
            WAIT_FOR_SETTING_QR:      [MessageHandler(filters.PHOTO, receive_set_qr)],
            WAIT_FOR_SETTING_SUP:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_sup)],
            WAIT_FOR_SETTING_MSG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_msg)],
            WAIT_FOR_PROD_LINK:       [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_set_dl_link)],
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
        },
        fallbacks=[CallbackQueryHandler(cancel_conv_callback, pattern="^cancel_conv$")],
        per_message=False,
        allow_reentry=True,
    )
    app.add_handler(admin_conv)

    # ── User conversation handler ──────────────────────────────────────────────
    user_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_ticket, pattern="^user_ticket$"),
            CallbackQueryHandler(prompt_user_promo, pattern="^user_promo$"),
        ],
        states={
            WAIT_FOR_TICKET:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ticket)],
            WAIT_FOR_USER_PROMO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_promo)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv_callback, pattern="^cancel_conv$")],
        per_message=False,
        allow_reentry=True,
    )
    app.add_handler(user_conv)

    # ── Callback routers ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(
        handle_user_callbacks,
        pattern="^(user_|buy_|gen_qr_|verify_pay_|confirm_buy_)",
    ))
    app.add_handler(CallbackQueryHandler(
        handle_admin_callbacks,
        pattern="^(admin_|adm_)",
    ))

    logger.info("🔥 Bot is starting (MongoDB + Render + Self-hosted Payment Service) 🔥")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error("FATAL ERROR DURING STARTUP:")
        logger.error(traceback.format_exc())
        # Force flush logs
        import sys
        sys.stderr.flush()
        sys.stdout.flush()