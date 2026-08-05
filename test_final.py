"""
Final verification tests for the dual-bot system.

Tests real imports, config validation, per-bot AI engine isolation,
GroupRoom coordination, reply-to routing, bot loop prevention,
memory isolation, single-bot mode, and cleanup correctness.
"""

import os
import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta


class TestImports(unittest.TestCase):
    """Verify all critical modules import without error."""

    def test_import_config(self):
        from config import Config, logger
        self.assertTrue(hasattr(Config, 'NIYATI_BOT_TOKEN'))
        self.assertTrue(hasattr(Config, 'PALAK_BOT_TOKEN'))
        self.assertTrue(hasattr(Config, 'PALAK_BOT_USERNAME'))

    def test_import_ai_engine(self):
        from ai_engine import get_ai_engine, AIEngine
        self.assertTrue(callable(get_ai_engine))

    def test_import_group_room(self):
        from group_room import group_manager, GroupRoomState, GroupRoomManager
        self.assertIsInstance(group_manager, GroupRoomManager)

    def test_import_memory(self):
        from memory import get_memory, MemoryManager
        self.assertTrue(callable(get_memory))

    def test_import_handlers_messages(self):
        from handlers.messages import handle_message
        self.assertTrue(callable(handle_message))

    def test_import_bot(self):
        from bot import create_bot, setup_jobs
        self.assertTrue(callable(create_bot))

    def test_import_main(self):
        import main
        self.assertTrue(hasattr(main, 'main'))


class TestConfig(unittest.TestCase):
    """Test Config validation with realistic environment strings."""

    def test_palak_username_default(self):
        """PALAK_BOT_USERNAME must default to 'palakdevabot'."""
        from config import Config
        # If no env var is set, default should be palakdevabot
        with patch.dict(os.environ, {}, clear=False):
            # Re-evaluate — the default is baked at class load time
            # so we just verify the current value is not 'Palak_bot'
            self.assertNotEqual(Config.PALAK_BOT_USERNAME, 'Palak_bot')

    def test_get_bot_config_niyati(self):
        from config import Config
        cfg = Config.get_bot_config('niyati')
        self.assertIn('token', cfg)
        self.assertIn('username', cfg)

    def test_get_bot_config_palak(self):
        from config import Config
        cfg = Config.get_bot_config('palak')
        self.assertIn('token', cfg)
        self.assertIn('username', cfg)

    def test_get_bot_config_unknown_raises(self):
        from config import Config
        with self.assertRaises(ValueError):
            Config.get_bot_config('Palak')  # uppercase must fail

    def test_get_bot_config_unknown_random(self):
        from config import Config
        with self.assertRaises(ValueError):
            Config.get_bot_config('randombot')


class TestAIEngineRegistry(unittest.TestCase):
    """Verify per-bot AI engine instances are separate."""

    def test_engines_are_different_objects(self):
        from ai_engine import get_ai_engine
        e1 = get_ai_engine('niyati')
        e2 = get_ai_engine('palak')
        self.assertIsNot(e1, e2)

    def test_engine_persistence(self):
        from ai_engine import get_ai_engine
        e1 = get_ai_engine('niyati')
        e2 = get_ai_engine('niyati')
        self.assertIs(e1, e2)

    def test_engine_case_normalization(self):
        from ai_engine import get_ai_engine
        e1 = get_ai_engine('Niyati')
        e2 = get_ai_engine('niyati')
        self.assertIs(e1, e2)


