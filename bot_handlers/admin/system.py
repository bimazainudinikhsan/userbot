import asyncio, os, sys, json
from datetime import datetime
from telethon import events, Button
from config import bot, ADMIN_ID
from database import get_all_members_safe
from state import ACTIVE_USERBOTS

# Track the auto_update_watcher task untuk proper cleanup
AUTO_UPDATE_TASK = None

async def execute_restart_sequence(trigger_event=None):
    target_chat_id = ADMIN_ID
    status_msg = None

    if trigger_event:
        target_chat_id = trigger_event.chat_id
        await trigger_event.answer("🔄 Memulai proses...", alert=True)
        status_msg = await trigger_event.edit("🔄 **SYSTEM RESTART**\n\nMengirim notifikasi...")
    else:
        status_msg = await bot.send_message(ADMIN_ID, "🔄 **AUTO UPDATE DETECTED**\n\nMengirim notifikasi...")

    members = get_all_members_safe()
    now_str = datetime.now().strftime("%d-%m-%Y %H:%M WIB")
    mc = read_manager_control()
    mc["system_status"] = "maintenance"
    mc["restart_started_at"] = datetime.now().isoformat()
    write_manager_control(mc)
    _log_audit("restart_start", {"at": mc["restart_started_at"]})
    
    # Broadcast Kilat
    for row in members:
        try:
            uid = str(row.get("User ID"))
            if uid.isdigit() and int(uid) != ADMIN_ID:
                await bot.send_message(int(uid), f"⚠️ **PENGUMUMAN SISTEM**\nSistem sedang melakukan pembaruan pada {now_str}. Mohon tunggu beberapa saat hingga bot kembali normal.\nEstimasi: 1–3 menit")
        except: pass
    
    if status_msg: await status_msg.edit("🔄 Rebooting Server…")

    # Flag untuk pesan sukses setelah nyala kembali
    with open("RESTART_FLAG.json", "w") as f: 
        json.dump({"chat_id": target_chat_id, "admin_id": ADMIN_ID, "started_at": mc["restart_started_at"]}, f)
        
    os.execl(sys.executable, sys.executable, *sys.argv)

