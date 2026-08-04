import os
import sys
import unittest
import asyncio

# Setup fake environment for testing fallback
os.environ['KAVYA_BOT_TOKEN'] = 'old_kavya_token'
os.environ['KAVYA_BOT_USERNAME'] = 'old_kavya_bot'

# Import Config AFTER setting environment variables
from config import Config
from characters import get_character

class TestPhase1Migration(unittest.TestCase):
    
    def test_config_fallback(self):
        # Config should fall back to KAVYA variables if PALAK is not set
        # Since config.py is imported once, we can test current state
        self.assertEqual(Config.PALAK_BOT_TOKEN, 'old_kavya_token')
        self.assertEqual(Config.PALAK_BOT_USERNAME, 'old_kavya_bot')
        print("[SUCCESS] Config loads PALAK variables with KAVYA fallback.")

    def test_get_character_palak(self):
        try:
            char = get_character("palak")
            self.assertEqual(char['bot_name'], 'palak')
            print("[SUCCESS] get_character('palak') succeeds.")
        except Exception as e:
            self.fail(f"get_character('palak') failed: {e}")

    def test_get_character_niyati(self):
        try:
            char = get_character("niyati")
            self.assertEqual(char['bot_name'], 'niyati')
            print("[SUCCESS] get_character('niyati') remains unchanged.")
        except Exception as e:
            self.fail(f"get_character('niyati') failed: {e}")



if __name__ == '__main__':
    unittest.main()
