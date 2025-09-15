import os
import logging
import requests
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
import base64
from typing import List, Dict, Optional
from fastapi import HTTPException


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
                    detail=f"Walmart token refresh failed: {response.text}",
                )

            token_data = response.json()

            # Update our access token for immediate use
            if "access_token" in token_data:
                self.access_token = token_data["access_token"]
            else:
                raise Exception("No access_token in Walmart refresh response")

            return token_data

        except HTTPException:
            # Re-raise HTTPException as-is
            raise
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


class walmart(Extensions):
    """
    The Walmart Marketplace extension provides integration with Walmart's seller APIs.
    This extension allows AI agents to:
    - Manage orders (get, acknowledge, cancel, refund)
    - Handle inventory updates
    - Manage product listings
    - Process reports
    - Handle returns

    The extension requires the user to be authenticated with Walmart Marketplace through OAuth.
    AI agents should use this when they need to interact with a seller's Walmart account
    for tasks like processing orders, updating inventory, or managing products.
    """

    CATEGORY = "E-commerce & Shopping"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("WALMART_ACCESS_TOKEN", None)
        walmart_client_id = getenv("WALMART_CLIENT_ID")
        walmart_client_secret = getenv("WALMART_CLIENT_SECRET")
        self.marketplace_id = getenv("WALMART_MARKETPLACE_ID")
        self.auth = None

        if walmart_client_id and walmart_client_secret:
            self.commands = {
                "Walmart - Get Orders": self.get_orders,
                "Walmart - Acknowledge Order": self.acknowledge_order,
                "Walmart - Cancel Order": self.cancel_order,
                "Walmart - Get Inventory": self.get_inventory,
                "Walmart - Update Inventory": self.update_inventory,
                "Walmart - Get Products": self.get_products,
                "Walmart - Update Product": self.update_product,
                "Walmart - Get Returns": self.get_returns,
                "Walmart - Process Return": self.process_return,
                "Walmart - Generate Report": self.generate_report,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Walmart client: {str(e)}")

    def verify_user(self):
        """
        Verifies that the current access token corresponds to a valid user.
        If verification fails, raises an exception.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="walmart")

        logging.info(f"Verifying user with token: {self.access_token}")
        headers = {
            "WM_SEC.ACCESS_TOKEN": self.access_token,
            "WM_SVC.NAME": "Walmart Marketplace",
            "WM_QOS.CORRELATION_ID": self.marketplace_id,
            "Accept": "application/json",
        }

        response = requests.get(
            "https://marketplace.walmartapis.com/v3/seller/info", headers=headers
        )

        if response.status_code != 200:
            raise Exception(
                f"User verification failed. Status: {response.status_code}, "
                f"Response: {response.text}"
            )

    async def get_orders(
        self,
        status: str = "Created",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Retrieves orders from Walmart Marketplace.

        Args:
            status (str): Order status filter (Created, Acknowledged, Shipped, Delivered)
            start_date (datetime): Start date for order search
            end_date (datetime): End date for order search
            limit (int): Maximum number of orders to retrieve

        Returns:
            list: List of order dictionaries
        """
        try:
            self.verify_user()

            if not start_date:
                start_date = datetime.now() - timedelta(days=7)
            if not end_date:
                end_date = datetime.now()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Accept": "application/json",
            }

            params = {
                "status": status,
                "createdStartDate": start_date.isoformat(),
                "createdEndDate": end_date.isoformat(),
                "limit": limit,
            }

            response = requests.get(
                "https://marketplace.walmartapis.com/v3/orders",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch orders: {response.text}")

            orders = []
            for order in response.json().get("elements", []):
                orders.append(
                    {
                        "purchase_order_id": order["purchaseOrderId"],
                        "customer_order_id": order["customerOrderId"],
                        "status": order["status"],
                        "order_date": order["orderDate"],
                        "shipping_info": order["shippingInfo"],
                        "order_lines": order["orderLines"]["orderLine"],
                    }
                )

            return orders

        except Exception as e:
            logging.error(f"Error retrieving orders: {str(e)}")
            return []

    async def acknowledge_order(self, purchase_order_id: str) -> str:
        """
        Acknowledges a Walmart Marketplace order.

        Args:
            purchase_order_id (str): The purchase order ID to acknowledge

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Content-Type": "application/json",
            }

            response = requests.post(
                f"https://marketplace.walmartapis.com/v3/orders/{purchase_order_id}/acknowledge",
                headers=headers,
            )

            if response.status_code == 204:
                return "Order acknowledged successfully."
            else:
                raise Exception(f"Failed to acknowledge order: {response.text}")

        except Exception as e:
            logging.error(f"Error acknowledging order: {str(e)}")
            return f"Failed to acknowledge order: {str(e)}"

    async def get_inventory(self, sku_list: List[str] = None) -> List[Dict]:
        """
        Gets inventory levels for specified SKUs.

        Args:
            sku_list (list): Optional list of SKUs to check inventory for

        Returns:
            list: List of inventory dictionaries
        """
        try:
            self.verify_user()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Accept": "application/json",
            }

            params = {}
            if sku_list:
                params["sku"] = ",".join(sku_list)

            response = requests.get(
                "https://marketplace.walmartapis.com/v3/inventory",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch inventory: {response.text}")

            inventory = []
            for item in response.json().get("elements", []):
                inventory.append(
                    {
                        "sku": item["sku"],
                        "quantity": item["quantity"],
                        "fulfillment_type": item.get(
                            "fulfillmentType", "Seller Fulfilled"
                        ),
                        "last_updated": item.get("lastUpdated"),
                    }
                )

            return inventory

        except Exception as e:
            logging.error(f"Error retrieving inventory: {str(e)}")
            return []

    async def update_inventory(self, sku: str, quantity: int) -> str:
        """
        Updates inventory quantity for a specific SKU.

        Args:
            sku (str): The SKU to update
            quantity (int): New quantity value

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Content-Type": "application/json",
            }

            data = {"sku": sku, "quantity": {"unit": "EACH", "amount": quantity}}

            response = requests.put(
                f"https://marketplace.walmartapis.com/v3/inventory",
                headers=headers,
                json=data,
            )

            if response.status_code == 200:
                return "Inventory updated successfully."
            else:
                raise Exception(f"Failed to update inventory: {response.text}")

        except Exception as e:
            logging.error(f"Error updating inventory: {str(e)}")
            return f"Failed to update inventory: {str(e)}"

    async def get_products(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        Retrieves product listings from Walmart Marketplace.

        Args:
            limit (int): Maximum number of products to retrieve
            offset (int): Number of products to skip

        Returns:
            list: List of product dictionaries
        """
        try:
            self.verify_user()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Accept": "application/json",
            }

            params = {"limit": limit, "offset": offset}

            response = requests.get(
                "https://marketplace.walmartapis.com/v3/items",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch products: {response.text}")

            products = []
            for item in response.json().get("items", []):
                products.append(
                    {
                        "sku": item["sku"],
                        "product_id": item.get("productId"),
                        "title": item.get("title"),
                        "price": item.get("price", {}).get("amount"),
                        "published": item.get("published", False),
                        "lifecycle_status": item.get("lifecycleStatus"),
                    }
                )

            return products

        except Exception as e:
            logging.error(f"Error retrieving products: {str(e)}")
            return []

    async def update_product(self, sku: str, updates: Dict) -> str:
        """
        Updates product information for a specific SKU.

        Args:
            sku (str): The SKU to update
            updates (dict): Dictionary of fields to update (price, quantity, etc.)

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Content-Type": "application/json",
            }

            # Structure the update data according to Walmart's API requirements
            data = {"sku": sku, **updates}

            response = requests.put(
                f"https://marketplace.walmartapis.com/v3/items/{sku}",
                headers=headers,
                json=data,
            )

            if response.status_code == 200:
                return "Product updated successfully."
            else:
                raise Exception(f"Failed to update product: {response.text}")

        except Exception as e:
            logging.error(f"Error updating product: {str(e)}")
            return f"Failed to update product: {str(e)}"

    async def get_returns(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Retrieves return requests from Walmart Marketplace.

        Args:
            start_date (datetime): Start date for returns search
            end_date (datetime): End date for returns search
            limit (int): Maximum number of returns to retrieve

        Returns:
            list: List of return dictionaries
        """
        try:
            self.verify_user()

            if not start_date:
                start_date = datetime.now() - timedelta(days=30)
            if not end_date:
                end_date = datetime.now()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Accept": "application/json",
            }

            params = {
                "createdStartDate": start_date.isoformat(),
                "createdEndDate": end_date.isoformat(),
                "limit": limit,
            }

            response = requests.get(
                "https://marketplace.walmartapis.com/v3/returns",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch returns: {response.text}")

            returns = []
            for return_item in response.json().get("returns", []):
                returns.append(
                    {
                        "return_order_id": return_item["returnOrderId"],
                        "customer_order_id": return_item["customerOrderId"],
                        "return_reason": return_item.get("returnReason"),
                        "status": return_item["status"],
                        "created_date": return_item["createdDate"],
                        "items": return_item.get("returnLineItems", []),
                    }
                )

            return returns

        except Exception as e:
            logging.error(f"Error retrieving returns: {str(e)}")
            return []

    async def process_return(
        self, return_order_id: str, action: str, refund_amount: Optional[float] = None
    ) -> str:
        """
        Processes a return request with specified action.

        Args:
            return_order_id (str): The return order ID to process
            action (str): Action to take (Accept, Reject, Refund)
            refund_amount (float): Optional refund amount if action is Refund

        Returns:
            str: Success or failure message
        """
        try:
            self.verify_user()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Content-Type": "application/json",
            }

            data = {"returnOrderId": return_order_id, "action": action}

            if refund_amount and action == "Refund":
                data["refundAmount"] = refund_amount

            response = requests.post(
                f"https://marketplace.walmartapis.com/v3/returns/{return_order_id}/actions",
                headers=headers,
                json=data,
            )

            if response.status_code == 200:
                return f"Return {action.lower()}ed successfully."
            else:
                raise Exception(f"Failed to process return: {response.text}")

        except Exception as e:
            logging.error(f"Error processing return: {str(e)}")
            return f"Failed to process return: {str(e)}"

    async def generate_report(
        self,
        report_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """
        Generates a Walmart Marketplace report.

        Args:
            report_type (str): Type of report to generate (Orders, Items, Returns)
            start_date (datetime): Start date for report
            end_date (datetime): End date for report

        Returns:
            str: Report ID or failure message
        """
        try:
            self.verify_user()

            if not start_date:
                start_date = datetime.now() - timedelta(days=30)
            if not end_date:
                end_date = datetime.now()

            headers = {
                "WM_SEC.ACCESS_TOKEN": self.access_token,
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self.marketplace_id,
                "Content-Type": "application/json",
            }

            data = {
                "reportType": report_type,
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
            }

            response = requests.post(
                "https://marketplace.walmartapis.com/v3/reports/generate",
                headers=headers,
                json=data,
            )

            if response.status_code == 200:
                report_id = response.json().get("reportId")
                return f"Report generated successfully. Report ID: {report_id}"
            else:
                raise Exception(f"Failed to generate report: {response.text}")

        except Exception as e:
            logging.error(f"Error generating report: {str(e)}")
            return f"Failed to generate report: {str(e)}"
