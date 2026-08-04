import asyncio
import unittest
from utils import rate_limiter

class TestPhase3RateLimiter(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self):
        # Clear rate limiter before each test
        rate_limiter.cooldowns.clear()
        rate_limiter.requests.clear()
        
    async def test_independent_cooldown(self):
        user_id = 12345
        
        # Niyati request 1 -> allowed
        allowed, reason = await rate_limiter.check("niyati", user_id)
        self.assertTrue(allowed)
        
        # Niyati request 2 immediately -> cooldown
        allowed, reason = await rate_limiter.check("niyati", user_id)
        self.assertFalse(allowed)
        self.assertEqual(reason, "cooldown")
        
        # Palak request for same user -> should be allowed! (independent)
        allowed, reason = await rate_limiter.check("palak", user_id)
        self.assertTrue(allowed)
        print("[SUCCESS] Palak independent of Niyati cooldown.")
        
    async def test_daily_total(self):
        user_id = 999
        await rate_limiter.check("niyati", user_id)
        await asyncio.sleep(0.01) # to bypass cooldown slightly or just force stats? Wait, cooldown blocks it.
        # Actually, let's just use different users to test daily totals quickly
        await rate_limiter.check("niyati", 111)
        await rate_limiter.check("palak", 222)
        await rate_limiter.check("palak", 333)
        
        niyati_total = rate_limiter.get_daily_total("niyati")
        palak_total = rate_limiter.get_daily_total("palak")
        combined_total = rate_limiter.get_daily_total()
        
        self.assertEqual(niyati_total, 2)
        self.assertEqual(palak_total, 2)
        self.assertEqual(combined_total, 4)
        print("[SUCCESS] Admin stats separate request counts correctly.")
        
if __name__ == '__main__':
    unittest.main()
