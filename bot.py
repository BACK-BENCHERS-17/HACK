#!/usr/bin/env python3
import json
import asyncio
import os
import re
import sys
import threading
import time
import random
from datetime import datetime
from collections import Counter
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
import requests
from flask import Flask, jsonify
from pymongo import MongoClient
import dns.resolver
import certifi

# Fix for Termux/Android DNS (only if in Termux)
if os.path.exists('/data/data/com.termux'):
    try:
        dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
        dns.resolver.default_resolver.nameservers = ['8.8.8.8', '8.8.4.4']
    except Exception as e:
        print(f"⚠️ DNS fix failed: {e}")

# ==========================
# 📝 CONFIG
# ==========================
SESSION_FILE = "sessions.json"
API_ID = 33679425
API_HASH = "317cec181636ecdbb76c6d43a2d5935d"
BOT_TOKEN = "8181377432:AAGCMxdbGAo5zX1nxcG00pQO9Qcep5ywt4c"
MONGO_URL = "mongodb+srv://bb:bb@cluster0.upxxpnl.mongodb.net/?appName=Cluster0"

mongo_client = MongoClient(MONGO_URL, tlsCAFile=certifi.where(), tlsAllowInvalidCertificates=True)
db = mongo_client['wordle_solver']
sessions_col = db['sessions']
blacklist_col = db['blacklist']

def is_blacklisted(chat_id):
    return blacklist_col.find_one({"chat_id": chat_id}) is not None

def toggle_blacklist(chat_id):
    if is_blacklisted(chat_id):
        blacklist_col.delete_one({"chat_id": chat_id})
        return False
    else:
        blacklist_col.insert_one({"chat_id": chat_id})
        return True

MATH_MAP = {
    '𝐀': 'A', '𝐁': 'B', '𝐂': 'C', '𝐃': 'D', '𝐄': 'E', '𝐅': 'F', '𝐆': 'G', '𝐇': 'H', '𝐈': 'I', '𝐉': 'J', '𝐊': 'K', '𝐋': 'L', '𝐌': 'M', '𝐍': 'N', '𝐎': 'O', '𝐏': 'P', '𝗐': 'W', '𝐗': 'X', '𝐘': 'Y', '𝐙': 'Z',
    '𝐚': 'A', '𝐛': 'B', '𝐜': 'C', '𝐝': 'D', '𝐞': 'E', '𝐟': 'F', '𝐠': 'G', '𝐡': 'H', '𝐢': 'I', '𝐣': 'J', '𝐤': 'K', '𝐥': 'L', '𝐦': 'M', '𝐧': 'N', '𝐨': 'O', '𝐩': 'P', '𝐪': 'Q', '𝐫': 'R', '𝐬': 'S', '𝐭': 'T', '𝐮': 'U', '𝐯': 'V', '𝐰': 'W', 'ｘ': 'X', 'ｙ': 'Y', 'ｚ': 'Z',
    '𝗔': 'A', '𝗕': 'B', '𝗖': 'C', '𝗗': 'D', '𝗘': 'E', '𝗙': 'F', '𝗚': 'G', '𝗛': 'H', '𝗜': 'I', '𝗝': 'J', '𝗞': 'K', '𝗟': 'L', '𝗠': 'M', '𝗡': 'N', '𝗢': 'O', '𝗣': 'P', '𝗤': 'Q', '𝗥': 'R', '𝗦': 'S', '𝗧': 'T', '𝗨': 'U', '𝗩': 'V', '𝗪': 'W', '𝗫': 'X', '𝗬': 'Y', '𝗭': 'Z',
    '𝗮': 'A', '𝗯': 'B', '𝗰': 'C', '𝗱': 'D', '𝗲': 'E', '𝗳': 'F', '𝗴': 'G', '𝗵': 'H', '𝗶': 'I', '𝗷': 'J', 'ｋ': 'K', 'ｌ': 'L', 'ｍ': 'M', 'ｎ': 'N', '𝗼': 'O', '𝐩': 'P', '𝗾': 'Q', '𝗿': 'R', 'ｓ': 'S', 'ｔ': 'T', 'ｕ': 'U', 'ｖ': 'V', 'ｗ': 'W', 'ｘ': 'X', 'ｙ': 'Y', 'ｚ': 'Z',
}

