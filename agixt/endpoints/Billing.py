from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from Models import (
    CryptoInvoiceRequest,
    CryptoInvoiceResponse,
    CryptoVerifyRequest,
    PaymentQuoteRequest,
    PaymentQuoteResponse,
    PaymentTransactionResponse,
    StripePaymentIntentRequest,
    StripePaymentIntentResponse,
)
from MagicalAuth import MagicalAuth, verify_api_key
from Globals import getenv
from DB import PaymentTransaction, get_session
from payments import (
    CryptoPaymentService,
    PriceService,
    StripePaymentService,
    SUPPORTED_CURRENCIES,
)

app = APIRouter()

price_service = PriceService()
crypto_service = CryptoPaymentService(price_service=price_service)
stripe_service = StripePaymentService(price_service=price_service)


def _get_user_id(user: object) -> Optional[str]:
    if isinstance(user, dict):
        return user.get("id")
    return getattr(user, "id", None)


def _is_admin(user: object) -> bool:
    if isinstance(user, dict):
        return bool(user.get("admin"))
    return bool(getattr(user, "admin", False))


@app.get("/v1/billing/currencies", tags=["Billing"])
async def get_supported_currencies():
    currencies = [
        {
            "symbol": symbol,
            "network": details.get("network"),
            "decimals": details.get("decimals"),
            "mint": details.get("mint"),
        }
        for symbol, details in SUPPORTED_CURRENCIES.items()
    ]
    return {
        "base_price_usd": float(price_service.base_price_usd),
        "wallet_address": getenv("PAYMENT_WALLET_ADDRESS"),
        "currencies": currencies,
    }


@app.post(
    "/v1/billing/quote",
    response_model=PaymentQuoteResponse,
    tags=["Billing"],
)
async def get_payment_quote(payload: PaymentQuoteRequest):
    quote = await price_service.get_quote(payload.currency, payload.seat_count)
    return PaymentQuoteResponse(
        reference_code=None,
        seat_count=quote["seat_count"],
        currency=quote["currency"],
        network=quote.get("network"),
        amount_usd=quote["amount_usd"],
        amount_currency=quote["amount_currency"],
        exchange_rate=quote["exchange_rate"],
        wallet_address=getenv("PAYMENT_WALLET_ADDRESS"),
        expires_at=None,
    )


@app.post(
    "/v1/billing/crypto/invoice",
    response_model=CryptoInvoiceResponse,
    tags=["Billing"],
)
async def create_crypto_invoice(
    payload: CryptoInvoiceRequest,
    authorization: str = Header(None),
    user=Depends(verify_api_key),
):
    user_id = _get_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User context missing")
    company_id = None
    if authorization:
        company_auth = MagicalAuth(token=authorization)
        company_id = getattr(company_auth, "company_id", None)
    invoice = await crypto_service.create_invoice(
        seat_count=payload.seat_count,
        currency=payload.currency,
        expires_in_minutes=payload.expires_in_minutes,
        memo=payload.memo,
        user_id=user_id,
        company_id=company_id,
    )
    return CryptoInvoiceResponse(**invoice)


@app.post(
    "/v1/billing/crypto/verify",
    response_model=PaymentTransactionResponse,
    tags=["Billing"],
)
async def verify_crypto_invoice(
    payload: CryptoVerifyRequest,
    user=Depends(verify_api_key),
):
    user_id = _get_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User context missing")

    record = await crypto_service.verify_transaction(
        reference_code=payload.reference_code,
        transaction_hash=payload.transaction_hash,
        expected_user_id=user_id,
    )
    if record.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Payment not confirmed")
    return PaymentTransactionResponse(**record)


@app.post(
    "/v1/billing/stripe/payment-intent",
    response_model=StripePaymentIntentResponse,
    tags=["Billing"],
)
async def create_stripe_payment_intent(
    payload: StripePaymentIntentRequest,
    user=Depends(verify_api_key),
):
    user_id = _get_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User context missing")
    try:
        result = await stripe_service.create_payment_intent(
            seat_count=payload.seat_count,
            metadata=payload.metadata,
            user_id=user_id,
            company_id=None,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guardrail
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return StripePaymentIntentResponse(
        client_secret=result["client_secret"],
        payment_intent_id=result["payment_intent_id"],
        amount_usd=result["amount_usd"],
        seat_count=result["seat_count"],
        reference_code=result.get("reference_code"),
    )


@app.get(
    "/v1/billing/transactions",
    response_model=List[PaymentTransactionResponse],
    tags=["Billing"],
)
async def list_payment_transactions(
    status: Optional[str] = None,
    limit: int = 50,
    user=Depends(verify_api_key),
):
    user_id = _get_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="User context missing")
    is_admin = _is_admin(user)
    limit = max(1, min(limit, 200))
    status_value = status.lower() if status else None

    session = get_session()
    try:
        query = session.query(PaymentTransaction)
        if not is_admin:
            query = query.filter(PaymentTransaction.user_id == user_id)
        if status_value:
            query = query.filter(PaymentTransaction.status == status_value)
        records = (
            query.order_by(PaymentTransaction.created_at.desc()).limit(limit).all()
        )
        return [
            PaymentTransactionResponse(**crypto_service._serialize_record(r))
            for r in records
        ]
    finally:
        session.close()
