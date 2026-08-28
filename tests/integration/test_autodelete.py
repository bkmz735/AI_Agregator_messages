import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage

class TestAutoDeleteIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()

    async def test_expired_notifications_retrieval(self):
        # Save notification that expired 5 minutes ago
        past_time = (datetime.utcnow() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        
        async with self.storage.get_db() as db:
            await db.execute(
                "INSERT INTO sent_notifications (chat_id, message_id, delete_at) VALUES (?, ?, ?)",
                (12345, 999111, past_time)
            )
            await db.commit()

        expired = await self.storage.get_expired_notifications()
        expired_ids = [n["message_id"] for n in expired]
        self.assertIn(999111, expired_ids)

        # Cleanup
        async with self.storage.get_db() as db:
            await db.execute("DELETE FROM sent_notifications WHERE message_id = 999111")
            await db.commit()

if __name__ == "__main__":
    unittest.main()
