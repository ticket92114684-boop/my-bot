import asyncio
import json
import os
import re
import time
import csv
import io
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)
from playwright.async_api import async_playwright

# ========== CONFIG — APNI ID DAALO ==========
BOT_TOKEN       = "8936294237:AAFJ-uEwsj2WdLTGgpO2V_5Abp7z7BAjksY"
CHANNEL_ID      = -1001234567890   # apna channel ID daalo
CHANNEL_ID2     = -1009876543210   # apna channel ID daalo
ADMIN_ID        = 8473160748
PANEL_USER      = "xyz@gmail.com"
PANEL_PASS      = "Sanju@71"
POLL_INTERVAL   = 12
AUTO_RELEASE_H  = 24

LOGIN_URL       = "https://livestatspanel.com/index.php"
SMS_URL         = "https://livestatspanel.com/index.php?opt=shw_sms_tod&lang=EN"

auth_state_file = "auth_state.json"
numbers_file    = "numbers.json"
seen_messages   = set()
bot_ref         = None
last_alert_time = 0
screenshot_dir  = "screenshots"
os.makedirs(screenshot_dir, exist_ok=True)

# ========== NUMBER DB ==========
numbers_db = {}
def load_numbers():
    global numbers_db
    try:
        if os.path.exists(numbers_file):
            with open(numbers_file) as f: numbers_db = json.load(f)
    except: numbers_db = {}
def save_numbers():
    try:
        with open(numbers_file, 'w') as f: json.dump(numbers_db, f, indent=2)
    except: pass

def get_free_number():
    for n, d in numbers_db.items():
        if d.get("status") == "free": return n, d
    return None, None
def allocate_number(uid, uname):
    n, d = get_free_number()
    if not n: return None
    numbers_db[n] = {"status":"allocated","user_id":uid,"username":uname,"allocated_at":time.time(),"range":d.get("range","N/A")}
    save_numbers()
    return n
def get_user_number(uid):
    for n, d in numbers_db.items():
        if d.get("status")=="allocated" and d.get("user_id")==uid: return n, d
    return None, None
def release_number(uid):
    n, d = get_user_number(uid)
    if n:
        numbers_db[n] = {"status":"free","range":d.get("range","N/A")}
        save_numbers()
        return n
    return None
def force_free_number(n):
    if n in numbers_db:
        numbers_db[n] = {"status":"free","range":numbers_db[n].get("range","N/A")}
        save_numbers()
        return True
    return False
def add_number(num, rng="N/A"):
    num = re.sub(r'\D','',num)
    if len(num)<10: return False
    if num not in numbers_db:
        numbers_db[num] = {"status":"free","range":rng}
        save_numbers()
        return True
    return False
def delete_number(num):
    num = re.sub(r'\D','',num)
    if num in numbers_db: del numbers_db[num]; save_numbers(); return True
    return False
def get_stats():
    t=len(numbers_db); f=sum(1 for d in numbers_db.values() if d.get("status")=="free"); return t,f,t-f
def auto_release_check():
    now=time.time(); rel=0
    for n,d in list(numbers_db.items()):
        if d.get("status")=="allocated" and now-d.get("allocated_at",0) > AUTO_RELEASE_H*3600:
            numbers_db[n] = {"status":"free","range":d.get("range","N/A")}; rel+=1
    if rel>0: save_numbers()
    return rel

# ========== JOIN CHECK ==========
async def check_subscription(uid:int)->bool:
    try:
        for ch in [CHANNEL_ID,CHANNEL_ID2]:
            m = await bot_ref.get_chat_member(chat_id=ch, user_id=uid)
            if m.status in ['left','kicked','banned']:
                print(f"❌ User {uid} not in {ch}", flush=True)
                return False
        return True
    except Exception as e:
        print(f"⚠️ Check err: {e} — allow", flush=True)
        return True
def get_join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel 1", url=f"https://t.me/c/{str(CHANNEL_ID).replace('-100','')}")],
        [InlineKeyboardButton("📢 Join Channel 2", url=f"https://t.me/c/{str(CHANNEL_ID2).replace('-100','')}")],
        [InlineKeyboardButton("✅ Joined - Check Again", callback_data="check_join")]
    ])

