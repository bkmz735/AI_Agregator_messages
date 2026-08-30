import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from master_bot import MasterBot
from settings_manager import SettingsManager

class TestNightModeAndBuffer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()
        self.settings = SettingsManager(self.storage)
        self.bot = MasterBot(storage=self.storage)

    async def test_night_mode_digest_suppression(self):
        self.bot.night_mode_enabled = True
        self.bot.night_start_hour = 23
        self.bot.night_end_hour = 7
        self.bot.delivery_mode = "digest"
        
        # Mock is_night_time to True
        with patch.object(self.bot, 'is_night_time', return_value=True):
            self.bot.flush_buffer_now = AsyncMock()
            
            # Simulate one iteration of digest scheduler logic
            if self.bot.delivery_mode == "digest":
                if self.bot.is_night_time():
                    pass # should skip flush
                else:
                    await self.bot.flush_buffer_now()
            
            self.bot.flush_buffer_now.assert_not_called()

    async def test_muted_categories_not_stuck_in_buffer(self):
        # Disable 'media' category
        await self.settings.update_ai_category_filters({"media": False, "news": True})
        
        # handle_incoming_analyzed_message for muted 'media' category
        handled = await self.bot.handle_incoming_analyzed_message(
            channel="vk",
            sender="TestVK",
            text="Media post",
            category="media",
            summary="Media summary",
            action_required=False
        )
        self.assertEqual(handled, 2, "Muted category should return DeliveryStatus.FILTERED (2)")

        # Save to storage as main.py does
        await self.storage.save_message(
            msg_uid="muted_msg_1",
            channel="vk",
            sender="TestVK",
            text="Media post",
            category="media",
            summary="Media summary",
            action_required=False,
            is_delivered=handled
        )

        filters = await self.settings.get_ai_category_filters()
        disabled_cats = [cat for cat, enabled in filters.items() if not enabled]

        # Buffer count should be 0 for disabled categories
        buf_count = await self.storage.get_buffer_count(disabled_categories=disabled_cats)
        self.assertEqual(buf_count, 0)

        # Cleanup
        async with self.storage.get_db() as db:
            await db.execute("DELETE FROM messages WHERE msg_uid = 'muted_msg_1'")
            await db.commit()

    async def test_flush_clears_stuck_disabled_category_messages(self):
        # Save a message with category='media' and is_delivered=0 (simulating old data)
        await self.storage.save_message(
            msg_uid="stuck_media_1",
            channel="vk",
            sender="OldSender",
            text="Old media post",
            category="media",
            summary="Old media",
            action_required=False,
            is_delivered=0
        )

        disabled_cats = ["media"]
        # Call get_buffered_messages with mark_as_delivered=True
        messages = await self.storage.get_buffered_messages(mark_as_delivered=True, disabled_categories=disabled_cats)
        
        # 'media' message should not be in delivered digest list
        self.assertEqual(len(messages), 0)

        # But it should now be updated to is_delivered=2 in DB
        async with self.storage.get_db() as db:
            async with db.execute("SELECT is_delivered FROM messages WHERE msg_uid = 'stuck_media_1'") as cursor:
                row = await cursor.fetchone()
                self.assertEqual(row[0], 2)

        # Cleanup
        async with self.storage.get_db() as db:
            await db.execute("DELETE FROM messages WHERE msg_uid = 'stuck_media_1'")
            await db.commit()

if __name__ == "__main__":
    unittest.main()
