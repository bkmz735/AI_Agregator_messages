import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage import Storage
from ai_engine import AIEngine, AudioAnalysisResult
from master_bot import MasterBot

class TestSubsystemsIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = Storage()
        await self.storage.init_db()

    async def asyncTearDown(self):
        await self.storage.close()

    async def test_audio_transcription_fallback(self):
        ai = AIEngine(api_key=None, storage=self.storage)
        dummy_audio = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
        res = await ai.transcribe_and_analyze_audio(dummy_audio, mime_type="audio/ogg")
        self.assertIsInstance(res, AudioAnalysisResult)
        self.assertIn("[Голосовое сообщение", res.transcription)

    async def test_log_sanitization(self):
        master_bot = MasterBot(storage=self.storage)
        import config
        original_proxy = config.config.TELEGRAM_PROXY
        config.config.TELEGRAM_PROXY = "http://admin:secret123@1.2.3.4:8080"

        log_text, _ = await master_bot._get_diagnostic_logs_text_and_keyboard()
        self.assertNotIn("secret123", log_text)
        self.assertIn("****", log_text)

        config.config.TELEGRAM_PROXY = original_proxy

if __name__ == "__main__":
    unittest.main()
