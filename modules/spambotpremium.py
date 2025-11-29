# bmcodexbot/modules/spambotpremium.py
import asyncio
import random
from telethon import events
from config import bot

ACTIVE_PREM_TASKS = {}

# Kata-kata variasi untuk Premium
AI_PREFIXES = [
    "Cek profil ya kak", "Yang mau rate sini yuk", "Bantu saya kak", 
    "Salam kenal semuanya", "Ada yang gabut gak", "Info dong kak", 
    "Permisi numpang lewat", "Misi gan", "Punteun"
]

async def run_spam_prem(client, target, count, base_msg):
    try:
        entity = await client.get_entity(target)
        for i in range(count):
            if not client.is_connected(): await asyncio.sleep(5)
            
            # Fitur Premium: Tambah variasi kata di depan
            prefix = random.choice(AI_PREFIXES)
            final_msg = f"{prefix} {base_msg}"
            
            await client.send_message(entity, final_msg)
            await asyncio.sleep(1.0) # Delay lebih cepat (Premium)
            
    except Exception as e:
        print(f"Error Spam Prem: {e}")

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spambotpremium"] = {
        "title": "Spam Premium 💎",
        "usage": ".spambotpremium <target> <jumlah>\nSpam cepat dengan variasi."
    }

    @client.on(events.NewMessage(pattern=r"(?i)^\.spambotpremium (\S+) (\d+)"))
    async def spam_prem_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spam"): return await event.edit("🔒 Fitur Premium dikunci.")
        
        target = event.pattern_match.group(1)
        count = int(event.pattern_match.group(2))
        msg = "Info Premium cek bio" # Contoh pesan
        
        if user_id in ACTIVE_PREM_TASKS and not ACTIVE_PREM_TASKS[user_id].done():
            return await event.edit("⚠️ Task Premium sedang berjalan.")

        await event.delete()
        
        task = asyncio.create_task(run_spam_prem(client, target, count, msg))
        ACTIVE_PREM_TASKS[user_id] = task
        
        try: await task
        except: pass
        finally: 
            if user_id in ACTIVE_PREM_TASKS: del ACTIVE_PREM_TASKS[user_id]