# bmcodexbot/bot_handlers/livechat.py
import asyncio
from telethon import events, Button
from config import bot, ADMIN_ID
from database import find_member_row
from state import LIVE_CHAT_SESSIONS, CHAT_QUEUE 

TIMEOUT_SECONDS = 300 # 5 Menit

# ==========================================
# 1. LISTENER PESAN (STANDALONE)
# ==========================================

# Handler Pesan dari MEMBER (User -> Admin)
@bot.on(events.NewMessage(incoming=True))
async def livechat_user_handler(event):
    user_id = event.sender_id
    
    # Abaikan pesan dari admin atau grup
    if user_id == ADMIN_ID or not event.is_private:
        return 

    # Cek apakah user ini sedang dalam sesi Live Chat
    if user_id in LIVE_CHAT_SESSIONS:
        session = LIVE_CHAT_SESSIONS[user_id]
        
        # Update waktu aktivitas terakhir
        session['last_activity'] = asyncio.get_running_loop().time()
        
        # Forward pesan ke Admin
        admin_id = session['admin_id']
        try:
            header = f"📩 **User `{user_id}`:**\n"
            if event.message.text:
                await bot.send_message(admin_id, header + event.message.text)
            elif event.message.media:
                await bot.send_message(admin_id, header + (event.message.text or ""), file=event.message.media)
        except:
            pass
        
        # HENTIKAN PROSES AGAR TIDAK LANJUT KE messages.py / autoreply
        raise events.StopPropagation

# Handler Pesan dari ADMIN (Admin -> User)
@bot.on(events.NewMessage(from_users=ADMIN_ID, incoming=True))
async def livechat_admin_handler(event):
    # Cek apakah admin me-reply pesan bot yang berisi ID user
    reply = await event.get_reply_message()
    target_user = None
    
    if reply:
        # Coba cari ID dari teks pesan yang direply
        import re
        match = re.search(r"User `(\d+)`", reply.text)
        if not match:
            match = re.search(r"User: (\d+)", reply.text)
        
        if match:
            target_user = int(match.group(1))
            
    # Jika tidak reply, tapi hanya ada 1 sesi chat aktif, asumsikan kirim ke dia
    if not target_user and len(LIVE_CHAT_SESSIONS) == 1:
        target_user = list(LIVE_CHAT_SESSIONS.keys())[0]
        
    if target_user and target_user in LIVE_CHAT_SESSIONS:
        session = LIVE_CHAT_SESSIONS[target_user]
        session['last_activity'] = asyncio.get_running_loop().time()
        
        # Kirim ke User
        try:
            header = "👨‍💻 **Admin Support:**\n"
            if event.message.text:
                await bot.send_message(target_user, header + event.message.text)
            elif event.message.media:
                await bot.send_message(target_user, header + (event.message.text or ""), file=event.message.media)
        except:
            pass
            
        # Hentikan proses
        raise events.StopPropagation


# ==========================================
# 2. MENU & ANTRIAN
# ==========================================

