from telethon import events, Button, errors
from config import bot, ADMIN_ID
from state import GLOBAL_CONFIG
import os, json, asyncio
from datetime import datetime
from urllib.request import urlopen
from .system import execute_force_regenerate_manager_session

# ==========================================
# HELPER: KONTEN DASHBOARD
# ==========================================
def get_dashboard_content():
    """Mengembalikan text dan buttons untuk dashboard admin."""
    is_trial_on = GLOBAL_CONFIG.get("free_trial", False)
    status_trial = "✅ ON" if is_trial_on else "❌ OFF"
    try:
        with open("manager_control.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
            lock_disabled = bool(cfg.get("disable_lock", False))
    except:
        lock_disabled = False
    lock_status = "Lock: ❌ Disabled" if lock_disabled else "Lock: ✅ Enabled"
    
    text = (
        "👑 **ADMINISTRATOR PANEL**\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "Selamat datang kembali, Tuan. \n"
        "Sistem telah siap. Silakan pilih modul manajemen:\n"
    )
    
    buttons = [
        # Baris 1: Mode Trial & Remote
        [Button.inline(f"🆓 Free Trial: {status_trial}", b"TOGGLE_TRIAL"),
         Button.inline("📱 Remote Apps (Firebase)", b"menu_remote_app")],
        
        # Baris 2: Member & Fitur
        [Button.inline("👥 Kelola Member", b"cmd_admin_status"), 
         Button.inline("🌍 Fitur Global", b"cmd_global_fitur")],
        
        # Baris 3: Izin User
        [Button.inline("🔐 Izin User Spesifik", b"cmd_admin_fitur")],
        
        # Baris 4: System
        [Button.inline("🔄 Restart Bot", b"cmd_admin_restart"), 
         Button.inline("🛑 Shutdown", b"cmd_admin_shutdown")],
        
        # Baris 5: Session & Lock
        [Button.inline("🛠 Force Regen Session", b"cmd_force_regen_session"),
         Button.inline(lock_status, b"cmd_toggle_lock")],
         
        # Baris 6: Bantuan
        [Button.inline("ℹ️ Bantuan Perintah", b"cmd_admin_help")],
        [Button.inline("📘 Session Monitor", b"menu_session_monitor")]
    ]
    return text, buttons

# ==========================================
# HANDLER COMMAND /START KHUSUS ADMIN
# ==========================================
@bot.on(events.NewMessage(pattern="/start"))
async def handler_admin_start(event):
    if event.sender_id == ADMIN_ID:
        text, buttons = get_dashboard_content()
        await event.respond(text, buttons=buttons)
        raise events.StopPropagation

@bot.on(events.NewMessage(pattern="/admin"))
async def handler_admin(event):
    if event.sender_id != ADMIN_ID: return
    text, buttons = get_dashboard_content()
    await event.respond(text, buttons=buttons)

# ==========================================
# HANDLER CALLBACK (MENU UTAMA)
# ==========================================
@bot.on(events.CallbackQuery(pattern=b"menu_admin_dashboard"))
async def cb_admin_dashboard(event):
    if event.sender_id != ADMIN_ID: return
    text, buttons = get_dashboard_content()
    # Edit pesan yang ada (Tindih)
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"cmd_force_regen_session"))
async def cb_force_regen_session(event):
    if event.sender_id != ADMIN_ID:
        return
    text = "⚠️ Konfirmasi: Force Regenerate Manager Session\nTindakan ini akan me-restart bot dan membuat session baru."
    buttons = [
        [Button.inline("✅ Lanjutkan", b"CONF_FORCE_REGEN")],
        [Button.inline("🔙 Batal", b"menu_admin_dashboard")]
    ]
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"CONF_FORCE_REGEN"))
async def cb_force_regen_confirm(event):
    if event.sender_id != ADMIN_ID:
        return
    await execute_force_regenerate_manager_session(event)

