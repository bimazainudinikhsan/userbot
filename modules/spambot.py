# bmcodexbot/modules/spambot.py
import asyncio
import random
from datetime import datetime
from telethon import events, Button
from telethon.errors import FloodWaitError, MessageNotModifiedError, ReplyMarkupInvalidError
from config import bot, ADMIN_ID

ACTIVE_STD_TASKS = {}
SPAM_PROGRESS = {}

# Kata sensitif dan berisiko (penanganan konten)
SARA_WORDS = [
    "anjing", "babi", "bangsat", "kontol", "memek", "ngentot", "tai", "goblok",
    "tolol", "bodoh", "idiot", "kampret", "bajingan", "keparat", "setan", "iblis",
    "kafir", "yahudi", "nasrani", "agama", "suku", "ras", "cina", "jawa", "arab",
    "negro", "nigga", "fuck", "shit", "bitch", "asshole", "dick", "pussy",
    "jancok", "asu", "cuk", "jembut", "perek", "lonte", "pelacur", "sundal"
]
RISKY_WORDS = ["jual", "beli", "promo", "diskon", "slot", "gacor", "link", "http", "wa.me", "t.me"]

def contains_sensitive(text):
    t = (text or "").lower()
    return any(w in t for w in SARA_WORDS) or any(w in t for w in RISKY_WORDS)

def write_spam_log(kind, payload):
    try:
        entry = {"ts": datetime.now().isoformat(), "kind": kind}
        entry.update(payload or {})
        with open("spam_activity.log", "a", encoding="utf-8") as f:
            f.write(__import__("json").dumps(entry) + "\n")
    except:
        pass

async def send_progress_to_admin(user_id, target, current, total, status="running"):
    """Kirim progress ke admin dengan tombol stop"""
    progress_pct = int((current / total) * 100) if total > 0 else 0
    progress_bar = "▓" * (progress_pct // 10) + "░" * (10 - progress_pct // 10)
    
    text = (
        f"🤖 **SPAM BOT PROGRESS**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: `{user_id}`\n"
        f"🎯 Target: `{target}`\n"
        f"📊 Progress: [{progress_bar}] {progress_pct}%\n"
        f"📨 Terkirim: {current}/{total}\n"
        f"⏱ Status: {status}"
    )
    
    buttons = []
    if "Berjalan" in status or status == "running" or "Scraping" in status:
        buttons.append([Button.inline("🛑 STOP SPAM", f"STOP_SPAM_STD:{user_id}")])
    markup = buttons if buttons else None
    
    try:
        if user_id in SPAM_PROGRESS and SPAM_PROGRESS[user_id].get("msg_id"):
            try:
                await bot.edit_message(user_id, SPAM_PROGRESS[user_id]["msg_id"], text, buttons=markup)
            except MessageNotModifiedError:
                pass
            except ReplyMarkupInvalidError:
                try:
                    await bot.edit_message(user_id, SPAM_PROGRESS[user_id]["msg_id"], text, buttons=None)
                except Exception as e:
                    print(f"Edit fallback failed: {e}")
        else:
            msg = await bot.send_message(user_id, text, buttons=markup)
            SPAM_PROGRESS[user_id] = {"msg_id": msg.id}
    except Exception as e:
        print(f"Error sending progress: {e}")
    write_spam_log("std_progress", {"user_id": user_id, "target": str(target), "current": current, "total": total, "status": status})

async def run_spam_std(client, user_id, target, count, msg):
    """Jalankan spam standar dengan progress reporting"""
    target_name = str(target)
    print(f"[SPAM STD] user={user_id} target={target} count={count}")
    try:
        entity = await client.get_entity(target)
        target_name = getattr(entity, 'title', getattr(entity, 'first_name', str(target)))
        
        for i in range(count):
            if user_id not in ACTIVE_STD_TASKS:
                return
                
            if not client.is_connected():
                await asyncio.sleep(5)
                continue
            
            try:
                if contains_sensitive(msg):
                    write_spam_log("std_skip_sensitive", {"user_id": user_id, "target": str(target), "msg": msg})
                else:
                    async with client.action(entity, 'typing'):
                        await asyncio.sleep(min(len(msg) * 0.02, 1.0))
                        await client.send_message(entity, msg)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + random.uniform(0.5, 1.5))
                continue
            
            if i % 1 == 0 or i == count - 1:
                await send_progress_to_admin(user_id, target_name, i + 1, count, "🔄 Berjalan...")
            
            # Default rate limiting: ~1 pesan/detik (dengan jitter kecil)
            if hasattr(entity, 'megagroup') and entity.megagroup:
                await asyncio.sleep(1.2 + random.uniform(0.05, 0.25))
            else:
                await asyncio.sleep(1.0 + random.uniform(0.05, 0.25))
            
        await send_progress_to_admin(user_id, target_name, count, count, "✅ Selesai")
        # Finalize: delete progress msg and notify
        try:
            mp = SPAM_PROGRESS.get(user_id, {})
            mid = mp.get("msg_id")
            if mid:
                try:
                    await bot.delete_messages(user_id, mid)
                except Exception:
                    pass
                del SPAM_PROGRESS[user_id]
            await bot.send_message(user_id, "✅ Proses spam selesai", buttons=[[Button.inline("⬅️ Kembali ke Menu Member", b"menu_start")]])
        except Exception as e:
            print(f"Finalize error: {e}")
        
    except asyncio.CancelledError:
        return
    except Exception as e:
        print(f"Error Spam Std: {e}")
        await send_progress_to_admin(user_id, target_name, 0, count, f"❌ Error: {str(e)[:30]}")
        write_spam_log("std_error", {"user_id": user_id, "target": str(target), "error": str(e)})

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spambot"] = {
        "title": "Spam Biasa 🤖",
        "usage": ".spambot <target> <jumlah> [kata]\nDefault delay ~1 msg/detik. Gunakan bertanggung jawab."
    }

    @client.on(events.NewMessage(pattern=r"(?i)^\.spambot (\S+) (\d+)(?:\s+(.+))?"))
    async def spam_std_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spambot"): 
            return await event.edit("🔒 Fitur SpamBot dikunci Admin.")
        if not await check_status(client, user_id, event):
            return
        
        target = event.pattern_match.group(1)
        count = int(event.pattern_match.group(2))
        msg = event.pattern_match.group(3) or "Halo"
        
        if count < 1:
            return await event.edit("⚠️ Jumlah minimal 1.")
        if count > 100:
            return await event.edit("⚠️ Maksimal 100 pesan per sesi.")
        
        if user_id in ACTIVE_STD_TASKS and not ACTIVE_STD_TASKS[user_id].done():
            return await event.edit("⚠️ Task spam sedang berjalan. Tunggu atau stop dulu.")

        await event.delete()
        
        write_spam_log("std_start", {"user_id": user_id, "target": str(target), "count": count, "msg_len": len(msg)})
        task = asyncio.create_task(run_spam_std(client, user_id, target, count, msg))
        ACTIVE_STD_TASKS[user_id] = task
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            if user_id in ACTIVE_STD_TASKS: 
                del ACTIVE_STD_TASKS[user_id]

