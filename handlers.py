# handlers.py
import asyncio
import uuid
import os
import sys
import json
from datetime import datetime, timedelta
from telethon import events, Button, TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# Import Module Lokal
from config import bot, API_ID, API_HASH, ADMIN_ID, PRICE_PER_MONTH, format_rp
from bot_handlers.admin.system import read_manager_control, write_manager_control
from database import (
    find_member_row, append_member, update_member_expire, 
    update_member_name_email, save_session_to_sheet, log_history,
    get_all_members_safe, update_member_status, update_member_permissions, get_member_permissions
)
from state import (
    LOGIN_STATE, ACTIVE_USERBOTS, pending_tx, user_tx_map, 
    awaiting_photo, WAIT_NAME, WAIT_EMAIL, WAIT_PAYMENT_PROOF,
    GLOBAL_CONFIG, USER_PERMISSIONS, EDIT_PERMISSION_STATE, awaiting_reject_comment
)
from aktif_fitur import start_userbot

# Fitur yang bisa diatur ON/OFF oleh admin
ALL_FEATURES_LIST = ["ping", "alive", "id", "botpesan", "spam", "autoreply", "setreply", "faktur"]

# ==========================================
# 1. MENU UTAMA & DASHBOARD
# ==========================================

@bot.on(events.NewMessage(pattern="/start"))
async def handler_start(event):
    # Jika Admin, tampilkan Dashboard
    if event.sender_id == ADMIN_ID:
        await show_admin_dashboard(event)
    else:
        # Jika User Biasa
        await event.respond(
            "👋 **Selamat datang di Bot Manager!**\nPilih menu:",
            buttons=[
                [Button.inline("🔐 Aktivasi/Perpanjang Membership", b"menu_buy")],
                [Button.inline("⚙️ Hubungkan Userbot", b"menu_connect_ub")],
                [Button.inline("📊 Cek Status", b"menu_status")]
            ]
        )

@bot.on(events.CallbackQuery(pattern=b"menu_start")) # Tombol Back
async def cb_back_main(event):
    if event.sender_id == ADMIN_ID:
        await show_admin_dashboard(event)
    else:
        await event.edit(
            "👋 **Menu Utama**",
            buttons=[
                [Button.inline("🔐 Aktivasi/Perpanjang", b"menu_buy")],
                [Button.inline("⚙️ Hubungkan Userbot", b"menu_connect_ub")],
                [Button.inline("📊 Cek Status", b"menu_status")]
            ]
        )

@bot.on(events.CallbackQuery(pattern=b"menu_admin_dashboard"))
async def cb_open_admin_dashboard(event):
    await show_admin_dashboard(event)

# ==========================================
# 2. ADMIN DASHBOARD & LOGIC
# ==========================================

