from telethon import events, Button
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
        return await event.edit("⚠️ **Tidak ada aplikasi ditemukan di database.**", 
                                buttons=[[Button.inline("⬅️ Kembali", b"menu_admin_dashboard")]])

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
    await event.edit(msg, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"rapp_view_(.+)"))
async def cb_remote_view_app(event):
    """Detail Aplikasi: Info PIN & Config"""
    app_name = event.data.decode().split("_")[2]
    config = get_app_config(app_name)
    devices = get_app_devices(app_name)
    
    total_dev = len(devices) if devices else 0
    
    if not config:
        return await event.answer("❌ Gagal memuat data aplikasi.", alert=True)

    msg = (
        f"📂 **APLIKASI: {app_name.upper()}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔑 **PIN Kiosk:** `{config['pin']}`\n"
        f"🔐 **Admin Pass:** `{config['admin_pass']}`\n"
        f"📱 **Total Device:** {total_dev}\n"
        f"📝 **Pesan Layar:**\n_{config['text'][:100]}..._\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    buttons = [
        [Button.inline("✏️ Ganti PIN", data=f"rapp_editpin_{app_name}")],
        [Button.inline(f"📱 Lihat Device ({total_dev})", data=f"rapp_devlist_{app_name}")],
        [Button.inline("⬅️ Kembali", b"menu_remote_app")]
    ]
    await event.edit(msg, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"rapp_devlist_(.+)"))
async def cb_remote_device_list(event):
    """List Perangkat yang Terhubung"""
    app_name = event.data.decode().split("_")[2]
    devices = get_app_devices(app_name)
    
    if not devices:
        return await event.answer("⚠️ Belum ada perangkat yang terhubung.", alert=True)
        
    msg = f"📱 **LIST DEVICE ({app_name})**\nPilih device untuk aksi remote:"
    buttons = []
    
    for dev_id, info in devices.items():
        dev_name = info.get('nama_perangkat', 'Unknown')
        batt = info.get('persen_baterai', '?')
        # Potong ID biar tombol gak kepanjangan
        short_id = dev_id.replace("android_", "")[:6]
        
        btn_text = f"{dev_name} ({batt}%)"
        buttons.append([Button.inline(btn_text, data=f"rapp_act_{app_name}_{dev_id}")])
        
    buttons.append([Button.inline("⬅️ Kembali", data=f"rapp_view_{app_name}")])
    await event.edit(msg, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"rapp_act_(.+)"))
async def cb_remote_device_action_menu(event):
    """Menu Aksi untuk Satu Device"""
    data = event.data.decode().split("_")
    app_name = data[2]
    # Gabungkan sisa split jika ID mengandung underscore, atau ambil index ke-3
    # Format ID di DB: android_xxxx. Karena split by '_', kita harus hati-hati.
    # Cara aman: ambil substring setelah rapp_act_{app_name}_
    prefix = f"rapp_act_{app_name}_"
    dev_id = event.data.decode()[len(prefix):]
    
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
    await event.edit(msg, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"rapp_do_(.+)"))
async def cb_remote_exec_action(event):
    """Eksekusi Perintah Remote"""
    # Format: rapp_do_{app_name}_{dev_id}_{action}
    parts = event.data.decode().split("_")
    action = parts[-1]
    
    # Reconstruct app_name & dev_id is tricky with splits. 
    # Logic: rapp_do_ (8 chars) ... _{action}
    full_str = event.data.decode()
    base_data = full_str[8:-(len(action)+1)] # remove prefix & suffix action
    
    # base_data is like "hot51_android_12345"
    # Kita perlu tahu app_name. Untungnya kita punya list app_name dari firebase
    # Tapi demi efisiensi, kita asumsikan app_name tidak ada underscore atau kita split manual
    # Cara paling aman: parsing manual
    
    # Mencari split pertama untuk app_name
    apps = get_all_apps() # Ambil list app valid untuk matching
    target_app = None
    target_dev = None
    
    for app in apps:
        if base_data.startswith(app + "_"):
            target_app = app
            target_dev = base_data[len(app)+1:]
            break
            
    if not target_app:
        return await event.answer("❌ Error parsing data.", alert=True)
        
    # Mapping action ke value database
    db_value = "sukses" if action == "buka" else "mulai"
    
    if remote_device_action(target_app, target_dev, db_value):
        await event.answer(f"✅ Perintah '{action}' dikirim!", alert=True)
        # Refresh menu
        await cb_remote_device_action_menu(event)
        # Hacky re-trigger event with correct data structure
        event.data = f"rapp_act_{target_app}_{target_dev}".encode()
    else:
        await event.answer("❌ Gagal mengirim perintah.", alert=True)

@bot.on(events.CallbackQuery(pattern=r"rapp_editpin_(.+)"))
async def cb_remote_edit_pin(event):
    """Mode Edit PIN"""
    app_name = event.data.decode().split("_")[2]
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
        
        # Kembali ke menu view (Trigger ulang)
        # Karena NewMessage tidak bisa edit pesan bot sebelumnya dengan mudah tanpa ID,
        # Kita kirim pesan baru berisi menu
        config = get_app_config(app_name)
        devices = get_app_devices(app_name)
        total_dev = len(devices) if devices else 0
        
        msg = (
            f"📂 **APLIKASI: {app_name.upper()}**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔑 **PIN Kiosk:** `{config['pin']}`\n"
            f"🔐 **Admin Pass:** `{config['admin_pass']}`\n"
            f"📱 **Total Device:** {total_dev}\n"
            f"📝 **Pesan Layar:**\n_{config['text'][:100]}..._\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        buttons = [
            [Button.inline("✏️ Ganti PIN", data=f"rapp_editpin_{app_name}")],
            [Button.inline(f"📱 Lihat Device ({total_dev})", data=f"rapp_devlist_{app_name}")],
            [Button.inline("⬅️ Kembali", b"menu_remote_app")]
        ]
        await event.respond(msg, buttons=buttons)