import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- AWS_CLIENT_ID: AWS Cognito OAuth client ID
- AWS_CLIENT_SECRET: AWS Cognito OAuth client secret
- AWS_USER_POOL_ID: AWS Cognito User Pool ID
- AWS_REGION: AWS Cognito Region

Required scopes for AWS OAuth

- openid
- email
- profile
"""
SCOPES = ["openid", "email", "profile"]
AUTHORIZE = "https://www.amazon.com/ap/oa"
PKCE_REQUIRED = False


class AmazonSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("AWS_CLIENT_ID")
        self.client_secret = getenv("AWS_CLIENT_SECRET")
        self.user_pool_id = getenv("AWS_USER_POOL_ID")
        self.region = getenv("AWS_REGION")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            f"https://{self.user_pool_id}.auth.{self.region}.amazoncognito.com/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": "openid email profile",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = f"https://{self.user_pool_id}.auth.{self.region}.amazoncognito.com/oauth2/userInfo"
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
            first_name = data.get("given_name", "")
            last_name = data.get("family_name", "")
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from AWS",
            )


def sso(code, redirect_uri=None) -> AmazonSSO:
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
        f"https://{getenv('AWS_USER_POOL_ID')}.auth.{getenv('AWS_REGION')}.amazoncognito.com/oauth2/token",
        data={
            "client_id": getenv("AWS_CLIENT_ID"),
            "client_secret": getenv("AWS_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting AWS access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return AmazonSSO(access_token=access_token, refresh_token=refresh_token)
