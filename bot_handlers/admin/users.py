from telethon import events, Button
from config import bot, ADMIN_ID
from database import (
    find_member_row, get_all_members_safe, update_member_name_email, 
    delete_member, update_member_status
)
from state import ACTIVE_USERBOTS, ADMIN_ACTION_STATE, awaiting_reject_comment, pending_tx

# Helper pagination
def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

ADMIN_SEARCH_QUERY = {} 

@bot.on(events.CallbackQuery(pattern=r"cmd_admin_status(:(\d+))?"))
async def cb_admin_status_list(event):
    if event.sender_id != ADMIN_ID: return
    
    data_str = event.data.decode()
    page = int(data_str.split(":")[1]) if ":" in data_str else 0
    
    all_records = get_all_members_safe()
    if not all_records:
        return await event.edit("❌ Belum ada member.", buttons=[[Button.inline("🔙 Kembali", b"menu_admin_dashboard")]])

    # Filter Pencarian
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

    # Sort & Pagination
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
    online_count = sum(1 for r in all_records if str(r.get("User ID")).isdigit() and int(r.get("User ID")) in ACTIVE_USERBOTS)

    for row in current_chunk:
        uid = str(row.get("User ID"))
        name = row.get("Nama", "Unknown")[:15]
        status = row.get("Status", "Pending")
        
        icon = "🟢" if status == "Approved" else "🔴" if status == "Rejected" else "🟡"
        if uid.isdigit() and int(uid) in ACTIVE_USERBOTS: icon = "⚡" 
            
        buttons.append([Button.inline(f"{icon} {name} ({uid})", f"ADM_USR:{uid}")])

    # Navigasi Halaman
    nav_row = []
    if page > 0: nav_row.append(Button.inline("⬅️", f"cmd_admin_status:{page-1}"))
    nav_row.append(Button.inline(f"📄 {page+1}/{total_pages}", b"noop"))
    if page < total_pages - 1: nav_row.append(Button.inline("➡️", f"cmd_admin_status:{page+1}"))
    if nav_row: buttons.append(nav_row)

    # Tombol Search & Back
    search_btn_text = f"🔍 Cari: {query}" if query else "🔍 Cari Member"
    action_row = [Button.inline(search_btn_text, b"ADM_SEARCH_MODE")]
    if query: action_row.append(Button.inline("❌ Reset", b"ADM_RESET_SEARCH"))
    buttons.append(action_row)
    # PERBAIKAN TOMBOL KEMBALI
    buttons.append([Button.inline("🔙 Kembali ke Dashboard", b"menu_admin_dashboard")])

    header_text = f"📊 **DAFTAR MEMBER**\nTotal: {len(all_records)} | ⚡ Online: {online_count}\n"
    if query: header_text += f"🔎 Hasil: `{query}` ({len(filtered_records)})\n"
    
    if hasattr(event, 'edit'):
        await event.edit(header_text, buttons=buttons)
    else:
        await event.respond(header_text, buttons=buttons)

# --- Search Logic ---
@bot.on(events.CallbackQuery(pattern=b"ADM_SEARCH_MODE"))
async def cb_admin_search_mode(event):
    if event.sender_id != ADMIN_ID: return
    ADMIN_ACTION_STATE[ADMIN_ID] = {"action": "SEARCH_MEMBER", "target": None}
    await event.edit("🔍 **MODE PENCARIAN**\n\nKirim kata kunci (Nama/Email/ID).\nKetik `/batal` untuk batal.")

@bot.on(events.CallbackQuery(pattern=b"ADM_RESET_SEARCH"))
async def cb_admin_reset_search(event):
    if event.sender_id != ADMIN_ID: return
    if ADMIN_ID in ADMIN_SEARCH_QUERY: del ADMIN_SEARCH_QUERY[ADMIN_ID]
    event.data = b"cmd_admin_status:0" 
    await cb_admin_status_list(event)

