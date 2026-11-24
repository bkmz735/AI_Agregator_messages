import os
import sys
import asyncio
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from master_bot import MasterBot

class TestInputStates(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()
        self.master_bot = MasterBot(storage=self.storage)

    async def asyncTearDown(self):
        await self.storage.close()

    async def test_input_state_clearing(self):
        self.master_bot._waiting_for_banword_scope = "email"
        self.assertEqual(self.master_bot._waiting_for_banword_scope, "email")

        self.master_bot.clear_input_states()
        self.assertIsNone(self.master_bot._waiting_for_banword_scope)

    async def test_input_state_override(self):
        self.master_bot._waiting_for_tg_channel = True
        self.assertTrue(self.master_bot._waiting_for_tg_channel)

        self.master_bot.clear_input_states()
        self.master_bot._waiting_for_liked_topic = True
        self.assertFalse(self.master_bot._waiting_for_tg_channel)
        self.assertTrue(self.master_bot._waiting_for_liked_topic)

        self.master_bot.clear_input_states()
        self.assertFalse(self.master_bot._waiting_for_liked_topic)

    async def test_navigation_clears_all_interactive_input_flags(self):
        """Verifies that navigation callback handlers actively wipe input states."""
        self.master_bot.bot_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
        self.master_bot._init_bot_instance(use_proxy=False)

        # Set all interactive input flags
        self.master_bot._waiting_for_banword_scope = "email"
        self.master_bot._waiting_for_tg_channel = True
        self.master_bot._waiting_for_liked_topic = True
        self.master_bot._waiting_for_disliked_topic = True
        self.master_bot._waiting_for_dns_ip = True

        from unittest.mock import AsyncMock, MagicMock
        from aiogram import types
        mock_cb = AsyncMock()
        mock_cb.data = "settings_main_menu"
        mock_msg = MagicMock(spec=types.Message)
        mock_msg.edit_text = AsyncMock()
        mock_cb.message = mock_msg

        # Find settings_main_menu handler
        for h in self.master_bot.dp.callback_query.handlers:
            if h.callback.__name__ == "process_settings_main_menu":
                await h.callback(mock_cb)
                break

        self.assertIsNone(self.master_bot._waiting_for_banword_scope)
        self.assertFalse(self.master_bot._waiting_for_tg_channel)
        self.assertFalse(self.master_bot._waiting_for_liked_topic)
        self.assertFalse(self.master_bot._waiting_for_disliked_topic)
        self.assertFalse(self.master_bot._waiting_for_dns_ip)

if __name__ == "__main__":
    unittest.main()