def clean_text(text):
    return "".join(MATH_MAP.get(c, c) for c in text).upper()

def get_saved_sessions():
    try:
        saved = list(sessions_col.find())
        if saved: return {s['phone']: s for s in saved}
    except: pass
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_session(phone, session_string, mode="TURBO", enabled=True, owner_id=None):
    update_fields = {"string": session_string, "mode": mode, "enabled": enabled}
    if owner_id: update_fields["owner_id"] = owner_id
    
    try:
        sessions_col.update_one({"phone": phone}, {"$set": update_fields}, upsert=True)
    except: pass
    
    data = get_saved_sessions()
    data[phone] = {**data.get(phone, {}), "phone": phone, **update_fields}
    with open(SESSION_FILE, "w") as f: json.dump(data, f)

def delete_session(phone):
    try: sessions_col.delete_one({"phone": phone})
    except: pass
    data = get_saved_sessions()
    if phone in data: del data[phone]
    with open(SESSION_FILE, "w") as f: json.dump(data, f)

bot = TelegramClient('manager', API_ID, API_HASH)
clients = {}
BOT_ON = True
LOGIN_DATA = {}
game_sessions = {}

# ==========================
# 🧠 SOLVER LOGIC
# ==========================
def load_words(length=5):
    f = f"words_{length}letter.txt"
    if not os.path.exists(f): return []
    try:
        with open(f, 'r', encoding='utf-8') as file:
            return [l.strip().upper() for l in file if len(l.strip()) == length and l.strip().isalpha()]
    except: return []

ALL_WORDS = {4: load_words(4), 5: load_words(5), 6: load_words(6)}

class Solver:
    def __init__(self, length=5):
        self.length = length
        self.reset()
    def reset(self):
        self.fixed, self.forbidden, self.min_c, self.max_c = {}, {}, {}, {}
        self.known = set()
        self.candidates = ALL_WORDS.get(self.length, []).copy()
        self.count = 0
    def get_guess(self):
        if not self.candidates: return None
        if self.count == 0:
            starters = {4: ["DATE", "RARE"], 5: ["CRANE", "SLATE", "ADIEU"], 6: ["STREAK", "PLANET"]}
            for s in starters.get(self.length, ["CRANE"]):
                if s in self.candidates: return s
        if len(self.candidates) <= 2: return self.candidates[0]
        freq = Counter("".join(self.candidates))
        return max(self.candidates, key=lambda w: sum(freq[c] for c in set(w)))
    def process(self, guess, pattern):
        self.count += 1
        if pattern == "G" * self.length: return
        if guess in self.candidates: self.candidates.remove(guess)

        counts = Counter()
        for i, (p, c) in enumerate(zip(pattern, guess)):
            if p in ("G", "Y"):
                counts[c] += 1

        for c, count in counts.items():
            self.min_c[c] = max(self.min_c.get(c, 0), count)
            self.known.add(c)

        for i, (p, c) in enumerate(zip(pattern, guess)):
            if p == "G":
                self.fixed[i] = c
            elif p == "Y":
                if i not in self.forbidden: self.forbidden[i] = set()
                self.forbidden[i].add(c)
            else:
                if i not in self.forbidden: self.forbidden[i] = set()
                self.forbidden[i].add(c)
                if c in counts:
                    self.max_c[c] = counts[c]
                else:
                    self.max_c[c] = 0
        self.candidates = [w for w in self.candidates if self.is_valid(w)]

    def is_valid(self, w):
        for i, c in self.fixed.items():
            if w[i] != c: return False
        for i, f in self.forbidden.items():
            if w[i] in f: return False
        for c, m in self.max_c.items():
            if w.count(c) > m: return False
        for c, m in self.min_c.items():
            if w.count(c) < m: return False
        return True

