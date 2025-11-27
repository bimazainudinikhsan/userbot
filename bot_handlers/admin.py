# bmcodexbot/bot_handlers/admin.py
import json, os, sys
import asyncio
from datetime import datetime, timedelta
from telethon import events, Button

from config import bot, ADMIN_ID
from database import (
    find_member_row, update_member_expire, update_member_status,
    update_member_name_email, append_member, log_history,
    get_all_members_safe, get_member_permissions, update_member_permissions,
    delete_member
)
from state import (
    GLOBAL_CONFIG, pending_tx, awaiting_reject_comment,
    EDIT_PERMISSION_STATE, USER_PERMISSIONS, ADMIN_ACTION_STATE,
    ACTIVE_USERBOTS, GLOBAL_FEATURE_FLAGS 
)

# Menambahkan modul baru jika ingin kontrol terpisah, tapi saat ini ikut 'autoreply'
ALL_FEATURES_LIST = ["ping", "alive", "id", "botpesan", "spam", "autoreply", "setreply", "faktur"]

# --- UTILS: Pagination Helper ---
def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

async def show_admin_dashboard(event):
    is_trial_on = GLOBAL_CONFIG.get("free_trial", False)
    status_trial = "✅ ON" if is_trial_on else "❌ OFF"
    
    text = "👑 **ADMIN DASHBOARD**\nSelamat datang, Admin! Silakan pilih menu manajemen:"
    buttons = [
        [Button.inline(f"🆓 Mode Free Trial: {status_trial}", b"TOGGLE_TRIAL")],
        [Button.inline("👥 Manajemen Member", b"cmd_admin_status")],
        # Menu Baru: Global Fitur & Izin User
        [Button.inline("🌍 On/Off Fitur Global", b"cmd_global_fitur"), Button.inline("👤 Izin Fitur User", b"cmd_admin_fitur")],
        [Button.inline("🔄 Restart System", b"cmd_admin_restart"), Button.inline("🛑 Shutdown", b"cmd_admin_shutdown")], # Tombol Shutdown Baru
        [Button.inline("ℹ️ Bantuan", b"cmd_admin_help")]
    ]
    
    if isinstance(event, events.CallbackQuery.Event):
        await event.edit(text, buttons=buttons)
    else:
        await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"TOGGLE_TRIAL"))
async def cb_toggle_trial(event):
    if event.sender_id != ADMIN_ID: return
    GLOBAL_CONFIG["free_trial"] = not GLOBAL_CONFIG.get("free_trial", False)
    await show_admin_dashboard(event)

# ==================================================================
# FITUR GLOBAL MANAGEMENT
# ==================================================================

@bot.on(events.CallbackQuery(pattern=b"cmd_global_fitur"))
async def cb_global_fitur_menu(event):
    if event.sender_id != ADMIN_ID: return
    
    text = "🌍 **KELOLA FITUR GLOBAL**\n\nMatikan atau nyalakan fitur untuk **SEMUA MEMBER**.\n(Berguna saat maintenance)."
    buttons = []
    row = []
    
    for feature in ALL_FEATURES_LIST:
        is_active = GLOBAL_FEATURE_FLAGS.get(feature, True)
        icon = "✅" if is_active else "🔴"
        row.append(Button.inline(f"{icon} {feature}", f"GLB_TOGGLE:{feature}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
            
    if row: buttons.append(row)
    buttons.append([Button.inline("🔙 Kembali Dashboard", b"menu_start")])
    
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"GLB_TOGGLE:(.+)"))
async def cb_global_toggle(event):
    if event.sender_id != ADMIN_ID: return
    feature = event.data.decode().split(":")[1]
    current = GLOBAL_FEATURE_FLAGS.get(feature, True)
    GLOBAL_FEATURE_FLAGS[feature] = not current
    await cb_global_fitur_menu(event)

# ==================================================================
# MANAJEMEN MEMBER (MODERN UI + SEARCH & SORT)
# ==================================================================

ADMIN_SEARCH_QUERY = {} 

