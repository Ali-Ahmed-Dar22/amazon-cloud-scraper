import requests
from bs4 import BeautifulSoup
import csv
import time
import re
import os
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Configuration (change these as needed)
keywords = ["T-shirt", "Jeans", "Sneakers"]  # ← Add as many keywords as you want
max_price_filter = None  # Filter products with price <= this value (in USD, set to None to disable)

# Headers
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.amazon.nl/",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def setup_selenium():
    options = Options()
    options.binary_location = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # options.add_argument(f"--user-data-dir={os.path.expanduser('~/amazon_profile_' + str(int(time.time())))}")
    options.add_argument("--incognito")
    options.add_argument(f"--user-agent={headers['User-Agent']}")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--disable-features=SessionRestore")
    options.add_argument("--disable-dev-shm-usage")
    
    try:
        driver = uc.Chrome(options=options,            
            headless=False,
            use_subprocess=True,
            version_main=146)
        
        return driver
    except WebDriverException as e:
        print(f"Selenium setup failed: {e}")
        return None

# ✅ UPDATED PRICE FUNCTION
def extract_prices(product):
    # ✅ Current price (offscreen)
    offscreen = product.find('span', class_='a-offscreen')
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
            try:
                Link = product.select_one('a', class_='a-link-normal s-line-clamp-4 s-link-style a-text-normal').text
            except:
                Link = "N/A"

            previous_price, current_price = extract_prices(product)

            if name == "N/A" or (previous_price == "N/A" and current_price == "N/A"):
                if asin in seen_asins_na:
                    continue
                seen_asins_na.add(asin)

                na_data.append({
                    "Product": name,
                    "Previous Price": previous_price,
                    "Current Price": current_price
                })
                page_na_count += 1

                print(f"  N/A Product: {name}")
                print(f"  Previous Price: {previous_price}")
                print(f"  Current Price: {current_price}")
                print("  " + "-" * 50)
            else:
                if asin in seen_asins_main:
                    continue
                seen_asins_main.add(asin)

                page_data.append({
                    "Product": name,
                    "Previous Price": previous_price,
                    "Current Price": current_price
                })

                print(f"  Product: {name}")
                print(f"  Link: {Link}")
                print(f"  Previous Price: {previous_price}")
                print(f"  Current Price: {current_price}")
                print("  " + "-" * 50)

        all_scraped_data.extend(page_data)

        if not page_data and page_na_count == 0:
            break

        time.sleep(3)
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
        with open(filename_all, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["Product", "Previous Price", "Current Price"])
            writer.writeheader()
            writer.writerows(all_scraped_data)
        print(f"  All data saved to {filename_all}")
        print(f"  Total scraped products: {len(all_scraped_data)}")
    else:
        print(f"  No data to save for keyword: {keyword}")

    if filtered_data and max_price_filter is not None:
        filename_filtered = f"amazon_{keyword}_filtered_price_below_{max_price_filter}_data.csv"
        with open(filename_filtered, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["Product", "Previous Price", "Current Price"])
            writer.writeheader()
            writer.writerows(filtered_data)
        print(f"  Filtered data saved to {filename_filtered}")

    if na_data:
        filename_na = f"amazon_{keyword}_na_products.csv"
        with open(filename_na, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["Product", "Previous Price", "Current Price"])
            writer.writeheader()
            writer.writerows(na_data)
        print(f"  N/A data saved to {filename_na}")
    else:
        print(f"  No N/A products for keyword: {keyword}")

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
        for i, keyword in enumerate(keywords, 1):
            print(f"\n[{i}/{len(keywords)}] Keyword: '{keyword}'")
            print("-" * 60)

            all_scraped_data, na_data = scrape_keyword(driver, keyword)
            save_data(keyword, all_scraped_data, na_data)

            # Small delay between keywords to avoid rate limiting
            if i < len(keywords):
                print(f"\n  Waiting 5 seconds before next keyword...\n")
                time.sleep(5)

       
        driver.quit()

        print(f"\n{'='*60}")
        print(f"  All keywords done for Run #{run_count}")
        print(f"  Next run in 3 minutes... (Press Ctrl+C to stop)")
        print(f"{'='*60}\n")
        time.sleep(30)


if __name__ == "__main__":
    main()