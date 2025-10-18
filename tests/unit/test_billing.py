import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
AGIXT_SRC = os.path.join(PROJECT_ROOT, "agixt")
if AGIXT_SRC not in sys.path:
    sys.path.insert(0, AGIXT_SRC)

from agixt.Globals import getenv
from agixt.DB import PaymentTransaction, get_session, engine
from agixt.payments import CryptoPaymentService, PriceService


@pytest.fixture(autouse=True)
def _set_wallet_env(monkeypatch):
    monkeypatch.setenv(
        "PAYMENT_WALLET_ADDRESS",
        getenv(
            "PAYMENT_WALLET_ADDRESS", "EmMgRcfTuyoX577SmRhjFVkWRFRvTwFfiY8wf5preXC1"
        ),
    )


@pytest.fixture(scope="module", autouse=True)
def _ensure_payment_table():
    PaymentTransaction.__table__.create(bind=engine, checkfirst=True)
    session = get_session()
    try:
        session.query(PaymentTransaction).delete()
        session.commit()
    finally:
        session.close()
    yield
    session = get_session()
    try:
        session.query(PaymentTransaction).delete()
        session.commit()
    finally:
        session.close()


def test_price_service_quote_stable_coin():
    service = PriceService()
    quote = asyncio.run(service.get_quote("USDC", seat_count=3))
    assert quote["seat_count"] == 3
    assert quote["currency"] == "USDC"
    assert pytest.approx(quote["amount_usd"], rel=1e-6) == float(
        service.base_price_usd * 3
    )
    assert pytest.approx(quote["amount_currency"], rel=1e-6) == float(
        service.base_price_usd * 3
    )
    assert quote["exchange_rate"] == pytest.approx(1.0, rel=1e-6)


def test_crypto_invoice_persists_record():
    service = PriceService()
    crypto = CryptoPaymentService(price_service=service)

    invoice = asyncio.run(
        crypto.create_invoice(
            seat_count=2,
            currency="USDC",
            expires_in_minutes=60,
            memo="TEST-INVOICE",
            user_id="user-test",
            company_id=None,
        )
    )

    assert invoice["reference_code"]
    assert invoice["wallet_address"] == getenv("PAYMENT_WALLET_ADDRESS")
    assert invoice["memo"] == "TEST-INVOICE"
    assert invoice["expires_at"].tzinfo is not None

    session = get_session()
    try:
        record = (
            session.query(PaymentTransaction)
            .filter(PaymentTransaction.reference_code == invoice["reference_code"])
            .first()
        )
        assert record is not None
        assert record.status == "pending"
        session.delete(record)
        session.commit()
    finally:
        session.close()


def test_verify_transaction_enforces_user(monkeypatch):
    service = PriceService()
    crypto = CryptoPaymentService(price_service=service)

    invoice = asyncio.run(
        crypto.create_invoice(
            seat_count=1,
            currency="USDC",
            expires_in_minutes=60,
            memo="VERIFY",
            user_id="user-1",
            company_id=None,
        )
    )

    async def fake_verify(self, record, transaction_hash, session):
        record.status = "completed"
        record.transaction_hash = transaction_hash
        record.metadata_json = json.dumps(
            {
                "slot": 123,
                "block_time": int(datetime.now(timezone.utc).timestamp()),
                "confirmed_amount": str(record.amount_currency),
            }
        )

    monkeypatch.setattr(CryptoPaymentService, "_verify_on_solana", fake_verify)

    result = asyncio.run(
        crypto.verify_transaction(
            reference_code=invoice["reference_code"],
            transaction_hash="FAKEHASH",
            expected_user_id="user-1",
        )
    )
    assert result["status"] == "completed"
    assert result["transaction_hash"] == "FAKEHASH"

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            crypto.verify_transaction(
                reference_code=invoice["reference_code"],
                transaction_hash="FAKEHASH",
                expected_user_id="user-2",
            )
        )
    assert exc_info.value.status_code == 403

    session = get_session()
    try:
        record = (
            session.query(PaymentTransaction)
            .filter(PaymentTransaction.reference_code == invoice["reference_code"])
            .first()
        )
        if record:
            session.delete(record)
            session.commit()
    finally:
        session.close()
