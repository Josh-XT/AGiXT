import os
from fastapi import APIRouter, Header, HTTPException, Depends, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from MagicalAuth import MagicalAuth, verify_api_key, invalidate_user_scopes_cache
from payments.pricing import PriceService
from payments.crypto import CryptoPaymentService
from payments.stripe_service import StripePaymentService
from middleware import (
    send_discord_topup_notification,
    send_discord_subscription_notification,
    log_silenced_exception,
)
from DB import (
    PaymentTransaction,
    CompanyTokenUsage,
    Company,
    User,
    UserCompany,
    UserPreferences,
    get_session,
)
from sqlalchemy import desc
import logging

app = APIRouter()


# Request/Response Models
class TokenQuoteRequest(BaseModel):
    token_millions: int
    currency: str = "USD"


class TokenTopupCryptoRequest(BaseModel):
    token_millions: int
    currency: str
    company_id: Optional[str] = None


class TokenTopupStripeRequest(BaseModel):
    token_millions: int
    company_id: Optional[str] = None


class ConfirmPaymentRequest(BaseModel):
    payment_intent_id: str
    company_id: Optional[str] = None


class DismissWarningRequest(BaseModel):
    company_id: str


class AutoTopupSetupRequest(BaseModel):
    """Request to set up monthly auto top-up subscription"""

    company_id: str
    amount_usd: float = Field(
        ..., ge=5.0, description="Monthly top-up amount in USD (minimum $5)"
    )


class AutoTopupUpdateRequest(BaseModel):
    """Request to update auto top-up amount"""

    company_id: str
    amount_usd: float = Field(
        ..., ge=5.0, description="New monthly top-up amount in USD (minimum $5)"
    )


class AutoTopupCancelRequest(BaseModel):
    """Request to cancel auto top-up subscription"""

    company_id: str


