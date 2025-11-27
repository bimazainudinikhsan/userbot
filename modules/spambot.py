# bmcodexbot/modules/spambot.py
import asyncio
import random
import json
import os
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from telethon import events, Button, utils, types 
from telethon.errors import (
    ChatWriteForbiddenError, UserBannedInChannelError, 
    FloodWaitError, ChatAdminRequiredError, RPCError, MessageNotModifiedError
)
from config import bot

# File penyimpanan
SPAM_SETTINGS_FILE = "user_spambot_settings.json"
SPAM_SESSION_FILE = "spam_active_sessions.json" 

# State Memory (Runtime)
SPAM_STATE = {}
ACTIVE_SPAM_TASKS = {} 

# Kata-kata berisiko (Filter Rules)
RISKY_WORDS = [
    # 1. Dilarang PROMOSI / JUALAN
    "jual", "beli", "promo", "diskon", "murah", "cek bio", "open", "order", "ready", "minat", "pm", "dm", "testimoni", "pulsa", "convert", "cv", "jasa", "joki", "topup", "app premium", "netflix", "spotify", "dana kaget", "chip", "koin",
    
    # 2. Dilarang RUSUH / SPAM / 18+ / JUDOL
    "rusuh", "spam", "bokep", "montok", "bo", "vcs", "crot", "colmek", "sange", "horny", "desah", "wikwik", "slot", "gacor", "maxwin", "depo", "wd", "judol", "togel", "zeus", "pragmatic",
    
    # 3. Dilarang SHARE LINK
    "link", "join", "grup", "channel", "t.me", "http", "https", "bit.ly", ".com", ".id", ".net", ".org", "wa.me", "08", "biolink", "linktree", "undang", "tautan",
    
    # 4. Dilarang SARA / RASIS / MENGHINA / TOXIC
    "anjing", "babi", "tolol", "goblok", "bangsat", "kontol", "memek", "ngentot", "bodoh", "idiot", "autis", "hitam", "cina", "pribumi", "kafir", "lonte", "jalang", "kampang", "pantek", "yatim", "bego", "setan", "iblis", "monyet", "cacat", "bencong"
]

# --- DATABASE KATA AI (PREMIUM MODE - PREFIX) ---
AI_PREFIXES = [
    "Cek profil ya kak", "Yang mau rate sini yuk", "Bantu saya kak", 
    "Ditunggu ya chatnya", "Salam kenal semuanya", "Ada yang gabut gak", 
    "Nyari temen ngobrol nih", "Mampir profil bentar kak", "Butuh temen curhat", 
    "Yang on boleh sapa dong", "Cari temen baru nih", "Boleh kenalan gak", 
    "Izin share ya min", "Info dong kak", "Kak mau tanya sebentar",
    "Hai hai semua", "Halo kawan", "Permisi numpang lewat", "Misi gan", "Punteun"
]

# ==========================================
# 1. DATABASE HELPERS
# ==========================================

def load_json(filename):
    if not os.path.exists(filename): return {}
    try:
        with open(filename, 'r') as f: return json.load(f)
    except: return {}

def save_json(filename, data):
    with open(filename, 'w') as f: json.dump(data, f, indent=4)

def get_spam_settings(user_id):
    if not os.path.exists(SPAM_SETTINGS_FILE):
        save_json(SPAM_SETTINGS_FILE, {})
    data = load_json(SPAM_SETTINGS_FILE)
    str_uid = str(user_id)
    if str_uid not in data:
        data[str_uid] = {
            "messages": ["Halo", "Tes Spam", "Pesan Random"],
            "min_delay": 6.0, "max_delay": 10.0  
        }
        save_json(SPAM_SETTINGS_FILE, data)
    return data[str_uid]

def save_user_spam_setting(user_id, key, value):
    data = load_json(SPAM_SETTINGS_FILE)
    str_uid = str(user_id)
    if str_uid not in data: get_spam_settings(user_id); data = load_json(SPAM_SETTINGS_FILE)
    data[str_uid][key] = value
    save_json(SPAM_SETTINGS_FILE, data)

def load_active_sessions():
    return load_json(SPAM_SESSION_FILE)

def save_active_session(user_id, session_data):
    data = load_active_sessions()
    if session_data is None:
        if str(user_id) in data: del data[str(user_id)]
    else:
        data[str(user_id)] = session_data
    save_json(SPAM_SESSION_FILE, data)

# ==========================================
# 2. ENGINE UTAMA (RUNNER SPAM BIASA)
# ==========================================

