# bmcodexbot/aktif_fitur.py
import logging
from telethon import events
from telethon.errors import PersistentTimestampOutdatedError, SecurityError 

# Import Database & State
from database import find_member_row, get_member_permissions, update_member_status
from state import USER_PERMISSIONS, GLOBAL_FEATURE_FLAGS

# Import Modules Baru (Tambahkan unread)
from modules import faktur, general, unread, auto_spam, spambot, spambotpremium, spamai

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - USERBOT - %(levelname)s - %(message)s')

# ==================================================================
# LOGIKA UTAMA (LOADER)
# ==================================================================

async def check_userbot_status(client, user_id, event):
    """Fungsi Helper untuk mengecek apakah membership user masih valid"""
    idx, row = find_member_row(user_id)
    if not row:
        try: await client.disconnect() 
        except: pass
        return False
        
    status = row.get("Status", "Pending")
    if status != "Approved":
        await event.reply(f"❌ **AKSES DITOLAK**: Status akun {status}.")
        try: await client.disconnect()
        except: pass
        return False
    return True

async def start_userbot(client, user_id):
    """Fungsi utama untuk menjalankan userbot"""
    
    # 1. Load Permission dari Database
    perms = get_member_permissions(user_id)
    USER_PERMISSIONS[user_id] = perms
    print(f"[USERBOT {user_id}] Loaded Permissions: {perms}")

    # 2. Fungsi Helper Cek Izin (Closure)
    def is_allowed(feature):
        # --- CEK GLOBAL FEATURE FLAG ---
        if GLOBAL_FEATURE_FLAGS.get(feature) is False:
            return False

        # --- CEK USER PERMISSION ---
        user_perms = USER_PERMISSIONS.get(user_id, ["ALL"])
        if "ALL" in user_perms: return True
        if feature in user_perms: return True
        return False

    try:
        me = await client.get_me()
        print(f"[USERBOT {user_id}] ✅ Aktif sebagai: {me.first_name}")

        # 3. Dictionary untuk menampung command help dari semua modul
        help_dict = {}

        # 4. Register Modules
        await faktur.register(client, user_id, is_allowed, check_userbot_status, help_dict)
        await auto_spam.register(client, user_id, is_allowed, check_userbot_status, help_dict)
        await general.register(client, user_id, is_allowed, check_userbot_status, help_dict)
        await spambot.register(client, user_id, is_allowed, check_userbot_status, help_dict)
        await spambotpremium.register(client, user_id, is_allowed, check_userbot_status, help_dict)
        await spamai.register(client, user_id, is_allowed, check_userbot_status, help_dict)
        # Register modul Unread baru
        await unread.register(client, user_id, is_allowed, check_userbot_status, help_dict)

        # 5. Jalankan Client (Looping Utama)
        await client.run_until_disconnected()

    except (PersistentTimestampOutdatedError, SecurityError):
        # PENANGANAN ERROR KHUSUS: SESI RUSAK
        print(f"[USERBOT {user_id}] ❌ CRITICAL: Sesi Rusak/Expired/Logout dari device lain.")
        
        # Coba beri tahu user jika masih bisa (pakai bot manager)
        try: await client.disconnect()
        except: pass

    except Exception as e:
        print(f"[USERBOT {user_id}] Stopped: {e}")
