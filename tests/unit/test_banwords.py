import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from banwords import is_text_spam

class TestBanwords(unittest.TestCase):
    def test_system_banwords_matching(self):
        spam_text = "Получите ваш новый 1xbet бонус прямо сейчас!"
        self.assertTrue(is_text_spam(spam_text, channel="email"))

    def test_clean_text_passes(self):
        clean_text = "Здравствуйте, высылаю вам техническую документацию по проекту."
        self.assertFalse(is_text_spam(clean_text, channel="email"))

    def test_custom_banword_scope(self):
        custom_bws = [{"word": "казино", "scope": "email"}]
        self.assertTrue(is_text_spam("Играть в казино", channel="email", active_banwords=custom_bws))
        self.assertFalse(is_text_spam("Играть в казино", channel="vk", active_banwords=custom_bws))

if __name__ == "__main__":
    unittest.main()
