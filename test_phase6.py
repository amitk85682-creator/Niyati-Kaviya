import asyncio
import unittest
from group_room import group_manager
from config import Config

class TestPhase6BotToBot(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        group_manager._rooms.clear()

    async def test_bot_to_bot_limits(self):
        chat_id = -1001
        
        # 1. Partner message when no human session exists
        proceed, _ = await group_manager.process_partner_message(
            'niyati', chat_id, 1, 999, 'Palak', 'hello'
        )
        self.assertFalse(proceed, "Should not proceed without human session")
        
        # 2. Human opens session
        await group_manager.process_human_message('niyati', chat_id, 10, 100, 'User', 'hi dono')
        
        # 3. Partner message now accepted (1st bot reply)
        proceed, _ = await group_manager.process_partner_message(
            'niyati', chat_id, 11, 999, 'Palak', 'niyati suno' # Direct mention forces niyati
        )
        self.assertTrue(proceed, "Should proceed since session is active and under limits")
        
        # 4. Check counters
        room = await group_manager.get_room(chat_id)
        self.assertEqual(room.total_bot_replies, 1)
        self.assertEqual(room.consecutive_bot_replies, 1)
        
        # 5. Hit consecutive limit (assuming MAX_CONSECUTIVE = 1)
        proceed2, _ = await group_manager.process_partner_message(
            'palak', chat_id, 12, 888, 'Niyati', 'palak bolo'
        )
        self.assertFalse(proceed2, "Should hit consecutive limit")
        
        # 6. Human messages again (resets counters)
        await group_manager.process_human_message('palak', chat_id, 13, 100, 'User', 'nice')
        self.assertEqual(room.total_bot_replies, 0)
        self.assertEqual(room.consecutive_bot_replies, 0)
        print("[SUCCESS] Phase 6 tests passed")

if __name__ == '__main__':
    unittest.main()
