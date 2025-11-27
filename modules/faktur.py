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

# Inisialisasi Multi-Core Processor (Max 4 Worker)
PROCESS_POOL = ProcessPoolExecutor(max_workers=4)

FAKTUR_SESSION = {}      
BOT_SETTING_STATE = {}   

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

    data[str_uid][key] = value
    save_settings(data)

def save_settings(data):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}")

# ==========================================
# 2. BOT MANAGER HANDLERS (UI & VERIFIKASI)
# ==========================================

async def safe_edit(event, text, buttons=None):
    try:
        await event.edit(text, buttons=buttons)
    except MessageNotModifiedError: pass 
    except (QueryIdInvalidError, Exception):
        await event.respond(text, buttons=buttons)

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
    
    if not client:
        await event.answer("Userbot offline.", alert=True)
        return
    
    if action == "fkt_ok":
        sess['step'] = 'WAIT_NAME'
        await event.edit("✅ **Diterima.** Meminta input Nama...")
        try:
            await client.send_message(cid, "✅ **Verifikasi Berhasil.**\n\n👤 **Silakan Ketik NAMA:**")
        except: pass
            
    elif action == "fkt_no":
        sess['step'] = 'WAIT_SS' 
        await event.edit("❌ **Ditolak.** Meminta ulang...")
        try:
            await client.send_message(cid, "❌ **Screenshot Tidak Valid.**\nMohon kirim ulang screenshot tampilan HP Anda.")
        except: pass

# --- MENU PENGATURAN UTAMA ---
async def show_setting_menu(event, user_id):
    conf = get_settings(user_id)
    math_rd = "ON" if conf.get('rounddown_math') else "OFF"
    ppn = "ON" if conf.get('ppn') else "OFF"
    bank = conf.get('template_bank', '-')
    if bank == "-": bank = "(Belum diset)"
    note = conf.get('template_note', '-')
    if note == "-": note = "(Belum diset)"
    
    items = conf.get('default_items', [])
    item_count = len(items)

    text = (
        f"⚙️ **PENGATURAN FAKTUR**\n\n"
        f"📋 **Daftar Roundown:** {item_count} Layanan\n"
        f"🏦 **Info Bank:**\n`{bank}`\n\n"
        f"📝 **Catatan Kaki:**\n`{note}`\n\n"
        f"➖➖➖➖➖➖➖➖➖\n"
        f"💰 PPN (5%): **{ppn}**\n"
        f"📉 Pembulatan Nominal: **{math_rd}**\n"
    )

    buttons = [
        [Button.inline(f"📋 Kelola Roundown ({item_count})", b"sf_manage_items")],
        [Button.inline("✏️ Edit Bank", b"sf_edit_bank"), Button.inline("✏️ Edit Catatan", b"sf_edit_note")],
        [Button.inline(f"PPN: {ppn}", b"sf_toggle_ppn"), Button.inline(f"Bulatkan: {math_rd}", b"sf_toggle_rd")],
        [Button.inline("✅ Selesai", b"sf_done")]
    ]
    await safe_edit(event, text, buttons)

# --- MENU KELOLA ROUNDOWN ---
async def show_manage_items_menu(event, user_id):
    conf = get_settings(user_id)
    items = conf.get('default_items', [])
    
    text = "📋 **KELOLA ROUNDOWN LAYANAN**\n\n"
    buttons = []
    
    if not items:
        text += "_Belum ada layanan tersimpan._"
    else:
        for idx, item in enumerate(items):
            # Tampilkan list text
            text += f"{idx+1}. {item['desc']} | {item['price']:,}\n"
            # Buat tombol edit/hapus per item (Row)
            # Format Callback: sf_act_idx (act: ed=edit, del=delete)
            buttons.append([
                Button.inline(f"✏️ Edit No.{idx+1}", f"sf_itm_ed:{idx}"),
                Button.inline(f"🗑️ Hapus No.{idx+1}", f"sf_itm_del:{idx}")
            ])
    
    # Tombol Tambah & Kembali
    buttons.append([Button.inline("➕ Tambah Layanan Baru", b"sf_itm_add")])
    buttons.append([Button.inline("🔙 Kembali ke Menu", b"sf_menu_back")])
    
    await safe_edit(event, text, buttons)

# --- CALLBACKS PENGATURAN ---
@bot.on(events.CallbackQuery(pattern=b"sf_toggle_ppn"))
async def cb_sf_ppn(event):
    user_id = event.sender_id
    curr = get_settings(user_id).get('ppn', False)
    save_user_setting(user_id, 'ppn', not curr)
    await show_setting_menu(event, user_id)

