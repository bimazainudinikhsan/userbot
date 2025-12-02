# 📋 EXACT CHANGES MADE

## File 1: database.py

### Added (Lines 1-13)
```python
import os
import time
import asyncio  # Added
from datetime import datetime, timedelta
from config import spreadsheet

# Setup Worksheets
member_sheet = None
history_sheet = None
_CACHE_MEMBERS = {"data": None, "ts": 0}
_CACHE_TTL_SEC = 30
_MAX_RETRIES = 3  # Added
_RETRY_DELAY = 1  # seconds  # Added
```

### Added (Lines 25-54)
```python
def _retry_gspread_op(operation, *args, **kwargs):
    """
    Wrapper untuk retry operasi gspread dengan exponential backoff.
    Mengatasi 'database is locked' dan timeout errors.
    """
    last_exception = None
    for attempt in range(_MAX_RETRIES):
        try:
            result = operation(*args, **kwargs)
            if attempt > 0:
                _db_log("gspread_retry_success", {"attempt": attempt + 1})
            return result
        except Exception as e:
            last_exception = e
            error_msg = str(e).lower()
            
            # Jika error database locked atau timeout, retry
            if "locked" in error_msg or "timeout" in error_msg or "connection" in error_msg:
                wait_time = _RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                if attempt < _MAX_RETRIES - 1:
                    _db_log("gspread_retry", {"attempt": attempt + 1, "error": error_msg, "wait_sec": wait_time})
                    time.sleep(wait_time)
                continue
            else:
                # Untuk error lain, raise langsung
                raise
    
    # Jika semua retry gagal
    _db_log("gspread_max_retries", {"error": str(last_exception), "max_attempts": _MAX_RETRIES})
    raise last_exception
```

### Updated `get_all_members_safe()` function
**BEFORE:**
```python
def get_all_members_safe():
    try:
        return member_sheet.get_all_records()
    except Exception as e:
        print(f"Gagal mengambil record: {e}")
        return []
```

**AFTER:**
```python
def get_all_members_safe():
    """
    Mengambil semua record dari Member sheet dengan caching dan retry logic.
    Ini adalah operasi critical saat startup, jadi perlu robust error handling.
    """
    if member_sheet is None:
        return []
    try:
        # 1. Check cache first
        cached = _cache_get_members()
        if cached is not None:
            return cached
        
        # 2. Fetch dari Sheets dengan retry
        def fetch_records():
            return member_sheet.get_all_records()
        
        data = _retry_gspread_op(fetch_records)
        
        # 3. Cache result
        _cache_set_members(data)
        _db_log("read_members", {"count": len(data)})
        return data
    except Exception as e:
        error_msg = str(e)
        _db_log("read_members_failed", {"error": error_msg})
        print(f"❌ Gagal mengambil record: {error_msg}")
        
        # Return cached data jika ada, walaupun expired
        if _CACHE_MEMBERS.get("data"):
            print(f"⚠️ Menggunakan cache lama (possibly stale)")
            return _CACHE_MEMBERS["data"]
        return []
```

### Updated `ensure_sheets()` function
**BEFORE:**
```python
def ensure_sheets():
    global member_sheet, history_sheet
    if spreadsheet is None:
        print("⚠️ Skipping Google Sheets setup (no credentials)")
        return
    
    try:
        names = [ws.title for ws in spreadsheet.worksheets()]
        # ... setup code ...
    except Exception as e:
        print(f"Error checking sheets: {e}")
```

**AFTER:**
```python
def ensure_sheets():
    global member_sheet, history_sheet
    if spreadsheet is None:
        print("⚠️ Skipping Google Sheets setup (no credentials)")
        return
    
    def _setup():
        # Wrapped in function for retry
        names = [ws.title for ws in spreadsheet.worksheets()]
        # ... setup code ...
        return mem_sheet, hist_sheet
    
    try:
        member_sheet, history_sheet = _retry_gspread_op(_setup)
        print("✅ Database sheets ready (Member & History)")
    except Exception as e:
        error_msg = str(e)
        print(f"⚠️ Error setting up sheets (will retry on first access): {error_msg}")
        _db_log("ensure_sheets_failed", {"error": error_msg})
```

---

## File 2: bot_handlers/admin/system.py

### Added (Line 9)
```python
# Track the auto_update_watcher task untuk proper cleanup
AUTO_UPDATE_TASK = None
```

### Updated `auto_update_watcher()` function
**BEFORE:**
```python
async def auto_update_watcher():
    TRIGGER_PATH = "/home/bmcodex/userbot/restart_trigger.txt"
    while True:
        if os.path.exists(TRIGGER_PATH):
            try: os.remove(TRIGGER_PATH) 
            except: pass
            await execute_restart_sequence(trigger_event=None)
        try:
            # ... monitoring code ...
        except:
            pass
        await asyncio.sleep(5) 

try:
    bot.loop.create_task(auto_update_watcher())
except Exception as e: print(f"❌ Watcher Error: {e}")
```

