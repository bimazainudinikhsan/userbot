# ==============================
# USERBOT TEMPLATE
# ==============================

from telethon import TelegramClient, events
from telethon.sessions import StringSession

API_ID = {API_ID}
API_HASH = "{API_HASH}"
SESSION_STRING = "{SESSION_STRING}"

import sys
import asyncio

async def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

    await client.start()
    print("Userbot started.")

    @client.on(events.NewMessage(pattern="ping"))
    async def ping_handler(event):
        await event.reply("pong")

    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Userbot stopped.")
