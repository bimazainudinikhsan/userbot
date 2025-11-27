# bmcodexbot/bot_handlers/payment.py
import uuid
from datetime import datetime
from telethon import events, Button
from config import bot, PRICE_PER_MONTH, format_rp
from database import find_member_row
from state import pending_tx, user_tx_map, awaiting_photo, WAIT_NAME, GLOBAL_CONFIG

@bot.on(events.CallbackQuery(pattern=b"menu_buy"))
async def cb_menu_buy(event):
    user_id = event.sender_id
    is_free_trial = GLOBAL_CONFIG.get("free_trial", False)

    if is_free_trial:
        WAIT_NAME[user_id] = {"months": 0, "total": 0, "is_trial": True}
        await event.edit("🎁 **SELAMAT DATANG MEMBER BARU!**\n\nAnda berhak mendapatkan **Free Trial 3 Hari**.\n📝 Silakan kirim **Nama Lengkap** Anda:")
    else:
        tmp_key = f"tmp_{user_id}"
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

@bot.on(events.CallbackQuery(pattern=b"minus_1|plus_1|month_1"))
async def cb_months(event):
    user_id = event.sender_id
    data = event.data.decode()
    tmp = f"tmp_{user_id}"
    
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
    
    if not idx or (not row.get("Nama") or row.get("Nama") == "-"):
        WAIT_NAME[user_id] = {"months": data_tx["months"], "total": data_tx["total"], "is_trial": False}
        return await event.edit("📝 Silakan kirim *Nama lengkap* Anda.", parse_mode="markdown")

    # Process Request Logic
    tx_id = str(uuid.uuid4())
    pending_tx[tx_id] = data_tx
    pending_tx[tx_id]["name"] = row.get("Nama")
    pending_tx[tx_id]["email"] = row.get("Email")
    user_tx_map[user_id] = tx_id
    
    awaiting_photo.add(user_id)
    await event.edit(f"💳 Total: {format_rp(data_tx['total'])}\nSilakan upload foto bukti transfer.")
    try: await bot.send_file(user_id, "qris.jpg", caption=f"Total: {format_rp(data_tx['total'])}")
    except: await bot.send_message(user_id, "⚠ qris.jpg tidak ditemukan.")