import asyncio
import json
import os
from datetime import datetime

from telethon import events, Button
from config import bot, ADMIN_ID
from database import (
    find_member_row, get_all_members_safe, update_member_name_email, 
    delete_member, update_member_status, delete_history_by_user
)
from firebase_manager import clear_session_lock
from state import (
    ACTIVE_USERBOTS, ADMIN_ACTION_STATE, awaiting_reject_comment, 
    pending_tx, user_tx_map, awaiting_photo, WAIT_NAME, WAIT_EMAIL, 
    WAIT_PAYMENT_PROOF, LIVE_CHAT_SESSIONS
)

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
    if not idx:
        return await event.edit(f"❌ User `{user_id}` tidak ditemukan.", buttons=[[Button.inline("🔙 List", b"cmd_admin_status")]])

    # 1) Disconnect userbot jika aktif
    try:
        if int(user_id) in ACTIVE_USERBOTS:
            try:
                await ACTIVE_USERBOTS[int(user_id)].disconnect()
            except:
                pass
            try:
                del ACTIVE_USERBOTS[int(user_id)]
            except:
                pass
    except:
        pass

    # 2) Hapus sesi lokal & meta
    try:
        sp = f"botsession/{user_id}.session"
        if os.path.exists(sp):
            try:
                os.remove(sp)
            except:
                pass
        mp = os.path.join("user_session_meta", f"{user_id}.json")
        if os.path.exists(mp):
            try:
                os.remove(mp)
            except:
                pass
    except:
        pass

    # 3) Clear remote session lock
    try:
        clear_session_lock(user_id)
    except:
        pass

    # 4) Hapus data di Google Sheets: Member + History
    ok_member = delete_member(user_id)
    ok_hist = delete_history_by_user(user_id)

    # 5) Bersihkan state transaksi/queue
    try:
        # pending_tx entries
        to_del = [k for k,v in pending_tx.items() if str(v.get("user_id")) == str(user_id)]
        for k in to_del:
            try:
                del pending_tx[k]
            except:
                pass
        # user_tx_map
        try:
            if user_id in user_tx_map:
                del user_tx_map[user_id]
        except:
            pass
        # awaiting_photo
        try:
            if int(user_id) in awaiting_photo:
                awaiting_photo.discard(int(user_id))
        except:
            pass
        # WAIT_* buffers
        for buf in (WAIT_NAME, WAIT_EMAIL, WAIT_PAYMENT_PROOF):
            try:
                if user_id in buf:
                    del buf[user_id]
            except:
                pass
    except:
        pass

    # 6) Audit log
    try:
        entry = {
            "ts": datetime.now().isoformat(),
            "kind": "admin_delete_member",
            "user_id": str(user_id),
            "ok_member": ok_member,
            "ok_history": ok_hist
        }
        with open("session_usage.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except:
        pass

    # 7) Integritas: cek residual
    residual = []
    try:
        if int(user_id) in ACTIVE_USERBOTS:
            residual.append("active_userbot")
        if os.path.exists(f"botsession/{user_id}.session"):
            residual.append("local_session")
        if os.path.exists(os.path.join("user_session_meta", f"{user_id}.json")):
            residual.append("local_meta")
        idx2, _ = find_member_row(user_id)
        if idx2:
            residual.append("sheet_member")
    except:
        pass

    msg = "✅ User dihapus tuntas." if not residual else f"⚠️ Selesai dengan residu: {', '.join(residual)}"
    await event.edit(msg, buttons=[[Button.inline("🔙 List", b"cmd_admin_status")]])

@bot.on(events.CallbackQuery(pattern=r"ADM_MSG:(.+)"))
async def cb_admin_message_member(event):
    if event.sender_id != ADMIN_ID: 
        return
        
    user_id = int(event.data.decode().split(":")[1])
    
    # Check if member is online
    is_online = user_id in ACTIVE_USERBOTS
    if not is_online:
        return await event.answer("❌ Member sedang offline. Tidak dapat mengirim pesan.", alert=True)
    
    # Check if already in a chat session
    if user_id in LIVE_CHAT_SESSIONS:
        return await event.answer("❌ Sudah ada sesi chat aktif dengan member ini.", alert=True)
    
    # Create a new chat session
    task = asyncio.create_task(chat_timeout_checker(user_id))
    LIVE_CHAT_SESSIONS[user_id] = {
        'admin_id': ADMIN_ID,
        'last_activity': asyncio.get_running_loop().time(),
        'task': task
    }
    
    # Notify admin
    await event.edit(
        f"💬 **CHAT DIMULAI**\n\n"
        f"Anda sekarang dapat mengirim pesan ke member `{user_id}`.\n"
        "Balas pesan ini untuk mengirim pesan.\n"
        "Sesi akan berakhir setelah 5 menit tidak ada aktivitas.",
        buttons=[
            [Button.inline("� Akhiri Chat", f"END_CHAT:{user_id}")],
            [Button.inline("🔙 Kembali ke Profil", f"ADM_USR:{user_id}")]
        ]
    )
    
    # Notify member
    try:
        await bot.send_message(
            user_id,
            "👨‍💼 **ADMIN MENGIRIM PESAN**\n\n"
            "Anda menerima pesan dari Admin. Silakan balas pesan ini untuk membalas.\n"
            "_(Chat otomatis berakhir jika 5 menit tidak aktif)_",
            buttons=[[Button.inline("🛑 Akhiri Chat", b"end_chat_user")]]
        )
    except Exception as e:
        await event.answer(f"❌ Gagal mengirim notifikasi ke member: {str(e)}", alert=True)
        await end_chat_session(user_id, "Gagal mengirim notifikasi")
        return

# ==========================================
# 4. CHAT SESSION MANAGEMENT
# ==========================================

async def chat_timeout_checker(user_id):
    """Background task to check for chat session timeout"""
    try:
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds
            if user_id not in LIVE_CHAT_SESSIONS:
                break
                
            session = LIVE_CHAT_SESSIONS.get(user_id)
            if not session:
                break
                
            last_activity = session.get('last_activity', 0)
            current_time = asyncio.get_running_loop().time()
            
            # 5 minutes timeout
            if (current_time - last_activity) > 300:  # 300 seconds = 5 minutes
                await end_chat_session(user_id, "Sesi berakhir (tidak ada aktivitas)")
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Error in chat_timeout_checker: {e}")

async def end_chat_session(user_id, reason):
    """End a chat session and clean up"""
    if user_id not in LIVE_CHAT_SESSIONS:
        return
        
    session = LIVE_CHAT_SESSIONS.pop(user_id, None)
    if not session:
        return
        
    # Cancel the timeout checker task
    task = session.get('task')
    if task and not task.done():
        task.cancel()
    
    # Notify admin
    try:
        await bot.send_message(
            session['admin_id'],
            f"🛑 **Sesi Chat Berakhir**\n"
            f"Dengan: `{user_id}`\n"
            f"Alasan: {reason}",
            buttons=[[Button.inline("🔙 Daftar Member", b"cmd_admin_status")]]
        )
    except Exception as e:
        print(f"Error notifying admin: {e}")
    
    # Notify user
    try:
        await bot.send_message(
            user_id,
            f"🛑 **Sesi Chat dengan Admin Berakhir**\n{reason}",
            buttons=[[Button.inline("🔙 Menu Utama", b"menu_start")]]
        )
    except Exception as e:
        print(f"Error notifying user: {e}")

@bot.on(events.CallbackQuery(pattern=r"END_CHAT:(.+)"))
async def handle_admin_end_chat(event):
    """Handler for admin ending the chat"""
    if event.sender_id != ADMIN_ID:
        return
        
    try:
        user_id = int(event.data.decode().split(":")[1])
        await end_chat_session(user_id, "Diakhiri oleh Admin")
        await event.answer("✅ Chat diakhiri")
    except Exception as e:
        await event.answer(f"❌ Gagal mengakhiri chat: {str(e)}", alert=True)

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
