from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ApiClient import verify_api_key
from MagicalAuth import MagicalAuth
from Marketplace import (
    EntitlementService,
    MarketplaceCatalogService,
    company_marketplace_credit_balance,
    env_flag,
    marketplace_enabled,
    slugify,
)

app = APIRouter()


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
        "stripe_enabled": env_flag("MARKETPLACE_STRIPE_ENABLED", "false"),
        "credits_enabled": env_flag("MARKETPLACE_CREDITS_ENABLED", "false"),
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
    company_id: Optional[str] = Query(None),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    auth = MagicalAuth(token=authorization)
    _resolve_company_id(auth, company_id)
    if not env_flag("MARKETPLACE_STRIPE_ENABLED", "false"):
        raise HTTPException(
            status_code=503,
            detail="Marketplace Stripe checkout is not enabled on this server.",
        )
    raise HTTPException(
        status_code=501,
        detail="Marketplace checkout storage is ready, but checkout creation has not been connected yet.",
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
    _resolve_company_id(auth, company_id)
    if not env_flag("MARKETPLACE_CREDITS_ENABLED", "false"):
        raise HTTPException(
            status_code=503,
            detail="Marketplace credit activation is not enabled on this server.",
        )
    raise HTTPException(
        status_code=501,
        detail="Marketplace credit ledger is ready, but credit activation has not been connected yet.",
    )