# ========== SCREENSHOT HELPER ==========
async def take_screenshot(name:str):
    """Login ke baad screenshot leke admin ko bheje"""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"{screenshot_dir}/{name}_{ts}.png"
        await page.screenshot(path=path, full_page=True)
        with open(path, 'rb') as f:
            await bot_ref.send_photo(chat_id=ADMIN_ID, photo=f, caption=f"📸 {name}")
        os.remove(path)
        print(f"📸 Screenshot sent: {name}", flush=True)
    except Exception as e:
        print(f"📸 Screenshot err: {e}", flush=True)

# ========== BROWSER — MAX ANTI-DETECT ==========
pw = browser = context = page = None

async def save_auth_state():
    try: await context.storage_state(path=auth_state_file); print("💾 Session saved", flush=True)
    except Exception as e: print(f"Save err: {e}", flush=True)

async def start_browser():
    global pw, browser, context, page
    try:
        if page: await page.close()
        if context: await context.close()
        if browser: await browser.close()
        if pw: await pw.stop()
    except: pass

    if os.path.exists(auth_state_file):
        try: os.remove(auth_state_file)
        except: pass

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True, args=[
        '--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage',
        '--disable-gpu','--disable-blink-features=AutomationControlled',
        '--start-maximized'
    ])
    context = await browser.new_context(
        viewport={'width':1366,'height':768},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        locale='en-US',
        timezone_id='Asia/Kolkata'
    )
    # Anti-detect scripts
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        window.chrome = {runtime: {}};
    """)
    await context.route("**/*",lambda r: r.abort() if r.request.resource_type in ['image','stylesheet','font','media'] else r.continue_())
    page = await context.new_page()
    print("🌐 Browser ready", flush=True)

async def do_login():
    global page
    try:
        print("🔐 Login start...", flush=True)
        await page.goto(LOGIN_URL, timeout=30000, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        await take_screenshot("login_page")
        
        inp_user = page.locator('input[type="text"], input[name*="user"], input[name*="email"]').first
        await inp_user.click(timeout=5000)
        await inp_user.fill(PANEL_USER)
        await asyncio.sleep(1)
        
        inp_pass = page.locator('input[type="password"]').first
        await inp_pass.click(timeout=5000)
        await inp_pass.fill(PANEL_PASS)
        await asyncio.sleep(1.5)
        
        btn = page.locator('button:has-text("Login"), input[type="submit"], button[type="submit"]').first
        await btn.click()
        
        await page.wait_for_load_state('networkidle', timeout=20000)
        await asyncio.sleep(3)
        
        await take_screenshot("after_login")
        
        await save_auth_state()
        
        if 'shw_sms_tod' in page.url or await check_login():
            print("✅ LOGIN SUCCESS", flush=True)
            await take_screenshot("sms_page")
            return True
        else:
            print("❌ Login par redirect nahi hua", flush=True)
            return False
    except Exception as e:
        print(f"❌ Login error: {e}", flush=True)
        await take_screenshot("login_error")
        return False

async def check_login():
    try:
        res = await page.goto(SMS_URL, timeout=20000, wait_until='domcontentloaded')
        await asyncio.sleep(1.5)
        url = page.url.lower()
        txt = await page.content()
        
        if 'login' in url or 'please enter your login' in txt.lower() or 'login here' in txt.lower():
            print(f"🔴 Session expired — URL: {page.url}", flush=True)
            await take_screenshot("session_expired")
            return False
        return True
    except Exception as e:
        print(f"Check err: {e}", flush=True)
        return False

# ========== HELPERS ==========
async def safe_send(cid, txt):
    for _ in range(2):
        try: await bot_ref.send_message(cid, txt, parse_mode="Markdown", read_timeout=20); return True
        except: await asyncio.sleep(1)
    return False
def mask(p): return p.strip() if len(p)<=6 else f"{p[:4]}*****{p[-3:]}"
def extract_otp(t):
    m = re.search(r'\b(\d{4,8})\b',t); return m.group(1) if m else "N/A"

# ========== MAIN POLLER ==========
async def run_poller():
    global seen_messages
    await start_browser()
    
    if not await check_login():
        await do_login()
    
    print(f"✅ ONLINE — {POLL_INTERVAL}s check", flush=True)
    await safe_send(ADMIN_ID, f"✅ Bot chalu!\n⏱️ {POLL_INTERVAL}s\n🔢 {len(numbers_db)}\n📸 Screenshot ON")
    
    err = crash = 0
    while True:
        try:
            if int(time.time())%60 < POLL_INTERVAL and auto_release_check():
                print("🔄 Auto-release done", flush=True)
            
            if not await check_login():
                print("🔄 Session expired — Re-login...", flush=True)
                await start_browser()
                await do_login()
                continue
            
            rows = page.locator('table tbody tr')
            total = await rows.count()
            
            for i in range(total):
                cols = rows.nth(i).locator('td')
                if await cols.count()<7: continue
                num = (await cols.nth(0).inner_text()).strip()
                rng = (await cols.nth(1).inner_text()).strip()
                sender = (await cols.nth(2).inner_text()).strip()
                
                try: await cols.nth(6).click()
                except: continue
                await asyncio.sleep(0.8)
                
                try:
                    drows = page.locator('table tbody tr')
                    dj = await drows.count()
                    for j in range(dj):
                        dc = drows.nth(j).locator('td')
                        if await dc.count()>=4:
                            dt = (await dc.nth(0).inner_text()).strip()
                            ph = (await dc.nth(1).inner_text()).strip()
                            se = (await dc.nth(2).inner_text()).strip()
                            ms = (await dc.nth(3).inner_text()).strip()
                            if ms and dt:
                                key = f"{dt}|{ph}|{ms[:40]}"
                                if key not in seen_messages:
                                    seen_messages.add(key)
                                    otp = extract_otp(ms)
                                    txt = f"🔐 *NEW OTP*\n📱 `{mask(ph)}`\n🕐 {dt}\n✉️ {se}\n🔢 `{otp}`\n📝 {ms[:300]}"
                                    await safe_send(CHANNEL_ID, txt)
                                    await safe_send(CHANNEL_ID2, txt)
                                    ph_clean = re.sub(r'\D','',ph)
                                    if ph_clean in numbers_db and numbers_db[ph_clean].get("status")=="allocated":
                                        uid = numbers_db[ph_clean].get("user_id")
                                        if uid: await safe_send(uid, f"🔐 *APNA OTP*\n📱 `{mask(ph)}`\n🔢 `{otp}`\n✉️ {se}\n📝 {ms[:200]}")
                                    print(f"✅ SENT — {otp}", flush=True)
                    await page.go_back()
                    await asyncio.sleep(0.3)
                except:
                    try: await page.goto(SMS_URL, timeout=15000)
                    except: pass
            
            if len(seen_messages)>500: seen_messages=set(list(seen_messages)[-250:])
            err=0
            
        except Exception as e:
            err+=1; print(f"Err {err}/5: {e}", flush=True)
            if 'closed' in str(e).lower() or 'crash' in str(e).lower():
                crash+=1; await start_browser()
                if not await check_login(): await do_login()
                if crash>=3: print("⚠️ Restarting...", flush=True); crash=0
            if err>=5:
                print("🔄 Recovery...", flush=True)
                try: await start_browser(); await do_login()
                except: pass
                err=0
        await asyncio.sleep(POLL_INTERVAL)

# ========== COMMANDS ==========
async def start_cmd(u:Update,c:ContextTypes):
    if not await check_subscription(u.effective_user.id):
        await u.message.reply_text("⚠️ Pehle join karein!", reply_markup=get_join_keyboard(), parse_mode="Markdown")
        return
    n,d = get_user_number(u.effective_user.id)
    if n: await u.message.reply_text(f"✅ Welcome!\n📱 `{n}`\n🌍 {d.get('range','N/A')}", parse_mode="Markdown")
    else: await u.message.reply_text("✅ /getnumber se number le")

async def check_join_cb(u:Update,c:ContextTypes):
    await u.callback_query.answer()
    if await check_subscription(u.callback_query.from_user.id):
        await u.callback_query.edit_message_text("✅ Join done! /getnumber le lo", parse_mode="Markdown")
    else:
        await u.callback_query.edit_message_text("❌ Abhi join nahi hue", reply_markup=get_join_keyboard(), parse_mode="Markdown")

async def getnumber_cmd(u:Update,c:ContextTypes):
    if not await check_subscription(u.effective_user.id):
        await u.message.reply_text("⚠️ Pehle join karein!", reply_markup=get_join_keyboard())
        return
    n,_ = get_user_number(u.effective_user.id)
    if n: await u.message.reply_text(f"⚠️ Already: `{n}`\n/release pehle", parse_mode="Markdown"); return
    n = allocate_number(u.effective_user.id, u.effective_user.username or u.effective_user.first_name)
    if n: await u.message.reply_text(f"🎉 Allocated!\n📱 `{n}`", parse_mode="Markdown")
    else: await u.message.reply_text("😔 Free nahi")

async def mynumber_cmd(u:Update,c:ContextTypes):
    n,d = get_user_number(u.effective_user.id)
    if n: await u.message.reply_text(f"📱 `{n}`\n🌍 {d.get('range','N/A')}")
    else: await u.message.reply_text("❌ /getnumber le lo")

async def release_cmd(u:Update,c:ContextTypes):
    n = release_number(u.effective_user.id)
    await u.message.reply_text(f"✅ `{n}` free" if n else "❌ Nahi hai")

async def status_cmd(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    t,f,a = get_stats()
    await u.message.reply_text(f"📊 Total:{t} Free:{f} Used:{a}")

async def addnumber_cmd(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    p = u.message.text.split()
    if len(p)<2: await u.message.reply_text("/addnumber 1234567890 IND"); return
    if add_number(p[1], p[2] if len(p)>2 else "N/A"): await u.message.reply_text("✅ Added")
    else: await u.message.reply_text("❌ Failed")

async def delnumber_cmd(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    if delete_number(u.message.text.split()[1]): await u.message.reply_text("✅ Deleted")
    else: await u.message.reply_text("❌ Nahi mila")

async def forcefree_cmd(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    if force_free_number(u.message.text.split()[1]): await u.message.reply_text("✅ Free")
    else: await u.message.reply_text("❌ Nahi mila")

async def freenumbers_cmd(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    free = [(n,d) for n,d in numbers_db.items() if d.get("status")=="free"]
    if not free: await u.message.reply_text("❌ Free nahi"); return
    txt = "🆓 Free:\n"
    for n,d in free[:50]: txt += f"`{n}` — {d.get('range')}\n"
    await u.message.reply_text(txt, parse_mode="Markdown")

async def reloadnumbers_cmd(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    load_numbers(); t,f,a = get_stats()
    await u.message.reply_text(f"✅ Reloaded: {t} total")

async def restart_cmd(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    await u.message.reply_text("🔄 Restart...")
    await start_browser()
    if not await check_login(): await do_login()
    await u.message.reply_text("✅ Done")

async def relogin_cmd(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    try: os.remove(auth_state_file)
    except: pass
    await start_browser()
    await do_login()
    await u.message.reply_text("✅ Fresh login!")

async def handle_doc(u:Update,c:ContextTypes):
    if u.effective_user.id!=ADMIN_ID: return
    doc = u.message.document
    if not doc.file_name or not doc.file_name.lower().endswith('.csv'): return
    await u.message.reply_text("📤 Processing...")
    try:
        f = await doc.get_file()
        data = await f.download_as_bytearray()
        added=skip=0
        for row in csv.reader(io.StringIO(data.decode('utf-8','ignore'))):
            if not row or not row[0].strip(): continue
            num = re.sub(r'\D','',row[0].strip())
            rng = row[1].strip() if len(row)>1 else "N/A"
            if len(num)>=10:
                if add_number(num,rng): added+=1
                else: skip+=1
            else: skip+=1
        await u.message.reply_text(f"✅ Added:{added} Skip:{skip}")
    except Exception as e: await u.message.reply_text(f"❌ {e}")

# ========== MAIN ==========
async def main():
    global bot_ref
    load_numbers()
    print(f"📱 {len(numbers_db)} numbers", flush=True)
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).build()
    bot_ref = app.bot
    
    app.add_handler(CallbackQueryHandler(check_join_cb, pattern="check_join"))
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("getnumber", getnumber_cmd))
    app.add_handler(CommandHandler("mynumber", mynumber_cmd))
    app.add_handler(CommandHandler("release", release_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("addnumber", addnumber_cmd))
    app.add_handler(CommandHandler("delnumber", delnumber_cmd))
    app.add_handler(CommandHandler("forcefree", forcefree_cmd))
    app.add_handler(CommandHandler("freenumbers", freenumbers_cmd))
    app.add_handler(CommandHandler("reloadnumbers", reloadnumbers_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CommandHandler("relogin", relogin_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    asyncio.create_task(run_poller())
    print("🚀 STARTED", flush=True)
    await asyncio.Event().wait()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("STOPPED")
