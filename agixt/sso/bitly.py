import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- BITLY_CLIENT_ID: Bitly OAuth client ID
- BITLY_CLIENT_SECRET: Bitly OAuth client secret
- BITLY_ACCESS_TOKEN: Bitly access token (you can obtain it via OAuth or from the Bitly account settings)

Required scopes for Bitly OAuth

- `bitly:read`, `bitly:write`
"""


class Bitly:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token or getenv("BITLY_ACCESS_TOKEN")
        self.client_id = getenv("BITLY_CLIENT_ID")
        self.client_secret = getenv("BITLY_CLIENT_SECRET")

    def get_new_token(self):
        response = requests.post(
            "https://api-ssl.bitly.com/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code != 200:
            logging.error(f"Error refreshing Bitly token: {response.text}")
            raise HTTPException(status_code=400, detail="Error refreshing Bitly token")
        return response.json()["access_token"]

    def shorten_url(self, long_url):
        uri = "https://api-ssl.bitly.com/v4/shorten"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        data = {
            "long_url": long_url,
        }
        response = requests.post(uri, headers=headers, json=data)
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
            response = requests.post(uri, headers=headers, json=data)

        if response.status_code != 200:
            logging.error(f"Error shortening URL with Bitly: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail="Error shortening URL with Bitly",
            )
        return response.json()["link"]


def bitly_sso(code, redirect_uri=None) -> Bitly:
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
        "https://bit.ly/oauth/access_token",
        data={
            "client_id": getenv("BITLY_CLIENT_ID"),
            "client_secret": getenv("BITLY_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Bitly access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else None
    return Bitly(access_token=access_token, refresh_token=refresh_token)
