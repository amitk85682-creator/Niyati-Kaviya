"""
╔══════════════════════════════════════════════════════════════╗
║                    MAIN ENTRY POINT                          ║
║          Starts Niyati & Palak Bots Concurrently             ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from config import Config, logger
from database import db
from health import health_server
from bot import create_bot, setup_jobs
from group_room import group_manager


def main():
    """Main entry point - runs both bots"""

    # Validate config
    Config.validate()

    # ── Build Niyati Bot ──
    niyati_config = Config.get_bot_config('niyati')
    if not niyati_config['token']:
        logger.error("Niyati bot token missing!")
        return

    niyati_app = create_bot(
        bot_name='niyati',
        token=niyati_config['token'],
        bot_username=niyati_config['username']
    )

    # ── Check if Palak should run ──
    palak_app = None
    palak_config = Config.get_bot_config('palak')
    if palak_config['token']:
        palak_app = create_bot(
            bot_name='palak',
            token=palak_config['token'],
            bot_username=palak_config['username']
        )

    # ── Start bots ──
    if palak_app:
        logger.info("Starting both Niyati & Palak bots...")
        _run_both(niyati_app, palak_app)
    else:
        logger.info("Starting Niyati bot only (no Palak token)...")
        _run_single(niyati_app)


def _run_single(app):
    """Run single bot with manual init"""

    async def _start():
        await db.initialize()
        await health_server.start()

        await app.initialize()
        await setup_jobs(app, 'niyati')
        
        me = await app.bot.get_me()
        app.bot_data['bot_id'] = me.id
        
        # Validate startup username against Telegram get_me()
        real_username = me.username or ""
        configured_username = Config.NIYATI_BOT_USERNAME
        if real_username.lower() != configured_username.lower():
            logger.warning(f"Username mismatch for Niyati! Configured: {configured_username}, Real: {real_username}")
            Config.NIYATI_BOT_USERNAME = real_username
        app.bot_data['bot_username'] = real_username
            
        group_manager.register_bot('niyati', me.id)
        logger.info(f"Registered Niyati Bot ID: {me.id} (@{real_username})")
        
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Niyati Bot Started!")

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            logger.info("Shutting down...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            await health_server.stop()
            await db.close()
            logger.info("Bot stopped.")

    asyncio.run(_start())


def _run_both(niyati_app, palak_app):
    """Run both bots concurrently"""

    async def _start():
        await db.initialize()
        await health_server.start()

        # Initialize & start Niyati
        await niyati_app.initialize()
        await setup_jobs(niyati_app, 'niyati')
        
        me_niyati = await niyati_app.bot.get_me()
        niyati_app.bot_data['bot_id'] = me_niyati.id
        
        real_username_n = me_niyati.username or ""
        conf_username_n = Config.NIYATI_BOT_USERNAME
        if real_username_n.lower() != conf_username_n.lower():
            logger.warning(f"Username mismatch for Niyati! Configured: {conf_username_n}, Real: {real_username_n}")
            Config.NIYATI_BOT_USERNAME = real_username_n
        niyati_app.bot_data['bot_username'] = real_username_n
            
        group_manager.register_bot('niyati', me_niyati.id)
        logger.info(f"Registered Niyati Bot ID: {me_niyati.id} (@{real_username_n})")
        
        await niyati_app.start()
        await niyati_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Niyati Bot Started!")

        # Initialize & start Palak
        await palak_app.initialize()
        await setup_jobs(palak_app, 'palak')
        
        me_palak = await palak_app.bot.get_me()
        palak_app.bot_data['bot_id'] = me_palak.id
        
        real_username_p = me_palak.username or ""
        conf_username_p = Config.PALAK_BOT_USERNAME
        if real_username_p.lower() != conf_username_p.lower():
            logger.warning(f"Username mismatch for Palak! Configured: {conf_username_p}, Real: {real_username_p}")
            Config.PALAK_BOT_USERNAME = real_username_p
        palak_app.bot_data['bot_username'] = real_username_p
            
        group_manager.register_bot('palak', me_palak.id)
        logger.info(f"Registered Palak Bot ID: {me_palak.id} (@{real_username_p})")
        
        await palak_app.start()
        await palak_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Palak Bot Started!")

        logger.info("Both bots running! Press Ctrl+C to stop.")

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            logger.info("Shutting down...")
            await niyati_app.updater.stop()
            await niyati_app.stop()
            await niyati_app.shutdown()

            await palak_app.updater.stop()
            await palak_app.stop()
            await palak_app.shutdown()

            await health_server.stop()
            await db.close()
            logger.info("All bots stopped.")

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
        logger.error(f"Fatal Error: {e}", exc_info=True)
