import os
import uuid
from fastapi import APIRouter, Header, HTTPException, Depends, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from MagicalAuth import (
    MagicalAuth,
    verify_api_key,
    invalidate_user_scopes_cache,
    add_user_to_company_channels,
    invalidate_user_company_cache,
)
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
    token_millions: int = Field(..., ge=1)
    currency: str = "USD"


class TokenTopupCryptoRequest(BaseModel):
    token_millions: int = Field(..., ge=1)
    currency: str
    company_id: Optional[str] = None


class TokenTopupStripeRequest(BaseModel):
    token_millions: int = Field(..., ge=1)
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


class PlanCheckoutRequest(BaseModel):
    """Request to subscribe to a plan tier"""

    company_id: str
    plan_id: str = Field(
        ...,
        description="Plan tier ID (e.g., 'starter', 'team_5') or bed count for NurseXT",
    )
    billing_interval: str = Field(
        "month", description="Billing interval: 'month' or 'year'"
    )


class TokenTopupPlanRequest(BaseModel):
    """Request to add tokens to a tiered plan"""

    company_id: str
    token_millions: int = Field(
        ..., ge=1, description="Number of millions of tokens to purchase (minimum 1M)"
    )


class AddonRequest(BaseModel):
    """Request to add user/resource addons (Enterprise Plus only)"""

    company_id: str
    addon_count: int = Field(1, ge=1, description="Number of addons to add")


class UpdateCompanyRequest(BaseModel):
    """Request to update company details (super admin only)"""

    name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None


class ChangeUserRoleRequest(BaseModel):
    """Request to change a user's role in a company (super admin only)"""

    role_id: int = Field(
        ...,
        ge=0,
        le=3,
        description="New role ID (0=Super Admin, 1=Admin, 2=Manager, 3=User)",
    )


class AssignUserToCompanyRequest(BaseModel):
    """Request to assign a user to a company (super admin only)"""

    user_email: str = Field(..., description="Email address of the user to assign")
    role_id: int = Field(
        3, ge=0, le=3, description="Role ID (0=Super Admin, 1=Admin, 2=Manager, 3=User)"
    )


