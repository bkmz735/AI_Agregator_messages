import asyncio
import logging
import sys
import uuid
from typing import List, Dict, Any
from config import config
from storage import Storage
from ai_engine import AIEngine
from master_bot import MasterBot

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
        if config.TELEGRAM_PROXY:
            logger.info(f"Using configured TELEGRAM_PROXY: {config.TELEGRAM_PROXY}")

        self.storage = Storage()
        self.ai_engine = AIEngine()
        self.bot = MasterBot(storage=self.storage, simulate_callback=self.process_incoming_message, ai_engine=self.ai_engine)
        
        self.adapters = [
            VKAdapter(),
            EmailAdapter(),
            TelegramAdapter()
        ]

        # Raw message queue for batching requests to Gemini API (token saving)
        self.raw_message_queue: List[Dict[str, Any]] = []
        self._queue_lock = asyncio.Lock()

    async def process_incoming_message(self, channel: str, sender: str, text: str, msg_uid: str = None):
        """Collects raw incoming messages into batch queue."""
        if not msg_uid:
            msg_uid = f"{channel}_{uuid.uuid4().hex[:8]}"

        # 1. Deduplication check
        if await self.storage.is_duplicate(msg_uid):
            logger.info(f"Duplicate message skipped: {msg_uid}")
            return

        logger.info(f"Queued raw message from [{channel}] {sender} for batch AI processing...")

        async with self._queue_lock:
            self.raw_message_queue.append({
                "msg_uid": msg_uid,
                "channel": channel,
                "sender": sender,
                "text": text
            })

    async def _ai_batch_worker(self):
        """Background worker that flushes raw messages to Gemini API in 1 batch call."""
        while True:
            await asyncio.sleep(config.AI_BATCH_INTERVAL_SECONDS)
            try:
                await self._flush_raw_queue()
            except Exception as e:
                logger.error(f"Critical error in AI batch worker during flush: {e}", exc_info=True)

    async def _flush_raw_queue(self):
        async with self._queue_lock:
            if not self.raw_message_queue:
                return
            batch = list(self.raw_message_queue)
            self.raw_message_queue.clear()

        logger.info(f"Processing BATCH of {len(batch)} messages via Gemini API...")

        # Analyze entire batch in ONE Gemini API call
        analysis_results = await self.ai_engine.analyze_batch_messages(batch)
        results_map = {res.msg_uid: res for res in analysis_results}

        for msg in batch:
            uid = msg["msg_uid"]
            channel = msg["channel"]
            sender = msg["sender"]
            text = msg["text"]

            analysis = results_map.get(uid)
            if not analysis:
                analysis = await self.ai_engine.analyze_message(channel, sender, text, msg_uid=uid)

            # Process via MasterBot
            is_delivered = await self.bot.handle_incoming_analyzed_message(
                channel=channel,
                sender=sender,
                text=text,
                category=analysis.category,
                summary=analysis.summary,
                action_required=analysis.action_required,
                suggested_reply=analysis.suggested_reply
            )

            # Save to SQLite DB
            await self.storage.save_message(
                msg_uid=uid,
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

        # Start AI Batch processing background worker
        batch_task = asyncio.create_task(self._ai_batch_worker())

        logger.info("==================================================")
        logger.info("🚀 AI Message Aggregator & Buffer Service Started!")
        logger.info(f"AI Batching: Processing raw messages every {config.AI_BATCH_INTERVAL_SECONDS}s")
        logger.info("==================================================")

        # Start Bot polling task if enabled
        bot_task = None
        if self.bot.bot and self.bot.dp:
            bot_task = asyncio.create_task(self.bot.start_polling())

        # Handle SIGTERM from systemd gracefully
        import signal
        stop_event = asyncio.Event()

        def _handle_sigterm(*args):
            logger.info("Received SIGTERM from systemd, initiating graceful shutdown...")
            stop_event.set()

        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
        except (NotImplementedError, AttributeError):
            # Windows doesn't support add_signal_handler
            signal.signal(signal.SIGTERM, _handle_sigterm)

        try:
            await stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

        # --- Graceful shutdown ---
        logger.info("Shutting down AI Message Aggregator...")

        # 1. Stop adapters first (no new messages)
        for adapter in self.adapters:
            await adapter.stop()

        # 2. Flush any remaining messages in queue to DB before dying
        queue_size = len(self.raw_message_queue)
        if queue_size > 0:
            logger.info(f"Flushing {queue_size} queued messages before shutdown...")
            try:
                await self._flush_raw_queue()
                logger.info("Queue flushed successfully!")
            except Exception as e:
                logger.error(f"Error flushing queue on shutdown: {e}")

        # 3. Cancel background tasks
        batch_task.cancel()
        if bot_task:
            bot_task.cancel()

        logger.info("AI Message Aggregator stopped cleanly. ✅")

if __name__ == "__main__":
    app = MessageAggregatorApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
