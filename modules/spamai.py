# bmcodexbot/modules/spamai.py
import asyncio
import random
import re
import time
import json
import os
from collections import deque
from telethon import events, Button
from telethon.errors import FloodWaitError, MessageNotModifiedError, ReplyMarkupInvalidError
from config import bot, ADMIN_ID

ACTIVE_AI_TASKS = {}
SPAM_AI_PROGRESS = {}
WORD_CACHE = {}
AI_TASK_STATE = {}

STATE_FILE = "spam_active_sessions.json"

def load_global_state():
    try:
        if not os.path.exists(STATE_FILE):
            return {}
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_global_state(data):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except:
        pass

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

def compute_eta(user_id, current, total):
    st = AI_TASK_STATE.get(user_id, {})
    avg_delay = ((st.get("min_d", 1.0) + st.get("max_d", 1.0)) / 2.0) if st else 1.0
    remaining = max(0, total - current)
    eta_sec = int(remaining * avg_delay)
    return eta_sec

async def send_progress_to_admin(user_id, target, current, total, status="running", sentences_ready=0):
    """Kirim progress ke admin dengan tombol stop"""
    progress_pct = int((current / total) * 100) if total > 0 else 0
    progress_bar = "▓" * (progress_pct // 10) + "░" * (10 - progress_pct // 10)
    
    eta = compute_eta(user_id, current, total)
    paused = bool(AI_TASK_STATE.get(user_id, {}).get("paused"))
    text = (
        f"🧠 **SPAM AI PROGRESS**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: `{user_id}`\n"
        f"🎯 Target: `{target}`\n"
        f"📝 Kalimat siap: {sentences_ready}\n"
        f"� Terkirim: {current}/{total} • {progress_pct}%\n"
        f"⏱ Status: {'⏸ Paused' if paused else status}\n"
        f"🕒 ETA: ~{eta}s"
    )
    
    buttons = []
    if "Berjalan" in status or status == "running" or "Scraping" in status or "Refresh" in status or paused:
        row = []
        if paused:
            row.append(Button.inline("▶️ Resume", f"RESUME_SPAM_AI:{user_id}"))
        else:
            row.append(Button.inline("⏸ Pause", f"PAUSE_SPAM_AI:{user_id}"))
        row.append(Button.inline("🛑 Batalkan", f"STOP_SPAM_AI:{user_id}"))
        row.append(Button.inline("🔄 Refresh", f"REFRESH_SPAM_AI:{user_id}"))
        buttons.append(row)
    
    markup = buttons if buttons else None
    try:
        if user_id in SPAM_AI_PROGRESS and SPAM_AI_PROGRESS[user_id].get("msg_id"):
            try:
                await bot.edit_message(user_id, SPAM_AI_PROGRESS[user_id]["msg_id"], text, buttons=markup)
            except MessageNotModifiedError:
                pass
            except ReplyMarkupInvalidError:
                try:
                    await bot.edit_message(user_id, SPAM_AI_PROGRESS[user_id]["msg_id"], text, buttons=None)
                except Exception as e:
                    print(f"Edit fallback failed: {e}")
        else:
            msg = await bot.send_message(user_id, text, buttons=markup)
            SPAM_AI_PROGRESS[user_id] = {"msg_id": msg.id}
    except Exception as e:
        print(f"Error sending progress: {e}")
    try:
        with open("spam_activity.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": __import__("datetime").datetime.now().isoformat(), "kind": "ai_progress", "user_id": user_id, "target": str(target), "current": current, "total": total, "status": status, "sentences_ready": sentences_ready, "paused": paused, "eta_sec": eta}) + "\n")
    except:
        pass

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

