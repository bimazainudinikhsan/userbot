# bmcodexbot/bot_handlers/nav.py
from datetime import datetime, timedelta
from telethon import events, Button
import os, json
import logging
from telethon.errors import MessageNotModifiedError
from config import bot, ADMIN_ID
from database import (
    find_member_row, 
    append_member, 
    update_member_status, 
    update_member_name_email, 
    update_member_data 
)
# Gunakan GLOBAL_CONFIG untuk cek on/off fitur trial
from state import GLOBAL_FEATURE_FLAGS, WAIT_NAME, GLOBAL_CONFIG, ACTIVE_USERBOTS

# --- IMPORT MODULES ---
from modules.unread import (
    get_settings as get_ur_settings, 
    update_settings as update_ur_settings,
    is_unread_mode_enabled,
    set_unread_mode,
    ACTIVE_UNREAD_TASKS
)
from modules.auto_spam import get_settings as get_as_settings, update_setting as update_as_setting

# Backward compatibility
def update_ur_message(user_id, message):
    return update_ur_settings(user_id, {"message": message})

try:
    from modules.faktur import show_setting_menu as show_faktur_settings
except ImportError:
    show_faktur_settings = None

NAV_EDIT_STATE = {}
def read_auto_message_logs(user_id, limit=10):
    entries = []
    try:
        if os.path.exists("auto_message.log"):
            with open("auto_message.log", "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line.strip())
                        if str(obj.get("user_id")) == str(user_id):
                            entries.append(obj)
                    except:
                        pass
        entries = entries[-limit:]
    except:
        entries = []
    return entries

def compute_auto_message_stats(user_id):
    logs = read_auto_message_logs(user_id, limit=100)
    total = len(logs)
    ok = sum(1 for x in logs if x.get("status") == "ok")
    err = sum(1 for x in logs if x.get("status") == "error")
    latencies = [x.get("latency_ms") for x in logs if isinstance(x.get("latency_ms"), int)]
    avg = int(sum(latencies)/len(latencies)) if latencies else 0
    last = logs[-1] if logs else {}
    return {"total": total, "ok": ok, "err": err, "avg": avg, "last": last}

# ==========================================
# HELPER: MENU UTAMA
# ==========================================
def get_main_menu_data(user_id, row=None):
    nama = "-"
    email = "-"
    expired_str = "-"
    remaining_days = "0"
    is_approved = False

    if row:
        if row.get("Status") == "Approved":
            is_approved = True
        
        nama = row.get("Nama", "-")
        email = row.get("Email", "-")
        expired_str = row.get("Expired", "-")
        
        try:
            exp_date = datetime.strptime(expired_str, "%d-%m-%Y")
            delta = exp_date - datetime.now()
            remaining_days = str(max(0, delta.days))
        except:
            remaining_days = "-"

    # --- MENU MEMBER PREMIUM ---
    if is_approved:
        is_online = bool(user_id in ACTIVE_USERBOTS)
        if is_online:
            text = (
                "🎛 **CONTROL PANEL CLEAR VIRUS**\n"
                "➖➖➖➖➖➖➖➖➖➖\n"
                f"👤 **User ID:** `{user_id}`\n"
                f"💎 **Status:** `Premium Active` ✅\n"
                f"🏷 **Nama:** `{nama}`\n"
                f"📧 **Email:** `{email}`\n"
                f"📅 **Berakhir:** `{expired_str}`\n"
                f"⏳ **Sisa:** `{remaining_days} Hari`\n\n"
                "Silakan pilih fitur yang ingin diatur:"
            )
            buttons = [
                [Button.inline("🔌 KONEKSI & STATUS", b"menu_connect_ub")],
                [Button.inline("🔔 Unread Mode", b"menu_unread"), Button.inline("📨 Auto Message", b"menu_autospam")],
                [Button.inline("🤖 Spam & AI", b"spam_menu")],
                [Button.inline("📑 Buat Faktur", b"menu_faktur")],
            ]
            if user_id == ADMIN_ID:
                buttons.append([Button.inline("📱 Remote App (Admin)", b"menu_remote_app")])
            buttons.append([Button.inline("📡 Live Chat Support", b"livechat_menu")])
        else:
            text = (
                "🟥 **HUBUNGKAN KE USERBOT**\n"
                "➖➖➖➖➖➖➖➖➖➖\n"
                f"🆔 ID: `{user_id}`\n"
                f"🏷 Nama: **{nama}**\n"
                f"📧 Email: `{email}`\n"
                f"🛡 Status: ✅ Aktif\n"
                f"📅 Expired: **{expired_str}**\n\n"
                "Status Userbot: 🔴 Offline\n\n"
                "Langkah Koneksi:\n"
                "1) Tekan tombol 'Hubungkan Userbot'.\n"
                "2) Masukkan nomor HP Telegram Anda.\n"
                "3) Input kode OTP yang dikirim Telegram.\n"
                "4) Selesai — Userbot akan Online.\n\n"
                "Troubleshooting:\n"
                "• Pastikan hanya 1 device menjalankan sesi.\n"
                "• Gunakan koneksi internet stabil.\n"
                "• Jika gagal OTP, coba 'Retry' dan cek format.\n\n"
                "Butuh bantuan? Hubungi Support."
            )
            buttons = [
                [Button.inline("🔌 Hubungkan Userbot", b"start_auth_process")],
                [Button.inline("📘 Panduan Koneksi", b"menu_connect_guide")],
                [Button.inline("🛠 Troubleshooting", b"menu_connect_trbl")],
                [Button.inline("📡 Live Chat Support", b"livechat_menu")]
            ]

    # --- MENU NON-PREMIUM ---
    else:
        text = (
            "👋 **Selamat Datang di BM CODEX**\n\n"
            "⚠️ **Status:** `Belum Terdaftar / Expired`\n\n"
            "Silakan aktifkan akun Anda:"
        )
        
        buttons = [
            [Button.inline("💎 Beli Premium", b"menu_buy")]
        ]
        
        # PERBAIKAN: Cek apakah fitur Free Trial AKTIF?
        # Jika dimatikan admin, tombol tidak muncul
        if GLOBAL_CONFIG.get("free_trial", False):
            buttons.append([Button.inline("🎁 Free Trial", b"try_free_trial")])
            
        buttons.append([Button.inline("📡 Live Chat Support", b"livechat_menu")])
    
    return text, buttons

# ==========================================
# HANDLER UTAMA
# ==========================================
@bot.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    user_id = event.sender_id
    if user_id == ADMIN_ID:
        from bot_handlers.admin.dashboard import send_admin_dashboard
        await send_admin_dashboard(event)
        return

    idx, row = find_member_row(user_id)
    text, buttons = get_main_menu_data(user_id, row)
    await event.reply(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"menu_start"))
