import base64
import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- IMGUR_CLIENT_ID: Imgur OAuth client ID
- IMGUR_CLIENT_SECRET: Imgur OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `IMGUR_CLIENT_ID` and `IMGUR_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Imgur SSO

- read
- write
"""


class ImgurSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("IMGUR_CLIENT_ID")
        self.client_secret = getenv("IMGUR_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://api.imgur.com/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        data = response.json()
        if response.status_code != 200:
            logging.error(f"Error refreshing Imgur access token: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail="Error refreshing Imgur access token",
            )
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        return self.access_token

    def get_user_info(self):
        uri = "https://api.imgur.com/3/account/me"
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
            data = response.json()["data"]
            username = data["url"]
            email = data["email"] if "email" in data else None
            return {
                "username": username,
                "email": email,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Imgur",
            )

    def upload_image(self, image_path, title=None, description=None):
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode()
        payload = {
            "image": image_data,
            "type": "base64",
        }
        if title:
            payload["title"] = title
        if description:
            payload["description"] = description
        response = requests.post(
            "https://api.imgur.com/3/image",
            headers={
                "Authorization": f"Bearer {self.access_token}",
            },
            data=payload,
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://api.imgur.com/3/image",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                },
                data=payload,
            )
        return response.json()


def imgur_sso(code, redirect_uri=None) -> ImgurSSO:
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
        "https://api.imgur.com/oauth2/token",
        data={
            "client_id": getenv("IMGUR_CLIENT_ID"),
            "client_secret": getenv("IMGUR_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Imgur access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return ImgurSSO(access_token=access_token, refresh_token=refresh_token)
