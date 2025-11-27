import firebase_admin
from firebase_admin import credentials, db
import os
import json
import sys

# w==========================================
# 1. KONEKSI KE FIREBASE
# ==========================================

CREDENTIAL_FILE = "credentials.json"

# URL Database sesuai permintaan Anda
DATABASE_URL = "https://clash-of-clans-401b1.firebaseio.com/"

def init_firebase():
    if not firebase_admin._apps:
        if os.path.exists(CREDENTIAL_FILE):
            try:
                cred = credentials.Certificate(CREDENTIAL_FILE)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': DATABASE_URL,
                    'httpTimeout': 30 
                })
                print(f"[Firebase] Credential dimuat. URL: {DATABASE_URL}")
                
                # --- TES KONEKSI NYATA ---
                try:
                    print("[Firebase] Mencoba menghubungi server database...")
                    # Tes baca root path ringan
                    db.reference().child("test_connection").get() 
                    print("✅ [Firebase] KONEKSI SUKSES! Bisa membaca data.")
                except Exception as e:
                    print(f"❌ [Firebase] GAGAL KONEKSI INTERNET/SERVER!")
                    print(f"   Error Detail: {e}")
                    print(f"   Saran: Cek koneksi internet VPS Anda. Pastikan bisa ping google.com")

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