@bot.on(events.CallbackQuery(pattern=b"sf_toggle_rd"))
async def cb_sf_rd(event):
    user_id = event.sender_id
    curr = get_settings(user_id).get('rounddown_math', False)
    save_user_setting(user_id, 'rounddown_math', not curr)
    await show_setting_menu(event, user_id)

@bot.on(events.CallbackQuery(pattern=b"sf_manage_items"))
async def cb_sf_manage(event):
    await show_manage_items_menu(event, event.sender_id)

@bot.on(events.CallbackQuery(pattern=b"sf_itm_add"))
async def cb_sf_itm_add(event):
    user_id = event.sender_id
    BOT_SETTING_STATE[user_id] = "WAIT_ITEM_ADD"
    msg = "➕ **Tambah Layanan Baru**\n\nFormat: `Nama Layanan | Harga`\nContoh: `Biaya Admin | 35000`\n\n_(Ketik 'batal' untuk kembali)_"
    await safe_edit(event, msg, buttons=[[Button.inline("🔙 Batal", b"sf_manage_items")]])

@bot.on(events.CallbackQuery(pattern=r"sf_itm_del:(.+)"))
async def cb_sf_itm_del(event):
    user_id = event.sender_id
    idx = int(event.data.decode().split(":")[1])
    
    conf = get_settings(user_id)
    items = conf.get('default_items', [])
    
    if 0 <= idx < len(items):
        deleted = items.pop(idx)
        save_user_setting(user_id, 'default_items', items)
        await event.answer(f"🗑️ Dihapus: {deleted['desc']}")
    else:
        await event.answer("❌ Item tidak ditemukan.", alert=True)
    
    await show_manage_items_menu(event, user_id)

@bot.on(events.CallbackQuery(pattern=r"sf_itm_ed:(.+)"))
async def cb_sf_itm_ed(event):
    user_id = event.sender_id
    idx = int(event.data.decode().split(":")[1])
    
    # Simpan index yang mau diedit di state
    BOT_SETTING_STATE[user_id] = f"WAIT_ITEM_EDIT:{idx}"
    
    conf = get_settings(user_id)
    items = conf.get('default_items', [])
    if 0 <= idx < len(items):
        item = items[idx]
        msg = (
            f"✏️ **Edit Layanan No.{idx+1}**\n"
            f"Saat ini: `{item['desc']} | {item['price']}`\n\n"
            f"Kirim format baru: `Nama Baru | Harga Baru`\n"
            f"_(Ketik 'batal' untuk kembali)_"
        )
        await safe_edit(event, msg, buttons=[[Button.inline("🔙 Batal", b"sf_manage_items")]])
    else:
        await show_manage_items_menu(event, user_id)

@bot.on(events.CallbackQuery(pattern=b"sf_edit_bank"))
async def cb_sf_bank(event):
    user_id = event.sender_id
    BOT_SETTING_STATE[user_id] = "WAIT_BANK"
    msg = "🏦 **Setting Info Bank**\nKirim Info Bank/E-Wallet.\n_(Ketik 'batal' kembali)_"
    await safe_edit(event, msg, buttons=[[Button.inline("🔙 Batal", b"sf_menu_back")]])

@bot.on(events.CallbackQuery(pattern=b"sf_edit_note"))
async def cb_sf_note(event):
    user_id = event.sender_id
    BOT_SETTING_STATE[user_id] = "WAIT_NOTE"
    msg = "📝 **Setting Catatan**\nKirim catatan kaki faktur.\n_(Ketik 'batal' kembali)_"
    await safe_edit(event, msg, buttons=[[Button.inline("🔙 Batal", b"sf_menu_back")]])

@bot.on(events.CallbackQuery(pattern=b"sf_menu_back"))
async def cb_sf_back(event):
    user_id = event.sender_id
    if user_id in BOT_SETTING_STATE: del BOT_SETTING_STATE[user_id]
    await show_setting_menu(event, user_id)

@bot.on(events.CallbackQuery(pattern=b"sf_done"))
async def cb_sf_done(event):
    try: await event.delete()
    except: pass

# --- CALLBACK UNTUK PINDAH KE MENU SETTING DARI TOMBOL FAKTUR ---
@bot.on(events.CallbackQuery(pattern=b"goto_set_faktur"))
async def cb_goto_set_faktur(event):
    user_id = event.sender_id
    # Hapus pesan faktur start sebelumnya jika perlu, atau edit saja
    await show_setting_menu(event, user_id)

