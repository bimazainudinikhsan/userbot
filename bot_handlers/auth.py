# bmcodexbot/bot_handlers/auth.py
import time
from telethon import events, Button, TelegramClient, errors
from telethon.sessions import StringSession
from config import bot, API_ID, API_HASH
from database import find_member_row, log_history
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
        pass # Ignore message not modified

# ==========================================
# 2. PROSES LOGIN (TOMBOL)
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"start_auth_process"))
async def cb_start_auth(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    
    if not row: return await event.answer("❌ Belum terdaftar.", alert=True)
    if row.get("Status") != "Approved": return await event.answer("❌ Akun tidak aktif.", alert=True)
    
    # Putuskan koneksi lama jika ada
    if user_id in ACTIVE_USERBOTS:
        try:
            await ACTIVE_USERBOTS[user_id].disconnect()
        except: pass
        if user_id in ACTIVE_USERBOTS: del ACTIVE_USERBOTS[user_id]

    # Inisialisasi Client Baru untuk Login
    new_client = TelegramClient(StringSession(), API_ID, API_HASH)
    await new_client.connect()
    
    LOGIN_STATE[user_id] = {
        "step": "phone", 
        "client": new_client,
        "phone": None,
        "phone_code_hash": None # Inisialisasi key ini dengan None
    }
    
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
    
    await cb_connect_ub_menu(event)

# ==========================================
# 3. HANDLER INPUT TEKS (PENTING!)
# ==========================================
@bot.on(events.NewMessage(incoming=True))
async def auth_input_handler(event):
    user_id = event.sender_id
    
    # Cek apakah user sedang dalam proses login
    if user_id not in LOGIN_STATE:
        return # Abaikan jika tidak sedang login

    if event.text.startswith("/"): return # Abaikan command

    state = LOGIN_STATE[user_id]
    step = state.get("step")
    client = state.get("client")

    if not client:
        return # Should not happen

    # --- LANGKAH 1: TERIMA NOMOR HP ---
    if step == "phone":
        # Bersihkan nomor HP dari spasi dan dash
        phone_number = event.text.strip().replace(" ", "").replace("-", "")
        
        msg = await event.reply("🔄 **Memproses nomor...**\nMohon tunggu sebentar.")
        
        try:
            # Request Kode OTP ke Telegram
            send_code = await client.send_code_request(phone_number)
            
            # PENTING: Simpan hash yang benar dengan nama key "phone_code_hash"
            state["phone"] = phone_number
            state["phone_code_hash"] = send_code.phone_code_hash 
            state["step"] = "code" # Pindah ke langkah berikutnya
            
            await msg.edit(
                f"✅ **Kode Terkirim!**\n\n"
                f"Kode OTP telah dikirim ke akun Telegram nomor `{phone_number}`.\n\n"
                f"👉 **Silakan balas pesan ini dengan KODE OTP tersebut.**\n"
                f"Format: `1 2 3 4 5` (Gunakan spasi)",
                buttons=[Button.inline("❌ Batal", b"cancel_login")]
            )
            
        except errors.PhoneNumberInvalidError:
            await msg.edit("❌ **Nomor HP Tidak Valid.**\nPastikan pakai kode negara (cth: +62...)", buttons=[Button.inline("Ulangi", b"start_auth_process")])
            if user_id in LOGIN_STATE: del LOGIN_STATE[user_id]
        except errors.FloodWaitError as e:
            await msg.edit(f"❌ **Terkena Limit (FloodWait)**\nTunggu {e.seconds} detik sebelum mencoba lagi.", buttons=[Button.inline("Batal", b"cancel_login")])
            if user_id in LOGIN_STATE: del LOGIN_STATE[user_id]
        except Exception as e:
            await msg.edit(f"❌ **Error:** {str(e)}", buttons=[Button.inline("Batal", b"cancel_login")])
            print(f"Auth Error (Phone): {e}")
            if user_id in LOGIN_STATE: del LOGIN_STATE[user_id]

    # --- LANGKAH 2: TERIMA KODE OTP ---
    elif step == "code":
        # Hapus spasi dan strip jika user mengetik "1 2 3 4 5" atau "1-2-3-4-5"
        otp_code = event.text.replace(" ", "").replace("-", "").strip()
        
        # Validasi sederhana input kode
        if not otp_code.isdigit():
            await event.reply("⚠️ **Format Kode Salah!**\nHarap masukkan hanya angka kode OTP.", buttons=[[Button.inline("Batal", b"cancel_login")]])
            return

        msg = await event.reply("🔄 **Verifikasi Kode...**")
        
        try:
            # PENTING: Ambil hash dengan key yang sama persis "phone_code_hash"
            # Menggunakan .get() untuk menghindari KeyError jika key tidak ada
            hash_code = state.get("phone_code_hash")
            
            # Pastikan hash tersedia
            if not hash_code:
                await msg.edit("❌ **Sesi Error:** Phone Hash hilang. Login ulang.", buttons=[[Button.inline("Login Ulang", b"start_auth_process")]])
                del LOGIN_STATE[user_id]
                return

            # Gunakan parameter yang benar: phone_code_hash
            await client.sign_in(state["phone"], otp_code, phone_code_hash=hash_code)
            
            # Jika sukses login
            # Simpan object client ke memori ACTIVE_USERBOTS
            ACTIVE_USERBOTS[user_id] = client 
            
            # Hapus state login
            del LOGIN_STATE[user_id]
            
            me = await client.get_me()
            name = me.first_name or "User"
            
            await msg.edit(
                f"🎉 **LOGIN BERHASIL!**\n\n"
                f"Halo, **{name}**! Userbot Anda aktif.\n"
                "Ketik `.alive` di Saved Messages untuk tes.",
                buttons=[Button.inline("⚙️ Menu Pengaturan", b"menu_connect_ub")]
            )

        except errors.SessionPasswordNeededError:
            # Jika user pakai 2FA (Verifikasi 2 Langkah)
            state["step"] = "password"
            await msg.edit(
                "🔐 **Butuh Password 2FA**\n\n"
                "Akun ini dilindungi verifikasi 2 langkah.\n"
                "👉 **Silakan balas dengan PASSWORD Anda.**",
                buttons=[Button.inline("❌ Batal", b"cancel_login")]
            )
            
        except errors.PhoneCodeInvalidError:
            await msg.edit("❌ **Kode Salah!**\nSilakan coba lagi.", buttons=[[Button.inline("Coba Lagi", b"retry_code")]])
        except errors.PhoneCodeExpiredError:
            await msg.edit("❌ **Kode Kadaluarsa.**\nMulai ulang login.", buttons=[[Button.inline("Ulangi", b"start_auth_process")]])
            if user_id in LOGIN_STATE: del LOGIN_STATE[user_id]
        except Exception as e:
            await msg.edit(f"❌ **Error Login:** {str(e)}", buttons=[[Button.inline("Batal", b"cancel_login")]])
            print(f"Auth Error (Code): {e}")

    # --- LANGKAH 3: TERIMA PASSWORD 2FA (JIKA ADA) ---
    elif step == "password":
        password = event.text.strip()
        msg = await event.reply("🔄 **Verifikasi Password...**")
        
        try:
            await client.sign_in(password=password)
            
            # Login Sukses
            ACTIVE_USERBOTS[user_id] = client
            del LOGIN_STATE[user_id]
            
            me = await client.get_me()
            name = me.first_name or "User"
            
            await msg.edit(
                f"🎉 **LOGIN BERHASIL (2FA)!**\n\n"
                f"Halo, **{name}**! Userbot Anda aktif.",
                buttons=[Button.inline("⚙️ Menu Pengaturan", b"menu_connect_ub")]
            )
            
        except errors.PasswordHashInvalidError:
            await msg.edit("❌ **Password Salah.**\nSilakan coba lagi.", buttons=[[Button.inline("Batal", b"cancel_login")]])
        except Exception as e:
            await msg.edit(f"❌ **Error 2FA:** {str(e)}", buttons=[[Button.inline("Batal", b"cancel_login")]])