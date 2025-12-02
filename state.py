# state.py

# Menyimpan status Login Userbot
# user_id -> {step, client, phone, phone_code_hash}
LOGIN_STATE = {}

# Menyimpan Userbot yang sedang aktif
# user_id -> client_object
ACTIVE_USERBOTS = {}

# Menyimpan Transaksi Pembayaran Pending
# tx_id -> {user_id, months, total, timestamp, photo_path, name?, email?}
pending_tx = {}

# Mapping User ID ke TX ID yang sedang berlangsung
user_tx_map = {}

# Set User ID yang sedang ditunggu upload bukti transfernya
awaiting_photo = set()

# Temporary buffers untuk input Nama & Email saat pendaftaran
WAIT_NAME = {}
WAIT_EMAIL = {}
WAIT_PAYMENT_PROOF = {}

# --- STATE BARU UNTUK ADMIN & PERMISSION ---

# Menyimpan konfigurasi global (misal: Free Trial ON/OFF)
GLOBAL_CONFIG = {
    "free_trial": False
}

# Menyimpan Status ON/OFF Fitur Global
GLOBAL_FEATURE_FLAGS = {}

# Menyimpan Izin/Permission Fitur per User ID
USER_PERMISSIONS = {}

# State Admin saat sedang mengedit fitur user
EDIT_PERMISSION_STATE = {}

# State Admin saat melakukan aksi ke member
ADMIN_ACTION_STATE = {}

# Menyimpan komentar reject pembayaran sementara
awaiting_reject_comment = {}

# --- STATE LIVE CHAT ---
LIVE_CHAT_SESSIONS = {}
CHAT_QUEUE = []

# --- STATE SPAMBOT (RUNTIME ONLY - Data persisten ada di json) ---
# Tidak perlu simpan sesi disini, karena sudah di-handle json.
# Tapi mungkin perlu melacak Task object untuk pembatalan.
# (Variable ACTIVE_SPAM_TASKS ada di modul spambot.py)