async def cb_menu_start(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    text, buttons = get_main_menu_data(user_id, row)
    try: await event.edit(text, buttons=buttons)
    except MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=b"menu_connect_guide"))
async def cb_connect_guide(event):
    text = (
        "📘 **PANDUAN KONEKSI USERBOT**\n\n"
        "1) Tekan 'Hubungkan Userbot'.\n"
        "2) Masukkan nomor HP (format lokal/internasional).\n"
        "3) Masukkan kode OTP sesuai format.\n"
        "4) Tunggu hingga status menjadi Online.\n\n"
        "Tips:\n"
        "• Pastikan akun tidak login di host lain.\n"
        "• Jangan bagikan kode OTP."
    )
    buttons = [[Button.inline("🔙 Kembali", b"menu_start")]]
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"menu_connect_trbl"))
async def cb_connect_trbl(event):
    text = (
        "🛠 **TROUBLESHOOTING KONEKSI**\n\n"
        "• Gagal OTP: cek format kode, gunakan tombol Retry.\n"
        "• Sesi konflik: pastikan tidak ada instance lain aktif.\n"
        "• Internet: pastikan koneksi stabil.\n"
        "• Jika masih bermasalah, hubungi Support."
    )
    buttons = [[Button.inline("📡 Live Chat Support", b"livechat_menu")], [Button.inline("🔙 Kembali", b"menu_start")]]
    await event.edit(text, buttons=buttons)

# ==========================================
# HANDLER FREE TRIAL
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"try_free_trial"))
async def cb_free_trial(event):
    user_id = event.sender_id
    
    # PERBAIKAN: Cek ulang status fitur (Double Check) - Gunakan GLOBAL_CONFIG
    if not GLOBAL_CONFIG.get("free_trial", False):
        return await event.answer("❌ Maaf, Free Trial sedang ditutup oleh Admin.", alert=True)
    
    idx, row = find_member_row(user_id)
    if row and row.get("Status") == "Approved":
        return await event.answer("✅ Akun Anda sudah aktif!", alert=True)
    
    NAV_EDIT_STATE[user_id] = "TRIAL_WAIT_NAME"
    
    await event.edit(
        "🎁 **PENDAFTARAN FREE TRIAL**\n\n"
        "Silakan masukkan data diri Anda untuk aktivasi otomatis.\n\n"
        "1️⃣ Silakan ketik **Nama Lengkap** Anda:",
        buttons=[[Button.inline("❌ Batal", b"menu_start")]]
    )

