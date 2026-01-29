"""
X (Twitter) Bot Manager for AGiXT

This module manages X/Twitter bots for multiple companies. Each company can have
its own X bot instance running concurrently within a single manager process.

The manager:
- Starts/stops bots based on company extension settings
- Monitors for new DMs and mentions
- Handles graceful shutdown of all bots
- Provides APIs for querying bot status

X (Twitter) bot functionality is primarily DM-based since there's no persistent
WebSocket connection like Discord. The bot polls for new DMs and mentions at
configurable intervals.

Required environment variables:
- X_CLIENT_ID: X OAuth client ID
- X_CLIENT_SECRET: X OAuth client secret

Required scopes:
- dm.read, dm.write for DM-based conversations
- tweet.read, tweet.write for mentions/replies
- users.read for user information
"""

import asyncio
import logging
import sys
import os
import requests
from typing import Dict, Optional, List, Set
from dataclasses import dataclass
from datetime import datetime

from DB import (
    get_session,
    CompanyExtensionSetting,
    ServerExtensionSetting,
    Company,
    UserOAuth,
    OAuthProvider,
)
from Globals import getenv
from MagicalAuth import impersonate_user, MagicalAuth
from InternalClient import InternalClient
from Models import ChatCompletions


def get_x_user_ids(company_id=None):
    """
    Get mapping of X user IDs to AGiXT user IDs for a company.
    
    Args:
        company_id: Optional company ID to filter by
        
    Returns:
        Dict mapping X user ID -> AGiXT user ID
    """
    user_ids = {}
    with get_session() as session:
        # Get the X OAuth provider
        provider = session.query(OAuthProvider).filter_by(name="x").first()
        if not provider:
            return user_ids
            
        # Query all X OAuth connections
        query = session.query(UserOAuth).filter_by(provider_id=provider.id)
        
        if company_id:
            # Filter by company if provided
            query = query.filter(UserOAuth.company_id == company_id)
            
        for oauth in query.all():
            if oauth.provider_user_id:
                user_ids[oauth.provider_user_id] = str(oauth.user_id)
                
    return user_ids


logger = logging.getLogger(__name__)


@dataclass
class XBotStatus:
    """Status information for a company's X bot."""
    
    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    last_dm_check: Optional[datetime] = None
    last_mention_check: Optional[datetime] = None
    messages_processed: int = 0


