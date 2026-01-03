"""
Claude Code Extension for AGiXT

This extension provides Anthropic/Claude integration following AGiXT's
standard OAuth patterns (similar to google.py, microsoft.py, github.py).

Environment Variables:
- ANTHROPIC_CLIENT_ID: OAuth client ID from Anthropic Console
- ANTHROPIC_CLIENT_SECRET: OAuth client secret from Anthropic Console
"""

import os
import logging
import requests
from typing import Dict, Any
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from safeexecute import execute_python_code


# =============================================================================
# OAuth Configuration (following AGiXT patterns)
# =============================================================================

SCOPES = [
    "user:read",
    "conversations:read",
    "conversations:write",
    "models:read",
    "usage:read",
]

AUTHORIZE = "https://claude.ai/oauth/authorize"
PKCE_REQUIRED = True


class AnthropicSSO:
    """
    Anthropic/Claude SSO handler following AGiXT OAuth patterns.
    Similar to GoogleSSO, MicrosoftSSO, GitHubSSO classes.
    """

    def __init__(self, access_token: str = None, refresh_token: str = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_url = "https://claude.ai/oauth/token"
        self.userinfo_url = "https://claude.ai/api/auth/session"
        self.client_id = getenv("ANTHROPIC_CLIENT_ID")
        self.client_secret = getenv("ANTHROPIC_CLIENT_SECRET")

    def get_new_token(self) -> str:
        """Refresh the access token using the refresh token"""
        if not self.refresh_token:
            logging.error("No refresh token available for Anthropic")
            return None

        response = requests.post(
            self.token_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )

        if response.status_code != 200:
            logging.error(f"Error refreshing Anthropic token: {response.text}")
            return None

        tokens = response.json()
        self.access_token = tokens.get("access_token", self.access_token)
        if "refresh_token" in tokens:
            self.refresh_token = tokens["refresh_token"]
        return self.access_token

    def get_user_info(self) -> Dict[str, Any]:
        """Get user info from Anthropic"""
        if not self.access_token:
            return None

        response = requests.get(
            self.userinfo_url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30,
        )

        if response.status_code == 401 and self.refresh_token:
            new_token = self.get_new_token()
            if new_token:
                response = requests.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {new_token}"},
                    timeout=30,
                )

        if response.status_code != 200:
            logging.error(f"Error getting Anthropic user info: {response.text}")
            return None

        data = response.json()
        user = data.get("user", data)
        return {
            "email": user.get("email", user.get("id", "")),
            "name": user.get("name", ""),
            "id": user.get("id"),
            "plan": user.get("plan", "free"),
        }


def sso(code: str, redirect_uri: str = None) -> AnthropicSSO:
    """
    Exchange authorization code for tokens.
    Standard AGiXT sso() function pattern.
    """
    client_id = getenv("ANTHROPIC_CLIENT_ID")
    client_secret = getenv("ANTHROPIC_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Anthropic OAuth not configured")
        return None

    response = requests.post(
        "https://claude.ai/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    if response.status_code != 200:
        logging.error(f"Error getting Anthropic access token: {response.text}")
        return None

    tokens = response.json()
    return AnthropicSSO(
        access_token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
    )


# =============================================================================
# Extension Class
# =============================================================================


class claude_code(Extensions):
    """
    Claude Code Extension - Send requests to Claude using OAuth credentials.
    Uses safeexecute tied to the conversation ID for sandboxed execution.
    """

    CATEGORY = "AI Integration"
    friendly_name = "Claude Code"

    def __init__(self, **kwargs):
        self.agent_name = kwargs.get("agent_name", "gpt4free")
        self.api_key = kwargs.get("api_key", "")
        self.conversation_id = kwargs.get("conversation_id", "")

        # Workspace tied to conversation ID
        self.working_directory = kwargs.get(
            "conversation_directory",
            os.path.join(os.getcwd(), "WORKSPACE", self.conversation_id or "default"),
        )
        os.makedirs(self.working_directory, exist_ok=True)

        # Initialize MagicalAuth for OAuth
        self.auth = None
        if self.api_key:
            try:
                self.auth = MagicalAuth(token=self.api_key)
            except Exception as e:
                logging.error(f"Error initializing Claude Code extension: {e}")

        self.commands = {
            "Make Request to Claude Code": self.make_request,
        }

    def _get_access_token(self) -> str:
        """Get the Anthropic access token from MagicalAuth OAuth"""
        if self.auth:
            try:
                oauth_data = self.auth.get_oauth_functions("anthropic")
                if oauth_data and hasattr(oauth_data, "access_token"):
                    return oauth_data.access_token
                return self.auth.refresh_oauth_token(provider="anthropic")
            except Exception as e:
                logging.error(f"Error getting Anthropic token: {e}")
        return None

    async def make_request(self, message: str) -> str:
        """
        Make a request to Claude Code using your connected Anthropic account.
        Executes in a sandboxed environment tied to your conversation.

        Args:
            message: The message/prompt to send to Claude

        Returns:
            Claude's response
        """
        access_token = self._get_access_token()
        if not access_token:
            return "Error: No Anthropic account connected. Please connect your Anthropic account via OAuth."

        code = f'''
import requests

response = requests.post(
    "https://api.anthropic.com/v1/messages",
    headers={{
        "Authorization": "Bearer {access_token}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }},
    json={{
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [{{"role": "user", "content": """{message.replace('"', '\\"')}"""}}],
    }},
    timeout=120,
)

if response.status_code == 200:
    data = response.json()
    content = data.get("content", [])
    print(content[0].get("text", "No response") if content else "No response from Claude")
else:
    print(f"Error: {{response.status_code}} - {{response.text}}")
'''
        return execute_python_code(code=code, working_directory=self.working_directory)
