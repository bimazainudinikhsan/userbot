# bmcodexbot/bot_handlers/remote/state.py

# Variable global untuk menyimpan state saat user mengedit PIN
# Format: {user_id: {"app": "nama_app", "action": "edit_pin"}}
REMOTE_STATE = {}