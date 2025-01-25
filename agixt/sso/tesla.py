import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- TESLA_CLIENT_ID: Tesla OAuth client ID
- TESLA_CLIENT_SECRET: Tesla OAuth client secret
- TESLA_REDIRECT_URI: OAuth redirect URI
- TESLA_AUDIENCE: Fleet API base URL (https://fleet-api.prd.na.vn.cloud.tesla.com)

Required scopes for Tesla OAuth:
- openid: Allow Tesla customers to sign in
- offline_access: Allow getting refresh tokens
- user_data: Contact/profile information
- vehicle_device_data: Vehicle live data and information
- vehicle_cmds: Core vehicle commands (lock, unlock, etc)
- vehicle_charging_cmds: Charging control commands
- vehicle_location: Vehicle location access
"""

# Combined scopes needed for full vehicle control
SCOPES = [
    "openid",
    "offline_access",
    "user_data",
    "vehicle_device_data",
    "vehicle_cmds",
    "vehicle_charging_cmds",
    "vehicle_location",
]


class TeslaSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("TESLA_CLIENT_ID")
        self.client_secret = getenv("TESLA_CLIENT_SECRET")
        self.audience = getenv(
            "TESLA_AUDIENCE", "https://fleet-api.prd.na.vn.cloud.tesla.com"
        )
        self.auth_base_url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3"
        self.api_base_url = f"{self.audience}/api/1"
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Get a new access token using the refresh token"""
        response = requests.post(
            f"{self.auth_base_url}/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": self.refresh_token,
                "audience": self.audience,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to refresh token: {response.text}",
            )

        data = response.json()
        self.access_token = data["access_token"]
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        return self.access_token

    def get_user_info(self):
        """Get user information from Tesla API"""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            # First try with current token
            response = requests.get(f"{self.api_base_url}/user", headers=headers)

            # If token expired, try refreshing
            if response.status_code == 401 and self.refresh_token:
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(f"{self.api_base_url}/user", headers=headers)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            data = response.json()
            return {
                "email": data.get("email"),
                "first_name": data.get("first_name"),
                "last_name": data.get("last_name"),
            }

        except Exception as e:
            logging.error(f"Error getting Tesla user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting Tesla user info: {str(e)}"
            )


def tesla_sso(code, redirect_uri=None):
    """Handle Tesla OAuth flow"""
    if not redirect_uri:
        redirect_uri = getenv("TESLA_REDIRECT_URI")

    # Exchange authorization code for tokens
    response = requests.post(
        "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token",
        data={
            "grant_type": "authorization_code",
            "client_id": getenv("TESLA_CLIENT_ID"),
            "client_secret": getenv("TESLA_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "audience": getenv(
                "TESLA_AUDIENCE", "https://fleet-api.prd.na.vn.cloud.tesla.com"
            ),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        logging.error(f"Error getting Tesla access token: {response.text}")
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    return TeslaSSO(access_token=access_token, refresh_token=refresh_token)


def get_authorization_url(state=None, prompt_missing_scopes=True):
    """Generate Tesla authorization URL"""
    client_id = getenv("TESLA_CLIENT_ID")
    redirect_uri = getenv("TESLA_REDIRECT_URI")

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "prompt_missing_scopes": str(prompt_missing_scopes).lower(),
    }

    if state:
        params["state"] = state

    # Build query string
    query = "&".join([f"{k}={v}" for k, v in params.items()])

    return f"https://auth.tesla.com/oauth2/v3/authorize?{query}"
