# bmcodexbot/modules/general.py
import asyncio
from datetime import datetime
from telethon import events

async def register(client, user_id, is_allowed, check_status, help_dict):
    # Daftarkan ke Help
    help_dict[".ping"] = {"title": "Cek Ping 🏓", "usage": "Cek latency bot."}
    help_dict[".alive"] = {"title": "Status ⚡", "usage": "Cek status bot."}
    help_dict[".spam"] = {"title": "Spam 💥", "usage": ".spam <jml> <pesan>"}
    help_dict[".help"] = {"title": "Menu Bantuan 📜", "usage": "Tampilkan list command."}

    @client.on(events.NewMessage(pattern=r"(?i)^\.ping$"))
    async def ping_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        if not is_allowed("ping"): return
        
        start = datetime.now()
        msg = await event.reply("🏓 Pong!")
        end = datetime.now()
        ms = (end - start).microseconds / 1000
        await msg.edit(f"🏓 **Pong!** `{ms}ms`")

    @client.on(events.NewMessage(pattern=r"(?i)^\.alive$"))
    async def alive_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        if not is_allowed("alive"): return
        await event.edit(f"⚡ **BmCodex Userbot Online**\n👤 User: {me.first_name}")

    @client.on(events.NewMessage(pattern=r"(?i)^\.spam (\d+) (.+)"))
    async def spam_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        if not is_allowed("spam"): 
            return await event.edit("🔒 Fitur Spam dimatikan admin.")
        if not await check_status(client, user_id, event): return
        
        await event.delete()
        count = int(event.pattern_match.group(1))
        msg = event.pattern_match.group(2)
        
        for _ in range(min(count, 50)):
            await client.send_message(event.chat_id, msg)
            await asyncio.sleep(0.2)

    # Handler Help Dinamis
    @client.on(events.NewMessage(pattern=r"(?i)^\.help$"))
    async def help_handler(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        
        txt = "**📜 MENU USERBOT**\n\n"
        for cmd, info in help_dict.items():
            txt += f"**{info['title']}**\n`{cmd}` - {info['usage']}\n"
        await event.edit(txt)