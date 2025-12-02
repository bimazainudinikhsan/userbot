# bmcodexbot/bot_handlers/remote/apps.py
from telethon import events, Button, errors
from config import bot, ADMIN_ID
from firebase_manager import (
    get_app_config, 
    get_app_devices, 
    update_app_pin,
    update_device_pesan_clear_virus,
    get_app_full_data,
    update_app_field,
    toggle_app_login,
    toggle_app_mode
)
from .state import REMOTE_STATE

@bot.on(events.CallbackQuery(pattern=r"rapp_view_(.+)"))
async def cb_remote_view_app(event):
    """Detail Aplikasi: Info PIN & Config"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_view_", "", 1).strip()
    
    config = get_app_config(app_name)
    devices = get_app_devices(app_name)
    total_dev = len(devices) if devices else 0
    
    status_db = "✅ Data Dimuat"
    if config is None:
        status_db = "⚠️ Config Tidak Ditemukan"
        config = {} 
    
    def format_val(key):
        val = config.get(key)
        if val is None or str(val).lower() == "null" or str(val).strip() == "":
            return "-(Belum Diset)-"
        return str(val)

    pin_val = format_val('pin')
    pass_val = format_val('admin_pass')
    text_val = format_val('text')
    if len(text_val) > 50: text_val = text_val[:50] + "..."

    msg = (
        f"📂 **APLIKASI: {app_name.upper()}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 **Status DB:** `{status_db}`\n"
        f"🔑 **PIN Kiosk:** `{pin_val}`\n"
        f"🔐 **Admin Pass:** `{pass_val}`\n"
        f"📱 **Total Device:** {total_dev}\n"
        f"📝 **Pesan Layar:**\n_{text_val}_\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    buttons = [
        [Button.inline("✏️ Ganti PIN", data=f"rapp_editpin_{app_name}")],
        [Button.inline(f"📱 Lihat Device ({total_dev})", data=f"rapp_devlist_{app_name}:0")],
        [Button.inline("⚙️ Pengaturan Aplikasi", data=f"rapp_settings_{app_name}")],
        [Button.inline("⬅️ Kembali", b"menu_remote_app")]
    ]
    try: await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"rapp_editpin_(.+)"))
async def cb_remote_edit_pin(event):
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_editpin_", "", 1).strip()
    user_id = event.sender_id
    
    REMOTE_STATE[user_id] = {"app": app_name, "action": "edit_pin"}
    
    await event.edit(
        f"✏️ **GANTI PIN: {app_name.upper()}**\nKetik PIN Baru (Angka) sekarang:",
        buttons=[Button.inline("❌ Batal", data=f"rapp_view_{app_name}")]
    )

@bot.on(events.NewMessage(incoming=True))
async def handle_remote_input(event):
    user_id = event.sender_id
    if user_id not in REMOTE_STATE: return
    
    state = REMOTE_STATE[user_id]
    app_name = state["app"]
    
    if state["action"] == "edit_pin":
        new_pin = event.text.strip()
        if not new_pin.isdigit(): return await event.reply("❌ PIN harus angka!")
            
        if update_app_pin(app_name, new_pin):
            await event.reply(f"✅ PIN {app_name} diubah ke `{new_pin}`")
        else:
            await event.reply("❌ Gagal update database.")
            
        del REMOTE_STATE[user_id]
        
        # Kembali ke menu view untuk refresh data
        # Kita panggil logic view lagi atau kirim menu baru
        config = get_app_config(app_name) or {}
        devices = get_app_devices(app_name)
        total_dev = len(devices) if devices else 0
        
        def format_val(key):
            val = config.get(key)
            if val is None or str(val).lower() == "null" or str(val).strip() == "": return "-(Belum Diset)-"
            return str(val)
        
        pin_val = format_val('pin')
        pass_val = format_val('admin_pass')
        text_val = format_val('text')
        if len(text_val) > 50: text_val = text_val[:50] + "..."
        
        msg = (
            f"📂 **APLIKASI: {app_name.upper()}**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📡 **Status DB:** `Updated`\n"
            f"🔑 **PIN Kiosk:** `{pin_val}`\n"
            f"🔐 **Admin Pass:** `{pass_val}`\n"
            f"📱 **Total Device:** {total_dev}\n"
            f"📝 **Pesan Layar:**\n_{text_val}_\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        buttons = [
            [Button.inline("✏️ Ganti PIN", data=f"rapp_editpin_{app_name}")],
            [Button.inline(f"📱 Lihat Device ({total_dev})", data=f"rapp_devlist_{app_name}:0")],
            [Button.inline("⚙️ Pengaturan Aplikasi", data=f"rapp_settings_{app_name}")],
            [Button.inline("⬅️ Kembali", b"menu_remote_app")]
        ]
        await event.respond(msg, buttons=buttons)
    
    elif state["action"] == "search_device":
        from .state import REMOTE_SEARCH_QUERY
        from bot_handlers.remote.devices import cb_remote_device_list
        
        query = event.text.strip()
        if query.lower() == "/batal":
            del REMOTE_STATE[user_id]
            if user_id in REMOTE_SEARCH_QUERY:
                del REMOTE_SEARCH_QUERY[user_id]
            await event.reply("❌ Pencarian dibatalkan.")
            # Kembali ke list tanpa search
            class FakeEvent:
                def __init__(self, user_id, app_name):
                    self.sender_id = user_id
                    self.data = f"rapp_devlist_{app_name}:0".encode()
                    self.chat_id = event.chat_id
                async def edit(self, *args, **kwargs):
                    await event.respond(*args, **kwargs)
                async def answer(self, *args, **kwargs):
                    pass
            fake_event = FakeEvent(user_id, app_name)
            await cb_remote_device_list(fake_event)
            return
        
        # Simpan query
        REMOTE_SEARCH_QUERY[user_id] = query
        del REMOTE_STATE[user_id]
        
        # Refresh list dengan search
        class FakeEvent:
            def __init__(self, user_id, app_name, query):
                self.sender_id = user_id
                self.data = f"rapp_devlist_{app_name}:0:{query}".encode()
                self.chat_id = event.chat_id
            async def edit(self, *args, **kwargs):
                await event.respond(*args, **kwargs)
            async def answer(self, *args, **kwargs):
                pass
        
        fake_event = FakeEvent(user_id, app_name, query)
        await cb_remote_device_list(fake_event)
    
    elif state["action"] == "edit_pesan_clear_virus":
        device_id = state.get("device")
        if not device_id:
            del REMOTE_STATE[user_id]
            return await event.reply("❌ Error: Device ID tidak ditemukan.")
        
        pesan_baru = event.text.strip()
        
        # Jika user kirim "hapus" atau "delete", set ke kosong
        if pesan_baru.lower() in ["hapus", "delete", "kosong"]:
            pesan_baru = ""
            pesan_display = "(Dihapus)"
        else:
            pesan_display = pesan_baru
        
        if update_device_pesan_clear_virus(app_name, device_id, pesan_baru):
            await event.reply(f"✅ Pesan Clear Virus diubah!\nPesan: `{pesan_display if pesan_baru else '(Kosong)'}`")
        else:
            await event.reply("❌ Gagal update database.")
        
        del REMOTE_STATE[user_id]
        
        # Refresh ke menu device action dengan membuat event callback baru
        from bot_handlers.remote.devices import render_device_menu
        devices = get_app_devices(app_name)
        msg, buttons = render_device_menu(app_name, device_id, devices)
        await event.respond(msg, buttons=buttons)
    
    elif state["action"] == "edit_latest_version_code":
        new_value = event.text.strip()
        if update_app_field(app_name, "latest_version_code", new_value):
            await event.reply(f"✅ Latest Version Code diubah ke `{new_value}`")
        else:
            await event.reply("❌ Gagal update database.")
        del REMOTE_STATE[user_id]
        # Refresh ke menu update aplikasi
        class FakeEvent:
            def __init__(self, app_name):
                self.data = f"rapp_update_app_{app_name}".encode()
                self.chat_id = event.chat_id
            async def edit(self, *args, **kwargs):
                await event.respond(*args, **kwargs)
            async def answer(self, *args, **kwargs):
                pass
        fake_event = FakeEvent(app_name)
        await cb_remote_update_app(fake_event)
    
    elif state["action"] == "edit_update_notes":
        new_value = event.text.strip()
        if update_app_field(app_name, "update_notes", new_value):
            await event.reply(f"✅ Update Notes diubah!")
        else:
            await event.reply("❌ Gagal update database.")
        del REMOTE_STATE[user_id]
        # Refresh ke menu update aplikasi
        class FakeEvent:
            def __init__(self, app_name):
                self.data = f"rapp_update_app_{app_name}".encode()
                self.chat_id = event.chat_id
            async def edit(self, *args, **kwargs):
                await event.respond(*args, **kwargs)
            async def answer(self, *args, **kwargs):
                pass
        fake_event = FakeEvent(app_name)
        await cb_remote_update_app(fake_event)
    
    elif state["action"] == "edit_update_url":
        new_value = event.text.strip()
        if update_app_field(app_name, "update_url", new_value):
            await event.reply(f"✅ Update URL diubah ke `{new_value}`")
        else:
            await event.reply("❌ Gagal update database.")
        del REMOTE_STATE[user_id]
        # Refresh ke menu update aplikasi
        class FakeEvent:
            def __init__(self, app_name):
                self.data = f"rapp_update_app_{app_name}".encode()
                self.chat_id = event.chat_id
            async def edit(self, *args, **kwargs):
                await event.respond(*args, **kwargs)
            async def answer(self, *args, **kwargs):
                pass
        fake_event = FakeEvent(app_name)
        await cb_remote_update_app(fake_event)

# ==========================================
# PENGATURAN APLIKASI
# ==========================================

@bot.on(events.CallbackQuery(pattern=r"rapp_settings_(.+)"))
async def cb_remote_settings_app(event):
    """Menu Pengaturan Aplikasi"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_settings_", "", 1).strip()
    
    app_data = get_app_full_data(app_name)
    login_status = app_data.get("login", "no")
    mode_status = app_data.get("mode", "none")
    
    msg = (
        f"⚙️ **PENGATURAN APLIKASI**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**Aplikasi:** `{app_name}`\n\n"
        f"**Status Login:** `{login_status.upper()}`\n"
        f"**Mode:** `{mode_status.upper()}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Pilih pengaturan yang ingin diubah:"
    )
    
    login_icon = "✅" if login_status == "yes" else "❌"
    mode_icon = "🔴" if mode_status == "live" else "⚪"
    
    buttons = [
        [Button.inline(f"{login_icon} Login: {login_status.upper()}", data=f"rapp_toggle_login_{app_name}")],
        [Button.inline(f"{mode_icon} Mode: {mode_status.upper()}", data=f"rapp_toggle_mode_{app_name}")],
        [Button.inline("🔑 Cek Key Aplikasi", data=f"rapp_cek_key_{app_name}")],
        [Button.inline("📱 Update Aplikasi", data=f"rapp_update_app_{app_name}")],
        [Button.inline("⬅️ Kembali", data=f"rapp_view_{app_name}")]
    ]
    
    try: 
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: 
        pass

