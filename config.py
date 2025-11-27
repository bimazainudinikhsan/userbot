import os
import sys
from telethon import TelegramClient
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load environment
load_dotenv('config.env')

# Validasi Config
try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
    SHEET_ID = os.getenv("SHEET_ID")
    PRICE_PER_MONTH = int(os.getenv("PRICE_PER_MONTH", "20000"))
except (TypeError, ValueError) as e:
    print(f"Error loading config.env: {e}")
    sys.exit(1)

# Init Google Sheets
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    gclient = gspread.authorize(creds)
    spreadsheet = gclient.open_by_key(SHEET_ID)
except Exception as e:
    print(f"Gagal koneksi Google Sheets: {e}")
    sys.exit(1)

# Init Bot Manager Client
bot = TelegramClient("bot_session", API_ID, API_HASH)

# Helper Format Rupiah
def format_rp(n):
    return f"Rp {n:,}"