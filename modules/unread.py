# bmcodexbot/modules/unread.py
import asyncio
import json
import os
import logging
from datetime import datetime
from telethon import events, Button
from telethon.tl.types import User, ChatBannedRights
from telethon.errors import FloodWaitError, MessageNotModifiedError, UserNotParticipantError, BotMethodInvalidError
from telethon.tl.functions.channels import GetParticipantRequest

# File penyimpanan setting
SETTINGS_FILE = 'user_unread_settings.json'
UNREAD_MODE_FILE = 'unread_mode_status.json'

# Default settings
DEFAULT_SETTINGS = {
    "message": "Maaf baru balas, ada yang bisa dibantu? (Auto Reply Unread)",
    "typing_duration": 3,
    "delay_between_chats": 5,
    "max_retries": 3,
    "last_used": None
}

# --- CONFIG ---
# Waktu istirahat setelah mengirim pesan ke 1 orang (agar tidak kena ban)
DELAY_PER_CHAT = 5 
# Berapa lama status 'sedang mengetik' muncul sebelum kirim pesan
TYPING_DURATION = 3 

# Track admin actions
ADMIN_ACTION_STATE = {}

def load_json_file(filename, default=None):
    """Helper to load JSON file with error handling"""
    if default is None:
        default = {}
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Error loading {filename}: {e}")
    return default

def save_json_file(filename, data):
    """Helper to save JSON file with error handling"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"Error saving {filename}: {e}")
        return False

def get_settings(user_id):
    """Get user settings with defaults"""
    data = load_json_file(SETTINGS_FILE, {})
    str_uid = str(user_id)
    
    if str_uid not in data or not isinstance(data[str_uid], dict):
        data[str_uid] = DEFAULT_SETTINGS.copy()
        save_json_file(SETTINGS_FILE, data)
    
    # Ensure all default settings exist
    for key, value in DEFAULT_SETTINGS.items():
        if key not in data[str_uid]:
            data[str_uid][key] = value
    
    return data[str_uid]

def update_settings(user_id, updates):
    """Update user settings"""
    data = load_json_file(SETTINGS_FILE, {})
    str_uid = str(user_id)
    
    if str_uid not in data:
        data[str_uid] = DEFAULT_SETTINGS.copy()
    
    data[str_uid].update(updates)
    data[str_uid]['last_updated'] = datetime.now().isoformat()
    
    return save_json_file(SETTINGS_FILE, data)

def get_unread_mode_status():
    """Get unread mode status for all users"""
    return load_json_file(UNREAD_MODE_FILE, {})

def set_unread_mode(user_id, status):
    """Enable/disable unread mode for user"""
    status_data = get_unread_mode_status()
    status_data[str(user_id)] = {
        'enabled': status,
        'last_updated': datetime.now().isoformat()
    }
    return save_json_file(UNREAD_MODE_FILE, status_data)

def is_unread_mode_enabled(user_id):
    """Check if unread mode is enabled for user"""
    status_data = get_unread_mode_status()
    return status_data.get(str(user_id), {}).get('enabled', False)

def save_user_message(user_id, message):
    """Legacy function for backward compatibility"""
    return update_settings(user_id, {"message": message})

async def is_valid_user(client, entity):
    """Check if entity is a valid user (not group/channel/bot)"""
    try:
        if not hasattr(entity, 'id'):
            return False
            
        # Skip if it's a bot
        if hasattr(entity, 'bot') and entity.bot:
            return False
            
        # Skip if it's a group or channel
        if hasattr(entity, 'broadcast') or hasattr(entity, 'megagroup'):
            return False
            
        # Additional check for user type
        user = await client.get_entity(entity)
        return isinstance(user, User)
        
    except Exception as e:
        logging.error(f"Error checking user validity: {e}")
        return False

# Track progress for each user
USER_PROGRESS = {}

async def process_unread_chats(event, client, user_id, is_allowed, check_status):
    """Process unread messages in user's chats"""
    if not await check_status(client, user_id, event):
        return
        
    if not await is_allowed("unread"):
        return await event.edit("❌ Anda tidak memiliki izin untuk menggunakan fitur ini.")
    
    settings = get_settings(user_id)
    status_msg = await event.edit("🔄 Mencari chat yang belum dibaca...")
    
    try:
        me = await client.get_me()
        is_bot = getattr(me, 'bot', False)
        
        # Debug info
        logging.info(f"Account info - ID: {me.id}, Username: {me.username}, First Name: {me.first_name}, Is Bot: {is_bot}")
        
        # If it's a bot account, just show the progress UI
        if is_bot:
            return await show_progress_ui(event, user_id, "Bot siap menerima update progress dari userbot...")
            
    except Exception as e:
        logging.error(f"Error getting account info: {e}")
        return await status_msg.edit("❌ Gagal memeriksa status akun. Silakan coba lagi.")
    
    # If we reach here, it's a user account (userbot)
    await process_userbot_unread(event, client, user_id, status_msg, settings)

