# bmcodexbot/bot_handlers/auth.py
import time
import json
import os
from telethon import events, Button, TelegramClient
from telethon.sessions import StringSession
from telethon.errors import MessageNotModifiedError
from config import bot, API_ID, API_HASH
from database import find_member_row, get_all_members_safe
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
            
    banner = "🟥 **Hubungkan ke Userbot**" if ub_status.startswith("🔴") else "🟩 **Userbot Terhubung**"
    text = (
        f"⚙️ **SETTING & KONEKSI**\n\n"
        f"{banner}\n"
        f"📡 **Status Userbot:** {ub_status}\n"
        f"📶 **Ping:** `{ping_ms}`\n"
        f"🤖 **Auto Reply:** {ar_status}\n\n"
    )
        # Tidak menampilkan informasi userbot member di UI pengguna
    text += "�👇 Pilih tindakan:"
    
    buttons = [
        [Button.inline("🔌 Hubungkan ke Userbot", b"start_auth_process")],
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

        # Buat client dengan timeout yang lebih lama untuk VPS
        new_client = TelegramClient(
            session_path, 
            API_ID, 
            API_HASH,
            connection_retries=5,
            retry_delay=2,
            timeout=30,
            request_retries=3
        )
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
        f"(Format: 1 2 3 4 5)",
        buttons=[[Button.inline("❌ Batal Login", b"cancel_login")]]
    )

# --- HANDLER RETRY SEND CODE (KIRIM ULANG KODE OTP) ---
@bot.on(events.CallbackQuery(pattern=b"retry_send_code"))
async def cb_retry_send_code(event):
    """Handler untuk mengirim ulang kode OTP"""
    import asyncio
    from telethon.errors import FloodWaitError
    
    user_id = event.sender_id
    if user_id not in LOGIN_STATE:
        return await event.edit("❌ Sesi telah berakhir. Silakan mulai ulang.", buttons=[[Button.inline("🔄 Mulai Ulang", b"start_auth_process")]])
    
    state = LOGIN_STATE[user_id]
    client = state.get("client")
    phone = state.get("phone")
    
    if not client or not phone:
        return await event.edit("❌ Data tidak lengkap. Silakan mulai ulang.", buttons=[[Button.inline("🔄 Mulai Ulang", b"start_auth_process")]])
    
    try:
        msg = await event.edit("🔄 Mengirim ulang kode OTP...")
        
        # Retry mechanism
        max_retries = 3
        retry_delay = 2
        sent = None
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Pastikan client masih terhubung
                if not client.is_connected():
                    await client.connect()
                
                # Kirim request kode dengan timeout lebih lama
                sent = await asyncio.wait_for(
                    client.send_code_request(phone),
                    timeout=30
                )
                break  # Berhasil, keluar dari loop
                
            except asyncio.TimeoutError:
                last_error = f"Timeout (percobaan {attempt + 1}/{max_retries})"
                if attempt < max_retries - 1:
                    await msg.edit(f"⏳ {last_error}. Mencoba lagi...")
                    await asyncio.sleep(retry_delay)
                else:
                    raise Exception(f"Gagal mengirim kode setelah {max_retries} percobaan: Timeout")
                    
            except FloodWaitError as e:
                wait_time = e.seconds
                last_error = f"FloodWait: tunggu {wait_time} detik"
                if attempt < max_retries - 1:
                    await msg.edit(f"⏳ {last_error}. Menunggu...")
                    await asyncio.sleep(wait_time + 1)
                else:
                    raise Exception(f"Gagal mengirim kode: {last_error}")
                    
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    await msg.edit(f"⚠️ Error: {last_error}. Mencoba lagi ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(retry_delay)
                else:
                    raise Exception(f"Gagal mengirim kode setelah {max_retries} percobaan: {last_error}")
        
        if sent is None:
            raise Exception(f"Gagal mengirim kode: {last_error}")
        
        # Update state dengan hash baru
        state["phone_code_hash"] = sent.phone_code_hash
        state["step"] = "code"
        
        await msg.edit(
            f"📩 **Kode Baru Terkirim ke {phone}**\n\n"
            "Silakan masukkan kode OTP yang baru Anda terima dari Telegram.\n"
            "Contoh: `1 2 3 4 5`\n\n"
            "💡 **Tips:** Jika kode tidak datang, coba:\n"
            "• Cek folder Spam/Notifikasi\n"
            "• Pastikan nomor HP aktif\n"
            "• Tunggu beberapa detik", 
            buttons=[[Button.inline("🔄 Kirim Ulang Kode", b"retry_send_code")], [Button.inline("❌ Batal", b"cancel_login")]]
        )
        
    except Exception as e:
        error_msg = str(e)
        import logging
        logging.error(f"Error retrying send code to {phone}: {error_msg}")
        
        if "Timeout" in error_msg or "timeout" in error_msg.lower():
            detailed_error = (
                f"❌ **Timeout - Koneksi ke Telegram terlalu lama**\n\n"
                f"**Kemungkinan penyebab:**\n"
                f"• Koneksi internet VPS lambat\n"
                f"• Firewall memblokir koneksi\n"
                f"• Telegram API sedang sibuk\n\n"
                f"**Solusi:**\n"
                f"• Coba lagi dalam beberapa saat\n"
                f"• Periksa koneksi internet server"
            )
        elif "FloodWait" in error_msg or "flood" in error_msg.lower():
            detailed_error = (
                f"❌ **Terlalu Banyak Permintaan**\n\n"
                f"Telegram membatasi jumlah request. Silakan tunggu beberapa saat dan coba lagi."
            )
        else:
            detailed_error = (
                f"❌ **Gagal mengirim ulang kode**\n\n"
                f"Error: `{error_msg[:200]}`\n\n"
                f"**Tips:**\n"
                f"• Coba lagi dalam beberapa saat\n"
                f"• Periksa koneksi internet server"
            )
        
        await event.edit(
            detailed_error,
            buttons=[[Button.inline("🔄 Coba Lagi", b"retry_send_code")], [Button.inline("❌ Batal", b"cancel_login")]]
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