@bot.on(events.CallbackQuery(pattern=b"start_livechat"))
async def cb_start_livechat(event):
    user_id = event.sender_id
    
    if user_id in LIVE_CHAT_SESSIONS:
        return await event.answer("Anda sudah dalam sesi chat!", alert=True)
    
    if user_id in CHAT_QUEUE:
        return await event.edit("⏳ **Anda sudah dalam antrian.**\nMohon tunggu admin merespon.", buttons=[[Button.inline("❌ Batalkan", b"cancel_queue")]])

    CHAT_QUEUE.append(user_id)
    
    await event.edit(
        "💬 **LIVE CHAT SUPPORT**\n\n"
        "Permintaan chat dikirim ke Admin.\n"
        "Mohon tunggu sebentar...",
        buttons=[[Button.inline("❌ Batalkan", b"cancel_queue")]]
    )
    
    # Info ke Admin
    idx, row = find_member_row(user_id)
    name = row.get("Nama", "User") if row else "Guest"
    
    await bot.send_message(
        ADMIN_ID,
        f"🔔 **LIVE CHAT REQUEST**\n\n"
        f"👤: {name} (`{user_id}`)\n"
        f"🔢 Antrian: {len(CHAT_QUEUE)}",
        buttons=[
            [Button.inline("✅ Terima", f"ACCEPT_CHAT:{user_id}"), Button.inline("⛔ Tolak", f"REJECT_CHAT:{user_id}")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=b"cancel_queue"))
async def cb_cancel_queue(event):
    user_id = event.sender_id
    if user_id in CHAT_QUEUE:
        CHAT_QUEUE.remove(user_id)
    await event.edit("✅ Chat dibatalkan.", buttons=[[Button.inline("⬅️ Menu Utama", b"menu_start")]])

# ==========================================
# 3. ADMIN ACTIONS (TERIMA/TOLAK)
# ==========================================

@bot.on(events.CallbackQuery(pattern=r"ACCEPT_CHAT:(.+)"))
async def cb_accept_chat(event):
    if event.sender_id != ADMIN_ID: return
    user_id = int(event.data.decode().split(":")[1])
    
    if user_id in CHAT_QUEUE: CHAT_QUEUE.remove(user_id)
    
    task = asyncio.create_task(chat_timeout_checker(user_id))
    LIVE_CHAT_SESSIONS[user_id] = {
        'admin_id': ADMIN_ID,
        'last_activity': asyncio.get_running_loop().time(),
        'task': task
    }
    
    await event.edit(
        f"✅ **CHAT AKTIF**\nUser: `{user_id}`\n\nSilakan reply pesan ini untuk chat.",
        buttons=[[Button.inline("🛑 Akhiri Sesi", f"END_CHAT:{user_id}")]]
    )
    
    await bot.send_message(
        user_id,
        "✅ **Admin Terhubung!**\nSilakan sampaikan pesan Anda.\n_(Chat otomatis berakhir jika 5 menit tidak aktif)_",
        buttons=[[Button.inline("🛑 Akhiri Chat", b"end_chat_user")]]
    )

@bot.on(events.CallbackQuery(pattern=r"REJECT_CHAT:(.+)"))
async def cb_reject_chat(event):
    if event.sender_id != ADMIN_ID: return
    user_id = int(event.data.decode().split(":")[1])
    
    if user_id in CHAT_QUEUE: CHAT_QUEUE.remove(user_id)
    await event.edit("⛔ Chat ditolak.")
    await bot.send_message(user_id, "❌ Maaf, Admin sedang sibuk.")

# ==========================================
# 4. END SESSION & TIMEOUT
# ==========================================

async def end_session(user_id, reason):
    if user_id in LIVE_CHAT_SESSIONS:
        sess = LIVE_CHAT_SESSIONS.pop(user_id)
        sess['task'].cancel()
        
        try: await bot.send_message(sess['admin_id'], f"🛑 Sesi `{user_id}` berakhir.\nAlasan: {reason}")
        except: pass
        
        try: await bot.send_message(user_id, f"🛑 **Sesi Berakhir.**\n{reason}", buttons=[[Button.inline("🔙 Menu Utama", b"menu_start")]])
        except: pass

@bot.on(events.CallbackQuery(pattern=r"END_CHAT:(.+)"))
async def cb_admin_end(event):
    user_id = int(event.data.decode().split(":")[1])
    await end_session(user_id, "Diakhiri oleh Admin.")
    await event.delete()

@bot.on(events.CallbackQuery(pattern=b"end_chat_user"))
async def cb_user_end(event):
    await end_session(event.sender_id, "Diakhiri oleh User.")
    await event.delete()

async def chat_timeout_checker(user_id):
    try:
        while True:
            await asyncio.sleep(60)
            if user_id not in LIVE_CHAT_SESSIONS: break
            
            last = LIVE_CHAT_SESSIONS[user_id]['last_activity']
            if (asyncio.get_running_loop().time() - last) > TIMEOUT_SECONDS:
                await end_session(user_id, "Otomatis (Timeout 5 menit).")
                break
    except asyncio.CancelledError: pass