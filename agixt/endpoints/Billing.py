from fastapi import APIRouter, Header, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from MagicalAuth import MagicalAuth, verify_api_key
from payments.pricing import PriceService
from payments.crypto import CryptoPaymentService
from payments.stripe_service import StripePaymentService
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
    sync: bool = True,
    authorization: str = Header(None),
):
    """Get company token balance - admin only. Automatically syncs payments from Stripe to catch missed webhooks."""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    # Sync payments from Stripe to catch any missed webhooks
    sync_result = None
    if sync:
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

        result = []
        for uc in user_companies_records:
            user = session.query(User).filter(User.id == uc.user_id).first()
            if not user:
                continue

            # Get user's token preferences
            input_tokens_pref = (
                session.query(UserPreferences)
                .filter(
                    UserPreferences.user_id == uc.user_id,
                    UserPreferences.pref_key == "input_tokens",
                )
                .first()
            )
            output_tokens_pref = (
                session.query(UserPreferences)
                .filter(
                    UserPreferences.user_id == uc.user_id,
                    UserPreferences.pref_key == "output_tokens",
                )
                .first()
            )

            input_tokens = int(input_tokens_pref.pref_value) if input_tokens_pref else 0
            output_tokens = (
                int(output_tokens_pref.pref_value) if output_tokens_pref else 0
            )

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
    Update the monthly auto top-up amount.

    This cancels the existing subscription and creates a new checkout session
    for the updated amount. The user will need to complete the checkout again.
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
    from Globals import getenv
    from decimal import Decimal

    # Verify AGiXT API Key
    agixt_api_key = getenv("AGIXT_API_KEY")
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
