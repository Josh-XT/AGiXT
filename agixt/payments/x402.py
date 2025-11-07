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
from typing import Dict, Optional, Any
from decimal import Decimal
import httpx
from sqlalchemy.orm import Session

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

    def create_payment_request(
        self,
        amount: Decimal,
        currency: str = "USDC",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a payment request that will be returned in a 402 response.

        Args:
            amount: Payment amount in the specified currency
            currency: Currency code (USDC, SOL, ETH, etc.)
            description: Human-readable payment description
            metadata: Optional metadata to include

        Returns:
            Payment request dictionary to include in 402 response body
        """
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
        }

        if metadata:
            payment_request["metadata"] = metadata

        return payment_request

    async def verify_payment(
        self,
        payment_payload: str,
        expected_amount: Decimal,
        expected_currency: str = "USDC",
    ) -> Dict[str, Any]:
        """
        Verify a payment payload via the facilitator.

        Args:
            payment_payload: Payment payload from X-PAYMENT header
            expected_amount: Expected payment amount
            expected_currency: Expected currency

        Returns:
            Verification result from facilitator

        Raises:
            X402FacilitatorError: If verification fails
        """
        verify_url = f"{self.facilitator_url}/verify"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    verify_url,
                    json={
                        "payload": payment_payload,
                        "merchant_wallet": self.merchant_wallet,
                        "network": self.network,
                        "expected_amount": str(expected_amount),
                        "expected_currency": expected_currency,
                    },
                )

                if response.status_code != 200:
                    error_msg = (
                        f"Facilitator verification failed: {response.status_code}"
                    )
                    if response.text:
                        error_msg += f" - {response.text}"
                    self.logger.error(error_msg)
                    raise X402FacilitatorError(error_msg)

                result = response.json()

                if not result.get("valid", False):
                    error_msg = f"Invalid payment: {result.get('reason', 'Unknown')}"
                    self.logger.error(error_msg)
                    raise X402FacilitatorError(error_msg)

                self.logger.info(f"Payment verified: {result.get('transaction_id')}")
                return result

        except httpx.HTTPError as e:
            error_msg = f"HTTP error during verification: {str(e)}"
            self.logger.error(error_msg)
            raise X402FacilitatorError(error_msg)

    async def settle_payment(
        self,
        transaction_id: str,
        payment_payload: str,
    ) -> Dict[str, Any]:
        """
        Settle a verified payment via the facilitator.

        Args:
            transaction_id: Transaction ID from verification
            payment_payload: Payment payload from X-PAYMENT header

        Returns:
            Settlement result from facilitator

        Raises:
            X402FacilitatorError: If settlement fails
        """
        settle_url = f"{self.facilitator_url}/settle"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    settle_url,
                    json={
                        "transaction_id": transaction_id,
                        "payload": payment_payload,
                        "merchant_wallet": self.merchant_wallet,
                        "network": self.network,
                    },
                )

                if response.status_code != 200:
                    error_msg = f"Facilitator settlement failed: {response.status_code}"
                    if response.text:
                        error_msg += f" - {response.text}"
                    self.logger.error(error_msg)
                    raise X402FacilitatorError(error_msg)

                result = response.json()

                if not result.get("settled", False):
                    error_msg = f"Settlement failed: {result.get('reason', 'Unknown')}"
                    self.logger.error(error_msg)
                    raise X402FacilitatorError(error_msg)

                self.logger.info(f"Payment settled: {result.get('blockchain_tx')}")
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
            db: Database session

        Returns:
            PaymentTransaction database record

        Raises:
            X402FacilitatorError: If verification or settlement fails
        """
        if db is None:
            db = get_session()

        try:
            # Verify payment
            verification = await self.verify_payment(
                payment_payload=payment_payload,
                expected_amount=amount,
                expected_currency=currency,
            )

            transaction_id = verification.get("transaction_id")

            # Settle payment
            settlement = await self.settle_payment(
                transaction_id=transaction_id,
                payment_payload=payment_payload,
            )

            # Record in database
            payment_record = PaymentTransaction(
                user_id=user_id,
                amount=float(amount),
                currency=currency,
                status="completed",
                transaction_hash=settlement.get("blockchain_tx", transaction_id),
                payment_method="x402",
                description=description,
                metadata={
                    "network": self.network,
                    "facilitator_tx_id": transaction_id,
                    "merchant_wallet": self.merchant_wallet,
                    "verification": verification,
                    "settlement": settlement,
                },
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
    - X402_FACILITATOR_URL: Facilitator service URL (default: https://x402.org/facilitator)
    - X402_MERCHANT_WALLET: Merchant wallet address (required)
    - X402_NETWORK: Blockchain network (passed as parameter, default: solana)
    """
    if facilitator_url is None:
        facilitator_url = getenv("X402_FACILITATOR_URL", "https://x402.org/facilitator")

    if merchant_wallet is None:
        merchant_wallet = getenv("X402_MERCHANT_WALLET", "")

    if not merchant_wallet:
        raise ValueError("X402_MERCHANT_WALLET must be configured")

    return X402PaymentService(
        facilitator_url=facilitator_url,
        merchant_wallet=merchant_wallet,
        network=network,
    )
