import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from ai_engine import AIEngine
from user_agent import ConversationalAgent

class TestListTools(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = MagicMock()
        self.ai = AIEngine(api_key=None, storage=self.storage)
        self.agent = ConversationalAgent(ai_engine=self.ai, storage=self.storage)

    async def test_list_tg_channels_empty_and_with_data(self):
        self.storage.get_tg_channels = AsyncMock(return_value=[])
        res_empty = await self.agent._list_tg_channels()
        self.assertIn("нет добавленных Telegram-каналов", res_empty)

        self.storage.get_tg_channels = AsyncMock(return_value=[{"username": "durov"}])
        res = await self.agent._list_tg_channels()
        self.assertIn("@durov", res)

    async def test_list_banwords_empty_and_with_data(self):
        self.storage.get_banwords = AsyncMock(return_value=[])
        res_empty = await self.agent._list_banwords()
        self.assertIn("нет добавленных банвордов", res_empty)

        self.storage.get_banwords = AsyncMock(return_value=[{"word": "спам", "scope": "global"}])
        res = await self.agent._list_banwords()
        self.assertIn("спам", res)

    async def test_list_news_topics_empty_and_with_data(self):
        self.storage.get_news_topics = AsyncMock(return_value=[])
        res_empty = await self.agent._list_news_topics()
        self.assertIn("нет настроенных тем новостей", res_empty)

        self.storage.get_news_topics = AsyncMock(side_effect=lambda preference: [{"topic": "Космос"}] if preference == "liked" else [{"topic": "Криминал"}])
        res = await self.agent._list_news_topics()
        self.assertIn("Космос", res)
        self.assertIn("Криминал", res)

    async def test_get_settings_summary(self):
        self.storage.get_setting = AsyncMock(side_effect=lambda key, default=None: default or "")
        res = await self.agent._get_settings_summary()
        self.assertIn("Режим доставки", res)
        self.assertIn("Часовой пояс", res)
        self.assertIn("Ночной режим", res)

if __name__ == "__main__":
    from unittest.mock import MagicMock
    unittest.main()
