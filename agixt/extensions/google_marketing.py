import logging
import requests
import json
from typing import Dict, List, Any, Optional
from fastapi import HTTPException
from Extensions import Extensions
from MagicalAuth import MagicalAuth
from Globals import getenv


"""
Google Marketing Extension - Google Ads, Analytics, and Tag Manager access.

This extension provides comprehensive access to Google's marketing suite including:
- Google Ads: Campaign management, ad groups, keywords, performance metrics
- Google Analytics 4: Properties, reports, real-time data, audiences
- Google Tag Manager: Container management, tags, triggers, variables

It requires separate OAuth authorization from the main Google SSO connection.

Required environment variables:

- GOOGLE_CLIENT_ID: Google OAuth client ID
- GOOGLE_CLIENT_SECRET: Google OAuth client secret
- GOOGLE_ADS_CUSTOMER_ID: (Optional) Default Google Ads customer ID

Required APIs:
- Google Ads API: https://console.cloud.google.com/marketplace/product/google/googleads.googleapis.com
- Google Analytics Admin API: https://console.cloud.google.com/marketplace/product/google/analyticsadmin.googleapis.com
- Google Analytics Data API: https://console.cloud.google.com/marketplace/product/google/analyticsdata.googleapis.com
- Tag Manager API: https://console.cloud.google.com/marketplace/product/google/tagmanager.googleapis.com

Required scopes:
- adwords: Google Ads management
- analytics.readonly: GA4 data read
- analytics.edit: GA4 configuration
- tagmanager.edit.containers: GTM container editing
- tagmanager.publish: GTM publishing
- content: Merchant Center (optional)
"""

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics.edit",
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
    "https://www.googleapis.com/auth/content",
]
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
PKCE_REQUIRED = False


