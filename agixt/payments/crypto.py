from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import HTTPException
from solana.rpc.async_api import AsyncClient
from solders.signature import Signature

from Globals import getenv
from DB import PaymentTransaction, User, get_session
from .pricing import PriceService, SUPPORTED_CURRENCIES

CONFIRMATION_TOLERANCE = Decimal("0.995")  # Allow 0.5% slippage on received amount
LAMPORTS_PER_SOL = Decimal("1000000000")


class CryptoPaymentService:
    def __init__(self, price_service: Optional[PriceService] = None) -> None:
        self.price_service = price_service or PriceService()
        self.wallet_address = getenv("PAYMENT_WALLET_ADDRESS")
        self.rpc_url = getenv(
            "PAYMENT_SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
        )

    async def create_invoice(
        self,
        *,
        amount_usd: Optional[float] = None,
        seat_count: Optional[int] = None,
        token_amount: Optional[int] = None,
        currency: str,
        expires_in_minutes: int = 30,
        memo: Optional[str] = None,
        user_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Support both seat-based and token-based billing
        if amount_usd is not None:
            # Token-based: amount_usd already provided
            quote_amount_usd = Decimal(str(amount_usd))
            # Still need to get currency conversion
            rate = await self.price_service._get_rate(currency.upper())
            symbol = currency.upper()
            decimals = SUPPORTED_CURRENCIES[symbol]["decimals"]
            amount_currency = self.price_service._quantize(
                quote_amount_usd / rate, decimals
            )
            quote = {
                "currency": symbol,
                "network": SUPPORTED_CURRENCIES[symbol].get("network"),
                "amount_usd": float(quote_amount_usd),
                "amount_currency": float(amount_currency),
                "exchange_rate": float(self.price_service._quantize(rate, 8)),
                "mint": SUPPORTED_CURRENCIES[symbol].get("mint"),
            }
            actual_seat_count = seat_count or 0
        else:
            # Seat-based: use existing logic
            if seat_count is None:
                raise HTTPException(
                    status_code=400, detail="Either amount_usd or seat_count required"
                )
            quote = await self.price_service.get_quote(currency, seat_count)
            actual_seat_count = seat_count

        reference_code = self._generate_reference()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
        memo_value = memo or f"AGIXT-{reference_code}"

        metadata: Dict[str, Any] = {"mint": quote.get("mint")}

        session = get_session()
        try:
            record = PaymentTransaction(
                reference_code=reference_code,
                user_id=user_id,
                company_id=company_id,
                seat_count=actual_seat_count,
                token_amount=token_amount,
                payment_method="crypto",
                currency=quote["currency"],
                network=quote.get("network"),
                amount_usd=quote["amount_usd"],
                amount_currency=quote["amount_currency"],
                exchange_rate=quote["exchange_rate"],
                wallet_address=self.wallet_address,
                memo=memo_value,
                expires_at=expires_at,
                metadata_json=json.dumps(metadata),
            )
            session.add(record)
            session.commit()
        finally:
            session.close()

        return {
            **quote,
            "reference_code": reference_code,
            "wallet_address": self.wallet_address,
            "memo": memo_value,
            "expires_at": expires_at,
        }

    async def verify_transaction(
        self,
        reference_code: str,
        transaction_hash: str,
        expected_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = get_session()
        try:
            record = (
                session.query(PaymentTransaction)
                .filter(PaymentTransaction.reference_code == reference_code)
                .first()
            )
            if not record:
                raise HTTPException(status_code=404, detail="Invoice not found")

            if (
                expected_user_id
                and record.user_id
                and record.user_id != expected_user_id
            ):
                raise HTTPException(
                    status_code=403, detail="Invoice does not belong to this user"
                )

            if record.status == "completed":
                if (
                    record.transaction_hash
                    and record.transaction_hash != transaction_hash
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Invoice already settled with different transaction hash",
                    )
                return self._serialize_record(record)

            expires_at = record.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at and expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Invoice has expired")

            if record.network != "solana":
                raise HTTPException(
                    status_code=400, detail="Unsupported network for verification"
                )

            await self._verify_on_solana(record, transaction_hash, session)
            session.commit()
            session.refresh(record)
            return self._serialize_record(record)
        finally:
            session.close()

    async def _verify_on_solana(
        self, record: PaymentTransaction, transaction_hash: str, session
    ) -> None:
        # Convert transaction hash string to Signature object
        try:
            signature = Signature.from_string(transaction_hash)
        except (ValueError, Exception) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid transaction signature format: {str(e)}",
            )

        async with AsyncClient(self.rpc_url) as client:
            response = await client.get_transaction(
                signature,
                encoding="jsonParsed",
                commitment="confirmed",
            )
        value = response.value
        if not value:
            raise HTTPException(
                status_code=404, detail="Transaction not found on Solana"
            )

        # Access transaction metadata from solders object
        meta = value.transaction.meta
        if not meta:
            raise HTTPException(
                status_code=400, detail="Transaction metadata unavailable"
            )

        if meta.err is not None:
            raise HTTPException(status_code=400, detail="Transaction failed on-chain")

        # Extract account keys from the transaction message
        transaction = value.transaction.transaction
        raw_keys = transaction.message.account_keys

        # Handle both ParsedAccount objects (from jsonParsed encoding) and raw keys
        if raw_keys and hasattr(raw_keys[0], "pubkey"):
            # ParsedAccount objects - extract pubkey attribute
            account_keys = [str(key.pubkey) for key in raw_keys]
        else:
            # Raw public keys
            account_keys = [str(key) for key in raw_keys]

        # Convert token balances from solders objects to dictionaries
        def convert_token_balance(tb):
            """Convert solders UiTransactionTokenBalance to dictionary."""
            return {
                "accountIndex": tb.account_index,
                "mint": str(tb.mint),
                "owner": str(tb.owner) if tb.owner else None,
                "programId": (
                    str(tb.program_id)
                    if hasattr(tb, "program_id") and tb.program_id
                    else None
                ),
                "uiTokenAmount": {
                    "amount": str(tb.ui_token_amount.amount),
                    "decimals": tb.ui_token_amount.decimals,
                    "uiAmount": tb.ui_token_amount.ui_amount,
                    "uiAmountString": tb.ui_token_amount.ui_amount_string,
                },
            }

        pre_token_balances = getattr(meta, "pre_token_balances", [])
        post_token_balances = getattr(meta, "post_token_balances", [])

        # Convert meta to dictionary for compatibility with existing extraction methods
        meta_dict = {
            "preBalances": meta.pre_balances,
            "postBalances": meta.post_balances,
            "preTokenBalances": (
                [convert_token_balance(tb) for tb in pre_token_balances]
                if pre_token_balances
                else []
            ),
            "postTokenBalances": (
                [convert_token_balance(tb) for tb in post_token_balances]
                if post_token_balances
                else []
            ),
        }

        currency_details = SUPPORTED_CURRENCIES.get(record.currency.upper())
        if not currency_details:
            raise HTTPException(
                status_code=400, detail="Unsupported currency configured for invoice"
            )

        if record.currency.upper() == "SOL":
            received_amount = self._extract_sol_amount(
                meta_dict, account_keys, self.wallet_address
            )
        else:
            received_amount = self._extract_token_amount(
                meta_dict,
                self.wallet_address,
                currency_details.get("mint"),
                currency_details.get("decimals", 9),
            )

        expected_amount = Decimal(str(record.amount_currency))
        if received_amount < expected_amount * CONFIRMATION_TOLERANCE:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Payment verification failed",
                    "expected_amount": str(expected_amount),
                    "received_amount": str(received_amount),
                    "currency": record.currency,
                    "reason": "Transaction does not contain the required payment amount to the merchant wallet",
                },
            )

        record.transaction_hash = transaction_hash
        record.status = "completed"
        record.metadata_json = json.dumps(
            {
                **(json.loads(record.metadata_json or "{}")),
                "slot": value.slot,
                "block_time": value.block_time,
                "confirmed_amount": str(received_amount),
            }
        )

        # Credit tokens to company if this is a token purchase
        if record.token_amount and record.company_id:
            from MagicalAuth import MagicalAuth

            auth = MagicalAuth()
            auth.add_tokens_to_company(
                company_id=record.company_id,
                token_amount=record.token_amount,
                amount_usd=float(record.amount_usd),
            )
            # Send Discord notification for token top-up
            try:
                from middleware import send_discord_topup_notification

                # Get user email from record
                user_email = "Unknown"
                if record.user_id:
                    session = get_session()
                    user = session.query(User).filter(User.id == record.user_id).first()
                    if user:
                        user_email = user.email
                    session.close()
                await send_discord_topup_notification(
                    email=user_email,
                    amount_usd=float(record.amount_usd),
                    tokens=record.token_amount,
                    company_id=str(record.company_id),
                )
            except Exception as e:
                import logging

                logging.warning(f"Failed to send Discord notification: {e}")

    @staticmethod
    def _extract_sol_amount(
        meta: Dict[str, Any], account_keys: Any, wallet_address: str
    ) -> Decimal:
        try:
            index = account_keys.index(wallet_address)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Transaction does not involve the merchant wallet",
                    "expected_wallet": wallet_address,
                    "reason": "This transaction was not sent to the correct payment address",
                },
            )
        pre_balances = meta.get("preBalances", [])
        post_balances = meta.get("postBalances", [])
        if len(pre_balances) <= index or len(post_balances) <= index:
            raise HTTPException(
                status_code=400, detail="Balance arrays missing expected index"
            )
        pre_value = Decimal(pre_balances[index]) / LAMPORTS_PER_SOL
        post_value = Decimal(post_balances[index]) / LAMPORTS_PER_SOL
        received = post_value - pre_value
        if received < Decimal("0"):
            received = Decimal("0")
        return received

    @staticmethod
    def _extract_token_amount(
        meta: Dict[str, Any], wallet_address: str, mint: Optional[str], decimals: int
    ) -> Decimal:
        if not mint:
            raise HTTPException(
                status_code=400, detail="Token mint not configured for currency"
            )

        def parse_balances(entries: Any) -> Dict[str, Decimal]:
            results: Dict[str, Decimal] = {}
            for entry in entries or []:
                owner = entry.get("owner")
                entry_mint = entry.get("mint")
                if owner != wallet_address or entry_mint != mint:
                    continue
                amount_info = entry.get("uiTokenAmount", {})
                ui_amount = amount_info.get("uiAmount")
                if ui_amount is not None:
                    results[owner] = Decimal(str(ui_amount))
                else:
                    raw_amount = Decimal(amount_info.get("amount", "0"))
                    results[owner] = raw_amount / (Decimal(10) ** decimals)
            return results

        pre_map = parse_balances(meta.get("preTokenBalances"))
        post_map = parse_balances(meta.get("postTokenBalances"))
        pre_value = pre_map.get(wallet_address, Decimal("0"))
        post_value = post_map.get(wallet_address, Decimal("0"))
        received = post_value - pre_value
        if received < Decimal("0"):
            received = Decimal("0")
        return received

    @staticmethod
    def _generate_reference() -> str:
        return uuid.uuid4().hex[:12].upper()

    @staticmethod
    def _serialize_record(record: PaymentTransaction) -> Dict[str, Any]:
        metadata = {}
        if record.metadata_json:
            try:
                metadata = json.loads(record.metadata_json)
            except json.JSONDecodeError:  # pragma: no cover - defensive guard
                metadata = {"raw": record.metadata_json}
        return {
            "reference_code": record.reference_code,
            "status": record.status,
            "currency": record.currency,
            "amount_usd": record.amount_usd,
            "amount_currency": record.amount_currency,
            "exchange_rate": record.exchange_rate,
            "transaction_hash": record.transaction_hash,
            "wallet_address": record.wallet_address,
            "memo": record.memo,
            "seat_count": record.seat_count,
            "metadata": metadata,
            "updated_at": record.updated_at,
            "expires_at": record.expires_at,
            "created_at": record.created_at,
        }