async def run_spam_batch(client, user_id, target_str, count, current_idx=0, status_msg_id=None, chat_id=None, is_premium=False, last_reply_id=None):
    # Logic spam biasa (kode disederhanakan agar fokus ke fitur baru)
    # Implementasi ini mengikuti struktur yang sudah ada sebelumnya
    conf = get_spam_settings(user_id)
    msgs = conf.get("messages", [])
    min_d = conf.get("min_delay", 6.0)
    max_d = conf.get("max_delay", 10.0)
    
    try: entity = await client.get_entity(target_str)
    except: entity = target_str
    display_target = f"`{target_str}`"
    
    status_msg = None
    if status_msg_id:
        try:
            m = await bot.get_messages(user_id, ids=[status_msg_id])
            if m: status_msg = m[0]
        except: pass
    
    if not status_msg:
        try: status_msg = await bot.send_message(user_id, f"🔄 **Spam Berjalan...**\nTarget: {display_target}")
        except: return

    cancel_btn = [[Button.inline("🛑 Hentikan Spam", b"spam_cancel_session")]]
    my_id = (await client.get_me()).id
    success, failed = 0, 0

    for i in range(current_idx, count):
        session_data = {"target": target_str, "count": count, "current_idx": i, "status_msg_id": status_msg.id, "chat_id": user_id, "mode": "spam"}
        save_active_session(user_id, session_data)

        while not client.is_connected():
            await asyncio.sleep(5)
        
        base = random.choice(msgs)
        final_msg = f"{random.choice(AI_PREFIXES)} {base}" if is_premium else base
        
        # Logic Reply Spam Biasa
        reply_id = None
        try:
            hist = await client.get_messages(entity, limit=15)
            targets = [m.id for m in hist if m.sender_id != my_id and not m.action]
            if targets: reply_id = random.choice(targets)
        except: pass

        delay = random.uniform(min_d, max_d)
        
        try:
            await status_msg.edit(f"🚀 **Spam Berjalan**\nTarget: {display_target}\nProgress: `{i+1}/{count}`\nSuccess: {success}", buttons=cancel_btn)
        except: pass

        try:
            async with client.action(entity, 'typing'):
                await asyncio.sleep(min(len(final_msg)*0.1, 4.0))
                await client.send_message(entity, final_msg, reply_to=reply_id)
            success += 1
        except FloodWaitError as e: await asyncio.sleep(e.seconds + 5)
        except: failed += 1

        try: await asyncio.sleep(delay)
        except asyncio.CancelledError: break

    save_active_session(user_id, None)
    if user_id in ACTIVE_SPAM_TASKS: del ACTIVE_SPAM_TASKS[user_id]
    try: await status_msg.edit("✅ Selesai.", buttons=None)
    except: pass

# ==========================================
# 3. SPAM AI (HYBRID SCRAPER + REPLY + MANUAL)
# ==========================================