async def run_spam_ai(client, user_id, target, min_d, max_d, count, seed_msg=None):
    """Jalankan spam AI dengan scraping dan reply"""
    target_name = str(target)
    print(f"[SPAM AI] user={user_id} target={target} count={count} delay={min_d}-{max_d} seed={bool(seed_msg)}")
    sentences = []
    try:
        entity = await client.get_entity(target)
        target_name = getattr(entity, 'title', getattr(entity, 'first_name', str(target)))
        AI_TASK_STATE[user_id] = {"paused": False, "current": 0, "total": count, "min_d": float(min_d), "max_d": float(max_d), "target": target_name, "started": time.time()}
        gs = load_global_state()
        gs.setdefault("ai", {})[str(user_id)] = {"target": target_name, "current": 0, "total": count, "min": float(min_d), "max": float(max_d), "seed": bool(seed_msg)}
        save_global_state(gs)

        await send_progress_to_admin(user_id, target_name, 0, count, "🔄 Scraping kata...", 0)
        
        words = await scrape_words(client, entity, 255)
        
        sentences = generate_sentences(words, 50)
        if seed_msg:
            base = seed_msg.strip()
            if base:
                for _ in range(10):
                    extra = ""
                    if words:
                        extra = " " + " ".join(random.sample(words, k=min(2, len(words))))
                    sentences.append((base + extra).strip())
        
        await send_progress_to_admin(user_id, target_name, 0, count, "🔄 Berjalan...", len(sentences))
        
        last_refresh = time.time()
        sentence_idx = 0
        
        for i in range(count):
            if user_id not in ACTIVE_AI_TASKS:
                return
                
            if not client.is_connected():
                await asyncio.sleep(5)
                continue
            # Pause handling
            while AI_TASK_STATE.get(user_id, {}).get("paused"):
                await send_progress_to_admin(user_id, target_name, i, count, "⏸ Paused", len(sentences))
                await asyncio.sleep(2)
            
            if time.time() - last_refresh > 600:
                words = await scrape_words(client, entity, 255)
                sentences = generate_sentences(words, 50)
                if seed_msg:
                    base = seed_msg.strip()
                    if base:
                        for _ in range(10):
                            extra = ""
                            if words:
                                extra = " " + " ".join(random.sample(words, k=min(2, len(words))))
                            sentences.append((base + extra).strip())
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
            
            AI_TASK_STATE[user_id]["current"] = i + 1
            gs = load_global_state()
            if gs.get("ai") and gs["ai"].get(str(user_id)):
                gs["ai"][str(user_id)]["current"] = i + 1
                save_global_state(gs)

            if i % 2 == 0 or i == count - 1:
                await send_progress_to_admin(user_id, target_name, i + 1, count, "🔄 Berjalan...", len(sentences))
            
            delay = random.uniform(min_d, max_d)
            await asyncio.sleep(delay)
            
        await send_progress_to_admin(user_id, target_name, count, count, "✅ Selesai", len(sentences))
        # Finalize: delete progress msg and notify
        try:
            mp = SPAM_AI_PROGRESS.get(user_id, {})
            mid = mp.get("msg_id")
            if mid:
                try:
                    await bot.delete_messages(user_id, mid)
                except Exception:
                    pass
                del SPAM_AI_PROGRESS[user_id]
            await bot.send_message(user_id, "✅ Proses spam selesai", buttons=[[Button.inline("⬅️ Kembali ke Menu Member", b"menu_start")]])
        except Exception as e:
            print(f"Finalize error: {e}")
        
    except asyncio.CancelledError:
        return
    except Exception as e:
        print(f"Error Spam AI: {e}")
        await send_progress_to_admin(user_id, target_name, 0, count, f"❌ Error: {str(e)[:30]}", len(sentences))
        try:
            with open("spam_activity.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": __import__("datetime").datetime.now().isoformat(), "kind": "ai_error", "user_id": user_id, "target": str(target), "error": str(e)}) + "\n")
        except:
            pass

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spamai"] = {
        "title": "Spam AI (Smart) 🧠",
        "usage": ".spamai <target> <delay min-max> <jumlah> <msg>\nSpam pintar dengan scraping kata dari grup.\nReply pesan orang lain otomatis.\nContoh: .spamai @grupku 5-10 50 Halo semua"
    }

    @client.on(events.NewMessage(pattern=r"(?i)^\.spamai (\S+) (\d+-\d+) (\d+)(?:\s+(.+))?"))
    async def spam_ai_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spamai"): 
            return await event.edit("🔒 Fitur SpamAI dikunci.")
        if not await check_status(client, user_id, event):
            return
        
        target = event.pattern_match.group(1)
        delay_rng = event.pattern_match.group(2)
        count = int(event.pattern_match.group(3))
        seed_msg = event.pattern_match.group(4) or ""
        
        try: 
            mn, mx = map(float, delay_rng.split('-'))
        except: 
            return await event.edit("⚠️ Format delay: min-max (contoh: 5-10)")
        if mn <= 0 or mx <= 0:
            return await event.edit("⚠️ Delay harus > 0 detik")
        if mn > mx:
            mn, mx = mx, mn
        
        if count < 1:
            return await event.edit("⚠️ Jumlah minimal 1.")
        if count > 100:
            return await event.edit("⚠️ Maksimal 100 pesan per sesi.")

        if user_id in ACTIVE_AI_TASKS and not ACTIVE_AI_TASKS[user_id].done():
            return await event.edit("⚠️ Task AI sedang jalan.")
        
        await event.reply(f"✅ Task AI dimulai: target=`{target}` jumlah={count} delay={mn}-{mx}s")
        await event.delete()
        
        task = asyncio.create_task(run_spam_ai(client, user_id, target, mn, mx, count, seed_msg))
        ACTIVE_AI_TASKS[user_id] = task
        
        try: 
            await task
        except asyncio.CancelledError: 
            pass
        finally:
            if user_id in ACTIVE_AI_TASKS: 
                del ACTIVE_AI_TASKS[user_id]
            if user_id in AI_TASK_STATE:
                del AI_TASK_STATE[user_id]

