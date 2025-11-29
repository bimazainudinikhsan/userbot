from telethon import events, Button
from config import bot, ADMIN_ID
from state import GLOBAL_FEATURE_FLAGS, EDIT_PERMISSION_STATE, USER_PERMISSIONS
from database import get_all_members_safe, get_member_permissions, update_member_permissions

ALL_FEATURES_LIST = [
    "ping",           # .ping - Cek latency bot
    "alive",          # .alive - Cek status bot
    "help",           # .help - Menu bantuan
    "spam",           # .spam - Spam pesan
    "faktur",         # .faktur - Buat faktur/invoice
    "unread",         # .replyunread - Balas pesan unread
    "spambot",        # .spambot - Spam bot biasa
    "spambotpremium", # .spambotpremium - Spam bot premium
    "spamai",         # .spamai - Spam dengan AI
    "automessage",    # Auto Message - Kirim pesan otomatis
]

FEATURE_LABELS = {
    "ping": "🏓 Ping",
    "alive": "⚡ Alive",
    "help": "📜 Help",
    "spam": "💥 Spam",
    "faktur": "📑 Faktur",
    "unread": "👻 Unread",
    "spambot": "🤖 SpamBot",
    "spambotpremium": "💎 SpamPrem",
    "spamai": "🧠 SpamAI",
    "automessage": "📨 AutoMsg",
}

# --- Global Features ---
@bot.on(events.CallbackQuery(pattern=b"cmd_global_fitur"))
async def cb_global_fitur_menu(event):
    if event.sender_id != ADMIN_ID: return
    
    text = (
        "🌍 **KELOLA FITUR GLOBAL**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Matikan/nyalakan fitur untuk SEMUA MEMBER.\n\n"
        "✅ = Aktif | 🔴 = Nonaktif"
    )
    buttons = []
    row = []
    
    for feature in ALL_FEATURES_LIST:
        is_active = GLOBAL_FEATURE_FLAGS.get(feature, True)
        icon = "✅" if is_active else "🔴"
        label = FEATURE_LABELS.get(feature, feature)
        row.append(Button.inline(f"{icon} {label}", f"GLB_TOGGLE:{feature}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
            
    if row: buttons.append(row)
    buttons.append([Button.inline("🔙 Kembali", b"menu_admin_dashboard")])
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"GLB_TOGGLE:(.+)"))
async def cb_global_toggle(event):
    if event.sender_id != ADMIN_ID: return
    feature = event.data.decode().split(":")[1]
    GLOBAL_FEATURE_FLAGS[feature] = not GLOBAL_FEATURE_FLAGS.get(feature, True)
    await cb_global_fitur_menu(event)

# --- User Permissions ---
@bot.on(events.CallbackQuery(pattern=b"cmd_admin_fitur"))
async def admin_fitur_menu(event):
    if event.sender_id != ADMIN_ID: return
    records = get_all_members_safe()
    buttons = []
    for row in records:
        if row.get("Status") == "Approved":
            buttons.append([Button.inline(f"{row.get('Nama')} ({row.get('User ID')})", f"EDIT_FITUR:{row.get('User ID')}")])
    
    if not buttons: return await event.answer("❌ Tidak ada member aktif.", alert=True)
    # TOMBOL KEMBALI FIXED
    buttons.append([Button.inline("⬅️ Kembali", b"menu_admin_dashboard")])
    await event.edit("🛠 **MANAJEMEN IZIN USER**\nPilih member:", buttons=buttons)

# ... (Sisa handler EDIT_FITUR dan SAVE_FITUR tetap sama, hanya pastikan tombol kembali di SAVE juga benar)

@bot.on(events.CallbackQuery(pattern=r"EDIT_FITUR:(.+)"))
async def cb_edit_fitur(event):
    if event.sender_id != ADMIN_ID: return
    target = int(event.data.decode().split(":")[1])
    perms = get_member_permissions(target)
    perm_dict = {f: (True if "ALL" in perms or f in perms else False) for f in ALL_FEATURES_LIST}
    
    if ADMIN_ID not in EDIT_PERMISSION_STATE: EDIT_PERMISSION_STATE[ADMIN_ID] = {}
    EDIT_PERMISSION_STATE[ADMIN_ID][target] = perm_dict
    await show_checklist(event, target)

async def show_checklist(event, target):
    p = EDIT_PERMISSION_STATE[ADMIN_ID][target]
    btns = []
    row = []
    for f in ALL_FEATURES_LIST:
        mark = "✅" if p[f] else "❌"
        label = FEATURE_LABELS.get(f, f)
        row.append(Button.inline(f"{mark} {label}", f"TOGGLE_F:{target}:{f}"))
        if len(row) == 2: 
            btns.append(row)
            row = []
    if row: btns.append(row)
    btns.append([Button.inline("💾 SIMPAN", f"SAVE_FITUR:{target}")])
    btns.append([Button.inline("🔙 Batal", b"cmd_admin_fitur")])
    
    text = (
        f"🛠 **EDIT IZIN USER**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User ID: `{target}`\n\n"
        f"✅ = Diizinkan | ❌ = Diblokir"
    )
    await event.edit(text, buttons=btns)

@bot.on(events.CallbackQuery(pattern=r"TOGGLE_F:(.+):(.+)"))
async def cb_toggle(event):
    d = event.data.decode().split(":")
    t, f = int(d[1]), d[2]
    EDIT_PERMISSION_STATE[ADMIN_ID][t][f] = not EDIT_PERMISSION_STATE[ADMIN_ID][t][f]
    await show_checklist(event, t)

@bot.on(events.CallbackQuery(pattern=r"SAVE_FITUR:(.+)"))
async def cb_save(event):
    t = int(event.data.decode().split(":")[1])
    pd = EDIT_PERMISSION_STATE[ADMIN_ID].pop(t, {})
    if all(pd.values()): final = ["ALL"]
    else: final = [k for k,v in pd.items() if v]
    
    update_member_permissions(t, final)
    USER_PERMISSIONS[t] = final
    await event.edit(f"✅ **Tersimpan!**\nUser: `{t}`", buttons=[[Button.inline("⬅️ Kembali", b"cmd_admin_fitur")]])