async def show_admin_dashboard(event):
    try:
        if event.sender_id != ADMIN_ID:
            try:
                await event.answer("❌ Akses ditolak: bukan admin", alert=True)
            except:
                pass
            try:
                with open("session_usage.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": datetime.now().isoformat(), "kind": "admin_dashboard_unauthorized", "by": event.sender_id}) + "\n")
            except:
                pass
            return
    except:
        pass
    is_trial_on = GLOBAL_CONFIG.get("free_trial", False)
    status_trial = "✅ ON" if is_trial_on else "❌ OFF"
    sys_status = read_manager_control().get("system_status", "normal")
    sys_label = "🟢 Normal" if sys_status == "normal" else "🟡 Maintenance"
    
    text = (
        "👑 **ADMIN DASHBOARD**\n"
        "Selamat datang, Admin! Silakan pilih menu manajemen di bawah ini:"
    )
    buttons = [
        [Button.inline(f"🆓 Mode Free Trial: {status_trial}", b"TOGGLE_TRIAL")],
        [Button.inline(f"🧰 Status Sistem: {sys_label}", b"cmd_admin_sys_status")],
        [Button.inline("🛠 Atur Fitur Member", b"cmd_admin_fitur")],
        [Button.inline("📊 Cek Status Semua User", b"cmd_admin_status")],
        [Button.inline("ℹ️ Bantuan & Perintah", b"cmd_admin_help")],
        [Button.inline("🔄 Restart System", b"cmd_admin_restart"), Button.inline("🔴 Shutdown", b"cmd_admin_shutdown")]
    ]
    
    try:
        if isinstance(event, events.CallbackQuery.Event):
            await event.edit(text, buttons=buttons)
        else:
            await event.respond(text, buttons=buttons)
        try:
            with open("session_usage.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.now().isoformat(), "kind": "admin_dashboard_open", "by": event.sender_id}) + "\n")
        except:
            pass
    except Exception as e:
        try:
            with open("session_usage.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.now().isoformat(), "kind": "admin_dashboard_error", "error": str(e)}) + "\n")
        except:
            pass

# --- Toggle Trial ---
@bot.on(events.CallbackQuery(pattern=b"TOGGLE_TRIAL"))
async def cb_toggle_trial(event):
    if event.sender_id != ADMIN_ID: return
    GLOBAL_CONFIG["free_trial"] = not GLOBAL_CONFIG.get("free_trial", False)
    await show_admin_dashboard(event)

# --- Admin Approve/Reject Payment ---
@bot.on(events.CallbackQuery(pattern=r"(PAYAPPROVE|PAYREJECT):(.+)"))
async def cb_admin_pay(event):
    if event.sender_id != ADMIN_ID: return
    data_str = event.data.decode()
    action, tx_id = data_str.split(':')
    
    tx = pending_tx.get(tx_id)
    if not tx: return await event.edit("❌ Transaksi kadaluarsa.")
    user_id = tx["user_id"]

    if action == "PAYAPPROVE":
        idx, row = find_member_row(user_id)
        if idx:
            try: exp = datetime.strptime(row.get("Expired"), "%d-%m-%Y")
            except: exp = datetime.now()
            new_exp = (max(datetime.now(), exp) + timedelta(days=30 * tx["months"])).strftime("%d-%m-%Y")
            update_member_expire(idx, new_exp)
            update_member_status(idx, "Approved")
            if tx.get("name"): update_member_name_email(idx, tx["name"], tx["email"])
        else:
            new_exp = append_member(user_id, tx.get("name"), tx.get("email"), tx["months"])
            
        log_history(user_id, tx["months"], tx["total"], "Approved")
        await bot.send_message(user_id, f"🎉 **PEMBAYARAN DITERIMA!**\n\nStatus: **Approved**\nExpired: **{new_exp}**\n\nSilakan klik /start lalu pilih **⚙️ Hubungkan Userbot**.")
        await event.edit(f"✅ **APPROVED**\nUser: `{user_id}`")
        pending_tx.pop(tx_id, None)

    elif action == "PAYREJECT":
        awaiting_reject_comment[ADMIN_ID] = tx_id
        await event.edit("💬 **REJECT**\nSilakan kirim pesan teks berisi alasan penolakan.")

@bot.on(events.NewMessage(from_users=ADMIN_ID))
async def admin_reject_reason(event):
    if ADMIN_ID in awaiting_reject_comment and not event.text.startswith('/'):
        tx_id = awaiting_reject_comment.pop(ADMIN_ID)
        tx = pending_tx.pop(tx_id, {})
        if tx:
            uid = tx["user_id"]
            idx, _ = find_member_row(uid)
            if idx: update_member_status(idx, "Rejected", event.text)
            await bot.send_message(uid, f"❌ **Pembayaran Ditolak**\nAlasan: {event.text}")
            await event.reply(f"✅ Transaksi user `{uid}` telah ditolak.")

# --- Admin Manage Fitur ---
@bot.on(events.CallbackQuery(pattern=b"cmd_admin_fitur"))
async def admin_fitur_menu(event):
    if event.sender_id != ADMIN_ID: return
    records = get_all_members_safe()
    buttons = []
    for row in records:
        if row.get("Status") == "Approved":
            buttons.append([Button.inline(f"{row.get('Nama')} ({row.get('User ID')})", f"EDIT_FITUR:{row.get('User ID')}")])
    
    if not buttons: return await event.answer("❌ Tidak ada member aktif.", alert=True)
    buttons.append([Button.inline("⬅️ Kembali", b"menu_start")])
    await event.edit("🛠 **MANAJEMEN FITUR**\nPilih member:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"EDIT_FITUR:(.+)"))
async def cb_edit_fitur(event):
    if event.sender_id != ADMIN_ID: return
    target = int(event.data.decode().split(":")[1])
    perms = get_member_permissions(target)
    perm_dict = {f: (True if "ALL" in perms or f in perms else False) for f in ALL_FEATURES_LIST}
    
    if ADMIN_ID not in EDIT_PERMISSION_STATE: EDIT_PERMISSION_STATE[ADMIN_ID] = {}
    EDIT_PERMISSION_STATE[ADMIN_ID][target] = perm_dict
    await show_checklist(event, target)

async def show_checklist(event, target):
    p = EDIT_PERMISSION_STATE[ADMIN_ID][target]
    btns = []
    row = []
    for f in ALL_FEATURES_LIST:
        mark = "✅" if p[f] else "❌"
        row.append(Button.inline(f"{mark} {f}", f"TOGGLE_F:{target}:{f}"))
        if len(row)==2: btns.append(row); row=[]
    if row: btns.append(row)
    btns.append([Button.inline("💾 SIMPAN", f"SAVE_FITUR:{target}")])
    btns.append([Button.inline("🔙 Batal", b"cmd_admin_fitur")])
    await event.edit(f"🛠 **Edit Izin User:** `{target}`", buttons=btns)

@bot.on(events.CallbackQuery(pattern=r"TOGGLE_F:(.+):(.+)"))
async def cb_toggle(event):
    d = event.data.decode().split(":")
    t, f = int(d[1]), d[2]
    EDIT_PERMISSION_STATE[ADMIN_ID][t][f] = not EDIT_PERMISSION_STATE[ADMIN_ID][t][f]
    await show_checklist(event, t)

@bot.on(events.CallbackQuery(pattern=r"SAVE_FITUR:(.+)"))
async def cb_save(event):
    t = int(event.data.decode().split(":")[1])
    pd = EDIT_PERMISSION_STATE[ADMIN_ID].pop(t, {})
    # Jika semua True -> ALL, jika tidak ambil yang True saja
    if all(pd.values()): final = ["ALL"]
    else: final = [k for k,v in pd.items() if v]
    
    update_member_permissions(t, final)
    USER_PERMISSIONS[t] = final
    await event.edit(f"✅ **Saved!**\nUser: `{t}`", buttons=[[Button.inline("⬅️ Kembali", b"cmd_admin_fitur")]])

# --- Admin Status & Help ---
@bot.on(events.CallbackQuery(pattern=b"cmd_admin_status"))
async def cb_admin_status_btn(event):
    if event.sender_id != ADMIN_ID: return
    records = get_all_members_safe()
    output = ["**📊 STATUS SEMUA MEMBER**"]
    online_count = 0
    for row in records:
        uid = str(row.get("User ID"))
        status = row.get("Status", "N/A")
        exp = row.get("Expired", "N/A")
        is_online = int(uid) in ACTIVE_USERBOTS if uid.isdigit() else False
        if is_online: online_count += 1
        koneksi = "🟢 On" if is_online else "🔴 Off"
        output.append(f"• `{uid}` | {status} | {koneksi} | Exp: {exp}")
    
    full_text = f"Total Online: {online_count}\n\n" + "\n".join(output)
    if len(full_text) > 4000: full_text = full_text[:4000] + "..."
    await event.edit(full_text, buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]])

@bot.on(events.CallbackQuery(pattern=b"cmd_admin_sys_status"))
async def cb_admin_sys_status(event):
    if event.sender_id != ADMIN_ID: return
    mc = read_manager_control()
    status = mc.get("system_status", "normal")
    started = mc.get("restart_started_at") or mc.get("shutdown_started_at")
    last = mc.get("last_restart") or {}
    text = "🧰 Status Sistem\n\n"
    text += f"Status: {'🟢 Normal' if status=='normal' else '🟡 Maintenance'}\n"
    if started:
        text += f"Mulai: {started}\n"
    if last:
        text += f"Restart terakhir: mulai {last.get('started_at','-')} selesai {last.get('completed_at','-')} durasi {last.get('duration_sec',0)} dtk\n"
    btns = []
    if status == "normal":
        btns.append([Button.inline("Set Maintenance", b"SET_SYS_MAINT")])
    else:
        btns.append([Button.inline("Set Normal", b"SET_SYS_NORMAL")])
    btns.append([Button.inline("⬅️ Kembali", b"menu_start")])
    await event.edit(text, buttons=btns)

@bot.on(events.CallbackQuery(pattern=b"SET_SYS_MAINT"))
async def cb_set_maint(event):
    if event.sender_id != ADMIN_ID: return
    mc = read_manager_control()
    mc["system_status"] = "maintenance"
    mc["manual_set_at"] = datetime.now().isoformat()
    write_manager_control(mc)
    await cb_admin_sys_status(event)

@bot.on(events.CallbackQuery(pattern=b"SET_SYS_NORMAL"))
async def cb_set_normal(event):
    if event.sender_id != ADMIN_ID: return
    mc = read_manager_control()
    mc["system_status"] = "normal"
    mc["manual_set_at"] = datetime.now().isoformat()
    write_manager_control(mc)
    await cb_admin_sys_status(event)

@bot.on(events.CallbackQuery(pattern=b"cmd_admin_help"))
async def cb_admin_help(event):
    await event.edit("Gunakan tombol menu untuk navigasi.", buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]])

