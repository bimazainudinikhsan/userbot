# bmcodexbot/bot_handlers/auth.py
import time
import asyncio
from telethon import events, Button, TelegramClient, errors
from telethon.sessions import StringSession
from config import bot, API_ID, API_HASH
from database import find_member_row
from state import ACTIVE_USERBOTS, LOGIN_STATE
from modules.autoreply import get_user_settings

# ==========================================
# 1. MENU SETTING & KONEKSI
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"menu_connect_ub"))
async def cb_connect_ub_menu(event):
    user_id = event.sender_id
    
    settings = get_user_settings(user_id)
    ar_status = "✅ ON" if settings.get("auto_reply") else "❌ OFF"
    
    client = ACTIVE_USERBOTS.get(user_id)
    ub_status = "🔴 Offline"
    ping_ms = "-"
    
    if client:
        try:
            if client.is_connected():
                ub_status = "🟢 Online"
                start = time.perf_counter()
                await client.get_me()
                end = time.perf_counter()
                ping_ms = f"{(end - start) * 1000:.0f}ms"
            else:
                ub_status = "⚠️ Disconnected"
        except:
            ub_status = "❌ Error"
            
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
    except Exception:
        await event.respond(text, buttons=buttons)

# ==========================================
# 2. PROSES LOGIN (TOMBOL)
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"start_auth_process"))
async def cb_start_auth(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    
    if not row: return await event.answer("❌ Belum terdaftar.", alert=True)
    if row.get("Status") != "Approved": return await event.answer("❌ Akun tidak aktif.", alert=True)
    
    # Bersihkan sesi lama jika ada
    if user_id in ACTIVE_USERBOTS:
        try: await ACTIVE_USERBOTS[user_id].disconnect()
        except: pass
        del ACTIVE_USERBOTS[user_id]
        
    # Bersihkan state login lama
    if user_id in LOGIN_STATE:
        try: await LOGIN_STATE[user_id]["client"].disconnect()
        except: pass
        del LOGIN_STATE[user_id]

    print(f"[AUTH] INIT: Membuat client baru untuk user {user_id}...")

    # Inisialisasi Client Baru
    try:
        new_client = TelegramClient(StringSession(), API_ID, API_HASH)
        await new_client.connect()
    except Exception as e:
        return await event.edit(f"❌ **Gagal Connect ke Telegram:**\n`{str(e)}`")
    
    # Reset State Login
    LOGIN_STATE[user_id] = {
        "step": "phone", 
        "client": new_client,
        "phone": None,
        "phone_code_hash": None 
    }
    
    print(f"[AUTH] START: Client connected. Menunggu nomor HP dari user {user_id}.")
    
    await event.edit(
        "📱 **LOGIN USERBOT**\n\n"
        "Silakan kirim **Nomor HP** akun Telegram Anda.\n"
        "Format: Kode Negara + Nomor (Contoh: `+628123456789`)", 
        buttons=[Button.inline("❌ Batal", b"cancel_login")]
    )

@bot.on(events.CallbackQuery(pattern=b"retry_code"))
async def cb_retry_code(event):
    user_id = event.sender_id
    if user_id not in LOGIN_STATE:
        return await event.edit("❌ Sesi habis. Mulai ulang.", buttons=[[Button.inline("🔄 Ulangi", b"start_auth_process")]])
    
    LOGIN_STATE[user_id]["step"] = "code"
    print(f"[AUTH] RETRY: User {user_id} meminta input ulang kode.")
    
    await event.edit(
        "📩 **INPUT KODE ULANG**\n\n"
        "Silakan masukkan kode OTP Telegram.\n"
        "Contoh: `1 2 3 4 5` (Pakai spasi agar tidak jadi link)",
        buttons=[[Button.inline("❌ Batal", b"cancel_login")]]
    )

@bot.on(events.CallbackQuery(pattern=b"cancel_login"))
async def cb_cancel_login(event):
    user_id = event.sender_id
    print(f"[AUTH] CANCEL REQUEST: User {user_id} menekan tombol Batal.")
    
    if user_id in LOGIN_STATE:
        try: 
            await LOGIN_STATE[user_id]["client"].disconnect()
            print(f"[AUTH] CANCEL: Client user {user_id} diputus.")
        except Exception as e: 
            print(f"[AUTH] CANCEL ERROR: {e}")
        del LOGIN_STATE[user_id]
    
    await cb_connect_ub_menu(event)

# ==========================================
# 3. HANDLER INPUT TEKS
# ==========================================
@bot.on(events.NewMessage(incoming=True))
async def auth_input_handler(event):
    user_id = event.sender_id
    
    if user_id not in LOGIN_STATE:
        return 

    if event.text.startswith("/"): return 

    state = LOGIN_STATE[user_id]
    step = state.get("step")
    client = state.get("client")

    # Cek apakah client masih hidup
    if not client or not client.is_connected():
        print(f"[AUTH ERROR] Client terputus/hilang untuk user {user_id}")
        await event.reply("❌ **Sesi Terputus.** Silakan tekan tombol login lagi.", buttons=[Button.inline("Login Ulang", b"start_auth_process")])
        del LOGIN_STATE[user_id]
        return 

    # --- LANGKAH 1: TERIMA NOMOR HP ---
    if step == "phone":
        raw_text = event.text.strip()
        phone_number = "".join(filter(str.isdigit, raw_text))
        if raw_text.startswith("+"):
            phone_number = "+" + phone_number
            
        print(f"[AUTH] PHONE STEP: User {user_id} input nomor: {phone_number}")
        
        msg = await event.reply("🔄 **Mengirim Kode OTP...**\nMohon tunggu...")
        
        try:
            # Request Kode
            send_code = await client.send_code_request(phone_number)
            
            # DEBUG PENTING: Print Hash ke Terminal VPS
            the_hash = send_code.phone_code_hash
            print(f"\n[AUTH] ========================================")
            print(f"[AUTH] KODE TERKIRIM KE: {phone_number}")
            print(f"[AUTH] PHONE_CODE_HASH : {the_hash}")
            print(f"[AUTH] ========================================\n")
            
            # Simpan State
            LOGIN_STATE[user_id]["phone"] = phone_number
            LOGIN_STATE[user_id]["phone_code_hash"] = the_hash
            LOGIN_STATE[user_id]["step"] = "code"
            
            await msg.edit(
                f"✅ **Kode Terkirim!**\n\n"
                f"Dikirim ke: `{phone_number}`\n"
                f"👉 **Balas pesan ini dengan angka KODE OTP.**\n"
                f"Contoh: `1 2 3 4 5` (Pakai spasi)",
                buttons=[Button.inline("❌ Batal", b"cancel_login")]
            )
            
        except errors.PhoneNumberInvalidError:
            await msg.edit("❌ **Nomor Tidak Valid.** Gunakan format internasional (cth: +62...)", buttons=[Button.inline("Ulangi", b"start_auth_process")])
        except errors.FloodWaitError as e:
            await msg.edit(f"❌ **Terkena Limit Telegram**\nTunggu {e.seconds} detik baru coba lagi.", buttons=[Button.inline("Batal", b"cancel_login")])
        except Exception as e:
            print(f"[AUTH ERROR] Send Code Exception: {e}")
            await msg.edit(f"❌ **Error:** `{str(e)}`", buttons=[Button.inline("Batal", b"cancel_login")])

    # --- LANGKAH 2: TERIMA KODE OTP ---
    elif step == "code":
        otp_code = "".join(filter(str.isdigit, event.text))
        
        if not otp_code:
            await event.reply("⚠️ Masukkan angka kodenya saja.", buttons=[[Button.inline("Batal", b"cancel_login")]])
            return

        msg = await event.reply("🔄 **Login...**")
        
        try:
            current_state = LOGIN_STATE.get(user_id, {})
            hash_code = current_state.get("phone_code_hash")
            phone_num = current_state.get("phone")

            if not hash_code:
                print(f"[AUTH FATAL] Hash Code hilang untuk user {user_id}!")
                await msg.edit("❌ **Sesi Error:** Hash hilang. Silakan Login ulang.", buttons=[[Button.inline("Login Ulang", b"start_auth_process")]])
                return

            print(f"[AUTH] VERIFIKASI: Phone={phone_num} | Code={otp_code} | Hash={hash_code}")

            # Eksekusi Sign In
            await client.sign_in(phone_num, otp_code, phone_code_hash=hash_code)
            
            # Jika sukses
            ACTIVE_USERBOTS[user_id] = client 
            del LOGIN_STATE[user_id]
            
            me = await client.get_me()
            name = me.first_name or "User"
            print(f"[AUTH] LOGIN SUKSES: {name} ({user_id})")
            
            await msg.edit(
                f"🎉 **LOGIN BERHASIL!**\n\n"
                f"Halo, **{name}**! Userbot aktif.\n"
                f"Hash verifikasi berhasil digunakan.",
                buttons=[Button.inline("⚙️ Menu Pengaturan", b"menu_connect_ub")]
            )

        except errors.SessionPasswordNeededError:
            LOGIN_STATE[user_id]["step"] = "password"
            print(f"[AUTH] 2FA STEP: User {user_id} butuh password.")
            await msg.edit(
                "🔐 **Verifikasi 2 Langkah (2FA)**\n\n"
                "Akun ini menggunakan password.\n"
                "👉 **Balas dengan PASSWORD akun Anda.**",
                buttons=[Button.inline("❌ Batal", b"cancel_login")]
            )
            
        except (errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError):
            await msg.edit("❌ **Kode Salah atau Kadaluarsa.**", buttons=[[Button.inline("Coba Lagi", b"retry_code")]])
        except Exception as e:
            print(f"[AUTH ERROR] Sign In Exception: {e}")
            await msg.edit(f"❌ **Gagal Login:** `{str(e)}`", buttons=[[Button.inline("Batal", b"cancel_login")]])

    # --- LANGKAH 3: TERIMA PASSWORD 2FA ---
    elif step == "password":
        password = event.text.strip()
        msg = await event.reply("🔄 **Cek Password...**")
        
        try:
            await client.sign_in(password=password)
            
            ACTIVE_USERBOTS[user_id] = client
            del LOGIN_STATE[user_id]
            
            me = await client.get_me()
            name = me.first_name or "User"
            print(f"[AUTH] LOGIN 2FA SUKSES: {name} ({user_id})")
            
            await msg.edit(
                f"🎉 **LOGIN BERHASIL!**\n\n"
                f"Halo, **{name}**! Userbot aktif.",
                buttons=[Button.inline("⚙️ Menu Pengaturan", b"menu_connect_ub")]
            )
        except errors.PasswordHashInvalidError:
            await msg.edit("❌ **Password Salah.** Coba lagi.", buttons=[[Button.inline("Batal", b"cancel_login")]])
        except Exception as e:
            await msg.edit(f"❌ **Error:** `{str(e)}`", buttons=[[Button.inline("Batal", b"cancel_login")]])