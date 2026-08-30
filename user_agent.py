import logging
import asyncio
from typing import Dict, Any
from google.genai import types
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

# Tool definitions for schema generation
def web_search(query: str) -> str:
    """Searches the internet for current news, facts, articles, weather, stock prices, or events. Parameter 'query' is the search query string."""
    return ''

async def perform_web_search(query: str, max_results: int = 5) -> str:
    """Executes DuckDuckGo search asynchronously using a thread pool and formats results into text."""
    if not query or not str(query).strip():
        return "Ошибка: Пустой поисковый запрос."

    def _sync_search():
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(str(query).strip(), max_results=max_results))
                return results
        except Exception as e:
            logger.error(f"DuckDuckGo search error for query '{query}': {e}", exc_info=True)
            return e

    try:
        results = await asyncio.to_thread(_sync_search)
        if isinstance(results, Exception):
            return f"⚠️ Не удалось выполнить поиск в интернете ({results}). Попробуйте позже."
        if not results:
            return f"ℹ️ По запросу «{query}» ничего не найдено в интернете."

        formatted_lines = [f"🔎 Результаты веб-поиска по запросу «{query}»:\n"]
        for idx, item in enumerate(results, 1):
            title = item.get("title", "Без названия")
            snippet = item.get("body", "")
            href = item.get("href", "")
            formatted_lines.append(f"{idx}. [{title}]({href})\n{snippet}\n")

        return "\n".join(formatted_lines)
    except Exception as e:
        logger.error(f"Async web search error: {e}", exc_info=True)
        return f"⚠️ Ошибка при выполнении веб-поиска: {e}"

def list_tg_channels() -> str:
    """Returns the list of all Telegram channels currently in the bot's watchlist."""
    return ''

def list_banwords() -> str:
    """Returns the list of all currently configured banwords categorized by scope (global, email, vk)."""
    return ''

def list_news_topics() -> str:
    """Returns the list of configured news topics separated by preference (liked or disliked)."""
    return ''

def get_settings_summary() -> str:
    """Returns a complete summary of all user settings (delivery mode, interval, timezone, night mode, AI features)."""
    return ''

def add_banword(word: str, scope: str = "global") -> str:
    """Adds a new banword to filter out unwanted messages. Scope can be 'global', 'email' or 'vk'."""
    return ''

def remove_banword(word: str) -> str:
    """Removes a banword from the blacklist."""
    return ''

def add_news_topic(topic: str, preference: str) -> str:
    """Adds a news topic. Preference must be either 'liked' (interesting) or 'disliked' (ignore)."""
    return ''

def remove_news_topic(topic: str, preference: str) -> str:
    """Removes a news topic. Preference must be either 'liked' or 'disliked'."""
    return ''

def add_tg_channel(channel_username: str) -> str:
    """Adds a Telegram channel to the bot's watchlist. Make sure channel_username is a valid @username or t.me/ link."""
    return ''

def remove_tg_channel(channel_username: str) -> str:
    """Removes a Telegram channel from the bot's watchlist."""
    return ''

def get_bot_stats() -> str:
    """Returns the current message statistics."""
    return ''

def set_timezone(offset_hours: int) -> str:
    """Sets the bot's timezone offset in hours from UTC (e.g., 3 for Moscow, 5 for Yekaterinburg)."""
    return ''

def set_digest_interval(minutes: int) -> str:
    """Sets the interval in minutes for sending automatic news digests (e.g., 60 for 1 hour)."""
    return ''

def set_delivery_mode(mode: str) -> str:
    """Sets the message delivery mode. Parameter 'mode' must be either 'instant' (deliver immediately) or 'digest' (collect into periodic summary)."""
    return ''

def toggle_night_mode(enabled: bool) -> str:
    """Enables or disables Night Mode (Quiet Hours). Set enabled=True to activate night mode, or enabled=False to deactivate it."""
    return ''

def set_night_hours(start_hour: int, end_hour: int) -> str:
    """Sets quiet hours interval for Night Mode (e.g. start_hour=23, end_hour=7)."""
    return ''

def toggle_category_filter(category: str, enabled: bool) -> str:
    """Enables or disables message filtering for a specific AI category. Available categories: spam, urgent, important, gov_debt, gov_service, news, media, general, politics, interesting, bullshit."""
    return ''

def clear_chat() -> str:
    """Clears the entire chat history and removes all stored messages from the bot's database. Requires confirmation."""
    return ''