@bot.on(events.CallbackQuery(pattern=r"cmd_admin_status(:(\d+))?"))
async def cb_admin_status_list(event):
    if event.sender_id != ADMIN_ID: return
    
    data_str = event.data.decode()
    if ":" in data_str:
        page = int(data_str.split(":")[1])
    else:
        page = 0
    
    all_records = get_all_members_safe()
    if not all_records:
        return await event.edit("❌ Belum ada member terdaftar.", buttons=[[Button.inline("🔙 Kembali", b"menu_start")]])

    query = ADMIN_SEARCH_QUERY.get(ADMIN_ID, "").lower()
    if query:
        filtered_records = [
            r for r in all_records 
            if query in str(r.get("Nama", "")).lower() or 
               query in str(r.get("Email", "")).lower() or
               query in str(r.get("User ID", ""))
        ]
    else:
        filtered_records = all_records

    sorted_records = list(reversed(filtered_records))
    ITEMS_PER_PAGE = 10
    chunks = list(chunk_list(sorted_records, ITEMS_PER_PAGE))
    
    if not chunks:
        current_chunk = []
        total_pages = 1
    else:
        if page >= len(chunks): page = 0
        current_chunk = chunks[page]
        total_pages = len(chunks)

    buttons = []
    online_count = 0
    for r in all_records:
        uid = str(r.get("User ID"))
        if uid.isdigit() and int(uid) in ACTIVE_USERBOTS:
            online_count += 1

    for row in current_chunk:
        uid = str(row.get("User ID"))
        name = row.get("Nama", "Unknown")
        if not name: name = "Unknown"
        name = name[:15] 
        status = row.get("Status", "Pending")
        
        icon = "🟢" if status == "Approved" else "🔴" if status == "Rejected" else "🟡"
        if uid.isdigit() and int(uid) in ACTIVE_USERBOTS:
            icon = "⚡" 
            
        btn_text = f"{icon} {name} ({uid})"
        buttons.append([Button.inline(btn_text, f"ADM_USR:{uid}")])

    nav_row = []
    if page > 0:
        nav_row.append(Button.inline("⬅️", f"cmd_admin_status:{page-1}"))
    nav_row.append(Button.inline(f"📄 {page+1}/{total_pages}", b"noop"))
    if page < total_pages - 1:
        nav_row.append(Button.inline("➡️", f"cmd_admin_status:{page+1}"))
    if nav_row: buttons.append(nav_row)

    search_btn_text = f"🔍 Cari: {query}" if query else "🔍 Cari Member"
    action_row = [Button.inline(search_btn_text, b"ADM_SEARCH_MODE")]
    if query:
        action_row.append(Button.inline("❌ Reset", b"ADM_RESET_SEARCH"))
    buttons.append(action_row)
    
    buttons.append([Button.inline("🔙 Kembali ke Dashboard", b"menu_start")])

    header_text = (
        f"📊 **DAFTAR SEMUA MEMBER**\n"
        f"Total: {len(all_records)} | ⚡ Online: {online_count}\n"
    )
    if query:
        header_text += f"🔎 Hasil pencarian: `{query}` ({len(filtered_records)} ditemukan)\n"
    
    header_text += f"\n👇 **Klik nama member untuk kelola:**"
    await event.edit(header_text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"ADM_SEARCH_MODE"))
async def cb_admin_search_mode(event):
    if event.sender_id != ADMIN_ID: return
    ADMIN_ACTION_STATE[ADMIN_ID] = {"action": "SEARCH_MEMBER", "target": None}
    await event.edit("🔍 **MODE PENCARIAN**\n\nKirim kata kunci (Nama, Email, atau ID) untuk mencari member.\n\nKetik `/batal` untuk kembali.")

@bot.on(events.CallbackQuery(pattern=b"ADM_RESET_SEARCH"))
async def cb_admin_reset_search(event):
    if event.sender_id != ADMIN_ID: return
    if ADMIN_ID in ADMIN_SEARCH_QUERY:
        del ADMIN_SEARCH_QUERY[ADMIN_ID]
    event.data = b"cmd_admin_status:0" 
    await cb_admin_status_list(event)

