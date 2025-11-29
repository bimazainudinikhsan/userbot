# bmcodexbot/modules/spamai.py
import asyncio
import random
import re
from collections import deque
from telethon import events
from telethon.errors import FloodWaitError
from config import bot

ACTIVE_AI_TASKS = {}

# Filter Kata & Prefix
RISKY_WORDS = ["jual", "beli", "promo", "diskon", "slot", "gacor", "link", "http"]
AI_PREFIXES = ["Halo kak", "Misi min", "Info dong", "Punten", "Salam kenal"]

async def run_spam_ai(client, target, min_d, max_d, count, manual_word):
    try:
        entity = await client.get_entity(target)
        
        # 1. Fase Scraping (Belajar dari grup)
        scraped_words = []
        async for message in client.iter_messages(entity, limit=50):
            if message.text and not message.sender.bot:
                # Bersihkan pesan
                clean = re.sub(r'http\S+', '', message.text)
                if not any(bad in clean.lower() for bad in RISKY_WORDS):
                    scraped_words.append(clean)
        
        # 2. Fase Eksekusi
        for i in range(count):
            if not client.is_connected(): await asyncio.sleep(5)
            
            # Buat kalimat campuran (Manual + Scraped)
            context = random.choice(scraped_words) if scraped_words else ""
            final_msg = f"{manual_word} {context}"[:100] # Potong biar gak kepanjangan
            
            delay = random.uniform(min_d, max_d)
            
            # Efek Ngetik (Biar Natural)
            async with client.action(entity, 'typing'):
                await asyncio.sleep(min(len(final_msg)*0.1, 3.0))
                await client.send_message(entity, final_msg)
            
            await asyncio.sleep(delay)
            
    except Exception as e:
        print(f"Error Spam AI: {e}")

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spamai"] = {
        "title": "Spam AI (Smart) 🧠",
        "usage": ".spamai <target> <min-max> <jml> <kata>\nSpam pintar dengan scraping."
    }

    @client.on(events.NewMessage(pattern=r"(?i)^\.spamai (\S+) (\d+-\d+) (\d+) (.+)"))
    async def spam_ai_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spam"): return await event.edit("🔒 Fitur dikunci.")
        
        target = event.pattern_match.group(1)
        delay_rng = event.pattern_match.group(2)
        count = int(event.pattern_match.group(3))
        word = event.pattern_match.group(4)
        
        try: mn, mx = map(float, delay_rng.split('-'))
        except: return await event.edit("⚠️ Format delay: min-max (cth: 2-5)")

        if user_id in ACTIVE_AI_TASKS: return await event.edit("⚠️ Task AI sedang jalan.")
        
        await event.delete()
        
        task = asyncio.create_task(run_spam_ai(client, target, mn, mx, count, word))
        ACTIVE_AI_TASKS[user_id] = task
        
        try: await task
        except: pass
        finally:
            if user_id in ACTIVE_AI_TASKS: del ACTIVE_AI_TASKS[user_id]