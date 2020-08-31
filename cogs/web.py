"""
Simple webserver to serve CAS requests/responses
"""
import aiohttp
from aiohttp import web

import asyncio
from collections import defaultdict
from typing import Optional, List

import discord
from discord.ext import commands
from discord.utils import escape_markdown, escape_mentions

from utils import checks
from utils.bot_class import MyBot
from utils.cog_class import Cog
from utils.ctx_class import MyContext
from utils.models import get_from_db, DiscordUser


class Web(Cog):

    def __init__(self, bot: MyBot, *args, **kwargs):
        super().__init__(bot, *args, **kwargs)
        self.task: Optional[asyncio.Task] = None
        self.app = web.Application()

        self.routes = web.RouteTableDef()

        @self.routes.get('/')
        async def redirect_to_discord(request):
            # raise web.HTTPFound(self.config()['official_invite'])
            return web.Response(text="Un jour, le CAS !")

        self.app.add_routes(self.routes)
        self.bot.loop.create_task(self.async_init())


    async def async_init(self):
        await self.bot.wait_until_ready()
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.config()['host'], self.config()['port'])
        self.task = self.bot.loop.create_task(site.start())
        self.bot.logger.info("API started.")

    def cog_unload(self):
        if self.task:
            self.task.cancel()
            self.bot.logger.info("API stopped.")


setup = Web.setup
