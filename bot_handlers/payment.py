# bmcodexbot/bot_handlers/payment.py
import uuid
import asyncio
from datetime import datetime, timedelta
from telethon import events, Button
from config import bot, PRICE_PER_MONTH, format_rp, ADMIN_ID
from database import find_member_row, append_member, update_member_name_email, update_member_status, update_member_expire
from state import pending_tx, user_tx_map, awaiting_photo, WAIT_NAME, WAIT_EMAIL, WAIT_PAYMENT_PROOF, GLOBAL_CONFIG

# ==========================================
# MENU BELI / AKTIVASI
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"menu_buy"))
async def cb_menu_buy(event):
    user_id = event.sender_id
    
    # Hapus state lama jika ada
    if user_id in WAIT_NAME: del WAIT_NAME[user_id]
    if user_id in WAIT_EMAIL: del WAIT_EMAIL[user_id]

    # Mode Pembayaran Normal (Bukan Trial)
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
            [Button.inline("💳 Lanjut ke Pembayaran", b"to_pay")],
            [Button.inline("⬅️ Kembali", b"menu_start")]
        ]
    )

# ==========================================
# HANDLER TOMBOL +/- BULAN
# ==========================================
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
            [Button.inline("💳 Lanjut ke Pembayaran", b"to_pay")],
            [Button.inline("⬅️ Kembali", b"menu_start")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=b"to_pay"))
async def cb_to_pay(event):
    user_id = event.sender_id
    tmp = f"tmp_{user_id}"
    if tmp not in pending_tx: return await event.answer("Sesi habis, ulangi lagi.", alert=True)
    
    data_tx = pending_tx[tmp]
    idx, row = find_member_row(user_id)
    
    # Cek apakah user sudah punya Nama/Email di database
    nama_db = row.get("Nama") if row else None
    email_db = row.get("Email") if row else None

    # Jika Data Belum Lengkap, Minta Input
    if not nama_db or nama_db == "-" or not email_db or email_db == "-":
        WAIT_NAME[user_id] = {
            "months": data_tx["months"], 
            "total": data_tx["total"], 
            "is_trial": False
        }
        return await event.edit(
            "📝 **DATA DIRI**\n\n"
            "Sebelum melanjutkan pembayaran, kami membutuhkan data Anda.\n"
            "1️⃣ Silakan kirim **Nama Lengkap** Anda:",
            buttons=[Button.inline("❌ Batal", b"menu_start")]
        )

    # Jika Data Sudah Ada, Langsung ke Proses Bayar
    await process_payment_final(event, user_id, nama_db, email_db, data_tx)