# ==========================================
# LISTENER INPUT (TRIAL & FITUR LAIN)
# ==========================================
@bot.on(events.NewMessage(incoming=True))
async def nav_input_listener(event):
    user_id = event.sender_id
    if user_id not in NAV_EDIT_STATE: return
    
    state = NAV_EDIT_STATE[user_id]
    text = event.message.text.strip()
    
    # --- 1. LOGIC TRIAL: INPUT NAMA ---
    if state == "TRIAL_WAIT_NAME":
        NAV_EDIT_STATE[user_id] = {"step": "TRIAL_WAIT_EMAIL", "nama": text}
        await event.reply(f"✅ Halo **{text}**.\n2️⃣ Sekarang kirim **Alamat Email** Anda:")
    
    # --- 2. LOGIC TRIAL: INPUT EMAIL & AKTIVASI ---
    elif isinstance(state, dict) and state.get("step") == "TRIAL_WAIT_EMAIL":
        if "@" not in text:
            return await event.reply("❌ Format email salah. Coba lagi.")
            
        nama = state["nama"]
        email = text
        
        # Aktivasi 3 Hari
        expire_date = (datetime.now() + timedelta(days=3)).strftime("%d-%m-%Y")
        
        idx, row = find_member_row(user_id)
        if idx is not None:
            update_member_name_email(user_id, nama, email)
            update_member_status(user_id, "Approved")
            update_member_data(user_id, "Expired", expire_date)
        else:
            append_member(user_id, nama, email, months=0)
            update_member_status(user_id, "Approved")
            update_member_data(user_id, "Expired", expire_date)
            
        del NAV_EDIT_STATE[user_id]
        
        try: await bot.send_message(ADMIN_ID, f"🎁 **NEW TRIAL USER**\nUser: `{user_id}`\nNama: {nama}")
        except: pass
        
        await event.reply(
            f"🎉 **SELAMAT! AKUN TRIAL AKTIF**\n\n"
            f"👤 Nama: {nama}\n"
            f"📧 Email: {email}\n"
            f"📅 Expired: {expire_date} (3 Hari)\n\n"
            f"Sekarang Anda bisa menghubungkan Userbot.",
            buttons=[[Button.inline("⚙️ Hubungkan Userbot", b"menu_connect_ub")]]
        )

    # --- 3. LOGIC FITUR LAIN ---
    elif state == "AS_WAIT_MSG":
        s = get_as_settings(user_id)
        msgs = s.get("messages") or []
        msgs.append(text)
        update_as_setting(user_id, "messages", msgs)
        del NAV_EDIT_STATE[user_id]
        await event.reply("✅ Disimpan!")
        await cb_as_set(await event.reply("🔄 Memuat..."))

    # Handle unread message template
    elif state == "UR_WAIT_MSG":
        update_ur_message(user_id, text)
        del NAV_EDIT_STATE[user_id]
        await event.reply("✅ Pesan berhasil disimpan!")
        await cb_ur_s(await event.reply("🔄 Memuat..."))
        
    # Handle unread delay setting
    elif state == "UR_SET_DELAY":
        if text.isdigit() and 3 <= int(text) <= 60:
            update_ur_settings(user_id, {"delay_between_chats": int(text)})
            del NAV_EDIT_STATE[user_id]
            await event.reply(f"✅ Delay antar chat diatur menjadi {text} detik!")
            await cb_ur_s(await event.reply("🔄 Memuat..."))
        else:
            await event.reply("❌ Masukkan angka antara 3-60 untuk delay (dalam detik).")
            
    # Handle typing duration setting
    elif state == "UR_SET_TYPING":
        if text.isdigit() and 1 <= int(text) <= 10:
            update_ur_settings(user_id, {"typing_duration": int(text)})
            del NAV_EDIT_STATE[user_id]
            await event.reply(f"✅ Durasi mengetik diatur menjadi {text} detik!")
            await cb_ur_s(await event.reply("🔄 Memuat..."))
        else:
            await event.reply("❌ Masukkan angka antara 1-10 untuk durasi mengetik (dalam detik).")
        
    elif isinstance(state, str) and state.startswith("AS_EDIT:"):
        try:
            idx = int(state.split(":")[1])
        except:
            idx = -1
        s = get_as_settings(user_id)
        msgs = s.get("messages") or ([] if not s.get("message") else [s.get("message")])
        if 0 <= idx < len(msgs):
            msgs[idx] = text
            update_as_setting(user_id, "messages", msgs)
        del NAV_EDIT_STATE[user_id]
        await event.reply("✅ Disimpan!")
        await cb_as_set(await event.reply("🔄 Memuat..."))

    elif state == "AS_WAIT_DELAY":
        if text.isdigit():
            update_as_setting(user_id, "delay", int(text))
            del NAV_EDIT_STATE[user_id]
            await event.reply("✅ Disimpan!")
            await cb_as_set(await event.reply("🔄 Memuat..."))
        else:
            await event.reply("⚠️ Angka saja.")