class ConversationalAgent:
    def __init__(self, ai_engine: Any, storage):
        self.ai_engine = ai_engine
        self.storage = storage
        self.model_name = "gemini-3.5-flash-lite"
        
        from config.prompts import CONVERSATIONAL_SYSTEM_INSTRUCTION
        self.system_instruction = CONVERSATIONAL_SYSTEM_INSTRUCTION

    def _get_tools(self):
        return [
            web_search,
            list_tg_channels,
            list_banwords,
            list_news_topics,
            get_settings_summary,
            add_banword,
            remove_banword,
            add_news_topic, 
            remove_news_topic, 
            add_tg_channel,
            remove_tg_channel,
            get_bot_stats,
            set_timezone,
            set_digest_interval,
            set_delivery_mode,
            toggle_night_mode,
            set_night_hours,
            toggle_category_filter,
            clear_chat
        ]

    async def _list_tg_channels(self) -> str:
        chans = await self.storage.get_tg_channels()
        if not chans:
            return "📢 У вас пока нет добавленных Telegram-каналов в отслеживании."
        lines = ["📢 **Ваши Telegram-каналы в отслеживании:**\n"]
        for ch in chans:
            uname = ch.get("username", "") if isinstance(ch, dict) else getattr(ch, "username", str(ch))
            lines.append(f"• @{uname.lstrip('@')}")
        return "\n".join(lines)

    async def _list_banwords(self) -> str:
        bws = await self.storage.get_banwords()
        if not bws:
            return "🚫 У вас пока нет добавленных банвордов."
        lines = ["🚫 **Ваши текущие банворды:**\n"]
        scopes = {"global": "Общие", "email": "Mail.ru", "vk": "ВКонтакте"}
        grouped = {}
        for b in bws:
            scope = b.get("scope", "global") if isinstance(b, dict) else getattr(b, "scope", "global")
            word = b.get("word", "") if isinstance(b, dict) else getattr(b, "word", str(b))
            grouped.setdefault(scope, []).append(word)
        for s_key, s_name in scopes.items():
            words = grouped.get(s_key, [])
            if words:
                words_formatted = ", ".join([f"`{w}`" for w in words])
                lines.append(f"• **{s_name}**: {words_formatted}")
        return "\n".join(lines)

    async def _list_news_topics(self) -> str:
        liked = await self.storage.get_news_topics(preference="liked")
        disliked = await self.storage.get_news_topics(preference="disliked")
        if not liked and not disliked:
            return "📰 У вас пока нет настроенных тем новостей."
        lines = ["📰 **Ваши темы новостей:**\n"]
        if liked:
            liked_names = [t.get("topic", "") if isinstance(t, dict) else getattr(t, "topic", str(t)) for t in liked]
            lines.append("💚 **Желаемые темы:**\n" + "\n".join([f"• {t}" for t in liked_names]) + "\n")
        if disliked:
            disliked_names = [t.get("topic", "") if isinstance(t, dict) else getattr(t, "topic", str(t)) for t in disliked]
            lines.append("🛑 **Запретные темы:**\n" + "\n".join([f"• {t}" for t in disliked_names]))
        return "\n".join(lines).strip()

    async def _get_settings_summary(self) -> str:
        settings = SettingsManager(self.storage)
        delivery_mode = await settings.get_delivery_mode()
        digest_interval = await settings.get_digest_interval_minutes()
        tz_offset = await settings.get_timezone_offset()
        night_enabled = await settings.get_night_mode_enabled()
        night_start = await settings.get_night_start_hour()
        night_end = await settings.get_night_end_hour()
        ai_chat = await settings.get_ai_text_chat_enabled()
        ai_sugg = await settings.get_ai_suggestions_enabled()
        filters = await settings.get_ai_category_filters()
        active_filters = [k for k, v in filters.items() if not v]
        return (
            f"⚙️ **Ваши текущие настройки бота:**\n\n"
            f"• **Режим доставки**: {'Мгновенно' if delivery_mode == 'instant' else 'Периодическая сводка'}\n"
            f"• **Интервал сводки**: {digest_interval} мин.\n"
            f"• **Часовой пояс**: UTC{'+' if tz_offset >= 0 else ''}{tz_offset}\n"
            f"• **Ночной режим**: {'Включен' if night_enabled else 'Выключен'} ({night_start:02d}:00 - {night_end:02d}:00)\n"
            f"• **Умный чат с ИИ**: {'Включен' if ai_chat else 'Выключен'}\n"
            f"• **Умные подсказки**: {'Включены' if ai_sugg else 'Выключены'}\n"
            f"• **Скрываемые категории ИИ**: {', '.join(active_filters) if active_filters else 'Нет'}"
        )

    async def process_message(self, text: str) -> Dict[str, Any]:
        """
        Processes a user message.
        Returns a dict:
        {
            "text": "Response text",
            "pending_action": {"action": "add_banword", "args": {"word": "..."}} | None
        }
        """
        if not getattr(self.ai_engine, 'client', None):
            return {"text": "Ошибка: API ключ AI не настроен. Агент недоступен.", "pending_action": None}

        # Load history
        raw_history = await self.storage.get_ai_chat_history()
        contents = []
        for msg in raw_history:
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part.from_text(text=msg["content"])]
                )
            )

        # Inject current time context
        try:
            settings = SettingsManager(self.storage)
            tz_offset = await settings.get_timezone_offset()
            from datetime import datetime, timezone, timedelta
            current_time = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=tz_offset)
            time_context = f"[Системное время (с учетом часового пояса пользователя): {current_time.strftime('%Y-%m-%d %H:%M:%S')}]\n"
            text_with_context = time_context + text
        except Exception as e:
            logger.error(f"Failed to inject time context: {e}")
            text_with_context = text

        # Add user's new message
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=text_with_context)]
            )
        )

        try:
            config = types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                tools=self._get_tools(),
                temperature=0.7,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
            
            response = await self.ai_engine.generate_content_with_retry(
                contents=contents,
                config=config
            )

            # Check for function calls
            if response.function_calls:
                fc = response.function_calls[0]
                action_name = fc.name
                args = fc.args or {}
                logger.info(f"🤖 AI Conversational Agent invoked tool: {action_name} with args: {args}")

                # Format a user-friendly response
                if action_name == "web_search":
                    search_query = args.get("query", text)
                    logger.info(f"🌐 Executing DuckDuckGo web search for query: '{search_query}'")
                    search_results = await perform_web_search(search_query)

                    # Feed search results back into Gemini conversation context to synthesize full answer
                    contents.append(
                        types.Content(
                            role="model",
                            parts=[types.Part.from_function_call(name="web_search", args={"query": search_query})]
                        )
                    )
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=f"[Результаты веб-поиска по запросу '{search_query}']:\n{search_results}\n\nПожалуйста, сформируй подробный и понятный ответ пользователю на основе этих результатов поиска. Обязательно укажи ключевые факты и ссылки на источники.")]
                        )
                    )
                    try:
                        second_response = await self.ai_engine.generate_content_with_retry(
                            contents=contents,
                            config=types.GenerateContentConfig(
                                system_instruction=self.system_instruction,
                                temperature=0.7
                            )
                        )
                        reply_text = second_response.text if second_response and second_response.text else search_results
                    except Exception as e:
                        logger.error(f"Error generating search summary response: {e}")
                        reply_text = search_results

                    await self.storage.add_ai_chat_message("user", text)
                    await self.storage.add_ai_chat_message("model", reply_text)
                    return {"text": reply_text, "pending_action": None}
                elif action_name in ("list_tg_channels", "list_banwords", "list_news_topics", "get_settings_summary"):
                    logger.info(f"📊 Executing list tool: '{action_name}'")
                    if action_name == "list_tg_channels":
                        tool_res = await self._list_tg_channels()
                    elif action_name == "list_banwords":
                        tool_res = await self._list_banwords()
                    elif action_name == "list_news_topics":
                        tool_res = await self._list_news_topics()
                    else:
                        tool_res = await self._get_settings_summary()

                    contents.append(
                        types.Content(
                            role="model",
                            parts=[types.Part.from_function_call(name=action_name, args={})]
                        )
                    )
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=f"[Результат выполнения запроса '{action_name}']:\n{tool_res}\n\nСформируй понятный и красивый ответ пользователю на основе этих данных.")]
                        )
                    )
                    try:
                        second_response = await self.ai_engine.generate_content_with_retry(
                            contents=contents,
                            config=types.GenerateContentConfig(
                                system_instruction=self.system_instruction,
                                temperature=0.7
                            )
                        )
                        reply_text = second_response.text if second_response and second_response.text else tool_res
                    except Exception as e:
                        logger.error(f"Error generating list summary response: {e}")
                        reply_text = tool_res

                    await self.storage.add_ai_chat_message("user", text)
                    await self.storage.add_ai_chat_message("model", reply_text)
                    return {"text": reply_text, "pending_action": None}
                elif action_name == "add_banword":
                    word = args.get("word")
                    scope = args.get("scope", "global")
                    scope_title = f" ({scope})" if scope != "global" else ""
                    reply_text = f"Вы хотите добавить банворд «{word}»{scope_title}?"
                elif action_name == "remove_banword":
                    word = args.get("word")
                    reply_text = f"Вы хотите удалить банворд «{word}»?"
                elif action_name == "add_news_topic":
                    topic = args.get("topic")
                    pref = args.get("preference")
                    p_str = "желаемую" if pref == "liked" else "запретную"
                    reply_text = f"Вы хотите добавить {p_str} тему «{topic}»?"
                elif action_name == "remove_news_topic":
                    topic = args.get("topic")
                    pref = args.get("preference")
                    p_str = "желаемую" if pref == "liked" else "запретную"
                    reply_text = f"Вы хотите удалить {p_str} тему «{topic}»?"
                elif action_name == "add_tg_channel":
                    channel = args.get("channel_username")
                    reply_text = f"Вы хотите добавить Telegram канал «{channel}»?"
                elif action_name == "remove_tg_channel":
                    channel = args.get("channel_username")
                    reply_text = f"Вы хотите удалить Telegram канал «{channel}»?"
                elif action_name == "get_bot_stats":
                    settings = SettingsManager(self.storage)
                    total = await settings.get_stats_total_processed()
                    spam = await settings.get_stats_spam_blocked()
                    reply_text = f"📊 Обработано сообщений: {total}\n🛑 Заблокировано спама: {spam}"
                    await self.storage.add_ai_chat_message("user", text)
                    await self.storage.add_ai_chat_message("model", reply_text)
                    return {"text": reply_text, "pending_action": None}
                elif action_name == "set_timezone":
                    offset = args.get("offset_hours", 0)
                    reply_text = f"⚙️ Меняю часовой пояс на UTC{'+' if int(offset) >= 0 else ''}{offset}..."
                elif action_name == "set_digest_interval":
                    mins = args.get("minutes", 60)
                    reply_text = f"⚙️ Меняю интервал сводок на {mins} мин..."
                elif action_name == "set_delivery_mode":
                    mode = args.get("mode", "digest")
                    reply_text = f"⚙️ Меняю режим доставки на «{'мгновенный (instant)' if mode == 'instant' else 'сводка (digest)'}»..."
                elif action_name == "toggle_night_mode":
                    enabled = bool(args.get("enabled", True))
                    reply_text = f"⚙️ {'Включаю' if enabled else 'Выключаю'} Ночной режим (часы тишины)..."
                elif action_name == "set_night_hours":
                    start_h = args.get("start_hour", 23)
                    end_h = args.get("end_hour", 7)
                    reply_text = f"⚙️ Устанавливаю часы тишины на {start_h}:00 - {end_h}:00..."
                elif action_name == "toggle_category_filter":
                    cat = args.get("category", "")
                    enabled = bool(args.get("enabled", True))
                    reply_text = f"⚙️ {'Включаю' if enabled else 'Отключаю'} фильтрацию категории «{cat}»..."
                elif action_name == "clear_chat":
                    reply_text = "Вы уверены, что хотите полностью очистить историю сообщений?"
                else:
                    reply_text = "Я хочу выполнить действие, но не понимаю какое."

                return {
                    "text": reply_text,
                    "pending_action": {
                        "action": action_name,
                        "args": args,
                        "user_text": text
                    }
                }

            reply_text = response.text if response.text else "Я не знаю что ответить."
            await self.storage.add_ai_chat_message("user", text)
            await self.storage.add_ai_chat_message("model", reply_text)
            
            return {"text": reply_text, "pending_action": None}

        except Exception as e:
            err_msg = str(e)
            if "временно на паузе" in err_msg or "лимит" in err_msg.lower():
                logger.warning(f"ConversationalAgent temporary rate limit: {e}")
                return {"text": f"⏳ {e}", "pending_action": None}
            logger.error(f"Error in ConversationalAgent: {e}", exc_info=True)
            return {"text": f"⚠️ Произошла ошибка при обращении к ИИ: {e}", "pending_action": None}
