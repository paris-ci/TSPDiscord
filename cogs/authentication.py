"""
Authenticate users to their Télécom SudParis accounts
"""
import asyncio
import secrets
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



class Authentication(Cog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.concurrency_dict: dict = {}
        self.auth_events = {}

    async def get_user_info(self, tsp_user) -> Optional[dict]:
        r = await self.bot.client_session.post(self.config()['check_login_url'], data={"login": tsp_user})
        res = await r.json()
        if res.get('error', False):
            return None
        else:
            return res

    async def check_password(self, tsp_user, tsp_password) -> bool:
        r = await self.bot.client_session.post(self.config()['check_login_url'], data={"login": tsp_user, "password": tsp_password})
        res = await r.json()
        return not res.get('error', False)

    async def get_roles_for_group(self, group) -> List[discord.Role]:
        pass

    async def set_member_roles(self, member: discord.Member, ldap_info: dict):
        self.bot.logger.info(f"Member {member.name}#{member.discriminator} ({member.id}) has logged in as {ldap_info['uid']}.")
        mapping = self.config()['roles_mapping']
        guild = member.guild
        group: str = ldap_info['title']
        await member.remove_roles(*[role for role in member.roles if role.id in self.config()['roles_mapping'].values()], reason=f"Login for {ldap_info['uid']}")

        roles_to_add = []

        if group.startswith("CL"):
            roles_to_add.append(guild.get_role(mapping['etudiant']))
            if group.startswith("CL_FI"):
                roles_to_add.append(guild.get_role(mapping['FISE']))
                year = group.split('-')[1]
                if year.startswith("EI"):
                    year = str(year[2]) + "A"
                    roles_to_add.append(guild.get_role(mapping[year]))
            elif group.startswith("CL_FIPA"):
                roles_to_add.append(guild.get_role(mapping['FIPA']))
                year = group.split('-')[1]
                if year.isdigit():
                    roles_to_add.append(guild.get_role(mapping[year + "A"]))
            elif group.startswith("CL_FE"):
                roles_to_add.append(guild.get_role(mapping['FIPA']))
        else:
            roles_to_add.append(guild.get_role(mapping['personnel']))

        await member.add_roles(*roles_to_add, reason=f"Login for {ldap_info['uid']}")
        initial = ldap_info['last_name'].split()[-1][0].upper()
        nick = f"{ldap_info['first_name']} {initial}.".title()
        self.bot.logger.debug(f"Member {member.name}#{member.discriminator} ({member.id}) is getting renamed to {nick} following login.")

        await member.edit(nick=nick, reason=f"Anonymité découragée")

    async def login_interaction(self, member, guild):
        db_user = await get_from_db(member, as_user=True)

        if db_user.is_registered:
            await member.send("Vous êtes déjà inscrit à TSP :) - Récupération de vos roles.")
            async with member.typing():
                ldap_info = await self.get_user_info(db_user.tsp_login)
                await self.set_member_roles(member, ldap_info)

            await member.send("Vos roles sont à jour. Bonne journée.")
            return

        secret_id = secrets.randbelow(1000000000000000000)
        self.auth_events[secret_id] = {"event": asyncio.Event(), "info": {}}
        await member.send(f"**Procédure de connection sécurisée** : Connectez vous sur https://etudiants.telecom-sudparis.eu/login?token={secret_id}")
        try:
            await asyncio.wait_for(self.auth_events[secret_id]["event"].wait(), timeout=660)
        except asyncio.TimeoutError:
            await member.send("Vous ne vous etes pas connecté, annulation.")
            del self.auth_events[secret_id]
            return

        tsp_user = self.auth_events[secret_id]["info"]["user"]

        ldap_info = await self.get_user_info(tsp_user=tsp_user)

        db_user.tsp_login = ldap_info['uid']
        db_user.is_registered = True
        await db_user.save()
        await member.send(
            f"Merci beaucoup {ldap_info['first_name']}. Vous êtes maintenent connecté. Vous allez recevoir dans très peu de temps les roles réservés. Merci d'avoir uilisé la connection TSP sécurisée.")
        async with member.typing():
            await self.set_member_roles(member, ldap_info)
        await member.send("👌 Procédure terminée.")

    @Cog.listener(name="on_raw_reaction_add")
    async def login_process(self, payload: discord.RawReactionActionEvent):
        config = self.config()
        if not config['reaction_channel_id'] == payload.channel_id:
            return
        elif not config['begin_login_emoji_id'] == payload.emoji.id:
            return

        member = payload.member
        guild = member.guild
        try:
            if not self.concurrency_dict.get(member.id, False):
                self.concurrency_dict[member.id] = True
                await self.login_interaction(member, guild)
            else:
                return
        except Exception as e:
            self.bot.logger.exception("Error happened in login_interaction.")

        del self.concurrency_dict[member.id]

    @commands.command(aliases=["kicé", "quiestce"])
    async def whois(self, ctx: 'MyContext', member: Optional[discord.Member] = None):
        if not member:
            member = ctx.author

        db_user: DiscordUser = await get_from_db(member, as_user=True)

        member_login = db_user.tsp_login
        if member_login:
            info = await self.get_user_info(member_login)
            pfp_url = self.config()['profile_picture_url'].format(login=info['uid'])
            e = discord.Embed(colour=discord.Colour.green(), title=f"{info['civilite']} {info['last_name']} {info['first_name']}")
            e.set_thumbnail(url=pfp_url)
            e.set_author(name=f"{member.name}#{member.discriminator}", url=str(member.avatar_url), icon_url=str(member.avatar_url))
            e.add_field(name="Email", value=info['mail'])
            e.add_field(name="Groupe", value=info['title'])
            # e.add_field(name="Login", value=info['uid'])
        else:
            e = discord.Embed(title="Utilisateur introuvable dans la base de données.", description="Dites lui de s'enregister dans <#744968789086699582>", colour=discord.Colour.red())

        await ctx.send(embed=e)



setup = Authentication.setup
