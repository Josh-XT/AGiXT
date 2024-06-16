import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- ZENDESK_CLIENT_ID: Zendesk OAuth client ID
- ZENDESK_CLIENT_SECRET: Zendesk OAuth client secret
- ZENDESK_SUBDOMAIN: Your Zendesk subdomain

Required APIs

Ensure you have the necessary APIs enabled, then add the `ZENDESK_CLIENT_ID`, `ZENDESK_CLIENT_SECRET`, and `ZENDESK_SUBDOMAIN` environment variables to your `.env` file.

Required scopes for Zendesk OAuth

- read
- write
"""


class ZendeskSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("ZENDESK_CLIENT_ID")
        self.client_secret = getenv("ZENDESK_CLIENT_SECRET")
        self.subdomain = getenv("ZENDESK_SUBDOMAIN")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            f"https://{self.subdomain}.zendesk.com/oauth/tokens",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = f"https://{self.subdomain}.zendesk.com/api/v2/users/me.json"
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
            data = response.json()["user"]
            first_name, last_name = data["name"].split(" ", 1)
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Zendesk",
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
            "request": {
                "subject": subject,
                "comment": {"body": message_text},
                "requester": {
                    "name": f"{self.user_info['first_name']} {self.user_info['last_name']}",
                    "email": self.user_info["email"],
                },
                "email_ccs": [
                    {
                        "user_email": to,
                    }
                ],
            }
        }

        response = requests.post(
            f"https://{self.subdomain}.zendesk.com/api/v2/requests.json",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(email_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                f"https://{self.subdomain}.zendesk.com/api/v2/requests.json",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(email_data),
            )
        return response.json()


def zendesk_sso(code, redirect_uri=None) -> ZendeskSSO:
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
        f"https://{getenv('ZENDESK_SUBDOMAIN')}.zendesk.com/oauth/tokens",
        data={
            "client_id": getenv("ZENDESK_CLIENT_ID"),
            "client_secret": getenv("ZENDESK_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Zendesk access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return ZendeskSSO(access_token=access_token, refresh_token=refresh_token)
