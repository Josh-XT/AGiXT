import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- DEVIANTART_CLIENT_ID: deviantART OAuth client ID
- DEVIANTART_CLIENT_SECRET: deviantART OAuth client secret

Required OAuth scopes for deviantART

- user
- browse
- stash
- send_message
"""


class DeviantArtSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("DEVIANTART_CLIENT_ID")
        self.client_secret = getenv("DEVIANTART_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://www.deviantart.com/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://www.deviantart.com/api/v1/oauth2/user/whoami"
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
            first_name = data.get("username", "Unknown")
            last_name = ""
            email = data.get(
                "usericon", "Unknown"
            )  # deviantART doesn't provide email, using user icon as unique identifier.
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from deviantART",
            )

    def send_message(self, to, subject, message_text):
        if not self.user_info.get("email"):
            user_info = self.get_user_info()
            self.email_address = user_info["email"]
        message = MIMEText(message_text)
        message["to"] = to
        message["from"] = self.email_address
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes())
        raw = raw.decode()
        message_data = {
            "subject": subject,
            "body": message_text,
        }
        response = requests.post(
            "https://www.deviantart.com/api/v1/oauth2/user/notes/send",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(message_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://www.deviantart.com/api/v1/oauth2/user/notes/send",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(message_data),
            )
        return response.json()


def deviantart_sso(code, redirect_uri=None) -> DeviantArtSSO:
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
        "https://www.deviantart.com/oauth2/token",
        data={
            "client_id": getenv("DEVIANTART_CLIENT_ID"),
            "client_secret": getenv("DEVIANTART_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting deviantART access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return DeviantArtSSO(access_token=access_token, refresh_token=refresh_token)
