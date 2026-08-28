import asyncio
import logging
import html
import io
from typing import Optional, Callable, Awaitable, Any, Dict
from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import TelegramObject
from config import config
from storage import Storage
import ui_keyboards as kb_ui

logger = logging.getLogger(__name__)

# Category Emojis
CATEGORY_EMOJIS = {
    "urgent": "🚨",
    "important": "⭐",
    "gov_debt": "⚖️",
    "gov_service": "🏛️",
    "general": "💬",
    "spam": "🚫",
    "news": "📰",
    "politics": "🏛️",
    "interesting": "💡",
    "bullshit": "🗑️",
    "media": "🎬"
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

        # Auto-capture master_chat_id if currently missing or 0
        if not master_id or str(master_id) in ("0", "None", ""):
            if user_id:
                logger.info(f"🔑 Auto-capturing master_chat_id={user_id} from Telegram Event [{event_name}]")
                self.master_bot.master_chat_id = user_id
                asyncio.create_task(self.master_bot.settings.update_master_chat_id(user_id))
                master_id = user_id

        # Security check: If master_chat_id is active, enforce strict lockdown
        if master_id and str(master_id) not in ("0", "None", ""):
            if user_id and str(user_id) != str(master_id):
                logger.warning(f"⛔ Blocking unauthorized Telegram interaction from user_id: {user_id} (Expected master_chat_id: {master_id})")
                return None  # Ignore unauthorized event completely

        # Clear FSM input states for all callback query button presses
        if isinstance(event, CallbackQuery):
            self.master_bot.clear_input_states()

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
        from settings_manager import SettingsManager
        self.settings = SettingsManager(self.storage)
        self.ai_engine = ai_engine
        self.simulate_callback = simulate_callback
        self.on_flush_raw_queue: Optional[Callable[..., Awaitable[None]]] = None
        self.delivery_mode = config.DELIVERY_MODE  # "instant" or "digest"
        self.digest_interval = config.DIGEST_INTERVAL_MINUTES
        self.auto_delete_delay_hours = config.AUTO_DELETE_DELAY_HOURS
        self.night_mode_enabled = config.NIGHT_MODE_ENABLED
        self.timezone_offset = 3  # Default UTC+3
        self.night_start_hour = config.NIGHT_START_HOUR
        self.night_end_hour = config.NIGHT_END_HOUR
        self._was_night_mode: bool = False
        self.current_menu_state = 'main'
        self._last_ui_msg_id = None
        self._last_clear_prompt_msg_id = None
        self._last_buffer_status_msg_id: int | None = None
        self._waiting_for_banword_scope: Optional[str] = None
        self._waiting_for_tg_channel: bool = False
        self._waiting_for_liked_topic: bool = False
        self._waiting_for_disliked_topic: bool = False
        self.dp: Optional[Dispatcher] = None
        self.bot: Optional[Bot] = None
        
        self.pending_ai_actions: Dict[str, Any] = {}
        self.user_agent = None
        if self.ai_engine and hasattr(self.ai_engine, 'client'):
            from user_agent import ConversationalAgent
            self.user_agent = ConversationalAgent(self.ai_engine, self.storage)

        if self.bot_token:
            self._init_bot_instance(use_proxy=True if config.TELEGRAM_PROXY else False)

    def set_ai_engine(self, ai_engine):
        self.ai_engine = ai_engine
        if self.ai_engine and hasattr(self.ai_engine, 'client'):
            from user_agent import ConversationalAgent
            self.user_agent = ConversationalAgent(self.ai_engine, self.storage)

    def set_flush_raw_queue_callback(self, callback: Callable[..., Awaitable[None]]):
        self.on_flush_raw_queue = callback

    def clear_input_states(self):
        """Clears all interactive FSM states."""
        self._waiting_for_banword_scope = None
        self._waiting_for_tg_channel = False
        self._waiting_for_liked_topic = False
        self._waiting_for_disliked_topic = False

    def is_night_time(self) -> bool:
        """Returns True if Night Mode is enabled and current local time (user timezone) falls in quiet hours."""
        if not self.night_mode_enabled:
            return False
        from datetime import datetime, timedelta
        now_utc = datetime.utcnow()
        now_local = now_utc + timedelta(hours=self.timezone_offset)
        now_hour = now_local.hour
        if self.night_start_hour > self.night_end_hour:
            return now_hour >= self.night_start_hour or now_hour < self.night_end_hour
        elif self.night_start_hour < self.night_end_hour:
            return self.night_start_hour <= now_hour < self.night_end_hour
        else:
            return False

    async def check_night_mode_transition(self):
        """Checks for transition from Night Mode to Day Mode and triggers morning digest."""
        is_night = self.is_night_time()
        if self._was_night_mode and not is_night:
            logger.info("🌅 Morning wake-up! Night mode ended. Flushing AI queue and sending Morning Digest...")
            if self.on_flush_raw_queue:
                try:
                    await self.on_flush_raw_queue(force=True)
                except Exception as e:
                    logger.error(f"Error flushing raw queue on morning wake-up: {e}")
            try:
                await self.flush_buffer_now()
            except Exception as e:
                logger.error(f"Error sending Morning Digest: {e}")

        self._was_night_mode = is_night

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
        return kb_ui.get_main_reply_keyboard(buffer_count)

    async def _register_bot_commands(self):
        """Registers blue '/' commands menu in Telegram app UI."""
        from aiogram.types import BotCommand
        commands = [
            BotCommand(command="start", description="Главное меню и статус"),
            BotCommand(command="help", description="Справка по командам и работе"),
            BotCommand(command="settings", description="Настройки (интервал сводки, режим, автоудаление)"),
            BotCommand(command="flush", description="Выгрузить накопившийся буфер прямо сейчас"),
            BotCommand(command="stats", description="Посмотреть статистику сообщений"),
            BotCommand(command="blacklist", description="Управление Чёрным списком спама"),
            BotCommand(command="clear", description="Очистить сообщения в чате"),
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
            log_lines = []
            for line in recent:
                if len(line) > 300:
                    line = line[:300] + "..."
                log_lines.append(f"• <code>{html.escape(line)}</code>")
        
        import re
        raw_proxy = config.TELEGRAM_PROXY if config.TELEGRAM_PROXY else "Прямое (Direct 🟢)"
        proxy_info = re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', raw_proxy)
        
        text = (
            "🛠️ <b>Диагностика системы и Живой Лог</b>\n\n"
            f"🌐 <b>Подключение Telegram:</b> {proxy_info}\n"
            f"👤 <b>Master Chat ID:</b> <code>{self.master_chat_id}</code>\n"
            f"⚡ <b>Режим:</b> {self.delivery_mode.upper()} ({self.digest_interval}м)\n"
            f"🌍 <b>Часовой пояс:</b> UTC{'+' if self.timezone_offset >= 0 else ''}{self.timezone_offset}\n"
            f"🌙 <b>Ночной режим:</b> {'Вкл 🟢' if self.night_mode_enabled else 'Выкл ❌'}\n\n"
            "📜 <b>Последние 10 системных событий:</b>\n"
            + "\n".join(log_lines)
        )
        
        if len(text) > 4000:
            text = text[:4000] + "...\n[Лог обрезан из-за лимитов Telegram]"
        
        return text, kb_ui.get_logs_keyboard()

    async def _get_formatted_stats_text(self, title_suffix: str = "") -> str:
        stats_data = await self.storage.get_stats()
        cats = stats_data.get("categories", {})
        channels = stats_data.get("channels", {})
        buf_count = await self.storage.get_buffer_count()

        lines = [
            f"📊 <b>Статистика{title_suffix}:</b>\n",
            "<b>Категории:</b>",
            f"🔥 <b>Срочные:</b> {cats.get('urgent', 0)}",
            f"❗️ <b>Важные:</b> {cats.get('important', 0)}",
            f"⚖️ <b>Задолженности/Штрафы:</b> {cats.get('gov_debt', 0)}",
            f"🏛️ <b>Госуслуги:</b> {cats.get('gov_service', 0)}",
            f"📰 <b>Новости:</b> {cats.get('news', 0)}",
            f"🗣️ <b>Политика:</b> {cats.get('politics', 0)}",
            f"💡 <b>Интересное:</b> {cats.get('interesting', 0)}",
            f"🎬 <b>Медиа:</b> {cats.get('media', 0)}",
            f"💬 <b>Обычные:</b> {cats.get('general', 0)}",
            f"🗑 <b>Мусорные (bullshit):</b> {cats.get('bullshit', 0)}",
            f"🛑 <b>Спам:</b> {cats.get('spam', 0)}\n",
            "<b>Источники:</b>"
        ]

        if channels:
            for ch_name, count in channels.items():
                ch_lower = ch_name.lower()
                if "mail" in ch_lower or "email" in ch_lower:
                    icon = "✉️"
                elif "vk" in ch_lower or "контакт" in ch_lower:
                    icon = "💬"
                elif "авито" in ch_lower or "avito" in ch_lower:
                    icon = "🟡"
                elif "insta" in ch_lower or "инста" in ch_lower:
                    icon = "📸"
                elif "tg" in ch_lower or "telegram" in ch_lower:
                    icon = "✈️"
                elif "voice" in ch_lower or "голос" in ch_lower:
                    icon = "🎙️"
                else:
                    icon = "📲"
                lines.append(f"{icon} <b>{ch_name}:</b> {count}")
        else:
            lines.append("<i>Источники пока не зарегистрированы</i>")

        lines.extend([
            f"\n📥 <b>Ожидают:</b> {buf_count}"
        ])

        return "\n".join(lines)

    async def _show_tg_channels_page(self, page: int = 1):
        chans = await self.storage.get_tg_channels()
        per_page = 9
        total_pages = max(1, (len(chans) + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * per_page
        page_chans = chans[start_idx:start_idx + per_page]

        lines = [f"✈️ <b>Отслеживаемые ТГ-каналы новостей</b>\n<i>(Стр. {page}/{total_pages}, всего: {len(chans)})</i>\n"]
        if not chans:
            lines.append("<i>Список отслеживаемых каналов пуст.</i>\n\n📌 <i>Нажмите ➕ Добавить канал ниже.</i>")
        else:
            for idx_in_page, c in enumerate(page_chans, start=start_idx + 1):
                lines.append(f"{idx_in_page}. <code>@{html.escape(c['username'])}</code>")
            lines.append("\n📌 <i>Нажмите ❌ #№ ниже для удаления из отслеживания:</i>")

        kb = kb_ui.get_tg_channels_list_keyboard(page_chans, page, total_pages, start_idx)
        await self.show_or_edit_ui_panel(text="\n".join(lines), keyboard=kb, force_new=False)

    async def _show_topics_main_page(self):
        liked_topics = await self.storage.get_news_topics(preference="liked")
        disliked_topics = await self.storage.get_news_topics(preference="disliked")
        
        text = (
            "📰 <b>Темы новостей</b>\n\n"
            "Укажите, какие темы вам нравятся (бот будет собирать их в интересное), "
            "а какие вам неприятны или неинтересны (бот будет их игнорировать как спам/bullshit)."
        )
        kb = kb_ui.get_news_topics_main_keyboard(len(liked_topics), len(disliked_topics))
        await self.show_or_edit_ui_panel(text=text, keyboard=kb, force_new=False)

    async def _show_topics_list_page(self, preference: str, page: int):
        topics = await self.storage.get_news_topics(preference=preference)
        per_page = 9
        total_pages = max(1, (len(topics) + per_page - 1) // per_page)
        
        start_idx = (page - 1) * per_page
        page_topics = topics[start_idx : start_idx + per_page]
        
        icon = "💚" if preference == "liked" else "🛑"
        pref_name = "Желаемые" if preference == "liked" else "Запретные"
        
        lines = [f"{icon} <b>{pref_name} темы новостей</b>\n<i>(Стр. {page}/{total_pages}, всего: {len(topics)})</i>\n"]
        if not topics:
            lines.append(f"<i>Список пуст.</i>")
        else:
            for idx_in_page, t in enumerate(page_topics, start=start_idx + 1):
                lines.append(f"{idx_in_page}. <code>{html.escape(t['topic'])}</code>")
            lines.append("\n📌 <i>Нажмите ❌ #№ ниже для удаления:</i>")

        kb = kb_ui.get_news_topics_list_keyboard(page_topics, page, total_pages, preference, start_idx)
        await self.show_or_edit_ui_panel(text="\n".join(lines), keyboard=kb, force_new=False)

    async def _get_settings_text_and_keyboard(self):
        mode_label = "⚡ Сразу" if self.delivery_mode == "instant" else "📥 Сводка"
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            f"Режим доставки: <b>{mode_label}</b>\n\n"
            "Выберите подраздел настроек ниже:"
        )
        return text, kb_ui.get_settings_keyboard(self.delivery_mode)

    async def _get_time_settings_text_and_keyboard(self):
        autodelete_label = f"{self.auto_delete_delay_hours} ч" if self.auto_delete_delay_hours > 0 else "Выключено ❌"
        text = (
            "⚙️ <b>Настройки Времени и Таймеров</b>\n\n"
            f"▪️ <b>Интервал сводки:</b> {self.digest_interval} мин\n"
            f"▪️ <b>Часовой пояс:</b> UTC{'+' if self.timezone_offset >= 0 else ''}{self.timezone_offset}\n"
            f"▪️ <b>Автоудаление логов:</b> {autodelete_label}\n\n"
            "<i>Выберите параметр для изменения:</i>"
        )
        return text, kb_ui.get_time_settings_keyboard()

    async def _get_timezone_settings_text_and_keyboard(self):
        from datetime import datetime, timedelta
        now_utc = datetime.utcnow()
        now_local = now_utc + timedelta(hours=self.timezone_offset)
        local_time_str = now_local.strftime("%H:%M")

        text = (
            "🌍 <b>Настройка часового пояса</b>\n\n"
            f"Текущий пояс: <b>UTC{'+' if self.timezone_offset >= 0 else ''}{self.timezone_offset}</b>\n"
            f"Текущее время: <b>{local_time_str}</b>\n\n"
            "<i>Это нужно для правильной работы расписания сводки и ночного режима.</i>"
        )
        return text, kb_ui.get_timezone_keyboard(self.timezone_offset)

    async def _get_night_settings_text_and_keyboard(self):
        night_status = "🟢 Включен" if self.night_mode_enabled else "❌ Выключен"
        text = (
            "🌙 <b>Ночной режим</b>\n\n"
            f"▪️ Статус: <b>{night_status}</b>\n"
            f"▪️ Часы тишины: <b>{self.night_start_hour:02d}:00 - {self.night_end_hour:02d}:00</b>\n\n"
            "В ночные часы уведомления отключаются, новые сообщения накапливаются в буфере."
        )
        return text, kb_ui.get_night_settings_keyboard(self.night_mode_enabled)

    async def _get_ai_settings_text_and_keyboard(self):
        chat_enabled = await self.settings.get_ai_text_chat_enabled()
        sugg_enabled = await self.settings.get_ai_suggestions_enabled()
        text = (
            "🧠 <b>Настройки ИИ</b>\n\n"
            "<b>Умный чат</b>: Позволяет боту отвечать на ваши текстовые сообщения в Главном меню.\n"
            "<b>Умные подсказки</b>: ИИ помогает вам при вводе настроек (авто-исправление опечаток в банвордах, каналах и т.д.).\n\n"
            "<i>Выберите нужные опции ниже:</i>"
        )
        return text, kb_ui.get_ai_settings_keyboard(chat_enabled, sugg_enabled)

    async def _get_ai_filters_text_and_keyboard(self):
        filters = await self.settings.get_ai_category_filters()
        text = (
            "🛡️ <b>Управление фильтрами ИИ</b>\n\n"
            "Здесь вы можете выбрать, какие категории сообщений ИИ будет фильтровать (прятать) в фоне.\n\n"
            "🟢 — Пропускать (доставлять в сводку)\n"
            "🔴 — Фильтровать (удалять как спам)\n\n"
            "<i>Нажмите на категорию, чтобы переключить ее статус:</i>"
        )
        return text, kb_ui.get_ai_filters_list_keyboard(filters)

    async def show_or_edit_ui_panel(self, text: str, keyboard: Any = None, parse_mode: str = "HTML", force_new: bool = False, chat_id: Optional[int] = None):
        """Displays or smoothly edits the single active UI window in-place."""
        target_chat = chat_id or self.master_chat_id
        if not target_chat or str(target_chat) in ("0", "None", "") or not self.bot:
            logger.warning(f"show_or_edit_ui_panel skipped: target_chat={target_chat}, bot={self.bot}")
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
            await self.settings.update_last_ui_msg_id(sent_msg.message_id)
        except Exception as e:
            logger.error(f"Error updating single UI panel: {e}")

    async def update_status_banner(self, chat_id: Optional[int] = None, force_new: bool = False):
        """Creates or updates the single active status banner in-place."""
        target_chat = chat_id or self.master_chat_id
        if not target_chat or str(target_chat) in ("0", "None", ""):
            return

        filters = await self.settings.get_ai_category_filters()
        disabled_cats = [cat for cat, enabled in filters.items() if not enabled]
        buf_count = await self.storage.get_buffer_count(disabled_categories=disabled_cats)
        text = "<b>Message Aggregator</b> — <i>Активен 🟢</i>"
        reply_kb = kb_ui.get_main_reply_keyboard(buf_count)
        await self.show_or_edit_ui_panel(text=text, keyboard=reply_kb, force_new=force_new)

    def _setup_handlers(self):
        from bot_handlers.all_handlers import setup_all_handlers
        setup_all_handlers(self)


    async def handle_incoming_analyzed_message(
        self, channel: str, sender: str, text: str, category: str, summary: str, action_required: bool, suggested_reply: Optional[str] = None
    ) -> bool:
        """
        Decides whether to send immediately or store in buffer based on category and delivery mode.
        Returns True if delivered immediately, False if buffered or muted/blocked.
        """
        filters = await self.settings.get_ai_category_filters()
        if not filters.get(category, True) or category == "spam":
            logger.info(f"Muting/blocking {category} message from [{channel}] {sender}.")
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
            f"📝 <b>Выжимка:</b>\n{html.escape(summary)}{action_part}{reply_part}"
        )

        logger.info(f"Sending Instant Notification [{category}] from {sender}")

        if self.bot and self.master_chat_id:
            try:
                inline_kb = kb_ui.get_read_notification_keyboard()
                sent_msg = await self.bot.send_message(
                    chat_id=self.master_chat_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=inline_kb
                )
                if self.auto_delete_delay_hours > 0 and sent_msg:
                    await self.storage.save_sent_notification(
                        chat_id=self.master_chat_id,
                        message_id=sent_msg.message_id,
                        delay_seconds=self.auto_delete_delay_hours * 3600
                    )
            except Exception as e:
                logger.error(f"Error sending Telegram notification: {e}")

    async def flush_buffer_now(self) -> int:
        """Sends all buffered messages as a formatted digest."""
        # 1. Flush any pending raw messages in queue to AI/DB first
        if self.on_flush_raw_queue:
            try:
                await self.on_flush_raw_queue(force=True)
            except Exception as fe:
                logger.error(f"Error flushing raw queue prior to digest: {fe}")

        filters = await self.settings.get_ai_category_filters()
        disabled_cats = [cat for cat, enabled in filters.items() if not enabled]
        messages = await self.storage.get_buffered_messages(mark_as_delivered=True, disabled_categories=disabled_cats)
        if not messages:
            return 0

        digest_parts = []
        regular_messages = []

        if self.bot and self.master_chat_id:
            for m in messages:
                regular_messages.append(m)
        else:
            regular_messages = messages

        if not regular_messages:
            return len(messages)

        digest_parts.append("📬 <b>СВОДКА СООБЩЕНИЙ</b>\n")
        
        groups: dict[str, list] = {
            "important": [],
            "news": [],
            "general": []
        }
        
        for m in regular_messages:
            cat = m['category']
            # Все новости из Telegram принудительно идут в блок новостей, даже если ИИ пометил их как 'urgent'
            if m['msg_uid'].startswith("tg_news_"):
                groups['news'].append(m)
            elif cat in ['urgent', 'important', 'gov', 'gov_debt', 'gov_service']:
                groups['important'].append(m)
            elif cat in ['news', 'politics', 'interesting', 'bullshit', 'media']:
                groups['news'].append(m)
            else:
                groups['general'].append(m)
                
        def format_msg(m):
            sender = html.escape(m['sender'])
            
            # Create inline link for TG news to save space
            if m['msg_uid'].startswith("tg_news_"):
                rest = m['msg_uid'][len("tg_news_"):]
                if "_" in rest:
                    tg_channel, msg_id = rest.rsplit('_', 1)
                    # For news, the "sender" is often already an @handle. Just link it.
                    sender_display = f"<a href=\"https://t.me/{tg_channel}/{msg_id}\">{sender}</a>"
                else:
                    sender_display = f"<b>{sender}</b>"
            else:
                sender_display = f"<b>{sender}</b> [{html.escape(m['channel'])}]"
                
            return f"▫️ {sender_display}: {html.escape(m['summary'])}"
            
        if groups['important']:
            digest_parts.append("\n🔴 <b>ВАЖНОЕ</b>")
            for m in groups['important']:
                digest_parts.append(format_msg(m))
                
        if groups['general']:
            digest_parts.append("\n✉️ <b>ЛИЧНЫЕ СООБЩЕНИЯ И УВЕДОМЛЕНИЯ</b>")
            for m in groups['general']:
                digest_parts.append(format_msg(m))
                
        if groups['news']:
            digest_parts.append("\n📰 <b>НОВОСТИ И ПОДПИСКИ</b>")
            for m in groups['news']:
                digest_parts.append(format_msg(m))

        if self.bot and self.master_chat_id:
            try:
                inline_kb = kb_ui.get_read_notification_keyboard()
                # Отправляем сводку, разбивая по сообщениям, чтобы не разорвать HTML-теги
                current_chunk = ""
                # Since we joined everything into full_digest, we need to split it by newlines or keep track.
                # Actually, digest_parts already has the blocks, we can just build chunks from digest_parts!
                
                for part in digest_parts:
                    if len(current_chunk) + len(part) + 5 > 4000:
                        if current_chunk:
                            sent_msg = await self.bot.send_message(
                                chat_id=self.master_chat_id, 
                                text=current_chunk, 
                                parse_mode="HTML",
                                reply_markup=inline_kb
                            )
                            if self.auto_delete_delay_hours > 0 and sent_msg:
                                await self.storage.save_sent_notification(
                                    chat_id=self.master_chat_id,
                                    message_id=sent_msg.message_id,
                                    delay_seconds=self.auto_delete_delay_hours * 3600
                                )
                        current_chunk = part
                    else:
                        if current_chunk:
                            current_chunk += "\n" + part
                        else:
                            current_chunk = part
                
                # Отправляем последний кусочек
                if current_chunk:
                    sent_msg = await self.bot.send_message(
                        chat_id=self.master_chat_id,
                        text=current_chunk,
                        parse_mode="HTML",
                        reply_markup=inline_kb
                    )
                    if self.auto_delete_delay_hours > 0 and sent_msg:
                        await self.storage.save_sent_notification(
                            chat_id=self.master_chat_id,
                            message_id=sent_msg.message_id,
                            delay_seconds=self.auto_delete_delay_hours * 3600
                        )
            except Exception as e:
                logger.error(f"Error sending digest: {e}")

        # Clean up the buffer status message if it exists
        if self._last_buffer_status_msg_id:
            try:
                await self.bot.delete_message(chat_id=self.master_chat_id, message_id=self._last_buffer_status_msg_id)
            except Exception:
                pass
            self._last_buffer_status_msg_id: int | None = None

        return len(messages)

    async def start_night_mode_scheduler(self):
        """Background task checking every 30s for Night Mode -> Day Mode transition to send Morning Digest."""
        logger.info("Night Mode transition scheduler running...")
        self._was_night_mode = self.is_night_time()
        while True:
            await asyncio.sleep(30)
            try:
                await self.check_night_mode_transition()
            except Exception as e:
                logger.error(f"Error in night mode scheduler: {e}")

    async def start_digest_scheduler(self):
        """Background task for sending scheduled digests aligned to wall-clock time."""
        from datetime import datetime, timedelta
        logger.info(f"Digest scheduler running (interval: {self.digest_interval} min, TZ: UTC{'+' if self.timezone_offset >= 0 else ''}{self.timezone_offset})...")
        while True:
            now_utc = datetime.utcnow()
            now_local = now_utc + timedelta(hours=self.timezone_offset)
            minutes_since_midnight = now_local.hour * 60 + now_local.minute
            interval = max(1, self.digest_interval)
            
            # Находим следующий кратный интервал в минутах от начала суток
            next_multiple = ((minutes_since_midnight // interval) + 1) * interval
            
            # Вычисляем сколько минут и секунд спать
            minutes_to_sleep = next_multiple - minutes_since_midnight
            seconds_to_sleep = (minutes_to_sleep * 60) - now_local.second
            
            # Если до срабатывания меньше 5 секунд, ждём следующий цикл, чтобы не было двойных срабатываний
            if seconds_to_sleep < 5:
                seconds_to_sleep += interval * 60
                
            logger.info(f"Digest scheduler: Next digest scheduled in {seconds_to_sleep} seconds (aligned to clock time).")
            await asyncio.sleep(seconds_to_sleep)
            
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
                if expired:
                    logger.info(f"🗑️ Found {len(expired)} expired notification(s) to auto-delete.")
                for item in expired:
                    try:
                        await self.bot.delete_message(chat_id=item['chat_id'], message_id=item['message_id'])
                        logger.info(f"🗑️ Auto-deleted expired message {item['message_id']} in chat {item['chat_id']}.")
                    except Exception as de:
                        err_str = str(de).lower()
                        if "not found" in err_str or "deleted" in err_str:
                            logger.debug(f"Expired message {item['message_id']} in chat {item['chat_id']} was already deleted by user.")
                        else:
                            logger.warning(f"Failed to auto-delete message {item['message_id']} in chat {item['chat_id']}: {de}")
                    # Always delete from DB so we don't retry endlessly
                    await self.storage.delete_sent_notification(item['id'])

                # 2. Database auto-purge for delivered/spam messages (runs once per hour)
                now_ts = asyncio.get_running_loop().time()
                if now_ts - last_db_purge_time >= 3600:
                    from settings_manager import SettingsManager
                    settings = SettingsManager(self.storage)
                    purge_days = await settings.get_db_purge_days()
                    
                    purged_count = await self.storage.purge_old_messages(days=purge_days)
                    if purged_count > 0:
                        logger.info(f"Auto-purged {purged_count} old messages older than {purge_days} days.")
                        
                    last_db_purge_time = now_ts

            except Exception as e:
                logger.error(f"Error in cleanup scheduler: {e}")

    async def start_polling(self):
        if self.bot and self.dp:
            logger.info("Starting Telegram Bot Polling loop...")
            
            try:
                # Load settings asynchronously from DB
                self.master_chat_id = await self.settings.get_master_chat_id()
                self.delivery_mode = await self.settings.get_delivery_mode()
                self.digest_interval = await self.settings.get_digest_interval_minutes()
                self.auto_delete_delay_hours = await self.settings.get_auto_delete_delay_hours()
                self.timezone_offset = await self.settings.get_timezone_offset()
                logger.info(f"Loaded config from DB: Delivery={self.delivery_mode}, Interval={self.digest_interval}m, TZ=UTC+{self.timezone_offset}, AutoDelete={self.auto_delete_delay_hours}h")
                
                self.night_mode_enabled = await self.settings.get_night_mode_enabled()
                self.night_start_hour = await self.settings.get_night_start_hour()
                self.night_end_hour = await self.settings.get_night_end_hour()
                self._was_night_mode = self.is_night_time()
                
                self._last_ui_msg_id = await self.settings.get_last_ui_msg_id()
            except Exception as se:
                logger.error(f"Error loading settings from DB: {se}", exc_info=True)

            await self._register_bot_commands()
            if self.master_chat_id:
                asyncio.create_task(self.update_status_banner(self.master_chat_id, force_new=True))
            asyncio.create_task(self.start_digest_scheduler())
            asyncio.create_task(self.start_cleanup_scheduler())
            asyncio.create_task(self.start_night_mode_scheduler())
            
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
