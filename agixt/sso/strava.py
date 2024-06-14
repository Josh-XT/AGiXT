import json
import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- STRAVA_CLIENT_ID: Strava OAuth client ID
- STRAVA_CLIENT_SECRET: Strava OAuth client secret

Required APIs 

No additional APIs need to be enabled beyond the standard Strava API settings.

Required scopes for Strava OAuth

- read
- activity:write
"""


class StravaSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("STRAVA_CLIENT_ID")
        self.client_secret = getenv("STRAVA_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://www.strava.com/api/v3/athlete"
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
            first_name = data["firstname"]
            last_name = data["lastname"]
            email = data.get("email")  # Strava API doesn't return email by default
            return {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,  # Might be None if not provided
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Strava",
            )

    def create_activity(
        self, name, activity_type, start_date, elapsed_time, description=None
    ):
        """Create an activity on Strava.

        :param name: The name of the activity.
        :param activity_type: Type of activity (e.g., "Run", "Ride").
        :param start_date: ISO 8601 formatted date-time when the activity took place.
        :param elapsed_time: Activity duration in seconds.
        :param description: Description of the activity.
        """
        if not self.user_info.get("email"):
            user_info = self.get_user_info()
            self.email_address = user_info["email"]

        activity_data = {
            "name": name,
            "type": activity_type,
            "start_date_local": start_date,
            "elapsed_time": elapsed_time,
        }

        if description:
            activity_data["description"] = description

        response = requests.post(
            "https://www.strava.com/api/v3/activities",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(activity_data),
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.post(
                "https://www.strava.com/api/v3/activities",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(activity_data),
            )
        return response.json()


def strava_sso(code, redirect_uri=None) -> StravaSSO:
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
        "https://www.strava.com/oauth/token",
        data={
            "client_id": getenv("STRAVA_CLIENT_ID"),
            "client_secret": getenv("STRAVA_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Strava access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return StravaSSO(access_token=access_token, refresh_token=refresh_token)
