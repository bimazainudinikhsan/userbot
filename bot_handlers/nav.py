# bmcodexbot/bot_handlers/nav.py
from telethon import events, Button
from telethon.errors import MessageNotModifiedError
from config import bot, ADMIN_ID
from database import find_member_row
from state import GLOBAL_CONFIG, WAIT_NAME

# ==========================================
# HELPER: MEMBUAT MENU UTAMA
# ==========================================
def get_main_menu_data(user_id, is_approved=False):
    if is_approved:
        text = (
            "🤖 **BM CODEX USERBOT**\n"
            "Status: ✅ **Premium Aktif**\n\n"
            "Halo! Sistem userbot Anda aktif dan siap digunakan.\n"
            "Gunakan menu di bawah untuk mengatur fitur:"
        )
        buttons = [
            [Button.inline("🔌 Koneksi & Setting", b"menu_connect_ub")],
            [Button.inline("💬 Auto Reply", b"menu_autoreply"), Button.inline("📑 Faktur", b"menu_faktur")],
            [Button.inline("📨 Auto Message", b"menu_autospam"), Button.inline("👻 Unread Mode", b"menu_unread")],
            [Button.inline("📡 Live Chat", b"livechat_menu")]
        ]
        if user_id == ADMIN_ID:
            buttons.append([Button.inline("📱 Remote App (Admin)", b"menu_remote_app")])

        buttons.append([Button.inline("👤 Akun Saya", b"my_account"), Button.inline("💲 Perpanjang", b"buy_subscription")])
        buttons.append([Button.inline("📞 Hubungi Admin", b"contact_admin")])

    else:
        text = (
            "👋 **Halo! Selamat Datang di BM CODEX**\n\n"
            "Layanan Userbot Telegram All-in-One.\n"
            "⚠️ **Status:** Belum Terdaftar / Expired\n\n"
            "Silakan daftar atau aktifkan akun Anda:"
        )
        buttons = [
            [Button.inline("💎 Beli Premium", b"buy_subscription")],
            [Button.inline("🎁 Daftar Free Trial", b"try_free_trial")],
            [Button.inline("📞 Hubungi Admin", b"contact_admin")]
        ]
    
    return text, buttons

# ==========================================
# HANDLER: /START COMMAND
# ==========================================
@bot.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    user_id = event.sender_id
    
    if user_id == ADMIN_ID:
        from bot_handlers.admin.dashboard import send_admin_dashboard
        await send_admin_dashboard(event)
        return

    # --- PERBAIKAN DI SINI ---
    # Kita HAPUS logika otomatis append_member.
    # Kita hanya cek apakah dia ada atau tidak.
    
    idx, row = find_member_row(user_id)
    
    # Jika row ada dan status Approved, maka aktif.
    # Jika row tidak ada, atau status bukan Approved, anggap belum aktif.
    is_approved = False
    if row and row.get("Status") == "Approved":
        is_approved = True

    text, buttons = get_main_menu_data(user_id, is_approved)
    await event.reply(text, buttons=buttons)

# ==========================================
# HANDLER: CALLBACK MENU UTAMA
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"menu_start"))
async def cb_menu_start(event):
    user_id = event.sender_id
    if user_id == ADMIN_ID:
        from bot_handlers.admin.dashboard import send_admin_dashboard
        await send_admin_dashboard(event)
        return

    idx, row = find_member_row(user_id)
    is_approved = (row and row.get("Status") == "Approved")
    
    text, buttons = get_main_menu_data(user_id, is_approved)
    try: await event.edit(text, buttons=buttons)
    except MessageNotModifiedError: pass

# ==========================================
# HANDLER TOMBOL TRIAL (MASUK INPUT NAMA)
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"try_free_trial"))
async def cb_free_trial(event):
    user_id = event.sender_id
    
    # Cek Config Global
    if not GLOBAL_CONFIG.get("free_trial", False):
        return await event.answer("❌ Maaf, Free Trial sedang ditutup.", alert=True)
    
    # Cek apakah user sudah terdaftar aktif
    idx, row = find_member_row(user_id)
    if row and row.get("Status") == "Approved":
        return await event.answer("✅ Akun Anda sudah aktif!", alert=True)
    
    # --- MASUK KE PROSES INPUT NAMA ---
    # Kita set state agar bot menunggu input nama
    WAIT_NAME[user_id] = {
        "is_trial": True,  # Penanda ini jalur trial
        "months": 0,
        "total": 0
    }
    
    await event.edit(
        "🎁 **PENDAFTARAN FREE TRIAL**\n\n"
        "Silakan masukkan data diri Anda untuk aktivasi.\n\n"
        "1️⃣ Silakan ketik **Nama Lengkap** Anda:",
        buttons=[[Button.inline("❌ Batal", b"menu_start")]]
    )

@bot.on(events.CallbackQuery(pattern=b"contact_admin"))
async def cb_contact_admin(event):
    await event.edit(
        "📞 **HUBUNGI ADMIN**\n\n"
        "Silakan hubungi: @danzx_9\n"
        "Untuk bantuan, pembayaran, atau laporan bug.",
        buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]]
    )

@bot.on(events.CallbackQuery(pattern=b"my_account"))
async def cb_my_account(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    
    status = row.get("Status", "-") if row else "Belum Terdaftar"
    expired = row.get("Expired", "-") if row else "-"
    nama = row.get("Nama", "-") if row else "-"
    
    text = (
        f"👤 **AKUN SAYA**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"🏷 Nama: `{nama}`\n"
        f"🛡 Status: `{status}`\n"
        f"📅 Berakhir pada: `{expired}`"
    )
    await event.edit(text, buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]])