@bot.on(events.CallbackQuery(pattern=r"STOP_SPAM_AI:(.+)"))
async def stop_spam_ai(event):
    
    target_user = int(event.data.decode().split(":")[1])
    if event.sender_id not in (ADMIN_ID, target_user):
        return
    
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
                try:
                    await bot.edit_message(target_user, SPAM_AI_PROGRESS[target_user]["msg_id"], text, buttons=None)
                except MessageNotModifiedError:
                    pass
                except ReplyMarkupInvalidError:
                    try:
                        await bot.edit_message(target_user, SPAM_AI_PROGRESS[target_user]["msg_id"], text)
                    except Exception:
                        pass
            except:
                pass
            try:
                await bot.delete_messages(target_user, SPAM_AI_PROGRESS[target_user]["msg_id"])
            except Exception:
                pass
            del SPAM_AI_PROGRESS[target_user]
        
        await event.answer("✅ Spam AI dihentikan!", alert=True)
        try:
            await bot.send_message(target_user, "🛑 Proses spam AI dihentikan", buttons=[[Button.inline("⬅️ Kembali ke Menu Member", b"menu_start")]])
        except Exception:
            pass
    else:
        await event.answer("⚠️ Task sudah selesai.", alert=True)

@bot.on(events.CallbackQuery(pattern=r"PAUSE_SPAM_AI:(.+)"))
async def pause_spam_ai(event):
    target_user = int(event.data.decode().split(":")[1])
    if event.sender_id not in (ADMIN_ID, target_user):
        return
    if target_user in AI_TASK_STATE:
        AI_TASK_STATE[target_user]["paused"] = True
        await event.answer("⏸ Dijeda", alert=True)
        st = AI_TASK_STATE[target_user]
        await send_progress_to_admin(target_user, st.get("target", "-"), st.get("current", 0), st.get("total", 0), "⏸ Paused", 0)

@bot.on(events.CallbackQuery(pattern=r"RESUME_SPAM_AI:(.+)"))
async def resume_spam_ai(event):
    target_user = int(event.data.decode().split(":")[1])
    if event.sender_id not in (ADMIN_ID, target_user):
        return
    if target_user in AI_TASK_STATE:
        AI_TASK_STATE[target_user]["paused"] = False
        await event.answer("▶️ Dilanjutkan", alert=True)
        st = AI_TASK_STATE[target_user]
        await send_progress_to_admin(target_user, st.get("target", "-"), st.get("current", 0), st.get("total", 0), "🔄 Berjalan...", 0)

@bot.on(events.CallbackQuery(pattern=r"REFRESH_SPAM_AI:(.+)"))
async def refresh_spam_ai(event):
    target_user = int(event.data.decode().split(":")[1])
    st = AI_TASK_STATE.get(target_user, {})
    await send_progress_to_admin(target_user, st.get("target", "-"), st.get("current", 0), st.get("total", 0), "🔄 Refresh", 0)
