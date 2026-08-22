import asyncio
import logging
import html
import io
from typing import Optional, Callable, Awaitable, Any, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from config import config
from storage import Storage
import ui_keyboards as kb_ui

logger = logging.getLogger(__name__)

# Category Emojis
CATEGORY_EMOJIS = {
    "urgent": "🚨 <b>СРОЧНО</b>",
    "important": "⭐ <b>ВАЖНОЕ</b>",
    "general": "💬 <b>ОБЫЧНОЕ</b>",
    "spam": "🚫 <b>СПАМ</b>"
}

class AccessControlMiddleware(BaseMiddleware):
    def __init__(self, master_bot_ref: Any):
        self.master_bot = master_bot_ref
        super().__init__()

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]], event: TelegramObject, data: dict) -> Any:
        from aiogram.types import Message, CallbackQuery
        user_id = None
        event_name = type(event).__name__
        text_preview = ""
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            text_preview = event.text or event.caption or ""
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            text_preview = event.data or ""

        master_id = self.master_bot.master_chat_id
        logger.info(f"📩 Telegram Event [{event_name}] from user_id={user_id} (data='{text_preview}', expected master_id={master_id})")

        # Security check:
        if master_id and str(master_id) != "0":
            # Strict lockdown: ONLY the registered owner ID is allowed
            if user_id and str(user_id) != str(master_id):
                if isinstance(event, Message) and event.text and event.text.startswith("/start"):
                    logger.info(f"Re-capturing master_chat_id via /start from user_id: {user_id}")
                    return await handler(event, data)

                logger.warning(f"⛔ Blocking unauthorized Telegram interaction from user_id: {user_id} (Expected master_chat_id: {master_id})")
                return None  # Ignore unauthorized event completely
        else:
            # First initialization fallback if master_chat_id is empty
            if user_id:
                logger.info(f"Auto-capturing initial master_chat_id from user_id: {user_id}")
                self.master_bot.master_chat_id = user_id
                asyncio.create_task(self.master_bot.storage.set_setting("master_chat_id", str(user_id)))

        return await handler(event, data)

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit_seconds: float = 0.7):
        self.rate_limit = rate_limit_seconds
        self.user_last_event: Dict[int, float] = {}
        super().__init__()

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]], event: TelegramObject, data: dict) -> Any:
        from aiogram.types import Message, CallbackQuery
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None

        if user_id:
            import time
            now = time.time()
            last_time = self.user_last_event.get(user_id, 0)
            if now - last_time < self.rate_limit:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("⚡ Слишком частые нажатия!", show_alert=False)
                    except Exception:
                        pass
                logger.warning(f"⚡ Throttled rapid update from user_id: {user_id} ({now - last_time:.2f}s < {self.rate_limit}s)")
                return None
            self.user_last_event[user_id] = now

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
        self._last_ui_msg_id = None
        self._last_clear_prompt_msg_id = None
        self._last_buffer_status_msg_id = None
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
        
        # Register security & rate-limiting middlewares
        self.dp.message.outer_middleware(AccessControlMiddleware(self))
        self.dp.message.outer_middleware(ThrottlingMiddleware(rate_limit_seconds=0.2))
        self.dp.callback_query.outer_middleware(AccessControlMiddleware(self))
        self.dp.callback_query.outer_middleware(ThrottlingMiddleware(rate_limit_seconds=0.2))
            
        self._setup_handlers()
        logger.info(f"Telegram MasterBot initialized (Proxy: {proxy_url if session else 'Direct'}).")

    def _get_menu_keyboard(self, buffer_count: int = 0, is_sub_menu: bool = False):
        return kb_ui.get_main_reply_keyboard(buffer_count, is_sub_menu=is_sub_menu)

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
            BotCommand(command="clear", description="Очистить последние сообщения чата"),
            BotCommand(command="logs", description="Живой лог событий и диагностика системы")
        ]
        try:
            await asyncio.wait_for(self.bot.set_my_commands(commands), timeout=5.0)
            logger.info("Registered Telegram Bot slash commands menu.")
        except Exception as e:
            logger.warning(f"Could not set bot commands: {e}")

    async def _get_diagnostic_logs_text_and_keyboard(self):
        from logger_config import RecentLogHandler
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        recent = RecentLogHandler.recent_logs[-10:]
        if not recent:
            log_lines = ["<i>Логи пока пусты.</i>"]
        else:
            log_lines = [f"• <code>{html.escape(line)}</code>" for line in recent]
        
        proxy_info = config.TELEGRAM_PROXY if config.TELEGRAM_PROXY else "Прямое (Direct 🟢)"
        
        text = (
            "🛠️ <b>Диагностика системы и Живой Лог</b>\n\n"
            f"🌐 <b>Подключение Telegram:</b> {proxy_info}\n"
            f"👤 <b>Master Chat ID:</b> <code>{self.master_chat_id}</code>\n"
            f"⚡ <b>Режим:</b> {self.delivery_mode.upper()} ({self.digest_interval}м)\n"
            f"🌙 <b>Ночной режим:</b> {'Вкл 🟢' if self.night_mode_enabled else 'Выкл ❌'}\n\n"
            "📜 <b>Последние 10 системных событий:</b>\n"
            + "\n".join(log_lines)
        )
        
        return text, kb_ui.get_logs_keyboard()

    async def _get_settings_text_and_keyboard(self):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        mode_label = "⚡ СРАЗУ (Мгновенно)" if self.delivery_mode == "instant" else "📥 СВОДКА (Раз в час)"
        autodelete_label = f"{self.auto_delete_delay_hours} ч" if self.auto_delete_delay_hours > 0 else "Выключено ❌"
        night_label = f"🟢 Включен ({self.night_start_hour:02d}:00 - {self.night_end_hour:02d}:00)" if self.night_mode_enabled else "Выключен ❌"
        
        all_bws = await self.storage.get_banwords()
        kw_count_label = f"{len(all_bws)} активных" if all_bws else "Пуст ⚪"

        text = (
            "⚙️ <b>Панель настроек AI Message Aggregator</b>\n\n"
            f"⚡ <b>Режим отправки:</b> {mode_label}\n"
            f"⏱️ <b>Интервал сводки:</b> {self.digest_interval} мин\n"
            f"🗑️ <b>Резервное автоудаление:</b> {autodelete_label}\n"
            f"🌙 <b>Ночной режим (Экономия ИИ):</b> {night_label}\n"
            f"🚫 <b>Банворды (Banwords):</b> {kw_count_label}\n\n"
            "Вы можете изменить параметры, нажав на соответствующие кнопки ниже:"
        )
        
        return text, kb_ui.get_settings_keyboard(self.delivery_mode, self.night_mode_enabled)

    async def show_or_edit_ui_panel(self, text: str, keyboard: Any = None, parse_mode: str = "HTML", force_new: bool = False):
        """Displays or smoothly edits the single active UI window in-place."""
        target_chat = self.master_chat_id
        if not target_chat or not self.bot:
            return

        from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
        inline_kb = keyboard if isinstance(keyboard, InlineKeyboardMarkup) else None
        reply_kb = keyboard if isinstance(keyboard, ReplyKeyboardMarkup) else None

        if self._last_ui_msg_id:
            if force_new:
                # User wants a fresh message at the bottom (e.g., used a command or reply keyboard)
                try:
                    await self.bot.delete_message(chat_id=target_chat, message_id=self._last_ui_msg_id)
                except Exception:
                    pass
                self._last_ui_msg_id = None
            else:
                try:
                    await self.bot.edit_message_text(
                        chat_id=target_chat,
                        message_id=self._last_ui_msg_id,
                        text=text,
                        reply_markup=inline_kb,
                        parse_mode=parse_mode
                    )
                    return
                except Exception as e:
                    err_str = str(e).lower()
                    if "not modified" in err_str:
                        return
                    # Message missing or deleted, reset ID to recreate
                    try:
                        await self.bot.delete_message(chat_id=target_chat, message_id=self._last_ui_msg_id)
                    except Exception:
                        pass
                    self._last_ui_msg_id = None

        try:
            sent_msg = await self.bot.send_message(
                chat_id=target_chat,
                text=text,
                reply_markup=inline_kb or reply_kb,
                parse_mode=parse_mode
            )
            self._last_ui_msg_id = sent_msg.message_id
            await self.storage.set_setting("last_ui_msg_id", str(sent_msg.message_id))
        except Exception as e:
            logger.error(f"Error updating single UI panel: {e}")

    async def update_status_banner(self, chat_id: Optional[int] = None, force_new: bool = False):
        """Creates or updates the single active status banner in-place."""
        target_chat = chat_id or self.master_chat_id
        if not target_chat or not self.bot:
            return

        buf_count = await self.storage.get_buffer_count()
        text = "<b>AI Message Aggregator</b> — <i>Активен 🟢</i>"
        reply_kb = kb_ui.get_main_reply_keyboard(buf_count)
        await self.show_or_edit_ui_panel(text=text, keyboard=reply_kb, force_new=force_new)

    def _setup_handlers(self):
        from aiogram.filters import Command
        from aiogram import types, F

        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            if message.from_user:
                self.master_chat_id = message.from_user.id
                await self.storage.set_setting("master_chat_id", str(self.master_chat_id))
                logger.info(f"Captured/Updated master_chat_id from /start: {self.master_chat_id}")
            try:
                await message.delete()
            except Exception:
                pass
            await self.update_status_banner(self.master_chat_id, force_new=True)

        @self.dp.message(F.text == "🏠 Главное меню")
        async def cmd_main_menu_button(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            await self.update_status_banner(force_new=False)

        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
            await self.show_or_edit_ui_panel(text=help_text, keyboard=kb_ui.get_help_keyboard(), force_new=False)

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

        @self.dp.message(F.text & ~F.text.startswith("/"))
        async def handle_text_message(message: types.Message):
            # Check if user clicked a menu ReplyButton
            menu_texts = ["📥 Буфер", "📊 Статистика", "⚙️ Настройки", "🧹 Очистить чат", "🚀 Отправить сводку", "🏠 Главное меню"]
            if any(message.text.startswith(m) for m in menu_texts):
                return  # Let specific handlers process menu triggers

            # Check if bot is waiting for interactive banword text input
            if self._waiting_for_banword_scope:
                word_to_add = message.text.strip()
                scope = self._waiting_for_banword_scope
                self._waiting_for_banword_scope = None

                try:
                    await message.delete()
                except Exception:
                    pass

                added = await self.storage.add_banword(word_to_add, scope=scope)
                scope_name = "Mail.ru" if scope == "email" else ("ВКонтакте" if scope == "vk" else "Общие")

                if added:
                    sent_msg = await message.answer(f"✅ Банворд <b>«{html.escape(word_to_add)}»</b> успешно добавлен в {scope_name}!", parse_mode="HTML")
                else:
                    sent_msg = await message.answer(f"ℹ️ Банворд <b>«{html.escape(word_to_add)}»</b> уже есть в {scope_name}.", parse_mode="HTML")

                await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=60)
                
                # Refresh UI panel to show banword list
                bws = await self.storage.get_banwords(scope=scope)
                lines = [f"{'✉️' if scope == 'email' else '💬'} <b>Банворды {scope_name}</b> (Всего: {len(bws)})\n"]
                for idx, b in enumerate(bws, 1):
                    lines.append(f"{idx}. <code>{html.escape(b['word'])}</code>")
                lines.append("\n📌 <i>Нажмите ❌ #№ ниже для удаления</i>")
                
                kb = kb_ui.get_banwords_list_keyboard(bws[:10], 1, max(1, (len(bws)+9)//10), scope, 0)
                await self.show_or_edit_ui_panel(text="\n".join(lines), keyboard=kb, force_new=False)

        @self.dp.message(F.text.startswith("📥 Буфер"))
        async def cmd_buffer(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
                
            buf_count = await self.storage.get_buffer_count()
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            await self.show_or_edit_ui_panel(text=text, keyboard=kb_ui.get_buffer_keyboard(buf_count), force_new=False)

        @self.dp.callback_query(F.data == "flush_now")
        async def process_flush_now_callback(callback_query: types.CallbackQuery):
            sent_count = await self.flush_buffer_now()
            if sent_count == 0:
                await callback_query.answer("📥 Буфер пуст!", show_alert=True)
            else:
                await callback_query.answer("🚀 Сводка отправлена!")
            await self.update_status_banner()

        @self.dp.message(F.text == "🚀 Отправить сводку")
        @self.dp.message(Command("flush"))
        async def cmd_send_digest(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
                
            try:
                sent_count = await self.flush_buffer_now()
                if sent_count == 0:
                    await self.update_status_banner(force_new=True)
            except Exception as e:
                logger.error(f"Error in manual digest flush: {e}", exc_info=True)

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
                "📊 <b>Статистика агрегатора:</b>\n\n"
                f"🚨 <b>Срочные:</b> {stats.get('urgent', 0)}\n"
                f"⭐ <b>Важные:</b> {stats.get('important', 0)}\n"
                f"💬 <b>Обычные:</b> {stats.get('general', 0)}\n"
                f"🚫 <b>Отфильтровано спама:</b> {stats.get('spam', 0)}\n\n"
                f"📥 <b>Не доставлено в буфере:</b> {buf_count}"
            )
            await self.show_or_edit_ui_panel(text=stats_msg, keyboard=kb_ui.get_stats_keyboard(), force_new=False)

        @self.dp.message(Command("logs"))
        @self.dp.message(Command("debug"))
        async def cmd_logs(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            text, kb = await self._get_diagnostic_logs_text_and_keyboard()
            await self.show_or_edit_ui_panel(text=text, keyboard=kb)

        @self.dp.callback_query(F.data == "refresh_logs")
        async def process_refresh_logs(callback_query: types.CallbackQuery):
            text, kb = await self._get_diagnostic_logs_text_and_keyboard()
            await self.show_or_edit_ui_panel(text=text, keyboard=kb, force_new=False)
            await callback_query.answer("Логи обновлены!")

        @self.dp.message(F.text == "⚙️ Настройки")
        @self.dp.message(Command("settings"))
        async def cmd_settings(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass

            text, kb = await self._get_settings_text_and_keyboard()
            await self.show_or_edit_ui_panel(text=text, keyboard=kb, force_new=False)

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
            text = (
                "⏱️ <b>Настройка интервала выгрузки сводки:</b>\n\n"
                f"Текущий интервал: <b>{self.digest_interval} мин</b>\n"
                "Выберите новый интервал ниже:"
            )
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_interval_keyboard(), parse_mode="HTML")
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
            autodelete_label = f"<b>{self.auto_delete_delay_hours} ч</b>" if self.auto_delete_delay_hours > 0 else "<b>Выключено</b>"
            text = (
                "🗑️ <b>Настройка времени автоудаления сообщений:</b>\n\n"
                f"Текущее время автоудаления: {autodelete_label}\n"
                "Выберите время жизни сообщений бота в чате (по истечении которого они будут стерты):"
            )
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_autodelete_keyboard(), parse_mode="HTML")
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
            text = (
                "🌙 <b>Настройка часов тишины ночного режима:</b>\n\n"
                f"Текущий интервал: <b>{self.night_start_hour:02d}:00 - {self.night_end_hour:02d}:00</b>\n"
                "Выберите удобный промежуток сна (в это время ИИ отключается, а сообщения не беспокоят):"
            )
            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_nighthours_keyboard(), parse_mode="HTML")
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
            bws_email = await self.storage.get_banwords(scope="email")
            bws_vk = await self.storage.get_banwords(scope="vk")
            
            text = (
                "🚫 <b>Управление Банвордами (Banwords)</b>\n\n"
                "Выберите категорию для просмотра полного списка и удаления слов:\n\n"
                f"✉️ <b>Mail.ru:</b> {len(bws_email)} банвордов\n"
                f"💬 <b>ВКонтакте (VK):</b> {len(bws_vk)} банвордов\n\n"
                "📌 <b>Команды в чате:</b>\n"
                "• <code>/block слово email</code> — добавить в Mail.ru\n"
                "• <code>/block слово vk</code> — добавить в VK\n"
                "• <code>/unblock номер email</code> или <code>/unblock номер vk</code> — удалить"
            )

            try:
                await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_blacklist_menu_keyboard(len(bws_email), len(bws_vk)), parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data.startswith("bw_view_email_"))
        async def process_bw_view_email(callback_query: types.CallbackQuery):
            page = int(callback_query.data.replace("bw_view_email_", ""))
            bws = await self.storage.get_banwords(scope="email")
            
            per_page = 10
            total_pages = max(1, (len(bws) + per_page - 1) // per_page)
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * per_page
            page_bws = bws[start_idx:start_idx + per_page]

            lines = [f"✉️ <b>Банворды Mail.ru</b> (Стр. {page}/{total_pages}, всего: {len(bws)})\n"]
            if not bws:
                lines.append("<i>Список банвордов Mail.ru пуст.</i>")
            else:
                for idx_in_page, b in enumerate(page_bws, start=start_idx + 1):
                    lines.append(f"{idx_in_page}. <code>{html.escape(b['word'])}</code>")

            lines.append("\n📌 <i>Нажмите ❌ #№ ниже для удаления или отправьте <code>/unblock номер email</code></i>")

            kb = kb_ui.get_banwords_list_keyboard(page_bws, page, total_pages, "email", start_idx)
            try:
                await callback_query.message.edit_text(text="\n".join(lines), reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data.startswith("bw_view_vk_"))
        async def process_bw_view_vk(callback_query: types.CallbackQuery):
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            page = int(callback_query.data.replace("bw_view_vk_", ""))
            bws = await self.storage.get_banwords(scope="vk")
            
            per_page = 10
            total_pages = max(1, (len(bws) + per_page - 1) // per_page)
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * per_page
            page_bws = bws[start_idx:start_idx + per_page]

            lines = [f"💬 <b>Банворды ВКонтакте (VK)</b> (Стр. {page}/{total_pages}, всего: {len(bws)})\n"]
            if not bws:
                lines.append("<i>Список банвордов VK пуст.</i>")
            else:
                for idx_in_page, b in enumerate(page_bws, start=start_idx + 1):
                    lines.append(f"{idx_in_page}. <code>{html.escape(b['word'])}</code>")

            lines.append("\n📌 <i>Нажмите ❌ #№ ниже для удаления или отправьте <code>/unblock номер vk</code></i>")

            rows = []
            row_buttons = []
            for idx_in_page, b in enumerate(page_bws, start=start_idx + 1):
                row_buttons.append(InlineKeyboardButton(text=f"❌ #{idx_in_page}", callback_data=f"remove_bw_vk_{idx_in_page}_{page}"))
                if len(row_buttons) == 3:
                    rows.append(row_buttons)
                    row_buttons = []
            if row_buttons:
                rows.append(row_buttons)

            # Pagination buttons
            nav_row = []
            if page > 1:
                nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"bw_view_vk_{page - 1}"))
            nav_row.append(InlineKeyboardButton(text="❇️ ➕ Добавить банворд", callback_data="add_bw_prompt_vk"))
            if page < total_pages:
                nav_row.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"bw_view_vk_{page + 1}"))
            rows.append(nav_row)

            rows.append([InlineKeyboardButton(text="🔙 К категориям банвордов", callback_data="settings_menu_blacklist")])
            rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="delete_msg")])

            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            try:
                await callback_query.message.edit_text(text="\n".join(lines), reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer()

        @self.dp.callback_query(F.data.startswith("remove_bw_email_"))
        async def process_remove_bw_email(callback_query: types.CallbackQuery):
            parts = callback_query.data.replace("remove_bw_email_", "").split("_")
            idx = parts[0]
            page = parts[1] if len(parts) > 1 else "1"
            await self.storage.remove_banword(idx, scope="email")
            callback_query.data = f"bw_view_email_{page}"
            await process_bw_view_email(callback_query)

        @self.dp.callback_query(F.data.startswith("remove_bw_vk_"))
        async def process_remove_bw_vk(callback_query: types.CallbackQuery):
            parts = callback_query.data.replace("remove_bw_vk_", "").split("_")
            idx = parts[0]
            page = parts[1] if len(parts) > 1 else "1"
            await self.storage.remove_banword(idx, scope="vk")
            callback_query.data = f"bw_view_vk_{page}"
            await process_bw_view_vk(callback_query)

        @self.dp.callback_query(F.data == "add_bw_select_scope")
        async def process_add_bw_select_scope(callback_query: types.CallbackQuery):
            await callback_query.answer()
            try:
                await callback_query.message.edit_text(
                    "➕ <b>Выберите категорию для добавления банворда:</b>",
                    reply_markup=kb_ui.get_add_bw_select_scope_keyboard(),
                    parse_mode="HTML"
                )
            except Exception:
                pass

        @self.dp.callback_query(F.data == "add_bw_prompt_email")
        async def process_add_bw_prompt_email(callback_query: types.CallbackQuery):
            await callback_query.answer()
            self._waiting_for_banword_scope = "email"
            try:
                await callback_query.message.edit_text(
                    "✏️ <b>Отправьте слово или фразу для добавления (Mail.ru):</b>",
                    reply_markup=kb_ui.get_add_banword_prompt_keyboard(),
                    parse_mode="HTML"
                )
            except Exception:
                pass

        @self.dp.callback_query(F.data == "add_bw_prompt_vk")
        async def process_add_bw_prompt_vk(callback_query: types.CallbackQuery):
            await callback_query.answer()
            self._waiting_for_banword_scope = "vk"
            try:
                await callback_query.message.edit_text(
                    "✏️ <b>Отправьте слово или фразу для добавления (VK):</b>",
                    reply_markup=kb_ui.get_add_banword_prompt_keyboard(),
                    parse_mode="HTML"
                )
            except Exception:
                pass

        @self.dp.callback_query(F.data == "reset_banwords_confirm")
        async def process_reset_banwords_confirm(callback_query: types.CallbackQuery):
            await self.storage.reset_banwords_to_default()
            await process_settings_menu_blacklist(callback_query)

        @self.dp.message(Command("block"))
        async def cmd_block(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                sent_msg = await message.answer(
                    "⚠️ <b>Использование /block:</b>\n"
                    "• <code>/block слово</code> (для всех каналов)\n"
                    "• <code>/block слово email</code> (для Mail.ru)\n"
                    "• <code>/block слово vk</code> (для VK)",
                    parse_mode="HTML"
                )
            else:
                word = args[1].strip()
                scope = args[2].strip().lower() if len(args) >= 3 else "global"
                if scope not in ("email", "vk", "global"):
                    scope = "global"
                res = await self.storage.add_banword(word, scope)
                if res:
                    scope_label = "Общий" if res['scope'] == 'global' else res['scope'].upper()
                    sent_msg = await message.answer(
                        f"🚫 Банворд #{res['id']} <b>«{html.escape(res['word'])}»</b> ({scope_label}) добавлен!",
                        parse_mode="HTML"
                    )
                else:
                    sent_msg = await message.answer(f"ℹ️ Банворд <b>«{html.escape(word)}»</b> уже есть в списке.", parse_mode="HTML")
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=60)

        @self.dp.message(Command("unblock"))
        async def cmd_unblock(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                sent_msg = await message.answer(
                    "⚠️ <b>Использование /unblock:</b>\n"
                    "• <code>/unblock номер email</code> (удалить из Mail.ru)\n"
                    "• <code>/unblock номер vk</code> (удалить из VK)\n"
                    "• <code>/unblock слово</code> (удалить слово по названию)",
                    parse_mode="HTML"
                )
            else:
                target = args[1].strip()
                scope = args[2].strip().lower() if len(args) >= 3 else None
                deleted_word = await self.storage.remove_banword(target, scope=scope)
                if deleted_word:
                    sent_msg = await message.answer(f"✅ Банворд <b>«{html.escape(deleted_word)}»</b> удален из списка!", parse_mode="HTML")
                else:
                    sent_msg = await message.answer(f"ℹ️ Банворд <b>«{html.escape(target)}»</b> не найден.", parse_mode="HTML")
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=60)

        @self.dp.message(Command("reset_banwords"))
        async def cmd_reset_banwords(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            await self.storage.reset_banwords_to_default()
            sent_msg = await message.answer("🔄 Все банворды сброшены к базовым системным настройкам!", parse_mode="HTML")
            await self.storage.save_sent_notification(chat_id=self.master_chat_id, message_id=sent_msg.message_id, delay_seconds=60)

        @self.dp.message(Command("banwords"))
        @self.dp.message(Command("blacklist"))
        async def cmd_blacklist(message: types.Message):
            try:
                await message.delete()
            except Exception:
                pass
            bws = await self.storage.get_banwords()
            
            lines = ["🚫 <b>Единый список банвордов (Banwords)</b>\n"]
            globals_list = [b for b in bws if b.get("scope", "global") == "global"]
            emails_list = [b for b in bws if b.get("scope") == "email"]
            vks_list = [b for b in bws if b.get("scope") == "vk"]

            if globals_list:
                lines.append("🌐 <b>Общие (для всех каналов):</b>")
                for b in globals_list:
                    lines.append(f"{b['id']}. <code>{html.escape(b['word'])}</code>")
                lines.append("")

            if emails_list:
                lines.append("✉️ <b>Mail.ru / Email:</b>")
                for b in emails_list:
                    lines.append(f"{b['id']}. <code>{html.escape(b['word'])}</code>")
                lines.append("")

            if vks_list:
                lines.append("💬 <b>ВКонтакте (VK):</b>")
                for b in vks_list:
                    lines.append(f"{b['id']}. <code>{html.escape(b['word'])}</code>")
                lines.append("")

            lines.append(
                "📌 <b>Управление:</b>\n"
                "• <code>/block слово</code> — добавить общий банворд\n"
                "• <code>/block слово email</code> — банворд для Mail.ru\n"
                "• <code>/block слово vk</code> — банворд для VK\n"
                "• <code>/unblock номер</code> — удалить по номеру (напр: <code>/unblock 1</code>)"
            )
            
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="delete_msg")]
            ])
            await self.show_or_edit_ui_panel(text="\n".join(lines), keyboard=inline_kb)

        @self.dp.callback_query(F.data == "confirm_reset_stats")
        async def process_confirm_reset_stats(callback_query: types.CallbackQuery):
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="delete_msg")],
                [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="do_reset_stats")]
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
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="delete_msg")],
                [InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="confirm_reset_stats")]
            ])
            try:
                await callback_query.message.edit_text(stats_msg, reply_markup=inline_kb, parse_mode="HTML")
            except Exception:
                pass
            await callback_query.answer("Статистика успешно сброшена!")

        @self.dp.callback_query(F.data == "cmd_buf_inline")
        async def process_cmd_buf_inline(callback_query: types.CallbackQuery):
            await callback_query.answer()
            buf_count = await self.storage.get_buffer_count()
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            if buf_count > 0:
                text = (
                    f"📥 <b>В буфере ожидают отправки:</b> {buf_count} сообщ.\n\n"
                    "Нажмите «🚀 Отправить сводку», чтобы получить их прямо сейчас, или дождитесь отправки по расписанию."
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Отправить сводку", callback_data="flush_now")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="delete_msg")]
                ])
            else:
                text = (
                    "📥 <b>Буфер пуст!</b> Новых сообщений для сводки пока нет.\n"
                    "Бот собирает входящие письма и сообщения в фоновом режиме."
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="delete_msg")]
                ])

            await self.show_or_edit_ui_panel(text=text, keyboard=kb)

        @self.dp.callback_query(F.data == "cmd_stats_inline")
        async def process_cmd_stats_inline(callback_query: types.CallbackQuery):
            await callback_query.answer()
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
                [InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="confirm_reset_stats")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="delete_msg")]
            ])
            await self.show_or_edit_ui_panel(text=stats_msg, keyboard=inline_kb)

        @self.dp.callback_query(F.data == "prompt_clear_chat")
        @self.dp.message(Command("clear"))
        @self.dp.message(F.text == "🧹 Очистить чат")
        async def cmd_clear_chat(event: Any):
            if isinstance(event, types.Message):
                try:
                    await event.delete()
                except Exception:
                    pass
            elif isinstance(event, types.CallbackQuery):
                await event.answer()

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            text = "⚠️ <b>Вы действительно хотите очистить последние сообщения в чате?</b>\n<i>(Сообщения останутся в базе данных)</i>"
            await self.show_or_edit_ui_panel(text=text, keyboard=kb_ui.get_clear_chat_prompt_keyboard(), force_new=False)

        # Handle inline "Close / Cancel" button click — returns UI to active status banner with ReplyKeyboard refreshed
        @self.dp.callback_query(F.data == "delete_msg")
        async def process_delete_msg(callback_query: types.CallbackQuery):
            await self.update_status_banner(callback_query.message.chat.id, force_new=True)
            await callback_query.answer()

        @self.dp.callback_query(F.data == "delete_this_message")
        async def process_delete_this_message(callback_query: types.CallbackQuery):
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            await callback_query.answer()

        # Handle inline confirmation of chat clearing
        @self.dp.callback_query(F.data == "confirm_clear_chat")
        async def process_confirm_clear_chat(callback_query: types.CallbackQuery):
            await callback_query.answer("Очистка чата...")
            
            # Reset UI msg id so fresh status banner is sent after purge
            self._last_ui_msg_id = None
            target_chat = callback_query.message.chat.id
            current_id = callback_query.message.message_id

            async def _do_delete_bg():
                for msg_id in range(current_id, current_id - 30, -1):
                    try:
                        await self.bot.delete_message(chat_id=target_chat, message_id=msg_id)
                    except Exception:
                        pass

                await self.update_status_banner(target_chat)

            asyncio.create_task(_do_delete_bg())

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
                    [InlineKeyboardButton(text="🗑️ Прочитано", callback_data="delete_this_message")]
                ])
                sent_msg = await self.bot.send_message(
                    chat_id=self.master_chat_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=inline_kb
                )
                # Notifications are NOT auto-deleted — they persist until user presses "🗑️ Прочитано"
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
                    [InlineKeyboardButton(text="🗑️ Прочитано", callback_data="delete_this_message")]
                ])
                # Split long messages if needed
                if len(full_digest) > 4000:
                    for chunk in [full_digest[i:i+4000] for i in range(0, len(full_digest), 4000)]:
                        await self.bot.send_message(
                            chat_id=self.master_chat_id, 
                            text=chunk, 
                            parse_mode="HTML",
                            reply_markup=inline_kb
                        )
                else:
                    await self.bot.send_message(
                        chat_id=self.master_chat_id,
                        text=full_digest,
                        parse_mode="HTML",
                        reply_markup=inline_kb
                    )
                    # Digests are NOT auto-deleted — they persist until user presses "🗑️ Прочитано"
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
            
            try:
                # Load settings asynchronously from DB
                saved_master_id = await self.storage.get_setting("master_chat_id")
                if saved_master_id and saved_master_id.isdigit() and saved_master_id != "0":
                    self.master_chat_id = int(saved_master_id)
                    logger.info(f"Loaded master_chat_id from DB: {self.master_chat_id}")

                self.delivery_mode = await self.storage.get_setting("delivery_mode", self.delivery_mode)
                self.digest_interval = int(await self.storage.get_setting("digest_interval_minutes", str(self.digest_interval)))
                self.auto_delete_delay_hours = int(await self.storage.get_setting("auto_delete_delay_hours", str(self.auto_delete_delay_hours)))
                self.night_mode_enabled = (await self.storage.get_setting("night_mode_enabled", "false")).lower() in ("true", "1", "yes")
                self.night_start_hour = int(await self.storage.get_setting("night_start_hour", str(self.night_start_hour)))
                self.night_end_hour = int(await self.storage.get_setting("night_end_hour", str(self.night_end_hour)))
                
                saved_ui_id = await self.storage.get_setting("last_ui_msg_id") or await self.storage.get_setting("last_status_msg_id")
                if saved_ui_id and saved_ui_id.isdigit():
                    self._last_ui_msg_id = int(saved_ui_id)
            except Exception as se:
                logger.error(f"Error loading settings from DB: {se}", exc_info=True)

            await self._register_bot_commands()
            if self.master_chat_id:
                asyncio.create_task(self.update_status_banner(self.master_chat_id, force_new=True))
            asyncio.create_task(self.start_digest_scheduler())
            asyncio.create_task(self.start_cleanup_scheduler())
            
            use_proxy_mode = True if config.TELEGRAM_PROXY else False
            while True:
                try:
                    me = await asyncio.wait_for(self.bot.get_me(), timeout=5.0)
                    logger.info(f"🤖 Connected to Telegram Bot: @{me.username} (ID: {me.id})")
                    await asyncio.wait_for(self.bot.delete_webhook(drop_pending_updates=True), timeout=5.0)
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
