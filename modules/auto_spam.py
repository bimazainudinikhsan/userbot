# bmcodexbot/modules/auto_spam.py
import asyncio
import json
import os
from telethon import events
from config import bot

SETTINGS_FILE = "user_autospam_settings.json"
AS_TASK = {} # Menyimpan task yang berjalan

# ==========================================
# 1. DATABASE & UTILS
# ==========================================
def get_settings(user_id):
    if not os.path.exists(SETTINGS_FILE):
        data = {}
    else:
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except:
            data = {}
            
    str_uid = str(user_id)
    if str_uid not in data:
        # Default Settings
        data[str_uid] = {
            "enabled": False,
            "message": "Halo, ini pesan otomatis.",
            "delay": 60, # Detik
            "target_type": "all" # all, group, user
        }
        save_settings(data)
    return data[str_uid]

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except:
        pass

def update_setting(user_id, key, value):
    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except:
            pass
    
    str_uid = str(user_id)
    if str_uid not in data: 
        get_settings(user_id)
        # Reload data safely
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except:
            pass
    
    if str_uid in data:
        data[str_uid][key] = value
        save_settings(data)

# ==========================================
# 2. LOGIC BROADCAST / AUTO MESSAGE
# ==========================================
async def start_auto_spam(client, user_id):
    settings = get_settings(user_id)
    if not settings.get("enabled"): return

    msg = settings.get("message")
    delay = settings.get("delay", 60)
    
    # Mencegah double task
    if user_id in AS_TASK:
        AS_TASK[user_id].cancel()
    
    AS_TASK[user_id] = asyncio.create_task(run_spam_loop(client, msg, delay))

async def run_spam_loop(client, msg, delay):
    while True:
        if not client.is_connected():
            await asyncio.sleep(5)
            continue
            
        try:
            # Broadcast ke semua dialog (hati-hati floodwait)
            async for dialog in client.iter_dialogs(limit=10):
                if dialog.is_group: # Hanya ke grup
                    try:
                        await client.send_message(dialog.entity, msg)
                        await asyncio.sleep(2) # Jeda antar chat
                    except: pass
            
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error Auto Spam: {e}")
            await asyncio.sleep(delay)

async def stop_auto_spam(user_id):
    if user_id in AS_TASK:
        AS_TASK[user_id].cancel()
        del AS_TASK[user_id]

# ==========================================
# 3. REGISTER USERBOT
# ==========================================
async def resume_spam_tasks(client):
    # Dipanggil saat startup
    user_id = (await client.get_me()).id
    await start_auto_spam(client, user_id)

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".automsg"] = {"title": "Auto Message 📨", "usage": "Mengirim pesan berkala ke grup."}
    
    # Resume saat load module
    await start_auto_spam(client, user_id)