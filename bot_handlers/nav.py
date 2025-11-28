# bmcodexbot/bot_handlers/nav.py
from telethon import events, Button
from telethon.errors import MessageNotModifiedError
from config import bot, ADMIN_ID
from database import find_member_row, append_member, update_member_name_email
from state import GLOBAL_CONFIG

# ==========================================
# HELPER: MEMBUAT MENU UTAMA
# ==========================================
def get_main_menu_data(user_id, is_approved=False):
    """
    Mengembalikan teks dan tombol untuk menu utama.
    User ID diperlukan untuk mengecek apakah dia ADMIN atau bukan.
    """
    if is_approved:
        text = (
            "🤖 **BM CODEX USERBOT**\n"
            "Status: ✅ **Premium Aktif**\n\n"
            "Halo! Sistem userbot Anda aktif dan siap digunakan.\n"
            "Gunakan menu di bawah untuk mengatur fitur:"
        )
        
        # --- SUSUNAN TOMBOL USER ---
        buttons = [
            # Baris 1: Koneksi & Setting
            [Button.inline("🔌 Koneksi & Setting", b"menu_connect_ub")],
            
            # Baris 2: Fitur Otomatis
            [Button.inline("💬 Auto Reply", b"menu_autoreply"), Button.inline("📑 Faktur", b"menu_faktur")],
            
            # Baris 3: Spam & Unread
            [Button.inline("📨 Auto Message", b"menu_autospam"), Button.inline("👻 Unread Mode", b"menu_unread")],
            
            # Baris 4: Live Chat
            [Button.inline("📡 Live Chat", b"livechat_menu")]
        ]

        # --- TOMBOL KHUSUS ADMIN (REMOTE APP) ---
        # Hanya muncul jika user adalah ADMIN_ID
        if user_id == ADMIN_ID:
            buttons.append([Button.inline("📱 Remote App (Admin)", b"menu_remote_app")])

        # Baris Terakhir: Akun & Kontak
        buttons.append([Button.inline("👤 Akun Saya", b"my_account"), Button.inline("💲 Perpanjang", b"buy_subscription")])
        buttons.append([Button.inline("📞 Hubungi Admin", b"contact_admin")])

    else:
        text = (
            "👋 **Halo! Selamat Datang di BM CODEX**\n\n"
            "Layanan Userbot Telegram All-in-One.\n"
            "⚠️ **Status:** Belum Aktif / Expired\n\n"
            "Silakan aktifkan akun Anda untuk menggunakan fitur:"
        )
        buttons = [
            [Button.inline("💎 Beli Langganan Premium", b"buy_subscription")],
            [Button.inline("🎁 Coba Free Trial", b"try_free_trial")],
            [Button.inline("📞 Hubungi Admin", b"contact_admin")]
        ]
    
    return text, buttons

# ==========================================
# HANDLER: /START COMMAND
# ==========================================
@bot.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    user_id = event.sender_id
    
    # 1. JIKA ADMIN -> KE DASHBOARD ADMIN
    if user_id == ADMIN_ID:
        from bot_handlers.admin.dashboard import send_admin_dashboard
        await send_admin_dashboard(event)
        return

    # 2. PROSES MEMBER BIASA
    sender = await event.get_sender()
    name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    username = f"@{sender.username}" if sender.username else "-"

    idx, row = find_member_row(user_id)
    
    # Auto Register jika belum ada
    if not row:
        print(f"➕ User Baru: {name} ({user_id})")
        try:
            # Default Pending (0 bulan)
            append_member(user_id, name, username, months=0)
            idx, row = find_member_row(user_id)
        except Exception as e:
            await event.reply("⚠️ Gagal memproses data. Coba lagi nanti.")
            return
    else:
        # Jika user lama start lagi, update nama/username biar data fresh
        try:
            update_member_name_email(idx, name, username) # Asumsi kolom email dipakai username sementara
        except: pass

    # Tentukan Status
    status = row.get("Status", "Pending")
    is_approved = (status == "Approved")
    
    text, buttons = get_main_menu_data(user_id, is_approved)
    await event.reply(text, buttons=buttons)

# ==========================================
# HANDLER: CALLBACK MENU UTAMA
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"menu_start"))
async def cb_menu_start(event):
    user_id = event.sender_id
    
    # Cek jika admin, arahkan ke dashboard admin
    if user_id == ADMIN_ID:
        from bot_handlers.admin.dashboard import send_admin_dashboard
        await send_admin_dashboard(event)
        return

    idx, row = find_member_row(user_id)
    is_approved = (row and row.get("Status") == "Approved")
    
    text, buttons = get_main_menu_data(user_id, is_approved)
    
    try:
        await event.edit(text, buttons=buttons)
    except MessageNotModifiedError: pass

# ==========================================
# HANDLER LAINNYA
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"try_free_trial"))
async def cb_free_trial(event):
    user_id = event.sender_id
    if not GLOBAL_CONFIG.get("free_trial", False):
        return await event.answer("❌ Maaf, Free Trial sedang ditutup.", alert=True)
    
    idx, row = find_member_row(user_id)
    if not row: return await event.answer("⚠️ Data error. Ketik /start ulang.", alert=True)
    if row.get("Status") == "Approved": return await event.answer("✅ Akun Anda sudah aktif!", alert=True)
    
    from database import update_member_status, update_member_expire
    from datetime import datetime, timedelta
    
    # Trial 1 Hari
    new_expire = (datetime.now() + timedelta(days=1)).strftime("%d-%m-%Y")
    update_member_status(idx, "Approved", "Free Trial Claimed")
    update_member_expire(idx, new_expire)
    
    await event.answer("✅ Selamat! Free Trial 1 Hari Aktif.", alert=True)
    await cb_menu_start(event) # Refresh menu

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
    
    status = row.get("Status", "-") if row else "-"
    expired = row.get("Expired", "-") if row else "-"
    
    text = (
        f"👤 **AKUN SAYA**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"🏷 Status: `{status}`\n"
        f"📅 Berakhir pada: `{expired}`"
    )
    await event.edit(text, buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]])