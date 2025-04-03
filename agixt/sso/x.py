import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- X_CLIENT_ID: X OAuth client ID
- X_CLIENT_SECRET: X OAuth client secret

Required scopes for Twitter OAuth:
"""

SCOPES = [
    "tweet.read",
    "tweet.write",
    "users.read",
    "offline.access",
    "like.read",
    "like.write",
    "follows.read",
    "follows.write",
    "dm.read",
    "dm.write",
]
AUTHORIZE = "https://x.com/i/oauth2/authorize"
PKCE_REQUIRED = True


class XSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("X_CLIENT_ID")
        self.client_secret = getenv("X_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://api.x.com/2/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(SCOPES),
            },
        )
        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.x.com/2/users/me?user.fields=name,username,profile_image_url"
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
            user_data = data["data"]
            full_name = user_data["name"]
            name_parts = full_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            username = user_data["username"]
            return {
                "email": username,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error parsing X user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from X",
            )


def sso(code, redirect_uri=None, code_verifier=None) -> XSSO:
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )
    client_id = getenv("X_CLIENT_ID")
    client_secret = getenv("X_CLIENT_SECRET")
    response = requests.post(
        "https://api.x.com/2/oauth2/token",
        data={
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        },
        auth=(client_id, client_secret),
    )
    if response.status_code != 200:
        logging.error(f"Error getting X access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else None
    return XSSO(access_token=access_token, refresh_token=refresh_token)
