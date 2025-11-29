# BmCodex Telegram Userbot Manager

## Overview
This is a Telegram userbot management system built with Python and Telethon. The bot allows administrators to manage multiple Telegram userbots, providing features like auto-reply, spam detection, invoice generation, and remote device management.

## Project Status
- ✅ Successfully imported and configured for Replit environment
- ✅ All dependencies installed
- ✅ Bot is running and operational
- ⚠️ Running without Google Sheets integration (requires credentials.json)
- ⚠️ Running without Firebase integration (requires credentials.json)

## Architecture

### Core Components
- **Main Bot Manager** (`main.py`): Orchestrates userbot instances and handles bot startup
- **Config Management** (`config.py`): Manages environment variables and API credentials
- **Database Layer** (`database.py`): Handles Google Sheets integration for user data
- **State Management** (`state.py`): Tracks active userbots and feature flags

### Handler Modules
Located in `bot_handlers/`:
- `admin/`: Admin dashboard, subscription management, user management
- `remote/`: Remote device and app management
- `auth.py`: User authentication and session management
- `payment.py`: Payment processing and subscription handling
- `nav.py`: Navigation and menu handlers

### Feature Modules
Located in `modules/`:
- `autoreply.py`: Automatic message replies
- `auto_spam.py`: Spam detection and prevention
- `faktur.py`: Invoice/receipt generation using ReportLab
- `unread.py`: Unread message management
- `spambot.py`: Anti-spam bot features

## Configuration

### Required Environment Variables
Set in `config.env`:
- `API_ID`: Telegram API ID (currently configured)
- `API_HASH`: Telegram API Hash (currently configured)
- `BOT_TOKEN`: Telegram Bot Token (currently configured)
- `ADMIN_ID`: Administrator user ID (currently configured)
- `SHEET_ID`: Google Sheets ID for database
- `PRICE_PER_MONTH`: Monthly subscription price (default: 20000)

### Optional Integrations

#### Google Sheets Integration
To enable Google Sheets database:
1. Create a Google Cloud service account
2. Download the credentials JSON file
3. Upload as `credentials.json` to the project root
4. The bot will automatically detect and use it on next restart

#### Firebase Integration
To enable Firebase remote device management:
1. Create a Firebase project
2. Download the credentials JSON file
3. Upload as `credentials.json` to the project root
4. Update `firebase_manager.py` with your database URL

## Running the Project

The bot runs automatically via the "Run Telegram Bot" workflow. It:
- Connects to Telegram using the configured bot token
- Loads active userbots from the database
- Starts all approved userbot sessions
- Listens for commands from users and admins

### Workflow
- **Name**: Run Telegram Bot
- **Command**: `python main.py`
- **Type**: Console application (always running)

## Recent Changes (2025-11-29)

### Setup for Replit Environment
1. Installed Python 3.11 and all required dependencies:
   - telethon (Telegram API)
   - gspread, oauth2client (Google Sheets)
   - reportlab, fpdf, pillow (PDF/invoice generation)
   - firebase-admin (Firebase integration)
   - python-dotenv (environment variables)

2. Modified `config.py`:
   - Added graceful handling for missing credentials.json
   - Bot now runs without Google Sheets if credentials are unavailable
   - Added default values for environment variables to prevent crashes

3. Modified `database.py`:
   - Added null checks for spreadsheet object
   - Functions return empty data when Google Sheets is unavailable
   - Bot remains functional without database integration

4. Added comprehensive `.gitignore`:
   - Python cache files and bytecode
   - Session files and sensitive credentials
   - Temporary and storage files

## Dependencies

### Python Packages (requirements.txt)
- `telethon`: Telegram client library
- `gspread`, `oauth2client`: Google Sheets integration
- `requests`, `asyncio`: HTTP and async operations
- `reportlab`, `fpdf`, `pillow`: PDF and image processing
- `firebase-admin`: Firebase integration
- `python-dotenv`: Environment variable management

## File Structure
```
BmCodex/
├── main.py                 # Entry point
├── config.py               # Configuration and credentials
├── database.py             # Google Sheets database layer
├── state.py                # State management
├── bot_handlers/           # Bot command handlers
│   ├── admin/              # Admin-only features
│   └── remote/             # Remote device management
├── modules/                # Feature modules
├── botsession/             # Session storage
├── storage/                # Media and file storage
└── requirements.txt        # Python dependencies
```

## User Preferences
- No specific preferences recorded yet

## Notes
- The bot is designed for Heroku deployment but has been adapted for Replit
- Session files are stored locally in the `botsession/` directory
- The bot uses StringSession for userbot authentication
- Admin commands are restricted to the user specified in ADMIN_ID
