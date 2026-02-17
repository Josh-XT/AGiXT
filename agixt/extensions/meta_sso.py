import logging
import requests
from Extensions import Extensions
from Globals import getenv
from fastapi import HTTPException

"""
Meta/Facebook SSO Extension - Minimal scopes for Single Sign-On only.

This extension provides OAuth authentication for Facebook accounts with the minimum
required scopes for user login. It does NOT include permissions for ads management,
business features, or page management - those are available through the meta_ads
extension that the user can connect separately.

Required environment variables:

- META_APP_ID: Facebook/Meta App ID
- META_APP_SECRET: Facebook/Meta App Secret

Required scopes (minimal for identity):
- email: User's email address
- public_profile: Basic profile information (name, picture, etc.)
"""

SCOPES = ["email", "public_profile"]
AUTHORIZE = "https://www.facebook.com/v18.0/dialog/oauth"
PKCE_REQUIRED = False
SSO_ONLY = True  # This provider can be used for login/registration
CATEGORY = "Authentication"


class MetaSsoSSO:
    """SSO handler for Meta/Facebook authentication with minimal scopes."""

    def __init__(self, access_token=None, refresh_token=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("META_APP_ID")
        self.client_secret = getenv("META_APP_SECRET")
        self.token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        self.api_base_url = "https://graph.facebook.com/v18.0"

        self.user_info = None
        if self.access_token and not self.access_token.startswith("test_"):
            try:
                self.user_info = self.get_user_info()
            except Exception as e:
                logging.warning(f"Could not get user info during initialization: {e}")
                self.user_info = None

    def get_new_token(self):
        """Refresh the access token using refresh token or exchange for long-lived token."""
        if not self.refresh_token:
            return self.get_long_lived_token()

        response = requests.post(
            self.token_url,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "fb_exchange_token": self.access_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to refresh token: {response.text}",
            )

        data = response.json()

        if "access_token" in data:
            self.access_token = data["access_token"]
        else:
            raise Exception("No access_token in Meta refresh response")

        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        return data

    def get_long_lived_token(self):
        """Exchange short-lived token for long-lived token."""
        response = requests.get(
            f"{self.api_base_url}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "fb_exchange_token": self.access_token,
            },
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to get long-lived token: {response.text}",
            )

        data = response.json()

        if "access_token" in data:
            self.access_token = data["access_token"]
        else:
            raise Exception("No access_token in Meta long-lived token response")

        return data

    def get_user_info(self):
        """Get user information from the Facebook Graph API."""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = requests.get(
                f"{self.api_base_url}/me",
                params={"fields": "id,name,email,first_name,last_name,picture"},
                headers=headers,
            )

            if response.status_code == 401 and self.refresh_token:
                logging.info("Token expired, refreshing...")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(
                    f"{self.api_base_url}/me",
                    params={"fields": "id,name,email,first_name,last_name,picture"},
                    headers=headers,
                )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            data = response.json()
            return {
                "email": data.get("email"),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "id": data.get("id"),
                "picture": data.get("picture", {}).get("data", {}).get("url", ""),
            }
        except Exception as e:
            logging.error(f"Error getting Meta user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Facebook",
            )


def sso(code, redirect_uri=None) -> MetaSsoSSO:
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

    response = requests.get(
        "https://graph.facebook.com/v18.0/oauth/access_token",
        params={
            "client_id": getenv("META_APP_ID"),
            "client_secret": getenv("META_APP_SECRET"),
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )

    if response.status_code != 200:
        logging.error(f"Error getting Meta access token: {response.text}")
        return None

    data = response.json()
    access_token = data.get("access_token")
    # Meta doesn't typically return refresh tokens
    refresh_token = data.get("refresh_token")
    return MetaSsoSSO(access_token=access_token, refresh_token=refresh_token)


class meta_sso(Extensions):
    """
    Meta/Facebook SSO Extension - Minimal scopes for login/registration only.

    This extension provides basic Facebook Single Sign-On functionality with minimal
    scope requirements. It is designed for user authentication and profile retrieval
    only. For advertising and business features, use the meta_ads extension.

    The user can connect the Meta Ads extension separately in settings to grant
    the AI access to manage advertising campaigns.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "Facebook SSO - Verify Connection": self.verify_meta_sso_connection,
            "Facebook SSO - Get User Profile": self.get_meta_user_profile,
        }
        self.META_SSO_ACCESS_TOKEN = kwargs.get("META_SSO_ACCESS_TOKEN", None)
        if self.META_SSO_ACCESS_TOKEN:
            self.meta_sso = MetaSsoSSO(access_token=self.META_SSO_ACCESS_TOKEN)

    async def verify_meta_sso_connection(self) -> str:
        """
        Verify that the Facebook SSO connection is working.

        Returns:
            str: Connection status message
        """
        if not self.META_SSO_ACCESS_TOKEN:
            return "Facebook SSO is not connected. Please connect your Facebook account in settings."

        try:
            user_info = self.meta_sso.get_user_info()
            return f"Facebook SSO connection verified. Connected as: {user_info.get('email', 'Unknown')}"
        except Exception as e:
            return f"Facebook SSO connection failed: {str(e)}"

    async def get_meta_user_profile(self) -> str:
        """
        Get the connected Facebook user's profile information.

        Returns:
            str: User profile information
        """
        if not self.META_SSO_ACCESS_TOKEN:
            return "Facebook SSO is not connected. Please connect your Facebook account in settings."

        try:
            user_info = self.meta_sso.get_user_info()
            return f"""Facebook User Profile:
- Email: {user_info.get('email', 'Not available')}
- First Name: {user_info.get('first_name', 'Not available')}
- Last Name: {user_info.get('last_name', 'Not available')}

Note: For advertising and business features, connect the Meta Ads extension in settings."""
        except Exception as e:
            return f"Error getting Facebook profile: {str(e)}"
