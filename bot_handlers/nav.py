# bmcodexbot/bot_handlers/nav.py
import time
import os
from telethon import events, Button
from config import bot, ADMIN_ID
from database import find_member_row
from .admin import show_admin_dashboard
from modules.autoreply import (
    get_user_settings, save_settings, 
    add_autoreply_content, delete_autoreply_content, update_autoreply_content,
    STORAGE_DIR
)
from modules.faktur import show_setting_menu
from state import ACTIVE_USERBOTS

# State untuk Input User (Tambah/Edit Auto Reply)
AR_STATE = {} 
# Format: {user_id: {"action": "add_text"|"add_media"|"edit", "index": int, "msg_id_to_edit": int}}

# ==========================================
# 1. MENU UTAMA & HELPER
# ==========================================

def get_main_menu_data(is_member):
    if is_member:
        text = (
            "👋 **Selamat datang di Clear Virus Bot!**\n\n"
            "Berikut adalah daftar fitur canggih yang siap membantu Anda.\n"
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
        text = "👋 **Selamat datang!**\nSilakan berlangganan untuk akses fitur."
        buttons = [
            [Button.inline("🔐 Membership", b"menu_buy"), Button.inline("💬 Admin", b"start_livechat")]
        ]
    return text, buttons

@bot.on(events.NewMessage(pattern="/start"))
async def handler_start(event):
    user_id = event.sender_id
    if user_id == ADMIN_ID: return await show_admin_dashboard(event)
    idx, row = find_member_row(user_id)
    is_member = row and row.get("Status") == "Approved"
    text, buttons = get_main_menu_data(is_member)
    await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"menu_start"))
async def cb_back_main(event):
    user_id = event.sender_id
    if user_id in AR_STATE: del AR_STATE[user_id] # Clear state jika kembali
    
    idx, row = find_member_row(user_id)
    is_member = row and row.get("Status") == "Approved"
    text, buttons = get_main_menu_data(is_member)
    await event.edit(text, buttons=buttons)

# ==========================================
# 2. INPUT HANDLER (TEXT & MEDIA)
# ==========================================

@bot.on(events.NewMessage(incoming=True))
async def handle_ar_input(event):
    """Menangani input text/media dari user saat mode Edit/Tambah."""
    user_id = event.sender_id
    
    # Cek apakah user sedang dalam mode input
    if user_id not in AR_STATE:
        return

    state = AR_STATE[user_id]
    action = state.get("action")
    index = state.get("index")
    
    # Data baru yang akan disimpan
    new_content = {}
    
    # 1. Handle Text Input
    if event.text and not event.media:
        new_content = {"type": "text", "text": event.text}
    
    # 2. Handle Media Input
    elif event.media:
        # Tentukan tipe
        media_type = "media"
        if event.photo: media_type = "photo"
        elif event.sticker: media_type = "sticker"
        elif event.voice: media_type = "voice"
        elif event.video: media_type = "video"
        elif event.document: media_type = "document"
        
        # Download media ke storage lokal bot manager
        status_msg = await event.reply("⏳ Mengunduh media...")
        path = await event.download_media(file=STORAGE_DIR)
        await status_msg.delete()
        
        new_content = {
            "type": media_type,
            "text": event.text or "", # Caption
            "file_path": path
        }
    else:
        return # Abaikan jika unknown type

    # Proses Simpan
    try:
        if action.startswith("add"):
            add_autoreply_content(user_id, new_content)
            reply_text = "✅ **Berhasil Ditambahkan!**"
        
        elif action == "edit":
            update_autoreply_content(user_id, index, new_content)
            reply_text = "✅ **Berhasil Diedit!**"

        # Clear state
        del AR_STATE[user_id]
        
        # Kembali ke menu view
        settings = get_user_settings(user_id)
        content = settings.get("reply_content", [])
        
        # Tampilkan ulang menu
        await event.respond(reply_text)
        await show_ar_list(event, content)
        
    except Exception as e:
        await event.respond(f"❌ Error: {e}")

# ==========================================
# 3. INTERFACE AUTO REPLY (CRUD)
# ==========================================

