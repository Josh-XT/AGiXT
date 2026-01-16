import logging
import requests
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any
from fastapi import HTTPException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


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

        if response.status_code != 200:
            raise Exception(f"Amazon Cognito token refresh failed: {response.text}")

        token_data = response.json()

        # Update our access token for immediate use
        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            raise Exception("No access_token in Amazon Cognito refresh response")

        return token_data

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
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    return AmazonSSO(access_token=access_token, refresh_token=refresh_token)


def get_authorization_url(state=None):
    """Generate Amazon authorization URL"""
    client_id = getenv("AWS_CLIENT_ID")
    redirect_uri = getenv("APP_URI")
    user_pool_id = getenv("AWS_USER_POOL_ID")
    region = getenv("AWS_REGION")

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

    return f"https://{user_pool_id}.auth.{region}.amazoncognito.com/oauth2/authorize?{query}"


class amazon(Extensions):
    """
    The Amazon extension provides integration with Amazon Web Services (AWS) and Amazon services.
    This extension allows AI agents to:
    - Manage AWS Cognito user authentication
    - Access user profile information
    - Work with Amazon Login with Amazon (LWA) authentication
    - Basic AWS service integration

    The extension requires the user to be authenticated through AWS Cognito OAuth.
    AI agents should use this when they need to interact with Amazon/AWS services
    for user authentication and basic profile management.
    """

    CATEGORY = "E-commerce & Shopping"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("AMAZON_ACCESS_TOKEN", None)
        aws_client_id = getenv("AWS_CLIENT_ID")
        aws_client_secret = getenv("AWS_CLIENT_SECRET")
        self.user_pool_id = getenv("AWS_USER_POOL_ID")
        self.region = getenv("AWS_REGION")
        self.auth = None

        if aws_client_id and aws_client_secret and self.user_pool_id and self.region:
            self.commands = {
                "Amazon - Get User Profile": self.get_user_profile,
                "Amazon - Verify Token": self.verify_token,
                "Amazon - Get Account Info": self.get_account_info,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Amazon extension: {str(e)}")
        else:
            self.commands = {}

    def verify_user(self):
        """
        Verify user access token and refresh if needed using MagicalAuth
        """
        if not self.auth:
            raise Exception("Authentication context not initialized.")

        try:
            # Refresh token via MagicalAuth, which handles expiry checks
            refreshed_token = self.auth.refresh_oauth_token(provider="amazon")
            if refreshed_token:
                self.access_token = refreshed_token
            else:
                if not self.access_token:
                    raise Exception("No valid Amazon access token found")

        except Exception as e:
            logging.error(f"Error verifying/refreshing Amazon token: {str(e)}")
            raise Exception("Failed to authenticate with Amazon")

    async def get_user_profile(self) -> str:
        """
        Get user profile information from Amazon/AWS Cognito

        Returns:
            str: User profile information
        """
        try:
            self.verify_user()

            headers = {"Authorization": f"Bearer {self.access_token}"}
            user_info_url = f"https://{self.user_pool_id}.auth.{self.region}.amazoncognito.com/oauth2/userInfo"

            response = requests.get(user_info_url, headers=headers)

            if response.status_code == 200:
                data = response.json()

                profile_info = f"""Amazon User Profile:
- Email: {data.get('email', 'N/A')}
- Name: {data.get('name', 'N/A')}
- Given Name: {data.get('given_name', 'N/A')}
- Family Name: {data.get('family_name', 'N/A')}
- Username: {data.get('username', 'N/A')}
- Subject: {data.get('sub', 'N/A')}
- Email Verified: {data.get('email_verified', 'N/A')}"""

                return profile_info
            else:
                return f"Failed to get user profile: HTTP {response.status_code} - {response.text}"

        except Exception as e:
            logging.error(f"Error getting user profile: {str(e)}")
            return f"Error getting user profile: {str(e)}"

    async def verify_token(self) -> str:
        """
        Verify the current access token is valid

        Returns:
            str: Token verification status
        """
        try:
            self.verify_user()

            headers = {"Authorization": f"Bearer {self.access_token}"}
            user_info_url = f"https://{self.user_pool_id}.auth.{self.region}.amazoncognito.com/oauth2/userInfo"

            response = requests.get(user_info_url, headers=headers)

            if response.status_code == 200:
                return "Amazon access token is valid and active"
            elif response.status_code == 401:
                return "Amazon access token is expired or invalid"
            else:
                return f"Token verification failed: HTTP {response.status_code}"

        except Exception as e:
            logging.error(f"Error verifying token: {str(e)}")
            return f"Error verifying token: {str(e)}"

    async def get_account_info(self) -> str:
        """
        Get comprehensive account information

        Returns:
            str: Account information summary
        """
        try:
            self.verify_user()

            headers = {"Authorization": f"Bearer {self.access_token}"}
            user_info_url = f"https://{self.user_pool_id}.auth.{self.region}.amazoncognito.com/oauth2/userInfo"

            response = requests.get(user_info_url, headers=headers)

            if response.status_code == 200:
                data = response.json()

                account_info = f"""Amazon Account Information:
                
📧 Contact Details:
- Email: {data.get('email', 'N/A')}
- Email Verified: {data.get('email_verified', 'N/A')}

👤 Profile Details:
- Full Name: {data.get('name', 'N/A')}
- Given Name: {data.get('given_name', 'N/A')}
- Family Name: {data.get('family_name', 'N/A')}
- Username: {data.get('username', 'N/A')}

🔐 Account Details:
- User ID: {data.get('sub', 'N/A')}
- Auth Time: {data.get('auth_time', 'N/A')}
- Cognito User Pool: {self.user_pool_id}
- Region: {self.region}"""

                return account_info
            else:
                return f"Failed to get account info: HTTP {response.status_code} - {response.text}"

        except Exception as e:
            logging.error(f"Error getting account info: {str(e)}")
            return f"Error getting account info: {str(e)}"
