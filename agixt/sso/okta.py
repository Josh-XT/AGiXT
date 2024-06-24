import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- OKTA_CLIENT_ID: Okta OAuth client ID
- OKTA_CLIENT_SECRET: Okta OAuth client secret
- OKTA_DOMAIN: Okta domain (e.g., dev-123456.okta.com)

Required scopes for Okta OAuth

- openid
- profile
- email
"""


class OktaSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("OKTA_CLIENT_ID")
        self.client_secret = getenv("OKTA_CLIENT_SECRET")
        self.domain = getenv("OKTA_DOMAIN")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            f"https://{self.domain}/oauth2/v1/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = f"https://{self.domain}/oauth2/v1/userinfo"
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
                detail="Error getting user info from Okta",
            )

    def send_email(self, to, subject, message_text):
        # Placeholder: Replace this with any specific email sending logic for Okta if available
        raise NotImplementedError("send_email is not supported for Okta")


def okta_sso(code, redirect_uri=None) -> OktaSSO:
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
        f"https://{getenv('OKTA_DOMAIN')}/oauth2/v1/token",
        data={
            "client_id": getenv("OKTA_CLIENT_ID"),
            "client_secret": getenv("OKTA_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Okta access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return OktaSSO(access_token=access_token, refresh_token=refresh_token)
