from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from ApiClient import verify_api_key
from DB import User, get_session
from MagicalAuth import MagicalAuth
from Marketplace import (
    EntitlementService,
    MarketplaceCatalogService,
    company_marketplace_credit_balance,
    marketplace_credits_enabled,
    marketplace_enabled,
    marketplace_stripe_enabled,
    slugify,
)
from payments.stripe_service import StripePaymentService

app = APIRouter()


class MarketplaceCheckoutRequest(BaseModel):
    tier_id: Optional[str] = None
    quantity: Optional[int] = None
    billing_interval: str = "month"


def _resolve_company_id(auth: MagicalAuth, company_id: Optional[str]) -> Optional[str]:
    auth.validate_user()
    user_companies = auth.get_user_companies()
    if company_id:
        if company_id not in user_companies and not auth.is_super_admin():
            raise HTTPException(
                status_code=403, detail="You do not have access to this company"
            )
        return company_id
    if user_companies:
        return user_companies[0]
    return None


def _require_marketplace_admin(auth: MagicalAuth, company_id: str) -> None:
    auth.require_any_scope(
        ["billing:write", "billing:admin", "company:billing", "company:write"],
        company_id,
    )


def _current_user_email(auth: MagicalAuth) -> Optional[str]:
    session = get_session()
    try:
        user = session.query(User).filter(User.id == auth.user_id).first()
        return user.email if user else None
    finally:
        session.close()


@app.get(
    "/v1/marketplace/apps",
    tags=["Marketplace"],
    dependencies=[Depends(verify_api_key)],
)
async def list_marketplace_apps(
    company_id: Optional[str] = Query(None),
    include_unlisted: bool = Query(False),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    auth = MagicalAuth(token=authorization)
    resolved_company_id = _resolve_company_id(auth, company_id)

    catalog = MarketplaceCatalogService()
    entitlement_service = EntitlementService()
    apps = entitlement_service.apps_with_entitlements(
        company_id=resolved_company_id,
        include_unlisted=include_unlisted and auth.is_super_admin(),
    )

    return {
        "marketplace_enabled": marketplace_enabled(),
        "site_slug": catalog.site_slug,
        "base_app_slug": catalog.base_app_slug,
        "company_id": resolved_company_id,
        "credit_balance_usd": company_marketplace_credit_balance(
            resolved_company_id or ""
        ),
        "stripe_enabled": marketplace_stripe_enabled(),
        "credits_enabled": marketplace_credits_enabled(),
        "apps": apps,
    }


@app.get(
    "/v1/marketplace/apps/{app_slug}",
    tags=["Marketplace"],
    dependencies=[Depends(verify_api_key)],
)
async def get_marketplace_app(
    app_slug: str,
    company_id: Optional[str] = Query(None),
    include_unlisted: bool = Query(False),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    auth = MagicalAuth(token=authorization)
    resolved_company_id = _resolve_company_id(auth, company_id)

    normalized_slug = slugify(app_slug)
    entitlement_service = EntitlementService()
    apps = entitlement_service.apps_with_entitlements(
        company_id=resolved_company_id,
        include_unlisted=include_unlisted and auth.is_super_admin(),
    )
    for marketplace_app in apps:
        if marketplace_app.get("app_slug") == normalized_slug:
            return marketplace_app
    raise HTTPException(status_code=404, detail="Marketplace app not found")


@app.get(
    "/v1/marketplace/entitlements",
    tags=["Marketplace"],
    dependencies=[Depends(verify_api_key)],
)
async def list_marketplace_entitlements(
    company_id: Optional[str] = Query(None),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    auth = MagicalAuth(token=authorization)
    resolved_company_id = _resolve_company_id(auth, company_id)
    if not resolved_company_id:
        return {"company_id": None, "entitlements": []}

    entitlements = EntitlementService().get_company_entitlements(resolved_company_id)
    return {
        "company_id": resolved_company_id,
        "credit_balance_usd": company_marketplace_credit_balance(resolved_company_id),
        "entitlements": entitlements,
    }


@app.post(
    "/v1/marketplace/apps/{app_slug}/checkout",
    tags=["Marketplace"],
    dependencies=[Depends(verify_api_key)],
)
async def create_marketplace_checkout(
    app_slug: str,
    request: Optional[MarketplaceCheckoutRequest] = None,
    company_id: Optional[str] = Query(None),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    auth = MagicalAuth(token=authorization)
    resolved_company_id = _resolve_company_id(auth, company_id)
    if not resolved_company_id:
        raise HTTPException(status_code=400, detail="Company context is required")
    _require_marketplace_admin(auth, resolved_company_id)
    if not marketplace_stripe_enabled():
        raise HTTPException(
            status_code=503,
            detail="Marketplace Stripe checkout is not enabled on this server.",
        )

    checkout_request = request or MarketplaceCheckoutRequest()
    stripe_service = StripePaymentService()
    try:
        return await stripe_service.create_marketplace_app_checkout(
            company_id=resolved_company_id,
            app_slug=app_slug,
            user_email=_current_user_email(auth),
            tier_id=checkout_request.tier_id,
            quantity=checkout_request.quantity,
            billing_interval=checkout_request.billing_interval,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to create marketplace checkout: {exc}"
        )


@app.post(
    "/v1/marketplace/apps/{app_slug}/activate-with-credits",
    tags=["Marketplace"],
    dependencies=[Depends(verify_api_key)],
)
async def activate_marketplace_app_with_credits(
    app_slug: str,
    company_id: Optional[str] = Query(None),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    auth = MagicalAuth(token=authorization)
    resolved_company_id = _resolve_company_id(auth, company_id)
    if not resolved_company_id:
        raise HTTPException(status_code=400, detail="Company context is required")
    _require_marketplace_admin(auth, resolved_company_id)
    if not marketplace_credits_enabled():
        raise HTTPException(
            status_code=503,
            detail="Marketplace credit activation is not enabled on this server.",
        )
    raise HTTPException(
        status_code=501,
        detail="Marketplace credit ledger is ready, but credit activation has not been connected yet.",
    )
