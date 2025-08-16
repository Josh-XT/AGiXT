import os
import json
import base64
import requests
from typing import Dict, Any, Optional, List, Union
from Extensions import Extensions
import logging


class bags_fm(Extensions):
    """
    The Bags.fm extension enables interaction with the Bags.fm API for Solana token operations.

    This extension provides functionality for:
    - Token launches with metadata and initial purchases
    - Fee sharing configuration between wallets
    - Analytics for token lifetime fees and creators
    - Fee claiming from various sources
    """

    def __init__(
        self,
        BAGS_FM_API_KEY: str = "",
        **kwargs,
    ):
        self.BAGS_FM_API_KEY = BAGS_FM_API_KEY
        self.BASE_URL = "https://public-api-v2.bags.fm/api/v1"

        # Set up headers with API key authentication
        self.headers = {}
        if self.BAGS_FM_API_KEY:
            self.headers["x-api-key"] = self.BAGS_FM_API_KEY

        self.commands = {
            "Create Token Info and Metadata": self.create_token_info,
            "Create Token Launch Configuration": self.create_token_launch_configuration,
            "Create Token Launch Transaction": self.create_token_launch_transaction,
            "Get Fee Share Wallet": self.get_fee_share_wallet,
            "Create Fee Share Configuration": self.create_fee_share_configuration,
            "Get Token Lifetime Fees": self.get_token_lifetime_fees,
            "Get Token Launch Creators": self.get_token_launch_creators,
            "Get Claim Transactions": self.get_claim_transactions,
            "Upload Token Image": self.upload_token_image,
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        files: Optional[Dict] = None,
        require_auth: bool = True,
    ) -> Dict[str, Any]:
        """
        Make a request to the Bags.fm API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters
            files: Files to upload
            require_auth: Whether authentication is required

        Returns:
            API response as dictionary
        """
        url = f"{self.BASE_URL}/{endpoint}"

        headers = self.headers.copy() if require_auth else {}

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                if files:
                    response = requests.post(
                        url, headers=headers, data=data, files=files
                    )
                else:
                    headers["Content-Type"] = "application/json"
                    response = requests.post(url, headers=headers, json=data)
            else:
                return {"success": False, "error": f"Unsupported HTTP method: {method}"}

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "success": False,
                    "error": f"API request failed with status {response.status_code}: {response.text}",
                }
        except Exception as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}

    async def create_token_info(
        self,
        name: str,
        symbol: str,
        description: str = "",
        image: str = "",
        twitter: str = "",
        telegram: str = "",
        website: str = "",
        is_mutable: bool = False,
    ) -> str:
        """
        Create token info and metadata for a new token launch.

        Args:
            name: Token name (e.g., "My Token")
            symbol: Token symbol (e.g., "MTK")
            description: Token description
            image: Base64 encoded image or URL
            twitter: Twitter/X handle or URL
            telegram: Telegram group URL
            website: Project website URL
            is_mutable: Whether metadata can be changed after creation

        Returns:
            JSON response with token metadata URI and other details
        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        data = {
            "name": name,
            "symbol": symbol,
            "description": description,
            "image": image,
            "showName": True,
            "createdOn": "bags.fm",
            "isMutable": is_mutable,
        }

        # Add social links if provided
        if twitter:
            data["twitter"] = twitter
        if telegram:
            data["telegram"] = telegram
        if website:
            data["website"] = website

        result = self._make_request("POST", "token-launch/create-token-info", data=data)
        return json.dumps(result, indent=2)

    async def create_token_launch_configuration(
        self,
        token_name: str,
        token_symbol: str,
        token_decimals: int = 6,
        initial_buy_sol: float = 0,
        slippage_bps: int = 500,
        priority_fee_lamports: int = 100000,
        creator_wallet: str = "",
        fee_share_wallet: str = "",
    ) -> str:
        """
        Create a token launch configuration transaction.

        Args:
            token_name: Name of the token
            token_symbol: Symbol of the token
            token_decimals: Number of decimals (default 6)
            initial_buy_sol: Amount of SOL for initial purchase
            slippage_bps: Slippage in basis points (100 = 1%)
            priority_fee_lamports: Priority fee for transaction
            creator_wallet: Creator's wallet address (Base58)
            fee_share_wallet: Optional fee share wallet address

        Returns:
            JSON response with serialized transaction
        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        data = {
            "tokenName": token_name,
            "tokenSymbol": token_symbol,
            "tokenDecimals": token_decimals,
            "initialBuySol": initial_buy_sol,
            "slippageBps": slippage_bps,
            "priorityFeeLamports": priority_fee_lamports,
            "creatorWallet": creator_wallet,
        }

        if fee_share_wallet:
            data["feeShareWallet"] = fee_share_wallet

        result = self._make_request("POST", "token-launch/create-config", data=data)
        return json.dumps(result, indent=2)

    async def create_token_launch_transaction(
        self,
        creator_wallet: str,
        token_name: str,
        token_symbol: str,
        token_uri: str,
        token_decimals: int = 6,
        initial_buy_sol: float = 0,
        slippage_bps: int = 500,
        priority_fee_lamports: int = 100000,
        token_launch_config: str = "",
        fee_share_config: str = "",
    ) -> str:
        """
        Create a complete token launch transaction.

        Args:
            creator_wallet: Creator's wallet address (Base58)
            token_name: Name of the token
            token_symbol: Symbol of the token
            token_uri: Metadata URI for the token
            token_decimals: Number of decimals (default 6)
            initial_buy_sol: Amount of SOL for initial purchase
            slippage_bps: Slippage in basis points
            priority_fee_lamports: Priority fee for transaction
            token_launch_config: Optional pre-existing launch config address
            fee_share_config: Optional fee share configuration address

        Returns:
            JSON response with serialized transaction and mint address
        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        data = {
            "creatorWallet": creator_wallet,
            "tokenName": token_name,
            "tokenSymbol": token_symbol,
            "tokenUri": token_uri,
            "tokenDecimals": token_decimals,
            "initialBuySol": initial_buy_sol,
            "slippageBps": slippage_bps,
            "priorityFeeLamports": priority_fee_lamports,
        }

        if token_launch_config:
            data["tokenLaunchConfig"] = token_launch_config
        if fee_share_config:
            data["feeShareConfig"] = fee_share_config

        result = self._make_request("POST", "token-launch/create", data=data)
        return json.dumps(result, indent=2)

    async def get_fee_share_wallet(
        self, primary_wallet: str, secondary_wallet: str
    ) -> str:
        """
        Get the fee share wallet address for two wallets.

        Args:
            primary_wallet: Primary wallet address (Base58)
            secondary_wallet: Secondary wallet address (Base58)

        Returns:
            JSON response with fee share wallet address
        """
        params = {"primaryWallet": primary_wallet, "secondaryWallet": secondary_wallet}

        # This endpoint might not require authentication based on docs
        result = self._make_request(
            "GET", "fee-share/wallet", params=params, require_auth=False
        )
        return json.dumps(result, indent=2)

    async def create_fee_share_configuration(
        self,
        primary_wallet: str,
        secondary_wallet: str,
        primary_share_bps: int = 5000,
        secondary_share_bps: int = 5000,
    ) -> str:
        """
        Create a fee share configuration transaction.

        Args:
            primary_wallet: Primary wallet address (Base58)
            secondary_wallet: Secondary wallet address (Base58)
            primary_share_bps: Primary wallet share in basis points (5000 = 50%)
            secondary_share_bps: Secondary wallet share in basis points

        Returns:
            JSON response with serialized transaction
        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        # Validate shares add up to 10000 (100%)
        if primary_share_bps + secondary_share_bps != 10000:
            return json.dumps(
                {
                    "success": False,
                    "error": "Primary and secondary shares must add up to 10000 basis points (100%)",
                }
            )

        data = {
            "primaryWallet": primary_wallet,
            "secondaryWallet": secondary_wallet,
            "primaryShareBps": primary_share_bps,
            "secondaryShareBps": secondary_share_bps,
        }

        result = self._make_request("POST", "fee-share/create-config", data=data)
        return json.dumps(result, indent=2)

    async def get_token_lifetime_fees(self, token_mint: str) -> str:
        """
        Get the lifetime fees collected for a token.

        Args:
            token_mint: Token mint address (Base58)

        Returns:
            JSON response with lifetime fees in lamports
        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        params = {"tokenMint": token_mint}

        result = self._make_request("GET", "token-launch/lifetime-fees", params=params)

        # Convert lamports to SOL if successful
        if result.get("success") and result.get("response"):
            try:
                lamports = int(result["response"])
                sol_amount = lamports / 1_000_000_000
                result["response_sol"] = f"{sol_amount:.9f} SOL"
                result["response_lamports"] = result["response"]
            except (ValueError, TypeError):
                pass

        return json.dumps(result, indent=2)

    async def get_token_launch_creators(self, token_mint: str) -> str:
        """
        Get the creators/launchers of a token.

        Args:
            token_mint: Token mint address (Base58)

        Returns:
            JSON response with creator information
        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        params = {"tokenMint": token_mint}

        result = self._make_request("GET", "token-launch/creators", params=params)
        return json.dumps(result, indent=2)

    async def get_claim_transactions(
        self, wallet_address: str, claim_type: str = "all"
    ) -> str:
        """
        Get transactions to claim fees from various sources.

        Args:
            wallet_address: Wallet address to claim fees for (Base58)
            claim_type: Type of fees to claim ("all", "creator", "holder", "referral")

        Returns:
            JSON response with serialized claim transactions
        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        valid_claim_types = ["all", "creator", "holder", "referral"]
        if claim_type not in valid_claim_types:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Invalid claim type. Must be one of: {', '.join(valid_claim_types)}",
                }
            )

        data = {"walletAddress": wallet_address, "claimType": claim_type}

        result = self._make_request(
            "POST", "fee-claiming/get-claim-transactions", data=data
        )
        return json.dumps(result, indent=2)

    async def upload_token_image(self, image_path: str) -> str:
        """
        Upload an image file for use as token metadata.

        Args:
            image_path: Path to the image file to upload

        Returns:
            JSON response with the uploaded image URL or base64 data
        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        if not os.path.exists(image_path):
            return json.dumps(
                {"success": False, "error": f"Image file not found: {image_path}"}
            )

        try:
            # Read and encode the image file
            with open(image_path, "rb") as image_file:
                image_data = image_file.read()

            # Check file size (limit to 5MB for safety)
            if len(image_data) > 5 * 1024 * 1024:
                return json.dumps(
                    {"success": False, "error": "Image file too large (max 5MB)"}
                )

            # Detect file type
            file_extension = os.path.splitext(image_path)[1].lower()
            if file_extension not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                return json.dumps(
                    {"success": False, "error": "Unsupported image format"}
                )

            # Try uploading as multipart form data first
            files = {
                "image": (
                    os.path.basename(image_path),
                    image_data,
                    f"image/{file_extension[1:]}",
                )
            }
            result = self._make_request(
                "POST", "token-launch/upload-image", files=files
            )

            # If that doesn't work, return base64 encoded data
            if not result.get("success"):
                image_base64 = base64.b64encode(image_data).decode("utf-8")
                mime_type = f"image/{file_extension[1:]}"
                data_uri = f"data:{mime_type};base64,{image_base64}"

                return json.dumps(
                    {
                        "success": True,
                        "response": {
                            "imageUri": data_uri,
                            "format": "base64",
                            "size": len(image_data),
                            "mimeType": mime_type,
                        },
                    }
                )

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps(
                {"success": False, "error": f"Failed to upload image: {str(e)}"}
            )