@bot.on(events.NewMessage(incoming=True))
async def bot_setting_listener(event):
    user_id = event.sender_id
    if user_id not in BOT_SETTING_STATE: return
    
    state_raw = BOT_SETTING_STATE[user_id]
    # Parse state (misal: WAIT_ITEM_EDIT:2)
    if ":" in state_raw:
        state, param = state_raw.split(":")
    else:
        state, param = state_raw, None

    text = event.text.strip()
    
    # Tombol Batal
    if text.lower() == 'batal':
        del BOT_SETTING_STATE[user_id]
        if "ITEM" in state:
            await show_manage_items_menu(event, user_id)
        else:
            await show_setting_menu(event, user_id)
        return

    # --- LOGIKA TAMBAH ITEM ---
    if state == "WAIT_ITEM_ADD":
        if '|' in text:
            parts = text.rsplit('|', 1)
            desc = parts[0].strip()
            price_str = parts[1].strip().replace('.', '').replace(',', '')
            
            if price_str.isdigit():
                conf = get_settings(user_id)
                items = conf.get('default_items', [])
                items.append({'desc': desc, 'price': int(price_str)})
                save_user_setting(user_id, 'default_items', items)
                
                await event.reply(f"✅ **Ditambahkan:** {desc}")
                del BOT_SETTING_STATE[user_id]
                
                # Refresh Menu
                msg = await event.reply("🔄 Memuat...")
                await show_manage_items_menu(msg, user_id)
            else:
                await event.reply("⚠️ Harga harus angka.")
        else:
            await event.reply("⚠️ Format salah. Contoh: `Admin | 20000`")

    # --- LOGIKA EDIT ITEM ---
    elif state == "WAIT_ITEM_EDIT":
        idx = int(param)
        if '|' in text:
            parts = text.rsplit('|', 1)
            desc = parts[0].strip()
            price_str = parts[1].strip().replace('.', '').replace(',', '')
            
            if price_str.isdigit():
                conf = get_settings(user_id)
                items = conf.get('default_items', [])
                
                if 0 <= idx < len(items):
                    items[idx] = {'desc': desc, 'price': int(price_str)}
                    save_user_setting(user_id, 'default_items', items)
                    await event.reply(f"✅ **Diupdate:** {desc}")
                
                del BOT_SETTING_STATE[user_id]
                msg = await event.reply("🔄 Memuat...")
                await show_manage_items_menu(msg, user_id)
            else:
                await event.reply("⚠️ Harga harus angka.")
        else:
            await event.reply("⚠️ Format salah. Contoh: `Admin Baru | 25000`")

    # --- LOGIKA BANK ---
    elif state == "WAIT_BANK":
        save_user_setting(user_id, 'template_bank', text)
        await event.reply("✅ Bank tersimpan!")
        del BOT_SETTING_STATE[user_id]
        msg = await event.reply("🔄 Memuat...")
        await show_setting_menu(msg, user_id)

    # --- LOGIKA CATATAN ---
    elif state == "WAIT_NOTE":
        save_user_setting(user_id, 'template_note', text)
        await event.reply("✅ Catatan tersimpan!")
        del BOT_SETTING_STATE[user_id]
        msg = await event.reply("🔄 Memuat...")
        await show_setting_menu(msg, user_id)


# ==========================================
# 3. USERBOT HANDLERS (EKSEKUSI)
# ==========================================

