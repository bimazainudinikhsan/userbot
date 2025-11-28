# bmcodexbot/bot_handlers/auth.py
import time
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
        if hasattr(event, 'edit'):
            await event.edit(text, buttons=buttons)
        else:
            await event.respond(text, buttons=buttons)
    except Exception as e:
        pass 

# ==========================================
# 2. PROSES LOGIN (TOMBOL)
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"start_auth_process"))
async def cb_start_auth(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    
    if not row: return await event.answer("❌ Belum terdaftar.", alert=True)
    if row.get("Status") != "Approved": return await event.answer("❌ Akun tidak aktif.", alert=True)
    
    # Reset sesi lama
    if user_id in ACTIVE_USERBOTS:
        try: await ACTIVE_USERBOTS[user_id].disconnect()
        except: pass
        if user_id in ACTIVE_USERBOTS: del ACTIVE_USERBOTS[user_id]

    # Inisialisasi Client Baru
    new_client = TelegramClient(StringSession(), API_ID, API_HASH)
    await new_client.connect()
    
    # Reset State Login
    LOGIN_STATE[user_id] = {
        "step": "phone", 
        "client": new_client,
        "phone": None,
        "phone_code_hash": None 
    }
    
    print(f"[AUTH] START: User {user_id} memulai login. Client connected.")
    
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
    if user_id in LOGIN_STATE:
        try: await LOGIN_STATE[user_id]["client"].disconnect()
        except: pass
        del LOGIN_STATE[user_id]
        print(f"[AUTH] CANCEL: User {user_id} membatalkan login.")
    
    await cb_connect_ub_menu(event)

# ==========================================
# 3. HANDLER INPUT TEKS (DEBUGGED)
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

    if not client:
        print(f"[AUTH ERROR] Client object missing for user {user_id}")
        del LOGIN_STATE[user_id]
        return 

    # --- LANGKAH 1: TERIMA NOMOR HP ---
    if step == "phone":
        # Bersihkan input sebersih mungkin
        raw_text = event.text.strip()
        phone_number = "".join(filter(str.isdigit, raw_text))
        if raw_text.startswith("+"):
            phone_number = "+" + phone_number
            
        print(f"[AUTH] PHONE STEP: Menerima nomor {phone_number} dari user {user_id}")
        
        msg = await event.reply("🔄 **Memproses nomor...**\nMohon tunggu sebentar.")
        
        try:
            send_code = await client.send_code_request(phone_number)
            
            # SIMPAN HASH DENGAN EKSPLISIT
            LOGIN_STATE[user_id]["phone"] = phone_number
            LOGIN_STATE[user_id]["phone_code_hash"] = send_code.phone_code_hash
            LOGIN_STATE[user_id]["step"] = "code"
            
            # Debug Print: Pastikan hash tersimpan
            saved_hash = LOGIN_STATE[user_id].get("phone_code_hash")
            print(f"[AUTH] SUCCESS SEND CODE: Hash '{saved_hash}' disimpan untuk user {user_id}")
            
            await msg.edit(
                f"✅ **Kode Terkirim!**\n\n"
                f"Kode OTP telah dikirim ke akun Telegram nomor `{phone_number}`.\n\n"
                f"👉 **Silakan balas pesan ini dengan KODE OTP tersebut.**\n"
                f"Format: `1 2 3 4 5` (Gunakan spasi)",
                buttons=[Button.inline("❌ Batal", b"cancel_login")]
            )
            
        except errors.PhoneNumberInvalidError:
            await msg.edit("❌ **Nomor HP Tidak Valid.**\nPastikan pakai kode negara (cth: +62...)", buttons=[Button.inline("Ulangi", b"start_auth_process")])
        except errors.FloodWaitError as e:
            await msg.edit(f"❌ **Terkena Limit (FloodWait)**\nTunggu {e.seconds} detik.", buttons=[Button.inline("Batal", b"cancel_login")])
        except Exception as e:
            await msg.edit(f"❌ **Error:** {str(e)}", buttons=[Button.inline("Batal", b"cancel_login")])
            print(f"[AUTH ERROR] Phone Step Exception: {e}")

    # --- LANGKAH 2: TERIMA KODE OTP ---
    elif step == "code":
        # Ambil hanya angka dari input
        otp_code = "".join(filter(str.isdigit, event.text))
        
        if not otp_code:
            await event.reply("⚠️ **Format Salah!** Masukkan angka saja.", buttons=[[Button.inline("Batal", b"cancel_login")]])
            return

        msg = await event.reply("🔄 **Verifikasi Kode...**")
        
        try:
            # DEBUG: Cek isi state sebelum sign_in
            current_state = LOGIN_STATE.get(user_id, {})
            hash_code = current_state.get("phone_code_hash")
            phone_num = current_state.get("phone")
            
            print(f"[AUTH] CODE STEP: Verifikasi User {user_id} | Hash: {hash_code} | Phone: {phone_num} | Code: {otp_code}")

            if not hash_code:
                print(f"[AUTH FATAL] Hash code KOSONG/HILANG untuk user {user_id}!")
                await msg.edit("❌ **Sesi Error:** Data verifikasi hilang dari memori. Silakan Login ulang.", buttons=[[Button.inline("Login Ulang", b"start_auth_process")]])
                del LOGIN_STATE[user_id]
                return

            # EKSEKUSI LOGIN
            await client.sign_in(phone_num, otp_code, phone_code_hash=hash_code)
            
            ACTIVE_USERBOTS[user_id] = client 
            del LOGIN_STATE[user_id]
            
            me = await client.get_me()
            name = me.first_name or "User"
            print(f"[AUTH] LOGIN SUKSES: {name} ({user_id})")
            
            await msg.edit(
                f"🎉 **LOGIN BERHASIL!**\n\n"
                f"Halo, **{name}**! Userbot Anda aktif.",
                buttons=[Button.inline("⚙️ Menu Pengaturan", b"menu_connect_ub")]
            )

        except errors.SessionPasswordNeededError:
            LOGIN_STATE[user_id]["step"] = "password"
            print(f"[AUTH] 2FA REQUIRED: User {user_id}")
            await msg.edit(
                "🔐 **Butuh Password 2FA**\n\n"
                "Akun ini dilindungi verifikasi 2 langkah.\n"
                "👉 **Silakan balas dengan PASSWORD Anda.**",
                buttons=[Button.inline("❌ Batal", b"cancel_login")]
            )
            
        except errors.PhoneCodeInvalidError:
            await msg.edit("❌ **Kode Salah!**", buttons=[[Button.inline("Coba Lagi", b"retry_code")]])
        except errors.PhoneCodeExpiredError:
            await msg.edit("❌ **Kode Kadaluarsa.**", buttons=[[Button.inline("Ulangi", b"start_auth_process")]])
        except Exception as e:
            await msg.edit(f"❌ **Error Login:** {str(e)}", buttons=[[Button.inline("Batal", b"cancel_login")]])
            print(f"[AUTH ERROR] Code Step Exception: {e}")

    # --- LANGKAH 3: TERIMA PASSWORD 2FA ---
    elif step == "password":
        password = event.text.strip()
        msg = await event.reply("🔄 **Verifikasi Password...**")
        
        try:
            await client.sign_in(password=password)
            
            ACTIVE_USERBOTS[user_id] = client
            del LOGIN_STATE[user_id]
            
            me = await client.get_me()
            name = me.first_name or "User"
            print(f"[AUTH] LOGIN 2FA SUKSES: {name} ({user_id})")
            
            await msg.edit(
                f"🎉 **LOGIN BERHASIL (2FA)!**\n\n"
                f"Halo, **{name}**! Userbot Anda aktif.",
                buttons=[Button.inline("⚙️ Menu Pengaturan", b"menu_connect_ub")]
            )
            
        except errors.PasswordHashInvalidError:
            await msg.edit("❌ **Password Salah.**", buttons=[[Button.inline("Batal", b"cancel_login")]])
        except Exception as e:
            await msg.edit(f"❌ **Error 2FA:** {str(e)}", buttons=[[Button.inline("Batal", b"cancel_login")]])