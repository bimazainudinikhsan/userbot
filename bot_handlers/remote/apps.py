# bmcodexbot/bot_handlers/remote/apps.py
from telethon import events, Button, errors
from config import bot, ADMIN_ID
from firebase_manager import get_app_config, get_app_devices, update_app_pin
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
        [Button.inline(f"📱 Lihat Device ({total_dev})", data=f"rapp_devlist_{app_name}")],
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
            [Button.inline(f"📱 Lihat Device ({total_dev})", data=f"rapp_devlist_{app_name}")],
            [Button.inline("⬅️ Kembali", b"menu_remote_app")]
        ]
        await event.respond(msg, buttons=buttons)