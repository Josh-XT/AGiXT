import requests
import json
import logging
import base64
import uuid
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- PAYPAL_CLIENT_ID: PayPal OAuth client ID
- PAYPAL_CLIENT_SECRET: PayPal OAuth client secret

Required APIs

Ensure you have PayPal REST API enabled and appropriate client credentials obtained.
Add the `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for PayPal OAuth:

- email
- openid
"""


class PayPalSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("PAYPAL_CLIENT_ID")
        self.client_secret = getenv("PAYPAL_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        token = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        response = requests.post(
            "https://api.paypal.com/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Error refreshing PayPal OAuth token",
            )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.paypal.com/v1/identity/oauth2/userinfo?schema=openid"
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
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from PayPal: {str(e)}",
            )

    def send_payment(self, recipient_email, amount, currency="USD"):
        """This is an extra method for sending payment in PayPal."""
        payment_data = {
            "sender_batch_header": {
                "sender_batch_id": "batch_" + str(uuid.uuid4()),
                "email_subject": "You have a payment",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "amount": {
                        "value": amount,
                        "currency": currency,
                    },
                    "receiver": recipient_email,
                    "note": "Thank you.",
                }
            ],
        }

        response = requests.post(
            "https://api.paypal.com/v1/payments/payouts",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payment_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://api.paypal.com/v1/payments/payouts",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(payment_data),
            )
        return response.json()


def paypal_sso(code, redirect_uri=None) -> PayPalSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    token = base64.b64encode(
        f"{getenv('PAYPAL_CLIENT_ID')}:{getenv('PAYPAL_CLIENT_SECRET')}".encode()
    ).decode()
    response = requests.post(
        "https://api.paypal.com/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting PayPal access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return PayPalSSO(access_token=access_token, refresh_token=refresh_token)
