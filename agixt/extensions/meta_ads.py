import logging
import requests
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from Extensions import Extensions
from MagicalAuth import MagicalAuth
from Globals import getenv
from fastapi import HTTPException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


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

        # Update our tokens for immediate use
        if "access_token" in data:
            self.access_token = data["access_token"]
        else:
            raise Exception("No access_token in Meta refresh response")

        # Meta doesn't typically return refresh tokens, so we keep the existing one
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        return data

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

        # Update our access token for immediate use
        if "access_token" in data:
            self.access_token = data["access_token"]
        else:
            raise Exception("No access_token in Meta long-lived token response")

        return data

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


class meta_ads(Extensions):
    """
    Meta Ads extension for marketing automation with Facebook and Instagram advertising.

    This extension provides comprehensive functionality for managing Meta (Facebook/Instagram) advertising campaigns including:
    - Campaign management (create, read, update, delete)
    - Ad set management with targeting options
    - Ad creative management
    - Audience management and custom audiences
    - Campaign insights and performance metrics
    - Budget management and optimization
    - Conversion tracking

    Required parameters:
    - META_APP_ID: Your Meta app ID for API access
    - META_APP_SECRET: Your Meta app secret for OAuth authentication
    - META_BUSINESS_ID: Your Meta Business Account ID

    Optional parameters:
    - access_token: OAuth access token for authenticated requests
    - api_key: AGiXT API key for MagicalAuth integration
    """

    CATEGORY = "Social & Communication"
    friendly_name = "Meta Ads"

    def __init__(self, **kwargs):
        """
        Initialize Meta Ads extension with required credentials

        The extension requires the user to be authenticated with Meta through OAuth.
        AI agents should use this when they need to interact with a user's Meta advertising account
        for tasks like managing campaigns, creating audiences, or analyzing ad performance.
        """
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("META_ACCESS_TOKEN", None)
        meta_app_id = getenv("META_APP_ID")
        meta_app_secret = getenv("META_APP_SECRET")
        meta_business_id = getenv("META_BUSINESS_ID")
        self.auth = None

        # Base URL for Meta Marketing API
        self.base_url = "https://graph.facebook.com/v18.0"

        # Store business ID for API calls
        self.business_id = meta_business_id

        # Initialize commands dictionary only if we have required credentials
        if meta_app_id and meta_app_secret and meta_business_id:
            self.commands = {
                "Meta Ads - Get Ad Accounts": self.get_ad_accounts,
                "Meta Ads - Create Campaign": self.create_campaign,
                "Meta Ads - Get Campaigns": self.get_campaigns,
                "Meta Ads - Update Campaign": self.update_campaign,
                "Meta Ads - Delete Campaign": self.delete_campaign,
                "Meta Ads - Create Ad Set": self.create_ad_set,
                "Meta Ads - Get Ad Sets": self.get_ad_sets,
                "Meta Ads - Update Ad Set": self.update_ad_set,
                "Meta Ads - Create Ad": self.create_ad,
                "Meta Ads - Get Ads": self.get_ads,
                "Meta Ads - Update Ad": self.update_ad,
                "Meta Ads - Get Campaign Insights": self.get_campaign_insights,
                "Meta Ads - Get Ad Set Insights": self.get_ad_set_insights,
                "Meta Ads - Get Ad Insights": self.get_ad_insights,
                "Meta Ads - Create Custom Audience": self.create_custom_audience,
                "Meta Ads - Get Custom Audiences": self.get_custom_audiences,
                "Meta Ads - Upload Audience Data": self.upload_audience_data,
                "Meta Ads - Create Lookalike Audience": self.create_lookalike_audience,
                "Meta Ads - Create Ad Creative": self.create_ad_creative,
                "Meta Ads - Get Ad Creatives": self.get_ad_creatives,
                "Meta Ads - Get Pages": self.get_pages,
                "Meta Ads - Get Targeting Options": self.get_targeting_options,
                "Meta Ads - Set Campaign Budget": self.set_campaign_budget,
                "Meta Ads - Pause Campaign": self.pause_campaign,
                "Meta Ads - Resume Campaign": self.resume_campaign,
                "Meta Ads - Get Conversions": self.get_conversions,
                "Meta Ads - Create Conversion Event": self.create_conversion_event,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Meta extension: {str(e)}")
        else:
            self.commands = {}

        # Initialize session for API requests
        self.session = requests.Session()
        if self.access_token:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                }
            )

    def verify_user(self):
        """Verify and refresh OAuth token using MagicalAuth"""
        if not self.auth:
            raise Exception("Authentication context not initialized.")

        try:
            # AGiXT's centralized OAuth token refresh
            refreshed_token = self.auth.refresh_oauth_token(provider="meta")
            if refreshed_token:
                self.access_token = refreshed_token
                self.session.headers.update(
                    {
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    }
                )
            else:
                logging.error("Failed to refresh OAuth token")
                raise Exception("Failed to refresh OAuth token")
        except Exception as e:
            logging.error(f"Error refreshing token: {str(e)}")
            raise

    async def _make_request(
        self, method: str, endpoint: str, params: Dict = None, data: Dict = None
    ) -> Dict:
        """Make authenticated request to Meta API with retry logic"""
        url = f"{self.base_url}/{endpoint}"

        # Add access token to params if not in headers
        if params is None:
            params = {}
        if self.access_token and "access_token" not in params:
            params["access_token"] = self.access_token

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if method.upper() == "GET":
                    response = self.session.get(url, params=params)
                elif method.upper() == "POST":
                    response = self.session.post(url, params=params, json=data)
                elif method.upper() == "DELETE":
                    response = self.session.delete(url, params=params)
                elif method.upper() == "PATCH":
                    response = self.session.patch(url, params=params, json=data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = (2**attempt) + 1
                    await asyncio.sleep(wait_time)
                    continue

                # Handle token expiration
                if response.status_code == 401:
                    if hasattr(self, "verify_user"):
                        self.verify_user()
                        # Update params with new token
                        if self.access_token:
                            params["access_token"] = self.access_token
                        continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    logging.error(
                        f"Request failed after {max_retries} attempts: {str(e)}"
                    )
                    raise e
                await asyncio.sleep(2**attempt)

        raise Exception("Max retries exceeded")

    async def get_ad_accounts(self) -> str:
        """
        Get all ad accounts accessible to the user

        Returns:
            str: JSON formatted list of ad accounts
        """
        try:
            response = await self._make_request(
                "GET",
                f"{self.business_id}/adaccounts",
                {
                    "fields": "id,name,account_status,currency,timezone_name,business,owner"
                },
            )

            accounts = response.get("data", [])
            if not accounts:
                return "No ad accounts found"

            return f"Found {len(accounts)} ad accounts:\n\n" + json.dumps(
                accounts, indent=2
            )

        except Exception as e:
            logging.error(f"Error getting ad accounts: {str(e)}")
            return f"Error retrieving ad accounts: {str(e)}"

    async def create_campaign(
        self, ad_account_id: str, name: str, objective: str, status: str = "PAUSED"
    ) -> str:
        """
        Create a new advertising campaign

        Args:
            ad_account_id (str): The ad account ID to create the campaign in
            name (str): Campaign name
            objective (str): Campaign objective (REACH, TRAFFIC, CONVERSIONS, etc.)
            status (str): Campaign status (ACTIVE, PAUSED)

        Returns:
            str: Campaign creation result with campaign ID
        """
        try:
            campaign_data = {
                "name": name,
                "objective": objective,
                "status": status,
                "special_ad_categories": [],
            }

            response = await self._make_request(
                "POST", f"{ad_account_id}/campaigns", data=campaign_data
            )

            campaign_id = response.get("id")
            if campaign_id:
                return f"Successfully created campaign '{name}' with ID: {campaign_id}"
            else:
                return f"Campaign creation failed: {response}"

        except Exception as e:
            logging.error(f"Error creating campaign: {str(e)}")
            return f"Error creating campaign: {str(e)}"

    async def get_campaigns(self, ad_account_id: str, status: str = "all") -> str:
        """
        Get campaigns from an ad account

        Args:
            ad_account_id (str): The ad account ID
            status (str): Filter by status (ACTIVE, PAUSED, DELETED, or all)

        Returns:
            str: JSON formatted list of campaigns
        """
        try:
            params = {
                "fields": "id,name,objective,status,created_time,updated_time,start_time,stop_time"
            }

            if status != "all":
                params["filtering"] = json.dumps(
                    [
                        {
                            "field": "campaign.effective_status",
                            "operator": "IN",
                            "value": [status],
                        }
                    ]
                )

            response = await self._make_request(
                "GET", f"{ad_account_id}/campaigns", params
            )

            campaigns = response.get("data", [])
            if not campaigns:
                return f"No campaigns found in ad account {ad_account_id}"

            return f"Found {len(campaigns)} campaigns:\n\n" + json.dumps(
                campaigns, indent=2
            )

        except Exception as e:
            logging.error(f"Error getting campaigns: {str(e)}")
            return f"Error retrieving campaigns: {str(e)}"

    async def update_campaign(self, campaign_id: str, **updates) -> str:
        """
        Update a campaign

        Args:
            campaign_id (str): The campaign ID to update
            **updates: Campaign fields to update (name, status, etc.)

        Returns:
            str: Update result
        """
        try:
            response = await self._make_request("PATCH", campaign_id, data=updates)

            if response.get("success"):
                return f"Successfully updated campaign {campaign_id}"
            else:
                return f"Campaign update failed: {response}"

        except Exception as e:
            logging.error(f"Error updating campaign: {str(e)}")
            return f"Error updating campaign: {str(e)}"

    async def delete_campaign(self, campaign_id: str) -> str:
        """
        Delete a campaign

        Args:
            campaign_id (str): The campaign ID to delete

        Returns:
            str: Deletion result
        """
        try:
            response = await self._make_request("DELETE", campaign_id)

            if response.get("success"):
                return f"Successfully deleted campaign {campaign_id}"
            else:
                return f"Campaign deletion failed: {response}"

        except Exception as e:
            logging.error(f"Error deleting campaign: {str(e)}")
            return f"Error deleting campaign: {str(e)}"

    async def create_ad_set(
        self,
        campaign_id: str,
        name: str,
        targeting: Dict,
        daily_budget: int,
        billing_event: str = "IMPRESSIONS",
        optimization_goal: str = "REACH",
    ) -> str:
        """
        Create an ad set within a campaign

        Args:
            campaign_id (str): The parent campaign ID
            name (str): Ad set name
            targeting (Dict): Targeting criteria
            daily_budget (int): Daily budget in cents
            billing_event (str): Billing event type
            optimization_goal (str): Optimization goal

        Returns:
            str: Ad set creation result
        """
        try:
            ad_set_data = {
                "name": name,
                "campaign_id": campaign_id,
                "targeting": targeting,
                "daily_budget": daily_budget,
                "billing_event": billing_event,
                "optimization_goal": optimization_goal,
                "status": "PAUSED",
            }

            response = await self._make_request(
                "POST", f"{campaign_id}/adsets", data=ad_set_data
            )

            ad_set_id = response.get("id")
            if ad_set_id:
                return f"Successfully created ad set '{name}' with ID: {ad_set_id}"
            else:
                return f"Ad set creation failed: {response}"

        except Exception as e:
            logging.error(f"Error creating ad set: {str(e)}")
            return f"Error creating ad set: {str(e)}"

    async def get_ad_sets(self, campaign_id: str) -> str:
        """
        Get ad sets from a campaign

        Args:
            campaign_id (str): The campaign ID

        Returns:
            str: JSON formatted list of ad sets
        """
        try:
            params = {
                "fields": "id,name,status,daily_budget,targeting,created_time,updated_time"
            }

            response = await self._make_request("GET", f"{campaign_id}/adsets", params)

            ad_sets = response.get("data", [])
            if not ad_sets:
                return f"No ad sets found in campaign {campaign_id}"

            return f"Found {len(ad_sets)} ad sets:\n\n" + json.dumps(ad_sets, indent=2)

        except Exception as e:
            logging.error(f"Error getting ad sets: {str(e)}")
            return f"Error retrieving ad sets: {str(e)}"

    async def update_ad_set(self, ad_set_id: str, **updates) -> str:
        """
        Update an ad set

        Args:
            ad_set_id (str): The ad set ID to update
            **updates: Ad set fields to update

        Returns:
            str: Update result
        """
        try:
            response = await self._make_request("PATCH", ad_set_id, data=updates)

            if response.get("success"):
                return f"Successfully updated ad set {ad_set_id}"
            else:
                return f"Ad set update failed: {response}"

        except Exception as e:
            logging.error(f"Error updating ad set: {str(e)}")
            return f"Error updating ad set: {str(e)}"

    async def create_ad(
        self, ad_set_id: str, name: str, creative_id: str, status: str = "PAUSED"
    ) -> str:
        """
        Create an ad within an ad set

        Args:
            ad_set_id (str): The parent ad set ID
            name (str): Ad name
            creative_id (str): The ad creative ID to use
            status (str): Ad status

        Returns:
            str: Ad creation result
        """
        try:
            ad_data = {
                "name": name,
                "adset_id": ad_set_id,
                "creative": {"creative_id": creative_id},
                "status": status,
            }

            response = await self._make_request(
                "POST", f"{ad_set_id}/ads", data=ad_data
            )

            ad_id = response.get("id")
            if ad_id:
                return f"Successfully created ad '{name}' with ID: {ad_id}"
            else:
                return f"Ad creation failed: {response}"

        except Exception as e:
            logging.error(f"Error creating ad: {str(e)}")
            return f"Error creating ad: {str(e)}"

    async def get_ads(self, ad_set_id: str) -> str:
        """
        Get ads from an ad set

        Args:
            ad_set_id (str): The ad set ID

        Returns:
            str: JSON formatted list of ads
        """
        try:
            params = {"fields": "id,name,status,creative,created_time,updated_time"}

            response = await self._make_request("GET", f"{ad_set_id}/ads", params)

            ads = response.get("data", [])
            if not ads:
                return f"No ads found in ad set {ad_set_id}"

            return f"Found {len(ads)} ads:\n\n" + json.dumps(ads, indent=2)

        except Exception as e:
            logging.error(f"Error getting ads: {str(e)}")
            return f"Error retrieving ads: {str(e)}"

    async def update_ad(self, ad_id: str, **updates) -> str:
        """
        Update an ad

        Args:
            ad_id (str): The ad ID to update
            **updates: Ad fields to update

        Returns:
            str: Update result
        """
        try:
            response = await self._make_request("PATCH", ad_id, data=updates)

            if response.get("success"):
                return f"Successfully updated ad {ad_id}"
            else:
                return f"Ad update failed: {response}"

        except Exception as e:
            logging.error(f"Error updating ad: {str(e)}")
            return f"Error updating ad: {str(e)}"

    async def get_campaign_insights(
        self,
        campaign_id: str,
        date_range: str = "last_7_days",
        metrics: List[str] = None,
    ) -> str:
        """
        Get performance insights for a campaign

        Args:
            campaign_id (str): The campaign ID
            date_range (str): Date range preset or custom range
            metrics (List[str]): List of metrics to retrieve

        Returns:
            str: JSON formatted campaign insights
        """
        try:
            if metrics is None:
                metrics = [
                    "impressions",
                    "clicks",
                    "spend",
                    "ctr",
                    "cpm",
                    "cpp",
                    "reach",
                    "frequency",
                ]

            params = {
                "fields": ",".join(metrics),
                "date_preset": date_range,
                "level": "campaign",
            }

            response = await self._make_request(
                "GET", f"{campaign_id}/insights", params
            )

            insights = response.get("data", [])
            if not insights:
                return f"No insights available for campaign {campaign_id}"

            return f"Campaign insights for {date_range}:\n\n" + json.dumps(
                insights, indent=2
            )

        except Exception as e:
            logging.error(f"Error getting campaign insights: {str(e)}")
            return f"Error retrieving campaign insights: {str(e)}"

    async def get_ad_set_insights(
        self, ad_set_id: str, date_range: str = "last_7_days", metrics: List[str] = None
    ) -> str:
        """
        Get performance insights for an ad set

        Args:
            ad_set_id (str): The ad set ID
            date_range (str): Date range preset
            metrics (List[str]): List of metrics to retrieve

        Returns:
            str: JSON formatted ad set insights
        """
        try:
            if metrics is None:
                metrics = [
                    "impressions",
                    "clicks",
                    "spend",
                    "ctr",
                    "cpm",
                    "cpp",
                    "reach",
                    "frequency",
                ]

            params = {
                "fields": ",".join(metrics),
                "date_preset": date_range,
                "level": "adset",
            }

            response = await self._make_request("GET", f"{ad_set_id}/insights", params)

            insights = response.get("data", [])
            if not insights:
                return f"No insights available for ad set {ad_set_id}"

            return f"Ad set insights for {date_range}:\n\n" + json.dumps(
                insights, indent=2
            )

        except Exception as e:
            logging.error(f"Error getting ad set insights: {str(e)}")
            return f"Error retrieving ad set insights: {str(e)}"

    async def get_ad_insights(
        self, ad_id: str, date_range: str = "last_7_days", metrics: List[str] = None
    ) -> str:
        """
        Get performance insights for an ad

        Args:
            ad_id (str): The ad ID
            date_range (str): Date range preset
            metrics (List[str]): List of metrics to retrieve

        Returns:
            str: JSON formatted ad insights
        """
        try:
            if metrics is None:
                metrics = [
                    "impressions",
                    "clicks",
                    "spend",
                    "ctr",
                    "cpm",
                    "cpp",
                    "reach",
                    "frequency",
                ]

            params = {
                "fields": ",".join(metrics),
                "date_preset": date_range,
                "level": "ad",
            }

            response = await self._make_request("GET", f"{ad_id}/insights", params)

            insights = response.get("data", [])
            if not insights:
                return f"No insights available for ad {ad_id}"

            return f"Ad insights for {date_range}:\n\n" + json.dumps(insights, indent=2)

        except Exception as e:
            logging.error(f"Error getting ad insights: {str(e)}")
            return f"Error retrieving ad insights: {str(e)}"

    async def create_custom_audience(
        self, ad_account_id: str, name: str, subtype: str, description: str = ""
    ) -> str:
        """
        Create a custom audience

        Args:
            ad_account_id (str): The ad account ID
            name (str): Audience name
            subtype (str): Audience subtype (CUSTOM, WEBSITE, etc.)
            description (str): Audience description

        Returns:
            str: Custom audience creation result
        """
        try:
            audience_data = {
                "name": name,
                "subtype": subtype,
                "description": description,
                "customer_file_source": "USER_PROVIDED_ONLY",
            }

            response = await self._make_request(
                "POST", f"{ad_account_id}/customaudiences", data=audience_data
            )

            audience_id = response.get("id")
            if audience_id:
                return f"Successfully created custom audience '{name}' with ID: {audience_id}"
            else:
                return f"Custom audience creation failed: {response}"

        except Exception as e:
            logging.error(f"Error creating custom audience: {str(e)}")
            return f"Error creating custom audience: {str(e)}"

    async def get_custom_audiences(self, ad_account_id: str) -> str:
        """
        Get custom audiences from an ad account

        Args:
            ad_account_id (str): The ad account ID

        Returns:
            str: JSON formatted list of custom audiences
        """
        try:
            params = {
                "fields": "id,name,description,subtype,approximate_count,data_source"
            }

            response = await self._make_request(
                "GET", f"{ad_account_id}/customaudiences", params
            )

            audiences = response.get("data", [])
            if not audiences:
                return f"No custom audiences found in ad account {ad_account_id}"

            return f"Found {len(audiences)} custom audiences:\n\n" + json.dumps(
                audiences, indent=2
            )

        except Exception as e:
            logging.error(f"Error getting custom audiences: {str(e)}")
            return f"Error retrieving custom audiences: {str(e)}"

    async def upload_audience_data(
        self, audience_id: str, data_list: List[Dict], data_type: str = "email"
    ) -> str:
        """
        Upload data to a custom audience

        Args:
            audience_id (str): The custom audience ID
            data_list (List[Dict]): List of customer data
            data_type (str): Type of data being uploaded

        Returns:
            str: Upload result
        """
        try:
            upload_data = {
                "payload": {
                    "schema": [data_type],
                    "data": [[item[data_type]] for item in data_list],
                }
            }

            response = await self._make_request(
                "POST", f"{audience_id}/users", data=upload_data
            )

            if response.get("num_received"):
                return f"Successfully uploaded {response['num_received']} records to audience {audience_id}"
            else:
                return f"Audience data upload failed: {response}"

        except Exception as e:
            logging.error(f"Error uploading audience data: {str(e)}")
            return f"Error uploading audience data: {str(e)}"

    async def create_lookalike_audience(
        self,
        ad_account_id: str,
        name: str,
        origin_audience_id: str,
        country: str,
        ratio: float = 0.01,
    ) -> str:
        """
        Create a lookalike audience based on a source audience

        Args:
            ad_account_id (str): The ad account ID
            name (str): Lookalike audience name
            origin_audience_id (str): Source audience ID
            country (str): Target country code
            ratio (float): Audience size ratio (0.01 to 0.20)

        Returns:
            str: Lookalike audience creation result
        """
        try:
            audience_data = {
                "name": name,
                "subtype": "LOOKALIKE",
                "origin_audience_id": origin_audience_id,
                "lookalike_spec": {
                    "type": "similarity",
                    "ratio": ratio,
                    "country": country,
                },
            }

            response = await self._make_request(
                "POST", f"{ad_account_id}/customaudiences", data=audience_data
            )

            audience_id = response.get("id")
            if audience_id:
                return f"Successfully created lookalike audience '{name}' with ID: {audience_id}"
            else:
                return f"Lookalike audience creation failed: {response}"

        except Exception as e:
            logging.error(f"Error creating lookalike audience: {str(e)}")
            return f"Error creating lookalike audience: {str(e)}"

    async def create_ad_creative(
        self, ad_account_id: str, name: str, object_story_spec: Dict
    ) -> str:
        """
        Create ad creative

        Args:
            ad_account_id (str): The ad account ID
            name (str): Creative name
            object_story_spec (Dict): Creative specification

        Returns:
            str: Creative creation result
        """
        try:
            creative_data = {"name": name, "object_story_spec": object_story_spec}

            response = await self._make_request(
                "POST", f"{ad_account_id}/adcreatives", data=creative_data
            )

            creative_id = response.get("id")
            if creative_id:
                return (
                    f"Successfully created ad creative '{name}' with ID: {creative_id}"
                )
            else:
                return f"Ad creative creation failed: {response}"

        except Exception as e:
            logging.error(f"Error creating ad creative: {str(e)}")
            return f"Error creating ad creative: {str(e)}"

    async def get_ad_creatives(self, ad_account_id: str) -> str:
        """
        Get ad creatives from an ad account

        Args:
            ad_account_id (str): The ad account ID

        Returns:
            str: JSON formatted list of ad creatives
        """
        try:
            params = {
                "fields": "id,name,status,object_story_spec,created_time,updated_time"
            }

            response = await self._make_request(
                "GET", f"{ad_account_id}/adcreatives", params
            )

            creatives = response.get("data", [])
            if not creatives:
                return f"No ad creatives found in ad account {ad_account_id}"

            return f"Found {len(creatives)} ad creatives:\n\n" + json.dumps(
                creatives, indent=2
            )

        except Exception as e:
            logging.error(f"Error getting ad creatives: {str(e)}")
            return f"Error retrieving ad creatives: {str(e)}"

    async def get_pages(self) -> str:
        """
        Get Facebook pages accessible to the user

        Returns:
            str: JSON formatted list of pages
        """
        try:
            params = {"fields": "id,name,category,link,picture,fan_count,is_published"}

            response = await self._make_request("GET", "me/accounts", params)

            pages = response.get("data", [])
            if not pages:
                return "No pages found"

            return f"Found {len(pages)} pages:\n\n" + json.dumps(pages, indent=2)

        except Exception as e:
            logging.error(f"Error getting pages: {str(e)}")
            return f"Error retrieving pages: {str(e)}"

    async def get_targeting_options(self, type: str, query: str = "") -> str:
        """
        Get targeting options for ad sets

        Args:
            type (str): Targeting type (interests, behaviors, etc.)
            query (str): Search query for targeting options

        Returns:
            str: JSON formatted targeting options
        """
        try:
            params = {"type": type, "limit": 25}

            if query:
                params["q"] = query

            response = await self._make_request("GET", "search", params)

            options = response.get("data", [])
            if not options:
                return f"No targeting options found for type '{type}'"

            return (
                f"Found {len(options)} targeting options for '{type}':\n\n"
                + json.dumps(options, indent=2)
            )

        except Exception as e:
            logging.error(f"Error getting targeting options: {str(e)}")
            return f"Error retrieving targeting options: {str(e)}"

    async def set_campaign_budget(
        self, campaign_id: str, daily_budget: int = None, lifetime_budget: int = None
    ) -> str:
        """
        Set campaign budget

        Args:
            campaign_id (str): The campaign ID
            daily_budget (int): Daily budget in cents
            lifetime_budget (int): Lifetime budget in cents

        Returns:
            str: Budget update result
        """
        try:
            budget_data = {}
            if daily_budget:
                budget_data["daily_budget"] = daily_budget
            if lifetime_budget:
                budget_data["lifetime_budget"] = lifetime_budget

            response = await self._make_request("PATCH", campaign_id, data=budget_data)

            if response.get("success"):
                return f"Successfully updated budget for campaign {campaign_id}"
            else:
                return f"Budget update failed: {response}"

        except Exception as e:
            logging.error(f"Error setting campaign budget: {str(e)}")
            return f"Error setting campaign budget: {str(e)}"

    async def pause_campaign(self, campaign_id: str) -> str:
        """
        Pause a campaign

        Args:
            campaign_id (str): The campaign ID to pause

        Returns:
            str: Pause result
        """
        try:
            response = await self._make_request(
                "PATCH", campaign_id, data={"status": "PAUSED"}
            )

            if response.get("success"):
                return f"Successfully paused campaign {campaign_id}"
            else:
                return f"Campaign pause failed: {response}"

        except Exception as e:
            logging.error(f"Error pausing campaign: {str(e)}")
            return f"Error pausing campaign: {str(e)}"

    async def resume_campaign(self, campaign_id: str) -> str:
        """
        Resume a paused campaign

        Args:
            campaign_id (str): The campaign ID to resume

        Returns:
            str: Resume result
        """
        try:
            response = await self._make_request(
                "PATCH", campaign_id, data={"status": "ACTIVE"}
            )

            if response.get("success"):
                return f"Successfully resumed campaign {campaign_id}"
            else:
                return f"Campaign resume failed: {response}"

        except Exception as e:
            logging.error(f"Error resuming campaign: {str(e)}")
            return f"Error resuming campaign: {str(e)}"

    async def get_conversions(
        self, ad_account_id: str, date_range: str = "last_7_days"
    ) -> str:
        """
        Get conversion data for an ad account

        Args:
            ad_account_id (str): The ad account ID
            date_range (str): Date range preset

        Returns:
            str: JSON formatted conversion data
        """
        try:
            params = {
                "fields": "conversions,conversion_values,cost_per_conversion",
                "date_preset": date_range,
                "level": "account",
            }

            response = await self._make_request(
                "GET", f"{ad_account_id}/insights", params
            )

            conversions = response.get("data", [])
            if not conversions:
                return f"No conversion data available for ad account {ad_account_id}"

            return f"Conversion data for {date_range}:\n\n" + json.dumps(
                conversions, indent=2
            )

        except Exception as e:
            logging.error(f"Error getting conversions: {str(e)}")
            return f"Error retrieving conversions: {str(e)}"

    async def create_conversion_event(
        self, pixel_id: str, event_name: str, event_data: Dict
    ) -> str:
        """
        Create a conversion event for tracking

        Args:
            pixel_id (str): The Facebook Pixel ID
            event_name (str): Name of the conversion event
            event_data (Dict): Event data and parameters

        Returns:
            str: Conversion event creation result
        """
        try:
            conversion_data = {
                "data": [
                    {
                        "event_name": event_name,
                        "event_time": int(datetime.now().timestamp()),
                        "action_source": "website",
                        **event_data,
                    }
                ]
            }

            response = await self._make_request(
                "POST", f"{pixel_id}/events", data=conversion_data
            )

            if response.get("events_received"):
                return f"Successfully created conversion event '{event_name}'"
            else:
                return f"Conversion event creation failed: {response}"

        except Exception as e:
            logging.error(f"Error creating conversion event: {str(e)}")
            return f"Error creating conversion event: {str(e)}"
