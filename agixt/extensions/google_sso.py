import logging
import requests
from fastapi import HTTPException
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth


"""
Google SSO Extension - Minimal scopes for login/registration only.

This extension provides basic Google Single Sign-On functionality with minimal
scope requirements. It is designed for user authentication and profile retrieval
only. For email, calendar, and marketing functionality, use the respective
Google extensions (google_email, google_calendar, google_marketing).

Required environment variables:

- GOOGLE_CLIENT_ID: Google OAuth client ID
- GOOGLE_CLIENT_SECRET: Google OAuth client secret

Required scopes (minimal):
- userinfo.profile: Basic profile information
- userinfo.email: Email address
"""

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
PKCE_REQUIRED = False
SSO_ONLY = True  # This provider can be used for login/registration


class GoogleSsoSSO:
    """SSO handler for Google with minimal profile-only scopes."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GOOGLE_CLIENT_ID")
        self.client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.email_address = None
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(SCOPES),
            },
        )
        if response.status_code != 200:
            logging.error(f"Token refresh failed with response: {response.text}")
            raise Exception(f"Google token refresh failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            logging.error("No access_token in refresh response")

        return token_data

    def get_user_info(self):
        uri = "https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses"

        if not self.access_token:
            logging.error("No access token available")

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
            first_name = data["names"][0]["givenName"]
            last_name = data["names"][0]["familyName"]
            email = data["emailAddresses"][0]["value"]
            self.email_address = email
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error parsing Google user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Google",
            )


def sso(code, redirect_uri=None) -> GoogleSsoSSO:
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
        "https://accounts.google.com/o/oauth2/token",
        params={
            "code": code,
            "client_id": getenv("GOOGLE_CLIENT_ID"),
            "client_secret": getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Google access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else None
    return GoogleSsoSSO(access_token=access_token, refresh_token=refresh_token)


class google_sso(Extensions):
    """
    Google SSO Extension.

    This extension provides basic Google authentication functionality with minimal
    scope requirements. It is designed for user login and profile verification only.

    For extended functionality, connect the following extensions separately:
    - google_email: Gmail access
    - google_calendar: Calendar access
    - google_marketing: Google Ads, Analytics, and Tag Manager access
    """

    CATEGORY = "Authentication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("GOOGLE_SSO_ACCESS_TOKEN", None)
        google_client_id = getenv("GOOGLE_CLIENT_ID")
        google_client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.auth = None

        if google_client_id and google_client_secret:
            self.commands = {
                "Verify Google SSO Connection": self.verify_connection,
                "Get Google Profile": self.get_profile,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Google SSO: {str(e)}")

    def verify_user(self):
        """Verifies that the current access token is valid."""
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="google_sso")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get(
            "https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses",
            headers=headers,
        )
        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the Google SSO extension is connected."
            )

    async def verify_connection(self):
        """
        Verifies that the Google SSO OAuth connection is working.

        Returns:
            dict: Connection status and user information
        """
        try:
            self.verify_user()
            return {
                "success": True,
                "message": "Google SSO connection is working correctly.",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def get_profile(self):
        """
        Gets the user's Google profile information.

        Returns:
            dict: User profile including name and email
        """
        try:
            self.verify_user()

            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                "https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses,photos,organizations",
                headers=headers,
            )

            if response.status_code != 200:
                return {"error": f"Failed to get profile: {response.text}"}

            data = response.json()

            profile = {
                "email": data.get("emailAddresses", [{}])[0].get("value", ""),
                "first_name": data.get("names", [{}])[0].get("givenName", ""),
                "last_name": data.get("names", [{}])[0].get("familyName", ""),
                "display_name": data.get("names", [{}])[0].get("displayName", ""),
            }

            if data.get("photos"):
                profile["photo_url"] = data["photos"][0].get("url", "")

            if data.get("organizations"):
                profile["organization"] = data["organizations"][0].get("name", "")

            return profile

        except Exception as e:
            logging.error(f"Error getting Google profile: {str(e)}")
            return {"error": str(e)}
