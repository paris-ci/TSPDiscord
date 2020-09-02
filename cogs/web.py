"""
Simple webserver to serve CAS requests/responses
"""
import base64

import aiohttp
import aiohttp_session

from cryptography import fernet
from aiohttp import web
from aiohttp_session.cookie_storage import EncryptedCookieStorage

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
import cas


class Web(Cog):

    def __init__(self, bot: MyBot, *args, **kwargs):
        super().__init__(bot, *args, **kwargs)
        self.task: Optional[asyncio.Task] = None
        self.app = web.Application()
        self.cas_client = cas.CASClientV2(
                server_url=self.config()["cas_server_url"],
                service_url=self.config()["cas_service_url"],
            )

        self.routes = web.RouteTableDef()

        @self.routes.get('/')
        async def redirect_to_discord(request: web.Request):
            raise web.HTTPFound(self.config()['official_invite'])

        @self.routes.get('/login')
        async def login(request: web.Request):
            session = await aiohttp_session.get_session(request)

            token = request.query.get('token', None)

            if token:
                session['token'] = token

            token = int(session['token'])
            if not token:
                return web.Response(text="Vous n'avez pas de token.")

            ticket = request.query.get('ticket', None)
            user = request.query.get('user', None)

            if ticket:
                user, attributes, pgtiou = self.cas_client.verify_ticket(ticket)
                if user:
                    auth_cog = self.bot.get_cog("Authentication")
                    auth_cog.auth_events[token]["info"] = {"user": user, "attributes": attributes}
                    auth_cog.auth_events[token]["event"].set()

                    return web.Response(text="Retournez sur discord ! :)")
                    #return web.Response(text=f"Ok ? {ticket} -> user={user}, attributes={attributes}, pgtiou={pgtiou}")

            # https://cas.imtbs-tsp.eu/cas/login?service=https%3A%2F%2Fetudiants.telecom-sudparis.eu%2Flogin
            raise web.HTTPFound(self.cas_client.get_login_url())

            # return web.Response(text="Un jour, le CAS !")

        # secret_key must be 32 url-safe base64-encoded bytes
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        aiohttp_session.setup(self.app, EncryptedCookieStorage(secret_key))

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
