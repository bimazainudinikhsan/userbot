from telethon import events, Button
from config import bot, ADMIN_ID
from state import GLOBAL_CONFIG

# Import handler remote app agar tombolnya berfungsi
import bot_handlers.remote_app 

# ==========================================
# HANDLER COMMAND /START KHUSUS ADMIN
# ==========================================
@bot.on(events.NewMessage(pattern="/start"))
async def handler_admin_start(event):
    # Cek apakah pengirim adalah Admin
    if event.sender_id == ADMIN_ID:
        await show_admin_dashboard(event)
        # StopPropagation penting agar bot tidak lanjut memproses 
        # handler /start lain (misalnya menu member biasa di nav.py)
        raise events.StopPropagation

# ==========================================
# HANDLER UTAMA DASHBOARD
# ==========================================

@bot.on(events.NewMessage(pattern="/admin"))
async def handler_admin(event):
    if event.sender_id != ADMIN_ID: return
    await show_admin_dashboard(event)

@bot.on(events.CallbackQuery(pattern=b"menu_admin_dashboard"))
async def cb_admin_dashboard(event):
    if event.sender_id != ADMIN_ID: return
    await show_admin_dashboard(event)

@bot.on(events.CallbackQuery(pattern=b"close_menu"))
async def cb_close(event):
    await event.delete()

@bot.on(events.CallbackQuery(pattern=b"TOGGLE_TRIAL"))
async def cb_toggle_trial(event):
    if event.sender_id != ADMIN_ID: return
    GLOBAL_CONFIG["free_trial"] = not GLOBAL_CONFIG.get("free_trial", False)
    await show_admin_dashboard(event)

async def show_admin_dashboard(event):
    is_trial_on = GLOBAL_CONFIG.get("free_trial", False)
    status_trial = "✅ ON" if is_trial_on else "❌ OFF"
    
    text = "👑 **ADMIN DASHBOARD**\nSelamat datang, Admin! Silakan pilih menu manajemen:"
    
    buttons = [
        # Baris 1: Mode Trial
        [Button.inline(f"🆓 Mode Free Trial: {status_trial}", b"TOGGLE_TRIAL")],
        
        # Baris 2: Manajemen Member & REMOTE APP
        [
            Button.inline("👥 Manajemen Member", b"cmd_admin_status"),
            Button.inline("📱 Remote Aplikasi", b"menu_remote_app") 
        ],
        
        # Baris 3: Fitur Global & Izin User
        [Button.inline("🌍 On/Off Fitur Global", b"cmd_global_fitur"), Button.inline("👤 Izin Fitur User", b"cmd_admin_fitur")],
        
        # Baris 4: System
        [Button.inline("🔄 Restart System", b"cmd_admin_restart"), Button.inline("🛑 Shutdown", b"cmd_admin_shutdown")],
        
        # Baris 5: Bantuan & Close
        [Button.inline("ℹ️ Bantuan", b"cmd_admin_help"), Button.inline("❌ Close", b"close_menu")]
    ]
    
    # PERBAIKAN: Cek tipe event agar tidak error "MessageIdInvalidError"
    # NewMessage (teks dari user) -> Tidak bisa diedit -> Pakai respond()
    # CallbackQuery (klik tombol) -> Bisa diedit -> Pakai edit()
    if isinstance(event, events.CallbackQuery.Event):
        await event.edit(text, buttons=buttons)
    else:
        await event.respond(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"cmd_admin_help"))
async def cb_admin_help(event):
    await event.edit("Gunakan tombol menu untuk navigasi.", buttons=[[Button.inline("⬅️ Kembali", b"menu_admin_dashboard")]])