async def render_user_detail(event, user_id):
    idx, row = find_member_row(user_id)
    if not row:
        return await event.edit("❌ Member tidak ditemukan di database.", buttons=[[Button.inline("🔙 Kembali", b"cmd_admin_status")]])

    status = row.get("Status")
    status_icon = "✅ Aktif" if status == "Approved" else f"⛔ {status}"
    is_online = "🟢 Terhubung" if int(user_id) in ACTIVE_USERBOTS else "🔴 Offline"
    
    text = (
        f"👤 **PROFIL MEMBER**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"🏷 Nama: **{row.get('Nama')}**\n"
        f"📧 Email: `{row.get('Email')}`\n"
        f"🛡 Status: **{status_icon}**\n"
        f"📅 Expired: **{row.get('Expired')}**\n"
        f"🤖 Userbot: **{is_online}**\n\n"
        f"👇 **Pilih Tindakan:**"
    )

    buttons = [
        [Button.inline("⏳ Perpanjang", f"ADM_EXT:{user_id}"), Button.inline("💬 Kirim Pesan", f"ADM_MSG:{user_id}")],
        [Button.inline("⚙️ Tindakan Lanjutan (Edit/Hapus)", f"ADM_MORE:{user_id}")],
        [Button.inline("🔙 Daftar Member", b"cmd_admin_status")]
    ]
    try: await event.edit(text, buttons=buttons)
    except: await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"ADM_USR:(.+)"))
async def cb_admin_user_detail(event):
    if event.sender_id != ADMIN_ID: return
    user_id = event.data.decode().split(":")[1]
    await render_user_detail(event, user_id)

async def render_more_actions(event, user_id):
    idx, row = find_member_row(user_id)
    if not row: return await event.answer("Member tidak ditemukan.", alert=True)

    status = row.get("Status")
    suspend_btn = "⛔ Suspend Member" if status == "Approved" else "✅ Unsuspend (Aktifkan)"
    suspend_data = "SUSPEND" if status == "Approved" else "UNSUSPEND"

    text = f"⚙️ **MENU LANJUTAN**\nUser: `{user_id}` ({row.get('Nama')})\n\nHati-hati, tindakan di sini sensitif."
    
    buttons = [
        [Button.inline("✏️ Edit Nama & Email", f"ADM_EDIT:{user_id}")],
        [Button.inline(suspend_btn, f"ADM_ACT:{suspend_data}:{user_id}")],
        [Button.inline("🗑️ HAPUS MEMBER PERMANEN", f"ADM_DEL:{user_id}")],
        [Button.inline("🔙 Kembali ke Profil", f"ADM_USR:{user_id}")]
    ]
    try: await event.edit(text, buttons=buttons)
    except: await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"ADM_MORE:(.+)"))
async def cb_admin_more_actions(event):
    if event.sender_id != ADMIN_ID: return
    user_id = event.data.decode().split(":")[1]
    await render_more_actions(event, user_id)

# ==================================================================
# LOGIKA PERPANJANG (EXTEND)
# ==================================================================

@bot.on(events.CallbackQuery(pattern=r"ADM_EXT:(.+)"))
async def cb_admin_extend_menu(event):
    user_id = event.data.decode().split(":")[1]
    await render_extend_counter(event, user_id, 0, 0)

async def render_extend_counter(event, user_id, months, days):
    idx, row = find_member_row(user_id)
    nama = row.get("Nama", "Unknown") if row else "Unknown"
    
    text = (
        f"⏳ **ATUR PERPANJANGAN**\n"
        f"User: `{user_id}` ({nama})\n\n"
        f"Silakan atur durasi tambahan:\n"
        f"🗓 **Total: {months} Bulan {days} Hari**"
    )
    
    row_days = [
        Button.inline("➖ Hari", f"EXT_UPD:{user_id}:{months}:{days-1}"),
        Button.inline(f"{days} Hari", b"noop"),
        Button.inline("➕ Hari", f"EXT_UPD:{user_id}:{months}:{days+1}")
    ]
    row_months = [
        Button.inline("➖ Bulan", f"EXT_UPD:{user_id}:{months-1}:{days}"),
        Button.inline(f"{months} Bulan", b"noop"),
        Button.inline("➕ Bulan", f"EXT_UPD:{user_id}:{months+1}:{days}")
    ]
    row_actions = [
        Button.inline("✅ KONFIRMASI", f"EXT_OK:{user_id}:{months}:{days}"),
        Button.inline("🔙 Batal", f"ADM_USR:{user_id}")
    ]
    
    buttons = [row_days, row_months, row_actions]
    try: await event.edit(text, buttons=buttons)
    except: await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"EXT_UPD:(.+):(.+):(.+)"))
