"""
x402 Payment Protocol Implementation

This module implements the x402 payment protocol for AGiXT, enabling
HTTP 402-based cryptocurrency payments via facilitators like CDP and PayAI.

Protocol Flow:
1. Client requests a resource
2. Server returns 402 with payment details
3. Client prepares payment payload (signed by wallet)
4. Client retries request with X-PAYMENT header
5. Server verifies payload via facilitator
6. Server settles payment via facilitator
7. Server returns resource with X-PAYMENT-RESPONSE header

Learn more: https://x402.org
"""

import logging
import time
import json
import base64
from typing import Dict, Optional, Any
from decimal import Decimal
import httpx
from sqlalchemy.orm import Session

from Globals import getenv
from DB import (
    PaymentTransaction,
    get_session,
)
from Globals import getenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


class X402FacilitatorError(Exception):
    """Raised when facilitator operations fail"""

    pass


class X402PaymentService:
    """
    Service for handling x402 protocol payments via facilitators.

    Supports multiple facilitators:
    - CDP (Coinbase): Base mainnet, testnet at https://x402.org/facilitator
    - PayAI: Solana, Base, Polygon
    """

    def __init__(
        self,
        facilitator_url: str = "https://x402.org/facilitator",
        merchant_wallet: str = "",
        network: str = "solana",  # solana, base, polygon
    ):
        """
        Initialize x402 payment service.

        Args:
            facilitator_url: URL of the facilitator service
            merchant_wallet: Merchant's wallet address to receive payments
            network: Blockchain network (solana, base, polygon)
        """
        self.facilitator_url = facilitator_url.rstrip("/")
        self.merchant_wallet = merchant_wallet
        self.network = network
        self.logger = logging.getLogger(__name__)
        self._last_payment_requirements = None  # Store for verification

    def create_payment_request(
        self,
        amount: Decimal,
        currency: str = "USDC",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        resource: str = "",
    ) -> Dict[str, Any]:
        """
        Create a payment request that will be returned in a 402 response.
        Follows the x402 protocol specification for payment requirements.

        Args:
            amount: Payment amount in the specified currency
            currency: Currency code (USDC, SOL, ETH, etc.)
            description: Human-readable payment description
            metadata: Optional metadata to include
            resource: The resource URL being accessed

        Returns:
            Payment request dictionary to include in 402 response body
        """
        # Get asset/mint address for the currency
        from payments.pricing import SUPPORTED_CURRENCIES

        currency_config = SUPPORTED_CURRENCIES.get(currency, {})
        asset = currency_config.get("mint", "")
        decimals = currency_config.get("decimals", 6)

        # Convert amount to atomic units (amount * 10^decimals)
        amount_atomic = str(int(amount * (10**decimals)))

        # Get AGiXT URI from environment
        agixt_uri = getenv("AGIXT_URI")

        # Create payment requirements following x402 spec
        payment_requirements = {
            "scheme": "exact",
            "network": self.network,
            "maxAmountRequired": amount_atomic,
            "asset": asset,
            "payTo": self.merchant_wallet,
            "resource": resource or f"{agixt_uri}/v1/",
            "description": description,
            "maxTimeoutSeconds": 60,
        }

        # Add network-specific extras
        if self.network.startswith("solana"):
            # Solana requires feePayer in extra
            payment_requirements["extra"] = {
                "feePayer": self.merchant_wallet  # Or facilitator's fee payer
            }
        elif currency == "USDC" and not self.network.startswith("solana"):
            # EVM networks - add USDC version info
            payment_requirements["extra"] = {"name": "USDC", "version": "2"}

        # Store for later use in verification
        self._last_payment_requirements = payment_requirements

        # Return full payment request with both old format (for frontend) and x402 spec
        payment_request = {
            "protocol": "x402",
            "version": "1.0",
            "merchant": {
                "wallet": self.merchant_wallet,
                "network": self.network,
            },
            "payment": {
                "amount": str(amount),
                "currency": currency,
                "description": description,
            },
            "facilitator": {
                "url": self.facilitator_url,
                "verify_endpoint": f"{self.facilitator_url}/verify",
                "settle_endpoint": f"{self.facilitator_url}/settle",
            },
            "timestamp": int(time.time()),
            # x402 spec payment requirements (used by facilitator)
            "paymentRequirements": payment_requirements,
        }

        if metadata:
            payment_request["metadata"] = metadata

        return payment_request

    async def verify_simple_signature(
        self,
        payment_payload: str,
        expected_amount: Decimal,
        expected_currency: str = "USDC",
    ) -> Dict[str, Any]:
        """
        Verify a simple wallet signature payment (non-x402 standard).
        This is used when the client sends a wallet signature instead of a full x402 transaction.

        Args:
            payment_payload: JSON string containing wallet signature
            expected_amount: Expected payment amount
            expected_currency: Expected currency

        Returns:
            Verification result with payer wallet address

        Raises:
            X402FacilitatorError: If signature verification fails
        """
        try:
            # Parse the payload
            if payment_payload.startswith("{"):
                payload_obj = json.loads(payment_payload)
            else:
                decoded = base64.b64decode(payment_payload)
                payload_obj = json.loads(decoded)

            network = payload_obj.get("network")
            wallet_address = payload_obj.get("wallet")
            signature_b64 = payload_obj.get("signature")
            message_str = payload_obj.get("message")

            if not all([network, wallet_address, signature_b64, message_str]):
                raise X402FacilitatorError("Missing required fields in payment payload")

            # Parse the message
            message_obj = json.loads(message_str)
            amount = Decimal(str(message_obj.get("amount", "0")))
            currency = message_obj.get("currency")
            merchant = message_obj.get("merchant")

            # Verify the payment details match
            if merchant != self.merchant_wallet:
                raise X402FacilitatorError(
                    f"Merchant wallet mismatch: expected {self.merchant_wallet}, got {merchant}"
                )

            if amount != expected_amount:
                raise X402FacilitatorError(
                    f"Amount mismatch: expected {expected_amount}, got {amount}"
                )

            if currency != expected_currency:
                raise X402FacilitatorError(
                    f"Currency mismatch: expected {expected_currency}, got {currency}"
                )

            # Verify the signature
            if network == "solana":
                # Verify Solana signature
                import nacl.signing
                import nacl.encoding

                try:
                    # Decode the public key (wallet address)
                    from base58 import b58decode

                    public_key_bytes = b58decode(wallet_address)
                    verify_key = nacl.signing.VerifyKey(public_key_bytes)

                    # Decode the signature
                    signature_bytes = base64.b64decode(signature_b64)

                    # Verify the signature
                    message_bytes = message_str.encode("utf-8")
                    verify_key.verify(message_bytes, signature_bytes)

                    self.logger.info(
                        f"Signature verified for Solana wallet: {wallet_address}"
                    )

                except Exception as e:
                    raise X402FacilitatorError(
                        f"Solana signature verification failed: {str(e)}"
                    )

            elif network in ["ethereum", "base", "polygon"]:
                # Verify EVM signature
                from eth_account.messages import encode_defunct
                from eth_account import Account

                try:
                    message_hash = encode_defunct(text=message_str)
                    recovered_address = Account.recover_message(
                        message_hash, signature=signature_b64
                    )

                    if recovered_address.lower() != wallet_address.lower():
                        raise X402FacilitatorError(
                            f"Signature verification failed: recovered {recovered_address}, expected {wallet_address}"
                        )

                    self.logger.info(
                        f"Signature verified for EVM wallet: {wallet_address}"
                    )

                except Exception as e:
                    raise X402FacilitatorError(
                        f"EVM signature verification failed: {str(e)}"
                    )
            else:
                raise X402FacilitatorError(f"Unsupported network: {network}")

            # Return verification result
            return {
                "isValid": True,
                "payer": wallet_address,
                "network": network,
                "amount": str(amount),
                "currency": currency,
            }

        except json.JSONDecodeError as e:
            raise X402FacilitatorError(f"Failed to parse payment payload: {str(e)}")
        except Exception as e:
            if isinstance(e, X402FacilitatorError):
                raise
            raise X402FacilitatorError(f"Payment verification failed: {str(e)}")

    async def verify_payment(
        self,
        payment_payload: str,
        payment_requirements: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Verify a payment payload via the facilitator.

        Follows PayAI facilitator API format:
        POST /verify
        {
          "paymentPayload": { x402Version, scheme, network, payload },
          "paymentRequirements": { scheme, network, maxAmountRequired, ... }
        }

        Args:
            payment_payload: Payment payload from X-PAYMENT header (base64-encoded JSON or raw JSON)
            payment_requirements: Payment requirements that were sent to client (optional, uses last created if not provided)

        Returns:
            Verification result from facilitator

        Raises:
            X402FacilitatorError: If verification fails
        """
        verify_url = f"{self.facilitator_url}/verify"

        # Parse payment payload (might be base64 or raw JSON)
        try:
            if payment_payload.startswith("{"):
                # Raw JSON
                payment_payload_obj = json.loads(payment_payload)
            else:
                # Base64 encoded
                decoded = base64.b64decode(payment_payload)
                payment_payload_obj = json.loads(decoded)
        except Exception as e:
            raise X402FacilitatorError(f"Failed to parse payment payload: {str(e)}")

        # Use provided requirements or last created
        if payment_requirements is None:
            payment_requirements = self._last_payment_requirements

        if payment_requirements is None:
            raise X402FacilitatorError(
                "Payment requirements not available - create a payment request first"
            )

        # Build request following PayAI API spec
        request_data = {
            "paymentPayload": payment_payload_obj,
            "paymentRequirements": payment_requirements,
        }

        self.logger.info(f"Sending verification request to {verify_url}")
        self.logger.debug(f"Payment payload: {payment_payload_obj}")
        self.logger.debug(f"Payment requirements: {payment_requirements}")

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    verify_url,
                    json=request_data,
                )

                if response.status_code != 200:
                    error_msg = (
                        f"Facilitator verification failed: {response.status_code}"
                    )
                    if response.text:
                        error_msg += f" - {response.text}"
                    else:
                        error_msg += " (empty response body)"

                    # Add helpful context for common errors
                    if response.status_code == 500:
                        error_msg += ". The x402 facilitator may be experiencing issues. Try again later or contact the facilitator service."
                    elif response.status_code in (301, 302, 307, 308):
                        error_msg += f". Unexpected redirect - check facilitator URL configuration."

                    self.logger.error(error_msg)
                    self.logger.error(f"Request URL: {verify_url}")
                    self.logger.error(f"Request data: {request_data}")
                    self.logger.error(f"Response headers: {dict(response.headers)}")
                    raise X402FacilitatorError(error_msg)

                result = response.json()

                # PayAI returns { "isValid": true/false, "payer": "..." }
                if not result.get("isValid", False):
                    reason = result.get("invalidReason", "Unknown")
                    error_msg = f"Invalid payment: {reason}"
                    self.logger.error(error_msg)
                    raise X402FacilitatorError(error_msg)

                self.logger.info(f"Payment verified for payer: {result.get('payer')}")
                return result

        except httpx.HTTPError as e:
            error_msg = f"HTTP error during verification: {str(e)}"
            self.logger.error(error_msg)
            raise X402FacilitatorError(error_msg)

    async def settle_payment(
        self,
        payment_payload: str,
        payment_requirements: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Settle a verified payment via the facilitator.

        Follows PayAI facilitator API format:
        POST /settle
        {
          "paymentPayload": { x402Version, scheme, network, payload },
          "paymentRequirements": { scheme, network, maxAmountRequired, ... }
        }

        Args:
            payment_payload: Payment payload from X-PAYMENT header (base64-encoded JSON or raw JSON)
            payment_requirements: Payment requirements (optional, uses last created if not provided)

        Returns:
            Settlement result from facilitator: { success, payer, transaction, network }

        Raises:
            X402FacilitatorError: If settlement fails
        """
        settle_url = f"{self.facilitator_url}/settle"

        # Parse payment payload (might be base64 or raw JSON)
        try:
            if payment_payload.startswith("{"):
                # Raw JSON
                payment_payload_obj = json.loads(payment_payload)
            else:
                # Base64 encoded
                decoded = base64.b64decode(payment_payload)
                payment_payload_obj = json.loads(decoded)
        except Exception as e:
            raise X402FacilitatorError(f"Failed to parse payment payload: {str(e)}")

        # Use provided requirements or last created
        if payment_requirements is None:
            payment_requirements = self._last_payment_requirements

        if payment_requirements is None:
            raise X402FacilitatorError(
                "Payment requirements not available - create a payment request first"
            )

        # Build request following PayAI API spec
        request_data = {
            "paymentPayload": payment_payload_obj,
            "paymentRequirements": payment_requirements,
        }

        self.logger.info(f"Sending settlement request to {settle_url}")
        self.logger.debug(f"Settlement request: {request_data}")

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    settle_url,
                    json=request_data,
                )

                if response.status_code != 200:
                    error_msg = f"Facilitator settlement failed: {response.status_code}"
                    if response.text:
                        error_msg += f" - {response.text}"
                    self.logger.error(error_msg)
                    self.logger.error(f"Request data: {request_data}")
                    raise X402FacilitatorError(error_msg)

                result = response.json()

                # PayAI returns { "success": true/false, "payer": "...", "transaction": "...", "network": "..." }
                if not result.get("success", False):
                    reason = result.get("errorReason", "Unknown")
                    error_msg = f"Settlement failed: {reason}"
                    self.logger.error(error_msg)
                    raise X402FacilitatorError(error_msg)

                self.logger.info(
                    f"Payment settled: {result.get('transaction')} for payer {result.get('payer')}"
                )
                return result

        except httpx.HTTPError as e:
            error_msg = f"HTTP error during settlement: {str(e)}"
            self.logger.error(error_msg)
            raise X402FacilitatorError(error_msg)

    async def process_payment(
        self,
        payment_payload: str,
        amount: Decimal,
        currency: str,
        user_id: str,
        description: str = "",
        payment_requirements: Optional[Dict[str, Any]] = None,
        seat_count: int = 1,
        db: Optional[Session] = None,
    ) -> PaymentTransaction:
        """
        Complete payment processing: verify + settle + record in database.

        Args:
            payment_payload: Payment payload from X-PAYMENT header
            amount: Expected payment amount
            currency: Expected currency
            user_id: User ID making the payment
            description: Payment description
            payment_requirements: Payment requirements (optional, uses last created)
            seat_count: Number of seats being purchased
            db: Database session

        Returns:
            PaymentTransaction database record

        Raises:
            X402FacilitatorError: If verification or settlement fails
        """
        if db is None:
            db = get_session()

        # Generate reference code for tracking
        import secrets

        reference_code = f"X402-{secrets.token_urlsafe(12)}"

        # Get pricing info for database record
        from payments.pricing import PriceService

        price_service = PriceService()
        quote = await price_service.get_quote(currency, seat_count)

        try:
            # Detect payment payload type
            try:
                if payment_payload.startswith("{"):
                    payload_obj = json.loads(payment_payload)
                else:
                    decoded = base64.b64decode(payment_payload)
                    payload_obj = json.loads(decoded)
            except Exception as e:
                raise X402FacilitatorError(f"Failed to parse payment payload: {str(e)}")

            # Check if it's a simple wallet signature or full x402 transaction
            is_simple_signature = (
                "signature" in payload_obj
                and "message" in payload_obj
                and "x402Version" not in payload_obj
            )

            if is_simple_signature:
                self.logger.info(
                    "Processing simple wallet signature payment (non-x402)"
                )

                # Verify the signature directly
                verification = await self.verify_simple_signature(
                    payment_payload=payment_payload,
                    expected_amount=amount,
                    expected_currency=currency,
                )

                # Prepare metadata
                metadata = {
                    "network": verification.get("network", self.network),
                    "payer": verification["payer"],
                    "merchant_wallet": self.merchant_wallet,
                    "verification": verification,
                    "note": "Simple wallet signature - signature verified but no on-chain token transfer occurred",
                    "mint": quote.get("mint"),
                }

                # For simple signatures, we don't settle via facilitator - the signature IS the proof
                # Record in database immediately
                payment_record = PaymentTransaction(
                    reference_code=reference_code,
                    user_id=user_id,
                    seat_count=seat_count,
                    payment_method="x402-simple",
                    currency=currency,
                    network=verification.get("network", self.network),
                    amount_usd=quote["amount_usd"],
                    amount_currency=quote["amount_currency"],
                    exchange_rate=quote["exchange_rate"],
                    status="completed",  # Mark as completed since signature is verified
                    transaction_hash=f"sig-{verification['payer'][:8]}-{int(time.time())}",
                    wallet_address=verification["payer"],
                    memo=description or f"x402 payment - {seat_count} seat(s)",
                    metadata_json=json.dumps(metadata),
                )

                db.add(payment_record)
                db.commit()
                db.refresh(payment_record)

                self.logger.info(
                    f"Simple signature payment recorded: {payment_record.id} for user {user_id}"
                )

                return payment_record

            else:
                self.logger.info(
                    "Processing full x402 protocol payment with facilitator"
                )

                # Full x402 protocol flow
                verification = await self.verify_payment(
                    payment_payload=payment_payload,
                    payment_requirements=payment_requirements,
                )

                payer = verification.get("payer")

                # Settle payment
                settlement = await self.settle_payment(
                    payment_payload=payment_payload,
                    payment_requirements=payment_requirements,
                )

                # Prepare metadata
                metadata = {
                    "network": settlement.get("network", self.network),
                    "payer": payer,
                    "merchant_wallet": self.merchant_wallet,
                    "verification": verification,
                    "settlement": settlement,
                    "mint": quote.get("mint"),
                }

                # Record in database
                payment_record = PaymentTransaction(
                    reference_code=reference_code,
                    user_id=user_id,
                    seat_count=seat_count,
                    payment_method="x402",
                    currency=currency,
                    network=settlement.get("network", self.network),
                    amount_usd=quote["amount_usd"],
                    amount_currency=quote["amount_currency"],
                    exchange_rate=quote["exchange_rate"],
                    status="completed",
                    transaction_hash=settlement.get("transaction", ""),
                    wallet_address=payer,
                    memo=description or f"x402 payment - {seat_count} seat(s)",
                    metadata_json=json.dumps(metadata),
                )

                db.add(payment_record)
                db.commit()
                db.refresh(payment_record)

                self.logger.info(
                    f"Payment processed: {payment_record.id} for user {user_id}"
                )

                return payment_record

        except Exception as e:
            db.rollback()
            self.logger.error(f"Payment processing failed: {str(e)}")
            raise

    def create_payment_response_header(
        self,
        transaction_id: str,
        blockchain_tx: str,
    ) -> str:
        """
        Create X-PAYMENT-RESPONSE header value for successful payment.

        Args:
            transaction_id: Facilitator transaction ID
            blockchain_tx: Blockchain transaction hash

        Returns:
            Header value string
        """
        return f"transaction_id={transaction_id}; blockchain_tx={blockchain_tx}"


def get_x402_service(
    facilitator_url: Optional[str] = None,
    merchant_wallet: Optional[str] = None,
    network: str = "solana",
) -> X402PaymentService:
    """
    Factory function to create X402PaymentService with configuration.

    Loads configuration from environment variables:
    - X402_FACILITATOR_URL: Facilitator service URL (default: https://facilitator.payai.network)
    - X402_MERCHANT_WALLET: Merchant wallet address (required)
    - X402_NETWORK: Blockchain network (passed as parameter, default: solana)
    """
    if facilitator_url is None:
        facilitator_url = getenv(
            "X402_FACILITATOR_URL", "https://facilitator.payai.network"
        )

    if merchant_wallet is None:
        merchant_wallet = getenv("X402_MERCHANT_WALLET", "")

    if not merchant_wallet:
        raise ValueError("X402_MERCHANT_WALLET must be configured")

    return X402PaymentService(
        facilitator_url=facilitator_url,
        merchant_wallet=merchant_wallet,
        network=network,
    )
