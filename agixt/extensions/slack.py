import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Optional, List
import datetime
from fastapi import HTTPException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


"""
Required environment variables:

- SLACK_CLIENT_ID: Slack OAuth client ID
- SLACK_CLIENT_SECRET: Slack OAuth client secret
- SLACK_BOT_TOKEN: Slack Bot User OAuth Token (xoxb-...) for bot functionality
- SLACK_SIGNING_SECRET: Slack app signing secret for webhook verification

Required scopes for Slack OAuth:

User Token Scopes:
- chat:write: Post messages as the user
- channels:read: View basic channel information
- channels:history: View messages in channels
- groups:read: View private channels
- groups:history: View messages in private channels
- im:read: View direct messages
- im:history: View DM history
- mpim:read: View group DMs
- mpim:history: View group DM history
- users:read: View users
- users:read.email: View email addresses
- files:read: View files
- files:write: Upload files
- reactions:read: View emoji reactions
- reactions:write: Add emoji reactions

Bot Token Scopes (for SlackBotManager):
- app_mentions:read: Receive messages that mention the bot
- chat:write: Post messages
- channels:history: View messages
- groups:history: View private channel messages
- im:history: View DM history
- mpim:history: View group DM history
- users:read: View users
"""

SCOPES = [
    "chat:write",
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:read",
    "im:history",
    "mpim:read",
    "mpim:history",
    "users:read",
    "users:read.email",
    "files:read",
    "files:write",
    "reactions:read",
    "reactions:write",
]
AUTHORIZE = "https://slack.com/oauth/v2/authorize"
TOKEN_URL = "https://slack.com/api/oauth.v2.access"
USER_INFO_URL = "https://slack.com/api/users.identity"
PKCE_REQUIRED = False
SSO_ONLY = False  # Slack is a full extension with bot commands, not just SSO
LOGIN_CAPABLE = True  # Slack can also be used for login/registration


class SlackSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("SLACK_CLIENT_ID")
        self.client_secret = getenv("SLACK_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refreshes the Slack access token using the refresh token."""
        if not self.refresh_token:
            raise HTTPException(
                status_code=400, detail="No refresh token available for Slack."
            )

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }

        try:
            response = requests.post(TOKEN_URL, data=payload)
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                raise Exception(f"Slack token refresh failed: {data.get('error')}")

            self.access_token = data.get("access_token")
            if "refresh_token" in data:
                self.refresh_token = data.get("refresh_token")

            logging.info("Successfully refreshed Slack token.")
            return data
        except requests.exceptions.RequestException as e:
            logging.error(f"Error refreshing Slack token: {e}")
            raise HTTPException(
                status_code=401, detail=f"Failed to refresh Slack token: {str(e)}"
            )

    def get_user_info(self):
        """Gets user information from Slack API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = requests.get(USER_INFO_URL, headers=headers)

            if response.status_code == 401:
                logging.info("Slack token likely expired, attempting refresh.")
                self.access_token = self.get_new_token().get("access_token")
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(USER_INFO_URL, headers=headers)

            data = response.json()

            if not data.get("ok"):
                # Try alternative endpoint for bot tokens
                response = requests.get(
                    "https://slack.com/api/auth.test", headers=headers
                )
                data = response.json()
                if not data.get("ok"):
                    raise Exception(f"Slack API error: {data.get('error')}")

                # Get user info from users.info
                user_id = data.get("user_id")
                if user_id:
                    user_response = requests.get(
                        f"https://slack.com/api/users.info?user={user_id}",
                        headers=headers,
                    )
                    user_data = user_response.json()
                    if user_data.get("ok"):
                        user = user_data.get("user", {})
                        profile = user.get("profile", {})
                        return {
                            "email": profile.get("email", ""),
                            "first_name": profile.get("first_name", user.get("name", "")),
                            "last_name": profile.get("last_name", ""),
                            "provider_user_id": user.get("id"),
                        }

            user = data.get("user", {})
            team = data.get("team", {})
            return {
                "email": user.get("email", ""),
                "first_name": user.get("name", "").split()[0] if user.get("name") else "",
                "last_name": " ".join(user.get("name", "").split()[1:]) if user.get("name") else "",
                "provider_user_id": user.get("id"),
            }
        except requests.exceptions.RequestException as e:
            logging.error(f"Error getting user info from Slack: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Slack: {str(e)}",
            )


def sso(code, redirect_uri=None) -> SlackSSO:
    """Handles the OAuth2 authorization code flow for Slack."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("SLACK_CLIENT_ID")
    client_secret = getenv("SLACK_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Slack Client ID or Secret not configured.")
        return None

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }

    try:
        response = requests.post(TOKEN_URL, data=payload)
        data = response.json()

        if not data.get("ok"):
            logging.error(f"Slack OAuth error: {data.get('error')}")
            return None

        # Slack returns authed_user for user tokens
        authed_user = data.get("authed_user", {})
        access_token = authed_user.get("access_token") or data.get("access_token")
        refresh_token = authed_user.get("refresh_token") or data.get("refresh_token")

        logging.info("Slack token obtained successfully.")
        return SlackSSO(access_token=access_token, refresh_token=refresh_token)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error obtaining Slack access token: {e}")
        return None


