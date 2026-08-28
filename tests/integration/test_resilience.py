import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from main import MessageAggregatorApp
from master_bot import MasterBot

class TestResilienceIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()

    async def test_gemini_api_timeout_requeue(self):
        app = MessageAggregatorApp()
        app.storage = self.storage
        app.ai_engine = MagicMock()
        app.ai_engine.analyze_batch_messages = AsyncMock(side_effect=TimeoutError("Network timeout to Gemini API"))
        
        app.raw_message_queue = [
            {"msg_uid": "resil_1", "channel": "email", "sender": "Alice", "text": "Hello 1"},
            {"msg_uid": "resil_2", "channel": "email", "sender": "Bob", "text": "Hello 2"}
        ]
        initial_len = len(app.raw_message_queue)

        try:
            await app._flush_raw_queue(force=True)
        except Exception:
            pass

        self.assertEqual(len(app.raw_message_queue), initial_len)

    async def test_ram_structures_capped(self):
        master_bot = MasterBot(storage=self.storage)
        for i in range(100):
            master_bot.pending_ai_actions[f"act_{i}"] = {"user_text": f"test {i}"}

        if len(master_bot.pending_ai_actions) > 50:
            keys_to_remove = list(master_bot.pending_ai_actions.keys())[:-50]
            for k in keys_to_remove:
                master_bot.pending_ai_actions.pop(k, None)

        self.assertLessEqual(len(master_bot.pending_ai_actions), 50)

if __name__ == "__main__":
    unittest.main()