@bot.on(events.CallbackQuery(pattern=b"cmd_toggle_lock"))
async def cb_toggle_lock(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        with open("manager_control.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except:
        cfg = {}
    cur = bool(cfg.get("disable_lock", False))
    next_state = "OFF" if not cur else "ON"
    text = f"⚙️ Ubah Status Lock\nSaat ini: {'❌ Disabled' if cur else '✅ Enabled'}\nIngin set ke: {next_state}"
    buttons = [
        [Button.inline("✅ Konfirmasi", f"TGL_LOCK_OK:{next_state}")],
        [Button.inline("🔙 Batal", b"menu_admin_dashboard")]
    ]
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"TGL_LOCK_OK:(ON|OFF)"))
async def cb_toggle_lock_ok(event):
    if event.sender_id != ADMIN_ID:
        return
    val = event.data.decode().split(":")[1]
    target_disable = (val == "OFF")
    cfg = {}
    try:
        with open("manager_control.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except:
        cfg = {}
    cfg["disable_lock"] = target_disable
    cfg["changed_by"] = ADMIN_ID
    cfg["changed_at"] = datetime.now().isoformat()
    ok = False
    try:
        with open("manager_control.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        ok = True
    except Exception as e:
        ok = False
        await event.answer(f"❌ Gagal: {e}", alert=True)
    if ok:
        try:
            with open("session_usage.log", "a", encoding="utf-8") as lf:
                lf.write(json.dumps({
                    "ts": datetime.now().isoformat(),
                    "kind": "manager_lock_toggle",
                    "value": "disabled" if target_disable else "enabled",
                    "by": ADMIN_ID
                }) + "\n")
        except:
            pass
        await event.answer("✅ Disimpan.", alert=True)
    text, buttons = get_dashboard_content()
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"TOGGLE_TRIAL"))
async def cb_toggle_trial(event):
    if event.sender_id != ADMIN_ID: return
    GLOBAL_CONFIG["free_trial"] = not GLOBAL_CONFIG.get("free_trial", False)
    # Refresh dashboard langsung
    text, buttons = get_dashboard_content()
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"cmd_admin_help"))
async def cb_admin_help(event):
    if event.sender_id != ADMIN_ID: return
    text = (
        "ℹ️ **PANDUAN ADMIN**\n\n"
        "• **Free Trial**: Mengaktifkan mode trial otomatis untuk user baru.\n"
        "• **Remote Apps**: Mengontrol aplikasi Kiosk via Firebase.\n"
        "• **Kelola Member**: Lihat, edit, atau hapus user.\n"
        "• **Fitur Global**: Matikan fitur tertentu untuk semua user (Maintenance).\n"
        "• **Restart**: Mulai ulang bot jika ada update/error.\n\n"
        "**Panduan Session (Telethon)**\n"
        "• Jalankan bot pada satu IP/host secara konsisten.\n"
        "• Jangan salin file `bot_session.session` ke server lain.\n"
        "• Jika terjadi konflik IP: restart, sistem akan meregenerasi session otomatis.\n"
        "• Hindari menjalankan beberapa instance bot dengan session yang sama.\n"
        "• Untuk userbot, gunakan `Session String` berbeda per user."
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Kembali", b"menu_admin_dashboard")]])

SESSION_MONITOR_STATE = {}
SM_AUTO_TASK = {}

def read_session_logs():
    entries = []
    if os.path.exists("session_usage.log"):
        try:
            with open("session_usage.log", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except:
                        pass
        except:
            pass
    return entries

def geolocate_ip(ip, cache):
    if not ip:
        return {
            "country": "",
            "city": ""
        }
    if ip in cache:
        return cache[ip]
    try:
        with urlopen(f"http://ip-api.com/json/{ip}?fields=status,country,city") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                cache[ip] = {"country": data.get("country", ""), "city": data.get("city", "")}
                return cache[ip]
    except:
        pass
    return {"country": "", "city": ""}

async def render_logs(event, state):
    entries = read_session_logs()
    uid = state.get("filter_uid")
    kind = state.get("filter_kind")
    q = state.get("query")
    sort = state.get("sort", "time_desc")
    page = int(state.get("page", 1))
    per_page = int(state.get("per_page", 10))

    def match(e):
        if uid and str(e.get("uid")) != str(uid):
            return False
        if kind and str(e.get("kind")) != str(kind):
            return False
        if q:
            payload = json.dumps(e)
            if q.lower() not in payload.lower():
                return False
        return True

    filtered = [e for e in entries if match(e)]
    def key_ts(e):
        try:
            return datetime.fromisoformat(e.get("ts"))
        except:
            return datetime.min
    if sort == "time_asc":
        filtered.sort(key=key_ts)
    else:
        filtered.sort(key=key_ts, reverse=True)

    total = len(filtered)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    chunk = filtered[start:start + per_page]

    header = "📘 SESSION MONITOR\n━━━━━━━━━━━━━━━━━━━━\n\n"
    header += f"Mode: LOGS | Total: {total} | Page: {page}/{pages}\n"
    header += f"Sort: {'Time ↓' if sort=='time_desc' else 'Time ↑'}\n"
    if uid:
        header += f"Filter UID: {uid}\n"
    if kind:
        header += f"Filter Kind: {kind}\n"
    if q:
        header += f"Query: {q}\n"
    header += "\n"

    lines = []
    for e in chunk:
        ts = e.get("ts", "")
        k = e.get("kind", "")
        eu = e.get("uid", "")
        ip = e.get("ip", e.get("now_ip", ""))
        src = e.get("source", "")
        lines.append(f"• [{ts}] {k} uid={eu} ip={ip} src={src}")

    text = header + ("\n".join(lines) if lines else "(tidak ada data)")
    buttons = [
        [Button.inline("🔍 Filter UID", b"SM_FILTER_UID"), Button.inline("🔎 Filter Kind", b"SM_FILTER_KIND")],
        [Button.inline("🧹 Clear Filters", b"SM_CLEAR"), Button.inline("🔄 Refresh", b"SM_REFRESH")],
        [Button.inline("⏫ Sort Time ↑", b"SM_SORT_ASC"), Button.inline("⏬ Sort Time ↓", b"SM_SORT_DESC")],
        [Button.inline("⬅️ Prev", b"SM_PREV"), Button.inline("➡️ Next", b"SM_NEXT")],
        [Button.inline("📄 Export CSV", b"SM_EXPORT_LOGS"), Button.inline("🌐 IP Meta", b"SM_IPMETA")],
        [Button.inline("🔙 Kembali", b"menu_admin_dashboard")]
    ]
    await event.edit(text, buttons=buttons)

async def render_ipmeta(event, state):
    entries = read_session_logs()
    per_user = {}
    for e in entries:
        eu = str(e.get("uid", ""))
        ip = e.get("ip", e.get("now_ip", ""))
        if not eu:
            continue
        if eu not in per_user:
            per_user[eu] = set()
        if ip:
            per_user[eu].add(ip)

    try:
        with open("geo_cache.json", "r") as f:
            geo_cache = json.load(f)
    except:
        geo_cache = {}

    lines = []
    for eu, ips in list(per_user.items())[:50]:
        ip_list = list(ips)
        geo_list = []
        for ip in ip_list[:5]:
            g = geolocate_ip(ip, geo_cache)
            cc = g.get("country", "")
            city = g.get("city", "")
            geo_list.append(f"{ip} ({cc} {city})")
        lines.append(f"• UID {eu}: " + ", ".join(geo_list))

    try:
        with open("geo_cache.json", "w") as f:
            json.dump(geo_cache, f, indent=2)
    except:
        pass

    text = "📡 IP META\n━━━━━━━━━━━━━━━━━━━━\n\n" + ("\n".join(lines) if lines else "(tidak ada data)")
    buttons = [
        [Button.inline("📄 Export CSV", b"SM_EXPORT_IPMETA"), Button.inline("📘 Logs", b"SM_LOGS")],
        [Button.inline("🔙 Kembali", b"menu_admin_dashboard")]
    ]
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"menu_session_monitor"))
async def cb_sm_menu(event):
    if event.sender_id != ADMIN_ID:
        return
    SESSION_MONITOR_STATE[ADMIN_ID] = {"mode": "logs", "page": 1, "per_page": 10, "sort": "time_desc"}
    await render_logs(event, SESSION_MONITOR_STATE[ADMIN_ID])

