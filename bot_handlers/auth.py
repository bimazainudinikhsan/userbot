# bmcodexbot/bot_handlers/auth.py
import time
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
    if row.get("Status") != "Approved": return await event.answer("❌ Akun tidak aktif.", alert=True)
    
    if user_id in ACTIVE_USERBOTS:
        try:
            await ACTIVE_USERBOTS[user_id].disconnect()
        except: pass
        if user_id in ACTIVE_USERBOTS: del ACTIVE_USERBOTS[user_id]

    new_client = TelegramClient(StringSession(), API_ID, API_HASH)
    await new_client.connect()
    LOGIN_STATE[user_id] = {"step": "phone", "client": new_client}
    
    await event.edit(
        "📱 **HUBUNGKAN AKUN**\n\nSilakan kirim Nomor HP Anda.\nContoh: `+62812345678`", 
        buttons=[Button.inline("❌ Batal", b"cancel_login")]
    )

# --- HANDLER RETRY CODE (BARU) ---
@bot.on(events.CallbackQuery(pattern=b"retry_code"))
async def cb_retry_code(event):
    user_id = event.sender_id
    if user_id not in LOGIN_STATE:
        return await event.edit("❌ Sesi telah berakhir. Silakan mulai ulang.", buttons=[[Button.inline("🔄 Mulai Ulang", b"start_auth_process")]])
    
    # Kembalikan ke prompt kode tanpa reset client
    LOGIN_STATE[user_id]["step"] = "code"
    
    await event.edit(
        "📩 **Input Ulang Kode OTP**\n\nSilakan masukkan kode yang baru saja Anda terima di Telegram.\n(Format: 1 2 3 4 5)",
        buttons=[[Button.inline("❌ Batal Login", b"cancel_login")]]
    )

@bot.on(events.CallbackQuery(pattern=b"cancel_login"))
async def cb_cancel_login(event):
    user_id = event.sender_id
    if user_id in LOGIN_STATE:
        try: await LOGIN_STATE[user_id]["client"].disconnect()
        except: pass
        del LOGIN_STATE[user_id]
    
    await cb_connect_ub_menu(event)