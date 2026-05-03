# Amazon NL Scraper — 24/7 Cloud Edition (Oracle Cloud / Linux)
# ✅ Modified from Final_testing.py for headless Linux server deployment
# Changes made:
#   - Removed Brave Browser → uses system Chrome
#   - Removed winreg (Windows-only) → version auto-detected by uc
#   - Removed taskkill (Windows-only) → uses pkill (Linux)
#   - Added headless Chrome flags for server environment

import requests
from bs4 import BeautifulSoup
import csv
import time, random
import re
import os
import subprocess
import tempfile
import shutil
import threading
import queue
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Configuration (change these as needed)
keywords = ["Laptops", "Speakers", "Monitors", "Lamps","Iphone","Airbuds"]  # ← Add as many keywords as you want
max_price_filter = None  # Filter products with price <= this value (in USD, set to None to disable)
BETWEEN_RUNS_SLEEP = 180  # Seconds to wait between full scrape cycles

# Discord Webhook
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1491447455454203955/pCyighiZvpBxofRp6C-xfRnKNuljGngc59ZNSgH8BxOAq7Cqn1yAiYELcCrufuqqKWSj"

# ── Cross-run deduplication: tracks ASINs already notified to Discord ──
global_seen_asins: set = set()

# ── Background Discord queue ─────────────────────────────────────────────────
_discord_queue: queue.Queue = queue.Queue()
DISCORD_MIN_INTERVAL = 1.0   # seconds between sends — safe under Discord's limit

def _discord_worker():
    """Background thread: drains the queue and sends to Discord safely."""
    while True:
        payload = _discord_queue.get()
        if payload is None:
            break
        name_preview = payload.get("_name", "")[:60]
        payload.pop("_name", None)
        sent = False
        for attempt in range(3):
            try:
                response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
                if response.status_code == 204:
                    print(f"  ✅ Discord sent: {name_preview}")
                    sent = True
                    break
                elif response.status_code == 429:
                    try:
                        retry_after = float(response.json().get("retry_after", 2))
                    except Exception:
                        retry_after = 2.0
                    print(f"  ⚠️  Discord rate limited — waiting {retry_after:.1f}s (attempt {attempt+1})")
                    time.sleep(retry_after)
                else:
                    print(f"  ⚠️  Discord error {response.status_code}: {response.text[:80]}")
                    break
            except Exception as exc:
                print(f"  ⚠️  Discord request failed: {exc}")
                time.sleep(2)
        if not sent:
            print(f"  ❌ Gave up sending Discord notification for: {name_preview}")
        time.sleep(DISCORD_MIN_INTERVAL)
        _discord_queue.task_done()

# Start the worker thread
_discord_thread = threading.Thread(target=_discord_worker, daemon=True, name="DiscordWorker")
_discord_thread.start()

# Headers
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.amazon.nl/",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def send_discord_notification(product_name, current_price, previous_price, link, keyword):
    """
    Enqueues a Discord notification — returns INSTANTLY.
    The background _discord_worker thread handles sending, rate-limiting, and retries.
    """
    color = 0x2ECC71 if previous_price != "N/A" else 0x3498DB

    fields = [{"name": "💰 Current Price", "value": f"```{current_price}```", "inline": True}]
    if previous_price != "N/A":
        fields.append({"name": "~~Was~~ Previous Price", "value": f"~~{previous_price}~~", "inline": True})
    fields.append({"name": "🔗 Product Link", "value": f"[Click here to view on Amazon]({link})", "inline": False})

    embed = {
        "title": f"🛒 {product_name[:250]}",
        "url": link if link != "N/A" else None,
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"Amazon NL Scraper  •  Keyword: {keyword}  •  {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "icon_url": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg"
        },
        "thumbnail": {"url": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg"}
    }

    payload = {
        "_name": product_name,
        "username": "Amazon Scraper Bot 🤖",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg",
        "embeds": [embed]
    }

    _discord_queue.put(payload)
    print(f"  📬 Queued Discord notification for: {product_name[:60]}  (queue size: {_discord_queue.qsize()})")


# ── CLOUD VERSION: Setup Chrome in headless mode (no Brave, no Windows registry) ──
def get_chrome_main_version():
    """Dynamically detects the installed Chrome version on the Linux server."""
    try:
        # Runs `google-chrome --version` and extracts the major number (e.g., "147" from "Google Chrome 147.0.x.x")
        output = subprocess.check_output(['google-chrome', '--version']).decode('utf-8')
        version_str = re.search(r'\d+', output).group()
        return int(version_str)
    except Exception as e:
        print(f"Could not auto-detect Chrome version: {e}")
        return None