# --- Detail User & Edit ---
async def render_user_detail(event, user_id):
    idx, row = find_member_row(user_id)
    if not row: return await event.edit("❌ Member tidak ditemukan.", buttons=[[Button.inline("🔙 Kembali", b"cmd_admin_status")]])

    status = row.get("Status")
    status_icon = "✅ Aktif" if status == "Approved" else f"⛔ {status}"
    is_online = "🟢 Terhubung" if int(user_id) in ACTIVE_USERBOTS else "🔴 Offline"
    
    text = (
        f"👤 **PROFIL MEMBER**\n"
        f"🆔 ID: `{user_id}`\n"
        f"🏷 Nama: **{row.get('Nama')}**\n"
        f"📧 Email: `{row.get('Email')}`\n"
        f"🛡 Status: **{status_icon}**\n"
        f"📅 Expired: **{row.get('Expired')}**\n"
        f"🤖 Userbot: **{is_online}**\n"
    )

    buttons = [
        [Button.inline("⏳ Perpanjang", f"ADM_EXT:{user_id}"), Button.inline("💬 Kirim Pesan", f"ADM_MSG:{user_id}")],
        [Button.inline("⚙️ Menu Lanjutan (Hapus/Edit)", f"ADM_MORE:{user_id}")],
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

    suspend_btn = "⛔ Suspend Member" if row.get("Status") == "Approved" else "✅ Unsuspend"
    suspend_data = "SUSPEND" if row.get("Status") == "Approved" else "UNSUSPEND"

    text = f"⚙️ **MENU LANJUTAN**\nUser: `{user_id}`"
    buttons = [
        [Button.inline("✏️ Edit Nama & Email", f"ADM_EDIT:{user_id}")],
        [Button.inline(suspend_btn, f"ADM_ACT:{suspend_data}:{user_id}")],
        [Button.inline("🗑️ HAPUS PERMANEN", f"ADM_DEL:{user_id}")],
        [Button.inline("🔙 Kembali", f"ADM_USR:{user_id}")]
    ]
    
    if hasattr(event, 'edit'):
        await event.edit(text, buttons=buttons)
    else:
        await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"ADM_MORE:(.+)"))
async def cb_admin_more_actions(event):
    if event.sender_id != ADMIN_ID: return
    user_id = event.data.decode().split(":")[1]
    await render_more_actions(event, user_id)

@bot.on(events.CallbackQuery(pattern=r"ADM_DEL:(.+)"))
async def cb_admin_delete(event):
    user_id = event.data.decode().split(":")[1]
    await event.edit(f"⚠️ **KONFIRMASI HAPUS**\n\nYakin hapus `{user_id}`?", 
                     buttons=[[Button.inline("🗑️ YA, HAPUS", f"CONFIRM_DEL:{user_id}")], [Button.inline("🔙 Batal", f"ADM_MORE:{user_id}")]])

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
        await event.edit(f"✅ User `{user_id}` dihapus.", buttons=[[Button.inline("🔙 List", b"cmd_admin_status")]])

@bot.on(events.CallbackQuery(pattern=r"ADM_(MSG|EDIT):(.+)"))
async def cb_admin_input_mode(event):
    if event.sender_id != ADMIN_ID: return
    mode, user_id = event.data.decode().split(":")[1:]
    ADMIN_ACTION_STATE[ADMIN_ID] = {"action": mode, "target": user_id}
    msg = "💬 **MODE LIVECHAT**" if mode == "MSG" else "✏️ **EDIT DATA**\nFormat: `Nama | Email`"
    await event.edit(f"{msg}\n\nKetik `/batal` untuk keluar.")

@bot.on(events.NewMessage(from_users=ADMIN_ID))
async def admin_input_listener(event):
    # Handle Reject Payment
    if ADMIN_ID in awaiting_reject_comment and not event.text.startswith('/'):
        tx_id = awaiting_reject_comment.pop(ADMIN_ID)
        tx = pending_tx.pop(tx_id, {})
        if tx:
            uid = tx["user_id"]
            idx, _ = find_member_row(uid)
            if idx: update_member_status(idx, "Rejected", event.text)
            await bot.send_message(uid, f"❌ **Pembayaran Ditolak**\nAlasan: {event.text}")
            await event.reply(f"✅ Transaksi ditolak.")
        return

    if ADMIN_ID not in ADMIN_ACTION_STATE: return
    
    if event.text == "/batal":
        state = ADMIN_ACTION_STATE.pop(ADMIN_ID)
        await event.reply("✅ Dibatalkan.")
        if state["action"] != "SEARCH_MEMBER":
            msg = await event.respond("🔄 Memuat...")
            await render_user_detail(msg, state['target'])
        return

    state = ADMIN_ACTION_STATE[ADMIN_ID]
    action, target = state["action"], state["target"]
    
    if action == "MSG":
        try:
            await bot.send_message(int(target), f"📩 **Pesan Admin:**\n\n{event.text}\n\n_Balas pesan ini untuk chat._")
            await event.reply("✅ Terkirim.")
        except Exception as e: await event.reply(f"❌ Gagal: {e}")
            
    elif action == "EDIT":
        if "|" in event.text:
            new_name, new_email = map(str.strip, event.text.split("|")[:2])
            idx, row = find_member_row(target)
            if idx:
                update_member_name_email(idx, new_name, new_email)
                await event.reply("✅ Data diupdate.")
                del ADMIN_ACTION_STATE[ADMIN_ID]
                msg = await event.respond("Menu:")
                await render_user_detail(msg, target)
        else: await event.reply("⚠️ Format: `Nama | Email`")

    elif action == "SEARCH_MEMBER":
        ADMIN_SEARCH_QUERY[ADMIN_ID] = event.text.strip()
        del ADMIN_ACTION_STATE[ADMIN_ID]
        await event.reply(f"🔍 Mencari: `{event.text}`...")
        msg = await event.respond("🔄 Loading...")
        # Reset page ke 0
        event.data = b"cmd_admin_status:0"
        await cb_admin_status_list(msg)