import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- GITLAB_CLIENT_ID: GitLab OAuth client ID
- GITLAB_CLIENT_SECRET: GitLab OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `GITLAB_CLIENT_ID` and `GITLAB_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for GitLab SSO

- read_user
- api
- email
"""


class GitLabSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GITLAB_CLIENT_ID")
        self.client_secret = getenv("GITLAB_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://gitlab.com/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://gitlab.com/api/v4/user"
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
            first_name = data["name"].split()[0]
            last_name = data["name"].split()[-1]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from GitLab",
            )

    def send_email(self, to, subject, message_text):
        # Assuming that GitLab does not provide an email send capability directly.
        # One could use another email service here if required.
        raise NotImplementedError(
            "GitLab SSO does not support sending emails directly."
        )


def gitlab_sso(code, redirect_uri=None) -> GitLabSSO:
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
        f"https://gitlab.com/oauth/token",
        data={
            "client_id": getenv("GITLAB_CLIENT_ID"),
            "client_secret": getenv("GITLAB_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting GitLab access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else "Not provided"
    return GitLabSSO(access_token=access_token, refresh_token=refresh_token)
