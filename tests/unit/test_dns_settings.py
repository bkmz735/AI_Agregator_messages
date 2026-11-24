import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from settings_manager import SettingsManager
import ui_keyboards as kb_ui


class TestDNSSettings(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.test_db = Path(__file__).parent / "test_dns.db"
        if self.test_db.exists():
            self.test_db.unlink()
        self.storage = Storage(db_path=str(self.test_db))
        await self.storage.init_db()
        self.settings = SettingsManager(self.storage)

    async def asyncTearDown(self):
        await self.storage.close()
        if self.test_db.exists():
            self.test_db.unlink()

    async def test_default_dns_servers(self):
        servers = await self.settings.get_dns_servers()
        self.assertIsInstance(servers, list)
        self.assertTrue(len(servers) >= 2)
        self.assertIn("95.214.27.105", servers)

    async def test_add_valid_ipv4(self):
        ok, res = await self.settings.add_dns_server("77.88.8.8")
        self.assertTrue(ok)
        self.assertEqual(res, "77.88.8.8")
        servers = await self.settings.get_dns_servers()
        self.assertIn("77.88.8.8", servers)

    async def test_add_valid_ipv6(self):
        ok, res = await self.settings.add_dns_server("2a02:6b8::feed:0ff")
        self.assertTrue(ok)
        servers = await self.settings.get_dns_servers()
        self.assertIn("2a02:6b8::feed:0ff", servers)

    async def test_add_valid_doh_url(self):
        ok, res = await self.settings.add_dns_server("https://dns.google/dns-query")
        self.assertTrue(ok)
        servers = await self.settings.get_dns_servers()
        self.assertIn("https://dns.google/dns-query", servers)

    async def test_reject_invalid_address(self):
        ok, res = await self.settings.add_dns_server("invalid_dns_host_999")
        self.assertFalse(ok)
        self.assertIn("не является корректным", res)

    async def test_reject_duplicate(self):
        servers = await self.settings.get_dns_servers()
        first = servers[0]
        ok, res = await self.settings.add_dns_server(first)
        self.assertFalse(ok)
        self.assertIn("уже есть в списке", res)

    async def test_remove_by_index_and_by_str(self):
        await self.settings.add_dns_server("1.1.1.1")
        servers = await self.settings.get_dns_servers()
        idx = servers.index("1.1.1.1")

        ok, removed = await self.settings.remove_dns_server_by_index(idx)
        self.assertTrue(ok)
        self.assertEqual(removed, "1.1.1.1")
        servers_after = await self.settings.get_dns_servers()
        self.assertNotIn("1.1.1.1", servers_after)

        # Remove by str
        await self.settings.add_dns_server("1.0.0.1")
        removed_ok = await self.settings.remove_dns_server("1.0.0.1")
        self.assertTrue(removed_ok)
        self.assertNotIn("1.0.0.1", await self.settings.get_dns_servers())

    async def test_reset_dns_servers(self):
        await self.settings.update_dns_servers(["8.8.8.8"])
        servers = await self.settings.get_dns_servers()
        self.assertEqual(servers, ["8.8.8.8"])

        defaults = await self.settings.reset_dns_servers()
        self.assertIn("95.214.27.105", defaults)
        self.assertIn("111.88.96.54", defaults)

    async def test_toggle_dns_enabled(self):
        self.assertTrue(await self.settings.get_dns_enabled())
        await self.settings.update_dns_enabled(False)
        self.assertFalse(await self.settings.get_dns_enabled())
        await self.settings.update_dns_enabled(True)
        self.assertTrue(await self.settings.get_dns_enabled())

    def test_dns_keyboards(self):
        kb = kb_ui.get_dns_menu_keyboard(["95.214.27.105", "111.88.96.54"], enabled=True)
        callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("dns_check_health", callbacks)
        self.assertIn("dns_toggle_enabled", callbacks)
        self.assertIn("dns_make_primary_1", callbacks)
        self.assertIn("dns_prompt_add", callbacks)
        self.assertIn("dns_reset_defaults", callbacks)
        self.assertIn("dns_del_0", callbacks)
        self.assertIn("dns_del_1", callbacks)

        kb_prompt = kb_ui.get_dns_add_prompt_keyboard()
        prompt_cbs = [b.callback_data for row in kb_prompt.inline_keyboard for b in row]
        self.assertIn("settings_menu_dns", prompt_cbs)

    async def test_make_dns_primary(self):
        await self.settings.update_dns_servers(["1.1.1.1", "8.8.8.8", "77.88.8.8"])
        servers = await self.settings.get_dns_servers()
        self.assertEqual(servers[0], "1.1.1.1")

        # Make 77.88.8.8 (index 2) primary
        ok, srv = await self.settings.make_dns_primary(2)
        self.assertTrue(ok)
        self.assertEqual(srv, "77.88.8.8")

        servers_after = await self.settings.get_dns_servers()
        self.assertEqual(servers_after[0], "77.88.8.8")
        self.assertEqual(servers_after[1], "1.1.1.1")
        self.assertEqual(servers_after[2], "8.8.8.8")

        # Invalid index
        bad_ok, _ = await self.settings.make_dns_primary(99)
        self.assertFalse(bad_ok)

    async def test_check_all_dns_health(self):
        from unittest.mock import patch
        with patch("ai_engine.check_dns_server_health") as mock_health:
            mock_health.side_effect = lambda s, d: {
                "server": s,
                "status": True,
                "latency_ms": 25,
                "ip": "142.250.180.10",
                "error": None
            }
            await self.settings.update_dns_servers(["8.8.8.8", "1.1.1.1"])
            results = await self.settings.check_all_dns_health()
            self.assertEqual(len(results), 2)
            self.assertTrue(results[0]["status"])
            self.assertEqual(results[0]["server"], "8.8.8.8")
            self.assertEqual(results[1]["server"], "1.1.1.1")

    def test_check_dns_server_health_function(self):
        from ai_engine import check_dns_server_health
        # Test against Google public DNS
        res = check_dns_server_health("8.8.8.8", domain="google.com", timeout=3.0)
        self.assertIn("status", res)
        self.assertIn("latency_ms", res)
        self.assertIn("server", res)
        self.assertEqual(res["server"], "8.8.8.8")


if __name__ == "__main__":
    unittest.main()
