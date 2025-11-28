# bmcodexbot/bot_handlers/auth.py
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
    
    if client:
        if client.is_connected():
            try:
                me = await client.get_me()
                ub_status = f"🟢 Online ({me.first_name})"
            except:
                ub_status = "⚠️ Connected (No Auth)"
        else:
            ub_status = "⚠️ Disconnected"
            
    text = (
        f"⚙️ **SETTING & KONEKSI**\n\n"
        f"📡 **Status:** {ub_status}\n"
        f"🤖 **Auto Reply:** {ar_status}\n\n"
        f"👇 Pilih tindakan:"
    )
    
    buttons = [
        [Button.inline("🔌 Login / Ganti Akun", b"start_auth_process")],
        [Button.inline("🔄 Cek Koneksi", b"menu_connect_ub")],
        [Button.inline("⬅️ Menu Utama", b"menu_start")]
    ]
    
    await event.edit(text, buttons=buttons)

# ==========================================
# 2. PROSES LOGIN (INIT)
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"start_auth_process"))
async def cb_start_auth(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    
    if not row: return await event.answer("❌ Belum terdaftar.", alert=True)
    if row.get("Status") != "Approved": return await event.answer("❌ Akun tidak aktif.", alert=True)
    
    # Bersihkan sesi lama dengan aman
    if user_id in ACTIVE_USERBOTS:
        try: await ACTIVE_USERBOTS[user_id].disconnect()
        except: pass
        del ACTIVE_USERBOTS[user_id]
        
    if user_id in LOGIN_STATE:
        try: await LOGIN_STATE[user_id]["client"].disconnect()
        except: pass
        del LOGIN_STATE[user_id]

    msg = await event.edit("🔄 **Mempersiapkan Client...**")

    # Inisialisasi Client Baru
    try:
        new_client = TelegramClient(StringSession(), API_ID, API_HASH)
        await new_client.connect()
        
        if not await new_client.connect():
            return await msg.edit("❌ **Gagal Connect ke Server Telegram.** Coba lagi nanti.")
            
    except Exception as e:
        return await msg.edit(f"❌ **Error Init:** `{str(e)}`")
    
    # Simpan State
    LOGIN_STATE[user_id] = {
        "step": "phone", 
        "client": new_client,
        "phone": None,
        "phone_code_hash": None 
    }
    
    print(f"[AUTH] INIT: Client dibuat untuk user {user_id}. Connected: {new_client.is_connected()}")
    
    await msg.edit(
        "📱 **LOGIN USERBOT**\n\n"
        "Silakan kirim **Nomor HP** Anda.\n"
        "Format: `+628xx` (Gunakan Kode Negara)", 
        buttons=[Button.inline("❌ Batal", b"cancel_login")]
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
# 3. HANDLER INPUT (PHONE & CODE)
# ==========================================
@bot.on(events.NewMessage(incoming=True))
async def auth_input_handler(event):
    user_id = event.sender_id
    if user_id not in LOGIN_STATE: return 
    if event.text.startswith("/"): return 

    state = LOGIN_STATE[user_id]
    step = state.get("step")
    client = state.get("client")

    # --- PENCEGAHAN DISCONNECT ---
    if not client or not client.is_connected():
        print(f"[AUTH WARNING] Client user {user_id} terputus. Mencoba reconnect...")
        try:
            await client.connect()
        except:
            await event.reply("❌ **Koneksi Hilang.** Silakan tekan 'Login / Ganti Akun' lagi.")
            del LOGIN_STATE[user_id]
            return

    # ---------------------------
    # LANGKAH 1: INPUT NOMOR HP
    # ---------------------------
    if step == "phone":
        phone_number = event.text.strip().replace(" ", "")
        
        msg = await event.reply("🔄 **Meminta Kode OTP...** (Jangan spam)")
        
        try:
            # Request Code
            send_code = await client.send_code_request(phone_number)
            
            # AMBIL HASH DENGAN PASTI
            the_hash = str(send_code.phone_code_hash) # Convert ke string agar aman
            
            LOGIN_STATE[user_id]["phone"] = phone_number
            LOGIN_STATE[user_id]["phone_code_hash"] = the_hash
            LOGIN_STATE[user_id]["step"] = "code"
            
            print(f"[AUTH] SUKSES KIRIM KODE: {phone_number} | Hash: {the_hash}")
            
            await msg.edit(
                f"✅ **Kode Terkirim ke Telegram!**\n\n"
                f"Nomor: `{phone_number}`\n"
                f"Hash: `{the_hash[:10]}...`\n\n"
                f"👉 **Balas dengan angka KODE OTP.**\n"
                f"Contoh: `1 2 3 4 5` (Pakai spasi)",
                buttons=[Button.inline("❌ Batal", b"cancel_login")]
            )
            
        except errors.FloodWaitError as e:
            await msg.edit(f"❌ **Limit Telegram:** Tunggu {e.seconds} detik.")
        except Exception as e:
            print(f"[AUTH ERROR] Phone Step: {e}")
            await msg.edit(f"❌ **Error:** `{str(e)}`", buttons=[Button.inline("Batal", b"cancel_login")])

    # ---------------------------
    # LANGKAH 2: INPUT KODE OTP
    # ---------------------------
    elif step == "code":
        otp_code = "".join(filter(str.isdigit, event.text))
        if not otp_code: return await event.reply("⚠️ Masukkan angka saja.")

        msg = await event.reply("🔄 **Sedang Login...**")
        
        try:
            phone = state["phone"]
            phone_hash = state["phone_code_hash"]
            
            # Cek Hash sebelum login
            if not phone_hash:
                return await msg.edit("❌ **Sesi Invalid (Hash Hilang).** Ulangi Login.", buttons=[Button.inline("Ulangi", b"start_auth_process")])

            # LOGIN EKSEKUSI
            await client.sign_in(phone, otp_code, phone_code_hash=phone_hash)
            
            # Simpan Sesi
            ACTIVE_USERBOTS[user_id] = client
            del LOGIN_STATE[user_id]
            
            user = await client.get_me()
            await msg.edit(f"✅ **Login Berhasil!**\nSelamat datang, {user.first_name}", buttons=[Button.inline("Menu", b"menu_connect_ub")])

        except errors.SessionPasswordNeededError:
            LOGIN_STATE[user_id]["step"] = "password"
            await msg.edit("🔐 **Masukkan Password 2FA Anda:**", buttons=[Button.inline("Batal", b"cancel_login")])
            
        except (errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError):
            await msg.edit("❌ **Kode Salah / Kadaluarsa.**", buttons=[Button.inline("Batal", b"cancel_login")])
            
        except Exception as e:
            print(f"[AUTH ERROR] Login Step: {e}")
            await msg.edit(f"❌ **Gagal Login:** `{str(e)}`\n\nTips: Coba matikan bot lalu jalankan lagi.", buttons=[Button.inline("Batal", b"cancel_login")])

    # ---------------------------
    # LANGKAH 3: PASSWORD 2FA
    # ---------------------------
    elif step == "password":
        pwd = event.text.strip()
        msg = await event.reply("🔄 **Verifikasi Password...**")
        try:
            await client.sign_in(password=pwd)
            ACTIVE_USERBOTS[user_id] = client
            del LOGIN_STATE[user_id]
            await msg.edit("✅ **Login 2FA Berhasil!**", buttons=[Button.inline("Menu", b"menu_connect_ub")])
        except Exception as e:
            await msg.edit(f"❌ **Password Salah:** `{str(e)}`", buttons=[Button.inline("Batal", b"cancel_login")])