async def run_spamai_task(client, user_id, target_str, min_delay, max_delay, count, manual_words, status_msg):
    try:
        entity = await client.get_entity(target_str)
        display_target = f"`{target_str}`"
    except Exception as e:
        await status_msg.edit(f"❌ **Gagal:** Target tidak valid.\nError: {e}")
        if user_id in ACTIVE_SPAM_TASKS: del ACTIVE_SPAM_TASKS[user_id]
        return

    # Simpan Sesi
    session_data = {
        "target": target_str, "count": count, "current_idx": 0,
        "status_msg_id": status_msg.id, "chat_id": user_id, "mode": "spamai"
    }
    save_active_session(user_id, session_data)

    cancel_btn = [[Button.inline("🛑 Hentikan Spam AI", b"spam_cancel_session")]]
    
    # Ambil ID Sendiri untuk filter reply
    try:
        me = await client.get_me()
        my_id = me.id
    except: my_id = 0

    # --- 1. FASE SCRAPING (DATA KATA) ---
    word_buffer = deque(maxlen=500) 
    generated_sentences = []
    
    try:
        await status_msg.edit(
            f"🧠 **AI LEARNING...**\n"
            f"🎯 Target: {display_target}\n"
            f"⏳ Membaca history grup...",
            buttons=cancel_btn
        )
        
        async for message in client.iter_messages(entity, limit=100):
            if message.text and not message.sender.bot and message.sender_id != my_id:
                clean = re.sub(r'@\w+', '', message.text)
                clean = re.sub(r'http\S+', '', clean)
                clean = re.sub(r'\s+', ' ', clean).strip()
                if not clean: continue
                words = clean.split()
                if len(words) > 1: word_buffer.extend(words)
        
        # Generate Database Kalimat
        pool = list(word_buffer)
        if len(pool) >= 5:
            for _ in range(50):
                length = random.randint(2, 5)
                if len(pool) <= length: continue
                start = random.randint(0, len(pool) - length)
                chunk = pool[start : start + length]
                sentence = " ".join(chunk)
                if any(bad in sentence.lower() for bad in RISKY_WORDS): continue
                generated_sentences.append(sentence)
    except: pass

    # --- 2. FASE EKSEKUSI SPAM ---
    success = 0
    failed = 0
    
    for i in range(count):
        # Cek Koneksi
        while not client.is_connected():
            try: await status_msg.edit("⚠️ **Koneksi Terputus...**", buttons=cancel_btn)
            except: pass
            await asyncio.sleep(5)

        # Rangkai Pesan
        ai_part = random.choice(generated_sentences) if generated_sentences else ""
        style = random.randint(1, 3)
        if style == 1 and ai_part: final_msg = f"{manual_words} {ai_part}"
        elif style == 2 and ai_part: final_msg = f"{ai_part} {manual_words}"
        else: final_msg = manual_words

        # Hitung Delay
        this_delay = random.uniform(min_delay, max_delay)
        
        # --- LOGIKA REPLY PINTAR ---
        reply_to_id = None
        try:
            # Ambil 20 pesan terakhir di grup
            recent_msgs = await client.get_messages(entity, limit=20)
            
            # Filter: Bukan pesan sendiri, bukan pesan sistem (join/leave), harus ada ID
            valid_targets = [
                m.id for m in recent_msgs 
                if m.sender_id != my_id and not m.action and m.id
            ]
            
            # Jika ada pesan orang lain, pilih satu acak untuk di-reply
            # Jika list kosong (grup sepi / isinya cuma chat kita), reply_to_id tetap None
            if valid_targets:
                reply_to_id = random.choice(valid_targets)
        except: 
            pass # Lanjut tanpa reply jika gagal fetch

        # Update UI
        try:
            percent = int((i + 1) / count * 10)
            bar = "▰" * percent + "▱" * (10 - percent)
            display_msg = (final_msg[:40] + '...') if len(final_msg) > 40 else final_msg
            reply_status = "ON" if reply_to_id else "OFF (Sepi/Sendiri)"
            
            await status_msg.edit(
                f"🚀 **SPAM AI BERJALAN**\n"
                f"🎯 Target: {display_target}\n"
                f"📊 Progress: `{i+1}/{count}` [{bar}]\n"
                f"⏱️ Delay: `{this_delay:.1f}s` | ↩️ Reply: `{reply_status}`\n\n"
                f"✅ Sukses: `{success}`\n"
                f"❌ Gagal: `{failed}`\n"
                f"💬 **Last Sent:**\n`{display_msg}`",
                buttons=cancel_btn
            )
        except: pass

        # Kirim Pesan
        try:
            # Fitur Sedang Mengetik...
            async with client.action(entity, 'typing'):
                # Durasi ngetik disesuaikan panjang pesan (biar real)
                await asyncio.sleep(min(len(final_msg) * 0.1, 4.0)) 
                
                # Kirim dengan Reply (jika ada target)
                await client.send_message(entity, final_msg, reply_to=reply_to_id)
            success += 1
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 3)
        except Exception:
            failed += 1

        # Delay antar pesan
        try:
            await asyncio.sleep(this_delay)
        except asyncio.CancelledError:
            break

    # Selesai
    try:
        await status_msg.edit(
            f"✅ **SPAM AI SELESAI**\n"
            f"🎯 Target: {display_target}\n"
            f"📨 Terkirim: `{success}`\n"
            f"❌ Gagal: `{failed}`",
            buttons=[[Button.inline("🗑️ Tutup", b"spam_done")]]
        )
    except: pass
    
    save_active_session(user_id, None)
    if user_id in ACTIVE_SPAM_TASKS: del ACTIVE_SPAM_TASKS[user_id]

# ==========================================
# 4. UI & HANDLERS
# ==========================================

