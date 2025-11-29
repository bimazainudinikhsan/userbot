# bmcodexbot/modules/general.py
import asyncio
import time # Pakai time.perf_counter untuk akurasi tinggi
from datetime import datetime
from telethon import events

async def register(client, user_id, is_allowed, check_status, help_dict):
    # Daftarkan ke Help
    help_dict[".ping"] = {"title": "Cek Ping 🏓", "usage": "Cek latency bot."}
    help_dict[".alive"] = {"title": "Status ⚡", "usage": "Cek status bot."}
    help_dict[".spam"] = {"title": "Spam 💥", "usage": ".spam <jml> <pesan>"}
    help_dict[".help"] = {"title": "Menu Bantuan 📜", "usage": "Tampilkan list command."}

    # --- PING (Tanpa cek status database agar cepat) ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.ping$"))
    async def ping_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        # Cukup cek toggle fitur (is_allowed), tidak perlu cek membership status
        if not is_allowed("ping"): return 
        
        start = time.perf_counter()
        msg = await event.reply("🏓 Pong!")
        end = time.perf_counter()
        ms = (end - start) * 1000
        await msg.edit(f"🏓 **Pong!** `{ms:.2f}ms`")

    # --- ALIVE (Tanpa cek status database) ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.alive$"))
    async def alive_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        if not is_allowed("alive"): return
        
        await event.edit(
            f"⚡ **BmCodex Userbot Online**\n"
            f"👤 User: {me.first_name}\n"
            f"🆔 ID: `{me.id}`"
        )

    # --- HELP (Menu Bantuan) ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.help$"))
    async def help_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        txt = "**📜 MENU USERBOT**\n\n"
        for cmd, info in help_dict.items():
            txt += f"▫️ **{info['title']}**\n   `{cmd}`\n"
        await event.edit(txt)

    # --- SPAM (Fitur Berat = Perlu Cek Status) ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.spam (\d+) (.+)"))
    async def spam_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        # Cek Izin & Status Database (Penting untuk fitur abuse)
        if not is_allowed("spam"): 
            return await event.edit("🔒 Fitur Spam dimatikan.")
        
        if not await check_status(client, user_id, event): return
        
        await event.delete()
        count = int(event.pattern_match.group(1))
        msg = event.pattern_match.group(2)
        
        # Limit hardcoded agar aman
        limit = 50 
        for _ in range(min(count, limit)):
            await client.send_message(event.chat_id, msg)
            await asyncio.sleep(0.3)