# bmcodexbot/modules/auto_spam.py
import asyncio
import json
import os
from telethon import events, Button
from telethon.errors import FloodWaitError
from config import bot

SETTINGS_FILE = "user_autospam_settings.json"
ACTIVE_SPAM_TASKS = {} # Format: {user_id: {"task": asyncio.Task}}

# --- LOAD & SAVE SETTINGS ---
def load_spam_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_spam_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_user_spam_settings(user_id):
    data = load_spam_settings()
    return data.get(str(user_id), {
        "target": "", 
        "message": "Halo! Ini pesan otomatis.",
        "delay": 60,
        "is_running": False
    })

def update_user_spam_settings(user_id, updates):
    data = load_spam_settings()
    uid = str(user_id)
    if uid not in data: data[uid] = {}
    data[uid].update(updates)
    
    if "message" not in data[uid]: data[uid]["message"] = "Halo!"
    if "delay" not in data[uid]: data[uid]["delay"] = 60
    
    save_spam_settings(data)

# --- HANDLER MENU AUTO SPAM ---
# Kita gunakan callback 'menu_autospam' agar BEDA dengan 'menu_spambot' (AI punya kamu)
@bot.on(events.CallbackQuery(pattern=b"menu_autospam"))
async def cb_menu_autospam(event):
    user_id = event.sender_id
    settings = get_user_spam_settings(user_id)
    
    target = settings.get("target", "-")
    delay = settings.get("delay", 60)
    is_running = settings.get("is_running", False)
    
    status_icon = "🟢 BERJALAN" if is_running else "🔴 BERHENTI"
    btn_toggle = Button.inline("🛑 Stop", b"autospam_stop") if is_running else Button.inline("▶️ Mulai", b"autospam_start")

    text = (
        f"📨 **AUTO MESSAGE / SPAMMER**\n\n"
        f"Status: **{status_icon}**\n\n"
        f"🎯 **Target:** `{target}`\n"
        f"⏱ **Delay:** `{delay} detik`\n"
        f"📝 **Pesan:**\n`{settings.get('message')}`\n\n"
        f"__Fitur ini terpisah dari Spam AI.__"
    )
    
    buttons = [
        [btn_toggle],
        [Button.inline("🎯 Set Target", b"autospam_target"), Button.inline("⏱ Set Delay", b"autospam_delay")],
        [Button.inline("📝 Set Pesan", b"autospam_msg")],
        [Button.inline("⬅️ Menu Utama", b"menu_start")]
    ]
    
    await event.edit(text, buttons=buttons)

# --- TOMBOL ACTION ---
@bot.on(events.CallbackQuery(pattern=b"autospam_start"))
async def cb_autospam_start(event):
    user_id = event.sender_id
    from state import ACTIVE_USERBOTS
    if user_id not in ACTIVE_USERBOTS:
        return await event.answer("Userbot belum aktif!", alert=True)
        
    update_user_spam_settings(user_id, {"is_running": True})
    await resume_spam_tasks(ACTIVE_USERBOTS[user_id])
    await cb_menu_autospam(event)

@bot.on(events.CallbackQuery(pattern=b"autospam_stop"))
async def cb_autospam_stop(event):
    user_id = event.sender_id
    update_user_spam_settings(user_id, {"is_running": False})
    
    if user_id in ACTIVE_SPAM_TASKS:
        ACTIVE_SPAM_TASKS[user_id].cancel()
        del ACTIVE_SPAM_TASKS[user_id]
        
    await cb_menu_autospam(event)

# --- SPAM WORKER ---
async def spam_worker(client, user_id):
    print(f"🔄 AutoSpam Worker Started for {user_id}")
    while True:
        settings = get_user_spam_settings(user_id)
        if not settings.get("is_running"): break
            
        target = settings.get("target")
        msg = settings.get("message")
        delay = int(settings.get("delay", 60))
        
        if not target or not msg:
            update_user_spam_settings(user_id, {"is_running": False})
            break

        try:
            entity = int(target) if target.lstrip("-").isdigit() else target
            await client.send_message(entity, msg)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"❌ AutoSpam Error {user_id}: {e}")
        
        await asyncio.sleep(delay)

# --- FUNGSI RESUME (PENTING) ---
async def resume_spam_tasks(client):
    try:
        me = await client.get_me()
        user_id = me.id
        settings = get_user_spam_settings(user_id)
        
        if settings.get("is_running", False):
            if user_id in ACTIVE_SPAM_TASKS:
                ACTIVE_SPAM_TASKS[user_id].cancel()
            
            ACTIVE_SPAM_TASKS[user_id] = asyncio.create_task(spam_worker(client, user_id))
            print(f"▶️ Resuming AutoSpam for {user_id}")
    except Exception as e:
        print(f"❌ Error resuming autospam: {e}")