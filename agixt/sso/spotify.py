import base64
import requests
import logging
from email.mime.text import MIMEText
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- SPOTIFY_CLIENT_ID: Spotify OAuth client ID
- SPOTIFY_CLIENT_SECRET: Spotify OAuth client secret

Required APIs

Ensure that you have the required APIs enabled in your Spotify developer account and add the `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Spotify SSO

- user-read-email
- user-read-private
- playlist-read-private
"""


class SpotifySSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = getenv("SPOTIFY_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.spotify.com/v1/me"
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
            first_name, last_name = data["display_name"].split(" ", 1)
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Spotify",
            )

    def send_email(self, to, subject, message_text):
        if not self.user_info.get("email"):
            user_info = self.get_user_info()
            self.email_address = user_info["email"]
        message = MIMEText(message_text)
        message["to"] = to
        message["from"] = self.email_address
        message["subject"] = subject
        # Since Spotify does not have a direct API for sending emails, we'll only prepare the message
        raw = base64.urlsafe_b64encode(message.as_bytes())
        return {"raw_message": raw.decode()}


def spotify_sso(code, redirect_uri=None) -> SpotifySSO:
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
        "https://accounts.spotify.com/api/token",
        data={
            "client_id": getenv("SPOTIFY_CLIENT_ID"),
            "client_secret": getenv("SPOTIFY_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        logging.error(f"Error getting Spotify access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return SpotifySSO(access_token=access_token, refresh_token=refresh_token)