async def show_ar_list(event, content):
    """Fungsi helper untuk menampilkan daftar dengan tombol Edit/Hapus."""
    if not content:
        msg = "📭 **Daftar Auto Reply Kosong**\nSilakan tambah baru."
        buttons = [
            [Button.inline("➕ Tambah Teks", b"add_ar_text"), Button.inline("➕ Tambah Media", b"add_ar_media")],
            [Button.inline("⬅️ Kembali", b"ub_autoreply")]
        ]
    else:
        msg = "📋 **DAFTAR AUTO REPLY**\n\n"
        buttons = []
        
        for i, item in enumerate(content):
            # Info Item
            tipe = item.get("type", "text").upper()
            txt = item.get("text", "")
            if len(txt) > 20: txt = txt[:20] + "..."
            if not txt and tipe != "TEXT": txt = "(Media)"
            
            msg += f"**{i+1}. [{tipe}]** {txt}\n"
            
            # Tombol Edit & Hapus per item
            buttons.append([
                Button.inline(f"✏️ Edit No {i+1}", data=f"edit_ar_{i}".encode()),
                Button.inline(f"🗑 Hapus No {i+1}", data=f"del_ar_{i}".encode())
            ])
            
        msg += "\n👇 Klik tombol di bawah untuk mengelola:"
        
        # Tombol Tambah di bawah
        buttons.append([Button.inline("➕ Tambah Teks", b"add_ar_text"), Button.inline("➕ Tambah Media", b"add_ar_media")])
        buttons.append([Button.inline("⬅️ Kembali Menu Utama", b"ub_autoreply")])

    # Kirim/Edit pesan
    # PERBAIKAN: Cek tipe event agar tidak error saat NewMessage
    if isinstance(event, events.CallbackQuery):
        await event.edit(msg, buttons=buttons)
    else:
        # Jika dipanggil dari handle_ar_input (NewMessage), gunakan respond
        await event.respond(msg, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"view_ar_content"))
async def cb_view_ar_content(event):
    user_id = event.sender_id
    settings = get_user_settings(user_id)
    content = settings.get("reply_content", [])
    await show_ar_list(event, content)

@bot.on(events.CallbackQuery(pattern=r"del_ar_(\d+)"))
async def cb_del_ar(event):
    user_id = event.sender_id
    index = int(event.data.decode().split("_")[2])
    
    if delete_autoreply_content(user_id, index):
        await event.answer("🗑 Item dihapus!", alert=True)
        # Refresh list
        settings = get_user_settings(user_id)
        await show_ar_list(event, settings.get("reply_content", []))
    else:
        await event.answer("❌ Gagal menghapus.", alert=True)

@bot.on(events.CallbackQuery(pattern=r"edit_ar_(\d+)"))
async def cb_edit_ar(event):
    user_id = event.sender_id
    index = int(event.data.decode().split("_")[2])
    
    AR_STATE[user_id] = {"action": "edit", "index": index}
    
    msg = (
        f"✏️ **MODE EDIT NO {index+1}**\n\n"
        "Silakan kirim **Teks Baru** atau **Gambar/Sticker Baru** sekarang.\n"
        "Bot menunggu input Anda..."
    )
    await event.edit(msg, buttons=[Button.inline("❌ Batal", b"view_ar_content")])

@bot.on(events.CallbackQuery(pattern=b"add_ar_text"))
async def cb_add_ar_text(event):
    user_id = event.sender_id
    AR_STATE[user_id] = {"action": "add_text"}
    await event.edit(
        "➕ **TAMBAH BALASAN TEKS**\n\nSilakan ketik pesan teks yang ingin dijadikan auto reply:",
        buttons=[Button.inline("❌ Batal", b"view_ar_content")]
    )

@bot.on(events.CallbackQuery(pattern=b"add_ar_media"))
async def cb_add_ar_media(event):
    user_id = event.sender_id
    AR_STATE[user_id] = {"action": "add_media"}
    await event.edit(
        "➕ **TAMBAH BALASAN MEDIA**\n\nSilakan kirim **Foto, Sticker, atau Voice Note** sekarang:",
        buttons=[Button.inline("❌ Batal", b"view_ar_content")]
    )

# ==========================================
# 4. HANDLER SETTING & CONNECT (ASLI)
# ==========================================