@bot.on(events.CallbackQuery(pattern=b"SM_LOGS"))
async def cb_sm_logs(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {"mode": "logs"})
    st["mode"] = "logs"
    SESSION_MONITOR_STATE[ADMIN_ID] = st
    await render_logs(event, st)

@bot.on(events.CallbackQuery(pattern=b"SM_IPMETA"))
async def cb_sm_ipmeta(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {"mode": "ip"})
    st["mode"] = "ip"
    SESSION_MONITOR_STATE[ADMIN_ID] = st
    await render_ipmeta(event, st)

@bot.on(events.CallbackQuery(pattern=b"SM_NEXT"))
async def cb_sm_next(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    st["page"] = int(st.get("page", 1)) + 1
    SESSION_MONITOR_STATE[ADMIN_ID] = st
    await render_logs(event, st)

@bot.on(events.CallbackQuery(pattern=b"SM_PREV"))
async def cb_sm_prev(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    st["page"] = max(1, int(st.get("page", 1)) - 1)
    SESSION_MONITOR_STATE[ADMIN_ID] = st
    await render_logs(event, st)

@bot.on(events.CallbackQuery(pattern=b"SM_SORT_ASC"))
async def cb_sm_sort_asc(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    st["sort"] = "time_asc"
    SESSION_MONITOR_STATE[ADMIN_ID] = st
    await render_logs(event, st)

@bot.on(events.CallbackQuery(pattern=b"SM_SORT_DESC"))
async def cb_sm_sort_desc(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    st["sort"] = "time_desc"
    SESSION_MONITOR_STATE[ADMIN_ID] = st
    await render_logs(event, st)

@bot.on(events.CallbackQuery(pattern=b"SM_REFRESH"))
async def cb_sm_refresh(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    if st.get("mode") == "ip":
        await render_ipmeta(event, st)
    else:
        await render_logs(event, st)

@bot.on(events.CallbackQuery(pattern=b"SM_CLEAR"))
async def cb_sm_clear(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    for k in ["filter_uid", "filter_kind", "query"]:
        if k in st:
            del st[k]
    st["page"] = 1
    SESSION_MONITOR_STATE[ADMIN_ID] = st
    await render_logs(event, st)

@bot.on(events.CallbackQuery(pattern=b"SM_FILTER_UID"))
async def cb_sm_filter_uid(event):
    if event.sender_id != ADMIN_ID:
        return
    SESSION_MONITOR_STATE[ADMIN_ID] = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    SESSION_MONITOR_STATE[ADMIN_ID]["await"] = "uid"
    await event.edit("🔍 Masukkan UID untuk filter:", buttons=[[Button.inline("🔙 Kembali", b"SM_LOGS")]])

@bot.on(events.CallbackQuery(pattern=b"SM_FILTER_KIND"))
async def cb_sm_filter_kind(event):
    if event.sender_id != ADMIN_ID:
        return
    SESSION_MONITOR_STATE[ADMIN_ID] = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    SESSION_MONITOR_STATE[ADMIN_ID]["await"] = "kind"
    await event.edit("🔎 Masukkan jenis aktivitas (kind):", buttons=[[Button.inline("🔙 Kembali", b"SM_LOGS")]])

@bot.on(events.NewMessage(from_users=ADMIN_ID))
async def sm_input_listener(event):
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    if not st.get("await"):
        return
    val = (event.raw_text or "").strip()
    if st["await"] == "uid":
        st["filter_uid"] = val
    elif st["await"] == "kind":
        st["filter_kind"] = val
    st["await"] = None
    st["page"] = 1
    SESSION_MONITOR_STATE[ADMIN_ID] = st
    msg = await bot.send_message(ADMIN_ID, "✅ Filter diterapkan. Memuat...")
    await render_logs(msg, st)

@bot.on(events.CallbackQuery(pattern=b"SM_EXPORT_LOGS"))
async def cb_sm_export_logs(event):
    if event.sender_id != ADMIN_ID:
        return
    st = SESSION_MONITOR_STATE.get(ADMIN_ID, {})
    entries = read_session_logs()
    uid = st.get("filter_uid")
    kind = st.get("filter_kind")
    q = st.get("query")
    def match(e):
        if uid and str(e.get("uid")) != str(uid):
            return False
        if kind and str(e.get("kind")) != str(kind):
            return False
        if q:
            payload = json.dumps(e)
            if q.lower() not in payload.lower():
                return False
        return True
    filtered = [e for e in entries if match(e)]
    path = "session_usage_export.csv"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("ts,kind,uid,ip,source\n")
            for e in filtered:
                f.write(
                    f"{e.get('ts','')},{e.get('kind','')},{e.get('uid','')},{e.get('ip', e.get('now_ip',''))},{e.get('source','')}\n"
                )
        await bot.send_file(ADMIN_ID, path, caption="Export Logs")
    except Exception as e:
        await event.answer(f"Error export: {e}", alert=True)

@bot.on(events.CallbackQuery(pattern=b"SM_EXPORT_IPMETA"))
async def cb_sm_export_ipmeta(event):
    if event.sender_id != ADMIN_ID:
        return
    entries = read_session_logs()
    per_user = {}
    for e in entries:
        eu = str(e.get("uid", ""))
        ip = e.get("ip", e.get("now_ip", ""))
        if not eu:
            continue
        if eu not in per_user:
            per_user[eu] = set()
        if ip:
            per_user[eu].add(ip)
    path = "user_ip_meta_export.csv"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("uid,ips\n")
            for eu, ips in per_user.items():
                f.write(f"{eu},\"{', '.join(list(ips))}\"\n")
        await bot.send_file(ADMIN_ID, path, caption="Export IP Meta")
    except Exception as e:
        await event.answer(f"Error export: {e}", alert=True)