class ImpersonateUserRequest(BaseModel):
    """Request to impersonate a user (super admin only)"""

    user_email: str = Field(..., description="Email of the user to impersonate")


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
    else:
        # Default to user's primary company — never allow syncing all companies
        user_companies = auth.get_user_companies()
        if not user_companies:
            raise HTTPException(
                status_code=400, detail="User is not associated with any company"
            )
        company_id = user_companies[0]

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
        raise HTTPException(status_code=500, detail="Failed to create crypto invoice")


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
        raise HTTPException(status_code=500, detail="Failed to create payment intent")


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
        # Find the transaction with row-level locking to prevent double-crediting
        transaction = (
            session.query(PaymentTransaction)
            .with_for_update()
            .filter(
                PaymentTransaction.stripe_payment_intent_id == request.payment_intent_id
            )
            .first()
        )

        if not transaction:
            raise HTTPException(status_code=404, detail="Payment transaction not found")

        # Verify transaction belongs to user's company
        if transaction.company_id != company_id:
            raise HTTPException(
                status_code=403, detail="Transaction does not belong to your company"
            )

        # Check if already processed
        if transaction.status == "completed":
            tokens_credited = transaction.token_amount
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
                # Commit status FIRST so idempotency guard
                # catches retries if add_tokens_to_company
                # succeeds but later code fails
                session.commit()

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
            else:
                session.commit()
            return {
                "success": True,
                "message": "Payment confirmed and tokens credited",
                "tokens_credited": tokens_credited,
            }
        elif payment_intent.status == "processing":
            logging.info(f"PaymentIntent {request.payment_intent_id} still processing")
            return {
                "success": False,
                "message": "Payment is still processing. Please try again in a moment.",
            }
        elif payment_intent.status == "requires_payment_method":
            raise HTTPException(
                status_code=400, detail="Payment requires a valid payment method"
            )
        else:
            logging.warning(
                f"PaymentIntent {request.payment_intent_id} returned unexpected status: {getattr(payment_intent, 'status', None)}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Payment failed with status: {payment_intent.status}",
            )

    except stripe_lib.error.StripeError as e:
        session.rollback()
        logging.error(f"Stripe API error: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Payment processing error. Please try again."
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error confirming payment: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to confirm payment")
    finally:
        session.close()


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
        # Find the transaction by payment intent ID with row-level locking
        transaction = (
            session.query(PaymentTransaction)
            .with_for_update()
            .filter(
                PaymentTransaction.stripe_payment_intent_id == request.payment_intent_id
            )
            .first()
        )

        if not transaction:
            raise HTTPException(status_code=404, detail="Payment transaction not found")

        # Verify transaction belongs to the user
        if transaction.user_id != auth.user_id:
            raise HTTPException(
                status_code=403, detail="Transaction does not belong to you"
            )

        # Check if already processed
        if transaction.status == "completed":
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
                # Commit status FIRST so idempotency guard
                # catches retries if add_tokens_to_company
                # succeeds but later code fails
                session.commit()

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
            return {
                "success": True,
                "message": "Payment confirmed and processed",
                "seat_count": transaction.seat_count,
                "tokens_credited": transaction.token_amount,
            }
        elif payment_intent.status == "processing":
            logging.info(f"PaymentIntent {request.payment_intent_id} still processing")
            return {
                "success": False,
                "message": "Payment is still processing. Please try again in a moment.",
            }
        elif payment_intent.status == "requires_payment_method":
            raise HTTPException(
                status_code=400, detail="Payment requires a valid payment method"
            )
        else:
            logging.warning(
                f"PaymentIntent {request.payment_intent_id} returned unexpected status: {getattr(payment_intent, 'status', None)}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Payment failed with status: {payment_intent.status}",
            )

    except stripe_lib.error.StripeError as e:
        session.rollback()
        logging.error(f"Stripe API error: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Payment processing error. Please try again."
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error confirming payment: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to confirm payment")
    finally:
        session.close()


@app.post(
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
    limit: int = Query(100, le=1000, ge=1),
    offset: int = Query(0, ge=0),
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

        transactions = (
            query.order_by(desc(PaymentTransaction.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

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
    "/v1/billing/usage",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def get_company_usage(
    company_id: str,
    limit: int = Query(100, le=1000, ge=1),
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
        # Batch-fetch all users to avoid N+1
        user_ids = list({record.user_id for record in usage_records})
        users = (
            session.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
        )
        users_by_id = {str(u.id): u.email for u in users}

        result = []
        for record in usage_records:
            result.append(
                {
                    "user_id": record.user_id,
                    "user_email": users_by_id.get(str(record.user_id), "Unknown"),
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
        raise HTTPException(status_code=500, detail="Failed to create subscription")


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
        raise HTTPException(status_code=500, detail="Failed to update subscription")


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
        raise HTTPException(status_code=500, detail="Failed to cancel subscription")


# ============================================================================
# Plan Management Endpoints (tiered_plan and per_bed pricing)
# ============================================================================


@app.get(
    "/v1/billing/plan/limits",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Get plan limits and current usage",
)
async def get_plan_limits(
    company_id: str,
    authorization: str = Header(None),
):
    """
    Get current plan limits and usage for a company.

    Returns plan tier info, limits (users, devices, tokens, storage),
    current usage, addon info, and any warnings about approaching limits.
    """
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    return auth.get_plan_limits(company_id)


@app.post(
    "/v1/billing/plan/checkout",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Subscribe to a plan or change plan",
)
async def create_plan_checkout(
    request: PlanCheckoutRequest,
    authorization: str = Header(None),
):
    """
    Create a Stripe checkout session for subscribing to a plan tier.

    For tiered plans (AGiXT, XT Systems, BoltRemote, UltraEstimate):
    - Pass plan_id like 'starter', 'team_5', 'team_10', etc.

    For per-bed pricing (NurseXT):
    - Pass plan_id as the number of beds (e.g., '10' for 10 beds)

    Returns a checkout URL to redirect the user to Stripe.
    """
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    user_companies = auth.get_user_companies()
    if request.company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    session = get_session()
    try:
        user = session.query(User).filter(User.id == auth.user_id).first()
        user_email = user.email if user else None
    finally:
        session.close()

    stripe_service = StripePaymentService()
    try:
        # Validate billing_interval
        interval = request.billing_interval
        if interval not in ("month", "year"):
            interval = "month"

        result = await stripe_service.create_plan_checkout(
            company_id=request.company_id,
            plan_id=request.plan_id,
            user_email=user_email,
            billing_interval=interval,
        )
        return result
    except Exception as e:
        logging.error(f"Error creating plan checkout: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create checkout")


@app.post(
    "/v1/billing/plan/topup",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Purchase additional tokens",
)
async def purchase_token_topup(
    request: TokenTopupPlanRequest,
    authorization: str = Header(None),
):
    """
    Purchase additional tokens for a tiered plan.

    Tokens are $5 per 1M tokens, minimum purchase of 1M tokens.
    Purchased tokens are added to the company's balance immediately and
    do not expire at the end of the billing period.
    """
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    user_companies = auth.get_user_companies()
    if request.company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    stripe_service = StripePaymentService()
    try:
        session = get_session()
        try:
            user = session.query(User).filter(User.id == auth.user_id).first()
            user_email = user.email if user else None
        finally:
            session.close()

        result = await stripe_service.create_token_topup_checkout(
            company_id=request.company_id,
            token_millions=request.token_millions,
            user_email=user_email,
        )
        return result
    except Exception as e:
        logging.error(f"Error creating token topup: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create token topup")


@app.post(
    "/v1/billing/plan/addon",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Add user/resource addons (Enterprise Plus only)",
)
async def purchase_addon(
    request: AddonRequest,
    authorization: str = Header(None),
):
    """
    Purchase user/resource addons for the Enterprise Plus (enterprise_100) plan.

    Each addon ($10/month) adds:
    - 1 additional user
    - 100 additional devices
    - 10M additional monthly tokens
    - 2GB additional storage

    Only available for companies on the Enterprise Plus plan.
    """
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    user_companies = auth.get_user_companies()
    if request.company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    session = get_session()
    try:
        user = session.query(User).filter(User.id == auth.user_id).first()
        user_email = user.email if user else None
    finally:
        session.close()

    stripe_service = StripePaymentService()
    try:
        result = await stripe_service.create_addon_checkout(
            company_id=request.company_id,
            addon_count=request.addon_count,
            user_email=user_email,
        )
        return result
    except Exception as e:
        logging.error(f"Error creating addon checkout: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create addon checkout")


@app.get(
    "/v1/billing/plan/device-check",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Check device limit",
)
async def check_device_limit(
    company_id: str,
    authorization: str = Header(None),
):
    """Check if the company can register more devices based on current plan limits."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    return auth.check_device_limit(company_id)


@app.get(
    "/v1/billing/plan/storage-check",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Check storage limit",
)
async def check_storage_limit(
    company_id: str,
    additional_bytes: int = 0,
    authorization: str = Header(None),
):
    """Check if the company can use more storage based on current plan limits."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    return auth.check_storage_limit(company_id, additional_bytes)


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

    import hmac

    # Verify AGiXT API Key
    agixt_api_key = os.getenv("AGIXT_API_KEY", "")
    provided_key = str(authorization).replace("Bearer ", "").replace("bearer ", "")

    if not agixt_api_key or not hmac.compare_digest(provided_key, agixt_api_key):
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
            reference_code=f"ADMIN_CREDIT_{company}_{uuid.uuid4().hex[:8]}",
        )
        session.add(transaction)
        session.commit()

        # Add tokens via root parent resolution
        from MagicalAuth import MagicalAuth

        auth = MagicalAuth()
        auth.add_tokens_to_company(
            company_id=company,
            token_amount=tokens,
            amount_usd=float(amount_decimal),
        )

        # Re-fetch company to get updated balances
        session2 = get_session()
        try:
            company_record = (
                session2.query(Company).filter(Company.id == company).first()
            )
            new_balance_tokens = company_record.token_balance if company_record else 0
            new_balance_usd = (
                company_record.token_balance_usd if company_record else 0.0
            )
        finally:
            session2.close()

        return {
            "success": True,
            "company_id": company,
            "amount_usd": float(amount_decimal),
            "tokens_credited": tokens,
            "token_millions": float(token_millions),
            "new_balance_tokens": new_balance_tokens,
            "new_balance_usd": new_balance_usd,
            "transaction_id": transaction.id,
            "reference_code": transaction.reference_code,
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error issuing credits to company {company}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to issue credits")
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
            reference_code=f"ADMIN_CREDIT_{request.company_id}_{uuid.uuid4().hex[:8]}",
        )
        session.add(transaction)
        session.commit()

        # Add tokens via root parent resolution
        from MagicalAuth import MagicalAuth as MA

        ma = MA()
        ma.add_tokens_to_company(
            company_id=request.company_id,
            token_amount=tokens,
            amount_usd=float(amount_decimal),
        )

        # Re-fetch company to get updated balances
        session2 = get_session()
        try:
            company_record = (
                session2.query(Company).filter(Company.id == request.company_id).first()
            )
            new_balance_tokens = company_record.token_balance if company_record else 0
            new_balance_usd = (
                company_record.token_balance_usd if company_record else 0.0
            )
        finally:
            session2.close()

        return {
            "success": True,
            "company_id": request.company_id,
            "company_name": company_record.name if company_record else "",
            "amount_usd": float(amount_decimal),
            "tokens_credited": tokens,
            "token_millions": float(token_millions),
            "new_balance_tokens": new_balance_tokens,
            "new_balance_usd": new_balance_usd,
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
        raise HTTPException(status_code=500, detail="Failed to issue credits")
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
    import hmac

    agixt_api_key = os.getenv("AGIXT_API_KEY", "")
    provided_key = str(authorization).replace("Bearer ", "").replace("bearer ", "")

    is_api_key_auth = bool(agixt_api_key) and hmac.compare_digest(
        provided_key, agixt_api_key
    )
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
        raise HTTPException(status_code=500, detail="Failed to set super admin")
    finally:
        session.close()


# Protected company names that cannot be deleted (configurable via env)
PROTECTED_COMPANIES = [
    name.strip()
    for name in os.getenv("PROTECTED_COMPANIES", "DevXT,Josh's Team").split(",")
    if name.strip()
]

# Protected emails that cannot be deactivated (configurable via env)
PROTECTED_EMAILS = [
    email.strip().lower()
    for email in os.getenv("PROTECTED_EMAILS", "josh@devxt.com").split(",")
    if email.strip()
]


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
        raise HTTPException(status_code=500, detail="Failed to delete company")
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
        if user.email.lower() in PROTECTED_EMAILS:
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
        raise HTTPException(status_code=500, detail="Failed to deactivate user")
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
            status_code=500, detail="Failed to remove user from company"
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
    request: AssignUserToCompanyRequest,
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
        user = (
            session.query(User).filter(User.email == request.user_email.lower()).first()
        )
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with email '{request.user_email}' not found",
            )

        role_id = request.role_id

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

        # Add user to all non-invite-only company channels
        try:
            add_user_to_company_channels(
                session=session, user_id=str(user.id), company_id=company_id
            )
            session.commit()
            invalidate_user_company_cache(str(user.id))
        except Exception as e:
            logging.warning(f"Failed to add user to company channels: {e}")

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
        raise HTTPException(status_code=500, detail="Failed to assign user to company")
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
        raise HTTPException(status_code=500, detail="Failed to get server stats")
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

        # Create new company (use classmethod to auto-generate encryption_key)
        new_company = Company.create(
            session,
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
        raise HTTPException(status_code=500, detail="Failed to create company")
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
    request: UpdateCompanyRequest,
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
        if request.name is not None:
            # Check name uniqueness if changing
            if request.name != company.name:
                existing = (
                    session.query(Company).filter(Company.name == request.name).first()
                )
                if existing:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Company with name '{request.name}' already exists",
                    )
            company.name = request.name
            updated_fields.append("name")
        if request.email is not None:
            company.email = request.email
            updated_fields.append("email")
        if request.phone_number is not None:
            company.phone_number = request.phone_number
            updated_fields.append("phone_number")
        if request.website is not None:
            company.website = request.website
            updated_fields.append("website")
        if request.address is not None:
            company.address = request.address
            updated_fields.append("address")
        if request.city is not None:
            company.city = request.city
            updated_fields.append("city")
        if request.state is not None:
            company.state = request.state
            updated_fields.append("state")
        if request.zip_code is not None:
            company.zip_code = request.zip_code
            updated_fields.append("zip_code")
        if request.country is not None:
            company.country = request.country
            updated_fields.append("country")
        if request.notes is not None:
            company.notes = request.notes
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
        raise HTTPException(status_code=500, detail="Failed to update company")
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
    request: ChangeUserRoleRequest,
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

    role_id = request.role_id
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
        raise HTTPException(status_code=500, detail="Failed to change user role")
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
    request: ImpersonateUserRequest,
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
        user = (
            session.query(User).filter(User.email == request.user_email.lower()).first()
        )
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with email '{request.user_email}' not found",
            )

        # Generate token
        token = impersonate_user(request.user_email.lower())

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
            status_code=500, detail="Failed to generate impersonation token"
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
        raise HTTPException(status_code=500, detail="Failed to export companies")
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
        raise HTTPException(status_code=500, detail="Failed to suspend company")
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
        raise HTTPException(status_code=500, detail="Failed to unsuspend company")
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
        raise HTTPException(status_code=500, detail="Failed to merge companies")
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
                    int(usage_result["input_tokens"]) if usage_result else 0
                ),
                "audit_output_tokens": (
                    int(usage_result["output_tokens"]) if usage_result else 0
                ),
                "audit_total_tokens": (
                    int(usage_result["total_tokens"]) if usage_result else 0
                ),
                "audit_usage_count": (
                    int(usage_result["usage_count"]) if usage_result else 0
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
        raise HTTPException(status_code=500, detail="Failed to get usage analytics")
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
            status_code=500, detail="Failed to get company usage analytics"
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
        from sqlalchemy import func, case, literal_column
        from sqlalchemy.orm import aliased

        input_pref = aliased(UserPreferences)
        output_pref = aliased(UserPreferences)

        # Single query with LEFT JOINs to batch-load all related data
        base_query = (
            session.query(
                User.id,
                User.email,
                User.first_name,
                User.last_name,
                UserCompany.company_id,
                Company.name.label("company_name"),
                input_pref.pref_value.label("input_tokens_str"),
                output_pref.pref_value.label("output_tokens_str"),
            )
            .outerjoin(UserCompany, UserCompany.user_id == User.id)
            .outerjoin(Company, Company.id == UserCompany.company_id)
            .outerjoin(
                input_pref,
                (input_pref.user_id == User.id)
                & (input_pref.pref_key == "input_tokens"),
            )
            .outerjoin(
                output_pref,
                (output_pref.user_id == User.id)
                & (output_pref.pref_key == "output_tokens"),
            )
        )

        # Get total count first
        total_users = base_query.count()

        # Build rows and parse token values
        rows = base_query.all()
        users_data = []
        total_input = 0
        total_output = 0
        for row in rows:
            try:
                input_tokens = int(row.input_tokens_str) if row.input_tokens_str else 0
            except (ValueError, TypeError):
                input_tokens = 0
            try:
                output_tokens = (
                    int(row.output_tokens_str) if row.output_tokens_str else 0
                )
            except (ValueError, TypeError):
                output_tokens = 0
            total_input += input_tokens
            total_output += output_tokens
            users_data.append(
                {
                    "user_id": str(row.id),
                    "email": row.email,
                    "first_name": row.first_name or "",
                    "last_name": row.last_name or "",
                    "company_id": str(row.company_id) if row.company_id else None,
                    "company_name": row.company_name or "No Company",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            )

        # Sort in Python (token values are parsed from strings, hard to sort in DB)
        if sort_by == "input_tokens":
            sort_key = "input_tokens"
        elif sort_by == "output_tokens":
            sort_key = "output_tokens"
        else:
            sort_key = "total_tokens"

        reverse = sort_direction.lower() == "desc"
        users_data.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)

        total_tokens = total_input + total_output

        # Apply pagination
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
        raise HTTPException(status_code=500, detail="Failed to get all users usage")
    finally:
        session.close()


@app.get(
    "/v1/billing/invoice/{transaction_ref}",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
    summary="Get invoice/receipt URL for a transaction",
)
async def get_invoice_url(
    transaction_ref: str,
    authorization: str = Header(None),
):
    """
    Get the Stripe hosted invoice URL or receipt URL for a completed transaction.
    Returns URLs to view/download the invoice or receipt.
    """
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    session = get_session()
    try:
        # Find the transaction
        transaction = (
            session.query(PaymentTransaction)
            .filter(PaymentTransaction.reference_code == transaction_ref)
            .first()
        )

        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Verify user has access to this transaction's company
        user_companies = auth.get_user_companies()
        if transaction.company_id not in user_companies:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this transaction",
            )

        stripe_api_key = os.getenv("STRIPE_SECRET_KEY")
        if not stripe_api_key or stripe_api_key.lower() == "none":
            raise HTTPException(status_code=400, detail="Stripe is not configured")

        import stripe as stripe_lib

        stripe_lib.api_key = stripe_api_key

        payment_intent_id = transaction.stripe_payment_intent_id
        if not payment_intent_id:
            return {
                "invoice_url": None,
                "receipt_url": None,
                "invoice_pdf": None,
            }

        try:
            # Try to find an invoice associated with this payment
            # For subscriptions, the payment intent is linked to an invoice
            matching_invoice = None
            try:
                # Use Stripe's search to find invoice by payment_intent directly
                invoices = stripe_lib.Invoice.list(
                    limit=100,
                )
                for inv in invoices.data:
                    if inv.payment_intent == payment_intent_id:
                        matching_invoice = inv
                        break
            except Exception:
                pass

            if matching_invoice:
                return {
                    "invoice_url": matching_invoice.hosted_invoice_url,
                    "receipt_url": None,
                    "invoice_pdf": matching_invoice.invoice_pdf,
                }

            # Fall back to receipt URL from the charge
            pi = stripe_lib.PaymentIntent.retrieve(payment_intent_id)
            latest_charge = pi.latest_charge
            if latest_charge:
                charge = stripe_lib.Charge.retrieve(latest_charge)
                return {
                    "invoice_url": None,
                    "receipt_url": charge.receipt_url,
                    "invoice_pdf": None,
                }
        except Exception as e:
            logging.warning(f"Failed to fetch invoice URL from Stripe: {e}")

        return {
            "invoice_url": None,
            "receipt_url": None,
            "invoice_pdf": None,
        }
    finally:
        session.close()
