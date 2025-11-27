# modules/autoreply.py
import json
import os
import random
import time
from telethon import events
from config import bot

# File untuk menyimpan settingan per user
SETTINGS_FILE = "user_autoreply_settings.json"

# Cache memory untuk performa (biar gak baca file terus)
# Struktur: { "user_id": { "auto_reply": True, "reply_content": [...], "replied_chats": [] } }
USER_SETTINGS = {}

# ==========================================
# 1. FUNGSI UTILITAS (LOAD/SAVE)
# ==========================================

def load_settings():
    """Memuat settingan dari file JSON."""
    global USER_SETTINGS
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                # Konversi key string ke string (json force keys to string)
                USER_SETTINGS = data
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
    """Mengambil settingan user, buat default jika belum ada."""
    user_id = str(user_id)
    if user_id not in USER_SETTINGS:
        USER_SETTINGS[user_id] = {
            "auto_reply": False,
            "reply_content": [],  # List of dicts
            "replied_chats": []   # List of chat_ids yang sudah dibalas
        }
    
    # Migrasi format lama (string) ke format baru (list) jika perlu
    current_content = USER_SETTINGS[user_id].get("reply_content")
    if isinstance(current_content, str):
        USER_SETTINGS[user_id]["reply_content"] = [{
            "type": "text", 
            "text": current_content
        }]
        save_settings()
        
    return USER_SETTINGS[user_id]

# Load saat module diimport
load_settings()

# ==========================================
# 2. HANDLER COMMAND (.set_autoreply, dll)
# ==========================================

async def handle_autoreply_command(event, client):
    """
    Menangani command terkait auto reply dari Userbot.
    Dijalankan dari main.py atau handlers.py
    """
    message = event.message
    text = message.text
    user_id = str(client.uid) # ID pemilik userbot
    
    settings = get_user_settings(user_id)

    # --- 1. TOGGLE ON/OFF (.autoreply) ---
    if text.strip() == ".autoreply":
        settings["auto_reply"] = not settings["auto_reply"]
        status = "✅ ON" if settings["auto_reply"] else "❌ OFF"
        
        # Reset list chat yang sudah dibalas saat dihidupkan
        if settings["auto_reply"]:
            settings["replied_chats"] = []
            
        save_settings()
        await message.edit(f"🤖 **Auto Reply:** {status}")
        return

    # --- 2. SET KONTEN (.set_autoreply) ---
    elif text.startswith(".set_autoreply"):
        reply_msg = await message.get_reply_message()
        args = text.split(" ", 1)
        input_text = args[1] if len(args) > 1 else ""

        new_entry = None

        # A. Jika mereply pesan (Media/Sticker/Text lain)
        if reply_msg:
            if reply_msg.media:
                media_type = "media"
                if reply_msg.sticker: media_type = "sticker"
                elif reply_msg.photo: media_type = "photo"
                elif reply_msg.voice: media_type = "voice"
                elif reply_msg.video: media_type = "video"
                elif reply_msg.document: media_type = "document"

                new_entry = {
                    "type": media_type,
                    "text": input_text, # Caption opsional
                    "media_chat_id": reply_msg.chat_id,
                    "media_msg_id": reply_msg.id
                }
            else:
                # Reply text orang lain
                new_entry = {
                    "type": "text",
                    "text": reply_msg.text or input_text
                }
        
        # B. Jika input text langsung (.set_autoreply Halo)
        elif input_text:
            new_entry = {
                "type": "text",
                "text": input_text
            }
        
        else:
            await message.edit("❌ **Format salah.**\nKetik `.set_autoreply <pesan>` atau reply media/sticker.")
            return

        # Simpan ke list
        if new_entry:
            if not isinstance(settings["reply_content"], list):
                settings["reply_content"] = []
            
            settings["reply_content"].append(new_entry)
            save_settings()
            
            count = len(settings["reply_content"])
            await message.edit(
                f"✅ **Balasan ditambahkan ke urutan {count}!**\n"
                f"Sekarang bot akan mengirim {count} pesan secara berurutan.\n"
                f"Ketik `.view_autoreply` untuk melihat/menghapus."
            )

    # --- 3. LIHAT DAFTAR (.view_autoreply) ---
    elif text == ".view_autoreply":
        content = settings.get("reply_content", [])
        if not content:
            await message.edit("❌ Belum ada balasan auto reply tersimpan.\n\nGunakan `.set_autoreply <pesan>` untuk menambah.")
            return
            
        msg = "📋 **DAFTAR AUTO REPLY (Dikirim Berurutan)**\n"
        msg += "-------------------------------------------\n"
        for i, item in enumerate(content, 1):
            tipe = item.get("type", "text").upper()
            txt = item.get("text", "")
            
            # Preview text pendek
            if len(txt) > 30: txt = txt[:30] + "..."
            if not txt and tipe != "TEXT": txt = "(Tanpa Caption)"
            
            msg += f"**{i}. [{tipe}]** {txt}\n"
            
        msg += "-------------------------------------------\n"
        msg += "🗑 **Hapus:** `.del_autoreply <nomor>`\n"
        msg += "➕ **Tambah:** `.set_autoreply <pesan>` atau Reply Media"
        
        await message.edit(msg)

    # --- 4. HAPUS ITEM TERTENTU (.del_autoreply) ---
    elif text.startswith(".del_autoreply"):
        args = text.split(" ")
        if len(args) < 2 or not args[1].isdigit():
            await message.edit("❌ **Format salah.**\nGunakan `.del_autoreply <nomor>` (lihat di .view_autoreply)")
            return
            
        index = int(args[1]) - 1
        content = settings.get("reply_content", [])
        
        if 0 <= index < len(content):
            removed = content.pop(index)
            save_settings()
            tipe = removed.get("type", "text")
            await message.edit(f"✅ **Berhasil menghapus balasan no {index + 1} ({tipe})**")
        else:
            await message.edit("❌ Nomor tidak ditemukan.")

    # --- 5. HAPUS SEMUA (.clear_autoreply) ---
    elif text == ".clear_autoreply":
        settings["reply_content"] = []
        save_settings()
        await message.edit("🗑 **Semua balasan auto reply telah dihapus.**")

