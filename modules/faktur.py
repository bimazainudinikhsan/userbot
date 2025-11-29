# bmcodexbot/modules/faktur.py
import os
import json
import re
import math
import asyncio
import shutil
import functools
from concurrent.futures import ProcessPoolExecutor 
from telethon import events, Button
from telethon.errors import MessageNotModifiedError, QueryIdInvalidError
from config import bot, ADMIN_ID
from utils_faktur import generate_faktur
from state import ACTIVE_USERBOTS 

SETTINGS_FILE = 'user_faktur_settings.json'
BASE_STORAGE_DIR = 'penyimpanan_member'

# Inisialisasi Multi-Core Processor
PROCESS_POOL = ProcessPoolExecutor(max_workers=4)

FAKTUR_SESSION = {}      
BOT_SETTING_STATE = {}   

def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

# ==========================================
# 1. DATABASE PENGATURAN
# ==========================================
def get_settings(user_id):
    if not os.path.exists(SETTINGS_FILE):
        data = {}
    else:
        try:
            with open(SETTINGS_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {}
    
    str_uid = str(user_id)
    if str_uid not in data:
        data[str_uid] = {
            "rounddown_math": False,
            "rounddown_limit": 1000,
            "ppn": False,
            "template_bank": "-",
            "template_note": "-",
            "default_items": [] 
        }
        save_settings(data)
    return data[str_uid]

def save_user_setting(user_id, key, value):
    if not os.path.exists(SETTINGS_FILE): data = {}
    else:
        try: 
            with open(SETTINGS_FILE, 'r') as f: 
                data = json.load(f)
        except: data = {}
        
    str_uid = str(user_id)
    if str_uid not in data:
        get_settings(user_id)
        try: 
            with open(SETTINGS_FILE, 'r') as f: 
                data = json.load(f)
        except: data = {str_uid: {}}

    if str_uid in data:
        data[str_uid][key] = value
        save_settings(data)

def save_settings(data):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}")

# ==========================================
# 2. BOT MANAGER HANDLERS (ADMIN UI)
# ==========================================

async def safe_edit(event, text, buttons=None):
    try: await event.edit(text, buttons=buttons)
    except MessageNotModifiedError: pass 
    except (QueryIdInvalidError, Exception): await event.respond(text, buttons=buttons)

# --- HANDLER CANCEL PROGRESS ---
@bot.on(events.CallbackQuery(pattern=r"fkt_cancel:(.+)"))
async def cb_faktur_cancel(event):
    cid = int(event.data.decode().split(':')[1])
    if cid in FAKTUR_SESSION:
        sess = FAKTUR_SESSION[cid]
        try:
            if os.path.exists(sess['storage']):
                shutil.rmtree(sess['storage'])
        except: pass
        del FAKTUR_SESSION[cid]
        await event.edit("❌ **Proses Dibatalkan Paksa.**")
    else:
        await event.edit("⚠️ Proses sudah selesai/tidak ada.")

# --- HANDLER VERIFIKASI SCREENSHOT ---
@bot.on(events.CallbackQuery(pattern=r"fkt_(ok|no):(.+)"))
async def cb_faktur_verif(event):
    user_id = event.sender_id 
    data = event.data.decode().split(':')
    action = data[0]
    cid = int(data[1]) 
    
    if cid not in FAKTUR_SESSION:
        await event.edit("❌ **Sesi Berakhir.**")
        return

    sess = FAKTUR_SESSION[cid]
    client = ACTIVE_USERBOTS.get(user_id)
    if not client: return await event.answer("Userbot offline.", alert=True)
    
    # === VERIFIKASI AWAL (DATA DIRI) ===
    if sess['step'] == 'WAIT_SS_VERIF':
        if action == "fkt_ok":
            sess['step'] = 'WAIT_NAME'
            await event.edit("✅ **Diterima.** Meminta input Nama...")
            try:
                await client.send_message(cid, "✅ **Foto Diterima.**\n\n👤 **Silakan Ketik NAMA LENGKAP:**")
            except: pass
        elif action == "fkt_no":
            sess['step'] = 'WAIT_SS' 
            await event.edit("❌ **Ditolak.** Meminta ulang...")
            try:
                await client.send_message(cid, "❌ **Foto Tidak Valid.**\nMohon kirim ulang foto yang jelas.")
            except: pass

    # === VERIFIKASI PEMBAYARAN ===
    elif sess['step'] == 'WAIT_PAYMENT_VERIF':
        if action == "fkt_ok":
            await event.edit("✅ **Pembayaran Diterima.** Memproses selanjutnya...")
            
            # Notifikasi ke Klien (Hanya jika belum selesai semua)
            if sess['current_idx'] < len(sess['queue']):
                try:
                    await client.send_message(cid, "✅ **Bukti sudah di-aproved oleh admin.**\nSilahkan tunggu langkah berikutnya...")
                except: pass
            
            # Lanjut ke item berikutnya
            asyncio.create_task(process_next_item(client, user_id, cid))
            
        elif action == "fkt_no":
            sess['step'] = 'WAIT_PAYMENT_SS'
            await event.edit("❌ **Pembayaran Ditolak.** Meminta ulang...")
            try:
                await client.send_message(cid, "❌ **Bukti Pembayaran Tidak Valid.**\nMohon kirim ulang bukti transfer yang benar.")
            except: pass

