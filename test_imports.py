"""Quick import verification + old file cleanup"""
import os
import sys

# Delete old conflicting files FIRST (before any imports)
_dir = os.path.dirname(os.path.abspath(__file__))
for f in ['schemas.py', 'persona.py', 'run.py', 'handlers.py', 'handlers_OLD_DELETE_ME.py']:
    path = os.path.join(_dir, f)
    if os.path.exists(path):
        os.remove(path)
        print(f"🗑️ Deleted: {f}")

# Set minimal env vars for import testing
os.environ.setdefault('NIYATI_BOT_TOKEN', 'test')
os.environ.setdefault('GROQ_API_KEYS', 'test')

print("\n--- Testing imports ---")
errors = []

try:
    from config import Config, logger
    print(f"✅ config.py (Port: {Config.PORT})")
except Exception as e:
    errors.append(f"config: {e}")
    print(f"❌ config.py: {e}")

try:
    from database import db
    print("✅ database.py")
except Exception as e:
    errors.append(f"database: {e}")
    print(f"❌ database.py: {e}")

try:
    from memory import get_memory
    m = get_memory('niyati')
    print(f"✅ memory.py (bot: {m.bot_name})")
except Exception as e:
    errors.append(f"memory: {e}")
    print(f"❌ memory.py: {e}")

try:
    from characters import get_character
    n = get_character('niyati')
    k = get_character('Palak')
    print(f"✅ characters/ ({n['name']}, {k['name']})")
except Exception as e:
    errors.append(f"characters: {e}")
    print(f"❌ characters/: {e}")

try:
    from utils import TimeAware, Mood, rate_limiter
    print(f"✅ utils.py (time: {TimeAware.get_time_period()})")
except Exception as e:
    errors.append(f"utils: {e}")
    print(f"❌ utils.py: {e}")

try:
    from ai_engine import ai_engine
    print(f"✅ ai_engine.py ({len(ai_engine.all_keys)} keys)")
except Exception as e:
    errors.append(f"ai_engine: {e}")
    print(f"❌ ai_engine.py: {e}")

try:
    from health import health_server
    print("✅ health.py")
except Exception as e:
    errors.append(f"health: {e}")
    print(f"❌ health.py: {e}")

try:
    from handlers import (
        start_command, help_command, handle_message,
        admin_stats_command, grouphelp_command, handle_new_member
    )
    print("✅ handlers/ (all modules)")
except Exception as e:
    errors.append(f"handlers: {e}")
    print(f"❌ handlers/: {e}")

try:
    from bot import create_bot, setup_handlers
    print("✅ bot.py")
except Exception as e:
    errors.append(f"bot: {e}")
    print(f"❌ bot.py: {e}")

print()
if errors:
    print(f"❌ FAILED: {len(errors)} errors")
    for e in errors:
        print(f"  → {e}")
else:
    print("🎉 ALL IMPORTS PASSED!")

# Cleanup test file itself
try:
    os.remove(os.path.join(_dir, 'test_imports.py'))
    print("🗑️ Cleaned up test_imports.py")
except:
    pass