@bot.on(events.CallbackQuery(pattern=b"cmd_admin_restart"))
async def cb_restart(event):
    if event.sender_id != ADMIN_ID: return
    await event.answer("🔄 Restarting...", alert=True)
    with open("RESTART_FLAG.json", "w") as f: 
        json.dump({"chat_id": event.chat_id, "msg_id": event.message_id}, f)
    os.execl(sys.executable, sys.executable, *sys.argv)


# ==========================================
# 3. USER HANDLER (Login & Bayar)
# ==========================================

@bot.on(events.CallbackQuery(pattern=b"menu_status"))
async def cb_status(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    if not row: return await event.edit("❌ Kamu belum memiliki membership.", buttons=[[Button.inline("🔐 Aktivasi", b"menu_buy")]])
    
    expired = row.get("Expired", "-")
    status = row.get("Status", "-")
    ub_status = "🟢 Online" if user_id in ACTIVE_USERBOTS else "🔴 Offline"
    sys_status = read_manager_control().get("system_status", "normal")
    sys_label = "🟢 Normal" if sys_status == "normal" else "🟡 Maintenance"
    await event.edit(f"📊 Status Member\n\nID: `{user_id}`\nStatus: {status}\nUserbot: {ub_status}\nExpired: {expired}\nSistem: {sys_label}", buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]])

