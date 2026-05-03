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

# Configuration (change these as needed)
keyword = "Laptops"  # Search term
max_price_filter = None  # Filter products with price <= this value (in USD, set to None to disable) must set in (float)
image_folder = "product_images"  # Folder to save downloaded images
na_image_folder = "na_product_images"  # Folder to save N/A product images

# Create image folders if they don't exist
if not os.path.exists(image_folder):
    os.makedirs(image_folder)
if not os.path.exists(na_image_folder):
    os.makedirs(na_image_folder)

# Base Amazon search URL
base_url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}"

# Headers for requests (used as fallback or for Selenium user-agent)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Referer": "https://www.amazon.com/",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def setup_selenium():
    """Set up Selenium with headless Chrome."""
    options = Options()
    options.headless = True  # Run without opening a window
    options.add_argument(f"user-agent={headers['User-Agent']}")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    try:
        driver = webdriver.Chrome(options=options)  # Add executable_path="path/to/chromedriver" if needed
        return driver
    except WebDriverException as e:
        print(f"Selenium setup failed: {e}")
        return None

def is_sponsored(product):
    """Check if the product is sponsored."""
    sponsored = product.find('span', string=re.compile('Sponsored', re.I)) or \
                product.find('span', class_=re.compile('s-sponsored-label', re.I))
    return sponsored is not None

def extract_price(product):
    """
    Robust price extraction with multiple fallbacks.
    """
    # Primary: a-offscreen (full price like $12.34)
    offscreen = product.find('span', class_='a-offscreen')
    if offscreen and offscreen.text.strip():
        return offscreen.text.strip()
    
    # Secondary: Composed price (whole + fraction)
    whole = product.find('span', class_='a-price-whole')
    fraction = product.find('span', class_='a-price-fraction')
    if whole and fraction:
        return f"${whole.text.strip()}.{fraction.text.strip()}"
    
    # Tertiary: Whole price only
    if whole:
        return f"${whole.text.strip()}.00"
    
    # Quaternary: a-color-price (for special listings)
    color_price = product.find('span', class_='a-color-price')
    if color_price and color_price.text.strip():
        return color_price.text.strip()
    
    # Final fallback: Scan spans for $ and digits
    spans = product.find_all('span')
    for span in spans:
        text = span.text.strip()
        if '$' in text and any(c.isdigit() for c in text.replace('$', '').replace(',', '')):
            clean_price = re.sub(r'[^\d$.]', '', text)
            if clean_price.startswith('$') and '.' in clean_price:
                return text.strip()
    
    return "N/A"

def extract_rating(product):
    """
    Extract star rating (e.g., '4.5 out of 5 stars').
    """
    rating_elem = product.find('span', class_='a-icon-alt')
    return rating_elem.text.strip() if rating_elem else "N/A"

def extract_image_url(product):
    """
    Extract the main product image URL.
    """
    img_elem = product.find('img', class_='s-image')
    if img_elem and 'src' in img_elem.attrs:
        return img_elem['src']
    return None

def download_image(image_url, asin, folder):
    """
    Download the image to the specified folder using ASIN as filename.
    Returns the local path if successful, else "N/A".
    """
    if not image_url:
        return "N/A"
    try:
        response = requests.get(image_url, headers=headers, timeout=5)
        response.raise_for_status()
        file_path = os.path.join(folder, f"{asin}.jpg")
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return file_path
    except Exception as e:
        print(f"Failed to download image for ASIN {asin}: {e}")
        return "N/A"

def parse_price(price_str):
    """
    Convert price string (e.g., '$499.99') to float for sorting/filtering.
    Returns None if price is N/A or invalid.
    """
    if price_str == "N/A":
        return None
    try:
        # Remove $ and commas, convert to float
        return float(re.sub(r'[^\d.]', '', price_str))
    except (ValueError, TypeError):
        return None

# Initialize Selenium
driver = setup_selenium()
if not driver:
    print("Cannot proceed without Selenium. Please check ChromeDriver installation.")
    exit()

# List to store all scraped data and N/A data
all_scraped_data = []
na_data = []

