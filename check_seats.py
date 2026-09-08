import os
from datetime import datetime, time
import zoneinfo
import requests
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.icaionlineregistration.org/launchbatchdetail.aspx"

def is_within_active_hours():
    """Checks if current time is between 8:00 AM and 12:00 Midnight IST."""
    ist_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(ist_tz)
    current_time = now_ist.time()

    # Active window: 08:00:00 to 23:59:59 (8:00 AM to Midnight IST)
    start_time = time(8, 0, 0)
    end_time = time(23, 59, 59)

    if start_time <= current_time <= end_time:
        return True
    
    print(f"Current time is {now_ist.strftime('%I:%M %p')} IST. Outside 8:00 AM - 12:00 Midnight window. Skipping check.")
    return False

def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not configured.")
        return
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(api_url, json=payload, timeout=15)
        print("Telegram notification sent, status:", res.status_code)
    except Exception as e:
        print("Error sending Telegram message:", e)

def check_icai_seats():
    # 1. Enforce time window guard
    if not is_within_active_hours():
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating to ICAI portal...")
        page.goto(URL, timeout=60000)

        # 2. Select Region: Eastern
        page.select_option("select[id*='ddlRegion']", label="Eastern")
        page.wait_for_timeout(2500)

        # 3. Select POU: Kolkata
        page.select_option("select[id*='ddlPOU']", label="Kolkata")
        page.wait_for_timeout(2500)

        # 4. Select Course: AICITSS - Advanced Information Technology
        page.select_option("select[id*='ddlCourse']", label="AICITSS - Advanced Information Technology")
        page.wait_for_timeout(2500)

        # 5. Click Search button if present
        search_btn = page.locator("input[type='submit'][value*='Search'], input[id*='btnSearch']")
        if search_btn.count() > 0:
            search_btn.first.click()
            page.wait_for_timeout(3500)

        # 6. Parse the batch details table
        table_rows = page.locator("table tr").all()
        header_indices = {}
        vacant_8am_batches = []

        # Find column headers
        for row in table_rows:
            th_cells = row.locator("th").all()
            if th_cells:
                headers = [th.inner_text().strip().lower() for th in th_cells]
                for idx, h in enumerate(headers):
                    if "timing" in h or "time" in h:
                        header_indices["timing"] = idx
                    if "available" in h or "vacan" in h:
                        header_indices["available"] = idx
                    if "batch" in h:
                        header_indices["batch"] = idx
                    if "date" in h:
                        header_indices["dates"] = idx
                break

        # Check rows for 8:00 AM batches with seats > 0
        for row in table_rows:
            td_cells = [td.inner_text().strip() for td in row.locator("td").all()]
            if not td_cells:
                continue

            row_text = " ".join(td_cells)

            if "8:00 AM" in row_text:
                avail_seats = 0
                if "available" in header_indices and header_indices["available"] < len(td_cells):
                    val = td_cells[header_indices["available"]]
                    if val.isdigit():
                        avail_seats = int(val)
                else:
                    for cell in td_cells:
                        if cell.isdigit() and int(cell) > 0 and ("Available" in row_text or "Seats" in row_text):
                            avail_seats = int(cell)
                            break

                batch_name = td_cells[header_indices["batch"]] if "batch" in header_indices and header_indices["batch"] < len(td_cells) else "8:00 AM Batch"
                dates = td_cells[header_indices["dates"]] if "dates" in header_indices and header_indices["dates"] < len(td_cells) else ""

                if avail_seats > 0:
                    vacant_8am_batches.append(f"• *{batch_name}*\n  - Dates: {dates}\n  - Available Seats: *{avail_seats}*")

        browser.close()

        # 7. Notify ONLY if an 8:00 AM slot is available
        if vacant_8am_batches:
            alert_message = (
                "🚨 *ICAI AICITSS Seat Vacancy Found!*\n\n"
                "*Location:* Kolkata (Eastern Region)\n"
                "*Timing:* 8:00 AM – 2:00 PM\n\n"
                + "\n\n".join(vacant_8am_batches)
                + "\n\n🔗 [Book Immediately on ICAI Portal](https://www.icaionlineregistration.org/launchbatchdetail.aspx)"
            )
            print("Vacancy detected! Sending Telegram notification...")
            send_telegram_alert(alert_message)
        else:
            print("Check complete: 0 seats available for 8:00 AM batches. No alert sent.")

if __name__ == "__main__":
    check_icai_seats()
