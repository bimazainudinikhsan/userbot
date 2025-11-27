# main.py
import os
import asyncio
import uuid
from datetime import datetime, timedelta

from telethon import TelegramClient, events, Button
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aktif_fitur import start_userbot

# -------------------------
# Load env
# -------------------------
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
SHEET_ID = os.getenv("SHEET_ID")
PRICE_PER_MONTH = int(os.getenv("PRICE_PER_MONTH", "20000"))

# -------------------------
# Google Sheets init
# -------------------------
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gclient = gspread.authorize(creds)
spreadsheet = gclient.open_by_key(SHEET_ID)

# Ensure worksheets exist: Member & History
def ensure_sheets():
    names = [ws.title for ws in spreadsheet.worksheets()]
    if "Member" not in names:
        spreadsheet.add_worksheet(title="Member", rows="1000", cols="20")
        member = spreadsheet.worksheet("Member")
        member.append_row(["User ID", "Nama", "Email", "Status", "Expired", "Join Time"])
    if "History" not in names:
        spreadsheet.add_worksheet(title="History", rows="1000", cols="20")
        history = spreadsheet.worksheet("History")
        history.append_row(["User ID", "Months", "Total", "Status", "Timestamp"])

ensure_sheets()
member_sheet = spreadsheet.worksheet("Member")
history_sheet = spreadsheet.worksheet("History")

# -------------------------
# Telegram client
# -------------------------
bot = TelegramClient("bot_session", API_ID, API_HASH)

# -------------------------
# In-memory states
# -------------------------
pending_tx = {}             # tx_id -> {user_id, months, total, timestamp, photo_path, name?, email?}
user_tx_map = {}            # user_id -> tx_id (current pending tx)
awaiting_photo = set()      # user_id set: currently expected to upload photo

WAIT_NAME = {}              # user_id -> months (when waiting for name)
WAIT_EMAIL = {}             # user_id -> {"name":..., "months":...}
WAIT_PAYMENT_PROOF = {}     # user_id -> {"name","email","months","tx_id"}

# -------------------------
# Helper functions for sheet operations
# -------------------------
def find_member_row(user_id_str):
    """Return (idx, row_dict) or (None, None)"""
    records = member_sheet.get_all_records()
    for idx, row in enumerate(records, start=2):
        if str(row.get("User ID")) == str(user_id_str):
            return idx, row
    return None, None

def append_member(user_id, name="-", email="-", months=1):
    join_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    expire = (datetime.now() + timedelta(days=30 * months)).strftime("%d-%m-%Y")
    member_sheet.append_row([str(user_id), name, email, "Approved", expire, join_time])
    return expire

def update_member_expire(row_idx, new_expire_str):
    # Status at col 4 (Status), Expired at col 5 (Expired) per header
    member_sheet.update_cell(row_idx, 4, "Approved")
    member_sheet.update_cell(row_idx, 5, new_expire_str)

def update_member_name_email(row_idx, name, email):
    # Nama col 2, Email col 3
    member_sheet.update_cell(row_idx, 2, name)
    member_sheet.update_cell(row_idx, 3, email)

def log_history(user_id, months, total, status):
    ts = datetime.now().strftime("%d-%m-%Y %H:%M")
    history_sheet.append_row([str(user_id), str(months), str(total), status, ts])

def format_rp(n):
    return f"Rp {n:,}"