# ==========================================
# HANDLER INPUT TEXT (NAMA & EMAIL)
# ==========================================
@bot.on(events.NewMessage(incoming=True))
async def payment_input_listener(event):
    user_id = event.sender_id
    text = event.text.strip()
    
    # Abaikan command
    if text.startswith("/"): return

    # --- TAHAP 1: INPUT NAMA ---
    if user_id in WAIT_NAME:
        data = WAIT_NAME.pop(user_id)
        
        # Simpan nama sementara & lanjut minta email
        WAIT_EMAIL[user_id] = {
            "name": text,
            "months": data["months"],
            "total": data["total"],
            "is_trial": data.get("is_trial", False)
        }
        
        await event.reply(
            f"✅ Halo **{text}**.\n"
            "2️⃣ Sekarang silakan kirim **Alamat Email** Anda:"
        )
        return

    # --- TAHAP 2: INPUT EMAIL & FINALISASI ---
    if user_id in WAIT_EMAIL:
        if "@" not in text:
            return await event.reply("❌ Format email salah. Coba lagi (contoh: user@gmail.com).")
            
        data = WAIT_EMAIL.pop(user_id)
        name = data["name"]
        email = text
        is_trial = data.get("is_trial", False)
        
        # --- A. JIKA INI FREE TRIAL ---
        if is_trial:
            # Langsung buat member aktif
            # Expired 1 hari (atau sesuai config)
            expire_date = (datetime.now() + timedelta(days=1)).strftime("%d-%m-%Y")
            
            # Cek apakah user sudah ada (misal status pending/rejected)
            idx, row = find_member_row(user_id)
            if idx:
                # Update yang sudah ada
                update_member_name_email(idx, name, email)
                update_member_status(idx, "Approved", "Trial Activated")
                update_member_expire(idx, expire_date)
            else:
                # Buat baru
                # append_member(user_id, name, email, months=0) -> kita modif sedikit append_member agar return tanggal atau kita set manual
                append_member(user_id, name, email, months=0) # Ini default pending/1 hari
                # Kita paksa update jadi Approved & Expired benar
                idx_new, _ = find_member_row(user_id)
                if idx_new:
                    update_member_status(idx_new, "Approved", "Trial Activated")
                    update_member_expire(idx_new, expire_date)
            
            # Notif ke Admin
            await bot.send_message(ADMIN_ID, f"🎁 **NEW TRIAL USER**\nUser: `{user_id}`\nNama: {name}")
            
            # Notif ke User
            await event.reply(
                f"🎉 **SELAMAT! AKUN AKTIF**\n\n"
                f"👤 Nama: {name}\n"
                f"📧 Email: {email}\n"
                f"📅 Expired: {expire_date} (Trial 1 Hari)\n\n"
                f"Silakan klik menu di bawah untuk menghubungkan Userbot.",
                buttons=[[Button.inline("⚙️ Hubungkan Userbot", b"menu_connect_ub")]]
            )
            return

        # --- B. JIKA INI BERBAYAR ---
        else:
            # Data transaksi
            data_tx = {
                "user_id": user_id,
                "months": data["months"],
                "total": data["total"],
                "is_trial": False
            }
            # Simpan data user ke DB (Status Pending dulu kalau belum ada)
            idx, row = find_member_row(user_id)
            if idx:
                update_member_name_email(idx, name, email)
            else:
                append_member(user_id, name, email, months=0) # Status Pending
            
            # Lanjut ke proses QRIS
            await process_payment_final(event, user_id, name, email, data_tx)
            return

async def process_payment_final(event, user_id, name, email, data_tx):
    tx_id = str(uuid.uuid4())
    pending_tx[tx_id] = data_tx
    pending_tx[tx_id]["name"] = name
    pending_tx[tx_id]["email"] = email
    user_tx_map[user_id] = tx_id
    
    awaiting_photo.add(user_id)
    
    msg = (
        f"💳 **PEMBAYARAN**\n"
        f"👤 Nama: {name}\n"
        f"💰 Total: **{format_rp(data_tx['total'])}**\n\n"
        f"Silakan scan QRIS di bawah ini, lalu **kirim bukti transfer (foto)** di sini."
    )
    
    await event.reply(msg)
    try: 
        await bot.send_file(user_id, "qris.jpg", caption="Scan QRIS ini untuk pembayaran.")
    except: 
        await bot.send_message(user_id, "⚠️ QRIS tidak ditemukan. Hubungi Admin.")

# ==========================================
# HANDLER FOTO BUKTI TRANSFER
# ==========================================
@bot.on(events.NewMessage(incoming=True))
async def payment_proof_handler(event):
    user_id = event.sender_id
    
    # Hanya proses jika user mengirim foto DAN sedang dalam status menunggu bukti
    if event.photo and user_id in awaiting_photo:
        tx_id = user_tx_map.get(user_id)
        if not tx_id: return 

        # Download Foto
        photo = await event.download_media()
        pending_tx[tx_id]["photo_path"] = photo
        
        tx_data = pending_tx[tx_id]
        
        # Kirim ke Admin
        await bot.send_message(
            ADMIN_ID,
            f"📩 **BUKTI TRANSFER BARU**\n"
            f"👤 User: `{user_id}` ({tx_data.get('name')})\n"
            f"💰 Total: {format_rp(tx_data['total'])}\n"
            f"🗓 Durasi: {tx_data['months']} Bulan",
            file=photo,
            buttons=[
                [Button.inline("✅ Terima", f"PAYAPPROVE:{tx_id}"), Button.inline("❌ Tolak", f"PAYREJECT:{tx_id}")]
            ]
        )
        
        # Bersihkan state user
        awaiting_photo.remove(user_id)
        
        await event.reply(
            "✅ **Bukti Diterima!**\n"
            "Mohon tunggu, admin akan memverifikasi pembayaran Anda segera."
        )
        # Jangan stop propagation agar tidak mengganggu handler lain jika ada