import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- KEYCLOAK_CLIENT_ID: Keycloak OAuth client ID
- KEYCLOAK_CLIENT_SECRET: Keycloak OAuth client secret
- KEYCLOAK_REALM: Keycloak realm name
- KEYCLOAK_SERVER_URL: Keycloak server URL

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the KEYCLOAK_CLIENT_ID, KEYCLOAK_CLIENT_SECRET, KEYCLOAK_REALM, and KEYCLOAK_SERVER_URL environment variables to your `.env` file.

Required scopes for Keycloak SSO:

- openid
- email
- profile
"""


class KeycloakSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("KEYCLOAK_CLIENT_ID")
        self.client_secret = getenv("KEYCLOAK_CLIENT_SECRET")
        self.realm = getenv("KEYCLOAK_REALM")
        self.server_url = getenv("KEYCLOAK_SERVER_URL")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/userinfo"
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
            first_name = data.get("given_name")
            last_name = data.get("family_name")
            email = data.get("email")
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Keycloak",
            )


def keycloak_sso(code, redirect_uri=None) -> KeycloakSSO:
    if not redirect_uri:
        redirect_uri = getenv("MAGIC_LINK_URL")
    response = requests.post(
        f"{getenv('KEYCLOAK_SERVER_URL')}/realms/{getenv('KEYCLOAK_REALM')}/protocol/openid-connect/token",
        data={
            "client_id": getenv("KEYCLOAK_CLIENT_ID"),
            "client_secret": getenv("KEYCLOAK_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Keycloak access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return KeycloakSSO(access_token=access_token, refresh_token=refresh_token)
