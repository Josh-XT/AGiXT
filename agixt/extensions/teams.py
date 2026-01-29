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

- MICROSOFT_CLIENT_ID: Microsoft Azure AD OAuth client ID
- MICROSOFT_CLIENT_SECRET: Microsoft Azure AD OAuth client secret
- MICROSOFT_TENANT_ID: Azure AD tenant ID (or 'common' for multi-tenant)

Required scopes for Microsoft Teams OAuth:

- User.Read: Read user profile
- Chat.ReadWrite: Read and send chat messages
- ChannelMessage.Read.All: Read channel messages
- ChannelMessage.Send: Send channel messages
- Team.ReadBasic.All: Read teams
- Channel.ReadBasic.All: Read channels
- Files.ReadWrite.All: Read and write files
- offline_access: Get refresh tokens

Note: For bot functionality, you need to register a Bot Framework bot in Azure.
"""

SCOPES = [
    "User.Read",
    "Chat.ReadWrite",
    "ChannelMessage.Read.All",
    "ChannelMessage.Send",
    "Team.ReadBasic.All",
    "Channel.ReadBasic.All",
    "Files.ReadWrite.All",
    "offline_access",
]
AUTHORIZE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
USER_INFO_URL = "https://graph.microsoft.com/v1.0/me"
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = True


class TeamsSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.tenant_id = getenv("MICROSOFT_TENANT_ID", "common")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refreshes the Microsoft access token using the refresh token."""
        if not self.refresh_token:
            raise HTTPException(
                status_code=400, detail="No refresh token available for Microsoft Teams."
            )

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "scope": " ".join(SCOPES),
        }

        token_url = TOKEN_URL.format(tenant=self.tenant_id)

        try:
            response = requests.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()

            if "access_token" not in data:
                raise Exception("No access_token in refresh response")

            self.access_token = data.get("access_token")
            if "refresh_token" in data:
                self.refresh_token = data.get("refresh_token")

            logging.info("Successfully refreshed Microsoft Teams token.")
            return data
        except requests.exceptions.RequestException as e:
            logging.error(f"Error refreshing Microsoft Teams token: {e}")
            raise HTTPException(
                status_code=401, detail=f"Failed to refresh Microsoft Teams token: {str(e)}"
            )

    def get_user_info(self):
        """Gets user information from Microsoft Graph API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = requests.get(USER_INFO_URL, headers=headers)

            if response.status_code == 401:
                logging.info("Microsoft Teams token likely expired, attempting refresh.")
                self.access_token = self.get_new_token().get("access_token")
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(USER_INFO_URL, headers=headers)

            response.raise_for_status()
            data = response.json()

            return {
                "email": data.get("mail") or data.get("userPrincipalName", ""),
                "first_name": data.get("givenName", ""),
                "last_name": data.get("surname", ""),
                "provider_user_id": data.get("id"),
            }
        except requests.exceptions.RequestException as e:
            logging.error(f"Error getting user info from Microsoft Teams: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Microsoft Teams: {str(e)}",
            )


def sso(code, redirect_uri=None) -> TeamsSSO:
    """Handles the OAuth2 authorization code flow for Microsoft Teams."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("MICROSOFT_CLIENT_ID")
    client_secret = getenv("MICROSOFT_CLIENT_SECRET")
    tenant_id = getenv("MICROSOFT_TENANT_ID", "common")

    if not client_id or not client_secret:
        logging.error("Microsoft Client ID or Secret not configured.")
        return None

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": " ".join(SCOPES),
    }

    token_url = TOKEN_URL.format(tenant=tenant_id)

    try:
        response = requests.post(token_url, data=payload)
        response.raise_for_status()
        data = response.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        logging.info("Microsoft Teams token obtained successfully.")
        return TeamsSSO(access_token=access_token, refresh_token=refresh_token)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error obtaining Microsoft Teams access token: {e}")
        return None


def get_authorization_url(state=None):
    """Generate Microsoft Teams authorization URL"""
    from urllib.parse import urlencode

    client_id = getenv("MICROSOFT_CLIENT_ID")
    tenant_id = getenv("MICROSOFT_TENANT_ID", "common")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "response_mode": "query",
    }

    if state:
        params["state"] = state

    query = urlencode(params)
    authorize_url = AUTHORIZE.format(tenant=tenant_id)
    return f"{authorize_url}?{query}"


