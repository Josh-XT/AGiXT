import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- OPENAM_CLIENT_ID: OpenAM OAuth client ID
- OPENAM_CLIENT_SECRET: OpenAM OAuth client secret
- OPENAM_BASE_URL: Base URL for OpenAM server

Required scopes for OpenAM OAuth

- profile
- email
"""


class OpenAMSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("OPENAM_CLIENT_ID")
        self.client_secret = getenv("OPENAM_CLIENT_SECRET")
        self.base_url = getenv("OPENAM_BASE_URL")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            f"{self.base_url}/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = f"{self.base_url}/oauth2/userinfo"
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
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from OpenAM",
            )

    def send_email(self, to, subject, message_text):
        raise NotImplementedError(
            "OpenAM SSO does not support sending emails by default"
        )


def openam_sso(code, redirect_uri=None) -> OpenAMSSO:
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
        f"{getenv('OPENAM_BASE_URL')}/oauth2/token",
        data={
            "client_id": getenv("OPENAM_CLIENT_ID"),
            "client_secret": getenv("OPENAM_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting OpenAM access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return OpenAMSSO(access_token=access_token, refresh_token=refresh_token)