async def cb_extend_update(event):
    if event.sender_id != ADMIN_ID: return
    data = event.data.decode().split(":")
    user_id = data[1]
    months = int(data[2])
    days = int(data[3])
    await render_extend_counter(event, user_id, months, days)

@bot.on(events.CallbackQuery(pattern=r"EXT_OK:(.+):(.+):(.+)"))
async def cb_extend_confirm(event):
    if event.sender_id != ADMIN_ID: return
    data = event.data.decode().split(":")
    user_id = data[1]
    months = int(data[2])
    days = int(data[3])
    
    if months == 0 and days == 0:
        return await event.answer("⚠️ Durasi 0, tidak ada perubahan.", alert=True)

    idx, row = find_member_row(user_id)
    if not idx: return await event.answer("User tidak ditemukan.", alert=True)
    
    try:
        current_exp = datetime.strptime(row.get("Expired"), "%d-%m-%Y")
    except:
        current_exp = datetime.now()
    
    base_date = datetime.now() if current_exp < datetime.now() else current_exp
    total_added_days = (months * 30) + days
    new_exp = base_date + timedelta(days=total_added_days)
    new_exp_str = new_exp.strftime("%d-%m-%Y")
    
    update_member_expire(idx, new_exp_str)
    update_member_status(idx, "Approved") 
    
    await event.answer(f"✅ Berhasil! Expired baru: {new_exp_str}", alert=True)
    
    msg_member = (
        f"🎉 **SELAMAT!**\n\n"
        f"Anda mendapatkan perpanjangan masa aktif **{months} Bulan {days} Hari**.\n"
        f"📅 Hingga: **{new_exp_str}**"
    )
    try: await bot.send_message(int(user_id), msg_member)
    except: pass

    await render_user_detail(event, user_id)

# --- LOGIKA SUSPEND / DELETE ---
@bot.on(events.CallbackQuery(pattern=r"ADM_ACT:(.+):(.+)"))
async def cb_admin_actions(event):
    if event.sender_id != ADMIN_ID: return
    data = event.data.decode().split(":")
    action = data[1]
    user_id = data[2]
    idx, row = find_member_row(user_id)
    
    if not idx: return await event.answer("User tidak ditemukan.", alert=True)

    if action == "SUSPEND":
        update_member_status(idx, "Banned", "Admin Suspend")
        if int(user_id) in ACTIVE_USERBOTS:
            try: await ACTIVE_USERBOTS[int(user_id)].disconnect()
            except: pass
            del ACTIVE_USERBOTS[int(user_id)]
        await event.answer("⛔ Member berhasil di-suspend.", alert=True)
        
    elif action == "UNSUSPEND":
        update_member_status(idx, "Approved", "Admin Unsuspend")
        await event.answer("✅ Member diaktifkan kembali.", alert=True)
        
    await render_more_actions(event, user_id)

