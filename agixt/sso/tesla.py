import requests
import logging
from fastapi import HTTPException
from Globals import getenv
from endpoints.TeslaIntegration import ensure_keys_exist, get_tesla_private_key

"""
Required environment variables:

- TESLA_CLIENT_ID: Tesla OAuth client ID
- TESLA_CLIENT_SECRET: Tesla OAuth client secret
- TESLA_AUDIENCE: Fleet API base URL (https://fleet-api.prd.na.vn.cloud.tesla.com)
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
AUTHORIZE = "https://auth.tesla.com/oauth2/v3/authorize"
PKCE_REQUIRED = False


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
        self.domain = (
            getenv("AGIXT_URI")
            .replace("https://", "")
            .replace("http://", "")
            .rstrip("/")
        )
        self.audience = getenv(
            "TESLA_AUDIENCE", "https://fleet-api.prd.na.vn.cloud.tesla.com"
        )
        self.token_url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
        self.api_base_url = f"{self.audience}/api/1"
        self.auth_base_url = "https://auth.tesla.com/oauth2/v3"

        # Ensure we have Tesla keys generated
        ensure_keys_exist()

        # Get user info
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Get a new access token using the refresh token"""
        refresh_url = f"{self.auth_base_url}/token"

        response = requests.post(
            refresh_url,
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
            user_url = f"{self.api_base_url}/users/me"
            response = requests.get(user_url, headers=headers)

            # If token expired, try refreshing
            if response.status_code == 401 and self.refresh_token:
                logging.info("Tesla token expired, refreshing...")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(user_url, headers=headers)

            # If we get a 404, the endpoint might be different, try to diagnose
            if response.status_code == 404:
                logging.warning(f"Tesla API endpoint not found: {user_url}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            # If we need registration, log it clearly
            if response.status_code == 412 and "must be registered" in response.text:
                logging.error(f"Tesla account needs registration: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            data = response.json()
            if "response" in data:
                data = data["response"]
            return {
                "email": data.get("email"),
                "first_name": data.get("first_name"),
                "last_name": data.get("last_name"),
            }

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Error getting Tesla user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting Tesla user info: {str(e)}"
            )


def sso(code, redirect_uri=None):
    """Handle Tesla OAuth flow"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    logging.info(
        f"Exchanging Tesla authorization code for tokens with redirect URI: {redirect_uri}"
    )

    # Exchange authorization code for tokens
    token_url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"

    payload = {
        "grant_type": "authorization_code",
        "client_id": getenv("TESLA_CLIENT_ID"),
        "client_secret": getenv("TESLA_CLIENT_SECRET"),
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "audience": getenv(
            "TESLA_AUDIENCE", "https://fleet-api.prd.na.vn.cloud.tesla.com"
        ),
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    logging.info(f"Sending token request to {token_url}")
    response = requests.post(token_url, data=payload, headers=headers)

    if response.status_code != 200:
        logging.error(
            f"Error getting Tesla access token: {response.status_code} - {response.text}"
        )
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    logging.info(
        f"Successfully obtained Tesla tokens. Access token expires in {expires_in} seconds."
    )

    return TeslaSSO(access_token=access_token, refresh_token=refresh_token)

    # If we got here but user_info is None, run diagnostics
    if not tesla_client.user_info:
        logging.warning(
            "Got Tesla tokens but couldn't get user info. Running diagnostics..."
        )
        response = requests.get(
            f"{tesla_client.api_base_url}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    return tesla_client


def get_authorization_url(state=None, prompt_missing_scopes=True):
    """Generate Tesla authorization URL"""
    client_id = getenv("TESLA_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

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
