import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== SAB TERA HI DAAL DIYA HAI — CHANGE MAT KARNA ==========
BOT_TOKEN       = "8936294237:AAFmQLQ3WmepNb4n0sGRl4ydIZKyJb2mmqQ"

JOIN_CH1        = -1004437601665
JOIN_CH2        = -1003250473765

OTP_CHANNEL_ID  = -1003250473765
OTP_GROUP_ID    = -1004427004477
ADMIN_ID        = 8473160748

PANEL_USER      = "xyz@gmail.com"
PANEL_PASS      = "Sanju@71"

LOGIN_URL       = "https://livestatspanel.com/index.php"
SMS_URL         = "https://livestatspanel.com/index.php?opt=shw_sms_tod&lang=EN"
POLL_INTERVAL   = 12

seen_messages   = set()
browser = page = ctx = None

# ========== LOGIN — 100% WORKING ==========
async def login_panel():
    global browser, page, ctx
    try:
        print("🌐 Starting browser...", flush=True)
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        print(f"🔗 Going to login page...", flush=True)
        await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Email field
        email_filled = False
        for sel in ['input[name="user"]', 'input[name="email"]', 'input[type="text"]']:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel, timeout=3000)
                    await page.fill(sel, PANEL_USER, timeout=3000)
                    print(f"✅ Email filled: {sel}", flush=True)
                    email_filled = True
                    break
            except: pass
        if not email_filled:
            print("❌ Email field not found!", flush=True)
            return False

        await asyncio.sleep(1)

        # Password field
        try:
            await page.click('input[type="password"]', timeout=3000)
            await page.fill('input[type="password"]', PANEL_PASS, timeout=3000)
            print("✅ Password filled", flush=True)
        except:
            print("❌ Password field not found!", flush=True)
            return False

        await asyncio.sleep(1)

        # Login button
        btn_clicked = False
        for sel in ['button[type="submit"]', 'input[type="submit"]', 'form button']:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel, timeout=3000)
                    print(f"✅ Login button clicked", flush=True)
                    btn_clicked = True
                    break
            except: pass
        if not btn_clicked:
            await page.press('input[type="password"]', 'Enter')
            print("✅ Pressed Enter", flush=True)

        await asyncio.sleep(4)

        # Verify login
        if "login" not in page.url.lower():
            print("✅ LOGIN SUCCESSFUL! 🎉", flush=True)
            return True
        else:
            print(f"❌ Still on login page — URL: {page.url}", flush=True)
            return False

    except Exception as e:
        print(f"❌ Login error: {e}", flush=True)
        return False

# ========== OTP HELPERS ==========
def extract_otp(text):
    m = re.search(r'\b(\d{4,6})\b', text)
    if m: return m.group(1)
    m = re.search(r'\b([A-Za-z0-9]{6,12})\b', text)
    return m.group(1) if m else "N/A"

def mask_phone(text):
    d = re.sub(r'\D', '', text)
    if len(d) <= 8: return f"`{d}`"
    return f"`{d[:4]}****{d[-4:]}`"

async def send_msg(chat_id, text, app):
    try:
        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        return True
    except Exception as e:
        print(f"❌ Send to {chat_id}: {e}", flush=True)
        return False

# ========== CHECK SMS ==========
async def check_sms(app):
    global seen_messages
    try:
        await page.goto(SMS_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        rows = page.locator('table tbody tr')
        total = await rows.count()
        print(f"📊 Rows found: {total}", flush=True)

        for i in range(total):
            cells = rows.nth(i).locator('td')
            if await cells.count() < 4: continue

            dt = await cells.nth(0).inner_text()
            ph = await cells.nth(1).inner_text()
            msg = await cells.nth(3).inner_text()

            if len(msg) < 6: continue
            key = f"{dt}|{ph}|{msg[:50]}"
            if key in seen_messages: continue
            seen_messages.add(key)

            otp = extract_otp(msg)
            print(f"📩 NEW OTP — Phone: {mask_phone(ph)} | Code: {otp}", flush=True)

            txt = f"""🔐 *NEW OTP*
📱 Number: {mask_phone(ph)}
🔑 Code: `{otp}`"""

            await send_msg(OTP_CHANNEL_ID, txt, app)
            await send_msg(OTP_GROUP_ID, txt, app)
            print("✅ Sent to Channel + Group ✅", flush=True)

        if len(seen_messages) > 300:
            seen_messages = set(list(seen_messages)[-150:])

    except Exception as e:
        print(f"❌ Check error: {e}", flush=True)

# ========== BOT COMMANDS ==========
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot Online! OTP aayega yahaan bhi bhej dunga.")

# ========== MAIN ==========
async def main():
    print("🤖 Starting bot...", flush=True)
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    await app.initialize()
    await app.start()
    print("✅ Bot connected to Telegram!", flush=True)

    # Login
    login_ok = await login_panel()
    if not login_ok:
        print("🔄 Retrying login in 8s...", flush=True)
        await asyncio.sleep(8)
        login_ok = await login_panel()

    if login_ok:
        print("🚀 Started monitoring SMS...", flush=True)
        while True:
            await check_sms(app)
            await asyncio.sleep(POLL_INTERVAL)
    else:
        print("❌ Login failed — check email/password", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
