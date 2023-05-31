# pip install discord.py
import discord as dc
from discord.ext import commands
from Extensions import Extensions
import logging


class discord(Extensions):
    def __init__(
        self,
        DISCORD_API_KEY: str = "",
        DISCORD_COMMAND_PREFIX: str = "/AGiXT",
        **kwargs,
    ):
        self.DISCORD_API_KEY = DISCORD_API_KEY
        self.DISCORD_COMMAND_PREFIX = DISCORD_COMMAND_PREFIX
        if self.DISCORD_API_KEY:
            self.commands = {
                "Send Discord Message": self.send_message,
                "Get Discord Messages": self.get_messages,
                "Delete Discord Message": self.delete_message,
                "Create Discord Invite": self.create_invite,
                "Get Discord Servers": self.get_servers,
                "Get Discord Server Information": self.get_server_info,
            }

            try:
                intents = dc.Intents.default()
                intents.typing = False
                intents.presences = False
                if self.DISCORD_API_KEY != "None" and self.DISCORD_API_KEY != "":
                    self.bot = commands.Bot(
                        command_prefix=self.DISCORD_COMMAND_PREFIX, intents=intents
                    )
                    self.bot.run(self.DISCORD_API_KEY)

                @self.bot.event
                async def on_ready():
                    logging.info(f"{self.bot.user.name} is ready")

                @self.bot.event
                async def on_command_error(ctx, error):
                    await ctx.send(f"Error: {error}")

            except:
                pass

    async def send_message(self, channel_id: int, content: str):
        channel = self.bot.get_channel(channel_id)
        await channel.send(content)

    async def get_messages(self, channel_id: int, limit: int = 100):
        channel = self.bot.get_channel(channel_id)
        messages = await channel.history(limit=limit).flatten()
        return [(message.author, message.content) for message in messages]

    async def delete_message(self, channel_id: int, message_id: int):
        channel = self.bot.get_channel(channel_id)
        message = await channel.fetch_message(message_id)
        await message.delete()

    async def create_invite(self, channel_id: int, max_age: int = 0, max_uses: int = 0):
        channel = self.bot.get_channel(channel_id)
        invite = await channel.create_invite(max_age=max_age, max_uses=max_uses)
        return invite.url

    async def get_servers(self):
        return [guild.name for guild in self.bot.guilds]

    async def get_server_info(self, server_id: int):
        server = self.bot.get_guild(server_id)
        return {
            "name": server.name,
            "owner": server.owner,
            "member_count": server.member_count,
        }
