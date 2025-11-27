from datetime import datetime, timedelta
from telethon import events, Button
from config import bot, ADMIN_ID
from database import (
    find_member_row, update_member_expire, update_member_status, 
    update_member_name_email, append_member, log_history
)
from state import ACTIVE_USERBOTS, pending_tx, awaiting_reject_comment

# Import render user detail dari module users agar bisa refresh halaman
from .users import render_user_detail, render_more_actions

# --- Extend Logic ---
@bot.on(events.CallbackQuery(pattern=r"ADM_EXT:(.+)"))
async def cb_admin_extend_menu(event):
    user_id = event.data.decode().split(":")[1]
    await render_extend_counter(event, user_id, 0, 0)

async def render_extend_counter(event, user_id, months, days):
    idx, row = find_member_row(user_id)
    nama = row.get("Nama", "Unknown") if row else "Unknown"
    
    text = (
        f"⏳ **ATUR PERPANJANGAN**\nUser: `{user_id}` ({nama})\n\n"
        f"🗓 **Tambahan: {months} Bulan {days} Hari**"
    )
    
    row_days = [
        Button.inline("➖ Hari", f"EXT_UPD:{user_id}:{months}:{days-1}"),
        Button.inline(f"{days} Hari", b"noop"),
        Button.inline("➕ Hari", f"EXT_UPD:{user_id}:{months}:{days+1}")
    ]
    row_months = [
        Button.inline("➖ Bulan", f"EXT_UPD:{user_id}:{months-1}:{days}"),
        Button.inline(f"{months} Bln", b"noop"),
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
    d = event.data.decode().split(":")
    await render_extend_counter(event, d[1], int(d[2]), int(d[3]))

@bot.on(events.CallbackQuery(pattern=r"EXT_OK:(.+):(.+):(.+)"))
async def cb_extend_confirm(event):
    if event.sender_id != ADMIN_ID: return
    user_id, months, days = event.data.decode().split(":")[1:]
    months, days = int(months), int(days)
    
    if months == 0 and days == 0: return await event.answer("⚠️ Durasi 0.", alert=True)

    idx, row = find_member_row(user_id)
    if not idx: return await event.answer("User 404.", alert=True)
    
    try: current_exp = datetime.strptime(row.get("Expired"), "%d-%m-%Y")
    except: current_exp = datetime.now()
    
    base_date = datetime.now() if current_exp < datetime.now() else current_exp
    new_exp = (base_date + timedelta(days=(months*30)+days)).strftime("%d-%m-%Y")
    
    update_member_expire(idx, new_exp)
    update_member_status(idx, "Approved") 
    
    await event.answer(f"✅ Berhasil! Expired baru: {new_exp}", alert=True)
    try: await bot.send_message(int(user_id), f"🎉 **SELAMAT!**\nPerpanjangan Berhasil.\n📅 Hingga: **{new_exp}**")
    except: pass

    await render_user_detail(event, user_id)

# --- Suspend / Unsuspend Logic ---
@bot.on(events.CallbackQuery(pattern=r"ADM_ACT:(.+):(.+)"))
async def cb_admin_actions(event):
    if event.sender_id != ADMIN_ID: return
    action, user_id = event.data.decode().split(":")[1:]
    idx, row = find_member_row(user_id)
    
    if not idx: return await event.answer("User tidak ditemukan.", alert=True)

    if action == "SUSPEND":
        update_member_status(idx, "Banned", "Admin Suspend")
        if int(user_id) in ACTIVE_USERBOTS:
            try: await ACTIVE_USERBOTS[int(user_id)].disconnect()
            except: pass
            del ACTIVE_USERBOTS[int(user_id)]
        await event.answer("⛔ Member di-suspend.", alert=True)
    elif action == "UNSUSPEND":
        update_member_status(idx, "Approved", "Admin Unsuspend")
        await event.answer("✅ Member diaktifkan.", alert=True)
        
    await render_more_actions(event, user_id)

# --- Payment Approval ---
@bot.on(events.CallbackQuery(pattern=r"(PAYAPPROVE|PAYREJECT):(.+)"))
async def cb_admin_pay(event):
    if event.sender_id != ADMIN_ID: return
    action, tx_id = event.data.decode().split(':')
    
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
        await bot.send_message(user_id, f"🎉 **PEMBAYARAN DITERIMA!**\nExpired: **{new_exp}**\nKlik /start -> ⚙️ Hubungkan Userbot.")
        await event.edit(f"✅ **APPROVED**\nUser: `{user_id}`")
        pending_tx.pop(tx_id, None)

    elif action == "PAYREJECT":
        awaiting_reject_comment[ADMIN_ID] = tx_id
        await event.edit("💬 **REJECT**\nSilakan kirim pesan teks berisi alasan penolakan.")