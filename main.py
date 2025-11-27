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
from telethon.errors import PersistentTimestampOutdatedError, SecurityError

# Import Modules
from config import bot, API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from database import get_all_members_safe
from state import ACTIVE_USERBOTS, GLOBAL_CONFIG
from aktif_fitur import start_userbot

# Import handlers & Menu Helper
import bot_handlers
from bot_handlers.nav import get_main_menu_data
from bot_handlers.admin import show_admin_dashboard

# Import Spambot untuk Resume
from modules import spambot 

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MANAGER - %(levelname)s - %(message)s')

# ===============================================
# FUNGSI CEK KONEKSI INTERNET
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
            print("❌ Tidak ada internet. Menunggu koneksi... (Coba lagi dalam 5s)", end="\r")
            await asyncio.sleep(5)

# ===============================================
# TASK: AUTO CHECK EXPIRED
# ===============================================
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

# ===============================================
# FUNGSI BROADCAST STARTUP
# ===============================================
async def broadcast_system_online(is_restart=False):
    print("📢 Mengirim broadcast 'System Online' ke member...")
    now_str = datetime.now().strftime("%H:%M WIB")
    
    all_members = get_all_members_safe()
    count = 0

    for member in all_members:
        try:
            uid_str = str(member.get("User ID"))
            if not uid_str.isdigit(): continue
            
            user_id = int(uid_str)
            # Skip admin, karena admin ditangani terpisah via restart flag
            if user_id == ADMIN_ID: continue 

            is_approved = member.get("Status") == "Approved"
            
            menu_text, menu_buttons = get_main_menu_data(is_approved)
            
            if is_restart:
                header = (
                    f"✅ **SISTEM KEMBALI ONLINE**\n"
                    f"🕒 Waktu: `{now_str}`\n\n"
                    f"Terima kasih telah menunggu. Layanan kini sudah aktif kembali.\n"
                    f"Silakan pilih menu di bawah untuk melanjutkan:\n\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n\n"
                )
            else:
                header = (
                    f"✅ **BOT CLEAR VIRUS KEMBALI AKTIF**\n"
                    f"🕒 Waktu: `{now_str}`\n\n"
                    f"Layanan sudah siap digunakan kembali.\n\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n\n"
                )
            
            # INI YANG MEMBUAT USER LANGSUNG DAPAT MENU NAVIGASI
            full_message = header + menu_text
            
            await bot.send_message(user_id, full_message, buttons=menu_buttons)
            count += 1
            await asyncio.sleep(0.1) 
            
        except Exception:
            pass 
            
    print(f"✅ Broadcast terkirim ke {count} member.")

async def send_admin_dashboard_startup(target_id):
    # Ini memanggil fungsi dashboard yang sudah ada di admin.py
    # Tapi kita perlu trigger dummy event atau kirim pesan baru
    try:
        is_trial_on = GLOBAL_CONFIG.get("free_trial", False)
        status_trial = "✅ ON" if is_trial_on else "❌ OFF"
        
        text = (
            "✅ **SISTEM ONLINE**\n"
            "Restart berhasil diselesaikan.\n\n"
            "👑 **ADMIN DASHBOARD**\n"
            "Selamat datang kembali, Admin! Silakan pilih menu manajemen:"
        )
        buttons = [
            [Button.inline(f"🆓 Mode Free Trial: {status_trial}", b"TOGGLE_TRIAL")],
            [Button.inline("👥 Manajemen Member", b"cmd_admin_status")],
            [Button.inline("🌍 On/Off Fitur Global", b"cmd_global_fitur"), Button.inline("👤 Izin Fitur User", b"cmd_admin_fitur")],
            [Button.inline("🔄 Restart System", b"cmd_admin_restart"), Button.inline("🛑 Shutdown", b"cmd_admin_shutdown")],
            [Button.inline("ℹ️ Bantuan", b"cmd_admin_help")]
        ]
        await bot.send_message(target_id, text, buttons=buttons)
    except Exception as e:
        print(f"❌ Gagal kirim dashboard admin: {e}")

