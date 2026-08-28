import os
import sys
import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from master_bot import MasterBot
import bot_handlers.all_handlers as handlers_mod

class TestAIDisabledBehavior(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()
        self.master_bot = MasterBot(storage=self.storage)
        
        registered_handlers = []

        def mock_message_decorator(*args, **kwargs):
            def decorator(func):
                registered_handlers.append((args, kwargs, func))
                return func
            return decorator

        dp_mock = MagicMock()
        dp_mock.message = mock_message_decorator
        dp_mock.callback_query = mock_message_decorator
        self.master_bot.dp = dp_mock

        handlers_mod.setup_all_handlers(self.master_bot)
        handlers_mod.last_warning_time.clear()

        # Find handle_text_message
        self.handler = None
        for args, kwargs, func in registered_handlers:
            if func.__name__ == "handle_text_message":
                self.handler = func
                break

    async def test_both_flags_disabled_deletes_and_throttles_warning(self):
        # Disable both flags
        await self.storage.set_setting("ai_text_chat_enabled", "false")
        await self.storage.set_setting("ai_suggestions_enabled", "false")

        msg = AsyncMock()
        msg.text = "Обычное текстовое сообщение"
        msg.chat.id = 12345
        msg.delete = AsyncMock()
        sent_msg = AsyncMock()
        sent_msg.message_id = 999
        msg.answer = AsyncMock(return_value=sent_msg)

        # 1st message: should be deleted AND warning sent
        await self.handler(msg)
        msg.delete.assert_called_once()
        msg.answer.assert_called_once()
        self.assertIn("Чат с ИИ недоступен", msg.answer.call_args[0][0])

        # 2nd message within 5 minutes: should be deleted BUT warning NOT sent again
        msg.delete.reset_mock()
        msg.answer.reset_mock()
        await self.handler(msg)
        msg.delete.assert_called_once()
        msg.answer.assert_not_called()

        # Simulate 301 seconds elapsed
        handlers_mod.last_warning_time[12345] = time.time() - 301
        msg.delete.reset_mock()
        msg.answer.reset_mock()
        await self.handler(msg)
        msg.delete.assert_called_once()
        msg.answer.assert_called_once()

    async def test_one_flag_enabled_does_not_autodelete(self):
        # Enable suggestions flag, keep chat disabled
        await self.storage.set_setting("ai_text_chat_enabled", "false")
        await self.storage.set_setting("ai_suggestions_enabled", "true")

        msg = AsyncMock()
        msg.text = "Проверка текста"
        msg.chat.id = 12345
        msg.delete = AsyncMock()
        sent_msg = AsyncMock()
        sent_msg.message_id = 998
        msg.answer = AsyncMock(return_value=sent_msg)

        await self.handler(msg)
        # Message should NOT be auto-deleted by the dual-off handler, and NO warning should be sent
        msg.delete.assert_not_called()
        msg.answer.assert_not_called()

if __name__ == "__main__":
    unittest.main()
