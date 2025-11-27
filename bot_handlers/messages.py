# bmcodexbot/bot_handlers/messages.py
import asyncio, uuid
from datetime import datetime, timedelta
from telethon import events, Button
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    PhoneCodeExpiredError
)

from config import bot, ADMIN_ID, PRICE_PER_MONTH, format_rp
from database import (
    find_member_row, append_member, update_member_status,
    update_member_name_email, update_member_expire, 
    save_session_to_sheet, log_history
)
from state import (
    LOGIN_STATE, ACTIVE_USERBOTS, WAIT_NAME, WAIT_EMAIL,
    WAIT_PAYMENT_PROOF, pending_tx, user_tx_map, awaiting_photo,
    ADMIN_ACTION_STATE
)
from aktif_fitur import start_userbot
from bot_handlers.nav import get_main_menu_data 

# --- NOTE: LIVE CHAT HANDLER SUDAH BERDIRI SENDIRI DI livechat.py ---

async def finalize_login(user_id, client, msg_obj):
    try:
        session_string = client.session.save()
        save_session_to_sheet(user_id, session_string)
        ACTIVE_USERBOTS[user_id] = client
        asyncio.create_task(start_userbot(client, user_id))
        
        try: await msg_obj.delete()
        except: pass

        idx, row = find_member_row(user_id)
        is_member = row and row.get("Status") == "Approved"
        
        menu_text, menu_buttons = get_main_menu_data(is_member)
        final_text = "✅ **Login Berhasil! Userbot Telah Aktif.**\n\n" + menu_text
        
        await bot.send_message(user_id, final_text, buttons=menu_buttons)

        if user_id in LOGIN_STATE: del LOGIN_STATE[user_id]
    except Exception as e:
        await msg_obj.edit(f"❌ Error save session: {e}")

