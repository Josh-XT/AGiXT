import requests
import logging
from fastapi import HTTPException
from Globals import getenv
import xml.etree.ElementTree as ET

"""
Required environment variables:

- OSM_CLIENT_ID: OpenStreetMap OAuth client ID
- OSM_CLIENT_SECRET: OpenStreetMap OAuth client secret

Required APIs

Make sure you have appropriate OAuth configuration in OpenStreetMap and add the `OSM_CLIENT_ID` and `OSM_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for OpenStreetMap OAuth:

- read_prefs
"""


class OpenStreetMapSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("OSM_CLIENT_ID")
        self.client_secret = getenv("OSM_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://www.openstreetmap.org/oauth/access_token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.openstreetmap.org/api/0.6/user/details"
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
            data = ET.fromstring(response.content)
            user_info = data.find("user")
            if user_info is None:
                raise HTTPException(
                    status_code=400,
                    detail="Error getting user info from OpenStreetMap",
                )
            user = {
                "id": user_info.attrib.get("id"),
                "username": user_info.attrib.get("display_name"),
            }
            return user
        except:
            raise HTTPException(
                status_code=400,
                detail="Error parsing user info from OpenStreetMap",
            )


def openstreetmap_sso(code, redirect_uri=None) -> OpenStreetMapSSO:
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
        f"https://www.openstreetmap.org/oauth/access_token",
        data={
            "client_id": getenv("OSM_CLIENT_ID"),
            "client_secret": getenv("OSM_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting OpenStreetMap access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return OpenStreetMapSSO(access_token=access_token, refresh_token=refresh_token)
