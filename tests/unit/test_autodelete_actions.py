import os
import sys
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.settings import config
from master_bot import MasterBot

class TestActionAutoDelete(unittest.TestCase):
    def test_config_action_delay_default(self):
        """Verify that AUTO_DELETE_ACTION_DELAY defaults to 7 seconds."""
        self.assertEqual(config.AUTO_DELETE_ACTION_DELAY, 7)

    def test_schedule_delayed_deletion_filters_last_ui_msg(self):
        """Verify that active UI panel message (_last_ui_msg_id) is never deleted."""
        bot_mock = AsyncMock()
        storage_mock = AsyncMock()
        settings_mock = MagicMock()

        master_bot = MasterBot.__new__(MasterBot)
        master_bot.bot = bot_mock
        master_bot.storage = storage_mock
        master_bot.settings = settings_mock
        master_bot._last_ui_msg_id = 999  # Active UI panel ID

        async def run_check():
            master_bot.schedule_delayed_deletion(
                chat_id=12345,
                message_ids=[101, 102, 999],
                delay_seconds=0.01
            )
            await asyncio.sleep(0.05)
            deleted_ids = [call.kwargs.get("message_id") for call in bot_mock.delete_message.call_args_list]
            self.assertIn(101, deleted_ids)
            self.assertIn(102, deleted_ids)
            self.assertNotIn(999, deleted_ids)

        asyncio.run(run_check())

    def test_schedule_delayed_deletion_handles_errors_gracefully(self):
        """Verify that exceptions during message deletion (e.g. already deleted message) are swallowed silently."""
        bot_mock = AsyncMock()
        bot_mock.delete_message.side_effect = Exception("Message to delete not found")
        storage_mock = AsyncMock()

        master_bot = MasterBot.__new__(MasterBot)
        master_bot.bot = bot_mock
        master_bot.storage = storage_mock
        master_bot._last_ui_msg_id = 999

        async def run_check():
            # Should not raise exception even when delete_message fails
            master_bot.schedule_delayed_deletion(
                chat_id=12345,
                message_ids=[201, 202],
                delay_seconds=0.01
            )
            await asyncio.sleep(0.05)
            self.assertEqual(bot_mock.delete_message.call_count, 2)

        asyncio.run(run_check())

    def test_schedule_delayed_deletion_ignores_none_and_zero_ids(self):
        """Verify that None, 0, and invalid message IDs are ignored."""
        bot_mock = AsyncMock()
        storage_mock = AsyncMock()

        master_bot = MasterBot.__new__(MasterBot)
        master_bot.bot = bot_mock
        master_bot.storage = storage_mock
        master_bot._last_ui_msg_id = None

        async def run_check():
            master_bot.schedule_delayed_deletion(
                chat_id=12345,
                message_ids=[None, 0, 301],
                delay_seconds=0.01
            )
            await asyncio.sleep(0.05)
            deleted_ids = [call.kwargs.get("message_id") for call in bot_mock.delete_message.call_args_list]
            self.assertEqual(deleted_ids, [301])

        asyncio.run(run_check())

    def test_schedule_delayed_deletion_persists_to_storage(self):
        """Verify that scheduled deletions are saved to storage for crash resilience."""
        bot_mock = AsyncMock()
        storage_mock = AsyncMock()

        master_bot = MasterBot.__new__(MasterBot)
        master_bot.bot = bot_mock
        master_bot.storage = storage_mock
        master_bot._last_ui_msg_id = 999

        async def run_check():
            master_bot.schedule_delayed_deletion(
                chat_id=12345,
                message_ids=[401],
                delay_seconds=7
            )
            await asyncio.sleep(0.02)
            storage_mock.save_sent_notification.assert_called_once_with(12345, 401, 7)

        asyncio.run(run_check())

if __name__ == "__main__":
    unittest.main()
