import asyncio
import logging
from adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)

class TelegramAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(name="Telegram")

    async def start(self):
        logger.info("TelegramAdapter active (ready to receive webhook/bot messages).")

    async def stop(self):
        pass