class teams(Extensions):
    """
    The Microsoft Teams extension for AGiXT enables you to interact with Microsoft Teams
    using the user's authenticated account via OAuth2. It allows agents to read and send
    messages, manage teams and channels, and interact with files.
    Requires appropriate Microsoft Graph API permissions.
    """

    CATEGORY = "Social & Communication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("TEAMS_ACCESS_TOKEN", None)
        microsoft_client_id = getenv("MICROSOFT_CLIENT_ID")
        microsoft_client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.base_uri = "https://graph.microsoft.com/v1.0"
        self.auth = None
        self.commands = {}

        if microsoft_client_id and microsoft_client_secret:
            self.commands = {
                "Teams - Send Channel Message": self.send_channel_message,
                "Teams - Send Chat Message": self.send_chat_message,
                "Teams - Get Channel Messages": self.get_channel_messages,
                "Teams - Get Chat Messages": self.get_chat_messages,
                "Teams - Get Teams": self.get_teams,
                "Teams - Get Team Channels": self.get_team_channels,
                "Teams - Get Team Members": self.get_team_members,
                "Teams - Get Chats": self.get_chats,
                "Teams - Create Team": self.create_team,
                "Teams - Create Channel": self.create_channel,
                "Teams - Reply to Message": self.reply_to_message,
                "Teams - Get User Presence": self.get_user_presence,
                "Teams - Search Messages": self.search_messages,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Teams extension auth: {str(e)}")

    def _get_headers(self):
        """Returns the authorization headers for Microsoft Graph API requests."""
        if not self.access_token:
            raise Exception("Microsoft Teams Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def verify_user(self):
        """Verifies the access token and refreshes it if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="teams")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("teams_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
            logging.info("Microsoft Teams token verified/refreshed successfully.")
        except Exception as e:
            logging.error(f"Error verifying/refreshing Microsoft Teams token: {str(e)}")
            raise Exception(f"Microsoft Teams authentication error: {str(e)}")

    async def send_channel_message(self, team_id: str, channel_id: str, content: str):
        """
        Send a message to a Teams channel.

        Args:
            team_id (str): The ID of the team.
            channel_id (str): The ID of the channel.
            content (str): The message content.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/teams/{team_id}/channels/{channel_id}/messages"
            payload = {
                "body": {
                    "contentType": "html",
                    "content": content,
                }
            }

            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()

            return f"Message sent successfully. Message ID: {data.get('id')}"
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error sending Teams channel message: {str(e)}")
            return f"Error sending message: {str(e)}"
        except Exception as e:
            logging.error(f"Error sending Teams channel message: {str(e)}")
            return f"Error sending message: {str(e)}"

    async def send_chat_message(self, chat_id: str, content: str):
        """
        Send a message to a Teams chat.

        Args:
            chat_id (str): The ID of the chat.
            content (str): The message content.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/chats/{chat_id}/messages"
            payload = {
                "body": {
                    "contentType": "html",
                    "content": content,
                }
            }

            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()

            return f"Message sent successfully. Message ID: {data.get('id')}"
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error sending Teams chat message: {str(e)}")
            return f"Error sending message: {str(e)}"
        except Exception as e:
            logging.error(f"Error sending Teams chat message: {str(e)}")
            return f"Error sending message: {str(e)}"

    async def get_channel_messages(
        self, team_id: str, channel_id: str, limit: int = 50
    ):
        """
        Get messages from a Teams channel.

        Args:
            team_id (str): The ID of the team.
            channel_id (str): The ID of the channel.
            limit (int): Max number of messages to retrieve.

        Returns:
            list: List of message objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/teams/{team_id}/channels/{channel_id}/messages"
            params = {"$top": min(limit, 50)}

            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            data = response.json()

            messages = data.get("value", [])
            formatted_messages = [
                {
                    "id": msg.get("id"),
                    "from": msg.get("from", {})
                    .get("user", {})
                    .get("displayName", "Unknown"),
                    "content": msg.get("body", {}).get("content", ""),
                    "created": msg.get("createdDateTime"),
                    "importance": msg.get("importance"),
                    "reply_count": len(msg.get("replies", [])),
                }
                for msg in messages
            ]
            return formatted_messages
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error getting Teams channel messages: {str(e)}")
            return f"Error getting messages: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting Teams channel messages: {str(e)}")
            return f"Error getting messages: {str(e)}"

    async def get_chat_messages(self, chat_id: str, limit: int = 50):
        """
        Get messages from a Teams chat.

        Args:
            chat_id (str): The ID of the chat.
            limit (int): Max number of messages to retrieve.

        Returns:
            list: List of message objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/chats/{chat_id}/messages"
            params = {"$top": min(limit, 50)}

            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            data = response.json()

            messages = data.get("value", [])
            formatted_messages = [
                {
                    "id": msg.get("id"),
                    "from": msg.get("from", {})
                    .get("user", {})
                    .get("displayName", "Unknown"),
                    "content": msg.get("body", {}).get("content", ""),
                    "created": msg.get("createdDateTime"),
                }
                for msg in messages
            ]
            return formatted_messages
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error getting Teams chat messages: {str(e)}")
            return f"Error getting messages: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting Teams chat messages: {str(e)}")
            return f"Error getting messages: {str(e)}"

    async def get_teams(self):
        """
        Get list of teams the user is a member of.

        Returns:
            list: List of team objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/me/joinedTeams"

            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            teams_list = data.get("value", [])
            formatted_teams = [
                {
                    "id": team.get("id"),
                    "name": team.get("displayName"),
                    "description": team.get("description"),
                    "visibility": team.get("visibility"),
                }
                for team in teams_list
            ]
            return formatted_teams
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error getting Teams: {str(e)}")
            return f"Error getting teams: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting Teams: {str(e)}")
            return f"Error getting teams: {str(e)}"

    async def get_team_channels(self, team_id: str):
        """
        Get channels in a team.

        Args:
            team_id (str): The ID of the team.

        Returns:
            list: List of channel objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/teams/{team_id}/channels"

            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            channels = data.get("value", [])
            formatted_channels = [
                {
                    "id": ch.get("id"),
                    "name": ch.get("displayName"),
                    "description": ch.get("description"),
                    "membership_type": ch.get("membershipType"),
                }
                for ch in channels
            ]
            return formatted_channels
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error getting team channels: {str(e)}")
            return f"Error getting channels: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting team channels: {str(e)}")
            return f"Error getting channels: {str(e)}"

    async def get_team_members(self, team_id: str):
        """
        Get members of a team.

        Args:
            team_id (str): The ID of the team.

        Returns:
            list: List of member objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/teams/{team_id}/members"

            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            members = data.get("value", [])
            formatted_members = [
                {
                    "id": member.get("id"),
                    "user_id": member.get("userId"),
                    "display_name": member.get("displayName"),
                    "email": member.get("email"),
                    "roles": member.get("roles", []),
                }
                for member in members
            ]
            return formatted_members
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error getting team members: {str(e)}")
            return f"Error getting members: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting team members: {str(e)}")
            return f"Error getting members: {str(e)}"

    async def get_chats(self):
        """
        Get list of chats the user is part of.

        Returns:
            list: List of chat objects or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/me/chats"

            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            chats = data.get("value", [])
            formatted_chats = [
                {
                    "id": chat.get("id"),
                    "topic": chat.get("topic"),
                    "chat_type": chat.get("chatType"),
                    "created": chat.get("createdDateTime"),
                    "last_updated": chat.get("lastUpdatedDateTime"),
                }
                for chat in chats
            ]
            return formatted_chats
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error getting chats: {str(e)}")
            return f"Error getting chats: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting chats: {str(e)}")
            return f"Error getting chats: {str(e)}"

    async def create_team(self, display_name: str, description: str = ""):
        """
        Create a new team.

        Args:
            display_name (str): The name of the team.
            description (str): Description of the team.

        Returns:
            str: Confirmation message with team ID or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/teams"
            payload = {
                "template@odata.bind": "https://graph.microsoft.com/v1.0/teamsTemplates('standard')",
                "displayName": display_name,
                "description": description,
            }

            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()

            # Teams creation is async, check Location header
            location = response.headers.get("Location", "")
            return f"Team creation initiated. Check status at: {location}"
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error creating team: {str(e)}")
            return f"Error creating team: {str(e)}"
        except Exception as e:
            logging.error(f"Error creating team: {str(e)}")
            return f"Error creating team: {str(e)}"

    async def create_channel(
        self,
        team_id: str,
        display_name: str,
        description: str = "",
        membership_type: str = "standard",
    ):
        """
        Create a new channel in a team.

        Args:
            team_id (str): The ID of the team.
            display_name (str): The name of the channel.
            description (str): Description of the channel.
            membership_type (str): 'standard' or 'private'.

        Returns:
            str: Confirmation message with channel ID or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/teams/{team_id}/channels"
            payload = {
                "displayName": display_name,
                "description": description,
                "membershipType": membership_type,
            }

            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()

            return f"Channel created successfully. Channel ID: {data.get('id')}"
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error creating channel: {str(e)}")
            return f"Error creating channel: {str(e)}"
        except Exception as e:
            logging.error(f"Error creating channel: {str(e)}")
            return f"Error creating channel: {str(e)}"

    async def reply_to_message(
        self, team_id: str, channel_id: str, message_id: str, content: str
    ):
        """
        Reply to a message in a channel.

        Args:
            team_id (str): The ID of the team.
            channel_id (str): The ID of the channel.
            message_id (str): The ID of the message to reply to.
            content (str): The reply content.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies"
            payload = {
                "body": {
                    "contentType": "html",
                    "content": content,
                }
            }

            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()

            return f"Reply sent successfully. Reply ID: {data.get('id')}"
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error replying to message: {str(e)}")
            return f"Error replying: {str(e)}"
        except Exception as e:
            logging.error(f"Error replying to message: {str(e)}")
            return f"Error replying: {str(e)}"

    async def get_user_presence(self, user_id: str = None):
        """
        Get user presence status.

        Args:
            user_id (str, optional): User ID. If None, gets current user's presence.

        Returns:
            dict: Presence information or error string.
        """
        try:
            self.verify_user()
            if user_id:
                url = f"{self.base_uri}/users/{user_id}/presence"
            else:
                url = f"{self.base_uri}/me/presence"

            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            return {
                "availability": data.get("availability"),
                "activity": data.get("activity"),
            }
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error getting user presence: {str(e)}")
            return f"Error getting presence: {str(e)}"
        except Exception as e:
            logging.error(f"Error getting user presence: {str(e)}")
            return f"Error getting presence: {str(e)}"

    async def search_messages(self, query: str, limit: int = 25):
        """
        Search for messages across Teams.

        Args:
            query (str): The search query.
            limit (int): Max number of results.

        Returns:
            list: List of matching messages or error string.
        """
        try:
            self.verify_user()
            url = f"{self.base_uri}/search/query"
            payload = {
                "requests": [
                    {
                        "entityTypes": ["chatMessage"],
                        "query": {"queryString": query},
                        "from": 0,
                        "size": min(limit, 25),
                    }
                ]
            }

            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()

            results = []
            for result_set in data.get("value", []):
                for hit in result_set.get("hitsContainers", []):
                    for item in hit.get("hits", []):
                        resource = item.get("resource", {})
                        results.append(
                            {
                                "summary": item.get("summary"),
                                "from": resource.get("from", {})
                                .get("emailAddress", {})
                                .get("name"),
                                "created": resource.get("createdDateTime"),
                            }
                        )

            return results
        except requests.exceptions.HTTPError as e:
            logging.error(f"Error searching messages: {str(e)}")
            return f"Error searching: {str(e)}"
        except Exception as e:
            logging.error(f"Error searching messages: {str(e)}")
            return f"Error searching: {str(e)}"


def get_teams_user_ids(company_id: str = None) -> dict:
    """
    Get a mapping of Microsoft Teams user ID -> email for users who have connected
    their Teams account via OAuth.

    Args:
        company_id (str, optional): The company ID to get Teams user mappings for.
            If None, returns mappings for ALL users across all companies.

    Returns:
        dict: A dictionary mapping Teams user ID to user email
    """
    from DB import get_session, UserOAuth, OAuthProvider, UserCompany, User
    from sqlalchemy.orm import joinedload

    session = get_session()
    try:
        provider = (
            session.query(OAuthProvider).filter(OAuthProvider.name == "teams").first()
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
