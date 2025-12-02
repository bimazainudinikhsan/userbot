# Bot Startup Fixes Summary

## Problems Fixed

### 1. **Database Locked Error** ❌ → ✅
**Error:** `❌ Gagal Start Bot: database is locked`

**Root Cause:** 
- Google Sheets API timeout or concurrent access lock
- No retry mechanism for transient failures
- Single attempt would fail entire startup

**Solution Implemented:**
- Added `_retry_gspread_op()` wrapper function with exponential backoff
- Retry up to 3 times with increasing delays: 1s, 2s, 4s
- Graceful fallback to stale cache if all retries fail (at least bot can start)
- Comprehensive error logging in `db_usage.log`
- Updated `get_all_members_safe()` to use retry logic
- Updated `ensure_sheets()` to use retry logic for initialization

**Key Changes in `database.py`:**
```python
# New constants
_MAX_RETRIES = 3
_RETRY_DELAY = 1  # seconds

# New retry wrapper
def _retry_gspread_op(operation, *args, **kwargs):
    # Exponential backoff for 'locked', 'timeout', 'connection' errors
    # Logs all attempts and successes
    # Returns result or raises exception after max retries

# Updated get_all_members_safe()
# - Uses cache first (30-second TTL)
# - Retries gspread operation
# - Falls back to stale cache if all retries fail
```

---

### 2. **Async Task Cleanup (auto_update_watcher)** ❌ → ✅
**Errors:** 
- `ERROR:asyncio:Task was destroyed but it is pending!`
- `RuntimeWarning: coroutine 'auto_update_watcher' was never awaited`

**Root Cause:**
- Task created with `bot.loop.create_task()` but never stored or managed
- Task not cancelled on bot shutdown
- Improper exception handling in coroutine

**Solution Implemented:**
- Added global `AUTO_UPDATE_TASK` variable to track the task
- Implemented `init_auto_update_watcher()` function for proper initialization
- Added exception handling (try/except/finally) in `auto_update_watcher()` coroutine
- Added cleanup handler `on_bot_disconnect()` to cancel task gracefully
- Updated shutdown handler to properly cancel task before disconnect

**Key Changes in `bot_handlers/admin/system.py`:**
```python
# New global variable
AUTO_UPDATE_TASK = None

# Updated auto_update_watcher() with proper exception handling
async def auto_update_watcher():
    try:
        while True:
            try:
                # ... main loop ...
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                print("[System] Auto update watcher cancelled (graceful shutdown)")
                raise
            except Exception as e:
                print(f"[System] Watcher error: {e}")
    except asyncio.CancelledError:
        pass  # Graceful exit
    finally:
        print("[System] Auto update watcher stopped")

# New initialization function
def init_auto_update_watcher():
    global AUTO_UPDATE_TASK
    AUTO_UPDATE_TASK = bot.loop.create_task(auto_update_watcher())

# New cleanup handler
@bot.on(events.Raw)
async def on_bot_disconnect(update):
    if AUTO_UPDATE_TASK and not AUTO_UPDATE_TASK.done():
        AUTO_UPDATE_TASK.cancel()
        try:
            await AUTO_UPDATE_TASK
        except asyncio.CancelledError:
            pass

# Updated shutdown handler
@bot.on(events.CallbackQuery(pattern=b"confirm_shutdown"))
async def cb_shutdown_execute(event):
    global AUTO_UPDATE_TASK
    # Cancel task before disconnect
    if AUTO_UPDATE_TASK and not AUTO_UPDATE_TASK.done():
        AUTO_UPDATE_TASK.cancel()
        try:
            await AUTO_UPDATE_TASK
        except asyncio.CancelledError:
            pass
    # ... rest of shutdown logic ...
```

---

## Expected Behavior After Fixes

### Startup Sequence:
1. **Bot starts** → Calls `ensure_sheets()` with retry logic
   - If Google Sheets API is slow/locked: retries automatically
   - If all retries fail: logs error but continues with empty member list
   
2. **Resume Userbots** → Calls `get_all_members_safe()` with caching
   - First call: fetches from Sheets with retry
   - Subsequent calls (within 30 seconds): uses cache
   - If error: uses stale cache as fallback
   
3. **Auto Update Watcher** → Started as managed task
   - Task is stored in global variable
   - Properly cancels on bot shutdown
   - No "pending task" warnings

### Shutdown Sequence:
1. Admin triggers shutdown
2. `cb_shutdown_execute()` is called
3. Auto update watcher task is explicitly cancelled
4. Bot disconnects cleanly
5. No asyncio warnings in logs

---

## Testing Recommendations

```bash
# Test 1: Check database operation with retries
tail -f db_usage.log | grep "gspread_retry"

# Test 2: Verify no pending task warnings
python main.py 2>&1 | grep -i "pending\|destroyed"

# Test 3: Test shutdown gracefully
# In bot: /admin → 🛑 Shutdown
# Check logs for: "[System] Auto update watcher stopped"
```

---

## Files Modified
- ✅ `database.py` - Added retry logic, improved error handling
- ✅ `bot_handlers/admin/system.py` - Added task management for auto_update_watcher

## Backwards Compatibility
✅ All changes are backward compatible:
- Existing code that calls `get_all_members_safe()` works as before
- Retry logic is transparent to callers
- Fallback to cache ensures graceful degradation