# ==========================================
# (HANDLER FITUR LAINNYA)
# ==========================================

@bot.on(events.CallbackQuery(pattern=b"menu_unread"))
async def cb_ur(event):
    settings = get_ur_settings(event.sender_id)
    is_enabled = is_unread_mode_enabled(event.sender_id)
    
    text = (
        "🔔 **MODE BALAS OTOMATIS**\n\n"
        f"Status: {'🟢 AKTIF' if is_enabled else '🔴 NONAKTIF'}\n"
        f"Pesan: `{settings.get('message', 'Belum diatur')[:50]}...`\n\n"
        "📌 **Cara Penggunaan:**\n"
        "1. Aktifkan mode balas otomatis\n"
        "2. Atur pesan balasan yang diinginkan\n"
        "3. Klik 'Mulai Balas' untuk memproses pesan\n\n"
        "📝 **Fitur:**\n"
        "• Balas otomatis ke chat yang belum dibaca\n"
        "• Dapat disesuaikan pesannya\n"
        "• Hanya untuk chat personal (bukan grup/channel)"
    )
    
    buttons = [
        [
            Button.inline(f"{'🔴 Matikan' if is_enabled else '🟢 Nyalakan'}", b"unread_toggle"),
            Button.inline("⚙️ Pengaturan", b"menu_ur_set")
        ],
        [
            Button.inline("🚀 Mulai Balas", b"unread_start"),
            Button.inline("📊 Status", b"unread_status")
        ],
        [Button.inline("🔙 Kembali", b"menu_start")]
    ]
    
    try:
        await event.edit(text, buttons=buttons)
    except MessageNotModifiedError:
        await event.answer("Tidak ada perubahan", alert=False)

@bot.on(events.CallbackQuery(pattern=b"menu_ur_set"))
async def cb_ur_s(event):
    settings = get_ur_settings(event.sender_id)
    text = (
        "⚙️ **PENGATURAN BALAS OTOMATIS**\n\n"
        f"✉️ **Pesan Saat Ini:**\n`{settings.get('message', 'Belum diatur')}`\n\n"
        f"⏱️ **Delay Antar Chat:** `{settings.get('delay_between_chats', 5)} detik`\n"
        f"⌨️ **Durasi Mengetik:** `{settings.get('typing_duration', 3)} detik`\n\n"
        "Gunakan tombol di bawah untuk mengatur:"
    )
    
    buttons = [
        [Button.inline("✏️ Edit Pesan", b"nav_ur_edit")],
        [
            Button.inline("⏱️ Set Delay", b"unread_set_delay"),
            Button.inline("⌨️ Set Mengetik", b"unread_set_typing")
        ],
        [Button.inline("🔙 Kembali", b"menu_unread")]
    ]
    
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"nav_ur_edit"))
async def cb_ur_e(event):
    NAV_EDIT_STATE[event.sender_id] = "UR_WAIT_MSG"
    await event.edit(
        "✍️ **ATUR PESAN BALASAN**\n\n"
        "Silakan kirim pesan yang akan digunakan untuk membalas chat yang belum dibaca.\n\n"
        "**Variabel yang tersedia:**\n"
        "• `{name}` - Nama pengirim\n"
        "• `{id}` - ID pengirim\n\n"
        "Contoh:\n"
        "`Hai {name}, terima kasih sudah menghubungi. Saya akan segera membalas pesan Anda.`",
        buttons=[[Button.inline("❌ Batal", b"menu_ur_set")]]
    )

@bot.on(events.CallbackQuery(pattern=b"unread_toggle"))
async def unread_toggle_handler(event):
    current_status = is_unread_mode_enabled(event.sender_id)
    set_unread_mode(event.sender_id, not current_status)
    await event.answer(f"Mode balas otomatis {'diaktifkan' if not current_status else 'dinonaktifkan'}", alert=False)
    await cb_ur(event)

