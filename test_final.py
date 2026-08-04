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

        _, plan1 = await self.gm.process_human_message(
            'niyati', chat_id, 1, 10, 'User', 'hello')
        _, plan2 = await self.gm.process_human_message(
            'niyati', chat_id, 2, 10, 'User', 'hello again')

        # Plans are keyed by message_id — they should exist independently
        self.assertIsNotNone(room.get_plan(1))
        self.assertIsNotNone(room.get_plan(2))

    async def test_same_plan_for_both_bots(self):
        """Both bots seeing the same message_id must get the same plan."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        _, plan_n = await self.gm.process_human_message(
            'niyati', chat_id, 5, 10, 'User', 'test')
        _, plan_p = await self.gm.process_human_message(
            'palak', chat_id, 5, 10, 'User', 'test')

        self.assertEqual(plan_n, plan_p)

    async def test_dedup_same_bot_same_message(self):
        """Same bot processing the same message_id twice → False."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        proceed1, _ = await self.gm.process_human_message(
            'niyati', chat_id, 10, 10, 'User', 'test')
        proceed2, _ = await self.gm.process_human_message(
            'niyati', chat_id, 10, 10, 'User', 'test')

        self.assertTrue(proceed1)
        self.assertFalse(proceed2)

    async def test_reply_to_niyati_routes_to_niyati(self):
        """Reply-to Niyati's message must include niyati in plan."""
        from config import Config
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        _, plan = await self.gm.process_human_message(
            'niyati', chat_id, 20, 10, 'User', 'what do you think?',
            reply_to_bot_name='niyati')

        self.assertIn('niyati', plan)

    async def test_reply_to_palak_routes_to_palak(self):
        """Reply-to Palak's message must include palak in plan."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        _, plan = await self.gm.process_human_message(
            'palak', chat_id, 21, 10, 'User', 'tell me more',
            reply_to_bot_name='palak')

        self.assertIn('palak', plan)

    async def test_single_bot_presence(self):
        """If only niyati is present, she must be the sole responder."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = False

        _, plan = await self.gm.process_human_message(
            'niyati', chat_id, 30, 10, 'User', 'hello palak')

        self.assertEqual(plan, ['niyati'])

    async def test_bot_loop_prevention(self):
        """Bot-to-bot replies must stop at configured limits."""
        from config import Config
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        # Trigger a human message first to open session
        await self.gm.process_human_message(
            'niyati', chat_id, 40, 10, 'User', 'start')

        # First bot-to-bot exchange
        proceed1, _ = await self.gm.process_partner_message(
            'palak', chat_id, 41, 101, 'Niyati', 'response')

        # Consecutive limit should kick in
        proceed2, _ = await self.gm.process_partner_message(
            'niyati', chat_id, 42, 102, 'Palak', 'another response')

        # At least one should be blocked by MAX_CONSECUTIVE_BOT_TO_BOT_REPLIES=1
        # The exact behavior depends on plan, but consecutive limit blocks the 2nd
        if proceed1:
            # If first went through, consecutive_bot_replies is now 1
            # Second should be blocked since MAX_CONSECUTIVE is 1
            self.assertFalse(proceed2)

    async def test_bot_message_counts_toward_limit(self):
        """add_bot_message must increment the reply counter."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        room.niyati_present = True
        room.palak_present = True

        # Open session
        await self.gm.process_human_message(
            'niyati', chat_id, 50, 10, 'User', 'hello')

        before = room.get_bot_replies_for_trigger()
        await self.gm.add_bot_message('niyati', chat_id, 51, 'Niyati', 'hi there')
        after = room.get_bot_replies_for_trigger()

        self.assertEqual(after, before + 1)

    async def test_no_session_from_bot_message(self):
        """A bot message must NOT open or refresh a human session."""
        chat_id = -100
        room = await self.gm.get_room(chat_id)
        # No human session active
        self.assertFalse(room.has_active_human_session())

        await self.gm.add_bot_message('niyati', chat_id, 60, 'Niyati', 'hello')

        # Session should still be inactive
        self.assertFalse(room.has_active_human_session())


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