class CompanyXBot:
    """
    X (Twitter) bot instance for a single company.
    
    Handles:
    - Polling for new DMs and mentions
    - Responding to messages via AI agents
    - User impersonation for personalized responses
    - Admin commands for bot management
    
    Permission modes:
    - owner_only: Only the user who set up the bot can interact
    - recognized_users: Only users with linked AGiXT accounts can interact (default)
    - anyone: Anyone can interact with the bot
    """
    
    # Admin commands that users can use in DMs
    ADMIN_COMMANDS = {
        "!help": "Show available commands",
        "!list": "List available AI agents",
        "!select <agent>": "Select an AI agent to chat with",
        "!clear": "Clear conversation history",
        "!status": "Show bot status",
    }
    
    def __init__(
        self,
        company_id: str,
        company_name: str,
        bot_token: str,
        bot_user_id: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
    ):
        """
        Initialize the X bot for a company.
        
        Args:
            company_id: The company's UUID
            company_name: Human-readable company name
            bot_token: OAuth access token for the bot account
            bot_user_id: X user ID for the bot account
            bot_agent_id: Specific agent ID to use (None = user's default)
            bot_permission_mode: Permission mode (owner_only, recognized_users, anyone)
            bot_owner_id: User ID of who configured this bot
        """
        self.company_id = company_id
        self.company_name = company_name
        self.bot_token = bot_token
        self.bot_user_id = bot_user_id
        
        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
        
        # Bot state
        self.is_running = False
        self.started_at: Optional[datetime] = None
        self.last_dm_check: Optional[datetime] = None
        self.last_mention_check: Optional[datetime] = None
        self.messages_processed = 0
        
        # Track processed message IDs to avoid duplicates
        self.processed_dm_ids: Set[str] = set()
        self.processed_mention_ids: Set[str] = set()
        
        # User agent selections (X user ID -> agent name)
        self.user_agents: Dict[str, str] = {}
        
        # Polling intervals (in seconds)
        self.dm_poll_interval = 30
        self.mention_poll_interval = 60
        
        # Internal client for API calls
        self.internal_client = InternalClient()
        
        # Cache of X user IDs to AGiXT user IDs
        self._user_id_cache: Dict[str, str] = {}
        
        logger.info(f"Initialized X bot for company {company_name} ({company_id})")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers for X API requests."""
        return {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }
    
    def _refresh_user_id_cache(self):
        """Refresh the X user ID to AGiXT user ID cache."""
        self._user_id_cache = get_x_user_ids(self.company_id)
    
    def _get_agixt_user_id(self, x_user_id: str) -> Optional[str]:
        """
        Get the AGiXT user ID for an X user.
        
        Args:
            x_user_id: X user ID
            
        Returns:
            AGiXT user ID or None if not found
        """
        if x_user_id not in self._user_id_cache:
            self._refresh_user_id_cache()
        return self._user_id_cache.get(x_user_id)
    
    async def _get_user_token(self, x_user_id: str) -> Optional[str]:
        """
        Get an impersonation token for a user.
        
        Args:
            x_user_id: X user ID
            
        Returns:
            JWT token for the user or None
        """
        agixt_user_id = self._get_agixt_user_id(x_user_id)
        if not agixt_user_id:
            return None
            
        try:
            return impersonate_user(agixt_user_id)
        except Exception as e:
            logger.error(f"Error impersonating user {x_user_id}: {e}")
            return None
    
    async def _get_available_agents(self) -> List[str]:
        """Get list of available agents for this company."""
        try:
            # Use company admin token for listing agents
            with get_session() as session:
                company = session.query(Company).filter_by(id=self.company_id).first()
                if not company:
                    return ["XT"]
                    
                # Get any user from this company to list agents
                from DB import User
                user = session.query(User).filter_by(company_id=self.company_id).first()
                if not user:
                    return ["XT"]
                    
                user_id = str(user.id)
                
            token = impersonate_user(user_id)
            agents = self.internal_client.get_agents(token=token)
            return [a.get("name", "XT") for a in agents] if agents else ["XT"]
        except Exception as e:
            logger.error(f"Error getting agents: {e}")
            return ["XT"]
    
    async def _get_default_agent(self) -> str:
        """Get the default agent for this company."""
        # Check for company setting first
        with get_session() as session:
            setting = (
                session.query(CompanyExtensionSetting)
                .filter_by(company_id=self.company_id, setting_name="x_default_agent")
                .first()
            )
            if setting and setting.setting_value:
                return setting.setting_value
        return "XT"
    
    def _get_selected_agent(self, x_user_id: str) -> str:
        """Get the selected agent for a user, or default."""
        return self.user_agents.get(x_user_id, None)
    
    async def _send_dm(self, recipient_id: str, text: str) -> bool:
        """
        Send a DM to a user.
        
        Args:
            recipient_id: X user ID to send to
            text: Message text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # X has a 10,000 character limit for DMs
            if len(text) > 10000:
                # Split into chunks
                chunks = [text[i:i+9900] for i in range(0, len(text), 9900)]
                for chunk in chunks:
                    await self._send_dm(recipient_id, chunk)
                return True
            
            message_data = {
                "event": {
                    "type": "message_create",
                    "message_create": {
                        "target": {"recipient_id": recipient_id},
                        "message_data": {"text": text},
                    },
                }
            }
            
            response = requests.post(
                "https://api.x.com/1.1/direct_messages/events/new.json",
                headers=self._get_headers(),
                json=message_data,
            )
            
            if response.status_code in (200, 201):
                return True
            else:
                logger.error(f"Failed to send DM: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending DM: {e}")
            return False
    
    async def _reply_to_tweet(self, tweet_id: str, text: str) -> bool:
        """
        Reply to a tweet/mention.
        
        Args:
            tweet_id: ID of tweet to reply to
            text: Reply text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # X has a 280 character limit for tweets
            if len(text) > 280:
                text = text[:277] + "..."
            
            payload = {
                "text": text,
                "reply": {"in_reply_to_tweet_id": tweet_id},
            }
            
            response = requests.post(
                "https://api.x.com/2/tweets",
                headers=self._get_headers(),
                json=payload,
            )
            
            if response.status_code in (200, 201):
                return True
            else:
                logger.error(f"Failed to reply to tweet: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error replying to tweet: {e}")
            return False
    
    async def _handle_admin_command(
        self, x_user_id: str, command: str
    ) -> Optional[str]:
        """
        Handle admin commands in DMs.
        
        Args:
            x_user_id: X user ID who sent the command
            command: Command text
            
        Returns:
            Response message or None if not a command
        """
        cmd = command.lower().strip()
        
        if cmd == "!help":
            lines = ["**Available Commands:**"]
            for cmd_name, cmd_desc in self.ADMIN_COMMANDS.items():
                lines.append(f"• {cmd_name} - {cmd_desc}")
            return "\n".join(lines)
        
        elif cmd == "!list":
            agents = await self._get_available_agents()
            current = self._get_selected_agent(x_user_id) or await self._get_default_agent()
            lines = ["**Available Agents:**"]
            for agent in agents:
                marker = "✓ " if agent == current else "  "
                lines.append(f"{marker}{agent}")
            lines.append(f"\nCurrent: {current}")
            lines.append("Use !select <agent> to switch")
            return "\n".join(lines)
        
        elif cmd.startswith("!select "):
            agent_name = command[8:].strip()
            agents = await self._get_available_agents()
            
            # Case-insensitive match
            matched = None
            for agent in agents:
                if agent.lower() == agent_name.lower():
                    matched = agent
                    break
            
            if matched:
                self.user_agents[x_user_id] = matched
                return f"✓ Switched to agent: {matched}"
            else:
                return f"Agent '{agent_name}' not found. Use !list to see available agents."
        
        elif cmd == "!clear":
            # Clear conversation by removing from user_agents (they'll get a new conversation)
            if x_user_id in self.user_agents:
                del self.user_agents[x_user_id]
            return "✓ Conversation cleared. Your next message will start fresh."
        
        elif cmd == "!status":
            uptime = ""
            if self.started_at:
                delta = datetime.utcnow() - self.started_at
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime = f"{hours}h {minutes}m {seconds}s"
            
            current_agent = self._get_selected_agent(x_user_id) or await self._get_default_agent()
            
            return (
                f"**Bot Status**\n"
                f"Company: {self.company_name}\n"
                f"Uptime: {uptime}\n"
                f"Messages Processed: {self.messages_processed}\n"
                f"Your Agent: {current_agent}"
            )
        
        return None
    
    async def _process_dm(
        self, dm_id: str, sender_id: str, sender_username: str, text: str
    ):
        """
        Process an incoming DM.
        
        Args:
            dm_id: DM event ID
            sender_id: X user ID of sender
            sender_username: X username of sender
            text: Message text
        """
        if dm_id in self.processed_dm_ids:
            return
            
        self.processed_dm_ids.add(dm_id)
        
        # Don't respond to our own messages
        if sender_id == self.bot_user_id:
            return
        
        logger.info(f"Processing DM from @{sender_username}: {text[:100]}...")
        self.messages_processed += 1
        
        # Get AGiXT user ID for permission checks
        agixt_user_id = self._get_agixt_user_id(sender_id)
        use_owner_context = False
        
        # Apply permission mode checks
        if self.bot_permission_mode == "owner_only":
            # Only the owner can interact
            if not agixt_user_id or agixt_user_id != self.bot_owner_id:
                return
        elif self.bot_permission_mode == "recognized_users":
            # Default behavior - only users with linked accounts
            if not agixt_user_id:
                return
        elif self.bot_permission_mode == "anyone":
            # Anyone can interact
            if not agixt_user_id:
                use_owner_context = True
        else:
            # Unknown permission mode, default to recognized_users behavior
            if not agixt_user_id:
                return
        
        # Check for admin commands - only allow for recognized users
        if text.startswith("!") and not use_owner_context:
            response = await self._handle_admin_command(sender_id, text)
            if response:
                await self._send_dm(sender_id, response)
                return
        
        # Determine which agent to use
        agent_name = None
        
        # If bot has a configured agent, we'll use it
        if not self.bot_agent_id:
            # Get user's selected agent
            agent_name = self._get_selected_agent(sender_id)
            if not agent_name:
                agent_name = await self._get_default_agent()
        
        # Try to get user's token for personalized responses
        user_token = None
        if use_owner_context and self.bot_owner_id:
            user_token = impersonate_user(self.bot_owner_id)
        else:
            user_token = await self._get_user_token(sender_id)
        
        try:
            # Build conversation name from X username
            conversation_name = f"x-dm-{sender_username}-{self.company_id[:8]}"
            
            if user_token:
                # User is linked - use their token
                # If bot has configured agent, resolve agent name
                if self.bot_agent_id:
                    try:
                        from InternalClient import InternalClient
                        agixt = InternalClient(api_key=user_token)
                        agents = agixt.get_agents()
                        for agent in agents:
                            if isinstance(agent, dict) and str(agent.get("id")) == str(self.bot_agent_id):
                                agent_name = agent.get("name", "XT")
                                break
                        if not agent_name:
                            logger.warning(f"Configured bot agent ID {self.bot_agent_id} not found, using default")
                            agent_name = await self._get_default_agent()
                    except Exception as e:
                        logger.warning(f"Could not lookup configured agent: {e}")
                        agent_name = await self._get_default_agent()
                
                chat = ChatCompletions(
                    agent_name=agent_name,
                    api_key=user_token,
                )
            else:
                # User not linked - use company default
                with get_session() as session:
                    from DB import User
                    user = session.query(User).filter_by(company_id=self.company_id).first()
                    if user:
                        default_token = impersonate_user(str(user.id))
                        
                        # If bot has configured agent, resolve agent name
                        if self.bot_agent_id and not agent_name:
                            try:
                                from InternalClient import InternalClient
                                agixt = InternalClient(api_key=default_token)
                                agents = agixt.get_agents()
                                for agent in agents:
                                    if isinstance(agent, dict) and str(agent.get("id")) == str(self.bot_agent_id):
                                        agent_name = agent.get("name", "XT")
                                        break
                                if not agent_name:
                                    agent_name = await self._get_default_agent()
                            except Exception as e:
                                logger.warning(f"Could not lookup configured agent: {e}")
                                agent_name = await self._get_default_agent()
                        
                        chat = ChatCompletions(
                            agent_name=agent_name,
                            api_key=default_token,
                        )
                    else:
                        logger.error(f"No users found for company {self.company_id}")
                        await self._send_dm(sender_id, "Sorry, I'm having trouble connecting to my AI backend.")
                        return
            
            # Generate response
            response = await chat.chat_completions(
                messages=[{"role": "user", "content": text}],
                conversation_name=conversation_name,
                context_results=10,
            )
            
            if response and isinstance(response, dict):
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    await self._send_dm(sender_id, content)
                else:
                    await self._send_dm(sender_id, "I apologize, but I couldn't generate a response.")
            else:
                await self._send_dm(sender_id, "I apologize, but I couldn't generate a response.")
                
        except Exception as e:
            logger.error(f"Error processing DM: {e}")
            await self._send_dm(sender_id, "I encountered an error processing your message. Please try again.")
    
    async def _process_mention(
        self, tweet_id: str, author_id: str, author_username: str, text: str
    ):
        """
        Process a mention/reply to the bot.
        
        Args:
            tweet_id: Tweet ID
            author_id: X user ID of author
            author_username: X username of author
            text: Tweet text (with @mention removed)
        """
        if tweet_id in self.processed_mention_ids:
            return
            
        self.processed_mention_ids.add(tweet_id)
        
        # Don't respond to our own tweets
        if author_id == self.bot_user_id:
            return
        
        logger.info(f"Processing mention from @{author_username}: {text[:100]}...")
        self.messages_processed += 1
        
        # Get AGiXT user ID for permission checks
        agixt_user_id = self._get_agixt_user_id(author_id)
        use_owner_context = False
        
        # Apply permission mode checks
        if self.bot_permission_mode == "owner_only":
            if not agixt_user_id or agixt_user_id != self.bot_owner_id:
                return
        elif self.bot_permission_mode == "recognized_users":
            if not agixt_user_id:
                return
        elif self.bot_permission_mode == "anyone":
            if not agixt_user_id:
                use_owner_context = True
        else:
            if not agixt_user_id:
                return
        
        # Determine which agent to use
        agent_name = None
        if not self.bot_agent_id:
            agent_name = self._get_selected_agent(author_id)
            if not agent_name:
                agent_name = await self._get_default_agent()
        
        # Try to get user's token
        user_token = None
        if use_owner_context and self.bot_owner_id:
            user_token = impersonate_user(self.bot_owner_id)
        else:
            user_token = await self._get_user_token(author_id)
        
        try:
            # Build conversation name
            conversation_name = f"x-mention-{author_username}-{self.company_id[:8]}"
            
            if user_token:
                # If bot has configured agent, resolve agent name
                if self.bot_agent_id:
                    try:
                        from InternalClient import InternalClient
                        agixt = InternalClient(api_key=user_token)
                        agents = agixt.get_agents()
                        for agent in agents:
                            if isinstance(agent, dict) and str(agent.get("id")) == str(self.bot_agent_id):
                                agent_name = agent.get("name", "XT")
                                break
                        if not agent_name:
                            agent_name = await self._get_default_agent()
                    except Exception as e:
                        logger.warning(f"Could not lookup configured agent: {e}")
                        agent_name = await self._get_default_agent()
                
                chat = ChatCompletions(
                    agent_name=agent_name,
                    api_key=user_token,
                )
            else:
                with get_session() as session:
                    from DB import User
                    user = session.query(User).filter_by(company_id=self.company_id).first()
                    if user:
                        default_token = impersonate_user(str(user.id))
                        
                        # If bot has configured agent, resolve agent name
                        if self.bot_agent_id and not agent_name:
                            try:
                                from InternalClient import InternalClient
                                agixt = InternalClient(api_key=default_token)
                                agents = agixt.get_agents()
                                for agent in agents:
                                    if isinstance(agent, dict) and str(agent.get("id")) == str(self.bot_agent_id):
                                        agent_name = agent.get("name", "XT")
                                        break
                                if not agent_name:
                                    agent_name = await self._get_default_agent()
                            except Exception as e:
                                logger.warning(f"Could not lookup configured agent: {e}")
                                agent_name = await self._get_default_agent()
                        
                        chat = ChatCompletions(
                            agent_name=agent_name,
                            api_key=default_token,
                        )
                    else:
                        return
            
            # Generate response - keep it short for tweets
            response = await chat.chat_completions(
                messages=[
                    {
                        "role": "system",
                        "content": "Keep your response under 280 characters for Twitter.",
                    },
                    {"role": "user", "content": text},
                ],
                conversation_name=conversation_name,
                context_results=5,
            )
            
            if response and isinstance(response, dict):
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    # Prepend @username for reply
                    reply_text = f"@{author_username} {content}"
                    if len(reply_text) > 280:
                        reply_text = reply_text[:277] + "..."
                    await self._reply_to_tweet(tweet_id, reply_text)
                    
        except Exception as e:
            logger.error(f"Error processing mention: {e}")
    
    async def _poll_dms(self):
        """Poll for new DMs."""
        try:
            headers = self._get_headers()
            
            response = requests.get(
                "https://api.x.com/1.1/direct_messages/events/list.json",
                headers=headers,
                params={"count": 50},
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch DMs: {response.status_code} - {response.text}")
                return
            
            data = response.json()
            events = data.get("events", [])
            
            # Build user cache for lookups
            user_cache = {}
            
            for event in events:
                if event["type"] != "message_create":
                    continue
                    
                dm_id = event["id"]
                message_data = event["message_create"]
                sender_id = message_data["sender_id"]
                
                # Skip if we've already processed this
                if dm_id in self.processed_dm_ids:
                    continue
                
                # Skip our own messages
                if sender_id == self.bot_user_id:
                    continue
                
                # Get sender username
                if sender_id not in user_cache:
                    user_response = requests.get(
                        f"https://api.x.com/2/users/{sender_id}",
                        headers=headers,
                        params={"user.fields": "username"},
                    )
                    if user_response.status_code == 200:
                        user_data = user_response.json().get("data", {})
                        user_cache[sender_id] = user_data.get("username", f"user_{sender_id}")
                    else:
                        user_cache[sender_id] = f"user_{sender_id}"
                
                text = message_data["message_data"]["text"]
                
                await self._process_dm(
                    dm_id=dm_id,
                    sender_id=sender_id,
                    sender_username=user_cache[sender_id],
                    text=text,
                )
            
            self.last_dm_check = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error polling DMs: {e}")
    
    async def _poll_mentions(self):
        """Poll for mentions of the bot."""
        try:
            headers = self._get_headers()
            
            # Get our username first
            me_response = requests.get(
                "https://api.x.com/2/users/me",
                headers=headers,
                params={"user.fields": "username"},
            )
            
            if me_response.status_code != 200:
                logger.error(f"Failed to get bot user info: {me_response.status_code}")
                return
            
            bot_username = me_response.json()["data"]["username"]
            
            # Search for recent mentions
            params = {
                "query": f"@{bot_username} -is:retweet",
                "max_results": 20,
                "tweet.fields": "author_id,created_at,conversation_id",
                "expansions": "author_id",
                "user.fields": "username",
            }
            
            response = requests.get(
                "https://api.x.com/2/tweets/search/recent",
                headers=headers,
                params=params,
            )
            
            if response.status_code != 200:
                # Search API might not be available on all account types
                logger.debug(f"Mentions search not available: {response.status_code}")
                return
            
            data = response.json()
            tweets = data.get("data", [])
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
            
            for tweet in tweets:
                tweet_id = tweet["id"]
                author_id = tweet["author_id"]
                
                if tweet_id in self.processed_mention_ids:
                    continue
                
                if author_id == self.bot_user_id:
                    continue
                
                author = users.get(author_id, {})
                author_username = author.get("username", f"user_{author_id}")
                
                # Remove the @mention from the text
                text = tweet["text"]
                text = text.replace(f"@{bot_username}", "").strip()
                
                await self._process_mention(
                    tweet_id=tweet_id,
                    author_id=author_id,
                    author_username=author_username,
                    text=text,
                )
            
            self.last_mention_check = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error polling mentions: {e}")
    
    async def start(self):
        """Start the bot's polling loops."""
        self.is_running = True
        self.started_at = datetime.utcnow()
        
        logger.info(f"Starting X bot for {self.company_name}")
        
        # Run polling loops concurrently
        dm_task = asyncio.create_task(self._dm_poll_loop())
        mention_task = asyncio.create_task(self._mention_poll_loop())
        
        try:
            await asyncio.gather(dm_task, mention_task)
        except asyncio.CancelledError:
            logger.info(f"X bot for {self.company_name} cancelled")
        except Exception as e:
            logger.error(f"X bot error for {self.company_name}: {e}")
        finally:
            self.is_running = False
    
    async def _dm_poll_loop(self):
        """DM polling loop."""
        while self.is_running:
            try:
                await self._poll_dms()
            except Exception as e:
                logger.error(f"DM poll error: {e}")
            
            await asyncio.sleep(self.dm_poll_interval)
    
    async def _mention_poll_loop(self):
        """Mention polling loop."""
        while self.is_running:
            try:
                await self._poll_mentions()
            except Exception as e:
                logger.error(f"Mention poll error: {e}")
            
            await asyncio.sleep(self.mention_poll_interval)
    
    async def stop(self):
        """Stop the bot."""
        logger.info(f"Stopping X bot for {self.company_name}")
        self.is_running = False
    
    def get_status(self) -> XBotStatus:
        """Get current bot status."""
        return XBotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            started_at=self.started_at,
            is_running=self.is_running,
            last_dm_check=self.last_dm_check,
            last_mention_check=self.last_mention_check,
            messages_processed=self.messages_processed,
        )


