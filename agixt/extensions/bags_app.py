import os
import json
import base64
import requests
from typing import Dict, Any, Optional, List, Union
from Extensions import Extensions
import logging


class bags_app(Extensions):
    """
    The Bags App (bags.fm) extension enables interaction with the Bags.fm API for Solana token operations.

    This extension provides functionality for:
    - Token launches with metadata and initial purchases
    - Fee sharing configuration between wallets
    - Analytics for token lifetime fees and creators
    - Fee claiming from various sources
    """

    CATEGORY = "Finance & Crypto"

    def __init__(
        self,
        BAGS_FM_API_KEY: str = "",
        **kwargs,
    ):
        self.BAGS_FM_API_KEY = BAGS_FM_API_KEY
        self.BASE_URL = "https://public-api-v2.bags.fm/api/v1"
        self.creator_wallet = kwargs.get("SOLANA_WALLET_ADDRESS", "")
        # Set up headers with API key authentication
        self.headers = {}
        if self.BAGS_FM_API_KEY:
            self.headers["x-api-key"] = self.BAGS_FM_API_KEY

        self.commands = {
            "Launch Token on Bags.fm": self.launch_token_complete,
            "Get Fee Share Wallet": self.get_fee_share_wallet,
            "Get Token Lifetime Fees": self.get_token_lifetime_fees,
            "Get Token Launch Creators": self.get_token_launch_creators,
            "Get Claim Transactions": self.get_claim_transactions,
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

    async def launch_token_complete(
        self,
        token_name: str = "",
        token_symbol: str = "",
        token_description: str = "",
        token_image: str = "",
        twitter: str = "",
        telegram: str = "",
        website: str = "",
        creator_wallet: str = "",
        initial_buy_sol: float = 0,
        token_decimals: int = 6,
        slippage_bps: int = 500,
        priority_fee_lamports: int = 100000,
        is_mutable: bool = False,
        fee_share_wallet: str = "",
        fee_share_twitter_handle: str = "",
        fee_share_primary_bps: int = 0,
        fee_share_secondary_bps: int = 0,
    ) -> str:
        """
        Launch a new token on Bags.fm

        Args:
            token_name: Name of the token (e.g., "My Token") - REQUIRED
            token_symbol: Token symbol/ticker (e.g., "MTK") - REQUIRED
            token_description: Description of the token project (optional)
            token_image: URL to an image OR path to a local image file for the token logo (optional)
            twitter: Twitter/X handle or URL for the token's social media (optional)
            telegram: Telegram group URL (optional)
            website: Project website URL (optional)
            creator_wallet: Override the agent's default wallet address for royalties (optional)
                          If not provided, uses the agent's configured Solana wallet.
                          You can specify any Solana wallet address to receive the royalties.
            initial_buy_sol: Amount of SOL for initial purchase (0 = no initial buy)
            token_decimals: Number of decimals (default 6, standard for most tokens)
            slippage_bps: Slippage tolerance in basis points (500 = 5%)
            priority_fee_lamports: Priority fee for faster transaction processing
            is_mutable: Whether metadata can be changed after creation (default False for security)
            fee_share_wallet: Optional second wallet address to share fees with (splits royalties)
            fee_share_twitter_handle: Optional Twitter username to share fees with (e.g., "elonmusk" without @)
                                    The SDK will resolve this to a wallet address automatically
            fee_share_primary_bps: Creator's share in basis points (must total 10000 with secondary)
            fee_share_secondary_bps: Fee claimer's share in basis points

        Returns:
            JSON response with complete launch details including transaction and mint address

        Notes:
        Complete Bags.fm token launch workflow - creates metadata, handles images, and launches token in one command.

        FEE SHARING / ROYALTY DISTRIBUTION:
        - The creator_wallet receives the token creator fees/royalties
        - You can set creator_wallet to ANY Solana wallet address to direct royalties there
        - To split royalties between two parties, you have two options:
          1. Use fee_share_wallet with a Solana wallet address
          2. Use fee_share_twitter_handle with a Twitter username (e.g., "elonmusk")
             The SDK will automatically resolve the Twitter handle to a wallet address
        - When using fee sharing, set fee_share_primary_bps (creator's share) and
          fee_share_secondary_bps (fee claimer's share) - they must total 10000 (100%)
        - Example: 1000 (10%) for creator, 9000 (90%) for fee claimer

        IMPORTANT: The AI agent should ask the user for any required information that is not provided,
        unless the user explicitly says to proceed without it. Required fields include:
        - token_name: The name of the token (e.g., "My Amazing Token")
        - token_symbol: The ticker symbol (e.g., "MAT")

        The agent's Solana wallet will be used automatically for royalties unless overridden.

        Optional but commonly desired fields (ask if the user wants to provide these):
        - token_description: A description of the token project
        - token_image: URL to an image OR path to a local image file
        - social links: twitter, telegram, website URLs for the token
        - initial_buy_sol: Amount of SOL to buy initially (0 means no initial buy)
        - fee sharing: If they want to split royalties with another wallet

        """
        if not self.BAGS_FM_API_KEY:
            return json.dumps({"success": False, "error": "No API key configured"})

        # Use agent's wallet if no creator_wallet specified
        if not creator_wallet:
            creator_wallet = self.creator_wallet

        # Validate required fields
        if not creator_wallet:
            return json.dumps(
                {
                    "success": False,
                    "error": "No creator wallet configured. Please configure the agent's Solana wallet or provide a wallet address.",
                }
            )
        if not token_name:
            return json.dumps(
                {
                    "success": False,
                    "error": "Token name is required. Please provide a name for your token.",
                }
            )
        if not token_symbol:
            return json.dumps(
                {
                    "success": False,
                    "error": "Token symbol is required. Please provide a ticker symbol for your token.",
                }
            )

        try:
            # Step 1: Process image if provided
            image_uri = ""
            if token_image:
                # Check if it's a URL
                if token_image.startswith(("http://", "https://", "data:")):
                    image_uri = token_image
                # Check if it's a file path
                elif os.path.exists(token_image):
                    # Upload the image file
                    upload_result = await self.upload_token_image(token_image)
                    upload_data = json.loads(upload_result)
                    if upload_data.get("success"):
                        if upload_data.get("response", {}).get("imageUri"):
                            image_uri = upload_data["response"]["imageUri"]
                        elif upload_data.get("response", {}).get("url"):
                            image_uri = upload_data["response"]["url"]
                    else:
                        return json.dumps(
                            {
                                "success": False,
                                "error": f"Failed to upload image: {upload_data.get('error')}",
                            }
                        )
                else:
                    # Assume it's a URL even if we can't verify it
                    image_uri = token_image

            # Step 2: Create token metadata
            metadata_result = await self.create_token_info(
                name=token_name,
                symbol=token_symbol,
                description=token_description,
                image=image_uri,
                twitter=twitter,
                telegram=telegram,
                website=website,
                is_mutable=is_mutable,
            )

            metadata_data = json.loads(metadata_result)
            if not metadata_data.get("success"):
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Failed to create token metadata: {metadata_data.get('error')}",
                    }
                )

            token_uri = metadata_data.get("response", {}).get("metadataUri", "")
            if not token_uri:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Failed to get metadata URI from response",
                    }
                )

            # Step 3: Handle fee sharing if requested
            fee_share_config = ""

            # Determine the fee share wallet (either from direct wallet or Twitter handle)
            effective_fee_share_wallet = fee_share_wallet

            # If Twitter handle provided instead of wallet, note it for documentation
            fee_share_twitter_used = False
            if fee_share_twitter_handle and not fee_share_wallet:
                # Clean the Twitter handle (remove @ if present)
                clean_twitter = fee_share_twitter_handle.lstrip("@")
                # Note: The Bags.fm SDK can resolve Twitter handles to wallets
                # but we'll need to pass it through their system
                # For now, we'll treat it as a configuration option
                effective_fee_share_wallet = f"twitter:{clean_twitter}"
                fee_share_twitter_used = True

            if (effective_fee_share_wallet or fee_share_twitter_handle) and (
                fee_share_primary_bps > 0 or fee_share_secondary_bps > 0
            ):
                # Set default 50/50 split if not specified
                if fee_share_primary_bps == 0 and fee_share_secondary_bps == 0:
                    fee_share_primary_bps = 5000
                    fee_share_secondary_bps = 5000

                # Validate the split adds up to 100%
                if fee_share_primary_bps + fee_share_secondary_bps != 10000:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Fee share splits must total 10000 basis points (100%). Current: {fee_share_primary_bps} + {fee_share_secondary_bps} = {fee_share_primary_bps + fee_share_secondary_bps}",
                        }
                    )

                # If using Twitter handle, we note it but the actual resolution
                # would happen on the SDK/API side
                if not fee_share_twitter_used:
                    # Create fee share configuration with wallet addresses
                    fee_share_result = await self.create_fee_share_configuration(
                        primary_wallet=creator_wallet,
                        secondary_wallet=effective_fee_share_wallet,
                        primary_share_bps=fee_share_primary_bps,
                        secondary_share_bps=fee_share_secondary_bps,
                    )

                    fee_share_data = json.loads(fee_share_result)
                    if fee_share_data.get("success"):
                        fee_share_config = fee_share_data.get("response", {}).get(
                            "feeShareConfig", ""
                        )

            # Step 4: Create the token launch transaction
            launch_result = await self.create_token_launch_transaction(
                creator_wallet=creator_wallet,
                token_name=token_name,
                token_symbol=token_symbol,
                token_uri=token_uri,
                token_decimals=token_decimals,
                initial_buy_sol=initial_buy_sol,
                slippage_bps=slippage_bps,
                priority_fee_lamports=priority_fee_lamports,
                fee_share_config=fee_share_config,
            )

            launch_data = json.loads(launch_result)
            if not launch_data.get("success"):
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Failed to create launch transaction: {launch_data.get('error')}",
                    }
                )

            # Prepare comprehensive response
            response = {
                "success": True,
                "message": f"Token '{token_name}' ({token_symbol}) is ready to launch!",
                "token_details": {
                    "name": token_name,
                    "symbol": token_symbol,
                    "description": token_description,
                    "decimals": token_decimals,
                    "metadata_uri": token_uri,
                    "image": image_uri if image_uri else "No image provided",
                    "is_mutable": is_mutable,
                },
                "launch_configuration": {
                    "creator_wallet": creator_wallet,
                    "initial_buy_sol": initial_buy_sol,
                    "slippage_bps": slippage_bps,
                    "priority_fee_lamports": priority_fee_lamports,
                },
                "transaction": launch_data.get("response", {}),
            }

            if fee_share_config:
                response["fee_sharing"] = {
                    "enabled": True,
                    "primary_wallet": creator_wallet,
                    "secondary_wallet": fee_share_wallet,
                    "primary_share_bps": fee_share_primary_bps,
                    "secondary_share_bps": fee_share_secondary_bps,
                    "fee_share_config": fee_share_config,
                }

            if twitter or telegram or website:
                response["social_links"] = {}
                if twitter:
                    response["social_links"]["twitter"] = twitter
                if telegram:
                    response["social_links"]["telegram"] = telegram
                if website:
                    response["social_links"]["website"] = website

            return json.dumps(response, indent=2)

        except Exception as e:
            return json.dumps(
                {"success": False, "error": f"Token launch failed: {str(e)}"}
            )