def setup_selenium():
    options = Options()
    # ✅ No binary_location — uses system Chrome installed via apt
    options.add_argument("--headless=new")           # ✅ Headless: no screen needed
    options.add_argument("--no-sandbox")              # ✅ Required on Linux servers
    options.add_argument("--disable-dev-shm-usage")  # ✅ Prevents crashes on low RAM VMs
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--incognito")
    options.add_argument(f"--user-agent={headers['User-Agent']}")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--disable-features=SessionRestore")

    chrome_version = get_chrome_main_version()

    try:
        kwargs = {
            "options": options,
            "headless": True,
            "use_subprocess": True,
        }
        if chrome_version:
            kwargs["version_main"] = chrome_version  # ✅ Automatically matches installed version!

        driver = uc.Chrome(**kwargs)
        driver.set_page_load_timeout(30) # ✅ Prevents the 120s timeout hang
        return driver
    except WebDriverException as e:
        print(f"Selenium setup failed: {e}")
        return None


# ✅ UPDATED PRICE FUNCTION
def extract_prices(product):
    offscreen = product.select_one('span.a-price span.a-offscreen')
    current_price = offscreen.text.strip() if offscreen and offscreen.text.strip() else "N/A"

    previous_price = "N/A"

    list_price_span = product.find('span', string=re.compile(r'List:', re.I))
    if list_price_span:
        parent = list_price_span.find_parent()
        if parent:
            offscreen_list = parent.find('span', class_='a-offscreen')
            if offscreen_list:
                previous_price = offscreen_list.text.strip()

    if previous_price == "N/A":
        strike = product.find('span', class_='a-price a-text-price')
        if strike:
            off = strike.find('span', class_='a-offscreen')
            if off:
                previous_price = off.text.strip()

    if previous_price != "N/A" and current_price != "N/A":
        if re.sub(r'[^\d.]', '', previous_price) == re.sub(r'[^\d.]', '', current_price):
            previous_price = "N/A"

    return previous_price, current_price


def parse_price(price_str):
    if price_str == "N/A":
        return None
    try:
        return float(re.sub(r'[^\d.]', '', price_str))
    except (ValueError, TypeError):
        return None


def scrape_keyword(driver, keyword):
    """Scrapes all pages for a single keyword and returns the data."""

    base_url = f"https://www.amazon.nl/s?k={keyword.replace(' ', '+')}"

    all_scraped_data = []
    na_data = []

    seen_asins_main = set()
    seen_asins_na = set()

    page = 1
    MAX_PAGES = 20

    while page <= MAX_PAGES:
        url = f"{base_url}&page={page}"

        print(f"  Scraping page {page}...")

        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.s-result-item"))
            )
            soup = BeautifulSoup(driver.page_source, 'html.parser')
        except Exception as e:
            print(f"  Timeout/Error loading page {page}: {e}. Falling back to requests.")
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # If requests also returns a likely block page (no products), treat as failure
                if not soup.find_all('div', class_='s-result-item'):
                    if page == 1:
                        raise Exception("Amazon Block Detected (No products found via requests).")
            except requests.RequestException:
                if page == 1:
                    raise Exception(f"Critical connection failure on Page 1. Fallback failed.")
                break

        products = soup.find_all('div', class_='s-result-item')

        if not products:
            break

        page_data = []
        page_na_count = 0

        for product in products:
            if 'data-asin' not in product.attrs or not product.attrs['data-asin']:
                continue

            asin = product.attrs['data-asin']

            name_elem = product.select_one('h2 span')
            name = name_elem.text.strip() if name_elem else "N/A"
            link_elem = product.select_one('a.a-link-normal.s-line-clamp-4.s-link-style.a-text-normal')

            if link_elem and link_elem.get("href"):
                Link = "https://www.amazon.nl" + link_elem.get("href")
            else:
                Link = "N/A"

            previous_price, current_price = extract_prices(product)

            if name == "N/A" or (previous_price == "N/A" and current_price == "N/A"):
                if asin in seen_asins_na:
                    continue
                seen_asins_na.add(asin)

                na_data.append({
                    "Product": name,
                    "Link": Link,
                    "Previous Price": previous_price,
                    "Current Price": current_price
                })
                page_na_count += 1

                print(f"  N/A Product: {name}")
                print(f"  N/A Product: {Link}")
                print(f"  Previous Price: {previous_price}")
                print(f"  Current Price: {current_price}")
                print("  " + "-" * 50)
            else:
                if asin in seen_asins_main:
                    continue
                seen_asins_main.add(asin)

                page_data.append({
                    "Product": name,
                    "Link": Link,
                    "Previous Price": previous_price,
                    "Current Price": current_price
                })

                print(f"  Product: {name}")
                print(f"  Link: {Link}")
                print(f"  Previous Price: {previous_price}")
                print(f"  Current Price: {current_price}")
                print("  " + "-" * 50)

                # 🔔 Send Discord notification only for new ASINs (cross-run dedup)
                if asin not in global_seen_asins:
                    global_seen_asins.add(asin)
                    send_discord_notification(name, current_price, previous_price, Link, keyword)

        all_scraped_data.extend(page_data)

        if not page_data and page_na_count == 0:
            break

        time.sleep(random.uniform(0.5, 1))
        page += 1

    return all_scraped_data, na_data


