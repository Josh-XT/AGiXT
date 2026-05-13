import os
import sys
import uuid
from decimal import Decimal
from types import SimpleNamespace

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
AGIXT_SRC = os.path.join(PROJECT_ROOT, "agixt")
if AGIXT_SRC not in sys.path:
    sys.path.insert(0, AGIXT_SRC)

import MagicalAuth as magical_auth_module
from cryptography.fernet import Fernet
from DB import get_session
from MagicalAuth import MagicalAuth
from sqlalchemy import text
from TrialService import TrialService
from payments.pricing import PriceService


TIERED_PRICING_CONFIG = {
    "pricing_model": "tiered_plan",
    "tiers": [
        {
            "id": "starter",
            "name": "Starter",
            "price": 20.0,
            "limits": {
                "users": 1,
                "devices": 20,
                "tokens": 10_000_000,
                "storage_gb": 2,
            },
        }
    ],
    "trial": {
        "enabled": True,
        "plan_id": "starter",
        "days": 30,
        "credits_usd": 20.0,
        "requires_card": False,
    },
}


def test_tiered_trial_grant_records_usd_balance_when_token_price_is_zero(
    monkeypatch,
):
    user_id = f"trial-user-{uuid.uuid4()}"
    company_id = f"trial-company-{uuid.uuid4()}"
    email = f"trial-{uuid.uuid4()}@gmail.com"

    monkeypatch.setattr(PriceService, "get_token_price", lambda self: Decimal("0"))

    service = TrialService()
    monkeypatch.setattr(
        service.extensions_hub,
        "get_pricing_config",
        lambda: TIERED_PRICING_CONFIG,
    )

    _create_user_company(user_id=user_id, company_id=company_id, email=email)

    try:
        success, message, credits = service.grant_trial_credits(
            company_id=company_id,
            user_id=user_id,
            email=email,
        )

        assert success, message
        assert credits == 20.0

        session = get_session()
        try:
            company = (
                session.execute(
                    text(
                        "SELECT plan_id, trial_credits_granted, token_balance_usd, "
                        'token_balance FROM "Company" WHERE id = :company_id'
                    ),
                    {"company_id": company_id},
                )
                .mappings()
                .first()
            )
            user = (
                session.execute(
                    text('SELECT is_active FROM "user" WHERE id = :user_id'),
                    {"user_id": user_id},
                )
                .mappings()
                .first()
            )

            assert company["plan_id"] == "starter"
            assert company["trial_credits_granted"] == 20.0
            assert company["token_balance_usd"] == 20.0
            assert company["token_balance"] == 0
            assert bool(user["is_active"]) is True

            auth = MagicalAuth()
            auth.user_id = user_id
            user_companies = [SimpleNamespace(company_id=company_id)]
            assert auth._has_sufficient_token_balance(session, user_companies) is True
        finally:
            session.close()
    finally:
        _cleanup_user_company(user_id=user_id, company_id=company_id, email=email)


def test_inactive_billing_user_can_login_to_reach_payment(monkeypatch):
    user_id = f"inactive-user-{uuid.uuid4()}"
    company_id = f"inactive-company-{uuid.uuid4()}"
    email = f"inactive-{uuid.uuid4()}@example.com"
    password = "StrongPass123"
    auth = MagicalAuth()

    monkeypatch.setattr(
        magical_auth_module,
        "_get_cached_pricing_config",
        lambda: TIERED_PRICING_CONFIG,
    )

    _create_user_company(
        user_id=user_id,
        company_id=company_id,
        email=email,
        is_active=False,
        password_hash=auth.hash_password(password),
    )

    try:
        result = auth.login_with_password(username=email, password=password)

        assert result["status_code"] == 200
        assert result["token"]
        assert result["payment_required"] is True
        assert result["pricing_model"] == "tiered_plan"
        assert result["company_id"] == company_id

        session = get_session()
        try:
            user = (
                session.execute(
                    text('SELECT is_active FROM "user" WHERE id = :user_id'),
                    {"user_id": user_id},
                )
                .mappings()
                .first()
            )
            assert bool(user["is_active"]) is False
        finally:
            session.close()
    finally:
        _cleanup_user_company(user_id=user_id, company_id=company_id, email=email)


def _create_user_company(
    *,
    user_id: str,
    company_id: str,
    email: str,
    is_active: bool = False,
    password_hash: str = None,
):
    session = get_session()
    try:
        _ensure_auth_query_schema(session)
        session.execute(
            text(
                'INSERT INTO "user" '
                "(id, email, username, password_hash, first_name, last_name, admin, "
                "mfa_token, mfa_enabled, is_active) "
                "VALUES (:id, :email, :username, :password_hash, 'Trial', 'User', "
                "0, '', 0, :is_active)"
            ),
            {
                "id": user_id,
                "email": email,
                "username": email,
                "password_hash": password_hash,
                "is_active": is_active,
            },
        )
        session.execute(
            text(
                'INSERT INTO "Company" '
                "(id, name, encryption_key, token_balance, token_balance_usd, "
                "tokens_used_total, auto_topup_enabled, status) "
                "VALUES (:id, :name, :encryption_key, 0, 0.0, 0, 0, 1)"
            ),
            {
                "id": company_id,
                "name": f"Trial {company_id}",
                "encryption_key": Fernet.generate_key().decode(),
            },
        )
        session.execute(
            text(
                'INSERT INTO "UserCompany" (id, user_id, company_id, role_id) '
                "VALUES (:id, :user_id, :company_id, 2)"
            ),
            {
                "id": f"user-company-{uuid.uuid4()}",
                "user_id": user_id,
                "company_id": company_id,
            },
        )
        session.commit()
    finally:
        session.close()


def _cleanup_user_company(*, user_id: str, company_id: str, email: str):
    session = get_session()
    try:
        domain = email.split("@", 1)[1].lower()
        session.execute(
            text(
                'DELETE FROM "trial_domain" '
                "WHERE user_id = :user_id OR domain = :domain"
            ),
            {"user_id": user_id, "domain": domain},
        )
        session.execute(
            text(
                'DELETE FROM "UserCompany" '
                "WHERE user_id = :user_id OR company_id = :company_id"
            ),
            {"user_id": user_id, "company_id": company_id},
        )
        session.execute(
            text('DELETE FROM "Company" WHERE id = :company_id'),
            {"company_id": company_id},
        )
        session.execute(
            text('DELETE FROM "user" WHERE id = :user_id'),
            {"user_id": user_id},
        )
        session.commit()
    finally:
        session.close()


def _ensure_auth_query_schema(session):
    """Keep this unit test resilient against older local SQLite databases."""
    user_columns = _get_sqlite_columns(session, "user")
    if user_columns and "status_mode" not in user_columns:
        session.execute(
            text("ALTER TABLE user ADD COLUMN status_mode VARCHAR(20) DEFAULT 'online'")
        )
        session.commit()

    user_company_columns = _get_sqlite_columns(session, "UserCompany")
    if user_company_columns and "sort_order" not in user_company_columns:
        session.execute(text('ALTER TABLE "UserCompany" ADD COLUMN sort_order INTEGER'))
        session.commit()


def _get_sqlite_columns(session, table_name: str) -> set[str]:
    return {
        row[1]
        for row in session.execute(
            text(f'PRAGMA table_info("{table_name}")')
        ).fetchall()
    }