class Game:
    def __init__(self, chat_id, phone, length=5, target=1, command="/new"):
        self.chat_id, self.phone, self.length = chat_id, phone, length
        self.solver = Solver(length)
        self.active, self.target, self.done = True, target, 0
        self.command = command
        self.last_msg, self.last_guess = None, None
        self.last_action = 0
        self.processed = set()
        self.lock = asyncio.Lock()
        self.is_solving = False

# ==========================
# 📱 LOGIN & UI
# ==========================
def get_keypad(code=""):
    btns = []
    for i in range(0, 9, 3):
        btns.append([Button.inline(str(j+1), data=f"otp_{j+1}") for j in range(i, i+3)])
    btns.append([Button.inline("0", data="otp_0"), Button.inline("⬅️", data="otp_back")])
    btns.append([Button.inline("✅ Submit", data="otp_done"), Button.inline("❌ Cancel", data="otp_stop")])
    return btns

def get_hub_msg():
    return f"""WORDLE SOLVER — ELITE HUB
> _Next-gen AI automation for Wordle dominance._

◈ YOUR STATUS : ◉ RUNNING
◈ CONNECTED   : {len(clients)} bot(s)
◈ MODE        : » ADAPTIVE

FEATURES:
» Auto-joins ongoing Wordle games
» Loop: /new5 100 plays 100 rounds
» Mid-game: detects live emoji boards
» Prefix: /ping · .ping · ping
▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄"""

def get_hub_buttons():
    return [
        [Button.inline("[ ACCOUNTS ]", data="pg_accounts"), Button.inline("[ STATS ]", data="pg_stats")],
        [Button.inline("[ HELP ]", data="pg_help")]
    ]

@bot.on(events.NewMessage(pattern=r'(?i)^/start$'))
async def on_start(e):
    await e.reply(get_hub_msg(), buttons=get_hub_buttons())

@bot.on(events.CallbackQuery(data="pg_accounts"))
async def on_pg_accounts(e):
    all_sessions = get_saved_sessions()
    my_sessions = {p: s for p, s in all_sessions.items() if s.get('owner_id') == e.sender_id}
    
    if not my_sessions:
        return await e.edit("No active sessions owned by you.", buttons=[[Button.inline("➕ Add Account", data="login_init")], [Button.inline("⬅️ Back", data="start_back")]])

    msg = f"◈◈◈ ACTIVE ACCOUNTS ◈◈◈\n\nSelect an account to manage settings.\n\n"
    btns = []
    for i, phone in enumerate(my_sessions.keys(), 1):
        msg += f"{i}. +{phone}\n"
        btns.append([Button.inline(f"» +{phone}", data=f"acc_{phone}")])
    
    btns.append([Button.inline("➕ Add Account", data="login_init")])
    btns.append([Button.inline("⬅️ Back", data="start_back")])
    await e.edit(msg, buttons=btns)

@bot.on(events.CallbackQuery(data=re.compile(rb'acc_(\d+)')))
async def on_pg_acc_details(e):
    phone = e.data.decode().split('_')[1]
    data = get_saved_sessions().get(phone, {})
    
    if data.get('owner_id') != e.sender_id:
        return await e.answer("❌ You are not the owner of this account!", alert=True)
    
    mode = data.get("mode", "TURBO")
    enabled = data.get("enabled", True)
    
    msg = f"""◈ SETTINGS: +{phone} ◈

Manage the behavior of this specific userbot.

» STATUS: ONLINE 🟢
» BOT: {'ENABLED ✅' if enabled else 'DISABLED ❌'}
» MODE: {mode}
» SPEED: {'Fast' if mode == 'TURBO' else 'Safe'}"""
    
    await e.edit(msg, buttons=[
        [Button.inline(f"{'🔴 Disable' if enabled else '🟢 Enable'} Bot", data=f"toggle_{phone}")],
        [Button.inline(f"🔄 Switch to {'STRENGTH' if mode == 'TURBO' else 'TURBO'}", data=f"mode_{phone}")],
        [Button.inline("🔒 Blacklist", data=f"bl_{phone}"), Button.inline("🚪 Logout", data=f"out_{phone}")],
        [Button.inline("⬅️ Back to Accounts", data="pg_accounts")]
    ])

