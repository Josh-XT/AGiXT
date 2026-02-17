import logging
import requests
from Extensions import Extensions
from Globals import getenv
from fastapi import HTTPException

"""
Microsoft SSO Extension - Minimal scopes for Single Sign-On only.

This extension provides OAuth authentication for Microsoft accounts with the minimum
required scopes for user login. It does NOT include permissions for email, calendar,
OneDrive, or SharePoint - those are available through separate extensions that the
user can connect individually.

Required environment variables:

- MICROSOFT_CLIENT_ID: Microsoft OAuth client ID
- MICROSOFT_CLIENT_SECRET: Microsoft OAuth client secret

Required scopes:
- offline_access: Required for refresh tokens
- User.Read: Read user profile information
"""

SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
]
AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
PKCE_REQUIRED = False
SSO_ONLY = True  # This provider can be used for login/registration


class MicrosoftSsoSSO:
    """SSO handler for Microsoft authentication with minimal scopes."""

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

        if response.status_code != 200:
            logging.error(f"Token refresh failed with response: {response.text}")
            raise Exception(f"Microsoft SSO token refresh failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            logging.error("No access_token in refresh response")

        return token_data

    def get_user_info(self):
        uri = "https://graph.microsoft.com/v1.0/me"

        if not self.access_token:
            logging.error("No access token available")

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
            first_name = data.get("givenName", "") or ""
            last_name = data.get("surname", "") or ""
            email = data.get("mail") or data.get("userPrincipalName", "")

            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error parsing Microsoft user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Microsoft",
            )


def sso(code, redirect_uri=None) -> MicrosoftSsoSSO:
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
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
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
        logging.error(f"Error getting Microsoft SSO access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "Not provided")
    return MicrosoftSsoSSO(access_token=access_token, refresh_token=refresh_token)


class microsoft_sso(Extensions):
    """
    Microsoft Single Sign-On (SSO) Extension.

    This extension provides Microsoft account authentication with minimal permissions.
    It only requests the scopes necessary to identify and authenticate users.

    For additional Microsoft 365 features, users should connect the appropriate
    service-specific extensions:
    - Microsoft Email: For Outlook email access
    - Microsoft Calendar: For calendar management
    - Microsoft OneDrive: For file storage access
    - Microsoft SharePoint: For SharePoint site access

    Each of these extensions requires separate authorization with its own specific scopes,
    allowing users to grant only the permissions they need.
    """

    CATEGORY = "Authentication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("MICROSOFT_SSO_ACCESS_TOKEN", None)
        microsoft_client_id = getenv("MICROSOFT_CLIENT_ID")
        microsoft_client_secret = getenv("MICROSOFT_CLIENT_SECRET")

        if microsoft_client_id and microsoft_client_secret:
            self.commands = {
                "Verify Microsoft SSO Connection": self.verify_connection,
                "Get Microsoft User Profile": self.get_user_profile,
            }

    async def verify_connection(self):
        """
        Verifies that the Microsoft SSO connection is working.

        Returns:
            str: Success message with user information or error details
        """
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me", headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                name = f"{data.get('givenName', '')} {data.get('surname', '')}".strip()
                email = data.get("mail") or data.get("userPrincipalName", "")
                return (
                    f"Microsoft SSO connection verified. Connected as: {name} ({email})"
                )
            else:
                return f"Microsoft SSO verification failed: {response.text}"
        except Exception as e:
            logging.error(f"Error verifying Microsoft SSO: {str(e)}")
            return f"Failed to verify Microsoft SSO connection: {str(e)}"

    async def get_user_profile(self):
        """
        Gets the user's Microsoft profile information.

        Returns:
            dict: User profile information including name, email, etc.
        """
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me", headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "display_name": data.get("displayName", ""),
                    "first_name": data.get("givenName", ""),
                    "last_name": data.get("surname", ""),
                    "email": data.get("mail") or data.get("userPrincipalName", ""),
                    "job_title": data.get("jobTitle", ""),
                    "office_location": data.get("officeLocation", ""),
                    "mobile_phone": data.get("mobilePhone", ""),
                    "business_phones": data.get("businessPhones", []),
                }
            else:
                raise Exception(f"Failed to get profile: {response.text}")
        except Exception as e:
            logging.error(f"Error getting Microsoft user profile: {str(e)}")
            return {"error": str(e)}
