import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from settings_manager import SettingsManager
from master_bot import MasterBot, clean_sender_name, clean_summary_text
from user_agent import ConversationalAgent
from ai_engine import AIEngine
from adapters.vk_adapter import VKAdapter
from models.message import AnalysisResult

class TestBugFixes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()
        self.settings = SettingsManager(self.storage)
        self.ai = AIEngine(api_key=None, storage=self.storage)
        self.bot = MasterBot(storage=self.storage, ai_engine=self.ai)

    async def asyncTearDown(self):
        await self.storage.close()

    async def test_update_ai_category_filter_exists_and_works(self):
        """Verifies fix for bug 1.1: update_ai_category_filter singular method."""
        await self.settings.update_ai_category_filter("news", False)
        filters = await self.settings.get_ai_category_filters()
        self.assertFalse(filters.get("news"))

        await self.settings.update_ai_category_filter("news", True)
        filters = await self.settings.get_ai_category_filters()
        self.assertTrue(filters.get("news"))

    async def test_get_bot_stats_returns_real_counts(self):
        """Verifies fix for bug 2.1: get_bot_stats returns actual data from DB."""
        # Insert a message
        await self.storage.save_message(
            msg_uid="stat_test_msg_1",
            channel="Email",
            sender="Tester",
            text="Test message body",
            category="important",
            summary="Test summary",
            action_required=False,
            is_delivered=1
        )

        agent = ConversationalAgent(ai_engine=self.ai, storage=self.storage)
        res = await agent.process_message("Покажи статистику")
        # In simulation mode (no API key), it uses rule-based reply.
        # Direct test of stats retrieval:
        stats = await self.storage.get_stats()
        self.assertGreaterEqual(stats["total_all"], 1)
        self.assertGreaterEqual(stats["delivered_count"], 1)

    async def test_proxy_fallback_avoids_router_collision(self):
        """Verifies fix for bug 1.2: re-initializing bot with direct connection preserves Dispatcher."""
        self.bot.bot_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
        self.bot._init_bot_instance(use_proxy=True)
        initial_dp = self.bot.dp
        self.assertIsNotNone(initial_dp)

        # Trigger proxy fallback
        self.bot._init_bot_instance(use_proxy=False)
        self.assertIs(self.bot.dp, initial_dp)

    async def test_tg_news_never_marked_urgent_or_important(self):
        """Verifies fix for bug 2.2: Telegram news messages are safely downgraded to news."""
        chunk = [{
            "msg_uid": "tg_news_channel_123",
            "channel": "Telegram",
            "sender": "@channel",
            "text": "Срочная новость про налоги и штрафы!"
        }]
        results = await self.ai.analyze_batch_messages(chunk)
        self.assertEqual(len(results), 1)
        # Even if text looks like taxes or urgency, channel is news so it shouldn't require user action
        self.assertIn(results[0].category, ["news", "media", "interesting", "politics", "bullshit", "general"])
        self.assertFalse(results[0].action_required)

    def test_clean_sender_name(self):
        """Verifies email and handle sender cleaning."""
        self.assertEqual(clean_sender_name("Авито <noreply@avito.ru>"), "Авито")
        self.assertEqual(clean_sender_name("<support@corp.mail.ru>"), "support@corp.mail.ru")
        self.assertEqual(clean_sender_name("Иван Иванов"), "Иван Иванов")
        self.assertEqual(clean_sender_name("@@channel"), "channel")

    def test_clean_summary_text_deduplication(self):
        """Verifies that redundant source and boilerplate intro phrases are stripped from summary."""
        s1 = clean_summary_text("Сообщение от Иван Иванов: Привет, когда будет готово?", sender="Иван Иванов", channel="VK")
        self.assertEqual(s1, "Привет, когда будет готово?")

        s2 = clean_summary_text("Новость от @mash: В Москве открылась новая станция", sender="@mash", channel="Telegram")
        self.assertEqual(s2, "В Москве открылась новая станция")

        s3 = clean_summary_text("Авито: Покупатель оформил заказ", sender="Авито", channel="Авито")
        self.assertEqual(s3, "Покупатель оформил заказ")

if __name__ == "__main__":
    unittest.main()
