import asyncio
import platform
import logging
import os
import socket 
import json
from datetime import datetime

from telethon import TelegramClient, Button
from telethon.sessions import StringSession
from telethon.errors import AuthKeyError, SecurityError

from config import bot, API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from database import get_all_members_safe, save_session_to_sheet
from state import ACTIVE_USERBOTS
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MANAGER - %(levelname)s - %(message)s')

async def wait_for_internet():
    print("🔄 Memeriksa koneksi internet...")
    while True:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            print("✅ Internet OK.")
            return
        except OSError:
            print("❌ Tidak ada internet. Menunggu...", end="\r")
            await asyncio.sleep(5)

async def main():
    await wait_for_internet()
    print("🚀 Memulai Bot Manager...")
    
    try:
        bot.use_ipv6 = False 
        await bot.start(bot_token=BOT_TOKEN)
    except Exception as e:
        print(f"❌ Gagal Start Bot: {e}")
        return
    
    print(f"✅ Bot Manager Online: @{(await bot.get_me()).username}")

    # --- RESUME USERBOTS ---
    print("🔄 Mengecek userbot yang aktif di Database...")
    if not os.path.exists("botsession"):
        os.makedirs("botsession")

    records = get_all_members_safe()
    count = 0
    
    for row in records:
        try:
            uid = str(row.get("User ID"))
            status = row.get("Status") # Ambil status
            db_string = row.get("Session String")
            expired = row.get("Expired")
            
            # --- MODIFIKASI DISINI: SKIP JIKA PENDING ---
            if status == "Pending":
                # Jangan jalankan userbot jika pending
                continue

            is_active = False
            try:
                exp_date = datetime.strptime(expired, "%d-%m-%Y")
                # Pastikan HANYA yang APPROVED dan BELUM EXPIRED yang jalan
                if status == "Approved" and datetime.now() < exp_date:
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
                        client = TelegramClient(local_path, API_ID, API_HASH)
                        source = "FILE"
                    except: pass

                # 2. Cek String DB
                if not client and db_string and len(str(db_string)) > 50:
                    try:
                        client = TelegramClient(StringSession(db_string), API_ID, API_HASH)
                        source = "STRING"
                    except: pass

                # 3. Start Client
                if client:
                    try:
                        await client.start()
                        if await client.get_me():
                            ACTIVE_USERBOTS[user_id_int] = client
                            asyncio.create_task(start_userbot(client, user_id_int))
                            # Resume task lain jika ada
                            await auto_spam.resume_spam_tasks(client)
                            count += 1
                            print(f"✅ {uid} ONLINE ({source})")
                        else:
                            await client.disconnect()
                    except Exception as e:
                        print(f"❌ Gagal connect {uid}: {e}")

        except Exception as e:
            pass 

    print(f"📊 Total Userbot Berjalan: {count}")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass