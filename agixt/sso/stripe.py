import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- STRIPE_CLIENT_ID: Stripe OAuth client ID
- STRIPE_CLIENT_SECRET: Stripe OAuth client secret

Required scopes for Stripe SSO

- read_write
"""


class StripeSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("STRIPE_CLIENT_ID")
        self.client_secret = getenv("STRIPE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://connect.stripe.com/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.stripe.com/v1/account"
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
            email = data["email"]
            business_name = data["business_name"]
            return {
                "email": email,
                "business_name": business_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Stripe",
            )

    def send_email(self, to, subject, message_text):
        raise NotImplementedError("Stripe does not support sending email directly.")


def stripe_sso(code, redirect_uri=None) -> StripeSSO:
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
        "https://connect.stripe.com/oauth/token",
        data={
            "client_id": getenv("STRIPE_CLIENT_ID"),
            "client_secret": getenv("STRIPE_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Stripe access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return StripeSSO(access_token=access_token, refresh_token=refresh_token)
