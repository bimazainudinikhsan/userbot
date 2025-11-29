# bmcodexbot/modules/spambot.py
import asyncio
from datetime import datetime
from telethon import events, Button
from config import bot, ADMIN_ID

ACTIVE_STD_TASKS = {}
SPAM_PROGRESS = {}

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
    
    try:
        if user_id in SPAM_PROGRESS and SPAM_PROGRESS[user_id].get("msg_id"):
            await bot.edit_message(ADMIN_ID, SPAM_PROGRESS[user_id]["msg_id"], text, buttons=buttons)
        else:
            msg = await bot.send_message(ADMIN_ID, text, buttons=buttons)
            SPAM_PROGRESS[user_id] = {"msg_id": msg.id}
    except Exception as e:
        print(f"Error sending progress: {e}")

async def run_spam_std(client, user_id, target, count, msg):
    """Jalankan spam standar dengan progress reporting"""
    target_name = str(target)
    try:
        entity = await client.get_entity(target)
        target_name = getattr(entity, 'title', getattr(entity, 'first_name', str(target)))
        
        for i in range(count):
            if user_id not in ACTIVE_STD_TASKS:
                return
                
            if not client.is_connected():
                await asyncio.sleep(5)
                continue
            
            await client.send_message(entity, msg)
            
            if i % 5 == 0 or i == count - 1:
                await send_progress_to_admin(user_id, target_name, i + 1, count, "🔄 Berjalan...")
            
            await asyncio.sleep(2.0)
            
        await send_progress_to_admin(user_id, target_name, count, count, "✅ Selesai")
        
    except asyncio.CancelledError:
        return
    except Exception as e:
        print(f"Error Spam Std: {e}")
        await send_progress_to_admin(user_id, target_name, 0, count, f"❌ Error: {str(e)[:30]}")

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spambot"] = {
        "title": "Spam Biasa 🤖",
        "usage": ".spambot <target> <jumlah> <pesan>\nSpam pesan ke target."
    }

    @client.on(events.NewMessage(pattern=r"(?i)^\.spambot (\S+) (\d+) (.+)"))
    async def spam_std_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spambot"): 
            return await event.edit("🔒 Fitur SpamBot dikunci Admin.")
        
        target = event.pattern_match.group(1)
        count = int(event.pattern_match.group(2))
        msg = event.pattern_match.group(3)
        
        if count > 100:
            return await event.edit("⚠️ Maksimal 100 pesan per sesi.")
        
        if user_id in ACTIVE_STD_TASKS and not ACTIVE_STD_TASKS[user_id].done():
            return await event.edit("⚠️ Task spam sedang berjalan. Tunggu atau stop dulu.")

        await event.delete()
        
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
    if event.sender_id != ADMIN_ID: return
    
    target_user = int(event.data.decode().split(":")[1])
    
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
                await bot.edit_message(ADMIN_ID, SPAM_PROGRESS[target_user]["msg_id"], text, buttons=None)
            except:
                pass
            del SPAM_PROGRESS[target_user]
        
        await event.answer("✅ Spam dihentikan!", alert=True)
    else:
        await event.answer("⚠️ Task sudah selesai.", alert=True)