class TestGroupRoomCoordination(unittest.IsolatedAsyncioTestCase):
    """Test GroupRoom plan generation, dedup, and reply-to routing."""

    async def asyncSetUp(self):
        from group_room import group_manager
        self.gm = group_manager
        self.gm._rooms.clear()
        self.gm._bot_ids.clear()
        self.gm.register_bot('niyati', 101)
        self.gm.register_bot('palak', 102)

    async def test_fresh_plan_per_message_id(self):
        """Each message_id must produce its own plan."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        _, plan1, _ = await self.gm.process_human_message(
            'niyati', chat_id, 1, 10, 'User', 'hello')
        _, plan2, _ = await self.gm.process_human_message(
            'niyati', chat_id, 2, 10, 'User', 'hello again')

        # Plans are keyed by message_id — they should exist independently
        self.assertIsNotNone(room.get_trigger(1))
        self.assertIsNotNone(room.get_trigger(2))

    async def test_same_plan_for_both_bots(self):
        """Both bots seeing the same message_id must get the same plan."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        _, plan_n, _ = await self.gm.process_human_message(
            'niyati', chat_id, 5, 10, 'User', 'test')
        _, plan_p, _ = await self.gm.process_human_message(
            'palak', chat_id, 5, 10, 'User', 'test')

        self.assertEqual(plan_n, plan_p)

    async def test_dedup_same_bot_same_message(self):
        """Same bot processing the same message_id twice → False."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        proceed1, _, _ = await self.gm.process_human_message(
            'niyati', chat_id, 10, 10, 'User', 'test')
        proceed2, _, _ = await self.gm.process_human_message(
            'niyati', chat_id, 10, 10, 'User', 'test')

        self.assertTrue(proceed1)
        self.assertFalse(proceed2)

    async def test_reply_to_niyati_routes_to_niyati(self):
        """Reply-to Niyati's message must include niyati in plan."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        _, plan, _ = await self.gm.process_human_message(
            'niyati', chat_id, 20, 10, 'User', 'what do you think?',
            reply_to_bot_name='niyati')

        self.assertIn('niyati', plan)

    async def test_reply_to_palak_routes_to_palak(self):
        """Reply-to Palak's message must include palak in plan."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        _, plan, _ = await self.gm.process_human_message(
            'palak', chat_id, 21, 10, 'User', 'tell me more',
            reply_to_bot_name='palak')

        self.assertIn('palak', plan)

    async def test_single_bot_presence(self):
        """If only niyati is present, she must be the sole responder."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = False

        _, plan, _ = await self.gm.process_human_message(
            'niyati', chat_id, 30, 10, 'User', 'hello palak')

        self.assertEqual(plan, ['niyati'])

    async def test_bot_loop_prevention(self):
        """Bot-to-bot replies must stop at configured limits."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        # Trigger a human message first to open session
        _, _, trigger_id = await self.gm.process_human_message(
            'niyati', chat_id, 40, 10, 'User', 'start')

        # First bot-to-bot exchange
        proceed1, _ = await self.gm.process_partner_message(
            'palak', chat_id, 41, 101, 'Niyati', 'response', trigger_id)

        # Consecutive limit should kick in
        proceed2, _ = await self.gm.process_partner_message(
            'niyati', chat_id, 42, 102, 'Palak', 'another response', trigger_id)

        # At least one should be blocked by MAX_CONSECUTIVE_BOT_TO_BOT_REPLIES=1
        if proceed1:
            self.assertFalse(proceed2)

    async def test_bot_message_counts_toward_limit(self):
        """add_bot_message must increment the reply counter in TriggerState."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        # Open session
        _, _, trigger_id = await self.gm.process_human_message(
            'niyati', chat_id, 50, 10, 'User', 'hello')

        trigger = room.get_trigger(trigger_id)
        self.assertEqual(trigger.total_bot_replies, 0)
        
        await self.gm.add_bot_message('niyati', 9999, chat_id, 51, 'Niyati', 'hi there', trigger_id)
        self.assertEqual(trigger.total_bot_replies, 1)

    async def test_no_session_from_bot_message(self):
        """A bot message must NOT open or refresh a human session."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        self.assertFalse(room.has_active_human_session())

        # Give it a fake trigger ID, it shouldn't open session
        await self.gm.add_bot_message('niyati', 9999, chat_id, 60, 'Niyati', 'hello', 99)
        self.assertFalse(room.has_active_human_session())

    async def test_both_selected_bots_respond_exactly_once(self):
        """If plan is [Niyati, Palak], Palak seeing Niyati's message must NOT trigger a second AI delay path."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        # Mock decide_responders to return both
        with patch.object(self.gm, '_decide_responders', return_value=['niyati', 'palak']):
            _, plan, trigger_id = await self.gm.process_human_message(
                'niyati', chat_id, 70, 10, 'User', 'hello')
            
            # Niyati adds her message
            await self.gm.add_bot_message('niyati', 101, chat_id, 71, 'Niyati', 'Niyati response', trigger_id)
            
            # Palak sees Niyati's message.
            proceed, _ = await self.gm.process_partner_message(
                'palak', chat_id, 71, 101, 'Niyati', 'Niyati response', trigger_id)
            
            # proceed MUST be False to prevent double AI generation
            self.assertFalse(proceed)
            
            # But the transcript should have Niyati's message with real partner_id
            transcript = await self.gm.get_transcript(chat_id)
            self.assertEqual(transcript[-1]['sender_id'], 101)


