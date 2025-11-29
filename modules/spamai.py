# bmcodexbot/modules/spamai.py
import asyncio
import random
import re
import time
from collections import deque
from telethon import events, Button
from telethon.errors import FloodWaitError
from config import bot, ADMIN_ID

ACTIVE_AI_TASKS = {}
SPAM_AI_PROGRESS = {}
WORD_CACHE = {}

SARA_WORDS = [
    "anjing", "babi", "bangsat", "kontol", "memek", "ngentot", "tai", "goblok",
    "tolol", "bodoh", "idiot", "kampret", "bajingan", "keparat", "setan", "iblis",
    "kafir", "yahudi", "nasrani", "agama", "suku", "ras", "cina", "jawa", "arab",
    "negro", "nigga", "fuck", "shit", "bitch", "asshole", "dick", "pussy",
    "jancok", "asu", "cuk", "jembut", "perek", "lonte", "pelacur", "sundal"
]

RISKY_WORDS = ["jual", "beli", "promo", "diskon", "slot", "gacor", "link", "http", "wa.me", "t.me"]

def filter_words(text):
    """Filter kata-kata SARA dan berisiko"""
    words = text.lower().split()
    filtered = []
    for word in words:
        clean_word = re.sub(r'[^a-zA-Z0-9]', '', word)
        if len(clean_word) < 2:
            continue
        if any(sara in clean_word for sara in SARA_WORDS):
            continue
        if any(risky in clean_word for risky in RISKY_WORDS):
            continue
        filtered.append(word)
    return filtered

def generate_sentences(words, count=50):
    """Generate kalimat 3-5 kata dari word pool"""
    if len(words) < 5:
        return ["Halo semuanya", "Salam kenal ya", "Apa kabar semua"]
    
    sentences = []
    for _ in range(count):
        length = random.randint(3, 5)
        if len(words) >= length:
            selected = random.sample(words, length)
            sentence = " ".join(selected).capitalize()
            sentences.append(sentence)
    
    if not sentences:
        sentences = ["Halo semuanya", "Salam kenal ya"]
    
    return sentences

async def scrape_words(client, entity, limit=255):
    """Scrape kata-kata dari grup"""
    all_words = []
    
    try:
        async for message in client.iter_messages(entity, limit=100):
            if message.text and message.sender:
                if hasattr(message.sender, 'bot') and message.sender.bot:
                    continue
                
                clean = re.sub(r'http\S+', '', message.text)
                clean = re.sub(r'@\w+', '', clean)
                clean = re.sub(r'#\w+', '', clean)
                
                words = filter_words(clean)
                all_words.extend(words)
                
                if len(all_words) >= limit:
                    break
    except Exception as e:
        print(f"Error scraping: {e}")
    
    unique_words = list(set(all_words))[:limit]
    return unique_words

