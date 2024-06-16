# pip install discord.py
try:
    import discord as dc
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "discord"])
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
        self.commands = {
            "Send Discord Message": self.send_message,
            "Get Discord Messages": self.get_messages,
            "Delete Discord Message": self.delete_message,
            "Create Discord Invite": self.create_invite,
            "Get Discord Servers": self.get_servers,
            "Get Discord Server Information": self.get_server_info,
        }
        if self.DISCORD_API_KEY:
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
        """
        Send a message to a Discord channel

        Args:
        channel_id (int): The ID of the Discord channel
        content (str): The content of the message

        Returns:
        str: The result of sending the message
        """
        channel = self.bot.get_channel(channel_id)
        await channel.send(content)
        return f"Message sent to channel {channel_id} successfully!"

    async def get_messages(self, channel_id: int, limit: int = 100):
        """
        Get messages from a Discord channel

        Args:
        channel_id (int): The ID of the Discord channel
        limit (int): The number of messages to retrieve

        Returns:
        str: The messages from the channel
        """
        channel = self.bot.get_channel(channel_id)
        messages = await channel.history(limit=limit).flatten()
        str_messages = ""
        for message in messages:
            str_messages += f"{message.author}: {message.content}\n"
        return str_messages

    async def delete_message(self, channel_id: int, message_id: int):
        """
        Delete a message from a Discord channel

        Args:
        channel_id (int): The ID of the Discord channel
        message_id (int): The ID of the message to delete

        Returns:
        str: The result of deleting the message
        """
        channel = self.bot.get_channel(channel_id)
        message = await channel.fetch_message(message_id)
        await message.delete()
        return f"Message {message_id} deleted successfully!"

    async def create_invite(self, channel_id: int, max_age: int = 0, max_uses: int = 0):
        """
        Create an invite to a Discord channel

        Args:
        channel_id (int): The ID of the Discord channel
        max_age (int): The maximum age of the invite in seconds
        max_uses (int): The maximum number of uses for the invite

        Returns:
        str: The invite URL
        """
        channel = self.bot.get_channel(channel_id)
        invite = await channel.create_invite(max_age=max_age, max_uses=max_uses)
        return invite.url

    async def get_servers(self):
        """
        Get the list of servers the bot is connected to

        Returns:
        str: The list of servers
        """
        servers = [guild.name for guild in self.bot.guilds]
        return ", ".join(servers)

    async def get_server_info(self, server_id: int):
        """
        Get information about a Discord server

        Args:
        server_id (int): The ID of the Discord server

        Returns:
        dict: The information about the server
        """
        server = self.bot.get_guild(server_id)
        return {
            "name": server.name,
            "owner": server.owner,
            "member_count": server.member_count,
        }
