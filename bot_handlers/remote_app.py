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
        row.append(Button.inline(f"📂 {app_name}", data=f"rapp_view_{app_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([Button.inline("⬅️ Kembali Dashboard", b"menu_admin_dashboard")])
    
    try:
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError:
        pass # Abaikan jika pesan tidak berubah (misal double click)

@bot.on(events.CallbackQuery(pattern=r"rapp_view_(.+)"))
async def cb_remote_view_app(event):
    """Detail Aplikasi: Info PIN & Config"""
    # Parsing nama aplikasi dengan aman (menangani nama dengan underscore)
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_view_", "", 1)
    
    config = get_app_config(app_name)
    devices = get_app_devices(app_name)
    
    total_dev = len(devices) if devices else 0
    
    # PERBAIKAN: Jika config tidak ditemukan/kosong di DB, gunakan nilai Default/NULL
    # agar menu tetap bisa dibuka dan list device tetap bisa diakses.
    if not config:
        config = {} 

    # Gunakan .get() dengan default value "NULL" atau "-"
    pin_val = config.get('pin') or "NULL"
    pass_val = config.get('admin_pass') or "NULL"
    text_val = str(config.get('text', 'NULL'))

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
    app_name = full_data.replace("rapp_devlist_", "", 1)
    
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
    
    # Ambil sisa string setelah prefix
    data_content = full_data[len(prefix):]
    
    # Cari aplikasi yang cocok dari list apps (agar parsing akurat)
    apps = get_all_apps()
    app_name = None
    dev_id = None
    
    for app in apps:
        if data_content.startswith(app + "_"):
            app_name = app
            dev_id = data_content[len(app)+1:]
            break
            
    if not app_name:
        # Fallback split biasa
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
        f"Nama: **{dev_info.get('nama_perangkat')}**\n"
        f"Baterai: {dev_info.get('persen_baterai')}%\n"
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
    # Format: rapp_do_{app}_{dev}_{action}
    
    if full_str.endswith("_buka"):
        action = "buka"
        db_value = "sukses" # Value DB untuk unlock
    elif full_str.endswith("_mulai"):
        action = "mulai"
        db_value = "mulai" # Value DB untuk lock
    else:
        return await event.answer("❌ Aksi tidak valid.", alert=True)
        
    # Parsing App & Dev ID (menghapus prefix 'rapp_do_' dan suffix '_{action}')
    base_data = full_str[8:-(len(action)+1)]
    
    apps = get_all_apps()
    target_app = None
    target_dev = None
    
    for app in apps:
        if base_data.startswith(app + "_"):
            target_app = app
            target_dev = base_data[len(app)+1:]
            break
            
    if not target_app:
        return await event.answer("❌ Error parsing data.", alert=True)
        
    if remote_device_action(target_app, target_dev, db_value):
        await event.answer(f"✅ Perintah '{action.upper()}' dikirim!", alert=True)
        
        # Refresh menu dengan data terbaru
        devices = get_app_devices(target_app)
        dev_info = devices.get(target_dev, {})
        # Update status lokal biar realtime di UI
        dev_info['status_keluar_mode_kios'] = db_value 
        
        msg = (
            f"🎮 **REMOTE DEVICE CONTROL**\n"
            f"ID: `{target_dev}`\n"
            f"Nama: **{dev_info.get('nama_perangkat')}**\n"
            f"Baterai: {dev_info.get('persen_baterai')}%\n"
            f"Status: `{db_value}` (UPDATED)\n"
            f"Online: {dev_info.get('waktu_start')}\n"
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
    app_name = full_data.replace("rapp_editpin_", "", 1)
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
        if not config: config = {} # Safe fallback juga disini
        
        devices = get_app_devices(app_name)
        total_dev = len(devices) if devices else 0
        
        pin_val = config.get('pin') or "NULL"
        pass_val = config.get('admin_pass') or "NULL"
        text_val = str(config.get('text', 'NULL'))
        
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