def get_authorization_url(state=None):
    """Generate Slack authorization URL"""
    from urllib.parse import urlencode

    client_id = getenv("SLACK_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(SCOPES),
        "user_scope": ",".join(SCOPES),
    }

    if state:
        params["state"] = state

    query = urlencode(params)
    return f"{AUTHORIZE}?{query}"


class slack(Extensions):
    """
    The Slack extension for AGiXT enables you to interact with Slack workspaces
    using the user's authenticated account via OAuth2. It allows agents to read messages,
    send messages, manage channels, upload files, and interact with users.
    Requires appropriate Slack permissions and OAuth scopes.
    """

    CATEGORY = "Social & Communication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("SLACK_ACCESS_TOKEN", None)
        slack_client_id = getenv("SLACK_CLIENT_ID")
        slack_client_secret = getenv("SLACK_CLIENT_SECRET")
        self.base_uri = "https://slack.com/api"
        self.auth = None
        self.commands = {}

        if slack_client_id and slack_client_secret:
            self.commands = {
                "Slack - Send Message": self.send_message,
                "Slack - Get Messages": self.get_messages,
                "Slack - Delete Message": self.delete_message,
                "Slack - Get Channels": self.get_channels,
                "Slack - Get Channel Info": self.get_channel_info,
                "Slack - Get Users": self.get_users,
                "Slack - Get User Info": self.get_user_info,
                "Slack - Upload File": self.upload_file,
                "Slack - Add Reaction": self.add_reaction,
                "Slack - Remove Reaction": self.remove_reaction,
                "Slack - Create Channel": self.create_channel,
                "Slack - Invite to Channel": self.invite_to_channel,
                "Slack - Search Messages": self.search_messages,
                "Slack - Get Thread Replies": self.get_thread_replies,
                "Slack - Post Thread Reply": self.post_thread_reply,
                "Slack - Set Channel Topic": self.set_channel_topic,
                "Slack - Get Workspace Info": self.get_workspace_info,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Slack extension auth: {str(e)}")

    def _get_headers(self):
        """Returns the authorization headers for Slack API requests."""
        if not self.access_token:
            raise Exception("Slack Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def verify_user(self):
        """Verifies the access token and refreshes it if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="slack")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("slack_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
            logging.info("Slack token verified/refreshed successfully.")
        except Exception as e:
            logging.error(f"Error verifying/refreshing Slack token: {str(e)}")
            raise Exception(f"Slack authentication error: {str(e)}")

    async def send_message(self, channel_id: str, text: str, thread_ts: str = None):
        """
        Send a message to a Slack channel.

        Args:
            channel_id (str): The ID of the Slack channel.
            text (str): The message content.
            thread_ts (str, optional): Thread timestamp to reply in a thread.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/chat.postMessage"
            payload = {"channel": channel_id, "text": text}
            if thread_ts:
                payload["thread_ts"] = thread_ts

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error sending message: {data.get('error')}"

            ts = data.get("ts", "Unknown")
            return f"Message sent successfully to channel {channel_id}. Message timestamp: {ts}"
        except Exception as e:
            logging.error(f"Error sending Slack message: {str(e)}")
            return f"Error sending message: {str(e)}"

    async def get_messages(self, channel_id: str, limit: int = 50, oldest: str = None, latest: str = None):
        """
        Get messages from a Slack channel.

        Args:
            channel_id (str): The ID of the Slack channel.
            limit (int): Max number of messages to retrieve (1-100). Default 50.
            oldest (str, optional): Start of time range (unix timestamp).
            latest (str, optional): End of time range (unix timestamp).

        Returns:
            list: List of message objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.history"
            params = {"channel": channel_id, "limit": min(limit, 100)}
            if oldest:
                params["oldest"] = oldest
            if latest:
                params["latest"] = latest

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            if not data.get("ok"):
                return f"Error getting messages: {data.get('error')}"

            messages = data.get("messages", [])
            formatted_messages = [
                {
                    "ts": msg.get("ts"),
                    "user": msg.get("user"),
                    "text": msg.get("text"),
                    "thread_ts": msg.get("thread_ts"),
                    "reply_count": msg.get("reply_count", 0),
                    "reactions": msg.get("reactions", []),
                }
                for msg in messages
            ]
            return formatted_messages
        except Exception as e:
            logging.error(f"Error getting Slack messages: {str(e)}")
            return f"Error getting messages: {str(e)}"

    async def delete_message(self, channel_id: str, ts: str):
        """
        Delete a message from a Slack channel.

        Args:
            channel_id (str): The ID of the Slack channel.
            ts (str): The timestamp of the message to delete.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/chat.delete"
            payload = {"channel": channel_id, "ts": ts}

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error deleting message: {data.get('error')}"

            return f"Message deleted successfully from channel {channel_id}."
        except Exception as e:
            logging.error(f"Error deleting Slack message: {str(e)}")
            return f"Error deleting message: {str(e)}"

    async def get_channels(self, types: str = "public_channel,private_channel", limit: int = 100):
        """
        Get list of channels in the workspace.

        Args:
            types (str): Channel types to include (public_channel, private_channel, mpim, im).
            limit (int): Max number of channels to retrieve.

        Returns:
            list: List of channel objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.list"
            params = {"types": types, "limit": limit}

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            if not data.get("ok"):
                return f"Error getting channels: {data.get('error')}"

            channels = data.get("channels", [])
            formatted_channels = [
                {
                    "id": ch.get("id"),
                    "name": ch.get("name"),
                    "is_private": ch.get("is_private", False),
                    "is_member": ch.get("is_member", False),
                    "num_members": ch.get("num_members", 0),
                    "topic": ch.get("topic", {}).get("value", ""),
                    "purpose": ch.get("purpose", {}).get("value", ""),
                }
                for ch in channels
            ]
            return formatted_channels
        except Exception as e:
            logging.error(f"Error getting Slack channels: {str(e)}")
            return f"Error getting channels: {str(e)}"

    async def get_channel_info(self, channel_id: str):
        """
        Get detailed information about a Slack channel.

        Args:
            channel_id (str): The ID of the channel.

        Returns:
            dict: Channel information or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.info"
            params = {"channel": channel_id}

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            if not data.get("ok"):
                return f"Error getting channel info: {data.get('error')}"

            ch = data.get("channel", {})
            return {
                "id": ch.get("id"),
                "name": ch.get("name"),
                "is_private": ch.get("is_private", False),
                "is_archived": ch.get("is_archived", False),
                "num_members": ch.get("num_members", 0),
                "topic": ch.get("topic", {}).get("value", ""),
                "purpose": ch.get("purpose", {}).get("value", ""),
                "creator": ch.get("creator"),
                "created": ch.get("created"),
            }
        except Exception as e:
            logging.error(f"Error getting Slack channel info: {str(e)}")
            return f"Error getting channel info: {str(e)}"

    async def get_users(self, limit: int = 100):
        """
        Get list of users in the workspace.

        Args:
            limit (int): Max number of users to retrieve.

        Returns:
            list: List of user objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/users.list"
            params = {"limit": limit}

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            if not data.get("ok"):
                return f"Error getting users: {data.get('error')}"

            members = data.get("members", [])
            formatted_users = [
                {
                    "id": user.get("id"),
                    "name": user.get("name"),
                    "real_name": user.get("real_name"),
                    "display_name": user.get("profile", {}).get("display_name", ""),
                    "email": user.get("profile", {}).get("email", ""),
                    "is_admin": user.get("is_admin", False),
                    "is_bot": user.get("is_bot", False),
                    "status_text": user.get("profile", {}).get("status_text", ""),
                }
                for user in members
                if not user.get("deleted")
            ]
            return formatted_users
        except Exception as e:
            logging.error(f"Error getting Slack users: {str(e)}")
            return f"Error getting users: {str(e)}"

    async def get_user_info(self, user_id: str):
        """
        Get detailed information about a Slack user.

        Args:
            user_id (str): The ID of the user.

        Returns:
            dict: User information or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/users.info"
            params = {"user": user_id}

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            if not data.get("ok"):
                return f"Error getting user info: {data.get('error')}"

            user = data.get("user", {})
            profile = user.get("profile", {})
            return {
                "id": user.get("id"),
                "name": user.get("name"),
                "real_name": user.get("real_name"),
                "display_name": profile.get("display_name", ""),
                "email": profile.get("email", ""),
                "phone": profile.get("phone", ""),
                "title": profile.get("title", ""),
                "status_text": profile.get("status_text", ""),
                "status_emoji": profile.get("status_emoji", ""),
                "is_admin": user.get("is_admin", False),
                "is_owner": user.get("is_owner", False),
                "is_bot": user.get("is_bot", False),
                "tz": user.get("tz"),
            }
        except Exception as e:
            logging.error(f"Error getting Slack user info: {str(e)}")
            return f"Error getting user info: {str(e)}"

    async def upload_file(
        self,
        channels: str,
        content: str = None,
        file_path: str = None,
        filename: str = None,
        title: str = None,
        initial_comment: str = None,
    ):
        """
        Upload a file to Slack channels.

        Args:
            channels (str): Comma-separated channel IDs to share the file.
            content (str, optional): File content as text.
            file_path (str, optional): Local file path to upload.
            filename (str, optional): Filename for the upload.
            title (str, optional): Title for the file.
            initial_comment (str, optional): Comment to add with the file.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/files.upload"

            data = {"channels": channels}
            if title:
                data["title"] = title
            if initial_comment:
                data["initial_comment"] = initial_comment
            if filename:
                data["filename"] = filename

            headers = {"Authorization": f"Bearer {self.access_token}"}

            if file_path:
                import os

                with open(file_path, "rb") as f:
                    files = {"file": (filename or os.path.basename(file_path), f)}
                    response = requests.post(url, headers=headers, data=data, files=files)
            elif content:
                data["content"] = content
                response = requests.post(url, headers=headers, data=data)
            else:
                return "Error: Either content or file_path must be provided."

            result = response.json()

            if not result.get("ok"):
                return f"Error uploading file: {result.get('error')}"

            file_info = result.get("file", {})
            return f"File uploaded successfully. File ID: {file_info.get('id')}, URL: {file_info.get('permalink')}"
        except Exception as e:
            logging.error(f"Error uploading Slack file: {str(e)}")
            return f"Error uploading file: {str(e)}"

    async def add_reaction(self, channel_id: str, ts: str, emoji: str):
        """
        Add an emoji reaction to a message.

        Args:
            channel_id (str): The channel ID containing the message.
            ts (str): The timestamp of the message.
            emoji (str): The emoji name (without colons).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/reactions.add"
            payload = {"channel": channel_id, "timestamp": ts, "name": emoji}

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error adding reaction: {data.get('error')}"

            return f"Reaction :{emoji}: added successfully."
        except Exception as e:
            logging.error(f"Error adding Slack reaction: {str(e)}")
            return f"Error adding reaction: {str(e)}"

    async def remove_reaction(self, channel_id: str, ts: str, emoji: str):
        """
        Remove an emoji reaction from a message.

        Args:
            channel_id (str): The channel ID containing the message.
            ts (str): The timestamp of the message.
            emoji (str): The emoji name (without colons).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/reactions.remove"
            payload = {"channel": channel_id, "timestamp": ts, "name": emoji}

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error removing reaction: {data.get('error')}"

            return f"Reaction :{emoji}: removed successfully."
        except Exception as e:
            logging.error(f"Error removing Slack reaction: {str(e)}")
            return f"Error removing reaction: {str(e)}"

    async def create_channel(self, name: str, is_private: bool = False):
        """
        Create a new Slack channel.

        Args:
            name (str): The name of the new channel.
            is_private (bool): Whether the channel should be private.

        Returns:
            str: Confirmation message with channel ID or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.create"
            payload = {"name": name, "is_private": is_private}

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error creating channel: {data.get('error')}"

            ch = data.get("channel", {})
            return f"Channel created successfully. Channel ID: {ch.get('id')}, Name: #{ch.get('name')}"
        except Exception as e:
            logging.error(f"Error creating Slack channel: {str(e)}")
            return f"Error creating channel: {str(e)}"

    async def invite_to_channel(self, channel_id: str, user_ids: str):
        """
        Invite users to a channel.

        Args:
            channel_id (str): The channel ID.
            user_ids (str): Comma-separated user IDs to invite.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.invite"
            payload = {"channel": channel_id, "users": user_ids}

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error inviting users: {data.get('error')}"

            return f"Users invited successfully to channel {channel_id}."
        except Exception as e:
            logging.error(f"Error inviting to Slack channel: {str(e)}")
            return f"Error inviting users: {str(e)}"

    async def search_messages(self, query: str, count: int = 20, sort: str = "timestamp"):
        """
        Search for messages in the workspace.

        Args:
            query (str): The search query.
            count (int): Number of results to return.
            sort (str): Sort order ('score' or 'timestamp').

        Returns:
            list: List of matching messages or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/search.messages"
            params = {"query": query, "count": count, "sort": sort}

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            if not data.get("ok"):
                return f"Error searching messages: {data.get('error')}"

            matches = data.get("messages", {}).get("matches", [])
            formatted_results = [
                {
                    "ts": msg.get("ts"),
                    "channel": msg.get("channel", {}).get("name"),
                    "channel_id": msg.get("channel", {}).get("id"),
                    "user": msg.get("user"),
                    "username": msg.get("username"),
                    "text": msg.get("text"),
                    "permalink": msg.get("permalink"),
                }
                for msg in matches
            ]
            return formatted_results
        except Exception as e:
            logging.error(f"Error searching Slack messages: {str(e)}")
            return f"Error searching messages: {str(e)}"

    async def get_thread_replies(self, channel_id: str, thread_ts: str, limit: int = 50):
        """
        Get replies in a message thread.

        Args:
            channel_id (str): The channel ID.
            thread_ts (str): The timestamp of the parent message.
            limit (int): Max number of replies to retrieve.

        Returns:
            list: List of reply messages or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.replies"
            params = {"channel": channel_id, "ts": thread_ts, "limit": limit}

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            if not data.get("ok"):
                return f"Error getting thread replies: {data.get('error')}"

            messages = data.get("messages", [])
            formatted_replies = [
                {
                    "ts": msg.get("ts"),
                    "user": msg.get("user"),
                    "text": msg.get("text"),
                    "reply_count": msg.get("reply_count", 0),
                }
                for msg in messages
            ]
            return formatted_replies
        except Exception as e:
            logging.error(f"Error getting Slack thread replies: {str(e)}")
            return f"Error getting thread replies: {str(e)}"

    async def post_thread_reply(self, channel_id: str, thread_ts: str, text: str):
        """
        Post a reply in a message thread.

        Args:
            channel_id (str): The channel ID.
            thread_ts (str): The timestamp of the parent message.
            text (str): The reply content.

        Returns:
            str: Confirmation message or error.
        """
        return await self.send_message(channel_id, text, thread_ts)

    async def set_channel_topic(self, channel_id: str, topic: str):
        """
        Set the topic for a channel.

        Args:
            channel_id (str): The channel ID.
            topic (str): The new topic.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.setTopic"
            payload = {"channel": channel_id, "topic": topic}

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error setting topic: {data.get('error')}"

            return f"Channel topic updated successfully."
        except Exception as e:
            logging.error(f"Error setting Slack channel topic: {str(e)}")
            return f"Error setting topic: {str(e)}"

    async def get_workspace_info(self):
        """
        Get information about the Slack workspace.

        Returns:
            dict: Workspace information or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/team.info"

            response = requests.get(url, headers=self._get_headers())
            data = response.json()

            if not data.get("ok"):
                return f"Error getting workspace info: {data.get('error')}"

            team = data.get("team", {})
            return {
                "id": team.get("id"),
                "name": team.get("name"),
                "domain": team.get("domain"),
                "email_domain": team.get("email_domain"),
                "icon": team.get("icon", {}).get("image_132"),
            }
        except Exception as e:
            logging.error(f"Error getting Slack workspace info: {str(e)}")
            return f"Error getting workspace info: {str(e)}"


def get_slack_user_ids(company_id: str = None) -> dict:
    """
    Get a mapping of Slack user ID -> email for users who have connected
    their Slack account via OAuth.

    Args:
        company_id (str, optional): The company ID to get Slack user mappings for.
            If None, returns mappings for ALL users across all companies.

    Returns:
        dict: A dictionary mapping Slack user ID to user email
    """
    from DB import get_session, UserOAuth, OAuthProvider, UserCompany, User
    from sqlalchemy.orm import joinedload

    session = get_session()
    try:
        provider = (
            session.query(OAuthProvider).filter(OAuthProvider.name == "slack").first()
        )
        if not provider:
            return {}

        if company_id:
            user_ids = (
                session.query(UserCompany.user_id)
                .filter(UserCompany.company_id == company_id)
                .all()
            )
            user_ids = [str(uid[0]) for uid in user_ids]

            if not user_ids:
                return {}

            oauth_records = (
                session.query(UserOAuth)
                .options(joinedload(UserOAuth.user))
                .filter(UserOAuth.user_id.in_(user_ids))
                .filter(UserOAuth.provider_id == provider.id)
                .filter(UserOAuth.provider_user_id.isnot(None))
                .all()
            )
        else:
            oauth_records = (
                session.query(UserOAuth)
                .options(joinedload(UserOAuth.user))
                .filter(UserOAuth.provider_id == provider.id)
                .filter(UserOAuth.provider_user_id.isnot(None))
                .all()
            )

        result = {}
        for oauth in oauth_records:
            if oauth.provider_user_id and oauth.user:
                result[oauth.provider_user_id] = oauth.user.email

        return result
    finally:
        session.close()
