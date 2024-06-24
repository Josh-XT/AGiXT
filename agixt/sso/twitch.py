import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- TWITCH_CLIENT_ID: Twitch OAuth client ID
- TWITCH_CLIENT_SECRET: Twitch OAuth client secret

Required scope for Twitch OAuth

- user:read:email
Follow the links to confirm that you have the APIs enabled,
then add the `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` environment variables to your `.env` file.
"""


class TwitchSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("TWITCH_CLIENT_ID")
        self.client_secret = getenv("TWITCH_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.twitch.tv/helix/users"
        response = requests.get(
            uri,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Client-Id": self.client_id,
            },
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Client-Id": self.client_id,
                },
            )
        try:
            data = response.json()["data"][0]
            first_name = data["display_name"]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": "",  # Twitch API does not provide surname in user info
            }
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Twitch",
            )

    # Twitch doesn't support email sending directly, implement your own function for sending messages if needed
    def send_message(self, message_text):
        # You can implement another way to notify the user, like a whisper or chat message
        pass


def twitch_sso(code, redirect_uri=None) -> TwitchSSO:
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
        f"https://id.twitch.tv/oauth2/token",
        data={
            "client_id": getenv("TWITCH_CLIENT_ID"),
            "client_secret": getenv("TWITCH_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Twitch access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return TwitchSSO(access_token=access_token, refresh_token=refresh_token)
