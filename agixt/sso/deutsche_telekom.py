import base64
import json
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- DEUTSCHE_TELKOM_CLIENT_ID: Deutsche Telekom OAuth client ID
- DEUTSCHE_TELKOM_CLIENT_SECRET: Deutsche Telekom OAuth client secret

Required APIs:

- https://www.deutschetelekom.com/ldap-sso

Required scopes for Deutsche Telekom SSO:

- t-online-profile --> Access to profile data
- t-online-email --> Access to email services
"""


class DeutscheTelekomSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("DEUTSCHE_TELKOM_CLIENT_ID")
        self.client_secret = getenv("DEUTSCHE_TELKOM_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://www.telekom.com/ssoservice/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": "t-online-profile t-online-email",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://www.telekom.com/ssoservice/me"
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
                detail="Error getting user info from Deutsche Telekom",
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
            "https://www.telekom.com/ssoservice/sendMail",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(email_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://www.telekom.com/ssoservice/sendMail",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(email_data),
            )
        return response.json()


def deutsche_telekom_sso(code, redirect_uri=None) -> DeutscheTelekomSSO:
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
        f"https://www.telekom.com/ssoservice/token",
        data={
            "client_id": getenv("DEUTSCHE_TELKOM_CLIENT_ID"),
            "client_secret": getenv("DEUTSCHE_TELKOM_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": "t-online-profile t-online-email",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Deutsche Telekom access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return DeutscheTelekomSSO(access_token=access_token, refresh_token=refresh_token)
