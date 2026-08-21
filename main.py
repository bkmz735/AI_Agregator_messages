import asyncio
import logging
import sys
import uuid
from config import config
from storage import Storage
from ai_engine import AIEngine
from master_bot import MasterBot
from xray_tunnel import XrayTunnelManager

from adapters.vk_adapter import VKAdapter
from adapters.email_adapter import EmailAdapter
from adapters.tg_adapter import TelegramAdapter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("AggregatorMain")

class MessageAggregatorApp:
    def __init__(self):
        self.xray_tunnel = None
        
        # Start embedded Xray VLESS Tunnel if VLESS_LINK is configured
        if config.VLESS_LINK:
            logger.info("Initializing dedicated Xray VLESS tunnel for Telegram...")
            self.xray_tunnel = XrayTunnelManager(vless_url=config.VLESS_LINK)
            proxy_url = self.xray_tunnel.start()
            if proxy_url:
                config.TELEGRAM_PROXY = proxy_url
                logger.info(f"Telegram Bot routed through internal VLESS Proxy: {proxy_url}")

        self.storage = Storage()
        self.ai_engine = AIEngine()
        self.bot = MasterBot(storage=self.storage, simulate_callback=self.process_incoming_message)
        
        self.adapters = [
            VKAdapter(),
            EmailAdapter(),
            TelegramAdapter()
        ]

    async def process_incoming_message(self, channel: str, sender: str, text: str, msg_uid: str = None):
        """Pipeline for processing incoming messages from any adapter."""
        if not msg_uid:
            msg_uid = f"{channel}_{uuid.uuid4().hex[:8]}"

        # 1. Deduplication check
        if await self.storage.is_duplicate(msg_uid):
            logger.info(f"Duplicate message skipped: {msg_uid}")
            return

        logger.info(f"Processing new message from [{channel}] {sender}...")

        # 2. AI Analysis via Gemini API
        analysis = await self.ai_engine.analyze_message(channel=channel, sender=sender, text=text)

        # 3. Process via MasterBot (determines if sent immediately or buffered)
        is_delivered = await self.bot.handle_incoming_analyzed_message(
            channel=channel,
            sender=sender,
            text=text,
            category=analysis.category,
            summary=analysis.summary,
            action_required=analysis.action_required,
            suggested_reply=analysis.suggested_reply
        )

        # 4. Save to SQLite DB with delivered status
        await self.storage.save_message(
            msg_uid=msg_uid,
            channel=channel,
            sender=sender,
            text=text,
            category=analysis.category,
            summary=analysis.summary,
            action_required=analysis.action_required,
            suggested_reply=analysis.suggested_reply,
            is_delivered=is_delivered
        )

    async def run(self):
        # Initialize Database
        await self.storage.init_db()

        # Wire up adapter callbacks
        for adapter in self.adapters:
            adapter.set_callback(self.process_incoming_message)
            await adapter.start()

        logger.info("==================================================")
        logger.info("🚀 AI Message Aggregator & Buffer Service Started!")
        logger.info("==================================================")

        # Start Bot polling task if enabled
        bot_task = None
        if self.bot.bot and self.bot.dp:
            bot_task = asyncio.create_task(self.bot.start_polling())

        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Shutting down AI Message Aggregator...")
            for adapter in self.adapters:
                await adapter.stop()
            if self.xray_tunnel:
                self.xray_tunnel.stop()
            if bot_task:
                bot_task.cancel()

if __name__ == "__main__":
    app = MessageAggregatorApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