async def send_progress_to_admin(user_id, target, current, total, status="running", sentences_ready=0):
    """Kirim progress ke admin dengan tombol stop"""
    progress_pct = int((current / total) * 100) if total > 0 else 0
    progress_bar = "▓" * (progress_pct // 10) + "░" * (10 - progress_pct // 10)
    
    text = (
        f"🧠 **SPAM AI PROGRESS**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: `{user_id}`\n"
        f"🎯 Target: `{target}`\n"
        f"📝 Kalimat siap: {sentences_ready}\n"
        f"📊 Progress: [{progress_bar}] {progress_pct}%\n"
        f"📨 Terkirim: {current}/{total}\n"
        f"⏱ Status: {status}"
    )
    
    buttons = []
    if "Berjalan" in status or status == "running" or "Scraping" in status or "Refresh" in status:
        buttons.append([Button.inline("🛑 STOP SPAM", f"STOP_SPAM_AI:{user_id}")])
    
    try:
        if user_id in SPAM_AI_PROGRESS and SPAM_AI_PROGRESS[user_id].get("msg_id"):
            await bot.edit_message(ADMIN_ID, SPAM_AI_PROGRESS[user_id]["msg_id"], text, buttons=buttons)
        else:
            msg = await bot.send_message(ADMIN_ID, text, buttons=buttons)
            SPAM_AI_PROGRESS[user_id] = {"msg_id": msg.id}
    except Exception as e:
        print(f"Error sending progress: {e}")

async def get_recent_messages(client, entity, limit=20):
    """Ambil pesan terbaru untuk di-reply"""
    messages = []
    try:
        async for msg in client.iter_messages(entity, limit=limit):
            if msg.text and msg.sender:
                if hasattr(msg.sender, 'bot') and msg.sender.bot:
                    continue
                me = await client.get_me()
                if msg.sender_id != me.id:
                    messages.append(msg)
    except:
        pass
    return messages

async def run_spam_ai(client, user_id, target, min_d, max_d, count):
    """Jalankan spam AI dengan scraping dan reply"""
    target_name = str(target)
    sentences = []
    try:
        entity = await client.get_entity(target)
        target_name = getattr(entity, 'title', getattr(entity, 'first_name', str(target)))
        
        await send_progress_to_admin(user_id, target_name, 0, count, "🔄 Scraping kata...", 0)
        
        words = await scrape_words(client, entity, 255)
        
        sentences = generate_sentences(words, 50)
        
        await send_progress_to_admin(user_id, target_name, 0, count, "🔄 Berjalan...", len(sentences))
        
        last_refresh = time.time()
        sentence_idx = 0
        
        for i in range(count):
            if user_id not in ACTIVE_AI_TASKS:
                return
                
            if not client.is_connected():
                await asyncio.sleep(5)
                continue
            
            if time.time() - last_refresh > 600:
                words = await scrape_words(client, entity, 255)
                sentences = generate_sentences(words, 50)
                last_refresh = time.time()
                await send_progress_to_admin(user_id, target_name, i, count, "🔄 Refresh kata...", len(sentences))
            
            msg_text = sentences[sentence_idx % len(sentences)]
            sentence_idx += 1
            
            recent_msgs = await get_recent_messages(client, entity, 10)
            
            try:
                if recent_msgs:
                    target_msg = random.choice(recent_msgs)
                    async with client.action(entity, 'typing'):
                        await asyncio.sleep(min(len(msg_text) * 0.05, 2.0))
                        await client.send_message(entity, msg_text, reply_to=target_msg.id)
                else:
                    async with client.action(entity, 'typing'):
                        await asyncio.sleep(min(len(msg_text) * 0.05, 2.0))
                        await client.send_message(entity, msg_text)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 5)
                continue
            
            if i % 3 == 0 or i == count - 1:
                await send_progress_to_admin(user_id, target_name, i + 1, count, "🔄 Berjalan...", len(sentences))
            
            delay = random.uniform(min_d, max_d)
            await asyncio.sleep(delay)
            
        await send_progress_to_admin(user_id, target_name, count, count, "✅ Selesai", len(sentences))
        
    except asyncio.CancelledError:
        return
    except Exception as e:
        print(f"Error Spam AI: {e}")
        await send_progress_to_admin(user_id, target_name, 0, count, f"❌ Error: {str(e)[:30]}", len(sentences))

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spamai"] = {
        "title": "Spam AI (Smart) 🧠",
        "usage": ".spamai <target> <delay min-max> <jumlah>\nSpam pintar dengan scraping kata dari grup.\nReply pesan orang lain otomatis.\nContoh: .spamai @grupku 5-10 50"
    }

    @client.on(events.NewMessage(pattern=r"(?i)^\.spamai (\S+) (\d+-\d+) (\d+)"))
    async def spam_ai_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spamai"): 
            return await event.edit("🔒 Fitur SpamAI dikunci.")
        
        target = event.pattern_match.group(1)
        delay_rng = event.pattern_match.group(2)
        count = int(event.pattern_match.group(3))
        
        try: 
            mn, mx = map(float, delay_rng.split('-'))
        except: 
            return await event.edit("⚠️ Format delay: min-max (contoh: 5-10)")
        
        if count > 100:
            return await event.edit("⚠️ Maksimal 100 pesan per sesi.")

        if user_id in ACTIVE_AI_TASKS and not ACTIVE_AI_TASKS[user_id].done():
            return await event.edit("⚠️ Task AI sedang jalan.")
        
        await event.delete()
        
        task = asyncio.create_task(run_spam_ai(client, user_id, target, mn, mx, count))
        ACTIVE_AI_TASKS[user_id] = task
        
        try: 
            await task
        except asyncio.CancelledError: 
            pass
        finally:
            if user_id in ACTIVE_AI_TASKS: 
                del ACTIVE_AI_TASKS[user_id]

@bot.on(events.CallbackQuery(pattern=r"STOP_SPAM_AI:(.+)"))
async def stop_spam_ai(event):
    if event.sender_id != ADMIN_ID: return
    
    target_user = int(event.data.decode().split(":")[1])
    
    if target_user in ACTIVE_AI_TASKS:
        ACTIVE_AI_TASKS[target_user].cancel()
        del ACTIVE_AI_TASKS[target_user]
        
        if target_user in SPAM_AI_PROGRESS and SPAM_AI_PROGRESS[target_user].get("msg_id"):
            try:
                text = (
                    f"🧠 **SPAM AI PROGRESS**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 User: `{target_user}`\n"
                    f"⏱ Status: ❌ Dihentikan oleh Admin"
                )
                await bot.edit_message(ADMIN_ID, SPAM_AI_PROGRESS[target_user]["msg_id"], text, buttons=None)
            except:
                pass
            del SPAM_AI_PROGRESS[target_user]
        
        await event.answer("✅ Spam AI dihentikan!", alert=True)
    else:
        await event.answer("⚠️ Task sudah selesai.", alert=True)