@bot.on(events.CallbackQuery(pattern=b"menu_connect_ub"))
async def cb_connect_ub_menu(event):
    user_id = event.sender_id
    settings = get_user_settings(user_id)
    ar_status = "✅ ON" if settings.get("auto_reply") else "❌ OFF"
    
    client = ACTIVE_USERBOTS.get(user_id)
    ping_ms, ub_status = "N/A", "🔴 Offline"
    
    if client and client.is_connected():
        ub_status = "🟢 Online"
        start = time.perf_counter()
        try:
            await client.get_me()
            ping_ms = f"{(time.perf_counter() - start) * 1000:.0f}ms"
        except: ping_ms = "Timeout"
    elif client:
        ub_status = "🟡 Terputus"

    text = (
        f"⚙️ **PENGATURAN & KONEKSI**\n\n"
        f"🤖 Auto Reply: **{ar_status}**\n"
        f"📡 Status Userbot: **{ub_status}**\n"
        f"📶 Koneksi Ping: **{ping_ms}**\n"
    )
    buttons = [
        [Button.inline("🔌 Hubungkan/Ganti Akun", b"start_auth_process")],
        [Button.inline(f"Auto Reply: {ar_status}", b"quick_toggle_ar")],
        [Button.inline("🔄 Cek Koneksi Sekarang", b"menu_connect_ub")],
        [Button.inline("⬅️ Kembali", b"menu_start")]
    ]
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"quick_toggle_ar"))
async def cb_quick_toggle_ar(event):
    user_id = event.sender_id
    settings = get_user_settings(user_id)
    settings["auto_reply"] = not settings.get("auto_reply")
    if settings["auto_reply"]: settings["replied_chats"] = []
    save_settings()
    await cb_connect_ub_menu(event)

# ==========================================
# 5. HANDLER DETAIL FITUR
# ==========================================

@bot.on(events.CallbackQuery(pattern=b"trigger_set_faktur"))
async def cb_trigger_set_faktur(event):
    await show_setting_menu(event, event.sender_id)

@bot.on(events.CallbackQuery(pattern=b"toggle_ar_details"))
async def cb_toggle_ar_details(event):
    user_id = event.sender_id
    settings = get_user_settings(user_id)
    settings["auto_reply"] = not settings.get("auto_reply", False)
    if settings["auto_reply"]: settings["replied_chats"] = []
    save_settings()
    
    event.data = b"ub_autoreply" # Refresh menu
    await cb_feature_details(event)

@bot.on(events.CallbackQuery(pattern=r"ub_(.+)"))
async def cb_feature_details(event):
    data = event.data.decode()
    feature = data.split("_")[1]
    user_id = event.sender_id
    
    help_text = ""
    custom_buttons = None 
    
    if feature == "faktur":
        help_text = (
            "📄 **PANDUAN INVOICE**\n\n"
            "1. Ketik `.faktur` di chat.\n"
            "2. Kirim bukti transfer.\n"
            "3. Isi data pembeli.\n"
            "4. PDF otomatis terkirim."
        )
        custom_buttons = [
            [Button.inline("⚙️ Setting Faktur", b"trigger_set_faktur")],
            [Button.inline("⬅️ Kembali", b"menu_start")]
        ]
    elif feature == "autoreply":
        settings = get_user_settings(user_id)
        status = "✅ ON" if settings.get("auto_reply") else "❌ OFF"
        count = len(settings.get("reply_content", []))
        
        help_text = (
            f"🤖 **AUTO REPLY MANAGER**\n"
            f"Status: **{status}**\n"
            f"Total Balasan: **{count} item**\n\n"
            "Bot akan mengirimkan **SEMUA** daftar balasan secara berurutan kepada pengirim pesan pribadi."
        )
        custom_buttons = [
            [Button.inline(f"Saklar: {status}", b"toggle_ar_details")],
            [Button.inline("📋 Edit Daftar & Isi", b"view_ar_content")],
            [Button.inline("⬅️ Kembali", b"menu_start")]
        ]
    elif feature == "ping": help_text = "🏓 **CEK PING:** Ketik `.ping`"
    elif feature == "alive": help_text = "⚡ **STATUS:** Ketik `.alive`"
    elif feature == "spam": help_text = "🤖 **SPAM:** Ketik `.set_spambot` lalu `.spambot`"
    elif feature == "spamai": help_text = "🧠 **SPAM AI:** Ketik `.spamai <target> ...`"
    else: help_text = "Info tidak ditemukan."

    if not custom_buttons: custom_buttons = [[Button.inline("⬅️ Kembali", b"menu_start")]]
    await event.edit(help_text, buttons=custom_buttons)

@bot.on(events.CallbackQuery(pattern=b"menu_status"))
async def cb_status(event):
    user_id = event.sender_id
    idx, row = find_member_row(user_id)
    if not row: return await event.edit("❌ Belum member.", buttons=[[Button.inline("🔙", b"menu_start")]])
    text = f"📊 **INFO MEMBER**\nNama: {row.get('Nama')}\nStatus: {row.get('Status')}\nExpired: {row.get('Expired')}"
    await event.edit(text, buttons=[[Button.inline("⬅️ Kembali", b"menu_start")]])