import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- LINKEDIN_CLIENT_ID: LinkedIn OAuth client ID
- LINKEDIN_CLIENT_SECRET: LinkedIn OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for LinkedIn OAuth

- r_liteprofile
- r_emailaddress
- w_member_social
"""


class LinkedInSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = getenv("LINKEDIN_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return response.json()["access_token"]

    def get_user_info(self):
        profile_url = "https://api.linkedin.com/v2/me"
        email_url = "https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))"

        profile_response = requests.get(
            profile_url,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

        email_response = requests.get(
            email_url,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

        if profile_response.status_code == 401 or email_response.status_code == 401:
            self.access_token = self.get_new_token()
            profile_response = requests.get(
                profile_url,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            email_response = requests.get(
                email_url,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

        try:
            profile_data = profile_response.json()
            email_data = email_response.json()
            first_name = profile_data["localizedFirstName"]
            last_name = profile_data["localizedLastName"]
            email = email_data["elements"][0]["handle~"]["emailAddress"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from LinkedIn",
            )

    def send_email(self, to, subject, message_text):
        # LinkedIn API does not support sending emails directly
        raise NotImplementedError("LinkedIn API does not support sending emails")


def linkedin_sso(code, redirect_uri=None) -> LinkedInSSO:
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
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": getenv("LINKEDIN_CLIENT_ID"),
            "client_secret": getenv("LINKEDIN_CLIENT_SECRET"),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        logging.error(f"Error getting LinkedIn access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return LinkedInSSO(access_token=access_token, refresh_token=refresh_token)