page = 1
while True:
    # Construct URL with page parameter
    url = f"{base_url}&page={page}"
    
    print(f"Scraping page {page}...")
    
    # Try Selenium first
    try:
        driver.get(url)
        # Wait for product containers to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.s-result-item"))
        )
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except TimeoutException:
        print(f"Timeout loading page {page}. Falling back to requests.")
        # Fallback to requests if Selenium fails
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            print(f"Requests failed for page {page}: {e}")
            break  # Stop if request fails, assuming no more pages
    
    # Find all product containers
    products = soup.find_all('div', class_='s-result-item')
    
    # If no product containers found, stop pagination
    if not products:
        print(f"No more products found on page {page}. Stopping pagination.")
        break
    
    # List for this page's valid data
    page_data = []
    page_na_count = 0  # Track N/A on this page
    
    # Loop through each product
    for product in products:
        # Skip if not a valid product
        if 'data-asin' not in product.attrs or not product.attrs['data-asin'] or product.attrs['data-asin'] == '':
            continue
        
        # Skip sponsored products
        if is_sponsored(product):
            continue
        
        # Product name
        name_elem = product.select_one('h2 span')
        name = name_elem.text.strip() if name_elem else "N/A"
        
        # Extract price
        price = extract_price(product)
        
        # Extract rating
        rating = extract_rating(product)
        
        # Extract ASIN for unique identification
        asin = product.attrs['data-asin']
        
        # Extract image URL
        image_url = extract_image_url(product)
        
        # Check if name or price is N/A
        if name == "N/A" or price == "N/A":
            # Download image to N/A folder if image_url exists
            image_path = download_image(image_url, asin, na_image_folder)
            na_data.append({"Product": name, "Price": price, "Rating": rating, "Image Path": image_path})
            page_na_count += 1
            
            # Print to console for N/A
            print(f"N/A Product: {name}")
            print(f"N/A Price: {price}")
            print(f"Rating: {rating}")
            print(f"N/A Image Path: {image_path}")
            print("-" * 50)
        else:
            # Download image to main folder
            image_path = download_image(image_url, asin, image_folder)
            
            page_data.append({"Product": name, "Price": price, "Rating": rating, "Image Path": image_path})
            
            # Print to console
            print(f"Product: {name}")
            print(f"Price: {price}")
            print(f"Rating: {rating}")
            print(f"Image Path: {image_path}")
            print("-" * 50)
    
    # Append page data to all data
    all_scraped_data.extend(page_data)
    
    # Stop if no valid or N/A products were added on this page
    if not page_data and page_na_count == 0:
        print(f"No more products found on page {page}. Stopping pagination.")
        break
    
    # Delay to avoid rate limiting
    time.sleep(3)
    
    # Increment page
    page += 1

# Close Selenium
driver.quit()

# Sort by price (ascending, N/A prices go to the end)
all_scraped_data.sort(key=lambda x: parse_price(x["Price"]) if parse_price(x["Price"]) is not None else float('inf'))

# Filter by price (if max_price_filter is set)
filtered_data = all_scraped_data
if max_price_filter is not None:
    filtered_data = [item for item in all_scraped_data if parse_price(item["Price"]) is not None and parse_price(item["Price"]) <= max_price_filter]

# Save all data to CSV
if all_scraped_data:
    filename_all = f"amazon_{keyword}_all_pages_data.csv"
    with open(filename_all, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Product", "Price", "Rating", "Image Path"])
        writer.writeheader()
        writer.writerows(all_scraped_data)
    print(f"All data saved to {filename_all}")
    print(f"Total scraped products: {len(all_scraped_data)}")
else:
    print("No data to save.")

# Save filtered data to a separate CSV (if filtering applied)
if filtered_data and max_price_filter is not None:
    filename_filtered = f"amazon_{keyword}_filtered_price_below_{max_price_filter}_data.csv"
    with open(filename_filtered, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Product", "Price", "Rating", "Image Path"])
        writer.writeheader()
        writer.writerows(filtered_data)
    print(f"Filtered data (price <= ${max_price_filter}) saved to {filename_filtered}")
    print(f"Total filtered products: {len(filtered_data)}")

# Save N/A data to CSV
if na_data:
    filename_na = f"amazon_{keyword}_na_products.csv"
    with open(filename_na, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Product", "Price", "Rating", "Image Path"])
        writer.writeheader()
        writer.writerows(na_data)
    print(f"N/A data saved to {filename_na}")
    print(f"There are {len(na_data)} N/A products")
else:
    print("No N/A products to save.")