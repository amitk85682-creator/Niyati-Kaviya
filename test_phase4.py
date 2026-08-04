import asyncio
import unittest
from group_room import group_manager

class TestPhase4GroupRoom(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self):
        # Clear rooms before each test
        group_manager._rooms.clear()
        
    async def test_deduplication_and_session(self):
        chat_id = -100123
        msg_id = 42
        user_id = 99
        
        # 1. Niyati gets message 42
        proceed_niyati = await group_manager.process_human_message(
            'niyati', chat_id, msg_id, user_id, 'UserA', 'hello'
        )
        self.assertTrue(proceed_niyati, "Niyati should proceed")
        
        # 2. Niyati gets duplicate message 42 (e.g. from a retry or duplicate update)
        proceed_niyati_dup = await group_manager.process_human_message(
            'niyati', chat_id, msg_id, user_id, 'UserA', 'hello'
        )
        self.assertFalse(proceed_niyati_dup, "Niyati should drop duplicate")
        
        # 3. Palak gets message 42 (this is the key requirement! They must not block each other)
        proceed_palak = await group_manager.process_human_message(
            'palak', chat_id, msg_id, user_id, 'UserA', 'hello'
        )
        self.assertTrue(proceed_palak, "Palak should proceed independently")
        
        # 4. Check Transcript Dedupe
        transcript = await group_manager.get_transcript(chat_id)
        # Should only have 1 message despite 3 handler calls!
        self.assertEqual(len(transcript), 1, "Transcript should store human message exactly once")
        
        # 5. Check Session
        room = await group_manager.get_room(chat_id)
        self.assertTrue(room.has_active_human_session(), "Session should be active")
        
        # 6. Bot messages don't open session if it expired
        room.active_until = None # Force expire
        self.assertFalse(room.has_active_human_session())
        await group_manager.add_bot_message('niyati', chat_id, 999, 'Niyati', 'response')
        transcript = await group_manager.get_transcript(chat_id)
        # Since it was expired, bot message should be ignored
        self.assertEqual(len(transcript), 1, "Bot message should be ignored if session expired")
        print("[SUCCESS] Phase 4 test passed")

if __name__ == '__main__':
    unittest.main()