# --- CALLBACK SELESAI ---
@bot.on(events.CallbackQuery(pattern=r"fkt_finish:(.+)"))
async def cb_faktur_finish(event):
    cid = int(event.data.decode().split(':')[1])
    if cid in FAKTUR_SESSION:
        sess = FAKTUR_SESSION[cid]
        try:
            if os.path.exists(sess['storage']):
                shutil.rmtree(sess['storage'])
        except: pass
        del FAKTUR_SESSION[cid]
    
    await event.edit("✅ **Selesai & Data Dihapus.**", buttons=[[Button.inline("🏠 Menu Utama", b"menu_start")]])

# --- MENU SETTING ---
async def show_setting_menu(event, user_id):
    conf = get_settings(user_id)
    math_rd = "ON" if conf.get('rounddown_math') else "OFF"
    ppn = "ON" if conf.get('ppn') else "OFF"
    bank = conf.get('template_bank', '-')
    note = conf.get('template_note', '-')
    items = conf.get('default_items', [])
    
    text = (
        f"⚙️ **PENGATURAN FAKTUR**\n\n"
        f"📋 **Daftar Roundown:** {len(items)} Layanan\n"
        f"🏦 **Info Bank:** `{bank}`\n"
        f"📝 **Catatan:** `{note}`\n"
        f"➖➖➖➖➖➖➖➖➖\n"
        f"💰 PPN (5%): **{ppn}**\n"
        f"📉 Pembulatan: **{math_rd}**\n"
    )
    buttons = [
        [Button.inline(f"📋 Kelola Roundown ({len(items)})", b"sf_manage_items")],
        [Button.inline("✏️ Edit Bank", b"sf_edit_bank"), Button.inline("✏️ Edit Catatan", b"sf_edit_note")],
        [Button.inline(f"PPN: {ppn}", b"sf_toggle_ppn"), Button.inline(f"Bulatkan: {math_rd}", b"sf_toggle_rd")],
        [Button.inline("✅ Selesai", b"sf_done")]
    ]
    await safe_edit(event, text, buttons)

async def show_manage_items_menu(event, user_id):
    conf = get_settings(user_id)
    items = conf.get('default_items', [])
    text = "📋 **KELOLA ROUNDOWN LAYANAN**\n\n"
    buttons = []
    
    if not items: text += "_Belum ada layanan._"
    else:
        for idx, item in enumerate(items):
            text += f"{idx+1}. {item['desc']} | {item['price']:,}\n"
            buttons.append([
                Button.inline(f"✏️ Edit No.{idx+1}", f"sf_itm_ed:{idx}"),
                Button.inline(f"🗑️ Hapus No.{idx+1}", f"sf_itm_del:{idx}")
            ])
    buttons.append([Button.inline("➕ Tambah Layanan", b"sf_itm_add")])
    buttons.append([Button.inline("🔙 Kembali", b"sf_menu_back")])
    await safe_edit(event, text, buttons)

@bot.on(events.CallbackQuery(pattern=b"sf_toggle_ppn"))
async def cb_sf_ppn(event):
    uid = event.sender_id
    curr = get_settings(uid).get('ppn', False)
    save_user_setting(uid, 'ppn', not curr)
    await show_setting_menu(event, uid)

@bot.on(events.CallbackQuery(pattern=b"sf_toggle_rd"))
async def cb_sf_rd(event):
    uid = event.sender_id
    curr = get_settings(uid).get('rounddown_math', False)
    save_user_setting(uid, 'rounddown_math', not curr)
    await show_setting_menu(event, uid)

@bot.on(events.CallbackQuery(pattern=b"sf_manage_items"))
async def cb_sf_manage(event):
    await show_manage_items_menu(event, event.sender_id)

