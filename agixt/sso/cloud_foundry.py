import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- CF_CLIENT_ID: Cloud Foundry OAuth client ID
- CF_CLIENT_SECRET: Cloud Foundry OAuth client secret

Required APIs and Scopes:

- Cloud Foundry API (CF API)
- User Info API
"""


class CloudFoundrySSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("CF_CLIENT_ID")
        self.client_secret = getenv("CF_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://login.system.example.com/oauth/token",  # Update with your CF OAuth token URL
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://uaa.system.example.com/userinfo"  # Update with your CF User Info URL
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
                detail="Error getting user info from Cloud Foundry",
            )

    def send_email(self, to, subject, message_text):
        # Assuming you have a CF service for sending emails; use relevant API
        # This part is highly dependent on what services you use in Cloud Foundry
        raise NotImplementedError(
            "Email sending not supported for Cloud Foundry SSO yet."
        )


def cloud_foundry_sso(code, redirect_uri=None) -> CloudFoundrySSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3A", ":")
        .replace("%3F", "?")
    )
    response = requests.post(
        "https://login.system.example.com/oauth/token",  # Update with your CF OAuth token URL
        data={
            "client_id": getenv("CF_CLIENT_ID"),
            "client_secret": getenv("CF_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Cloud Foundry access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return CloudFoundrySSO(access_token=access_token, refresh_token=refresh_token)
