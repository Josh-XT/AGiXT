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

- TEAMS_CLIENT_ID: Microsoft Azure AD OAuth client ID (App Registration)
- TEAMS_CLIENT_SECRET: Microsoft Azure AD OAuth client secret
- TEAMS_BOT_ID: Microsoft Bot Framework Bot ID (optional, for bot functionality)
- TEAMS_BOT_SECRET: Microsoft Bot Framework Bot Secret (optional)

Required scopes for Microsoft Teams OAuth (User Token):
- offline_access: Maintain access to data you have given it access to
- https://graph.microsoft.com/User.Read: Read user profile
- https://graph.microsoft.com/Team.ReadBasic.All: Read the names and descriptions of teams
- https://graph.microsoft.com/Channel.ReadBasic.All: Read channel names and descriptions
- https://graph.microsoft.com/Chat.Read: Read user chat messages
- https://graph.microsoft.com/Chat.ReadWrite: Read and write user chat messages
- https://graph.microsoft.com/ChatMessage.Read: Read user chat messages
- https://graph.microsoft.com/ChannelMessage.Read.All: Read channel messages (requires admin consent)
- https://graph.microsoft.com/ChannelMessage.Send: Send channel messages

Required scopes for Bot (Application permissions):
- https://graph.microsoft.com/Team.ReadBasic.All
- https://graph.microsoft.com/Channel.ReadBasic.All
- https://graph.microsoft.com/ChannelMessage.Read.All
- https://graph.microsoft.com/ChannelMessage.Send
"""

# OAuth scopes for user authentication (Sign in with Microsoft Teams)
SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Team.ReadBasic.All",
    "https://graph.microsoft.com/Channel.ReadBasic.All",
    "https://graph.microsoft.com/Chat.Read",
    "https://graph.microsoft.com/Chat.ReadWrite",
    "https://graph.microsoft.com/ChatMessage.Read",
    "https://graph.microsoft.com/ChannelMessage.Read.All",
    "https://graph.microsoft.com/ChannelMessage.Send",
]

# Bot scopes for Teams bot functionality (Application permissions)
BOT_SCOPES = [
    "https://graph.microsoft.com/.default",
]

# OAuth URLs for Microsoft Identity Platform
AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_API_BETA = "https://graph.microsoft.com/beta"

# OAuth configuration flags (same as Discord extension pattern)
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = True


class TeamsSSO:
    """
    Microsoft Teams Single Sign-On handler.
    
    Handles OAuth token management and user info retrieval for Microsoft Teams.
    Follows the same pattern as DiscordSSO and SlackSSO.
    """

    def __init__(
        self,
        access_token: str = None,
        refresh_token: str = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("TEAMS_CLIENT_ID") or getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = getenv("TEAMS_CLIENT_SECRET") or getenv("MICROSOFT_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self) -> dict:
        """
        Refresh the access token using the refresh token.
        
        Returns:
            dict: Token response containing new access_token and refresh_token
        """
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(SCOPES),
            },
        )

        if response.status_code != 200:
            logging.error(f"Teams token refresh failed: {response.text}")
            raise HTTPException(
                status_code=401,
                detail=f"Microsoft Teams token refresh failed: {response.text}",
            )

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            self.refresh_token = token_data["refresh_token"]

        return token_data

    def get_user_info(self) -> dict:
        """
        Get user information from Microsoft Graph API.
        
        Returns:
            dict: User info with email, first_name, last_name, id
        """
        if not self.access_token:
            logging.error("No access token available for Teams user info")
            return {}

        uri = f"{GRAPH_API_BASE}/me"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = requests.get(uri, headers=headers)

        if response.status_code == 401:
            # Token expired, try to refresh
            try:
                self.get_new_token()
                response = requests.get(uri, headers=headers)
            except Exception as e:
                logging.error(f"Failed to refresh token for Teams user info: {e}")
                return {}

        if response.status_code != 200:
            logging.error(f"Failed to get Teams user info: {response.text}")
            return {}

        try:
            data = response.json()
            return {
                "email": data.get("mail") or data.get("userPrincipalName", ""),
                "first_name": data.get("givenName", "") or "",
                "last_name": data.get("surname", "") or "",
                "id": data.get("id", ""),
                "display_name": data.get("displayName", ""),
            }
        except Exception as e:
            logging.error(f"Error parsing Teams user info: {e}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Microsoft Teams",
            )


def sso(code: str, redirect_uri: str = None) -> TeamsSSO:
    """
    Exchange authorization code for access tokens.
    
    This function is called by the OAuth callback endpoint to exchange
    the authorization code for access and refresh tokens.
    
    Args:
        code: The authorization code from the OAuth callback
        redirect_uri: The redirect URI used in the authorization request
        
    Returns:
        TeamsSSO: An initialized TeamsSSO instance with tokens
    """
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    # Clean up the code (handle URL encoding)
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%26", "&")
    )

    client_id = getenv("TEAMS_CLIENT_ID") or getenv("MICROSOFT_CLIENT_ID")
    client_secret = getenv("TEAMS_CLIENT_SECRET") or getenv("MICROSOFT_CLIENT_SECRET")

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
        },
    )

    if response.status_code != 200:
        logging.error(f"Error getting Teams access token: {response.text}")
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token", "Not provided")

    return TeamsSSO(access_token=access_token, refresh_token=refresh_token)


def get_authorization_url(redirect_uri: str = None, state: str = None) -> str:
    """
    Generate the Microsoft Teams OAuth authorization URL.
    
    Args:
        redirect_uri: The callback URI for the OAuth flow
        state: Optional state parameter for CSRF protection
        
    Returns:
        str: The authorization URL to redirect users to
    """
    client_id = getenv("TEAMS_CLIENT_ID") or getenv("MICROSOFT_CLIENT_ID")
    if not redirect_uri:
        redirect_uri = f"{getenv('APP_URI')}/user/oauth/teams"

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "response_mode": "query",
    }
    
    if state:
        params["state"] = state

    query_string = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return f"{AUTHORIZE}?{query_string}"


def get_bot_install_url(client_id: str = None, token: str = None) -> str:
    """
    Generate the Microsoft Teams bot installation URL.
    
    For Teams, bot installation is done through the Teams admin center or
    by uploading a Teams app package. This returns a URL to the admin center.
    
    Args:
        client_id: The Azure AD application client ID (optional)
        token: Installation token for tracking (optional)
        
    Returns:
        str: URL to the Teams admin center for app management
    """
    if not client_id:
        client_id = getenv("TEAMS_CLIENT_ID") or getenv("MICROSOFT_CLIENT_ID")
    
    # Teams apps are managed through the Teams admin center
    # This URL points to the app management section
    base_url = "https://admin.teams.microsoft.com/policies/manage-apps"
    
    if token:
        return f"{base_url}?install_token={token}"
    return base_url


def get_teams_user_ids(company_id: str = None) -> Dict[str, str]:
    """
    Get mapping of Teams user IDs to email addresses for a company.
    
    This is used by the TeamsBotManager to map incoming Teams messages
    to AGiXT users for impersonation.
    
    Args:
        company_id: Optional company ID to filter users
        
    Returns:
        dict: Mapping of Teams user ID to email address
    """
    from DB import (
        get_session,
        User,
        UserOAuth,
        OAuthProvider,
        UserCompany,
        Company,
    )

    user_ids = {}

    with get_session() as session:
        # Get the Teams OAuth provider
        provider = (
            session.query(OAuthProvider)
            .filter(OAuthProvider.name == "teams")
            .first()
        )

        if not provider:
            logging.debug("Teams OAuth provider not found in database")
            return user_ids

        # Build query for users with Teams OAuth
        query = (
            session.query(UserOAuth, User)
            .join(User, UserOAuth.user_id == User.id)
            .filter(UserOAuth.provider_id == provider.id)
        )

        if company_id:
            # Filter by company membership
            query = (
                query.join(UserCompany, User.id == UserCompany.user_id)
                .join(Company, UserCompany.company_id == Company.id)
                .filter(Company.id == company_id)
            )

        results = query.all()

        for oauth, user in results:
            if oauth.provider_user_id and user.email:
                user_ids[oauth.provider_user_id] = user.email

    logging.debug(f"Found {len(user_ids)} Teams user mappings")
    return user_ids


class teams(Extensions):
    """
    Microsoft Teams extension for AGiXT.
    
    This extension provides integration with Microsoft Teams, allowing AI agents to:
    - Read and send messages in Teams channels
    - Manage team memberships
    - Access channel information
    - Handle file attachments
    
    The extension requires the user to be authenticated with Microsoft Teams through OAuth.
    AI agents should use this when they need to interact with a user's Teams workspace
    for tasks like sending messages, reading channel history, or managing team settings.
    """

    CATEGORY = "Communication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("TEAMS_ACCESS_TOKEN", None)
        
        # Fall back to Microsoft tokens if Teams-specific not available
        if not self.access_token:
            self.access_token = kwargs.get("MICROSOFT_ACCESS_TOKEN", None)
            
        self.client_id = getenv("TEAMS_CLIENT_ID") or getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = getenv("TEAMS_CLIENT_SECRET") or getenv("MICROSOFT_CLIENT_SECRET")
        self.commands = {
            "List Joined Teams": self.list_joined_teams,
            "Get Team Info": self.get_team_info,
            "List Team Channels": self.list_team_channels,
            "Get Channel Info": self.get_channel_info,
            "List Channel Messages": self.list_channel_messages,
            "Send Channel Message": self.send_channel_message,
            "Reply to Channel Message": self.reply_to_channel_message,
            "List Chats": self.list_chats,
            "Get Chat Messages": self.get_chat_messages,
            "Send Chat Message": self.send_chat_message,
            "List Team Members": self.list_team_members,
            "Get My Teams Profile": self.get_my_teams_profile,
            "Search Messages": self.search_messages,
            "Create Team Channel": self.create_team_channel,
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict = None,
        params: dict = None,
        use_beta: bool = False,
    ) -> Optional[Dict]:
        """
        Make a request to the Microsoft Graph API.
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (without base URL)
            data: Request body for POST/PATCH requests
            params: Query parameters
            use_beta: Whether to use the beta API endpoint
            
        Returns:
            dict: Response JSON or None on error
        """
        if not self.access_token:
            logging.error("No access token available for Teams API request")
            return None

        base_url = GRAPH_API_BETA if use_beta else GRAPH_API_BASE
        url = f"{base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method.upper() == "PATCH":
                response = requests.patch(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers)
            else:
                logging.error(f"Unsupported HTTP method: {method}")
                return None

            if response.status_code == 401:
                logging.warning("Teams token expired, attempting refresh...")
                # Token might be expired, attempt refresh if we have refresh token
                return None

            if response.status_code >= 400:
                logging.error(f"Teams API error: {response.status_code} - {response.text}")
                return None

            if response.status_code == 204:  # No content
                return {"status": "success"}

            return response.json()

        except Exception as e:
            logging.error(f"Error making Teams API request: {e}")
            return None

    async def list_joined_teams(self) -> str:
        """
        List all teams that the authenticated user has joined.
        
        Returns:
            str: Formatted list of joined teams with names and descriptions
        """
        result = self._make_request("GET", "me/joinedTeams")
        
        if not result or "value" not in result:
            return "Unable to retrieve teams. Please check your Teams connection."

        teams_list = result["value"]
        if not teams_list:
            return "You have not joined any teams yet."

        output_lines = ["**Your Teams:**\n"]
        for team in teams_list:
            team_name = team.get("displayName", "Unknown Team")
            team_id = team.get("id", "")
            description = team.get("description", "No description")
            output_lines.append(f"• **{team_name}** (ID: {team_id})")
            if description:
                output_lines.append(f"  Description: {description}")
            output_lines.append("")

        return "\n".join(output_lines)

    async def get_team_info(self, team_id: str) -> str:
        """
        Get detailed information about a specific team.
        
        Args:
            team_id: The ID of the team to get info for
            
        Returns:
            str: Formatted team information
        """
        result = self._make_request("GET", f"teams/{team_id}")
        
        if not result:
            return f"Unable to retrieve team info for team {team_id}."

        output_lines = [
            f"**Team: {result.get('displayName', 'Unknown')}**\n",
            f"Description: {result.get('description', 'No description')}",
            f"ID: {result.get('id', '')}",
            f"Visibility: {result.get('visibility', 'unknown')}",
            f"Created: {result.get('createdDateTime', 'Unknown')}",
        ]

        if result.get("webUrl"):
            output_lines.append(f"Web URL: {result.get('webUrl')}")

        return "\n".join(output_lines)

    async def list_team_channels(self, team_id: str) -> str:
        """
        List all channels in a specific team.
        
        Args:
            team_id: The ID of the team to list channels for
            
        Returns:
            str: Formatted list of channels
        """
        result = self._make_request("GET", f"teams/{team_id}/channels")
        
        if not result or "value" not in result:
            return f"Unable to retrieve channels for team {team_id}."

        channels = result["value"]
        if not channels:
            return "No channels found in this team."

        output_lines = ["**Channels:**\n"]
        for channel in channels:
            channel_name = channel.get("displayName", "Unknown Channel")
            channel_id = channel.get("id", "")
            membership_type = channel.get("membershipType", "standard")
            output_lines.append(f"• **{channel_name}** ({membership_type})")
            output_lines.append(f"  ID: {channel_id}")
            if channel.get("description"):
                output_lines.append(f"  Description: {channel.get('description')}")
            output_lines.append("")

        return "\n".join(output_lines)

    async def get_channel_info(self, team_id: str, channel_id: str) -> str:
        """
        Get detailed information about a specific channel.
        
        Args:
            team_id: The ID of the team
            channel_id: The ID of the channel
            
        Returns:
            str: Formatted channel information
        """
        result = self._make_request("GET", f"teams/{team_id}/channels/{channel_id}")
        
        if not result:
            return f"Unable to retrieve channel info."

        output_lines = [
            f"**Channel: {result.get('displayName', 'Unknown')}**\n",
            f"Description: {result.get('description', 'No description')}",
            f"ID: {result.get('id', '')}",
            f"Membership Type: {result.get('membershipType', 'standard')}",
            f"Created: {result.get('createdDateTime', 'Unknown')}",
        ]

        if result.get("webUrl"):
            output_lines.append(f"Web URL: {result.get('webUrl')}")

        return "\n".join(output_lines)

    async def list_channel_messages(
        self, team_id: str, channel_id: str, limit: int = 20
    ) -> str:
        """
        List recent messages from a channel.
        
        Args:
            team_id: The ID of the team
            channel_id: The ID of the channel
            limit: Maximum number of messages to retrieve (default: 20)
            
        Returns:
            str: Formatted list of messages
        """
        params = {"$top": min(limit, 50)}
        result = self._make_request(
            "GET", f"teams/{team_id}/channels/{channel_id}/messages", params=params
        )
        
        if not result or "value" not in result:
            return "Unable to retrieve channel messages."

        messages = result["value"]
        if not messages:
            return "No messages found in this channel."

        output_lines = ["**Recent Messages:**\n"]
        for msg in messages:
            sender = msg.get("from", {}).get("user", {}).get("displayName", "Unknown")
            content = msg.get("body", {}).get("content", "")
            created = msg.get("createdDateTime", "")
            msg_id = msg.get("id", "")
            
            # Strip HTML tags from content for readability
            import re
            content = re.sub(r"<[^>]+>", "", content).strip()
            
            if len(content) > 200:
                content = content[:200] + "..."
                
            output_lines.append(f"**{sender}** ({created[:10]})")
            output_lines.append(f"  {content}")
            output_lines.append(f"  Message ID: {msg_id}")
            output_lines.append("")

        return "\n".join(output_lines)

    async def send_channel_message(
        self, team_id: str, channel_id: str, message: str
    ) -> str:
        """
        Send a message to a Teams channel.
        
        Args:
            team_id: The ID of the team
            channel_id: The ID of the channel
            message: The message content to send
            
        Returns:
            str: Confirmation message or error
        """
        data = {
            "body": {
                "content": message,
            }
        }
        
        result = self._make_request(
            "POST", f"teams/{team_id}/channels/{channel_id}/messages", data=data
        )
        
        if result:
            msg_id = result.get("id", "unknown")
            return f"Message sent successfully. Message ID: {msg_id}"
        return "Failed to send message to the channel."

    async def reply_to_channel_message(
        self, team_id: str, channel_id: str, message_id: str, reply: str
    ) -> str:
        """
        Reply to a specific message in a Teams channel.
        
        Args:
            team_id: The ID of the team
            channel_id: The ID of the channel
            message_id: The ID of the message to reply to
            reply: The reply content
            
        Returns:
            str: Confirmation message or error
        """
        data = {
            "body": {
                "content": reply,
            }
        }
        
        result = self._make_request(
            "POST",
            f"teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies",
            data=data,
        )
        
        if result:
            reply_id = result.get("id", "unknown")
            return f"Reply sent successfully. Reply ID: {reply_id}"
        return "Failed to send reply."

    async def list_chats(self, limit: int = 20) -> str:
        """
        List the user's recent chats (direct messages and group chats).
        
        Args:
            limit: Maximum number of chats to retrieve (default: 20)
            
        Returns:
            str: Formatted list of chats
        """
        params = {"$top": min(limit, 50), "$expand": "members"}
        result = self._make_request("GET", "me/chats", params=params)
        
        if not result or "value" not in result:
            return "Unable to retrieve chats."

        chats = result["value"]
        if not chats:
            return "No chats found."

        output_lines = ["**Your Chats:**\n"]
        for chat in chats:
            chat_type = chat.get("chatType", "unknown")
            chat_id = chat.get("id", "")
            topic = chat.get("topic", "Untitled Chat")
            
            # Get member names for display
            members = chat.get("members", [])
            member_names = [m.get("displayName", "Unknown") for m in members]
            
            if chat_type == "oneOnOne":
                display_name = ", ".join([n for n in member_names if n != "You"][:2])
            else:
                display_name = topic or ", ".join(member_names[:3])
                
            output_lines.append(f"• **{display_name}** ({chat_type})")
            output_lines.append(f"  Chat ID: {chat_id}")
            output_lines.append("")

        return "\n".join(output_lines)

    async def get_chat_messages(self, chat_id: str, limit: int = 20) -> str:
        """
        Get recent messages from a specific chat.
        
        Args:
            chat_id: The ID of the chat
            limit: Maximum number of messages to retrieve (default: 20)
            
        Returns:
            str: Formatted list of messages
        """
        params = {"$top": min(limit, 50)}
        result = self._make_request("GET", f"me/chats/{chat_id}/messages", params=params)
        
        if not result or "value" not in result:
            return "Unable to retrieve chat messages."

        messages = result["value"]
        if not messages:
            return "No messages found in this chat."

        output_lines = ["**Chat Messages:**\n"]
        for msg in messages:
            sender = msg.get("from", {})
            if sender:
                sender_name = sender.get("user", {}).get("displayName", "Unknown")
            else:
                sender_name = "System"
                
            content = msg.get("body", {}).get("content", "")
            created = msg.get("createdDateTime", "")
            
            # Strip HTML tags
            import re
            content = re.sub(r"<[^>]+>", "", content).strip()
            
            if len(content) > 200:
                content = content[:200] + "..."
                
            output_lines.append(f"**{sender_name}** ({created[:10]})")
            output_lines.append(f"  {content}")
            output_lines.append("")

        return "\n".join(output_lines)

    async def send_chat_message(self, chat_id: str, message: str) -> str:
        """
        Send a message to a specific chat.
        
        Args:
            chat_id: The ID of the chat
            message: The message content to send
            
        Returns:
            str: Confirmation message or error
        """
        data = {
            "body": {
                "content": message,
            }
        }
        
        result = self._make_request("POST", f"me/chats/{chat_id}/messages", data=data)
        
        if result:
            msg_id = result.get("id", "unknown")
            return f"Message sent successfully. Message ID: {msg_id}"
        return "Failed to send chat message."

    async def list_team_members(self, team_id: str) -> str:
        """
        List all members of a specific team.
        
        Args:
            team_id: The ID of the team
            
        Returns:
            str: Formatted list of team members
        """
        result = self._make_request("GET", f"teams/{team_id}/members")
        
        if not result or "value" not in result:
            return f"Unable to retrieve team members."

        members = result["value"]
        if not members:
            return "No members found in this team."

        output_lines = ["**Team Members:**\n"]
        for member in members:
            display_name = member.get("displayName", "Unknown")
            email = member.get("email", "")
            roles = member.get("roles", [])
            role_str = ", ".join(roles) if roles else "member"
            
            output_lines.append(f"• **{display_name}** ({role_str})")
            if email:
                output_lines.append(f"  Email: {email}")

        return "\n".join(output_lines)

    async def get_my_teams_profile(self) -> str:
        """
        Get the authenticated user's Teams profile information.
        
        Returns:
            str: Formatted user profile information
        """
        result = self._make_request("GET", "me")
        
        if not result:
            return "Unable to retrieve your profile."

        output_lines = [
            f"**Your Teams Profile:**\n",
            f"Name: {result.get('displayName', 'Unknown')}",
            f"Email: {result.get('mail') or result.get('userPrincipalName', '')}",
            f"Job Title: {result.get('jobTitle', 'Not set')}",
            f"Department: {result.get('department', 'Not set')}",
            f"Office Location: {result.get('officeLocation', 'Not set')}",
            f"User ID: {result.get('id', '')}",
        ]

        return "\n".join(output_lines)

    async def search_messages(self, query: str, limit: int = 20) -> str:
        """
        Search for messages across Teams chats and channels.
        
        Note: This requires Microsoft Search API permissions.
        
        Args:
            query: The search query string
            limit: Maximum number of results (default: 20)
            
        Returns:
            str: Formatted search results
        """
        # Use Microsoft Search API for message search
        data = {
            "requests": [
                {
                    "entityTypes": ["chatMessage"],
                    "query": {"queryString": query},
                    "from": 0,
                    "size": min(limit, 50),
                }
            ]
        }
        
        result = self._make_request("POST", "search/query", data=data)
        
        if not result or "value" not in result:
            return "Unable to search messages. This feature may require additional permissions."

        hits = result.get("value", [{}])[0].get("hitsContainers", [{}])[0].get("hits", [])
        
        if not hits:
            return f"No messages found matching '{query}'."

        output_lines = [f"**Search Results for '{query}':**\n"]
        for hit in hits:
            resource = hit.get("resource", {})
            summary = resource.get("summary", "")
            sender = resource.get("from", {}).get("user", {}).get("displayName", "Unknown")
            
            output_lines.append(f"• **{sender}**: {summary}")
            output_lines.append("")

        return "\n".join(output_lines)

    async def create_team_channel(
        self,
        team_id: str,
        channel_name: str,
        description: str = "",
        membership_type: str = "standard",
    ) -> str:
        """
        Create a new channel in a team.
        
        Args:
            team_id: The ID of the team
            channel_name: The name for the new channel
            description: Optional channel description
            membership_type: Channel type - 'standard', 'private', or 'shared'
            
        Returns:
            str: Confirmation message with channel details or error
        """
        data = {
            "displayName": channel_name,
            "description": description,
            "membershipType": membership_type,
        }
        
        result = self._make_request("POST", f"teams/{team_id}/channels", data=data)
        
        if result:
            channel_id = result.get("id", "unknown")
            return (
                f"Channel '{channel_name}' created successfully.\n"
                f"Channel ID: {channel_id}"
            )
        return f"Failed to create channel '{channel_name}'."
