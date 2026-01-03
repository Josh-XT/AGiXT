"""
Claude Code Extension for AGiXT

This extension runs the Claude Code CLI (@anthropic-ai/claude-code) in the
conversation's sandbox environment via safeexecute.

OAuth Flow:
1. User connects Anthropic account via OAuth (ANTHROPIC_CLIENT_ID/SECRET)
2. Access token is retrieved via MagicalAuth
3. Token is passed as ANTHROPIC_API_KEY to Claude Code CLI in safeexecute

Requirements:
- Node.js installed in the sandbox environment
- Claude Code CLI: npm install -g @anthropic-ai/claude-code

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
    Claude Code Extension - Runs the Claude Code CLI in safeexecute sandbox.
    Uses OAuth to get Anthropic API key, then passes it to Claude Code CLI.
    """

    CATEGORY = "AI Integration"
    friendly_name = "Claude Code"

    def __init__(self, **kwargs):
        self.agent_name = kwargs.get("agent_name", "gpt4free")
        self.api_key = kwargs.get("api_key", "")
        self.conversation_id = kwargs.get("conversation_id", "")
        self.conversation_name = kwargs.get("conversation_name", "")
        self.activity_id = kwargs.get("activity_id", "")
        self.user = kwargs.get("user", "")

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

        from InternalClient import InternalClient

        self.ApiClient = kwargs.get("ApiClient") or InternalClient(
            api_key=self.api_key,
            user=self.user,
        )

        self.commands = {
            "Make Request to Claude Code": self.make_request,
        }

    def _get_api_key(self) -> str:
        """Get the Anthropic API key from MagicalAuth OAuth"""
        if self.auth:
            try:
                oauth_data = self.auth.get_oauth_functions("anthropic")
                if oauth_data and hasattr(oauth_data, "access_token"):
                    return oauth_data.access_token
                return self.auth.refresh_oauth_token(provider="anthropic")
            except Exception as e:
                logging.error(f"Error getting Anthropic token: {e}")
        return None

    def _send_subactivity(self, message: str):
        """Send a sub-activity message if activity tracking is available"""
        if self.activity_id and self.conversation_name:
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] {message}",
                conversation_name=self.conversation_name,
            )

    async def make_request(self, message: str) -> str:
        """
        Run Claude Code CLI in the safeexecute sandbox.
        Gets API key via OAuth and passes to Claude Code.
        Streams output as sub-activities during execution.

        Args:
            message: The prompt/task for Claude Code to execute

        Returns:
            Claude Code's final output
        """
        api_key = self._get_api_key()
        if not api_key:
            return "Error: No Anthropic account connected. Please connect your Anthropic account via OAuth."

        self._send_subactivity("Starting Claude Code...")

        # Escape message for shell
        escaped_message = message.replace("'", "'\\''")

        # Run Claude Code CLI in safeexecute sandbox
        code = f"""
import subprocess
import os
import json

os.chdir("{self.working_directory}")

# Set API key from OAuth
env = os.environ.copy()
env["ANTHROPIC_API_KEY"] = "{api_key}"

# Run Claude Code in non-interactive mode with streaming JSON output
process = subprocess.Popen(
    ["claude", "--print", "--output-format", "stream-json", '{escaped_message}'],
    cwd="{self.working_directory}",
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

output_lines = []
for line in process.stdout:
    line = line.strip()
    if not line:
        continue
    output_lines.append(line)
    try:
        data = json.loads(line)
        msg_type = data.get("type", "")
        if msg_type == "assistant":
            message_data = data.get("message", {{}})
            content = message_data.get("content", [])
            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        print(f"[response] {{text[:200]}}")
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    print(f"[tool] Using: {{tool_name}}")
        elif msg_type == "result":
            result_text = data.get("result", "")
            if result_text:
                print(f"[result] {{result_text[:500]}}")
    except json.JSONDecodeError:
        print(line[:200])

process.wait()
stderr = process.stderr.read()
if stderr:
    print(f"[stderr] {{stderr}}")
if process.returncode != 0:
    print(f"[exit] Claude Code exited with code {{process.returncode}}")
"""
        # Execute Claude Code in the sandbox
        result = execute_python_code(
            code=code, working_directory=self.working_directory
        )

        # Stream each line as a sub-activity
        if result:
            for line in result.strip().split("\n"):
                if line.strip():
                    self._send_subactivity(line.strip())

        self._send_subactivity("Claude Code session completed.")
        return result if result else "Claude Code task completed."