@bot.on(events.CallbackQuery(pattern=r"ADM_DEL:(.+)"))
async def cb_admin_delete(event):
    user_id = event.data.decode().split(":")[1]
    await event.edit(
        f"⚠️ **KONFIRMASI HAPUS**\n\nYakin ingin menghapus user `{user_id}`?\nData tidak bisa dikembalikan.",
        buttons=[
            [Button.inline("🗑️ YA, HAPUS", f"CONFIRM_DEL:{user_id}")],
            [Button.inline("🔙 Batal", f"ADM_MORE:{user_id}")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=r"CONFIRM_DEL:(.+)"))
async def cb_confirm_delete(event):
    if event.sender_id != ADMIN_ID: return
    user_id = event.data.decode().split(":")[1]
    idx, row = find_member_row(user_id)
    
    if idx:
        delete_member(idx)
        if int(user_id) in ACTIVE_USERBOTS:
            try: await ACTIVE_USERBOTS[int(user_id)].disconnect()
            except: pass
            del ACTIVE_USERBOTS[int(user_id)]
        await event.edit(f"✅ User `{user_id}` telah dihapus dari database.", buttons=[[Button.inline("🔙 Kembali ke List", b"cmd_admin_status")]])
    else:
        await event.answer("User tidak ditemukan.", alert=True)

# --- LOGIKA KIRIM PESAN & EDIT DATA ---
@bot.on(events.CallbackQuery(pattern=r"ADM_(MSG|EDIT):(.+)"))
async def cb_admin_input_mode(event):
    if event.sender_id != ADMIN_ID: return
    data = event.data.decode().split(":")
    if len(data) < 3: return await event.answer("❌ Data callback tidak valid.", alert=True)

    mode = data[1] # MSG or EDIT
    user_id = data[2]
    
    ADMIN_ACTION_STATE[ADMIN_ID] = {"action": mode, "target": user_id}
    
    if mode == "MSG":
        await event.edit(f"💬 **MODE LIVECHAT**\n\nKirim pesan teks sekarang, pesan akan langsung diteruskan ke user `{user_id}`.\n\nKetik `/batal` untuk keluar.")
    elif mode == "EDIT":
        await event.edit(f"✏️ **EDIT DATA MEMBER**\nUser: `{user_id}`\n\nFormat: `NamaBaru | EmailBaru`\nContoh: `Budi | budi@gmail.com`\n\nKetik `/batal` untuk keluar.")

@bot.on(events.NewMessage(from_users=ADMIN_ID))
async def admin_input_listener(event):
    if ADMIN_ID not in ADMIN_ACTION_STATE: return
    
    if event.text.startswith("/"): 
        if event.text == "/batal":
            if ADMIN_ID in ADMIN_ACTION_STATE:
                state = ADMIN_ACTION_STATE[ADMIN_ID]
                del ADMIN_ACTION_STATE[ADMIN_ID]
                await event.reply("✅ Mode dibatalkan.")
                if state["action"] != "SEARCH_MEMBER":
                    user_id = state['target']
                    msg = await event.reply("🔄 Memuat menu...")
                    await render_user_detail(msg, user_id)
            return

    state = ADMIN_ACTION_STATE[ADMIN_ID]
    action = state["action"]
    target = state["target"]
    
    if action == "MSG":
        user_id = target
        try:
            await bot.send_message(int(user_id), f"📩 **Pesan dari Admin:**\n\n{event.text}\n\n_Balas pesan ini untuk menghubungi admin._")
            await event.reply(f"✅ Pesan terkirim ke `{user_id}`.")
        except Exception as e:
            await event.reply(f"❌ Gagal kirim: {e}")
            
    elif action == "EDIT":
        user_id = target
        if "|" in event.text:
            parts = event.text.split("|")
            new_name = parts[0].strip()
            new_email = parts[1].strip() if len(parts) > 1 else "-"
            idx, row = find_member_row(user_id)
            if idx:
                update_member_name_email(idx, new_name, new_email)
                await event.reply(f"✅ Data user `{user_id}` diupdate.\nNama: {new_name}\nEmail: {new_email}")
                del ADMIN_ACTION_STATE[ADMIN_ID]
                msg = await event.respond("Menu:")
                await render_user_detail(msg, user_id)
            else:
                await event.reply("❌ User tidak ditemukan.")
        else:
            await event.reply("⚠️ Format salah. Gunakan: `Nama | Email`")

    elif action == "SEARCH_MEMBER":
        query = event.text.strip()
        ADMIN_SEARCH_QUERY[ADMIN_ID] = query
        del ADMIN_ACTION_STATE[ADMIN_ID]
        await event.reply(f"🔍 Mencari: `{query}`...")
        msg = await event.respond("🔄 Memuat hasil...")
        await msg.edit(f"Hasil untuk: `{query}`", buttons=[[Button.inline("📂 LIHAT HASIL", b"cmd_admin_status")]])

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
    await event.edit("🛠 **MANAJEMEN IZIN USER**\nPilih member untuk diatur izinnya:", buttons=buttons)

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
    if all(pd.values()): final = ["ALL"]
    else: final = [k for k,v in pd.items() if v]
    
    update_member_permissions(t, final)
    USER_PERMISSIONS[t] = final
    await event.edit(f"✅ **Saved!**\nUser: `{t}`", buttons=[[Button.inline("⬅️ Kembali", b"cmd_admin_fitur")]])

# --- Admin Payment Approval ---
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
        months = tx.get("months", 1)
        if idx:
            try: exp = datetime.strptime(row.get("Expired"), "%d-%m-%Y")
            except: exp = datetime.now()
            base = exp if exp > datetime.now() else datetime.now()
            new_exp = (base + timedelta(days=30 * months)).strftime("%d-%m-%Y")
            
            update_member_expire(idx, new_exp)
            update_member_status(idx, "Approved")
            if tx.get("name"): update_member_name_email(idx, tx["name"], tx["email"])
        else:
            new_exp = append_member(user_id, tx.get("name"), tx.get("email"), months)
            
        log_history(user_id, months, tx["total"], "Approved")
        await bot.send_message(user_id, f"🎉 **PEMBAYARAN DITERIMA!**\n\nStatus: **Approved**\nExpired: **{new_exp}**\n\nSilakan klik /start lalu pilih **⚙️ Hubungkan Userbot**.")
        await event.edit(f"✅ **APPROVED**\nUser: `{user_id}`")
        pending_tx.pop(tx_id, None)

    elif action == "PAYREJECT":
        awaiting_reject_comment[ADMIN_ID] = tx_id
        await event.edit("💬 **REJECT**\nSilakan kirim pesan teks berisi alasan penolakan.")

@bot.on(events.NewMessage(from_users=ADMIN_ID))
async def admin_reject_reason(event):
    if ADMIN_ID in ADMIN_ACTION_STATE: return 

    if ADMIN_ID in awaiting_reject_comment and not event.text.startswith('/'):
        tx_id = awaiting_reject_comment.pop(ADMIN_ID)
        tx = pending_tx.pop(tx_id, {})
        if tx:
            uid = tx["user_id"]
            idx, _ = find_member_row(uid)
            if idx: update_member_status(idx, "Rejected", event.text)
            await bot.send_message(uid, f"❌ **Pembayaran Ditolak**\nAlasan: {event.text}")
            await event.reply(f"✅ Transaksi user `{uid}` telah ditolak.")

@bot.on(events.CallbackQuery(pattern=b"cmd_admin_help"))
async def cb_admin_help(event):
    await event.edit("Gunakan tombol menu untuk navigasi.", buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]])

