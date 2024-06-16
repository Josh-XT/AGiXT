import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- YELP_CLIENT_ID: Yelp OAuth client ID
- YELP_CLIENT_SECRET: Yelp OAuth client secret

Required APIs

Ensure you have registered your app with Yelp and obtained the CLIENT_ID and CLIENT_SECRET.

Required scopes for Yelp OAuth

- business 
"""


class YelpSSO:
    def __init__(self, access_token=None, refresh_token=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("YELP_CLIENT_ID")
        self.client_secret = getenv("YELP_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://api.yelp.com/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response_data = response.json()
        if response.status_code != 200:
            logging.error(f"Error refreshing Yelp access token: {response_data}")
            raise HTTPException(
                status_code=response.status_code,
                detail="Error refreshing Yelp access token.",
            )
        return response_data["access_token"]

    def get_user_info(self):
        uri = "https://api.yelp.com/v3/users/self"
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
            first_name = data["first_name"]
            last_name = data["last_name"]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Yelp",
            )

    def send_email(self, to, subject, message_text):
        raise NotImplementedError("Yelp API does not support sending emails directly.")


def yelp_sso(code, redirect_uri=None) -> YelpSSO:
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
        f"https://api.yelp.com/oauth2/token",
        data={
            "client_id": getenv("YELP_CLIENT_ID"),
            "client_secret": getenv("YELP_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Yelp access token: {response.text}")
        raise HTTPException(
            status_code=response.status_code, detail="Error getting Yelp access token."
        )
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return YelpSSO(access_token=access_token, refresh_token=refresh_token)