@bot.on(events.CallbackQuery(pattern=b"unread_status"))
async def unread_status_handler(event):
    try:
        settings = get_ur_settings(event.sender_id)
        is_enabled = is_unread_mode_enabled(event.sender_id)
        last_used = settings.get('last_used', 'Belum pernah digunakan')
        
        if last_used and last_used != 'Belum pernah digunakan':
            try:
                last_used_dt = datetime.fromisoformat(last_used)
                last_used = last_used_dt.strftime("%d %b %Y %H:%M")
            except:
                pass
        
        text = (
            "📊 **STATUS BALAS OTOMATIS**\n\n"
            f"🔘 Status: {'🟢 AKTIF' if is_enabled else '🔴 NONAKTIF'}\n"
            f"📅 Terakhir Digunakan: {last_used}\n"
            f"⏱️ Delay: {settings.get('delay_between_chats', 5)} detik\n"
            f"⌨️ Durasi Mengetik: {settings.get('typing_duration', 3)} detik\n\n"
            f"📝 **Pesan:**\n`{settings.get('message', 'Belum diatur')}`"
        )
        
        buttons = [
            [Button.inline("🔄 Perbarui", b"unread_status")],
            [Button.inline("🔙 Kembali", b"menu_unread")]
        ]
        
        try:
            await event.edit(text, buttons=buttons)
        except MessageNotModifiedError:
            await event.answer("Tidak ada perubahan")
    except Exception as e:
        logging.error(f"Error in unread_status_handler: {e}")
        await event.answer("❌ Terjadi kesalahan. Silakan coba lagi.", alert=True)

@bot.on(events.CallbackQuery(pattern=b"unread_set_delay"))
async def unread_set_delay_handler(event):
    NAV_EDIT_STATE[event.sender_id] = "UR_SET_DELAY"
    current_delay = get_ur_settings(event.sender_id).get('delay_between_chats', 5)
    await event.edit(
        f"⏱ **ATUR DELAY ANTAR CHAT**\n\n"
        f"Delay saat ini: `{current_delay}` detik\n\n"
        "Masukkan angka (dalam detik) untuk delay antar pengiriman pesan.\n"
        "Minimal 3 detik, maksimal 60 detik.",
        buttons=[[Button.inline("❌ Batal", b"menu_ur_set")]]
    )

@bot.on(events.CallbackQuery(pattern=b"unread_set_typing"))
async def unread_set_typing_handler(event):
    NAV_EDIT_STATE[event.sender_id] = "UR_SET_TYPING"
    current_duration = get_ur_settings(event.sender_id).get('typing_duration', 3)
    await event.edit(
        f"⌨️ **ATUR DURASI MENGETIK**\n\n"
        f"Durasi saat ini: `{current_duration}` detik\n\n"
        "Masukkan angka (dalam detik) untuk durasi efek mengetik.\n"
        "Minimal 1 detik, maksimal 10 detik.",
        buttons=[[Button.inline("❌ Batal", b"menu_ur_set")]]
    )

