import os
import logging
import hashlib
import time
import json
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth, verify_api_key
import nacl.encoding
import nacl.signing

try:
    from eth_account.messages import encode_defunct  # type: ignore[import]
    from eth_account import Account  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    encode_defunct = None
    Account = None

import pyotp

from DB import get_session, User, PaymentTransaction
from Models import (
    Detail,
    Login,
    Register,
    CryptoInvoiceRequest,
    CryptoInvoiceResponse,
    CryptoVerifyRequest,
    PaymentQuoteRequest,
    PaymentQuoteResponse,
    PaymentTransactionResponse,
    StripePaymentIntentRequest,
    StripePaymentIntentResponse,
    StripeCustomerPortalRequest,
    StripeCustomerPortalResponse,
)
from payments import (
    CryptoPaymentService,
    PriceService,
    StripePaymentService,
    SUPPORTED_CURRENCIES,
)

"""
Crypto Wallet Authentication Extension

Supports:
- Phantom Wallet (Solana)
- Brave Wallet (Multi-chain)
- MetaMask (EVM)
- Other Web3 wallets

This extension provides signature-based authentication for crypto wallets,
allowing users to log in using their wallet signatures instead of traditional
OAuth or password-based authentication.
"""

# Nonce storage (in production, use Redis or database)
nonce_storage: Dict[str, Dict[str, Any]] = {}


def generate_nonce() -> str:
    """Generate a secure random nonce for wallet signature"""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")


def store_nonce(nonce: str, wallet_address: str, chain: str = "unknown") -> None:
    """Store nonce with timestamp for expiration"""
    nonce_storage[nonce] = {
        "wallet_address": wallet_address.lower(),
        "chain": chain,
        "timestamp": time.time(),
        "used": False,
    }


def verify_nonce(nonce: str, wallet_address: str) -> bool:
    """Verify nonce is valid and hasn't expired (5 minutes)"""
    if nonce not in nonce_storage:
        return False

    nonce_data = nonce_storage[nonce]
    current_time = time.time()

    # Check if nonce has expired (5 minutes)
    if current_time - nonce_data["timestamp"] > 300:
        del nonce_storage[nonce]
        return False

    # Check if nonce was already used
    if nonce_data["used"]:
        return False

    # Check if wallet address matches
    if nonce_data["wallet_address"] != wallet_address.lower():
        return False

    # Mark as used
    nonce_storage[nonce]["used"] = True
    return True


def cleanup_expired_nonces():
    """Clean up expired nonces from storage"""
    current_time = time.time()
    expired_nonces = [
        nonce
        for nonce, data in nonce_storage.items()
        if current_time - data["timestamp"] > 300
    ]
    for nonce in expired_nonces:
        del nonce_storage[nonce]