class XBotManager:
    """
    Manager for all company X bots.
    
    Handles:
    - Starting/stopping bots based on company settings
    - Monitoring bot health
    - Syncing with database configuration
    """
    
    def __init__(self):
        self.bots: Dict[str, CompanyXBot] = {}
        self.bot_tasks: Dict[str, asyncio.Task] = {}
        self._sync_lock = asyncio.Lock()
        self._running = False
        
        logger.info("X Bot Manager initialized")
    
    async def _get_companies_with_x_bot(self) -> List[Dict]:
        """
        Get all companies that have X bot configuration.
        
        Returns:
            List of company configs with X bot settings
        """
        companies = []
        
        with get_session() as session:
            # Query for companies with X bot token set
            settings = (
                session.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.setting_name == "x_bot_token",
                    CompanyExtensionSetting.setting_value.isnot(None),
                    CompanyExtensionSetting.setting_value != "",
                )
                .all()
            )
            
            for setting in settings:
                company = session.query(Company).filter_by(id=setting.company_id).first()
                if not company:
                    continue
                
                # Get bot user ID
                bot_user_id_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="x_bot_user_id",
                    )
                    .first()
                )
                
                # Get enabled setting (default to True if token exists)
                enabled_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="x_bot_enabled",
                    )
                    .first()
                )
                
                is_enabled = True
                if enabled_setting and enabled_setting.setting_value:
                    is_enabled = enabled_setting.setting_value.lower() in ("true", "1", "yes")
                
                if not is_enabled:
                    continue
                
                # Get new permission settings
                agent_id_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="x_bot_agent_id",
                    )
                    .first()
                )
                permission_mode_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="x_bot_permission_mode",
                    )
                    .first()
                )
                owner_id_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="x_bot_owner_id",
                    )
                    .first()
                )
                
                companies.append({
                    "company_id": str(setting.company_id),
                    "company_name": company.name,
                    "bot_token": setting.setting_value,
                    "bot_user_id": bot_user_id_setting.setting_value if bot_user_id_setting else None,
                    "bot_agent_id": agent_id_setting.setting_value if agent_id_setting else None,
                    "bot_permission_mode": permission_mode_setting.setting_value if permission_mode_setting else "recognized_users",
                    "bot_owner_id": owner_id_setting.setting_value if owner_id_setting else None,
                })
        
        return companies
    
    async def sync_bots(self):
        """
        Synchronize running bots with database configuration.
        
        Starts new bots, stops removed ones, updates changed configurations.
        """
        async with self._sync_lock:
            try:
                companies = await self._get_companies_with_x_bot()
                company_ids = {c["company_id"] for c in companies}
                
                # Stop bots for companies that no longer have X bot configured
                for company_id in list(self.bots.keys()):
                    if company_id not in company_ids:
                        await self._stop_bot(company_id)
                
                # Start or update bots for configured companies
                for company_config in companies:
                    company_id = company_config["company_id"]
                    
                    if company_id in self.bots:
                        # Bot already running - check if config changed
                        bot = self.bots[company_id]
                        if bot.bot_token != company_config["bot_token"]:
                            # Token changed - restart bot
                            await self._stop_bot(company_id)
                            await self._start_bot(company_config)
                    else:
                        # New bot - start it
                        await self._start_bot(company_config)
                        
            except Exception as e:
                logger.error(f"Error syncing X bots: {e}")
    
    async def _start_bot(self, config: Dict):
        """Start a bot for a company."""
        company_id = config["company_id"]
        
        try:
            # Get or fetch bot user ID
            bot_user_id = config.get("bot_user_id")
            if not bot_user_id:
                # Fetch from API
                headers = {
                    "Authorization": f"Bearer {config['bot_token']}",
                    "Content-Type": "application/json",
                }
                response = requests.get(
                    "https://api.x.com/2/users/me",
                    headers=headers,
                )
                if response.status_code == 200:
                    bot_user_id = response.json()["data"]["id"]
                    
                    # Save for future use
                    with get_session() as session:
                        setting = CompanyExtensionSetting(
                            company_id=company_id,
                            setting_name="x_bot_user_id",
                            setting_value=bot_user_id,
                        )
                        session.merge(setting)
                        session.commit()
                else:
                    logger.error(f"Failed to get bot user ID for {company_id}: {response.text}")
                    return
            
            bot = CompanyXBot(
                company_id=company_id,
                company_name=config["company_name"],
                bot_token=config["bot_token"],
                bot_user_id=bot_user_id,
                bot_agent_id=config.get("bot_agent_id"),
                bot_permission_mode=config.get("bot_permission_mode", "recognized_users"),
                bot_owner_id=config.get("bot_owner_id"),
            )
            
            self.bots[company_id] = bot
            self.bot_tasks[company_id] = asyncio.create_task(bot.start())
            
            logger.info(f"Started X bot for {config['company_name']}")
            
        except Exception as e:
            logger.error(f"Error starting X bot for {company_id}: {e}")
    
    async def _stop_bot(self, company_id: str):
        """Stop a bot for a company."""
        try:
            if company_id in self.bots:
                bot = self.bots[company_id]
                await bot.stop()
                
            if company_id in self.bot_tasks:
                task = self.bot_tasks[company_id]
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                del self.bot_tasks[company_id]
            
            if company_id in self.bots:
                del self.bots[company_id]
                
            logger.info(f"Stopped X bot for company {company_id}")
            
        except Exception as e:
            logger.error(f"Error stopping X bot for {company_id}: {e}")
    
    async def start(self):
        """Start the bot manager."""
        self._running = True
        logger.info("Starting X Bot Manager")
        
        # Initial sync
        await self.sync_bots()
        
        # Periodic sync loop
        while self._running:
            await asyncio.sleep(60)  # Sync every minute
            await self.sync_bots()
    
    async def stop(self):
        """Stop all bots and the manager."""
        self._running = False
        logger.info("Stopping X Bot Manager")
        
        # Stop all bots
        for company_id in list(self.bots.keys()):
            await self._stop_bot(company_id)
    
    def get_all_status(self) -> List[XBotStatus]:
        """Get status of all bots."""
        return [bot.get_status() for bot in self.bots.values()]
    
    def get_bot_status(self, company_id: str) -> Optional[XBotStatus]:
        """Get status of a specific company's bot."""
        bot = self.bots.get(company_id)
        return bot.get_status() if bot else None


# Global manager instance
_manager: Optional[XBotManager] = None


def get_x_bot_manager() -> Optional[XBotManager]:
    """Get the global X bot manager instance."""
    return _manager


async def start_x_bot_manager():
    """Start the global X bot manager."""
    global _manager
    
    if _manager is not None:
        logger.warning("X Bot Manager already running")
        return
    
    _manager = XBotManager()
    await _manager.start()


async def stop_x_bot_manager():
    """Stop the global X bot manager."""
    global _manager
    
    if _manager is None:
        return
    
    await _manager.stop()
    _manager = None


if __name__ == "__main__":
    # Run the bot manager standalone for testing
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    async def main():
        try:
            await start_x_bot_manager()
        except KeyboardInterrupt:
            await stop_x_bot_manager()
    
    asyncio.run(main())
