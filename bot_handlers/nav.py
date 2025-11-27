# bmcodexbot/bot_handlers/nav.py
import time
from telethon import events, Button
from config import bot, ADMIN_ID
from database import find_member_row
from .admin import show_admin_dashboard
from modules.autoreply import get_user_settings
from modules.faktur import show_setting_menu # IMPORT FUNGSI DARI FAKTUR
from state import ACTIVE_USERBOTS

# ==========================================
# FUNGSI HELPER
# ==========================================

def get_main_menu_data(is_member):
    if is_member:
        text = (
            "👋 **Selamat datang di Clear Virus Bot!**\n\n"
            "Berikut adalah daftar fitur canggih yang siap membantu Anda. "
            "Silakan pilih menu di bawah untuk melihat panduan penggunaan:\n\n"
            "📄 **INVOICE OTOMATIS**\n"
            "Buat faktur PDF profesional secara instan dengan template custom.\n\n"
            "🤖 **AUTO REPLY PINTAR**\n"
            "Balas pesan pribadi otomatis (Teks/Gambar) saat Anda sibuk.\n\n"
            "🧠 **SPAM AI HYBRID (BARU!)**\n"
            "Spam cerdas yang mempelajari gaya bahasa grup target & reply member lain secara natural.\n\n"
            "⚡ **STATUS & DIAGNOSTIK**\n"
            "Cek koneksi ping, status userbot, dan masa aktif akun Anda.\n"
        )
        buttons = [
            [Button.inline("📄 Buat Invoice", b"ub_faktur"), Button.inline("🤖 Auto Reply", b"ub_autoreply")],
            [Button.inline("🧠 Spam AI Hybrid", b"ub_spamai"), Button.inline("🤖 Spam Biasa", b"ub_spam")],
            [Button.inline("🏓 Cek Ping", b"ub_ping"), Button.inline("⚡ Status Bot", b"ub_alive")],
            [Button.inline("⚙️ Setting & Koneksi", b"menu_connect_ub")],
            [Button.inline("📊 Cek Status Akun", b"menu_status")],
            [Button.inline("💬 Hubungi Admin (Live Chat)", b"start_livechat")]
        ]
    else:
        text = (
            "👋 **Selamat datang di Bot Manager!**\n\n"
            "Status Anda: **Belum Terdaftar / Non-Aktif**\n"
            "Silakan pilih menu di bawah untuk mulai berlangganan:"
        )
        buttons = [
            [Button.inline("🔐 Aktivasi/Perpanjang Membership", b"menu_buy")],
            [Button.inline("⚙️ Hubungkan Userbot", b"menu_connect_ub")],
            [Button.inline("📊 Cek Status", b"menu_status")],
            [Button.inline("💬 Hubungi Admin", b"start_livechat")]
        ]
    
    return text, buttons

# ==========================================
# 1. LOGIKA MENU /START
# ==========================================

@bot.on(events.NewMessage(pattern="/start"))
async def handler_start(event):
    user_id = event.sender_id
    if user_id == ADMIN_ID:
        await show_admin_dashboard(event)
        return

    idx, row = find_member_row(user_id)
    is_member = row and row.get("Status") == "Approved"
    text, buttons = get_main_menu_data(is_member)
    await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"menu_start"))
async def cb_back_main(event):
    user_id = event.sender_id
    if user_id == ADMIN_ID:
        await show_admin_dashboard(event)
        return

    idx, row = find_member_row(user_id)
    is_member = row and row.get("Status") == "Approved"
    text, buttons = get_main_menu_data(is_member)
    
    if hasattr(event, 'edit'):
        await event.edit(text, buttons=buttons)
    else:
        await event.respond(text, buttons=buttons)

# ==========================================
# 3. MENU SETTING & KONEKSI
# ==========================================

@bot.on(events.CallbackQuery(pattern=b"menu_connect_ub"))
async def cb_connect_ub_menu(event):
    user_id = event.sender_id
    
    # Ambil Status Auto Reply
    settings = get_user_settings(user_id)
    ar_status = "✅ ON" if settings.get("auto_reply") else "❌ OFF"
    
    # Cek Koneksi Userbot (Ping)
    client = ACTIVE_USERBOTS.get(user_id)
    
    ping_ms = "N/A"
    ub_status = "🔴 Offline"
    
    if client:
        if client.is_connected():
            ub_status = "🟢 Online"
            # Hitung Ping Sederhana
            start = time.perf_counter()
            try:
                await client.get_me()
                end = time.perf_counter()
                ping_ms = f"{(end - start) * 1000:.0f}ms"
            except:
                ping_ms = "Timeout"
        else:
            ub_status = "🟡 Terputus"

    text = (
        f"⚙️ **PENGATURAN & KONEKSI**\n\n"
        f"🤖 Auto Reply: **{ar_status}**\n"
        f"📡 Status Userbot: **{ub_status}**\n"
        f"📶 Koneksi Ping: **{ping_ms}**\n\n"
        f"👇 Klik tombol di bawah untuk mengubah:"
    )
    
    buttons = [
        [Button.inline("🔌 Hubungkan/Ganti Akun", b"start_auth_process")],
        [Button.inline(f"Auto Reply: {ar_status}", b"quick_toggle_ar")],
        [Button.inline("🔄 Cek Koneksi Sekarang", b"menu_connect_ub")],
        [Button.inline("⬅️ Kembali", b"menu_start")]
    ]
    
    try:
        await event.edit(text, buttons=buttons)
    except Exception:
        # Ignore if message not modified (user spam click refresh)
        await event.answer("✅ Status sudah paling update.")

