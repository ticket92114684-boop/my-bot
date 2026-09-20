import asyncio
import json
import os
import re
import time
import csv
import io
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, Document, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)
from playwright.async_api import async_playwright

# ========== LOAD ENV ==========
load_dotenv()

BOT_TOKEN       = os.getenv("BOT_TOKEN", "")
CHANNEL_ID      = os.getenv("CHANNEL_ID", "@dolaotp")
CHANNEL_ID2     = os.getenv("CHANNEL_ID2", "@methodsbytoji")
ADMIN_ID        = int(os.getenv("ADMIN_ID", "8473160748"))
PANEL_USER      = os.getenv("PANEL_USER", "")
PANEL_PASS      = os.getenv("PANEL_PASS", "")
POLL_INTERVAL   = int(os.getenv("POLL_INTERVAL", "10"))
AUTO_RELEASE_H  = int(os.getenv("AUTO_RELEASE_HOURS", "24"))

LOGIN_URL       = "https://livestatspanel.com/index.php"
SMS_URL         = "https://livestatspanel.com/index.php?opt=shw_sms_tod&lang=EN"

cookies_file    = "panel_cookies.json"
numbers_file    = "numbers.json"
seen_messages   = set()
bot_ref         = None
last_alert_time = 0

# ========== NUMBER MANAGEMENT ==========
numbers_db = {}

def load_numbers():
    global numbers_db
    try:
        if os.path.exists(numbers_file):
            with open(numbers_file) as f:
                numbers_db = json.load(f)
    except:
        numbers_db = {}

def save_numbers():
    try:
        with open(numbers_file, 'w') as f:
            json.dump(numbers_db, f, indent=2)
    except:
        pass

def get_free_number():
    for num, data in numbers_db.items():
        if data.get("status") == "free":
            return num, data
    return None, None

def allocate_number(user_id, username):
    num, data = get_free_number()
    if not num:
        return None
    numbers_db[num] = {
        "status": "allocated",
        "user_id": user_id,
        "username": username,
        "allocated_at": time.time(),
        "range": data.get("range", "N/A")
    }
    save_numbers()
    return num

def get_user_number(user_id):
    for num, data in numbers_db.items():
        if data.get("status") == "allocated" and data.get("user_id") == user_id:
            return num, data
    return None, None

def release_number(user_id):
    num, data = get_user_number(user_id)
    if num:
        numbers_db[num] = {
            "status": "free",
            "range": data.get("range", "N/A")
        }
        save_numbers()
        return num
    return None

def force_free_number(num):
    num = re.sub(r'\D', '', num)
    if num in numbers_db:
        numbers_db[num] = {
            "status": "free",
            "range": numbers_db[num].get("range", "N/A")
        }
        save_numbers()
        return True
    return False

def add_number(num, rng="N/A"):
    num = re.sub(r'\D', '', num)
    if len(num) < 10:
        return False
    if num not in numbers_db:
        numbers_db[num] = {"status": "free", "range": rng}
        save_numbers()
        return True
    return False

def delete_number(num):
    num = re.sub(r'\D', '', num)
    if num in numbers_db:
        del numbers_db[num]
        save_numbers()
        return True
    return False

def get_stats():
    total = len(numbers_db)
    free = sum(1 for d in numbers_db.values() if d.get("status") == "free")
    allocated = total - free
    return total, free, allocated

def auto_release_check():
    now = time.time()
    released = 0
    for num, data in list(numbers_db.items()):
        if data.get("status") == "allocated":
            alloc_time = data.get("allocated_at", 0)
            if now - alloc_time > (AUTO_RELEASE_H * 3600):
                numbers_db[num] = {"status": "free", "range": data.get("range", "N/A")}
                released += 1
    if released > 0:
        save_numbers()
    return released

# ========== FORCE SUBSCRIBE CHECK ==========
async def check_subscription(user_id: int) -> bool:
    try:
        for ch in [CHANNEL_ID, CHANNEL_ID2]:
            member = await bot_ref.get_chat_member(ch, user_id)
            if member.status in ['left', 'kicked']:
                return False
        return True
    except:
        return False

