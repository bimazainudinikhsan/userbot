# bmcodexbot/modules/auto_spam.py
import asyncio
import json
import os
import time
from telethon import events
from telethon.tl.types import DocumentAttributeSticker, DocumentAttributeAudio
from config import bot

SETTINGS_FILE = "user_autospam_settings.json"
AS_TASK = {}

# ==========================================
# 1. DATABASE & UTILS
# ==========================================
def get_settings(user_id):
    if not os.path.exists(SETTINGS_FILE):
        data = {}
    else:
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except:
            data = {}
            
    str_uid = str(user_id)
    if str_uid not in data:
        data[str_uid] = {
            "enabled": False,
            "messages": [],
            "delay": 60,
            "target_type": "user",
            "replied_chats": []
        }
        save_settings(data)
    return data[str_uid]

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except:
        pass

def update_setting(user_id, key, value):
    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except:
            pass
    
    str_uid = str(user_id)
    if str_uid not in data: 
        get_settings(user_id)
        # Reload data safely
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except:
            pass
    
    if str_uid in data:
        data[str_uid][key] = value
        save_settings(data)

# ==========================================
# 2. LOGIC BROADCAST / AUTO MESSAGE
# ==========================================
async def start_auto_spam(client, user_id):
    # Tidak lagi menjalankan broadcast loop; balasan otomatis ditangani handler incoming
    if user_id in AS_TASK:
        try:
            AS_TASK[user_id].cancel()
        except:
            pass
    return

async def run_spam_loop(client, msg, delay):
    return

async def stop_auto_spam(user_id):
    if user_id in AS_TASK:
        AS_TASK[user_id].cancel()
        del AS_TASK[user_id]

# ==========================================
# 3. REGISTER USERBOT
# ==========================================
async def resume_spam_tasks(client):
    # Dipanggil saat startup
    user_id = (await client.get_me()).id
    await start_auto_spam(client, user_id)

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".automsg"] = {"title": "Auto Message 📨", "usage": "Balas otomatis pesan masuk."}

    @client.on(events.NewMessage(incoming=True))
    async def automsg_handler(event):
        if not is_allowed("automessage"):
            return
        if event.out:
            return
        if not event.is_private:
            return
        try:
            entity = await client.get_entity(event.sender_id)
            if getattr(entity, "bot", False):
                return
        except:
            return
        s = get_settings(user_id)
        if not s.get("enabled"):
            return
        msgs = s.get("messages") or ([] if not s.get("message") else [s.get("message")])
        replied = s.get("replied_chats") or []
        if event.sender_id in replied:
            return
        try:
            t0 = time.time()
            await client.send_read_acknowledge(event.chat_id, event.message)
            async with client.action(event.chat_id, 'typing'):
                await asyncio.sleep(1.0)
            msg_obj = event.message
            mtype = "text"
            if getattr(msg_obj, "photo", None):
                mtype = "image"
            elif getattr(msg_obj, "video", None):
                mtype = "video"
            elif getattr(msg_obj, "document", None):
                attrs = getattr(msg_obj.document, "attributes", [])
                if any(isinstance(a, DocumentAttributeSticker) for a in attrs):
                    mtype = "sticker"
                elif any(isinstance(a, DocumentAttributeAudio) and getattr(a, "voice", False) for a in attrs):
                    mtype = "voice"
                else:
                    mtype = "document"
            elif event.media:
                mtype = "media"
            import random
            chosen = None
            if msgs:
                try:
                    chosen = random.choice(msgs)
                except:
                    chosen = msgs[0]
            default_by_type = {
                "text": "Terima kasih, pesan Anda sudah kami terima.",
                "image": "Terima kasih atas fotonya! Kami akan segera merespon.",
                "video": "Terima kasih atas videonya!",
                "voice": "Terima kasih atas voice note-nya!",
                "sticker": "Sticker diterima 👍",
                "document": "Dokumen Anda sudah diterima.",
                "media": "Konten media diterima.",
            }
            reply_text = chosen or default_by_type.get(mtype, "Terima kasih atas pesan Anda.")

            await event.reply(reply_text)
            replied.append(event.sender_id)
            update_setting(user_id, "replied_chats", replied)
            t1 = time.time()
            try:
                with open("auto_message.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": __import__("datetime").datetime.now().isoformat(),
                        "user_id": user_id,
                        "chat_id": event.chat_id,
                        "message_type": mtype,
                        "len": len(reply_text),
                        "latency_ms": int((t1 - t0) * 1000),
                        "ack": True,
                        "status": "ok"
                    }) + "\n")
            except:
                pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error Auto Message: {e}")
            try:
                with open("auto_message.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": __import__("datetime").datetime.now().isoformat(),
                        "user_id": user_id,
                        "chat_id": getattr(event, "chat_id", None),
                        "message_type": "unknown",
                        "len": 0,
                        "latency_ms": None,
                        "ack": False,
                        "status": "error",
                        "error": str(e)
                    }) + "\n")
            except:
                pass
            try:
                await event.reply("Maaf, sistem sedang sibuk. Pesan Anda sudah tercatat dan akan direspon.")
            except:
                pass

    # Tidak perlu memulai loop; handler incoming sudah aktif
    return