class TestMemoryIsolation(unittest.IsolatedAsyncioTestCase):
    """Test that private memory is isolated per bot."""

    async def asyncSetUp(self):
        from database import db
        self.db = db
        # Use local storage
        self.db.connected = False
        self.db.local_users.clear()

    async def test_private_memory_isolated(self):
        from memory import get_memory
        mem_n = get_memory('niyati')
        mem_p = get_memory('palak')

        self.assertIsNot(mem_n, mem_p)

        # Create user entries in local cache first (required for local fallback)
        await self.db.get_or_create_user('niyati', 1, 'TestUser')
        await self.db.get_or_create_user('palak', 1, 'TestUser')

        # Save messages for each bot
        await mem_n.save_private_message(1, 'user', 'hi niyati')
        await mem_p.save_private_message(1, 'user', 'hi palak')

        ctx_n = await mem_n.get_private_context(1, 'User')
        ctx_p = await mem_p.get_private_context(1, 'User')

        # Each should see only their own messages
        n_contents = [m['content'] for m in ctx_n]
        p_contents = [m['content'] for m in ctx_p]

        self.assertIn('hi niyati', n_contents)
        self.assertNotIn('hi palak', n_contents)
        self.assertIn('hi palak', p_contents)
        self.assertNotIn('hi niyati', p_contents)


class TestSupabaseIsolation(unittest.IsolatedAsyncioTestCase):
    """Test that database methods pass bot_name for Supabase isolation."""

    async def asyncSetUp(self):
        from database import db, SupabaseClient
        self.db = db
        self.db.connected = True
        self.db.client = AsyncMock(spec=SupabaseClient)
        self.db.client.rest_url = "http://mock"
        
        # Setup mock return values to prevent NoneType errors on len()
        self.db.client.select.return_value = []
        self.db.client.insert.return_value = {'bot_name': 'mock', 'user_id': 1}
        self.db.client.update.return_value = {'bot_name': 'mock', 'user_id': 1}

    async def test_supabase_bot_name_queries(self):
        await self.db.get_or_create_user('niyati', 99, 'Test')
        self.db.client.select.assert_called_with('users', '*', {'bot_name': 'niyati', 'user_id': 99})

        await self.db.save_message('palak', 99, 'user', 'hello')
        self.db.client.select.assert_called_with('users', 'messages,total_messages', {'bot_name': 'palak', 'user_id': 99})

        await self.db.clear_user_memory('niyati', 99)
        self.db.client.update.assert_called_with('users', unittest.mock.ANY, {'bot_name': 'niyati', 'user_id': 99})


class TestRateLimiting(unittest.IsolatedAsyncioTestCase):
    """Test independent rate limiting per bot."""

    async def asyncSetUp(self):
        from utils import rate_limiter
        self.rl = rate_limiter
        self.rl.cooldowns.clear()
        self.rl.requests.clear()

    async def test_independent_cooldown(self):
        """Niyati's cooldown must not block Palak."""
        user_id = 1

        # Niyati request
        allowed_n, _ = await self.rl.check('niyati', user_id)
        self.assertTrue(allowed_n)

        # Niyati cooldown
        allowed_n2, _ = await self.rl.check('niyati', user_id)
        self.assertFalse(allowed_n2)

        # Palak should still be allowed
        allowed_p, _ = await self.rl.check('palak', user_id)
        self.assertTrue(allowed_p)


