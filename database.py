# bmcodexbot/database.py
import os
from datetime import datetime, timedelta
from config import spreadsheet

# Setup Worksheets
member_sheet = None
history_sheet = None

def ensure_sheets():
    global member_sheet, history_sheet
    
    # Skip if spreadsheet is not available
    if spreadsheet is None:
        print("⚠️ Skipping Google Sheets setup (no credentials)")
        return
    
    try:
        names = [ws.title for ws in spreadsheet.worksheets()]
        
        # --- SETUP MEMBER SHEET ---
        if "Member" not in names:
            spreadsheet.add_worksheet(title="Member", rows="1000", cols="20")
            member = spreadsheet.worksheet("Member")
            # Header Standar
            member.append_row(["User ID", "Nama", "Email", "Status", "Expired", "Join Time", "Session String", "Permissions"])
        
        member_sheet = spreadsheet.worksheet("Member")
        
        # Cek & Fix Header
        current_header = member_sheet.row_values(1)
        STANDARD_HEADER = ["User ID", "Nama", "Email", "Status", "Expired", "Join Time", "Session String", "Permissions"]
        
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

# ==========================================
# CORE READ FUNCTIONS
# ==========================================
def get_all_members_safe():
    if member_sheet is None:
        return []
    try:
        return member_sheet.get_all_records()
    except Exception as e:
        print(f"Gagal mengambil record: {e}")
        return []

def find_member_row(user_id_str):
    try:
        records = get_all_members_safe()
        # Start 2 karena row 1 adalah header di Google Sheets
        for idx, row in enumerate(records, start=2): 
            if str(row.get("User ID")) == str(user_id_str):
                return idx, row
    except Exception as e:
        print(f"Error finding member: {e}")
    return None, None

# ==========================================
# GENERIC UPDATE FUNCTION (YANG HILANG)
# ==========================================
def update_member_data(user_id, key, value):
    """
    Fungsi update fleksibel. Memetakan nama kolom ke index kolom di Sheets.
    """
    # Mapping Nama Kolom -> Nomor Kolom (1-based index)
    COL_MAP = {
        "User ID": 1,
        "Nama": 2,
        "Email": 3,
        "Status": 4,
        "Expired": 5,
        "Join Time": 6,
        "Session String": 7,
        "Permissions": 8
    }
    
    col_idx = COL_MAP.get(key)
    if not col_idx:
        print(f"❌ Key '{key}' tidak dikenali di database.")
        return False
        
    idx, row = find_member_row(user_id)
    if idx:
        try:
            # Handle list permissions agar disimpan sebagai string koma
            if key == "Permissions" and isinstance(value, list):
                value = ",".join(value)
                
            member_sheet.update_cell(idx, col_idx, value)
            print(f"✅ DB Update: Row {idx}, Col {col_idx} ({key}) -> {value}")
            return True
        except Exception as e:
            print(f"❌ Gagal update member data: {e}")
            return False
    return False

# ==========================================
# WRAPPER FUNCTIONS (UNTUK KOMPATIBILITAS)
# ==========================================
def update_member_expire(row_idx, new_expire_str):
    # row_idx disini bisa berupa user_id jika dipanggil dari modul baru
    # Kita cek tipe datanya
    if isinstance(row_idx, int) and row_idx < 10000: # Asumsi ID row sheet kecil
        member_sheet.update_cell(row_idx, 5, new_expire_str)
    else:
        update_member_data(row_idx, "Expired", new_expire_str)

def update_member_status(user_id_or_row, new_status, reason=""):
    if isinstance(user_id_or_row, int) and user_id_or_row < 10000:
        member_sheet.update_cell(user_id_or_row, 4, new_status)
    else:
        update_member_data(user_id_or_row, "Status", new_status)

def update_member_name_email(user_id_or_row, name, email):
    if isinstance(user_id_or_row, int) and user_id_or_row < 10000:
        member_sheet.update_cell(user_id_or_row, 2, name)
        member_sheet.update_cell(user_id_or_row, 3, email)
    else:
        update_member_data(user_id_or_row, "Nama", name)
        update_member_data(user_id_or_row, "Email", email)

def update_member_permissions(user_id, perm_list):
    return update_member_data(user_id, "Permissions", perm_list)

def get_member_permissions(user_id):
    idx, row = find_member_row(user_id)
    if not row: return ["ALL"]
    try:
        perms_str = str(row.get("Permissions", ""))
        if not perms_str or perms_str == "" or perms_str == "ALL": return ["ALL"]
        return perms_str.split(",")
    except:
        return ["ALL"]

# ==========================================
# ADD & DELETE
# ==========================================
def append_member(user_id, name="-", email="-", months=0):
    join_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    
    # Hitung Expired jika months > 0
    now = datetime.now()
    if months > 0:
        expire = (now + timedelta(days=30 * int(months))).strftime("%d-%m-%Y")
    else:
        # Default 1 hari (Trial)
        expire = (now + timedelta(days=1)).strftime("%d-%m-%Y")
    
    # Default Permissions: ALL
    row_data = [str(user_id), name, email, "Pending", expire, join_time, "", "ALL"]
    
    member_sheet.append_row(row_data)
    return expire

def delete_member(user_id):
    idx, row = find_member_row(user_id)
    if idx:
        try:
            member_sheet.delete_rows(idx)
            print(f"🗑️ Database: Menghapus baris {idx}")
            return True
        except Exception as e:
            print(f"❌ Gagal hapus member: {e}")
            return False
    return False

def save_session_to_sheet(user_id, session_string):
    return update_member_data(user_id, "Session String", session_string)

def log_history(user_id, months, total, status):
    ts = datetime.now().strftime("%d-%m-%Y %H:%M")
    history_sheet.append_row([str(user_id), str(months), str(total), status, ts])