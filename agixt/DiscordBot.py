import os
import base64
import discord
import aiohttp
from MagicalAuth import impersonate_user
from extensions.discord_integration import get_discord_user_ids
from InternalClient import InternalClient
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMPANY_ID = os.getenv("COMPANY_ID")  # Company ID for Discord user mapping

# Cache for Discord user ID -> email mapping
discord_user_cache = {}


def refresh_discord_user_cache():
    """Refresh the Discord user ID -> email mapping cache"""
    global discord_user_cache
    if COMPANY_ID:
        discord_user_cache = get_discord_user_ids(COMPANY_ID)
    return discord_user_cache

def get_user_email_from_discord_id(discord_id: int) -> str:
    """Get user email from Discord ID, refreshing cache if needed"""
    discord_id_str = str(discord_id)
    if discord_id_str not in discord_user_cache:
        refresh_discord_user_cache()
    return discord_user_cache.get(discord_id_str)


async def get_channel_context(channel, limit=10):
    """Get the last messages from the channel up to the bot's last message"""
    messages = []
    async for message in channel.history(limit=limit):
        if message.author == bot.user:
            break
        if message.author.bot:
            continue
        messages.insert(0, f"{message.author.display_name}: {message.content}")
    return "\n".join(messages)


async def download_attachment(attachment):
    """Download an attachment and return its base64 encoded content"""
    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as response:
            if response.status == 200:
                data = await response.read()
                encoded_data = base64.b64encode(data).decode("utf-8")
                return f"data:{attachment.content_type};base64,{encoded_data}"
    return None


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")
    # Refresh the Discord user cache on startup
    refresh_discord_user_cache()
    print(f"Loaded {len(discord_user_cache)} Discord user mappings")


@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Get user email from Discord ID mapping
    user_email = get_user_email_from_discord_id(message.author.id)

    if not user_email:
        # User hasn't connected their Discord account via OAuth
        return

    # Get JWT for impersonation
    user_jwt = impersonate_user(user_email)

    # Create internal client for this user
    agixt = InternalClient(api_key=user_jwt, user=user_email)
    # Check if the message is a direct message or mentions the bot
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions

    if is_dm or is_mentioned:
        # Remove the bot mention from the message if present
        content = message.content.replace(f"<@{bot.user.id}>", "").strip()

        # If the message is empty after removing the mention and has no attachments, ignore it
        if not content and not message.attachments:
            return

        async with message.channel.typing():
            try:
                # Get conversation context
                context = await get_channel_context(message.channel)
                # Prepare prompt arguments
                prompt_args = {
                    "user_input": content,
                    "context": context,
                    "conversation_name": f"discord-{message.channel.id}",
                }

                # Handle attachments
                if message.attachments:
                    file_urls = []
                    for attachment in message.attachments:
                        file_data = await download_attachment(attachment)
                        if file_data:
                            file_urls.append(file_data)
                    if file_urls:
                        prompt_args["file_urls"] = file_urls

                # Call AGiXT API
                response = agixt.prompt_agent(
                    agent_name="XT",
                    prompt_name="Think About It",
                    prompt_args=prompt_args,
                )

                # Get the response content
                reply = (
                    response["response"]
                    if isinstance(response, dict)
                    else str(response)
                )

                # Split long messages if needed
                if len(reply) > 2000:
                    # Split the message into chunks of 2000 characters
                    chunks = [reply[i : i + 2000] for i in range(0, len(reply), 2000)]
                    for chunk in chunks:
                        await message.reply(chunk)
                else:
                    await message.reply(reply)

            except Exception as e:
                await message.reply(f"Sorry, I encountered an error: {str(e)}")

    await bot.process_commands(message)


# Run the bot
if __name__ == "__main__":

    if not DISCORD_TOKEN:
        raise ValueError("No Discord token found in environment variables")

    bot.run(DISCORD_TOKEN)
