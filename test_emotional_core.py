import unittest
import asyncio
from datetime import datetime, timezone, timedelta
from emotional_core.models import MoodState, NeedState, RelationshipState, CharacterRuntimeState, ConversationAction, EmotionalInputContext, UnresolvedEvent
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
        
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=10, text="tum pagal ho", is_group=False)
        appraisal = AppraisalEngine.appraise(ctx, relationship=s.relationship)
        self.assertTrue(appraisal.is_playful_teasing)
        
        EmotionEngine.apply_appraisal(s, appraisal, 10)
        self.assertGreater(s.mood.playfulness, 0.5)

    async def test_teasing_unknown(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.relationship.familiarity = 0.1 # Unknown
        
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=10, text="tum pagal ho", is_group=False)
        appraisal = AppraisalEngine.appraise(ctx, relationship=s.relationship)
        self.assertTrue(appraisal.is_serious_insult)
        
        EmotionEngine.apply_appraisal(s, appraisal, 10)
        self.assertGreater(s.mood.irritation, 0.0)

    async def test_sadness_reduces_teasing(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.mood.playfulness = 0.8
        
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=10, text="main bahut dukhi hu", is_group=False)
        appraisal = AppraisalEngine.appraise(ctx, relationship=s.relationship)
        self.assertTrue(appraisal.is_user_sad)
        
        EmotionEngine.apply_appraisal(s, appraisal, 10)
        self.assertLess(s.mood.playfulness, 0.8)

    async def test_arjun_target_niyati(self):
        ctx = EmotionalInputContext(bot_name="palak", chat_id=1, user_id=99, message_id=10, text="Arjun kon hai", is_group=True)
        appraisal = AppraisalEngine.appraise(ctx)
        self.assertEqual(appraisal.target_bot, "niyati")
import unittest
import asyncio
from datetime import datetime, timezone, timedelta
from emotional_core.models import MoodState, NeedState, RelationshipState, CharacterRuntimeState, ConversationAction, EmotionalInputContext, UnresolvedEvent
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
        
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=10, text="tum pagal ho", is_group=False)
        appraisal = AppraisalEngine.appraise(ctx, relationship=s.relationship)
        self.assertTrue(appraisal.is_playful_teasing)
        
        EmotionEngine.apply_appraisal(s, appraisal, 10)
        self.assertGreater(s.mood.playfulness, 0.5)

    async def test_teasing_unknown(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.relationship.familiarity = 0.1 # Unknown
        
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=10, text="tum pagal ho", is_group=False)
        appraisal = AppraisalEngine.appraise(ctx, relationship=s.relationship)
        self.assertTrue(appraisal.is_serious_insult)
        
        EmotionEngine.apply_appraisal(s, appraisal, 10)
        self.assertGreater(s.mood.irritation, 0.0)

    async def test_sadness_reduces_teasing(self):
        s = await state_manager.get_state("niyati", 1, 99)
        s.mood.playfulness = 0.8
        
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=10, text="main bahut dukhi hu", is_group=False)
        appraisal = AppraisalEngine.appraise(ctx, relationship=s.relationship)
        self.assertTrue(appraisal.is_user_sad)
        
        EmotionEngine.apply_appraisal(s, appraisal, 10)
        self.assertLess(s.mood.playfulness, 0.8)

    async def test_arjun_target_niyati(self):
        ctx = EmotionalInputContext(bot_name="palak", chat_id=1, user_id=99, message_id=10, text="Arjun kon hai", is_group=True)
        appraisal = AppraisalEngine.appraise(ctx)
        self.assertEqual(appraisal.target_bot, "niyati")
        
        s_palak = await state_manager.get_state("palak", 1, 99)
        decision = ConversationPolicy.decide_action(s_palak, appraisal, is_group=True)
        self.assertFalse(decision.should_respond)
        self.assertEqual(decision.action, ConversationAction.STAY_SILENT)

    async def test_integration_repair_mistake(self):
        s_palak = await state_manager.get_state("palak", 1, 99)
        
        # Simulating palak previously responded
        ctx1 = EmotionalInputContext(bot_name="palak", chat_id=1, user_id=99, message_id=10, text="...", is_group=True, previous_character_action="ANSWER")
        appraisal1 = AppraisalEngine.appraise(ctx1, s_palak.relationship)
        EmotionEngine.apply_appraisal(s_palak, appraisal1, 10)
        await state_manager.save_state(s_palak)
        
        # User corrects palak
        ctx2 = EmotionalInputContext(bot_name="palak", chat_id=1, user_id=99, message_id=11, text="maine niyati se pucha tha", is_group=True, previous_character_action="ANSWER")
        appraisal2 = AppraisalEngine.appraise(ctx2, s_palak.relationship)
        self.assertTrue(appraisal2.is_correction)
        
        EmotionEngine.apply_appraisal(s_palak, appraisal2, 11)
        self.assertTrue(any(e.type == "repair_interruption" for e in s_palak.unresolved_events))
        self.assertGreater(s_palak.mood.embarrassment, 0.0)
        
        decision = ConversationPolicy.decide_action(s_palak, appraisal2, is_group=True, context=ctx2)
        self.assertEqual(decision.action, ConversationAction.REPAIR_MISTAKE)
        # Should now be resolved
        self.assertTrue(all(e.resolved for e in s_palak.unresolved_events if e.type == "repair_interruption"))

    async def test_simple_acknowledgement(self):
        s = await state_manager.get_state("niyati", 1, 99)
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=10, text="acha", is_group=False)
        appraisal = AppraisalEngine.appraise(ctx)
        self.assertEqual(appraisal.intent, "acknowledgement")
        
        decision_group = ConversationPolicy.decide_action(s, appraisal, is_group=True)
        self.assertFalse(decision_group.should_respond)
        
        decision_private = ConversationPolicy.decide_action(s, appraisal, is_group=False)
        self.assertTrue(decision_private.should_respond)
        self.assertEqual(decision_private.action, ConversationAction.ACKNOWLEDGE)

    async def test_atomic_mutation_concurrency(self):
        s = await state_manager.get_state("niyati", 1, 99)
        self.assertEqual(s.relationship.interaction_count, 0)
        
        async def mutate_once(i):
            def mutator(st):
                st.relationship.interaction_count += 1
            await state_manager.mutate_state("niyati", 1, 99, mutator)
            
        tasks = [mutate_once(i) for i in range(50)]
        await asyncio.gather(*tasks)
        
        final_state = await state_manager.get_state("niyati", 1, 99)
        self.assertEqual(final_state.relationship.interaction_count, 50)
        
    async def test_idempotent_appraisal(self):
        s = await state_manager.get_state("niyati", 1, 99)
        self.assertEqual(s.relationship.interaction_count, 0)
        
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=55, text="tum pagal ho", is_group=False)
        appraisal = AppraisalEngine.appraise(ctx, relationship=s.relationship)
        
        # Apply first time
        EmotionEngine.apply_appraisal(s, appraisal, 55)
        self.assertEqual(s.relationship.interaction_count, 1)
        self.assertEqual(len(s.processed_events), 1)
        
        # Apply second time (retry)
        EmotionEngine.apply_appraisal(s, appraisal, 55)
        # Should not increment again
        self.assertEqual(s.relationship.interaction_count, 1)

if __name__ == "__main__":
    unittest.main()
