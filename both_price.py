import requests
from bs4 import BeautifulSoup
import csv
import time
import re
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Multiple keywords (URLs)
keywords = ["Laptops", "Mobiles", "Headphones"]

# Configuration
max_price_filter = None

# Headers
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Referer": "https://www.amazon.com/",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def setup_selenium():
    options = Options()
    options.headless = True
    options.add_argument(f"user-agent={headers['User-Agent']}")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except WebDriverException as e:
        print(f"Selenium setup failed: {e}")
        return None

def is_sponsored(product):
    sponsored = product.find('span', string=re.compile('Sponsored', re.I)) or \
                product.find('span', class_=re.compile('s-sponsored-label', re.I))
    return sponsored is not None

# ✅ MODIFIED ONLY THIS FUNCTION
def extract_price(product):
    # Previous price
    offscreen = product.find('span', class_='a-offscreen')
    previous_price = offscreen.text.strip() if offscreen and offscreen.text.strip() else "N/A"
    
    # Current price
    whole = product.find('span', class_='a-price-whole')
    fraction = product.find('span', class_='a-price-fraction')
    
    if whole and fraction:
        current_price = f"${whole.text.strip()}.{fraction.text.strip()}"
    elif whole:
        current_price = f"${whole.text.strip()}.00"
    else:
        current_price = "N/A"
    
    return current_price, previous_price


def extract_rating(product):
    rating_elem = product.find('span', class_='a-icon-alt')
    return rating_elem.text.strip() if rating_elem else "N/A"

def parse_price(price_str):
    if price_str == "N/A":
        return None
    try:
        return float(re.sub(r'[^\d.]', '', price_str))
    except (ValueError, TypeError):
        return None

def run_scraper(keyword):

    base_url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}"

    driver = setup_selenium()
    if not driver:
        print("Cannot proceed without Selenium.")
        return

    all_scraped_data = []
    na_data = []

    page = 1
    while True:
        url = f"{base_url}&page={page}"
        
        print(f"[{keyword}] Scraping page {page}...")
        
        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.s-result-item"))
            )
            soup = BeautifulSoup(driver.page_source, 'html.parser')
        except TimeoutException:
            print(f"Timeout page {page}, fallback requests")
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
            
            if is_sponsored(product):
                continue
            
            name_elem = product.select_one('h2 span')
            name = name_elem.text.strip() if name_elem else "N/A"
            
            current_price, previous_price = extract_price(product)
            rating = extract_rating(product)
            
            if name == "N/A" or current_price == "N/A":
                na_data.append({
                    "Product": name,
                    "Current Price": current_price,
                    "Previous Price": previous_price,
                    "Rating": rating
                })
                page_na_count += 1
            else:
                page_data.append({
                    "Product": name,
                    "Current Price": current_price,
                    "Previous Price": previous_price,
                    "Rating": rating
                })
        
        all_scraped_data.extend(page_data)
        
        if not page_data and page_na_count == 0:
            break
        
        time.sleep(3)
        page += 1

    driver.quit()

    # Sorting based on current price
    all_scraped_data.sort(
        key=lambda x: parse_price(x["Current Price"]) if parse_price(x["Current Price"]) is not None else float('inf')
    )

    filename = f"amazon_{keyword}.csv"
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Product", "Current Price", "Previous Price", "Rating"])
        writer.writeheader()
        writer.writerows(all_scraped_data)

    print(f"[{keyword}] Done. Total: {len(all_scraped_data)}")


# 🔁 Run every 3 minutes
while True:
    print("Starting new cycle...\n")
    
    for keyword in keywords:
        run_scraper(keyword)
    
    print("Sleeping for 3 minutes...\n")
    time.sleep(180)