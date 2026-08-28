import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from settings_manager import SettingsManager
from banwords import is_text_spam

class TestPipelineIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()
        self.settings = SettingsManager(self.storage)

    async def test_end_to_end_buffer_and_filtering(self):
        # 1. Banword check
        bws = await self.storage.get_banwords()
        test_spam_text = "Получите ваш новый 1xbet бонус"
        is_spam = is_text_spam(test_spam_text, channel="email", active_banwords=bws)
        self.assertTrue(is_spam)

        # 2. Muted categories in buffer query
        await self.storage.save_message(
            msg_uid="pipe_test_1",
            channel="email",
            sender="Boss",
            text="Need urgent response",
            category="urgent",
            summary="Urgent task",
            action_required=True,
            is_delivered=False
        )

        buf_msgs = await self.storage.get_buffered_messages(mark_as_delivered=False)
        buf_uids = [m["msg_uid"] for m in buf_msgs]
        self.assertIn("pipe_test_1", buf_uids)

        # Cleanup
        async with self.storage.get_db() as db:
            await db.execute("DELETE FROM messages WHERE msg_uid = 'pipe_test_1'")
            await db.commit()

if __name__ == "__main__":
    unittest.main()
