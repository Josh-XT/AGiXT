# ./agixt/sso/discord.py
import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- DISCORD_CLIENT_ID: Discord OAuth client ID
- DISCORD_CLIENT_SECRET: Discord OAuth client secret

Required scopes for Discord OAuth:

- identify: Access user's basic info (username, avatar, discriminator)
- email: Access user's email address
- guilds: Access list of guilds the user is in
- guild.members.read: Access list of members in a guild
"""

SCOPES = ["identify", "email", "guilds", "guild.members.read"]
AUTHORIZE = "https://discord.com/api/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
USER_INFO_URL = "https://discord.com/api/users/@me"
PKCE_REQUIRED = False


class DiscordSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("DISCORD_CLIENT_ID")
        self.client_secret = getenv("DISCORD_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refreshes the Discord access token using the refresh token."""
        if not self.refresh_token:
            raise HTTPException(
                status_code=400, detail="No refresh token available for Discord."
            )

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(TOKEN_URL, data=payload, headers=headers)
            response.raise_for_status()  # Raise exception for bad status codes
            data = response.json()
            self.access_token = data.get("access_token")
            # Discord refresh tokens might be single-use or long-lived, handle accordingly
            self.refresh_token = data.get("refresh_token", self.refresh_token)
            logging.info("Successfully refreshed Discord token.")
            return self.access_token
        except requests.exceptions.RequestException as e:
            logging.error(f"Error refreshing Discord token: {response.text}")
            raise HTTPException(
                status_code=401, detail=f"Failed to refresh Discord token: {str(e)}"
            )

    def get_user_info(self):
        """Gets user information from Discord API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = requests.get(USER_INFO_URL, headers=headers)

            if response.status_code == 401:  # Token might be expired
                logging.info("Discord token likely expired, attempting refresh.")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(USER_INFO_URL, headers=headers)

            response.raise_for_status()
            data = response.json()

            # Discord provides username + discriminator, combine for uniqueness if needed
            # Or use email if available and preferred.
            email = data.get("email")
            username = data.get("username")
            full_username = f"{username}#{data.get('discriminator', '0000')}"
            global_name = data.get("global_name")  # Newer display name

            # Use global_name for first name, username for last name if names aren't structured
            first_name = global_name if global_name else username
            last_name = ""  # Discord doesn't provide separate last name

            return {
                "email": email
                or full_username,  # Fallback to username#discriminator if email scope not granted/available
                "first_name": first_name,
                "last_name": last_name,
            }
        except requests.exceptions.RequestException as e:
            logging.error(f"Error getting user info from Discord: {response.text}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Discord: {str(e)}",
            )


def sso(code, redirect_uri=None) -> DiscordSSO:
    """Handles the OAuth2 authorization code flow for Discord."""
    if not redirect_uri:
        redirect_uri = getenv(
            "APP_URI"
        )  # Make sure this matches exactly what's in Discord Dev Portal

    client_id = getenv("DISCORD_CLIENT_ID")
    client_secret = getenv("DISCORD_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Discord Client ID or Secret not configured.")
        return None

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),  # Ensure scopes match requested ones
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = requests.post(TOKEN_URL, data=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")  # Useful for knowing when to refresh
        logging.info(f"Discord token obtained. Expires in: {expires_in} seconds.")
        return DiscordSSO(access_token=access_token, refresh_token=refresh_token)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error obtaining Discord access token: {response.text}")
        return None
