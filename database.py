# bmcodexbot/database.py
import os
import time
from datetime import datetime, timedelta
from config import spreadsheet

# Setup Worksheets
member_sheet = None
history_sheet = None
_CACHE_MEMBERS = {"data": None, "ts": 0}
_CACHE_TTL_SEC = 30

def _db_log(kind, payload=None):
    try:
        entry = {"ts": datetime.now().isoformat(), "kind": kind}
        if payload:
            entry.update(payload)
        with open("db_usage.log", "a", encoding="utf-8") as f:
            f.write(__import__("json").dumps(entry) + "\n")
    except:
        pass

def _cache_get_members():
    try:
        now = time.time()
        if _CACHE_MEMBERS["data"] is not None and (now - _CACHE_MEMBERS["ts"]) < _CACHE_TTL_SEC:
            return _CACHE_MEMBERS["data"]
    except:
        pass
    return None

def _cache_set_members(data):
    try:
        _CACHE_MEMBERS["data"] = data
        _CACHE_MEMBERS["ts"] = time.time()
    except:
        pass

def _cache_invalidate_members():
    _CACHE_MEMBERS["data"] = None
    _CACHE_MEMBERS["ts"] = 0

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
        cached = _cache_get_members()
        if cached is not None:
            return cached
        data = member_sheet.get_all_records()
        _cache_set_members(data)
        _db_log("read_members", {"count": len(data)})
        return data
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
    if member_sheet is None:
        print(f"⚠️ Cannot update member data: Google Sheets not available")
        return False
    
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
            if not _validate_value(key, value):
                _db_log("validate_fail", {"user_id": str(user_id), "key": key, "value": str(value)})
                return False
            member_sheet.update_cell(idx, col_idx, value)
            print(f"✅ DB Update: Row {idx}, Col {col_idx} ({key}) -> {value}")
            _cache_invalidate_members()
            _db_log("update_member", {"user_id": str(user_id), "key": key})
            return True
        except Exception as e:
            print(f"❌ Gagal update member data: {e}")
            return False
    return False

def _validate_value(key, value):
    try:
        if key == "User ID":
            s = str(value)
            return s.isdigit()
        if key == "Nama":
            return isinstance(value, str) and len(value) <= 100
        if key == "Email":
            v = str(value)
            return v == "-" or ("@" in v and len(v) <= 100)
        if key == "Status":
            return str(value) in ["Approved", "Pending", "Rejected"]
        if key == "Expired":
            try:
                datetime.strptime(str(value), "%d-%m-%Y")
                return True
            except:
                return False
        if key == "Join Time":
            return isinstance(value, str) and len(value) <= 30
        if key == "Session String":
            return isinstance(value, str) and len(value) <= 4096
        if key == "Permissions":
            if isinstance(value, list):
                return all(isinstance(x, str) and len(x) <= 50 for x in value)
            if isinstance(value, str):
                return len(value) <= 200
            return False
        return True
    except:
        return False

# ==========================================
# WRAPPER FUNCTIONS (UNTUK KOMPATIBILITAS)
# ==========================================
def update_member_expire(row_idx, new_expire_str):
    if member_sheet is None:
        print(f"⚠️ Cannot update member expire: Google Sheets not available")
        return False
    # row_idx disini bisa berupa user_id jika dipanggil dari modul baru
    # Kita cek tipe datanya
    try:
        if isinstance(row_idx, int) and row_idx < 10000: # Asumsi ID row sheet kecil
            if not _validate_value("Expired", new_expire_str):
                return False
            member_sheet.update_cell(row_idx, 5, new_expire_str)
            _cache_invalidate_members()
            _db_log("update_expire_row", {"row": row_idx})
            return True
        else:
            return update_member_data(row_idx, "Expired", new_expire_str)
    except Exception as e:
        print(f"❌ Failed to update member expire: {e}")
        return False

def update_member_status(user_id_or_row, new_status, reason=""):
    if member_sheet is None:
        print(f"⚠️ Cannot update member status: Google Sheets not available")
        return False
    try:
        if isinstance(user_id_or_row, int) and user_id_or_row < 10000:
            if not _validate_value("Status", new_status):
                return False
            member_sheet.update_cell(user_id_or_row, 4, new_status)
            _cache_invalidate_members()
            _db_log("update_status_row", {"row": user_id_or_row})
            return True
        else:
            return update_member_data(user_id_or_row, "Status", new_status)
    except Exception as e:
        print(f"❌ Failed to update member status: {e}")
        return False

