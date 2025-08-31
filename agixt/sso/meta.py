import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- META_APP_ID: Meta (Facebook) application ID
- META_APP_SECRET: Meta (Facebook) application secret
"""

# Meta Marketing API permissions required for advertising
SCOPES = [
    "ads_management",
    "ads_read",
    "business_management",
    "pages_read_engagement",
    "pages_manage_ads",
    "pages_show_list",
    "read_insights",
    "email",
]

AUTHORIZE = "https://www.facebook.com/v18.0/dialog/oauth"
PKCE_REQUIRED = False


class MetaSSO:
    def __init__(self, access_token=None, refresh_token=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("META_APP_ID")
        self.client_secret = getenv("META_APP_SECRET")
        self.token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        self.api_base_url = "https://graph.facebook.com/v18.0"

        # Get user info upon initialization (only if we have a valid token)
        self.user_info = None
        if self.access_token and not self.access_token.startswith("test_"):
            try:
                self.user_info = self.get_user_info()
            except Exception as e:
                logging.warning(f"Could not get user info during initialization: {e}")
                self.user_info = None

    def get_new_token(self):
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            # Meta doesn't provide refresh tokens by default
            # Instead, we need to get a long-lived token
            return self.get_long_lived_token()

        response = requests.post(
            self.token_url,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "fb_exchange_token": self.access_token,
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

        # Meta doesn't typically return refresh tokens, so we keep the existing one
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        return self.access_token

    def get_long_lived_token(self):
        """Exchange short-lived token for long-lived token"""
        response = requests.get(
            f"{self.api_base_url}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "fb_exchange_token": self.access_token,
            },
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to get long-lived token: {response.text}",
            )

        data = response.json()
        self.access_token = data["access_token"]

        return self.access_token

    def get_user_info(self):
        """Get user information from the Facebook Graph API"""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = requests.get(
                f"{self.api_base_url}/me",
                params={"fields": "id,name,email"},
                headers=headers,
            )

            # Auto-refresh if token expired
            if response.status_code == 401 and self.refresh_token:
                logging.info("Token expired, refreshing...")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(
                    f"{self.api_base_url}/me",
                    params={"fields": "id,name,email"},
                    headers=headers,
                )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            data = response.json()
            return {
                "email": data.get("email"),
                "name": data.get("name"),
                "id": data.get("id"),
            }

        except Exception as e:
            logging.error(f"Error getting user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting user info: {str(e)}"
            )

    def get_business_accounts(self):
        """Get business accounts accessible to the user"""
        if not self.access_token:
            return []

        try:
            response = requests.get(
                f"{self.api_base_url}/me/businesses",
                params={
                    "fields": "id,name,is_verified",
                    "access_token": self.access_token,
                },
            )

            if response.status_code == 401:
                # Try to refresh token
                self.get_new_token()
                response = requests.get(
                    f"{self.api_base_url}/me/businesses",
                    params={
                        "fields": "id,name,is_verified",
                        "access_token": self.access_token,
                    },
                )

            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            else:
                logging.error(f"Error getting business accounts: {response.text}")
                return []

        except Exception as e:
            logging.error(f"Error getting business accounts: {str(e)}")
            return []

    def get_ad_accounts(self):
        """Get ad accounts accessible to the user"""
        if not self.access_token:
            return []

        try:
            response = requests.get(
                f"{self.api_base_url}/me/adaccounts",
                params={
                    "fields": "id,name,account_status",
                    "access_token": self.access_token,
                },
            )

            if response.status_code == 401:
                # Try to refresh token
                self.get_new_token()
                response = requests.get(
                    f"{self.api_base_url}/me/adaccounts",
                    params={
                        "fields": "id,name,account_status",
                        "access_token": self.access_token,
                    },
                )

            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            else:
                logging.error(f"Error getting ad accounts: {response.text}")
                return []

        except Exception as e:
            logging.error(f"Error getting ad accounts: {str(e)}")
            return []


def sso(code, redirect_uri=None):
    """Handle OAuth authorization code exchange"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    # Exchange authorization code for access token
    response = requests.get(
        "https://graph.facebook.com/v18.0/oauth/access_token",
        params={
            "client_id": getenv("META_APP_ID"),
            "client_secret": getenv("META_APP_SECRET"),
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )

    if response.status_code != 200:
        logging.error(
            f"Error getting access token: {response.status_code} - {response.text}"
        )
        return None

    data = response.json()

    # Create SSO instance with the access token
    meta_sso = MetaSSO(
        access_token=data.get("access_token"),
        refresh_token=data.get("refresh_token"),  # Meta typically doesn't provide this
    )

    # Get long-lived token immediately
    try:
        meta_sso.get_long_lived_token()
    except Exception as e:
        logging.warning(f"Could not get long-lived token: {str(e)}")

    return meta_sso


def get_authorization_url(state=None):
    """Generate OAuth authorization URL"""
    client_id = getenv("META_APP_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(SCOPES),
        "response_type": "code",
    }

    if state:
        params["state"] = state

    query = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{AUTHORIZE}?{query}"
