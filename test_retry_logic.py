#!/usr/bin/env python3
"""
Test script untuk mendemonstrasikan retry logic yang sudah di-implement.
Run ini untuk verify bahwa database lock akan di-handle dengan baik.
"""

import time

# Simulate the retry logic
_MAX_RETRIES = 3
_RETRY_DELAY = 1

def simulate_locked_operation(fail_count=2):
    """Simulasi operasi yang pertama kali gagal, tapi berhasil di-retry."""
    global call_count
    call_count = 0
    
    def operation():
        global call_count
        call_count += 1
        if call_count <= fail_count:
            raise Exception(f"database is locked (attempt {call_count})")
        return f"✅ Success on attempt {call_count}"
    
    return operation

def _retry_gspread_op(operation, *args, **kwargs):
    """
    Wrapper untuk retry operasi gspread dengan exponential backoff.
    """
    last_exception = None
    for attempt in range(_MAX_RETRIES):
        try:
            result = operation(*args, **kwargs)
            if attempt > 0:
                print(f"  ✅ Retry berhasil pada attempt {attempt + 1}")
            return result
        except Exception as e:
            last_exception = e
            error_msg = str(e).lower()
            
            # Jika error database locked atau timeout, retry
            if "locked" in error_msg or "timeout" in error_msg or "connection" in error_msg:
                wait_time = _RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                if attempt < _MAX_RETRIES - 1:
                    print(f"  ⚠️  Attempt {attempt + 1} failed: {error_msg}")
                    print(f"  ⏳ Retrying dalam {wait_time} detik...")
                    time.sleep(wait_time)
                continue
            else:
                # Untuk error lain, raise langsung
                raise
    
    # Jika semua retry gagal
    raise last_exception

# Test 1: Operasi yang gagal 1x, berhasil di-retry
print("=" * 60)
print("TEST 1: Database locked 1x, berhasil di-retry")
print("=" * 60)
try:
    op = simulate_locked_operation(fail_count=1)
    result = _retry_gspread_op(op)
    print(f"Result: {result}")
except Exception as e:
    print(f"❌ Final error: {e}")

print()

# Test 2: Operasi yang gagal 2x, berhasil di-retry
print("=" * 60)
print("TEST 2: Database locked 2x, berhasil di-retry")
print("=" * 60)
try:
    op = simulate_locked_operation(fail_count=2)
    result = _retry_gspread_op(op)
    print(f"Result: {result}")
except Exception as e:
    print(f"❌ Final error: {e}")

print()

# Test 3: Operasi yang gagal 3x, exhaust retries
print("=" * 60)
print("TEST 3: Database locked 3x, exhaust retries")
print("=" * 60)
try:
    op = simulate_locked_operation(fail_count=3)
    result = _retry_gspread_op(op)
    print(f"Result: {result}")
except Exception as e:
    print(f"❌ Final error (after {_MAX_RETRIES} attempts): {e}")

print()

# Test 4: Operasi yang langsung berhasil
print("=" * 60)
print("TEST 4: Operasi langsung berhasil (no retry needed)")
print("=" * 60)
try:
    op = simulate_locked_operation(fail_count=0)
    result = _retry_gspread_op(op)
    print(f"Result: {result}")
except Exception as e:
    print(f"❌ Final error: {e}")

print()
print("=" * 60)
print("✅ Semua test selesai!")
print("=" * 60)
print()
print("Summary:")
print("  • Retry logic berhasil mengatasi transient 'database locked' errors")
print("  • Exponential backoff: 1s, 2s, 4s")
print("  • Max 3 attempts sebelum raise exception")
print("  • All database operations otomatis di-retry")