def get_join_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel 1", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")],
        [InlineKeyboardButton("📢 Join Channel 2", url=f"https://t.me/{CHANNEL_ID2.replace('@','')}")],
        [InlineKeyboardButton("✅ Joined - Check Again", callback_data="check_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== BROWSER MANAGEMENT ==========
pw = None
browser = None
context = None
page = None

async def start_browser():
    global pw, browser, context, page
    try:
        if page: await page.close()
        if context: await context.close()
        if browser: await browser.close()
        if pw: await pw.stop()
    except: pass

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
              '--disable-gpu', '--disable-blink-features=AutomationControlled',
              '--disable-extensions', '--no-first-run', '--no-zygote']
    )
    context = await browser.new_context(
        viewport={'width': 1024, 'height': 768},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        window.chrome = {runtime: {}};
    """)
    await context.route("**/*", lambda route:
        route.abort() if route.request.resource_type in ['image', 'stylesheet', 'font', 'media'] else route.continue_()
    )
    page = await context.new_page()
    try:
        with open(cookies_file) as f:
            await context.add_cookies(json.load(f))
    except: pass
    print("🌐 Browser started (memory optimized)", flush=True)

async def save_cookies():
    try:
        with open(cookies_file, 'w') as f:
            json.dump(await context.cookies(), f)
    except: pass

async def do_login():
    try:
        print("🔐 Logging in...", flush=True)
        await page.goto(LOGIN_URL, timeout=25000, wait_until='domcontentloaded')
        await asyncio.sleep(1.2)
        u = page.locator('input[type="text"]').first
        await u.click()
        await asyncio.sleep(0.2)
        await u.fill(PANEL_USER)
        await asyncio.sleep(0.3)
        p = page.locator('input[type="password"]').first
        await p.click()
        await asyncio.sleep(0.2)
        await p.fill(PANEL_PASS)
        await asyncio.sleep(0.3)
        await page.locator('button, input[type="submit"]').first.click()
        await asyncio.sleep(2)
        await save_cookies()
        print("✅ Login OK", flush=True)
        return True
    except Exception as e:
        print(f"❌ Login failed: {e}", flush=True)
        return False

async def check_login():
    try:
        await page.goto(SMS_URL, timeout=20000, wait_until='domcontentloaded')
        await asyncio.sleep(0.6)
        content = await page.content()
        if 'Please enter your login details' in content or 'Login Here' in content:
            return False
        return True
    except Exception as e:
        if 'crashed' in str(e).lower() or 'closed' in str(e).lower():
            return None
        return False

# ========== HELPER FUNCTIONS ==========
async def safe_send(chat_id, text):
    for _ in range(3):
        try:
            await bot_ref.send_message(chat_id, text, parse_mode="Markdown", read_timeout=15, write_timeout=15)
            return True
        except:
            await asyncio.sleep(1)
    return False

async def admin_alert(text):
    global last_alert_time
    now = time.time()
    if now - last_alert_time < 3600:
        return
    last_alert_time = now
    await safe_send(ADMIN_ID, text)

def mask(p):
    p = p.strip()
    return p if len(p) <= 6 else f"{p[:4]}*****{p[-3:]}"

def extract_otp(t):
    m = re.search(r'\b(\d{4,8})\b', t)
    return m.group(1) if m else "N/A"

# ========== MAIN POLLER ==========
async def run_poller():
    global seen_messages

    await start_browser()

    status = await check_login()
    if status == False:
        await do_login()
    elif status is None:
        await start_browser()
        await do_login()

    print(f"✅ BOT ONLINE — Har {POLL_INTERVAL}s check", flush=True)
    await safe_send(ADMIN_ID, f"✅ Bot chalu hai!\n⏱️ Har {POLL_INTERVAL}s check\n🔢 Numbers: {len(numbers_db)}")

    err_count = 0
    crash_count = 0

    while True:
        try:
            if int(time.time()) % 60 < POLL_INTERVAL:
                released = auto_release_check()
                if released > 0:
                    print(f"🔄 Auto-released {released} numbers", flush=True)

            try:
                await page.goto(SMS_URL, timeout=20000, wait_until='domcontentloaded')
                await asyncio.sleep(0.5)
            except Exception as e:
                if 'crashed' in str(e).lower() or 'closed' in str(e).lower():
                    crash_count += 1
                    print(f"💥 Page crashed ({crash_count}) — restarting browser...", flush=True)
                    await start_browser()
                    await do_login()
                    if crash_count >= 3:
                        await admin_alert(f"⚠️ Browser baar-baar crash ho raha ({crash_count} baar)")
                        crash_count = 0
                    await asyncio.sleep(5)
                    continue
                raise

            crash_count = 0
            content = await page.content()
            if 'Please enter your login details' in content or 'Login Here' in content:
                print("🔄 Session expired — re-login", flush=True)
                ok = await do_login()
                if not ok:
                    await asyncio.sleep(5)
                    continue
                await page.goto(SMS_URL, timeout=20000, wait_until='domcontentloaded')
                await asyncio.sleep(0.5)

            rows = page.locator('table tbody tr')
            total = await rows.count()
            print(f"📊 Check: {total} rows", flush=True)

            for i in range(total):
                row = rows.nth(i)
                cols = row.locator('td')
                if await cols.count() < 7:
                    continue

                num = (await cols.nth(0).inner_text()).strip()
                num_clean = re.sub(r'\D', '', num)
                rng = (await cols.nth(1).inner_text()).strip()
                sender = (await cols.nth(2).inner_text()).strip()

                clicked = False
                detail_cell = cols.nth(6)
                form = detail_cell.locator('form').first
                if await form.count() > 0:
                    try:
                        await form.click()
                        clicked = True
                    except:
                        pass
                if not clicked:
                    btn = detail_cell.locator('button, input[type="submit"]').first
                    if await btn.count() > 0:
                        try:
                            await btn.click()
                            clicked = True
                        except:
                            pass
                if not clicked:
                    try:
                        await detail_cell.click()
                        clicked = True
                    except:
                        pass
                if not clicked:
                    continue

                try:
                    await page.wait_for_load_state('domcontentloaded', timeout=8000)
                    await asyncio.sleep(0.7)

                    detail_rows = page.locator('table tbody tr')
                    for j in range(await detail_rows.count()):
                        dcols = detail_rows.nth(j).locator('td')
                        if await dcols.count() >= 4:
                            dt = (await dcols.nth(0).inner_text()).strip()
                            ph = (await dcols.nth(1).inner_text()).strip()
                            se = (await dcols.nth(2).inner_text()).strip()
                            ms = (await dcols.nth(-1).inner_text()).strip()

                            if ms and len(ms) > 3 and dt:
                                key = f"{dt}|{ph}|{ms[:40]}"
                                if key not in seen_messages:
                                    seen_messages.add(key)
                                    otp = extract_otp(ms)
                                    masked = mask(ph)

                                    text = (f"🔐 *NEW OTP RECEIVED*\n"
                                            f"📱 Phone: `{masked}`\n"
                                            f"🕐 Time: {dt}\n"
                                            f"✉️ Sender: `{se}`\n"
                                            f"🔢 Code: `{otp}`\n"
                                            f"📝 Message:\n`{ms[:300]}`")

                                    await safe_send(CHANNEL_ID, text)
                                    await safe_send(CHANNEL_ID2, text)

                                    ph_clean = re.sub(r'\D', '', ph)
                                    if ph_clean in numbers_db and numbers_db[ph_clean].get("status") == "allocated":
                                        uid = numbers_db[ph_clean].get("user_id")
                                        if uid:
                                            user_text = (f"🔐 *APNE NUMBER PE OTP AAYA*\n"
                                                         f"📱 Number: `{masked}`\n"
                                                         f"🔢 OTP: `{otp}`\n"
                                                         f"✉️ Sender: `{se}`\n"
                                                         f"📝 Message: `{ms[:200]}`")
                                            await safe_send(uid, user_text)

                                    print(f"✅ SENT: {masked} | OTP: {otp}", flush=True)

                    await page.go_back()
                    await page.wait_for_load_state('domcontentloaded', timeout=8000)
                    await asyncio.sleep(0.2)
                except Exception as e:
                    print(f"Detail err: {e}", flush=True)
                    try:
                        await page.goto(SMS_URL, timeout=15000, wait_until='domcontentloaded')
                    except:
                        pass

            import random
            if random.random() < 0.15:
                await save_cookies()

            if len(seen_messages) > 500:
                seen_messages = set(list(seen_messages)[-250:])
            err_count = 0

        except Exception as e:
            err_count += 1
            print(f"Poll err ({err_count}/5): {e}", flush=True)
            if 'crashed' in str(e).lower() or 'closed' in str(e).lower():
                print("💥 Crash detected — full browser restart", flush=True)
                await start_browser()
                await do_login()
            if err_count >= 5:
                await admin_alert("⚠️ Network issues — recover ho raha hai")
                err_count = 0
                try:
                    await start_browser()
                    await do_login()
                except:
                    pass

        await asyncio.sleep(POLL_INTERVAL)

# ========== COMMAND HANDLERS ==========
async def start_cmd(u: Update, c: ContextTypes):
    user = u.effective_user
    if not await check_subscription(user.id):
        await u.message.reply_text(
            "⚠️ *Bot use karne se pehle dono channels join karein!*\n\n"
            "Neeche buttons se channel join karein, phir 'Joined' button dabayein 👇",
            reply_markup=get_join_keyboard(),
            parse_mode="Markdown"
        )
        return

    num, data = get_user_number(user.id)
    if num:
        await u.message.reply_text(
            f"✅ *Welcome back!*\n\n"
            f"📱 Tera allocated number: `{num}`\n"
            f"🌍 Range: {data.get('range', 'N/A')}\n\n"
            f"Commands:\n"
            f"/mynumber — Apna number dekhe\n"
            f"/release — Number free kare",
            parse_mode="Markdown"
        )
    else:
        await u.message.reply_text(
            "✅ *Welcome!*\n\n"
            "Number lene ke liye /getnumber dabayein 👇\n\n"
            "Commands:\n"
            "/getnumber — Naya number le\n"
            "/mynumber — Apna number dekhe\n"
            "/release — Number free kare",
            parse_mode="Markdown"
        )

async def callback_check_join(u: Update, c: ContextTypes):
    q = u.callback_query
    await q.answer()
    user = q.from_user

    if await check_subscription(user.id):
        await q.edit_message_text(
            "✅ *Sab channels join ho gaye!*\n\nAb /getnumber se number le sakte ho! 🎉",
            parse_mode="Markdown"
        )
    else:
        await q.edit_message_text(
            "❌ *Abhi bhi channels join nahi hue!*\n\n"
            "Dono channels join karein phir try karein 👇",
            reply_markup=get_join_keyboard(),
            parse_mode="Markdown"
        )

async def getnumber_cmd(u: Update, c: ContextTypes):
    user = u.effective_user
    if not await check_subscription(user.id):
        await u.message.reply_text(
            "⚠️ Pehle dono channels join karein!",
            reply_markup=get_join_keyboard(),
            parse_mode="Markdown"
        )
        return

    num, data = get_user_number(user.id)
    if num:
        await u.message.reply_text(
            f"⚠️ Tere paas already number hai:\n\n"
            f"📱 `{num}`\n"
            f"🌍 Range: {data.get('range', 'N/A')}\n\n"
            f"Naya lene ke liye pehle /release karo.",
            parse_mode="Markdown"
        )
        return

    num = allocate_number(user.id, user.username or user.first_name)
    if num:
        await u.message.reply_text(
            f"🎉 *Number allocated!*\n\n"
            f"📱 Number: `{num}`\n"
            f"🌍 Range: {numbers_db[num].get('range', 'N/A')}\n\n"
            f"⚠️ Yeh number sirf tere liye lock hai.\n"
            f"Ispe aane wala OTP tujhe direct DM mein milega!",
            parse_mode="Markdown"
        )
    else:
        await u.message.reply_text(
            "😔 *Abhi koi free number nahi hai!*\n\nAdmin ko contact karein ya thodi der baad try karein.",
            parse_mode="Markdown"
        )

async def mynumber_cmd(u: Update, c: ContextTypes):
    user = u.effective_user
    if not await check_subscription(user.id):
        await u.message.reply_text("⚠️ Pehle channels join karein!", reply_markup=get_join_keyboard())
        return

    num, data = get_user_number(user.id)
    if num:
        alloc_time = datetime.fromtimestamp(data.get("allocated_at", 0)).strftime("%d %b %H:%M")
        await u.message.reply_text(
            f"📱 *Tera Number:*\n\n"
            f"`{num}`\n"
            f"🌍 Range: {data.get('range', 'N/A')}\n"
            f"📅 Mila tha: {alloc_time}",
            parse_mode="Markdown"
        )
    else:
        await u.message.reply_text("❌ Tere paas koi number nahi hai!\n/getnumber se le lo.")

async def release_cmd(u: Update, c: ContextTypes):
    user = u.effective_user
    if not await check_subscription(user.id):
        await u.message.reply_text("⚠️ Pehle channels join karein!", reply_markup=get_join_keyboard())
        return

    num = release_number(user.id)
    if num:
        await u.message.reply_text(f"✅ Number `{num}` free kar diya gaya!")
    else:
        await u.message.reply_text("❌ Tere paas koi number nahi hai!")

# ========== ADMIN COMMANDS ==========
async def status_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    total, free, allocated = get_stats()
    await u.message.reply_text(
        f"✅ *Bot Status*\n\n"
        f"⏱️ Poll Interval: {POLL_INTERVAL}s\n"
        f"📊 Total Numbers: {total}\n"
        f"🆓 Free: {free}\n"
        f"🔒 Allocated: {allocated}\n"
        f"🔄 Auto-release: {AUTO_RELEASE_H}h\n"
        f"📢 Channels: 2\n"
        f"🛡️ Force Subscribe: ON",
        parse_mode="Markdown"
    )

async def numberstats_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    total, free, allocated = get_stats()
    await u.message.reply_text(
        f"📊 *Number Stats*\n\n"
        f"Total: {total}\n"
        f"Free: {free}\n"
        f"Allocated: {allocated}",
        parse_mode="Markdown"
    )

async def addnumber_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    parts = u.message.text.split()
    if len(parts) < 2:
        await u.message.reply_text("Usage: `/addnumber <number> [range]`", parse_mode="Markdown")
        return
    num = parts[1]
    rng = parts[2] if len(parts) > 2 else "N/A"
    if add_number(num, rng):
        await u.message.reply_text(f"✅ Number `{num}` ({rng}) add ho gaya!")
    else:
        await u.message.reply_text(f"❌ Number add nahi hua (pehle se hai ya galat format)")

async def delnumber_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    parts = u.message.text.split()
    if len(parts) < 2:
        await u.message.reply_text("Usage: `/delnumber <number>`", parse_mode="Markdown")
        return
    num = parts[1]
    if delete_number(num):
        await u.message.reply_text(f"✅ Number `{num}` delete ho gaya!")
    else:
        await u.message.reply_text(f"❌ Number nahi mila")

async def forcefree_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    parts = u.message.text.split()
    if len(parts) < 2:
        await u.message.reply_text("Usage: `/forcefree <number>`", parse_mode="Markdown")
        return
    num = parts[1]
    if force_free_number(num):
        await u.message.reply_text(f"✅ Number `{num}` force free kar diya!")
    else:
        await u.message.reply_text(f"❌ Number nahi mila")

async def freenumbers_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    free_nums = [(n, d) for n, d in numbers_db.items() if d.get("status") == "free"]
    if not free_nums:
        await u.message.reply_text("❌ Koi free number nahi hai!")
        return
    msg = "🆓 *Free Numbers:*\n\n"
    for i, (n, d) in enumerate(free_nums[:50], 1):
        msg += f"{i}. `{n}` — {d.get('range', 'N/A')}\n"
    if len(free_nums) > 50:
        msg += f"\n... aur {len(free_nums) - 50} aur"
    await u.message.reply_text(msg, parse_mode="Markdown")

async def reloadnumbers_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    load_numbers()
    total, free, allocated = get_stats()
    await u.message.reply_text(f"✅ Numbers reload ho gaye!\nTotal: {total}, Free: {free}, Allocated: {allocated}")

async def restart_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    await u.message.reply_text("🔄 Browser restart ho raha hai...")
    await start_browser()
    await do_login()
    await u.message.reply_text("✅ Browser restart + login done!")

async def relogin_cmd(u: Update, c: ContextTypes):
    if u.effective_user.id != ADMIN_ID:
        return
    try:
        os.remove(cookies_file)
    except:
        pass
    await u.message.reply_text("✅ Cookie delete — auto re-login hoga")

# ========== CSV FILE HANDLER ==========
async def handle_document(u: Update, c: ContextTypes):
    user = u.effective_user
    if user.id != ADMIN_ID:
        return

    doc: Document = u.message.document
    if not doc.file_name or not doc.file_name.lower().endswith('.csv'):
        return

    await u.message.reply_text("📤 CSV file process ho rahi hai...")

    try:
        file = await doc.get_file()
        file_bytes = await file.download_as_bytearray()
        content = file_bytes.decode('utf-8', errors='ignore')

        added = 0
        skipped = 0
        reader = csv.reader(io.StringIO(content))
        header_skipped = False

        for row in reader:
            if not row or not row[0].strip():
                continue

            if not header_skipped and not re.sub(r'\D', '', row[0]):
                header_skipped = True
                continue

            num = re.sub(r'\D', '', row[0].strip())
            rng = row[1].strip() if len(row) > 1 else "N/A"

            if len(num) >= 10:
                if add_number(num, rng):
                    added += 1
                else:
                    skipped += 1
            else:
                skipped += 1

        await u.message.reply_text(
            f"✅ *CSV Processed!*\n\n"
            f"✅ Added: {added}\n"
            f"⚠️ Skipped: {skipped}\n"
            f"📊 Total numbers: {len(numbers_db)}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await u.message.reply_text(f"❌ Error: {str(e)}")

# ========== MAIN ==========
async def main():
    global bot_ref

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing!"); return
    if not PANEL_USER or not PANEL_PASS:
        print("❌ PANEL credentials missing!"); return

    load_numbers()
    print(f"📱 Loaded {len(numbers_db)} numbers", flush=True)

    app = Application.builder().token(BOT_TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    bot_ref = app.bot

    app.add_handler(CallbackQueryHandler(callback_check_join, pattern="^check_join$"))
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("getnumber", getnumber_cmd))
    app.add_handler(CommandHandler("mynumber", mynumber_cmd))
    app.add_handler(CommandHandler("release", release_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("numberstats", numberstats_cmd))
    app.add_handler(CommandHandler("addnumber", addnumber_cmd))
    app.add_handler(CommandHandler("delnumber", delnumber_cmd))
    app.add_handler(CommandHandler("forcefree", forcefree_cmd))
    app.add_handler(CommandHandler("freenumbers", freenumbers_cmd))
    app.add_handler(CommandHandler("reloadnumbers", reloadnumbers_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CommandHandler("relogin", relogin_cmd))
    app.add_handler(MessageHandler(filters.Document.CSV, handle_document))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    asyncio.create_task(run_poller())

    print("🚀 Bot started!", flush=True)
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("STOPPED", flush=True)
