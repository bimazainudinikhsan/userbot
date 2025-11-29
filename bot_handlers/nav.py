# bmcodexbot/bot_handlers/nav.py
from datetime import datetime, timedelta
from telethon import events, Button
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
from state import GLOBAL_FEATURE_FLAGS, WAIT_NAME, GLOBAL_CONFIG

# --- IMPORT MODULES ---
from modules.autoreply import get_user_settings as get_ar_settings, save_settings as save_ar_settings
from modules.unread import get_settings as get_ur_settings, save_user_message as update_ur_message
from modules.auto_spam import get_settings as get_as_settings, update_setting as update_as_setting

try:
    from modules.faktur import show_setting_menu as show_faktur_settings
except ImportError:
    show_faktur_settings = None

NAV_EDIT_STATE = {}

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
            [Button.inline("💬 Auto Reply", b"menu_autoreply"), Button.inline("👻 Unread Mode", b"menu_unread")],
            [Button.inline("📨 Auto Message", b"menu_autospam"), Button.inline("🤖 Spam & AI", b"spam_menu")],
            [Button.inline("📑 Buat Faktur", b"menu_faktur")],
        ]
        if user_id == ADMIN_ID:
            buttons.append([Button.inline("📱 Remote App (Admin)", b"menu_remote_app")])
        
        buttons.append([Button.inline("📡 Live Chat Support", b"livechat_menu")])

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
    elif state == "AR_WAIT_TEXT":
        settings = get_ar_settings(user_id)
        if "reply_content" not in settings: settings["reply_content"] = []
        settings["reply_content"].append({"type": "text", "text": text})
        save_ar_settings()
        del NAV_EDIT_STATE[user_id]
        await event.reply("✅ Disimpan!")
        await cb_ar_set(await event.reply("🔄 Memuat..."))

    elif state == "UR_WAIT_MSG":
        update_ur_message(user_id, text)
        del NAV_EDIT_STATE[user_id]
        await event.reply("✅ Disimpan!")
        await cb_ur_set(await event.reply("🔄 Memuat..."))
        
    elif state == "AS_WAIT_MSG":
        update_as_setting(user_id, "message", text)
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

@bot.on(events.CallbackQuery(pattern=b"menu_autoreply"))
async def cb_ar_guide(event):
    await event.edit("📚 **PANDUAN AUTO REPLY**\nKlik **Atur Auto Reply** untuk setting.", buttons=[[Button.inline("⚙️ Atur", b"menu_ar_set")], [Button.inline("⬅️ Kembali", b"menu_start")]])

@bot.on(events.CallbackQuery(pattern=b"menu_ar_set"))
async def cb_ar_set(event):
    s = get_ar_settings(event.sender_id)
    icon = "✅" if s.get("auto_reply") else "❌"
    await event.edit(f"⚙️ **SETTING AR**\nStatus: {icon}", buttons=[
        [Button.inline(f"Ubah: {icon}", b"nav_ar_on" if not s.get("auto_reply") else b"nav_ar_off")],
        [Button.inline("➕ Tambah", b"nav_ar_add"), Button.inline("📋 List", b"nav_ar_list")],
        [Button.inline("🔙 Kembali", b"menu_autoreply")]
    ])

@bot.on(events.CallbackQuery(pattern=b"nav_ar_on"))
async def cb_ar_on(event):
    s = get_ar_settings(event.sender_id); s["auto_reply"]=True; save_ar_settings(); await cb_ar_set(event)

@bot.on(events.CallbackQuery(pattern=b"nav_ar_off"))
async def cb_ar_off(event):
    s = get_ar_settings(event.sender_id); s["auto_reply"]=False; save_ar_settings(); await cb_ar_set(event)

@bot.on(events.CallbackQuery(pattern=b"nav_ar_add"))
async def cb_ar_add(event):
    NAV_EDIT_STATE[event.sender_id] = "AR_WAIT_TEXT"
    await event.edit("➕ **Tambah Pesan**\nKirim pesan:", buttons=[[Button.inline("❌ Batal", b"menu_ar_set")]])

@bot.on(events.CallbackQuery(pattern=b"nav_ar_list"))
async def cb_ar_list(event):
    s = get_ar_settings(event.sender_id); c = s.get("reply_content", [])
    if not c: return await event.answer("⚠️ Kosong.", alert=True)
    t = "📋 **LIST PESAN**\n\n"; b = []
    for i, item in enumerate(c):
        t += f"{i+1}. {item.get('text','')}[:15]...\n"
        b.append([Button.inline(f"🗑 Hapus {i+1}", f"nav_ar_del:{i}")])
    b.append([Button.inline("⬅️ Kembali", b"menu_ar_set")])
    await event.edit(t, buttons=b)

@bot.on(events.CallbackQuery(pattern=r"nav_ar_del:(.+)"))
async def cb_ar_del(event):
    i = int(event.data.decode().split(":")[1]); s = get_ar_settings(event.sender_id); c = s.get("reply_content", [])
    if 0 <= i < len(c): c.pop(i); s["reply_content"] = c; save_ar_settings(); await event.answer("✅ Dihapus")
    await cb_ar_list(event)

