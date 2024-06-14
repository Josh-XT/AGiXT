import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- BATTLENET_CLIENT_ID: Battle.net OAuth client ID
- BATTLENET_CLIENT_SECRET: Battle.net OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `BATTLENET_CLIENT_ID` and `BATTLENET_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Battle.net OAuth

- openid
- email
"""


class BattleNetSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("BATTLENET_CLIENT_ID")
        self.client_secret = getenv("BATTLENET_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://oauth.battle.net/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = f"https://oauth.battle.net/oauth/userinfo"
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
            battletag = data["battletag"]
            email = data["email"]
            return {
                "email": email,
                "battletag": battletag,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Battle.net",
            )


def battlenet_sso(code, redirect_uri=None) -> BattleNetSSO:
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
        f"https://oauth.battle.net/token",
        data={
            "client_id": getenv("BATTLENET_CLIENT_ID"),
            "client_secret": getenv("BATTLENET_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Battle.net access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return BattleNetSSO(access_token=access_token, refresh_token=refresh_token)