@bot.on(events.CallbackQuery(data=re.compile(rb'toggle_(\d+)')))
async def on_bot_toggle_cb(e):
    phone = e.data.decode().split('_')[1]
    data = get_saved_sessions().get(phone, {})
    if data.get('owner_id') != e.sender_id: return
    new_status = not data.get("enabled", True)
    save_session(phone, data['string'], data.get("mode", "TURBO"), new_status, owner_id=e.sender_id)
    await on_pg_acc_details(e)

@bot.on(events.CallbackQuery(data=re.compile(rb'mode_(\d+)')))
async def on_mode_toggle(e):
    phone = e.data.decode().split('_')[1]
    data = get_saved_sessions().get(phone, {})
    if data.get('owner_id') != e.sender_id: return
    new_mode = "STRENGTH" if data.get("mode") == "TURBO" else "TURBO"
    save_session(phone, data['string'], new_mode, data.get("enabled", True), owner_id=e.sender_id)
    await on_pg_acc_details(e)

@bot.on(events.CallbackQuery(data="pg_stats"))
async def on_pg_stats(e):
    msg = f"""◈◈◈ STATISTICS ◈◈◈

PERFORMANCE DATA
Real-time status of your bots and infrastructure.

» YOUR BOTS: {len(clients)}
» TOTAL NETWORK: {len(clients)}
» GLOBAL SOLVER: ONLINE 🟢"""
    await e.edit(msg, buttons=[[Button.inline("⬅️ Back", data="start_back")]])

@bot.on(events.CallbackQuery(data="pg_help"))
async def on_pg_help(e):
    msg = f"""📖 USERBOT COMMANDS & HELP

"Control your bots directly in any chat."

» /ping
Check latency and mode.

» /new [n] | /new4 [n] | /new6 [n]
Start a 5, 4, or 6-letter game with optional game number [n].

💡 PRO TIP:
Automatic detection for mid-game boards is enabled."""
    await e.edit(msg, buttons=[[Button.inline("⬅️ Back", data="start_back")]])

@bot.on(events.CallbackQuery(data="start_back"))
async def on_back_start(e):
    await e.edit(get_hub_msg(), buttons=get_hub_buttons())

@bot.on(events.CallbackQuery(data=re.compile(rb'bl_(\d+)')))
async def on_bl_init(e):
    phone = e.data.decode().split('_')[1]
    data = get_saved_sessions().get(phone, {})
    if data.get('owner_id') != e.sender_id: return
    
    LOGIN_DATA[e.chat_id] = {'step': 'blacklist', 'phone': phone}
    msg = f"""◈ BLACKLIST: +{phone} ◈

Toggle group status or view current blacklist. 
» INFO: Send a Group ID to block/unblock it."""
    
    await e.edit(msg, buttons=[
        [Button.inline("📋 View Blacklist", data=f"blview_{phone}")],
        [Button.inline("⬅️ Back", data=f"acc_{phone}")]
    ])

@bot.on(events.CallbackQuery(data=re.compile(rb'blview_(\d+)')))
async def on_bl_view(e):
    phone = e.data.decode().split('_')[1]
    data = get_saved_sessions().get(phone, {})
    if data.get('owner_id') != e.sender_id: return
    
    bl_list = list(blacklist_col.find())
    if not bl_list:
        return await e.answer("Blacklist is empty!", alert=True)
    
    msg = "◈◈◈ BLACKLISTED GROUPS ◈◈◈\n\nClick a Group ID to UNBLOCK it.\n\n"
    btns = []
    for entry in bl_list:
        gid = entry.get('chat_id')
        btns.append([Button.inline(f"❌ {gid}", data=f"unbl_{gid}_{phone}")])
    
    btns.append([Button.inline("⬅️ Back", data=f"bl_{phone}")])
    await e.edit(msg, buttons=btns)