# --- FUNGSI INTI: RESTART PROCESS ---
# Fungsi ini bisa dipanggil oleh Tombol atau Auto Update
async def execute_restart_sequence(trigger_event=None):
    # 1. Tentukan target Admin & Pesan Awal
    # Jika dipanggil lewat tombol, edit pesan. Jika otomatis, kirim pesan baru ke Admin.
    target_chat_id = ADMIN_ID # Pastikan variabel ADMIN_ID sudah ada di atas
    status_msg = None

    if trigger_event:
        # Jika dipicu tombol admin
        target_chat_id = trigger_event.chat_id
        await trigger_event.answer("🔄 Memulai proses restart...", alert=True)
        status_msg = await trigger_event.edit("🔄 **SYSTEM RESTART INITIATED**\n\nSedang mengirim notifikasi ke seluruh member...")
    else:
        # Jika dipicu Auto Update
        status_msg = await bot.send_message(ADMIN_ID, "🔄 **AUTO UPDATE DETECTED**\n\nSedang mengirim notifikasi ke seluruh member...")

    # 2. Broadcast Peringatan ke Semua Member
    members = get_all_members_safe() # Pastikan fungsi ini tersedia
    count = 0
    now_str = datetime.now().strftime("%H:%M WIB")

    for row in members:
        try:
            uid = str(row.get("User ID"))
            if uid.isdigit() and int(uid) != ADMIN_ID:
                await bot.send_message(
                    int(uid), 
                    f"⚠️ **PEMBERITAHUAN SISTEM**\n\n"
                    f"Sistem sedang melakukan **UPDATE/RESTART**.\n"
                    f"Layanan akan terhenti sejenak. Mohon tunggu hingga sistem menyala kembali.\n\n"
                    f"🕒 Waktu: **{now_str}**"
                )
                count += 1
                await asyncio.sleep(0.1) 
        except: pass
    
    # Update status ke Admin
    final_text = f"✅ Broadcast terkirim ke {count} member.\n🔄 **Me-restart Server Sekarang...**"
    if status_msg:
        await status_msg.edit(final_text)

    # 3. Simpan Flag Restart
    # Kita simpan ID pesan status_msg agar nanti pas nyala bisa diedit jadi "Sistem Online"
    with open("RESTART_FLAG.json", "w") as f: 
        json.dump({
            "chat_id": target_chat_id, 
            "msg_id": status_msg.id if status_msg else None, 
            "admin_id": ADMIN_ID,
            "type": "auto" if trigger_event is None else "manual"
        }, f)
        
    # 4. Eksekusi Restart
    print("Mengeksekusi os.execl...")
    os.execl(sys.executable, sys.executable, *sys.argv)


