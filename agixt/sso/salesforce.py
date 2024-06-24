import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- SALESFORCE_CLIENT_ID: Salesforce OAuth client ID
- SALESFORCE_CLIENT_SECRET: Salesforce OAuth client secret

Required APIs

Follow the links to confirm that you have the APIs enabled,
then add the `SALESFORCE_CLIENT_ID` and `SALESFORCE_CLIENT_SECRET` environment variables to your `.env` file.

Required scopes for Salesforce OAuth

- refresh_token
- full
- email
"""


class SalesforceSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
        instance_url=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.instance_url = instance_url
        self.client_id = getenv("SALESFORCE_CLIENT_ID")
        self.client_secret = getenv("SALESFORCE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            f"{self.instance_url}/services/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()["access_token"]

    def get_user_info(self):
        uri = f"{self.instance_url}/services/oauth2/userinfo"
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
            first_name = data["given_name"]
            last_name = data["family_name"]
            email = data["email"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Salesforce",
            )

    def send_email(self, to, subject, message_text):
        # Salesforce does not have a direct email sending API in the same way Google and Microsoft do.
        # This will need to be implemented according to the specific Salesforce instance and setup.
        raise NotImplementedError(
            "Send email functionality is dependent on the Salesforce instance configuration."
        )


def salesforce_sso(code, redirect_uri=None) -> SalesforceSSO:
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
        f"https://login.salesforce.com/services/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": getenv("SALESFORCE_CLIENT_ID"),
            "client_secret": getenv("SALESFORCE_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Salesforce access token: {response.text}")
        return None, None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    instance_url = data["instance_url"]
    return SalesforceSSO(
        access_token=access_token,
        refresh_token=refresh_token,
        instance_url=instance_url,
    )