@bot.on(events.CallbackQuery(data=re.compile(rb'unbl_(-?\d+)_(\d+)')))
async def on_unbl_action(e):
    m = re.match(rb'unbl_(-?\d+)_(\d+)', e.data)
    gid = int(m.group(1))
    phone = m.group(2).decode()
    data = get_saved_sessions().get(phone, {})
    if data.get('owner_id') != e.sender_id: return
    
    blacklist_col.delete_one({"chat_id": gid})
    await e.answer(f"✅ Unblocked {gid}")
    await on_bl_view(e)

@bot.on(events.CallbackQuery(data=re.compile(rb'out_(\d+)')))
async def on_logout(e):
    phone = e.data.decode().split('_')[1]
    data = get_saved_sessions().get(phone, {})
    if data.get('owner_id') != e.sender_id: return
    
    if phone in clients:
        await clients[phone].disconnect()
        del clients[phone]
    delete_session(phone)
    await e.edit(f"👋 **Logged out +{phone} successfully.**", buttons=[[Button.inline("⬅️ Back to Accounts", data="pg_accounts")]])

@bot.on(events.CallbackQuery(data="login_init"))
async def on_login_init(e):
    LOGIN_DATA[e.chat_id] = {'step': 'phone'}
    await e.edit("📱 Send your phone number (e.g., `+91...`)", buttons=[Button.inline("❌ Cancel", data="otp_stop")])

@bot.on(events.CallbackQuery(data=re.compile(b'otp_')))
async def on_otp_btn(e):
    cid = e.chat_id
    if cid not in LOGIN_DATA or LOGIN_DATA[cid]['step'] != 'code': return
    act = e.data.decode().split('_')[1]
    data = LOGIN_DATA[cid]
    code = data.get('code', "")
    if act == 'stop':
        if 'temp' in data: await data['temp'].disconnect()
        del LOGIN_DATA[cid]
        await e.edit("❌ Login Cancelled.", buttons=None)
    elif act == 'back':
        data['code'] = code[:-1]
        await e.edit(f"📥 OTP: `{data['code'] or '(empty)'}`", buttons=get_keypad())
    elif act == 'done':
        if not code: return await e.answer("Enter code!")
        await e.answer("Verifying...")
        await do_sign_in(e, cid, code)
    else:
        if len(code) < 6:
            data['code'] = code + act
            await e.edit(f"📥 OTP: `{data['code']}`", buttons=get_keypad())

async def do_sign_in(e, cid, code):
    data = LOGIN_DATA[cid]
    try:
        if data['step'] == 'code':
            await data['temp'].sign_in(data['phone'], code, phone_code_hash=data['hash'])
        else:
            await data['temp'].sign_in(password=code)

        me = await data['temp'].get_me()
        ss = data['temp'].session.save()
        save_session(me.phone, ss, owner_id=cid)

        new_client = TelegramClient(StringSession(ss), API_ID, API_HASH)
        reg_handlers(new_client, me.phone)
        await new_client.start()
        clients[str(me.phone)] = new_client

        msg = f"✅ **LOGGED IN:** `{me.first_name}` (+{me.phone})"
        if isinstance(e, events.CallbackQuery.Event): await e.edit(msg, buttons=None)
        else: await e.reply(msg)
        del LOGIN_DATA[cid]
    except Exception as ex:
        if "Two-step" in str(ex):
            data['step'] = 'pass'
            msg = "🔐 2FA Detected. Please send your Cloud Password."
            if isinstance(e, events.CallbackQuery.Event): await e.edit(msg, buttons=None)
            else: await e.reply(msg)
        else:
            msg = f"❌ Error: {ex}"
            if isinstance(e, events.CallbackQuery.Event): await e.answer(msg, alert=True)
            else: await e.reply(msg)

