from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal, ROUND_UP
from typing import Any, Dict, Optional

from fastapi import HTTPException

from Globals import getenv
from DB import PaymentTransaction, User, UserPreferences, Company, get_session
from .pricing import PriceService


class StripePaymentService:
    """Wrapper around Stripe for tiered plan, per-bed, seat-based, and token-based billing."""

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
        """Create a Stripe payment intent for seat-based billing.

        Gets the price per unit from the pricing configuration tiers.
        For seat-based models (per_user, per_capacity, per_location),
        the amount is calculated as: seat_count × price_per_unit
        """
        from ExtensionsHub import ExtensionsHub

        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )
        if seat_count < 1:
            raise HTTPException(status_code=400, detail="Seat count must be at least 1")

        # Get price per unit from pricing configuration
        hub = ExtensionsHub()
        pricing_config = hub.get_pricing_config()

        # Default price per unit
        price_per_unit = Decimal("75.00")

        # Get price from first tier if available
        if pricing_config and pricing_config.get("tiers"):
            first_tier = pricing_config["tiers"][0]
            tier_price = first_tier.get("price_per_unit")
            if tier_price is not None:
                price_per_unit = Decimal(str(tier_price))

        amount_usd = price_per_unit * Decimal(seat_count)
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

    async def get_or_create_company_customer(
        self,
        *,
        company_id: str,
        company_name: str,
        email: Optional[str] = None,
    ) -> str:
        """Get or create a Stripe customer for a company"""
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            # Check if company already has a Stripe customer ID
            if company.stripe_customer_id and company.stripe_customer_id.startswith(
                "cus_"
            ):
                return company.stripe_customer_id

            # Create new Stripe customer for the company
            customer_id = await self._create_customer_async(
                email=email or company.email or f"company_{company_id}@billing.local",
                metadata={
                    "company_id": str(company_id),
                    "company_name": company_name,
                },
            )

            # Store the customer ID
            company.stripe_customer_id = customer_id
            session.commit()

            return customer_id
        finally:
            session.close()

    async def create_auto_topup_subscription(
        self,
        *,
        company_id: str,
        amount_usd: float,
        user_email: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a monthly subscription for a company.

        For tiered_plan and per_bed pricing: creates a subscription for the plan amount.
        For token-based pricing: creates a monthly auto top-up subscription.
        """
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        if amount_usd < 5.0:
            raise HTTPException(
                status_code=400, detail="Minimum monthly top-up is $5.00"
            )

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            # Get or create Stripe customer for company
            customer_id = await self.get_or_create_company_customer(
                company_id=company_id,
                company_name=company.name or f"Company {company_id}",
                email=user_email or company.email,
            )

            # Create checkout session for subscription
            checkout_session = await self._create_subscription_checkout_async(
                customer_id=customer_id,
                amount_cents=int(Decimal(str(amount_usd)) * Decimal("100")),
                company_id=company_id,
                plan_id=plan_id,
                plan_name=plan_id,  # Will be resolved in the checkout method
            )

            return {
                "checkout_url": checkout_session.get("url"),
                "session_id": checkout_session.get("id"),
                "amount_usd": amount_usd,
                "company_id": company_id,
                "plan_id": plan_id,
            }
        finally:
            session.close()

    async def _create_subscription_checkout_async(
        self, *, customer_id: str, amount_cents: int, company_id: str,
        plan_id: str = None, plan_name: str = None,
        billing_interval: str = "month",
    ) -> Dict[str, Any]:
        """Create a Stripe checkout session for a subscription.

        Args:
            billing_interval: 'month' or 'year'
        """
        import stripe
        from ExtensionsHub import ExtensionsHub

        stripe.api_key = self.api_key

        return_url = (
            getenv("BILLING_PORTAL_RETURN_URL")
            or getenv("APP_URI")
            or "https://agixt.com"
        )

        # Get app name for product naming
        hub = ExtensionsHub()
        pricing_config = hub.get_pricing_config()
        app_name = pricing_config.get("app_name") if pricing_config else None
        if not app_name:
            app_name = getenv("APP_NAME") or "AGiXT"

        pricing_model = (
            pricing_config.get("pricing_model") if pricing_config else "per_token"
        )

        # Build product description based on pricing model
        interval_label = "Annual" if billing_interval == "year" else "Monthly"
        if pricing_model == "tiered_plan" and plan_name:
            product_name = f"{app_name} {plan_name} Plan ({interval_label})"
            product_description = f"{plan_name} plan for {app_name}"
        elif pricing_model == "per_bed":
            product_name = f"{app_name} Subscription ({interval_label})"
            product_description = f"Per-bed subscription for {app_name}"
        else:
            product_name = f"{app_name} {interval_label} Subscription"
            product_description = f"{interval_label} subscription for {app_name}"

        def _create_checkout() -> Dict[str, Any]:
            amount_usd = amount_cents / 100
            success_params = f"method=subscription&amount={amount_usd}"
            if plan_id:
                success_params += f"&plan_id={plan_id}"

            metadata = {
                "company_id": str(company_id),
                "type": "auto_topup_subscription",
                "amount_usd": str(amount_usd),
                "app_name": app_name,
                "pricing_model": pricing_model,
                "billing_interval": billing_interval,
            }
            if plan_id:
                metadata["plan_id"] = plan_id

            checkout = stripe.checkout.Session.create(
                customer=customer_id,
                mode="subscription",
                success_url=f"{return_url}/thank-you?{success_params}",
                cancel_url=f"{return_url}/billing?subscription=cancelled",
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": product_name,
                                "description": product_description,
                            },
                            "unit_amount": amount_cents,
                            "recurring": {
                                "interval": billing_interval,
                            },
                        },
                        "quantity": 1,
                    }
                ],
                metadata=metadata,
                subscription_data={
                    "metadata": metadata,
                },
            )
            return checkout

        return await asyncio.to_thread(_create_checkout)

    async def get_auto_topup_status(self, *, company_id: str) -> Dict[str, Any]:
        """Get the subscription status for a company.

        For tiered_plan pricing:
        - Returns plan_id, plan limits, and usage
        - Includes addon info

        For per_bed pricing (NurseXT):
        - Returns bed count and monthly cost

        For seat-based pricing models (per_user, per_capacity, per_location):
        - Returns user_limit as seat_count (paid capacity)
        - Returns actual_user_count

        For token-based pricing:
        - Returns stored auto_topup_amount_usd
        """
        from DB import UserCompany
        from datetime import datetime, timedelta, timezone
        from ExtensionsHub import ExtensionsHub

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            # Determine pricing model from ExtensionsHub
            hub = ExtensionsHub()
            pricing_config = hub.get_pricing_config()
            pricing_model = (
                pricing_config.get("pricing_model", "per_token").lower()
                if pricing_config
                else "per_token"
            )
            is_seat_based = pricing_model in [
                "per_user",
                "per_capacity",
                "per_location",
            ]

            # Get actual user count
            actual_user_count = (
                session.query(UserCompany)
                .filter(UserCompany.company_id == company_id)
                .count()
            )

            # Build base result
            if pricing_model == "tiered_plan":
                plan_id = company.plan_id
                tier = {}
                if plan_id and pricing_config:
                    for t in pricing_config.get("tiers", []):
                        if t.get("id") == plan_id:
                            tier = t
                            break

                limits = tier.get("limits", {})
                user_limit = (limits.get("users") or 0) + (company.addon_users or 0)
                device_limit = (limits.get("devices") or 0) + (company.addon_devices or 0)
                token_limit = (limits.get("tokens") or 0) + (company.addon_tokens or 0)
                storage_gb = (limits.get("storage_gb") or 0)
                storage_limit_bytes = storage_gb * 1024 * 1024 * 1024 + (company.addon_storage_bytes or 0)

                amount_usd = tier.get("price", 0)
                seat_count = user_limit
            elif pricing_model == "per_bed":
                bed_limit = company.bed_limit or 0
                price_per_bed = pricing_config.get("price_per_unit", 10.0) if pricing_config else 10.0
                amount_usd = bed_limit * price_per_bed
                seat_count = bed_limit
            elif is_seat_based:
                seat_count = company.user_limit or 1
                price_per_unit = 75.0
                if pricing_config and pricing_config.get("tiers"):
                    price_per_unit = float(
                        pricing_config["tiers"][0].get("price_per_unit", 75)
                    )
                amount_usd = seat_count * price_per_unit
            else:
                seat_count = 0
                amount_usd = company.auto_topup_amount_usd

            # Check trial status
            trial_info = None
            if company.trial_credits_granted and company.trial_credits_granted_at:
                trial_config = pricing_config.get("trial", {}) if pricing_config else {}
                trial_days = trial_config.get("days")

                if trial_days is not None:
                    trial_end = company.trial_credits_granted_at + timedelta(
                        days=trial_days
                    )
                    is_trial_active = datetime.now(timezone.utc).replace(tzinfo=None) < trial_end
                    days_remaining = max(0, (trial_end - datetime.now(timezone.utc).replace(tzinfo=None)).days)
                    trial_end_str = trial_end.isoformat()
                else:
                    is_trial_active = (company.token_balance_usd or 0) > 0
                    days_remaining = None
                    trial_end_str = None

                trial_info = {
                    "credits_granted": company.trial_credits_granted,
                    "credits_remaining": company.token_balance_usd or 0,
                    "granted_at": company.trial_credits_granted_at.isoformat(),
                    "trial_end": trial_end_str,
                    "is_active": is_trial_active,
                    "days_remaining": days_remaining,
                    "domain": company.trial_domain,
                }

            result = {
                "enabled": company.auto_topup_enabled,
                "amount_usd": amount_usd,
                "seat_count": seat_count,
                "actual_user_count": actual_user_count,
                "subscription_id": company.stripe_subscription_id,
                "subscription_status": None,
                "next_billing_date": None,
                "app_name": company.app_name,
                "pricing_model": pricing_model,
                "last_billing_date": (
                    company.last_subscription_billing_date.isoformat()
                    if company.last_subscription_billing_date
                    else None
                ),
                "trial": trial_info,
            }

            # Add tiered plan details
            if pricing_model == "tiered_plan":
                result["plan"] = {
                    "id": company.plan_id,
                    "name": tier.get("name", "None"),
                    "price": tier.get("price", 0),
                    "limits": {
                        "users": user_limit,
                        "devices": device_limit,
                        "tokens_per_month": token_limit,
                        "storage_gb": round(storage_limit_bytes / (1024 * 1024 * 1024), 2),
                    },
                    "usage": {
                        "users": actual_user_count,
                        "devices": company.device_count or 0,
                        "tokens_this_period": company.tokens_used_this_period or 0,
                        "storage_gb": round((company.storage_used_bytes or 0) / (1024 * 1024 * 1024), 2),
                    },
                    "addons": {
                        "users": company.addon_users or 0,
                        "devices": company.addon_devices or 0,
                        "tokens": company.addon_tokens or 0,
                        "storage_bytes": company.addon_storage_bytes or 0,
                    },
                }
            elif pricing_model == "per_bed":
                result["plan"] = {
                    "id": company.plan_id,
                    "bed_limit": company.bed_limit or 0,
                    "bed_count": company.bed_count or 0,
                    "price_per_bed": pricing_config.get("price_per_unit", 10.0) if pricing_config else 10.0,
                    "monthly_cost": amount_usd,
                }

            # If there's an active subscription, get more details from Stripe
            if company.stripe_subscription_id and self.api_key:
                try:
                    subscription = await self._get_subscription_async(
                        company.stripe_subscription_id
                    )
                    if subscription:
                        result["subscription_status"] = subscription.get("status")
                        if subscription.get("current_period_end"):
                            result["next_billing_date"] = datetime.fromtimestamp(
                                subscription["current_period_end"]
                            ).isoformat()
                except Exception as e:
                    logging.debug(f"Could not fetch Stripe subscription details: {e}")

            return result
        finally:
            session.close()

    async def _get_subscription_async(
        self, subscription_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a subscription from Stripe"""
        import stripe

        stripe.api_key = self.api_key

        def _get_subscription() -> Optional[Dict[str, Any]]:
            try:
                return stripe.Subscription.retrieve(subscription_id)
            except stripe.error.InvalidRequestError:
                return None

        return await asyncio.to_thread(_get_subscription)

    async def create_plan_checkout(
        self,
        *,
        company_id: str,
        plan_id: str,
        user_email: Optional[str] = None,
        billing_interval: str = "month",
    ) -> Dict[str, Any]:
        """Create a Stripe checkout session for a specific plan tier.

        For tiered_plan pricing: looks up the tier price and creates a subscription.
        For per_bed pricing: calculates price based on bed count (plan_id = bed count string).

        Args:
            billing_interval: 'month' or 'year'. Annual pricing applies discount if configured.
        """
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        from ExtensionsHub import ExtensionsHub

        hub = ExtensionsHub()
        pricing_config = hub.get_pricing_config()
        if not pricing_config:
            raise HTTPException(status_code=400, detail="No pricing configuration found")

        pricing_model = pricing_config.get("pricing_model", "per_token")

        if pricing_model == "tiered_plan":
            # Find the tier
            tier = None
            for t in pricing_config.get("tiers", []):
                if t.get("id") == plan_id:
                    tier = t
                    break

            if not tier:
                raise HTTPException(status_code=400, detail=f"Invalid plan ID: {plan_id}")

            amount_usd = float(tier.get("price", 0))
            if amount_usd <= 0:
                raise HTTPException(status_code=400, detail="Plan has no price configured")

            plan_name = tier.get("name", plan_id)

            # Apply annual discount if applicable
            if billing_interval == "year":
                contracts = pricing_config.get("contracts", {})
                annual_discount = float(contracts.get("annual_discount_percent", 0))
                if annual_discount > 0:
                    amount_usd = amount_usd * 12 * (1 - annual_discount / 100)
                else:
                    amount_usd = amount_usd * 12  # No discount, just 12x monthly

        elif pricing_model == "per_bed":
            try:
                bed_count = int(plan_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="For NurseXT, plan_id should be the bed count")

            min_beds = pricing_config.get("min_units", 5)
            if bed_count < min_beds:
                raise HTTPException(status_code=400, detail=f"Minimum bed count is {min_beds}")

            price_per_bed = float(pricing_config.get("price_per_unit", 10.0))
            amount_usd = bed_count * price_per_bed
            plan_name = f"{bed_count} Beds"

            # Apply annual pricing for per-bed
            if billing_interval == "year":
                contracts = pricing_config.get("contracts", {})
                annual_discount = float(contracts.get("annual_discount_percent", 0))
                if annual_discount > 0:
                    amount_usd = amount_usd * 12 * (1 - annual_discount / 100)
                else:
                    amount_usd = amount_usd * 12
        else:
            raise HTTPException(status_code=400, detail="Plan checkout only available for tiered or per-bed pricing")

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            customer_id = await self.get_or_create_company_customer(
                company_id=company_id,
                company_name=company.name or f"Company {company_id}",
                email=user_email or company.email,
            )

            # If already has a subscription, cancel old one first
            if company.stripe_subscription_id:
                try:
                    await self._cancel_subscription_async(company.stripe_subscription_id)
                except Exception as e:
                    logging.warning(
                        f"Failed to cancel old subscription {company.stripe_subscription_id} for company {company_id}: {e}"
                    )

            checkout_session = await self._create_subscription_checkout_async(
                customer_id=customer_id,
                amount_cents=int(Decimal(str(amount_usd)) * Decimal("100")),
                company_id=company_id,
                plan_id=plan_id,
                plan_name=plan_name,
                billing_interval=billing_interval,
            )

            return {
                "checkout_url": checkout_session.get("url"),
                "session_id": checkout_session.get("id"),
                "amount_usd": amount_usd,
                "company_id": company_id,
                "plan_id": plan_id,
                "plan_name": plan_name,
            }
        finally:
            session.close()

    async def create_token_topup_checkout(
        self,
        *,
        company_id: str,
        token_millions: int,
        user_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a one-time Stripe checkout session for token top-up.

        For tiered plans: allows purchasing additional tokens at $5/1M.
        Returns a checkout_url that the user is redirected to.
        """
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        if token_millions < 1:
            raise HTTPException(
                status_code=400, detail="Minimum purchase is 1M tokens"
            )

        from ExtensionsHub import ExtensionsHub
        hub = ExtensionsHub()
        pricing_config = hub.get_pricing_config()

        # Get token topup price
        price_per_million = 5.0  # Default
        if pricing_config:
            addons = pricing_config.get("addons", {})
            topup = addons.get("token_topup", {})
            price_per_million = float(topup.get("price_per_million", 5.0))

        amount_usd = token_millions * price_per_million
        token_amount = token_millions * 1_000_000

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            customer_id = await self.get_or_create_company_customer(
                company_id=company_id,
                company_name=company.name or f"Company {company_id}",
                email=user_email or company.email,
            )

            app_name = (
                pricing_config.get("app_name") if pricing_config else None
            ) or getenv("APP_NAME") or "AGiXT"

            import stripe
            stripe.api_key = self.api_key

            return_url = (
                getenv("BILLING_PORTAL_RETURN_URL")
                or getenv("APP_URI")
                or "https://agixt.com"
            )

            def _create_checkout():
                return stripe.checkout.Session.create(
                    customer=customer_id,
                    mode="payment",
                    success_url=f"{return_url}/thank-you?method=topup&tokens={token_millions}M",
                    cancel_url=f"{return_url}/billing?topup=cancelled",
                    line_items=[
                        {
                            "price_data": {
                                "currency": "usd",
                                "product_data": {
                                    "name": f"{app_name} Token Top-up",
                                    "description": f"{token_millions}M tokens",
                                },
                                "unit_amount": int(price_per_million * 100),
                            },
                            "quantity": token_millions,
                        }
                    ],
                    metadata={
                        "company_id": str(company_id),
                        "type": "token_topup",
                        "token_amount": str(token_amount),
                        "token_millions": str(token_millions),
                        "price_per_million": str(price_per_million),
                    },
                )

            checkout = await asyncio.to_thread(_create_checkout)

            return {
                "checkout_url": checkout.get("url"),
                "session_id": checkout.get("id"),
                "amount_usd": amount_usd,
                "token_amount": token_amount,
                "token_millions": token_millions,
                "company_id": company_id,
            }
        finally:
            session.close()

    async def create_addon_checkout(
        self,
        *,
        company_id: str,
        addon_count: int = 1,
        user_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a checkout for user/resource addons (Enterprise Plus only).

        Each addon adds: 1 user, 100 devices, 10M tokens, 2GB storage for $10/month.
        """
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        from ExtensionsHub import ExtensionsHub
        hub = ExtensionsHub()
        pricing_config = hub.get_pricing_config()
        if not pricing_config:
            raise HTTPException(status_code=400, detail="No pricing configuration found")

        # Verify billing company is on enterprise_100 plan
        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            # Resolve billing company (root parent)
            from MagicalAuth import MagicalAuth
            auth = MagicalAuth()
            root_company_id = auth.get_root_parent_company(str(company.id), session=session)
            if str(root_company_id) != str(company.id):
                billing_company = session.query(Company).filter(Company.id == root_company_id).first()
            else:
                billing_company = company

            if not billing_company or billing_company.plan_id != "enterprise_100":
                raise HTTPException(
                    status_code=400,
                    detail="Addons are only available for the Enterprise Plus plan",
                )

            addons_config = pricing_config.get("addons", {}).get("user_addon", {})
            price_per_addon = float(addons_config.get("price", 10.0))
            amount_usd = addon_count * price_per_addon

            customer_id = await self.get_or_create_company_customer(
                company_id=company_id,
                company_name=company.name or f"Company {company_id}",
                email=user_email or company.email,
            )

            app_name = pricing_config.get("app_name") or getenv("APP_NAME") or "AGiXT"

            import stripe
            stripe.api_key = self.api_key

            return_url = (
                getenv("BILLING_PORTAL_RETURN_URL")
                or getenv("APP_URI")
                or "https://agixt.com"
            )

            def _create_addon_checkout():
                return stripe.checkout.Session.create(
                    customer=customer_id,
                    mode="subscription",
                    success_url=f"{return_url}/thank-you?method=addon&count={addon_count}",
                    cancel_url=f"{return_url}/billing?addon=cancelled",
                    line_items=[
                        {
                            "price_data": {
                                "currency": "usd",
                                "product_data": {
                                    "name": f"{app_name} Resource Addon",
                                    "description": f"Adds {addon_count} user(s), {addon_count * 100} devices, {addon_count * 10}M tokens, {addon_count * 2}GB storage per month",
                                },
                                "unit_amount": int(price_per_addon * 100),
                                "recurring": {"interval": "month"},
                            },
                            "quantity": addon_count,
                        }
                    ],
                    metadata={
                        "company_id": str(billing_company.id),
                        "type": "addon_subscription",
                        "addon_count": str(addon_count),
                    },
                    subscription_data={
                        "metadata": {
                            "company_id": str(billing_company.id),
                            "type": "addon_subscription",
                            "addon_count": str(addon_count),
                        },
                    },
                )

            checkout = await asyncio.to_thread(_create_addon_checkout)

            return {
                "checkout_url": checkout.get("url"),
                "session_id": checkout.get("id"),
                "amount_usd": amount_usd,
                "addon_count": addon_count,
                "company_id": company_id,
            }
        finally:
            session.close()

    async def cancel_auto_topup_subscription(
        self, *, company_id: str
    ) -> Dict[str, Any]:
        """Cancel the auto top-up subscription for a company"""
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            if not company.stripe_subscription_id:
                raise HTTPException(
                    status_code=400, detail="No active subscription found"
                )

            # Cancel the subscription in Stripe
            await self._cancel_subscription_async(company.stripe_subscription_id)

            # Update company record
            company.auto_topup_enabled = False
            company.stripe_subscription_id = None
            session.commit()

            return {
                "success": True,
                "message": "Auto top-up subscription cancelled",
                "company_id": company_id,
            }
        finally:
            session.close()

    async def _cancel_subscription_async(self, subscription_id: str) -> None:
        """Cancel a subscription in Stripe"""
        import stripe

        stripe.api_key = self.api_key

        def _cancel_subscription() -> None:
            stripe.Subscription.cancel(subscription_id)

        await asyncio.to_thread(_cancel_subscription)

    async def update_subscription_quantity(
        self, *, company_id: str, new_quantity: int
    ) -> Dict[str, Any]:
        """Update the subscription quantity (seats) for seat-based billing.

        This modifies the existing subscription in Stripe rather than
        cancelling and recreating it.
        """
        import stripe

        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        if new_quantity < 1:
            raise HTTPException(status_code=400, detail="Quantity must be at least 1")

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            if not company.stripe_subscription_id:
                raise HTTPException(
                    status_code=400, detail="No active subscription found"
                )

            stripe.api_key = self.api_key

            # Get the subscription to find the subscription item
            subscription = stripe.Subscription.retrieve(company.stripe_subscription_id)

            if (
                not subscription
                or not subscription.items
                or not subscription.items.data
            ):
                raise HTTPException(
                    status_code=400, detail="Could not retrieve subscription items"
                )

            # Update the quantity on the first subscription item
            subscription_item_id = subscription.items.data[0].id

            # Update the subscription item quantity
            stripe.SubscriptionItem.modify(
                subscription_item_id,
                quantity=new_quantity,
                proration_behavior="create_prorations",  # Prorate charges
            )

            # Update company user_limit to match new quantity
            from ExtensionsHub import ExtensionsHub

            hub = ExtensionsHub()
            pricing_config = hub.get_pricing_config()
            price_per_unit = 75.0
            if pricing_config and pricing_config.get("tiers"):
                price_per_unit = float(
                    pricing_config["tiers"][0].get("price_per_unit", 75)
                )
            company.user_limit = new_quantity
            company.auto_topup_amount_usd = new_quantity * price_per_unit
            session.commit()

            import logging

            logging.info(
                f"Updated subscription quantity to {new_quantity} for company {company_id}"
            )

            return {
                "success": True,
                "message": f"Subscription updated to {new_quantity} seats",
                "company_id": company_id,
                "new_quantity": new_quantity,
                "new_amount_usd": new_quantity * price_per_unit,
            }
        except stripe.error.InvalidRequestError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            session.close()

    async def update_auto_topup_amount(
        self, *, company_id: str, new_amount_usd: float
    ) -> Dict[str, Any]:
        """Update the auto top-up amount for an existing subscription.

        This cancels the existing subscription and creates a new checkout
        session for the new amount.
        """
        if not self.api_key or self.api_key.lower() == "none":
            raise HTTPException(
                status_code=400, detail="Stripe API key is not configured"
            )

        if new_amount_usd < 5.0:
            raise HTTPException(
                status_code=400, detail="Minimum monthly top-up is $5.00"
            )

        session = get_session()
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            # Cancel existing subscription if any
            if company.stripe_subscription_id:
                try:
                    await self._cancel_subscription_async(
                        company.stripe_subscription_id
                    )
                except Exception as e:
                    logging.warning(
                        f"Failed to cancel old subscription {company.stripe_subscription_id} for company {company_id}: {e}"
                    )

            # Create new subscription with updated amount
            result = await self.create_auto_topup_subscription(
                company_id=company_id,
                amount_usd=new_amount_usd,
            )

            return result
        finally:
            session.close()

    async def sync_payments(
        self, *, company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sync payments from Stripe that may not have been processed by webhooks.

        This checks for:
        1. Subscription invoices that were paid but not recorded
        2. Checkout sessions that completed but weren't processed
        3. Payment intents that succeeded but weren't recorded

        For seat-based pricing models (per_user, per_capacity, per_location):
        - Updates billing dates
        - Applies credits toward subscription (if available)
        - Does NOT add tokens (payment is for seat access)

        For token-based pricing (per_token):
        - Adds tokens to the account balance

        Returns a summary of what was synced.
        """
        import stripe
        import logging
        from datetime import datetime, timedelta, timezone

        if not self.api_key or self.api_key.lower() == "none":
            return {
                "success": False,
                "message": "Stripe API key not configured",
                "synced": [],
            }

        stripe.api_key = self.api_key
        session = get_session()
        synced = []

        # Determine pricing model from ExtensionsHub
        from ExtensionsHub import ExtensionsHub

        hub = ExtensionsHub()
        pricing_config = hub.get_pricing_config()
        pricing_model = (
            pricing_config.get("pricing_model", "per_token").lower()
            if pricing_config
            else "per_token"
        )
        is_seat_based = pricing_model in ["per_user", "per_capacity", "per_location"]
        is_plan_based = pricing_model in ["tiered_plan", "per_bed"]

        try:
            # Look back 7 days for unprocessed payments
            since = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())

            # 1. Check for subscription invoices
            if company_id:
                company = (
                    session.query(Company).filter(Company.id == company_id).first()
                )
                if company and company.stripe_subscription_id:
                    try:
                        invoices = stripe.Invoice.list(
                            subscription=company.stripe_subscription_id,
                            status="paid",
                            created={"gte": since},
                            limit=10,
                        )

                        for invoice in invoices.data:
                            # Check if we already have this invoice recorded
                            existing = (
                                session.query(PaymentTransaction)
                                .filter(
                                    PaymentTransaction.stripe_payment_intent_id
                                    == invoice.id
                                )
                                .first()
                            )

                            # Also check if we already synced via checkout session for this subscription
                            if not existing:
                                existing = (
                                    session.query(PaymentTransaction)
                                    .filter(
                                        PaymentTransaction.company_id
                                        == str(company.id),
                                        PaymentTransaction.payment_method
                                        == "stripe_subscription",
                                        PaymentTransaction.reference_code.like(
                                            "SYNC_CHECKOUT_%"
                                        ),
                                        PaymentTransaction.created_at
                                        >= datetime.fromtimestamp(since),
                                    )
                                    .first()
                                )

                            if not existing:
                                amount_usd = invoice.amount_paid / 100.0
                                if amount_usd > 0:
                                    tokens = 0
                                    credits_applied = 0.0

                                    if is_seat_based or is_plan_based:
                                        # Seat-based billing: update billing dates, apply credits
                                        # Check if credits available to apply
                                        available_credits = (
                                            company.token_balance_usd or 0.0
                                        )
                                        if available_credits > 0:
                                            credits_applied = min(
                                                available_credits, amount_usd
                                            )
                                            company.token_balance_usd = (
                                                available_credits - credits_applied
                                            )
                                            logging.info(
                                                f"Applied ${credits_applied:.2f} credits toward subscription for company {company_id}"
                                            )

                                        # Update billing dates
                                        company.last_subscription_billing_date = (
                                            datetime.now(timezone.utc)
                                        )

                                        transaction = PaymentTransaction(
                                            user_id=None,
                                            company_id=str(company.id),
                                            seat_count=company.user_limit or 1,
                                            token_amount=0,
                                            payment_method="stripe_subscription",
                                            currency="USD",
                                            network="stripe",
                                            amount_usd=amount_usd,
                                            amount_currency=amount_usd,
                                            exchange_rate=1.0,
                                            stripe_payment_intent_id=invoice.id,
                                            status="completed",
                                            reference_code=f"SYNC_SUB_{company.stripe_subscription_id[:12]}_{invoice.id[:12]}",
                                            metadata_json=json.dumps({
                                                "credits_applied": credits_applied,
                                                "pricing_model": pricing_model,
                                            }),
                                        )
                                        session.add(transaction)
                                        synced.append(
                                            {
                                                "type": "subscription",
                                                "invoice_id": invoice.id,
                                                "amount_usd": amount_usd,
                                                "tokens": 0,
                                                "credits_applied": credits_applied,
                                            }
                                        )
                                        logging.info(
                                            f"Synced seat-based subscription payment: ${amount_usd} (${credits_applied:.2f} credits applied) for company {company_id}"
                                        )
                                    else:
                                        # Token-based billing: add tokens via root parent resolution
                                        token_price = float(
                                            getenv(
                                                "TOKEN_PRICE_PER_MILLION_USD", "0.50"
                                            )
                                        )
                                        if token_price <= 0:
                                            token_price = 0.50
                                        tokens = int(
                                            (amount_usd / token_price) * 1_000_000
                                        )

                                        transaction = PaymentTransaction(
                                            user_id=None,
                                            company_id=str(company.id),
                                            seat_count=0,
                                            token_amount=tokens,
                                            payment_method="stripe_subscription",
                                            currency="USD",
                                            network="stripe",
                                            amount_usd=amount_usd,
                                            amount_currency=amount_usd,
                                            exchange_rate=1.0,
                                            stripe_payment_intent_id=invoice.id,
                                            status="completed",
                                            reference_code=f"SYNC_SUB_{company.stripe_subscription_id[:12]}_{invoice.id[:12]}",
                                        )
                                        session.add(transaction)
                                        session.commit()

                                        # Credit tokens via root parent resolution
                                        from MagicalAuth import MagicalAuth

                                        auth = MagicalAuth()
                                        auth.add_tokens_to_company(
                                            company_id=str(company.id),
                                            token_amount=tokens,
                                            amount_usd=amount_usd,
                                        )

                                        synced.append(
                                            {
                                                "type": "subscription",
                                                "invoice_id": invoice.id,
                                                "amount_usd": amount_usd,
                                                "tokens": tokens,
                                            }
                                        )
                                        logging.info(
                                            f"Synced subscription payment: ${amount_usd} -> {tokens} tokens for company {company_id}"
                                        )
                    except Exception as e:
                        logging.warning(f"Error syncing subscription invoices: {e}")

            # 2. Check for completed checkout sessions with our metadata
            try:
                checkout_sessions = stripe.checkout.Session.list(
                    created={"gte": since},
                    status="complete",
                    limit=50,
                )

                for cs in checkout_sessions.data:
                    metadata = cs.get("metadata", {})
                    cs_company_id = metadata.get("company_id")

                    # Only process if it matches our company (or we're checking all)
                    if company_id and cs_company_id != company_id:
                        continue

                    if not cs_company_id:
                        continue

                    # Check if already recorded
                    existing = (
                        session.query(PaymentTransaction)
                        .filter(PaymentTransaction.stripe_payment_intent_id == cs.id)
                        .first()
                    )

                    # Also check by payment intent if available
                    if not existing and cs.payment_intent:
                        existing = (
                            session.query(PaymentTransaction)
                            .filter(
                                PaymentTransaction.stripe_payment_intent_id
                                == cs.payment_intent
                            )
                            .first()
                        )

                    if not existing:
                        company = (
                            session.query(Company)
                            .filter(Company.id == cs_company_id)
                            .first()
                        )
                        if not company:
                            continue

                        # Handle subscription checkout
                        if (
                            cs.mode == "subscription"
                            and metadata.get("type") == "auto_topup_subscription"
                        ):
                            amount_usd = float(metadata.get("amount_usd", 0))
                            subscription_id = cs.subscription

                            if subscription_id:
                                # Check if we already synced this subscription from an invoice
                                # (Stripe fires both checkout.session.completed AND invoice.payment_succeeded)
                                existing_sub_payment = (
                                    session.query(PaymentTransaction)
                                    .filter(
                                        PaymentTransaction.company_id
                                        == str(company.id),
                                        PaymentTransaction.reference_code.like(
                                            f"SYNC_SUB_{subscription_id[:12]}%"
                                        ),
                                    )
                                    .first()
                                )

                                if existing_sub_payment:
                                    # Already credited via invoice sync, just update subscription fields
                                    company.auto_topup_enabled = True
                                    company.auto_topup_amount_usd = amount_usd
                                    company.stripe_subscription_id = subscription_id
                                    logging.info(
                                        f"Skipping checkout session sync (already synced via invoice) for subscription {subscription_id}"
                                    )
                                    continue

                                company.auto_topup_enabled = True
                                company.auto_topup_amount_usd = amount_usd
                                company.stripe_subscription_id = subscription_id

                                # Credit initial tokens (only for token-based pricing)
                                if amount_usd > 0 and not is_seat_based and not is_plan_based:
                                    token_price = float(
                                        getenv("TOKEN_PRICE_PER_MILLION_USD", "0.50")
                                    )
                                    if token_price <= 0:
                                        token_price = 0.50
                                    tokens = int((amount_usd / token_price) * 1_000_000)

                                    transaction = PaymentTransaction(
                                        user_id=None,
                                        company_id=str(company.id),
                                        seat_count=0,
                                        token_amount=tokens,
                                        payment_method="stripe_subscription",
                                        currency="USD",
                                        network="stripe",
                                        amount_usd=amount_usd,
                                        amount_currency=amount_usd,
                                        exchange_rate=1.0,
                                        stripe_payment_intent_id=cs.id,
                                        status="completed",
                                        reference_code=f"SYNC_CHECKOUT_{cs.id[:20]}",
                                    )
                                    session.add(transaction)
                                    session.commit()

                                    # Credit tokens via root parent resolution
                                    from MagicalAuth import MagicalAuth

                                    auth = MagicalAuth()
                                    auth.add_tokens_to_company(
                                        company_id=str(company.id),
                                        token_amount=tokens,
                                        amount_usd=amount_usd,
                                    )

                                    synced.append(
                                        {
                                            "type": "subscription_checkout",
                                            "session_id": cs.id,
                                            "amount_usd": amount_usd,
                                            "tokens": tokens,
                                        }
                                    )
                                    logging.info(
                                        f"Synced subscription checkout: ${amount_usd} -> {tokens} tokens for company {cs_company_id}"
                                    )
                                elif amount_usd > 0:
                                    # Seat/plan-based: record transaction without token credit
                                    company.last_subscription_billing_date = (
                                        datetime.now(timezone.utc)
                                    )
                                    transaction = PaymentTransaction(
                                        user_id=None,
                                        company_id=str(company.id),
                                        seat_count=company.user_limit or 1,
                                        token_amount=0,
                                        payment_method="stripe_subscription",
                                        currency="USD",
                                        network="stripe",
                                        amount_usd=amount_usd,
                                        amount_currency=amount_usd,
                                        exchange_rate=1.0,
                                        stripe_payment_intent_id=cs.id,
                                        status="completed",
                                        reference_code=f"SYNC_CHECKOUT_{cs.id[:20]}",
                                        metadata_json=json.dumps({
                                            "pricing_model": pricing_model,
                                        }),
                                    )
                                    session.add(transaction)
                                    synced.append(
                                        {
                                            "type": "subscription_checkout",
                                            "session_id": cs.id,
                                            "amount_usd": amount_usd,
                                            "tokens": 0,
                                        }
                                    )
                                    logging.info(
                                        f"Synced {pricing_model} subscription checkout: ${amount_usd} for company {cs_company_id}"
                                    )

                        # Handle one-time token purchase checkout
                        elif (
                            cs.mode == "payment"
                            and metadata.get("type") in ("token_purchase", "token_topup")
                        ):
                            amount_usd = float(metadata.get("amount_usd", 0))
                            token_amount = int(metadata.get("token_amount", 0))

                            if amount_usd > 0 and token_amount > 0:
                                transaction = PaymentTransaction(
                                    user_id=None,
                                    company_id=str(company.id),
                                    seat_count=0,
                                    token_amount=token_amount,
                                    payment_method="stripe",
                                    currency="USD",
                                    network="stripe",
                                    amount_usd=amount_usd,
                                    amount_currency=amount_usd,
                                    exchange_rate=1.0,
                                    stripe_payment_intent_id=cs.id,
                                    status="completed",
                                    reference_code=f"SYNC_TOKEN_{cs.id[:20]}",
                                )
                                session.add(transaction)
                                session.commit()

                                # Credit tokens via root parent resolution
                                from MagicalAuth import MagicalAuth

                                auth = MagicalAuth()
                                auth.add_tokens_to_company(
                                    company_id=str(company.id),
                                    token_amount=token_amount,
                                    amount_usd=amount_usd,
                                )

                                synced.append(
                                    {
                                        "type": "token_purchase",
                                        "session_id": cs.id,
                                        "amount_usd": amount_usd,
                                        "tokens": token_amount,
                                    }
                                )
                                logging.info(
                                    f"Synced token purchase: ${amount_usd} -> {token_amount} tokens for company {cs_company_id}"
                                )

            except Exception as e:
                logging.warning(f"Error syncing checkout sessions: {e}")

            session.commit()

            return {
                "success": True,
                "synced_count": len(synced),
                "synced": synced,
            }

        except Exception as e:
            session.rollback()
            logging.error(f"Error in sync_payments: {e}")
            return {"success": False, "message": str(e), "synced": []}
        finally:
            session.close()
