import discord

from utils.cog_class import Cog


class Bonjour(Cog):
    @Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        React with an emoji to every GUILD_JOIN / new member message
        """
        if message.type == discord.MessageType.new_member:
            await message.add_reaction(self.config()['emoji_hello'])


setup = Bonjour.setup
