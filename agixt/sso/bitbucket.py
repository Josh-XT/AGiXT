import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- BITBUCKET_CLIENT_ID: Bitbucket OAuth client ID
- BITBUCKET_CLIENT_SECRET: Bitbucket OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `BITBUCKET_CLIENT_ID` and `BITBUCKET_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Bitbucket SSO

- account
- email
"""


class BitbucketSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("BITBUCKET_CLIENT_ID")
        self.client_secret = getenv("BITBUCKET_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://bitbucket.org/site/oauth2/access_token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            auth=(self.client_id, self.client_secret),
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Error refreshing Bitbucket access token",
            )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.bitbucket.org/2.0/user"
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
            user_data = response.json()
            email_response = requests.get(
                "https://api.bitbucket.org/2.0/user/emails",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            email_data = email_response.json()
            email = next(
                email["email"] for email in email_data["values"] if email["is_primary"]
            )
            first_name = user_data.get("display_name", "").split()[0]
            last_name = " ".join(user_data.get("display_name", "").split()[1:])
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error getting Bitbucket user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Bitbucket",
            )


def bitbucket_sso(code, redirect_uri=None) -> BitbucketSSO:
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
        "https://bitbucket.org/site/oauth2/access_token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(getenv("BITBUCKET_CLIENT_ID"), getenv("BITBUCKET_CLIENT_SECRET")),
    )
    if response.status_code != 200:
        logging.error(f"Error getting Bitbucket access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return BitbucketSSO(access_token=access_token, refresh_token=refresh_token)
