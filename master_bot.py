import asyncio
import logging
import html
import io
from typing import Optional, Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from config import config
from storage import Storage

logger = logging.getLogger(__name__)

# Category Emojis
CATEGORY_EMOJIS = {
    "urgent": "🚨 <b>СРОЧНО</b>",
    "important": "⭐ <b>ВАЖНОЕ</b>",
    "general": "💬 <b>ОБЫЧНОЕ</b>",
    "spam": "🚫 <b>СПАМ</b>"
}

class AccessControlMiddleware(BaseMiddleware):
    def __init__(self, master_chat_id: int):
        self.master_chat_id = master_chat_id
        super().__init__()

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]], event: TelegramObject, data: dict) -> Any:
        from aiogram.types import Message, CallbackQuery
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None

        if user_id and user_id != self.master_chat_id:
            logger.warning(f"Blocking unauthorized Telegram interaction from user_id: {user_id}")
            return None  # Ignore event completely
            
        return await handler(event, data)

class MasterBot:
    def __init__(self, storage: Storage, simulate_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None, ai_engine: Optional[Any] = None):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.master_chat_id = config.MASTER_CHAT_ID
        self.storage = storage
        self.ai_engine = ai_engine
        self.simulate_callback = simulate_callback
        self.on_flush_raw_queue: Optional[Callable[[], Awaitable[None]]] = None
        self.delivery_mode = config.DELIVERY_MODE  # "instant" or "digest"
        self.digest_interval = config.DIGEST_INTERVAL_MINUTES
        self.auto_delete_delay_hours = config.AUTO_DELETE_DELAY_HOURS
        self.night_mode_enabled = config.NIGHT_MODE_ENABLED
        self.night_start_hour = config.NIGHT_START_HOUR
        self.night_end_hour = config.NIGHT_END_HOUR
        self._last_buffer_status_msg_id = None
        self._last_settings_msg_id = None
        self._last_stats_msg_id = None
        self._last_clear_prompt_msg_id = None
        self.dp = None
        self.bot = None

        if self.bot_token:
            self._init_bot_instance(use_proxy=True if config.TELEGRAM_PROXY else False)

    def set_ai_engine(self, ai_engine):
        self.ai_engine = ai_engine

    def set_flush_raw_queue_callback(self, callback: Callable[[], Awaitable[None]]):
        self.on_flush_raw_queue = callback

    def is_night_time(self) -> bool:
        """Returns True if Night Mode is enabled and current time falls in quiet hours."""
        if not self.night_mode_enabled:
            return False
        from datetime import datetime
        now_hour = datetime.now().hour
        if self.night_start_hour > self.night_end_hour:
            return now_hour >= self.night_start_hour or now_hour < self.night_end_hour
        else:
            return self.night_start_hour <= now_hour < self.night_end_hour

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
        
        # Register security middleware to restrict access to master user only
        if self.master_chat_id:
            self.dp.message.outer_middleware(AccessControlMiddleware(self.master_chat_id))
            self.dp.callback_query.outer_middleware(AccessControlMiddleware(self.master_chat_id))
            
        self._setup_handlers()
        logger.info(f"Telegram MasterBot initialized (Proxy: {proxy_url if session else 'Direct'}).")

    def _get_menu_keyboard(self, buffer_count: int = 0):
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        if buffer_count > 0:
            kb = [
                [KeyboardButton(text=f"📥 Буфер ({buffer_count})"), KeyboardButton(text="🚀 Отправить сводку")],
                [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🧹 Очистить чат")]
            ]
        else:
            kb = [
                [KeyboardButton(text="📥 Буфер")],
                [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🧹 Очистить чат")]
            ]
        return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)

    async def _register_bot_commands(self):
        """Registers blue '/' commands menu in Telegram app UI."""
        from aiogram.types import BotCommand
        commands = [
            BotCommand(command="start", description="Главное меню и статус"),
            BotCommand(command="help", description="Справка по командам и работе бота"),
            BotCommand(command="settings", description="Настройки (интервал сводки, режим, автоудаление)"),
            BotCommand(command="flush", description="Выгрузить накопившийся буфер прямо сейчас"),
            BotCommand(command="stats", description="Посмотреть статистику сообщений"),
            BotCommand(command="block", description="Добавить слово в Чёрный список спама"),
            BotCommand(command="unblock", description="Удалить слово из Чёрного списка спама"),
            BotCommand(command="blacklist", description="Посмотреть весь Чёрный список спама"),
            BotCommand(command="clear", description="Очистить последние сообщения чата")
        ]
        try:
            await self.bot.set_my_commands(commands)
            logger.info("Registered Telegram Bot slash commands menu.")
        except Exception as e:
            logger.warning(f"Could not set bot commands: {e}")

    async def _get_settings_text_and_keyboard(self):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        mode_label = "⚡ СРАЗУ (Мгновенно)" if self.delivery_mode == "instant" else "📥 СВОДКА (Раз в час)"
        autodelete_label = f"{self.auto_delete_delay_hours} ч" if self.auto_delete_delay_hours > 0 else "Выключено ❌"
        night_label = f"🟢 Включен ({self.night_start_hour:02d}:00 - {self.night_end_hour:02d}:00)" if self.night_mode_enabled else "Выключен ❌"
        
        custom_kws = await self.storage.get_custom_spam_keywords()
        kw_count_label = f"{len(custom_kws)} слов" if custom_kws else "Пуст ⚪"

        text = (
            "⚙️ <b>Панель настроек AI Message Aggregator</b>\n\n"
            f"⚡ <b>Режим отправки:</b> {mode_label}\n"
            f"⏱️ <b>Интервал сводки:</b> {self.digest_interval} мин\n"
            f"🗑️ <b>Резервное автоудаление:</b> {autodelete_label}\n"
            f"🌙 <b>Ночной режим (Экономия ИИ):</b> {night_label}\n"
            f"🚫 <b>Чёрный список спама:</b> {kw_count_label}\n\n"
            "Вы можете изменить параметры, нажав на соответствующие кнопки ниже:"
        )
        
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"⚡ Режим: {'Сводка' if self.delivery_mode == 'instant' else 'Сразу'}", callback_data="settings_toggle_mode")
            ],
            [
                InlineKeyboardButton(text="⏱️ Изменить интервал сводки", callback_data="settings_menu_interval")
            ],
            [
                InlineKeyboardButton(text="🗑️ Изменить время автоудаления", callback_data="settings_menu_autodelete")
            ],
            [
                InlineKeyboardButton(text=f"🌙 Ночной режим: {'Вкл 🟢' if not self.night_mode_enabled else 'Выкл ❌'}", callback_data="settings_toggle_night_mode")
            ],
            [
                InlineKeyboardButton(text="⏰ Часы ночного режима", callback_data="settings_menu_night_hours")
            ],
            [
                InlineKeyboardButton(text="🚫 Управление Чёрным списком", callback_data="settings_menu_blacklist")
            ],
            [
                InlineKeyboardButton(text="❌ Закрыть настройки", callback_data="delete_msg")
            ]
        ])
        return text, inline_kb

    async def _clear_previous_ui_panels(self):
        """Deletes any previously active UI panel (buffer, settings, stats, clear) to keep chat clean."""
        panels = [
            ("_last_buffer_status_msg_id", self._last_buffer_status_msg_id),
            ("_last_settings_msg_id", self._last_settings_msg_id),
            ("_last_stats_msg_id", self._last_stats_msg_id),
            ("_last_clear_prompt_msg_id", self._last_clear_prompt_msg_id),
        ]
        for attr_name, msg_id in panels:
            if msg_id:
                try:
                    await self.bot.delete_message(chat_id=self.master_chat_id, message_id=msg_id)
                except Exception:
                    pass
                setattr(self, attr_name, None)

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
            sent_msg = await message.answer(
                "🤖 <b>AI Message Aggregator</b>\n\n"
                "Я собираю сообщения из VK и Mail.ru (Авито / Instagram), отсеиваю спам через ИИ "
                "и присылаю важные выжимки по вашему графику.\n\n"
                "🎙️ <b>Отправьте мне голосовое сообщение</b> — я мгновенно переведу его в текст и подготовлю выжимку!\n\n"
                "⚡ <b>Срочные сообщения</b> приходят мгновенно!\n"
                "📥 <b>Обычные и важные</b> копятся в буфере и отправляются сводкой.\n\n"
                "Используйте команду /help для справки по кнопкам.",
                reply_markup=self._get_menu_keyboard(buf_count),
                parse_mode="HTML"
            )
            # Register welcome screen for auto-deletion after 5 minutes
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=300)

        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            buf_count = await self.storage.get_buffer_count()
            help_text = (
                "📖 <b>Справка по командам бота:</b>\n\n"
                "🔹 `/start` — Показать главное меню\n"
                "🔹 `/help` — Эта справка\n"
                "🔹 `/settings` (или ⚙️ Настройки) — Изменить интервал сводки, режим работы и автоудаление\n"
                "🔹 `/flush` (или 🚀 Отправить сводку) — Прислать сообщения из буфера прямо сейчас\n"
                "🔹 `/stats` (или 📊 Статистика) — Посмотреть статистику сообщений\n"
                "🔹 `/clear` (или 🧹 Очистить чат) — Стереть сообщения в чате\n\n"
                "🎙️ <b>Расшифровка голосовых:</b> перешлите или отправьте голосуху, и ИИ переведет её в текст!\n\n"
                "💡 <b>Как работает агрегатор:</b>\n"
                "• Спам отсеивается ИИ и не беспокоит вас.\n"
                "• Запросы клиентов обработаются пакетно раз в 60с для экономии токенов.\n"
                "• При превышении лимита (429 Rate Limit) бот автоматически сделает паузу без потери сообщений!"
            )
            sent_msg = await message.answer(help_text, reply_markup=self._get_menu_keyboard(buf_count), parse_mode="HTML")
            # Register help screen for auto-deletion after 5 minutes
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=300)

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
                    f"🎙️ <b>РАСШИФРОВКА ГОЛОСОВОГО</b>\n\n"
                    f"🗣️ <b>Текст записи:</b>\n<i>{html.escape(res.transcription)}</i>\n\n"
                    f"📝 <b>Выжимка ИИ:</b>\n{html.escape(res.summary)}"
                )

                await status_msg.edit_text(text_response, parse_mode="HTML")

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
                
            await self._clear_previous_ui_panels()
                
            buf_count = await self.storage.get_buffer_count()
            if buf_count > 0:
                status_msg = await message.answer(
                    f"📥 <b>В буфере ожидают отправки:</b> {buf_count} сообщ.\n\n"
                    "Нажмите «🚀 Отправить сводку», чтобы получить их прямо сейчас, или дождитесь отправки по расписанию.",
                    reply_markup=self._get_menu_keyboard(buf_count),
                    parse_mode="HTML"
                )
            else:
                status_msg = await message.answer(
                    "📥 <b>Буфер пуст!</b> Новых сообщений для сводки пока нет.\n"
                    "Бот собирает входящие письма и сообщения в фоновом режиме.",
                    reply_markup=self._get_menu_keyboard(0),
                    parse_mode="HTML"
                )
            self._last_buffer_status_msg_id = status_msg.message_id
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=status_msg.message_id, delay_seconds=300)

        @self.dp.message(F.text == "🚀 Отправить сводку")
        @self.dp.message(Command("flush"))
        async def cmd_send_digest(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
                
            await self._clear_previous_ui_panels()
                
            try:
                sent_count = await self.flush_buffer_now()
                if sent_count == 0:
                    sent_msg = await message.answer("📥 Буфер пуст! Новых сообщений нет.", reply_markup=self._get_menu_keyboard(0))
                    await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=300)
            except Exception as e:
                logger.error(f"Error in manual digest flush: {e}", exc_info=True)
                await message.answer(f"❌ Ошибка отправки сводки: {e}")

        @self.dp.message(F.text == "📊 Статистика")
        @self.dp.message(Command("stats"))
        async def cmd_stats(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass

            await self._clear_previous_ui_panels()

            stats = await self.storage.get_stats()
            buf_count = await self.storage.get_buffer_count()

            stats_msg = (
                "📊 <b>Статистика агрегатора:</b>\n\n"
                f"🚨 <b>Срочные:</b> {stats.get('urgent', 0)}\n"
                f"⭐ <b>Важные:</b> {stats.get('important', 0)}\n"
                f"💬 <b>Обычные:</b> {stats.get('general', 0)}\n"
                f"🚫 <b>Отфильтровано спама:</b> {stats.get('spam', 0)}\n\n"
                f"📥 <b>Не доставлено в буфере:</b> {buf_count}"
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="confirm_reset_stats"),
                    InlineKeyboardButton(text="🗑️ Закрыть", callback_data="delete_msg")
                ]
            ])
            sent_msg = await message.answer(stats_msg, reply_markup=inline_kb, parse_mode="HTML")
            self._last_stats_msg_id = sent_msg.message_id
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=300)

        @self.dp.message(F.text == "⚙️ Настройки")
        @self.dp.message(Command("settings"))
        async def cmd_settings(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass

            await self._clear_previous_ui_panels()

            text, kb = await self._get_settings_text_and_keyboard()
            sent_msg = await message.answer(text=text, reply_markup=kb, parse_mode="HTML")
            self._last_settings_msg_id = sent_msg.message_id
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=300)

        # Handle inline settings menu navigation and callbacks
        @self.dp.callback_query(F.data == "settings_main_menu")
        async def process_settings_main_menu(callback_query: types.CallbackQuery):
            text, kb = await self._get_settings_text_and_keyboard()
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data == "settings_toggle_mode")
        async def process_settings_toggle_mode(callback_query: types.CallbackQuery):
            self.delivery_mode = "instant" if self.delivery_mode == "digest" else "digest"
            await self.storage.set_setting("delivery_mode", self.delivery_mode)
            
            text, kb = await self._get_settings_text_and_keyboard()
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer("Режим отправки изменен!")

        @self.dp.callback_query(F.data == "settings_menu_interval")
        async def process_settings_menu_interval(callback_query: types.CallbackQuery):
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            text = (
                "⏱️ <b>Настройка интервала выгрузки сводки:</b>\n\n"
                f"Текущий интервал: <b>{self.digest_interval} мин</b>\n"
                "Выберите новый интервал ниже:"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="15 мин", callback_data="set_interval_15"),
                    InlineKeyboardButton(text="30 мин", callback_data="set_interval_30"),
                    InlineKeyboardButton(text="1 час (60м)", callback_data="set_interval_60")
                ],
                [
                    InlineKeyboardButton(text="2 часа (120м)", callback_data="set_interval_120"),
                    InlineKeyboardButton(text="4 часа (240м)", callback_data="set_interval_240")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="settings_main_menu")
                ]
            ])
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data.startswith("set_interval_"))
        async def process_set_interval(callback_query: types.CallbackQuery):
            interval_val = int(callback_query.data.split("_")[-1])
            self.digest_interval = interval_val
            await self.storage.set_setting("digest_interval_minutes", str(self.digest_interval))
            
            text, kb = await self._get_settings_text_and_keyboard()
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer(f"Интервал изменен на {interval_val} минут!")

        @self.dp.callback_query(F.data == "settings_menu_autodelete")
        async def process_settings_menu_autodelete(callback_query: types.CallbackQuery):
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            autodelete_label = f"<b>{self.auto_delete_delay_hours} ч</b>" if self.auto_delete_delay_hours > 0 else "<b>Выключено</b>"
            text = (
                "🗑️ <b>Настройка времени автоудаления сообщений:</b>\n\n"
                f"Текущее время автоудаления: {autodelete_label}\n"
                "Выберите время жизни сообщений бота в чате (по истечении которого они будут стерты):"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Отключить ❌", callback_data="set_autodelete_0"),
                    InlineKeyboardButton(text="1 час", callback_data="set_autodelete_1"),
                    InlineKeyboardButton(text="2 часа", callback_data="set_autodelete_2")
                ],
                [
                    InlineKeyboardButton(text="4 часа", callback_data="set_autodelete_4"),
                    InlineKeyboardButton(text="8 часов", callback_data="set_autodelete_8"),
                    InlineKeyboardButton(text="24 часа", callback_data="set_autodelete_24")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="settings_main_menu")
                ]
            ])
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data.startswith("set_autodelete_"))
        async def process_set_autodelete(callback_query: types.CallbackQuery):
            delay_val = int(callback_query.data.split("_")[-1])
            self.auto_delete_delay_hours = delay_val
            await self.storage.set_setting("auto_delete_delay_hours", str(self.auto_delete_delay_hours))
            
            text, kb = await self._get_settings_text_and_keyboard()
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            msg = f"Автоудаление изменено на {delay_val} ч!" if delay_val > 0 else "Автоудаление выключено!"
            await callback_query.answer(msg)

        @self.dp.callback_query(F.data == "settings_toggle_night_mode")
        async def process_settings_toggle_night_mode(callback_query: types.CallbackQuery):
            self.night_mode_enabled = not self.night_mode_enabled
            await self.storage.set_setting("night_mode_enabled", "true" if self.night_mode_enabled else "false")
            
            text, kb = await self._get_settings_text_and_keyboard()
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            msg = "Ночной режим включен! 🌙" if self.night_mode_enabled else "Ночной режим выключен!"
            await callback_query.answer(msg)

        @self.dp.callback_query(F.data == "settings_menu_night_hours")
        async def process_settings_menu_night_hours(callback_query: types.CallbackQuery):
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            text = (
                "🌙 <b>Настройка часов тишины ночного режима:</b>\n\n"
                f"Текущий интервал: <b>{self.night_start_hour:02d}:00 - {self.night_end_hour:02d}:00</b>\n"
                "Выберите удобный промежуток сна (в это время ИИ отключается, а сообщения не беспокоят):"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="23:00 - 07:00", callback_data="set_nighthours_23_7"),
                    InlineKeyboardButton(text="00:00 - 08:00", callback_data="set_nighthours_0_8")
                ],
                [
                    InlineKeyboardButton(text="22:00 - 06:00", callback_data="set_nighthours_22_6"),
                    InlineKeyboardButton(text="01:00 - 09:00", callback_data="set_nighthours_1_9")
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="settings_main_menu")
                ]
            ])
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data.startswith("set_nighthours_"))
        async def process_set_nighthours(callback_query: types.CallbackQuery):
            parts = callback_query.data.split("_")
            start_h, end_h = int(parts[2]), int(parts[3])
            self.night_start_hour = start_h
            self.night_end_hour = end_h
            await self.storage.set_setting("night_start_hour", str(start_h))
            await self.storage.set_setting("night_end_hour", str(end_h))
            
            text, kb = await self._get_settings_text_and_keyboard()
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer(f"Часы тишины установлены: {start_h:02d}:00 - {end_h:02d}:00!")

        @self.dp.callback_query(F.data == "settings_menu_blacklist")
        async def process_settings_menu_blacklist(callback_query: types.CallbackQuery):
            kws = await self.storage.get_custom_spam_keywords()
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            rows = []
            if kws:
                for kw in kws[:10]:  # Show top 10 keywords with inline remove button
                    rows.append([InlineKeyboardButton(text=f"❌ {kw}", callback_data=f"remove_kw_{kw[:20]}")])
                if len(kws) > 10:
                    rows.append([InlineKeyboardButton(text=f"...и ещё {len(kws) - 10} слов", callback_data="none")])
                rows.append([InlineKeyboardButton(text="🧹 Очистить весь список", callback_data="clear_all_blacklist")])

            rows.append([InlineKeyboardButton(text="🔙 Назад в настройки", callback_data="settings_main_menu")])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)

            kws_formatted = ", ".join([f"<code>{html.escape(k)}</code>" for k in kws]) if kws else "<i>Список пока пуст</i>"
            text = (
                "🚫 <b>Управление Чёрным списком спама</b>\n\n"
                f"Текущие слова: {kws_formatted}\n\n"
                "📌 <b>Как использовать:</b>\n"
                "• Отправьте <code>/block слово</code> — заблокировать новое слово (например: <code>/block ставки</code>)\n"
                "• Отправьте <code>/unblock слово</code> — разблокировать слово\n"
                "• Или нажимайте ❌ напротив слова ниже:"
            )
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data.startswith("remove_kw_"))
        async def process_remove_kw(callback_query: types.CallbackQuery):
            kw_to_remove = callback_query.data.replace("remove_kw_", "").strip()
            await self.storage.remove_spam_keyword(kw_to_remove)
            await process_settings_menu_blacklist(callback_query)

        @self.dp.callback_query(F.data == "clear_all_blacklist")
        async def process_clear_all_blacklist(callback_query: types.CallbackQuery):
            await self.storage.set_setting("custom_spam_keywords", "")
            await process_settings_menu_blacklist(callback_query)

        @self.dp.message(Command("block"))
        async def cmd_block(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                sent_msg = await message.answer("⚠️ Использование: <code>/block слово</code> (например: <code>/block казино</code>)", parse_mode="HTML")
            else:
                word = args[1].strip()
                added = await self.storage.add_spam_keyword(word)
                if added:
                    sent_msg = await message.answer(f"🚫 Слово <b>«{html.escape(word)}»</b> добавлено в Чёрный список!", parse_mode="HTML")
                else:
                    sent_msg = await message.answer(f"ℹ️ Слово <b>«{html.escape(word)}»</b> уже есть в Чёрном списке.", parse_mode="HTML")
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=60)

        @self.dp.message(Command("unblock"))
        async def cmd_unblock(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                sent_msg = await message.answer("⚠️ Использование: <code>/unblock слово</code> (например: <code>/unblock казино</code>)", parse_mode="HTML")
            else:
                word = args[1].strip()
                removed = await self.storage.remove_spam_keyword(word)
                if removed:
                    sent_msg = await message.answer(f"✅ Слово <b>«{html.escape(word)}»</b> удалено из Чёрного списка!", parse_mode="HTML")
                else:
                    sent_msg = await message.answer(f"ℹ️ Слова <b>«{html.escape(word)}»</b> не было в Чёрном списке.", parse_mode="HTML")
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=60)

        @self.dp.message(Command("blacklist"))
        async def cmd_blacklist(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            kws = await self.storage.get_custom_spam_keywords()
            if not kws:
                txt = "🚫 <b>Ваш Чёрный список спама пуст.</b>\n\nЧтобы добавить слово: <code>/block слово</code>"
            else:
                formatted = "\n".join([f"• <code>{html.escape(k)}</code>" for k in kws])
                txt = f"🚫 <b>Ваш Чёрный список спама ({len(kws)}):</b>\n\n{formatted}\n\nДля добавления: <code>/block слово</code>\nДля удаления: <code>/unblock слово</code>"
            
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑️ Закрыть", callback_data="delete_msg")]
            ])
            sent_msg = await message.answer(txt, reply_markup=inline_kb, parse_mode="HTML")
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=300)

        @self.dp.callback_query(F.data == "confirm_reset_stats")
        async def process_confirm_reset_stats(callback_query: types.CallbackQuery):
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, сбросить", callback_data="do_reset_stats"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="delete_msg")
                ]
            ])
            try:
                await callback_query.message.edit_text(
                    "⚠️ <b>Вы действительно хотите сбросить всю накопленную статистику сообщений?</b>",
                    reply_markup=inline_kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data == "do_reset_stats")
        async def process_do_reset_stats(callback_query: types.CallbackQuery):
            await self.storage.reset_stats()
            stats = await self.storage.get_stats()
            buf_count = await self.storage.get_buffer_count()

            stats_msg = (
                "📊 <b>Статистика агрегатора (Сброшено ✅):</b>\n\n"
                f"🚨 <b>Срочные:</b> {stats.get('urgent', 0)}\n"
                f"⭐ <b>Важные:</b> {stats.get('important', 0)}\n"
                f"💬 <b>Обычные:</b> {stats.get('general', 0)}\n"
                f"🚫 <b>Отфильтровано спама:</b> {stats.get('spam', 0)}\n\n"
                f"📥 <b>Не доставлено в буфере:</b> {buf_count}"
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="confirm_reset_stats"),
                    InlineKeyboardButton(text="🗑️ Закрыть", callback_data="delete_msg")
                ]
            ])
            try:
                await callback_query.message.edit_text(stats_msg, reply_markup=inline_kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer("Статистика успешно сброшена!")

        @self.dp.message(Command("clear"))
        @self.dp.message(F.text == "🧹 Очистить чат")
        async def cmd_clear_chat(message: types.Message):
            # Delete the user's trigger message to keep it clean
            try:
                await message.delete()
            except Exception:
                pass

            # Auto-delete previous clear prompt if open
            if self._last_clear_prompt_msg_id:
                try:
                    await self.bot.delete_message(chat_id=self.master_chat_id, message_id=self._last_clear_prompt_msg_id)
                except Exception:
                    pass
                self._last_clear_prompt_msg_id = None

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, очистить", callback_data="confirm_clear_chat"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clear_chat")
                ]
            ])
            sent_msg = await message.answer(
                text="⚠️ <b>Вы действительно хотите очистить чат в Telegram?</b>\n<i>(Сообщения останутся в базе данных)</i>",
                reply_markup=inline_kb,
                parse_mode="HTML"
            )
            self._last_clear_prompt_msg_id = sent_msg.message_id
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=300)

        # Handle inline "Read/Delete" button click
        @self.dp.callback_query(F.data == "delete_msg")
        async def process_delete_msg(callback_query: types.CallbackQuery):
            msg_id = callback_query.message.message_id
            if msg_id == self._last_settings_msg_id:
                self._last_settings_msg_id = None
            if msg_id == self._last_stats_msg_id:
                self._last_stats_msg_id = None
            if msg_id == self._last_buffer_status_msg_id:
                self._last_buffer_status_msg_id = None
            if msg_id == self._last_clear_prompt_msg_id:
                self._last_clear_prompt_msg_id = None
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            await callback_query.answer()

        # Handle inline confirmation of chat clearing
        @self.dp.callback_query(F.data == "confirm_clear_chat")
        async def process_confirm_clear_chat(callback_query: types.CallbackQuery):
            await callback_query.answer("Очистка чата...")
            
            # Delete the confirmation message immediately
            try:
                await callback_query.message.delete()
            except Exception:
                pass
                
            # Perform deletion loop and keyboard restoration asynchronously in background
            async def _do_delete_bg():
                current_id = callback_query.message.message_id
                for msg_id in range(current_id, current_id - 100, -1):
                    try:
                        await self.bot.delete_message(chat_id=callback_query.message.chat.id, message_id=msg_id)
                    except Exception:
                        pass

                try:
                    buf_count = await self.storage.get_buffer_count()
                    sent_msg = await self.bot.send_message(
                        chat_id=callback_query.message.chat.id,
                        text="🤖 <b>AI Message Aggregator</b> — <i>Активен 🟢</i>",
                        reply_markup=self._get_menu_keyboard(buf_count),
                        parse_mode="HTML"
                    )
                    self._last_buffer_status_msg_id = sent_msg.message_id
                except Exception as e:
                    logger.error(f"Error restoring reply keyboard after clear: {e}")

            asyncio.create_task(_do_delete_bg())

        @self.dp.callback_query(F.data == "cancel_clear_chat")
        async def process_cancel_clear_chat(callback_query: types.CallbackQuery):
            # Just delete the confirmation message
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
        header = CATEGORY_EMOJIS.get(category, "📩 <b>СООБЩЕНИЕ</b>")
        reply_part = f"\n\n💡 <b>Черновик ответа:</b>\n<code>{html.escape(suggested_reply)}</code>" if suggested_reply else ""
        action_part = "\n⚡ <b>Требуется ответ!</b>" if action_required else ""

        message_text = (
            f"{header}\n"
            f"📍 <b>Канал:</b> {html.escape(channel)}\n"
            f"👤 <b>От:</b> {html.escape(sender)}\n\n"
            f"📝 <b>Выжимка AI:</b>\n{html.escape(summary)}{action_part}{reply_part}\n\n"
            f"--- Текст ---\n"
            f"<i>{html.escape(text[:250])}{'...' if len(text) > 250 else ''}</i>"
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
                    parse_mode="HTML",
                    reply_markup=inline_kb
                )
                # Register for auto-deletion if config value is greater than 0
                if self.auto_delete_delay_hours > 0:
                    delay = self.auto_delete_delay_hours * 3600
                    await self.storage.save_sent_notification(
                        chat_id=self.master_chat_id,
                        message_id=sent_msg.message_id,
                        delay_seconds=delay
                    )
            except Exception as e:
                logger.error(f"Error sending Telegram notification: {e}")

    async def flush_buffer_now(self) -> int:
        """Sends all buffered messages as a formatted digest."""
        # 1. Flush any pending raw messages in queue to AI/DB first
        if self.on_flush_raw_queue:
            try:
                await self.on_flush_raw_queue()
            except Exception as fe:
                logger.error(f"Error flushing raw queue prior to digest: {fe}")

        messages = await self.storage.get_buffered_messages(mark_as_delivered=True)
        if not messages:
            return 0

        digest_parts = [f"📬 <b>СВОДКА СООБЩЕНИЙ ({len(messages)})</b>\n"]
        for idx, m in enumerate(messages, 1):
            emoji = CATEGORY_EMOJIS.get(m['category'], "💬")
            digest_parts.append(
                f"<b>{idx}. [{html.escape(m['channel'])}]</b> {html.escape(m['sender'])} ({emoji})\n"
                f"📝 {html.escape(m['summary'])}\n"
                f"<i>{html.escape(m['text'][:150])}...</i>\n"
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
                            parse_mode="HTML",
                            reply_markup=inline_kb
                        )
                        if self.auto_delete_delay_hours > 0:
                            delay = self.auto_delete_delay_hours * 3600
                            await self.storage.save_sent_notification(
                                chat_id=self.master_chat_id,
                                message_id=sent_msg.message_id,
                                delay_seconds=delay
                            )
                else:
                    sent_msg = await self.bot.send_message(
                        chat_id=self.master_chat_id,
                        text=full_digest,
                        parse_mode="HTML",
                        reply_markup=inline_kb
                    )
                    if self.auto_delete_delay_hours > 0:
                        delay = self.auto_delete_delay_hours * 3600
                        await self.storage.save_sent_notification(
                            chat_id=self.master_chat_id,
                            message_id=sent_msg.message_id,
                            delay_seconds=delay
                        )
            except Exception as e:
                logger.error(f"Error sending digest: {e}")

        # Clean up the buffer status message if it exists
        if self._last_buffer_status_msg_id:
            try:
                await self.bot.delete_message(chat_id=self.master_chat_id, message_id=self._last_buffer_status_msg_id)
            except Exception:
                pass
            self._last_buffer_status_msg_id = None

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
        """Background task that periodically deletes expired notifications from Telegram and purges old DB records."""
        logger.info(f"Cleanup scheduler running (auto-delete delay: {self.auto_delete_delay_hours}h, DB 7-day purge active)...")
        last_db_purge_time = 0
        while True:
            await asyncio.sleep(60)  # Check every minute
            try:
                # 1. Telegram Message Auto-Deletion
                expired = await self.storage.get_expired_notifications()
                for item in expired:
                    try:
                        await self.bot.delete_message(chat_id=item['chat_id'], message_id=item['message_id'])
                        logger.info(f"Auto-deleted expired message {item['message_id']} in chat {item['chat_id']}.")
                    except Exception as de:
                        logger.debug(f"Failed to auto-delete message {item['message_id']} in chat {item['chat_id']}: {de}")
                    # Always delete from DB so we don't retry endlessly
                    await self.storage.delete_sent_notification(item['id'])

                # 2. Database 7-day auto-purge for delivered/spam messages (runs once per hour)
                now_ts = asyncio.get_running_loop().time()
                if now_ts - last_db_purge_time >= 3600:
                    await self.storage.purge_old_messages(days=7)
                    last_db_purge_time = now_ts

            except Exception as e:
                logger.error(f"Error in cleanup scheduler: {e}")

    async def start_polling(self):
        if self.bot and self.dp:
            logger.info("Starting Telegram Bot Polling loop...")
            
            # Load settings asynchronously from DB
            self.delivery_mode = await self.storage.get_setting("delivery_mode", self.delivery_mode)
            self.digest_interval = int(await self.storage.get_setting("digest_interval_minutes", str(self.digest_interval)))
            self.auto_delete_delay_hours = int(await self.storage.get_setting("auto_delete_delay_hours", str(self.auto_delete_delay_hours)))
            self.night_mode_enabled = (await self.storage.get_setting("night_mode_enabled", "false")).lower() in ("true", "1", "yes")
            self.night_start_hour = int(await self.storage.get_setting("night_start_hour", str(self.night_start_hour)))
            self.night_end_hour = int(await self.storage.get_setting("night_end_hour", str(self.night_end_hour)))
            
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
