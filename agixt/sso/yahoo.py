import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- YAHOO_CLIENT_ID: Yahoo OAuth client ID
- YAHOO_CLIENT_SECRET: Yahoo OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `YAHOO_CLIENT_ID` and `YAHOO_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Yahoo OAuth

- profile
- email
- mail-w
"""


class YahooSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("YAHOO_CLIENT_ID")
        self.client_secret = getenv("YAHOO_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://api.login.yahoo.com/oauth2/get_token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.login.yahoo.com/openid/v1/userinfo"
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
            first_name = data["given_name"]
            last_name = data["family_name"]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Yahoo",
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
        email_data = {"raw": raw}
        response = requests.post(
            "https://api.login.yahoo.com/ws/mail/v3/send",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(email_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://api.login.yahoo.com/ws/mail/v3/send",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(email_data),
            )
        return response.json()


def yahoo_sso(code, redirect_uri=None) -> YahooSSO:
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
        f"https://api.login.yahoo.com/oauth2/get_token",
        data={
            "client_id": getenv("YAHOO_CLIENT_ID"),
            "client_secret": getenv("YAHOO_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        logging.error(f"Error getting Yahoo access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return YahooSSO(access_token=access_token, refresh_token=refresh_token)