def update_member_name_email(user_id_or_row, name, email):
    if member_sheet is None:
        print(f"⚠️ Cannot update member name/email: Google Sheets not available")
        return False
    try:
        if isinstance(user_id_or_row, int) and user_id_or_row < 10000:
            if not _validate_value("Nama", name):
                return False
            if not _validate_value("Email", email):
                return False
            member_sheet.update_cell(user_id_or_row, 2, name)
            member_sheet.update_cell(user_id_or_row, 3, email)
            _cache_invalidate_members()
            _db_log("update_name_email_row", {"row": user_id_or_row})
            return True
        else:
            result1 = update_member_data(user_id_or_row, "Nama", name)
            result2 = update_member_data(user_id_or_row, "Email", email)
            return result1 and result2
    except Exception as e:
        print(f"❌ Failed to update member name/email: {e}")
        return False

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
    if member_sheet is None:
        print(f"⚠️ Cannot append member: Google Sheets not available")
        # Return a default expiry date so callers don't break
        now = datetime.now()
        if months > 0:
            expire = (now + timedelta(days=30 * int(months))).strftime("%d-%m-%Y")
        else:
            expire = (now + timedelta(days=1)).strftime("%d-%m-%Y")
        return expire
    
    try:
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
        if not (_validate_value("User ID", row_data[0]) and _validate_value("Nama", row_data[1]) and _validate_value("Email", row_data[2]) and _validate_value("Status", row_data[3]) and _validate_value("Expired", row_data[4])):
            return expire
        member_sheet.append_row(row_data)
        _cache_invalidate_members()
        _db_log("append_member", {"user_id": str(user_id)})
        return expire
    except Exception as e:
        print(f"❌ Failed to append member: {e}")
        # Return expiry anyway
        now = datetime.now()
        if months > 0:
            return (now + timedelta(days=30 * int(months))).strftime("%d-%m-%Y")
        else:
            return (now + timedelta(days=1)).strftime("%d-%m-%Y")

def delete_member(user_id):
    if member_sheet is None:
        print(f"⚠️ Cannot delete member: Google Sheets not available")
        return False
    idx, row = find_member_row(user_id)
    if idx:
        try:
            member_sheet.delete_rows(idx)
            print(f"🗑️ Database: Menghapus baris {idx}")
            _cache_invalidate_members()
            _db_log("delete_member_row", {"user_id": str(user_id), "row": idx})
            return True
        except Exception as e:
            print(f"❌ Gagal hapus member: {e}")
            return False
    return False

def save_session_to_sheet(user_id, session_string):
    return update_member_data(user_id, "Session String", session_string)

def log_history(user_id, months, total, status):
    if history_sheet is None:
        print(f"⚠️ Cannot log history: Google Sheets not available")
        return False
    ts = datetime.now().strftime("%d-%m-%Y %H:%M")
    history_sheet.append_row([str(user_id), str(months), str(total), status, ts])
    _db_log("log_history", {"user_id": str(user_id), "months": months, "total": total, "status": status})
    return True

def get_member_by_id(user_id):
    try:
        all_rows = get_all_members_safe()
        for row in all_rows:
            if str(row.get("User ID")) == str(user_id):
                return row
        return None
    except:
        return None

def delete_history_by_user(user_id):
    if history_sheet is None:
        print(f"⚠️ Cannot delete history: Google Sheets not available")
        return False
    try:
        values = history_sheet.get_all_values()
        rows_to_delete = []
        for idx, row in enumerate(values[1:], start=2):
            try:
                if str(row[0]) == str(user_id):
                    rows_to_delete.append(idx)
            except:
                pass
        for r in sorted(rows_to_delete, reverse=True):
            try:
                history_sheet.delete_rows(r)
            except Exception as e:
                print(f"❌ Gagal hapus history row {r}: {e}")
        _db_log("delete_history", {"user_id": str(user_id), "deleted_rows": len(rows_to_delete)})
        return True
    except Exception as e:
        print(f"❌ Gagal baca history: {e}")
        return False
