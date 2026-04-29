"""
╔══════════════════════════════════════════════════════════════╗
║                    MAIN ENTRY POINT                          ║
║          Starts Niyati & Kavya Bots Concurrently             ║
║                                                              ║
║  Architecture:                                               ║
║  config.py       → Central configuration                     ║
║  database.py     → Supabase + local DB (bot-aware)           ║
║  memory.py       → Per-user, per-bot memory manager          ║
║  characters/     → Character cards (personality per bot)      ║
║  ai_engine.py    → Hybrid AI (OpenAI/Groq/Gemini)            ║
║  handlers/       → Command & message handlers                ║
║  utils.py        → Utilities (time, mood, fonts, rate limit) ║
║  health.py       → Health server for Render.com              ║
║  bot.py          → Bot builder & job scheduler               ║
║  main.py         → THIS FILE - entry point                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import asyncio

from config import Config, logger
from database import db
from health import health_server
from bot import create_bot, setup_jobs



def main():
    """Main entry point - runs both bots"""

    # Validate config
    Config.validate()

    # ── Build Niyati Bot ──
    niyati_config = Config.get_bot_config('niyati')
    if not niyati_config['token']:
        logger.error("❌ Niyati bot token missing!")
        return

    niyati_app = create_bot(
        bot_name='niyati',
        token=niyati_config['token'],
        bot_username=niyati_config['username']
    )

    # ── Check if Kavya should run ──
    kavya_app = None
    kavya_config = Config.get_bot_config('kavya')
    if kavya_config['token']:
        kavya_app = create_bot(
            bot_name='kavya',
            token=kavya_config['token'],
            bot_username=kavya_config['username']
        )

    # ── Start bots ──
    if kavya_app:
        # Both bots - run concurrently
        logger.info("⏳ Starting both Niyati & Kavya bots...")
        _run_both(niyati_app, kavya_app)
    else:
        # Only Niyati
        logger.info("⏳ Starting Niyati bot only (no Kavya token)...")
        _run_single(niyati_app)


def _run_single(app):
    """Run single bot with manual init"""

    async def _start():
        await db.initialize()
        await health_server.start()

        await app.initialize()
        await setup_jobs(app, 'niyati')
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("🚀 Niyati Bot Started!")

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            logger.info("🔄 Shutting down...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            await health_server.stop()
            await db.close()
            logger.info("😴 Bot stopped.")

    asyncio.run(_start())


def _run_both(niyati_app, kavya_app):
    """Run both bots concurrently"""

    async def _start():
        # Initialize shared resources
        await db.initialize()
        await health_server.start()

        # Initialize & start Niyati
        await niyati_app.initialize()
        await setup_jobs(niyati_app, 'niyati')
        await niyati_app.start()
        await niyati_app.updater.start_polling(drop_pending_updates=True)
        logger.info("🚀 Niyati Bot Started!")

        # Initialize & start Kavya
        await kavya_app.initialize()
        await setup_jobs(kavya_app, 'kavya')
        await kavya_app.start()
        await kavya_app.updater.start_polling(drop_pending_updates=True)
        logger.info("🚀 Kavya Bot Started!")

        logger.info("✅ Both bots running! Press Ctrl+C to stop.")

        # Keep alive
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            # Graceful shutdown
            logger.info("🔄 Shutting down...")
            await niyati_app.updater.stop()
            await niyati_app.stop()
            await niyati_app.shutdown()

            await kavya_app.updater.stop()
            await kavya_app.stop()
            await kavya_app.shutdown()

            await health_server.stop()
            await db.close()
            logger.info("😴 All bots stopped.")

    asyncio.run(_start())


if __name__ == "__main__":
    try:
        if sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(
                asyncio.WindowsSelectorEventLoopPolicy()
            )
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"❌ Fatal Error: {e}", exc_info=True)
