from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import HTTPException
from solana.rpc.async_api import AsyncClient

from Globals import getenv
from DB import PaymentTransaction, get_session
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
        if not self.wallet_address:
            raise RuntimeError("PAYMENT_WALLET_ADDRESS must be configured")

    async def create_invoice(
        self,
        *,
        seat_count: int,
        currency: str,
        expires_in_minutes: int,
        memo: Optional[str] = None,
        user_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        quote = await self.price_service.get_quote(currency, seat_count)
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
                seat_count=seat_count,
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
        async with AsyncClient(self.rpc_url) as client:
            response = await client.get_transaction(
                transaction_hash,
                encoding="jsonParsed",
                commitment="confirmed",
            )
        value = response.value
        if not value:
            raise HTTPException(
                status_code=404, detail="Transaction not found on Solana"
            )

        meta = value.get("meta")
        if not meta:
            raise HTTPException(
                status_code=400, detail="Transaction metadata unavailable"
            )

        if meta.get("err") is not None:
            raise HTTPException(status_code=400, detail="Transaction failed on-chain")

        account_keys = [
            key["pubkey"] if isinstance(key, dict) else key
            for key in value["transaction"]["message"]["accountKeys"]
        ]

        currency_details = SUPPORTED_CURRENCIES.get(record.currency.upper())
        if not currency_details:
            raise HTTPException(
                status_code=400, detail="Unsupported currency configured for invoice"
            )

        if record.currency.upper() == "SOL":
            received_amount = self._extract_sol_amount(
                meta, account_keys, self.wallet_address
            )
        else:
            received_amount = self._extract_token_amount(
                meta,
                self.wallet_address,
                currency_details.get("mint"),
                currency_details.get("decimals", 9),
            )

        expected_amount = Decimal(str(record.amount_currency))
        if received_amount < expected_amount * CONFIRMATION_TOLERANCE:
            raise HTTPException(
                status_code=400,
                detail="Received amount is below required threshold",
            )

        record.transaction_hash = transaction_hash
        record.status = "completed"
        record.metadata_json = json.dumps(
            {
                **(json.loads(record.metadata_json or "{}")),
                "slot": value.get("slot"),
                "block_time": value.get("blockTime"),
                "confirmed_amount": str(received_amount),
            }
        )

    @staticmethod
    def _extract_sol_amount(
        meta: Dict[str, Any], account_keys: Any, wallet_address: str
    ) -> Decimal:
        try:
            index = account_keys.index(wallet_address)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Wallet address not present in transaction"
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
