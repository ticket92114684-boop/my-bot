import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== CONFIG (Use Env Vars in Production) ==========
BOT_TOKEN       = "8951473771:AAEZfooWkx1d-AfZP6Af5lkhuY45npPukWA"
OTP_CHANNEL_ID  = -1003250473765
OTP_GROUP_ID    = -1004427004477
ADMIN_ID        = 8473160748
PANEL_USER      = "xyz@gmail.com"
PANEL_PASS      = "Sanju@71"
LOGIN_URL       = "https://livestatspanel.com/index.php"
SMS_URL         = "https://livestatspanel.com/index.php?opt=shw_sms_tod&lang=EN"
POLL_INTERVAL   = 12

seen_messages = set()

# ========== UTILITY FUNCTIONS ==========
async def send_screenshot(page, app, caption="📸 Screenshot"):
    try:
        screenshot = await page.screenshot(type="jpeg", quality=80, full_page=True)
        await app.bot.send_photo(chat_id=ADMIN_ID, photo=screenshot, caption=caption)
        return True
    except Exception as e:
        print(f"❌ Screenshot failed: {e}", flush=True)
        return False

def extract_otp(text):
    """Pehle 4-6 digit OTP, phir alphanumeric 6-12 chars"""
    m = re.search(r'\b(\d{4,6})\b', text)
    if m:
        return m.group(1)
    m = re.search(r'\b([A-Za-z0-9]{6,12})\b', text)
    return m.group(1) if m else "N/A"

def mask_phone(text):
    digits = re.sub(r'\D', '', text)
    if len(digits) <= 8:
        return f"`{digits}`"
    return f"`{digits[:4]}****{digits[-4:]}`"

def clean_text(text):
    """Extra spaces, newlines, special chars clean karega"""
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def send_msg(chat_id, text, app):
    try:
        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        return True
    except Exception as e:
        print(f"❌ Send to {chat_id}: {e}", flush=True)
        return False

# ========== LOGIN PANEL ==========
async def login_panel(app):
    pw = browser = ctx = page = None
    try:
        print("🌐 Starting browser...", flush=True)
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0.0.0"
        )
        page = await ctx.new_page()

        print("🔗 Opening login page...", flush=True)
        await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        await send_screenshot(page, app, "🔐 Step 1: Login Page")

        # Username fill
        email_filled = False
        for sel in ['input[name="user"]', 'input[name="email"]', 'input[type="text"]']:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    await loc.click(timeout=3000)
                    await loc.fill(PANEL_USER, timeout=3000)
                    print(f"✅ Username filled: {sel}", flush=True)
                    email_filled = True
                    break
            except Exception:
                continue
        if not email_filled:
            await send_screenshot(page, app, "❌ Username field not found!")
            return False, None

        await asyncio.sleep(0.5)

        # Password fill
        try:
            pass_input = page.locator('input[type="password"]')
            await pass_input.click(timeout=5000)
            await pass_input.fill(PANEL_PASS, timeout=5000)
            print("✅ Password filled", flush=True)
        except Exception as e:
            await send_screenshot(page, app, f"❌ Password field error: {e}")
            return False, None

        await asyncio.sleep(0.5)
        await send_screenshot(page, app, "🔐 Step 2: Form Filled")

        # Submit form
        submitted = False
        btn_selectors = [
            'button[type="submit"]', 'input[type="submit"]',
            'input[value*="Login"]', 'button:has-text("Login")',
            'form button'
        ]
        for sel in btn_selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    await loc.click(timeout=5000)
                    submitted = True
                    break
            except Exception:
                continue
        if not submitted:
            print("⚠️ Using form.submit()", flush=True)
            await page.evaluate("document.querySelector('form')?.submit()")

        await asyncio.sleep(3)
        await send_screenshot(page, app, "🔐 Step 3: After Submit")

        # ✅ Fixed Login Verification
        page_content = await page.content()
        if "Please enter your login details" not in page_content:
            await send_screenshot(page, app, "✅ LOGIN SUCCESSFUL! Monitoring started 🎉")
            print("✅ LOGIN SUCCESSFUL!", flush=True)
            return True, page
        else:
            await send_screenshot(page, app, "❌ LOGIN FAILED — Still on login page")
            print("❌ Login failed — check credentials", flush=True)
            return False, None

    except Exception as e:
        print(f"❌ Login error: {e}", flush=True)
        return False, None

# ========== CLEANUP HELPER ==========
async def cleanup_resources(page):
    try:
        if page:
            ctx = page.context
            browser = ctx.browser
            pw = getattr(browser, "_playwright", None)
            await page.close()
            await ctx.close()
            await browser.close()
            if pw:
                await pw.stop()
    except Exception as e:
        print(f"⚠️ Cleanup note: {e}", flush=True)

