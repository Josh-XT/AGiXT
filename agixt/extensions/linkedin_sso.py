import logging
import requests
from Extensions import Extensions
from Globals import getenv
from fastapi import HTTPException

"""
LinkedIn SSO Extension - Minimal scopes for Single Sign-On only.

This extension provides OAuth authentication for LinkedIn accounts with the minimum
required scopes for user login. It does NOT include permissions for posting or
social features - those are available through the main linkedin extension that
the user can connect separately.

Required environment variables:

- LINKEDIN_CLIENT_ID: LinkedIn OAuth client ID
- LINKEDIN_CLIENT_SECRET: LinkedIn OAuth client secret

Required scopes (minimal for identity):
- openid: OpenID Connect authentication
- profile: Basic profile information
- email: Email address
"""

SCOPES = ["openid", "profile", "email"]
AUTHORIZE = "https://www.linkedin.com/oauth/v2/authorization"
PKCE_REQUIRED = False
SSO_ONLY = True  # This provider can be used for login/registration
CATEGORY = "Authentication"


class LinkedinSsoSSO:
    """SSO handler for LinkedIn authentication with minimal scopes."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = getenv("LINKEDIN_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refresh the access token using the refresh token."""
        response = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logging.error(f"LinkedIn token refresh failed: {response.text}")
            raise Exception(f"LinkedIn token refresh failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            logging.error("No access_token in LinkedIn refresh response")
            raise Exception("No access_token in LinkedIn refresh response")

        return token_data

    def get_user_info(self):
        """Get user profile information using the userinfo endpoint."""
        uri = "https://api.linkedin.com/v2/userinfo"

        if not self.access_token:
            logging.error("No access token available")
            return {}

        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

        if response.status_code == 401:
            self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

        try:
            data = response.json()
            first_name = data.get("given_name", "") or ""
            last_name = data.get("family_name", "") or ""
            email = data.get("email", "")

            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "sub": data.get("sub", ""),
                "picture": data.get("picture", ""),
            }
        except Exception as e:
            logging.error(f"Error parsing LinkedIn user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from LinkedIn",
            )


def sso(code, redirect_uri=None) -> LinkedinSsoSSO:
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
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": getenv("LINKEDIN_CLIENT_ID"),
            "client_secret": getenv("LINKEDIN_CLIENT_SECRET"),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        logging.error(f"Error getting LinkedIn access token: {response.text}")
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    return LinkedinSsoSSO(access_token=access_token, refresh_token=refresh_token)


class linkedin_sso(Extensions):
    """
    LinkedIn SSO Extension - Minimal scopes for login/registration only.

    This extension provides basic LinkedIn Single Sign-On functionality with minimal
    scope requirements. It is designed for user authentication and profile retrieval
    only. For posting and social features, use the main linkedin extension.

    The user can connect the full LinkedIn extension separately in settings to grant
    the AI access to post on their behalf.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "LinkedIn SSO - Verify Connection": self.verify_linkedin_sso_connection,
            "LinkedIn SSO - Get User Profile": self.get_linkedin_user_profile,
        }
        self.LINKEDIN_SSO_ACCESS_TOKEN = kwargs.get("LINKEDIN_SSO_ACCESS_TOKEN", None)
        if self.LINKEDIN_SSO_ACCESS_TOKEN:
            self.linkedin_sso = LinkedinSsoSSO(
                access_token=self.LINKEDIN_SSO_ACCESS_TOKEN
            )

    async def verify_linkedin_sso_connection(self) -> str:
        """
        Verify that the LinkedIn SSO connection is working.

        Returns:
            str: Connection status message
        """
        if not self.LINKEDIN_SSO_ACCESS_TOKEN:
            return "LinkedIn SSO is not connected. Please connect your LinkedIn account in settings."

        try:
            user_info = self.linkedin_sso.get_user_info()
            return f"LinkedIn SSO connection verified. Connected as: {user_info.get('email', 'Unknown')}"
        except Exception as e:
            return f"LinkedIn SSO connection failed: {str(e)}"

    async def get_linkedin_user_profile(self) -> str:
        """
        Get the connected LinkedIn user's profile information.

        Returns:
            str: User profile information
        """
        if not self.LINKEDIN_SSO_ACCESS_TOKEN:
            return "LinkedIn SSO is not connected. Please connect your LinkedIn account in settings."

        try:
            user_info = self.linkedin_sso.get_user_info()
            return f"""LinkedIn User Profile:
- Email: {user_info.get('email', 'Not available')}
- First Name: {user_info.get('first_name', 'Not available')}
- Last Name: {user_info.get('last_name', 'Not available')}

Note: For posting and social features, connect the full LinkedIn extension in settings."""
        except Exception as e:
            return f"Error getting LinkedIn profile: {str(e)}"
