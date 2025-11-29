# bmcodexbot/modules/unread.py
import asyncio
import json
import os
import logging
from telethon import events
from telethon.tl.types import User
from telethon.errors import FloodWaitError, MessageNotModifiedError

# File penyimpanan setting
SETTINGS_FILE = 'user_unread_settings.json'

# --- CONFIG ---
# Waktu istirahat setelah mengirim pesan ke 1 orang (agar tidak kena ban)
DELAY_PER_CHAT = 5 
# Berapa lama status 'sedang mengetik' muncul sebelum kirim pesan
TYPING_DURATION = 3 

def get_settings(user_id):
    if not os.path.exists(SETTINGS_FILE):
        data = {}
    else:
        try:
            with open(SETTINGS_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {}
    
    str_uid = str(user_id)
    if str_uid not in data:
        data[str_uid] = {
            "message": "Maaf baru balas, ada yang bisa dibantu? (Auto Reply Unread)",
        }
        save_settings(data)
    return data[str_uid]

def save_settings(data):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Gagal simpan setting unread: {e}")

def save_user_message(user_id, message):
    if not os.path.exists(SETTINGS_FILE): data = {}
    else:
        try: 
            with open(SETTINGS_FILE, 'r') as f: data = json.load(f)
        except: data = {}
        
    str_uid = str(user_id)
    if str_uid not in data: data[str_uid] = {}
    
    data[str_uid]["message"] = message
    save_settings(data)

async def register(client, user_id, is_allowed, check_status, help_dict):
    # Daftarkan ke menu Help
    help_dict[".replyunread"] = {
        "title": "Balas Chat Menumpuk 📩", 
        "usage": "Balas chat personal unread satu per satu dengan efek mengetik."
    }
    help_dict[".set_unread"] = {
        "title": "Set Pesan Unread 📝", 
        "usage": ".set_unread <pesan baru>"
    }

    # --- COMMAND: SET PESAN ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.set_unread (.+)"))
    async def set_unread_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        if not is_allowed("unread"): return await event.edit("🔒 Fitur dikunci Admin.")

        message = event.pattern_match.group(1).strip()
        save_user_message(user_id, message)
        await event.edit(f"✅ **Pesan Unread Disimpan:**\n\n`{message}`")

    # --- COMMAND: EKSEKUSI REPLY UNREAD ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.replyunread$"))
    async def reply_unread_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not await check_status(client, user_id, event): return
        if not is_allowed("autoreply"): return await event.edit("🔒 Fitur dikunci Admin.")

        settings = get_settings(user_id)
        reply_msg = settings.get("message")
        
        status_msg = await event.edit("🔄 **Memindai chat personal yang belum dibaca...**")
        
        target_chats = []
        
        # Iterasi dialog (Limit None = Scan semua)
        async for dialog in client.iter_dialogs(limit=None):
            # === FILTER FILTER KETAT ===
            # Pastikan hanya User Personal (Bukan Grup, Channel, atau Bot)
            is_valid_user = False
            if dialog.is_user and not dialog.is_channel and not dialog.is_group:
                if isinstance(dialog.entity, User) and not dialog.entity.bot:
                    is_valid_user = True
            
            if dialog.unread_count > 0 and is_valid_user:
                target_chats.append(dialog)

        total_count = len(target_chats)
        if total_count == 0:
            return await status_msg.edit("✅ **Semua chat personal sudah terbaca.**\nTidak ada tindakan yang diperlukan.")

        await status_msg.edit(
            f"🔍 Ditemukan: **{total_count}** chat personal belum dibaca.\n"
            f"🚀 **Memulai Auto Reply...**\n\n"
            f"✍️ Efek Mengetik: **{TYPING_DURATION} detik**\n"
            f"⏳ Jeda Antar Chat: **{DELAY_PER_CHAT} detik**\n"
            "⚠️ _Bot akan berjalan di latar belakang._"
        )
        await asyncio.sleep(2)
        
        success = 0
        failed = 0
        
        for i, dialog in enumerate(target_chats):
            try:
                current_user_name = dialog.name or "Unknown"
                
                # --- UPDATE STATUS DI TELEGRAM ---
                # Memberi info ke kamu siapa yang sedang diproses
                try:
                    await status_msg.edit(
                        f"🚀 **Proses Berjalan: {i+1}/{total_count}**\n"
                        f"👤 Target: **{current_user_name}**\n"
                        f"✍️ Status: **Sedang Mengetik...**\n"
                        f"✅ Sukses: {success} | ❌ Gagal: {failed}"
                    )
                except MessageNotModifiedError: pass
                except: pass # Abaikan error edit jika terlalu cepat

                # 1. TANDAI SUDAH DIBACA (Mark as Read)
                await client.send_read_acknowledge(dialog.entity)
                
                # 2. EFEK MENGETIK (TYPING ACTION) & KIRIM
                # 'typing' mengirim sinyal ke chat lawan bahwa kamu sedang mengetik
                async with client.action(dialog.entity, 'typing'):
                    await asyncio.sleep(TYPING_DURATION) 
                    await client.send_message(dialog.entity, reply_msg)
                
                success += 1
                
                # 3. JEDA AMAN (COOLDOWN)
                # Tampilkan status cooldown (Jeda agar tidak kena FloodWait)
                try:
                    await status_msg.edit(
                        f"🚀 **Proses Berjalan: {i+1}/{total_count}**\n"
                        f"👤 Selesai: **{current_user_name}**\n"
                        f"⏳ **Cooldown: Menunggu {DELAY_PER_CHAT} detik...**\n"
                        f"✅ Sukses: {success} | ❌ Gagal: {failed}"
                    )
                except: pass
                
                await asyncio.sleep(DELAY_PER_CHAT)

            except FloodWaitError as e:
                print(f"FloodWait {e.seconds}s. Sleeping...")
                try:
                    await status_msg.edit(f"⚠️ **Limit Telegram (FloodWait).**\nIstirahat {e.seconds} detik...")
                except: pass
                await asyncio.sleep(e.seconds + 5)
            except Exception as e:
                print(f"Gagal reply {dialog.name}: {e}")
                failed += 1
        
        await status_msg.edit(
            f"✅ **Selesai Membalas Unread!**\n\n"
            f"📊 Total: {total_count}\n"
            f"✅ Berhasil: {success}\n"
            f"❌ Gagal: {failed}\n\n"
            f"Semua pesan personal yang menumpuk sudah dibalas."
        )
