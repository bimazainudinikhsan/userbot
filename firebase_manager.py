import firebase_admin
from firebase_admin import credentials, db
import os
import json

# ==========================================
# 1. KONEKSI KE FIREBASE
# ==========================================

CREDENTIAL_FILE = "credentials.json"
# URL disesuaikan dengan Project ID dari file credentials.json Anda
DATABASE_URL = "https://clash-of-clans-401b1-default-rtdb.firebaseio.com/"

def init_firebase():
    if not firebase_admin._apps:
        if os.path.exists(CREDENTIAL_FILE):
            try:
                cred = credentials.Certificate(CREDENTIAL_FILE)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': DATABASE_URL
                })
                print(f"[Firebase] Terhubung ke: {DATABASE_URL}")
            except Exception as e:
                print(f"[Firebase] Gagal: {e}")
        else:
            print(f"[Firebase] File {CREDENTIAL_FILE} tidak ditemukan.")

init_firebase()

# ==========================================
# 2. FUNGSI REMOTE APLIKASI (BARU)
# ==========================================

def get_all_apps():
    """Mengambil daftar nama aplikasi dari node 'aplikasi'."""
    try:
        # Node 'aplikasi' berisi mapping ID -> Nama App
        apps = db.reference('aplikasi').get()
        if apps:
            # Kita hanya butuh values-nya (nama app), karena itu yang jadi key node config
            return list(apps.values())
        return []
    except Exception as e:
        print(f"Error get_all_apps: {e}")
        return []

def get_app_config(app_name):
    """Mengambil konfigurasi spesifik aplikasi (PIN, Pesan, dll)."""
    try:
        # Mengambil root node aplikasi (misal: 'hot51')
        ref = db.reference(app_name)
        data = ref.get()
        if data:
            # Filter hanya data config penting
            return {
                "pin": data.get("kiosk_mode_pin", "-"),
                "text": data.get("keterangan", "-"),
                "admin_pass": data.get("password", "-"),
                "button_text": data.get("button_5_text", "BUKA")
            }
        return None
    except Exception as e:
        print(f"Error get_app_config: {e}")
        return None

def get_app_devices(app_name):
    """Mengambil daftar perangkat yang terhubung ke aplikasi."""
    try:
        ref = db.reference(f'{app_name}/perangkat')
        devices = ref.get()
        return devices if devices else {}
    except Exception as e:
        print(f"Error get_app_devices: {e}")
        return {}

def update_app_pin(app_name, new_pin):
    """Mengubah PIN Kiosk Mode."""
    try:
        db.reference(f'{app_name}/kiosk_mode_pin').set(int(new_pin))
        return True
    except:
        return False

def remote_device_action(app_name, device_id, action):
    """
    Mengontrol status device.
    Action: 'buka_paksa', 'mulai', 'lock'
    """
    try:
        # Mengubah status_keluar_mode_kios
        # Value yang umum di DB Anda: "mulai", "sukses" (atau string command lain yang dikenali app)
        db.reference(f'{app_name}/perangkat/{device_id}/status_keluar_mode_kios').set(action)
        return True
    except:
        return False

# ==========================================
# 3. FUNGSI USER MANAGER (YANG LAMA)
# ==========================================
# ... (Biarkan fungsi user manager yang lama tetap ada di bawah sini) ...
def get_user_data(user_id):
    return db.reference(f'users/{user_id}').get()