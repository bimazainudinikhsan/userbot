# bmcodexbot/bot_handlers/remote/devices.py
from telethon import events, Button, errors
from config import bot, ADMIN_ID
from firebase_manager import get_app_devices, get_all_apps, remote_device_action

@bot.on(events.CallbackQuery(pattern=r"rapp_devlist_(.+)"))
async def cb_remote_device_list(event):
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_devlist_", "", 1).strip()
    devices = get_app_devices(app_name)
    
    if not devices:
        msg = f"📱 **LIST DEVICE ({app_name})**\n\n❌ Belum ada perangkat terdeteksi."
        buttons = [[Button.inline("⬅️ Kembali", data=f"rapp_view_{app_name}")]]
        return await event.edit(msg, buttons=buttons)
        
    msg = f"📱 **LIST DEVICE ({app_name})**\nPilih device untuk aksi remote:"
    buttons = []
    limit = 10
    count = 0
    
    for dev_id, info in devices.items():
        if count >= limit: break
        dev_name = info.get('nama_perangkat', 'Unknown Device')
        batt = info.get('persen_baterai', '?')
        buttons.append([Button.inline(f"{dev_name} ({batt}%)", data=f"rapp_act_{app_name}_{dev_id}")])
        count += 1
    
    if len(devices) > limit: msg += f"\n\n_(Menampilkan 10 dari {len(devices)} device)_"
    buttons.append([Button.inline("⬅️ Kembali", data=f"rapp_view_{app_name}")])
    try: await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"rapp_act_(.+)"))
async def cb_remote_device_action_menu(event):
    prefix = f"rapp_act_"
    full_data = event.data.decode()
    data_content = full_data[len(prefix):]
    
    apps = get_all_apps()
    app_name = None
    dev_id = None
    
    # Parsing Logic
    for app in apps:
        app_clean = str(app).strip()
        if data_content.startswith(app_clean + "_"):
            app_name = app_clean
            dev_id = data_content[len(app_clean)+1:]
            break
            
    if not app_name:
        parts = data_content.split("_")
        if len(parts) >= 2: app_name = parts[0]; dev_id = "_".join(parts[1:])
        else: return await event.answer("❌ Error parsing.", alert=True)
    
    devices = get_app_devices(app_name)
    dev_info = devices.get(dev_id, {})
    nm = dev_info.get('nama_perangkat', 'Unknown')
    bt = dev_info.get('persen_baterai', 0)
    st = dev_info.get('status_keluar_mode_kios', 'Unknown')
    wk = dev_info.get('waktu_start', '-')
    
    msg = (
        f"🎮 **REMOTE CONTROL**\nID: `{dev_id}`\nNama: **{nm}**\nBaterai: {bt}%\nStatus: `{st}`\nOnline: {wk}\n"
    )
    buttons = [
        [Button.inline("🔓 Buka Paksa (Unlock)", data=f"rapp_do_{app_name}_{dev_id}_buka")],
        [Button.inline("🔒 Kunci Kembali (Start)", data=f"rapp_do_{app_name}_{dev_id}_mulai")],
        [Button.inline("⬅️ Kembali List", data=f"rapp_devlist_{app_name}")]
    ]
    try: await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"rapp_do_(.+)"))
async def cb_remote_exec_action(event):
    full_str = event.data.decode()
    if full_str.endswith("_buka"): action, db_value = "buka", "sukses" 
    elif full_str.endswith("_mulai"): action, db_value = "mulai", "mulai" 
    else: return await event.answer("❌ Aksi invalid.", alert=True)
        
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
            
    if not target_app: return await event.answer("❌ Error parsing.", alert=True)
        
    if remote_device_action(target_app, target_dev, db_value):
        await event.answer(f"✅ Perintah '{action.upper()}' dikirim!", alert=True)
        # Refresh UI
        devices = get_app_devices(target_app)
        dev_info = devices.get(target_dev, {})
        nm = dev_info.get('nama_perangkat', 'Unknown')
        bt = dev_info.get('persen_baterai', 0)
        wk = dev_info.get('waktu_start', '-')
        
        msg = (
            f"🎮 **REMOTE CONTROL**\nID: `{target_dev}`\nNama: **{nm}**\nBaterai: {bt}%\nStatus: `{db_value}` (UPDATED)\nOnline: {wk}\n"
        )
        buttons = [
            [Button.inline("🔓 Buka Paksa (Unlock)", data=f"rapp_do_{target_app}_{target_dev}_buka")],
            [Button.inline("🔒 Kunci Kembali (Start)", data=f"rapp_do_{target_app}_{target_dev}_mulai")],
            [Button.inline("⬅️ Kembali List", data=f"rapp_devlist_{target_app}")]
        ]
        try: await event.edit(msg, buttons=buttons)
        except errors.MessageNotModifiedError: pass
    else:
        await event.answer("❌ Gagal kirim DB.", alert=True)