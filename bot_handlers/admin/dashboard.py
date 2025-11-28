from telethon import events, Button, errors
from config import bot, ADMIN_ID
from state import GLOBAL_CONFIG

# ==========================================
# HELPER: KONTEN DASHBOARD
# ==========================================
def get_dashboard_content():
    """Mengembalikan text dan buttons untuk dashboard admin."""
    is_trial_on = GLOBAL_CONFIG.get("free_trial", False)
    status_trial = "✅ ON" if is_trial_on else "❌ OFF"
    
    text = (
        "👑 **ADMINISTRATOR PANEL**\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "Selamat datang kembali, Tuan. \n"
        "Sistem telah siap. Silakan pilih modul manajemen:\n"
    )
    
    buttons = [
        # Baris 1: Mode Trial & Remote
        [Button.inline(f"🆓 Free Trial: {status_trial}", b"TOGGLE_TRIAL"),
         Button.inline("📱 Remote Apps (Firebase)", b"menu_remote_app")],
        
        # Baris 2: Member & Fitur
        [Button.inline("👥 Kelola Member", b"cmd_admin_status"), 
         Button.inline("🌍 Fitur Global", b"cmd_global_fitur")],
        
        # Baris 3: Izin User
        [Button.inline("🔐 Izin User Spesifik", b"cmd_admin_fitur")],
        
        # Baris 4: System
        [Button.inline("🔄 Restart Bot", b"cmd_admin_restart"), 
         Button.inline("🛑 Shutdown", b"cmd_admin_shutdown")],
         
        # Baris 5: Bantuan
        [Button.inline("ℹ️ Bantuan Perintah", b"cmd_admin_help")]
    ]
    return text, buttons

# ==========================================
# HANDLER COMMAND /START KHUSUS ADMIN
# ==========================================
@bot.on(events.NewMessage(pattern="/start"))
async def handler_admin_start(event):
    if event.sender_id == ADMIN_ID:
        text, buttons = get_dashboard_content()
        await event.respond(text, buttons=buttons)
        raise events.StopPropagation

@bot.on(events.NewMessage(pattern="/admin"))
async def handler_admin(event):
    if event.sender_id != ADMIN_ID: return
    text, buttons = get_dashboard_content()
    await event.respond(text, buttons=buttons)

# ==========================================
# HANDLER CALLBACK (MENU UTAMA)
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"menu_admin_dashboard"))
async def cb_admin_dashboard(event):
    if event.sender_id != ADMIN_ID: return
    text, buttons = get_dashboard_content()
    # Edit pesan yang ada (Tindih)
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"TOGGLE_TRIAL"))
async def cb_toggle_trial(event):
    if event.sender_id != ADMIN_ID: return
    GLOBAL_CONFIG["free_trial"] = not GLOBAL_CONFIG.get("free_trial", False)
    # Refresh dashboard langsung
    text, buttons = get_dashboard_content()
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"cmd_admin_help"))
async def cb_admin_help(event):
    if event.sender_id != ADMIN_ID: return
    text = (
        "ℹ️ **PANDUAN ADMIN**\n\n"
        "• **Free Trial**: Mengaktifkan mode trial otomatis untuk user baru.\n"
        "• **Remote Apps**: Mengontrol aplikasi Kiosk via Firebase.\n"
        "• **Kelola Member**: Lihat, edit, atau hapus user.\n"
        "• **Fitur Global**: Matikan fitur tertentu untuk semua user (Maintenance).\n"
        "• **Restart**: Mulai ulang bot jika ada update/error."
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"menu_admin_dashboard")]])