import asyncio
import platform
import logging
import os
import socket 
import json
from datetime import datetime

from telethon import TelegramClient, Button
from telethon.sessions import StringSession
from telethon.errors import AuthKeyError, SecurityError, RPCError

from config import bot, API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from bot_handlers.admin.system import read_manager_control, write_manager_control
from firebase_manager import get_session_lock, set_session_lock, clear_session_lock, should_block_by_lock
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
    if bot is None:
        print("❌ Bot client gagal diinisialisasi.")
        return
    
    # --- SINGLE INSTANCE LOCK ---
    LOCK_FILE = "bot_session.lock"
    disable_lock = False
    try:
        try:
            with open("manager_control.json", "r", encoding="utf-8") as cf:
                cfg = json.load(cf)
                disable_lock = bool(cfg.get("disable_lock", False))
        except:
            disable_lock = False
        if not disable_lock and os.path.exists(LOCK_FILE):
            print("⚠️ Lock file ditemukan. Bot sudah berjalan atau belum shutdown bersih.")
            try:
                await bot.send_message(ADMIN_ID, "⚠️ Bot tidak start karena lock file ada. Pastikan satu instance saja.")
            except:
                pass
            return
        if not disable_lock:
            with open(LOCK_FILE, "w") as f:
                f.write(str(os.getpid()))
        else:
            try:
                with open("session_usage.log", "a", encoding="utf-8") as lf:
                    lf.write(json.dumps({"ts": datetime.now().isoformat(), "kind": "manager_lock_disabled_start"}) + "\n")
            except:
                pass
    except:
        pass
    
    # --- SESSION CONSISTENCY CHECK & RECOVERY ---
    async def recover_manager_session(err: Exception):
        msg = str(err)
        session_path = "bot_session.session"
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = f"{session_path}.bak-{ts}"
        try:
            if os.path.exists(session_path):
                try:
                    os.rename(session_path, backup_path)
                except: 
                    pass
                try:
                    os.remove(session_path)
                except: 
                    pass
            # Retry start with fresh session
            try:
                await bot.disconnect()
            except:
                pass
            bot.use_ipv6 = False
            await bot.start(bot_token=BOT_TOKEN)
            # Log meta for IP consistency
            meta = {
                "hostname": socket.gethostname(),
                "local_ip": socket.gethostbyname(socket.gethostname()),
                "timestamp": ts,
                "note": "manager session regenerated"
            }
            try:
                with open("manager_session_meta.json", "w") as f:
                    json.dump(meta, f, indent=2)
            except:
                pass
            try:
                await bot.send_message(ADMIN_ID, "⚠️ Manager session dikembalikan (regenerated).")
            except:
                pass
            return True
        except Exception as e2:
            print(f"❌ Recovery gagal: {e2}")
            return False

    try:
        # Pre-check existing session; detect potential conflicts
        if os.path.exists("bot_session.session"):
            try:
                await bot.connect()
                await bot.disconnect()
            except (SecurityError, AuthKeyError, RPCError) as se:
                print(f"⚠️ Detected session issue: {se}")
                ok = await recover_manager_session(se)
                if not ok:
                    print("❌ Tidak bisa recovery session.")
                    return
        # Start normally
        bot.use_ipv6 = False 
        await bot.start(bot_token=BOT_TOKEN)
    except (SecurityError, AuthKeyError, RPCError) as e:
        print(f"⚠️ Session error saat start: {e}")
        ok = await recover_manager_session(e)
        if not ok:
            return
    except Exception as e:
        print(f"❌ Gagal Start Bot: {e}")
        return
    
    print(f"✅ Bot Manager Online: @{(await bot.get_me()).username}")

    try:
        if os.path.exists("RESTART_FLAG.json"):
            with open("RESTART_FLAG.json", "r", encoding="utf-8") as f:
                flag = json.load(f)
            started_at = flag.get("started_at")
            dur = 0
            try:
                if started_at:
                    dur = int((datetime.now() - datetime.fromisoformat(started_at)).total_seconds())
            except:
                dur = 0
            mc = read_manager_control()
            mc["system_status"] = "normal"
            mc["last_restart"] = {"started_at": started_at, "completed_at": datetime.now().isoformat(), "duration_sec": dur}
            write_manager_control(mc)
            try:
                await bot.send_message(ADMIN_ID, "✅ Sistem telah kembali normal", buttons=[[Button.inline("📋 Buka Dashboard Admin", b"menu_admin_dashboard")]])
            except:
                pass
            try:
                records = get_all_members_safe()
                for row in records:
                    uid = str(row.get("User ID"))
                    if uid.isdigit() and int(uid) != ADMIN_ID and row.get("Status") == "Approved":
                        await bot.send_message(int(uid), "✅ Bot telah kembali normal. Selamat menggunakan layanan kami", buttons=[[Button.inline("⬅️ Menu Member", b"menu_start")]])
            except:
                pass
            try:
                os.remove("RESTART_FLAG.json")
            except:
                pass
            try:
                with open("session_usage.log", "a", encoding="utf-8") as lf:
                    lf.write(json.dumps({"ts": datetime.now().isoformat(), "kind": "restart_complete", "duration_sec": dur}) + "\n")
            except:
                pass
    except:
        pass

    # --- RESUME USERBOTS ---
    print("🔄 Mengecek userbot yang aktif di Database...")
    if not os.path.exists("botsession"):
        os.makedirs("botsession")
    # Meta & log dirs
    if not os.path.exists("user_session_meta"):
        os.makedirs("user_session_meta")
    
    def get_local_ip():
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "0.0.0.0"
    
    def log_session_usage(kind, payload):
        try:
            entry = {"ts": datetime.now().isoformat(), "kind": kind, **payload}
            with open("session_usage.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except:
            pass

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

                # 3. IP Consistency Check per user (local meta)
                meta_path = os.path.join("user_session_meta", f"{uid}.json")
                current_ip = get_local_ip()
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r") as f:
                            meta = json.load(f)
                        last_ip = meta.get("local_ip")
                        if last_ip and last_ip != current_ip:
                            # Jangan paksa start untuk menghindari AUTH_KEY_DUPLICATED, beri tahu admin
                            try:
                                await bot.send_message(ADMIN_ID, f"⚠️ Session user `{uid}` di-host IP berbeda (last {last_ip} → now {current_ip}). Skip start.")
                            except:
                                pass
                            log_session_usage("user_skip_ip_mismatch", {"uid": uid, "last_ip": last_ip, "now_ip": current_ip})
                            continue
                    except:
                        pass

                # 3b. Remote session lock (Firebase) untuk mencegah multi-IP
                try:
                    lock = get_session_lock(uid)
                except:
                    lock = {}
                if should_block_by_lock(lock, current_ip):
                    try:
                        await bot.send_message(ADMIN_ID, f"⚠️ Remote lock aktif untuk user `{uid}` pada IP {lock.get('ip')}. Host sekarang {current_ip}. Skip start.")
                    except:
                        pass
                    log_session_usage("user_skip_remote_lock", {"uid": uid, "lock_ip": lock.get('ip'), "now_ip": current_ip})
                    continue

                # 4. Start Client
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
                            # tulis meta
                            try:
                                with open(meta_path, "w") as f:
                                    json.dump({"local_ip": current_ip, "ts": datetime.now().isoformat()}, f, indent=2)
                            except:
                                pass
                            try:
                                set_session_lock(uid, current_ip, socket.gethostname(), "started")
                            except:
                                pass
                            log_session_usage("user_started", {"uid": uid, "source": source, "ip": current_ip})
                        else:
                            await client.disconnect()
                    except Exception as e:
                        print(f"❌ Gagal connect {uid}: {e}")
                        # AUTH_KEY_DUPLICATED recovery for per-user sessions
                        msg = str(e)
                        if "AUTH_KEY_DUPLICATED" in msg or "authorization key" in msg:
                            try:
                                # remove local session to force re-login
                                local_path = f"botsession/{uid}.session"
                                if os.path.exists(local_path):
                                    try:
                                        os.remove(local_path)
                                    except:
                                        pass
                                try:
                                    clear_session_lock(uid)
                                except:
                                    pass
                                await bot.send_message(int(uid), "⚠️ Session Anda konflik IP. Silakan hubungkan ulang Userbot dari menu.")
                                await bot.send_message(ADMIN_ID, f"⚠️ Recovery dilakukan untuk session user `{uid}` (hapus file lokal, minta relog).")
                                log_session_usage("user_authkey_recovered", {"uid": uid})
                            except:
                                pass

        except Exception as e:
            pass 

    print(f"📊 Total Userbot Berjalan: {count}")
    try:
        await bot.run_until_disconnected()
    finally:
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
            # Lepas remote locks untuk semua user yang aktif
            try:
                for uid in list(ACTIVE_USERBOTS.keys()):
                    clear_session_lock(str(uid))
            except:
                pass
        except:
            pass

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
