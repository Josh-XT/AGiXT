import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- JIVE_CLIENT_ID: Jive OAuth client ID
- JIVE_CLIENT_SECRET: Jive OAuth client secret

Required APIs:

Ensure you have the necessary Jive API enabled.

Required scopes for Jive OAuth:
These scopes will need to be accurate according to Jive�s API documentation.

"""


class JiveSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("JIVE_CLIENT_ID")
        self.client_secret = getenv("JIVE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://example.jive.com/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": "your_required_scopes_here",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://example.jive.com/api/core/v3/people/@me"
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
            first_name = data["name"]["givenName"]
            last_name = data["name"]["familyName"]
            email = data["emails"][0]["value"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Jive",
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
            "https://example.jive.com/api/core/v3/messages",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(email_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://example.jive.com/api/core/v3/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(email_data),
            )
        return response.json()


def jive_sso(code, redirect_uri=None) -> JiveSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    code = str(code).replace("%2F", "/").replace("%3D", "=").replace("%3F", "?")
    response = requests.post(
        "https://example.jive.com/oauth2/token",
        data={
            "client_id": getenv("JIVE_CLIENT_ID"),
            "client_secret": getenv("JIVE_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": "your_required_scopes_here",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Jive access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return JiveSSO(access_token=access_token, refresh_token=refresh_token)