# Endpoints
@app.get(
    "/v1/billing/tokens/balance",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def get_token_balance(
    company_id: str,
    sync: bool = False,
    authorization: str = Header(None),
):
    """Get company token balance - admin only. Optionally syncs payments from Stripe to catch missed webhooks."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    # Sync payments from Stripe to catch any missed webhooks
    # Skip if billing is paused
    sync_result = None
    if sync:
        from Globals import getenv

        billing_paused = getenv("BILLING_PAUSED", "false").lower() == "true"
        if not billing_paused:
            try:
                stripe_service = StripePaymentService()
                sync_result = await stripe_service.sync_payments(company_id=company_id)
            except Exception as e:
                logging.warning(f"Failed to sync payments: {e}")

    balance = auth.get_company_token_balance(company_id)
    if sync_result:
        balance["sync_result"] = sync_result
    return balance


@app.post(
    "/v1/billing/sync",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def sync_payments_endpoint(
    company_id: Optional[str] = None,
    authorization: str = Header(None),
):
    """
    Sync payments from Stripe that may not have been processed by webhooks.

    This checks for subscription invoices, completed checkout sessions, and
    token purchases that were paid but not recorded in the system.
    """
    from Globals import getenv

    # Skip sync if billing is paused
    billing_paused = getenv("BILLING_PAUSED", "false").lower() == "true"
    if billing_paused:
        return {"message": "Billing is paused, sync skipped", "synced": 0}

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # If company_id provided, verify user has access
    if company_id:
        user_companies = auth.get_user_companies()
        if company_id not in user_companies:
            raise HTTPException(
                status_code=403, detail="You do not have access to this company"
            )

    stripe_service = StripePaymentService()
    result = await stripe_service.sync_payments(company_id=company_id)
    return result


@app.post("/v1/billing/tokens/quote", tags=["Billing"])
async def get_token_purchase_quote(request: TokenQuoteRequest):
    """Get quote for token purchase"""
    price_service = PriceService()

    if request.currency.upper() == "USD":
        return await price_service.get_token_quote(request.token_millions)
    else:
        return await price_service.get_token_quote_for_currency(
            request.token_millions, request.currency
        )


@app.get("/v1/billing/pricing", tags=["Billing"])
async def get_pricing_config() -> Dict[str, Any]:
    """
    Get pricing configuration for the current application.

    Returns pricing model, tiers, trial info, and other billing configuration
    based on the extension hub's pricing.json or default token-based pricing.

    This endpoint is public (no authentication required) as pricing info
    is typically displayed on landing pages before user login.
    """
    from ExtensionsHub import ExtensionsHub

    hub = ExtensionsHub()
    config = hub.get_pricing_config()

    if config:
        # If pricing.json exists, check if it has any paid tiers
        tiers = config.get("tiers", [])
        has_paid_tiers = any(
            tier.get("price_per_unit") is not None or tier.get("custom_pricing", False)
            for tier in tiers
        )
        # Add billing_disabled field if no paid tiers
        config["billing_disabled"] = not has_paid_tiers
        return config

    # Return default token-based pricing (includes billing_disabled when token price is 0)
    return hub.get_default_pricing_config()


@app.get("/v1/billing/pricing/enabled", tags=["Billing"])
async def is_billing_enabled() -> Dict[str, Any]:
    """
    Check if billing is enabled and what type of billing model is active.

    Returns:
        Dict with billing_enabled flag and pricing_model type
    """
    from ExtensionsHub import ExtensionsHub
    from Globals import getenv

    # Check if billing is paused globally
    billing_paused = getenv("BILLING_PAUSED", "false").lower() == "true"
    if billing_paused:
        return {
            "billing_enabled": False,
            "reason": "paused",
            "pricing_model": None,
        }

    hub = ExtensionsHub()
    config = hub.get_pricing_config()

    if config:
        # Subscription-based pricing is enabled if we have a pricing.json
        # Check if any tier has actual pricing
        tiers = config.get("tiers", [])
        has_paid_tiers = any(
            tier.get("price_per_unit") is not None or tier.get("custom_pricing", False)
            for tier in tiers
        )
        return {
            "billing_enabled": has_paid_tiers,
            "pricing_model": config.get("pricing_model"),
            "app_name": config.get("app_name"),
            "unit_name": config.get("unit_name"),
        }

    # Check token-based pricing
    token_price = getenv("TOKEN_PRICE_PER_MILLION_USD")
    try:
        token_price_float = float(token_price) if token_price else 0.0
    except (ValueError, TypeError):
        token_price_float = 0.0

    return {
        "billing_enabled": token_price_float > 0,
        "pricing_model": "per_token" if token_price_float > 0 else None,
        "token_price_per_million": token_price_float,
    }


class TrialEligibilityRequest(BaseModel):
    """Request to check trial eligibility for an email address"""

    email: str


class TrialEligibilityResponse(BaseModel):
    """Response for trial eligibility check"""

    eligible: bool
    reason: str
    credits_usd: Optional[float] = None
    is_business_domain: bool


@app.post("/v1/billing/trial/check", tags=["Billing"])
async def check_trial_eligibility(
    request: TrialEligibilityRequest,
) -> TrialEligibilityResponse:
    """
    Check if an email address is eligible for trial credits.

    This is a public endpoint (no auth required) so users can check eligibility
    before registration.

    Trial eligibility requires:
    1. A business email domain (not gmail, outlook, etc.)
    2. The domain has not already been used for trial credits
    3. Trials are enabled in the pricing configuration
    """
    from TrialService import trial_service

    eligible, reason, credits_usd = trial_service.check_trial_eligibility(request.email)
    is_business = trial_service.is_business_domain(request.email)

    return TrialEligibilityResponse(
        eligible=eligible,
        reason=reason,
        credits_usd=credits_usd,
        is_business_domain=is_business,
    )


@app.get(
    "/v1/billing/trial/status",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def get_trial_status(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Get trial status for a company.

    Returns whether trial credits have been used and the amount granted.
    """
    from TrialService import trial_service

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    return trial_service.get_trial_status(company_id)


@app.get("/v1/billing/trial/config", tags=["Billing"])
async def get_trial_config():
    """
    Get trial configuration.

    This is a public endpoint showing trial settings from pricing configuration.
    """
    from TrialService import trial_service

    return trial_service.get_trial_config()


@app.post(
    "/v1/billing/tokens/topup/crypto",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def create_token_topup_crypto(
    request: TokenTopupCryptoRequest,
    authorization: str = Header(None),
):
    """Create crypto invoice for token top-up"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Get user companies
    user_companies = auth.get_user_companies()

    # Use provided company_id or default to primary company
    if request.company_id:
        company_id = request.company_id
        # Verify user has access to this company
        if company_id not in user_companies:
            raise HTTPException(
                status_code=403, detail="You do not have access to this company"
            )
    else:
        # Use primary company (first in the list)
        if not user_companies:
            raise HTTPException(
                status_code=400, detail="User is not associated with any company"
            )
        company_id = user_companies[0]

    # Get pricing quote
    price_service = PriceService()
    quote = await price_service.get_token_quote_for_currency(
        request.token_millions, request.currency
    )

    # If billing is disabled (price == 0), do not create crypto invoices
    if float(quote.get("amount_usd", 0)) <= 0:
        raise HTTPException(
            status_code=400,
            detail="Billing is disabled; token purchases are not available",
        )

    # Create crypto invoice
    crypto_service = CryptoPaymentService()
    try:
        invoice = await crypto_service.create_invoice(
            amount_usd=quote["amount_usd"],
            currency=request.currency,
            company_id=company_id,
            user_id=auth.user_id,
            token_amount=quote["tokens"],  # Pass actual token count
        )
        return invoice
    except Exception as e:
        logging.error(f"Error creating crypto invoice: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create crypto invoice: {str(e)}"
        )


@app.post(
    "/v1/billing/tokens/topup/stripe",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def create_token_topup_stripe(
    request: TokenTopupStripeRequest,
    authorization: str = Header(None),
):
    """Create Stripe payment intent for token top-up"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Get user companies
    user_companies = auth.get_user_companies()

    # Use provided company_id or default to primary company
    if request.company_id:
        company_id = request.company_id
        # Verify user has access to this company
        if company_id not in user_companies:
            raise HTTPException(
                status_code=403, detail="You do not have access to this company"
            )
    else:
        # Use primary company (first in the list)
        if not user_companies:
            raise HTTPException(
                status_code=400, detail="User is not associated with any company"
            )
        company_id = user_companies[0]

    # Get pricing quote
    price_service = PriceService()
    quote = await price_service.get_token_quote(request.token_millions)

    # If billing is disabled (price == 0), do not create Stripe payment intents
    if float(quote.get("amount_usd", 0)) <= 0:
        raise HTTPException(
            status_code=400,
            detail="Billing is disabled; token purchases are not available",
        )

    # Create Stripe payment intent
    stripe_service = StripePaymentService()
    try:
        payment_intent = await stripe_service.create_token_payment_intent(
            amount_usd=quote["amount_usd"],
            company_id=company_id,
            user_id=auth.user_id,
            token_amount=quote["tokens"],  # Pass actual token count
        )
        return payment_intent
    except Exception as e:
        logging.error(f"Error creating Stripe payment intent: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create payment intent: {str(e)}"
        )


@app.post(
    "/v1/billing/tokens/topup/stripe/confirm",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def confirm_stripe_payment(
    request: ConfirmPaymentRequest,
    authorization: str = Header(None),
):
    """Confirm and process a Stripe payment by checking payment intent status"""
    import stripe as stripe_lib
    from os import getenv

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Get user companies
    user_companies = auth.get_user_companies()

    # Use provided company_id or default to primary company
    if request.company_id:
        company_id = request.company_id
        # Verify user has access to this company
        if company_id not in user_companies:
            raise HTTPException(
                status_code=403, detail="You do not have access to this company"
            )
    else:
        # Use primary company (first in the list)
        if not user_companies:
            raise HTTPException(
                status_code=400, detail="User is not associated with any company"
            )
        company_id = user_companies[0]

    session = get_session()
    try:
        # Find the transaction
        transaction = (
            session.query(PaymentTransaction)
            .filter(
                PaymentTransaction.stripe_payment_intent_id == request.payment_intent_id
            )
            .first()
        )

        if not transaction:
            session.close()
            raise HTTPException(status_code=404, detail="Payment transaction not found")

        # Verify transaction belongs to user's company
        if transaction.company_id != company_id:
            session.close()
            raise HTTPException(
                status_code=403, detail="Transaction does not belong to your company"
            )

        # Check if already processed
        if transaction.status == "completed":
            tokens_credited = transaction.token_amount
            session.close()
            return {
                "success": True,
                "message": "Payment already processed",
                "tokens_credited": tokens_credited,
            }

        # Retrieve payment intent from Stripe
        stripe_lib.api_key = getenv("STRIPE_API_KEY")
        payment_intent = stripe_lib.PaymentIntent.retrieve(request.payment_intent_id)

        logging.info(
            f"Retrieved Stripe PaymentIntent {request.payment_intent_id}: status={getattr(payment_intent, 'status', None)} request_id={getattr(payment_intent, 'id', None)}"
        )

        # Check if payment succeeded
        if payment_intent.status == "succeeded":
            # Store values before session operations
            tokens_credited = transaction.token_amount
            transaction_company_id = transaction.company_id
            transaction_amount_usd = float(transaction.amount_usd)

            # Update transaction status
            transaction.status = "completed"

            # Credit tokens to company
            if tokens_credited and transaction_company_id:
                auth.add_tokens_to_company(
                    company_id=transaction_company_id,
                    token_amount=tokens_credited,
                    amount_usd=transaction_amount_usd,
                )
                logging.info(
                    f"Credited {tokens_credited} tokens to company {transaction_company_id} via payment intent {request.payment_intent_id}"
                )
                # Send Discord notification for token top-up
                await send_discord_topup_notification(
                    email=auth.email,
                    amount_usd=transaction_amount_usd,
                    tokens=tokens_credited,
                    company_id=transaction_company_id,
                )

            session.commit()
            session.close()
            return {
                "success": True,
                "message": "Payment confirmed and tokens credited",
                "tokens_credited": tokens_credited,
            }
        elif payment_intent.status == "processing":
            logging.info(f"PaymentIntent {request.payment_intent_id} still processing")
            session.close()
            return {
                "success": False,
                "message": "Payment is still processing. Please try again in a moment.",
            }
        elif payment_intent.status == "requires_payment_method":
            session.close()
            raise HTTPException(
                status_code=400, detail="Payment requires a valid payment method"
            )
        else:
            logging.warning(
                f"PaymentIntent {request.payment_intent_id} returned unexpected status: {getattr(payment_intent, 'status', None)}"
            )
            session.close()
            raise HTTPException(
                status_code=400,
                detail=f"Payment failed with status: {payment_intent.status}",
            )

    except stripe_lib.error.StripeError as e:
        session.rollback()
        session.close()
        logging.error(f"Stripe API error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        logging.error(f"Error confirming payment: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to confirm payment: {str(e)}"
        )


@app.post(
    "/v1/billing/stripe/confirm",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def confirm_stripe_payment_general(
    request: ConfirmPaymentRequest,
    authorization: str = Header(None),
):
    """Confirm and process any Stripe payment (seats or tokens) by checking payment intent status.
    This endpoint should be called by the frontend after Stripe confirms the payment to ensure
    the backend has processed the payment and updated subscription/token status.
    """
    import stripe as stripe_lib
    from os import getenv

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    session = get_session()
    try:
        # Find the transaction by payment intent ID
        transaction = (
            session.query(PaymentTransaction)
            .filter(
                PaymentTransaction.stripe_payment_intent_id == request.payment_intent_id
            )
            .first()
        )

        if not transaction:
            session.close()
            raise HTTPException(status_code=404, detail="Payment transaction not found")

        # Verify transaction belongs to the user
        if transaction.user_id != auth.user_id:
            session.close()
            raise HTTPException(
                status_code=403, detail="Transaction does not belong to you"
            )

        # Check if already processed
        if transaction.status == "completed":
            session.close()
            return {
                "success": True,
                "message": "Payment already processed",
                "seat_count": transaction.seat_count,
                "tokens_credited": transaction.token_amount,
            }

        # Retrieve payment intent from Stripe to verify status
        stripe_lib.api_key = getenv("STRIPE_API_KEY")
        payment_intent = stripe_lib.PaymentIntent.retrieve(request.payment_intent_id)

        logging.info(
            f"Retrieved Stripe PaymentIntent {request.payment_intent_id}: status={getattr(payment_intent, 'status', None)}"
        )

        # Check if payment succeeded
        if payment_intent.status == "succeeded":
            # Update transaction status
            transaction.status = "completed"

            # Handle token-based payment
            if transaction.token_amount and transaction.company_id:
                auth.add_tokens_to_company(
                    company_id=transaction.company_id,
                    token_amount=transaction.token_amount,
                    amount_usd=float(transaction.amount_usd),
                )
                logging.info(
                    f"Credited {transaction.token_amount} tokens to company {transaction.company_id} via payment confirmation"
                )

            # Handle seat-based payment
            elif transaction.seat_count and transaction.seat_count > 0:
                # Activate the user
                user_obj = (
                    session.query(User).filter(User.id == transaction.user_id).first()
                )
                if user_obj:
                    user_obj.is_active = True
                    logging.info(
                        f"Activated user {transaction.user_id} after Stripe payment confirmation"
                    )

                # Update company for seat-based subscription
                user_company = (
                    session.query(UserCompany)
                    .filter(UserCompany.user_id == transaction.user_id)
                    .first()
                )

                company_id_for_notification = None
                if user_company:
                    company = (
                        session.query(Company)
                        .filter(Company.id == user_company.company_id)
                        .first()
                    )
                    if company:
                        company.user_limit = transaction.seat_count
                        # Set stripe_payment_intent_id as a pseudo-subscription ID for seat validation
                        # This satisfies the _has_sufficient_token_balance check for seat-based billing
                        company.stripe_subscription_id = request.payment_intent_id
                        company.auto_topup_enabled = True
                        company_id_for_notification = str(company.id)
                        logging.info(
                            f"Updated company {company.id} user_limit to {transaction.seat_count} "
                            f"and enabled subscription for Stripe payment"
                        )
                    else:
                        logging.warning(
                            f"Company not found for user_company.company_id={user_company.company_id} "
                            f"during seat-based payment confirmation"
                        )
                else:
                    logging.warning(
                        f"UserCompany not found for user_id={transaction.user_id} "
                        f"during seat-based payment confirmation"
                    )

                # Send Discord notification for subscription (always attempt, even if company lookup failed)
                try:
                    from ExtensionsHub import ExtensionsHub

                    hub = ExtensionsHub()
                    pricing_config = hub.get_pricing_config()
                    pricing_model = (
                        pricing_config.get("pricing_model") if pricing_config else None
                    )
                except Exception:
                    pricing_model = None

                await send_discord_subscription_notification(
                    email=auth.email,
                    seat_count=transaction.seat_count,
                    amount_usd=float(transaction.amount_usd),
                    company_id=company_id_for_notification,
                    pricing_model=pricing_model,
                )

            session.commit()
            session.close()
            return {
                "success": True,
                "message": "Payment confirmed and processed",
                "seat_count": transaction.seat_count,
                "tokens_credited": transaction.token_amount,
            }
        elif payment_intent.status == "processing":
            logging.info(f"PaymentIntent {request.payment_intent_id} still processing")
            session.close()
            return {
                "success": False,
                "message": "Payment is still processing. Please try again in a moment.",
            }
        elif payment_intent.status == "requires_payment_method":
            session.close()
            raise HTTPException(
                status_code=400, detail="Payment requires a valid payment method"
            )
        else:
            logging.warning(
                f"PaymentIntent {request.payment_intent_id} returned unexpected status: {getattr(payment_intent, 'status', None)}"
            )
            session.close()
            raise HTTPException(
                status_code=400,
                detail=f"Payment failed with status: {payment_intent.status}",
            )

    except stripe_lib.error.StripeError as e:
        session.rollback()
        session.close()
        logging.error(f"Stripe API error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        logging.error(f"Error confirming payment: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to confirm payment: {str(e)}"
        )


@app.get(
    "/v1/billing/tokens/warning/dismiss",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def dismiss_warning(
    request: DismissWarningRequest,
    authorization: str = Header(None),
):
    """Admin dismisses low balance warning"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has admin access to this company
    user_companies = auth.get_user_companies()
    if request.company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    auth.dismiss_low_balance_warning(request.company_id)
    return {"detail": "Warning dismissed"}


@app.get(
    "/v1/billing/tokens/should_warn",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def should_show_warning(
    company_id: str,
    authorization: str = Header(None),
):
    """Check if low balance warning should be shown"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    should_warn = auth.should_show_low_balance_warning(company_id)
    return {"should_warn": should_warn}


@app.get(
    "/v1/billing/transactions",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def get_payment_transactions(
    status: Optional[str] = None,
    authorization: str = Header(None),
):
    """Get payment transaction history for user's companies"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    session = get_session()
    try:
        # Get all companies the user has access to
        user_companies = auth.get_user_companies()

        # Query transactions for these companies
        query = session.query(PaymentTransaction).filter(
            PaymentTransaction.company_id.in_(user_companies)
        )

        if status:
            query = query.filter(PaymentTransaction.status == status)

        transactions = query.order_by(desc(PaymentTransaction.created_at)).all()

        # Convert to dict for JSON serialization
        result = []
        for txn in transactions:
            result.append(
                {
                    "reference_code": txn.reference_code,
                    "status": txn.status,
                    "currency": txn.currency,
                    "amount_usd": txn.amount_usd,
                    "amount_currency": txn.amount_currency,
                    "exchange_rate": txn.exchange_rate,
                    "transaction_hash": txn.transaction_hash,
                    "wallet_address": txn.wallet_address,
                    "memo": txn.memo,
                    "seat_count": txn.seat_count or 0,
                    "token_amount": txn.token_amount,
                    "app_name": txn.app_name,
                    "metadata": {},
                    "created_at": (
                        txn.created_at.isoformat() if txn.created_at else None
                    ),
                    "updated_at": (
                        txn.updated_at.isoformat() if txn.updated_at else None
                    ),
                    "expires_at": (
                        txn.expires_at.isoformat() if txn.expires_at else None
                    ),
                }
            )

        return result
    finally:
        session.close()


@app.get(
    "/v1/billing/subscription",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def get_subscription_info(
    authorization: str = Header(None),
):
    """Get subscription information - currently returns empty as we use token-based billing"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # For now, return empty subscription info since we're using token-based billing
    # This endpoint exists to prevent frontend errors
    return {
        "monthly_price_usd": 0.0,
        "next_billing_date": None,
        "subscription_status": "inactive",
        "upcoming_cycles": [],
    }


@app.get(
    "/v1/billing/usage",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def get_company_usage(
    company_id: str,
    limit: int = 100,
    authorization: str = Header(None),
):
    """Get company-level token usage breakdown by user"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    session = get_session()
    try:
        # Get recent usage records
        usage_records = (
            session.query(CompanyTokenUsage)
            .filter(CompanyTokenUsage.company_id == company_id)
            .order_by(desc(CompanyTokenUsage.timestamp))
            .limit(limit)
            .all()
        )

        # Convert to dict for JSON serialization
        result = []
        for record in usage_records:
            # Get user email for display
            user = session.query(User).filter(User.id == record.user_id).first()
            result.append(
                {
                    "user_id": record.user_id,
                    "user_email": user.email if user else "Unknown",
                    "input_tokens": record.input_tokens,
                    "output_tokens": record.output_tokens,
                    "total_tokens": record.total_tokens,
                    "timestamp": (
                        record.timestamp.isoformat() if record.timestamp else None
                    ),
                }
            )

        return result
    finally:
        session.close()


@app.get(
    "/v1/billing/usage/totals",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def get_company_usage_totals(
    company_id: str,
    authorization: str = Header(None),
):
    """Get cumulative token usage totals for all users in the company"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    session = get_session()
    try:
        # Get all users in the company
        user_companies_records = (
            session.query(UserCompany)
            .filter(UserCompany.company_id == company_id)
            .all()
        )

        if not user_companies_records:
            return []

        # Batch load all users
        user_ids = [uc.user_id for uc in user_companies_records]
        users = session.query(User).filter(User.id.in_(user_ids)).all()
        users_map = {u.id: u for u in users}

        # Batch load all relevant preferences (input_tokens and output_tokens)
        prefs = (
            session.query(UserPreferences)
            .filter(
                UserPreferences.user_id.in_(user_ids),
                UserPreferences.pref_key.in_(["input_tokens", "output_tokens"]),
            )
            .all()
        )

        # Build lookup: user_id -> {pref_key: pref_value}
        prefs_map = {}
        for pref in prefs:
            if pref.user_id not in prefs_map:
                prefs_map[pref.user_id] = {}
            prefs_map[pref.user_id][pref.pref_key] = pref.pref_value

        result = []
        for uc in user_companies_records:
            user = users_map.get(uc.user_id)
            if not user:
                continue

            user_prefs = prefs_map.get(uc.user_id, {})
            input_tokens = int(user_prefs.get("input_tokens", 0) or 0)
            output_tokens = int(user_prefs.get("output_tokens", 0) or 0)

            result.append(
                {
                    "user_id": str(uc.user_id),
                    "user_email": user.email,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            )

        # Sort by total tokens descending
        result.sort(key=lambda x: x["total_tokens"], reverse=True)

        return result
    finally:
        session.close()


@app.get(
    "/v1/billing/config",
    tags=["Billing"],
)
async def get_billing_config():
    """Get billing configuration - public endpoint to check if billing is enabled"""
    price_service = PriceService()
    token_price = price_service.get_token_price()

    return {
        "billing_enabled": token_price > 0,
        "token_price_usd": token_price,
    }


# ============================================================================
# Auto Top-Up Subscription Endpoints
# ============================================================================


@app.get(
    "/v1/billing/auto-topup",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Get auto top-up subscription status",
)
async def get_auto_topup_status(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Get the current auto top-up subscription status for a company.

    Returns subscription status, amount, and next billing date if active.
    """
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    stripe_service = StripePaymentService()
    return await stripe_service.get_auto_topup_status(company_id=company_id)


@app.post(
    "/v1/billing/auto-topup",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Set up monthly auto top-up subscription",
)
async def setup_auto_topup(
    request: AutoTopupSetupRequest,
    authorization: str = Header(None),
):
    """
    Set up a monthly auto top-up subscription for a company.

    This creates a Stripe Checkout session for setting up recurring monthly payments.
    The subscription will automatically credit tokens to the company each month.

    **Recommendations:**
    - Plan for approximately $20 per active user per month
    - Power users may exceed this, so monitor usage and adjust as needed
    - Tokens don't expire and can be topped up anytime
    - Tokens are non-refundable as they prepay for compute resources

    **Minimum:** $5/month
    """
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if request.company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    # Get user email for Stripe customer creation
    session = get_session()
    try:
        user = session.query(User).filter(User.id == auth.user_id).first()
        user_email = user.email if user else None
    finally:
        session.close()

    stripe_service = StripePaymentService()
    try:
        result = await stripe_service.create_auto_topup_subscription(
            company_id=request.company_id,
            amount_usd=request.amount_usd,
            user_email=user_email,
        )
        return result
    except Exception as e:
        logging.error(f"Error creating auto top-up subscription: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create subscription: {str(e)}"
        )


@app.put(
    "/v1/billing/auto-topup",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Update auto top-up amount",
)
async def update_auto_topup(
    request: AutoTopupUpdateRequest,
    authorization: str = Header(None),
):
    """
    Update the monthly auto top-up amount or seat count.

    For seat-based pricing (per_user, per_capacity, per_location):
    - Updates the subscription quantity directly in Stripe
    - Prorates charges automatically
    - No checkout needed

    For token-based pricing:
    - Cancels the existing subscription and creates a new checkout session
    - User needs to complete checkout again
    """
    from Globals import getenv

    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if request.company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    stripe_service = StripePaymentService()

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

    try:
        if is_seat_based:
            # For seat-based billing, update quantity directly
            price_per_unit = 75.0
            if pricing_config and pricing_config.get("tiers"):
                price_per_unit = float(
                    pricing_config["tiers"][0].get("price_per_unit", 75)
                )
            new_quantity = max(1, round(request.amount_usd / price_per_unit))

            result = await stripe_service.update_subscription_quantity(
                company_id=request.company_id,
                new_quantity=new_quantity,
            )
            return result
        else:
            # For token-based billing, cancel and recreate (requires checkout)
            result = await stripe_service.update_auto_topup_amount(
                company_id=request.company_id,
                new_amount_usd=request.amount_usd,
            )
            return result
    except Exception as e:
        logging.error(f"Error updating auto top-up: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update subscription: {str(e)}"
        )


@app.delete(
    "/v1/billing/auto-topup",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Cancel auto top-up subscription",
)
async def cancel_auto_topup(
    request: AutoTopupCancelRequest,
    authorization: str = Header(None),
):
    """
    Cancel the monthly auto top-up subscription.

    The subscription will be cancelled immediately. No further charges will be made.
    Existing token balance remains available and does not expire.
    """
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if request.company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    stripe_service = StripePaymentService()
    try:
        result = await stripe_service.cancel_auto_topup_subscription(
            company_id=request.company_id,
        )
        return result
    except Exception as e:
        logging.error(f"Error cancelling auto top-up: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel subscription: {str(e)}"
        )


@app.post(
    "/v1/credit",
    tags=["Billing"],
    summary="Issue credits to a company",
    description="Admin-only endpoint to manually issue credits to a company as if they purchased them. Requires AGiXT API Key.",
)
async def issue_company_credits(
    company: str,
    amount: str,
    authorization: str = Header(None),
):
    """
    Issue credits to a company manually (admin only - requires AGiXT API Key).

    This endpoint allows administrators to issue credits to a company as if they purchased them
    through Stripe or crypto payment. The credits are added to the company's token balance.

    Args:
        company: The company ID to credit
        amount: The amount in USD to credit (as string to avoid float precision issues)
        authorization: AGiXT API Key (required)

    Returns:
        Success message with credited amount and token count

    Raises:
        HTTPException: If unauthorized, company not found, or invalid amount
    """
    from decimal import Decimal

    # Verify AGiXT API Key
    agixt_api_key = os.getenv("AGIXT_API_KEY", "")
    provided_key = str(authorization).replace("Bearer ", "").replace("bearer ", "")

    if not agixt_api_key or provided_key != agixt_api_key:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. This endpoint requires the AGiXT API Key.",
        )

    # Convert and validate amount
    try:
        amount_decimal = Decimal(str(amount))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount format")

    if amount_decimal <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    # Get company
    session = get_session()
    try:
        from DB import Company

        company_record = session.query(Company).filter(Company.id == company).first()
        if not company_record:
            raise HTTPException(status_code=404, detail=f"Company {company} not found")

        # Calculate tokens based on current pricing
        price_service = PriceService()
        token_price = price_service.get_token_price()

        if token_price <= 0:
            # If billing is disabled, still allow manual crediting
            # Default to $0.50 per million tokens for calculation
            token_price = Decimal("0.50")
        else:
            token_price = Decimal(str(token_price))

        # Calculate how many tokens this amount buys
        token_millions = amount_decimal / token_price
        tokens = int(token_millions * 1_000_000)

        # Add tokens to company balance
        company_record.token_balance = (company_record.token_balance or 0) + tokens
        company_record.token_balance_usd = (
            company_record.token_balance_usd or 0
        ) + float(amount_decimal)

        # Create a payment transaction record for audit trail
        transaction = PaymentTransaction(
            user_id=None,  # Admin credit, no specific user
            company_id=company,
            seat_count=0,  # Not seat-based, it's token-based
            token_amount=tokens,
            payment_method="manual_credit",
            currency="USD",
            network=None,
            amount_usd=float(amount_decimal),
            amount_currency=float(amount_decimal),  # Same as USD for manual credits
            exchange_rate=1.0,  # 1:1 for USD
            status="completed",
            reference_code=f"ADMIN_CREDIT_{company}_{int(datetime.now().timestamp())}",
        )
        session.add(transaction)

        session.commit()

        return {
            "success": True,
            "company_id": company,
            "amount_usd": float(amount_decimal),
            "tokens_credited": tokens,
            "token_millions": float(token_millions),
            "new_balance_tokens": company_record.token_balance,
            "new_balance_usd": company_record.token_balance_usd,
            "transaction_id": transaction.id,
            "reference_code": transaction.reference_code,
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error issuing credits to company {company}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to issue credits: {str(e)}"
        )
    finally:
        session.close()


# Admin endpoints (role 0 only)


class AdminCompanySearchResponse(BaseModel):
    """Response model for admin company search"""

    companies: List[dict]
    total: int
    limit: int
    offset: int


class AdminCreditRequest(BaseModel):
    """Request model for admin credit issuance"""

    company_id: str
    amount_usd: float


@app.get(
    "/v1/admin/companies",
    tags=["Admin"],
    summary="Get all companies (super admin only)",
    description="Super admin endpoint to retrieve all companies on the server with search, filter, and sort capability.",
    response_model=AdminCompanySearchResponse,
)
async def admin_get_all_companies(
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    sort_by: Optional[str] = None,
    sort_direction: Optional[str] = "asc",
    filter_balance: Optional[str] = None,
    filter_users: Optional[str] = None,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Get all companies on the server (super admin only).

    Args:
        search: Optional search string (company name, ID, or user email)
        limit: Maximum number of results (default 100)
        offset: Number of results to skip for pagination
        sort_by: Field to sort by (name, token_balance, token_balance_usd, user_count)
        sort_direction: Sort direction (asc or desc)
        filter_balance: Filter by balance (no_balance, has_balance)
        filter_users: Filter by user count (single_user, multiple_users)
        authorization: JWT token (required)

    Returns:
        List of companies with pagination info
    """
    auth = MagicalAuth(token=authorization)
    return auth.get_all_server_companies(
        search=search,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_direction=sort_direction,
        filter_balance=filter_balance,
        filter_users=filter_users,
    )


@app.post(
    "/v1/admin/credit",
    tags=["Admin"],
    summary="Issue credits to any company (super admin only)",
    description="Super admin endpoint to manually issue credits to any company.",
)
async def admin_issue_credits(
    request: AdminCreditRequest,
    email: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Issue credits to any company (super admin only).

    Args:
        request: Contains company_id and amount_usd
        authorization: JWT token (required)

    Returns:
        Success message with credited amount and token count
    """
    from decimal import Decimal

    auth = MagicalAuth(token=authorization)

    # Verify super admin access
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin role required.",
        )

    # Validate amount
    try:
        amount_decimal = Decimal(str(request.amount_usd))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount format")

    if amount_decimal <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    # Get company
    session = get_session()
    try:
        company_record = (
            session.query(Company).filter(Company.id == request.company_id).first()
        )
        if not company_record:
            raise HTTPException(
                status_code=404, detail=f"Company {request.company_id} not found"
            )

        # Calculate tokens based on current pricing
        price_service = PriceService()
        token_price = price_service.get_token_price()

        if token_price <= 0:
            # If billing is disabled, default to $0.50 per million tokens
            token_price = Decimal("0.50")
        else:
            token_price = Decimal(str(token_price))

        # Calculate how many tokens this amount buys
        token_millions = amount_decimal / token_price
        tokens = int(token_millions * 1_000_000)

        # Add tokens to company balance
        company_record.token_balance = (company_record.token_balance or 0) + tokens
        company_record.token_balance_usd = (
            company_record.token_balance_usd or 0
        ) + float(amount_decimal)

        # Create a payment transaction record for audit trail
        transaction = PaymentTransaction(
            user_id=auth.user_id,  # Track which admin issued the credit
            company_id=request.company_id,
            seat_count=0,
            token_amount=tokens,
            payment_method="admin_credit",
            currency="USD",
            network=None,
            amount_usd=float(amount_decimal),
            amount_currency=float(amount_decimal),
            exchange_rate=1.0,
            status="completed",
            reference_code=f"ADMIN_CREDIT_{request.company_id}_{int(datetime.now().timestamp())}",
        )
        session.add(transaction)
        session.commit()

        return {
            "success": True,
            "company_id": request.company_id,
            "company_name": company_record.name,
            "amount_usd": float(amount_decimal),
            "tokens_credited": tokens,
            "token_millions": float(token_millions),
            "new_balance_tokens": company_record.token_balance,
            "new_balance_usd": company_record.token_balance_usd,
            "transaction_id": str(transaction.id),
            "reference_code": transaction.reference_code,
            "issued_by": auth.email,
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error issuing admin credits: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to issue credits: {str(e)}"
        )
    finally:
        session.close()


@app.post(
    "/v1/admin/set-super-admin",
    tags=["Admin"],
    summary="Set a user as super admin (AGiXT API Key or existing super admin required)",
    description="Promotes a user to super admin (role 0) in their primary company. Requires AGiXT API Key or existing super admin permissions.",
)
async def set_super_admin(
    email: str,
    authorization: str = Header(None),
):
    """
    Set a user as super admin (role 0).

    This endpoint can be called with either:
    1. The AGiXT API Key for initial setup
    2. A JWT from an existing super admin

    Args:
        email: The email of the user to promote to super admin
        authorization: AGiXT API Key or super admin JWT

    Returns:
        Success message with user details
    """
    agixt_api_key = os.getenv("AGIXT_API_KEY", "")
    provided_key = str(authorization).replace("Bearer ", "").replace("bearer ", "")

    is_api_key_auth = agixt_api_key and provided_key == agixt_api_key
    is_super_admin_auth = False
    # Check if it's a JWT from a super admin
    if not is_api_key_auth:
        try:
            auth = MagicalAuth(token=authorization)
            is_super_admin_auth = auth.is_super_admin()
        except Exception as e:
            log_silenced_exception(e, "delete_user: checking super admin auth")

    if not is_api_key_auth and not is_super_admin_auth:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. This endpoint requires the AGiXT API Key or super admin permissions.",
        )

    session = get_session()
    try:
        # Find the user by email
        user = session.query(User).filter(User.email == email.lower()).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {email} not found")

        # Get the user's primary company
        user_company = (
            session.query(UserCompany).filter(UserCompany.user_id == user.id).first()
        )

        if not user_company:
            raise HTTPException(
                status_code=404,
                detail=f"User {email} is not a member of any company",
            )

        # Set role to 0 (super_admin)
        old_role = user_company.role_id
        user_company.role_id = 0
        session.commit()

        # Invalidate user scopes cache since their role changed
        invalidate_user_scopes_cache(
            user_id=str(user.id), company_id=str(user_company.company_id)
        )

        return {
            "success": True,
            "user_id": str(user.id),
            "email": user.email,
            "company_id": str(user_company.company_id),
            "old_role_id": old_role,
            "new_role_id": 0,
            "message": f"User {email} has been promoted to super admin (role 0)",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error setting super admin: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to set super admin: {str(e)}"
        )
    finally:
        session.close()


# Protected company names that cannot be deleted
PROTECTED_COMPANIES = ["DevXT", "Josh's Team"]


@app.delete(
    "/v1/admin/companies/{company_id}",
    tags=["Admin"],
    summary="Delete a company (super admin only)",
    description="Permanently deletes a company and removes all user associations. Requires super admin permissions. Protected companies cannot be deleted.",
)
async def admin_delete_company(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Delete a company (super admin only).

    This endpoint permanently removes a company and all associated user memberships.
    Protected companies (DevXT, Josh's Team) cannot be deleted.

    Args:
        company_id: The UUID of the company to delete
        authorization: Super admin JWT

    Returns:
        Success message with company details
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Check if company is protected
        if company.name in PROTECTED_COMPANIES:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot delete protected company: {company.name}",
            )

        company_name = company.name

        # Get count of users that will be affected
        user_count = (
            session.query(UserCompany)
            .filter(UserCompany.company_id == company_id)
            .count()
        )

        # Delete all user associations
        session.query(UserCompany).filter(UserCompany.company_id == company_id).delete()

        # Delete the company
        session.delete(company)
        session.commit()

        return {
            "success": True,
            "company_id": company_id,
            "company_name": company_name,
            "users_removed": user_count,
            "message": f"Company '{company_name}' has been deleted",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error deleting company: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete company: {str(e)}"
        )
    finally:
        session.close()


@app.delete(
    "/v1/admin/users/{user_id}",
    tags=["Admin"],
    summary="Deactivate a user (super admin only)",
    description="Deactivates a user account. Requires super admin permissions. Protected users cannot be deactivated.",
)
async def admin_delete_user(
    user_id: str,
    authorization: str = Header(None),
):
    """
    Deactivate a user (super admin only).

    This endpoint deactivates a user account (sets is_active to False).
    Protected users (josh@devxt.com) cannot be deactivated.

    Args:
        user_id: The UUID of the user to deactivate
        authorization: Super admin JWT

    Returns:
        Success message with user details
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if user is protected
        protected_emails = ["josh@devxt.com"]
        if user.email.lower() in protected_emails:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot deactivate protected user: {user.email}",
            )

        user_email = user.email
        user.is_active = False
        session.commit()

        return {
            "success": True,
            "user_id": user_id,
            "email": user_email,
            "message": f"User '{user_email}' has been deactivated",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error deactivating user: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to deactivate user: {str(e)}"
        )
    finally:
        session.close()


@app.delete(
    "/v1/admin/companies/{company_id}/users/{user_id}",
    tags=["Admin"],
    summary="Remove a user from a company (super admin only)",
    description="Removes a user from a specific company. Requires super admin permissions.",
)
async def admin_remove_user_from_company(
    company_id: str,
    user_id: str,
    authorization: str = Header(None),
):
    """
    Remove a user from a company (super admin only).

    This endpoint removes a user's association with a specific company.
    The user account remains active but is no longer a member of that company.

    Args:
        company_id: The UUID of the company
        user_id: The UUID of the user to remove
        authorization: Super admin JWT

    Returns:
        Success message with details
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        # Verify company exists
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Verify user exists
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Find the user-company association
        user_company = (
            session.query(UserCompany)
            .filter(
                UserCompany.user_id == user_id, UserCompany.company_id == company_id
            )
            .first()
        )
        if not user_company:
            raise HTTPException(
                status_code=404,
                detail=f"User '{user.email}' is not a member of company '{company.name}'",
            )

        session.delete(user_company)
        session.commit()

        return {
            "success": True,
            "company_id": company_id,
            "company_name": company.name,
            "user_id": user_id,
            "user_email": user.email,
            "message": f"User '{user.email}' has been removed from company '{company.name}'",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error removing user from company: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to remove user from company: {str(e)}"
        )
    finally:
        session.close()


@app.post(
    "/v1/admin/companies/{company_id}/users",
    tags=["Admin"],
    summary="Assign a user to a company (super admin only)",
    description="Adds a user to a company with a specified role. Requires super admin permissions.",
)
async def admin_assign_user_to_company(
    company_id: str,
    user_email: str = Query(..., description="Email address of the user to assign"),
    role_id: int = Query(
        3,
        description="Role ID for the user (0=Super Admin, 1=Admin, 2=Manager, 3=User)",
    ),
    authorization: str = Header(None),
):
    """
    Assign a user to a company (super admin only).

    This endpoint adds a user to a company with the specified role.
    If the user is already in the company, their role will be updated.

    Args:
        company_id: The UUID of the company
        user_email: Email address of the user to assign
        role_id: Role ID (0=Super Admin, 1=Admin, 2=Manager, 3=User), defaults to 3
        authorization: Super admin JWT

    Returns:
        Success message with details
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        # Verify company exists
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Find user by email
        user = session.query(User).filter(User.email == user_email.lower()).first()
        if not user:
            raise HTTPException(
                status_code=404, detail=f"User with email '{user_email}' not found"
            )

        # Validate role_id
        if role_id < 0 or role_id > 3:
            raise HTTPException(
                status_code=400,
                detail="Invalid role_id. Must be 0 (Super Admin), 1 (Admin), 2 (Manager), or 3 (User)",
            )

        role_names = {0: "Super Admin", 1: "Admin", 2: "Manager", 3: "User"}

        # Check if user is already in the company
        existing = (
            session.query(UserCompany)
            .filter(
                UserCompany.user_id == user.id, UserCompany.company_id == company_id
            )
            .first()
        )

        if existing:
            # Update the role
            old_role = existing.role_id
            existing.role_id = role_id
            session.commit()
            return {
                "success": True,
                "company_id": company_id,
                "company_name": company.name,
                "user_id": str(user.id),
                "user_email": user.email,
                "role_id": role_id,
                "role_name": role_names[role_id],
                "updated": True,
                "message": f"User '{user.email}' role updated from {role_names.get(old_role, 'Unknown')} to {role_names[role_id]} in company '{company.name}'",
            }

        # Create new user-company association
        user_company = UserCompany(
            user_id=user.id,
            company_id=company_id,
            role_id=role_id,
        )
        session.add(user_company)
        session.commit()

        return {
            "success": True,
            "company_id": company_id,
            "company_name": company.name,
            "user_id": str(user.id),
            "user_email": user.email,
            "role_id": role_id,
            "role_name": role_names[role_id],
            "updated": False,
            "message": f"User '{user.email}' has been assigned to company '{company.name}' as {role_names[role_id]}",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error assigning user to company: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to assign user to company: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Server Statistics
# ============================================


@app.get(
    "/v1/admin/stats",
    tags=["Admin"],
    summary="Get server-wide statistics (super admin only)",
    description="Returns aggregate statistics about all companies and users on the server.",
)
async def admin_get_server_stats(
    authorization: str = Header(None),
):
    """
    Get server-wide statistics for super admin dashboard.

    Returns:
        - Total companies
        - Total users
        - Total token balance (sum across all companies)
        - Companies with no balance
        - Companies with single user
        - Active companies (with balance > 0)
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        from sqlalchemy import func

        # Total companies
        total_companies = session.query(func.count(Company.id)).scalar() or 0

        # Total users
        total_users = session.query(func.count(User.id)).scalar() or 0

        # Total token balance
        total_tokens = session.query(func.sum(Company.token_balance)).scalar() or 0
        total_usd = session.query(func.sum(Company.token_balance_usd)).scalar() or 0

        # Companies with no balance
        no_balance_count = (
            session.query(func.count(Company.id))
            .filter(
                (Company.token_balance == None)
                | (Company.token_balance == 0)
                | (Company.token_balance_usd == None)
                | (Company.token_balance_usd == 0)
            )
            .scalar()
            or 0
        )

        # Companies with balance
        with_balance_count = total_companies - no_balance_count

        # Companies with single user
        user_counts = (
            session.query(
                UserCompany.company_id, func.count(UserCompany.user_id).label("cnt")
            )
            .group_by(UserCompany.company_id)
            .subquery()
        )
        single_user_companies = (
            session.query(func.count())
            .select_from(user_counts)
            .filter(user_counts.c.cnt == 1)
            .scalar()
            or 0
        )

        # Companies with multiple users
        multi_user_companies = (
            session.query(func.count())
            .select_from(user_counts)
            .filter(user_counts.c.cnt > 1)
            .scalar()
            or 0
        )

        # Suspended companies
        suspended_count = (
            session.query(func.count(Company.id))
            .filter(Company.status == False)
            .scalar()
            or 0
        )

        return {
            "total_companies": total_companies,
            "total_users": total_users,
            "total_token_balance": total_tokens,
            "total_usd_balance": float(total_usd) if total_usd else 0.0,
            "companies_with_balance": with_balance_count,
            "companies_no_balance": no_balance_count,
            "single_user_companies": single_user_companies,
            "multi_user_companies": multi_user_companies,
            "suspended_companies": suspended_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting server stats: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get server stats: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Create Company
# ============================================


@app.post(
    "/v1/admin/companies",
    tags=["Admin"],
    summary="Create a new company (super admin only)",
    description="Creates a new company on the server.",
)
async def admin_create_company(
    name: str = Query(..., description="Company name"),
    email: str = Query(None, description="Company contact email"),
    phone_number: str = Query(None, description="Company phone number"),
    website: str = Query(None, description="Company website"),
    address: str = Query(None, description="Company address"),
    city: str = Query(None, description="City"),
    state: str = Query(None, description="State/Province"),
    zip_code: str = Query(None, description="ZIP/Postal code"),
    country: str = Query(None, description="Country"),
    notes: str = Query(None, description="Admin notes"),
    authorization: str = Header(None),
):
    """
    Create a new company (super admin only).
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        # Check if company name already exists
        existing = session.query(Company).filter(Company.name == name).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Company with name '{name}' already exists",
            )

        # Create new company
        new_company = Company(
            name=name,
            email=email,
            phone_number=phone_number,
            website=website,
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            country=country,
            notes=notes,
            status=True,
            token_balance=0,
            token_balance_usd=0,
        )
        session.add(new_company)
        session.commit()

        return {
            "success": True,
            "company_id": str(new_company.id),
            "name": new_company.name,
            "message": f"Company '{name}' created successfully",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error creating company: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create company: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Edit Company
# ============================================


@app.patch(
    "/v1/admin/companies/{company_id}",
    tags=["Admin"],
    summary="Update company details (super admin only)",
    description="Updates company information including name, contact details, and admin notes.",
)
async def admin_update_company(
    company_id: str,
    name: str = Query(None, description="Company name"),
    email: str = Query(None, description="Company contact email"),
    phone_number: str = Query(None, description="Company phone number"),
    website: str = Query(None, description="Company website"),
    address: str = Query(None, description="Company address"),
    city: str = Query(None, description="City"),
    state: str = Query(None, description="State/Province"),
    zip_code: str = Query(None, description="ZIP/Postal code"),
    country: str = Query(None, description="Country"),
    notes: str = Query(None, description="Admin notes"),
    authorization: str = Header(None),
):
    """
    Update company details (super admin only).
    Only provided fields will be updated.
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Update only provided fields
        updated_fields = []
        if name is not None:
            # Check name uniqueness if changing
            if name != company.name:
                existing = session.query(Company).filter(Company.name == name).first()
                if existing:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Company with name '{name}' already exists",
                    )
            company.name = name
            updated_fields.append("name")
        if email is not None:
            company.email = email
            updated_fields.append("email")
        if phone_number is not None:
            company.phone_number = phone_number
            updated_fields.append("phone_number")
        if website is not None:
            company.website = website
            updated_fields.append("website")
        if address is not None:
            company.address = address
            updated_fields.append("address")
        if city is not None:
            company.city = city
            updated_fields.append("city")
        if state is not None:
            company.state = state
            updated_fields.append("state")
        if zip_code is not None:
            company.zip_code = zip_code
            updated_fields.append("zip_code")
        if country is not None:
            company.country = country
            updated_fields.append("country")
        if notes is not None:
            company.notes = notes
            updated_fields.append("notes")

        session.commit()

        return {
            "success": True,
            "company_id": str(company.id),
            "name": company.name,
            "updated_fields": updated_fields,
            "message": f"Company '{company.name}' updated successfully",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error updating company: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update company: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Change User Role
# ============================================


@app.patch(
    "/v1/admin/companies/{company_id}/users/{user_id}/role",
    tags=["Admin"],
    summary="Change a user's role in a company (super admin only)",
    description="Updates a user's role within a specific company.",
)
async def admin_change_user_role(
    company_id: str,
    user_id: str,
    role_id: int = Query(
        ..., description="New role ID (0=Super Admin, 1=Admin, 2=Manager, 3=User)"
    ),
    authorization: str = Header(None),
):
    """
    Change a user's role in a company (super admin only).
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    if role_id < 0 or role_id > 3:
        raise HTTPException(
            status_code=400,
            detail="Invalid role_id. Must be 0 (Super Admin), 1 (Admin), 2 (Manager), or 3 (User)",
        )

    session = get_session()
    try:
        # Verify company exists
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Verify user exists
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Find user-company relationship
        user_company = (
            session.query(UserCompany)
            .filter(
                UserCompany.user_id == user_id, UserCompany.company_id == company_id
            )
            .first()
        )
        if not user_company:
            raise HTTPException(
                status_code=404,
                detail=f"User is not a member of company '{company.name}'",
            )

        role_names = {0: "Super Admin", 1: "Admin", 2: "Manager", 3: "User"}
        old_role_id = user_company.role_id
        old_role_name = role_names.get(old_role_id, "Unknown")

        user_company.role_id = role_id
        session.commit()

        # Invalidate user scopes cache since their role changed
        invalidate_user_scopes_cache(user_id=user_id, company_id=company_id)

        return {
            "success": True,
            "company_id": company_id,
            "company_name": company.name,
            "user_id": user_id,
            "user_email": user.email,
            "old_role_id": old_role_id,
            "old_role_name": old_role_name,
            "new_role_id": role_id,
            "new_role_name": role_names[role_id],
            "message": f"User '{user.email}' role changed from {old_role_name} to {role_names[role_id]} in company '{company.name}'",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error changing user role: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to change user role: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Impersonate User
# ============================================


@app.post(
    "/v1/admin/impersonate",
    tags=["Admin"],
    summary="Get a login token for any user (super admin only)",
    description="Generates a JWT token to log in as any user for support purposes.",
)
async def admin_impersonate_user(
    user_email: str = Query(..., description="Email of the user to impersonate"),
    authorization: str = Header(None),
):
    """
    Generate a login JWT for any user (super admin only).
    Used for support and debugging purposes.
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        from MagicalAuth import impersonate_user

        # Verify user exists
        user = session.query(User).filter(User.email == user_email.lower()).first()
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with email '{user_email}' not found",
            )

        # Generate token
        token = impersonate_user(user_email.lower())

        # Get user's companies
        user_companies = (
            session.query(UserCompany, Company)
            .join(Company)
            .filter(UserCompany.user_id == user.id)
            .all()
        )
        companies = [
            {"id": str(c.id), "name": c.name, "role_id": uc.role_id}
            for uc, c in user_companies
        ]

        return {
            "success": True,
            "user_id": str(user.id),
            "user_email": user.email,
            "user_name": f"{user.first_name or ''} {user.last_name or ''}".strip()
            or user.email,
            "jwt": token,
            "companies": companies,
            "message": f"Generated login token for user '{user.email}'",
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error impersonating user: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate impersonation token: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Export Data
# ============================================


@app.get(
    "/v1/admin/export/companies",
    tags=["Admin"],
    summary="Export all companies data (super admin only)",
    description="Returns all companies with their users in a format suitable for CSV export.",
)
async def admin_export_companies(
    authorization: str = Header(None),
):
    """
    Export all companies and users for reporting.
    Returns data in a flat structure suitable for CSV.
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        from sqlalchemy.orm import joinedload

        companies = (
            session.query(Company)
            .options(
                joinedload(Company.users).joinedload(UserCompany.user),
                joinedload(Company.users).joinedload(UserCompany.role),
            )
            .all()
        )

        rows = []
        role_names = {0: "Super Admin", 1: "Admin", 2: "Manager", 3: "User"}

        for company in companies:
            if not company.users:
                # Company with no users
                rows.append(
                    {
                        "company_id": str(company.id),
                        "company_name": company.name,
                        "company_email": company.email or "",
                        "company_phone": company.phone_number or "",
                        "company_website": company.website or "",
                        "company_address": company.address or "",
                        "company_city": company.city or "",
                        "company_state": company.state or "",
                        "company_zip": company.zip_code or "",
                        "company_country": company.country or "",
                        "company_notes": company.notes or "",
                        "company_status": (
                            "Active"
                            if getattr(company, "status", True)
                            else "Suspended"
                        ),
                        "token_balance": getattr(company, "token_balance", 0) or 0,
                        "token_balance_usd": getattr(company, "token_balance_usd", 0)
                        or 0,
                        "user_id": "",
                        "user_email": "",
                        "user_first_name": "",
                        "user_last_name": "",
                        "user_role": "",
                    }
                )
            else:
                for uc in company.users:
                    user = uc.user
                    rows.append(
                        {
                            "company_id": str(company.id),
                            "company_name": company.name,
                            "company_email": company.email or "",
                            "company_phone": company.phone_number or "",
                            "company_website": company.website or "",
                            "company_address": company.address or "",
                            "company_city": company.city or "",
                            "company_state": company.state or "",
                            "company_zip": company.zip_code or "",
                            "company_country": company.country or "",
                            "company_notes": company.notes or "",
                            "company_status": (
                                "Active"
                                if getattr(company, "status", True)
                                else "Suspended"
                            ),
                            "token_balance": getattr(company, "token_balance", 0) or 0,
                            "token_balance_usd": getattr(
                                company, "token_balance_usd", 0
                            )
                            or 0,
                            "user_id": str(user.id),
                            "user_email": user.email,
                            "user_first_name": user.first_name or "",
                            "user_last_name": user.last_name or "",
                            "user_role": role_names.get(uc.role_id, "User"),
                        }
                    )

        return {
            "columns": [
                "company_id",
                "company_name",
                "company_email",
                "company_phone",
                "company_website",
                "company_address",
                "company_city",
                "company_state",
                "company_zip",
                "company_country",
                "company_notes",
                "company_status",
                "token_balance",
                "token_balance_usd",
                "user_id",
                "user_email",
                "user_first_name",
                "user_last_name",
                "user_role",
            ],
            "rows": rows,
            "total_rows": len(rows),
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error exporting companies: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to export companies: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Suspend/Unsuspend Company
# ============================================


@app.post(
    "/v1/admin/companies/{company_id}/suspend",
    tags=["Admin"],
    summary="Suspend a company (super admin only)",
    description="Temporarily disables access to a company without deleting it.",
)
async def admin_suspend_company(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Suspend a company (super admin only).
    Sets company status to False, preventing user access.
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        if not getattr(company, "status", True):
            return {
                "success": True,
                "company_id": str(company.id),
                "company_name": company.name,
                "status": "suspended",
                "message": f"Company '{company.name}' is already suspended",
            }

        company.status = False
        session.commit()

        return {
            "success": True,
            "company_id": str(company.id),
            "company_name": company.name,
            "status": "suspended",
            "message": f"Company '{company.name}' has been suspended",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error suspending company: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to suspend company: {str(e)}"
        )
    finally:
        session.close()


@app.post(
    "/v1/admin/companies/{company_id}/unsuspend",
    tags=["Admin"],
    summary="Unsuspend a company (super admin only)",
    description="Re-enables access to a suspended company.",
)
async def admin_unsuspend_company(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Unsuspend a company (super admin only).
    Sets company status to True, restoring user access.
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    session = get_session()
    try:
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        if getattr(company, "status", True):
            return {
                "success": True,
                "company_id": str(company.id),
                "company_name": company.name,
                "status": "active",
                "message": f"Company '{company.name}' is already active",
            }

        company.status = True
        session.commit()

        return {
            "success": True,
            "company_id": str(company.id),
            "company_name": company.name,
            "status": "active",
            "message": f"Company '{company.name}' has been unsuspended",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error unsuspending company: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to unsuspend company: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Merge Companies
# ============================================


@app.post(
    "/v1/admin/companies/merge",
    tags=["Admin"],
    summary="Merge two companies (super admin only)",
    description="Moves all users from source company to target company, then deletes source.",
)
async def admin_merge_companies(
    source_company_id: str = Query(
        ..., description="Company to merge FROM (will be deleted)"
    ),
    target_company_id: str = Query(
        ..., description="Company to merge INTO (will receive users)"
    ),
    authorization: str = Header(None),
):
    """
    Merge two companies (super admin only).
    Moves all users from source to target, then deletes the source company.
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Super admin permissions required.",
        )

    if source_company_id == target_company_id:
        raise HTTPException(
            status_code=400,
            detail="Source and target companies must be different",
        )

    session = get_session()
    try:
        # Verify both companies exist
        source = session.query(Company).filter(Company.id == source_company_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Source company not found")

        target = session.query(Company).filter(Company.id == target_company_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="Target company not found")

        # Get source company users
        source_users = (
            session.query(UserCompany)
            .filter(UserCompany.company_id == source_company_id)
            .all()
        )

        moved_users = []
        skipped_users = []

        for uc in source_users:
            # Check if user already in target
            existing = (
                session.query(UserCompany)
                .filter(
                    UserCompany.user_id == uc.user_id,
                    UserCompany.company_id == target_company_id,
                )
                .first()
            )

            user = session.query(User).filter(User.id == uc.user_id).first()
            user_email = user.email if user else str(uc.user_id)

            if existing:
                # User already in target, skip
                skipped_users.append(user_email)
                session.delete(uc)
            else:
                # Move user to target
                uc.company_id = target_company_id
                moved_users.append(user_email)

        # Add source token balance to target
        source_tokens = getattr(source, "token_balance", 0) or 0
        source_usd = getattr(source, "token_balance_usd", 0) or 0
        target.token_balance = (
            getattr(target, "token_balance", 0) or 0
        ) + source_tokens
        target.token_balance_usd = (
            getattr(target, "token_balance_usd", 0) or 0
        ) + source_usd

        # Delete source company
        source_name = source.name
        session.delete(source)
        session.commit()

        return {
            "success": True,
            "source_company": {
                "id": source_company_id,
                "name": source_name,
                "deleted": True,
            },
            "target_company": {
                "id": target_company_id,
                "name": target.name,
            },
            "moved_users": moved_users,
            "skipped_users": skipped_users,
            "tokens_transferred": source_tokens,
            "usd_transferred": source_usd,
            "message": f"Merged '{source_name}' into '{target.name}'. {len(moved_users)} users moved, {len(skipped_users)} skipped (already in target).",
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error merging companies: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to merge companies: {str(e)}"
        )
    finally:
        session.close()


# ============================================
# SUPER ADMIN ENDPOINTS - Token Usage Analytics
# ============================================


class AnalyticsDateRange(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@app.get(
    "/v1/admin/analytics/usage",
    tags=["Admin", "Analytics"],
    summary="Get server-wide token usage analytics (super admin only)",
    description="Returns aggregated token usage statistics across all companies and users. Works regardless of billing status.",
)
async def admin_get_usage_analytics(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    sort_by: Optional[str] = Query(
        "total_tokens", description="Sort by: total_tokens, input_tokens, output_tokens"
    ),
    sort_direction: Optional[str] = Query(
        "desc", description="Sort direction: asc, desc"
    ),
    limit: int = Query(100, description="Max companies to return"),
    offset: int = Query(0, description="Offset for pagination"),
    authorization: str = Header(None),
):
    """
    Get server-wide token usage analytics (super admin only).

    Returns aggregated token usage per company including:
    - Total tokens used per company (from CompanyTokenUsage audit trail)
    - Per-user breakdown within each company
    - Total input/output tokens
    - User count per company

    This endpoint works regardless of whether billing is enabled.
    """
    from sqlalchemy import func, case

    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin role required.",
        )

    session = get_session()
    try:
        # Parse date filters
        start_dt = None
        end_dt = None
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format")

        # Get all companies with user counts
        companies = session.query(Company).all()
        company_ids = [c.id for c in companies]

        # Batch load user counts per company
        user_counts_query = (
            session.query(
                UserCompany.company_id,
                func.count(UserCompany.id).label("user_count"),
            )
            .filter(UserCompany.company_id.in_(company_ids))
            .group_by(UserCompany.company_id)
            .all()
        )
        user_counts_map = {row.company_id: row.user_count for row in user_counts_query}

        # Batch load CompanyTokenUsage aggregates per company
        usage_base_query = session.query(
            CompanyTokenUsage.company_id,
            func.coalesce(func.sum(CompanyTokenUsage.input_tokens), 0).label(
                "input_tokens"
            ),
            func.coalesce(func.sum(CompanyTokenUsage.output_tokens), 0).label(
                "output_tokens"
            ),
            func.coalesce(func.sum(CompanyTokenUsage.total_tokens), 0).label(
                "total_tokens"
            ),
            func.count(CompanyTokenUsage.id).label("usage_count"),
        ).filter(CompanyTokenUsage.company_id.in_(company_ids))

        if start_dt:
            usage_base_query = usage_base_query.filter(
                CompanyTokenUsage.timestamp >= start_dt
            )
        if end_dt:
            usage_base_query = usage_base_query.filter(
                CompanyTokenUsage.timestamp <= end_dt
            )

        usage_results = usage_base_query.group_by(CompanyTokenUsage.company_id).all()
        usage_map = {
            row.company_id: {
                "input_tokens": int(row.input_tokens),
                "output_tokens": int(row.output_tokens),
                "total_tokens": int(row.total_tokens),
                "usage_count": int(row.usage_count),
            }
            for row in usage_results
        }

        # Batch load all UserCompany records
        all_user_companies = (
            session.query(UserCompany)
            .filter(UserCompany.company_id.in_(company_ids))
            .all()
        )
        # Group by company_id
        company_users_map = {}
        all_user_ids = set()
        for uc in all_user_companies:
            if uc.company_id not in company_users_map:
                company_users_map[uc.company_id] = []
            company_users_map[uc.company_id].append(uc)
            all_user_ids.add(uc.user_id)

        # Batch load all UserPreferences for token counts
        all_prefs = (
            session.query(UserPreferences)
            .filter(
                UserPreferences.user_id.in_(all_user_ids),
                UserPreferences.pref_key.in_(["input_tokens", "output_tokens"]),
            )
            .all()
        )
        # Build lookup: {user_id: {pref_key: pref_value}}
        prefs_map = {}
        for pref in all_prefs:
            if pref.user_id not in prefs_map:
                prefs_map[pref.user_id] = {}
            prefs_map[pref.user_id][pref.pref_key] = pref.pref_value

        company_data = {}

        for company in companies:
            company_id = str(company.id)

            user_count = user_counts_map.get(company.id, 0)
            usage_result = usage_map.get(company.id)

            # Calculate cumulative from UserPreferences for users in this company
            cumulative_input = 0
            cumulative_output = 0
            for uc in company_users_map.get(company.id, []):
                user_prefs = prefs_map.get(uc.user_id, {})
                input_val = user_prefs.get("input_tokens")
                output_val = user_prefs.get("output_tokens")
                if input_val:
                    try:
                        cumulative_input += int(input_val)
                    except (ValueError, TypeError):
                        pass
                if output_val:
                    try:
                        cumulative_output += int(output_val)
                    except (ValueError, TypeError):
                        pass

            company_data[company_id] = {
                "company_id": company_id,
                "company_name": company.name,
                "status": getattr(company, "status", True),
                "user_count": user_count,
                "token_balance": getattr(company, "token_balance", 0) or 0,
                "token_balance_usd": getattr(company, "token_balance_usd", 0) or 0,
                "tokens_used_total": getattr(company, "tokens_used_total", 0) or 0,
                # Audit trail usage (from CompanyTokenUsage)
                "audit_input_tokens": (
                    int(usage_result.input_tokens) if usage_result else 0
                ),
                "audit_output_tokens": (
                    int(usage_result.output_tokens) if usage_result else 0
                ),
                "audit_total_tokens": (
                    int(usage_result.total_tokens) if usage_result else 0
                ),
                "audit_usage_count": (
                    int(usage_result.usage_count) if usage_result else 0
                ),
                # Cumulative usage (from UserPreferences)
                "cumulative_input_tokens": cumulative_input,
                "cumulative_output_tokens": cumulative_output,
                "cumulative_total_tokens": cumulative_input + cumulative_output,
            }

        # Convert to list and sort
        company_list = list(company_data.values())

        # Determine sort key
        if sort_by == "input_tokens":
            sort_key = "cumulative_input_tokens"
        elif sort_by == "output_tokens":
            sort_key = "cumulative_output_tokens"
        else:
            sort_key = "cumulative_total_tokens"

        reverse = sort_direction.lower() == "desc"
        company_list.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)

        # Calculate totals
        total_input = sum(c["cumulative_input_tokens"] for c in company_list)
        total_output = sum(c["cumulative_output_tokens"] for c in company_list)
        total_tokens = total_input + total_output

        # Apply pagination
        total_companies = len(company_list)
        paginated = company_list[offset : offset + limit]

        return {
            "companies": paginated,
            "total": total_companies,
            "limit": limit,
            "offset": offset,
            "summary": {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_tokens,
                "total_companies": total_companies,
                "total_users": sum(c["user_count"] for c in company_list),
            },
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting usage analytics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get usage analytics: {str(e)}"
        )
    finally:
        session.close()


@app.get(
    "/v1/admin/analytics/usage/company/{company_id}",
    tags=["Admin", "Analytics"],
    summary="Get detailed token usage for a specific company (super admin only)",
    description="Returns per-user token usage breakdown for a company.",
)
async def admin_get_company_usage_analytics(
    company_id: str,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    authorization: str = Header(None),
):
    """
    Get detailed token usage analytics for a specific company (super admin only).

    Returns per-user breakdown including:
    - User email and name
    - Input/output/total tokens per user
    - Recent usage records from audit trail
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin role required.",
        )

    session = get_session()
    try:
        # Verify company exists
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Parse date filters
        start_dt = None
        end_dt = None
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format")

        # Get all users in this company
        user_companies = (
            session.query(UserCompany)
            .filter(UserCompany.company_id == company_id)
            .all()
        )

        if not user_companies:
            return {
                "company": {
                    "id": str(company.id),
                    "name": company.name,
                    "status": getattr(company, "status", True),
                    "token_balance": getattr(company, "token_balance", 0) or 0,
                    "token_balance_usd": getattr(company, "token_balance_usd", 0) or 0,
                    "tokens_used_total": getattr(company, "tokens_used_total", 0) or 0,
                },
                "users": [],
                "summary": {
                    "total_users": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tokens": 0,
                },
                "date_range": {"start_date": start_date, "end_date": end_date},
            }

        # Batch load all related data
        user_ids = [uc.user_id for uc in user_companies]
        role_ids = {uc.role_id for uc in user_companies if uc.role_id}

        # Batch load users
        users = session.query(User).filter(User.id.in_(user_ids)).all()
        users_map = {u.id: u for u in users}

        # Batch load roles
        from DB import UserRole

        roles_map = {}
        if role_ids:
            roles = session.query(UserRole).filter(UserRole.id.in_(role_ids)).all()
            roles_map = {r.id: r for r in roles}

        # Batch load preferences
        prefs = (
            session.query(UserPreferences)
            .filter(
                UserPreferences.user_id.in_(user_ids),
                UserPreferences.pref_key.in_(["input_tokens", "output_tokens"]),
            )
            .all()
        )
        prefs_map = {}
        for pref in prefs:
            if pref.user_id not in prefs_map:
                prefs_map[pref.user_id] = {}
            prefs_map[pref.user_id][pref.pref_key] = pref.pref_value

        # Build audit query base
        audit_query = session.query(CompanyTokenUsage).filter(
            CompanyTokenUsage.company_id == company_id,
            CompanyTokenUsage.user_id.in_(user_ids),
        )
        if start_dt:
            audit_query = audit_query.filter(CompanyTokenUsage.timestamp >= start_dt)
        if end_dt:
            audit_query = audit_query.filter(CompanyTokenUsage.timestamp <= end_dt)

        # Get all audit records (we'll group them by user_id after)
        all_audit_records = audit_query.order_by(
            desc(CompanyTokenUsage.timestamp)
        ).all()

        # Group audit records by user_id and limit to 50 each
        audit_by_user = {}
        for record in all_audit_records:
            if record.user_id not in audit_by_user:
                audit_by_user[record.user_id] = []
            if len(audit_by_user[record.user_id]) < 50:
                audit_by_user[record.user_id].append(record)

        users_data = []
        for uc in user_companies:
            user = users_map.get(uc.user_id)
            if not user:
                continue

            role = roles_map.get(uc.role_id)
            role_name = role.friendly_name if role else f"Role {uc.role_id}"

            user_prefs = prefs_map.get(uc.user_id, {})
            input_tokens = 0
            output_tokens = 0
            try:
                input_tokens = int(user_prefs.get("input_tokens", 0) or 0)
            except (ValueError, TypeError):
                pass
            try:
                output_tokens = int(user_prefs.get("output_tokens", 0) or 0)
            except (ValueError, TypeError):
                pass

            audit_records = audit_by_user.get(uc.user_id, [])

            users_data.append(
                {
                    "user_id": str(uc.user_id),
                    "email": user.email,
                    "first_name": getattr(user, "first_name", ""),
                    "last_name": getattr(user, "last_name", ""),
                    "role_id": uc.role_id,
                    "role_name": role_name,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "recent_usage": [
                        {
                            "timestamp": (
                                r.timestamp.isoformat() if r.timestamp else None
                            ),
                            "input_tokens": r.input_tokens,
                            "output_tokens": r.output_tokens,
                            "total_tokens": r.total_tokens,
                        }
                        for r in audit_records
                    ],
                }
            )

        # Sort by total tokens descending
        users_data.sort(key=lambda x: x["total_tokens"], reverse=True)

        # Calculate company totals
        total_input = sum(u["input_tokens"] for u in users_data)
        total_output = sum(u["output_tokens"] for u in users_data)

        return {
            "company": {
                "id": str(company.id),
                "name": company.name,
                "status": getattr(company, "status", True),
                "token_balance": getattr(company, "token_balance", 0) or 0,
                "token_balance_usd": getattr(company, "token_balance_usd", 0) or 0,
                "tokens_used_total": getattr(company, "tokens_used_total", 0) or 0,
            },
            "users": users_data,
            "summary": {
                "total_users": len(users_data),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
            },
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting company usage analytics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get company usage analytics: {str(e)}"
        )
    finally:
        session.close()


@app.get(
    "/v1/admin/analytics/usage/users",
    tags=["Admin", "Analytics"],
    summary="Get all users' token usage across the server (super admin only)",
    description="Returns a flat list of all users with their token usage, sorted by usage.",
)
async def admin_get_all_users_usage(
    sort_by: Optional[str] = Query(
        "total_tokens", description="Sort by: total_tokens, input_tokens, output_tokens"
    ),
    sort_direction: Optional[str] = Query(
        "desc", description="Sort direction: asc, desc"
    ),
    limit: int = Query(100, description="Max users to return"),
    offset: int = Query(0, description="Offset for pagination"),
    authorization: str = Header(None),
):
    """
    Get all users' token usage across the server (super admin only).

    Returns a flat list of all users with:
    - User details (email, name)
    - Company association
    - Total input/output/tokens
    """
    auth = MagicalAuth(token=authorization)
    if not auth.is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin role required.",
        )

    session = get_session()
    try:
        # Get all users
        users = session.query(User).all()
        users_data = []

        for user in users:
            # Get user's company
            user_company = (
                session.query(UserCompany)
                .filter(UserCompany.user_id == user.id)
                .first()
            )
            company = None
            company_name = "No Company"
            if user_company:
                company = (
                    session.query(Company)
                    .filter(Company.id == user_company.company_id)
                    .first()
                )
                if company:
                    company_name = company.name

            # Get cumulative tokens from UserPreferences
            input_pref = (
                session.query(UserPreferences)
                .filter(
                    UserPreferences.user_id == user.id,
                    UserPreferences.pref_key == "input_tokens",
                )
                .first()
            )
            output_pref = (
                session.query(UserPreferences)
                .filter(
                    UserPreferences.user_id == user.id,
                    UserPreferences.pref_key == "output_tokens",
                )
                .first()
            )
            input_tokens = 0
            output_tokens = 0
            if input_pref:
                try:
                    input_tokens = int(input_pref.pref_value)
                except (ValueError, TypeError):
                    pass
            if output_pref:
                try:
                    output_tokens = int(output_pref.pref_value)
                except (ValueError, TypeError):
                    pass

            users_data.append(
                {
                    "user_id": str(user.id),
                    "email": user.email,
                    "first_name": getattr(user, "first_name", ""),
                    "last_name": getattr(user, "last_name", ""),
                    "company_id": (
                        str(user_company.company_id) if user_company else None
                    ),
                    "company_name": company_name,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            )

        # Determine sort key
        if sort_by == "input_tokens":
            sort_key = "input_tokens"
        elif sort_by == "output_tokens":
            sort_key = "output_tokens"
        else:
            sort_key = "total_tokens"

        reverse = sort_direction.lower() == "desc"
        users_data.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)

        # Calculate totals
        total_input = sum(u["input_tokens"] for u in users_data)
        total_output = sum(u["output_tokens"] for u in users_data)
        total_tokens = total_input + total_output

        # Apply pagination
        total_users = len(users_data)
        paginated = users_data[offset : offset + limit]

        return {
            "users": paginated,
            "total": total_users,
            "limit": limit,
            "offset": offset,
            "summary": {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_tokens,
                "total_users": total_users,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting all users usage: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get all users usage: {str(e)}"
        )
    finally:
        session.close()
