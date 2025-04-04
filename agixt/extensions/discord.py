import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Optional
import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class discord(Extensions):
    """
    The Discord extension for AGiXT enables you to interact with Discord servers and channels
    using the user's authenticated account via OAuth2. It allows agents to read messages,
    send messages, manage invites, manage members (kick/ban/mute/roles), manage messages (edit/pin),
    and get server information as the logged-in user. Requires appropriate Discord permissions.
    """

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)  # User's AGiXT JWT
        self.access_token = kwargs.get("DISCORD_ACCESS_TOKEN", None)
        discord_client_id = getenv("DISCORD_CLIENT_ID")
        discord_client_secret = getenv("DISCORD_CLIENT_SECRET")
        self.base_uri = "https://discord.com/api/v10"  # Use Discord API v10
        self.auth = None
        self.commands = {}  # Initialize empty, enable if config is valid

        if discord_client_id and discord_client_secret:
            # Define commands only if Discord SSO is configured
            self.commands = {
                "Discord - Send Message": self.send_message,
                "Discord - Get Messages": self.get_messages,
                "Discord - Delete Message": self.delete_message,
                "Discord - Create Invite": self.create_invite,
                "Discord - Get Servers (Guilds)": self.get_guilds,
                "Discord - Get Server Information": self.get_guild_info,
                "Discord - Get Channels in Server": self.get_guild_channels,
                "Discord - Edit Message": self.edit_message,
                "Discord - Pin Message": self.pin_message,
                "Discord - Unpin Message": self.unpin_message,
                "Discord - Kick Member": self.kick_member,
                "Discord - Ban Member": self.ban_member,
                "Discord - Unban Member": self.unban_member,
                "Discord - Mute Member (Timeout)": self.timeout_member,
                "Discord - Unmute Member (Remove Timeout)": self.remove_timeout,
                "Discord - Add Role to Member": self.add_role_to_member,
                "Discord - Remove Role from Member": self.remove_role_from_member,
                "Discord - Get Server Roles": self.get_guild_roles,
                "Discord - Get Guild Members": self.get_guild_members,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(
                        f"Error initializing Discord extension auth: {str(e)}"
                    )

    def _get_headers(self):
        """Returns the authorization headers for Discord API requests."""
        if not self.access_token:
            raise Exception("Discord Access Token is missing.")
        # Always include Content-Type for POST/PATCH/PUT
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def verify_user(self):
        """
        Verifies the access token and refreshes it if necessary using MagicalAuth.
        """
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            # Refresh token via MagicalAuth, which handles expiry checks
            refreshed_token = self.auth.refresh_oauth_token(provider="discord")
            if not refreshed_token:
                # If refresh failed but we still have an old token, try using it
                if not self.access_token:
                    raise Exception(
                        "Failed to refresh Discord token and no existing token available."
                    )
                else:
                    logging.warning(
                        "Failed to refresh Discord token, attempting with existing token."
                    )
            else:
                self.access_token = (
                    refreshed_token  # Update with the new or existing token
                )
            logging.info("Discord token verified/refreshed successfully.")
        except Exception as e:
            logging.error(f"Error verifying/refreshing Discord token: {str(e)}")
            raise Exception(
                f"Discord authentication error: {str(e)}"
            )  # Re-raise for command handling

    async def get_guild_members(
        self, guild_id: str, limit: int = 100, after: Optional[str] = None
    ):
        """
        Get a list of members in a specific Discord server (guild).

        Args:
            guild_id (str): The ID of the server.
            limit (int): Max number of members to retrieve (1-1000). Default 100.
            after (str, optional): Get members whose user ID is alphabetically after the specified ID (for pagination).

        Returns:
            list: List of member objects (user_id, username, nickname, roles, joined_at) or error string.
        """
        try:
            self.verify_user()
            # Validate limit (Discord API max is 1000)
            limit = max(1, min(limit, 1000))
            url = f"{self.base_uri}/guilds/{guild_id}/members"
            params = {"limit": limit}
            if after:
                params["after"] = after

            # Use GET headers without Content-Type
            get_headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=get_headers, params=params)
            response.raise_for_status()
            members_data = response.json()  # Response is a list of member objects

            formatted_members = []
            for member in members_data:
                user_info = member.get("user", {})
                formatted_members.append(
                    {
                        "user_id": user_info.get("id"),
                        "username": user_info.get("username"),
                        "global_name": user_info.get(
                            "global_name"
                        ),  # Newer display name
                        "nickname": member.get("nick"),  # Server-specific nickname
                        "roles": member.get("roles", []),  # List of role IDs
                        "joined_at": member.get("joined_at"),
                        "is_pending": member.get(
                            "pending", False
                        ),  # If user hasn't passed membership screening
                        "avatar": user_info.get("avatar"),  # User avatar hash
                        "guild_avatar": member.get(
                            "avatar"
                        ),  # Server-specific avatar hash
                    }
                )

            return formatted_members

        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error getting Discord guild members: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error getting members: Permission denied or missing 'guilds.members.read' scope in guild {guild_id}."
            elif status_code == 404:
                return f"Error getting members: Guild {guild_id} not found."
            else:
                return f"Error getting members: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting Discord guild members: {str(e)}")
            return f"Error getting members: {str(e)}"

    async def send_message(self, channel_id: str, content: str):
        """
        Send a message to a Discord channel as the authenticated user.

        Args:
            channel_id (str): The ID of the Discord channel.
            content (str): The content of the message. Max 2000 characters.

        Returns:
            str: Confirmation message or error.
        """
        if len(content) > 2000:
            return "Error: Message content cannot exceed 2000 characters."
        try:
            self.verify_user()
            url = f"{self.base_uri}/channels/{channel_id}/messages"
            payload = {"content": content}
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            message_id = response.json().get("id", "Unknown ID")
            return f"Message sent successfully to channel {channel_id}. Message ID: {message_id}"
        except Exception as e:
            logging.error(f"Error sending Discord message: {str(e)}")
            return f"Error sending message: {str(e)}"

    async def get_messages(self, channel_id: str, limit: int = 50):
        """
        Get messages from a Discord channel.

        Args:
            channel_id (str): The ID of the Discord channel.
            limit (int): Max number of messages to retrieve (1-100). Default 50.

        Returns:
            list: List of message objects (id, author_id, author_username, content, timestamp) or error string.
        """
        try:
            self.verify_user()
            limit = max(1, min(limit, 100))
            url = f"{self.base_uri}/channels/{channel_id}/messages?limit={limit}"
            # Use GET headers without Content-Type
            get_headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=get_headers)
            response.raise_for_status()
            messages = response.json()
            formatted_messages = [
                {
                    "id": msg.get("id"),
                    "author_id": msg.get("author", {}).get("id"),
                    "author_username": msg.get("author", {}).get("username"),
                    "content": msg.get("content"),
                    "timestamp": msg.get("timestamp"),
                }
                for msg in messages
            ]
            return formatted_messages
        except Exception as e:
            logging.error(f"Error getting Discord messages: {str(e)}")
            return f"Error getting messages: {str(e)}"

    async def delete_message(self, channel_id: str, message_id: str):
        """
        Delete a message from a Discord channel. Requires 'Manage Messages' permission if deleting others' messages.

        Args:
            channel_id (str): The ID of the Discord channel.
            message_id (str): The ID of the message to delete.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/channels/{channel_id}/messages/{message_id}"
            # Use GET headers without Content-Type for DELETE
            delete_headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.delete(url, headers=delete_headers)
            response.raise_for_status()  # Will raise HTTPError for 4xx/5xx
            # Discord returns 204 No Content on successful deletion
            if response.status_code == 204:
                return f"Message {message_id} deleted successfully from channel {channel_id}."
            else:
                # Should technically not be reached if raise_for_status works, but belt-and-suspenders
                return f"Deleted message {message_id}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error deleting Discord message: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error deleting message {message_id}: Permission denied. You might not have the rights to delete this message."
            elif status_code == 404:
                return f"Error deleting message {message_id}: Message not found."
            else:
                return f"Error deleting message {message_id}: {str(e)}"
        except Exception as e:
            logging.error(f"Error deleting Discord message: {str(e)}")
            return f"Error deleting message: {str(e)}"

    async def create_invite(
        self, channel_id: str, max_age_seconds: int = 86400, max_uses: int = 0
    ):
        """
        Create an invite to a Discord channel. Requires 'Create Invite' permission in the channel.

        Args:
            channel_id (str): The ID of the Discord channel.
            max_age_seconds (int): Duration of invite in seconds (0 for never expires). Default 24 hours.
            max_uses (int): Max number of uses (0 for unlimited). Default unlimited.

        Returns:
            str: The invite URL (e.g., https://discord.gg/CODE) or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/channels/{channel_id}/invites"
            payload = {
                "max_age": max_age_seconds,
                "max_uses": max_uses,
                "temporary": False,  # Make invite grant temporary membership if true (user kicked on disconnect)
                "unique": True,  # Request a unique invite code to avoid collisions
            }
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            invite_code = response.json().get("code")
            if invite_code:
                return f"https://discord.gg/{invite_code}"
            else:
                return "Error: Invite created but code not found in response."
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error creating Discord invite: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error creating invite: Permission denied. Ensure the user has 'Create Invite' permission in channel {channel_id}."
            elif status_code == 404:
                return f"Error creating invite: Channel {channel_id} not found."
            else:
                return f"Error creating invite: {str(e)}"
        except Exception as e:
            logging.error(f"Error creating Discord invite: {str(e)}")
            return f"Error creating invite: {str(e)}"

    async def get_guilds(self):
        """
        Get the list of servers (guilds) the authenticated user is a member of.

        Returns:
            list: List of guild objects (id, name, icon hash, is_owner) or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/users/@me/guilds"
            # Use GET headers without Content-Type
            get_headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=get_headers)
            response.raise_for_status()
            guilds_data = response.json()
            formatted_guilds = [
                {
                    "id": guild.get("id"),
                    "name": guild.get("name"),
                    "icon": guild.get("icon"),  # Icon hash
                    "owner": guild.get("owner", False),  # Is the user the owner?
                }
                for guild in guilds_data
            ]
            return formatted_guilds
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error getting Discord guilds: {str(e)} - Response: {e.response.text}"
            )
            if e.response.status_code == 401 and "scope" in e.response.text.lower():
                return f"Error getting guilds: Missing 'guilds' scope. Please re-authenticate with Discord."
            return f"Error getting guilds: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting Discord guilds: {str(e)}")
            return f"Error getting guilds: {str(e)}"

    async def get_guild_info(self, guild_id: str):
        """
        Get detailed information about a specific Discord server (guild). User must be a member.

        Args:
            guild_id (str): The ID of the Discord server.

        Returns:
            dict: Dictionary containing server information or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}?with_counts=true"  # Add counts for members
            # Use GET headers without Content-Type
            get_headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=get_headers)
            response.raise_for_status()
            guild_data = response.json()
            formatted_info = {
                "id": guild_data.get("id"),
                "name": guild_data.get("name"),
                "description": guild_data.get("description"),
                "owner_id": guild_data.get("owner_id"),
                "member_count": guild_data.get("approximate_member_count"),
                "presence_count": guild_data.get(
                    "approximate_presence_count"
                ),  # Online members
                "icon": guild_data.get("icon"),  # Icon hash
                "splash": guild_data.get("splash"),  # Invite splash hash
                "banner": guild_data.get("banner"),  # Server banner hash
                "features": guild_data.get("features", []),
                "verification_level": guild_data.get("verification_level"),
                "vanity_url_code": guild_data.get("vanity_url_code"),
            }
            return formatted_info
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error getting Discord guild info: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error getting guild info: Access denied. User might not be a member of guild {guild_id} or lack permissions."
            elif status_code == 404:
                return f"Error getting guild info: Guild {guild_id} not found."
            else:
                return f"Error getting guild info: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting Discord guild info: {str(e)}")
            return f"Error getting guild info: {str(e)}"

    async def get_guild_channels(self, guild_id: str):
        """
        Get the list of channels in a specific Discord server (guild).

        Args:
            guild_id (str): The ID of the Discord server.

        Returns:
            list: List of channel objects (id, name, type, position, parent_id) or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/channels"
            # Use GET headers without Content-Type
            get_headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=get_headers)
            response.raise_for_status()
            channels_data = response.json()
            channel_types = {
                0: "Text",
                1: "DM",
                2: "Voice",
                3: "Group DM",
                4: "Category",
                5: "News",
                10: "News Thread",
                11: "Public Thread",
                12: "Private Thread",
                13: "Stage Voice",
                14: "Directory",
                15: "Forum",
            }
            formatted_channels = [
                {
                    "id": channel.get("id"),
                    "name": channel.get("name"),
                    "type": channel_types.get(channel.get("type"), "Unknown"),
                    "position": channel.get("position"),
                    "parent_id": channel.get(
                        "parent_id"
                    ),  # Useful for category grouping
                }
                for channel in channels_data
            ]
            formatted_channels.sort(
                key=lambda x: x.get("position", 0)
            )  # Sort by visual order
            return formatted_channels
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error getting Discord guild channels: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error getting channels: Access denied. User might not be a member or lack permissions in guild {guild_id}."
            elif status_code == 404:
                return f"Error getting channels: Guild {guild_id} not found."
            else:
                return f"Error getting channels: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting Discord guild channels: {str(e)}")
            return f"Error getting channels: {str(e)}"

    # --- New Moderation/Management Commands ---

    async def edit_message(self, channel_id: str, message_id: str, new_content: str):
        """
        Edit a message sent by the authenticated user. Cannot edit other users' messages.

        Args:
            channel_id (str): The ID of the Discord channel.
            message_id (str): The ID of the message to edit.
            new_content (str): The new content for the message. Max 2000 characters.

        Returns:
            str: Confirmation message or error.
        """
        if len(new_content) > 2000:
            return "Error: New message content cannot exceed 2000 characters."
        try:
            self.verify_user()
            url = f"{self.base_uri}/channels/{channel_id}/messages/{message_id}"
            payload = {"content": new_content}
            response = requests.patch(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return f"Message {message_id} edited successfully in channel {channel_id}."
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error editing Discord message: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error editing message {message_id}: Permission denied. You can only edit your own messages."
            elif status_code == 404:
                return (
                    f"Error editing message {message_id}: Message or Channel not found."
                )
            else:
                return f"Error editing message {message_id}: {str(e)}"
        except Exception as e:
            logging.error(f"Error editing Discord message: {str(e)}")
            return f"Error editing message: {str(e)}"

    async def pin_message(self, channel_id: str, message_id: str):
        """
        Pin a message in a channel. Requires 'Manage Messages' permission.

        Args:
            channel_id (str): The ID of the Discord channel.
            message_id (str): The ID of the message to pin.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/channels/{channel_id}/pins/{message_id}"
            # PUT request needs Content-Length: 0 header if no body
            put_headers = self._get_headers()
            put_headers["Content-Length"] = "0"
            response = requests.put(url, headers=put_headers)
            response.raise_for_status()  # Raises for 4xx/5xx
            # Successful pin returns 204 No Content
            if response.status_code == 204:
                return (
                    f"Message {message_id} pinned successfully in channel {channel_id}."
                )
            else:
                return f"Pinned message {message_id}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error pinning Discord message: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error pinning message {message_id}: Permission denied. Requires 'Manage Messages' permission."
            elif status_code == 404:
                return (
                    f"Error pinning message {message_id}: Message or Channel not found."
                )
            else:
                return f"Error pinning message {message_id}: {str(e)}"
        except Exception as e:
            logging.error(f"Error pinning Discord message: {str(e)}")
            return f"Error pinning message: {str(e)}"

    async def unpin_message(self, channel_id: str, message_id: str):
        """
        Unpin a message in a channel. Requires 'Manage Messages' permission.

        Args:
            channel_id (str): The ID of the Discord channel.
            message_id (str): The ID of the message to unpin.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/channels/{channel_id}/pins/{message_id}"
            # Use GET headers without Content-Type for DELETE
            delete_headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.delete(url, headers=delete_headers)
            response.raise_for_status()  # Raises for 4xx/5xx
            if response.status_code == 204:
                return f"Message {message_id} unpinned successfully in channel {channel_id}."
            else:
                return f"Unpinned message {message_id}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error unpinning Discord message: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error unpinning message {message_id}: Permission denied. Requires 'Manage Messages' permission."
            elif status_code == 404:
                return f"Error unpinning message {message_id}: Message or Channel not found."
            else:
                return f"Error unpinning message {message_id}: {str(e)}"
        except Exception as e:
            logging.error(f"Error unpinning Discord message: {str(e)}")
            return f"Error unpinning message: {str(e)}"

    async def kick_member(
        self, guild_id: str, user_id_to_kick: str, reason: Optional[str] = None
    ):
        """
        Kick a member from a server (guild). Requires 'Kick Members' permission.

        Args:
            guild_id (str): The ID of the server.
            user_id_to_kick (str): The ID of the user to kick.
            reason (str, optional): Reason for kicking the member (shows in Audit Log).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/members/{user_id_to_kick}"
            # Use GET headers without Content-Type for DELETE
            delete_headers = {"Authorization": f"Bearer {self.access_token}"}
            # Add reason to Audit Log header if provided
            if reason:
                delete_headers["X-Audit-Log-Reason"] = reason

            response = requests.delete(url, headers=delete_headers)
            response.raise_for_status()
            if response.status_code == 204:
                return (
                    f"User {user_id_to_kick} kicked successfully from guild {guild_id}."
                    + (f" Reason: {reason}" if reason else "")
                )
            else:
                return f"Kicked user {user_id_to_kick}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error kicking Discord member: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error kicking user {user_id_to_kick}: Permission denied. Requires 'Kick Members' permission."
            elif status_code == 404:
                return f"Error kicking user {user_id_to_kick}: User or Guild not found."
            else:
                return f"Error kicking user {user_id_to_kick}: {str(e)}"
        except Exception as e:
            logging.error(f"Error kicking Discord member: {str(e)}")
            return f"Error kicking member: {str(e)}"

    async def ban_member(
        self,
        guild_id: str,
        user_id_to_ban: str,
        reason: Optional[str] = None,
        delete_message_days: int = 0,
    ):
        """
        Ban a member from a server (guild). Requires 'Ban Members' permission.

        Args:
            guild_id (str): The ID of the server.
            user_id_to_ban (str): The ID of the user to ban.
            reason (str, optional): Reason for banning the member (shows in Audit Log).
            delete_message_days (int): Number of days of messages to delete (0-7). Default 0.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/bans/{user_id_to_ban}"
            put_headers = self._get_headers()
            # Add reason to Audit Log header if provided
            if reason:
                put_headers["X-Audit-Log-Reason"] = reason

            payload = {"delete_message_days": max(0, min(delete_message_days, 7))}

            response = requests.put(url, headers=put_headers, json=payload)
            response.raise_for_status()
            if response.status_code == 204:
                return (
                    f"User {user_id_to_ban} banned successfully from guild {guild_id}."
                    + (f" Reason: {reason}" if reason else "")
                )
            else:
                return f"Banned user {user_id_to_ban}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error banning Discord member: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error banning user {user_id_to_ban}: Permission denied. Requires 'Ban Members' permission."
            elif status_code == 404:
                return f"Error banning user {user_id_to_ban}: User or Guild not found."
            else:
                return f"Error banning user {user_id_to_ban}: {str(e)}"
        except Exception as e:
            logging.error(f"Error banning Discord member: {str(e)}")
            return f"Error banning member: {str(e)}"

    async def unban_member(
        self, guild_id: str, user_id_to_unban: str, reason: Optional[str] = None
    ):
        """
        Unban a member from a server (guild). Requires 'Ban Members' permission.

        Args:
            guild_id (str): The ID of the server.
            user_id_to_unban (str): The ID of the user to unban.
            reason (str, optional): Reason for unbanning (shows in Audit Log).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/bans/{user_id_to_unban}"
            # Use GET headers without Content-Type for DELETE
            delete_headers = {"Authorization": f"Bearer {self.access_token}"}
            if reason:
                delete_headers["X-Audit-Log-Reason"] = reason

            response = requests.delete(url, headers=delete_headers)
            response.raise_for_status()
            if response.status_code == 204:
                return (
                    f"User {user_id_to_unban} unbanned successfully from guild {guild_id}."
                    + (f" Reason: {reason}" if reason else "")
                )
            else:
                return f"Unbanned user {user_id_to_unban}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error unbanning Discord member: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error unbanning user {user_id_to_unban}: Permission denied. Requires 'Ban Members' permission."
            elif status_code == 404:
                return f"Error unbanning user {user_id_to_unban}: User or Guild not found, or user was not banned."
            else:
                return f"Error unbanning user {user_id_to_unban}: {str(e)}"
        except Exception as e:
            logging.error(f"Error unbanning Discord member: {str(e)}")
            return f"Error unbanning member: {str(e)}"

    async def timeout_member(
        self,
        guild_id: str,
        user_id_to_timeout: str,
        duration_seconds: int,
        reason: Optional[str] = None,
    ):
        """
        Timeout (mute) a member in a server. Requires 'Moderate Members' permission.

        Args:
            guild_id (str): The ID of the server.
            user_id_to_timeout (str): The ID of the user to timeout.
            duration_seconds (int): Duration of the timeout in seconds (max 28 days = 2419200 seconds).
            reason (str, optional): Reason for the timeout (shows in Audit Log).

        Returns:
            str: Confirmation message or error.
        """
        if duration_seconds <= 0 or duration_seconds > 2419200:
            return "Error: Timeout duration must be between 1 second and 28 days."
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/members/{user_id_to_timeout}"
            patch_headers = self._get_headers()
            if reason:
                patch_headers["X-Audit-Log-Reason"] = reason

            # Calculate timeout end timestamp in ISO 8601 format
            timeout_end_time = datetime.datetime.utcnow() + datetime.timedelta(
                seconds=duration_seconds
            )
            timeout_iso = (
                timeout_end_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            )  # ISO 8601 format

            payload = {"communication_disabled_until": timeout_iso}

            response = requests.patch(url, headers=patch_headers, json=payload)
            response.raise_for_status()
            if response.status_code == 200:  # PATCH returns 200 on success
                return (
                    f"User {user_id_to_timeout} timed out successfully in guild {guild_id} for {duration_seconds} seconds."
                    + (f" Reason: {reason}" if reason else "")
                )
            else:
                return f"Timed out user {user_id_to_timeout}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error timing out Discord member: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error timing out user {user_id_to_timeout}: Permission denied. Requires 'Moderate Members' permission."
            elif status_code == 404:
                return f"Error timing out user {user_id_to_timeout}: User or Guild not found."
            else:
                return f"Error timing out user {user_id_to_timeout}: {str(e)}"
        except Exception as e:
            logging.error(f"Error timing out Discord member: {str(e)}")
            return f"Error timing out member: {str(e)}"

    async def remove_timeout(
        self, guild_id: str, user_id_to_unmute: str, reason: Optional[str] = None
    ):
        """
        Remove timeout (unmute) for a member. Requires 'Moderate Members' permission.

        Args:
            guild_id (str): The ID of the server.
            user_id_to_unmute (str): The ID of the user to remove timeout from.
            reason (str, optional): Reason for removing timeout (shows in Audit Log).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/members/{user_id_to_unmute}"
            patch_headers = self._get_headers()
            if reason:
                patch_headers["X-Audit-Log-Reason"] = reason

            # Set communication_disabled_until to null to remove timeout
            payload = {"communication_disabled_until": None}

            response = requests.patch(url, headers=patch_headers, json=payload)
            response.raise_for_status()
            if response.status_code == 200:
                return (
                    f"Timeout removed successfully for user {user_id_to_unmute} in guild {guild_id}."
                    + (f" Reason: {reason}" if reason else "")
                )
            else:
                return f"Removed timeout for user {user_id_to_unmute}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error removing Discord member timeout: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error removing timeout for user {user_id_to_unmute}: Permission denied. Requires 'Moderate Members' permission."
            elif status_code == 404:
                return f"Error removing timeout for user {user_id_to_unmute}: User or Guild not found."
            else:
                return f"Error removing timeout for user {user_id_to_unmute}: {str(e)}"
        except Exception as e:
            logging.error(f"Error removing Discord member timeout: {str(e)}")
            return f"Error removing timeout: {str(e)}"

    async def add_role_to_member(
        self,
        guild_id: str,
        user_id_to_modify: str,
        role_id: str,
        reason: Optional[str] = None,
    ):
        """
        Add a role to a member in a server. Requires 'Manage Roles' permission.

        Args:
            guild_id (str): The ID of the server.
            user_id_to_modify (str): The ID of the user to add the role to.
            role_id (str): The ID of the role to add.
            reason (str, optional): Reason for adding the role (shows in Audit Log).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/members/{user_id_to_modify}/roles/{role_id}"
            # PUT requires Content-Length: 0 if no body
            put_headers = self._get_headers()
            put_headers["Content-Length"] = "0"
            if reason:
                put_headers["X-Audit-Log-Reason"] = reason

            response = requests.put(url, headers=put_headers)
            response.raise_for_status()
            if response.status_code == 204:
                return (
                    f"Role {role_id} added successfully to user {user_id_to_modify} in guild {guild_id}."
                    + (f" Reason: {reason}" if reason else "")
                )
            else:
                return f"Added role {role_id} to user {user_id_to_modify}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error adding Discord role: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error adding role {role_id} to user {user_id_to_modify}: Permission denied. Requires 'Manage Roles' permission."
            elif status_code == 404:
                return f"Error adding role {role_id} to user {user_id_to_modify}: User, Guild, or Role not found."
            else:
                return (
                    f"Error adding role {role_id} to user {user_id_to_modify}: {str(e)}"
                )
        except Exception as e:
            logging.error(f"Error adding Discord role: {str(e)}")
            return f"Error adding role: {str(e)}"

    async def remove_role_from_member(
        self,
        guild_id: str,
        user_id_to_modify: str,
        role_id: str,
        reason: Optional[str] = None,
    ):
        """
        Remove a role from a member in a server. Requires 'Manage Roles' permission.

        Args:
            guild_id (str): The ID of the server.
            user_id_to_modify (str): The ID of the user to remove the role from.
            role_id (str): The ID of the role to remove.
            reason (str, optional): Reason for removing the role (shows in Audit Log).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/members/{user_id_to_modify}/roles/{role_id}"
            # Use GET headers without Content-Type for DELETE
            delete_headers = {"Authorization": f"Bearer {self.access_token}"}
            if reason:
                delete_headers["X-Audit-Log-Reason"] = reason

            response = requests.delete(url, headers=delete_headers)
            response.raise_for_status()
            if response.status_code == 204:
                return (
                    f"Role {role_id} removed successfully from user {user_id_to_modify} in guild {guild_id}."
                    + (f" Reason: {reason}" if reason else "")
                )
            else:
                return f"Removed role {role_id} from user {user_id_to_modify}, but received unexpected status code: {response.status_code}"
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error removing Discord role: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error removing role {role_id} from user {user_id_to_modify}: Permission denied. Requires 'Manage Roles' permission."
            elif status_code == 404:
                return f"Error removing role {role_id} from user {user_id_to_modify}: User, Guild, or Role not found."
            else:
                return f"Error removing role {role_id} from user {user_id_to_modify}: {str(e)}"
        except Exception as e:
            logging.error(f"Error removing Discord role: {str(e)}")
            return f"Error removing role: {str(e)}"

    async def get_guild_roles(self, guild_id: str):
        """
        Get the list of roles in a specific Discord server (guild).

        Args:
            guild_id (str): The ID of the server.

        Returns:
            list: List of role objects (id, name, color, position) or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/guilds/{guild_id}/roles"
            # Use GET headers without Content-Type
            get_headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=get_headers)
            response.raise_for_status()
            roles_data = response.json()
            formatted_roles = [
                {
                    "id": role.get("id"),
                    "name": role.get("name"),
                    "color": role.get("color"),  # Decimal color value
                    "position": role.get("position"),  # Position in role hierarchy
                    "permissions": role.get(
                        "permissions"
                    ),  # Permissions bitwise value as string
                }
                for role in roles_data
            ]
            # Sort roles by position (visual order in Discord settings)
            formatted_roles.sort(key=lambda x: x.get("position", 0), reverse=True)
            return formatted_roles
        except requests.exceptions.HTTPError as e:
            logging.error(
                f"Error getting Discord guild roles: {str(e)} - Response: {e.response.text}"
            )
            status_code = e.response.status_code
            if status_code == 403:
                return f"Error getting roles: Access denied. User might not be a member or lack permissions in guild {guild_id}."
            elif status_code == 404:
                return f"Error getting roles: Guild {guild_id} not found."
            else:
                return f"Error getting roles: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting Discord guild roles: {str(e)}")
            return f"Error getting roles: {str(e)}"
