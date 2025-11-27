# modules/autoreply.py
import json
import os
import random
import time
from telethon import events
from config import bot

# File untuk menyimpan settingan per user
SETTINGS_FILE = "user_autoreply_settings.json"
BASE_STORAGE_DIR = "storage/autoreply_media"

# Pastikan base folder ada
if not os.path.exists(BASE_STORAGE_DIR):
    os.makedirs(BASE_STORAGE_DIR)

# Cache memory
USER_SETTINGS = {}

# ==========================================
# 1. FUNGSI UTILITAS (LOAD/SAVE & STORAGE)
# ==========================================

def load_settings():
    """Memuat settingan dari file JSON."""
    global USER_SETTINGS
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                USER_SETTINGS = json.load(f)
        except Exception as e:
            print(f"[AutoReply] Error loading settings: {e}")
            USER_SETTINGS = {}
    else:
        USER_SETTINGS = {}

def save_settings():
    """Menyimpan settingan ke file JSON."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(USER_SETTINGS, f, indent=2)
    except Exception as e:
        print(f"[AutoReply] Error saving settings: {e}")

def get_user_settings(user_id):
    """Mengambil settingan user."""
    user_id = str(user_id)
    if user_id not in USER_SETTINGS:
        USER_SETTINGS[user_id] = {
            "auto_reply": False,
            "reply_content": [],
            "replied_chats": []
        }
    return USER_SETTINGS[user_id]

# --- FUNGSI BARU UNTUK MANAJEMEN STORAGE PER USER ---

def get_user_storage_path(user_id):
    """Mendapatkan path folder khusus untuk user tertentu."""
    user_path = os.path.join(BASE_STORAGE_DIR, str(user_id))
    if not os.path.exists(user_path):
        os.makedirs(user_path)
    return user_path

def get_storage_usage(user_id):
    """Menghitung total penggunaan storage user dalam format string (MB/KB)."""
    user_path = os.path.join(BASE_STORAGE_DIR, str(user_id))
    total_size = 0
    
    if os.path.exists(user_path):
        for dirpath, dirnames, filenames in os.walk(user_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
    
    # Format ke KB atau MB
    if total_size < 1024 * 1024:
        return f"{total_size / 1024:.2f} KB"
    else:
        return f"{total_size / (1024 * 1024):.2f} MB"

# Load saat module diimport
load_settings()

# ==========================================
# 2. HANDLER USERBOT (Check & Reply)
# ==========================================

async def check_and_reply(event, client):
    """Dipanggil setiap ada pesan masuk (Incoming Private Message)."""
    if event.is_group or event.is_channel or event.out:
        return 

    user_id = str(client.uid)
    sender_id = event.sender_id
    if sender_id == client.uid: return
    
    settings = get_user_settings(user_id)
    
    if not settings.get("auto_reply"): return

    # Reply Once Logic
    replied_list = settings.get("replied_chats", [])
    if sender_id in replied_list: return 

    contents = settings.get("reply_content", [])
    if not contents: return

    try:
        async with client.action(event.chat_id, 'typing'):
            await time.sleep(random.uniform(1.0, 2.0))

        for item in contents:
            tipe = item.get("type", "text")
            
            if tipe == "text":
                await event.reply(item.get("text"))
            
            # Handling Media
            elif tipe in ["sticker", "photo", "voice", "video", "document", "audio", "media"]:
                caption = item.get("text", "")
                file_sent = False

                # A. Prioritas: Kirim dari File Path (Upload dari Bot Manager)
                file_path = item.get("file_path")
                if file_path and os.path.exists(file_path):
                    try:
                        await event.reply(caption, file=file_path)
                        file_sent = True
                    except Exception as e:
                        print(f"[AutoReply] Upload failed: {e}")

                # B. Fallback: Ambil dari Chat History (Settingan Lama/Manual)
                if not file_sent:
                    source_chat = item.get("media_chat_id")
                    source_msg_id = item.get("media_msg_id")
                    if source_chat and source_msg_id:
                        try:
                            msg = await client.get_messages(source_chat, ids=source_msg_id)
                            if msg and msg.media:
                                await event.reply(caption, file=msg.media)
                                file_sent = True
                        except:
                            pass
                
                # C. Jika Gagal Semua
                if not file_sent and caption:
                    await event.reply(f"{caption}\n_(Media tidak tersedia)_")
            
            await time.sleep(0.8)

        replied_list.append(sender_id)
        settings["replied_chats"] = replied_list
        
    except Exception as e:
        print(f"[AutoReply] Failed: {e}")

# ==========================================
# 3. FUNGSI HELPER UNTUK BOT MANAGER (CRUD)
# ==========================================

def add_autoreply_content(user_id, content_data):
    settings = get_user_settings(user_id)
    if not isinstance(settings["reply_content"], list):
        settings["reply_content"] = []
    settings["reply_content"].append(content_data)
    save_settings()

def update_autoreply_content(user_id, index, content_data):
    settings = get_user_settings(user_id)
    if 0 <= index < len(settings["reply_content"]):
        # Hapus file lama jika diganti media baru
        old_item = settings["reply_content"][index]
        old_path = old_item.get("file_path")
        
        # Jika ada path baru, dan beda dengan path lama, hapus yang lama
        if old_path and os.path.exists(old_path):
            new_path = content_data.get("file_path")
            if new_path != old_path:
                try:
                    os.remove(old_path)
                except: pass

        settings["reply_content"][index] = content_data
        save_settings()
        return True
    return False

def delete_autoreply_content(user_id, index):
    settings = get_user_settings(user_id)
    content_list = settings.get("reply_content", [])
    
    if 0 <= index < len(content_list):
        # 1. Ambil data item sebelum dihapus
        item_to_remove = content_list[index]
        
        # 2. Cek apakah ada file media fisik yang tersimpan
        file_path = item_to_remove.get("file_path")
        
        # 3. Hapus file dari penyimpanan server
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[AutoReply] File media dihapus: {file_path}")
            except Exception as e:
                print(f"[AutoReply] Gagal menghapus file media: {e}")
        
        # 4. Hapus item dari list database
        content_list.pop(index)
        save_settings()
        return True
    return False