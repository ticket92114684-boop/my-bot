import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== CONFIG ==========
BOT_TOKEN       = "8936294237:AAFmQLQ3WmepNb4n0sGRl4ydIZKyJb2mmqQ"
OTP_CHANNEL_ID  = -1003250473765
OTP_GROUP_ID    = -1004427004477
ADMIN_ID        = 8473160748
PANEL_USER      = "xyz@gmail.com"
PANEL_PASS      = "Sanju@71"
LOGIN_URL       = "https://livestatspanel.com/index.php"
SMS_URL         = "https://livestatspanel.com/index.php?opt=shw_sms_tod&lang=EN"
POLL_INTERVAL   = 12

seen_messages = set()

# ========== ADMIN KO SCREENSHOT BHEJE ✅ ==========
async def send_screenshot(page, app, caption="📸 Screenshot"):
    try:
        screenshot = await page.screenshot(type="jpeg", quality=80, full_page=True)
        await app.bot.send_photo(chat_id=ADMIN_ID, photo=screenshot, caption=caption)
        print(f"📸 Screenshot sent to admin", flush=True)
        return True
    except Exception as e:
        print(f"❌ Screenshot send failed: {e}", flush=True)
        return False

# ========== LOGIN WITH SCREENSHOT ✅ ==========
async def login_panel(app):
    try:
        print("🌐 Browser start...", flush=True)
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0.0.0"
        )
        page = await ctx.new_page()

        print("🔗 Login page open...", flush=True)
        await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Step 1: Login page ka screenshot
        await send_screenshot(page, app, "🔐 Step 1: Login Page")

        # Username fill
        email_filled = False
        for sel in ['input[name="user"]', 'input[name="email"]', 'input[type="text"]']:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel, timeout=3000)
                    await page.fill(sel, PANEL_USER, timeout=3000)
                    print(f"✅ User filled: {sel}", flush=True)
                    email_filled = True
                    break
            except: pass
        if not email_filled:
            await send_screenshot(page, app, "❌ Username field nahi mili!")
            return False, None, pw, browser, ctx

        await asyncio.sleep(0.5)

        # Password fill
        try:
            pass_sel = 'input[type="password"]'
            await page.click(pass_sel, timeout=5000)
            await page.fill(pass_sel, PANEL_PASS, timeout=5000)
            print("✅ Password filled", flush=True)
        except Exception as e:
            await send_screenshot(page, app, f"❌ Password field nahi mili: {e}")
            return False, None, pw, browser, ctx

        await asyncio.sleep(0.5)

        # Step 2: Filled form ka screenshot
        await send_screenshot(page, app, "🔐 Step 2: User + Password filled")

        # Login button click
        btn_clicked = False
        btn_selectors = [
            'button[type="submit"]', 'input[type="submit"]', 'form button',
            'input[value*="Login"]', 'button:has-text("Login")', 'input[value*="login"]'
        ]
        for sel in btn_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel, timeout=5000)
                    print(f"✅ Button clicked: {sel}", flush=True)
                    btn_clicked = True
                    break
            except: continue
        
        if not btn_clicked:
            print("⚠️ Button nahi mila — form.submit()", flush=True)
            try:
                await page.evaluate("document.querySelector('form').submit()")
            except: pass

        await asyncio.sleep(3)

        # Step 3: After login screenshot
        await send_screenshot(page, app, "🔐 Step 3: After clicking Login")

        # Verify login
        current_url = page.url
        content = await page.content()
        
        if "login" not in current_url.lower() or "Please enter your login details" not in content:
            await send_screenshot(page, app, "✅ LOGIN SUCCESSFUL! 🎉 Monitoring start...")
            print("✅ LOGIN SUCCESSFUL! 🎉", flush=True)
            return True, page, pw, browser, ctx
        else:
            await send_screenshot(page, app, "❌ FAILED — Abhi bhi login page par hain!")
            print("❌ Login failed — check credentials", flush=True)
            return False, None, pw, browser, ctx

    except Exception as e:
        print(f"❌ Login error: {e}", flush=True)
        return False, None, None, None, None

# ========== HELPERS ==========
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
        print(f"❌ Send {chat_id}: {e}", flush=True)
        return False

# ========== CHECK SMS ==========
async def check_sms(app, page):
    global seen_messages
    try:
        await page.goto(SMS_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        content = await page.content()
        if "Please enter your login details" in content:
            print("🔄 Session expired — re-login needed", flush=True)
            return False

        rows = page.locator('table tr')
        total = await rows.count()
        print(f"📊 Rows: {total}", flush=True)

        for i in range(total):
            try:
                cells = rows.nth(i).locator('td')
                if await cells.count() < 4: continue
                dt = await cells.nth(0).inner_text()
                ph = await cells.nth(1).inner_text()
                sender = await cells.nth(2).inner_text()
                msg = await cells.nth(3).inner_text()
                if len(msg) < 6: continue
                key = f"{dt}|{ph}|{msg[:50]}"
                if key in seen_messages: continue
                seen_messages.add(key)
                otp = extract_otp(msg)
                print(f"📩 NEW — {mask_phone(ph)} | OTP: {otp}", flush=True)
                txt = f"""🔐 *NEW OTP*
📱 Number: {mask_phone(ph)}
✉️ Sender: `{sender}`
🔑 Code: `{otp}`
📝 Message: `{msg[:200]}`"""
                await send_msg(OTP_CHANNEL_ID, txt, app)
                await send_msg(OTP_GROUP_ID, txt, app)
            except Exception as e:
                print(f"⚠️ Row {i} skip: {e}", flush=True)
                continue

        if len(seen_messages) > 300:
            seen_messages = set(list(seen_messages)[-150:])
        return True
    except Exception as e:
        print(f"❌ Check error: {e}", flush=True)
        return False

# ========== MAIN ==========
async def main():
    print("🤖 Bot start...", flush=True)
    app = Application.builder().token(BOT_TOKEN).build()

    async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ Bot chalu! Login process shuru dekhne ke liye wait...")

    async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text(f"✅ Running\n⏱️ Check every {POLL_INTERVAL}s\n📊 Seen: {len(seen_messages)}")

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print("✅ Telegram connected!", flush=True)

    page = pw = browser = ctx = None
    while True:
        login_ok, page, pw, browser, ctx = await login_panel(app)
        
        if not login_ok or not page:
            print("🔄 8s baad fir try...", flush=True)
            await asyncio.sleep(8)
            continue

        print("🚀 Monitoring shuru!", flush=True)
        while True:
            ok = await check_sms(app, page)
            if not ok:
                print("🔄 Session lost — re-login...", flush=True)
                try:
                    if page: await page.close()
                    if ctx: await ctx.close()
                    if browser: await browser.close()
                    if pw: await pw.stop()
                except: pass
                break
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Stopped", flush=True)
