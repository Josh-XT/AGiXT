import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- CLEAR_SCORE_CLIENT_ID: ClearScore OAuth client ID
- CLEAR_SCORE_CLIENT_SECRET: ClearScore OAuth client secret

Required APIs

Add the `CLEAR_SCORE_CLIENT_ID` and `CLEAR_SCORE_CLIENT_SECRET` environment variables to your `.env` file.

Assumed Required scopes for ClearScore OAuth and email capabilities:

- user.info.read
- email.send
"""


class ClearScoreSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("CLEAR_SCORE_CLIENT_ID")
        self.client_secret = getenv("CLEAR_SCORE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://auth.clearscore.com/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": "user.info.read email.send",
            },
        )
        if response.status_code != 200:
            logging.error(f"Error refreshing ClearScore access token: {response.text}")
            raise HTTPException(
                status_code=400,
                detail="Error refreshing ClearScore access token",
            )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.clearscore.com/v1/me"
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
                detail="Error getting user info from ClearScore",
            )

    def send_email(self, to, subject, message_text):
        if not self.user_info.get("email"):
            self.user_info = self.get_user_info()
        email_address = self.user_info["email"]
        message = MIMEText(message_text)
        message["to"] = to
        message["from"] = email_address
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
            "https://api.clearscore.com/v1/me/sendMail",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(email_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://api.clearscore.com/v1/me/sendMail",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(email_data),
            )
        if response.status_code != 202:
            logging.error(f"Error sending email: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail="Error sending email",
            )
        return response.json()


def clearscore_sso(code, redirect_uri=None) -> ClearScoreSSO:
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
        "https://auth.clearscore.com/oauth2/token",
        data={
            "code": code,
            "client_id": getenv("CLEAR_SCORE_CLIENT_ID"),
            "client_secret": getenv("CLEAR_SCORE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "user.info.read email.send",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting ClearScore access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return ClearScoreSSO(access_token=access_token, refresh_token=refresh_token)
