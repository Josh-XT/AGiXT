import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- FOURSQUARE_CLIENT_ID: Foursquare OAuth client ID
- FOURSQUARE_CLIENT_SECRET: Foursquare OAuth client secret

Required APIs:

- Follow the links to confirm that you have the APIs enabled,
  then add the `FOURSQUARE_CLIENT_ID` and `FOURSQUARE_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Foursquare OAuth:

- No specific scope is needed for basic user info, as Foursquare uses a userless access approach for its APIs.
"""


class FoursquareSSO:
    def __init__(
        self,
        access_token=None,
    ):
        self.access_token = access_token
        self.client_id = getenv("FOURSQUARE_CLIENT_ID")
        self.client_secret = getenv("FOURSQUARE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self, existing_refresh_token):
        # Foursquare does not use a refresh token mechanism, re-authentication might be needed
        raise NotImplementedError(
            "Foursquare does not implement a refresh token mechanism"
        )

    def get_user_info(self):
        uri = "https://api.foursquare.com/v2/users/self"
        response = requests.get(
            uri,
            params={
                "oauth_token": self.access_token,
                "v": "20230410",  # Versioning date that Foursquare expects, can be current date
            },
        )
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized, please re-authenticate",
            )
        try:
            data = response.json()
            user = data["response"]["user"]
            first_name = user["firstName"]
            last_name = user.get("lastName", "")  # lastName may be optional
            email = user["contact"]["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Foursquare",
            )


def foursquare_sso(code, redirect_uri=None) -> FoursquareSSO:
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
        f"https://foursquare.com/oauth2/access_token",
        params={
            "client_id": getenv("FOURSQUARE_CLIENT_ID"),
            "client_secret": getenv("FOURSQUARE_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Foursquare access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    return FoursquareSSO(access_token=access_token)