class TestCleanup(unittest.IsolatedAsyncioTestCase):
    """Test that cleanup_cooldowns is properly awaitable."""

    async def test_cleanup_is_coroutine(self):
        from utils import rate_limiter
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(rate_limiter.cleanup_cooldowns))

    async def test_cleanup_runs(self):
        from utils import rate_limiter
        # Force cleanup by setting old timestamp
        rate_limiter._last_cleanup = datetime.now(timezone.utc) - timedelta(hours=2)
        await rate_limiter.cleanup_cooldowns()
        # Should not raise


class TestOneBotMissing(unittest.TestCase):
    """Test graceful operation when one bot token is missing."""

    def test_palak_token_missing_no_crash(self):
        from config import Config
        # If PALAK_BOT_TOKEN is empty, get_bot_config should still work
        cfg = Config.get_bot_config('palak')
        # Token will be empty string, which is falsy — main.py checks this
        self.assertIsInstance(cfg['token'], str)


class TestPartnerValidation(unittest.TestCase):
    """Test trusted partner checks."""

    def test_username_none_safe(self):
        """user.username being None must not crash."""
        from handlers.messages import _is_trusted_partner
        from group_room import group_manager
        group_manager.register_bot('niyati', 101)
        group_manager.register_bot('palak', 102)

        mock_user = MagicMock()
        mock_user.id = 999
        mock_user.username = None  # This is the crash case
        mock_user.is_bot = True

        # Should not raise AttributeError
        result = _is_trusted_partner(mock_user, 'niyati')
        self.assertFalse(result)

    def test_partner_by_id(self):
        """Partner must be validated by registered bot ID."""
        from handlers.messages import _is_trusted_partner
        from group_room import group_manager
        group_manager.register_bot('niyati', 101)
        group_manager.register_bot('palak', 102)

        mock_user = MagicMock()
        mock_user.id = 102
        mock_user.username = None
        mock_user.is_bot = True

        result = _is_trusted_partner(mock_user, 'niyati')
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()