async def show_progress_ui(event, user_id, message, progress=None, total=None, current=None):
    """Show progress UI in the bot"""
    try:
        if progress is not None and total is not None and current is not None:
            progress_bar = ""
            filled = int(20 * current / total) if total > 0 else 0
            progress_bar = f"[{'=' * filled}{' ' * (20 - filled)}] {current}/{total}"
            message = f"{message}\n\n{progress_bar}\n{progress}%"
            
        await event.edit(message)
    except Exception as e:
        logging.error(f"Error updating progress UI: {e}")

async def process_userbot_unread(event, client, user_id, status_msg, settings):
    """Handle unread messages processing for userbot"""
    target_chats = []
    
    try:
        # Get dialogs with unread messages
        async for dialog in client.iter_dialogs(limit=100):
            try:
                # Skip groups, channels, and broadcasts
                if dialog.is_group or dialog.is_channel or dialog.is_broadcast:
                    continue
                    
                # Only process user dialogs with unread messages
                if dialog.unread_count > 0 and dialog.is_user:
                    try:
                        user = await client.get_entity(dialog.entity)
                        if not getattr(user, 'bot', False):  # Skip bots
                            target_chats.append(dialog)
                    except Exception as e:
                        logging.error(f"Error getting user {dialog.id}: {e}")
                        continue
            except Exception as e:
                logging.error(f"Error processing dialog: {e}")
                continue
                
        total_chats = len(target_chats)
        if total_chats == 0:
            await status_msg.edit("✅ Tidak ada chat personal yang belum dibaca.")
            return
            
        # Update status
        await status_msg.edit(f"🔍 Ditemukan {total_chats} chat dengan pesan belum dibaca.\nMulai memproses...")
        
        success = 0
        failed = 0
        
        for i, dialog in enumerate(target_chats, 1):
            try:
                user = await client.get_entity(dialog.entity)
                user_name = getattr(user, 'first_name', '') or getattr(user, 'title', 'Unknown')
                
                # Update progress
                progress = int((i / total_chats) * 100)
                progress_msg = (
                    f"🚀 **Proses Berjalan** ({i}/{total_chats})\n"
                    f"👤 Target: **{user_name}**\n"
                    f"✍️ Status: **Mengirim balasan...**\n"
                    f"✅ Sukses: {success} | ❌ Gagal: {failed}"
                )
                
                # Send progress update to admin
                await event.respond(progress_msg)
                
                # Mark as read
                await client.send_read_acknowledge(dialog.entity)
                
                # Format message with user's name
                message = settings['message'].format(
                    name=user_name,
                    id=user.id,
                    username=getattr(user, 'username', '')
                )
                
                # Typing effect and send message
                async with client.action(dialog.entity, 'typing'):
                    await asyncio.sleep(settings.get('typing_duration', 3))
                    await client.send_message(dialog.entity, message)
                
                success += 1
                
                # Add delay between messages
                await asyncio.sleep(settings.get('delay_between_chats', 5))
                
            except FloodWaitError as e:
                wait_time = e.seconds
                await event.respond(f"⚠️ **Menunggu {wait_time} detik** - Melebihi batas pengiriman Telegram...")
                await asyncio.sleep(wait_time + 5)
                continue
                
            except Exception as e:
                logging.error(f"Error processing chat {dialog.id}: {e}")
                failed += 1
                continue
                
        # Send completion message
        await event.respond(
            f"✅ **Proses Selesai!**\n\n"
            f"Total chat diproses: {total_chats}\n"
            f"✅ Berhasil: {success}\n"
            f"❌ Gagal: {failed}"
        )
        
    except Exception as e:
        error_msg = str(e).lower()
        logging.error(f"Error in process_userbot_unread: {e}")
        
        if any(term in error_msg for term in ['flood', 'wait']):
            await event.respond(
                "⚠️ **Terlalu banyak permintaan**\n"
                "Silakan tunggu beberapa saat dan coba lagi."
                "\n\nKode Error: FLOOD_WAIT"
            )
        else:
            return await event.respond(
                f"❌ **Terjadi kesalahan**\n\n"
                f"Pesan error: {str(e)[:200]}\n\n"
                "Pastikan:\n"
                "1. Akun userbot sudah terhubung\n"
                "2. Koneksi internet stabil\n"
                "3. Coba lagi nanti"
            )

    total_count = len(target_chats)
    if total_count == 0:
        return await status_msg.edit("✅ Tidak ada chat personal yang belum dibaca.")

    # Update last used time
    update_settings(user_id, {"last_used": datetime.now().isoformat()})
    
    await status_msg.edit(
        f"🔍 Ditemukan: **{total_count}** chat personal belum dibaca.\n"
        f"🚀 **Memulai Auto Reply...**\n\n"
        f"✍️ Efek Mengetik: **{settings.get('typing_duration', 3)} detik**\n"
        f"⏳ Jeda Antar Chat: **{settings.get('delay_between_chats', 5)} detik**\n"
        "⚠️ _Bot akan berjalan di latar belakang._"
    )
    
    success = 0
    failed = 0
    processed = 0
    
    for dialog in target_chats:
        try:
            user = await client.get_entity(dialog.entity)
            user_name = getattr(user, 'first_name', '') or getattr(user, 'title', 'Unknown')
            
            # Update status
            processed += 1
            progress = f"({processed}/{total_count})"
            
            try:
                status_text = (
                    f"🚀 **Proses Berjalan** {progress}\n"
                    f"👤 Target: **{user_name}**\n"
                    f"✍️ Status: **Sedang Mengetik...**\n"
                    f"✅ Sukses: {success} | ❌ Gagal: {failed}"
                )
                await status_msg.edit(status_text)
            except Exception:
                pass
            
            # Mark as read
            await client.send_read_acknowledge(dialog.entity)
            
            # Format message with user's name
            message = settings['message'].format(
                name=user_name,
                id=user.id,
                username=getattr(user, 'username', '')
            )
            
            # Typing effect
            async with client.action(dialog.entity, 'typing'):
                await asyncio.sleep(settings.get('typing_duration', 3))
                await client.send_message(dialog.entity, message)
            
            success += 1
            
            # Show cooldown status
            try:
                status_text = (
                    f"🚀 **Proses Berjalan** {progress}\n"
                    f"👤 Selesai: **{user_name}**\n"
                    f"⏳ **Cooldown: Menunggu {settings.get('delay_between_chats', 5)} detik...**\n"
                    f"✅ Sukses: {success} | ❌ Gagal: {failed}"
                )
                await status_msg.edit(status_text)
            except Exception:
                pass
            
            # Delay between chats
            await asyncio.sleep(settings.get('delay_between_chats', 5))
            
        except FloodWaitError as e:
            # Handle flood wait
            wait_time = e.seconds
            await status_msg.edit(f"⏳ **Tunggu {wait_time} detik**\nMelebihi batas pengiriman Telegram...")
            await asyncio.sleep(wait_time + 5)
            
        except Exception as e:
            logging.error(f"Error processing chat {dialog.id}: {e}")
            failed += 1
            
    # Final status
    await status_msg.edit(
        f"✅ **Selesai Membalas Unread!**\n\n"
        f"📊 Total: {total_count}\n"
        f"✅ Berhasil: {success}\n"
        f"❌ Gagal: {failed}\n\n"
        f"Semua pesan personal yang menumpuk sudah dibalas."
    )