def save_data(keyword, all_scraped_data, na_data):
    """Saves scraped data to CSV files."""

    all_scraped_data.sort(
        key=lambda x: parse_price(x["Current Price"]) if parse_price(x["Current Price"]) is not None else float('inf')
    )

    filtered_data = all_scraped_data
    if max_price_filter is not None:
        filtered_data = [
            item for item in all_scraped_data
            if parse_price(item["Current Price"]) is not None and parse_price(item["Current Price"]) <= max_price_filter
        ]

    if all_scraped_data:
        filename_all = f"amazon_{keyword}_all_pages_data.csv"
        _safe_write_csv(filename_all, all_scraped_data)
        print(f"  All data saved to {filename_all}")
        print(f"  Total scraped products: {len(all_scraped_data)}")
    else:
        print(f"  No data to save for keyword: {keyword}")

    if filtered_data and max_price_filter is not None:
        filename_filtered = f"amazon_{keyword}_filtered_price_below_{max_price_filter}_data.csv"
        _safe_write_csv(filename_filtered, filtered_data)
        print(f"  Filtered data saved to {filename_filtered}")


def _safe_write_csv(filename: str, rows: list):
    """Writes CSV atomically via a temp file to avoid corruption on crash."""
    fieldnames = ["Product", "Previous Price", "Current Price", "Link"]
    dir_name = os.path.dirname(os.path.abspath(filename)) or "."
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8",
            dir=dir_name, delete=False, suffix=".tmp"
        ) as tmp:
            tmp_name = tmp.name
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        shutil.move(tmp_name, filename)
    except Exception as e:
        print(f"  ⚠️  Failed to write {filename}: {e}")
        try:
            os.remove(tmp_name)
        except Exception:
            pass


def _force_kill_driver(driver):
    """Quit the driver gracefully; fall back to killing Chrome process on Linux."""
    try:
        driver.quit()
    except Exception:
        pass
    try:
        # ✅ Linux version: pkill instead of Windows taskkill
        subprocess.run(
            ["pkill", "-f", "chrome"],
            capture_output=True, timeout=5
        )
    except Exception:
        pass


def main():
    run_count = 0

    while True:
        run_count += 1
        print(f"\n{'='*60}")
        print(f"  Run #{run_count}  |  {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Keywords: {', '.join(keywords)}")
        print(f"{'='*60}\n")

        keyword_index = 0
        driver = None

        while keyword_index < len(keywords):
            if driver is None:
                driver = setup_selenium()
                if not driver:
                    print("Cannot proceed without Selenium. Retrying in 3 minutes...")
                    time.sleep(180)
                    continue

            keyword = keywords[keyword_index]
            try:
                print(f"\n[{keyword_index + 1}/{len(keywords)}] Keyword: '{keyword}'")
                print("-" * 60)

                all_scraped_data, na_data = scrape_keyword(driver, keyword)
                save_data(keyword, all_scraped_data, na_data)

                # Move to next keyword only if successful
                keyword_index += 1

                if keyword_index < len(keywords):
                    print(f"\n  Waiting 3 seconds before next keyword...\n")
                    time.sleep(3)

            except KeyboardInterrupt:
                print("\n  KeyboardInterrupt received. Shutting down...")
                _force_kill_driver(driver)
                return
            except Exception as e:
                print(f"  ⚠️  Unexpected error during keyword '{keyword}': {e}")
                print(f"  Restarting browser to resume from '{keyword}'...")
                _force_kill_driver(driver)
                driver = None  # Force driver to be recreated on next loop
                time.sleep(5)  # Brief pause before restarting browser

        # Cleanup driver at the end of the full run
        if driver:
            _force_kill_driver(driver)

        print(f"\n{'='*60}")
        print(f"  All keywords done for Run #{run_count}")
        print(f"  Next run in {BETWEEN_RUNS_SLEEP}s... (Press Ctrl+C to stop)")
        print(f"{'='*60}\n")
        time.sleep(BETWEEN_RUNS_SLEEP)


if __name__ == "__main__":
    main()