@bot.on(events.NewMessage)
async def on_msg(e):
    cid = e.chat_id
    if cid not in LOGIN_DATA: return
    data = LOGIN_DATA[cid]
    step, text = data['step'], e.raw_text.strip()
    if text.lower() in ['/cancel', '/stop']:
        if 'temp' in data: await data['temp'].disconnect()
        del LOGIN_DATA[cid]
        await e.reply("🛑 Process stopped.")
        return
    if step == 'blacklist':
        try:
            target_id = int(text)
            status = toggle_blacklist(target_id)
            msg = f"✅ Group `{target_id}` is now **{'BLACKLISTED' if status else 'REMOVED from Blacklist'}**."
            await e.reply(msg)
            del LOGIN_DATA[cid]
        except ValueError: await e.reply("❌ Please send a valid numeric Group ID.")
        return
    if step == 'phone' and text.startswith('+'):
        msg = await e.reply("⏳ Sending OTP...")
        tmp = TelegramClient(StringSession(), API_ID, API_HASH)
        await tmp.connect()
        try:
            res = await tmp.send_code_request(text)
            LOGIN_DATA[cid] = {'step': 'code', 'phone': text, 'hash': res.phone_code_hash, 'temp': tmp, 'code': ""}
            await e.reply(f"📥 OTP: `(empty)`", buttons=get_keypad())
        except Exception as ex: await e.reply(f"❌ Error: {ex}")
    elif step == 'pass': await do_sign_in(e, cid, text)
    elif step == 'code' and text.isdigit(): await do_sign_in(e, cid, text)

# ==========================
# 🎮 USERBOT HANDLERS
# ==========================
def reg_handlers(c, phone):
    c.add_event_handler(lambda e: h_ping(e, phone), events.NewMessage(pattern=r'(?i)^[./]?ping$'))
    c.add_event_handler(lambda e: h_new(e, phone), events.NewMessage(pattern=r'(?i)^[./]?new(4|6)?(?:\s+(\d+))?'))
    c.add_event_handler(lambda e: h_stop(e, phone), events.NewMessage(pattern=r'(?i)^[./]?stop$'))
    c.add_event_handler(lambda e: h_game(e, phone), events.NewMessage)

async def h_ping(e, phone):
    data = get_saved_sessions().get(str(phone), {})
    if not data.get("enabled", True): return
    start = time.time()
    msg = await e.reply("🏓 **PONG**")
    end = time.time()
    await msg.edit(f"🏓 **PONG**\n» **LATENCY:** `{(end - start) * 1000:.0f}ms`")

async def h_new(e, phone):
    data = get_saved_sessions().get(str(phone), {})
    if not data.get("enabled", True): return
    if is_blacklisted(e.chat_id): return
    m = re.match(r'(?i)^[./]?new(4|6)?(?:\s+(\d+))?', e.raw_text)
    if not m: return
    length_map = {"4": 4, "6": 6, None: 5}
    l = length_map.get(m.group(1))
    n_str = m.group(2)
    
    if not n_str and e.chat_id in game_sessions:
        # This is a continuation command or standard join
        s = game_sessions[e.chat_id]
        if s.active and s.target > 1 and s.done < s.target and s.length == l:
            async with s.lock:
                s.solver.reset()
                s.processed.clear()
                s.last_msg = None
                s.last_guess = None
                # NO GUESS SENT HERE. Wait for "Game started" to avoid crane-crane.
                return
    
    # New session initialization
    n = int(n_str or 1)
    base_cmd = f"/new{m.group(1) or ''}"
    game_sessions[e.chat_id] = Game(e.chat_id, phone, l, target=n, command=base_cmd)
    # NO GUESS SENT HERE. Wait for "Game started".

async def h_stop(e, phone):
    me = await e.client.get_me()
    if e.sender_id != me.id: return
    if e.chat_id in game_sessions: 
        game_sessions[e.chat_id].active = False
        await e.reply("🛑 Stopped.")