@bot.on(events.CallbackQuery(pattern=b"menu_connect_ub"))
async def cb_connect_ub(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    
    # --- PERBAIKAN DI SINI ---
    
    # 1. Cek jika user sama sekali tidak ada di database
    if not row:
        return await event.answer("❌ Status Membership: Belum Terdaftar", alert=True)
    
    # 2. Cek jika user ada, tapi statusnya bukan Approved
    if row.get("Status") != "Approved":
        return await event.answer(f"❌ Status Membership: {row.get('Status')}", alert=True)
    
    # -------------------------
    
    if user_id in ACTIVE_USERBOTS:
        return await event.edit("✅ Userbot sudah aktif.")

    # Mulai Login Flow
    new_client = TelegramClient(StringSession(), API_ID, API_HASH)
    await new_client.connect()
    LOGIN_STATE[user_id] = {"step": "phone", "client": new_client}
    await event.edit("📱 **Hubungkan Akun**\nKirim Nomor HP (contoh: `+62812345`)", buttons=[Button.inline("❌ Batal", b"cancel_login")])
    
@bot.on(events.CallbackQuery(pattern=b"cancel_login"))
async def cb_cancel_login(event):
    user_id = event.sender_id
    if user_id in LOGIN_STATE:
        await LOGIN_STATE[user_id]["client"].disconnect()
        del LOGIN_STATE[user_id]
    await event.edit("Login dibatalkan.", buttons=[[Button.inline("⬅️ Menu", b"menu_start")]])

async def finalize_login(user_id, client, msg_obj):
    try:
        session_string = client.session.save()
        save_session_to_sheet(user_id, session_string)
        ACTIVE_USERBOTS[user_id] = client
        asyncio.create_task(start_userbot(client, user_id))
        await msg_obj.edit("✅ **Login Berhasil!** Userbot aktif.")
        await bot.send_message(user_id, "Ketik `.help` di chat manapun untuk melihat menu userbot.")
        if user_id in LOGIN_STATE: del LOGIN_STATE[user_id]
    except Exception as e:
        await msg_obj.edit(f"❌ Error save session: {e}")

# ==========================================
# 4. LISTENER PESAN (Login & Payment)
# ==========================================
@bot.on(events.NewMessage)
async def message_handler(event):
    if event.sender_id == (await bot.get_me()).id: return
    user_id = event.sender_id
    text = (event.raw_text or "").strip()

    # --- HANDLER LOGIN ---
    if user_id in LOGIN_STATE:
        state = LOGIN_STATE[user_id]
        client = state["client"]
        try:
            if state["step"] == "phone":
                phone = text.replace(" ", "")
                msg = await event.reply("🔄 Mengirim OTP...")
                try:
                    ph = await client.send_code_request(phone)
                    # ph may be an object with phone_code_hash attribute; store only the string
                    phone_code_hash = getattr(ph, 'phone_code_hash', ph)
                    state.update({"phone_code_hash": phone_code_hash, "phone": phone, "step": "code"})
                    await msg.edit("📩 Masukkan Kode OTP (spasi angka, cth: 1 2 3 4 5)")
                except Exception as e: await msg.edit(f"❌ Error: {e}")
                
            elif state["step"] == "code":
                code = text.replace(" ", "")
                msg = await event.reply("🔄 Login...")
                try:
                    await client.sign_in(state["phone"], code, phone_code_hash=state.get("phone_code_hash"))
                    await finalize_login(user_id, client, msg)
                except SessionPasswordNeededError:
                    state["step"] = "password"
                    await msg.edit("🔐 Masukkan Password 2FA.")
                except Exception as e: await msg.edit(f"❌ Error: {e}")
                
            elif state["step"] == "password":
                msg = await event.reply("🔄 Verifikasi...")
                try:
                    await client.sign_in(password=text)
                    await finalize_login(user_id, client, msg)
                except Exception as e: await msg.edit(f"❌ Error: {e}")
        except Exception as e:
            await event.reply(f"Fatal Error: {e}")
            del LOGIN_STATE[user_id]
        return

    # ==========================================
# 1. MENU PEMBELIAN / FREE TRIAL
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"menu_buy"))
async def cb_menu_buy(event):
    user_id = event.sender_id
    
    # CEK APAKAH MODE FREE TRIAL AKTIF
    is_free_trial = GLOBAL_CONFIG.get("free_trial", False)

    if is_free_trial:
        # --- ALUR FREE TRIAL ---
        # Langsung bypass pemilihan harga, set indikator is_trial=True
        # Kita set 'total' = 0 dan 'months' = 0 (sebagai penanda)
        
        WAIT_NAME[user_id] = {
            "months": 0, 
            "total": 0, 
            "is_trial": True
        }
        
        await event.edit(
            "🎁 **SELAMAT DATANG MEMBER BARU!**\n\n"
            "Anda berhak mendapatkan **Free Trial 3 Hari**.\n"
            "Silakan lengkapi data berikut untuk aktivasi langsung.\n\n"
            "📝 Silakan kirim **Nama Lengkap** Anda:",
        )
    else:
        # --- ALUR BERBAYAR (NORMAL) ---
        tmp_key = f"tmp_{user_id}"
        pending_tx.pop(tmp_key, None)
        pending_tx[tmp_key] = {
            "user_id": user_id, "months": 1, 
            "total": PRICE_PER_MONTH, "timestamp": datetime.now().isoformat(),
            "is_trial": False
        }
        user_tx_map[user_id] = tmp_key
        
        await event.edit(
            f"📅 Perpanjang / Aktivasi Membership\nDurasi: 1 bulan\nTotal: {format_rp(PRICE_PER_MONTH)}",
            buttons=[
                [Button.inline("➖", b"minus_1"), Button.inline("1 Bulan", b"month_1"), Button.inline("➕", b"plus_1")],
                [Button.inline("💳 Lanjut ke Pembayaran", b"to_pay")]
            ]
        )

