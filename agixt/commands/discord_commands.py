# pip install discord.py
import discord
from discord.ext import commands
from Commands import Commands
from Config import Config

CFG = Config()


class discord_commands(Commands):
    def __init__(self):
        self.extension_keys = [
            "DISCORD_API_KEY",
        ]
        if CFG.DISCORD_API_KEY:
            self.commands = {
                "Send Discord Message": self.send_message,
                "Get Discord Messages": self.get_messages,
                "Delete Discord Message": self.delete_message,
                "Create Discord Invite": self.create_invite,
                "Get Discord Servers": self.get_servers,
                "Get Discord Server Information": self.get_server_info,
            }
            intents = discord.Intents.default()
            intents.typing = False
            intents.presences = False
            self.bot = commands.Bot(command_prefix=CFG.PREFIX, intents=intents)
            self.bot.run(CFG.DISCORD_API_KEY)

            @self.bot.event
            async def on_ready():
                print(f"{self.bot.user.name} is ready")

            @self.bot.event
            async def on_command_error(ctx, error):
                await ctx.send(f"Error: {error}")

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