# ========== 🔑 NEW: GET FULL MESSAGE BODY VIA SELECT BUTTON ==========
async def get_full_message_body(row, page):
    """Row ke Select button ko click karke modal se full message extract karega"""
    try:
        # Select button dhoondho
        select_btn = None
        select_selectors = [
            'a:has-text("Select")',
            'button:has-text("Select")',
            'td:last-child a',
            'td:last-child button',
            '.btn-select',
            'a[href*="view_sms"]',
            'a[onclick*="view"]'
        ]
        
        for sel in select_selectors:
            try:
                btn = row.locator(sel)
                if await btn.count() > 0:
                    select_btn = btn
                    break
            except Exception:
                continue
        
        if not select_btn:
            print("⚠️ Select button nahi mila, table text use kar raha", flush=True)
            return None

        # Modal ka wait karo before click
        async with page.expect_popup(timeout=5000) as popup_info:
            try:
                await select_btn.click(timeout=3000)
                popup = await popup_info.value
                await popup.wait_for_load_state("domcontentloaded", timeout=5000)
                await asyncio.sleep(1)
                
                # Popup se full message extract
                # Common selectors for message body
                body_selectors = [
                    'textarea',
                    'div.message-body',
                    'div.sms-body',
                    'div.modal-body',
                    'pre',
                    'p.message',
                    'body'
                ]
                
                full_msg = None
                for bsel in body_selectors:
                    try:
                        el = popup.locator(bsel).first
                        if await el.count() > 0:
                            full_msg = await el.inner_text()
                            if full_msg and len(full_msg) > 10:
                                break
                    except Exception:
                        continue
                
                await popup.close()
                return clean_text(full_msg) if full_msg else None
                
            except Exception:
                # Popup nahi khula, shayad modal same page mein hai
                pass
        
        # Agar same page modal hai to yahan try karo
        await select_btn.click(timeout=3000)
        await asyncio.sleep(1)
        
        # Modal selectors
        modal_selectors = [
            '.modal.show',
            '.modal.in',
            'div[role="dialog"]',
            '#smsModal',
            '#messageModal',
            '.modal-dialog'
        ]
        
        modal = None
        for msel in modal_selectors:
            try:
                m = page.locator(msel).first
                if await m.count() > 0 and await m.is_visible():
                    modal = m
                    break
            except Exception:
                continue
        
        if not modal:
            print("⚠️ Modal nahi mila", flush=True)
            return None
        
        # Modal se message extract
        full_msg = None
        body_selectors = [
            'textarea',
            '.message-body',
            '.sms-content',
            '.modal-body',
            'pre',
            'p'
        ]
        
        for bsel in body_selectors:
            try:
                el = modal.locator(bsel).first
                if await el.count() > 0:
                    full_msg = await el.inner_text()
                    if full_msg and len(full_msg) > 10:
                        break
            except Exception:
                continue
        
        # Close modal
        close_selectors = [
            '.close',
            'button:has-text("Close")',
            'button:has-text("×")',
            '.modal-header button',
            '[data-dismiss="modal"]'
        ]
        
        for csel in close_selectors:
            try:
                close_btn = modal.locator(csel).first
                if await close_btn.count() > 0:
                    await close_btn.click(timeout=2000)
                    break
            except Exception:
                continue
        
        await asyncio.sleep(0.5)
        return clean_text(full_msg) if full_msg else None
        
    except Exception as e:
        print(f"⚠️ Full message extract error: {e}", flush=True)
        return None

# ========== CHECK SMS (UPDATED WITH FULL MESSAGE) ==========
async def check_sms(app, page):
    global seen_messages
    try:
        await page.goto(SMS_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        page_content = await page.content()
        if "Please enter your login details" in page_content:
            print("🔄 Session expired — Need re-login", flush=True)
            return False

        rows = page.locator('table tr')
        total_rows = await rows.count()
        print(f"📊 Found {total_rows} rows", flush=True)

        for i in range(total_rows):
            try:
                row = rows.nth(i)
                cells = row.locator('td')
                cell_count = await cells.count()
                
                if cell_count < 4:
                    continue

                dt = clean_text(await cells.nth(0).inner_text())
                ph = clean_text(await cells.nth(1).inner_text())
                sender = clean_text(await cells.nth(2).inner_text())
                preview_msg = clean_text(await cells.nth(3).inner_text())

                if len(preview_msg) < 6:
                    continue

                msg_key = f"{dt}|{ph}|{preview_msg[:50]}"
                if msg_key in seen_messages:
                    continue

                seen_messages.add(msg_key)

                # 🔑 Full message body extract karo via Select button
                full_msg = await get_full_message_body(row, page)
                
                # Agar full message nahi mila to preview hi use karo
                final_msg = full_msg if full_msg else preview_msg
                
                otp = extract_otp(final_msg)

                print(f"📩 NEW — {mask_phone(ph)} | OTP: {otp}", flush=True)
                print(f"   Full msg: {final_msg[:100]}...", flush=True)

                message_text = f"""🔐 *NEW OTP RECEIVED*
📅 Time: `{dt}`
📱 Number: {mask_phone(ph)}
✉️ Sender: `{sender}`
🔑 Code: `{otp}`
📝 Full Message:
`{final_msg[:400]}`"""

                await send_msg(OTP_CHANNEL_ID, message_text, app)
                await send_msg(OTP_GROUP_ID, message_text, app)

            except Exception as row_err:
                print(f"⚠️ Row {i} skipped: {row_err}", flush=True)
                continue

        # Memory cleanup
        if len(seen_messages) > 300:
            seen_messages = set(list(seen_messages)[-150:])

        return True

    except Exception as e:
        print(f"❌ Check SMS error: {e}", flush=True)
        return False

# ========== MAIN ==========
async def main():
    print("🤖 Bot Starting...", flush=True)
    app = Application.builder().token(BOT_TOKEN).build()

    async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ Bot is Active! Login process in progress...")

    async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text(
                f"✅ Bot Running\n⏱️ Check every {POLL_INTERVAL}s\n📊 Processed: {len(seen_messages)}"
            )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print("✅ Telegram Connected!", flush=True)

    while True:
        login_ok, page = await login_panel(app)

        if not login_ok or not page:
            print("🔄 Retry login in 8s...", flush=True)
            await asyncio.sleep(8)
            continue

        print("🚀 Monitoring Started!", flush=True)

        while True:
            check_ok = await check_sms(app, page)
            if not check_ok:
                print("🔄 Session lost — Re-logging in...", flush=True)
                await cleanup_resources(page)
                break
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot Stopped by User", flush=True)