# ===============================================
# MAIN FUNCTION
# ===============================================
async def main():
    was_offline_at_start = await wait_for_internet()

    print("🚀 Memulai Bot Manager...")
    
    try:
        bot.use_ipv6 = False 
        await bot.start(bot_token=BOT_TOKEN)
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        print(f"⚠️ Terdeteksi FILE SESI RUSAK ({e}). Resetting...")
        if os.path.exists("bot_session.session"): os.remove("bot_session.session")
        if os.path.exists("bot.session"): os.remove("bot.session")
        return
    except Exception as e:
        print(f"❌ Gagal Start Bot: {e}")
        return
    
    me = await bot.get_me()
    print(f"✅ Bot Manager Online: @{me.username}")

    # ===============================================
    # 🟢 DETEKSI RESTART & BROADCAST
    # ===============================================
    if os.path.exists("restart_status.txt"): # Legacy check
        os.remove("restart_status.txt") # Hapus file legacy jika ada
        
    if os.path.exists("RESTART_FLAG.json"):
        print("🔄 Mendeteksi pemulihan dari restart...")
        try:
            with open("RESTART_FLAG.json", "r") as f:
                data = json.load(f)
                chat_id = data.get("chat_id")
                msg_id = data.get("msg_id")
                admin_id = data.get("admin_id", ADMIN_ID)
            
            # Hapus pesan "Restarting..." yang lama agar bersih
            try:
                await bot.delete_messages(chat_id, msg_id)
            except: pass
            
            # Kirim Dashboard Admin Baru
            await send_admin_dashboard_startup(admin_id)
            
            # Broadcast ke semua member (bahwa sistem online + menu)
            await broadcast_system_online(is_restart=True)
            
            os.remove("RESTART_FLAG.json")
            
        except Exception as e:
            print(f"⚠️ Gagal memproses post-restart: {e}")
            if os.path.exists("RESTART_FLAG.json"): os.remove("RESTART_FLAG.json")
    
    else:
        # Start Manual (Bukan dari tombol restart)
        print("ℹ️ Start Manual Terdeteksi.")
        # Kirim dashboard ke admin saat start manual juga (opsional, tapi bagus untuk UX)
        await send_admin_dashboard_startup(ADMIN_ID)
        # Broadcast opsional (bisa dimatikan jika mengganggu saat dev)
        # await broadcast_system_online(is_restart=False) 

    # ===============================================
    # RESUME EXISTING USERBOTS & SPAM SESSIONS
    # ===============================================
    print("🔄 Mengecek userbot yang aktif di Database...")
    try:
        records = get_all_members_safe()
        count = 0
        
        for row in records:
            try:
                uid = str(row.get("User ID"))
                status = row.get("Status")
                sess = row.get("Session String")
                expired = row.get("Expired")
                
                is_active = False
                if status == "Approved" and sess and sess.strip():
                    try:
                        exp_date = datetime.strptime(expired, "%d-%m-%Y")
                        if datetime.now() < exp_date:
                            is_active = True
                    except ValueError: pass
                
                if is_active:
                    print(f"▶ Memulai userbot untuk {uid}...")
                    try:
                        client = TelegramClient(
                            StringSession(sess), 
                            API_ID, 
                            API_HASH,
                            connection_retries=3,
                            flood_sleep_threshold=60,
                            use_ipv6=False
                        )
                        await client.start()
                        ACTIVE_USERBOTS[int(uid)] = client
                        asyncio.create_task(start_userbot(client, int(uid)))
                        
                        # --- TAMBAHAN: RESUME SPAMBOT ---
                        await spambot.resume_spam_tasks(client)
                        
                        count += 1
                    
                    except (PersistentTimestampOutdatedError, SecurityError):
                        print(f"❌ Sesi Userbot {uid} RUSAK/REVOKED. Menunggu login ulang.")
                        # Jangan biarkan client aktif
                        try: await client.disconnect()
                        except: pass
                        
                    except Exception as e:
                        print(f"❌ Gagal connect userbot {uid}: {e}")

            except Exception as e:
                print(f"❌ Gagal memproses row: {e}")

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
        print("Bot dimatikan.")