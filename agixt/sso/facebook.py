import json
import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- FACEBOOK_CLIENT_ID: Facebook OAuth client ID
- FACEBOOK_CLIENT_SECRET: Facebook OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `FACEBOOK_CLIENT_ID` and `FACEBOOK_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Facebook OAuth

- public_profile
- email
- pages_messaging (for sending messages, if applicable)
"""


class FacebookSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("FACEBOOK_CLIENT_ID")
        self.client_secret = getenv("FACEBOOK_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.get(
            "https://graph.facebook.com/v10.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "fb_exchange_token": self.refresh_token,
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://graph.facebook.com/v10.0/me?fields=id,first_name,last_name,email"
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
                detail="Error getting user info from Facebook",
            )

    def send_message(self, to, message_text):
        """
        Sending messages through Facebook may require the pages_messaging permission
        and the user to be an admin of the page through which the message is sent.
        This example assumes those permissions and settings are in place.
        """
        uri = f"https://graph.facebook.com/v10.0/me/messages"
        message_data = {
            "recipient": {"id": to},
            "message": {"text": message_text},
        }
        response = requests.post(
            uri,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(message_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                uri,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(message_data),
            )
        return response.json()


def facebook_sso(code, redirect_uri=None) -> FacebookSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    response = requests.get(
        f"https://graph.facebook.com/v10.0/oauth/access_token",
        params={
            "client_id": getenv("FACEBOOK_CLIENT_ID"),
            "client_secret": getenv("FACEBOOK_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Facebook access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = (
        access_token  # For simplicity, assigning access_token to refresh_token
    )
    return FacebookSSO(access_token=access_token, refresh_token=refresh_token)
