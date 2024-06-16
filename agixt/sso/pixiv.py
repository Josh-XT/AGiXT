import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- PIXIV_CLIENT_ID: Pixiv OAuth client ID
- PIXIV_CLIENT_SECRET: Pixiv OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `PIXIV_CLIENT_ID` and `PIXIV_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Pixiv OAuth

- pixiv.scope.profile.read
"""


class PixivSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("PIXIV_CLIENT_ID")
        self.client_secret = getenv("PIXIV_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://oauth.secure.pixiv.net/auth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Error refreshing Pixiv token",
            )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://app-api.pixiv.net/v1/user/me"
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
            user = data["user"]
            first_name = user["name"]
            email = user.get("mail_address", "No_Email_Provided")
            return {
                "email": email,
                "first_name": first_name,
                "last_name": "",
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Pixiv",
            )

    def send_email(self, to, subject, message_text):
        raise NotImplementedError("Pixiv does not support sending messages")


def pixiv_sso(code, redirect_uri=None) -> PixivSSO:
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
        f"https://oauth.secure.pixiv.net/auth/token",
        data={
            "code": code,
            "client_id": getenv("PIXIV_CLIENT_ID"),
            "client_secret": getenv("PIXIV_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Pixiv access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return PixivSSO(access_token=access_token, refresh_token=refresh_token)
