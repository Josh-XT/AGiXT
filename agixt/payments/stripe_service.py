from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal, ROUND_UP
from typing import Any, Dict, Optional

from fastapi import HTTPException

from Globals import getenv
from DB import PaymentTransaction, get_session
from .pricing import PriceService


class StripePaymentService:
    """Wrapper around Stripe PaymentIntent for seat-based billing."""

    def __init__(self, price_service: Optional[PriceService] = None) -> None:
        self.price_service = price_service or PriceService()
        self.api_key = getenv("STRIPE_API_KEY")

    async def create_payment_intent(
        self,
        *,
        seat_count: int,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )
        if seat_count < 1:
            raise HTTPException(status_code=400, detail="Seat count must be at least 1")

        amount_usd = self.price_service.base_price_usd * Decimal(seat_count)
        amount_cents = int(
            (amount_usd * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_UP)
        )
        reference_code = uuid.uuid4().hex[:12].upper()

        stripe_payload = await self._create_payment_intent_async(
            amount_cents=amount_cents,
            metadata={
                **(metadata or {}),
                "reference_code": reference_code,
                "seat_count": seat_count,
            },
        )

        session = get_session()
        try:
            record = PaymentTransaction(
                reference_code=reference_code,
                user_id=user_id,
                company_id=company_id,
                seat_count=seat_count,
                payment_method="stripe",
                currency="USD",
                network="stripe",
                amount_usd=float(amount_usd),
                amount_currency=float(amount_usd),
                exchange_rate=1.0,
                stripe_payment_intent_id=stripe_payload["id"],
                status=stripe_payload.get("status", "requires_payment_method"),
                metadata_json=json.dumps(metadata or {}),
            )
            session.add(record)
            session.commit()
        finally:
            session.close()

        return {
            "reference_code": reference_code,
            "client_secret": stripe_payload["client_secret"],
            "payment_intent_id": stripe_payload["id"],
            "amount_usd": float(amount_usd),
            "seat_count": seat_count,
            "status": stripe_payload.get("status"),
        }

    async def _create_payment_intent_async(
        self, *, amount_cents: int, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        import stripe

        stripe.api_key = self.api_key

        def _create_intent() -> Dict[str, Any]:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                automatic_payment_methods={"enabled": True},
                metadata=metadata,
            )
            return intent

        return await asyncio.to_thread(_create_intent)
