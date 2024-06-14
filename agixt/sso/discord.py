import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- DISCORD_CLIENT_ID: Discord OAuth client ID
- DISCORD_CLIENT_SECRET: Discord OAuth client secret

Required APIs and Scopes

Follow the links to confirm that you have the APIs enabled,
then add the `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` environment variables to your `.env` file.

- OAuth2 API
- Email scope https://discord.com/developers/docs/topics/oauth2#shared-resources-oauth2-scopes
"""


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
        response = requests.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://discord.com/api/users/@me"
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
            username = data["username"]
            discriminator = data["discriminator"]
            email = data["email"]
            return {
                "username": username,
                "discriminator": discriminator,
                "email": email,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Discord",
            )

    # Discord doesn't have a direct send email API, but you could implement similar functionality
    # using a bot or webhook if necessary.


def discord_sso(code, redirect_uri=None) -> DiscordSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )
    response = requests.post(
        f"https://discord.com/api/oauth2/token",
        data={
            "client_id": getenv("DISCORD_CLIENT_ID"),
            "client_secret": getenv("DISCORD_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        logging.error(f"Error getting Discord access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return DiscordSSO(access_token=access_token, refresh_token=refresh_token)
