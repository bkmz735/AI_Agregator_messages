import asyncio
import logging
import html
from typing import Optional, Callable, Awaitable
from config import config
from storage import Storage

logger = logging.getLogger(__name__)

# Category Emojis
CATEGORY_EMOJIS = {
    "urgent": "🚨 **СРОЧНО**",
    "important": "⭐ **ВАЖНОЕ**",
    "general": "💬 **ОБЫЧНОЕ**",
    "spam": "🚫 **СПАМ**"
}

class MasterBot:
    def __init__(self, storage: Storage, simulate_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.master_chat_id = config.MASTER_CHAT_ID
        self.storage = storage
        self.simulate_callback = simulate_callback
        self.delivery_mode = config.DELIVERY_MODE  # "instant" or "digest"
        self.digest_interval = config.DIGEST_INTERVAL_MINUTES
        self.dp = None
        self.bot = None

        if self.bot_token:
            try:
                from aiogram import Bot, Dispatcher
                from aiogram.client.session.aiohttp import AiohttpSession
                
                session = AiohttpSession(proxy=config.TELEGRAM_PROXY) if config.TELEGRAM_PROXY else None
                self.bot = Bot(token=self.bot_token, session=session)
                self.dp = Dispatcher()
                self._setup_handlers()
                logger.info(f"Telegram MasterBot initialized (Proxy: {config.TELEGRAM_PROXY or 'Direct'}).")
            except Exception as e:
                logger.warning(f"Could not initialize aiogram Bot: {e}")

    def _get_menu_keyboard(self, buffer_count: int = 0):
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        kb = [
            [KeyboardButton(text=f"📥 Буфер ({buffer_count})"), KeyboardButton(text="🚀 Отправить сводку")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text=f"⚙️ Режим: {self.delivery_mode.upper()}")]
        ]
        return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    def _setup_handlers(self):
        from aiogram.filters import Command
        from aiogram import types, F

        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            buf_count = await self.storage.get_buffer_count()
            await message.answer(
                "🤖 **AI Message Aggregator & Buffer Bot**\n\n"
                "Я собираю сообщения из VK, Авито, TG и Mail.ru, отсеиваю спам через ИИ "
                "и присылаю важные выжимки по вашему графику.\n\n"
                "🚨 **Срочные сообщения** приходят мгновенно!\n"
                "📥 **Обычные и важные** копятся в буфере и отправляются сводкой.",
                reply_markup=self._get_menu_keyboard(buf_count),
                parse_mode="Markdown"
            )

        @self.dp.message(F.text.startswith("📥 Буфер"))
        async def cmd_buffer(message: types.Message):
            buf_count = await self.storage.get_buffer_count()
            await message.answer(
                f"📥 **В буфере ожидают отправки:** {buf_count} сообщ.\n\n"
                "Нажмите «🚀 Отправить сводку», чтобы получить их прямо сейчас, или дождитесь отправки по расписанию.",
                reply_markup=self._get_menu_keyboard(buf_count),
                parse_mode="Markdown"
            )

        @self.dp.message(F.text == "🚀 Отправить сводку")
        async def cmd_send_digest(message: types.Message):
            sent_count = await self.flush_buffer_now()
            buf_count = await self.storage.get_buffer_count()
            if sent_count == 0:
                await message.answer("📥 Буфер пуст! Новых сообщений нет.", reply_markup=self._get_menu_keyboard(0))
            else:
                await message.answer(f"✅ Сводка отправлена ({sent_count} сообщ.)", reply_markup=self._get_menu_keyboard(buf_count))

        @self.dp.message(F.text == "📊 Статистика")
        async def cmd_stats(message: types.Message):
            stats = await self.storage.get_stats()
            buf_count = await self.storage.get_buffer_count()
            stats_msg = (
                "📊 **Статистика агрегатора:**\n\n"
                f"🚨 Срочные: {stats.get('urgent', 0)}\n"
                f"⭐ Важные: {stats.get('important', 0)}\n"
                f"💬 Обычные: {stats.get('general', 0)}\n"
                f"🚫 Отфильтровано спама: {stats.get('spam', 0)}\n\n"
                f"📥 Не доставлено в буфере: {buf_count}"
            )
            await message.answer(stats_msg, reply_markup=self._get_menu_keyboard(buf_count), parse_mode="Markdown")

        @self.dp.message(F.text.startswith("⚙️ Режим"))
        async def cmd_toggle_mode(message: types.Message):
            # Toggle mode between digest and instant
            self.delivery_mode = "instant" if self.delivery_mode == "digest" else "digest"
            buf_count = await self.storage.get_buffer_count()
            msg = f"⚙️ Режим отправки изменен на: **{self.delivery_mode.upper()}**\n\n"
            if self.delivery_mode == "digest":
                msg += "🚨 Срочные — мгновенно.\n📥 Важные/Обычные — по расписанию."
            else:
                msg += "⚡ Все не-спам сообщения приходят мгновенно."
            await message.answer(msg, reply_markup=self._get_menu_keyboard(buf_count), parse_mode="Markdown")

    async def handle_incoming_analyzed_message(
        self, channel: str, sender: str, text: str, category: str, summary: str, action_required: bool, suggested_reply: Optional[str] = None
    ) -> bool:
        """
        Decides whether to send immediately or store in buffer based on category and delivery mode.
        Returns True if delivered immediately, False if buffered.
        """
        if category == "spam":
            logger.info(f"Muting spam message from [{channel}] {sender}.")
            return False

        # Urgent messages ALWAYS bypass buffer and notify immediately!
        if category == "urgent" or self.delivery_mode == "instant":
            await self.send_instant_notification(channel, sender, text, category, summary, action_required, suggested_reply)
            return True
        else:
            logger.info(f"Message from [{channel}] {sender} buffered for next scheduled digest.")
            return False

    async def send_instant_notification(
        self, channel: str, sender: str, text: str, category: str, summary: str, action_required: bool, suggested_reply: Optional[str] = None
    ):
        header = CATEGORY_EMOJIS.get(category, "📩 **СООБЩЕНИЕ**")
        reply_part = f"\n\n💡 **Черновик ответа:**\n`{html.escape(suggested_reply)}`" if suggested_reply else ""
        action_part = "\n⚡ **Требуется ответ!**" if action_required else ""

        message_text = (
            f"{header}\n"
            f"📍 **Канал:** {html.escape(channel)}\n"
            f"👤 **От:** {html.escape(sender)}\n\n"
            f"📝 **Выжимка AI:**\n{html.escape(summary)}{action_part}{reply_part}\n\n"
            f"--- Текст ---\n"
            f"_{html.escape(text[:250])}{'...' if len(text) > 250 else ''}_"
        )

        logger.info(f"Sending Instant Notification [{category}] from {sender}")

        if self.bot and self.master_chat_id:
            try:
                buf_count = await self.storage.get_buffer_count()
                await self.bot.send_message(
                    chat_id=self.master_chat_id,
                    text=message_text,
                    parse_mode="Markdown",
                    reply_markup=self._get_menu_keyboard(buf_count)
                )
            except Exception as e:
                logger.error(f"Error sending Telegram notification: {e}")

    async def flush_buffer_now(self) -> int:
        """Sends all buffered messages as a formatted digest."""
        messages = await self.storage.get_buffered_messages(mark_as_delivered=True)
        if not messages:
            return 0

        digest_parts = [f"📬 **СВОДКА СООБЩЕНИЙ ({len(messages)})**\n"]
        for idx, m in enumerate(messages, 1):
            emoji = CATEGORY_EMOJIS.get(m['category'], "💬")
            digest_parts.append(
                f"**{idx}. [{m['channel']}]** {m['sender']} ({emoji})\n"
                f"📝 {m['summary']}\n"
                f"_{m['text'][:150]}...\n"
            )

        full_digest = "\n---\n".join(digest_parts)

        if self.bot and self.master_chat_id:
            try:
                # Split long messages if needed
                if len(full_digest) > 4000:
                    for chunk in [full_digest[i:i+4000] for i in range(0, len(full_digest), 4000)]:
                        await self.bot.send_message(chat_id=self.master_chat_id, text=chunk, parse_mode="Markdown")
                else:
                    await self.bot.send_message(
                        chat_id=self.master_chat_id,
                        text=full_digest,
                        parse_mode="Markdown",
                        reply_markup=self._get_menu_keyboard(0)
                    )
            except Exception as e:
                logger.error(f"Error sending digest: {e}")

        return len(messages)

    async def start_digest_scheduler(self):
        """Background task for sending scheduled digests."""
        logger.info(f"Digest scheduler running (interval: {self.digest_interval} min)...")
        while True:
            await asyncio.sleep(self.digest_interval * 60)
            if self.delivery_mode == "digest":
                logger.info("Executing scheduled buffer digest flush...")
                await self.flush_buffer_now()

    async def start_polling(self):
        if self.bot and self.dp:
            logger.info("Starting Telegram Bot Polling loop...")
            asyncio.create_task(self.start_digest_scheduler())
            await self.dp.start_polling(self.bot)
