import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from DB import CompanyAppEntitlement, get_db_session
from ExtensionsHub import ExtensionsHub
from Globals import getenv

logger = logging.getLogger(__name__)


ACTIVE_ENTITLEMENT_STATUSES = {
    "active",
    "included",
    "trialing",
    "manually_granted",
    "credit_granted",
}


def slugify(value: Optional[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "agixt"


def env_flag(name: str, default: str = "false") -> bool:
    return str(getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def marketplace_enabled() -> bool:
    return env_flag("MARKETPLACE_ENABLED", "true")


def stripe_configured() -> bool:
    api_key = getenv("STRIPE_API_KEY") or getenv("STRIPE_SECRET_KEY")
    return bool(api_key and str(api_key).strip().lower() not in {"", "none", "false"})


def marketplace_stripe_enabled() -> bool:
    return env_flag(
        "MARKETPLACE_STRIPE_ENABLED", "true" if stripe_configured() else "false"
    )


def marketplace_credits_enabled() -> bool:
    return env_flag("MARKETPLACE_CREDITS_ENABLED", "false")


def entitlement_enforcement_enabled() -> bool:
    return env_flag("MARKETPLACE_ENFORCE_ENTITLEMENTS", "false")


def _safe_price(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_price(config: Dict[str, Any]) -> Optional[float]:
    candidates: List[float] = []
    for key in ("price", "price_per_unit"):
        price = _safe_price(config.get(key))
        if price is not None:
            candidates.append(price)

    for tier in config.get("tiers") or []:
        if not isinstance(tier, dict):
            continue
        for key in ("price", "price_per_unit"):
            price = _safe_price(tier.get(key))
            if price is not None:
                candidates.append(price)

    if not candidates:
        return None
    return min(candidates)


def _price_summary(config: Dict[str, Any]) -> Dict[str, Any]:
    pricing_model = config.get("pricing_model") or "per_token"
    currency = config.get("currency") or "USD"
    price = _first_price(config)
    if pricing_model == "per_bed":
        return {
            "amount": price,
            "currency": currency,
            "interval": config.get("billing_period") or "monthly",
            "unit": config.get("unit_name") or "bed",
            "label": f"${price:g}/bed/mo" if price is not None else "Custom",
        }
    if price is None:
        return {
            "amount": None,
            "currency": currency,
            "interval": config.get("billing_period") or "monthly",
            "unit": None,
            "label": "Custom",
        }
    return {
        "amount": price,
        "currency": currency,
        "interval": config.get("billing_period") or "monthly",
        "unit": None,
        "label": f"From ${price:g}/mo",
    }


def _desktop_extension_ids(hub_path: str) -> List[str]:
    desktop_root = os.path.join(hub_path, "desktop")
    if not os.path.isdir(desktop_root):
        return []
    extension_ids: List[str] = []
    for entry in sorted(os.listdir(desktop_root)):
        path = os.path.join(desktop_root, entry)
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "manifest.json")):
            extension_ids.append(entry)
    return extension_ids


def _load_pricing_files() -> List[Dict[str, Any]]:
    configs: List[Dict[str, Any]] = []
    for path in ExtensionsHub().get_extension_search_paths():
        pricing_path = os.path.join(path, "pricing.json")
        if not os.path.exists(pricing_path):
            continue
        try:
            with open(pricing_path, "r", encoding="utf-8") as pricing_file:
                config = json.load(pricing_file)
            if not isinstance(config, dict):
                continue
            configs.append(
                {
                    "config": config,
                    "hub_path": path,
                    "pricing_path": pricing_path,
                }
            )
        except json.JSONDecodeError as exc:
            logger.warning("Invalid pricing.json at %s: %s", pricing_path, exc)
        except Exception as exc:
            logger.warning("Failed to read pricing.json at %s: %s", pricing_path, exc)
    return configs


def current_site_slug() -> str:
    pricing_config = ExtensionsHub().get_pricing_config() or {}
    return slugify(
        getenv("SITE_SLUG")
        or getenv("APP_SLUG")
        or pricing_config.get("site_slug")
        or pricing_config.get("app_slug")
        or getenv("APP_NAME")
        or pricing_config.get("app_name")
        or "agixt"
    )


def current_base_app_slug() -> str:
    pricing_config = ExtensionsHub().get_pricing_config() or {}
    return slugify(
        pricing_config.get("app_slug")
        or getenv("APP_SLUG")
        or pricing_config.get("app_name")
        or getenv("APP_NAME")
        or "agixt"
    )


class MarketplaceCatalogService:
    def __init__(self):
        self.site_slug = current_site_slug()
        self.base_app_slug = current_base_app_slug()

    def load_catalog(self, include_unlisted: bool = False) -> List[Dict[str, Any]]:
        if not marketplace_enabled():
            return []

        apps_by_slug: Dict[str, Dict[str, Any]] = {}
        for item in _load_pricing_files():
            config = item["config"]
            hub_path = item["hub_path"]
            app_name = config.get("app_name") or "AGiXT"
            app_slug = slugify(config.get("app_slug") or app_name)
            marketplace = config.get("marketplace") or {}
            if not isinstance(marketplace, dict):
                marketplace = {}

            listed = bool(marketplace.get("listed", True))
            if not listed and not include_unlisted:
                continue

            included_on_sites = marketplace.get("included_on_sites")
            if not isinstance(included_on_sites, list):
                included_on_sites = [slugify(config.get("site_slug") or app_slug)]

            base_on_sites = marketplace.get("base_on_sites")
            if not isinstance(base_on_sites, list):
                base_on_sites = [slugify(config.get("site_slug") or app_slug)]

            trial_policy = marketplace.get("trial_policy")
            if not isinstance(trial_policy, dict):
                trial = config.get("trial") or {}
                trial_policy = {
                    "enabled": bool(trial.get("enabled", False)),
                    "mode": "base_signup_only",
                    "allowed_sites": base_on_sites,
                }

            tiers = config.get("tiers") if isinstance(config.get("tiers"), list) else []
            addons = (
                config.get("addons") if isinstance(config.get("addons"), dict) else {}
            )
            desktop_ids = marketplace.get("desktop_extension_ids")
            if not isinstance(desktop_ids, list):
                desktop_ids = _desktop_extension_ids(hub_path)

            purchase_mode = marketplace.get("purchase_mode") or "subscription"
            is_base_app = app_slug == self.base_app_slug
            included_with_current_site = self.site_slug in {
                slugify(site) for site in included_on_sites
            }
            can_subscribe = (
                marketplace_stripe_enabled()
                and purchase_mode == "subscription"
                and not is_base_app
                and not included_with_current_site
            )
            can_use_credits = (
                marketplace_credits_enabled()
                and purchase_mode in {"subscription", "credits", "credit_grant"}
                and not is_base_app
                and not included_with_current_site
            )

            app = {
                "app_slug": app_slug,
                "app_name": app_name,
                "display_name": marketplace.get("display_name") or app_name,
                "publisher": config.get("publisher")
                or marketplace.get("publisher")
                or app_name,
                "site_slug": slugify(config.get("site_slug") or app_slug),
                "summary": marketplace.get("summary")
                or config.get("tagline")
                or config.get("description")
                or "",
                "description": config.get("description")
                or marketplace.get("description")
                or "",
                "category": marketplace.get("category") or "Apps",
                "pricing_model": config.get("pricing_model") or "per_token",
                "price_summary": _price_summary(config),
                "currency": config.get("currency") or "USD",
                "min_units": config.get("min_units"),
                "unit_name": config.get("unit_name"),
                "contracts": config.get("contracts") or {},
                "listed": listed,
                "purchase_mode": purchase_mode,
                "base_on_sites": [slugify(site) for site in base_on_sites],
                "included_on_sites": [slugify(site) for site in included_on_sites],
                "included_with_current_site": included_with_current_site,
                "is_base_app": is_base_app,
                "trial_policy": trial_policy,
                "tiers": tiers,
                "addons": addons,
                "included_extensions": marketplace.get("included_extensions") or [],
                "desktop_extension_ids": desktop_ids,
                "required_scopes": marketplace.get("required_scopes") or [],
                "can_purchase": can_subscribe,
                "can_use_credits": can_use_credits,
            }

            # First match wins, mirroring desktop extension collision behavior.
            apps_by_slug.setdefault(app_slug, app)

        return sorted(
            apps_by_slug.values(), key=lambda app: app["display_name"].lower()
        )

    def get_app(
        self, app_slug: str, include_unlisted: bool = False
    ) -> Optional[Dict[str, Any]]:
        normalized = slugify(app_slug)
        for app in self.load_catalog(include_unlisted=include_unlisted):
            if app.get("app_slug") == normalized:
                return app
        return None


class EntitlementService:
    def __init__(self):
        self.catalog = MarketplaceCatalogService()

    def get_company_entitlements(self, company_id: str) -> List[Dict[str, Any]]:
        entitlements: Dict[str, Dict[str, Any]] = {}
        if not company_id:
            return []

        for app in self.catalog.load_catalog(include_unlisted=True):
            if app.get("is_base_app") or app.get("included_with_current_site"):
                entitlements[app["app_slug"]] = {
                    "app_slug": app["app_slug"],
                    "company_id": company_id,
                    "source_site_slug": self.catalog.site_slug,
                    "status": "included",
                    "tier_id": None,
                    "quantity": 1,
                    "current_period_start": None,
                    "current_period_end": None,
                    "trial_start": None,
                    "trial_end": None,
                    "purchased_with_credits": False,
                    "credit_amount_usd": None,
                    "is_active": True,
                    "is_virtual": True,
                }

        try:
            with get_db_session() as session:
                rows = (
                    session.query(CompanyAppEntitlement)
                    .filter(CompanyAppEntitlement.company_id == company_id)
                    .all()
                )
                for row in rows:
                    entitlements[row.app_slug] = self._serialize_entitlement(row)
        except Exception as exc:
            logger.warning(
                "Failed to load marketplace entitlements for company %s: %s",
                company_id,
                exc,
            )

        return sorted(entitlements.values(), key=lambda item: item["app_slug"])

    def has_entitlement(self, company_id: str, app_slug: str) -> bool:
        normalized = slugify(app_slug)
        for entitlement in self.get_company_entitlements(company_id):
            if entitlement.get("app_slug") != normalized:
                continue
            return entitlement.get("status") in ACTIVE_ENTITLEMENT_STATUSES
        return False

    def apps_with_entitlements(
        self, company_id: Optional[str], include_unlisted: bool = False
    ) -> List[Dict[str, Any]]:
        apps = self.catalog.load_catalog(include_unlisted=include_unlisted)
        entitlements = {
            item["app_slug"]: item
            for item in self.get_company_entitlements(company_id or "")
        }
        for app in apps:
            entitlement = entitlements.get(app["app_slug"])
            app["entitlement"] = entitlement
            app["entitlement_status"] = (
                entitlement.get("status") if entitlement else "available"
            )
            app["is_entitled"] = bool(
                entitlement and entitlement.get("status") in ACTIVE_ENTITLEMENT_STATUSES
            )
        return apps

    def _serialize_entitlement(
        self, entitlement: CompanyAppEntitlement
    ) -> Dict[str, Any]:
        def dt(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if value else None

        return {
            "id": str(entitlement.id),
            "company_id": str(entitlement.company_id),
            "app_slug": entitlement.app_slug,
            "source_site_slug": entitlement.source_site_slug,
            "status": entitlement.status,
            "tier_id": entitlement.tier_id,
            "quantity": entitlement.quantity,
            "stripe_customer_id": entitlement.stripe_customer_id,
            "stripe_subscription_id": entitlement.stripe_subscription_id,
            "stripe_subscription_item_id": entitlement.stripe_subscription_item_id,
            "stripe_price_id": entitlement.stripe_price_id,
            "current_period_start": dt(entitlement.current_period_start),
            "current_period_end": dt(entitlement.current_period_end),
            "trial_start": dt(entitlement.trial_start),
            "trial_end": dt(entitlement.trial_end),
            "purchased_with_credits": bool(entitlement.purchased_with_credits),
            "credit_amount_usd": entitlement.credit_amount_usd,
            "is_active": entitlement.status in ACTIVE_ENTITLEMENT_STATUSES,
            "is_virtual": False,
        }


def company_has_marketplace_entitlement(company_id: str, app_slug: str) -> bool:
    if not entitlement_enforcement_enabled():
        return True
    return EntitlementService().has_entitlement(
        company_id=company_id, app_slug=app_slug
    )


def company_marketplace_credit_balance(company_id: str) -> float:
    if not company_id:
        return 0.0
    try:
        from DB import CompanyCreditLedger

        with get_db_session() as session:
            row = (
                session.query(CompanyCreditLedger)
                .filter(CompanyCreditLedger.company_id == company_id)
                .order_by(CompanyCreditLedger.created_at.desc())
                .first()
            )
            return float(row.balance_after_usd) if row else 0.0
    except Exception:
        return 0.0