@bot.on(events.CallbackQuery(pattern=b"sf_itm_add"))
async def cb_sf_itm_add(event):
    BOT_SETTING_STATE[event.sender_id] = "WAIT_ITEM_ADD"
    await safe_edit(event, "➕ **Tambah Layanan**\nFormat: `Nama | Harga`\nContoh: `Admin | 35000`\n_(Ketik 'batal' kembali)_", buttons=[[Button.inline("🔙 Batal", b"sf_manage_items")]])

@bot.on(events.CallbackQuery(pattern=r"sf_itm_del:(.+)"))
async def cb_sf_itm_del(event):
    uid, idx = event.sender_id, int(event.data.decode().split(":")[1])
    conf = get_settings(uid)
    items = conf.get('default_items', [])
    if 0 <= idx < len(items):
        items.pop(idx)
        save_user_setting(uid, 'default_items', items)
        await event.answer("🗑️ Dihapus!")
    await show_manage_items_menu(event, uid)

@bot.on(events.CallbackQuery(pattern=r"sf_itm_ed:(.+)"))
async def cb_sf_itm_ed(event):
    uid, idx = event.sender_id, int(event.data.decode().split(":")[1])
    BOT_SETTING_STATE[uid] = f"WAIT_ITEM_EDIT:{idx}"
    await safe_edit(event, f"✏️ **Edit No.{idx+1}**\nFormat: `Nama | Harga`", buttons=[[Button.inline("🔙 Batal", b"sf_manage_items")]])

@bot.on(events.CallbackQuery(pattern=b"sf_edit_bank"))
async def cb_sf_bank(event):
    BOT_SETTING_STATE[event.sender_id] = "WAIT_BANK"
    await safe_edit(event, "🏦 **Setting Info Bank**\nKirim Info Bank/E-Wallet.", buttons=[[Button.inline("🔙 Batal", b"sf_menu_back")]])

@bot.on(events.CallbackQuery(pattern=b"sf_edit_note"))
async def cb_sf_note(event):
    BOT_SETTING_STATE[event.sender_id] = "WAIT_NOTE"
    await safe_edit(event, "📝 **Setting Catatan**\nKirim catatan kaki.", buttons=[[Button.inline("🔙 Batal", b"sf_menu_back")]])

@bot.on(events.CallbackQuery(pattern=b"sf_menu_back"))
async def cb_sf_back(event):
    if event.sender_id in BOT_SETTING_STATE: del BOT_SETTING_STATE[event.sender_id]
    await show_setting_menu(event, event.sender_id)

@bot.on(events.CallbackQuery(pattern=b"sf_done"))
async def cb_sf_done(event):
    try: await event.delete()
    except: pass

@bot.on(events.NewMessage(incoming=True))
async def bot_setting_listener(event):
    uid = event.sender_id
    if uid not in BOT_SETTING_STATE: return
    
    state_raw = BOT_SETTING_STATE[uid]
    state, param = state_raw.split(":") if ":" in state_raw else (state_raw, None)
    text = event.text.strip()
    
    if text.lower() == 'batal':
        del BOT_SETTING_STATE[uid]
        await (show_manage_items_menu(event, uid) if "ITEM" in state else show_setting_menu(event, uid))
        return

    if state == "WAIT_ITEM_ADD" or state == "WAIT_ITEM_EDIT":
        if '|' in text:
            parts = text.rsplit('|', 1)
            desc, price_str = parts[0].strip(), parts[1].strip().replace('.', '').replace(',', '')
            if price_str.isdigit():
                conf = get_settings(uid)
                items = conf.get('default_items', [])
                if state == "WAIT_ITEM_ADD": items.append({'desc': desc, 'price': int(price_str)})
                else: 
                    idx = int(param)
                    if 0 <= idx < len(items): items[idx] = {'desc': desc, 'price': int(price_str)}
                save_user_setting(uid, 'default_items', items)
                await event.reply("✅ Tersimpan!")
                del BOT_SETTING_STATE[uid]
                await show_manage_items_menu(await event.reply("🔄 Memuat..."), uid)
            else: await event.reply("⚠️ Harga harus angka.")
        else: await event.reply("⚠️ Format: `Nama | Harga`")

    elif state == "WAIT_BANK":
        save_user_setting(uid, 'template_bank', text)
        await event.reply("✅ Tersimpan!")
        del BOT_SETTING_STATE[uid]
        await show_setting_menu(await event.reply("🔄 Memuat..."), uid)

    elif state == "WAIT_NOTE":
        save_user_setting(uid, 'template_note', text)
        await event.reply("✅ Tersimpan!")
        del BOT_SETTING_STATE[uid]
        await show_setting_menu(await event.reply("🔄 Memuat..."), uid)

