import logging
import json
from typing import Optional, Dict, Any, List
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class ConversationalAgent:
    def __init__(self, ai_engine: Any, storage):
        self.ai_engine = ai_engine
        self.storage = storage
        self.model_name = "gemini-3.5-flash"
        
        self.system_instruction = (
            "Ты — личный ИИ-ассистент в Telegram боте агрегаторе сообщений.\n"
            "Бот собирает сообщения, фильтрует спам, выдает сводки, а также автоматически распознает штрафы, налоги и уведомления от Госуслуг.\n"
            "Умеешь общаться, отвечать на вопросы, добавлять банворды, каналы в Telegram и настраивать темы новостей.\n"
            "Если пользователь спрашивает, что ты умеешь, обязательно перечисли свои возможности, включая умную фильтрацию задолженностей и Госуслуг.\n"
            "Если пользователь просит добавить/удалить банворд (слово для фильтрации спама), тему новостей или Телеграм канал, "
            "Используй доступные инструменты (tools). Тебе не нужно самому подтверждать выполнение инструмента. "
            "Просто вызови инструмент, а бот запросит разрешение у пользователя.\n"
            "Если пользователь просит добавить Телеграм канал (например 'добавь канал Nexta'), обязательно ИСПОЛЬЗУЙ встроенный инструмент google_search, чтобы найти правильный юзернейм (@username) или ссылку на этот канал, а затем вызови инструмент add_tg_channel.\n"
            "Также ты можешь управлять настройками бота (часовой пояс, интервал сводок) и очищать чат, вызывая соответствующие инструменты.\n"
            "Отвечай кратко и дружелюбно."
        )

    # Tool definitions
    def add_banword(self, word: str, scope: str = "global") -> str:
        """Adds a new banword to filter out unwanted messages."""
        pass 

    def add_news_topic(self, topic: str, preference: str) -> str:
        """Adds a news topic. Preference must be either 'liked' (interesting) or 'disliked' (ignore)."""
        pass 

    def remove_news_topic(self, topic: str, preference: str) -> str:
        """Removes a news topic. Preference must be either 'liked' or 'disliked'."""
        pass 

    def add_tg_channel(self, channel_username: str) -> str:
        """Adds a Telegram channel to the bot's watchlist. Make sure channel_username is a valid @username or t.me/ link."""
        pass

    def get_bot_stats(self) -> str:
        """Returns the current message statistics."""
        pass 

    def set_timezone(self, offset_hours: int) -> str:
        """Sets the bot's timezone offset in hours from UTC (e.g., 3 for Moscow, 5 for Yekaterinburg)."""
        pass

    def set_digest_interval(self, minutes: int) -> str:
        """Sets the interval in minutes for sending automatic news digests (e.g., 60 for 1 hour)."""
        pass

    def clear_chat(self) -> str:
        """Clears the entire chat history and removes all stored messages from the bot's database. Requires confirmation."""
        pass

    def _get_tools(self):
        return [
            self.add_banword, 
            self.add_news_topic, 
            self.remove_news_topic, 
            self.add_tg_channel,
            self.get_bot_stats,
            self.set_timezone,
            self.set_digest_interval,
            self.clear_chat,
            {"google_search": {}} # Native AI Google Search tool
        ]

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
            from settings_manager import SettingsManager
            settings = SettingsManager(self.storage)
            tz_offset = await settings.get_timezone_offset()
            from datetime import datetime, timedelta
            current_time = datetime.utcnow() + timedelta(hours=tz_offset)
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
                temperature=0.7
            )
            
            response = await self.ai_engine.generate_content_with_retry(
                contents=contents,
                config=config
            )

            # Check for function calls
            if response.function_calls:
                fc = response.function_calls[0]
                action_name = fc.name
                args = fc.args

                # Format a user-friendly response
                if action_name == "add_banword":
                    word = args.get("word")
                    reply_text = f"Вы хотите добавить банворд «{word}»?"
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
                elif action_name == "get_bot_stats":
                    from settings_manager import SettingsManager
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
            logger.error(f"Error in ConversationalAgent: {e}", exc_info=True)
            return {"text": f"Произошла ошибка при обращении к ИИ: {e}", "pending_action": None}
