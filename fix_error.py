import os

# Jalur file yang wajib ada
path = os.path.join("bot_handlers", "remote", "__init__.py")

# Cek apakah folder 'bot_handlers/remote' ada
if os.path.exists(os.path.dirname(path)):
    # Buat file __init__.py jika belum ada
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("") # File kosong cukup
        print(f"✅ SUKSES: File {path} berhasil dibuat.")
    else:
        print(f"ℹ️ INFO: File {path} sudah ada.")
else:
    print("❌ ERROR: Folder 'bot_handlers/remote' tidak ditemukan. Pastikan Anda menjalankan script ini dari folder utama bot.")