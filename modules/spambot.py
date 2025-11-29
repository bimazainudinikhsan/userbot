# bmcodexbot/modules/spambot.py
import asyncio
from telethon import events
from config import bot

# State untuk menyimpan task aktif
ACTIVE_STD_TASKS = {}

async def run_spam_std(client, target, count, msg):
    try:
        entity = await client.get_entity(target)
        for i in range(count):
            if not client.is_connected():
                await asyncio.sleep(5)
                continue
            
            # Kirim pesan
            await client.send_message(entity, msg)
            await asyncio.sleep(2.0) # Delay aman untuk spam biasa
            
    except Exception as e:
        print(f"Error Spam Std: {e}")

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spambot"] = {
        "title": "Spam Biasa 🤖",
        "usage": ".spambot <target> <jumlah>\nSpam pesan standar."
    }

    @client.on(events.NewMessage(pattern=r"(?i)^\.spambot (\S+) (\d+)"))
    async def spam_std_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spam"): return await event.edit("🔒 Fitur dikunci Admin.")
        
        target = event.pattern_match.group(1)
        count = int(event.pattern_match.group(2))
        
        # Pesan default atau bisa diambil dari config
        msg = "Pesan Spam Standar"
        
        if user_id in ACTIVE_STD_TASKS and not ACTIVE_STD_TASKS[user_id].done():
            return await event.edit("⚠️ Task lain sedang berjalan.")

        await event.delete()
        
        # Jalankan Task
        task = asyncio.create_task(run_spam_std(client, target, count, msg))
        ACTIVE_STD_TASKS[user_id] = task
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            if user_id in ACTIVE_STD_TASKS: del ACTIVE_STD_TASKS[user_id]