async def register(client, user_id, is_allowed, check_status, help_dict):
    help_dict[".faktur"] = {"title": "Buat Invoice 📄", "usage": "Eksekusi Roundown Otomatis."}
    help_dict[".set_faktur"] = {"title": "Atur Faktur ⚙️", "usage": "Setting Roundown."}

    @client.on(events.NewMessage(pattern=r"(?i)^\.set_faktur$"))
    async def set_faktur_cmd(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        try: await event.delete()
        except: pass
        try:
            msg = await bot.send_message(user_id, "🔄 **Memuat Pengaturan...**")
            await show_setting_menu(msg, user_id)
        except Exception as e:
            await client.send_message("me", f"⚠️ Gagal membuka menu.\nError: {e}")

    # --- START FAKTUR ---
    @client.on(events.NewMessage(pattern=r"(?i)^\.faktur$"))
    async def faktur_start(event):
        me = await client.get_me()
        if event.sender_id != me.id: return
        if not await check_status(client, user_id, event): return
        if not is_allowed("faktur"): return await event.edit("🔒 Terkunci.")

        conf = get_settings(user_id)
        items = conf.get('default_items', [])
        
        if not items:
            return await event.edit("⚠️ **Roundown Kosong.**\nSilakan set di `.set_faktur` dulu.")

        # Buat folder penyimpanan
        user_storage = os.path.join(BASE_STORAGE_DIR, str(event.chat_id))
        if not os.path.exists(user_storage):
            os.makedirs(user_storage)

        FAKTUR_SESSION[event.chat_id] = {
            'queue': list(items),
            'current_idx': 0,
            'client_data': {},
            'step': 'WAIT_SS', 
            'storage': user_storage
        }
        
        # === MODIFIKASI: Menambahkan Tombol .set_faktur ===
        await event.edit(
            "📸 **VERIFIKASI DEVICE**\n\n"
            "Mohon kirimkan **Screenshot Tampilan HP** Anda sekarang sebelum melanjutkan.\n\n"
            "_.faktur (cara pakai)_\n"
            "_.set_faktur (tombol di bawah)_",
            buttons=[[Button.inline("⚙️ Atur Faktur (.set_faktur)", b"goto_set_faktur")]]
        )

    # --- LISTENER INPUT ---
    @client.on(events.NewMessage()) 
    async def faktur_listener(event):
        cid = event.chat_id
        if cid not in FAKTUR_SESSION: return
        
        me = await client.get_me()
        is_owner = event.out
        text = event.text.strip()
        sess = FAKTUR_SESSION[cid]
        step = sess['step']
        storage = sess['storage']

        # 1. OWNER ACTIONS
        if is_owner:
            if text.lower() == '.batal':
                if os.path.exists(storage):
                    shutil.rmtree(storage)
                del FAKTUR_SESSION[cid]
                await event.reply("❌ **Sesi Dibatalkan & Data Dihapus.**")
                return
            
            if step == 'WAIT_CONFIRM' and text.lower() == '.ok':
                try: await event.delete() 
                except: pass
                
                await event.respond("⏳ **Mohon tunggu langkah selanjutnya...**")
                asyncio.create_task(process_next_item(client, user_id, cid))
                return

        # 2. CLIENT INPUT
        if not is_owner:
            if step == 'WAIT_SS':
                if event.photo:
                    try:
                        ss_path = os.path.join(storage, "screenshot.jpg")
                        await event.download_media(file=ss_path)
                        
                        await bot.send_file(
                            user_id,
                            file=ss_path,
                            caption=f"📸 **Verifikasi Screenshot Klien**\nChat ID: `{cid}`\n\nIzinkan lanjut?",
                            buttons=[
                                [Button.inline("✅ Lanjut", f"fkt_ok:{cid}"), Button.inline("❌ Ulang", f"fkt_no:{cid}")]
                            ]
                        )
                        
                        sess['step'] = 'WAIT_SS_VERIF' 
                        await event.reply("⏳ **Screenshot diterima. Mohon tunggu verifikasi admin...**")
                        
                    except Exception as e:
                        await event.reply(f"⚠️ Gagal simpan gambar: {e}")

            elif step == 'WAIT_NAME':
                sess['client_data']['nama'] = text
                sess['step'] = 'WAIT_EMAIL'
                await event.reply("✅ **Nama OK.**\n📧 Ketik **EMAIL:**")

            elif step == 'WAIT_EMAIL':
                sess['client_data']['email'] = text
                sess['step'] = 'WAIT_HP'
                await event.reply("✅ **Email OK.**\n📱 Ketik **NO HP:**")

            elif step == 'WAIT_HP':
                sess['client_data']['hp'] = text
                sess['step'] = 'PROCESSING'
                await event.reply("✅ **Data Lengkap.**\n⏳ **Tunggu Kami sedang membuat faktur..**")
                asyncio.create_task(process_next_item(client, user_id, cid))

async def process_next_item(client, user_id, cid):
    if cid not in FAKTUR_SESSION: return
    sess = FAKTUR_SESSION[cid]
    idx = sess['current_idx']
    queue = sess['queue']
    storage = sess['storage']
    
    if idx >= len(queue):
        await client.send_message(cid, "✅ **Semua Faktur Selesai!**\n_Terima kasih telah order._")
        try:
            if os.path.exists(storage):
                shutil.rmtree(storage)
        except Exception as e:
            print(f"Error deleting folder: {e}")
            
        del FAKTUR_SESSION[cid]
        return

    item = queue[idx]
    conf = get_settings(user_id)
    cdata = sess['client_data']
    
    loop = asyncio.get_running_loop()

    try:
        subtotal = item['price']
        ppn = 0
        if conf.get('ppn'): ppn = subtotal * 0.05
        
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
        if conf.get('ppn'):
            caption += f"PPN (5%): **Rp {int(ppn):,}**\n"
        
        caption += f"💰 **TOTAL: Rp {int(total_final):,}**\n\n"
        caption += f"⏳ _Menunggu verifikasi admin..._"
        
        await client.send_file(cid, file=pdf_path, caption=caption)
        
        sess['current_idx'] += 1
        sess['step'] = 'WAIT_CONFIRM'
        
    except Exception as e:
        await client.send_message(cid, f"❌ Terjadi kesalahan: {e}")