@bot.on(events.CallbackQuery(pattern=r"rapp_toggle_login_(.+)"))
async def cb_remote_toggle_login(event):
    """Toggle Login Status"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_toggle_login_", "", 1).strip()
    
    new_value = toggle_app_login(app_name)
    if new_value:
        await event.answer(f"✅ Login diubah ke {new_value.upper()}!", alert=True)
        # Refresh settings menu
        class FakeEvent:
            def __init__(self, app_name):
                self.data = f"rapp_settings_{app_name}".encode()
                self.chat_id = event.chat_id
            async def edit(self, *args, **kwargs):
                await event.edit(*args, **kwargs)
            async def answer(self, *args, **kwargs):
                pass
        fake_event = FakeEvent(app_name)
        await cb_remote_settings_app(fake_event)
    else:
        await event.answer("❌ Gagal update login.", alert=True)

@bot.on(events.CallbackQuery(pattern=r"rapp_toggle_mode_(.+)"))
async def cb_remote_toggle_mode(event):
    """Toggle Mode Status"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_toggle_mode_", "", 1).strip()
    
    new_value = toggle_app_mode(app_name)
    if new_value:
        await event.answer(f"✅ Mode diubah ke {new_value.upper()}!", alert=True)
        # Refresh settings menu
        class FakeEvent:
            def __init__(self, app_name):
                self.data = f"rapp_settings_{app_name}".encode()
                self.chat_id = event.chat_id
            async def edit(self, *args, **kwargs):
                await event.edit(*args, **kwargs)
            async def answer(self, *args, **kwargs):
                pass
        fake_event = FakeEvent(app_name)
        await cb_remote_settings_app(fake_event)
    else:
        await event.answer("❌ Gagal update mode.", alert=True)

