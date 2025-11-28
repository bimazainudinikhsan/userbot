# bmcodexbot/bot_handlers/messages.py
import asyncio
from telethon import events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError, FloodWaitError

from config import bot
from state import LOGIN_STATE, ACTIVE_USERBOTS
from database import save_session_to_sheet, update_member_status, find_member_row
from aktif_fitur import start_userbot

# --- PERUBAHAN: Import dari file baru ---
from modules import auto_spam

def convert_to_string_session(client):
    try:
        string_sess = StringSession()
        string_sess.set_dc(client.session.dc_id, client.session.server_address, client.session.port)
        string_sess.auth_key = client.session.auth_key
        return string_sess.save()
    except: return None

@bot.on(events.NewMessage(incoming=True))
async def handle_incoming_message(event):
    if not event.is_private or event.sender_id == (await bot.get_me()).id: return

    user_id = event.sender_id
    text = event.message.text.strip()
    
    if user_id in LOGIN_STATE:
        state_data = LOGIN_STATE[user_id]
        step = state_data.get("step")
        client = state_data.get("client")
        phone = state_data.get("phone")
        phone_code_hash = state_data.get("phone_code_hash")

        if step == "phone":
            # Membersihkan input nomor HP dari spasi, dash, kurung
            clean_phone = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            
            # Normalisasi format nomor (08 -> 628, 8 -> 628)
            if clean_phone.startswith("08"): clean_phone = "62" + clean_phone[1:]
            elif clean_phone.startswith("8"): clean_phone = "62" + clean_phone
            
            # Tambahkan + jika belum ada
            if not clean_phone.startswith("+"): clean_phone = "+" + clean_phone

            # Validasi akhir: harus digit dan panjang minimal
            if not clean_phone[1:].isdigit() or len(clean_phone) < 10:
                return await event.reply("⚠️ Format Salah. Contoh: `08123456789`")

            try:
                msg = await event.reply(f"🔄 Memproses `{clean_phone}`...")
                sent = await client.send_code_request(clean_phone)
                
                # Simpan state
                LOGIN_STATE[user_id]["phone"] = clean_phone
                LOGIN_STATE[user_id]["phone_code_hash"] = sent.phone_code_hash
                LOGIN_STATE[user_id]["step"] = "code"
                
                await msg.edit(
                    f"📩 **Kode Terkirim ke {clean_phone}**\n\n"
                    "Silakan masukkan kode OTP yang Anda terima dari Telegram.\n"
                    "Contoh: `1 2 3 4 5`", 
                    buttons=[[Button.inline("❌ Batal", b"cancel_login")]]
                )
            except Exception as e:
                await event.reply(f"❌ Gagal kirim kode: {e}")
            return

        elif step == "code":
            # PENTING: Hapus semua spasi dari input user (misal "1 2 3 4 5" jadi "12345")
            code = text.replace(" ", "")
            
            if not code.isdigit():
                 return await event.reply("⚠️ Kode harus berupa angka. Silakan cek lagi.")

            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                await process_login_success(user_id, client, event)
            except SessionPasswordNeededError:
                LOGIN_STATE[user_id]["step"] = "password"
                await event.reply("🔐 Akun dilindungi **Verifikasi 2 Langkah (2FA)**.\nSilakan masukkan Password Anda:")
            except PhoneCodeInvalidError:
                await event.reply("❌ Kode Salah/Kadaluarsa.", buttons=[[Button.inline("🔄 Kirim Ulang", b"retry_code")]])
            except Exception as e:
                await event.reply(f"❌ Error Login: {e}")
            return

        elif step == "password":
            try:
                # Password biasanya tidak boleh di-strip spasinya sembarangan jika passwordnya mengandung spasi
                # Tapi .strip() di awal sudah cukup
                await client.sign_in(password=text)
                await process_login_success(user_id, client, event)
            except Exception as e:
                await event.reply(f"❌ Password Salah: {e}")
            return

async def process_login_success(user_id, client, event):
    msg = await event.reply("✅ **Login Berhasil!** Sedang menyimpan sesi...")
    try:
        # Simpan sesi string ke Sheet (Backup)
        session_string = convert_to_string_session(client)
        if session_string: save_session_to_sheet(user_id, session_string)

        # Update Active Userbots
        if user_id in ACTIVE_USERBOTS:
            try: await ACTIVE_USERBOTS[user_id].disconnect()
            except: pass
        ACTIVE_USERBOTS[user_id] = client
        
        # Update Status Member di Database
        idx, row = find_member_row(user_id)
        if row and row.get("Status") != "Approved":
            update_member_status(idx, "Approved", "Login Success")

        # Hapus state login
        if user_id in LOGIN_STATE: del LOGIN_STATE[user_id]
        
        # Jalankan fitur userbot
        asyncio.create_task(start_userbot(client, user_id))
        
        # Resume Auto Spam jika ada task tertunda
        await auto_spam.resume_spam_tasks(client)

        await msg.edit(
            "🚀 **Userbot Telah Aktif!**\n\n"
            "Sekarang Anda bisa menggunakan semua fitur Premium.",
            buttons=[[Button.inline("⬅️ Menu Utama", b"menu_start")]]
        )
    except Exception as e:
        await msg.edit(f"⚠️ Login sukses tapi gagal setup bot: {e}")