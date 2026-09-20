import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== CONFIG ==========
BOT_TOKEN       = "8951473771:AAEZfooWkx1d-AfZP6Af5lkhuY45npPukWA"  # ⚠️ JALDI CHANGE KARO!
OTP_CHANNEL_ID  = -1003250473765
OTP_GROUP_ID    = -1004427004477
ADMIN_ID        = 8473160748
PANEL_USER      = "xyz@gmail.com"
PANEL_PASS      = "Sanju@71"  # ⚠️ JALDI CHANGE KARO!
LOGIN_URL       = "https://livestatspanel.com/index.php"
SMS_URL         = "https://livestatspanel.com/index.php?opt=shw_sms_tod&lang=EN"
POLL_INTERVAL   = 12

seen_messages = set()

# ========== UTILS ==========
async def send_screenshot(page, app, caption="Screenshot"):
    try:
        screenshot = await page.screenshot(type="jpeg", quality=80, full_page=True)
        await app.bot.send_photo(chat_id=ADMIN_ID, photo=screenshot, caption=caption)
        return True
    except Exception as e:
        print(f"Screenshot failed: {e}", flush=True)
        return False

def extract_otp(text):
    """Pehle 4-6 digit OTP dhundho, nahi mila toh alphanumeric"""
    m = re.search(r'\b(\d{4,6})\b', text)
    if m:
        return m.group(1)
    m = re.search(r'\b([A-Za-z0-9]{6,12})\b', text)
    return m.group(1) if m else "N/A"

def mask_phone(text):
    """Phone number ko ** format mein mask karo"""
    digits = re.sub(r'\D', '', text)
    if len(digits) <= 8:
        return digits
    return f"{digits[:4]}**{digits[-4:]}"

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def is_valid_phone(text):
    digits = re.sub(r'\D', '', text)
    return len(digits) >= 10

def is_header_row(phone_text):
    """Header row detect karo"""
    header_keywords = ['NUMBER', 'Number', 'number', 'PHONE', 'Phone', 'phone']
    return any(keyword in phone_text for keyword in header_keywords)

def escape_markdown(text):
    """Markdown special characters escape karo"""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def send_msg(chat_id, text, app):
    try:
        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="MarkdownV2")
        return True
    except Exception as e:
        print(f"Send to {chat_id}: {e}", flush=True)
        try:
            await app.bot.send_message(chat_id=chat_id, text=text)
            return True
        except Exception as e2:
            print(f"Simple text bhi fail: {e2}", flush=True)
            return False

# ========== LOGIN ==========
async def login_panel(app):
    pw = browser = ctx = page = None
    try:
        print("Starting browser...", flush=True)
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0.0.0"
        )
        page = await ctx.new_page()
        
        print("Opening login page...", flush=True)
        await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        # Username fill karo
        email_filled = False
        for sel in ['input[name="user"]', 'input[name="email"]', 'input[type="text"]']:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    await loc.click(timeout=3000)
                    await loc.fill(PANEL_USER, timeout=3000)
                    print(f"Username filled: {sel}", flush=True)
                    email_filled = True
                    break
            except Exception:
                continue
        
        if not email_filled:
            await send_screenshot(page, app, "Username field not found!")
            await cleanup_resources_direct(pw, browser, ctx, page)
            return False, None
        
        await asyncio.sleep(0.5)
        
        # Password fill karo
        try:
            pass_input = page.locator('input[type="password"]')
            await pass_input.click(timeout=5000)
            await pass_input.fill(PANEL_PASS, timeout=5000)
            print("Password filled", flush=True)
        except Exception as e:
            await send_screenshot(page, app, f"Password field error: {e}")
            await cleanup_resources_direct(pw, browser, ctx, page)
            return False, None
        
        await asyncio.sleep(0.5)
        
        # Login button click karo
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
            print("Using form.submit()", flush=True)
            await page.evaluate("document.querySelector('form')?.submit()")
        
        await asyncio.sleep(3)
        
        page_content = await page.content()
        if "Please enter your login details" not in page_content:
            print("LOGIN SUCCESSFUL!", flush=True)
            return True, page
        else:
            await send_screenshot(page, app, "LOGIN FAILED - Still on login page")
            print("Login failed - check credentials", flush=True)
            await cleanup_resources_direct(pw, browser, ctx, page)
            return False, None
            
    except Exception as e:
        print(f"Login error: {e}", flush=True)
        await cleanup_resources_direct(pw, browser, ctx, page)
        return False, None