@bot.on(events.CallbackQuery(pattern=r"rapp_cek_key_(.+)"))
async def cb_remote_cek_key(event):
    """Cek Key Aplikasi"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_cek_key_", "", 1).strip()
    
    app_data = get_app_full_data(app_name)
    key = app_data.get("nama_id_aplikasi", "-")
    
    msg = (
        f"🔑 **KEY APLIKASI**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**Aplikasi:** `{app_name}`\n\n"
        f"**Key:** `{key}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    buttons = [
        [Button.inline("⬅️ Kembali", data=f"rapp_settings_{app_name}")]
    ]
    
    try: 
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: 
        pass

@bot.on(events.CallbackQuery(pattern=r"rapp_update_app_(.+)"))
async def cb_remote_update_app(event):
    """Menu Update Aplikasi"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_update_app_", "", 1).strip()
    
    app_data = get_app_full_data(app_name)
    latest_version_code = app_data.get("latest_version_code", "-")
    update_notes = app_data.get("update_notes", "-")
    update_url = app_data.get("update_url", "-")
    
    # Format update_notes jika terlalu panjang
    if update_notes and update_notes != "-" and len(update_notes) > 50:
        update_notes_display = update_notes[:50] + "..."
    else:
        update_notes_display = update_notes if update_notes else "(Kosong)"
    
    msg = (
        f"📱 **UPDATE APLIKASI**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**Aplikasi:** `{app_name}`\n\n"
        f"**Latest Version Code:** `{latest_version_code}`\n"
        f"**Update Notes:** `{update_notes_display}`\n"
        f"**Update URL:** `{update_url if update_url else '(Kosong)'}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Pilih data yang ingin diubah:"
    )
    
    buttons = [
        [Button.inline("✏️ Edit Latest Version Code", data=f"rapp_edit_version_{app_name}")],
        [Button.inline("✏️ Edit Update Notes", data=f"rapp_edit_notes_{app_name}")],
        [Button.inline("✏️ Edit Update URL", data=f"rapp_edit_url_{app_name}")],
        [Button.inline("⬅️ Kembali", data=f"rapp_settings_{app_name}")]
    ]
    
    try: 
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: 
        pass

