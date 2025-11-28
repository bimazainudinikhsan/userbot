# bmcodexbot/bot_handlers/remote/menu.py
from telethon import events, Button, errors
from config import bot, ADMIN_ID
from firebase_manager import get_all_apps

@bot.on(events.CallbackQuery(pattern=b"menu_remote_app"))
async def cb_remote_dashboard(event):
    """Menu Utama: Menampilkan Daftar Aplikasi"""
    user_id = event.sender_id
    if user_id != ADMIN_ID:
        return await event.answer("❌ Akses Ditolak!", alert=True)
    
    apps = get_all_apps()
    
    # Jika apps kosong
    if not apps:
        try:
            return await event.edit("⚠️ **Tidak ada aplikasi ditemukan di database.**\nCek koneksi Firebase.", 
                                    buttons=[[Button.inline("⬅️ Kembali", b"menu_admin_dashboard")]])
        except errors.MessageNotModifiedError: return

    msg = "📱 **REMOTE APLIKASI CONTROL (FIREBASE)**\n\nSilakan pilih aplikasi:"
    buttons = []
    
    # Buat tombol per aplikasi (2 kolom)
    row = []
    for app_name in apps:
        clean_name = str(app_name).strip()
        row.append(Button.inline(f"📂 {clean_name}", data=f"rapp_view_{clean_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    # Tombol kembali ke Dashboard Admin
    buttons.append([Button.inline("⬅️ Kembali Dashboard", b"menu_admin_dashboard")])
    
    try:
        await event.edit(msg, buttons=buttons)
    except errors.MessageNotModifiedError:
        pass