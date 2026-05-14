import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
AGIXT_SRC = os.path.join(PROJECT_ROOT, "agixt")
if AGIXT_SRC not in sys.path:
    sys.path.insert(0, AGIXT_SRC)

from ExtensionsHub import ExtensionsHub
from Marketplace import MarketplaceCatalogService, slugify


def test_slugify_produces_stable_app_ids():
    assert slugify("XT Systems") == "xt-systems"
    assert slugify(" NurseXT ") == "nursext"
    assert slugify("") == "agixt"


def test_marketplace_catalog_loads_all_pricing_files(monkeypatch, tmp_path):
    xt_hub = tmp_path / "xtsystems_extensions"
    nurse_hub = tmp_path / "nursext"
    xt_hub.mkdir()
    nurse_hub.mkdir()
    (xt_hub / "pricing.json").write_text(
        json.dumps(
            {
                "app_name": "XT Systems",
                "app_slug": "xtsystems",
                "site_slug": "xtsystems",
                "pricing_model": "tiered_plan",
                "tagline": "Machine management",
                "tiers": [{"id": "starter", "name": "Starter", "price": 20}],
                "marketplace": {
                    "listed": True,
                    "category": "IT Management",
                    "included_on_sites": ["xtsystems"],
                    "desktop_extension_ids": ["machines"],
                },
            }
        ),
        encoding="utf-8",
    )
    (nurse_hub / "pricing.json").write_text(
        json.dumps(
            {
                "app_name": "NurseXT",
                "app_slug": "nursext",
                "site_slug": "nursext",
                "pricing_model": "per_bed",
                "price_per_unit": 10,
                "unit_name": "bed",
                "marketplace": {
                    "listed": True,
                    "category": "Healthcare",
                    "included_on_sites": ["nursext"],
                    "desktop_extension_ids": ["residents"],
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_NAME", "NurseXT")
    monkeypatch.setenv("SITE_SLUG", "nursext")
    monkeypatch.setenv("MARKETPLACE_ENABLED", "true")
    monkeypatch.setattr(
        ExtensionsHub,
        "get_extension_search_paths",
        lambda self: [str(xt_hub), str(nurse_hub)],
    )
    monkeypatch.setattr(
        ExtensionsHub,
        "get_pricing_config",
        lambda self: {
            "app_name": "NurseXT",
            "app_slug": "nursext",
            "site_slug": "nursext",
        },
    )

    apps = MarketplaceCatalogService().load_catalog()
    by_slug = {app["app_slug"]: app for app in apps}

    assert set(by_slug) == {"nursext", "xtsystems"}
    assert by_slug["nursext"]["is_base_app"] is True
    assert by_slug["nursext"]["included_with_current_site"] is True
    assert by_slug["xtsystems"]["included_with_current_site"] is False
    assert by_slug["xtsystems"]["price_summary"]["label"] == "From $20/mo"
    assert by_slug["nursext"]["price_summary"]["label"] == "$10/bed/mo"
