# Amazon NL Scraper — 24/7 edition
# Working perfect

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
# Scraper puts payloads here instantly (non-blocking).
# A single daemon thread drains the queue and handles all rate-limiting.
_discord_queue: queue.Queue = queue.Queue()
DISCORD_MIN_INTERVAL = 1.0   # seconds between sends — safe under Discord's limit

def _discord_worker():
    """Background thread: drains the queue and sends to Discord safely."""
    while True:
        payload = _discord_queue.get()          # blocks until something arrives
        if payload is None:                     # None = shutdown signal
            break
        name_preview = payload.get("_name", "")[:60]
        payload.pop("_name", None)              # remove internal key before sending
        sent = False
        for attempt in range(3):                # up to 3 attempts per item
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
        time.sleep(DISCORD_MIN_INTERVAL)        # pace ourselves between sends
        _discord_queue.task_done()

# Start the worker thread (daemon=True so it dies when main exits)
_discord_thread = threading.Thread(target=_discord_worker, daemon=True, name="DiscordWorker")
_discord_thread.start()

# Headers
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
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
        "_name": product_name,   # internal key stripped before sending
        "username": "Amazon Scraper Bot 🤖",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg",
        "embeds": [embed]
    }

    _discord_queue.put(payload)   # ← non-blocking, returns immediately
    print(f"  📬 Queued Discord notification for: {product_name[:60]}  (queue size: {_discord_queue.qsize()})")


BRAVE_EXE = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"


def _get_brave_major_version() -> int | None:
    """
    Auto-detects the installed Brave major version so we never have to
    hard-code version_main again. Tries three methods in order:

    1. PowerShell  – reads the .exe file version directly (most reliable)
    2. winreg      – reads Brave's BLBeacon registry key
    3. Returns None – caller falls back to letting uc auto-detect
    """
    # ── Method 1: PowerShell FileVersionInfo ──────────────────────────────
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f'(Get-Item "{BRAVE_EXE}").VersionInfo.ProductVersion'
            ],
            capture_output=True, text=True, timeout=8
        )
        version_str = result.stdout.strip()          # e.g. "147.0.7727.117"
        if version_str:
            major = int(version_str.split(".")[0])
            print(f"  🔍 Brave version detected (PowerShell): {version_str}  →  version_main={major}")
            return major
    except Exception:
        pass

    # ── Method 2: Windows Registry (BLBeacon) ────────────────────────────
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\BraveSoftware\Brave-Browser\BLBeacon"
        )
        version_str, _ = winreg.QueryValueEx(key, "version")
        winreg.CloseKey(key)
        major = int(version_str.split(".")[0])
        print(f"  🔍 Brave version detected (registry): {version_str}  →  version_main={major}")
        return major
    except Exception:
        pass

    print("  ⚠️  Could not detect Brave version — letting undetected_chromedriver auto-detect.")
    return None


def setup_selenium():
    options = Options()
    options.binary_location = BRAVE_EXE
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--incognito")
    options.add_argument(f"--user-agent={headers['User-Agent']}")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--disable-features=SessionRestore")

    # ── Auto-detect browser version — no manual updates ever needed ──────
    brave_version = _get_brave_major_version()

    try:
        driver = uc.Chrome(
            options=options,
            headless=False,
            use_subprocess=False,
            version_main=brave_version,   # None → uc will auto-detect
        )
        return driver
    except WebDriverException as e:
        print(f"Selenium setup failed: {e}")
        return None

# ✅ UPDATED PRICE FUNCTION
def extract_prices(product):
    # ✅ Current price (offscreen)
    offscreen = product.select_one('span.a-price span.a-offscreen')
    current_price = offscreen.text.strip() if offscreen and offscreen.text.strip() else "N/A"

    # ✅ Previous/List price
    previous_price = "N/A"

    # Look for "List:" price
    list_price_span = product.find('span', string=re.compile(r'List:', re.I))
    if list_price_span:
        parent = list_price_span.find_parent()
        if parent:
            offscreen_list = parent.find('span', class_='a-offscreen')
            if offscreen_list:
                previous_price = offscreen_list.text.strip()

    # Alternative fallback (strikethrough price)
    if previous_price == "N/A":
        strike = product.find('span', class_='a-price a-text-price')
        if strike:
            off = strike.find('span', class_='a-offscreen')
            if off:
                previous_price = off.text.strip()

    # If both prices are same → no discount → set previous as N/A
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
            # input("press")
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.s-result-item"))
            )
            soup = BeautifulSoup(driver.page_source, 'html.parser')
        except TimeoutException:
            print(f"  Timeout loading page {page}. Falling back to requests.")
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
            except requests.RequestException:
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

        time.sleep(random.uniform(0.5,1))
        page += 1

    return all_scraped_data, na_data


def save_data(keyword, all_scraped_data, na_data):
    """Saves scraped data to CSV files."""

    # Sort based on CURRENT price
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
        shutil.move(tmp_name, filename)  # Atomic on same filesystem
    except Exception as e:
        print(f"  ⚠️  Failed to write {filename}: {e}")
        try:
            os.remove(tmp_name)
        except Exception:
            pass


def _force_kill_driver(driver):
    """Quit the driver gracefully; fall back to killing the process on failure."""
    try:
        driver.quit()
    except Exception:
        pass  # Already dead or handle error — try OS-level kill
    try:
        # Kill any lingering chrome/brave processes spawned by this Python PID
        subprocess.run(
            ["taskkill", "/F", "/IM", "brave.exe"],
            capture_output=True, timeout=5
        )
    except Exception:
        pass


def main():
# ─────────────────────────────────────────────
#  Main loop — runs every 3 minutes
# ─────────────────────────────────────────────
    run_count = 0

    while True:
        run_count += 1
        print(f"\n{'='*60}")
        print(f"  Run #{run_count}  |  {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Keywords: {', '.join(keywords)}")
        print(f"{'='*60}\n")

        # Initialize Selenium once per run (shared across all keywords)
        driver = setup_selenium()
        if not driver:
            print("Cannot proceed without Selenium. Retrying in 3 minutes...")
            time.sleep(180)
            continue

        # Loop through each keyword
        try:
            for i, keyword in enumerate(keywords, 1):
                print(f"\n[{i}/{len(keywords)}] Keyword: '{keyword}'")
                print("-" * 60)

                all_scraped_data, na_data = scrape_keyword(driver, keyword)
                save_data(keyword, all_scraped_data, na_data)

                # Small delay between keywords to avoid rate limiting
                if i < len(keywords):
                    print(f"\n  Waiting 5 seconds before next keyword...\n")
                    time.sleep(3)
        except KeyboardInterrupt:
            print("\n  KeyboardInterrupt received. Shutting down...")
            _force_kill_driver(driver)
            return
        except Exception as e:
            print(f"  ⚠️  Unexpected error during scraping: {e}")
        finally:
            # Always clean up the driver, even on crash
            _force_kill_driver(driver)

        print(f"\n{'='*60}")
        print(f"  All keywords done for Run #{run_count}")
        print(f"  Next run in {BETWEEN_RUNS_SLEEP}s... (Press Ctrl+C to stop)")
        print(f"{'='*60}\n")
        time.sleep(BETWEEN_RUNS_SLEEP)


if __name__ == "__main__":
    main()