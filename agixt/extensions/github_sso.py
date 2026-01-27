import logging
import requests
from Extensions import Extensions
from Globals import getenv
from fastapi import HTTPException


"""
GitHub SSO Extension - Minimal scopes for Single Sign-On only.

This extension provides OAuth authentication for GitHub accounts with the minimum
required scopes for user login. It does NOT include permissions for repository access,
workflows, or other GitHub features - those are available through the main github
extension that the user can connect separately.

Required environment variables:

- GITHUB_CLIENT_ID: GitHub OAuth client ID
- GITHUB_CLIENT_SECRET: GitHub OAuth client secret

Required scopes (minimal for identity):
- user:email: Access user's email address
- read:user: Read user profile information
"""

SCOPES = ["user:email", "read:user"]
AUTHORIZE = "https://github.com/login/oauth/authorize"
PKCE_REQUIRED = False
SSO_ONLY = True  # This provider can be used for login/registration
CATEGORY = "Authentication"


class GithubSsoSSO:
    """SSO handler for GitHub authentication with minimal scopes."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GITHUB_CLIENT_ID")
        self.client_secret = getenv("GITHUB_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """GitHub tokens do not support refresh tokens directly."""
        if not self.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="GitHub tokens do not support refresh. Please re-authenticate.",
            )

        # This will likely fail since GitHub doesn't support refresh tokens
        # but we'll try anyway in case their API changes
        try:
            response = requests.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )

            if response.status_code != 200:
                raise Exception(f"GitHub token refresh failed: {response.text}")

            token_data = response.json()

            if "access_token" in token_data:
                self.access_token = token_data["access_token"]

            return token_data
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail="GitHub tokens do not support refresh. Please re-authenticate.",
            )

    def get_user_info(self):
        """Get user profile information from GitHub API."""
        uri = "https://api.github.com/user"
        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        try:
            data = response.json()
            # Get the primary email from the login
            primary_email = data.get("email") or data.get("login")
            return {
                "email": primary_email,
                "first_name": (
                    data.get("name", "").split()[0] if data.get("name") else ""
                ),
                "last_name": (
                    data.get("name", "").split()[-1] if data.get("name") else ""
                ),
            }
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from GitHub",
            )


def sso(code, redirect_uri=None) -> GithubSsoSSO:
    """Exchange authorization code for access token."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": getenv("GITHUB_CLIENT_ID"),
            "client_secret": getenv("GITHUB_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting GitHub access token: {response.text}")
        return None
    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    return GithubSsoSSO(access_token=access_token, refresh_token=refresh_token)


class github_sso(Extensions):
    """
    GitHub SSO Extension - Minimal scopes for login/registration only.

    This extension provides basic GitHub Single Sign-On functionality with minimal
    scope requirements. It is designed for user authentication and profile retrieval
    only. For repository access, workflows, and other GitHub features, use the main
    github extension.

    The user can connect the full GitHub extension separately in settings to grant
    the AI access to work with their repositories.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "GitHub SSO - Verify Connection": self.verify_github_sso_connection,
            "GitHub SSO - Get User Profile": self.get_github_user_profile,
        }
        self.GITHUB_SSO_ACCESS_TOKEN = kwargs.get("GITHUB_SSO_ACCESS_TOKEN", None)
        if self.GITHUB_SSO_ACCESS_TOKEN:
            self.github_sso = GithubSsoSSO(access_token=self.GITHUB_SSO_ACCESS_TOKEN)

    async def verify_github_sso_connection(self) -> str:
        """
        Verify that the GitHub SSO connection is working.

        Returns:
            str: Connection status message
        """
        if not self.GITHUB_SSO_ACCESS_TOKEN:
            return "GitHub SSO is not connected. Please connect your GitHub account in settings."

        try:
            user_info = self.github_sso.get_user_info()
            return f"GitHub SSO connection verified. Connected as: {user_info.get('email', 'Unknown')}"
        except Exception as e:
            return f"GitHub SSO connection failed: {str(e)}"

    async def get_github_user_profile(self) -> str:
        """
        Get the connected GitHub user's profile information.

        Returns:
            str: User profile information
        """
        if not self.GITHUB_SSO_ACCESS_TOKEN:
            return "GitHub SSO is not connected. Please connect your GitHub account in settings."

        try:
            user_info = self.github_sso.get_user_info()
            return f"""GitHub User Profile:
- Email: {user_info.get('email', 'Not available')}
- First Name: {user_info.get('first_name', 'Not available')}
- Last Name: {user_info.get('last_name', 'Not available')}

Note: For repository access and other GitHub features, connect the full GitHub extension in settings."""
        except Exception as e:
            return f"Error getting GitHub profile: {str(e)}"