async def register(client, user_id, is_allowed, check_status, help_dict):
    """Register help commands"""
    help_dict["unread"] = {
        "title": "🔔 Mode Balas Otomatis",
        "description": "Balas otomatis ke chat yang belum dibaca",
        "commands": {
            ".unread on": "Aktifkan mode balas otomatis",
            ".unread off": "Nonaktifkan mode balas otomatis",
            ".unread setmsg": "Atur pesan balasan otomatis",
            ".unread settings": "Lihat pengaturan saat ini",
            ".unread start": "Mulai membalas chat yang belum dibaca"
        }
    }

    # --- COMMAND: UNREAD MODE TOGGLE ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.unread\s+(on|off|status|setmsg|start|settings)"))
    async def unread_mode_handler(event):
        if not await check_status(client, user_id, event): 
            return
            
        if not is_allowed("unread"): 
            return await event.edit("🔒 Fitur ini dikunci oleh Admin.")
        
        # Get account info
        try:
            me = await client.get_me()
            is_bot = getattr(me, 'bot', False)
            logging.info(f"Command from - ID: {me.id}, Username: {me.username}, Is Bot: {is_bot}")
        except Exception as e:
            logging.error(f"Error getting account info: {e}")
            is_bot = False
            
        args = event.pattern_match.group(1).lower()
        
        # For bot accounts, only allow status and settings
        if is_bot and args not in ['status', 'settings']:
            return await event.edit(
                "🤖 **Mode Tampilan Bot Aktif**\n\n"
                "Bot ini hanya menampilkan progress pengiriman pesan.\n"
                "Gunakan perintah `.unread status` untuk melihat status terbaru."
            )
            
        settings = get_settings(user_id)
        
        if args == "on":
            set_unread_mode(user_id, True)
            await event.edit("✅ **Mode Balas Otomatis Diaktifkan**\n\nSekarang bot akan membalas chat yang belum dibaca.")
            
        elif args == "off":
            set_unread_mode(user_id, False)
            await event.edit("❌ **Mode Balas Otomatis Dinonaktifkan**")
            
        elif args == "status":
            status = "🟢 AKTIF" if is_unread_mode_enabled(user_id) else "🔴 NONAKTIF"
            await event.edit(
                f"🔔 **Status Mode Balas Otomatis**\n\n"
                f"Status: **{status}**\n"
                f"Pesan: `{settings['message']}`\n"
                f"Delay: {settings['delay_between_chats']} detik\n"
                f"Typing: {settings['typing_duration']} detik"
            )
            
        elif args == "setmsg":
            ADMIN_ACTION_STATE[user_id] = {"action": "set_unread_msg"}
            await event.edit(
                "✍️ **Atur Pesan Balasan Otomatis**\n\n"
                "Silakan kirim pesan yang akan dikirim ke chat yang belum dibaca.\n"
                "Gunakan variabel `{name}` untuk menyertakan nama pengirim.\n\n"
                "Contoh:\n"
                "`Hai {name}, terima kasih sudah menghubungi saya. Saya akan segera membalas pesan Anda.`"
            )
            
        elif args == "settings":
            await show_unread_settings(event, user_id, settings)
            
        elif args == "start":
            await process_unread_chats(event, client, user_id, is_allowed, check_status)
    
    # --- HANDLE MESSAGE INPUT FOR SETTINGS ---
    @client.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id == user_id))
    async def unread_message_handler(event):
        if user_id not in ADMIN_ACTION_STATE:
            return
            
        action = ADMIN_ACTION_STATE[user_id].get("action")
        
        if action == "set_unread_msg":
            message = event.text.strip()
            if not message:
                await event.reply("❌ Pesan tidak boleh kosong.")
                return
                
            update_settings(user_id, {"message": message, "last_updated": datetime.now().isoformat()})
            del ADMIN_ACTION_STATE[user_id]
            await event.reply(f"✅ **Pesan berhasil disimpan:**\n\n`{message}`")
    
    async def show_unread_settings(event, user_id, settings=None):
        if settings is None:
            settings = get_settings(user_id)
            
        status = "🟢 AKTIF" if is_unread_mode_enabled(user_id) else "🔴 NONAKTIF"
        last_used = settings.get('last_used', 'Belum pernah digunakan')
        
        if last_used and last_used != 'Belum pernah digunakan':
            try:
                last_used_dt = datetime.fromisoformat(last_used)
                last_used = last_used_dt.strftime("%d %b %Y %H:%M")
            except:
                pass
        
        buttons = [
            [
                Button.inline("🔘 Status: " + ("Hidup" if is_unread_mode_enabled(user_id) else "Mati"), 
                           b"unread_toggle"),
                Button.inline("✏️ Pesan", b"unread_set_msg")
            ],
            [
                Button.inline("⏱️ Delay: " + str(settings.get('delay_between_chats', 5)) + "s", 
                           b"unread_set_delay"),
                Button.inline("⌨️ Typing: " + str(settings.get('typing_duration', 3)) + "s", 
                           b"unread_set_typing")
            ],
            [Button.inline("🚀 Mulai Balas Sekarang", b"unread_start")],
            [Button.inline("❌ Tutup", b"unread_close")]
        ]
        
        text = (
            f"🔔 **PENGATURAN BALAS OTOMATIS**\n\n"
            f"Status: **{status}**\n"
            f"Terakhir Digunakan: **{last_used}**\n\n"
            "**Pesan Saat Ini:**\n"
            f"`{settings.get('message', 'Tidak ada pesan')}`"
        )
        
        try:
            await event.edit(text, buttons=buttons)
        except:
            await event.reply(text, buttons=buttons)

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
