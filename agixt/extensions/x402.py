import logging
import asyncio
import os
from eth_account import Account
from Extensions import Extensions
from Globals import getenv
from typing import Optional, Dict, Any, List
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class x402(Extensions):
    """
    X402 extension for AGiXT enables interaction with x402-protected services
    using the x402 Payment Protocol. This extension allows agents to make payments
    to access protected resources, discover available services, and manage payment flows.
    
    Required parameters:
    - PRIVATE_KEY: Ethereum private key for signing payments
    - RESOURCE_SERVER_URL: Base URL of the x402-protected resource server
    - ENDPOINT_PATH: Default endpoint path to access on the resource server
    
    Optional parameters:
    - MAX_VALUE: Maximum allowed payment amount in base units
    - NETWORK_FILTER: Network to filter payment requirements (e.g., "base-sepolia")
    - SCHEME_FILTER: Payment scheme to filter by (e.g., "exact")
    """

    CATEGORY = "Payments & Web3"

    def __init__(self, PRIVATE_KEY: str, RESOURCE_SERVER_URL: str, ENDPOINT_PATH: str, MAX_VALUE: Optional[int] = None, NETWORK_FILTER: Optional[str] = None, SCHEME_FILTER: Optional[str] = None, **kwargs):
        """Initialize the x402 extension with required parameters"""
        
        # Validate required parameters
        if not PRIVATE_KEY:
            raise ValueError("PRIVATE_KEY is required for x402 extension")
        if not RESOURCE_SERVER_URL:
            raise ValueError("RESOURCE_SERVER_URL is required for x402 extension")
        if not ENDPOINT_PATH:
            raise ValueError("ENDPOINT_PATH is required for x402 extension")
        
        # Assign parameters
        self.private_key = PRIVATE_KEY
        self.resource_server_url = RESOURCE_SERVER_URL
        self.endpoint_path = ENDPOINT_PATH
        self.max_value = MAX_VALUE
        self.network_filter = NETWORK_FILTER
        self.scheme_filter = SCHEME_FILTER
        
        # Initialize eth_account from private key
        try:
            self.account = Account.from_key(private_key)
            logging.info(f"Initialized x402 account: {self.account.address}")
        except Exception as e:
            raise ValueError(f"Invalid private key: {str(e)}")
        
        # Define available commands
        self.commands = {
            "X402 - Make Payment Request": self.make_payment_request,
            "X402 - Discover Resources": self.discover_resources,
            "X402 - Get Account Info": self.get_account_info,
            "X402 - Custom Payment Request": self.custom_payment_request,
        }

    def _create_payment_selector(self, accepts, network_filter=None, scheme_filter=None, max_value=None):
        """Custom payment selector that filters by network and scheme"""
        # Use instance defaults if not provided
        network_filter = network_filter or self.network_filter
        scheme_filter = scheme_filter or self.scheme_filter
        max_value = max_value or self.max_value
        
        # Filter by network if specified
        if network_filter:
            accepts = [pr for pr in accepts if pr.network == network_filter]
        
        # Filter by scheme if specified
        if scheme_filter:
            accepts = [pr for pr in accepts if pr.scheme == scheme_filter]
        
        # Filter by max value if specified
        if max_value:
            accepts = [pr for pr in accepts if int(pr.max_amount_required) <= max_value]
        
        # Return the first available payment requirement or raise error
        if not accepts:
            raise Exception("No suitable payment requirements found with current filters")
        
        return accepts[0]

    async def make_payment_request(self, endpoint_path: Optional[str] = None) -> str:
        """
        Make a payment request to the configured resource server using default settings.
        
        Args:
            endpoint_path (str, optional): Custom endpoint path to access. Uses default if not provided.
            
        Returns:
            str: Response from the resource server or error message
        """
        try:
            target_endpoint = endpoint_path or self.endpoint_path
            
            # Import x402 client dynamically to avoid dependency issues
            try:
                from x402.clients.httpx import x402HttpxClient
                from x402.clients.base import decode_x_payment_response
            except ImportError:
                return "Error: x402 package not installed. Please install with: pip install x402"
            
            # Create x402 client with custom payment selector
            async with x402HttpxClient(
                account=self.account,
                base_url=self.resource_server_url,
                payment_requirements_selector=self._create_payment_selector,
            ) as client:
                # Make request - payment handling is automatic
                response = await client.get(target_endpoint)
                
                # Read the response content
                content = await response.aread()
                result = f"Response from {target_endpoint}: {content.decode()}"
                
                # Check for payment response header
                if "X-Payment-Response" in response.headers:
                    payment_response = decode_x_payment_response(
                        response.headers["X-Payment-Response"]
                    )
                    result += f"\nPayment response: Transaction {payment_response['transaction']} on {payment_response['network']}"
                else:
                    result += "\nWarning: No payment response header found"
                
                return result
                
        except Exception as e:
            logging.error(f"Error making payment request: {str(e)}")
            return f"Error making payment request: {str(e)}"

    async def custom_payment_request(self, endpoint_path: str, max_value: Optional[int] = None, network_filter: Optional[str] = None, scheme_filter: Optional[str] = None) -> str:
        """
        Make a custom payment request with specific parameters.
        
        Args:
            endpoint_path (str): Endpoint path to access
            max_value (int, optional): Maximum payment amount in base units
            network_filter (str, optional): Network to filter by (e.g., "base-sepolia")
            scheme_filter (str, optional): Payment scheme to filter by (e.g., "exact")
            
        Returns:
            str: Response from the resource server or error message
        """
        try:
            # Import x402 client dynamically
            try:
                from x402.clients.httpx import x402HttpxClient
                from x402.clients.base import decode_x_payment_response
            except ImportError:
                return "Error: x402 package not installed. Please install with: pip install x402"
            
            # Create custom payment selector
            def custom_selector(accepts, nf=None, sf=None, mv=None):
                return self._create_payment_selector(accepts, network_filter or nf, scheme_filter or sf, max_value or mv)
            
            # Create x402 client with custom selector
            async with x402HttpxClient(
                account=self.account,
                base_url=self.resource_server_url,
                payment_requirements_selector=custom_selector,
            ) as client:
                response = await client.get(endpoint_path)
                content = await response.aread()
                result = f"Response from {endpoint_path}: {content.decode()}"
                
                # Check for payment response header
                if "X-Payment-Response" in response.headers:
                    payment_response = decode_x_payment_response(
                        response.headers["X-Payment-Response"]
                    )
                    result += f"\nPayment response: Transaction {payment_response['transaction']} on {payment_response['network']}"
                
                return result
                
        except Exception as e:
            logging.error(f"Error making custom payment request: {str(e)}")
            return f"Error making custom payment request: {str(e)}"

    async def discover_resources(self) -> str:
        """
        Discover available x402-protected resources using the facilitator.
        
        Returns:
            str: List of available resources or error message
        """
        try:
            # Import discovery functionality
            try:
                from x402.facilitator import FacilitatorClient
            except ImportError:
                return "Error: x402 package not installed. Please install with: pip install x402"
            
            # This would typically require a facilitator URL
            # For now, we'll return a placeholder response
            return "Resource discovery functionality requires facilitator configuration. Please check x402 documentation for setup."
            
        except Exception as e:
            logging.error(f"Error discovering resources: {str(e)}")
            return f"Error discovering resources: {str(e)}"

    async def get_account_info(self) -> str:
        """
        Get information about the configured x402 account.
        
        Returns:
            str: Account information including address and balance details
        """
        try:
            account_info = {
                "address": self.account.address,
                "private_key_present": bool(self.private_key),
                "resource_server_url": self.resource_server_url,
                "default_endpoint_path": self.endpoint_path,
                "max_value": self.max_value,
                "network_filter": self.network_filter,
                "scheme_filter": self.scheme_filter
            }
            
            return f"X402 Account Information:\n{json.dumps(account_info, indent=2)}"
            
        except Exception as e:
            logging.error(f"Error getting account info: {str(e)}")
            return f"Error getting account info: {str(e)}"

# Helper function to create x402 extension instance
def create_x402_extension(private_key: str, resource_server_url: str, endpoint_path: str, max_value: Optional[int] = None, network_filter: Optional[str] = None, scheme_filter: Optional[str] = None) -> x402:
    """
    Helper function to create an x402 extension instance.
    
    Args:
        private_key (str): Ethereum private key for signing payments
        resource_server_url (str): Base URL of the x402-protected resource server
        endpoint_path (str): Default endpoint path to access on the resource server
        max_value (int, optional): Maximum allowed payment amount in base units
        network_filter (str, optional): Network to filter payment requirements
        scheme_filter (str, optional): Payment scheme to filter by
        
    Returns:
        x402: Configured x402 extension instance
    """
    return x402(
        PRIVATE_KEY=private_key,
        RESOURCE_SERVER_URL=resource_server_url,
        ENDPOINT_PATH=endpoint_path,
        MAX_VALUE=max_value,
        NETWORK_FILTER=network_filter,
        SCHEME_FILTER=scheme_filter
    )