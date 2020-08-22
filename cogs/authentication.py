"""
Authenticate users to their Télécom SudParis accounts
"""
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


class Authentication(Cog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.concurrency_dict: dict = {}

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
        def message_check(message):
            return message.author.id == member.id and message.guild is None

        db_user = await get_from_db(member, as_user=True)

        if db_user.is_registered:
            await member.send("Vous êtes déjà inscrit à TSP :) - Récupération de vos roles.")
            async with member.typing():
                ldap_info = await self.get_user_info(db_user.tsp_login)
                await self.set_member_roles(member, ldap_info)

            await member.send("Vos roles sont à jour. Bonne journée.")
            return

        await member.send("**Procédure de connection sécurisée** : Entrez votre nom d'utilisateur ou votre email TSP.")
        login_ok = False

        while not login_ok:
            try:
                message: discord.Message = await self.bot.wait_for('message', timeout=600, check=message_check)
            except asyncio.TimeoutError:
                await member.send("Vous n'avez pas répondu dans la durée impartie, annulation de la connexion.")
                return
            status = await member.send("Vérifications en cours, patientez SVP...")
            async with member.typing():
                ldap_info = await self.get_user_info(tsp_user=message.content)
                if not ldap_info:
                    await status.edit(content="❌ Votre login n'existe pas. Veuillez réessayer. Entrez votre nom d'utilisateur.")
                else:
                    login_ok = True
                    db_user.tsp_login = ldap_info['uid']

        password_ok = False
        await member.send(f"Bonjour, {ldap_info['display_name']}! Pour vérifier qu'il s'agit bien de vous, veuillez entrer votre mot de passe.")
        while not password_ok:
            try:
                message: discord.Message = await self.bot.wait_for('message', timeout=600, check=message_check)
            except asyncio.TimeoutError:
                await member.send("Vous n'avez pas répondu dans la durée impartie, annulation de la connexion. Rien n'a été sauvegardé.")
                return
            status = await member.send("Vérifications en cours, patientez SVP...")
            with member.typing():
                password_ok = await self.check_password(tsp_user=ldap_info['uid'], tsp_password=message.content)
                if not password_ok:
                    await status.edit(content="❌ Votre mot de passe est incorrect. Veuillez réessayer en entrant votre mot de passe.")
        db_user.is_registered = True
        await db_user.save()
        await member.send(
            f"Merci beaucoup {ldap_info['first_name']}. Vous êtes maintenent connecté. Vous allez recevoir dans très peu de temps les roles réservés. Merci d'avoir uilisé la connection TSP sécurisée.")
        async with member.typing():
            await self.set_member_roles(member, ldap_info)
        await member.send("👌 Procédure terminée. **Pensez à supprimer votre mot de passe de ce chat** (clic sur les ..., puis supprimer).")

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

        db_user: DiscordUser = get_from_db(member, as_user=True)

        member_login = db_user.tsp_login
        if member_login:
            info = await self.get_user_info(member_login)



setup = Authentication.setup