# --- HANDLER 1: TOMBOL ADMIN (Manual) ---
@bot.on(events.CallbackQuery(pattern=b"cmd_admin_restart"))
async def cb_restart(event):
    if event.sender_id != ADMIN_ID: return
    # Panggil fungsi inti dengan membawa event tombol
    await execute_restart_sequence(trigger_event=event)


# --- HANDLER 2: PEMANTAU AUTO UPDATE (Otomatis) ---
async def auto_update_watcher():
    print("Auto-update watcher started...")
    while True:
        # Cek apakah file penanda dari script bash ada
        if os.path.exists("restart_trigger.txt"):
            print("File trigger ditemukan! Memulai sequence restart...")
            try:
                os.remove("restart_trigger.txt") # Hapus file segera
            except: pass
            
            # Panggil fungsi inti TANPA event (None)
            await execute_restart_sequence(trigger_event=None)
        
        await asyncio.sleep(10) # Cek setiap 10 detik
# --- JALANKAN WATCHER ---
# Letakkan baris ini SEBELUM bot.run_until_disconnected()
bot.loop.create_task(auto_update_watcher())
# ==================================================================
# SHUTDOWN HANDLER (BARU)
# ==================================================================

@bot.on(events.CallbackQuery(pattern=b"cmd_admin_shutdown"))
async def cb_shutdown_confirm(event):
    if event.sender_id != ADMIN_ID: return
    await event.edit(
        "⚠️ **KONFIRMASI SHUTDOWN**\n\n"
        "Anda yakin ingin mematikan bot?\n"
        "Semua layanan akan berhenti dan userbot akan terputus.",
        buttons=[
            [Button.inline("🔴 YA, MATIKAN", b"confirm_shutdown")],
            [Button.inline("🔙 Batal", b"menu_start")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=b"confirm_shutdown"))
async def cb_shutdown_execute(event):
    if event.sender_id != ADMIN_ID: return
    
    await event.answer("🔴 Mematikan system...", alert=True)
    msg = await event.edit("🔴 **SYSTEM SHUTDOWN**\n\nSedang mengirim pesan perpisahan..")
    
    members = get_all_members_safe()
    count = 0
    
    # Broadcast ke semua member
    for row in members:
        try:
            uid = str(row.get("User ID"))
            if uid.isdigit():
                await bot.send_message(
                    int(uid), 
                    "⚠️ **PEMBERITAHUAN SISTEM**\n\n"
                    "Bot sedang dimatikan untuk maintenance/shutdown.\n"
                    "Layanan dihentikan sementara sampai pemberitahuan lebih lanjut."
                )
                count += 1
                await asyncio.sleep(0.1)
        except: pass
    
    await msg.edit(f"✅ Broadcast terkirim ke {count} member.\n🔴 **Bot Offline.**")
    
    # Shutdown Process
    # Disconnect semua userbot dulu agar clean
    for uid, client in list(ACTIVE_USERBOTS.items()):
        try: await client.disconnect()
        except: pass
    
    try: await bot.disconnect()
    except: pass
    
    sys.exit(0) # Matikan script