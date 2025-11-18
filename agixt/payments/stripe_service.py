from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal, ROUND_UP
from typing import Any, Dict, Optional

from fastapi import HTTPException

from Globals import getenv
from DB import PaymentTransaction, User, UserPreferences, get_session
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

    async def create_customer_portal_session(
        self,
        *,
        user_id: str,
        email: str,
        seat_count: Optional[int] = None,
        return_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )
        if not user_id:
            raise HTTPException(status_code=401, detail="User context missing")
        if seat_count is not None and seat_count < 1:
            raise HTTPException(status_code=400, detail="Seat count must be at least 1")

        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            stripe_pref = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == user_id)
                .filter(UserPreferences.pref_key == "stripe_id")
                .first()
            )
            customer_id = stripe_pref.pref_value if stripe_pref else None
            if not customer_id or not customer_id.startswith("cus_"):
                customer_id = await self._create_customer_async(
                    email=email or user.email,
                    metadata={"user_id": str(user_id)},
                )
                if stripe_pref:
                    stripe_pref.pref_value = customer_id
                else:
                    session.add(
                        UserPreferences(
                            user_id=user_id,
                            pref_key="stripe_id",
                            pref_value=customer_id,
                        )
                    )
                session.commit()

            seat_pref = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == user_id)
                .filter(UserPreferences.pref_key == "seat_count")
                .first()
            )

            current_seat_count: Optional[int] = None
            if seat_count is not None:
                if seat_pref:
                    seat_pref.pref_value = str(seat_count)
                else:
                    session.add(
                        UserPreferences(
                            user_id=user_id,
                            pref_key="seat_count",
                            pref_value=str(seat_count),
                        )
                    )
                current_seat_count = seat_count
                session.commit()
            elif seat_pref and seat_pref.pref_value:
                try:
                    current_seat_count = int(seat_pref.pref_value)
                except (TypeError, ValueError):
                    current_seat_count = None
        finally:
            session.close()

        if seat_count is not None:
            await self._update_customer_metadata_async(
                customer_id=customer_id,
                metadata={"seat_count": str(seat_count)},
            )

        portal_session = await self._create_portal_session_async(
            customer_id=customer_id,
            return_url=return_url,
        )

        session_url = portal_session.get("url")
        if not session_url:
            raise HTTPException(
                status_code=502, detail="Stripe portal session creation failed"
            )

        return {
            "url": session_url,
            "customer_id": customer_id,
            "seat_count": current_seat_count,
        }

    async def create_token_payment_intent(
        self,
        *,
        amount_usd: float,
        token_amount: int,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create payment intent for token purchase"""
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        # Defensive: do not create Stripe payment intents for zero or negative amounts
        try:
            amount_decimal = Decimal(str(amount_usd))
        except Exception:
            amount_decimal = Decimal("0")

        if amount_decimal <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid amount: billing is disabled or the requested amount is zero",
            )

        amount_cents = int(
            (amount_decimal * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_UP)
        )
        reference_code = uuid.uuid4().hex[:12].upper()

        stripe_payload = await self._create_payment_intent_async(
            amount_cents=amount_cents,
            metadata={
                **(metadata or {}),
                "reference_code": reference_code,
                "token_amount": token_amount,
                "type": "token_purchase",
            },
        )

        session = get_session()
        try:
            record = PaymentTransaction(
                reference_code=reference_code,
                user_id=user_id,
                company_id=company_id,
                seat_count=0,  # Not seat-based
                token_amount=token_amount,
                payment_method="stripe",
                currency="USD",
                network="stripe",
                amount_usd=amount_usd,
                amount_currency=amount_usd,
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
            "amount_usd": amount_usd,
            "token_amount": token_amount,
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

    async def _create_customer_async(
        self, *, email: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        import stripe

        stripe.api_key = self.api_key

        def _create_customer() -> Dict[str, Any]:
            return stripe.Customer.create(email=email, metadata=metadata)

        customer = await asyncio.to_thread(_create_customer)
        customer_id = customer.get("id")
        if not customer_id:
            raise HTTPException(
                status_code=502, detail="Stripe customer creation failed"
            )
        return customer_id

    async def _update_customer_metadata_async(
        self, *, customer_id: str, metadata: Dict[str, Any]
    ) -> None:
        import stripe

        stripe.api_key = self.api_key

        def _update_customer() -> None:
            stripe.Customer.modify(customer_id, metadata=metadata)

        await asyncio.to_thread(_update_customer)

    async def _create_portal_session_async(
        self, *, customer_id: str, return_url: Optional[str]
    ) -> Dict[str, Any]:
        import stripe

        stripe.api_key = self.api_key
        default_return = (
            return_url
            or getenv("BILLING_PORTAL_RETURN_URL")
            or getenv("APP_URI")
            or "https://agixt.com"
        )

        def _create_session() -> Dict[str, Any]:
            return stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=default_return,
            )

        return await asyncio.to_thread(_create_session)
