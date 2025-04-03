import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- GITHUB_CLIENT_ID: GitHub OAuth client ID
- GITHUB_CLIENT_SECRET: GitHub OAuth client secret

Required scopes for GitHub OAuth

- repo
- user:email
- read:user
- workflow
"""

SCOPES = ["repo", "user:email", "read:user", "workflow"]
AUTHORIZE = "https://github.com/login/oauth/authorize"
PKCE_REQUIRED = False


class GitHubSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GITHUB_CLIENT_ID")
        self.client_secret = getenv("GITHUB_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        # GitHub tokens do not support refresh tokens directly, we need to re-authorize.
        response = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = "https://api.github.com/user"
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
            response = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {self.access_token}"},
            )
            primary_email = response.json()["login"]
            return {
                "email": primary_email,
                "first_name": (
                    data.get("name", "").split()[0] if data.get("name") else ""
                ),
                "last_name": (
                    data.get("name", "").split()[-1] if data.get("name") else ""
                ),
            }
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from GitHub",
            )


def sso(code, redirect_uri=None) -> GitHubSSO:
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
        f"https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": getenv("GITHUB_CLIENT_ID"),
            "client_secret": getenv("GITHUB_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting GitHub access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "Not provided")
    return GitHubSSO(access_token=access_token, refresh_token=refresh_token)
