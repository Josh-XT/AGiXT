import json
import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- YAMMER_CLIENT_ID: Yammer OAuth client ID
- YAMMER_CLIENT_SECRET: Yammer OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `YAMMER_CLIENT_ID` and `YAMMER_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Yammer OAuth

- messages:email
- messages:post
"""


class YammerSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("YAMMER_CLIENT_ID")
        self.client_secret = getenv("YAMMER_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://www.yammer.com/oauth2/access_token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://www.yammer.com/api/v1/users/current.json"
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
            first_name = data["first_name"]
            last_name = data["last_name"]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Yammer",
            )

    def send_message(self, group_id, message_text):
        if not self.user_info.get("email"):
            user_info = self.get_user_info()
            self.email_address = user_info["email"]
        message_data = {
            "body": message_text,
            "group_id": group_id,
        }
        response = requests.post(
            "https://www.yammer.com/api/v1/messages.json",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(message_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://www.yammer.com/api/v1/messages.json",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(message_data),
            )
        return response.json()


def yammer_sso(code, redirect_uri=None) -> YammerSSO:
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
        f"https://www.yammer.com/oauth2/token",
        data={
            "client_id": getenv("YAMMER_CLIENT_ID"),
            "client_secret": getenv("YAMMER_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Yammer access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return YammerSSO(access_token=access_token, refresh_token=refresh_token)