@bot.on(events.CallbackQuery(pattern=b"unread_start"))
async def unread_start_handler(event):
    user_id = event.sender_id
    
    # Cek apakah userbot sudah terhubung
    if user_id not in ACTIVE_USERBOTS:
        await event.answer("❌ Userbot belum terhubung. Silakan hubungkan userbot terlebih dahulu.", alert=True)
        return await cb_ur(event)
    
    settings = get_ur_settings(user_id)
    if not settings.get('message'):
        await event.answer("❌ Silakan atur pesan terlebih dahulu di pengaturan.", alert=True)
        return await cb_ur_s(event)
    
    if not is_unread_mode_enabled(user_id):
        set_unread_mode(user_id, True)
    
    await event.edit(
        "🚀 **MEMULAI BALAS PESAN**\n\n"
        "Bot akan mulai membalas pesan yang belum dibaca.\n"
        "Proses ini berjalan di latar belakang.\n\n"
        f"🔘 Status: {'🟢 AKTIF' if is_unread_mode_enabled(user_id) else '🔴 NONAKTIF'}\n"
        f"⏱️ Delay: {settings.get('delay_between_chats', 5)} detik\n"
        f"⌨️ Durasi Mengetik: {settings.get('typing_duration', 3)} detik\n\n"
        f"📝 **Pesan:**\n`{settings.get('message')[:100]}...`\n\n"
        "Tekan tombol di bawah untuk memulai atau batalkan.",
        buttons=[
            [Button.inline("✅ Ya, Mulai Sekarang", b"confirm_unread_start")],
            [Button.inline("❌ Batalkan", b"menu_unread")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=b"confirm_unread_start"))
async def confirm_unread_start_handler(event):
    try:
        import logging
        
        user_id = event.sender_id
        
        # Cek apakah userbot sudah terhubung
        if user_id not in ACTIVE_USERBOTS:
            await event.answer("❌ Userbot belum terhubung. Silakan hubungkan userbot terlebih dahulu.", alert=True)
            return await cb_ur(event)
        
        # Get userbot client
        userbot_client = ACTIVE_USERBOTS[user_id]
        
        # Get the original message to update it - ini akan menjadi status_msg
        message = await event.get_message()
        status_msg = await message.edit(
            "🔄 **Mencari chat yang belum dibaca...**\n\n"
            "⏳ Harap tunggu, proses sedang dimulai...",
            buttons=None
        )
        
        # Define a simple is_allowed function that always returns True
        async def is_allowed(feature):
            return True
            
        # Define a simple check_status function
        async def check_status(client, user_id, event):
            return True
        
        # Import function yang diperlukan
        from modules.unread import process_userbot_unread
        
        # Get settings (sudah di-import sebagai get_ur_settings)
        settings = get_ur_settings(user_id)
        
        # Start processing unread chats dengan userbot client
        await process_userbot_unread(event, userbot_client, user_id, status_msg, settings)
        
    except Exception as e:
        import logging
        logging.error(f"Error in confirm_unread_start_handler: {e}")
        try:
            await event.answer("❌ Gagal memproses pesan. Silakan coba lagi.", alert=True)
        except:
            pass

@bot.on(events.CallbackQuery(pattern=b"menu_autospam"))
async def cb_as(event):
    text = (
        "📨 **AUTO MESSAGE**\n"
        "Balas otomatis chat pribadi secara real-time.\n\n"
        "📌 Petunjuk Penggunaan:\n"
        "• Aktifkan fitur dan set daftar pesan.\n"
        "• Bot akan merespon < 5 detik dengan efek mengetik.\n"
        "• Mendukung berbagai jenis pesan: teks, foto, video, dokumen, sticker.\n\n"
        "🔎 Lihat status untuk indikator: \n"
        "• 📤 Terkirim • 👁 Dibaca • 💬 Direspon\n"
    )
    await event.edit(text, buttons=[[Button.inline("⚙️ Atur", b"menu_as_set")], [Button.inline("📊 Status", b"nav_as_status")], [Button.inline("⬅️ Back", b"menu_start")]])
@bot.on(events.CallbackQuery(pattern=b"menu_as_set"))
async def cb_as_s(event): 
    s=get_as_settings(event.sender_id); st="✅" if s.get("enabled") else "❌"
    stats = compute_auto_message_stats(event.sender_id)
    info = f"🧾 Log: {stats['total']} • ✅ OK: {stats['ok']} • ❌ Err: {stats['err']}\n⏱ Rata2: {stats['avg']}ms"
    await event.edit(f"⚙️ **SET AUTO MSG**\nStatus: {st}\n{info}", buttons=[[Button.inline(f"Ubah: {st}", b"nav_as_off" if s.get("enabled") else b"nav_as_on")], [Button.inline("✏️ Pesan", b"nav_as_msg"), Button.inline("📋 List", b"nav_as_list")], [Button.inline("⏱ Delay", b"nav_as_delay")], [Button.inline("♻ Reset Balasan", b"nav_as_reset")], [Button.inline("📊 Status", b"nav_as_status")], [Button.inline("🔙 Back", b"menu_autospam")]])
@bot.on(events.CallbackQuery(pattern=b"nav_as_on"))
async def cb_as_on(event): update_as_setting(event.sender_id, "enabled", True); await cb_as_s(event)
@bot.on(events.CallbackQuery(pattern=b"nav_as_off"))
async def cb_as_off(event): update_as_setting(event.sender_id, "enabled", False); await cb_as_s(event)
@bot.on(events.CallbackQuery(pattern=b"nav_as_msg"))
async def cb_as_m(event): NAV_EDIT_STATE[event.sender_id]="AS_WAIT_MSG"; await event.edit("✏️ Kirim pesan baru:", buttons=[[Button.inline("❌", b"menu_as_set")]])
@bot.on(events.CallbackQuery(pattern=b"nav_as_delay"))
async def cb_as_d(event): NAV_EDIT_STATE[event.sender_id]="AS_WAIT_DELAY"; await event.edit("⏱ Kirim delay (angka):", buttons=[[Button.inline("❌", b"menu_as_set")]])

@bot.on(events.CallbackQuery(pattern=b"nav_as_status"))
async def cb_as_status(event):
    stats = compute_auto_message_stats(event.sender_id)
    last = stats["last"]
    status_icon = "✅" if last.get("status") == "ok" else ("❌" if last else "-")
    msg_type = last.get("message_type", "-")
    lat = last.get("latency_ms")
    sla = "⚡ SLA OK" if isinstance(lat, int) and lat <= 5000 else ("🐢 SLA Slow" if isinstance(lat, int) else "-")
    entries = read_auto_message_logs(event.sender_id, limit=10)
    lines = []
    for e in entries:
        ti = e.get("ts", "-").replace("T", " ")
        ic = "✅" if e.get("status") == "ok" else "❌"
        lt = e.get("latency_ms")
        mt = e.get("message_type", "-")
        lines.append(f"{ic} {ti} • {mt} • {lt}ms")
    body = "\n".join(lines) if lines else "(Belum ada log)"
    text = (
        "📊 **STATUS AUTO MESSAGE**\n\n"
        f"Terakhir: {status_icon} • tipe={msg_type} • ⏱={lat}ms\n{sla}\n\n"
        f"Ringkasan: Total {stats['total']} • ✅ {stats['ok']} • ❌ {stats['err']} • Avg {stats['avg']}ms\n\n"
        f"Log Terbaru:\n{body}"
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"menu_as_set")]])

