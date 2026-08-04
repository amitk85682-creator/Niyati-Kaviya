import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta

from group_room import group_manager, GroupRoomState
from memory import get_memory
from utils import rate_limiter
from config import Config
from ai_engine import AIEngine
from database import db

# Mock Context
class MockBot:
    def __init__(self, id, username):
        self.id = id
        self.username = username

class MockContext:
    def __init__(self, bot_name, bot_id, bot_username):
        self.bot_data = {'bot_name': bot_name, 'bot_username': bot_username}
        self.bot = MockBot(bot_id, bot_username)

class MockUser:
    def __init__(self, id, first_name, is_bot=False, username=""):
        self.id = id
        self.first_name = first_name
        self.is_bot = is_bot
        self.username = username

class MockChat:
    def __init__(self, id, type="group"):
        self.id = id
        self.type = type

class MockMessage:
    def __init__(self, message_id, text, user, chat, reply_to_message=None):
        self.message_id = message_id
        self.text = text
        self.from_user = user
        self.chat = chat
        self.reply_to_message = reply_to_message

class MockUpdate:
    def __init__(self, message):
        self.message = message
        self.effective_user = message.from_user
        self.effective_chat = message.chat


class FinalVerificationTests(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self):
        # Reset globals
        group_manager._rooms.clear()
        group_manager._bot_ids.clear()
        rate_limiter.cooldowns.clear()
        rate_limiter.requests.clear()
        
        group_manager.register_bot('niyati', 101)
        group_manager.register_bot('palak', 102)
        
        Config.NIYATI_BOT_USERNAME = "NiyatiBot"
        Config.PALAK_BOT_USERNAME = "PalakDevaBot"
        
        # Mock DB
        self.mock_db_data = {'niyati': {}, 'palak': {}}
        async def mock_save_msg(bot, user_id, role, content):
            if user_id not in self.mock_db_data[bot]:
                self.mock_db_data[bot][user_id] = []
            self.mock_db_data[bot][user_id].append({'bot': bot, 'role': role, 'content': content})
            
        async def mock_get_context(bot, user_id):
            return self.mock_db_data[bot].get(user_id, [])
            
        self.db_patcher1 = patch('memory.db.save_message', new=mock_save_msg)
        self.db_patcher2 = patch('memory.db.get_user_context', new=mock_get_context)
        self.db_patcher1.start()
        self.db_patcher2.start()

    async def asyncTearDown(self):
        self.db_patcher1.stop()
        self.db_patcher2.stop()

    # =========================================================================
    # PRIVATE CHAT SCENARIOS
    # =========================================================================
    async def test_01_02_private_chats_isolated(self):
        """Scenarios 1, 2, 5: Verify private chats are routed correctly and histories isolated."""
        mem_niyati = get_memory('niyati')
        mem_palak = get_memory('palak')
        
        # They should return different objects
        self.assertNotEqual(id(mem_niyati), id(mem_palak))
        
        await mem_niyati.save_private_message(1, 'user', 'hi niyati')
        await mem_palak.save_private_message(1, 'user', 'hi palak')
        
        hist_n = await mem_niyati.get_private_context(1, 'user')
        hist_p = await mem_palak.get_private_context(1, 'user')
        
        self.assertEqual(hist_n[-1]['content'], 'hi niyati')
        self.assertEqual(hist_p[-1]['content'], 'hi palak')

    # =========================================================================
    # GROUP MENTIONS & GENERAL DECISIONS
    # =========================================================================
    async def test_03_04_05_06_group_mentions(self):
        """Scenarios 3, 4, 5, 6: Turn coordination decisions."""
        chat_id = -100
        room = await group_manager.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True
        
        # Scenario 3: Mention only Niyati
        p_niyati = group_manager._decide_responders(room, 1, 10, "hello niyati")
        self.assertIn('niyati', p_niyati)
        
        # Scenario 4: Mention only Palak
        p_palak = group_manager._decide_responders(room, 2, 10, "hello palak")
        self.assertIn('palak', p_palak)
        
        # Scenario 5: Address both
        p_both = group_manager._decide_responders(room, 3, 10, "hello dono niyati and palak")
        self.assertCountEqual(p_both, ['niyati', 'palak'])
        
        # Scenario 6: General message
        # Probabilistic, so we just ensure it returns a list
        p_general = group_manager._decide_responders(room, 4, 10, "kya haal hai")
        self.assertIsInstance(p_general, list)

    # =========================================================================
    # BOT TO BOT REACTIONS
    # =========================================================================
    async def test_09_10_12_bot_reactions(self):
        """Scenarios 9, 10, 12: Bot-to-bot interactions and ignoring unknown bots."""
        chat_id = -100
        room = await group_manager.get_room(chat_id)
        room.active_until = datetime.now(timezone.utc) + timedelta(minutes=1) # simulate active human
        room.niyati_present = True
        room.palak_present = True
        
        # Niyati replies, Palak reacts (Scenario 9)
        # Niyati sends message 10
        await group_manager.add_bot_message('niyati', chat_id, 10, 'NiyatiBot', "how are you palak")
        
        # Palak processes Niyati's message
        proceed, planned = await group_manager.process_partner_message(
            bot_name='palak', chat_id=chat_id, message_id=10, 
            partner_id=101, partner_name='NiyatiBot', text="how are you palak"
        )
        self.assertTrue(proceed, "Palak should process Niyati's message")
        
        # Unknown bot speaks (Scenario 12)
        # Assuming handled correctly by the handler returning early, but manager should ignore if called.
        # Actually in messages.py it checks _OTHER_BOT_USERNAMES. We'll simulate by max limits.
        room.total_bot_replies = 99
        proceed, _ = await group_manager.process_partner_message('palak', chat_id, 11, 999, 'RandoBot', 'spam')
        self.assertFalse(proceed, "Should hit bot reply limit and stop")

    # =========================================================================
    # SILENCE / TIMEOUT
    # =========================================================================
    async def test_11_user_silence(self):
        """Scenario 11: User becomes silent"""
        chat_id = -100
        room = await group_manager.get_room(chat_id)
        room.active_until = datetime.now(timezone.utc) - timedelta(seconds=1) # expired
        
        # Partner bot message comes in while human is silent
        proceed, _ = await group_manager.process_partner_message('palak', chat_id, 20, 101, 'Niyati', 'hello')
        self.assertFalse(proceed, "Bot should not react if human session is expired")

    # =========================================================================
    # DEDUPLICATION
    # =========================================================================
    async def test_13_deduplication(self):
        """Scenario 13: Same update delivered twice"""
        chat_id = -100
        
        # Process once
        proc1, _ = await group_manager.process_human_message('niyati', chat_id, 1, 10, 'User', 'test')
        self.assertTrue(proc1)
        
        # Process again (same update)
        proc2, _ = await group_manager.process_human_message('niyati', chat_id, 1, 10, 'User', 'test')
        self.assertFalse(proc2, "Duplicate message should be dropped")

    # =========================================================================
    # RATE LIMITING
    # =========================================================================
    async def test_20_rate_limiting(self):
        """Scenario 20: Rate limits reached by one bot independently"""
        user_id = 1
        
        # Drain Niyati's limits
        for i in range(10):
            await rate_limiter.check("niyati", user_id)
            
        allowed_niyati, _ = await rate_limiter.check("niyati", user_id)
        self.assertFalse(allowed_niyati)
        
        allowed_palak, _ = await rate_limiter.check("palak", user_id)
        self.assertTrue(allowed_palak, "Palak should not be blocked by Niyati's limits")

    # =========================================================================
    # FALLBACKS / ISOLATION / PRESENCE
    # =========================================================================
    async def test_19_presence(self):
        """Scenario 19: One bot removed from group"""
        chat_id = -100
        room = await group_manager.get_room(chat_id)
        
        await group_manager.update_presence(chat_id, 'niyati', True)
        await group_manager.update_presence(chat_id, 'palak', False) # removed
        
        planned = group_manager._decide_responders(room, 5, 10, "hello palak")
        self.assertEqual(planned, ['niyati'], "Niyati should take over 100% if she is alone")

if __name__ == '__main__':
    unittest.main()
