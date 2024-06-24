import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- APPLE_CLIENT_ID: Apple OAuth client ID
- APPLE_CLIENT_SECRET: Apple OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `APPLE_CLIENT_ID` and `APPLE_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Apple SSO

- name
- email
"""


class AppleSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("APPLE_CLIENT_ID")
        self.client_secret = getenv("APPLE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://appleid.apple.com/auth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        # Apple SSO does not have a straightforward URI to get user info post authentication like Google/Microsoft.
        # User info should be captured during the initial token exchange.
        try:
            # Placeholder: Requires custom logic to handle user info retrieval from the initial login response.
            # Capture name and email from initial response or authenticate/authorize endpoint.
            first_name = "First"  # replace with actual logic
            last_name = "Last"  # replace with actual logic
            email = "email@example.com"  # replace with actual logic
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Apple",
            )

    def send_email(self, to, subject, message_text):
        # Note: Apple does not provide an email sending service in their APIs.
        # Placeholder: Functionality should be implemented using SMTP or another email service.
        raise NotImplementedError(
            "Apple OAuth does not support sending emails directly via API"
        )


def apple_sso(code, redirect_uri=None) -> AppleSSO:
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
        "https://appleid.apple.com/auth/token",
        data={
            "client_id": getenv("APPLE_CLIENT_ID"),
            "client_secret": getenv("APPLE_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Apple access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return AppleSSO(access_token=access_token, refresh_token=refresh_token)
