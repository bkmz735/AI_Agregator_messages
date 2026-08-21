import asyncio
import logging
import html
import io
from typing import Optional, Callable, Awaitable, Any
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
    def __init__(self, storage: Storage, simulate_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None, ai_engine: Optional[Any] = None):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.master_chat_id = config.MASTER_CHAT_ID
        self.storage = storage
        self.ai_engine = ai_engine
        self.simulate_callback = simulate_callback
        self.delivery_mode = config.DELIVERY_MODE  # "instant" or "digest"
        self.digest_interval = config.DIGEST_INTERVAL_MINUTES
        self.dp = None
        self.bot = None

        if self.bot_token:
            self._init_bot_instance(use_proxy=True if config.TELEGRAM_PROXY else False)

    def set_ai_engine(self, ai_engine):
        self.ai_engine = ai_engine

    def _init_bot_instance(self, use_proxy: bool = True):
        from aiogram import Bot, Dispatcher
        from aiogram.client.session.aiohttp import AiohttpSession
        
        session = None
        proxy_url = config.TELEGRAM_PROXY if use_proxy else None
        
        if proxy_url:
            try:
                session = AiohttpSession(proxy=proxy_url)
                logger.info(f"Telegram Bot AiohttpSession initialized with proxy: {proxy_url}")
            except Exception as pe:
                logger.warning(f"Proxy setup warning ({proxy_url}): {pe}. Using direct connection.")
                session = None
        
        self.bot = Bot(token=self.bot_token, session=session)
        self.dp = Dispatcher()
        self._setup_handlers()
        logger.info(f"Telegram MasterBot initialized (Proxy: {proxy_url if session else 'Direct'}).")

    def _get_menu_keyboard(self, buffer_count: int = 0):
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        mode_label = "⚡ СРАЗУ" if self.delivery_mode == "instant" else "📥 СВОДКА"
        kb = [
            [KeyboardButton(text=f"📥 Буфер ({buffer_count})"), KeyboardButton(text="🚀 Отправить сводку")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text=f"⚙️ Режим: {mode_label}"), KeyboardButton(text="🧹 Очистить чат")]
        ]
        return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)

    async def _register_bot_commands(self):
        """Registers blue '/' commands menu in Telegram app UI."""
        from aiogram.types import BotCommand
        commands = [
            BotCommand(command="start", description="Главное меню и статус"),
            BotCommand(command="help", description="Справка по командам и работе бота"),
            BotCommand(command="flush", description="Выгрузить накопившийся буфер прямо сейчас"),
            BotCommand(command="stats", description="Посмотреть статистику сообщений"),
            BotCommand(command="mode", description="Переключить режим (Сразу / Сводка)"),
            BotCommand(command="clear", description="Очистить последние сообщения чата")
        ]
        try:
            await self.bot.set_my_commands(commands)
            logger.info("Registered Telegram Bot slash commands menu.")
        except Exception as e:
            logger.warning(f"Could not set bot commands: {e}")

    def _setup_handlers(self):
        from aiogram.filters import Command
        from aiogram import types, F

        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            buf_count = await self.storage.get_buffer_count()
            await message.answer(
                "🤖 **AI Message Aggregator & Buffer Bot**\n\n"
                "Я собираю сообщения из VK, Авито, TG и Mail.ru, отсеиваю спам через ИИ "
                "и присылаю важные выжимки по вашему графику.\n\n"
                "🎙️ **Отправьте мне голосовое сообщение** — я мгновенно переведу его в текст и подготовлю выжимку!\n\n"
                "🚨 **Срочные сообщения** приходят мгновенно!\n"
                "📥 **Обычные и важные** копятся в буфере и отправляются сводкой.\n\n"
                "Используйте кнопку `/help` для справки по командам.",
                reply_markup=self._get_menu_keyboard(buf_count),
                parse_mode="Markdown"
            )

        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            buf_count = await self.storage.get_buffer_count()
            help_text = (
                "📖 **Справка по командам бота:**\n\n"
                "🔹 `/start` — Показать главное меню\n"
                "🔹 `/help` — Эта справка\n"
                "🔹 `/flush` (или 🚀 Отправить сводку) — Прислать выжимку из буфера прямо сейчас\n"
                "🔹 `/stats` (или 📊 Статистика) — Посмотреть статистику сообщений\n"
                "🔹 `/mode` (или ⚙️ Режим) — Переключить режим (Сразу / Сводка)\n\n"
                "🎙️ **Расшифровка голосовых:** перешлите или отправьте голосуху, и ИИ переведет её в текст!\n\n"
                "💡 **Как работает агрегатор:**\n"
                "• Спам отсеивается ИИ и не беспокоит вас.\n"
                "• Запросы клиентов обработаются пакетно раз в 60с для экономии токенов.\n"
                "• При превышении лимита (429 Rate Limit) бот автоматически сделает паузу без потери сообщений!"
            )
            await message.answer(help_text, reply_markup=self._get_menu_keyboard(buf_count), parse_mode="Markdown")

        @self.dp.message(F.voice | F.audio)
        async def handle_voice_message(message: types.Message):
            """Transcribes voice or audio messages via Gemini Multimodal API."""
            status_msg = await message.answer("🎙️ *Расшифровываю голосовое сообщение через Gemini AI...*", parse_mode="Markdown")
            try:
                voice_or_audio = message.voice or message.audio
                file_info = await self.bot.get_file(voice_or_audio.file_id)
                audio_stream = io.BytesIO()
                await self.bot.download_file(file_info.file_path, destination=audio_stream)
                audio_bytes = audio_stream.getvalue()
                
                mime_type = getattr(voice_or_audio, 'mime_type', 'audio/ogg') or 'audio/ogg'
                sender_name = message.from_user.full_name or message.from_user.username or "Пользователь"

                if self.ai_engine:
                    res = await self.ai_engine.transcribe_and_analyze_audio(audio_bytes, mime_type=mime_type)
                else:
                    from ai_engine import AudioAnalysisResult
                    res = AudioAnalysisResult(
                        transcription="[Расшифровка недоступна]",
                        category="important",
                        summary="Голосовое сообщение",
                        action_required=True,
                        suggested_reply="Спасибо за сообщение!"
                    )

                text_response = (
                    f"🎙️ **РАСШИФРОВКА ГОЛОСОВОГО**\n\n"
                    f"🗣️ **Текст записи:**\n_{html.escape(res.transcription)}_\n\n"
                    f"📝 **Выжимка ИИ:**\n{html.escape(res.summary)}"
                )

                await status_msg.edit_text(text_response, parse_mode="Markdown")

                # Also queue it in DB
                await self.storage.save_message(
                    msg_uid=f"tg_voice_{message.message_id}",
                    channel="Telegram Voice",
                    sender=sender_name,
                    text=f"[Voice] {res.transcription}",
                    category=res.category,
                    summary=res.summary,
                    action_required=res.action_required,
                    suggested_reply=res.suggested_reply,
                    is_delivered=True
                )
            except Exception as e:
                logger.error(f"Error processing voice message: {e}")
                await status_msg.edit_text(f"❌ Ошибка расшифровки голосового: {e}")

        @self.dp.message(F.text.startswith("📥 Буфер"))
        async def cmd_buffer(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            buf_count = await self.storage.get_buffer_count()
            await message.answer(
                f"📥 **В буфере ожидают отправки:** {buf_count} сообщ.\n\n"
                "Нажмите «🚀 Отправить сводку», чтобы получить их прямо сейчас, или дождитесь отправки по расписанию.",
                reply_markup=self._get_menu_keyboard(buf_count),
                parse_mode="Markdown"
            )

        @self.dp.message(F.text == "🚀 Отправить сводку")
        @self.dp.message(Command("flush"))
        async def cmd_send_digest(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            sent_count = await self.flush_buffer_now()
            buf_count = await self.storage.get_buffer_count()
            if sent_count == 0:
                await message.answer("📥 Буфер пуст! Новых сообщений нет.", reply_markup=self._get_menu_keyboard(0))
            else:
                await message.answer(f"✅ Сводка отправлена ({sent_count} сообщ.)", reply_markup=self._get_menu_keyboard(buf_count))

        @self.dp.message(F.text == "📊 Статистика")
        @self.dp.message(Command("stats"))
        async def cmd_stats(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
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
        @self.dp.message(Command("mode"))
        async def cmd_toggle_mode(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            # Toggle mode between digest and instant
            self.delivery_mode = "instant" if self.delivery_mode == "digest" else "digest"
            buf_count = await self.storage.get_buffer_count()
            mode_label = "⚡ СРАЗУ" if self.delivery_mode == "instant" else "📥 СВОДКА"
            
            msg = f"⚙️ Режим отправки изменен на: **{mode_label}**\n\n"
            if self.delivery_mode == "digest":
                msg += "📥 **СВОДКА (Буферизация):**\n"
                msg += "Все обычные и важные сообщения копятcя в буфере и приходят раз в час в виде одного удобного отчета.\n"
                msg += "*(Срочные сообщения всё равно придут мгновенно)*"
            else:
                msg += "⚡ **СРАЗУ (Мгновенно):**\n"
                msg += "Все новые входящие сообщения будут моментально присылаться в Телеграм по одному, без накопления."
            
            await message.answer(msg, reply_markup=self._get_menu_keyboard(buf_count), parse_mode="Markdown")

        @self.dp.message(Command("clear"))
        @self.dp.message(F.text == "🧹 Очистить чат")
        async def cmd_clear_chat(message: types.Message):
            current_id = message.message_id
            
            # loop backward to delete last 100 messages silently
            for msg_id in range(current_id, current_id - 100, -1):
                try:
                    await self.bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                except Exception:
                    pass

        # Handle inline "Read/Delete" button click
        @self.dp.callback_query(F.data == "delete_msg")
        async def process_delete_msg(callback_query: types.CallbackQuery):
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            await callback_query.answer()

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
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🗑️ Прочитано", callback_data="delete_msg")]
                ])
                sent_msg = await self.bot.send_message(
                    chat_id=self.master_chat_id,
                    text=message_text,
                    parse_mode="Markdown",
                    reply_markup=inline_kb
                )
                # Register for auto-deletion if config value is greater than 0
                if config.AUTO_DELETE_DELAY_HOURS > 0:
                    delay = config.AUTO_DELETE_DELAY_HOURS * 3600
                    await self.storage.save_sent_notification(
                        chat_id=self.master_chat_id,
                        message_id=sent_msg.message_id,
                        delay_seconds=delay
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
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🗑️ Прочитано", callback_data="delete_msg")]
                ])
                # Split long messages if needed
                if len(full_digest) > 4000:
                    for chunk in [full_digest[i:i+4000] for i in range(0, len(full_digest), 4000)]:
                        sent_msg = await self.bot.send_message(
                            chat_id=self.master_chat_id, 
                            text=chunk, 
                            parse_mode="Markdown",
                            reply_markup=inline_kb
                        )
                        if config.AUTO_DELETE_DELAY_HOURS > 0:
                            delay = config.AUTO_DELETE_DELAY_HOURS * 3600
                            await self.storage.save_sent_notification(
                                chat_id=self.master_chat_id,
                                message_id=sent_msg.message_id,
                                delay_seconds=delay
                            )
                else:
                    sent_msg = await self.bot.send_message(
                        chat_id=self.master_chat_id,
                        text=full_digest,
                        parse_mode="Markdown",
                        reply_markup=inline_kb
                    )
                    if config.AUTO_DELETE_DELAY_HOURS > 0:
                        delay = config.AUTO_DELETE_DELAY_HOURS * 3600
                        await self.storage.save_sent_notification(
                            chat_id=self.master_chat_id,
                            message_id=sent_msg.message_id,
                            delay_seconds=delay
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
                try:
                    await self.flush_buffer_now()
                except Exception as e:
                    logger.error(f"Critical error in digest scheduler: {e}", exc_info=True)

    async def start_cleanup_scheduler(self):
        """Background task that periodically deletes expired notifications from Telegram."""
        logger.info(f"Cleanup scheduler running (auto-delete delay: {config.AUTO_DELETE_DELAY_HOURS}h)...")
        while True:
            await asyncio.sleep(60)  # Check every minute
            try:
                expired = await self.storage.get_expired_notifications()
                for item in expired:
                    try:
                        await self.bot.delete_message(chat_id=item['chat_id'], message_id=item['message_id'])
                        logger.info(f"Auto-deleted expired message {item['message_id']} in chat {item['chat_id']}.")
                    except Exception as de:
                        logger.debug(f"Failed to auto-delete message {item['message_id']} in chat {item['chat_id']}: {de}")
                    # Always delete from DB so we don't retry endlessly
                    await self.storage.delete_sent_notification(item['id'])
            except Exception as e:
                logger.error(f"Error in cleanup scheduler: {e}")

    async def start_polling(self):
        if self.bot and self.dp:
            logger.info("Starting Telegram Bot Polling loop...")
            await self._register_bot_commands()
            asyncio.create_task(self.start_digest_scheduler())
            asyncio.create_task(self.start_cleanup_scheduler())
            
            use_proxy_mode = True if config.TELEGRAM_PROXY else False
            while True:
                try:
                    await self.bot.delete_webhook(drop_pending_updates=True)
                    await self.dp.start_polling(self.bot, drop_pending_updates=True)
                except Exception as e:
                    logger.warning(f"Telegram polling error: {e}")
                    # If proxy connection failed (ClientOSError), auto fallback to Direct connection
                    if use_proxy_mode:
                        logger.warning("Proxy connection failed. Auto-switching to DIRECT connection for Telegram Bot...")
                        use_proxy_mode = False
                        self._init_bot_instance(use_proxy=False)
                        await self._register_bot_commands()
                    await asyncio.sleep(3)
