"""
╔══════════════════════════════════════════════════════════════╗
║                    MAIN ENTRY POINT                          ║
║          Starts Niyati & Palak Bots Concurrently             ║
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
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print("DEBUG: main.py loaded, starting imports...", flush=True)

try:
    import asyncio
    print("DEBUG: asyncio imported", flush=True)
    from config import Config, logger
    print("DEBUG: config imported", flush=True)
    from database import db
    print("DEBUG: database imported", flush=True)
    from health import health_server
    print("DEBUG: health imported", flush=True)
    from bot import create_bot, setup_jobs
    print("DEBUG: bot imported", flush=True)
    from group_room import group_manager
    print("DEBUG: group_manager imported", flush=True)
except Exception as e:
    print(f"DEBUG: Import failed: {e}", flush=True)
    raise



def main():
    """Main entry point - runs both bots"""
    print("DEBUG: main() started", flush=True)

    # Validate config
    try:
        Config.validate()
        print("DEBUG: Config.validate() passed", flush=True)
    except Exception as e:
        print(f"DEBUG: Config.validate() failed: {e}", flush=True)
        raise

    # ── Build Niyati Bot ──
    niyati_config = Config.get_bot_config('niyati')
    if not niyati_config['token']:
        print("DEBUG: Niyati bot token missing! Exiting.", flush=True)
        logger.error("❌ Niyati bot token missing!")
        return

    print("DEBUG: Creating Niyati bot...", flush=True)
    niyati_app = create_bot(
        bot_name='niyati',
        token=niyati_config['token'],
        bot_username=niyati_config['username']
    )

    # ── Check if Palak should run ──
    Palak_app = None
    Palak_config = Config.get_bot_config('Palak')
    if Palak_config['token']:
        Palak_app = create_bot(
            bot_name='Palak',
            token=Palak_config['token'],
            bot_username=Palak_config['username']
        )

    # ── Start bots ──
    if Palak_app:
        # Both bots - run concurrently
        logger.info("⏳ Starting both Niyati & Palak bots...")
        _run_both(niyati_app, Palak_app)
    else:
        # Only Niyati
        logger.info("⏳ Starting Niyati bot only (no Palak token)...")
        _run_single(niyati_app)


def _run_single(app):
    """Run single bot with manual init"""

    async def _start():
        await db.initialize()
        await health_server.start()

        await app.initialize()
        await setup_jobs(app, 'niyati')
        
        # 🔴 Fetch and register bot ID
        me = await app.bot.get_me()
        app.bot_data['bot_id'] = me.id
        group_manager.register_bot('niyati', me.id)
        logger.info(f"🆔 Registered Niyati Bot ID: {me.id}")
        
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


def _run_both(niyati_app, Palak_app):
    """Run both bots concurrently"""

    async def _start():
        # Initialize shared resources
        await db.initialize()
        await health_server.start()

        # Initialize & start Niyati
        await niyati_app.initialize()
        await setup_jobs(niyati_app, 'niyati')
        
        me_niyati = await niyati_app.bot.get_me()
        niyati_app.bot_data['bot_id'] = me_niyati.id
        group_manager.register_bot('niyati', me_niyati.id)
        logger.info(f"🆔 Registered Niyati Bot ID: {me_niyati.id}")
        
        await niyati_app.start()
        await niyati_app.updater.start_polling(drop_pending_updates=True)
        logger.info("🚀 Niyati Bot Started!")

        # Initialize & start Palak
        await Palak_app.initialize()
        await setup_jobs(Palak_app, 'Palak')
        
        me_palak = await Palak_app.bot.get_me()
        Palak_app.bot_data['bot_id'] = me_palak.id
        group_manager.register_bot('palak', me_palak.id)
        logger.info(f"🆔 Registered Palak Bot ID: {me_palak.id}")
        
        await Palak_app.start()
        await Palak_app.updater.start_polling(drop_pending_updates=True)
        logger.info("🚀 Palak Bot Started!")

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

            await Palak_app.updater.stop()
            await Palak_app.stop()
            await Palak_app.shutdown()

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
