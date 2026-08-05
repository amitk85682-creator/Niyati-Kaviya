import unittest
import asyncio
from datetime import datetime, timezone, timedelta
from emotional_core.models import MoodState, NeedState, RelationshipState, CharacterRuntimeState, ConversationAction
from emotional_core.state_manager import state_manager
from emotional_core.appraisal import AppraisalEngine
from emotional_core.emotion_engine import EmotionEngine
from emotional_core.conversation_policy import ConversationPolicy
from emotional_core.daily_life import DailyLifeGenerator

class TestEmotionalCore(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Reset state before each test
        await state_manager.reset_state("niyati", 1, 99)
        await state_manager.reset_state("palak", 1, 99)

    async def test_state_isolation(self):
        s1 = await state_manager.get_state("niyati", 1, 99)
        s2 = await state_manager.get_state("palak", 1, 99)
        s3 = await state_manager.get_state("niyati", 1, 100)
        
        self.assertNotEqual(id(s1), id(s2))
        self.assertNotEqual(id(s1), id(s3))
        self.assertEqual(s1.bot_name, "niyati")
        self.assertEqual(s2.bot_name, "palak")

    async def test_clamping(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.mood.irritation = 1.5
        s.mood.playfulness = -0.5
        s.clamp_all()
        self.assertEqual(s.mood.irritation, 1.0)
        self.assertEqual(s.mood.playfulness, 0.0)

    async def test_deterministic_decay(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.mood.irritation = 1.0
        s.mood.embarrassment = 1.0
        s.mood.sadness = 1.0
        
        now = datetime.now(timezone.utc)
        s.last_updated_at = now - timedelta(hours=1)
        
        state_manager.apply_decay(s, now)
        self.assertAlmostEqual(s.mood.embarrassment, 0.0, places=2)
        self.assertAlmostEqual(s.mood.irritation, 0.67, places=2)
        self.assertAlmostEqual(s.mood.sadness, 0.92, places=2)

    def test_daily_life_stable(self):
        s1 = DailyLifeGenerator.generate("niyati", "2026-08-05")
        s2 = DailyLifeGenerator.generate("niyati", "2026-08-05")
        s3 = DailyLifeGenerator.generate("palak", "2026-08-05")
        
        self.assertEqual(s1.current_activity, s2.current_activity)
        self.assertNotEqual(s1.current_activity, s3.current_activity)
        
    async def test_playful_teasing_familiar(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.relationship.familiarity = 0.5 # Familiar
        s.relationship.trust = 0.5
        
        appraisal = AppraisalEngine.appraise("tum pagal ho", relationship=s.relationship)
        self.assertTrue(appraisal.is_playful_teasing)
        
        EmotionEngine.apply_appraisal(s, appraisal)
        self.assertGreater(s.mood.playfulness, 0.5)

    async def test_teasing_unknown(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.relationship.familiarity = 0.1 # Unknown
        
        appraisal = AppraisalEngine.appraise("tum pagal ho", relationship=s.relationship)
        self.assertTrue(appraisal.is_serious_insult)
        
        EmotionEngine.apply_appraisal(s, appraisal)
        self.assertGreater(s.mood.irritation, 0.0)

    async def test_sadness_reduces_teasing(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.mood.playfulness = 0.8
        
        appraisal = AppraisalEngine.appraise("main bahut dukhi hu", relationship=s.relationship)
        self.assertTrue(appraisal.is_user_sad)
        
        EmotionEngine.apply_appraisal(s, appraisal)
        self.assertLess(s.mood.playfulness, 0.8)

    async def test_arjun_target_niyati(self):
        appraisal = AppraisalEngine.appraise("Arjun kon hai")
        self.assertEqual(appraisal.target_bot, "niyati")
        
        s_palak = await state_manager.get_state("palak", 1, 99)
        decision = ConversationPolicy.decide_action(s_palak, appraisal, is_group=True)
        self.assertFalse(decision.should_respond)
        self.assertEqual(decision.action, ConversationAction.STAY_SILENT)

    async def test_integration_repair_mistake(self):
        # 1. Setup Palak state with repair event
        s_palak = await state_manager.get_state("palak", 1, 99)
        
        # 2. User says "maine Niyati se pucha tha"
        appraisal = AppraisalEngine.appraise("maine niyati se pucha tha")
        self.assertTrue(appraisal.is_correction)
        
        # 3. Emotion update
        EmotionEngine.apply_appraisal(s_palak, appraisal)
        self.assertIn("repair_interruption", s_palak.unresolved_events)
        self.assertGreater(s_palak.mood.embarrassment, 0.0)
        
        # 4. Decision
        decision = ConversationPolicy.decide_action(s_palak, appraisal, is_group=True)
        self.assertEqual(decision.action, ConversationAction.REPAIR_MISTAKE)
        self.assertNotIn("repair_interruption", s_palak.unresolved_events)
        
    async def test_simple_acknowledgement(self):
        s = await state_manager.get_state("niyati", 1, 99)
        appraisal = AppraisalEngine.appraise("acha")
        self.assertEqual(appraisal.intent, "acknowledgement")
        
        # In group, acha -> silence
        decision_group = ConversationPolicy.decide_action(s, appraisal, is_group=True)
        self.assertFalse(decision_group.should_respond)
        
        # In private, acha -> acknowledge
        decision_private = ConversationPolicy.decide_action(s, appraisal, is_group=False)
        self.assertTrue(decision_private.should_respond)
        self.assertEqual(decision_private.action, ConversationAction.ACKNOWLEDGE)

if __name__ == "__main__":
    unittest.main()