@bot.on(events.NewMessage)
async def global_message_handler(event):
    if event.sender_id == (await bot.get_me()).id: return
    user_id = event.sender_id
    text = (event.raw_text or "").strip()

    # --- CEK LIVE CHAT DI livechat.py (Sudah Auto Handle) ---

    # --- CEK INPUT ADMIN MANUAL ---
    if user_id == ADMIN_ID and ADMIN_ID in ADMIN_ACTION_STATE:
        return 

    # --- LOGIN FLOW ---
    if user_id in LOGIN_STATE:
        state = LOGIN_STATE[user_id]
        client = state["client"]
        try:
            if state["step"] == "phone":
                phone = text.replace(" ", "")
                msg = await event.reply("🔄 Mengirim OTP...")
                try:
                    ph = await client.send_code_request(phone)
                    state.update({"phone_hash": ph, "phone": phone, "step": "code"})
                    # TAMBAHAN: Tombol Batal saat menunggu kode
                    await msg.edit(
                        "📩 **Kode OTP Terkirim!**\n\nSilakan masukkan Kode OTP dari Telegram (pisahkan dengan spasi, cth: `1 2 3 4 5`).",
                        buttons=[[Button.inline("❌ Batal Login", b"cancel_login")]]
                    )
                except Exception as e: 
                    await msg.edit(
                        f"❌ **Gagal Kirim OTP:**\n`{e}`\n\nPastikan nomor benar dan diawali kode negara (misal +62).",
                        buttons=[[Button.inline("🔄 Coba Lagi", b"start_auth_process")]]
                    )
                
            elif state["step"] == "code":
                code = text.replace(" ", "")
                msg = await event.reply("🔄 Verifikasi Kode...")
                try:
                    await client.sign_in(state["phone"], code, phone_code_hash=state["phone_hash"].phone_code_hash)
                    await finalize_login(user_id, client, msg)
                except SessionPasswordNeededError:
                    state["step"] = "password"
                    await msg.edit("🔐 **Verifikasi 2 Langkah (2FA)**\n\nAkun ini dilindungi password cloud. Silakan masukkan password Anda.", buttons=[[Button.inline("❌ Batal", b"cancel_login")]])
                except (PhoneCodeInvalidError, PhoneCodeExpiredError):
                    # TAMBAHAN: Tombol Input Ulang atau Ganti Nomor
                    await msg.edit(
                        "❌ **Kode OTP Salah atau Kadaluarsa!**\n\nSilakan cek kembali kode Anda.",
                        buttons=[
                            [Button.inline("🔄 Masukkan Ulang Kode", b"retry_code")],
                            [Button.inline("📱 Ganti Nomor / Mulai Awal", b"start_auth_process")]
                        ]
                    )
                except Exception as e: 
                    await msg.edit(f"❌ Error tidak diketahui: {e}", buttons=[[Button.inline("🔄 Coba Lagi", b"retry_code")]])
                
            elif state["step"] == "password":
                msg = await event.reply("🔄 Verifikasi Password...")
                try:
                    await client.sign_in(password=text)
                    await finalize_login(user_id, client, msg)
                except Exception as e: 
                    await msg.edit(
                        f"❌ **Password Salah:**\n`{e}`\n\nSilakan coba lagi.",
                        buttons=[[Button.inline("❌ Batal", b"cancel_login")]]
                    )
        except Exception as e:
            await event.reply(f"Fatal Error: {e}")
            if user_id in LOGIN_STATE: del LOGIN_STATE[user_id]
        return

    # --- REGISTRATION & PAYMENT FLOW ---
    if user_id in WAIT_NAME:
        data = WAIT_NAME.pop(user_id)
        WAIT_EMAIL[user_id] = {"name": text, "months": data["months"], "total": data["total"], "is_trial": data.get("is_trial", False)}
        await event.reply("📨 Sekarang kirim *Email* Anda.")
        return

    if user_id in WAIT_EMAIL:
        if "@" not in text: return await event.reply("❌ Email tidak valid. Coba lagi.")
        data = WAIT_EMAIL.pop(user_id)
        
        if data.get("is_trial"):
            expire_date = (datetime.now() + timedelta(days=3)).strftime("%d-%m-%Y")
            append_member(user_id, data["name"], text, 1)
            idx_new, _ = find_member_row(user_id)
            update_member_expire(idx_new, expire_date)
            update_member_status(idx_new, "Approved")
            log_history(user_id, 0, 0, "Approved (Trial)")
            await event.reply(f"✅ **Aktivasi Free Trial Berhasil!**\nExpired: **{expire_date}**\nSilakan hubungkan Userbot.", buttons=[[Button.inline("⚙️ Hubungkan Userbot", b"menu_connect_ub")]])
            await bot.send_message(ADMIN_ID, f"🎁 **New Free Trial User**\nID: `{user_id}`\nNama: {data['name']}")
            return
        else:
            WAIT_PAYMENT_PROOF[user_id] = {"name": data["name"], "email": text, "months": data["months"], "total": data["total"]}
            tmp = f"tmp_{user_id}"
            pending_tx[tmp] = {"user_id": user_id, "months": data["months"], "total": data["total"], "timestamp": datetime.now().isoformat(), "is_trial": False}
            user_tx_map[user_id] = tmp
            awaiting_photo.add(user_id)
            await event.reply(f"✅ Data tersimpan. Total: {format_rp(data['total'])}. Silakan upload bukti transfer.")
            try: await bot.send_file(user_id, "qris.jpg")
            except: pass
            return

    if event.photo and user_id in awaiting_photo:
        tx_id = user_tx_map.get(user_id) or str(uuid.uuid4())
        if tx_id not in pending_tx: 
             data = WAIT_PAYMENT_PROOF.get(user_id, {})
             pending_tx[tx_id] = {
                 "user_id": user_id, 
                 "months": data.get("months", 1), 
                 "total": data.get("total", PRICE_PER_MONTH)
             }

        info = WAIT_PAYMENT_PROOF.pop(user_id, {})
        name = info.get("name") or pending_tx[tx_id].get("name") or "-"
        email = info.get("email") or pending_tx[tx_id].get("email") or "-"
        pending_tx[tx_id]["name"] = name
        pending_tx[tx_id]["email"] = email

        idx, row = find_member_row(user_id)
        if idx:
            if name != "-": update_member_name_email(idx, name, email)
            update_member_status(idx, "Pending")
        else:
            append_member(user_id, name, email, 1)
            idx_new, _ = find_member_row(user_id)
            update_member_status(idx_new, "Pending")

        await bot.send_message(
            ADMIN_ID, 
            f"📩 **Bukti Transfer Baru**\nUser: `{user_id}`\nNama: {name}\nTotal: {format_rp(pending_tx[tx_id]['total'])}",
            file=event.media, 
            buttons=[[Button.inline("✔ Approve", f"PAYAPPROVE:{tx_id}"), Button.inline("❌ Reject", f"PAYREJECT:{tx_id}")]]
        )
        
        awaiting_photo.discard(user_id)
        await event.reply("✅ Bukti terkirim. Tunggu konfirmasi admin.")