**AFTER:**
```python
async def auto_update_watcher():
    """
    Background task untuk monitoring file trigger restart dan status maintenance.
    Task ini akan di-cancel dengan benar saat shutdown.
    """
    TRIGGER_PATH = "/home/bmcodex/userbot/restart_trigger.txt"
    try:
        while True:
            try:
                # ... monitoring code ...
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                # Cleanup saat task di-cancel
                print("[System] Auto update watcher cancelled (graceful shutdown)")
                raise
            except Exception as e:
                print(f"[System] Watcher error: {e}")
                await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass  # Task is being cancelled, exit gracefully
    finally:
        print("[System] Auto update watcher stopped")

# Initialize auto_update_watcher task dengan proper management
def init_auto_update_watcher():
    global AUTO_UPDATE_TASK
    try:
        AUTO_UPDATE_TASK = bot.loop.create_task(auto_update_watcher())
        print("✅ Auto update watcher started")
    except Exception as e:
        print(f"❌ Watcher Error: {e}")

# Add cleanup handler saat bot disconnect
@bot.on(events.Raw)
async def on_bot_disconnect(update):
    # Cleanup when bot is about to disconnect
    if AUTO_UPDATE_TASK and not AUTO_UPDATE_TASK.done():
        AUTO_UPDATE_TASK.cancel()
        try:
            await AUTO_UPDATE_TASK
        except asyncio.CancelledError:
            pass

# Initialization moved to main.py (after bot.start())
# NOTE: Do NOT initialize here - event loop not ready yet!
# Will be initialized in main.py after bot.start()
```

### Updated `cb_shutdown_execute()` function
**BEFORE:**
```python
@bot.on(events.CallbackQuery(pattern=b"confirm_shutdown"))
async def cb_shutdown_execute(event):
    if event.sender_id != ADMIN_ID: return
    await event.edit("🔴 Bot Offline.")
    # ... rest of code ...
```

**AFTER:**
```python
@bot.on(events.CallbackQuery(pattern=b"confirm_shutdown"))
async def cb_shutdown_execute(event):
    global AUTO_UPDATE_TASK
    if event.sender_id != ADMIN_ID: return
    
    # Cancel auto_update_watcher task
    if AUTO_UPDATE_TASK and not AUTO_UPDATE_TASK.done():
        AUTO_UPDATE_TASK.cancel()
        try:
            await AUTO_UPDATE_TASK
        except asyncio.CancelledError:
            pass
    
    await event.edit("🔴 Bot Offline.")
    # ... rest of code (same as before) ...
```

---

## File 3: main.py

### Added (After line 147: `print(f"✅ Bot Manager Online: @{(await bot.get_me()).username}")`)
```python
    # Initialize auto_update_watcher now that event loop is running
    try:
        from bot_handlers.admin.system import init_auto_update_watcher
        init_auto_update_watcher()
    except Exception as e:
        print(f"⚠️ Auto update watcher init error: {e}")
```

---

## Summary Statistics

| File | Added Lines | Removed Lines | Net Change |
|------|-------------|---------------|-----------|
| database.py | ~95 | 15 | +80 |
| bot_handlers/admin/system.py | ~65 | 3 | +62 |
| main.py | 5 | 0 | +5 |
| **TOTAL** | **165** | **18** | **+147** |

---

## Key Function Additions

### New Functions Added
- `_retry_gspread_op()` - Retry wrapper with exponential backoff
- `init_auto_update_watcher()` - Task initialization function
- `on_bot_disconnect()` - Cleanup handler for task

### Functions Modified (Logic Enhanced)
- `get_all_members_safe()` - Added retry and cache fallback
- `ensure_sheets()` - Added retry logic
- `auto_update_watcher()` - Added proper exception handling
- `cb_shutdown_execute()` - Added task cancellation

### Global Variables Added
- `AUTO_UPDATE_TASK` - Tracks the background task

---

## Imports Added

**database.py:**
- `import asyncio` (for future-proofing)

**main.py:**
- `from bot_handlers.admin.system import init_auto_update_watcher` (local import)

---

## NO Removed Functions

All existing functions remain intact. Only enhancements and additions.

---

## NO Removed Imports

All existing imports remain. Only additions where needed.

---

## NO API Changes

All public function signatures unchanged. All changes are internal implementation details.

---

## Configuration Values Added

**database.py:**
```python
_MAX_RETRIES = 3         # Number of retry attempts
_RETRY_DELAY = 1         # Base delay in seconds (exponential)
_CACHE_TTL_SEC = 30      # Cache validity (already existed)
```

These can be adjusted in the future if needed:
- Increase `_MAX_RETRIES` for more retries
- Increase `_RETRY_DELAY` for longer waits between retries
