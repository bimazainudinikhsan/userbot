# bmcodexbot/main.py
import asyncio
import platform
import logging
import os
import socket 
import sqlite3
import json
from datetime import datetime

from telethon import TelegramClient, Button
from telethon.sessions import StringSession
from telethon.errors import PersistentTimestampOutdatedError, SecurityError, AuthKeyError

from config import bot, API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from database import get_all_members_safe, save_session_to_sheet
from state import ACTIVE_USERBOTS, GLOBAL_CONFIG
from aktif_fitur import start_userbot

# Import Modules
import bot_handlers.admin
import bot_handlers.nav
import bot_handlers.auth
import bot_handlers.payment
import bot_handlers.messages
import bot_handlers.livechat
import bot_handlers.remote_app
from modules import auto_spam 

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MANAGER - %(levelname)s - %(message)s')

# ===============================================
# FUNGSI UTILITY
# ===============================================
async def wait_for_internet():
    print("🔄 Memeriksa koneksi internet...")
    was_offline = False
    
    while True:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            if was_offline:
                print("✅ Internet Terhubung Kembali! Melanjutkan...")
            else:
                print("✅ Internet OK.")
            return was_offline
        except OSError:
            was_offline = True
            print("❌ Tidak ada internet. Menunggu... (Retry 5s)", end="\r")
            await asyncio.sleep(5)

async def check_expired_loop():
    while True:
        try:
            records = get_all_members_safe()
            to_disconnect = []

            for row in records:
                uid = str(row.get("User ID"))
                expired_str = row.get("Expired")
                
                if uid.isdigit() and int(uid) in ACTIVE_USERBOTS:
                    try:
                        exp_date = datetime.strptime(expired_str, "%d-%m-%Y")
                        if datetime.now() > exp_date:
                            to_disconnect.append(int(uid))
                    except ValueError:
                        pass
            
            for user_id in to_disconnect:
                print(f"⛔ [EXPIRED] Mematikan userbot {user_id}...")
                client = ACTIVE_USERBOTS.get(user_id)
                if client:
                    await client.disconnect()
                    del ACTIVE_USERBOTS[user_id]
                    try:
                        await bot.send_message(
                            user_id, 
                            "⛔ **Masa Aktif Habis!**\n\nUserbot dinonaktifkan otomatis."
                        )
                    except: pass

        except Exception as e:
            print(f"❌ Error pada Auto-Check Loop: {e}")

        await asyncio.sleep(3600)

async def send_startup_notification():
    """Mengirim notifikasi ke admin saat bot baru nyala (terutama setelah restart)"""
    if os.path.exists("RESTART_FLAG.json"):
        try:
            with open("RESTART_FLAG.json", "r") as f:
                data = json.load(f)
            
            # 1. Hapus Pesan "Restarting..." lama
            try:
                await bot.delete_messages(data.get("chat_id"), data.get("msg_id"))
            except: pass
            
            # 2. Kirim Dashboard Admin Langsung
            # Kita import dashboard di sini untuk memastikan handler sudah siap
            from bot_handlers.admin.dashboard import send_admin_dashboard
            
            # Kita buat object dummy event agar kompatibel dengan handler dashboard
            # Atau panggil fungsi helper dashboard jika ada
            
            await bot.send_message(
                ADMIN_ID,
                "✅ **SYSTEM REBOOT SUCCESS**\nBot telah aktif kembali.",
                buttons=[[Button.inline("👑 Buka Dashboard Admin", b"cmd_admin_dashboard")]]
            )
            
            # Hapus flag agar tidak double notif next time
            os.remove("RESTART_FLAG.json")
            
        except Exception as e:
            print(f"⚠️ Gagal memproses restart flag: {e}")
            if os.path.exists("RESTART_FLAG.json"): os.remove("RESTART_FLAG.json")
    else:
        # Start manual (bukan restart via bot), opsional mau kirim notif atau tidak
        print("ℹ️ Bot started manually.")

# ===============================================
# MAIN FUNCTION
# ===============================================
async def main():
    await wait_for_internet()
    print("🚀 Memulai Bot Manager...")
    
    try:
        bot.use_ipv6 = False 
        await bot.start(bot_token=BOT_TOKEN)
    except Exception as e:
        print(f"❌ Gagal Start Bot: {e}")
        return
    
    me = await bot.get_me()
    print(f"✅ Bot Manager Online: @{me.username}")

    # --- HANDLE RESTART NOTIFICATION ---
    await send_startup_notification()

    # --- RESUME USERBOTS ---
    print("🔄 Mengecek userbot yang aktif di Database...")
    if not os.path.exists("botsession"):
        os.makedirs("botsession")

    try:
        records = get_all_members_safe()
        count = 0
        
        for row in records:
            try:
                uid = str(row.get("User ID"))
                status = row.get("Status")
                db_string = row.get("Session String")
                expired = row.get("Expired")
                
                is_active = False
                try:
                    exp_date = datetime.strptime(expired, "%d-%m-%Y")
                    if datetime.now() < exp_date and status == "Approved":
                        is_active = True
                except ValueError: pass
                
                if is_active:
                    user_id_int = int(uid)
                    client = None
                    source = "NONE"

                    # 1. Cek File Lokal
                    local_path = f"botsession/{uid}"
                    if os.path.exists(f"{local_path}.session"):
                        try:
                            client = TelegramClient(local_path, API_ID, API_HASH, connection_retries=2, use_ipv6=False)
                            source = "FILE"
                        except: pass

                    # 2. Cek String DB
                    if not client and db_string and len(str(db_string)) > 50:
                        try:
                            client = TelegramClient(StringSession(db_string), API_ID, API_HASH, connection_retries=2, use_ipv6=False)
                            source = "STRING"
                        except: pass

                    # 3. Start Client
                    if client:
                        try:
                            await client.start()
                            if await client.get_me():
                                ACTIVE_USERBOTS[user_id_int] = client
                                asyncio.create_task(start_userbot(client, user_id_int))
                                await auto_spam.resume_spam_tasks(client)
                                count += 1
                                print(f"✅ {uid} ONLINE ({source})")
                                
                                # Auto-Sync ke Sheet jika pakai File
                                if source == "FILE" and (not db_string or len(str(db_string)) < 50):
                                    ss = StringSession()
                                    ss.set_dc(client.session.dc_id, client.session.server_address, client.session.port)
                                    ss.auth_key = client.session.auth_key
                                    save_session_to_sheet(uid, ss.save())
                            else:
                                await client.disconnect()
                        except (AuthKeyError, SecurityError):
                            # Jika sesi rusak, hapus file lokal agar user login ulang bersih
                            try: await client.disconnect()
                            except: pass
                            if source == "FILE" and os.path.exists(f"{local_path}.session"):
                                os.remove(f"{local_path}.session")
                        except Exception as e:
                            print(f"❌ Gagal connect {uid}: {e}")

            except Exception as e:
                pass # Skip row error

        print(f"📊 Total Userbot Berjalan: {count}")

    except Exception as e:
        print(f"❌ Error saat loading userbots: {e}")

    asyncio.create_task(check_expired_loop())
    await bot.run_until_disconnected()

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass