import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- XING_CLIENT_ID: XING OAuth client ID
- XING_CLIENT_SECRET: XING OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `XING_CLIENT_ID` and `XING_CLIENT_SECRET` environment variables to your `.env` file.

- Xing API https://dev.xing.com/

Required scopes for XING SSO

- https://api.xing.com/v1/users/me
- https://api.xing.com/v1/authorize
"""


class XingSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("XING_CLIENT_ID")
        self.client_secret = getenv("XING_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://api.xing.com/v1/oauth/token",
            auth=(self.client_id, self.client_secret),
            data={
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.xing.com/v1/users/me"
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
            user_profile = data["users"][0]
            first_name = user_profile["first_name"]
            last_name = user_profile["last_name"]
            email = user_profile["active_email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from XING",
            )

    def send_email(self, to, subject, message_text):
        if not self.email_address:
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
            "https://api.xing.com/v1/messages",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(email_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://api.xing.com/v1/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(email_data),
            )
        return response.json()


def xing_sso(code, redirect_uri=None) -> XingSSO:
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
        f"https://api.xing.com/v1/oauth/token",
        data={
            "client_id": getenv("XING_CLIENT_ID"),
            "client_secret": getenv("XING_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": "https://api.xing.com/v1/users/me https://api.xing.com/v1/messages",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting XING access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "Not provided")
    return XingSSO(access_token=access_token, refresh_token=refresh_token)
