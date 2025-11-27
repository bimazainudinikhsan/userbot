from telethon import events, Button, errors
from config import bot, ADMIN_ID
from firebase_manager import (
    get_all_apps, get_app_config, get_app_devices, 
    update_app_pin, remote_device_action
)

# State untuk input edit PIN
REMOTE_STATE = {} 

@bot.on(events.CallbackQuery(pattern=b"menu_remote_app"))
async def cb_remote_dashboard(event):
    """Menu Utama: Menampilkan Daftar Aplikasi"""
    user_id = event.sender_id
    if user_id != ADMIN_ID:
        return await event.answer("❌ Akses Ditolak!", alert=True)
    
    apps = get_all_apps()
    
    if not apps:
        try:
            return await event.edit("⚠️ **Tidak ada aplikasi ditemukan di database.**", 
                                    buttons=[[Button.inline("⬅️ Kembali", b"menu_admin_dashboard")]])
        except errors.MessageNotModifiedError: return

    msg = "📱 **REMOTE APLIKASI CONTROL**\n\nSilakan pilih aplikasi yang ingin dikelola:"
    buttons = []
    
    # Buat tombol per aplikasi (2 kolom)
    row = []
    for app_name in apps:
        # Pastikan app_name string bersih
        clean_name = str(app_name).strip()
        row.append(Button.inline(f"📂 {clean_name}", data=f"rapp_view_{clean_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([Button.inline("⬅️ Kembali Dashboard", b"menu_admin_dashboard")])
    
    try:
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError:
        pass 

@bot.on(events.CallbackQuery(pattern=r"rapp_view_(.+)"))
async def cb_remote_view_app(event):
    """Detail Aplikasi: Info PIN & Config"""
    full_data = event.data.decode()
    # Replace prefix dan strip spasi agar nama aplikasi akurat
    app_name = full_data.replace("rapp_view_", "", 1).strip()
    
    config = get_app_config(app_name)
    devices = get_app_devices(app_name)
    
    total_dev = len(devices) if devices else 0
    
    # Fallback jika config kosong (Database node belum lengkap)
    if not config:
        config = {}

    # Helper untuk display data kosong
    def val_or_empty(key, default="-(Kosong)-"):
        val = config.get(key)
        # Jika val None atau string kosong atau string "NULL" dari firebase_manager
        if val is None or val == "" or val == "NULL":
            return default
        return val

    pin_val = val_or_empty('pin')
    pass_val = val_or_empty('admin_pass')
    text_val = str(val_or_empty('text'))

    msg = (
        f"📂 **APLIKASI: {app_name.upper()}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔑 **PIN Kiosk:** `{pin_val}`\n"
        f"🔐 **Admin Pass:** `{pass_val}`\n"
        f"📱 **Total Device:** {total_dev}\n"
        f"📝 **Pesan Layar:**\n_{text_val[:100]}..._\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    buttons = [
        [Button.inline("✏️ Ganti PIN", data=f"rapp_editpin_{app_name}")],
        [Button.inline(f"📱 Lihat Device ({total_dev})", data=f"rapp_devlist_{app_name}")],
        [Button.inline("⬅️ Kembali", b"menu_remote_app")]
    ]
    try:
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"rapp_devlist_(.+)"))
async def cb_remote_device_list(event):
    """List Perangkat yang Terhubung"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_devlist_", "", 1).strip()
    
    devices = get_app_devices(app_name)
    
    if not devices:
        return await event.answer("⚠️ Belum ada perangkat yang terhubung.", alert=True)
        
    msg = f"📱 **LIST DEVICE ({app_name})**\nPilih device untuk aksi remote:"
    buttons = []
    
    # Batasi tampilan jika device terlalu banyak (misal max 10)
    limit = 10
    count = 0
    
    for dev_id, info in devices.items():
        if count >= limit: break
        
        dev_name = info.get('nama_perangkat', 'Unknown')
        batt = info.get('persen_baterai', '?')
        
        btn_text = f"{dev_name} ({batt}%)"
        buttons.append([Button.inline(btn_text, data=f"rapp_act_{app_name}_{dev_id}")])
        count += 1
        
    buttons.append([Button.inline("⬅️ Kembali", data=f"rapp_view_{app_name}")])
    try:
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"rapp_act_(.+)"))
async def cb_remote_device_action_menu(event):
    """Menu Aksi untuk Satu Device"""
    prefix = f"rapp_act_"
    full_data = event.data.decode()
    
    data_content = full_data[len(prefix):]
    
    apps = get_all_apps()
    app_name = None
    dev_id = None
    
    # Logic matching yang lebih robust
    for app in apps:
        app_clean = str(app).strip()
        if data_content.startswith(app_clean + "_"):
            app_name = app_clean
            dev_id = data_content[len(app_clean)+1:]
            break
            
    if not app_name:
        parts = data_content.split("_")
        if len(parts) >= 2:
            app_name = parts[0]
            dev_id = "_".join(parts[1:])
        else:
             return await event.answer("❌ Error parsing device ID.", alert=True)
    
    devices = get_app_devices(app_name)
    dev_info = devices.get(dev_id, {})
    
    status = dev_info.get('status_keluar_mode_kios', '-')
    waktu = dev_info.get('waktu_start', '-')
    
    msg = (
        f"🎮 **REMOTE DEVICE CONTROL**\n"
        f"ID: `{dev_id}`\n"
        f"Nama: **{dev_info.get('nama_perangkat', 'Unknown')}**\n"
        f"Baterai: {dev_info.get('persen_baterai', 0)}%\n"
        f"Status: `{status}`\n"
        f"Online: {waktu}\n"
    )
    
    buttons = [
        [Button.inline("🔓 Buka Paksa (Unlock)", data=f"rapp_do_{app_name}_{dev_id}_buka")],
        [Button.inline("🔒 Kunci Kembali (Start)", data=f"rapp_do_{app_name}_{dev_id}_mulai")],
        [Button.inline("⬅️ Kembali List", data=f"rapp_devlist_{app_name}")]
    ]
    try:
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"rapp_do_(.+)"))
async def cb_remote_exec_action(event):
    """Eksekusi Perintah Remote"""
    full_str = event.data.decode()
    
    if full_str.endswith("_buka"):
        action = "buka"
        db_value = "sukses" 
    elif full_str.endswith("_mulai"):
        action = "mulai"
        db_value = "mulai" 
    else:
        return await event.answer("❌ Aksi tidak valid.", alert=True)
        
    base_data = full_str[8:-(len(action)+1)]
    
    apps = get_all_apps()
    target_app = None
    target_dev = None
    
    for app in apps:
        app_clean = str(app).strip()
        if base_data.startswith(app_clean + "_"):
            target_app = app_clean
            target_dev = base_data[len(app_clean)+1:]
            break
            
    if not target_app:
        return await event.answer("❌ Error parsing data.", alert=True)
        
    if remote_device_action(target_app, target_dev, db_value):
        await event.answer(f"✅ Perintah '{action.upper()}' dikirim!", alert=True)
        
        devices = get_app_devices(target_app)
        dev_info = devices.get(target_dev, {})
        dev_info['status_keluar_mode_kios'] = db_value 
        
        msg = (
            f"🎮 **REMOTE DEVICE CONTROL**\n"
            f"ID: `{target_dev}`\n"
            f"Nama: **{dev_info.get('nama_perangkat', 'Unknown')}**\n"
            f"Baterai: {dev_info.get('persen_baterai', 0)}%\n"
            f"Status: `{db_value}` (UPDATED)\n"
            f"Online: {dev_info.get('waktu_start', '-')}\n"
        )
        buttons = [
            [Button.inline("🔓 Buka Paksa (Unlock)", data=f"rapp_do_{target_app}_{target_dev}_buka")],
            [Button.inline("🔒 Kunci Kembali (Start)", data=f"rapp_do_{target_app}_{target_dev}_mulai")],
            [Button.inline("⬅️ Kembali List", data=f"rapp_devlist_{target_app}")]
        ]
        try:
            await event.edit(msg, buttons=buttons)
        except errors.MessageNotModifiedError: pass
        
    else:
        await event.answer("❌ Gagal mengirim perintah ke Database.", alert=True)

@bot.on(events.CallbackQuery(pattern=r"rapp_editpin_(.+)"))
async def cb_remote_edit_pin(event):
    """Mode Edit PIN"""
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_editpin_", "", 1).strip()
    user_id = event.sender_id
    
    REMOTE_STATE[user_id] = {"app": app_name, "action": "edit_pin"}
    
    await event.edit(
        f"✏️ **GANTI PIN: {app_name.upper()}**\n\n"
        f"Silakan ketik PIN Baru (Angka) sekarang:",
        buttons=[Button.inline("❌ Batal", data=f"rapp_view_{app_name}")]
    )

@bot.on(events.NewMessage(incoming=True))
async def handle_remote_input(event):
    """Handler Input Teks untuk Edit PIN"""
    user_id = event.sender_id
    if user_id not in REMOTE_STATE: return
    
    state = REMOTE_STATE[user_id]
    app_name = state["app"]
    
    if state["action"] == "edit_pin":
        new_pin = event.text.strip()
        if not new_pin.isdigit():
            return await event.reply("❌ PIN harus berupa angka!")
            
        if update_app_pin(app_name, new_pin):
            await event.reply(f"✅ PIN {app_name} berhasil diubah ke `{new_pin}`")
        else:
            await event.reply("❌ Gagal update database.")
            
        del REMOTE_STATE[user_id]
        
        # Kembali ke menu view
        config = get_app_config(app_name)
        if not config: config = {} 
        
        devices = get_app_devices(app_name)
        total_dev = len(devices) if devices else 0
        
        def val_or_empty(key, default="-(Kosong)-"):
            val = config.get(key)
            if val is None or val == "" or val == "NULL": return default
            return val
        
        pin_val = val_or_empty('pin')
        pass_val = val_or_empty('admin_pass')
        text_val = str(val_or_empty('text'))
        
        msg = (
            f"📂 **APLIKASI: {app_name.upper()}**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔑 **PIN Kiosk:** `{pin_val}`\n"
            f"🔐 **Admin Pass:** `{pass_val}`\n"
            f"📱 **Total Device:** {total_dev}\n"
            f"📝 **Pesan Layar:**\n_{text_val[:100]}..._\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        buttons = [
            [Button.inline("✏️ Ganti PIN", data=f"rapp_editpin_{app_name}")],
            [Button.inline(f"📱 Lihat Device ({total_dev})", data=f"rapp_devlist_{app_name}")],
            [Button.inline("⬅️ Kembali", b"menu_remote_app")]
        ]
        await event.respond(msg, buttons=buttons)