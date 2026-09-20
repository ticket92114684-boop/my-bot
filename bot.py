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

def escape_markdown(text):
    """Markdown special characters escape karo taaki error na aaye"""
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
        # Markdown fail ho jaye toh simple text bhejo
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
    """Direct resources cleanup jab login fail ho"""
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
    """Page se resources cleanup"""
    try:
        if page:
            ctx = page.context
            browser = ctx.browser
            await page.close()
            await ctx.close()
            await browser.close()
            # Playwright ko alag se track karna padega, isliye best effort
    except Exception as e:
        print(f"Cleanup note: {e}", flush=True)

# ========== SMS DETAILS EXTRACT ==========
async def get_sms_details(page, phone, sender):
    """
    Select button click karne par jo SMS details table aata hai,
    usse date time aur message body extract karo
    """
    try:
        # SMS details table dhundho (jo Select click karne par upar aata hai)
        # Pehle check karo ki details table aaya bhi hai ya nahi
        await asyncio.sleep(1)
        
        details_tables = page.locator('table')
        table_count = await details_tables.count()
        
        if table_count < 2:
            print("Details table nahi mila", flush=True)
            return None, None
        
        # Pehla table SMS details wala hai (header: SMS details)
        details_table = details_tables.first
        details_rows = details_table.locator('tbody tr')
        details_row_count = await details_rows.count()
        
        if details_row_count == 0:
            # Header row ke baad data row check karo
            all_rows = details_table.locator('tr')
            all_row_count = await all_rows.count()
            if all_row_count < 2:
                print("Details table mein data nahi hai", flush=True)
                return None, None
            # Second row (index 1) data row hai
            data_row = all_rows.nth(1)
        else:
            data_row = details_rows.first
        
        cells = data_row.locator('td')
        cell_count = await cells.count()
        
        if cell_count < 5:
            print(f"Details row mein kam cells: {cell_count}", flush=True)
            return None, None
        
        # Details table ke columns:
        # 0 = DATE TIME, 1 = RANGE, 2 = SENDER, 3 = RECEIVER, 4 = MESSAGE BODY
        dt = clean_text(await cells.nth(0).inner_text())
        msg_body = clean_text(await cells.nth(4).inner_text())
        
        print(f"Date: {dt}", flush=True)
        print(f"Message: {msg_body[:100]}...", flush=True)
        
        return dt, msg_body
        
    except Exception as e:
        print(f"SMS details error: {e}", flush=True)
        return None, None

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
        
        # Main list table dhundho (Today's SMS Statistics)
        # Ye page par dusra table hai (ya last table)
        tables = page.locator('table')
        table_count = await tables.count()
        
        if table_count == 0:
            print("Koi table nahi mila", flush=True)
            return True
        
        # Main list table usually last table hota hai
        main_table = tables.last
        rows = main_table.locator('tbody tr')
        total_rows = await rows.count()
        
        # Agar tbody mein rows nahi hain toh direct tr check karo
        if total_rows == 0:
            rows = main_table.locator('tr')
            total_rows = await rows.count()
            # Header row skip karo
            start_idx = 1
        else:
            start_idx = 0
        
        print(f"Found {total_rows - start_idx} data rows", flush=True)
        
        for i in range(start_idx, total_rows):
            try:
                row = rows.nth(i)
                cells = row.locator('td')
                cell_count = await cells.count()
                
                print(f"\nRow {i}: {cell_count} cells", flush=True)
                
                if cell_count < 7:
                    print(f"Skip: Kam cells ({cell_count})", flush=True)
                    continue
                
                # Main list table ke columns:
                # 0 = NUMBER, 1 = RANGE, 2 = SENDER, 3 = STATUS, 4 = CLIENT, 5 = MESSAGES, 6 = DETAILS (Select)
                ph = clean_text(await cells.nth(0).inner_text())
                range_name = clean_text(await cells.nth(1).inner_text())
                sender = clean_text(await cells.nth(2).inner_text())
                status = clean_text(await cells.nth(3).inner_text())
                msg_count = clean_text(await cells.nth(5).inner_text())
                
                print(f"Phone: {ph}", flush=True)
                print(f"Range: {range_name}", flush=True)
                print(f"Sender: {sender}", flush=True)
                print(f"Status: {status}", flush=True)
                
                if not is_valid_phone(ph):
                    print(f"Skip: Invalid phone", flush=True)
                    continue
                
                # Unique key banayein taaki duplicate na bhejein
                msg_key = f"{ph}|{sender}|{msg_count}"
                if msg_key in seen_messages:
                    print(f"Skip: Already seen", flush=True)
                    continue
                
                # Select button par click karo
                select_btn = None
                select_selectors = [
                    'a:has-text("Select")',
                    'a:has-text("select")',
                    'td:last-child a',
                    'a'
                ]
                
                for sel in select_selectors:
                    try:
                        btn = row.locator(sel).first
                        if await btn.count() > 0 and await btn.is_visible():
                            btn_text = await btn.inner_text()
                            print(f"Button found: [{sel}] = '{btn_text.strip()}'", flush=True)
                            select_btn = btn
                            break
                    except Exception:
                        continue
                
                if not select_btn:
                    print("Select button nahi mila", flush=True)
                    # Phir bhi seen mein add kar do taaki baar baar try na kare
                    seen_messages.add(msg_key)
                    continue
                
                # Select button click karo
                await select_btn.click(timeout=3000)
                await asyncio.sleep(2)
                
                # SMS details extract karo
                dt, full_msg = await get_sms_details(page, ph, sender)
                
                if not full_msg:
                    print("Message nahi mila, skip", flush=True)
                    seen_messages.add(msg_key)
                    continue
                
                # Seen mein add karo
                seen_messages.add(msg_key)
                
                # OTP extract karo
                otp = extract_otp(full_msg)
                print(f"OTP: {otp}", flush=True)
                
                # Message format - simple aur clean, user ke hisaab se
                message_text = f"""📱 *Number*: `{escape_markdown(mask_phone(ph))}`
🔑 *OTP*: `{escape_markdown(otp)}`
📝 *Message*:
`{escape_markdown(full_msg[:400])}`"""
                
                if dt:
                    message_text = f"⏰ *Time*: `{escape_markdown(dt)}`\n" + message_text
                
                await send_msg(OTP_CHANNEL_ID, message_text, app)
                await send_msg(OTP_GROUP_ID, message_text, app)
                
            except Exception as row_err:
                print(f"Row {i} error: {row_err}", flush=True)
                continue
        
        # Memory management - 300 se zyada ho jaye toh purane hata do
        if len(seen_messages) > 300:
            seen_messages = set(list(seen_messages)[-150:])
        
        return True
        
    except Exception as e:
        print(f"Check SMS error: {e}", flush=True)
        return False

# ========== MAIN ==========
async def main():
    print("Bot Starting...", flush=True)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Bot is Active! Login process in progress...")
    
    async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text(
                f"Bot Running\nCheck every {POLL_INTERVAL}s\nProcessed: {len(seen_messages)}"
            )
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    
    await app.initialize()
    await app.start()
    
    # Webhook clean karo + pending updates drop karo
    print("Cleaning webhook & pending updates...", flush=True)
    await app.bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    
    # Polling start karo
    await app.updater.start_polling(drop_pending_updates=True, allowed_updates=[])
    print("Telegram Connected & Polling Started!", flush=True)
    
    while True:
        login_ok, page = await login_panel(app)
        if not login_ok or not page:
            print("Retry login in 8s...", flush=True)
            await asyncio.sleep(8)
            continue
        
        print("Monitoring Started!", flush=True)
        
        while True:
            check_ok = await check_sms(app, page)
            if not check_ok:
                print("Session lost - Re-logging in...", flush=True)
                await cleanup_resources(page)
                break
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot Stopped by User", flush=True)
