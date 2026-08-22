import asyncio
import logging
import re
import html
from typing import Optional, Any, Set
import aiohttp
from adapters.base_adapter import BaseAdapter
from config import config

logger = logging.getLogger(__name__)

class TGNewsAdapter(BaseAdapter):
    def __init__(self, storage: Optional[Any] = None):
        super().__init__(name="Telegram News")
        self.storage = storage
        self._running = False
        self._task = None
        self._seen_uids: Set[str] = set()

    async def start(self):
        self._running = True
        logger.info("Starting Telegram News adapter polling service...")
        self._task = asyncio.create_task(self._poll_channels())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _poll_channels(self):
        """Periodically polls public Telegram channels configured in SQLite DB."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }

        proxy = config.TELEGRAM_PROXY if config.TELEGRAM_PROXY else None

        while self._running:
            try:
                channels = []
                if self.storage:
                    db_chans = await self.storage.get_tg_channels()
                    channels = [c["username"] for c in db_chans]
                
                if not channels and config.TG_NEWS_CHANNELS:
                    channels = [c.strip().lstrip("@") for c in config.TG_NEWS_CHANNELS.split(",") if c.strip()]

                if channels:
                    async with aiohttp.ClientSession(headers=headers) as session:
                        for channel in channels:
                            if not self._running:
                                break
                            try:
                                url = f"https://t.me/s/{channel}"
                                async with session.get(url, proxy=proxy, timeout=15) as resp:
                                    if resp.status == 200:
                                        html_content = await resp.text()
                                        await self._parse_channel_html(channel, html_content)
                                    else:
                                        logger.warning(f"Telegram News: HTTP {resp.status} for channel @{channel}")
                            except Exception as ce:
                                logger.warning(f"Telegram News: Error fetching channel @{channel}: {ce}")
                            
                            await asyncio.sleep(2)  # Polite gap between channel requests

                await asyncio.sleep(config.TG_NEWS_POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in TGNewsAdapter poll loop: {e}")
                await asyncio.sleep(30)

    async def _parse_channel_html(self, channel: str, html_content: str):
        """Extracts posts from Telegram public web preview HTML."""
        posts = re.findall(
            r'data-post="([^"]+)".*?<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            html_content,
            re.DOTALL
        )

        # Ограничиваем до 5 последних (самых свежих) новостей за один цикл проверки,
        # чтобы не заваливать нейросеть десятками старых постов при первом запуске
        posts = posts[-5:]

        for post_path, text_raw in posts:
            msg_uid = f"tg_news_{post_path.replace('/', '_')}"
            
            if msg_uid in self._seen_uids:
                continue

            if self.storage and await self.storage.is_duplicate(msg_uid):
                self._seen_uids.add(msg_uid)
                continue

            text_clean = re.sub(r'<br\s*/?>', '\n', text_raw)
            text_clean = re.sub(r'<[^>]+>', '', text_clean)
            text_clean = html.unescape(text_clean).strip()

            if not text_clean or len(text_clean) < 15:
                self._seen_uids.add(msg_uid)
                continue

            channel_override = f"Telegram (@{channel})"
            sender = f"Канал @{channel}"
            
            logger.info(f"Emitting news post from @{channel} (UID: {msg_uid}): {text_clean[:60]}...")
            await self.emit_message(
                sender=sender,
                text=text_clean,
                msg_uid=msg_uid,
                channel_override=channel_override
            )
            self._seen_uids.add(msg_uid)