class WalletSSO:
    """
    Wallet SSO handler for signature-based authentication
    """

    def __init__(
        self,
        wallet_address: str = None,
        wallet_type: str = None,
        chain: str = None,
        signature: str = None,
        message: str = None,
        nonce: str = None,
    ):
        self.wallet_address = wallet_address
        self.wallet_type = wallet_type  # phantom, brave, metamask, etc.
        self.chain = chain  # solana, ethereum, polygon, etc.
        self.signature = signature
        self.message = message
        self.nonce = nonce
        self.user_info = None

    def verify_solana_signature(self) -> bool:
        """
        Verify Ed25519 signature for Solana wallets
        """
        try:
            # Decode the base58 encoded public key (wallet address)
            import base58

            public_key_bytes = base58.b58decode(self.wallet_address)

            # Create a verification key from the public key
            verify_key = nacl.signing.VerifyKey(public_key_bytes)

            # Decode the signature (should be base58 encoded)
            signature_bytes = base58.b58decode(self.signature)

            # Verify the signature
            verify_key.verify(self.message.encode("utf-8"), signature_bytes)
            return True

        except Exception as e:
            logging.error(f"Solana signature verification failed: {str(e)}")
            return False

    def verify_ethereum_signature(self) -> bool:
        """
        Verify EIP-191 signature for Ethereum/EVM wallets
        """
        try:
            if not encode_defunct or not Account:
                logging.error("eth_account package is not available")
                return False
            # Create the message hash
            message_hash = encode_defunct(text=self.message)

            # Recover the address from the signature
            recovered_address = Account.recover_message(
                message_hash, signature=self.signature
            )

            # Compare addresses (case-insensitive)
            return recovered_address.lower() == self.wallet_address.lower()

        except Exception as e:
            logging.error(f"Ethereum signature verification failed: {str(e)}")
            return False

    def verify_signature(self) -> bool:
        """
        Verify wallet signature based on chain type
        """
        # Verify nonce first
        if not verify_nonce(self.nonce, self.wallet_address):
            logging.error(f"Invalid or expired nonce: {self.nonce}")
            return False

        # Verify signature based on chain
        if self.chain in ["solana"]:
            return self.verify_solana_signature()
        elif self.chain in [
            "ethereum",
            "polygon",
            "bsc",
            "avalanche",
            "arbitrum",
            "optimism",
        ]:
            return self.verify_ethereum_signature()
        else:
            logging.error(f"Unsupported chain: {self.chain}")
            return False

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get user info from wallet authentication
        """
        if not self.wallet_address:
            return None

        # Create synthetic email for wallet users
        # Truncate address for display (first 6 and last 4 chars)
        truncated_address = f"{self.wallet_address[:6]}...{self.wallet_address[-4:]}"
        synthetic_email = f"{self.wallet_address.lower()}@crypto.wallet"

        return {
            "email": synthetic_email,
            "first_name": "Anonymous",
            "last_name": "User",
            "wallet_address": self.wallet_address,
            "wallet_type": self.wallet_type,
            "chain": self.chain,
            "verified": True,  # Wallet signature serves as verification
        }


def sso(
    wallet_address: str,
    signature: str,
    message: str,
    nonce: str,
    wallet_type: str = "unknown",
    chain: str = "unknown",
    redirect_uri: str = None,
) -> WalletSSO:
    """
    Main SSO function for wallet authentication

    Args:
        wallet_address: The user's wallet address
        signature: The signature from the wallet
        message: The message that was signed
        nonce: The nonce used in the message
        wallet_type: Type of wallet (phantom, brave, etc.)
        chain: Blockchain network (solana, ethereum, etc.)
        redirect_uri: Not used for wallet auth but kept for compatibility

    Returns:
        WalletSSO instance with user info if verification succeeds
    """
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    # Create WalletSSO instance
    wallet_sso = WalletSSO(
        wallet_address=wallet_address,
        wallet_type=wallet_type,
        chain=chain,
        signature=signature,
        message=message,
        nonce=nonce,
    )

    # Verify the signature
    if not wallet_sso.verify_signature():
        logging.error(f"Wallet signature verification failed for {wallet_address}")
        return None

    # Get user info
    wallet_sso.user_info = wallet_sso.get_user_info()

    # For compatibility with OAuth flow, set these attributes
    wallet_sso.access_token = f"wallet_{wallet_address}"  # Synthetic token
    wallet_sso.refresh_token = None  # No refresh for wallet auth
    wallet_sso.expires_in = 3600  # 1 hour session

    return wallet_sso


class wallet(Extensions):
    """
    The Crypto Wallet extension provides Web3 authentication integration.
    This extension allows AI agents to:
    - Authenticate users via crypto wallets (Phantom, Brave, MetaMask, etc.)
    - Verify wallet signatures
    - Manage wallet-based sessions

    The extension supports multiple blockchain networks including Solana and EVM chains.
    """

    CATEGORY = "Finance & Crypto"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.user_email = kwargs.get("user", None)

        # Clean up expired nonces periodically
        cleanup_expired_nonces()

        # Commands for interacting with the USER's connected wallet (not the agent's wallet)
        # These prepare transactions that need to be signed by the user in their browser
        self.commands = {
            "Get Connected Wallet Balance": self.get_connected_wallet_balance,
            "Prepare SOL Transfer": self.prepare_sol_transfer,
            "Prepare Token Transfer": self.prepare_token_transfer,
            "Get Connected Wallet Tokens": self.get_connected_wallet_tokens,
            "Prepare Swap Transaction": self.prepare_swap_transaction,
            "Get Connected Wallet Info": self.get_connected_wallet_info,
        }

        # Set up FastAPI router for REST endpoints
        self.router = APIRouter(tags=["Wallet"], prefix="")

        # Initialize payment services reused for billing endpoints
        self.price_service = PriceService()
        self.crypto_service = CryptoPaymentService(price_service=self.price_service)
        self.stripe_service = StripePaymentService(price_service=self.price_service)

        @self.router.get(
            "/v1/wallet/providers",
            summary="Get supported wallet providers",
        )
        async def get_wallet_providers():
            """Get list of supported wallet providers and their configurations"""
            return {"providers": WALLET_PROVIDERS}

        @self.router.post(
            "/v1/wallet/nonce",
            summary="Generate nonce for wallet authentication",
        )
        async def generate_wallet_nonce_endpoint(request: Request):
            """
            Generate a nonce for wallet signature authentication

            Request body:
            - wallet_address: The user's wallet address
            - chain: The blockchain network (solana, ethereum, etc.)
            """
            data = await request.json()

            if "wallet_address" not in data:
                raise HTTPException(
                    status_code=400, detail="Wallet address is required"
                )

            wallet_address = data["wallet_address"]
            chain = data.get("chain", "unknown")

            # Generate and store nonce
            nonce = generate_nonce()
            store_nonce(nonce, wallet_address, chain)

            # Create message for signing
            timestamp = datetime.now().isoformat()
            app_name = getenv("APP_NAME", "AGiXT")

            message = (
                f"Sign this message to authenticate with {app_name}\n\n"
                f"Wallet: {wallet_address}\n"
                f"Nonce: {nonce}\n"
                f"Timestamp: {timestamp}\n"
                f"Chain: {chain}"
            )

            return {"nonce": nonce, "message": message, "timestamp": timestamp}

        @self.router.post(
            "/v1/wallet/verify",
            response_model=Detail,
            summary="Verify wallet signature and authenticate",
        )
        async def verify_wallet_signature_endpoint(request: Request):
            """
            Verify wallet signature and authenticate
            Handles both login authentication and wallet connection for existing users

            Request body:
            - wallet_address: The user's wallet address
            - signature: The signature from the wallet
            - message: The message that was signed
            - nonce: The nonce used in the message
            - wallet_type: Type of wallet (phantom, brave, etc.)
            - chain: Blockchain network
            - invitation_id: Optional invitation ID
            - referrer: Optional referrer URL
            """
            data = await request.json()
            client_ip = request.headers.get("X-Forwarded-For") or request.client.host
            auth_header = request.headers.get("Authorization")

            required_fields = ["wallet_address", "signature", "message", "nonce"]
            for field in required_fields:
                if field not in data:
                    raise HTTPException(status_code=400, detail=f"{field} is required")

            # Verify the wallet signature
            wallet_auth = sso(
                wallet_address=data["wallet_address"],
                signature=data["signature"],
                message=data["message"],
                nonce=data["nonce"],
                wallet_type=data.get("wallet_type", "unknown"),
                chain=data.get("chain", "unknown"),
            )

            if not wallet_auth or not wallet_auth.user_info:
                raise HTTPException(status_code=401, detail="Invalid wallet signature")

            # Check if this is a wallet connection request from an existing authenticated user
            if auth_header and auth_header.startswith("Bearer "):
                try:
                    # This is a wallet connection for existing user
                    existing_auth = MagicalAuth(token=auth_header.split(" ")[1])
                    existing_user_email = existing_auth.email

                    # Store wallet metadata in the authenticated user's preferences
                    existing_auth.update_user(
                        wallet_address=data["wallet_address"],
                        wallet_type=data.get("wallet_type", "unknown"),
                        wallet_chain=data.get("chain", "unknown"),
                    )

                    return {
                        "detail": None,  # No redirect for wallet association
                        "email": existing_user_email,
                        "token": None,  # Keep existing session
                        "wallet_address": data["wallet_address"],
                        "connected": True,
                    }
                except Exception as e:
                    logging.error(
                        f"Failed to connect wallet to existing user: {str(e)}"
                    )
                    raise HTTPException(
                        status_code=401, detail="Invalid authentication token"
                    )
            else:
                # This is a wallet login/authentication request
                # Create or get user with the synthetic email
                auth = MagicalAuth()
                auth.email = wallet_auth.user_info["email"]

                # Check if user exists
                user_exists = auth.user_exists(email=auth.email)

                if not user_exists:
                    # Register new wallet user
                    register = Register(
                        email=wallet_auth.user_info["email"],
                        first_name=wallet_auth.user_info["first_name"],
                        last_name=wallet_auth.user_info["last_name"],
                        invitation_id=data.get("invitation_id"),
                    )

                    result = auth.register(
                        new_user=register,
                        invitation_id=data.get("invitation_id"),
                        verify_email=True,  # Wallet signature serves as verification
                    )

                    if result["status_code"] != 200:
                        raise HTTPException(
                            status_code=result["status_code"], detail=result["error"]
                        )

                # Create login session
                # Get user's MFA token for login
                session = get_session()
                user = session.query(User).filter(User.email == auth.email).first()
                session.close()

                if not user:
                    raise HTTPException(status_code=404, detail="User not found")

                # Use TOTP for internal login
                totp = pyotp.TOTP(user.mfa_token)
                login = Login(email=auth.email, token=totp.now())

                # Get magic link (JWT token)
                referrer = data.get("referrer", getenv("APP_URI"))
                magic_link = auth.send_magic_link(
                    ip_address=client_ip,
                    login=login,
                    referrer=referrer,
                    send_link=False,
                )

                # Store wallet metadata in user preferences
                auth.update_user(
                    wallet_address=data["wallet_address"],
                    wallet_type=data.get("wallet_type", "unknown"),
                    wallet_chain=data.get("chain", "unknown"),
                )

                return {
                    "detail": magic_link,
                    "email": auth.email,
                    "token": auth.token,
                    "wallet_address": data["wallet_address"],
                }

        @self.router.get(
            "/v1/wallet/session",
            summary="Get wallet session info",
            dependencies=[Depends(verify_api_key)],
        )
        async def get_wallet_session_endpoint(
            email: str = Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            """Get wallet session information for the authenticated user"""
            auth = MagicalAuth(token=authorization)
            user_preferences = auth.get_user_preferences()

            # Check if this is a wallet user
            if not auth.email.endswith("@crypto.wallet"):
                return {"is_wallet_user": False}

            return {
                "is_wallet_user": True,
                "wallet_address": user_preferences.get("wallet_address"),
                "wallet_type": user_preferences.get("wallet_type"),
                "wallet_chain": user_preferences.get("wallet_chain"),
                "email": auth.email,
            }

        # ----------------------------
        # Billing / Payments endpoints
        # ----------------------------

        @self.router.get("/v1/billing/currencies", tags=["Billing"])
        async def get_supported_currencies():
            currencies = [
                {
                    "symbol": symbol,
                    "network": details.get("network"),
                    "decimals": details.get("decimals"),
                    "mint": details.get("mint"),
                }
                for symbol, details in SUPPORTED_CURRENCIES.items()
            ]
            return {
                "base_price_usd": float(self.price_service.base_price_usd),
                "wallet_address": getenv("PAYMENT_WALLET_ADDRESS"),
                "currencies": currencies,
            }

        @self.router.post(
            "/v1/billing/quote",
            response_model=PaymentQuoteResponse,
            tags=["Billing"],
        )
        async def get_payment_quote(payload: PaymentQuoteRequest):
            quote = await self.price_service.get_quote(
                payload.currency, payload.seat_count
            )
            return PaymentQuoteResponse(
                reference_code=None,
                seat_count=quote["seat_count"],
                currency=quote["currency"],
                network=quote.get("network"),
                amount_usd=quote["amount_usd"],
                amount_currency=quote["amount_currency"],
                exchange_rate=quote["exchange_rate"],
                wallet_address=getenv("PAYMENT_WALLET_ADDRESS"),
                expires_at=None,
            )

        @self.router.post(
            "/v1/billing/crypto/invoice",
            response_model=CryptoInvoiceResponse,
            tags=["Billing"],
        )
        async def create_crypto_invoice(
            payload: CryptoInvoiceRequest,
            authorization: str = Header(None),
            user=Depends(verify_api_key),
        ):
            user_id = self._get_user_id(user)
            if not user_id:
                raise HTTPException(status_code=401, detail="User context missing")

            company_id: Optional[str] = None
            if authorization:
                company_auth = MagicalAuth(token=authorization)
                company_id = getattr(company_auth, "company_id", None)

            invoice = await self.crypto_service.create_invoice(
                seat_count=payload.seat_count,
                currency=payload.currency,
                expires_in_minutes=payload.expires_in_minutes,
                memo=payload.memo,
                user_id=user_id,
                company_id=company_id,
            )
            return CryptoInvoiceResponse(**invoice)

        @self.router.post(
            "/v1/billing/crypto/verify",
            response_model=PaymentTransactionResponse,
            tags=["Billing"],
        )
        async def verify_crypto_invoice(
            payload: CryptoVerifyRequest,
            user=Depends(verify_api_key),
        ):
            user_id = self._get_user_id(user)
            if not user_id:
                raise HTTPException(status_code=401, detail="User context missing")

            record = await self.crypto_service.verify_transaction(
                reference_code=payload.reference_code,
                transaction_hash=payload.transaction_hash,
                expected_user_id=user_id,
            )
            if record.get("status") != "completed":
                raise HTTPException(status_code=400, detail="Payment not confirmed")
            return PaymentTransactionResponse(**record)

        @self.router.post(
            "/v1/billing/stripe/payment-intent",
            response_model=StripePaymentIntentResponse,
            tags=["Billing"],
        )
        async def create_stripe_payment_intent(
            payload: StripePaymentIntentRequest,
            user=Depends(verify_api_key),
        ):
            user_id = self._get_user_id(user)
            if not user_id:
                raise HTTPException(status_code=401, detail="User context missing")
            try:
                result = await self.stripe_service.create_payment_intent(
                    seat_count=payload.seat_count,
                    metadata=payload.metadata,
                    user_id=user_id,
                    company_id=None,
                )
            except HTTPException:
                raise
            except Exception as exc:  # pragma: no cover - defensive guardrail
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            return StripePaymentIntentResponse(
                client_secret=result["client_secret"],
                payment_intent_id=result["payment_intent_id"],
                amount_usd=result["amount_usd"],
                seat_count=result["seat_count"],
                reference_code=result.get("reference_code"),
            )

        @self.router.post(
            "/v1/billing/stripe/customer-portal",
            response_model=StripeCustomerPortalResponse,
            tags=["Billing"],
        )
        async def create_stripe_customer_portal(
            payload: StripeCustomerPortalRequest,
            user=Depends(verify_api_key),
        ):
            user_id = self._get_user_id(user)
            if not user_id:
                raise HTTPException(status_code=401, detail="User context missing")

            try:
                result = await self.stripe_service.create_customer_portal_session(
                    user_id=user_id,
                    email=self._get_user_email(user),
                    seat_count=payload.seat_count,
                    return_url=payload.return_url,
                )
            except HTTPException:
                raise
            except Exception as exc:  # pragma: no cover - defensive guardrail
                raise HTTPException(status_code=500, detail=str(exc)) from exc

            return StripeCustomerPortalResponse(**result)

        @self.router.get(
            "/v1/billing/transactions",
            response_model=List[PaymentTransactionResponse],
            tags=["Billing"],
        )
        async def list_payment_transactions(
            status: Optional[str] = None,
            limit: int = 50,
            user=Depends(verify_api_key),
        ):
            user_id = self._get_user_id(user)
            if not user_id:
                raise HTTPException(status_code=401, detail="User context missing")
            is_admin = self._is_admin(user)
            limit_value = max(1, min(limit, 200))
            status_value = status.lower() if status else None

            session = get_session()
            try:
                query = session.query(PaymentTransaction)
                if not is_admin:
                    query = query.filter(PaymentTransaction.user_id == user_id)
                if status_value:
                    query = query.filter(PaymentTransaction.status == status_value)
                records = (
                    query.order_by(PaymentTransaction.created_at.desc())
                    .limit(limit_value)
                    .all()
                )
                return [
                    PaymentTransactionResponse(
                        **self.crypto_service._serialize_record(r)
                    )
                    for r in records
                ]
            finally:
                session.close()

    async def generate_wallet_nonce(
        self, wallet_address: str, chain: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Generate a nonce for wallet signature authentication

        Args:
            wallet_address: The user's wallet address
            chain: The blockchain network

        Returns:
            Dictionary containing nonce and message to sign
        """
        try:
            # Generate nonce
            nonce = generate_nonce()

            # Store nonce
            store_nonce(nonce, wallet_address, chain)

            # Create message for signing
            timestamp = datetime.now().isoformat()
            app_name = getenv("APP_NAME", "AGiXT")

            message = (
                f"Sign this message to authenticate with {app_name}\n\n"
                f"Wallet: {wallet_address}\n"
                f"Nonce: {nonce}\n"
                f"Timestamp: {timestamp}\n"
                f"Chain: {chain}"
            )

            return {
                "success": True,
                "nonce": nonce,
                "message": message,
                "timestamp": timestamp,
            }

        except Exception as e:
            logging.error(f"Error generating wallet nonce: {str(e)}")
            return {"success": False, "error": str(e)}

    async def verify_wallet_signature(
        self,
        wallet_address: str,
        signature: str,
        message: str,
        nonce: str,
        wallet_type: str = "unknown",
        chain: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Verify a wallet signature for authentication

        Args:
            wallet_address: The user's wallet address
            signature: The signature from the wallet
            message: The message that was signed
            nonce: The nonce used in the message
            wallet_type: Type of wallet (phantom, brave, etc.)
            chain: Blockchain network

        Returns:
            Dictionary containing verification result and user info
        """
        try:
            wallet_sso = sso(
                wallet_address=wallet_address,
                signature=signature,
                message=message,
                nonce=nonce,
                wallet_type=wallet_type,
                chain=chain,
            )

            if wallet_sso and wallet_sso.user_info:
                return {
                    "success": True,
                    "verified": True,
                    "user_info": wallet_sso.user_info,
                    "access_token": wallet_sso.access_token,
                }
            else:
                return {
                    "success": False,
                    "verified": False,
                    "error": "Signature verification failed",
                }

        except Exception as e:
            logging.error(f"Error verifying wallet signature: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_wallet_user_info(
        self, wallet_address: str, wallet_type: str = "unknown", chain: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Get user information for a wallet address

        Args:
            wallet_address: The user's wallet address
            wallet_type: Type of wallet
            chain: Blockchain network

        Returns:
            Dictionary containing user information
        """
        try:
            wallet_sso = WalletSSO(
                wallet_address=wallet_address, wallet_type=wallet_type, chain=chain
            )

            user_info = wallet_sso.get_user_info()

            return {"success": True, "user_info": user_info}

        except Exception as e:
            logging.error(f"Error getting wallet user info: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_connected_wallet_info(self) -> Dict[str, Any]:
        """
        Get information about the connected wallet from user preferences
        """
        try:
            if not self.user_email or not self.user_email.endswith("@crypto.wallet"):
                return {
                    "success": False,
                    "error": "No connected wallet found. User must authenticate with wallet first.",
                }

            # Get user preferences from MagicalAuth
            from MagicalAuth import MagicalAuth, impersonate_user

            token = impersonate_user(self.user_email)
            auth = MagicalAuth(token=token)
            preferences = auth.get_user_preferences()

            return {
                "success": True,
                "wallet_address": preferences.get("wallet_address"),
                "wallet_type": preferences.get("wallet_type"),
                "wallet_chain": preferences.get("wallet_chain"),
                "email": self.user_email,
            }
        except Exception as e:
            logging.error(f"Error getting connected wallet info: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_connected_wallet_balance(self) -> Dict[str, Any]:
        """
        Get the balance of the user's connected wallet

        Returns a transaction request that the frontend needs to execute
        """
        try:
            wallet_info = await self.get_connected_wallet_info()
            if not wallet_info.get("success"):
                return wallet_info

            wallet_address = wallet_info.get("wallet_address")
            chain = wallet_info.get("wallet_chain", "solana")

            # For Solana
            if chain == "solana":
                from solana.rpc.async_api import AsyncClient
                from solders.pubkey import Pubkey

                client = AsyncClient("https://api.mainnet-beta.solana.com")
                pubkey = Pubkey.from_string(wallet_address)
                response = await client.get_balance(pubkey)
                balance_lamports = response.value
                sol_balance = balance_lamports / 1_000_000_000

                return {
                    "success": True,
                    "wallet_address": wallet_address,
                    "balance": sol_balance,
                    "chain": chain,
                    "unit": "SOL",
                }

            # For EVM chains
            elif chain in ["ethereum", "polygon", "bsc"]:
                # This would need web3.py for EVM chains
                return {
                    "success": False,
                    "error": f"EVM chain {chain} balance check not yet implemented",
                }

            else:
                return {"success": False, "error": f"Unsupported chain: {chain}"}

        except Exception as e:
            logging.error(f"Error getting wallet balance: {str(e)}")
            return {"success": False, "error": str(e)}

    async def prepare_sol_transfer(
        self, to_address: str, amount: float
    ) -> Dict[str, Any]:
        """
        Prepare a SOL transfer transaction for the user to sign in their browser

        Returns transaction data that needs to be signed client-side
        """
        try:
            wallet_info = await self.get_connected_wallet_info()
            if not wallet_info.get("success"):
                return wallet_info

            from_address = wallet_info.get("wallet_address")
            chain = wallet_info.get("wallet_chain", "solana")

            if chain != "solana":
                return {
                    "success": False,
                    "error": "SOL transfers only available on Solana chain",
                }

            # Convert amount to lamports
            lamports = int(amount * 1_000_000_000)

            # Return transaction parameters for frontend to build and sign
            return {
                "success": True,
                "action": "transfer_sol",
                "requires_signature": True,
                "transaction": {
                    "from": from_address,
                    "to": to_address,
                    "amount": lamports,
                    "unit": "lamports",
                    "display_amount": f"{amount} SOL",
                },
                "message": f"Prepare to transfer {amount} SOL to {to_address}",
            }

        except Exception as e:
            logging.error(f"Error preparing SOL transfer: {str(e)}")
            return {"success": False, "error": str(e)}

    async def prepare_token_transfer(
        self, to_address: str, token_mint: str, amount: float, decimals: int = 9
    ) -> Dict[str, Any]:
        """
        Prepare an SPL token transfer for the user to sign
        """
        try:
            wallet_info = await self.get_connected_wallet_info()
            if not wallet_info.get("success"):
                return wallet_info

            from_address = wallet_info.get("wallet_address")
            chain = wallet_info.get("wallet_chain", "solana")

            if chain != "solana":
                return {
                    "success": False,
                    "error": "SPL token transfers only available on Solana chain",
                }

            # Calculate amount in base units
            amount_base = int(amount * (10**decimals))

            return {
                "success": True,
                "action": "transfer_token",
                "requires_signature": True,
                "transaction": {
                    "from": from_address,
                    "to": to_address,
                    "token_mint": token_mint,
                    "amount": amount_base,
                    "decimals": decimals,
                    "display_amount": f"{amount} tokens",
                },
                "message": f"Prepare to transfer {amount} tokens to {to_address}",
            }

        except Exception as e:
            logging.error(f"Error preparing token transfer: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_connected_wallet_tokens(self) -> Dict[str, Any]:
        """
        Get all SPL tokens owned by the connected wallet
        """
        try:
            wallet_info = await self.get_connected_wallet_info()
            if not wallet_info.get("success"):
                return wallet_info

            wallet_address = wallet_info.get("wallet_address")
            chain = wallet_info.get("wallet_chain", "solana")

            if chain != "solana":
                return {
                    "success": False,
                    "error": "Token list only available for Solana chain currently",
                }

            from solana.rpc.async_api import AsyncClient
            from solders.pubkey import Pubkey
            from solana.rpc.types import TokenAccountOpts
            import base58

            client = AsyncClient("https://api.mainnet-beta.solana.com")
            wallet_pubkey = Pubkey.from_string(wallet_address)

            TOKEN_PROGRAM_ID = Pubkey.from_string(
                "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
            )

            # Get all token accounts
            response = await client.get_token_accounts_by_owner(
                wallet_pubkey, TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
            )

            if not response.value:
                return {
                    "success": True,
                    "wallet_address": wallet_address,
                    "tokens": [],
                    "message": "No tokens found",
                }

            tokens = []
            for account in response.value:
                try:
                    balance_response = await client.get_token_account_balance(
                        account.pubkey
                    )
                    if balance_response.value:
                        amount = balance_response.value.amount
                        decimals = balance_response.value.decimals
                        ui_amount = int(amount) / (10**decimals)

                        # Get mint from account data
                        account_info = await client.get_account_info(account.pubkey)
                        if account_info.value and account_info.value.data:
                            data = base58.b58decode(account_info.value.data)
                            mint = base58.b58encode(data[0:32]).decode()

                            tokens.append(
                                {
                                    "mint": mint,
                                    "balance": ui_amount,
                                    "decimals": decimals,
                                    "account": str(account.pubkey),
                                }
                            )
                except Exception:
                    continue

            return {
                "success": True,
                "wallet_address": wallet_address,
                "tokens": tokens,
                "token_count": len(tokens),
            }

        except Exception as e:
            logging.error(f"Error getting wallet tokens: {str(e)}")
            return {"success": False, "error": str(e)}

    async def prepare_swap_transaction(
        self, input_mint: str, output_mint: str, amount: float, slippage_bps: int = 100
    ) -> Dict[str, Any]:
        """
        Prepare a Jupiter swap transaction for the user to sign
        """
        try:
            wallet_info = await self.get_connected_wallet_info()
            if not wallet_info.get("success"):
                return wallet_info

            wallet_address = wallet_info.get("wallet_address")
            chain = wallet_info.get("wallet_chain", "solana")

            if chain != "solana":
                return {
                    "success": False,
                    "error": "Swaps only available on Solana chain",
                }

            # Get quote from Jupiter
            import requests

            # Convert amount to lamports/base units (assuming 9 decimals for simplicity)
            amount_base = int(amount * 1_000_000_000)

            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount_base,
                "slippageBps": slippage_bps,
                "onlyDirectRoutes": "false",
            }

            response = requests.get("https://quote-api.jup.ag/v6/quote", params=params)

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to get swap quote: {response.text}",
                }

            quote_data = response.json()

            # Return the quote for frontend to execute
            return {
                "success": True,
                "action": "swap_tokens",
                "requires_signature": True,
                "quote": quote_data,
                "transaction": {
                    "wallet_address": wallet_address,
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "inputAmount": quote_data.get("inAmount"),
                    "outputAmount": quote_data.get("outAmount"),
                    "priceImpact": quote_data.get("priceImpactPct"),
                },
                "message": f"Prepare to swap {amount} tokens",
            }

        except Exception as e:
            logging.error(f"Error preparing swap transaction: {str(e)}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _get_user_id(user: Any) -> Optional[str]:
        if user is None:
            return None
        if isinstance(user, dict):
            value = user.get("id") or user.get("user_id")
        else:
            value = getattr(user, "id", None)
        return str(value) if value else None

    @staticmethod
    def _get_user_email(user: Any) -> Optional[str]:
        if user is None:
            return None
        if isinstance(user, dict):
            return user.get("email")
        return getattr(user, "email", None)

    @staticmethod
    def _is_admin(user: Any) -> bool:
        if user is None:
            return False
        if isinstance(user, dict):
            return bool(user.get("admin"))
        return bool(getattr(user, "admin", False))


# Configuration for wallet providers
WALLET_PROVIDERS = {
    "phantom": {
        "name": "Phantom",
        "chains": ["solana", "ethereum", "polygon"],
        "primary_chain": "solana",
        "icon": "phantom",
    },
    "brave": {
        "name": "Brave Wallet",
        "chains": ["solana", "ethereum", "polygon", "bsc"],
        "primary_chain": "ethereum",
        "icon": "brave",
    },
    "metamask": {
        "name": "MetaMask",
        "chains": ["ethereum", "polygon", "bsc", "avalanche", "arbitrum", "optimism"],
        "primary_chain": "ethereum",
        "icon": "metamask",
    },
    "solflare": {
        "name": "Solflare",
        "chains": ["solana"],
        "primary_chain": "solana",
        "icon": "solflare",
    },
    "solana_mobile_stack": {
        "name": "Solana Mobile Wallet",
        "chains": ["solana"],
        "primary_chain": "solana",
        "icon": "solana",
    },
}

# This is required for the OAuth discovery mechanism to find this as a provider
SCOPES = []  # No scopes needed for wallet auth
AUTHORIZE = ""  # No authorization URL for wallet auth
PKCE_REQUIRED = False  # No PKCE for wallet auth