# -------------------------
# Commands & UI
# -------------------------
@bot.on(events.NewMessage(pattern="/start"))
async def handler_start(event):
    await event.respond(
        "👋 Selamat datang!\nPilih menu:",
        buttons=[
            [Button.inline("🔐 Aktivasi/Perpanjang Membership", b"menu_buy")],
            [Button.inline("📊 Cek Status", b"menu_status")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=b"menu_status"))
async def cb_status(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    if not row:
        await event.edit("❌ Kamu belum memiliki membership. Tekan Aktivasi untuk mulai.", buttons=[[Button.inline("🔐 Aktivasi", b"menu_buy")]])
        return
    expired = row.get("Expired", "-")
    status = row.get("Status", "-")
    await event.edit(f"📊 Status Member\n\nUser ID: {user_id}\nStatus: {status}\nExpired: {expired}")

@bot.on(events.CallbackQuery(pattern=b"menu_buy"))
async def cb_menu_buy(event):
    user_id = event.sender_id
    # initialize tmp tx
    tmp_key = f"tmp_{user_id}"
    # clear previous tmp if exists
    pending_tx.pop(tmp_key, None)
    pending_tx[tmp_key] = {"user_id": user_id, "months": 1, "total": PRICE_PER_MONTH, "timestamp": datetime.now().isoformat()}
    user_tx_map[user_id] = tmp_key
    await event.edit(
        f"📅 Perpanjang / Aktivasi Membership\nDurasi: 1 bulan\nTotal: {format_rp(PRICE_PER_MONTH)}",
        buttons=[
            [Button.inline("➖", b"minus_1"), Button.inline("1 Bulan", b"month_1"), Button.inline("➕", b"plus_1")],
            [Button.inline("💳 Lanjut ke Pembayaran", b"to_pay")]
        ]
    )

# Month selection callbacks (operate on tmp_{user_id})
@bot.on(events.CallbackQuery(pattern=b"minus_1|plus_1|month_1"))
async def cb_months(event):
    user_id = event.sender_id
    data = event.data.decode()
    tmp = f"tmp_{user_id}"
    if tmp not in pending_tx:
        pending_tx[tmp] = {"user_id": user_id, "months": 1, "total": PRICE_PER_MONTH, "timestamp": datetime.now().isoformat()}
        user_tx_map[user_id] = tmp
    
    old_current = pending_tx[tmp]["months"]
    current = old_current

    if data.startswith("minus"):
        current = max(1, current - 1)
    elif data.startswith("plus"):
        current = current + 1
    elif data.startswith("month"):
        current = int(data.split("_")[1])

    if old_current == current:
        await event.answer()
        return

    pending_tx[tmp]["months"] = current
    pending_tx[tmp]["total"] = current * PRICE_PER_MONTH
    
    await event.edit(
        f"📅 Perpanjang / Aktivasi Membership\nDurasi: {current} bulan\nTotal: {format_rp(pending_tx[tmp]['total'])}",
        buttons=[
            [Button.inline("➖", b"minus_1"), Button.inline(f"{current} Bulan", f"month_{current}".encode()), Button.inline("➕", b"plus_1")],
            [Button.inline("💳 Lanjut ke Pembayaran", b"to_pay")]
        ]
    )

# Go to payment: check name/email; if absent -> ask; else send qris and request photo
@bot.on(events.CallbackQuery(pattern=b"to_pay"))
async def cb_to_pay(event):
    user_id = event.sender_id
    tmp = f"tmp_{user_id}"
    if tmp not in pending_tx:
        await event.answer("Terjadi error. Coba lagi.", alert=True)
        return
    months = pending_tx[tmp]["months"]
    total = pending_tx[tmp]["total"]

    # check member record
    idx, row = find_member_row(user_id)
    needs_info = True
    if row:
        name = row.get("Nama", "-")
        email = row.get("Email", "-")
        # if both exist (not "-"), no need to ask
        if name and name != "-" and email and email != "-":
            needs_info = False

    if needs_info:
        # ask name first
        WAIT_NAME[user_id] = {"months": months, "total": total}
        await event.edit("📝 Sebelum melanjutkan, silakan kirim *Nama lengkap* Anda.", parse_mode="markdown")
        return

    # else proceed to payment
    tx_id = str(uuid.uuid4())
    pending_tx[tx_id] = pending_tx.pop(tmp)
    user_tx_map[user_id] = tx_id
    awaiting_photo.add(user_id)
    # store existing name/email to tx
    pending_tx[tx_id]["name"] = name
    pending_tx[tx_id]["email"] = email
    await event.edit(f"💳 Total: {format_rp(total)}\nSilakan scan QR di bawah lalu upload foto bukti transfer (kirim sebagai foto, bukan file).")
    try:
        await bot.send_file(user_id, "qris.jpg", caption=f"📸 Scan QR untuk bayar\nTotal: {format_rp(total)}")
    except Exception:
        await bot.send_message(user_id, "⚠ Gagal kirim QR. Pastikan qris.jpg berada di folder yang sama dengan main.py.")
    await bot.send_message(user_id, "📤 Setelah bayar, upload *foto bukti transfer* di sini.", parse_mode="markdown")

# Helper to continue to payment after collecting name/email
async def continue_to_payment_after_info(user_id):
    # tmp might be converted already or not
    tmp = f"tmp_{user_id}"
    # if tmp still exists, convert
    if tmp in pending_tx:
        tx_id = str(uuid.uuid4())
        pending_tx[tx_id] = pending_tx.pop(tmp)
        user_tx_map[user_id] = tx_id
    else:
        # try find tx for user
        tx_id = None
        for tid, v in pending_tx.items():
            if v.get("user_id") == user_id:
                tx_id = tid
                break
        if not tx_id:
            # create one from WAIT_PAYMENT_PROOF
            return False

    tx = pending_tx[tx_id]
    months = tx["months"]
    total = tx["total"]
    # take name/email from WAIT_PAYMENT_PROOF if available
    info = WAIT_PAYMENT_PROOF.get(user_id, {})
    name = info.get("name")
    email = info.get("email")
    if name:
        tx["name"] = name
    if email:
        tx["email"] = email

    awaiting_photo.add(user_id)
    # send QR + instruction
    try:
        await bot.send_file(user_id, "qris.jpg", caption=f"📸 Scan QR untuk bayar\nTotal: {format_rp(total)}")
    except Exception:
        await bot.send_message(user_id, "⚠ Gagal kirim QR. Pastikan qris.jpg berada di folder yang sama dengan main.py.")
    await bot.send_message(user_id, "📤 Setelah bayar, upload *foto bukti transfer* di sini.", parse_mode="markdown")
    return True

# -------------------------
# Single NewMessage handler: handles name, email, photo, and non-photo while awaiting
# -------------------------
@bot.on(events.NewMessage)
async def generic_message_handler(event):
    user_id = event.sender_id
    message_text = (event.raw_text or "").strip()

    # 1) If waiting for name
    if user_id in WAIT_NAME:
        # accept text as name
        name = message_text
        months = WAIT_NAME[user_id]["months"]
        total = WAIT_NAME[user_id]["total"]
        WAIT_EMAIL[user_id] = {"name": name, "months": months, "total": total}
        del WAIT_NAME[user_id]
        await event.reply("📨 Terima kasih. Sekarang kirim *Email* Anda.", parse_mode="markdown")
        return

    # 2) If waiting for email
    if user_id in WAIT_EMAIL:
        email = message_text
        data = WAIT_EMAIL.pop(user_id)
        name = data["name"]
        months = data["months"]
        total = data["total"]

        # basic email validation
        if "@" not in email or "." not in email:
            WAIT_EMAIL[user_id] = data  # put back
            await event.reply("❌ Format email tidak valid. Silakan kirim email yang benar.")
            return

        # store into WAIT_PAYMENT_PROOF so photo handler can pick up
        WAIT_PAYMENT_PROOF[user_id] = {"name": name, "email": email, "months": months, "total": total}
        # also ensure tmp tx exists
        tmp = f"tmp_{user_id}"
        if tmp not in pending_tx:
            pending_tx[tmp] = {"user_id": user_id, "months": months, "total": total, "timestamp": datetime.now().isoformat()}
            user_tx_map[user_id] = tmp

        await event.reply(f"✅ Terima kasih. Total: {format_rp(total)}.")
        try:
            await bot.send_file(user_id, "qris.jpg", caption=f"📸 Scan QR untuk bayar\nTotal: {format_rp(total)}")
        except Exception:
            await bot.send_message(user_id, "⚠ Gagal kirim QR. Pastikan qris.jpg berada di folder yang sama dengan main.py.")
        
        await bot.send_message(user_id, "📤 Setelah bayar, upload *foto bukti transfer* di sini.", parse_mode="markdown")
        awaiting_photo.add(user_id)

        return

    # 3) If event contains photo
    if event.photo:
        # only accept if user is expected to upload photo
        if user_id not in awaiting_photo and user_id not in WAIT_PAYMENT_PROOF:
            await event.reply("❗ Kamu tidak sedang melakukan pembayaran. Ketik /start untuk mulai.")
            return

        # If user had not yet been converted to tx id, convert now
        tx_id = user_tx_map.get(user_id)
        if tx_id is None:
            # try tmp key
            tmp = f"tmp_{user_id}"
            if tmp in pending_tx:
                tx_id = str(uuid.uuid4())
                pending_tx[tx_id] = pending_tx.pop(tmp)
                user_tx_map[user_id] = tx_id
            else:
                # create default tx using WAIT_PAYMENT_PROOF or default months=1
                data = WAIT_PAYMENT_PROOF.get(user_id, {})
                months = data.get("months", 1)
                total = data.get("total", months * PRICE_PER_MONTH)
                tx_id = str(uuid.uuid4())
                pending_tx[tx_id] = {"user_id": user_id, "months": months, "total": total, "timestamp": datetime.now().isoformat()}
                user_tx_map[user_id] = tx_id

        # download photo
        photo_path = await event.download_media()
        pending_tx[tx_id]["photo_path"] = photo_path
        pending_tx[tx_id]["photo_ts"] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

        # If name/email available from WAIT_PAYMENT_PROOF, attach and save to member sheet preemptively
        info = WAIT_PAYMENT_PROOF.pop(user_id, {})
        name = info.get("name")
        email = info.get("email")
        if name or email:
            pending_tx[tx_id]["name"] = name or "-"
            pending_tx[tx_id]["email"] = email or "-"
            # write/update member row pre-approval with status Pending
            idx, row = find_member_row(user_id)
            if idx:
                # update name/email if blank
                try:
                    if (row.get("Nama") in [None, "-", ""] ) and name:
                        update_member_name_email(idx, name, row.get("Email", "-"))
                    if (row.get("Email") in [None, "-", ""]) and email:
                        update_member_name_email(idx, row.get("Nama", "-"), email)
                    # set status to Pending
                    member_sheet.update_cell(idx, 4, "Pending")
                except Exception:
                    pass
            else:
                # append pending member with provided data
                join_time = datetime.now().strftime("%d-%m-%Y %H:%M")
                expire_placeholder = "-"  # will be set after approval
                member_sheet.append_row([str(user_id), name or "-", email or "-", "Pending", expire_placeholder, join_time])

        # forward to admin
        try:
            await event.forward_to(ADMIN_ID)
        except Exception:
            # fallback to sending file
            await bot.send_file(ADMIN_ID, photo_path)

        months = pending_tx[tx_id].get("months", 1)
        total = pending_tx[tx_id].get("total", months * PRICE_PER_MONTH)

        # send admin message with approve/reject including tx_id
        await bot.send_message(
            ADMIN_ID,
            f"📩 Bukti Pembayaran Baru\n\nUser: {user_id}\nDurasi: {months} bulan\nTotal: {format_rp(total)}\nWaktu: {pending_tx[tx_id]['photo_ts']}",
            buttons=[[Button.inline("✔ Approve", f"PAYAPPROVE:{tx_id}"), Button.inline("❌ Reject", f"PAYREJECT:{tx_id}")]]
        )

        # notify user
        awaiting_photo.add(user_id)  # keep until admin acts
        await event.reply("✅ Bukti transfer berhasil dikirim ke admin. Menunggu verifikasi.")
        return

    # 4) Non-photo message while awaiting photo -> reject politely
    if user_id in awaiting_photo:
        # If not photo, prompt to upload photo
        await event.reply("❗ Silakan upload *foto bukti transfer* (bukan teks).", parse_mode="markdown")
        return

    # Otherwise ignore or let other handlers (e.g., /start) act
    return

# -------------------------
# Admin Approve / Reject callbacks
# -------------------------
@bot.on(events.CallbackQuery(pattern=b"PAYAPPROVE:|PAYREJECT:"))
async def cb_admin_pay(event):
    data = event.data.decode()
    if data.startswith("PAYAPPROVE:"):
        tx_id = data.split(":", 1)[1]
        tx = pending_tx.get(tx_id)
        if not tx:
            await event.answer("Transaksi tidak ditemukan atau sudah diproses.", alert=True)
            return

        user_id = tx["user_id"]
        months = tx.get("months", 1)
        total = tx.get("total", months * PRICE_PER_MONTH)
        name = tx.get("name", "-")
        email = tx.get("email", "-")

        # Find member row
        idx, row = find_member_row(user_id)
        if idx:
            # parse existing expire
            try:
                exp_dt = datetime.strptime(row.get("Expired", ""), "%d-%m-%Y")
            except Exception:
                exp_dt = datetime.now()
            now = datetime.now()
            base = now if now > exp_dt else exp_dt
            new_exp = base + timedelta(days=30 * months)
            new_exp_str = new_exp.strftime("%d-%m-%Y")
            update_member_expire(idx, new_exp_str)
            # update name/email if provided and blank
            try:
                if name and row.get("Nama") in [None, "-", ""]:
                    update_member_name_email(idx, name, row.get("Email", "-"))
                if email and row.get("Email") in [None, "-", ""]:
                    update_member_name_email(idx, row.get("Nama", "-"), email)
            except Exception:
                pass
        else:
            # create new member
            new_exp_str = append_member(user_id, name=name or "-", email=email or "-", months=months)

        # Log history
        log_history(user_id, months, total, "Approved")

        # Clean state
        pending_tx.pop(tx_id, None)
        # remove mapping user->tx if exists
        for k, v in list(user_tx_map.items()):
            if v == tx_id:
                user_tx_map.pop(k, None)
                awaiting_photo.discard(k)
        # inform user & edit admin msg
        await bot.send_message(user_id, f"🎉 Pembayaran diterima! Masa aktif diperpanjang hingga {new_exp_str}")
        await bot.send_message(user_id, "Fitur premium Anda telah diaktifkan.")
        await event.edit("✔ Pembayaran disetujui dan membership diperbarui.")
        return

    if data.startswith("PAYREJECT:"):
        tx_id = data.split(":", 1)[1]
        tx = pending_tx.get(tx_id)
        if not tx:
            await event.answer("Transaksi tidak ditemukan atau sudah diproses.", alert=True)
            return
        user_id = tx["user_id"]
        months = tx.get("months", 1)
        total = tx.get("total", months * PRICE_PER_MONTH)

        # Log rejection
        log_history(user_id, months, total, "Rejected")

        # Clean state
        pending_tx.pop(tx_id, None)
        for k, v in list(user_tx_map.items()):
            if v == tx_id:
                user_tx_map.pop(k, None)
                awaiting_photo.discard(k)

        # inform parties
        await bot.send_message(user_id, "❌ Pembayaran ditolak oleh admin. Silakan upload bukti ulang jika sudah membayar.")
        await event.edit("❌ Pembayaran ditolak.")
        return

# -------------------------
# Run bot
# -------------------------
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot running...")

    USER_SESSION_STRING = os.getenv("USER_SESSION_STRING")
    if USER_SESSION_STRING:
        print("Starting global userbot...")
        try:
            # We use ADMIN_ID as a placeholder user_id for the global userbot
            asyncio.create_task(start_userbot(API_ID, API_HASH, USER_SESSION_STRING, ADMIN_ID))
        except Exception as e:
            print(f"Could not start global userbot: {e}")
    else:
        print("WARNING: USER_SESSION_STRING not found in .env file. Global userbot not started.")

    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
