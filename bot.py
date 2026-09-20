import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== SAB TERA HI HAI ==========
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

# ========== LOGIN — BUTTON CLICK KAREGA, ENTER NAHI ==========
async def login_panel():
    try:
        print("🌐 Browser start...", flush=True)
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0.0.0"
        )
        page = await ctx.new_page()

        print("🔗 Login page open...", flush=True)
        await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Email fill karein
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
            print("❌ Email field nahi mili!", flush=True)
            return False, None

        await asyncio.sleep(1)

        # Password fill karein
        try:
            pass_sel = 'input[type="password"]'
            await page.click(pass_sel, timeout=5000)
            await page.fill(pass_sel, PANEL_PASS, timeout=5000)
            print("✅ Password filled", flush=True)
        except Exception as e:
            print(f"❌ Password field nahi mili: {e}", flush=True)
            return False, None

        await asyncio.sleep(1)

        # ========== YAHAN FIX — BUTTON CLICK KAREIN, ENTER NAHI ==========
        btn_clicked = False
        btn_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'form button',
            'input[value*="Login"]',
            'button:has-text("Login")',
            '.login-btn',
            '#login-btn'
        ]
        
        for sel in btn_selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    await page.click(sel, timeout=5000)
                    print(f"✅ Button clicked: {sel}", flush=True)
                    btn_clicked = True
                    break
            except:
                continue

        if not btn_clicked:
            print("⚠️ Koi button nahi mila — form.submit() se direct login kar rahe hain", flush=True)
            await page.evaluate("document.querySelector('form').submit()")

        await asyncio.sleep(5)

        # Check login
        current_url = page.url
        print(f"📍 Current URL: {current_url}", flush=True)
        
        if "login" not in current_url.lower():
            print("✅ LOGIN SUCCESSFUL! 🎉", flush=True)
            return True, page
        else:
            print("❌ Abhi bhi login page par hi hain", flush=True)
            return False, None

    except Exception as e:
        print(f"❌ Login error: {e}", flush=True)
        return False, None

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
        print(f"❌ Send {chat_id}: {e}", flush=True)
        return False

# ========== CHECK SMS ==========
async def check_sms(app, page):
    global seen_messages
    try:
        await page.goto(SMS_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        rows = page.locator('table tr')
        total = await rows.count()
        print(f"📊 Rows: {total}", flush=True)

        for i in range(total):
            cells = rows.nth(i).locator('td')
            if await cells.count() < 4: continue
            
            try:
                dt = await cells.nth(0).inner_text()
                ph = await cells.nth(1).inner_text()
                msg = await cells.nth(3).inner_text()
            except: continue

            if len(msg) < 6: continue
            key = f"{dt}|{ph}|{msg[:50]}"
            if key in seen_messages: continue
            seen_messages.add(key)

            otp = extract_otp(msg)
            print(f"📩 NEW — {mask_phone(ph)} | OTP: {otp}", flush=True)

            txt = f"""🔐 *NEW OTP*
📱 Number: {mask_phone(ph)}
🔑 Code: `{otp}`"""
            
            await send_msg(OTP_CHANNEL_ID, txt, app)
            await send_msg(OTP_GROUP_ID, txt, app)
            print("✅ Channel + Group mein bhej diya!", flush=True)

        if len(seen_messages) > 300:
            seen_messages = set(list(seen_messages)[-150:])

    except Exception as e:
        print(f"❌ Check: {e}", flush=True)

# ========== MAIN ==========
async def main():
    print("🤖 Bot start...", flush=True)
    app = Application.builder().token(BOT_TOKEN).build()
    
    async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ Bot chalu! SMS aayega bata dunga.")
    
    app.add_handler(CommandHandler("start", start_cmd))
    
    await app.initialize()
    await app.start()
    print("✅ Telegram se connect!", flush=True)

    login_ok, page = await login_panel()
    if not login_ok:
        print("🔄 8 second baad fir try...", flush=True)
        await asyncio.sleep(8)
        login_ok, page = await login_panel()

    if login_ok and page:
        print("🚀 Monitoring shuru!", flush=True)
        while True:
            await check_sms(app, page)
            await asyncio.sleep(POLL_INTERVAL)
    else:
        print("❌ Login nahi hua — email/pass check kar le", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
