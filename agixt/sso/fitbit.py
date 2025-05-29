import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- FITBIT_CLIENT_ID: Fitbit OAuth client ID
- FITBIT_CLIENT_SECRET: Fitbit OAuth client secret
"""

SCOPES = [
    "activity",
    "heartrate",
    "location",
    "nutrition",
    "profile",
    "settings",
    "sleep",
    "social",
    "weight",
]
AUTHORIZE = "https://www.fitbit.com/oauth2/authorize"
PKCE_REQUIRED = True


class FitbitSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("FITBIT_CLIENT_ID")
        self.client_secret = getenv("FITBIT_CLIENT_SECRET")
        self.domain = (
            getenv("AGIXT_URI")
            .replace("https://", "")
            .replace("http://", "")
            .rstrip("/")
        )
        self.token_url = "https://api.fitbit.com/oauth2/token"
        self.api_base_url = "https://api.fitbit.com"

        # Get user info
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Get a new access token using the refresh token"""
        import base64

        # Fitbit requires Basic auth with client credentials
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        response = requests.post(
            self.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to refresh Fitbit token: {response.text}",
            )

        data = response.json()
        self.access_token = data["access_token"]
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        return self.access_token

    def get_user_info(self):
        """Get user information from Fitbit API"""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            # Try with current token
            user_url = f"{self.api_base_url}/1/user/-/profile.json"
            response = requests.get(user_url, headers=headers)

            # If token expired, try refreshing
            if response.status_code == 401 and self.refresh_token:
                logging.info("Fitbit token expired, refreshing...")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(user_url, headers=headers)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get Fitbit user info: {response.text}",
                )

            data = response.json()
            user_data = data.get("user", {})

            return {
                "email": user_data.get("email"),
                "first_name": user_data.get("firstName"),
                "last_name": user_data.get("lastName"),
                "display_name": user_data.get("displayName"),
                "member_since": user_data.get("memberSince"),
                "country": user_data.get("country"),
                "timezone": user_data.get("timezone"),
            }

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Error getting Fitbit user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting Fitbit user info: {str(e)}"
            )


def sso(code, redirect_uri=None, code_verifier=None):
    """Handle Fitbit OAuth flow"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    logging.info(
        f"Exchanging Fitbit authorization code for tokens with redirect URI: {redirect_uri}"
    )

    import base64

    # Fitbit requires Basic auth with client credentials
    client_id = getenv("FITBIT_CLIENT_ID")
    client_secret = getenv("FITBIT_CLIENT_SECRET")
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    # Exchange authorization code for tokens
    token_url = "https://api.fitbit.com/oauth2/token"

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }

    # Add code verifier if using PKCE
    if code_verifier:
        payload["code_verifier"] = code_verifier

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    logging.info(f"Sending token request to {token_url}")
    response = requests.post(token_url, data=payload, headers=headers)

    if response.status_code != 200:
        logging.error(
            f"Error getting Fitbit access token: {response.status_code} - {response.text}"
        )
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    logging.info(
        f"Successfully obtained Fitbit tokens. Access token expires in {expires_in} seconds."
    )

    return FitbitSSO(access_token=access_token, refresh_token=refresh_token)


def get_authorization_url(state=None, code_challenge=None):
    """Generate Fitbit authorization URL"""
    client_id = getenv("FITBIT_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "redirect_uri": redirect_uri,
    }

    if state:
        params["state"] = state

    # Add PKCE parameters if provided
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    # Build query string
    query = "&".join([f"{k}={v}" for k, v in params.items()])

    return f"https://www.fitbit.com/oauth2/authorize?{query}"