@bot.on(events.CallbackQuery(pattern=b"menu_unread"))
async def cb_ur(event): await event.edit("👻 **UNREAD**\nCmd: `.replyunread`", buttons=[[Button.inline("⚙️ Atur", b"menu_ur_set")], [Button.inline("⬅️ Back", b"menu_start")]])
@bot.on(events.CallbackQuery(pattern=b"menu_ur_set"))
async def cb_ur_s(event): await event.edit(f"⚙️ **SET UNREAD**\nPesan: `{get_ur_settings(event.sender_id).get('message')}`", buttons=[[Button.inline("✏️ Edit", b"nav_ur_edit")], [Button.inline("🔙 Back", b"menu_unread")]])
@bot.on(events.CallbackQuery(pattern=b"nav_ur_edit"))
async def cb_ur_e(event): NAV_EDIT_STATE[event.sender_id]="UR_WAIT_MSG"; await event.edit("✏️ Kirim pesan baru:", buttons=[[Button.inline("❌ Batal", b"menu_ur_set")]])

@bot.on(events.CallbackQuery(pattern=b"menu_autospam"))
async def cb_as(event): await event.edit("📨 **AUTO MSG**", buttons=[[Button.inline("⚙️ Atur", b"menu_as_set")], [Button.inline("⬅️ Back", b"menu_start")]])
@bot.on(events.CallbackQuery(pattern=b"menu_as_set"))
async def cb_as_s(event): 
    s=get_as_settings(event.sender_id); st="✅" if s.get("enabled") else "❌"
    await event.edit(f"⚙️ **SET AUTO MSG**\nStatus: {st}", buttons=[[Button.inline(f"Ubah: {st}", b"nav_as_off" if s.get("enabled") else b"nav_as_on")], [Button.inline("✏️ Pesan", b"nav_as_msg"), Button.inline("⏱ Delay", b"nav_as_delay")], [Button.inline("🔙 Back", b"menu_autospam")]])
@bot.on(events.CallbackQuery(pattern=b"nav_as_on"))
async def cb_as_on(event): update_as_setting(event.sender_id, "enabled", True); await cb_as_s(event)
@bot.on(events.CallbackQuery(pattern=b"nav_as_off"))
async def cb_as_off(event): update_as_setting(event.sender_id, "enabled", False); await cb_as_s(event)
@bot.on(events.CallbackQuery(pattern=b"nav_as_msg"))
async def cb_as_m(event): NAV_EDIT_STATE[event.sender_id]="AS_WAIT_MSG"; await event.edit("✏️ Kirim pesan:", buttons=[[Button.inline("❌", b"menu_as_set")]])
@bot.on(events.CallbackQuery(pattern=b"nav_as_delay"))
async def cb_as_d(event): NAV_EDIT_STATE[event.sender_id]="AS_WAIT_DELAY"; await event.edit("⏱ Kirim delay (angka):", buttons=[[Button.inline("❌", b"menu_as_set")]])

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
        "`.spambot <target> <jumlah> <pesan>`\n\n"
        "**Contoh:**\n"
        "`.spambot @grupku 20 Halo semuanya`\n\n"
        "**Keterangan:**\n"
        "• target: username/ID grup/user\n"
        "• jumlah: berapa pesan (max 100)\n"
        "• pesan: isi pesan yang dikirim\n"
        "• Delay: 2 detik per pesan"
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"spam_menu")]])

@bot.on(events.CallbackQuery(pattern=b"guide_spam_prem"))
async def cb_sp2(event): 
    text = (
        "💎 **SPAM PREMIUM**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Penggunaan Spam:**\n"
        "`.spambotpremium <target> <jumlah>`\n\n"
        "**Pengaturan:**\n"
        "`.set_spambotpremium`\n\n"
        "**Contoh:**\n"
        "`.spambotpremium @grupku 30`\n\n"
        "**Fitur Premium:**\n"
        "• Multi pesan (random)\n"
        "• Delay custom (min-max detik)\n"
        "• Reply ke pesan atas (on/off)\n"
        "• Menu CRUD untuk kelola pesan"
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"spam_menu")]])

@bot.on(events.CallbackQuery(pattern=b"guide_spam_ai"))
async def cb_sp3(event): 
    text = (
        "🧠 **SPAM AI SMART**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Penggunaan:**\n"
        "`.spamai <target> <delay> <jumlah>`\n\n"
        "**Contoh:**\n"
        "`.spamai @grupku 5-10 50`\n\n"
        "**Keterangan:**\n"
        "• target: username/ID grup\n"
        "• delay: 5-10 (random 5-10 detik)\n"
        "• jumlah: berapa pesan (max 100)\n\n"
        "**Fitur AI:**\n"
        "• Scraping 255 kata dari grup\n"
        "• Filter kata SARA otomatis\n"
        "• Generate 50 kalimat (3-5 kata)\n"
        "• Reply pesan orang lain\n"
        "• Refresh kata setiap 10 menit"
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"spam_menu")]])

@bot.on(events.CallbackQuery(pattern=b"menu_faktur"))
async def cb_fk(event): await event.edit("📑 **FAKTUR**\nSetting layanan & bank.", buttons=[[Button.inline("⚙️ Atur", b"open_faktur_settings")], [Button.inline("⬅️ Back", b"menu_start")]])
@bot.on(events.CallbackQuery(pattern=b"open_faktur_settings"))
async def cb_fk_op(event): 
    if show_faktur_settings: await show_faktur_settings(event, event.sender_id)
    else: await event.answer("Error module.", alert=True)