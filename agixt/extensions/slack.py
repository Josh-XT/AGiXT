import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Optional, List, Dict, Any
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
- SLACK_SIGNING_SECRET: Slack app signing secret (for bot verification)
- SLACK_BOT_TOKEN: Bot User OAuth Token (for bot functionality)

Required scopes for Slack OAuth (User Token):
- identity.basic: Access user's basic info
- identity.email: Access user's email address  
- identity.avatar: Access user's avatar
- identity.team: Access user's team info

Required scopes for Slack Bot:
- app_mentions:read: Receive events when bot is mentioned
- channels:history: View messages in public channels
- channels:read: View basic channel info
- chat:write: Send messages
- files:read: View files shared in channels
- groups:history: View messages in private channels
- groups:read: View basic private channel info
- im:history: View direct messages
- im:read: View basic DM info
- im:write: Start direct messages with users
- mpim:history: View multi-person DM messages
- mpim:read: View multi-person DM info
- users:read: View people in workspace
- users:read.email: View email addresses of people
"""

# OAuth scopes for user authentication (Sign in with Slack)
SCOPES = ["identity.basic", "identity.email", "identity.avatar", "identity.team"]

# Bot scopes for workspace bot functionality
BOT_SCOPES = [
    "app_mentions:read",
    "channels:history",
    "channels:read",
    "chat:write",
    "files:read",
    "groups:history",
    "groups:read",
    "im:history",
    "im:read",
    "im:write",
    "mpim:history",
    "mpim:read",
    "users:read",
    "users:read.email",
]

AUTHORIZE = "https://slack.com/oauth/v2/authorize"
TOKEN_URL = "https://slack.com/api/oauth.v2.access"
USER_INFO_URL = "https://slack.com/api/users.identity"
PKCE_REQUIRED = False
SSO_ONLY = False  # Slack is a full extension with bot commands, not just SSO
LOGIN_CAPABLE = True  # Slack can also be used for login/registration


class SlackSSO:
    """Slack OAuth handler for user authentication."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
        team_id=None,
        team_name=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.team_id = team_id
        self.team_name = team_name
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

            if "access_token" not in data:
                raise Exception("No access_token in refresh response")

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
        except Exception as e:
            logging.error(f"Error processing Slack token response: {e}")
            raise HTTPException(
                status_code=401,
                detail=f"Failed to process Slack token refresh: {str(e)}",
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
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(USER_INFO_URL, headers=headers)

            data = response.json()

            if not data.get("ok"):
                raise Exception(f"Slack API error: {data.get('error')}")

            user = data.get("user", {})
            team = data.get("team", {})

            email = user.get("email")
            name = user.get("name", "")
            name_parts = name.split(" ", 1) if name else ["", ""]
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            slack_user_id = user.get("id")

            self.team_id = team.get("id")
            self.team_name = team.get("name")

            return {
                "email": email or f"{slack_user_id}@slack.user",
                "first_name": first_name,
                "last_name": last_name,
                "provider_user_id": slack_user_id,
                "team_id": self.team_id,
                "team_name": self.team_name,
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

        # Slack returns different structure for user vs bot tokens
        authed_user = data.get("authed_user", {})
        access_token = authed_user.get("access_token") or data.get("access_token")
        refresh_token = authed_user.get("refresh_token") or data.get("refresh_token")
        team = data.get("team", {})

        logging.info(f"Slack token obtained for team: {team.get('name')}")
        return SlackSSO(
            access_token=access_token,
            refresh_token=refresh_token,
            team_id=team.get("id"),
            team_name=team.get("name"),
        )
    except requests.exceptions.RequestException as e:
        logging.error(f"Error obtaining Slack access token: {e}")
        return None


def get_authorization_url(state=None):
    """Generate Slack authorization URL for user OAuth."""
    from urllib.parse import urlencode

    client_id = getenv("SLACK_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(SCOPES),
        "user_scope": ",".join(SCOPES),  # User-level scopes
    }

    if state:
        params["state"] = state

    query = urlencode(params)
    return f"{AUTHORIZE}?{query}"


def get_bot_install_url(state=None) -> str:
    """
    Generate Slack bot installation URL with bot scopes.
    This URL installs the bot to a workspace.
    """
    from urllib.parse import urlencode

    client_id = getenv("SLACK_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(BOT_SCOPES),  # Bot scopes
        "user_scope": ",".join(SCOPES),  # Also request user scopes
    }

    if state:
        params["state"] = state

    query = urlencode(params)
    return f"{AUTHORIZE}?{query}"


def get_slack_user_ids(company_id: str = None) -> Dict[str, str]:
    """
    Get mapping of Slack user IDs to email addresses for users who have
    connected their Slack accounts via OAuth.

    Args:
        company_id: Optional company ID to filter by. If None, returns all mappings.

    Returns:
        Dict mapping Slack user ID -> email address
    """
    from DB import get_session, UserOAuth, OAuthProvider, User, UserCompany

    session = get_session()
    try:
        # Find Slack OAuth provider
        provider = (
            session.query(OAuthProvider).filter(OAuthProvider.name == "slack").first()
        )

        if not provider:
            return {}

        # Query user OAuth connections for Slack
        query = session.query(UserOAuth, User).join(User, UserOAuth.user_id == User.id)
        query = query.filter(UserOAuth.provider_id == provider.id)

        # Filter by company if specified
        if company_id:
            query = query.join(UserCompany, User.id == UserCompany.user_id)
            query = query.filter(UserCompany.company_id == company_id)

        results = query.all()

        # Build mapping using provider_user_id (Slack user ID) -> email
        mapping = {}
        for user_oauth, user in results:
            if user_oauth.provider_user_id:
                mapping[user_oauth.provider_user_id] = user.email

        return mapping

    except Exception as e:
        logging.error(f"Error getting Slack user mappings: {e}")
        return {}
    finally:
        session.close()


class slack(Extensions):
    """
    The Slack extension for AGiXT enables you to interact with Slack workspaces
    using the user's authenticated account via OAuth2. It allows agents to read messages,
    send messages, manage channels, and get workspace information as the logged-in user.
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
                "Slack - Get Channels": self.get_channels,
                "Slack - Get Channel Info": self.get_channel_info,
                "Slack - Get Users": self.get_users,
                "Slack - Get User Info": self.get_user_info,
                "Slack - Search Messages": self.search_messages,
                "Slack - Upload File": self.upload_file,
                "Slack - Add Reaction": self.add_reaction,
                "Slack - Remove Reaction": self.remove_reaction,
                "Slack - Get Workspaces": self.get_workspaces,
                "Slack - Create Channel": self.create_channel,
                "Slack - Invite to Channel": self.invite_to_channel,
                "Slack - Set Channel Topic": self.set_channel_topic,
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
            if not refreshed_token:
                if not self.access_token:
                    raise Exception(
                        "Failed to refresh Slack token and no existing token available."
                    )
                else:
                    logging.warning(
                        "Failed to refresh Slack token, attempting with existing token."
                    )
            else:
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

    async def send_message(
        self,
        channel_id: str,
        text: str,
        thread_ts: str = None,
        blocks: List[Dict] = None,
    ):
        """
        Send a message to a Slack channel.

        Args:
            channel_id (str): The ID of the Slack channel.
            text (str): The message text.
            thread_ts (str): Optional thread timestamp to reply in a thread.
            blocks (List[Dict]): Optional Block Kit blocks for rich formatting.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/chat.postMessage"
            payload = {"channel": channel_id, "text": text}

            if thread_ts:
                payload["thread_ts"] = thread_ts
            if blocks:
                payload["blocks"] = blocks

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error sending message: {data.get('error')}"

            ts = data.get("ts", "Unknown")
            return f"Message sent successfully to channel {channel_id}. Timestamp: {ts}"
        except Exception as e:
            logging.error(f"Error sending Slack message: {str(e)}")
            return f"Error sending message: {str(e)}"

    async def get_messages(
        self,
        channel_id: str,
        limit: int = 100,
        oldest: str = None,
        latest: str = None,
    ):
        """
        Get messages from a Slack channel.

        Args:
            channel_id (str): The ID of the Slack channel.
            limit (int): Number of messages to retrieve (max 1000).
            oldest (str): Only messages after this Unix timestamp.
            latest (str): Only messages before this Unix timestamp.

        Returns:
            list: List of messages or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.history"
            params = {"channel": channel_id, "limit": min(limit, 1000)}

            if oldest:
                params["oldest"] = oldest
            if latest:
                params["latest"] = latest

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
            )
            data = response.json()

            if not data.get("ok"):
                return f"Error getting messages: {data.get('error')}"

            messages = data.get("messages", [])
            formatted = []
            for msg in messages:
                formatted.append(
                    {
                        "user": msg.get("user"),
                        "text": msg.get("text"),
                        "ts": msg.get("ts"),
                        "thread_ts": msg.get("thread_ts"),
                        "type": msg.get("type"),
                    }
                )
            return formatted
        except Exception as e:
            logging.error(f"Error getting Slack messages: {str(e)}")
            return f"Error getting messages: {str(e)}"

    async def get_channels(self, types: str = "public_channel,private_channel"):
        """
        Get list of channels in the workspace.

        Args:
            types (str): Comma-separated channel types (public_channel, private_channel, mpim, im).

        Returns:
            list: List of channels or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.list"
            params = {"types": types, "limit": 1000}

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
            )
            data = response.json()

            if not data.get("ok"):
                return f"Error getting channels: {data.get('error')}"

            channels = data.get("channels", [])
            formatted = []
            for ch in channels:
                formatted.append(
                    {
                        "id": ch.get("id"),
                        "name": ch.get("name"),
                        "is_private": ch.get("is_private"),
                        "is_archived": ch.get("is_archived"),
                        "num_members": ch.get("num_members"),
                        "topic": ch.get("topic", {}).get("value"),
                        "purpose": ch.get("purpose", {}).get("value"),
                    }
                )
            return formatted
        except Exception as e:
            logging.error(f"Error getting Slack channels: {str(e)}")
            return f"Error getting channels: {str(e)}"

    async def get_channel_info(self, channel_id: str):
        """
        Get detailed information about a channel.

        Args:
            channel_id (str): The ID of the Slack channel.

        Returns:
            dict: Channel information or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.info"
            params = {"channel": channel_id}

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
            )
            data = response.json()

            if not data.get("ok"):
                return f"Error getting channel info: {data.get('error')}"

            ch = data.get("channel", {})
            return {
                "id": ch.get("id"),
                "name": ch.get("name"),
                "is_private": ch.get("is_private"),
                "is_archived": ch.get("is_archived"),
                "is_member": ch.get("is_member"),
                "topic": ch.get("topic", {}).get("value"),
                "purpose": ch.get("purpose", {}).get("value"),
                "created": ch.get("created"),
                "creator": ch.get("creator"),
                "num_members": ch.get("num_members"),
            }
        except Exception as e:
            logging.error(f"Error getting Slack channel info: {str(e)}")
            return f"Error getting channel info: {str(e)}"

    async def get_users(self, limit: int = 200):
        """
        Get list of users in the workspace.

        Args:
            limit (int): Number of users to retrieve (max 1000).

        Returns:
            list: List of users or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/users.list"
            params = {"limit": min(limit, 1000)}

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
            )
            data = response.json()

            if not data.get("ok"):
                return f"Error getting users: {data.get('error')}"

            users = data.get("members", [])
            formatted = []
            for user in users:
                if not user.get("is_bot") and not user.get("deleted"):
                    profile = user.get("profile", {})
                    formatted.append(
                        {
                            "id": user.get("id"),
                            "name": user.get("name"),
                            "real_name": user.get("real_name"),
                            "email": profile.get("email"),
                            "is_admin": user.get("is_admin"),
                            "is_owner": user.get("is_owner"),
                            "timezone": user.get("tz"),
                        }
                    )
            return formatted
        except Exception as e:
            logging.error(f"Error getting Slack users: {str(e)}")
            return f"Error getting users: {str(e)}"

    async def get_user_info(self, user_id: str):
        """
        Get detailed information about a user.

        Args:
            user_id (str): The ID of the Slack user.

        Returns:
            dict: User information or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/users.info"
            params = {"user": user_id}

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
            )
            data = response.json()

            if not data.get("ok"):
                return f"Error getting user info: {data.get('error')}"

            user = data.get("user", {})
            profile = user.get("profile", {})
            return {
                "id": user.get("id"),
                "name": user.get("name"),
                "real_name": user.get("real_name"),
                "email": profile.get("email"),
                "display_name": profile.get("display_name"),
                "title": profile.get("title"),
                "is_admin": user.get("is_admin"),
                "is_owner": user.get("is_owner"),
                "is_bot": user.get("is_bot"),
                "timezone": user.get("tz"),
                "status_text": profile.get("status_text"),
                "status_emoji": profile.get("status_emoji"),
            }
        except Exception as e:
            logging.error(f"Error getting Slack user info: {str(e)}")
            return f"Error getting user info: {str(e)}"

    async def search_messages(self, query: str, count: int = 20, sort: str = "score"):
        """
        Search for messages in the workspace.

        Args:
            query (str): Search query.
            count (int): Number of results to return (max 100).
            sort (str): Sort order - 'score' (relevance) or 'timestamp'.

        Returns:
            list: List of matching messages or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/search.messages"
            params = {
                "query": query,
                "count": min(count, 100),
                "sort": sort,
            }

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
            )
            data = response.json()

            if not data.get("ok"):
                return f"Error searching messages: {data.get('error')}"

            messages = data.get("messages", {}).get("matches", [])
            formatted = []
            for msg in messages:
                formatted.append(
                    {
                        "channel": msg.get("channel", {}).get("name"),
                        "channel_id": msg.get("channel", {}).get("id"),
                        "user": msg.get("username"),
                        "text": msg.get("text"),
                        "ts": msg.get("ts"),
                        "permalink": msg.get("permalink"),
                    }
                )
            return formatted
        except Exception as e:
            logging.error(f"Error searching Slack messages: {str(e)}")
            return f"Error searching messages: {str(e)}"

    async def upload_file(
        self,
        channels: str,
        content: str = None,
        file_path: str = None,
        filename: str = "file.txt",
        title: str = None,
        initial_comment: str = None,
    ):
        """
        Upload a file to Slack channels.

        Args:
            channels (str): Comma-separated list of channel IDs.
            content (str): File content as text (use this or file_path).
            file_path (str): Path to file on disk (use this or content).
            filename (str): Name of the file.
            title (str): Title of the file.
            initial_comment (str): Message to include with the file.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/files.upload"

            data = {
                "channels": channels,
                "filename": filename,
            }
            if title:
                data["title"] = title
            if initial_comment:
                data["initial_comment"] = initial_comment

            files = None
            if content:
                data["content"] = content
            elif file_path:
                files = {"file": open(file_path, "rb")}

            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.post(url, headers=headers, data=data, files=files)
            result = response.json()

            if not result.get("ok"):
                return f"Error uploading file: {result.get('error')}"

            file_id = result.get("file", {}).get("id")
            return f"File uploaded successfully. File ID: {file_id}"
        except Exception as e:
            logging.error(f"Error uploading file to Slack: {str(e)}")
            return f"Error uploading file: {str(e)}"

    async def add_reaction(self, channel_id: str, timestamp: str, emoji: str):
        """
        Add a reaction to a message.

        Args:
            channel_id (str): The ID of the channel containing the message.
            timestamp (str): The timestamp of the message.
            emoji (str): The emoji name (without colons).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/reactions.add"
            payload = {
                "channel": channel_id,
                "timestamp": timestamp,
                "name": emoji,
            }

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error adding reaction: {data.get('error')}"

            return f"Reaction :{emoji}: added successfully."
        except Exception as e:
            logging.error(f"Error adding Slack reaction: {str(e)}")
            return f"Error adding reaction: {str(e)}"

    async def remove_reaction(self, channel_id: str, timestamp: str, emoji: str):
        """
        Remove a reaction from a message.

        Args:
            channel_id (str): The ID of the channel containing the message.
            timestamp (str): The timestamp of the message.
            emoji (str): The emoji name (without colons).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/reactions.remove"
            payload = {
                "channel": channel_id,
                "timestamp": timestamp,
                "name": emoji,
            }

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error removing reaction: {data.get('error')}"

            return f"Reaction :{emoji}: removed successfully."
        except Exception as e:
            logging.error(f"Error removing Slack reaction: {str(e)}")
            return f"Error removing reaction: {str(e)}"

    async def get_workspaces(self):
        """
        Get information about the connected workspace.

        Returns:
            dict: Workspace information or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/team.info"

            response = requests.get(
                url, headers={"Authorization": f"Bearer {self.access_token}"}
            )
            data = response.json()

            if not data.get("ok"):
                return f"Error getting workspace info: {data.get('error')}"

            team = data.get("team", {})
            return {
                "id": team.get("id"),
                "name": team.get("name"),
                "domain": team.get("domain"),
                "email_domain": team.get("email_domain"),
            }
        except Exception as e:
            logging.error(f"Error getting Slack workspace info: {str(e)}")
            return f"Error getting workspace info: {str(e)}"

    async def create_channel(self, name: str, is_private: bool = False):
        """
        Create a new channel.

        Args:
            name (str): Name of the channel (lowercase, no spaces).
            is_private (bool): Whether to create a private channel.

        Returns:
            str: Channel information or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/conversations.create"
            payload = {"name": name, "is_private": is_private}

            response = requests.post(url, headers=self._get_headers(), json=payload)
            data = response.json()

            if not data.get("ok"):
                return f"Error creating channel: {data.get('error')}"

            channel = data.get("channel", {})
            return f"Channel #{channel.get('name')} created. ID: {channel.get('id')}"
        except Exception as e:
            logging.error(f"Error creating Slack channel: {str(e)}")
            return f"Error creating channel: {str(e)}"

    async def invite_to_channel(self, channel_id: str, user_ids: str):
        """
        Invite users to a channel.

        Args:
            channel_id (str): The ID of the channel.
            user_ids (str): Comma-separated list of user IDs to invite.

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
            logging.error(f"Error inviting users to Slack channel: {str(e)}")
            return f"Error inviting users: {str(e)}"

    async def set_channel_topic(self, channel_id: str, topic: str):
        """
        Set the topic of a channel.

        Args:
            channel_id (str): The ID of the channel.
            topic (str): The new topic text.

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

            return f"Topic set successfully for channel {channel_id}."
        except Exception as e:
            logging.error(f"Error setting Slack channel topic: {str(e)}")
            return f"Error setting topic: {str(e)}"