def _log_audit(kind, payload):
    try:
        entry = {"ts": datetime.now().isoformat(), "kind": kind}
        entry.update(payload or {})
        with open("session_usage.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except:
        pass

def read_manager_control():
    try:
        with open("manager_control.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def write_manager_control(data):
    try:
        with open("manager_control.json", "w", encoding="utf-8") as f:
            json.dump(data, f)
        return True
    except:
        return False

async def execute_force_regenerate_manager_session(trigger_event=None):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_path = "bot_session.session"
    backup_path = f"{session_path}.bak-{ts}"
    try:
        backup_path = backup_and_remove_session(session_path, backup_path)
        _log_audit("manager_force_regen", {"by": ADMIN_ID, "backup": backup_path or "None"})
        if trigger_event:
            try:
                await trigger_event.answer("🔄 Memulai restart untuk regen session...", alert=True)
            except:
                pass
        await execute_restart_sequence(trigger_event)
    except Exception as e:
        if trigger_event:
            try:
                await trigger_event.answer(f"❌ Gagal: {e}", alert=True)
            except:
                pass
        _log_audit("manager_force_regen_error", {"error": str(e)})

def backup_and_remove_session(session_path, backup_path):
    try:
        if os.path.exists(session_path):
            try:
                os.rename(session_path, backup_path)
            except:
                backup_path = None
            try:
                os.remove(session_path)
            except:
                pass
            if os.path.exists(session_path):
                try:
                    import shutil
                    if backup_path:
                        shutil.copyfile(session_path, backup_path)
                    os.remove(session_path)
                except:
                    pass
        return backup_path
    except:
        return None

# --- Restart Trigger ---
@bot.on(events.CallbackQuery(pattern=b"cmd_admin_restart"))
async def cb_restart(event):
    if event.sender_id != ADMIN_ID: return
    await execute_restart_sequence(trigger_event=event)

# --- Auto Update Watcher ---
async def auto_update_watcher():
    """
    Background task untuk monitoring file trigger restart dan status maintenance.
    Task ini akan di-cancel dengan benar saat shutdown.
    """
    TRIGGER_PATH = "/home/bmcodex/userbot/restart_trigger.txt"
    try:
        while True:
            try:
                if os.path.exists(TRIGGER_PATH):
                    try: os.remove(TRIGGER_PATH) 
                    except: pass
                    await execute_restart_sequence(trigger_event=None)
                
                mc = read_manager_control()
                if mc.get("system_status") == "maintenance":
                    start = mc.get("restart_started_at") or mc.get("shutdown_started_at")
                    last_n = mc.get("last_maintenance_notify")
                    if start:
                        try:
                            elapsed = (datetime.now() - datetime.fromisoformat(start)).total_seconds()
                        except:
                            elapsed = 0
                        if elapsed > 300:
                            if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 300:
                                members = get_all_members_safe()
                                now_str = datetime.now().strftime("%d-%m-%Y %H:%M WIB")
                                for row in members:
                                    try:
                                        uid = str(row.get("User ID"))
                                        if uid.isdigit() and int(uid) != ADMIN_ID:
                                            await bot.send_message(int(uid), f"ℹ️ Pembaruan masih berlangsung sejak {now_str}. Mohon tunggu, proses memakan waktu lebih lama dari perkiraan.")
                                    except:
                                        pass
                                mc["last_maintenance_notify"] = datetime.now().isoformat()
                                write_manager_control(mc)
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                # Cleanup saat task di-cancel
                print("[System] Auto update watcher cancelled (graceful shutdown)")
                raise
            except Exception as e:
                print(f"[System] Watcher error: {e}")
                await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass  # Task is being cancelled, exit gracefully
    finally:
        print("[System] Auto update watcher stopped")

# Initialize auto_update_watcher task dengan proper management
def init_auto_update_watcher():
    global AUTO_UPDATE_TASK
    try:
        AUTO_UPDATE_TASK = bot.loop.create_task(auto_update_watcher())
        print("✅ Auto update watcher started")
    except Exception as e:
        print(f"❌ Watcher Error: {e}")

# Add cleanup handler saat bot disconnect
@bot.on(events.Raw)
async def on_bot_disconnect(update):
    # Cleanup when bot is about to disconnect
    if AUTO_UPDATE_TASK and not AUTO_UPDATE_TASK.done():
        AUTO_UPDATE_TASK.cancel()
        try:
            await AUTO_UPDATE_TASK
        except asyncio.CancelledError:
            pass

# Call init saat module di-import
# NOTE: Do NOT initialize here - event loop not ready yet!
# Will be initialized in main.py after bot.start()

# --- Shutdown ---
@bot.on(events.CallbackQuery(pattern=b"cmd_admin_shutdown"))
async def cb_shutdown_confirm(event):
    if event.sender_id != ADMIN_ID: return
    await event.edit("⚠️ **SHUTDOWN?**\nBot akan mati total.", 
                     buttons=[[Button.inline("🔴 MATIKAN", b"confirm_shutdown")], [Button.inline("🔙 Batal", b"menu_admin_dashboard")]])

@bot.on(events.CallbackQuery(pattern=b"confirm_shutdown"))
async def cb_shutdown_execute(event):
    global AUTO_UPDATE_TASK
    if event.sender_id != ADMIN_ID: return
    
    # Cancel auto_update_watcher task
    if AUTO_UPDATE_TASK and not AUTO_UPDATE_TASK.done():
        AUTO_UPDATE_TASK.cancel()
        try:
            await AUTO_UPDATE_TASK
        except asyncio.CancelledError:
            pass
    
    await event.edit("🔴 Bot Offline.")
    now_str = datetime.now().strftime("%d-%m-%Y %H:%M WIB")
    mc = read_manager_control()
    mc["system_status"] = "maintenance"
    mc["shutdown_started_at"] = datetime.now().isoformat()
    write_manager_control(mc)
    _log_audit("shutdown_start", {"at": mc["shutdown_started_at"]})
    
    members = get_all_members_safe()
    for row in members:
        try:
            uid = str(row.get("User ID"))
            if uid.isdigit() and int(uid) != ADMIN_ID:
                await bot.send_message(int(uid), f"🔴 **PENGUMUMAN SISTEM**\nSistem sedang melakukan pembaruan pada {now_str}. Mohon tunggu beberapa saat hingga bot kembali normal.")
        except:
            pass
    
    for uid, client in list(ACTIVE_USERBOTS.items()):
        try: await client.disconnect()
        except: pass
    try: await bot.disconnect()
    except: pass
    return
