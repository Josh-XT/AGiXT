import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- ORCID_CLIENT_ID: ORCID OAuth client ID
- ORCID_CLIENT_SECRET: ORCID OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `ORCID_CLIENT_ID` and `ORCID_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for ORCID SSO

- /authenticate (to read public profile information)
- /activities/update (optional, if you need to update activities)
"""


class ORCIDSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("ORCID_CLIENT_ID")
        self.client_secret = getenv("ORCID_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://orcid.org/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://pub.orcid.org/v3.0/0000-0002-1825-0097"  # Replace with actual ORCID ID endpoint after fetching authenticated ORCID ID
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
            first_name = data["person"]["name"]["given-names"]["value"]
            last_name = data["person"]["name"]["family-name"]["value"]
            email = (
                data["person"]["emails"]["email"][0]["email"]
                if data["person"]["emails"]["email"]
                else None
            )
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error getting user info from ORCID: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from ORCID",
            )


def orcid_sso(code, redirect_uri=None) -> ORCIDSSO:
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
        "https://orcid.org/oauth/token",
        data={
            "client_id": getenv("ORCID_CLIENT_ID"),
            "client_secret": getenv("ORCID_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting ORCID access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return ORCIDSSO(access_token=access_token, refresh_token=refresh_token)
