import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- WITHINGS_CLIENT_ID: Withings OAuth client ID
- WITHINGS_CLIENT_SECRET: Withings OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `WITHINGS_CLIENT_ID` and `WITHINGS_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Withings SSO

- user.info
- user.metrics
- user.activity
"""


class WithingsSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("WITHINGS_CLIENT_ID")
        self.client_secret = getenv("WITHINGS_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://wbsapi.withings.net/v2/oauth2",
            data={
                "action": "requesttoken",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
        )
        data = response.json()["body"]
        return data["access_token"]

    def get_user_info(self):
        uri = "https://wbsapi.withings.net/v2/user"
        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
            params={"action": "getdevice"},
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"action": "getdevice"},
            )
        try:
            data = response.json()["body"]["devices"][0]
            first_name = data.get("firstname", "")
            last_name = data.get("lastname", "")
            email = data.get("email", "")
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Withings",
            )

    def send_email(self, to, subject, message_text):
        raise HTTPException(
            status_code=501, detail="Withings API does not support sending email"
        )


def withings_sso(code, redirect_uri=None) -> WithingsSSO:
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
        f"https://wbsapi.withings.net/v2/oauth2",
        data={
            "action": "requesttoken",
            "client_id": getenv("WITHINGS_CLIENT_ID"),
            "client_secret": getenv("WITHINGS_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Withings access token: {response.text}")
        return None, None
    data = response.json()["body"]
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return WithingsSSO(access_token=access_token, refresh_token=refresh_token)
