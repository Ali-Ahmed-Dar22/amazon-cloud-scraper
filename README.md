#  Amazon E-Commerce Cloud Scraper

A robust, 24/7 automated web scraper built with Python, specifically designed to bypass advanced anti-bot mechanisms and monitor Amazon product prices in real-time. This project is optimized for headless deployment on Linux cloud servers (e.g., Oracle Cloud Ubuntu VMs).

##  Features

- **Advanced Bot-Bypass Engine:** Utilizes `undetected-chromedriver` and headless Chrome to bypass Amazon's strict scraping detection.
- **24/7 Cloud Ready:** Completely headless architecture optimized for low-resource Linux VMs without graphical interfaces.
- **Discord Webhook Integration:** Instantly pushes price drops and newly discovered items to a Discord channel using a background queuing thread.
- **Dynamic Price Extraction:** Accurately extracts both "Current Price" and "Previous Price" to calculate true discounts.
- **Atomic File Saving:** Employs temporary file buffers when writing to CSV to prevent data corruption in the event of server reboots or crashes.
- **Asynchronous Execution:** Discord notifications run on a separate daemon thread to ensure the main scraping loop never stalls.

##  Tech Stack

- **Language:** Python 3.10+
- **Browser Automation:** Selenium WebDriver, `undetected-chromedriver`
- **Parsing:** BeautifulSoup4
- **Network/API:** Requests
- **Deployment OS:** Ubuntu Linux / Oracle Cloud

##  Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/amazon-cloud-scraper.git
   cd amazon-cloud-scraper
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Google Chrome (Linux):**
   *(Required if running headless on a VM)*
   ```bash
   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
   sudo apt install ./google-chrome-stable_current_amd64.deb
   ```

##  Usage

Configure your target keywords and Discord webhook in `Final_testing_cloud.py`:

```python
keywords = ["Laptops", "Speakers", "Monitors"] 
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your-webhook-url"
BETWEEN_RUNS_SLEEP = 180 # Seconds to wait between cycles
```

**Run the scraper locally or on your server:**
```bash
python Final_testing_cloud.py
```

*For persistent 24/7 deployment, we recommend running the script inside a `tmux` session.*

##  Output
The script automatically categorizes items and saves data as `.csv` files locally while pushing live updates to Discord.

##  Legal & Ethical Disclaimer
This project is for educational purposes only. Automated data extraction from websites may violate their Terms of Service. Please respect `robots.txt` and do not overload servers.