# ==========================================
# 3. LOGIKA UTAMA AUTO REPLY (LISTENER)
# ==========================================

async def check_and_reply(event, client):
    """
    Dipanggil setiap ada pesan masuk (Incoming Private Message).
    """
    if event.is_group or event.is_channel or event.out:
        return # Hanya untuk PM masuk

    user_id = str(client.uid)
    sender_id = event.sender_id
    
    # Jangan reply ke diri sendiri atau bot admin/service
    if sender_id == client.uid: return
    
    settings = get_user_settings(user_id)
    
    # 1. Cek apakah fitur ON
    if not settings.get("auto_reply"):
        return

    # 2. Cek apakah sudah pernah dibalas (Reply Once per session)
    replied_list = settings.get("replied_chats", [])
    if sender_id in replied_list:
        return 

    # 3. Ambil konten
    contents = settings.get("reply_content", [])
    if not contents: return

    # 4. KIRIM SEMUA PESAN DALAM DAFTAR (Berurutan)
    try:
        # Simulasi mengetik awal
        async with client.action(event.chat_id, 'typing'):
            await time.sleep(random.uniform(1.0, 2.0))

        # Loop semua konten yang di-set
        for item in contents:
            tipe = item.get("type", "text")
            
            if tipe == "text":
                await event.reply(item.get("text"))
            
            elif tipe in ["sticker", "photo", "voice", "video", "media", "document"]:
                source_chat = item.get("media_chat_id")
                source_msg_id = item.get("media_msg_id")
                caption = item.get("text", "")
                
                sent = False
                if source_chat and source_msg_id:
                    try:
                        # Ambil pesan asli untuk mendapatkan medianya
                        msg = await client.get_messages(source_chat, ids=source_msg_id)
                        if msg and msg.media:
                            await event.reply(caption, file=msg.media)
                            sent = True
                    except Exception as e:
                        print(f"[AutoReply] Media fetch error: {e}")
                
                # Jika gagal ambil media, kirim caption saja (jika ada)
                if not sent and caption:
                    await event.reply(f"{caption}\n_(Media tidak tersedia)_")
            
            # Beri jeda sedikit antar pesan agar tidak terdeteksi spam/flood
            await time.sleep(0.8)

        # 5. Tandai sudah dibalas
        replied_list.append(sender_id)
        settings["replied_chats"] = replied_list
        
    except Exception as e:
        print(f"[AutoReply] Failed to reply sequence: {e}")