import asyncio
import unittest
from group_room import group_manager

class TestPhase7Presence(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        group_manager._rooms.clear()

    async def test_presence_logic(self):
        chat_id = -1002
        room = await group_manager.get_room(chat_id)
        
        # 1. Start with Niyati present only
        await group_manager.update_presence(chat_id, 'niyati', True)
        await group_manager.update_presence(chat_id, 'palak', False)
        
        # Test decide_responders
        planned1 = group_manager._decide_responders(room, 1, 100, "hello both of you")
        self.assertEqual(planned1, ['niyati'], "Should only plan niyati since she's alone")
        
        # 2. Both present
        await group_manager.update_presence(chat_id, 'palak', True)
        planned2 = group_manager._decide_responders(room, 2, 100, "hello dono")
        self.assertCountEqual(planned2, ['niyati', 'palak'], "Should plan both when both present")
        
        # 3. Only Palak present
        await group_manager.update_presence(chat_id, 'niyati', False)
        planned3 = group_manager._decide_responders(room, 3, 100, "hey niyati")
        self.assertEqual(planned3, ['palak'], "Should only plan palak despite niyati mention since she's alone")

        print("[SUCCESS] Phase 7 presence tests passed")

if __name__ == '__main__':
    unittest.main()
