from fastapi import APIRouter, Header, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel
from MagicalAuth import MagicalAuth, verify_api_key
from payments.pricing import PriceService
from payments.crypto import CryptoPaymentService
from payments.stripe_service import StripePaymentService
from DB import PaymentTransaction, CompanyTokenUsage, User, get_session
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


# Endpoints
@app.get(
    "/v1/billing/tokens/balance",
    tags=["Billing"],
    dependencies=[Depends(verify_api_key)],
)
async def get_token_balance(
    company_id: str,
    authorization: str = Header(None),
):
    """Get company token balance - admin only"""
    auth = MagicalAuth(token=authorization)
    auth.validate_user()

    # Verify user has access to this company
    user_companies = auth.get_user_companies()
    if company_id not in user_companies:
        raise HTTPException(
            status_code=403, detail="You do not have access to this company"
        )

    return auth.get_company_token_balance(company_id)


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