# ==========================================
# 3. USERBOT HANDLERS (EKSEKUSI)
# ==========================================

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".faktur"] = {"title": "Faktur 📄", "usage": ".faktur [nomor] (untuk kirim manual)"}
    help_dict[".set_faktur"] = {"title": "Atur Faktur ⚙️", "usage": "Menu Setting."}

    @client.on(events.NewMessage(pattern=r"(?i)^\.set_faktur$"))
    async def set_faktur_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        try: await event.delete()
        except: pass
        await bot.send_message(user_id, "🔄 **Membuka Pengaturan Faktur...**")
        await show_setting_menu(await bot.send_message(user_id, "Menu:"), user_id)

    # --- START FAKTUR ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.faktur(?: (\d+))?$"))
    async def faktur_start(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        if not await check_status(client, user_id, event): return
        if not is_allowed("faktur"): return await event.edit("🔒 Terkunci.")

        conf = get_settings(user_id)
        items = conf.get('default_items', [])
        
        if not items:
            return await event.edit("⚠️ **Roundown Kosong.** Set di `.set_faktur`.")

        user_storage = os.path.join(BASE_STORAGE_DIR, str(event.chat_id))
        if not os.path.exists(user_storage): os.makedirs(user_storage)

        queue_list = []
        arg_num = event.pattern_match.group(1)
        
        if arg_num:
            idx_req = int(arg_num) - 1
            if 0 <= idx_req < len(items):
                queue_list = [items[idx_req]] 
            else:
                return await event.edit(f"⚠️ Nomor {arg_num} tidak valid. Max {len(items)}.")
        else:
            queue_list = list(items)

        FAKTUR_SESSION[event.chat_id] = {
            'queue': queue_list,
            'current_idx': 0, 
            'client_data': {},
            'step': 'WAIT_SS', 
            'storage': user_storage
        }
        
        await event.edit(
            "📸 **VERIFIKASI DEVICE**\n\n"
            "Mohon kirimkan **Foto Tampilan HP** Anda sekarang sebelum melanjutkan."
        )

    # --- LISTENER INPUT ---
    @client.on(events.NewMessage()) 
    async def faktur_listener(event):
        cid = event.chat_id
        if cid not in FAKTUR_SESSION: return
        
        is_owner = event.out
        text = event.text.strip()
        sess = FAKTUR_SESSION[cid]
        step = sess['step']
        storage = sess['storage']

        if is_owner and text.lower() == '.batal':
            try: shutil.rmtree(storage)
            except: pass
            del FAKTUR_SESSION[cid]
            await event.reply("❌ **Dibatalkan.**")
            return

        if not is_owner:
            # A. Verifikasi Foto Device
            if step == 'WAIT_SS':
                if event.photo:
                    try:
                        path = os.path.join(storage, "screenshot.jpg")
                        await event.download_media(file=path)
                        
                        await bot.send_file(
                            user_id,
                            file=path,
                            caption=f"📸 **Verifikasi Foto Klien**\nChat ID: `{cid}`\n\nIzinkan lanjut?",
                            buttons=[
                                [Button.inline("✅ Lanjut", f"fkt_ok:{cid}"), Button.inline("❌ Tolak", f"fkt_no:{cid}")]
                            ]
                        )
                        sess['step'] = 'WAIT_SS_VERIF' 
                        await event.reply("⏳ **Foto diterima. Mohon tunggu verifikasi admin...**")
                    except Exception as e:
                        await event.reply(f"⚠️ Gagal: {e}")

            # B. Data Diri
            elif step == 'WAIT_NAME':
                sess['client_data']['nama'] = text
                sess['step'] = 'WAIT_EMAIL'
                await event.reply("✅ **Nama OK.**\n📧 Ketik **EMAIL:**")

            elif step == 'WAIT_EMAIL':
                if is_valid_email(text):
                    sess['client_data']['email'] = text
                    sess['step'] = 'WAIT_HP'
                    await event.reply("✅ **Email Valid.**\n📱 Ketik **NO HP:**")
                else:
                    await event.reply("⚠️ **Email Tidak Valid.**")

            elif step == 'WAIT_HP':
                sess['client_data']['hp'] = text
                sess['step'] = 'PROCESSING'
                
                # --- PERBAIKAN: NOTIFIKASI KE KLIEN ---
                await event.reply(
                    "✅ **Data Lengkap.**\n"
                    "⏳ **Tunggu sebentar ya kak, kami buatkan faktur dahulu.**"
                )
                
                item_now = sess['queue'][sess['current_idx']]
                await bot.send_message(
                    user_id,
                    f"⚙️ **Sedang Membuat Faktur...**\n"
                    f"Item: {item_now['desc']}\n"
                    f"Klien: {sess['client_data']['nama']}",
                    buttons=[[Button.inline("🛑 Cancel Progress", f"fkt_cancel:{cid}")]]
                )
                
                asyncio.create_task(process_next_item(client, user_id, cid))

            # C. Bukti Pembayaran
            elif step == 'WAIT_PAYMENT_SS':
                if event.photo:
                    try:
                        pay_path = os.path.join(storage, f"payment_{sess['current_idx']}.jpg")
                        await event.download_media(file=pay_path)
                        
                        await bot.send_file(
                            user_id,
                            file=pay_path,
                            caption=f"💸 **Bukti Pembayaran**\nChat ID: `{cid}`\n\nTerima pembayaran?",
                            buttons=[
                                [Button.inline("✅ Terima & Lanjut", f"fkt_ok:{cid}"), Button.inline("❌ Tolak", f"fkt_no:{cid}")]
                            ]
                        )
                        sess['step'] = 'WAIT_PAYMENT_VERIF'
                        await event.reply("⏳ **Bukti diterima. Menunggu verifikasi admin...**")
                    except Exception as e:
                        await event.reply(f"⚠️ Gagal: {e}")

async def process_next_item(client, user_id, cid):
    if cid not in FAKTUR_SESSION: return
    sess = FAKTUR_SESSION[cid]
    idx = sess['current_idx']
    queue = sess['queue']
    storage = sess['storage']
    cdata = sess['client_data']
    
    # CEK SELESAI
    if idx >= len(queue):
        # Laporan Akhir Admin
        report = (
            f"🎉 **Faktur Selesai Dikirim Semua!**\n\n"
            f"👤 Nama: `{cdata['nama']}`\n"
            f"📧 Email: `{cdata['email']}`\n"
            f"📱 No HP: `{cdata['hp']}`\n"
            f"✅ Total Item: {len(queue)}"
        )
        await bot.send_message(
            user_id, 
            report, 
            buttons=[[Button.inline("✅ Selesai & Hapus File", f"fkt_finish:{cid}")]]
        )
        
        await client.send_message(cid, "✅ **Bukti sudah di-aproved oleh admin.**\nSilahkan tunggu langkah berikutnya...")
        return

    item = queue[idx]
    conf = get_settings(user_id)
    loop = asyncio.get_running_loop()

    try:
        subtotal = item['price']
        ppn = subtotal * 0.05 if conf.get('ppn') else 0
        total_final = subtotal + ppn
        if conf.get('rounddown_math'):
            limit = conf.get('rounddown_limit', 1000)
            total_final = math.floor(total_final / limit) * limit

        desc_str = f"{item['desc']} (@ {item['price']:,})"
        
        func_gen = functools.partial(
            generate_faktur,
            user_id=user_id,
            nama_klien=cdata['nama'],
            email_klien=cdata['email'],
            no_hp=cdata['hp'],
            deskripsi=desc_str,
            subtotal=subtotal,
            catatan=conf.get('template_note', '-'),
            payment_details=conf.get('template_bank', '-'),
            do_rounddown=conf.get('rounddown_math', False),
            use_ppn=conf.get('ppn', False),
            rounddown_limit=conf.get('rounddown_limit', 1000),
            output_folder=storage
        )
        
        pdf_path = await loop.run_in_executor(PROCESS_POOL, func_gen)
        
        caption = (
            f"📄 **Faktur Pembayaran**\n"
            f"Layanan: **{item['desc']}**\n"
            f"Harga: **Rp {subtotal:,}**\n"
        )
        if conf.get('ppn'): caption += f"PPN (5%): **Rp {int(ppn):,}**\n"
        caption += f"💰 **TOTAL: Rp {int(total_final):,}**\n\n"
        
        # Pesan khusus jika belum selesai
        if idx < len(queue) - 1:
            caption += "**Selesaikan Pembayaran Untuk melanjutkan.**\n"
            caption += "📸 **Kirimkan Bukti Foto/Screenshot pembayarannya.**"
        else:
            caption += "**Pembayaran Terakhir.**\nSilakan selesaikan pembayaran."
        
        await client.send_file(cid, file=pdf_path, caption=caption)
        
        # Update State -> Tunggu Bayar
        sess['step'] = 'WAIT_PAYMENT_SS'
        # Increment Index SETELAH pembayaran diverifikasi
        sess['current_idx'] += 1 
        
    except Exception as e:
        await client.send_message(cid, f"❌ Gagal: {e}")