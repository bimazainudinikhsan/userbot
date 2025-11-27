import asyncio, os, sys, json
from datetime import datetime
from telethon import events, Button
from config import bot, ADMIN_ID
from database import get_all_members_safe
from state import ACTIVE_USERBOTS

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
    now_str = datetime.now().strftime("%H:%M WIB")
    
    # Broadcast Kilat
    for row in members:
        try:
            uid = str(row.get("User ID"))
            if uid.isdigit() and int(uid) != ADMIN_ID:
                await bot.send_message(int(uid), f"⚠️ **SYSTEM RESTART**\nBot sedang restart untuk pembaruan.\n🕒 {now_str}")
        except: pass
    
    if status_msg: await status_msg.edit("🔄 **Rebooting Server...**")

    # Flag untuk pesan sukses setelah nyala kembali
    with open("RESTART_FLAG.json", "w") as f: 
        json.dump({"chat_id": target_chat_id, "admin_id": ADMIN_ID}, f)
        
    os.execl(sys.executable, sys.executable, *sys.argv)

# --- Restart Trigger ---
@bot.on(events.CallbackQuery(pattern=b"cmd_admin_restart"))
async def cb_restart(event):
    if event.sender_id != ADMIN_ID: return
    await execute_restart_sequence(trigger_event=event)

# --- Auto Update Watcher ---
async def auto_update_watcher():
    TRIGGER_PATH = "/home/bmcodex/userbot/restart_trigger.txt"
    while True:
        if os.path.exists(TRIGGER_PATH):
            try: os.remove(TRIGGER_PATH) 
            except: pass
            await execute_restart_sequence(trigger_event=None)
        await asyncio.sleep(5) 

try:
    bot.loop.create_task(auto_update_watcher())
except Exception as e: print(f"❌ Watcher Error: {e}")

# --- Shutdown ---
@bot.on(events.CallbackQuery(pattern=b"cmd_admin_shutdown"))
async def cb_shutdown_confirm(event):
    if event.sender_id != ADMIN_ID: return
    await event.edit("⚠️ **SHUTDOWN?**\nBot akan mati total.", 
                     buttons=[[Button.inline("🔴 MATIKAN", b"confirm_shutdown")], [Button.inline("🔙 Batal", b"menu_admin_dashboard")]])

@bot.on(events.CallbackQuery(pattern=b"confirm_shutdown"))
async def cb_shutdown_execute(event):
    if event.sender_id != ADMIN_ID: return
    await event.edit("🔴 **Bot Offline.**")
    
    for uid, client in list(ACTIVE_USERBOTS.items()):
        try: await client.disconnect()
        except: pass
    try: await bot.disconnect()
    except: pass
    sys.exit(0)