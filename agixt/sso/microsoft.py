import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- MICROSOFT_CLIENT_ID: Microsoft OAuth client ID
- MICROSOFT_CLIENT_SECRET: Microsoft OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Microsoft OAuth

- offline_access
- https://graph.microsoft.com/User.Read
- https://graph.microsoft.com/Mail.Send
- https://graph.microsoft.com/Calendars.ReadWrite.Shared
- https://graph.microsoft.com/Calendars.ReadWrite

"""
SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Calendars.ReadWrite.Shared",
    "https://graph.microsoft.com/Calendars.ReadWrite",
]
AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
PKCE_REQUIRED = False


class MicrosoftSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(SCOPES),
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://graph.microsoft.com/v1.0/me"
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
            first_name = data["givenName"]
            last_name = data["surname"]
            email = data["mail"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Microsoft",
            )


def sso(code, redirect_uri=None) -> MicrosoftSSO:
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )
    response = requests.post(
        f"https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": getenv("MICROSOFT_CLIENT_ID"),
            "client_secret": getenv("MICROSOFT_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Microsoft access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return MicrosoftSSO(access_token=access_token, refresh_token=refresh_token)
