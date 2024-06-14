import base64
import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- FITBIT_CLIENT_ID: Fitbit OAuth client ID
- FITBIT_CLIENT_SECRET: Fitbit OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `FITBIT_CLIENT_ID` and `FITBIT_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Fitbit OAuth

- activity
- heartrate
- location
- nutrition
- profile
- settings
- sleep
- social
- weight
"""


class FitbitSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("FITBIT_CLIENT_ID")
        self.client_secret = getenv("FITBIT_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        decoded_token = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        response = requests.post(
            "https://api.fitbit.com/oauth2/token",
            headers={
                "Authorization": f"Basic {decoded_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
        )
        if response.status_code != 200:
            logging.error(f"Error refreshing Fitbit access token: {response.text}")
            raise HTTPException(
                status_code=403,
                detail="Error refreshing Fitbit access token",
            )
        tokens = response.json()
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens["refresh_token"]
        return self.access_token

    def get_user_info(self):
        uri = "https://api.fitbit.com/1/user/-/profile.json"
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
            first_name = data["user"]["firstName"]
            last_name = data["user"]["lastName"]
            email = data["user"][
                "fullName"
            ]  # Note: Fitbit may not provide email directly
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error fetching user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Fitbit",
            )

    def get_activities(self):
        uri = "https://api.fitbit.com/1/user/-/activities/date/today.json"
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
        if response.status_code != 200:
            logging.error(f"Error fetching user's activities: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail="Error fetching user's activities from Fitbit",
            )
        return response.json()


def fitbit_sso(code, redirect_uri=None) -> FitbitSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    token = base64.b64encode(
        f"{getenv('FITBIT_CLIENT_ID')}:{getenv('FITBIT_CLIENT_SECRET')}".encode()
    ).decode()
    response = requests.post(
        "https://api.fitbit.com/oauth2/token",
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "client_id": getenv("FITBIT_CLIENT_ID"),
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Fitbit access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return FitbitSSO(access_token=access_token, refresh_token=refresh_token)