async def cleanup_resources_direct(pw, browser, ctx, page):
    try:
        if page:
            await page.close()
        if ctx:
            await ctx.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()
    except Exception as e:
        print(f"Cleanup note: {e}", flush=True)

async def cleanup_resources(page):
    try:
        if page:
            ctx = page.context
            browser = ctx.browser
            await page.close()
            await ctx.close()
            await browser.close()
    except Exception as e:
        print(f"Cleanup note: {e}", flush=True)

# ========== SMS DETAILS EXTRACT ==========
async def get_sms_details(page):
    """Select click karne par jo SMS details table aata hai usse data extract karo"""
    try:
        await asyncio.sleep(1.5)
        
        # Sab tables dhundho
        tables = page.locator('table')
        table_count = await tables.count()
        
        if table_count < 2:
            print("Details table nahi mila", flush=True)
            return None, None
        
        # Pehla table SMS details wala hai
        details_table = tables.first
        all_rows = details_table.locator('tr')
        all_row_count = await all_rows.count()
        
        if all_row_count < 2:
            print("Details table mein data nahi hai", flush=True)
            return None, None
        
        # Second row data row hai
        data_row = all_rows.nth(1)
        cells = data_row.locator('td')
        cell_count = await cells.count()
        
        if cell_count < 5:
            print(f"Details row mein kam cells: {cell_count}", flush=True)
            return None, None
        
        # 0 = DATE TIME, 1 = RANGE, 2 = SENDER, 3 = RECEIVER, 4 = MESSAGE BODY
        dt = clean_text(await cells.nth(0).inner_text())
        msg_body = clean_text(await cells.nth(4).inner_text())
        
        print(f"Date: {dt}", flush=True)
        print(f"Message: {msg_body[:120]}...", flush=True)
        
        return dt, msg_body
        
    except Exception as e:
        print(f"SMS details error: {e}", flush=True)
        return None, None

# ========== CLICKABLE ELEMENT FIND ==========
async def find_and_click_select(details_cell):
    """
    Details cell mein clickable element dhoondho aur click karo
    Har tarah ke elements try karo
    """
    try:
        # Pehle cell ka HTML print karo debug ke liye
        cell_html = await details_cell.inner_html()
        print(f"  Cell HTML: {cell_html[:200]}", flush=True)
        
        # Sab clickable elements try karo
        element_selectors = [
            'a',
            'button',
            'span',
            'u',
            'div',
            'p',
            '[onclick]',
            '[href]',
            '*'  # Last resort: koi bhi element
        ]
        
        for sel in element_selectors:
            try:
                el = details_cell.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    el_text = await el.inner_text()
                    el_tag = await el.evaluate("e => e.tagName")
                    print(f"  Trying {el_tag}: '{el_text.strip()}'", flush=True)
                    await el.click(timeout=3000)
                    print(f"  Clicked successfully!", flush=True)
                    return True
            except Exception as e:
                print(f"  {sel} failed: {str(e)[:80]}", flush=True)
                continue
        
        # Last resort: cell ko directly click karo
        print(f"  Last resort: clicking cell directly", flush=True)
        await details_cell.click(timeout=3000)
        return True
        
    except Exception as e:
        print(f"  Find/click error: {e}", flush=True)
        return False

