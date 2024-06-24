import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- AUTODESK_CLIENT_ID: Autodesk OAuth client ID
- AUTODESK_CLIENT_SECRET: Autodesk OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `AUTODESK_CLIENT_ID` and `AUTODESK_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Autodesk OAuth

- data:read
- data:write
- bucket:read
- bucket:create
"""


class AutodeskSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("AUTODESK_CLIENT_ID")
        self.client_secret = getenv("AUTODESK_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://developer.api.autodesk.com/authentication/v1/refreshtoken",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://developer.api.autodesk.com/userprofile/v1/users/@me"
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
            email = data["emailId"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Autodesk",
            )

    def send_email(self, to, subject, message_text):
        raise NotImplementedError(
            "Autodesk API does not support sending emails via OAuth tokens"
        )

        if not self.email_address:
            user_info = self.get_user_info()
            self.email_address = user_info["email"]
        message = MIMEText(message_text)
        message["to"] = to
        message["from"] = self.email_address
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes())
        raw = raw.decode()
        message = {"raw": raw}
        response = requests.post(
            "https://developer.api.autodesk.com/email/v1/send",  # Placeholder URL
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(message),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://developer.api.autodesk.com/email/v1/send",  # Placeholder URL
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(message),
            )
        return response.json()


def autodesk_sso(code, redirect_uri=None) -> AutodeskSSO:
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
        f"https://developer.api.autodesk.com/authentication/v1/gettoken",
        data={
            "client_id": getenv("AUTODESK_CLIENT_ID"),
            "client_secret": getenv("AUTODESK_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Autodesk access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return AutodeskSSO(access_token=access_token, refresh_token=refresh_token)
