import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- XERO_CLIENT_ID: Xero OAuth client ID
- XERO_CLIENT_SECRET: Xero OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `XERO_CLIENT_ID` and `XERO_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Xero OAuth

- openid
- profile
- email
- offline_access
"""


class XeroSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("XERO_CLIENT_ID")
        self.client_secret = getenv("XERO_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://identity.xero.com/connect/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code != 200:
            logging.error(f"Error refreshing Xero token: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail="Unable to refresh token from Xero",
            )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.xero.com/connections"
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
            data = response.json()[0]  # Assuming you want the first connection info
            first_name = data.get("name", "").split()[0]
            last_name = " ".join(data.get("name", "").split()[1:])
            email = data.get("email", "")
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as exc:
            logging.error(f"Error parsing user info from Xero: {exc}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Xero",
            )

    def send_email(self, to, subject, message_text):
        # Xero does not provide an email sending service.
        raise NotImplementedError("Xero does not support sending emails via API.")


def xero_sso(code, redirect_uri=None) -> XeroSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    response = requests.post(
        "https://identity.xero.com/connect/token",
        data={
            "client_id": getenv("XERO_CLIENT_ID"),
            "client_secret": getenv("XERO_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        logging.error(f"Error getting Xero access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return XeroSSO(access_token=access_token, refresh_token=refresh_token)
