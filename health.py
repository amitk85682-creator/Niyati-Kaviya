"""
Health check server for Render.com
"""

from datetime import datetime, timezone
from aiohttp import web
from config import Config, logger


class HealthServer:
    """HTTP health check server"""

    def __init__(self):
        self.app = web.Application()
        self.app.router.add_get('/', self.health)
        self.app.router.add_get('/health', self.health)
        self.app.router.add_get('/status', self.status)
        self.runner = None
        self.start_time = datetime.now(timezone.utc)
        self.stats = {'messages': 0, 'users': 0, 'groups': 0}

    async def health(self, request):
        return web.json_response({'status': 'healthy', 'bot': 'Niyati & Kavya'})

    async def status(self, request):
        uptime = datetime.now(timezone.utc) - self.start_time
        return web.json_response({
            'status': 'running',
            'uptime_hours': round(uptime.total_seconds() / 3600, 2),
            'stats': self.stats
        })

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '0.0.0.0', Config.PORT)
        await site.start()
        logger.info(f"🌐 Health server on port {Config.PORT}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()


# Singleton
health_server = HealthServer()
