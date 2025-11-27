# bmcodexbot/modules/autoreply.py
import os
import logging
from telethon import events, utils
from modules.faktur import FAKTUR_SESSION 
from state import LIVE_CHAT_SESSIONS # FIX: Import dari state.py untuk hindari circular import

# Struktur Data:
# user_id -> {
#    "auto_reply": bool,
#    "reply_content": str,
#    "media_path": str (path file jika ada media),
#    "replied_chats": set()
# }
USER_SETTINGS = {}

# KONFIGURASI BATAS UKURAN FILE (Dalam Bytes)
# 10 MB = 10 * 1024 * 1024
MAX_FILE_SIZE = 10 * 1024 * 1024 

# Pastikan folder storage ada
if not os.path.exists('storage'):
    os.makedirs('storage', exist_ok=True)

def get_user_settings(user_id):
    if user_id not in USER_SETTINGS:
        USER_SETTINGS[user_id] = {
            "auto_reply": False,
            "reply_content": "🤖 Halo, saat ini saya sedang sibuk. Silakan tinggalkan pesan.",
            "media_path": None,
            "replied_chats": set()
        }
    return USER_SETTINGS[user_id]

async def register(client, user_id, is_allowed, check_status, help_dict):
    # Update Help Dictionary
    help_dict[".autoreply"] = {
        "title": "Auto Reply 🤖",
        "usage": "Nyalakan/Matikan auto reply."
    }
    help_dict[".set_autoreply"] = {
        "title": "Set Pesan Reply 📝",
        "usage": "Balas pesan (teks/media) dengan command ini untuk mengatur template."
    }

    # --- 1. TOGGLE ON/OFF ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.autoreply$"))
    async def enable_reply(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("autoreply"): 
            return await event.edit("🔒 Fitur dikunci.")
        
        settings = get_user_settings(user_id)
        settings["auto_reply"] = not settings["auto_reply"]
        
        # Reset replied chats saat ditoggle agar bisa reply lagi ke orang yg sama
        if settings["auto_reply"]:
            settings["replied_chats"] = set()
            
        status = "ON ✅" if settings["auto_reply"] else "OFF ❌"
        await event.edit(f"🤖 **Auto Reply {status}**")

    # --- 2. SET AUTOREPLY (BARU) ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.set_autoreply(?: |$)(.*)"))
    async def set_autoreply_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        if not is_allowed("autoreply"): return await event.edit("🔒 Fitur dikunci.")

        reply_msg = await event.get_reply_message()
        input_text = event.pattern_match.group(1).strip()
        settings = get_user_settings(user_id)
        
        await event.edit("🔄 Memproses pengaturan baru...")

        try:
            # KASUS A: User me-reply sebuah pesan (Bisa Media / Teks)
            if reply_msg:
                # 1. Jika pesan yang direply ada medianya (Gambar/Stiker/Dokumen/Voice)
                if reply_msg.media:
                    # --- VALIDASI UKURAN FILE ---
                    file_size = 0
                    if hasattr(reply_msg, 'document') and reply_msg.document:
                        file_size = reply_msg.document.size
                    elif hasattr(reply_msg, 'photo') and reply_msg.photo:
                        file_size = 0 
                    
                    if file_size > MAX_FILE_SIZE:
                        return await event.edit(f"⚠️ **Gagal:** Ukuran file terlalu besar!\nMaksimal: 10MB.\nFile Anda: {file_size / (1024*1024):.2f} MB")

                    # Hapus media lama jika ada
                    if settings["media_path"] and os.path.exists(settings["media_path"]):
                        try: os.remove(settings["media_path"])
                        except: pass
                    
                    # Download media baru
                    ext = utils.get_extension(reply_msg.media) or ".jpg"
                    file_path = f"storage/autoreply_{user_id}{ext}"
                    
                    await event.edit("⬇️ Mengunduh media...")
                    path = await reply_msg.download_media(file=file_path)
                    settings["media_path"] = path
                    
                    # Caption
                    if input_text:
                        settings["reply_content"] = input_text
                    else:
                        settings["reply_content"] = reply_msg.text or "" 
                    
                    await event.edit("✅ **Auto Reply Diupdate!**\nMedia: Terpasang\nCaption: Tersimpan.")
                
                # 2. Jika pesan yang direply hanya teks biasa
                else:
                    settings["media_path"] = None # Hapus media
                    settings["reply_content"] = input_text or reply_msg.text
                    await event.edit(f"✅ **Auto Reply Diupdate!**\nMode: Teks Saja\nPesan: `{settings['reply_content']}`")

            # KASUS B: Tidak me-reply pesan, cuma ketik .set_autoreply <pesan>
            elif input_text:
                settings["media_path"] = None
                settings["reply_content"] = input_text
                await event.edit(f"✅ **Auto Reply Diupdate!**\nMode: Teks Saja\nPesan: `{input_text}`")
            
            else:
                await event.edit("⚠️ **Cara Pakai:**\n\n1. Reply pesan (gambar/teks) dengan `.set_autoreply`\n2. Atau ketik `.set_autoreply <pesan baru>`")

        except Exception as e:
            logging.error(f"Set Autoreply Error: {e}")
            await event.edit(f"❌ Gagal menyimpan: {e}")


    # --- 3. LISTENER (PENGIRIM PESAN) ---
    @client.on(events.NewMessage(incoming=True)) 
    async def auto_reply_listener(event):
        me = await client.get_me()
        if event.sender_id == me.id: return 
        if not event.is_private: return 
        
        # 1. Cek Sesi Faktur
        if event.chat_id in FAKTUR_SESSION: return 
        
        # 2. Cek Sesi Live Chat (Jika di masa depan perlu integrasi)
        # Karena kita sudah pindahkan LIVE_CHAT_SESSIONS ke state.py, kita bisa akses dengan aman.
        # Namun logika userbot (akun member) vs bot manager (akun admin) berbeda.
        # Userbot membalas pesan di akun member. Livechat terjadi di bot manager.
        # Jadi ini tidak konflik. Biarkan saja.
        
        settings = get_user_settings(user_id)
        if not settings["auto_reply"]: return
        
        if event.chat_id in settings["replied_chats"]: return

        try:
            if settings["media_path"] and os.path.exists(settings["media_path"]):
                await event.reply(
                    file=settings["media_path"], 
                    message=settings["reply_content"]
                )
            elif settings["reply_content"]:
                await event.reply(settings["reply_content"])
            
            settings["replied_chats"].add(event.chat_id)
            logging.info(f"AutoReply sent to {event.chat_id}")
            
        except Exception as e:
            logging.error(f"AutoReply Error: {e}")