import asyncio
import aiohttp
import re

async def main():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get("https://t.me/s/rian_ru", timeout=10) as resp:
            html = await resp.text()
            posts = re.findall(r'data-post="([^"]+)".*?<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            print(f"Found {len(posts)} posts!")
            for post_id, text in posts[:3]:
                clean_text = re.sub(r'<[^>]+>', '', text).strip()
                print(f"[{post_id}] {clean_text[:100]}...\n")

if __name__ == "__main__":
    asyncio.run(main())
