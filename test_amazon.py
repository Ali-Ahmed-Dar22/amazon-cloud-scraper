import requests
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7"
}
r = requests.get("https://www.amazon.nl/s?k=T-shirt", headers=headers)
with open("amazon_test.html", "w", encoding="utf-8") as f:
    f.write(r.text)
print("Saved to amazon_test.html", len(r.text))
