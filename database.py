# database.py
import os
from datetime import datetime, timedelta
from config import spreadsheet

# Setup Worksheets
member_sheet = None
history_sheet = None

def ensure_sheets():
    global member_sheet, history_sheet
    try:
        names = [ws.title for ws in spreadsheet.worksheets()]
        
        # --- SETUP MEMBER SHEET ---
        if "Member" not in names:
            spreadsheet.add_worksheet(title="Member", rows="1000", cols="20")
            member = spreadsheet.worksheet("Member")
            # Header Standar (Kolom 8 = Permissions)
            member.append_row(["User ID", "Nama", "Email", "Status", "Expired", "Join Time", "Session String", "Permissions"])
        
        member_sheet = spreadsheet.worksheet("Member")
        
        # Cek Header
        current_header = member_sheet.row_values(1)
        # Header Standar yang Wajib Ada
        STANDARD_HEADER = ["User ID", "Nama", "Email", "Status", "Expired", "Join Time", "Session String", "Permissions"]
        
        # Fix Header jika belum lengkap (Update Kolom 8)
        if len(current_header) < 8:
            if member_sheet.col_count < 8: member_sheet.resize(cols=8)
            for col_num, val in enumerate(STANDARD_HEADER, 1):
                member_sheet.update_cell(1, col_num, val)

        # --- SETUP HISTORY SHEET ---
        if "History" not in names:
            spreadsheet.add_worksheet(title="History", rows="1000", cols="20")
            history = spreadsheet.worksheet("History")
            history.append_row(["User ID", "Months", "Total", "Status", "Timestamp"])
            
        history_sheet = spreadsheet.worksheet("History")

    except Exception as e:
        print(f"Error checking sheets: {e}")

# Jalankan saat import
ensure_sheets()

def get_all_members_safe():
    try:
        return member_sheet.get_all_records()
    except Exception as e:
        print(f"Gagal mengambil record: {e}")
        return []

def find_member_row(user_id_str):
    try:
        records = get_all_members_safe()
        for idx, row in enumerate(records, start=2): # Start 2 karena row 1 header
            if str(row.get("User ID")) == str(user_id_str):
                return idx, row
    except Exception as e:
        print(f"Error finding member: {e}")
    return None, None

def append_member(user_id, name="-", email="-", months=0):
    join_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    # Expired default 1 hari dulu (dummy), nanti diupdate saat approve/bayar
    expire = (datetime.now() + timedelta(days=1)).strftime("%d-%m-%Y")
    
    # --- STATUS DEFAULT 'Pending' AGAR TIDAK LANGSUNG AKTIF ---
    member_sheet.append_row([str(user_id), name, email, "Pending", expire, join_time, "", "ALL"])
    return expire

def update_member_expire(row_idx, new_expire_str):
    member_sheet.update_cell(row_idx, 5, new_expire_str)

def update_member_status(row_idx, new_status, reason=""):
    member_sheet.update_cell(row_idx, 4, new_status)
    print(f"✅ Database: User di row {row_idx} status -> {new_status} ({reason})")

def update_member_name_email(row_idx, name, email):
    member_sheet.update_cell(row_idx, 2, name)
    member_sheet.update_cell(row_idx, 3, email)

def delete_member(row_idx):
    try:
        member_sheet.delete_rows(row_idx)
        print(f"🗑️ Database: Menghapus baris {row_idx}")
        return True
    except Exception as e:
        print(f"❌ Gagal hapus member: {e}")
        return False

def save_session_to_sheet(user_id, session_string):
    idx, row = find_member_row(user_id)
    if idx:
        member_sheet.update_cell(idx, 7, session_string)

def log_history(user_id, months, total, status):
    ts = datetime.now().strftime("%d-%m-%Y %H:%M")
    history_sheet.append_row([str(user_id), str(months), str(total), status, ts])

# --- FUNGSI PERMISSION (YANG SEBELUMNYA HILANG) ---

def get_member_permissions(user_id):
    """Mengambil list izin fitur dari database (Kolom 8)"""
    idx, row = find_member_row(user_id)
    if not row: return ["ALL"]
    try:
        perms_str = row.get("Permissions")
        if not perms_str or perms_str == "": return ["ALL"]
        return perms_str.split(",")
    except:
        return ["ALL"]

def update_member_permissions(user_id, perm_list):
    """Menyimpan list izin ke database"""
    idx, row = find_member_row(user_id)
    if idx:
        perm_str = ",".join(perm_list)
        member_sheet.update_cell(idx, 8, perm_str)