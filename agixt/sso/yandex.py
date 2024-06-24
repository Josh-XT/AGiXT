import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- YANDEX_CLIENT_ID: Yandex OAuth client ID
- YANDEX_CLIENT_SECRET: Yandex OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `YANDEX_CLIENT_ID` and `YANDEX_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Yandex OAuth

- login:info
- login:email
- mail.send
"""


class YandexSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("YANDEX_CLIENT_ID")
        self.client_secret = getenv("YANDEX_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://oauth.yandex.com/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://login.yandex.ru/info"
        response = requests.get(
            uri,
            headers={"Authorization": f"OAuth {self.access_token}"},
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"OAuth {self.access_token}"},
            )
        try:
            data = response.json()
            first_name = data.get("first_name")
            last_name = data.get("last_name")
            email = data.get("default_email", data.get("emails", [None])[0])
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Yandex",
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
            "to": to,
            "subject": subject,
            "text": message_text,
        }
        response = requests.post(
            "https://smtp.yandex.ru/send",
            headers={
                "Authorization": f"OAuth {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(email_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://smtp.yandex.ru/send",
                headers={
                    "Authorization": f"OAuth {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(email_data),
            )
        return response.json()


def yandex_sso(code, redirect_uri=None) -> YandexSSO:
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
        f"https://oauth.yandex.com/token",
        data={
            "code": code,
            "client_id": getenv("YANDEX_CLIENT_ID"),
            "client_secret": getenv("YANDEX_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Yandex access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "Not provided")
    return YandexSSO(access_token=access_token, refresh_token=refresh_token)
