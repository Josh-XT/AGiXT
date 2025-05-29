import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- GARMIN_CLIENT_ID: Garmin OAuth client ID (Consumer Key)
- GARMIN_CLIENT_SECRET: Garmin OAuth client secret (Consumer Secret)
"""

# Garmin Connect IQ uses OAuth 1.0a, not OAuth 2.0
# For OAuth 1.0a, scopes are typically handled differently
SCOPES = []  # Garmin OAuth 1.0a doesn't use traditional scopes
AUTHORIZE = "https://connect.garmin.com/oauthConfirm"
PKCE_REQUIRED = False


class GarminSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
        oauth_token=None,
        oauth_token_secret=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.oauth_token = oauth_token
        self.oauth_token_secret = oauth_token_secret
        self.client_id = getenv("GARMIN_CLIENT_ID")  # Consumer Key
        self.client_secret = getenv("GARMIN_CLIENT_SECRET")  # Consumer Secret
        self.domain = (
            getenv("AGIXT_URI")
            .replace("https://", "")
            .replace("http://", "")
            .rstrip("/")
        )
        self.request_token_url = (
            "https://connectapi.garmin.com/oauth-service/oauth/request_token"
        )
        self.access_token_url = (
            "https://connectapi.garmin.com/oauth-service/oauth/access_token"
        )
        self.api_base_url = "https://connectapi.garmin.com"

        # Get user info
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Garmin uses OAuth 1.0a, tokens don't typically expire but can be refreshed"""
        # For OAuth 1.0a, we typically don't refresh tokens the same way
        # Instead, we would need to re-authorize if the token becomes invalid
        logging.warning(
            "Garmin OAuth 1.0a tokens typically don't support refresh. Re-authorization may be required."
        )
        return self.access_token

    def get_user_info(self):
        """Get user information from Garmin Connect API"""
        if not self.oauth_token or not self.oauth_token_secret:
            return None

        try:
            # Garmin Connect API requires OAuth 1.0a signed requests
            from requests_oauthlib import OAuth1

            auth = OAuth1(
                self.client_id,
                client_secret=self.client_secret,
                resource_owner_key=self.oauth_token,
                resource_owner_secret=self.oauth_token_secret,
            )

            # Try to get user profile information
            user_url = f"{self.api_base_url}/userprofile-service/userprofile"
            response = requests.get(user_url, auth=auth)

            if response.status_code == 401:
                logging.warning(
                    "Garmin OAuth token may be invalid. Re-authorization may be required."
                )
                return None

            if response.status_code != 200:
                # Try alternative endpoint
                user_url = f"{self.api_base_url}/userprofile-service/userprofile/personal-information"
                response = requests.get(user_url, auth=auth)

                if response.status_code != 200:
                    logging.warning(
                        f"Failed to get Garmin user info: {response.status_code} - {response.text}"
                    )
                    return {"oauth_token": self.oauth_token, "provider": "garmin"}

            try:
                data = response.json()
                return {
                    "display_name": data.get("displayName"),
                    "first_name": data.get("firstName"),
                    "last_name": data.get("lastName"),
                    "email": data.get("email"),
                    "username": data.get("username"),
                    "provider": "garmin",
                    "oauth_token": self.oauth_token,
                }
            except:
                # If JSON parsing fails, return basic info
                return {"oauth_token": self.oauth_token, "provider": "garmin"}

        except ImportError:
            logging.error("requests-oauthlib is required for Garmin OAuth 1.0a support")
            raise HTTPException(
                status_code=500,
                detail="requests-oauthlib is required for Garmin OAuth 1.0a support",
            )
        except Exception as e:
            logging.error(f"Error getting Garmin user info: {str(e)}")
            return {
                "oauth_token": self.oauth_token,
                "provider": "garmin",
                "error": str(e),
            }


def sso(oauth_verifier, oauth_token=None, oauth_token_secret=None):
    """Handle Garmin OAuth 1.0a flow"""
    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        logging.error("requests-oauthlib is required for Garmin OAuth 1.0a support")
        raise HTTPException(
            status_code=500,
            detail="requests-oauthlib is required for Garmin OAuth 1.0a support",
        )

    logging.info("Exchanging Garmin OAuth verifier for access token")

    client_id = getenv("GARMIN_CLIENT_ID")
    client_secret = getenv("GARMIN_CLIENT_SECRET")

    # Create OAuth1 auth for access token request
    auth = OAuth1(
        client_id,
        client_secret=client_secret,
        resource_owner_key=oauth_token,
        verifier=oauth_verifier,
    )

    # Exchange verifier for access token
    access_token_url = "https://connectapi.garmin.com/oauth-service/oauth/access_token"

    response = requests.post(access_token_url, auth=auth)

    if response.status_code != 200:
        logging.error(
            f"Error getting Garmin access token: {response.status_code} - {response.text}"
        )
        return None

    # Parse OAuth 1.0a response (URL encoded)
    from urllib.parse import parse_qs

    token_data = parse_qs(response.text)

    final_oauth_token = token_data.get("oauth_token", [None])[0]
    final_oauth_token_secret = token_data.get("oauth_token_secret", [None])[0]

    if not final_oauth_token or not final_oauth_token_secret:
        logging.error("Failed to get valid Garmin OAuth tokens")
        return None

    logging.info("Successfully obtained Garmin OAuth tokens")

    return GarminSSO(
        oauth_token=final_oauth_token,
        oauth_token_secret=final_oauth_token_secret,
    )


def get_authorization_url(callback_uri=None):
    """Generate Garmin authorization URL (OAuth 1.0a flow)"""
    try:
        from requests_oauthlib import OAuth1Session
    except ImportError:
        logging.error("requests-oauthlib is required for Garmin OAuth 1.0a support")
        raise HTTPException(
            status_code=500,
            detail="requests-oauthlib is required for Garmin OAuth 1.0a support",
        )

    if not callback_uri:
        callback_uri = getenv("APP_URI")

    client_id = getenv("GARMIN_CLIENT_ID")
    client_secret = getenv("GARMIN_CLIENT_SECRET")

    # Step 1: Get request token
    request_token_url = (
        "https://connectapi.garmin.com/oauth-service/oauth/request_token"
    )

    oauth = OAuth1Session(
        client_id, client_secret=client_secret, callback_uri=callback_uri
    )

    try:
        fetch_response = oauth.fetch_request_token(request_token_url)
        oauth_token = fetch_response.get("oauth_token")
        oauth_token_secret = fetch_response.get("oauth_token_secret")

        # Step 2: Generate authorization URL
        authorization_url = oauth.authorization_url(
            "https://connect.garmin.com/oauthConfirm"
        )

        # Store the token secret for later use (in a real implementation, you'd store this in session/database)
        # For now, we'll include it in the state parameter (not recommended for production)
        return authorization_url

    except Exception as e:
        logging.error(f"Error generating Garmin authorization URL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating Garmin authorization URL: {str(e)}",
        )
