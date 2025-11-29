# bmcodexbot/modules/autoreply.py
import json
import os
import random
import asyncio # PERBAIKAN: Menggunakan asyncio untuk sleep
from telethon import events

SETTINGS_FILE = "user_autoreply_settings.json"
BASE_STORAGE_DIR = "storage/autoreply_media"

# Pastikan folder storage ada
if not os.path.exists(BASE_STORAGE_DIR):
    os.makedirs(BASE_STORAGE_DIR)

USER_SETTINGS = {}

# ==========================================
# 1. DATABASE & UTILS (Backend)
# ==========================================
def load_settings():
    global USER_SETTINGS
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                USER_SETTINGS = json.load(f)
        except:
            USER_SETTINGS = {}
    else:
        USER_SETTINGS = {}

def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(USER_SETTINGS, f, indent=2)
    except:
        pass

def get_user_settings(user_id):
    user_id = str(user_id)
    if user_id not in USER_SETTINGS:
        # Default Settings
        USER_SETTINGS[user_id] = {
            "auto_reply": False, 
            "reply_content": [], 
            "replied_chats": []
        }
    return USER_SETTINGS[user_id]

def update_user_setting(user_id, key, value):
    settings = get_user_settings(user_id)
    settings[key] = value
    save_settings()

# Load saat module diimport pertama kali
load_settings()

# ==========================================
# 2. LOGIKA USERBOT (Auto Reply Engine)
# ==========================================
async def check_and_reply(event, client):
    """
    Fungsi inti untuk mengecek pesan masuk dan membalasnya.
    """
    # Filter: Hanya chat pribadi (incoming), bukan grup/channel/bot
    if event.is_group or event.is_channel or event.out or event.sender_id == (await client.get_me()).id:
        return 

    user_id = str((await client.get_me()).id)
    sender_id = event.sender_id
    
    settings = get_user_settings(user_id)
    
    # Cek apakah fitur ON
    if not settings.get("auto_reply"): 
        return

    # Cek apakah sudah pernah dibalas (Reply Once)
    replied_list = settings.get("replied_chats", [])
    if sender_id in replied_list: 
        return 

    # Cek apakah ada konten balasan
    contents = settings.get("reply_content", [])
    if not contents: 
        return

    try:
        # Efek mengetik (biar natural)
        async with client.action(event.chat_id, 'typing'):
            # PERBAIKAN: Gunakan asyncio.sleep agar tidak error
            await asyncio.sleep(random.uniform(1.5, 3.0))

        # Kirim pesan balasan (Looping jika ada banyak bubble chat)
        for item in contents:
            tipe = item.get("type", "text")
            text_msg = item.get("text", "")
            
            if tipe == "text":
                await event.reply(text_msg)
            
            # (Tambahkan logic media di sini jika nanti diperlukan)
            
            await asyncio.sleep(0.8) # Jeda antar bubble

        # Tandai user ini sudah dibalas
        replied_list.append(sender_id)
        settings["replied_chats"] = replied_list
        save_settings()
        
    except Exception as e:
        print(f"[AutoReply] Error sending reply: {e}")

# ==========================================
# 3. REGISTER FUNCTION (Wajib Ada!)
# ==========================================
async def register(client, user_id, is_allowed, check_status, help_dict):
    """
    Fungsi ini dipanggil oleh aktif_fitur.py untuk mendaftarkan event handler.
    """
    # Daftarkan info bantuan
    help_dict[".autoreply"] = {
        "title": "Auto Reply 💬",
        "usage": "Balas PM otomatis. Setting via Bot Manager."
    }

    # Daftarkan Event Handler (New Message)
    @client.on(events.NewMessage(incoming=True))
    async def autoreply_handler(event):
        # 1. Cek Permission Global
        if not is_allowed("autoreply"): 
            return
            
        # 2. Jalankan logika auto reply
        await check_and_reply(event, client)