async def h_game(e, phone):
    data = get_saved_sessions().get(str(phone), {})
    if not data.get("enabled", True): return
    if e.chat_id not in game_sessions: return
    if is_blacklisted(e.chat_id): return
    s = game_sessions[e.chat_id]
    if not s.active: return
    
    t = e.raw_text.lower()
    new_info = False
    opponent_played = False
    is_game_over = False

    async with s.lock:
        if not s.active: return
        
        is_game_over = "congrats" in t or "correct" in t or "🟩" * s.length in e.raw_text
        is_game_start = "game started" in t or "guess the" in t
        has_emojis = any(c in e.raw_text for c in "🟩🟨🟥⬛⬜")

        if is_game_start:
            s.solver.reset()
            s.processed.clear()
            s.last_msg = None
            s.last_guess = None
            g = s.solver.get_guess()
            if g:
                s.last_guess = g
                s.last_action = time.time()
                await asyncio.sleep(2)
                await e.client.send_message(e.chat_id, g.lower())
            return

        if "already guessed" in t or "someone has already guessed" in t:
            if time.time() - s.last_action < 1.5: return
            if s.last_guess and s.last_guess in s.solver.candidates:
                s.solver.candidates.remove(s.last_guess)
            g = s.solver.get_guess()
            if g and g != s.last_guess:
                s.last_guess = g
                s.last_action = time.time()
                await asyncio.sleep(2)
                if s.active:
                    await e.client.send_message(e.chat_id, g.lower())
            return

        if not has_emojis and not is_game_over: return
        if e.raw_text == s.last_msg: return
        s.last_msg = e.raw_text

        lines = e.raw_text.splitlines()
        for line in lines:
            p = "".join('G' if c == '🟩' else 'Y' if c == '🟨' else 'B' for c in line if c in "🟩🟨🟥⬛⬜")
            if len(p) == s.length:
                word = "".join(c for c in clean_text(line) if c.isalpha())
                if len(word) > s.length: word = word[-s.length:]
                if len(word) == s.length:
                    key = f"{word}-{p}"
                    if key not in s.processed:
                        s.solver.process(word, p)
                        s.processed.add(key)
                        new_info = True
                        me = await e.client.get_me()
                        if e.sender_id != me.id: opponent_played = True

        if is_game_over:
            s.active = False # Immediately stop this round
            s.done += 1
            s.last_action = time.time()
            if s.done < s.target:
                await asyncio.sleep(3)
                # Restart for next round
                s.active = True
                await e.client.send_message(e.chat_id, s.command)
            else:
                await e.reply(f"🏆 **SOLVED {s.done} GAMES!**")
            return

    # Solving logic outside the primary lock to prevent event starvation
    if new_info and s.active and not is_game_over and not s.is_solving:
        if time.time() - s.last_action < 1.5: return
        s.is_solving = True
        try:
            delay = 2 if data.get("mode") == "TURBO" else 4
            if opponent_played: delay += 3
            await asyncio.sleep(delay)
            
            async with s.lock:
                if not s.active: return
                g = s.solver.get_guess()
                if g and g != s.last_guess:
                    s.last_guess = g
                    s.last_action = time.time()
                    await e.client.send_message(e.chat_id, g.lower())
        finally:
            s.is_solving = False

app = Flask(__name__)
@app.route('/')
def home(): return "Online"

async def main():
    port = int(os.environ.get("PORT", 5000))
    print(f"📡 Starting Flask server on port {port}...")
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False), daemon=True).start()

    print("⏳ Starting bot...")
    try:
        await bot.start(bot_token=BOT_TOKEN)
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        return

    saved_sessions = get_saved_sessions()
    for phone, s_data in saved_sessions.items():
        try:
            new_client = TelegramClient(StringSession(s_data['string']), API_ID, API_HASH)
            reg_handlers(new_client, phone)
            await new_client.start()
            clients[str(phone)] = new_client
            print(f"🚀 Loaded +{phone}")
        except Exception as e:
            print(f"⚠️ Failed to load +{phone}: {e}")

    print("✨ Bot is running."); await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Stopped by user.")