@bot.on(events.CallbackQuery(pattern=r"rapp_edit_version_(.+)"))
async def cb_remote_edit_version(event):
    """Edit Latest Version Code"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_edit_version_", "", 1).strip()
    user_id = event.sender_id
    
    app_data = get_app_full_data(app_name)
    current_value = app_data.get("latest_version_code", "")
    
    REMOTE_STATE[user_id] = {"app": app_name, "action": "edit_latest_version_code"}
    
    await event.edit(
        f"✏️ **EDIT LATEST VERSION CODE**\n"
        f"Aplikasi: `{app_name}`\n\n"
        f"Nilai saat ini: `{current_value if current_value else '(Kosong)'}`\n\n"
        f"Ketik nilai baru sekarang:",
        buttons=[Button.inline("❌ Batal", data=f"rapp_update_app_{app_name}")]
    )

@bot.on(events.CallbackQuery(pattern=r"rapp_edit_notes_(.+)"))
async def cb_remote_edit_notes(event):
    """Edit Update Notes"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_edit_notes_", "", 1).strip()
    user_id = event.sender_id
    
    app_data = get_app_full_data(app_name)
    current_value = app_data.get("update_notes", "")
    
    REMOTE_STATE[user_id] = {"app": app_name, "action": "edit_update_notes"}
    
    await event.edit(
        f"✏️ **EDIT UPDATE NOTES**\n"
        f"Aplikasi: `{app_name}`\n\n"
        f"Notes saat ini: `{current_value if current_value else '(Kosong)'}`\n\n"
        f"Ketik notes baru sekarang:",
        buttons=[Button.inline("❌ Batal", data=f"rapp_update_app_{app_name}")]
    )

@bot.on(events.CallbackQuery(pattern=r"rapp_edit_url_(.+)"))
async def cb_remote_edit_url(event):
    """Edit Update URL"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_edit_url_", "", 1).strip()
    user_id = event.sender_id
    
    app_data = get_app_full_data(app_name)
    current_value = app_data.get("update_url", "")
    
    REMOTE_STATE[user_id] = {"app": app_name, "action": "edit_update_url"}
    
    await event.edit(
        f"✏️ **EDIT UPDATE URL**\n"
        f"Aplikasi: `{app_name}`\n\n"
        f"URL saat ini: `{current_value if current_value else '(Kosong)'}`\n\n"
        f"Ketik URL baru sekarang:",
        buttons=[Button.inline("❌ Batal", data=f"rapp_update_app_{app_name}")]
    )