# ========== CHECK SMS ==========
async def check_sms(app, page):
    global seen_messages
    try:
        await page.goto(SMS_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        page_content = await page.content()
        if "Please enter your login details" in page_content:
            print("Session expired - Need re-login", flush=True)
            return False
        
        # "Today's SMS Statistics" wali table dhundho
        tables = page.locator('table')
        table_count = await tables.count()
        
        if table_count == 0:
            print("Koi table nahi mila", flush=True)
            return True
        
        # Har table check karo ki usme "Today's SMS Statistics" hai ya nahi
        main_table = None
        for i in range(table_count):
            tbl = tables.nth(i)
            try:
                tbl_text = await tbl.inner_text()
                if "Today's SMS Statistics" in tbl_text:
                    main_table = tbl
                    print(f"Main table found at index {i}", flush=True)
                    break
            except Exception:
                continue
        
        if not main_table:
            # Agar nahi mila toh first table use karo
            main_table = tables.first
            print("Using first table as main table", flush=True)
        
        # Sab rows dhundho
        all_rows = main_table.locator('tr')
        total_rows = await all_rows.count()
        
        print(f"Total rows in main table: {total_rows}", flush=True)
        
        new_messages_found = 0
        
        for i in range(total_rows):
            try:
                row = all_rows.nth(i)
                cells = row.locator('td')
                cell_count = await cells.count()
                
                if cell_count < 7:
                    continue
                
                # Columns: 0=NUMBER, 1=RANGE, 2=SENDER, 3=STATUS, 4=CLIENT, 5=MESSAGES, 6=DETAILS
                ph = clean_text(await cells.nth(0).inner_text())
                sender = clean_text(await cells.nth(2).inner_text())
                msg_count = clean_text(await cells.nth(5).inner_text())
                details_cell = cells.nth(6)
                
                # Header row skip karo
                if is_header_row(ph):
                    print(f"Row {i}: Header row, skip", flush=True)
                    continue
                
                # Invalid phone skip karo
                if not is_valid_phone(ph):
                    print(f"Row {i}: Invalid phone ({ph}), skip", flush=True)
                    continue
                
                print(f"\nRow {i}: Phone={ph}, Sender={sender}", flush=True)
                
                # Unique key
                msg_key = f"v3_{ph}_{sender}_{msg_count}"
                
                if msg_key in seen_messages:
                    print(f"  Skip: Already seen", flush=True)
                    continue
                
                # 🔴 Select button/link dhoondho aur click karo
                clicked = await find_and_click_select(details_cell)
                
                if not clicked:
                    print(f"  Click nahi ho paya, skip", flush=True)
                    continue
                
                # SMS details extract karo
                dt, full_msg = await get_sms_details(page)
                
                if not full_msg:
                    print(f"  Message nahi mila, skip", flush=True)
                    # Seen mein nahi add karo taaki agli baar try kare
                    continue
                
                # Ab seen mein add karo
                seen_messages.add(msg_key)
                new_messages_found += 1
                
                # OTP extract karo
                otp = extract_otp(full_msg)
                print(f"  OTP: {otp}", flush=True)
                
                # Message format
                message_text = f"""📱 *Number*: `{escape_markdown(mask_phone(ph))}`
🔑 *OTP*: `{escape_markdown(otp)}`
📝 *Message*:
`{escape_markdown(full_msg[:400])}`"""
                
                if dt:
                    message_text = f"⏰ *Time*: `{escape_markdown(dt)}`\n" + message_text
                
                await send_msg(OTP_CHANNEL_ID, message_text, app)
                await send_msg(OTP_GROUP_ID, message_text, app)
                print(f"  ✅ OTP sent to Telegram!", flush=True)
                
            except Exception as row_err:
                print(f"Row {i} error: {row_err}", flush=True)
                continue
        
        print(f"\n📊 This cycle: {new_messages_found} new messages found", flush=True)
        print(f"📊 Total seen: {len(seen_messages)}", flush=True)
        
        # Memory management
        if len(seen_messages) > 500:
            seen_messages = set(list(seen_messages)[-250:])
            print(f"🧹 Cleaned seen_messages, now: {len(seen_messages)}", flush=True)
        
        return True
        
    except Exception as e:
        print(f"Check SMS error: {e}", flush=True)
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
    
    async def reset_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        global seen_messages
        if update.effective_user.id == ADMIN_ID:
            old_count = len(seen_messages)
            seen_messages = set()
            await update.message.reply_text(f"🔄 Seen cache reset! Old: {old_count}, New: 0")
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    
    await app.initialize()
    await app.start()
    
    print("🔒 Cleaning webhook & pending updates...", flush=True)
    await app.bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    
    await app.updater.start_polling(drop_pending_updates=True, allowed_updates=[])
    print("✅ Telegram Connected & Polling Started!", flush=True)
    
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
                print("🔄 Session lost - Re-logging in...", flush=True)
                await cleanup_resources(page)
                break
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot Stopped by User", flush=True)
