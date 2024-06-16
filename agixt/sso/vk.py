import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- VK_CLIENT_ID: VK OAuth client ID
- VK_CLIENT_SECRET: VK OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `VK_CLIENT_ID` and `VK_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for VK SSO

- email
"""


class VKSSO:
    def __init__(
        self,
        access_token=None,
        user_id=None,
        email=None,
    ):
        self.access_token = access_token
        self.user_id = user_id
        self.email = email
        self.client_id = getenv("VK_CLIENT_ID")
        self.client_secret = getenv("VK_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        raise NotImplementedError("VK API does not use refresh tokens.")

    def get_user_info(self):
        uri = f"https://api.vk.com/method/users.get?user_ids={self.user_id}&fields=first_name,last_name&access_token={self.access_token}&v=5.131"
        response = requests.get(uri)
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Error getting user info from VK",
            )
        try:
            data = response.json()["response"][0]
            first_name = data["first_name"]
            last_name = data["last_name"]
            return {
                "email": self.email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error parsing user info from VK",
            )

    def send_email(self, to, subject, message_text):
        raise NotImplementedError("VK API does not support sending emails.")


def vk_sso(code, redirect_uri=None) -> VKSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    response = requests.get(
        "https://oauth.vk.com/access_token",
        params={
            "client_id": getenv("VK_CLIENT_ID"),
            "client_secret": getenv("VK_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting VK access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    user_id = data["user_id"]
    email = data.get("email", "Not provided")
    return VKSSO(access_token=access_token, user_id=user_id, email=email)
