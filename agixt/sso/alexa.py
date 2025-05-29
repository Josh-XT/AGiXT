import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- ALEXA_CLIENT_ID: Alexa OAuth client ID
- ALEXA_CLIENT_SECRET: Alexa OAuth client secret
"""

SCOPES = [
    "alexa:all",
    "alexa::async_event:write",
    "alexa::health:profile:write",
    "alexa::profile:email:read",
    "alexa::profile:name:read",
    "alexa::devices:all:address:country_and_postal_code:read",
]
AUTHORIZE = "https://www.amazon.com/ap/oa"
PKCE_REQUIRED = False


class AlexaSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("ALEXA_CLIENT_ID")
        self.client_secret = getenv("ALEXA_CLIENT_SECRET")
        self.domain = (
            getenv("AGIXT_URI")
            .replace("https://", "")
            .replace("http://", "")
            .rstrip("/")
        )
        self.token_url = "https://api.amazon.com/auth/o2/token"
        self.api_base_url = "https://api.amazonalexa.com"
        
        # Get user info
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Get a new access token using the refresh token"""
        response = requests.post(
            self.token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to refresh Alexa token: {response.text}",
            )

        data = response.json()
        self.access_token = data["access_token"]
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        return self.access_token

    def get_user_info(self):
        """Get user information from Alexa API"""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            # Try with current token
            user_url = f"{self.api_base_url}/v2/accounts/~current/settings/Profile.email"
            response = requests.get(user_url, headers=headers)

            # If token expired, try refreshing
            if response.status_code == 401 and self.refresh_token:
                logging.info("Alexa token expired, refreshing...")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(user_url, headers=headers)

            if response.status_code != 200:
                # Try alternative endpoint for user profile
                user_url = f"{self.api_base_url}/v2/accounts/~current/settings/Profile.name"
                response = requests.get(user_url, headers=headers)
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to get Alexa user info: {response.text}",
                    )

            email_response = requests.get(
                f"{self.api_base_url}/v2/accounts/~current/settings/Profile.email",
                headers=headers
            )
            name_response = requests.get(
                f"{self.api_base_url}/v2/accounts/~current/settings/Profile.name",
                headers=headers
            )

            email = email_response.text if email_response.status_code == 200 else None
            name = name_response.text if name_response.status_code == 200 else None

            return {
                "email": email,
                "name": name,
                "first_name": name.split()[0] if name and " " in name else name,
                "last_name": name.split()[-1] if name and " " in name else None,
            }

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Error getting Alexa user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting Alexa user info: {str(e)}"
            )


def sso(code, redirect_uri=None):
    """Handle Alexa OAuth flow"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    logging.info(
        f"Exchanging Alexa authorization code for tokens with redirect URI: {redirect_uri}"
    )

    # Exchange authorization code for tokens
    token_url = "https://api.amazon.com/auth/o2/token"

    payload = {
        "grant_type": "authorization_code",
        "client_id": getenv("ALEXA_CLIENT_ID"),
        "client_secret": getenv("ALEXA_CLIENT_SECRET"),
        "code": code,
        "redirect_uri": redirect_uri,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    logging.info(f"Sending token request to {token_url}")
    response = requests.post(token_url, data=payload, headers=headers)

    if response.status_code != 200:
        logging.error(
            f"Error getting Alexa access token: {response.status_code} - {response.text}"
        )
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    logging.info(
        f"Successfully obtained Alexa tokens. Access token expires in {expires_in} seconds."
    )

    return AlexaSSO(access_token=access_token, refresh_token=refresh_token)


def get_authorization_url(state=None):
    """Generate Alexa authorization URL"""
    client_id = getenv("ALEXA_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "redirect_uri": redirect_uri,
    }

    if state:
        params["state"] = state

    # Build query string
    query = "&".join([f"{k}={v}" for k, v in params.items()])

    return f"https://www.amazon.com/ap/oa?{query}"