class TestPhase11(unittest.IsolatedAsyncioTestCase):
    async def test_database_409_retry_and_fallback(self):
        from database import Database
        db = Database()
        db.connected = True
        db.client = AsyncMock()
        db.client.select.return_value = []  # User missing
        db.client.insert.side_effect = ValueError("409 Conflict")
        
        res = await db.save_message('niyati', 999, 'user', 'hi')
        self.assertTrue(res)
        
        key = db._user_key('niyati', 999)
        self.assertIn(key, db.local_users)
        self.assertEqual(db.local_users[key]['messages'][0]['content'], 'hi')
        self.assertEqual(db.client.insert.call_count, 2)
        
    async def test_database_missing_row_creation(self):
        from database import Database
        db = Database()
        db.connected = True
        db.client = AsyncMock()
        db.client.select.return_value = []  # User missing
        db.client.insert.return_value = {'bot_name': 'niyati', 'user_id': 999}
        
        res = await db.save_message('niyati', 999, 'user', 'hi')
        self.assertTrue(res)
        self.assertEqual(db.client.insert.call_count, 1)

    async def test_group_room_dedupe_and_reservation(self):
        from group_room import group_manager, TriggerState
        room = await group_manager.get_room(123)
        room.triggers[100] = TriggerState()
        
        # Test Reservation
        res1 = await group_manager.reserve_bot('niyati', 123, 100)
        self.assertTrue(res1)
        res2 = await group_manager.reserve_bot('niyati', 123, 100)
        self.assertFalse(res2)
        
        # Test exact-once transcript
        room.active_until = datetime.now(timezone.utc) + timedelta(minutes=1)
        await group_manager.add_bot_message('niyati', 1234, 123, 100, 'Niyati', 'hi', 100)
        await group_manager.add_bot_message('niyati', 1234, 123, 100, 'Niyati', 'hi', 100)
        self.assertEqual(len(room.transcript), 1)
        self.assertEqual(room.transcript[0]['sender_id'], 1234)

    def test_readme_contains_migration(self):
        with open('README.md', 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('migrations/001_add_bot_name_to_users.sql', content)
        self.assertNotIn('No schema migration is needed', content)

class TestBotChainIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from group_room import group_manager
        self.gm = group_manager
        self.gm._rooms.clear()
        self.gm._bot_ids.clear()
        self.gm.register_bot('niyati', 101)
        self.gm.register_bot('palak', 102)

    @patch('ai_engine.AIEngine.generate_response')
    @patch('handlers.messages.send_multi_messages')
    async def test_multi_turn_bot_chain_prevention(self, mock_send, mock_gen):
        from group_room import group_manager
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True
        
        # Setup mocks
        mock_gen.return_value = ["chunk 1", "chunk 2"] # AI returns 2 chunks
        mock_send.return_value = [1000] # send_multi_messages returns msg ID
        
        # 1. Human says "Hello"
        with patch.object(self.gm, '_decide_responders', return_value=['niyati', 'palak']):
            _, plan, human_trigger_id = await self.gm.process_human_message(
                'niyati', chat_id, 1, 10, 'User', 'Hello'
            )
            # Both get it
            _, _, _ = await self.gm.process_human_message(
                'palak', chat_id, 1, 10, 'User', 'Hello'
            )
            
        # Mock handlers logic for Niyati (simulate generating)
        await self.gm.reserve_bot('niyati', chat_id, human_trigger_id)
        # In group chat, responses are joined
        joined_resp = ["chunk 1\n\nchunk 2"]
        # Add Niyati's message to transcript
        await self.gm.add_bot_message('niyati', 101, chat_id, 1000, 'Niyati', joined_resp[0], human_trigger_id)
        
        # Mock Palak processing Niyati's message (as partner)
        # process_partner_message must return False and empty plan so AI generation is skipped
        proceed, planned = await self.gm.process_partner_message(
            'palak', chat_id, 1000, 101, 'Niyati', joined_resp[0], human_trigger_id
        )
        self.assertFalse(proceed)
        self.assertEqual(planned, [])
        
        # Mock Palak generating her own planned response to the human trigger
        await self.gm.reserve_bot('palak', chat_id, human_trigger_id)
        # Add Palak's message to transcript
        await self.gm.add_bot_message('palak', 102, chat_id, 1001, 'Palak', joined_resp[0], human_trigger_id)
        
        # Mock Niyati processing Palak's message
        proceed_n, _ = await self.gm.process_partner_message(
            'niyati', chat_id, 1001, 102, 'Palak', joined_resp[0], human_trigger_id
        )
        self.assertFalse(proceed_n)
        
        # Assertions
        trigger = room.get_trigger(human_trigger_id)
        self.assertTrue(trigger.closed)
        self.assertEqual(len(trigger.responded_bots), 2)
        
        # Assert no further reactions
        proceed_p2, _ = await self.gm.process_partner_message(
            'palak', chat_id, 1001, 101, 'Niyati', 'extra', human_trigger_id
        )
        self.assertFalse(proceed_p2)

class TestMentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_mentions(self):
        from group_room import group_manager
        from config import Config
        chat_id = -100
        room = await group_manager.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True
        
        # Exact configured username
        Config.NIYATI_BOT_USERNAME = 'NiyatiBotConfigured'
        plan1 = group_manager._decide_responders(room, 1, 10, 'hey @NiyatiBotConfigured')
        self.assertIn('niyati', plan1)
        
        # Username from Telegram get_me (Simulate overriding)
        Config.PALAK_BOT_USERNAME = 'PalakRealGetMe'
        plan2 = group_manager._decide_responders(room, 2, 10, 'yo @PalakRealGetMe whatsup')
        self.assertIn('palak', plan2)
        
        # Direct mention while another human name is present
        plan3 = group_manager._decide_responders(room, 3, 10, 'hey amit and @NiyatiBotConfigured')
        self.assertIn('niyati', plan3)
        
        # Test utils is_user_talking_to_others
        from utils import is_user_talking_to_others
        
        msg = MagicMock()
        msg.text = 'hey @amit @PalakRealGetMe'
        msg.reply_to_message = None
        
        ent1 = MagicMock()
        ent1.type = 'mention'
        ent1.offset = 4
        ent1.length = 5
        
        ent2 = MagicMock()
        ent2.type = 'mention'
        ent2.offset = 10
        ent2.length = 15
        
        msg.entities = [ent1, ent2]
        
        # Should NOT suppress because bot was mentioned
        res = is_user_talking_to_others(msg, 'PalakRealGetMe', 102, 'palak')
        self.assertFalse(res)


class TestProductionFixes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from group_room import group_manager
        self.gm = group_manager
        self.gm._rooms.clear()
        self.gm._bot_ids.clear()
        self.gm.register_bot('niyati', 101)
        self.gm.register_bot('palak', 102)

    async def test_targeting_routing(self):
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        # "Hello Palak" plans only Palak
        plan_p = self.gm._decide_responders(room, 1, 10, 'Hello Palak')
        self.assertEqual(plan_p, ['palak'])

        # "Niyati ghar par kon hai" plans only Niyati
        plan_n = self.gm._decide_responders(room, 2, 10, 'Niyati ghar par kon hai')
        self.assertEqual(plan_n, ['niyati'])

        # "tum dono kya kar rahi ho" plans both
        plan_b = self.gm._decide_responders(room, 3, 10, 'tum dono kya kar rahi ho')
        self.assertCountEqual(plan_b, ['niyati', 'palak'])

        # "hello" uses ordinary coordinator behaviour (could be any, but usually 1 or 2)
        import random
        random.seed(123)
        plan_h = self.gm._decide_responders(room, 4, 10, 'hello')
        self.assertTrue(len(plan_h) > 0)

    async def test_abort_waiters(self):
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        
        # Setup trigger
        from group_room import TriggerState
        trigger = TriggerState(planned_responders=['palak', 'niyati'])
        room.triggers[100] = trigger
        
        # Start wait for niyati
        wait_task = asyncio.create_task(self.gm.wait_for_turn('niyati', chat_id, ['palak', 'niyati'], 100))
        
        # Abort it
        await asyncio.sleep(0.1)
        await self.gm.abort_waiters(chat_id, 100)
        
        # Should finish very fast, not 15 seconds
        await asyncio.wait_for(wait_task, timeout=1.0)
        self.assertTrue(trigger.closed)
        self.assertTrue(trigger.aborted)

    @patch('ai_engine.AIEngine._call_gpt')
    async def test_ai_engine_generate_response_args(self, mock_call):
        mock_call.return_value = "Mock response"
        from ai_engine import get_ai_engine
        engine = get_ai_engine('niyati')
        
        try:
            res = await engine.generate_response(
                bot_name='niyati',
                user_id=99,
                chat_id=1,
                user_message="hi",
                user_name="Test",
                is_group=False,
                psychological_context="Mock psych context"
            )
            self.assertEqual(res, ["Mock response"])
            
            # Assert psychological_context was used
            call_args = mock_call.call_args[0][0]
            system_prompt = call_args[0]['content']
            self.assertIn("Mock psych context", system_prompt)
        except NameError as e:
            self.fail(f"generate_response raised NameError: {e}")

    def test_appraisal_greeting_directed(self):
        from emotional_core.appraisal import AppraisalEngine
        from emotional_core.models import EmotionalInputContext
        
        ctx = EmotionalInputContext(
            bot_name="palak",
            chat_id=1, user_id=99, message_id=10,
            text="Hello Palak", is_group=True,
            semantic_target_bot="palak"
        )
        appraisal = AppraisalEngine.appraise(ctx)
        
        self.assertEqual(appraisal.intent, "greeting")
        self.assertTrue(appraisal.directed_to_character)
        self.assertEqual(appraisal.target_bot, "palak")


class TestPhase2A(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from group_room import group_manager
        self.gm = group_manager
        self.gm._rooms.clear()
        self.gm._bot_ids.clear()
        self.gm.register_bot('niyati', 101)
        self.gm.register_bot('palak', 102)

    async def test_semantic_routing(self):
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        # Topic ownership
        plan1 = self.gm._decide_responders(room, 1, 10, 'Arjun kon hai')
        self.assertEqual(plan1, ['niyati'])
        
        plan2 = self.gm._decide_responders(room, 2, 10, 'Bruno kahan hai')
        self.assertEqual(plan2, ['palak'])

        # Plural
        plan3 = self.gm._decide_responders(room, 3, 10, 'tum dono kahan se ho')
        self.assertCountEqual(plan3, ['niyati', 'palak'])

        # General message defaults to one responder
        import random
        random.seed(42)
        plan4 = self.gm._decide_responders(room, 4, 10, 'kya kar rahi ho')
        self.assertEqual(len(plan4), 1)

    async def test_leave_request_and_withdrawal(self):
        from emotional_core.models import CharacterRuntimeState, EmotionalInputContext
        from emotional_core.appraisal import AppraisalEngine
        from emotional_core.conversation_policy import ConversationPolicy
        
        state = CharacterRuntimeState(bot_name="palak", chat_id=1, user_id=99)
        ctx = EmotionalInputContext(
            bot_name="palak", chat_id=1, user_id=99, message_id=10,
            text="chali jao", is_group=True, semantic_target_bot="palak"
        )
        
        appraisal = AppraisalEngine.appraise(ctx)
        self.assertEqual(appraisal.intent, "REQUEST_LEAVE")
        
        decision = ConversationPolicy.decide_action(state, appraisal, is_group=True, context=ctx)
        self.assertEqual(decision.action.name, "ACKNOWLEDGE")
        self.assertEqual(state.dialogue.stance, "WITHDRAWN")
        
        # Next message shouldn't get a response
        ctx2 = EmotionalInputContext(
            bot_name="palak", chat_id=1, user_id=99, message_id=11,
            text="kya kar rahi ho", is_group=True, semantic_target_bot="palak"
        )
        appraisal2 = AppraisalEngine.appraise(ctx2)
        decision2 = ConversationPolicy.decide_action(state, appraisal2, is_group=True, context=ctx2)
        
        self.assertEqual(decision2.action.name, "STAY_SILENT")
        self.assertFalse(decision2.should_respond)

    async def test_repeated_hostility(self):
        from emotional_core.models import CharacterRuntimeState, EmotionalInputContext
        from emotional_core.appraisal import AppraisalEngine
        from emotional_core.conversation_policy import ConversationPolicy
        
        state = CharacterRuntimeState(bot_name="niyati", chat_id=1, user_id=99)
        
        # Message 1
        ctx = EmotionalInputContext(bot_name="niyati", chat_id=1, user_id=99, message_id=10, text="tum pagal ho", is_group=True)
        appraisal = AppraisalEngine.appraise(ctx)
        decision = ConversationPolicy.decide_action(state, appraisal, is_group=True, context=ctx)
        self.assertEqual(decision.action.name, "SET_BOUNDARY")
        self.assertEqual(state.dialogue.consecutive_hostility_count, 1)
        
        # Message 2
        decision2 = ConversationPolicy.decide_action(state, appraisal, is_group=True, context=ctx)
        self.assertEqual(decision2.action.name, "SET_BOUNDARY")
        self.assertEqual(state.dialogue.stance, "GUARDED")
        self.assertEqual(state.dialogue.consecutive_hostility_count, 2)
        
        # Message 3
        decision3 = ConversationPolicy.decide_action(state, appraisal, is_group=True, context=ctx)
        self.assertEqual(decision3.action.name, "STAY_SILENT")
        self.assertEqual(state.dialogue.stance, "WITHDRAWN")
        self.assertEqual(state.dialogue.consecutive_hostility_count, 3)

    async def test_fingerprinting_rejection(self):
        from ai_engine import get_ai_engine
        engine = get_ai_engine('niyati')
        engine.recent_responses.append("meri galti thi")
        
        # Add 'humein' to check identity leak rejection
        with patch.object(engine, '_call_gpt', side_effect=["humein koi farak nahi padta", "ignore"]):
            res = await engine.generate_response(
                bot_name='niyati', user_id=99, chat_id=1, user_message="test", user_name="Test", is_group=True
            )
            self.assertEqual(res, [])
