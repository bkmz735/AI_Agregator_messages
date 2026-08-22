import urllib.request
import re

url = "https://t.me/s/rian_ru"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
html = urllib.request.urlopen(req).read().decode("utf-8", errors="ignore")

posts = re.findall(r'data-post="([^"]+)".*?<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
print(f"Found {len(posts)} posts!")
for post_id, text in posts[:3]:
    clean_text = re.sub(r'<[^>]+>', '', text).strip()
    print(f"[{post_id}] {clean_text[:100]}...\n")
