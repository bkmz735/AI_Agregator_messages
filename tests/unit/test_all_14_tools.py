import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from ai_engine import AIEngine
from user_agent import ConversationalAgent

class TestAll14ToolsRegistration(unittest.TestCase):
    def test_all_14_tools_registered(self):
        storage = Storage()
        ai = AIEngine(api_key=None, storage=storage)
        agent = ConversationalAgent(ai_engine=ai, storage=storage)
        
        tools = agent._get_tools()
        tool_names = [t.__name__ for t in tools]
        
        expected_tools = [
            "web_search", "list_tg_channels", "list_banwords", "list_news_topics", "get_settings_summary",
            "add_banword", "remove_banword", "add_news_topic", "remove_news_topic",
            "add_tg_channel", "remove_tg_channel", "get_bot_stats", "set_timezone",
            "set_digest_interval", "set_delivery_mode", "toggle_night_mode",
            "set_night_hours", "toggle_category_filter", "clear_chat",
            "check_for_updates", "update_bot",
            "list_dns_servers", "add_dns_server", "remove_dns_server",
            "toggle_smart_dns", "reset_dns_servers"
        ]
        
        self.assertEqual(len(tool_names), 26)
        for et in expected_tools:
            self.assertIn(et, tool_names)

if __name__ == "__main__":
    unittest.main()
