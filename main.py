import asyncio
import logging
import uuid
from typing import List, Dict, Any
from banwords import is_text_spam
from config import config
from storage import Storage
from models.message import DeliveryStatus
from ai_engine import AIEngine
from master_bot import MasterBot
from settings_manager import SettingsManager
from adapters.vk_adapter import VKAdapter
from adapters.email_adapter import EmailAdapter
from adapters.tg_news_adapter import TGNewsAdapter

from logger_config import init_logging
from bot_handlers import all_handlers

init_logging(log_file="aggregator.log", level="INFO")
logger = logging.getLogger("AggregatorMain")

class MessageAggregatorApp:
    def __init__(self):
        if config.TELEGRAM_PROXY:
            logger.info(f"Using configured TELEGRAM_PROXY: {config.TELEGRAM_PROXY}")

        self.storage = Storage()
        self.settings = SettingsManager(self.storage)
        self.ai_engine = AIEngine(storage=self.storage)
        self.bot = MasterBot(storage=self.storage, simulate_callback=self.process_incoming_message, ai_engine=self.ai_engine)
        if self.bot.dp and all_handlers.router not in self.bot.dp.sub_routers:
            self.bot.dp.include_router(all_handlers.router)
        self.bot.set_flush_raw_queue_callback(self._flush_raw_queue)
        
        self.adapters = [
            VKAdapter(ai_engine=self.ai_engine),
            EmailAdapter(storage=self.storage),
            TGNewsAdapter(storage=self.storage)
        ]

        # Raw message queue for batching requests to AI API (token saving)
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

        # 2. Pre-check system & custom banwords (channel-aware)
        active_bws = await self.storage.get_banwords()
        combined_str = f"{sender} {text}"
        if is_text_spam(combined_str, channel=channel, active_banwords=active_bws):
            logger.warning(f"🚫 [SPAM FILTER] Message from [{channel}] '{sender}' matched banword. Auto-banned.")
            await self.storage.save_message(
                msg_uid=msg_uid,
                channel=channel,
                sender=sender,
                text=text,
                category="spam",
                summary="Отфильтровано по Банворду (Banword)",
                action_required=False,
                is_delivered=DeliveryStatus.FILTERED
            )
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
        """Background worker that flushes raw messages to AI API in 1 batch call."""
        while True:
            ai_batch_interval = await self.settings.get_ai_batch_interval_seconds()
            await asyncio.sleep(ai_batch_interval)
            try:
                await self._flush_raw_queue()
            except Exception as e:
                logger.error(f"Critical error in AI batch worker during flush: {e}", exc_info=True)

    async def _flush_raw_queue(self, force: bool = False):
        async with self._queue_lock:
            if not self.raw_message_queue:
                return
            if not force and self.bot and self.bot.is_night_time():
                logger.info(
                    f"🌙 Night mode active ({self.bot.night_start_hour:02d}:00 - {self.bot.night_end_hour:02d}:00). "
                    f"Holding {len(self.raw_message_queue)} messages in queue to save AI tokens until morning..."
                )
                return
            batch = list(self.raw_message_queue)
            self.raw_message_queue.clear()

        logger.info(f"Processing BATCH of {len(batch)} messages via AI API...")

        try:
            # Fetch custom news topics
            liked_topics = await self.storage.get_news_topics(preference="liked")
            disliked_topics = await self.storage.get_news_topics(preference="disliked")
            
            custom_prompt_suffix = ""
            if liked_topics or disliked_topics:
                custom_prompt_suffix = "Дополнительные инструкции по фильтрации тем от пользователя:\n"
                if liked_topics:
                    liked_list = ", ".join([t["topic"] for t in liked_topics])
                    custom_prompt_suffix += f"- ЖЕЛАТЕЛЬНЫЕ ТЕМЫ (относи к категории interesting): {liked_list}\n"
                if disliked_topics:
                    disliked_list = ", ".join([t["topic"] for t in disliked_topics])
                    custom_prompt_suffix += f"- ЗАПРЕТНЫЕ ТЕМЫ (игнорируй, относи к категории bullshit): {disliked_list}\n"

            # Analyze entire batch in ONE AI API call
            analysis_results = await self.ai_engine.analyze_batch_messages(batch, custom_prompt_suffix)
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
                delivery_status = await self.bot.handle_incoming_analyzed_message(
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
                    is_delivered=delivery_status
                )
        except Exception as e:
            logger.error(f"Error processing message batch: {e}. Re-queueing {len(batch)} messages.", exc_info=True)
            async with self._queue_lock:
                self.raw_message_queue = batch + self.raw_message_queue
            raise e

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
        ai_batch_interval = await self.settings.get_ai_batch_interval_seconds()
        logger.info(f"AI Batching: Processing raw messages every {ai_batch_interval}s")
        
        # Log current DB state
        try:
            bws = await self.storage.get_banwords()
            tg_chans = await self.storage.get_tg_channels()
            topics_liked = await self.storage.get_news_topics(preference="liked")
            topics_disliked = await self.storage.get_news_topics(preference="disliked")
            logger.info(f"Loaded from DB: {len(bws)} banwords, {len(tg_chans)} TG channels, {len(topics_liked)} liked topics, {len(topics_disliked)} disliked topics.")
        except Exception as e:
            logger.warning(f"Failed to load DB stats at startup: {e}")
            
        logger.info("==================================================")

        # Start Bot polling task if enabled
        bot_task = None
        if self.bot.bot and self.bot.dp:
            bot_task = asyncio.create_task(self.bot.start_polling())
        else:
            logger.error("❌ TELEGRAM_BOT_TOKEN не задан в .env! Telegram-бот не запущен.")

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
                # Add 3 second hard timeout to prevent systemd restart hangs
                await asyncio.wait_for(self._flush_raw_queue(force=True), timeout=3.0)
                logger.info("Queue flushed successfully!")
            except asyncio.TimeoutError:
                logger.warning("Queue flush timed out during shutdown! Skipping.")
            except Exception as e:
                logger.error(f"Error flushing queue on shutdown: {e}")

        # 3. Cancel background tasks
        batch_task.cancel()
        if bot_task:
            bot_task.cancel()

        # Close database connection
        await self.storage.close()

        logger.info("AI Message Aggregator stopped cleanly. ✅")

if __name__ == "__main__":
    app = MessageAggregatorApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
