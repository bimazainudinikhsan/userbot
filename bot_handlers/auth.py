# bmcodexbot/bot_handlers/auth.py
import time
import json
import os
from telethon import events, Button, TelegramClient
from telethon.sessions import StringSession
from telethon.errors import MessageNotModifiedError
from config import bot, API_ID, API_HASH
from database import find_member_row
from state import ACTIVE_USERBOTS, LOGIN_STATE
from modules.autoreply import get_user_settings

# --- MENU SETTING & KONEKSI ---
@bot.on(events.CallbackQuery(pattern=b"menu_connect_ub"))
async def cb_connect_ub_menu(event):
    user_id = event.sender_id
    
    settings = get_user_settings(user_id)
    ar_status = "✅ ON" if settings.get("auto_reply") else "❌ OFF"
    
    client = ACTIVE_USERBOTS.get(user_id)
    ub_status = "🔴 Offline"
    ping_ms = "-"
    
    if client and client.is_connected():
        ub_status = "🟢 Online"
        try:
            start = time.perf_counter()
            await client.get_me()
            end = time.perf_counter()
            ping_ms = f"{(end - start) * 1000:.0f}ms"
        except:
            ping_ms = "Timeout"
            
    text = (
        f"⚙️ **SETTING & KONEKSI**\n\n"
        f"📡 **Status Userbot:** {ub_status}\n"
        f"📶 **Ping:** `{ping_ms}`\n"
        f"🤖 **Auto Reply:** {ar_status}\n\n"
        f"👇 Pilih tindakan:"
    )
    
    buttons = [
        [Button.inline("🔌 Login / Ganti Akun", b"start_auth_process")],
        [Button.inline("🔄 Cek Koneksi Sekarang", b"menu_connect_ub")],
        [Button.inline("⬅️ Menu Utama", b"menu_start")]
    ]
    
    try:
        await event.edit(text, buttons=buttons)
    except MessageNotModifiedError:
        await event.answer("✅ Status sudah paling update.")
    except Exception as e:
        print(f"Error updating menu: {e}")

# --- PROSES LOGIN ---
@bot.on(events.CallbackQuery(pattern=b"start_auth_process"))
async def cb_start_auth(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    
    if not row: return await event.answer("❌ Belum terdaftar.", alert=True)
    # Status tidak dicek ketat di sini agar user Expired pun bisa login ulang
    # if row.get("Status") != "Approved": return await event.answer("❌ Akun tidak aktif.", alert=True)
    
    if user_id in ACTIVE_USERBOTS:
        try:
            await ACTIVE_USERBOTS[user_id].disconnect()
        except: pass
        if user_id in ACTIVE_USERBOTS: del ACTIVE_USERBOTS[user_id]

    # Inisialisasi Client Baru
    try:
        # Membuat folder sesi jika belum ada
        session_folder = "botsession"
        if not os.path.exists(session_folder):
            os.makedirs(session_folder)
            
        session_path = os.path.join(session_folder, str(user_id))
        
        # Hapus sesi lama jika ada agar bersih
        if os.path.exists(f"{session_path}.session"):
             try: os.remove(f"{session_path}.session")
             except: pass

        new_client = TelegramClient(session_path, API_ID, API_HASH)
        await new_client.connect()
    except Exception as e:
        return await event.edit(f"❌ **Gagal Connect ke Server Telegram:**\n`{str(e)}`\nSilakan coba lagi beberapa saat lagi.")
    
    # Reset State Login
    LOGIN_STATE[user_id] = {
        "step": "phone", 
        "client": new_client
    }
    
    # TAMPILAN INSTRUKSI YANG LEBIH JELAS
    await event.edit(
        "📱 **HUBUNGKAN AKUN TELEGRAM**\n\n"
        "Silakan kirim **Nomor HP** akun Telegram Anda di sini.\n"
        "Bot akan otomatis memperbaiki formatnya.\n\n"
        "**Contoh Format yang Diterima:**\n"
        "✅ `6281234567890` (Tanpa +)\n"
        "✅ `081234567890` (Format Lokal)\n"
        "✅ `+6281234567890` (Format Internasional)\n\n"
        "__Ketik nomornya dan kirim sekarang...__", 
        buttons=[Button.inline("❌ Batal", b"cancel_login")]
    )

# --- HANDLER RETRY CODE (JIKA SALAH INPUT OTP) ---
@bot.on(events.CallbackQuery(pattern=b"retry_code"))
async def cb_retry_code(event):
    user_id = event.sender_id
    if user_id not in LOGIN_STATE:
        return await event.edit("❌ Sesi telah berakhir. Silakan mulai ulang.", buttons=[[Button.inline("🔄 Mulai Ulang", b"start_auth_process")]])
    
    # Kembalikan ke prompt kode tanpa reset client
    LOGIN_STATE[user_id]["step"] = "code"
    phone = LOGIN_STATE[user_id].get("phone", "Nomor Anda")
    
    await event.edit(
        f"📩 **Input Ulang Kode OTP**\n\n"
        f"Silakan masukkan kode baru yang dikirim ke {phone}.\n"
        f"(Format: 1 2 3 4 5 atau 12345)",
        buttons=[[Button.inline("❌ Batal Login", b"cancel_login")]]
    )

# --- HANDLER BATAL LOGIN ---
@bot.on(events.CallbackQuery(pattern=b"cancel_login"))
async def cb_cancel_login(event):
    user_id = event.sender_id
    if user_id in LOGIN_STATE:
        try: await LOGIN_STATE[user_id]["client"].disconnect()
        except: pass
        del LOGIN_STATE[user_id]
    
    await cb_connect_ub_menu(event)