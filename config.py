import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load environment
load_dotenv('config.env')

# Validasi Config
try:
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
    SHEET_ID = os.getenv("SHEET_ID", "")
    PRICE_PER_MONTH = int(os.getenv("PRICE_PER_MONTH", "20000"))
except (TypeError, ValueError) as e:
    print(f"Error loading config.env: {e}")
    sys.exit(1)

# Init Google Sheets
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

gclient = None
spreadsheet = None

# Check if credentials.json exists before trying to use Google Sheets
if os.path.exists("credentials.json"):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        gclient = gspread.authorize(creds)
        spreadsheet = gclient.open_by_key(SHEET_ID)
        print("✅ Google Sheets connected successfully")
    except Exception as e:
        print(f"⚠️ Warning: Gagal koneksi Google Sheets: {e}")
        print("⚠️ Bot will run without Google Sheets integration")
else:
    print("⚠️ Warning: credentials.json not found")
    print("⚠️ Bot will run without Google Sheets integration")
    print("⚠️ To enable Google Sheets, add your credentials.json file")

# Init Bot Manager Client
def _init_bot_client():
    if os.getenv("DISABLE_TELEGRAM_CLIENT") == "1":
        return None
    session_name = "bot_session"
    session_file = f"{session_name}.session"
    try:
        return TelegramClient(session_name, API_ID, API_HASH)
    except Exception as e:
        try:
            from sqlite3 import DatabaseError
            is_db_err = isinstance(e, DatabaseError) or ("file is not a database" in str(e))
        except:
            is_db_err = ("file is not a database" in str(e))
        if is_db_err:
            try:
                if os.path.exists(session_file):
                    os.remove(session_file)
            except Exception as e2:
                print(f"⚠️ Cannot remove invalid session file: {e2}")
            try:
                return TelegramClient(session_name, API_ID, API_HASH)
            except Exception:
                try:
                    return TelegramClient(StringSession(), API_ID, API_HASH)
                except Exception as e4:
                    print(f"❌ Failed to create fresh session: {e4}")
                    return None
        else:
            print(f"❌ Failed to init bot client: {e}")
            return None

bot = _init_bot_client()

# Helper Format Rupiah
def format_rp(n):
    return f"Rp {n:,}"
