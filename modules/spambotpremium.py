# bmcodexbot/modules/spambotpremium.py
import asyncio
import random
import json
import os
from telethon import events, Button
from config import bot, ADMIN_ID

SETTINGS_FILE = "user_spambotpremium_settings.json"
ACTIVE_PREM_TASKS = {}
SPAM_PREM_PROGRESS = {}
EDIT_STATE = {}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass

def get_user_settings(user_id):
    data = load_settings()
    str_uid = str(user_id)
    if str_uid not in data:
        data[str_uid] = {
            "messages": ["Halo kak, cek profil ya", "Info dong kak", "Salam kenal semuanya"],
            "delay_min": 3,
            "delay_max": 5,
            "reply_to": False
        }
        save_settings(data)
    return data[str_uid]

def update_user_settings(user_id, key, value):
    data = load_settings()
    str_uid = str(user_id)
    if str_uid not in data:
        get_user_settings(user_id)
        data = load_settings()
    data[str_uid][key] = value
    save_settings(data)

async def send_progress_to_admin(user_id, target, current, total, status="running"):
    """Kirim progress ke admin dengan tombol stop"""
    progress_pct = int((current / total) * 100) if total > 0 else 0
    progress_bar = "▓" * (progress_pct // 10) + "░" * (10 - progress_pct // 10)
    
    text = (
        f"💎 **SPAM PREMIUM PROGRESS**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: `{user_id}`\n"
        f"🎯 Target: `{target}`\n"
        f"📊 Progress: [{progress_bar}] {progress_pct}%\n"
        f"📨 Terkirim: {current}/{total}\n"
        f"⏱ Status: {status}"
    )
    
    buttons = []
    if "Berjalan" in status or status == "running" or "Scraping" in status:
        buttons.append([Button.inline("🛑 STOP SPAM", f"STOP_SPAM_PREM:{user_id}")])
    
    try:
        if user_id in SPAM_PREM_PROGRESS and SPAM_PREM_PROGRESS[user_id].get("msg_id"):
            await bot.edit_message(ADMIN_ID, SPAM_PREM_PROGRESS[user_id]["msg_id"], text, buttons=buttons)
        else:
            msg = await bot.send_message(ADMIN_ID, text, buttons=buttons)
            SPAM_PREM_PROGRESS[user_id] = {"msg_id": msg.id}
    except Exception as e:
        print(f"Error sending progress: {e}")

async def run_spam_prem(client, user_id, target, count, reply_msg_id=None):
    """Jalankan spam premium dengan settings user"""
    target_name = str(target)
    try:
        settings = get_user_settings(user_id)
        messages = settings.get("messages", ["Halo kak"])
        delay_min = settings.get("delay_min", 3)
        delay_max = settings.get("delay_max", 5)
        reply_to = settings.get("reply_to", False)
        
        entity = await client.get_entity(target)
        target_name = getattr(entity, 'title', getattr(entity, 'first_name', str(target)))
        
        for i in range(count):
            if user_id not in ACTIVE_PREM_TASKS:
                return
                
            if not client.is_connected():
                await asyncio.sleep(5)
                continue
            
            msg = random.choice(messages)
            
            if reply_to and reply_msg_id:
                await client.send_message(entity, msg, reply_to=reply_msg_id)
            else:
                await client.send_message(entity, msg)
            
            if i % 3 == 0 or i == count - 1:
                await send_progress_to_admin(user_id, target_name, i + 1, count, "🔄 Berjalan...")
            
            delay = random.uniform(delay_min, delay_max)
            await asyncio.sleep(delay)
            
        await send_progress_to_admin(user_id, target_name, count, count, "✅ Selesai")
        
    except asyncio.CancelledError:
        return
    except Exception as e:
        print(f"Error Spam Prem: {e}")
        await send_progress_to_admin(user_id, target_name, 0, count, f"❌ Error: {str(e)[:30]}")

async def show_settings_menu(event, user_id):
    """Tampilkan menu settings spam premium"""
    settings = get_user_settings(user_id)
    messages = settings.get("messages", [])
    delay_min = settings.get("delay_min", 3)
    delay_max = settings.get("delay_max", 5)
    reply_to = settings.get("reply_to", False)
    
    reply_icon = "✅" if reply_to else "❌"
    
    text = (
        f"💎 **SETTINGS SPAM PREMIUM**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Daftar Pesan:** {len(messages)} pesan\n"
        f"⏱ **Delay:** {delay_min}-{delay_max} detik\n"
        f"↩️ **Reply Message:** {reply_icon}\n"
    )
    
    buttons = [
        [Button.inline("📝 Daftar Pesan", b"SPP_LIST_MSG")],
        [Button.inline("➕ Tambah Pesan", b"SPP_ADD_MSG")],
        [Button.inline(f"⏱ Delay: {delay_min}-{delay_max}s", b"SPP_SET_DELAY")],
        [Button.inline(f"↩️ Reply: {reply_icon}", b"SPP_TOGGLE_REPLY")],
        [Button.inline("🔙 Tutup", b"SPP_CLOSE")]
    ]
    
    await event.edit(text, buttons=buttons)

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".spambotpremium"] = {
        "title": "Spam Premium 💎",
        "usage": ".spambotpremium <target> <jumlah>\nSpam dengan variasi pesan.\n\n.set_spambotpremium\nAtur pesan & delay."
    }

    @client.on(events.NewMessage(pattern=r"(?i)^\.set_spambotpremium$"))
    async def set_spam_prem_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spambotpremium"): 
            return await event.edit("🔒 Fitur dikunci Admin.")
        
        await show_settings_menu(event, user_id)

    @client.on(events.NewMessage(pattern=r"(?i)^\.spambotpremium (\S+) (\d+)"))
    async def spam_prem_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spambotpremium"): 
            return await event.edit("🔒 Fitur Premium dikunci.")
        
        target = event.pattern_match.group(1)
        count = int(event.pattern_match.group(2))
        
        if count > 100:
            return await event.edit("⚠️ Maksimal 100 pesan per sesi.")
        
        if user_id in ACTIVE_PREM_TASKS and not ACTIVE_PREM_TASKS[user_id].done():
            return await event.edit("⚠️ Task Premium sedang berjalan.")

        reply_msg_id = None
        if event.reply_to_msg_id:
            reply_msg_id = event.reply_to_msg_id

        await event.delete()
        
        task = asyncio.create_task(run_spam_prem(client, user_id, target, count, reply_msg_id))
        ACTIVE_PREM_TASKS[user_id] = task
        
        try: 
            await task
        except asyncio.CancelledError: 
            pass
        finally: 
            if user_id in ACTIVE_PREM_TASKS: 
                del ACTIVE_PREM_TASKS[user_id]

    @client.on(events.CallbackQuery(pattern=b"SPP_LIST_MSG"))
    async def cb_list_msg(event):
        if event.sender_id != user_id: return
        settings = get_user_settings(user_id)
        messages = settings.get("messages", [])
        
        if not messages:
            return await event.answer("⚠️ Belum ada pesan.", alert=True)
        
        text = "📝 **DAFTAR PESAN SPAM**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        buttons = []
        
        for i, msg in enumerate(messages):
            preview = msg[:25] + "..." if len(msg) > 25 else msg
            text += f"{i+1}. {preview}\n"
            buttons.append([
                Button.inline(f"✏️ Edit {i+1}", f"SPP_EDIT:{i}"),
                Button.inline(f"🗑 Hapus {i+1}", f"SPP_DEL:{i}")
            ])
        
        buttons.append([Button.inline("🔙 Kembali", b"SPP_BACK")])
        await event.edit(text, buttons=buttons)

    @client.on(events.CallbackQuery(pattern=b"SPP_ADD_MSG"))
    async def cb_add_msg(event):
        if event.sender_id != user_id: return
        EDIT_STATE[user_id] = {"action": "add_msg"}
        await event.edit(
            "➕ **TAMBAH PESAN**\n\nKirim pesan baru yang ingin ditambahkan:",
            buttons=[[Button.inline("❌ Batal", b"SPP_BACK")]]
        )

    @client.on(events.CallbackQuery(pattern=r"SPP_EDIT:(\d+)"))
    async def cb_edit_msg(event):
        if event.sender_id != user_id: return
        idx = int(event.data.decode().split(":")[1])
        EDIT_STATE[user_id] = {"action": "edit_msg", "index": idx}
        
        settings = get_user_settings(user_id)
        current_msg = settings.get("messages", [])[idx] if idx < len(settings.get("messages", [])) else ""
        
        await event.edit(
            f"✏️ **EDIT PESAN {idx+1}**\n\nPesan saat ini:\n`{current_msg}`\n\nKirim pesan baru:",
            buttons=[[Button.inline("❌ Batal", b"SPP_BACK")]]
        )

    @client.on(events.CallbackQuery(pattern=r"SPP_DEL:(\d+)"))
    async def cb_del_msg(event):
        if event.sender_id != user_id: return
        idx = int(event.data.decode().split(":")[1])
        
        settings = get_user_settings(user_id)
        messages = settings.get("messages", [])
        
        if 0 <= idx < len(messages):
            messages.pop(idx)
            update_user_settings(user_id, "messages", messages)
            await event.answer("✅ Pesan dihapus!", alert=True)
        
        await cb_list_msg(event)

    @client.on(events.CallbackQuery(pattern=b"SPP_SET_DELAY"))
    async def cb_set_delay(event):
        if event.sender_id != user_id: return
        EDIT_STATE[user_id] = {"action": "set_delay"}
        await event.edit(
            "⏱ **ATUR DELAY**\n\nKirim delay dalam format: `min-max`\nContoh: `3-5` (artinya 3-5 detik)",
            buttons=[[Button.inline("❌ Batal", b"SPP_BACK")]]
        )

    @client.on(events.CallbackQuery(pattern=b"SPP_TOGGLE_REPLY"))
    async def cb_toggle_reply(event):
        if event.sender_id != user_id: return
        settings = get_user_settings(user_id)
        current = settings.get("reply_to", False)
        update_user_settings(user_id, "reply_to", not current)
        await event.answer(f"Reply: {'ON' if not current else 'OFF'}", alert=True)
        await show_settings_menu(event, user_id)

    @client.on(events.CallbackQuery(pattern=b"SPP_BACK"))
    async def cb_back(event):
        if event.sender_id != user_id: return
        if user_id in EDIT_STATE:
            del EDIT_STATE[user_id]
        await show_settings_menu(event, user_id)

    @client.on(events.CallbackQuery(pattern=b"SPP_CLOSE"))
    async def cb_close(event):
        if event.sender_id != user_id: return
        if user_id in EDIT_STATE:
            del EDIT_STATE[user_id]
        await event.delete()

    @client.on(events.NewMessage(incoming=False))
    async def input_listener(event):
        if user_id not in EDIT_STATE: return
        if event.sender_id != user_id: return
        
        state = EDIT_STATE.get(user_id, {})
        action = state.get("action")
        text = event.message.text.strip()
        
        if action == "add_msg":
            settings = get_user_settings(user_id)
            messages = settings.get("messages", [])
            messages.append(text)
            update_user_settings(user_id, "messages", messages)
            del EDIT_STATE[user_id]
            await event.reply(f"✅ Pesan ditambahkan! Total: {len(messages)} pesan")
        
        elif action == "edit_msg":
            idx = state.get("index", 0)
            settings = get_user_settings(user_id)
            messages = settings.get("messages", [])
            if 0 <= idx < len(messages):
                messages[idx] = text
                update_user_settings(user_id, "messages", messages)
            del EDIT_STATE[user_id]
            await event.reply("✅ Pesan diperbarui!")
        
        elif action == "set_delay":
            try:
                parts = text.split("-")
                delay_min = float(parts[0])
                delay_max = float(parts[1])
                if delay_min > delay_max:
                    delay_min, delay_max = delay_max, delay_min
                update_user_settings(user_id, "delay_min", delay_min)
                update_user_settings(user_id, "delay_max", delay_max)
                del EDIT_STATE[user_id]
                await event.reply(f"✅ Delay diatur: {delay_min}-{delay_max} detik")
            except:
                await event.reply("⚠️ Format salah. Gunakan: min-max (contoh: 3-5)")

@bot.on(events.CallbackQuery(pattern=r"STOP_SPAM_PREM:(.+)"))
async def stop_spam_prem(event):
    if event.sender_id != ADMIN_ID: return
    
    target_user = int(event.data.decode().split(":")[1])
    
    if target_user in ACTIVE_PREM_TASKS:
        ACTIVE_PREM_TASKS[target_user].cancel()
        del ACTIVE_PREM_TASKS[target_user]
        
        if target_user in SPAM_PREM_PROGRESS and SPAM_PREM_PROGRESS[target_user].get("msg_id"):
            try:
                text = (
                    f"💎 **SPAM PREMIUM PROGRESS**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 User: `{target_user}`\n"
                    f"⏱ Status: ❌ Dihentikan oleh Admin"
                )
                await bot.edit_message(ADMIN_ID, SPAM_PREM_PROGRESS[target_user]["msg_id"], text, buttons=None)
            except:
                pass
            del SPAM_PREM_PROGRESS[target_user]
        
        await event.answer("✅ Spam Premium dihentikan!", alert=True)
    else:
        await event.answer("⚠️ Task sudah selesai.", alert=True)
