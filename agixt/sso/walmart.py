import requests
import logging
from fastapi import HTTPException
from Globals import getenv

"""
Required environment variables:

- WALMART_CLIENT_ID: Walmart OAuth client ID
- WALMART_CLIENT_SECRET: Walmart OAuth client secret
- WALMART_MARKETPLACE_ID: Your Walmart Marketplace ID

Required APIs and Scopes for Walmart OAuth:

- https://marketplace.walmartapis.com/v3/token

Required scopes: 
"""

SCOPES = [
    "orders",
    "items",
    "inventory",
    "pricing",
    "reports",
    "returns",
]
AUTHORIZE = "https://developer.walmart.com/api/oauth/authorize"
PKCE_REQUIRED = False


class WalmartSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("WALMART_CLIENT_ID")
        self.client_secret = getenv("WALMART_CLIENT_SECRET")
        self.marketplace_id = getenv("WALMART_MARKETPLACE_ID")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refreshes the access token using the refresh token"""
        try:
            response = requests.post(
                "https://marketplace.walmartapis.com/v3/token",
                headers={
                    "WM_SVC.NAME": "Walmart Marketplace",
                    "WM_QOS.CORRELATION_ID": self.marketplace_id,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )

            if response.status_code != 200:
                logging.error(f"Error refreshing token: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to refresh Walmart token: {response.text}",
                )

            return response.json()["access_token"]
        except Exception as e:
            logging.error(f"Error refreshing Walmart token: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error refreshing Walmart token: {str(e)}"
            )

    def get_user_info(self):
        """Gets seller account information"""
        try:
            uri = "https://marketplace.walmartapis.com/v3/seller/info"
            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Accept": "application/json",
            }

            response = requests.get(uri, headers=headers)

            # If token expired, refresh and retry
            if response.status_code == 401:
                self.access_token = self.get_new_token()
                headers["WM_SEC.ACCESS_TOKEN"] = self.access_token
                response = requests.get(uri, headers=headers)

            if response.status_code != 200:
                logging.error(f"Error getting seller info: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error getting seller info: {response.text}",
                )

            data = response.json()
            return {
                "email": data["sellerEmail"],
                "company_name": data["companyName"],
                "marketplace_id": data["marketplaceId"],
                "partner_id": data["partnerId"],
            }

        except Exception as e:
            logging.error(f"Error getting Walmart seller info: {str(e)}")
            raise HTTPException(
                status_code=400, detail="Error getting seller info from Walmart"
            )


def sso(code, redirect_uri=None) -> WalmartSSO:
    """
    Handles the OAuth2 authorization code flow for Walmart Marketplace
    """
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )

    try:
        response = requests.post(
            "https://marketplace.walmartapis.com/v3/token",
            headers={
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": getenv("WALMART_MARKETPLACE_ID"),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": getenv("WALMART_CLIENT_ID"),
                "client_secret": getenv("WALMART_CLIENT_SECRET"),
                "redirect_uri": redirect_uri,
            },
        )

        if response.status_code != 200:
            logging.error(f"Error getting Walmart access token: {response.text}")
            return None

        data = response.json()
        access_token = data["access_token"]
        refresh_token = data.get("refresh_token", "Not provided")

        return WalmartSSO(access_token=access_token, refresh_token=refresh_token)

    except Exception as e:
        logging.error(f"Error in Walmart SSO: {str(e)}")
        return None