@bot.on(events.CallbackQuery(pattern=b"nav_as_reset"))
async def cb_as_reset(event):
    update_as_setting(event.sender_id, "replied_chats", [])
    await event.answer("✅ Daftar balasan direset", alert=True)
    await cb_as_s(event)

@bot.on(events.CallbackQuery(pattern=b"livechat_menu"))
async def cb_lc(event): await event.edit("📡 **LIVE CHAT**\nHubungkan ke Admin.", buttons=[[Button.inline("💬 Mulai", b"start_livechat")], [Button.inline("⬅️ Back", b"menu_start")]])

@bot.on(events.CallbackQuery(pattern=b"spam_menu"))
async def cb_sp(event): 
    text = (
        "🤖 **MENU SPAM**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pilih jenis spam yang ingin digunakan.\n"
        "Progress akan ditampilkan di bot admin."
    )
    buttons = [
        [Button.inline("🤖 SpamBot Biasa", b"guide_spam_std")],
        [Button.inline("💎 SpamBot Premium", b"guide_spam_prem")],
        [Button.inline("⚙️ Atur Spam Premium", b"open_spambotpremium_settings")],
        [Button.inline("🧠 SpamAI Smart", b"guide_spam_ai")],
        [Button.inline("⬅️ Kembali", b"menu_start")]
    ]
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"guide_spam_std"))
async def cb_sp1(event): 
    text = (
        "🤖 **SPAM BIASA**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Penggunaan:**\n"
        "`.spambot <target> <jumlah> [kata]`\n\n"
        "**Contoh:**\n"
        "`.spambot @grupku 20 Halo semuanya`\n"
        "`.spambot @user 10` (tanpa kata → default)\n\n"
        "**Parameter:**\n"
        "• target (wajib): username/ID grup/user\n"
        "• jumlah (wajib): banyak pesan (max 100)\n"
        "• kata (opsional): isi pesan\n"
        "• jeda (default): ~1 pesan/detik (rate limit aman)\n\n"
        "⚠️ Gunakan secara bertanggung jawab. Hindari kata-kata sensitif dan spam berlebihan."
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"spam_menu")]])

@bot.on(events.CallbackQuery(pattern=b"guide_spam_prem"))
async def cb_sp2(event): 
    text = (
        "💎 **SPAM PREMIUM**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Penggunaan:**\n"
        "`.spambotpremium <target> <jumlah>`\n\n"
        "**Pengaturan (CRUD via tombol):**\n"
        "`.set_spambotpremium`\n"
        "• Tambah/Edit/Hapus pesan (minimal 10)\n"
        "• Set delay min-max (contoh 3-5 detik)\n"
        "• Toggle reply ke pesan (On/Off)\n"
        "• Pesan akan di-random per kirim\n\n"
        "**Contoh:**\n"
        "`.spambotpremium @grupku 30`\n\n"
        "⚠️ Ikuti rate limit Telegram dan gunakan secara bertanggung jawab."
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"spam_menu")]])

@bot.on(events.CallbackQuery(pattern=b"open_spambotpremium_settings"))
async def cb_open_spp_settings(event):
    from modules.spambotpremium import show_settings_menu
    await show_settings_menu(event, event.sender_id)

