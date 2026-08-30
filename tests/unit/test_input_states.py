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

if __name__ == "__main__":
    unittest.main()