@bot.on(events.CallbackQuery(pattern=r"STOP_SPAM_STD:(.+)"))
async def stop_spam_std(event):
    # Izinkan Admin atau member pemilik task
    target_user = int(event.data.decode().split(":")[1])
    if event.sender_id not in (ADMIN_ID, target_user):
        return
    
    if target_user in ACTIVE_STD_TASKS:
        ACTIVE_STD_TASKS[target_user].cancel()
        del ACTIVE_STD_TASKS[target_user]
        
        if target_user in SPAM_PROGRESS and SPAM_PROGRESS[target_user].get("msg_id"):
            try:
                text = (
                    f"🤖 **SPAM BOT PROGRESS**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 User: `{target_user}`\n"
                    f"⏱ Status: ❌ Dihentikan oleh Admin"
                )
                try:
                    await bot.edit_message(target_user, SPAM_PROGRESS[target_user]["msg_id"], text, buttons=None)
                except MessageNotModifiedError:
                    pass
                except ReplyMarkupInvalidError:
                    try:
                        await bot.edit_message(target_user, SPAM_PROGRESS[target_user]["msg_id"], text)
                    except Exception:
                        pass
            except:
                pass
            try:
                await bot.delete_messages(target_user, SPAM_PROGRESS[target_user]["msg_id"])
            except Exception:
                pass
            del SPAM_PROGRESS[target_user]
        
        await event.answer("✅ Spam dihentikan!", alert=True)
        try:
            await bot.send_message(target_user, "🛑 Proses spam dihentikan", buttons=[[Button.inline("⬅️ Kembali ke Menu Member", b"menu_start")]])
        except Exception:
            pass
        write_spam_log("std_stop", {"user_id": target_user})
    else:
        await event.answer("⚠️ Task sudah selesai.", alert=True)