@bot.on(events.CallbackQuery(pattern=b"guide_spam_ai"))
async def cb_sp3(event): 
    text = (
        "🧠 **SPAM AI SMART**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Penggunaan:**\n"
        "`.spamai <target> <min-max> <jumlah> <msg>`\n\n"
        "**Contoh:**\n"
        "`.spamai @grupku 5-10 50 Halo semua`\n\n"
        "**Parameter:**\n"
        "• target (wajib): username/ID grup\n"
        "• min-max (wajib): delay acak detik (mis. 5-10)\n"
        "• jumlah (wajib): banyak pesan (max 100)\n"
        "• msg (opsional): tema/pola kalimat yang disisipkan\n\n"
        "**Fitur AI:**\n"
        "• Baca 255 kata terakhir dari grup\n"
        "• Filter kata-kata SARA dan berisiko\n"
        "• Bangun 50 kalimat persiapan (3-5 kata/kalimat)\n"
        "• Regenerasi kata setiap 10 menit\n"
        "• Opsi reply ke pesan orang lain\n\n"
        "⚠️ Konten sensitif akan difilter. Gunakan dengan bijak."
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"spam_menu")]])

@bot.on(events.CallbackQuery(pattern=b"menu_faktur"))
async def cb_fk(event): await event.edit("📑 **FAKTUR**\nSetting layanan & bank.", buttons=[[Button.inline("⚙️ Atur", b"open_faktur_settings")], [Button.inline("⬅️ Back", b"menu_start")]])
@bot.on(events.CallbackQuery(pattern=b"open_faktur_settings"))
async def cb_fk_op(event): 
    if show_faktur_settings: await show_faktur_settings(event, event.sender_id)
    else: await event.answer("Error module.", alert=True)
@bot.on(events.CallbackQuery(pattern=b"nav_as_list"))
async def cb_as_list(event):
    s = get_as_settings(event.sender_id)
    msgs = s.get("messages") or ([] if not s.get("message") else [s.get("message")])
    if not msgs:
        return await event.answer("⚠️ Kosong.", alert=True)
    t = "📋 **LIST PESAN**\n\n"; b = []
    for i, m in enumerate(msgs):
        short = m if len(m) <= 30 else m[:30] + "..."
        t += f"{i+1}. {short}\n"
        b.append([Button.inline(f"✏️ Edit {i+1}", f"nav_as_edit:{i}"), Button.inline(f"🗑 Hapus {i+1}", f"nav_as_del:{i}")])
    b.append([Button.inline("⬅️ Kembali", b"menu_as_set")])
    await event.edit(t, buttons=b)

@bot.on(events.CallbackQuery(pattern=r"nav_as_del:(\d+)"))
async def cb_as_del(event):
    i = int(event.data.decode().split(":")[1])
    s = get_as_settings(event.sender_id)
    msgs = s.get("messages") or ([] if not s.get("message") else [s.get("message")])
    if 0 <= i < len(msgs):
        msgs.pop(i)
        update_as_setting(event.sender_id, "messages", msgs)
        await event.answer("✅ Dihapus")
    await cb_as_list(event)

@bot.on(events.CallbackQuery(pattern=r"nav_as_edit:(\d+)"))
async def cb_as_edit(event):
    i = int(event.data.decode().split(":")[1])
    NAV_EDIT_STATE[event.sender_id] = f"AS_EDIT:{i}"
    await event.edit("✏️ Kirim pesan pengganti:", buttons=[[Button.inline("❌ Batal", b"menu_as_set")]])

@bot.on(events.CallbackQuery(pattern=r"stop_unread:(.+)"))
async def stop_unread_handler(event):
    """Handler untuk menghentikan proses unread"""
    try:
        target_user = int(event.data.decode().split(":")[1])
        user_id = event.sender_id
        
        # Izinkan Admin atau member pemilik task
        if user_id not in (ADMIN_ID, target_user):
            return await event.answer("❌ Anda tidak memiliki izin untuk menghentikan proses ini.", alert=True)
        
        if target_user in ACTIVE_UNREAD_TASKS:
            # Cancel task
            task = ACTIVE_UNREAD_TASKS[target_user]
            task.cancel()
            del ACTIVE_UNREAD_TASKS[target_user]
            
            await event.answer("✅ Proses dihentikan!", alert=True)
            
            # Update message jika masih bisa
            try:
                message = await event.get_message()
                await message.edit(
                    "🛑 **Proses Dihentikan**\n\n"
                    "Proses balas otomatis telah dihentikan oleh pengguna.",
                    buttons=[[Button.inline("🔙 Kembali ke Menu", b"menu_start")]]
                )
            except Exception as e:
                logging.error(f"Error updating stop message: {e}")
        else:
            await event.answer("⚠️ Proses sudah selesai atau tidak berjalan.", alert=True)
    except Exception as e:
        import logging
        logging.error(f"Error in stop_unread_handler: {e}")
        await event.answer("❌ Terjadi kesalahan saat menghentikan proses.", alert=True)