class GoogleMarketingSSO:
    """SSO handler for Google Marketing with Ads/Analytics/GTM scopes."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GOOGLE_CLIENT_ID")
        self.client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.email_address = None
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://oauth2.googleapis.com/token",
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
            raise Exception(f"Google Marketing token refresh failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            logging.error("No access_token in refresh response")

        return token_data

    def get_user_info(self):
        uri = "https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses"

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
            first_name = data["names"][0]["givenName"]
            last_name = data["names"][0]["familyName"]
            email = data["emailAddresses"][0]["value"]
            self.email_address = email
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error parsing Google user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Google",
            )


def sso(code, redirect_uri=None) -> GoogleMarketingSSO:
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
        "https://accounts.google.com/o/oauth2/token",
        params={
            "code": code,
            "client_id": getenv("GOOGLE_CLIENT_ID"),
            "client_secret": getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Google access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"] if "refresh_token" in data else None
    return GoogleMarketingSSO(access_token=access_token, refresh_token=refresh_token)


class google_marketing(Extensions):
    """
    Google Marketing Extension.

    This extension provides comprehensive access to Google's marketing tools:
    
    Google Ads:
    - Get accounts and campaigns
    - Create/update campaigns
    - Manage ad groups, ads, and keywords
    - Get performance metrics
    - Create audiences

    Google Analytics 4:
    - Get properties
    - Run reports
    - Get real-time data
    - Manage audiences and dimensions

    Google Tag Manager:
    - Get containers
    - Create/update tags
    - Create triggers and variables
    - Publish containers

    This extension requires separate authorization with marketing-specific scopes,
    independent from the basic Google SSO connection.
    """

    CATEGORY = "Marketing"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("GOOGLE_MARKETING_ACCESS_TOKEN", None)
        google_client_id = getenv("GOOGLE_CLIENT_ID")
        google_client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.google_ads_customer_id = getenv("GOOGLE_ADS_CUSTOMER_ID")
        self.auth = None

        self.session = requests.Session()
        if self.access_token:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                }
            )

        if google_client_id and google_client_secret:
            self.commands = {
                # Google Ads commands
                "Google Ads - Get Accounts": self.get_google_ads_accounts,
                "Google Ads - Create Campaign": self.create_google_ads_campaign,
                "Google Ads - Get Campaigns": self.get_google_ads_campaigns,
                "Google Ads - Update Campaign": self.update_google_ads_campaign,
                "Google Ads - Create Ad Group": self.create_google_ads_ad_group,
                "Google Ads - Get Ad Groups": self.get_google_ads_ad_groups,
                "Google Ads - Create Ad": self.create_google_ads_ad,
                "Google Ads - Get Performance": self.get_google_ads_performance,
                "Google Ads - Manage Keywords": self.manage_google_ads_keywords,
                "Google Ads - Create Audience": self.create_google_ads_audience,
                # Google Analytics commands
                "Google Analytics - Get Properties": self.get_analytics_properties,
                "Google Analytics - Get Reports": self.get_analytics_reports,
                "Google Analytics - Get Real Time Data": self.get_analytics_realtime,
                "Google Analytics - Get Audiences": self.get_analytics_audiences,
                "Google Analytics - Create Custom Dimension": self.create_analytics_dimension,
                # Google Tag Manager commands
                "GTM - Get Containers": self.get_gtm_containers,
                "GTM - Create Tag": self.create_gtm_tag,
                "GTM - Update Tag": self.update_gtm_tag,
                "GTM - Create Trigger": self.create_gtm_trigger,
                "GTM - Create Variable": self.create_gtm_variable,
                "GTM - Publish Container": self.publish_gtm_container,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Google Marketing: {str(e)}")

    def verify_user(self):
        """Verifies that the current access token is valid."""
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="google_marketing")
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                }
            )

    # ==================== GOOGLE ADS FUNCTIONS ====================

    async def get_google_ads_accounts(self) -> str:
        """
        Get all Google Ads accounts accessible to the user

        Returns:
            str: JSON formatted list of Google Ads accounts
        """
        try:
            self.verify_user()
            url = "https://googleads.googleapis.com/v15/customers:listAccessibleCustomers"
            response = self.session.get(url)

            if response.status_code == 200:
                accounts = response.json()
                return (
                    f"Found {len(accounts.get('resourceNames', []))} Google Ads accounts:\n\n"
                    + json.dumps(accounts, indent=2)
                )
            else:
                return f"Error retrieving Google Ads accounts: {response.text}"
        except Exception as e:
            logging.error(f"Error getting Google Ads accounts: {str(e)}")
            return f"Error retrieving Google Ads accounts: {str(e)}"

    async def create_google_ads_campaign(
        self,
        customer_id: str,
        name: str,
        budget_amount: int,
        advertising_channel_type: str = "SEARCH",
        status: str = "PAUSED",
    ) -> str:
        """
        Create a new Google Ads campaign

        Args:
            customer_id (str): The Google Ads customer ID
            name (str): Campaign name
            budget_amount (int): Daily budget in micros (e.g., 10000000 = $10)
            advertising_channel_type (str): Campaign type (SEARCH, DISPLAY, SHOPPING, VIDEO)
            status (str): Campaign status (ENABLED, PAUSED, REMOVED)

        Returns:
            str: Campaign creation result
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/campaigns:mutate"

            campaign_data = {
                "operations": [
                    {
                        "create": {
                            "name": name,
                            "status": status,
                            "advertisingChannelType": advertising_channel_type,
                            "campaignBudget": f"customers/{customer_id}/campaignBudgets/temp_budget_id",
                            "biddingStrategy": "MAXIMIZE_CONVERSIONS",
                        }
                    }
                ]
            }

            response = self.session.post(url, json=campaign_data)

            if response.status_code == 200:
                return f"Successfully created campaign '{name}'"
            else:
                return f"Campaign creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating Google Ads campaign: {str(e)}")
            return f"Error creating campaign: {str(e)}"

    async def get_google_ads_campaigns(self, customer_id: str) -> str:
        """
        Get campaigns from a Google Ads account

        Args:
            customer_id (str): The Google Ads customer ID

        Returns:
            str: JSON formatted list of campaigns
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/googleAds:search"

            query = {
                "query": """
                    SELECT campaign.id, campaign.name, campaign.status, 
                           campaign.advertising_channel_type, campaign_budget.amount_micros
                    FROM campaign 
                    ORDER BY campaign.id
                """
            }

            response = self.session.post(url, json=query)

            if response.status_code == 200:
                campaigns = response.json()
                return f"Google Ads campaigns:\n\n" + json.dumps(campaigns, indent=2)
            else:
                return f"Error retrieving campaigns: {response.text}"

        except Exception as e:
            logging.error(f"Error getting Google Ads campaigns: {str(e)}")
            return f"Error retrieving campaigns: {str(e)}"

    async def update_google_ads_campaign(
        self, customer_id: str, campaign_id: str, **updates
    ) -> str:
        """
        Update a Google Ads campaign

        Args:
            customer_id (str): The Google Ads customer ID
            campaign_id (str): The campaign ID to update
            **updates: Campaign fields to update

        Returns:
            str: Update result
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/campaigns:mutate"

            operation = {
                "operations": [
                    {"update": updates, "updateMask": ",".join(updates.keys())}
                ]
            }

            response = self.session.post(url, json=operation)

            if response.status_code == 200:
                return f"Successfully updated campaign {campaign_id}"
            else:
                return f"Campaign update failed: {response.text}"

        except Exception as e:
            logging.error(f"Error updating campaign: {str(e)}")
            return f"Error updating campaign: {str(e)}"

    async def create_google_ads_ad_group(
        self,
        customer_id: str,
        campaign_id: str,
        name: str,
        cpc_bid_micros: int = 1000000,
    ) -> str:
        """
        Create an ad group within a Google Ads campaign

        Args:
            customer_id (str): The Google Ads customer ID
            campaign_id (str): The parent campaign ID
            name (str): Ad group name
            cpc_bid_micros (int): CPC bid in micros

        Returns:
            str: Ad group creation result
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/adGroups:mutate"

            ad_group_data = {
                "operations": [
                    {
                        "create": {
                            "campaign": f"customers/{customer_id}/campaigns/{campaign_id}",
                            "name": name,
                            "status": "ENABLED",
                            "type": "SEARCH_STANDARD",
                            "cpcBidMicros": cpc_bid_micros,
                        }
                    }
                ]
            }

            response = self.session.post(url, json=ad_group_data)

            if response.status_code == 200:
                return f"Successfully created ad group '{name}'"
            else:
                return f"Ad group creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating ad group: {str(e)}")
            return f"Error creating ad group: {str(e)}"

    async def get_google_ads_ad_groups(self, customer_id: str, campaign_id: str) -> str:
        """
        Get ad groups from a Google Ads campaign

        Args:
            customer_id (str): The Google Ads customer ID
            campaign_id (str): The campaign ID

        Returns:
            str: JSON formatted list of ad groups
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/googleAds:search"

            query = {
                "query": f"""
                    SELECT ad_group.id, ad_group.name, ad_group.status, 
                           ad_group.cpc_bid_micros
                    FROM ad_group 
                    WHERE campaign.id = {campaign_id}
                """
            }

            response = self.session.post(url, json=query)

            if response.status_code == 200:
                ad_groups = response.json()
                return f"Ad groups:\n\n" + json.dumps(ad_groups, indent=2)
            else:
                return f"Error retrieving ad groups: {response.text}"

        except Exception as e:
            logging.error(f"Error getting ad groups: {str(e)}")
            return f"Error retrieving ad groups: {str(e)}"

    async def create_google_ads_ad(
        self,
        customer_id: str,
        ad_group_id: str,
        headlines: List[str],
        descriptions: List[str],
        final_urls: List[str],
    ) -> str:
        """
        Create a responsive search ad

        Args:
            customer_id (str): The Google Ads customer ID
            ad_group_id (str): The parent ad group ID
            headlines (List[str]): List of headline texts (max 30 chars each)
            descriptions (List[str]): List of description texts (max 90 chars each)
            final_urls (List[str]): Landing page URLs

        Returns:
            str: Ad creation result
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/ads:mutate"

            ad_data = {
                "operations": [
                    {
                        "create": {
                            "adGroup": f"customers/{customer_id}/adGroups/{ad_group_id}",
                            "status": "ENABLED",
                            "responsiveSearchAd": {
                                "headlines": [{"text": h} for h in headlines],
                                "descriptions": [{"text": d} for d in descriptions],
                            },
                            "finalUrls": final_urls,
                        }
                    }
                ]
            }

            response = self.session.post(url, json=ad_data)

            if response.status_code == 200:
                return "Successfully created responsive search ad"
            else:
                return f"Ad creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating ad: {str(e)}")
            return f"Error creating ad: {str(e)}"

    async def get_google_ads_performance(
        self, customer_id: str, date_range: str = "LAST_7_DAYS"
    ) -> str:
        """
        Get performance metrics for Google Ads campaigns

        Args:
            customer_id (str): The Google Ads customer ID
            date_range (str): Date range for metrics

        Returns:
            str: JSON formatted performance metrics
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/googleAds:search"

            query = {
                "query": f"""
                    SELECT campaign.name, metrics.impressions, metrics.clicks, 
                           metrics.cost_micros, metrics.conversions, metrics.ctr, 
                           metrics.average_cpc
                    FROM campaign 
                    WHERE segments.date DURING {date_range}
                """
            }

            response = self.session.post(url, json=query)

            if response.status_code == 200:
                performance = response.json()
                return f"Google Ads performance ({date_range}):\n\n" + json.dumps(
                    performance, indent=2
                )
            else:
                return f"Error retrieving performance: {response.text}"

        except Exception as e:
            logging.error(f"Error getting performance: {str(e)}")
            return f"Error retrieving performance: {str(e)}"

    async def manage_google_ads_keywords(
        self,
        customer_id: str,
        ad_group_id: str,
        keywords: List[Dict],
        action: str = "ADD",
    ) -> str:
        """
        Manage keywords for an ad group

        Args:
            customer_id (str): The Google Ads customer ID
            ad_group_id (str): The ad group ID
            keywords (List[Dict]): List of keyword dictionaries with 'text' and 'match_type'
            action (str): ADD, REMOVE, or UPDATE

        Returns:
            str: Keyword management result
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/keywordCriteria:mutate"

            operations = []
            for keyword in keywords:
                if action == "ADD":
                    operations.append(
                        {
                            "create": {
                                "adGroup": f"customers/{customer_id}/adGroups/{ad_group_id}",
                                "keyword": {
                                    "text": keyword["text"],
                                    "matchType": keyword.get("match_type", "BROAD"),
                                },
                                "status": "ENABLED",
                            }
                        }
                    )
                elif action == "REMOVE":
                    operations.append(
                        {
                            "remove": f"customers/{customer_id}/keywordCriteria/{keyword['id']}"
                        }
                    )

            response = self.session.post(url, json={"operations": operations})

            if response.status_code == 200:
                return f"Successfully {action.lower()}ed {len(keywords)} keywords"
            else:
                return f"Keyword operation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error managing keywords: {str(e)}")
            return f"Error managing keywords: {str(e)}"

    async def create_google_ads_audience(
        self, customer_id: str, name: str, description: str, members: List[Dict]
    ) -> str:
        """
        Create a custom audience for Google Ads

        Args:
            customer_id (str): The Google Ads customer ID
            name (str): Audience name
            description (str): Audience description
            members (List[Dict]): List of audience members

        Returns:
            str: Audience creation result
        """
        try:
            self.verify_user()
            url = f"https://googleads.googleapis.com/v15/customers/{customer_id}/userLists:mutate"

            audience_data = {
                "operations": [
                    {
                        "create": {
                            "name": name,
                            "description": description,
                            "membershipStatus": "OPEN",
                            "membershipLifeSpan": 540,
                            "crmBasedUserList": {
                                "uploadKeyType": "CONTACT_INFO",
                                "dataSourceType": "FIRST_PARTY",
                            },
                        }
                    }
                ]
            }

            response = self.session.post(url, json=audience_data)

            if response.status_code == 200:
                return f"Successfully created audience '{name}'"
            else:
                return f"Audience creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating audience: {str(e)}")
            return f"Error creating audience: {str(e)}"

    # ==================== GOOGLE ANALYTICS FUNCTIONS ====================

    async def get_analytics_properties(self) -> str:
        """
        Get all Google Analytics 4 properties accessible to the user

        Returns:
            str: JSON formatted list of GA4 properties
        """
        try:
            self.verify_user()
            url = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                properties = []
                for account in data.get("accountSummaries", []):
                    for property_summary in account.get("propertySummaries", []):
                        properties.append(
                            {
                                "property": property_summary.get("property"),
                                "displayName": property_summary.get("displayName"),
                                "propertyType": property_summary.get("propertyType"),
                                "parent": property_summary.get("parent"),
                            }
                        )

                return f"Found {len(properties)} GA4 properties:\n\n" + json.dumps(
                    properties, indent=2
                )
            else:
                return f"Error retrieving GA4 properties: {response.text}"
        except Exception as e:
            logging.error(f"Error getting GA4 properties: {str(e)}")
            return f"Error retrieving GA4 properties: {str(e)}"

    async def get_analytics_reports(
        self,
        property_id: str,
        start_date: str = "7daysAgo",
        end_date: str = "today",
        metrics: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
    ) -> str:
        """
        Get reports from Google Analytics 4

        Args:
            property_id (str): The GA4 property ID (e.g., "properties/123456")
            start_date (str): Start date (e.g., "2024-01-01" or "7daysAgo")
            end_date (str): End date (e.g., "2024-01-31" or "today")
            metrics (List[str]): List of metrics to retrieve
            dimensions (List[str]): List of dimensions to retrieve

        Returns:
            str: JSON formatted analytics report
        """
        try:
            self.verify_user()
            url = f"https://analyticsdata.googleapis.com/v1beta/{property_id}:runReport"

            if not metrics:
                metrics = [
                    "activeUsers",
                    "sessions",
                    "bounceRate",
                    "averageSessionDuration",
                    "screenPageViews",
                ]

            if not dimensions:
                dimensions = ["date", "country", "deviceCategory"]

            report_request = {
                "dateRanges": [{"startDate": start_date, "endDate": end_date}],
                "metrics": [{"name": metric} for metric in metrics],
                "dimensions": [{"name": dimension} for dimension in dimensions],
            }

            response = self.session.post(url, json=report_request)

            if response.status_code == 200:
                report = response.json()
                return f"GA4 Report ({start_date} to {end_date}):\n\n" + json.dumps(
                    report, indent=2
                )
            else:
                return f"Error retrieving GA4 report: {response.text}"

        except Exception as e:
            logging.error(f"Error getting GA4 reports: {str(e)}")
            return f"Error retrieving GA4 reports: {str(e)}"

    async def get_analytics_realtime(self, property_id: str) -> str:
        """
        Get real-time data from Google Analytics 4

        Args:
            property_id (str): The GA4 property ID

        Returns:
            str: JSON formatted real-time data
        """
        try:
            self.verify_user()
            url = f"https://analyticsdata.googleapis.com/v1beta/{property_id}:runRealtimeReport"

            realtime_request = {
                "metrics": [
                    {"name": "activeUsers"},
                    {"name": "screenPageViews"},
                    {"name": "eventCount"},
                ],
                "dimensions": [
                    {"name": "country"},
                    {"name": "deviceCategory"},
                    {"name": "unifiedPageScreen"},
                ],
            }

            response = self.session.post(url, json=realtime_request)

            if response.status_code == 200:
                realtime_data = response.json()
                return f"GA4 Real-time Data:\n\n" + json.dumps(realtime_data, indent=2)
            else:
                return f"Error retrieving real-time data: {response.text}"

        except Exception as e:
            logging.error(f"Error getting real-time data: {str(e)}")
            return f"Error retrieving real-time data: {str(e)}"

    async def get_analytics_audiences(self, property_id: str) -> str:
        """
        Get audiences from Google Analytics 4

        Args:
            property_id (str): The GA4 property ID

        Returns:
            str: JSON formatted list of audiences
        """
        try:
            self.verify_user()
            url = (
                f"https://analyticsadmin.googleapis.com/v1beta/{property_id}/audiences"
            )
            response = self.session.get(url)

            if response.status_code == 200:
                audiences = response.json()
                return f"GA4 Audiences:\n\n" + json.dumps(audiences, indent=2)
            else:
                return f"Error retrieving audiences: {response.text}"

        except Exception as e:
            logging.error(f"Error getting audiences: {str(e)}")
            return f"Error retrieving audiences: {str(e)}"

    async def create_analytics_dimension(
        self,
        property_id: str,
        display_name: str,
        scope: str = "EVENT",
        description: str = "",
    ) -> str:
        """
        Create a custom dimension in Google Analytics 4

        Args:
            property_id (str): The GA4 property ID
            display_name (str): Display name for the dimension
            scope (str): Scope of the dimension (EVENT or USER)
            description (str): Description of the dimension

        Returns:
            str: Dimension creation result
        """
        try:
            self.verify_user()
            url = f"https://analyticsadmin.googleapis.com/v1beta/{property_id}/customDimensions"

            dimension_data = {
                "displayName": display_name,
                "scope": scope,
                "description": description,
                "disallowAdsPersonalization": False,
            }

            response = self.session.post(url, json=dimension_data)

            if response.status_code == 200:
                return f"Successfully created custom dimension '{display_name}'"
            else:
                return f"Dimension creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating dimension: {str(e)}")
            return f"Error creating dimension: {str(e)}"

    # ==================== GOOGLE TAG MANAGER FUNCTIONS ====================

    async def get_gtm_containers(self) -> str:
        """
        Get all Google Tag Manager containers accessible to the user

        Returns:
            str: JSON formatted list of GTM containers
        """
        try:
            self.verify_user()
            url = "https://www.googleapis.com/tagmanager/v2/accounts"
            response = self.session.get(url)

            if response.status_code == 200:
                accounts = response.json()
                containers = []

                for account in accounts.get("account", []):
                    account_id = account.get("accountId")
                    container_url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers"
                    container_response = self.session.get(container_url)

                    if container_response.status_code == 200:
                        container_data = container_response.json()
                        for container in container_data.get("container", []):
                            containers.append(
                                {
                                    "accountId": account_id,
                                    "containerId": container.get("containerId"),
                                    "name": container.get("name"),
                                    "publicId": container.get("publicId"),
                                    "domainName": container.get("domainName", []),
                                    "usageContext": container.get("usageContext", []),
                                }
                            )

                return f"Found {len(containers)} GTM containers:\n\n" + json.dumps(
                    containers, indent=2
                )
            else:
                return f"Error retrieving GTM containers: {response.text}"

        except Exception as e:
            logging.error(f"Error getting GTM containers: {str(e)}")
            return f"Error retrieving GTM containers: {str(e)}"

    async def create_gtm_tag(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        name: str,
        type: str,
        parameter: List[Dict],
        firing_trigger_id: List[str],
    ) -> str:
        """
        Create a new tag in Google Tag Manager

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            name (str): Tag name
            type (str): Tag type (e.g., "ua", "ga4", "html")
            parameter (List[Dict]): Tag parameters
            firing_trigger_id (List[str]): List of trigger IDs

        Returns:
            str: Tag creation result
        """
        try:
            self.verify_user()
            url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}/tags"

            tag_data = {
                "name": name,
                "type": type,
                "parameter": parameter,
                "firingTriggerId": firing_trigger_id,
            }

            response = self.session.post(url, json=tag_data)

            if response.status_code == 200:
                tag = response.json()
                return f"Successfully created tag '{name}' with ID: {tag.get('tagId')}"
            else:
                return f"Tag creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating GTM tag: {str(e)}")
            return f"Error creating tag: {str(e)}"

    async def update_gtm_tag(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        tag_id: str,
        **updates,
    ) -> str:
        """
        Update an existing tag in Google Tag Manager

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            tag_id (str): Tag ID to update
            **updates: Tag fields to update

        Returns:
            str: Tag update result
        """
        try:
            self.verify_user()
            url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}/tags/{tag_id}"

            response = self.session.put(url, json=updates)

            if response.status_code == 200:
                return f"Successfully updated tag {tag_id}"
            else:
                return f"Tag update failed: {response.text}"

        except Exception as e:
            logging.error(f"Error updating GTM tag: {str(e)}")
            return f"Error updating tag: {str(e)}"

    async def create_gtm_trigger(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        name: str,
        type: str,
        custom_event_filter: Optional[List[Dict]] = None,
    ) -> str:
        """
        Create a new trigger in Google Tag Manager

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            name (str): Trigger name
            type (str): Trigger type (e.g., "pageview", "click", "customEvent")
            custom_event_filter (List[Dict]): Optional filters for the trigger

        Returns:
            str: Trigger creation result
        """
        try:
            self.verify_user()
            url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}/triggers"

            trigger_data = {
                "name": name,
                "type": type,
            }

            if custom_event_filter:
                trigger_data["customEventFilter"] = custom_event_filter

            response = self.session.post(url, json=trigger_data)

            if response.status_code == 200:
                trigger = response.json()
                return f"Successfully created trigger '{name}' with ID: {trigger.get('triggerId')}"
            else:
                return f"Trigger creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating GTM trigger: {str(e)}")
            return f"Error creating trigger: {str(e)}"

    async def create_gtm_variable(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        name: str,
        type: str,
        parameter: Optional[List[Dict]] = None,
    ) -> str:
        """
        Create a new variable in Google Tag Manager

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            name (str): Variable name
            type (str): Variable type (e.g., "jsm", "v", "c")
            parameter (List[Dict]): Variable parameters

        Returns:
            str: Variable creation result
        """
        try:
            self.verify_user()
            url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}/variables"

            variable_data = {
                "name": name,
                "type": type,
            }

            if parameter:
                variable_data["parameter"] = parameter

            response = self.session.post(url, json=variable_data)

            if response.status_code == 200:
                variable = response.json()
                return f"Successfully created variable '{name}' with ID: {variable.get('variableId')}"
            else:
                return f"Variable creation failed: {response.text}"

        except Exception as e:
            logging.error(f"Error creating GTM variable: {str(e)}")
            return f"Error creating variable: {str(e)}"

    async def publish_gtm_container(
        self,
        account_id: str,
        container_id: str,
        workspace_id: str,
        version_name: str,
        notes: str = "",
    ) -> str:
        """
        Publish a Google Tag Manager container version

        Args:
            account_id (str): GTM account ID
            container_id (str): GTM container ID
            workspace_id (str): GTM workspace ID
            version_name (str): Version name for the publication
            notes (str): Optional notes for the version

        Returns:
            str: Publication result
        """
        try:
            self.verify_user()
            version_url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}:create_version"

            version_data = {
                "name": version_name,
                "notes": notes,
            }

            version_response = self.session.post(version_url, json=version_data)

            if version_response.status_code == 200:
                version = version_response.json()
                version_id = version.get("containerVersion", {}).get(
                    "containerVersionId"
                )

                publish_url = f"https://www.googleapis.com/tagmanager/v2/accounts/{account_id}/containers/{container_id}/versions/{version_id}:publish"

                publish_response = self.session.post(publish_url)

                if publish_response.status_code == 200:
                    return f"Successfully published container version '{version_name}'"
                else:
                    return f"Publication failed: {publish_response.text}"
            else:
                return f"Version creation failed: {version_response.text}"

        except Exception as e:
            logging.error(f"Error publishing GTM container: {str(e)}")
            return f"Error publishing container: {str(e)}"
