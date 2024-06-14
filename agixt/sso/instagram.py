import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- INSTAGRAM_CLIENT_ID: Instagram OAuth client ID
- INSTAGRAM_CLIENT_SECRET: Instagram OAuth client secret

Required APIs

Make sure you have the Instagram Basic Display API enabled.
Add the `INSTAGRAM_CLIENT_ID` and `INSTAGRAM_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Instagram OAuth

- user_profile
- user_media
"""


class InstagramSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("INSTAGRAM_CLIENT_ID")
        self.client_secret = getenv("INSTAGRAM_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://graph.instagram.com/refresh_access_token",
            params={
                "grant_type": "ig_refresh_token",
                "access_token": self.access_token,
            },
        )
        if response.status_code != 200:
            logging.error(f"Error refreshing Instagram access token: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail="Error refreshing Instagram access token",
            )

        return response.json()["access_token"]

    def get_user_info(self):
        uri = f"https://graph.instagram.com/me?fields=id,username,media_count&access_token={self.access_token}"
        response = requests.get(uri)
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(uri)
        try:
            data = response.json()
            username = data["username"]
            return {
                "username": username,
                "media_count": data.get("media_count", 0),
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Instagram",
            )

    def send_media_post(self, image_url, caption):
        uri = f"https://graph.instagram.com/me/media?image_url={image_url}&caption={caption}&access_token={self.access_token}"
        response = requests.post(uri)
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(uri)
        return response.json()


def instagram_sso(code, redirect_uri=None) -> InstagramSSO:
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
        f"https://api.instagram.com/oauth/access_token",
        data={
            "client_id": getenv("INSTAGRAM_CLIENT_ID"),
            "client_secret": getenv("INSTAGRAM_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Instagram access token: {response.text}")
        raise HTTPException(
            status_code=response.status_code,
            detail="Error getting Instagram access token",
        )

    data = response.json()
    access_token = data["access_token"]
    refresh_token = "Not applicable for Instagram"  # Instagram tokens last 60 days and refresh automatically every time a user interacts with the app

    return InstagramSSO(access_token=access_token, refresh_token=refresh_token)