# ==========================================
# 2. LOGIKA PILIH BULAN (Hanya untuk Berbayar)
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"minus_1|plus_1|month_1"))
async def cb_months(event):
    user_id = event.sender_id
    data = event.data.decode()
    tmp = f"tmp_{user_id}"
    
    # Safety check
    if tmp not in pending_tx:
        pending_tx[tmp] = {"user_id": user_id, "months": 1, "total": PRICE_PER_MONTH, "is_trial": False}
    
    current = pending_tx[tmp]["months"]
    if data.startswith("minus"): current = max(1, current - 1)
    elif data.startswith("plus"): current = current + 1
    
    pending_tx[tmp]["months"] = current
    pending_tx[tmp]["total"] = current * PRICE_PER_MONTH
    
    await event.edit(
        f"📅 Durasi: {current} bulan\nTotal: {format_rp(pending_tx[tmp]['total'])}",
        buttons=[
            [Button.inline("➖", b"minus_1"), Button.inline(f"{current} Bulan", b"month_1"), Button.inline("➕", b"plus_1")],
            [Button.inline("💳 Lanjut ke Pembayaran", b"to_pay")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=b"to_pay"))
async def cb_to_pay(event):
    user_id = event.sender_id
    tmp = f"tmp_{user_id}"
    if tmp not in pending_tx: return await event.answer("Error, coba lagi.", alert=True)
    
    data_tx = pending_tx[tmp]
    idx, row = find_member_row(user_id)
    
    # Cek apakah nama sudah ada di DB
    if not idx or (not row.get("Nama") or row.get("Nama") == "-"):
        WAIT_NAME[user_id] = {
            "months": data_tx["months"], 
            "total": data_tx["total"],
            "is_trial": False
        }
        return await event.edit("📝 Silakan kirim *Nama lengkap* Anda.", parse_mode="markdown")

    # Jika nama sudah ada, langsung minta bukti transfer
    await process_payment_request(event, user_id, row.get("Nama"), row.get("Email"), data_tx)

async def process_payment_request(event, user_id, name, email, data_tx):
    tx_id = str(uuid.uuid4())
    # Pindahkan dari tmp ke pending_tx utama
    pending_tx[tx_id] = data_tx
    pending_tx[tx_id]["name"] = name
    pending_tx[tx_id]["email"] = email
    user_tx_map[user_id] = tx_id
    
    awaiting_photo.add(user_id)
    
    msg_text = f"💳 Total: {format_rp(data_tx['total'])}\nSilakan upload foto bukti transfer."
    await event.edit(msg_text)
    try: await bot.send_file(user_id, "qris.jpg", caption=f"Total: {format_rp(data_tx['total'])}")
    except: await bot.send_message(user_id, "⚠ qris.jpg tidak ditemukan.")

# ==========================================
# 3. HANDLER INPUT TEXT (NAMA & EMAIL)
# ==========================================
@bot.on(events.NewMessage)
async def payment_text_handler(event):
    user_id = event.sender_id
    text = (event.raw_text or "").strip()
    
    # A. INPUT NAMA
    if user_id in WAIT_NAME:
        data = WAIT_NAME.pop(user_id)
        # Lanjut ke minta Email
        WAIT_EMAIL[user_id] = {
            "name": text, 
            "months": data["months"], 
            "total": data["total"],
            "is_trial": data.get("is_trial", False)
        }
        await event.reply("📨 Sekarang kirim *Email* Anda.")
        return

    # B. INPUT EMAIL
    if user_id in WAIT_EMAIL:
        if "@" not in text: return await event.reply("❌ Email tidak valid. Coba lagi.")
        
        data = WAIT_EMAIL.pop(user_id)
        is_trial = data.get("is_trial", False)
        
        # --- CABANG LOGIKA: FREE TRIAL VS BERBAYAR ---
        
        if is_trial:
            # === LOGIKA FREE TRIAL (TANPA BUKTI BAYAR) ===
            # Langsung Aktivasi Member
            
            # 1. Hitung Expired (3 Hari dari sekarang)
            expire_date = (datetime.now() + timedelta(days=3)).strftime("%d-%m-%Y")
            
            # 2. Simpan ke Database (Langsung Approved)
            idx, row = find_member_row(user_id)
            if idx:
                update_member_name_email(idx, data["name"], text)
                update_member_status(idx, "Approved")
                update_member_expire(idx, expire_date) # Update fungsi di database.py harus support ini
            else:
                append_member(user_id, data["name"], text, "Approved", expire_date)
            
            # 3. Notifikasi Sukses
            await event.reply(
                f"✅ **Aktivasi Free Trial Berhasil!**\n\n"
                f"👤 Nama: {data['name']}\n"
                f"📅 Expired: **{expire_date}** (3 Hari)\n\n"
                f"Akun Anda sudah aktif. Silakan hubungkan Userbot sekarang.",
                buttons=[[Button.inline("⚙️ Hubungkan Userbot", b"menu_connect_ub")]]
            )
            
            # 4. Info ke Admin
            await bot.send_message(ADMIN_ID, f"🎁 **New Free Trial User**\nID: `{user_id}`\nNama: {data['name']}")
            
            # SELESAI. Tidak meminta foto, tidak menyimpan bukti.
            return

        else:
            # === LOGIKA BERBAYAR (MINTA BUKTI BAYAR) ===
            WAIT_PAYMENT_PROOF[user_id] = {
                "name": data["name"], 
                "email": text, 
                "months": data["months"], 
                "total": data["total"],
                "is_trial": False
            }
            
            # Siapkan transaksi pending
            tmp = f"tmp_{user_id}"
            pending_tx[tmp] = {
                "user_id": user_id, 
                "months": data["months"], 
                "total": data["total"], 
                "timestamp": datetime.now().isoformat(),
                "is_trial": False
            }
            user_tx_map[user_id] = tmp
            
            await event.reply(f"✅ Data tersimpan. Total: {format_rp(data['total'])}. Silakan upload bukti transfer.")
            awaiting_photo.add(user_id)
            try: await bot.send_file(user_id, "qris.jpg")
            except: pass
            return

    # C. HANDLER FOTO BUKTI (HANYA UNTUK USER BERBAYAR)
    # Jika Free Trial, user tidak akan pernah masuk ke set 'awaiting_photo',
    # jadi kode di bawah ini tidak akan pernah dieksekusi untuk user gratisan.
    if event.photo and user_id in awaiting_photo:
        tx_id = user_tx_map.get(user_id)
        if not tx_id:
             data = WAIT_PAYMENT_PROOF.get(user_id, {})
             tx_id = str(uuid.uuid4())
             pending_tx[tx_id] = {
                 "user_id": user_id, 
                 "months": data.get("months", 1), 
                 "total": data.get("total", PRICE_PER_MONTH), 
                 "timestamp": datetime.now().isoformat(),
                 "is_trial": False
             }

        # Simpan Foto (Hanya Berbayar)
        pending_tx[tx_id]["photo_path"] = await event.download_media()
        pending_tx[tx_id]["photo_ts"] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

        # Update Nama/Email di DB jika belum ada
        info = WAIT_PAYMENT_PROOF.pop(user_id, {})
        idx, row = find_member_row(user_id)
        name = info.get("name") or pending_tx[tx_id].get("name")
        email = info.get("email") or pending_tx[tx_id].get("email")
        
        if idx:
            if name and (not row.get("Nama") or row.get("Nama") == "-"): 
                update_member_name_email(idx, name, email or "-")
            update_member_status(idx, "Pending")
        else:
            append_member(user_id, name or "-", email or "-", "Pending")

        # Kirim ke Admin
        await bot.send_message(
            ADMIN_ID, 
            f"📩 **Bukti Transfer Baru**\nUser: `{user_id}`\nTotal: {format_rp(pending_tx[tx_id]['total'])}",
            file=pending_tx[tx_id]["photo_path"],
            buttons=[[Button.inline("✔ Approve", f"PAYAPPROVE:{tx_id}"), Button.inline("❌ Reject", f"PAYREJECT:{tx_id}")]]
        )
        
        awaiting_photo.remove(user_id)
        await event.reply("✅ Bukti terkirim. Tunggu konfirmasi admin.")
