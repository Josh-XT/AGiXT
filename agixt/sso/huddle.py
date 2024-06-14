import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- HUDDLE_CLIENT_ID: Huddle OAuth client ID
- HUDDLE_CLIENT_SECRET: Huddle OAuth client secret

Required APIs

Ensure the necessary Huddle APIs are enabled,
then add the `HUDDLE_CLIENT_ID` and `HUDDLE_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Huddle OAuth

- user_info
- send_email
"""


class HuddleSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("HUDDLE_CLIENT_ID")
        self.client_secret = getenv("HUDDLE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://login.huddle.com/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": "user_info send_email",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.huddle.com/1.0/user_info"
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
            first_name = data["firstName"]
            last_name = data["lastName"]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Huddle",
            )

    def send_email(self, to, subject, message_text):
        if not self.user_info.get("email"):
            user_info = self.get_user_info()
            self.email_address = user_info["email"]
        message = MIMEText(message_text)
        message["to"] = to
        message["from"] = self.email_address
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes())
        raw = raw.decode()
        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": message_text,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to,
                        }
                    }
                ],
            },
            "saveToSentItems": "true",
        }
        response = requests.post(
            "https://api.huddle.com/1.0/send_email",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(email_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://api.huddle.com/1.0/send_email",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(email_data),
            )
        return response.json()


def huddle_sso(code, redirect_uri=None) -> HuddleSSO:
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
        f"https://login.huddle.com/oauth2/token",
        data={
            "client_id": getenv("HUDDLE_CLIENT_ID"),
            "client_secret": getenv("HUDDLE_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": "user_info send_email",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Huddle access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return HuddleSSO(access_token=access_token, refresh_token=refresh_token)
