import asyncio
import unittest
from group_room import group_manager

class TestPhase5Coordinator(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        group_manager._rooms.clear()

    async def test_deterministic_decisions(self):
        chat_id = -1001
        msg_id = 99
        sender_id = 123
        
        # 1. "dono" mentioned -> both bots
        res1 = group_manager._decide_responders(chat_id, msg_id, sender_id, "dono kahan ho")
        self.assertEqual(len(res1), 2)
        self.assertIn('niyati', res1)
        self.assertIn('palak', res1)
        
        # 2. Same inputs produce exact same result
        res_a = group_manager._decide_responders(chat_id, 100, sender_id, "hello")
        res_b = group_manager._decide_responders(chat_id, 100, sender_id, "hello")
        self.assertEqual(res_a, res_b)
        
        # 3. Direct mention Niyati
        res2 = group_manager._decide_responders(chat_id, 101, sender_id, "niyati hi")
        self.assertIn('niyati', res2)
        
        # 4. Direct mention Palak
        res3 = group_manager._decide_responders(chat_id, 102, sender_id, "palak hi")
        self.assertIn('palak', res3)
        print("[SUCCESS] Deterministic coordinator logic tests passed.")
        
if __name__ == '__main__':
    unittest.main()