async def show_spambot_menu(event, user_id):
    text = "🤖 **MENU SPAMBOT**\nPilih mode spam yang tersedia:"
    buttons = [
        [Button.inline("❓ Bantuan Command", b"spam_help")],
        [Button.inline("⚙️ Cek Config", b"set_spambot")],
        [Button.inline("🛑 Stop Semua Task", b"spam_cancel_session")]
    ]
    try: await event.edit(text, buttons=buttons)
    except: await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"spam_help"))
async def cb_spam_help(event):
    help_txt = (
        "📚 **PANDUAN SPAMBOT**\n\n"
        "**1. Spam Biasa**\n"
        "`.spambot <target> <jumlah>`\n\n"
        "**2. Spam Premium**\n"
        "`.spambotpremium <target> <jumlah>`\n\n"
        "**3. Spam AI (Smart Context)**\n"
        "`.spamai <target> <min-max> <jml> <kata>`\n"
        "Fitur:\n"
        "- Scraping kata grup\n"
        "- Gabung kata manual + AI\n"
        "- Auto reply member lain\n"
        "- Auto stop reply jika grup sepi\n\n"
        "Contoh: `.spamai @grupkita 5-10 20 Halo bang`"
    )
    await event.edit(help_txt, buttons=[[Button.inline("🔙 Kembali", b"spam_menu")]])

@bot.on(events.CallbackQuery(pattern=b"spam_cancel_session"))
async def cb_spam_cancel_session(event):
    user_id = event.sender_id
    if user_id in ACTIVE_SPAM_TASKS:
        ACTIVE_SPAM_TASKS[user_id].cancel()
        del ACTIVE_SPAM_TASKS[user_id]
        await event.answer("🛑 Menghentikan proses...", alert=True)
        try: await event.edit("✅ **Proses Dihentikan User.**", buttons=None)
        except: pass
    else:
        await event.answer("⚠️ Tidak ada task berjalan.", alert=True)
    save_active_session(user_id, None)

@bot.on(events.CallbackQuery(pattern=b"spam_done"))
async def cb_spam_done(event): await event.delete()

@bot.on(events.CallbackQuery(pattern=b"spam_menu"))
async def cb_spam_menu(event): await show_spambot_menu(event, event.sender_id)

# ==========================================
# 5. REGISTRASI COMMAND
# ==========================================

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spamai"] = {"title": "Spam AI 🧠", "usage": ".spamai <target> <delay> <jml> <msg>"}
    help_dict[".spambot"] = {"title": "Spam Biasa 🤖", "usage": "Spam pesan config."}

    @client.on(events.NewMessage(pattern=r"(?i)^\.spambot (\S+) (\d+)"))
    async def exec_spam_std(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        if not is_allowed("spam"): return await event.edit("🔒 Dikunci Admin.")
        
        target = event.pattern_match.group(1)
        count = int(event.pattern_match.group(2))
        
        if user_id in ACTIVE_SPAM_TASKS and not ACTIVE_SPAM_TASKS[user_id].done():
            return await event.edit("⚠️ Masih ada task berjalan.")
        
        try: await event.delete()
        except: pass
        
        try: status_msg = await bot.send_message(user_id, f"🔄 **Spam Biasa...**\nTarget: {target}")
        except: return

        task = asyncio.create_task(run_spam_batch(client, user_id, target, count, 0, status_msg.id, user_id, False))
        ACTIVE_SPAM_TASKS[user_id] = task

    @client.on(events.NewMessage(pattern=r"(?i)^\.spamai (\S+) (\d+-\d+) (\d+) (.+)"))
    async def exec_spam_ai(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spam"): return await event.edit("🔒 Fitur dikunci Admin.")
        
        target = event.pattern_match.group(1)
        delay_range = event.pattern_match.group(2)
        count = int(event.pattern_match.group(3))
        msg = event.pattern_match.group(4)
        
        try:
            mn, mx = map(float, delay_range.split('-'))
        except:
            return await event.edit("⚠️ Format delay salah. Gunakan `min-max` (cth: `2-5`).")
        
        if user_id in ACTIVE_SPAM_TASKS and not ACTIVE_SPAM_TASKS[user_id].done():
            return await event.edit("⚠️ **Masih ada task berjalan!** Stop dulu.")

        try: await event.delete()
        except: pass
        
        try:
            status_msg = await bot.send_message(
                user_id, 
                f"🧠 **Inisialisasi Spam AI...**\nTarget: `{target}`\n\nSedang memproses..."
            )
        except: return

        task = asyncio.create_task(run_spamai_task(client, user_id, target, mn, mx, count, msg, status_msg))
        ACTIVE_SPAM_TASKS[user_id] = task