# Handler Quick Toggle Auto Reply di Menu Setting
@bot.on(events.CallbackQuery(pattern=b"quick_toggle_ar"))
async def cb_quick_toggle_ar(event):
    user_id = event.sender_id
    settings = get_user_settings(user_id)
    settings["auto_reply"] = not settings.get("auto_reply")
    if settings["auto_reply"]: settings["replied_chats"] = set()
    
    # Refresh menu
    await cb_connect_ub_menu(event)

# ==========================================
# 4. HANDLER INFO FITUR & STATUS LAINNYA
# ==========================================

# Handler khusus untuk tombol trigger .set_faktur
@bot.on(events.CallbackQuery(pattern=b"trigger_set_faktur"))
async def cb_trigger_set_faktur(event):
    user_id = event.sender_id
    # Langsung panggil fungsi menu setting dari modules/faktur.py
    # Ini akan mengedit pesan saat ini menjadi menu setting faktur
    await show_setting_menu(event, user_id)

@bot.on(events.CallbackQuery(pattern=r"ub_(.+)"))
async def cb_feature_details(event):
    data = event.data.decode()
    feature = data.split("_")[1]
    
    help_text = ""
    custom_buttons = None # Default buttons (Back only)
    
    if feature == "faktur":
        # --- UPDATE REQUEST: CARA PAKAI DI ATAS, TOMBOL SETTING DI BAWAH ---
        help_text = (
            "📄 **PANDUAN INVOICE OTOMATIS**\n\n"
            "**Cara Penggunaan:**\n"
            "1️⃣ Ketik command `.faktur` di chat manapun (PC/Grup).\n"
            "2️⃣ Bot akan meminta screenshot bukti transfer.\n"
            "3️⃣ Ikuti langkah selanjutnya (Input Nama -> Email -> No HP).\n"
            "4️⃣ PDF Faktur akan otomatis terkirim.\n\n"
            "👇 **Klik tombol di bawah untuk mengatur template:**"
        )
        custom_buttons = [
            [Button.inline("⚙️ Setting Faktur (.set_faktur)", b"trigger_set_faktur")],
            [Button.inline("⬅️ Kembali", b"menu_start")]
        ]

    elif feature == "autoreply":
        help_text = (
            "🤖 **FITUR AUTO REPLY (MEDIA)**\n\n"
            "Bot membalas pesan masuk (PC) otomatis saat Anda sibuk.\n\n"
            "**1. On/Off:** Ketik `.autoreply`\n"
            "**2. Setup:**\n"
            "• Teks: `.set_autoreply Pesan..`\n"
            "• Media: Reply gambar/file -> `.set_autoreply <caption opsional>`"
        )
    elif feature == "ping":
        help_text = (
            "🏓 **CEK PING**\n\n"
            "Mengetahui latency userbot ke Server Telegram.\n\n"
            "**Cara Pakai:**\n"
            "Ketik `.ping` di chat manapun."
        )
    elif feature == "alive":
        help_text = (
            "⚡ **STATUS BOT**\n\n"
            "Mengecek status aktif userbot.\n\n"
            "**Cara Pakai:**\n"
            "Ketik `.alive` di chat manapun."
        )
    elif feature == "spam":
        help_text = (
            "🤖 **SPAM BIASA (CONFIG)**\n\n"
            "Spam pesan random ke grup/chat menggunakan list pesan yang sudah diatur.\n\n"
            "**1. Konfigurasi:**\n"
            "Ketik `.set_spambot` untuk atur list pesan & delay.\n\n"
            "**2. Eksekusi:**\n"
            "`.spambot <target> <jumlah>`"
        )
    elif feature == "spamai":
        help_text = (
            "🧠 **SPAM AI HYBRID (RECOMMENDED)**\n\n"
            "Spam cerdas yang menggabungkan pesan manual Anda dengan kalimat yang dipelajari dari grup target.\n\n"
            "**Fitur Unggulan:**\n"
            "✅ Auto Reply member lain (Bukan monolog)\n"
            "✅ Bahasa natural (Mengikuti gaya grup)\n"
            "✅ Delay Acak (Anti-Ban)\n\n"
            "**Cara Pakai:**\n"
            "`.spamai <target> <min-max> <jumlah> <pesan_anda>`\n\n"
            "**Contoh:**\n"
            "`.spamai @grup_jodoh 5-10 50 Halo bang boleh kenalan`"
        )
    else:
        help_text = "⚠️ Info tidak ditemukan."

    # Gunakan custom buttons jika ada (untuk faktur), jika tidak gunakan default back
    if custom_buttons:
        buttons = custom_buttons
    else:
        buttons = [[Button.inline("⬅️ Kembali", b"menu_start")]]

    await event.edit(help_text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"menu_status"))
async def cb_status(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    
    if not row: 
        return await event.edit("❌ Belum member.", buttons=[[Button.inline("🔙 Kembali", b"menu_start")]])
    
    ub_status = "🟢 Online" if user_id in ACTIVE_USERBOTS else "🔴 Offline"
    
    text = (
        f"📊 **STATUS MEMBER**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Nama: {row.get('Nama')}\n"
        f"🛡 Status: **{row.get('Status')}**\n"
        f"🤖 Userbot: {ub_status}\n"
        f"📅 Expired: {row.get('Expired')}"
    )
    await event.edit(text, buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]])