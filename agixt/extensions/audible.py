import asyncio
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from ApiClient import Agent as ApiAgent, get_api_client, verify_api_key
from Extensions import Extensions
from MagicalAuth import MagicalAuth

try:
    import audible as audible_api
    from audible import Authenticator
    from audible.localization import Locale
    from audible.login import build_oauth_url, create_code_verifier
    from audible.register import register as register_device

    AUDIBLE_AVAILABLE = True
except ImportError:
    AUDIBLE_AVAILABLE = False
    audible_api = None
    Authenticator = None  # type: ignore
    Locale = None  # type: ignore


# ---------------------------------------------------------------------
# Helpers shared by the LLM-facing commands and the desktop UI router.
# ---------------------------------------------------------------------

_ASIN_RE = re.compile(r"^[A-Z0-9]{6,16}$")
_AUDIO_CACHE_ROOT = Path(os.path.expanduser("~/.agixt/audiobooks"))
_AUTH_FILE = os.path.join(os.path.expanduser("~"), ".agixt", "audible_auth.json")
_CLIENT_CACHE: Dict[str, Any] = {}  # cache_key -> audible_api.Client
_DOWNLOAD_TASKS: Dict[str, asyncio.Task] = {}

# In-flight external-browser logins, keyed by an opaque pending_id we
# hand back to the desktop client. Each entry holds the PKCE code
# verifier + serial we generated for this login attempt — the user pastes
# the redirect URL back, we extract the auth code, and exchange it via
# `audible.register` to mint long-lived tokens. Entries older than one
# hour are garbage-collected on each new start request.
_PENDING_LOGINS: Dict[str, Dict[str, Any]] = {}
_PENDING_TTL_SECONDS = 60 * 60


def _validate_asin(asin: str) -> str:
    asin = (asin or "").strip().upper()
    if not _ASIN_RE.match(asin):
        raise HTTPException(status_code=400, detail="invalid asin")
    return asin


def _require_audible_pkg() -> None:
    if not AUDIBLE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="The 'audible' python package is not installed on the server.",
        )


def _audible_client_for_settings(cache_key: str):
    """Return a logged-in `audible_api.Client` from the cached auth file.

    Auth source of truth is `~/.agixt/audible_auth.json`, populated by
    the desktop Audible page's Connect flow (`/v1/audible/auth/*`).
    No username/password paths exist on the server side anymore —
    Amazon CAPTCHA + 2FA make that brittle. If the file is missing or
    invalid we return a structured 401 so the desktop UI pops the
    Connect screen.
    """
    _require_audible_pkg()
    cached = _CLIENT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if os.path.exists(_AUTH_FILE):
        try:
            authenticator = Authenticator.from_file(_AUTH_FILE)
            client = audible_api.Client(auth=authenticator)
            _CLIENT_CACHE[cache_key] = client
            return client
        except Exception as exc:
            logging.warning("audible: cached auth invalid (%s); needs re-login", exc)
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "audible_auth_required",
                    "message": (
                        "Your Audible session has expired. Open the Audible "
                        "page in the AGiXT desktop sidebar and click Connect "
                        "to sign in again."
                    ),
                },
            )
    raise HTTPException(
        status_code=401,
        detail={
            "code": "audible_auth_required",
            "message": (
                "Not connected to Audible. Open the Audible page in the AGiXT "
                "desktop sidebar and click Connect to sign in with your "
                "Amazon account."
            ),
        },
    )


def _gc_pending_logins() -> None:
    cutoff = time.time() - _PENDING_TTL_SECONDS
    for k, v in list(_PENDING_LOGINS.items()):
        if v.get("created_at", 0) < cutoff:
            _PENDING_LOGINS.pop(k, None)


def _make_locale(locale_code: str):
    """Resolve a country-code string to an `audible.Locale`.

    The audible package keys these by country code (us/uk/de/fr/au/ca/
    it/in/es/jp/br). We normalise unknown values to "us" since that's
    by far the most common store.
    """
    _require_audible_pkg()
    code = (locale_code or "us").strip().lower() or "us"
    try:
        return Locale(code)
    except Exception:
        return Locale("us")


def _start_audible_login(
    locale_code: str, with_username: bool = False
) -> Dict[str, Any]:
    """Generate the Amazon OAuth URL the user needs to visit in a browser.

    Returns `pending_id` so the desktop client can call `/auth/complete`
    later with the redirect URL.
    """
    _gc_pending_logins()
    locale = _make_locale(locale_code)
    code_verifier = create_code_verifier()
    oauth_url, serial = build_oauth_url(
        country_code=locale.country_code,
        domain=locale.domain,
        market_place_id=locale.market_place_id,
        code_verifier=code_verifier,
        with_username=with_username,
    )
    pending_id = secrets.token_urlsafe(24)
    _PENDING_LOGINS[pending_id] = {
        "locale_code": locale.country_code,
        "domain": locale.domain,
        "market_place_id": locale.market_place_id,
        "code_verifier": code_verifier,
        "serial": serial,
        "with_username": with_username,
        "created_at": time.time(),
    }
    return {"pending_id": pending_id, "login_url": oauth_url}


def _complete_audible_login(pending_id: str, redirect_url: str) -> Dict[str, Any]:
    """Exchange a redirected URL for an Audible auth file on disk."""
    _require_audible_pkg()
    pending = _PENDING_LOGINS.pop(pending_id, None)
    if pending is None:
        raise HTTPException(
            status_code=400,
            detail="Login session expired or not found. Click Connect again.",
        )
    if not redirect_url or "openid.oa2.authorization_code=" not in redirect_url:
        raise HTTPException(
            status_code=400,
            detail=(
                "That URL doesn't include the Amazon authorization code. After "
                "logging in, copy the FULL URL from the 'page not found' screen "
                "(it should contain openid.oa2.authorization_code=...) and try "
                "again."
            ),
        )
    try:
        parsed = httpx.URL(redirect_url)
        query = parse_qs(parsed.query.decode())
        authorization_code = query["openid.oa2.authorization_code"][0]
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not parse redirect URL: {exc}"
        )

    try:
        register_response = register_device(
            authorization_code=authorization_code,
            code_verifier=pending["code_verifier"],
            domain=pending["domain"],
            serial=pending["serial"],
            with_username=pending["with_username"],
        )
    except Exception as exc:
        logging.error("audible: register exchange failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Amazon rejected the authorization code: {exc}",
        )

    auth = Authenticator()
    auth.locale = _make_locale(pending["locale_code"])
    # `_update_attrs` is the same method the package uses internally
    # after registration — it just setattrs the device tokens onto the
    # authenticator so to_file() can serialize them.
    auth._update_attrs(with_username=pending["with_username"], **register_response)
    os.makedirs(os.path.dirname(_AUTH_FILE), exist_ok=True)
    auth.to_file(_AUTH_FILE)

    # Wipe any cached client objects that were built against the old
    # (or missing) auth file so the next API call rebuilds.
    _CLIENT_CACHE.clear()

    return _audible_auth_status()


def _audible_browser_dir() -> Path:
    """Persistent Playwright profile used by `/auth/auto`.

    First time the user runs `/auth/auto` they sign into Amazon in the
    visible window; cookies are stored in this dir. Subsequent runs
    bounce straight from the OAuth URL to the auth-code redirect with
    no human input.

    We don't reach into Chrome/Edge/Brave's actual profile dirs — those
    are typically locked while the browser is running, and silently
    cloning a user's primary cookie jar feels invasive. If the user
    wants single-click reuse of their default-browser session, install
    `browser_cookie3` and we'll seed this profile from it on first run.
    """
    p = Path(os.path.expanduser("~/.agixt/audible_browser"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _amazon_cookies_from_default_browser() -> List[Dict[str, Any]]:
    """Pull `amazon.*` and `audible.*` cookies from the user's default
    browser, formatted for Playwright's `context.add_cookies()`.

    Requires the optional `browser_cookie3` dependency. Returns an empty
    list if it isn't installed or if no matching cookies are found —
    callers should fall back to the visible-login flow in that case.
    """
    try:
        import browser_cookie3  # type: ignore
    except ImportError:
        return []
    cookies: List[Dict[str, Any]] = []
    for domain_filter in ("amazon.com", "amazon.co.uk", "audible.com", "audible.co.uk"):
        try:
            jar = browser_cookie3.load(domain_name=domain_filter)
        except Exception as exc:
            logging.debug("audible: browser_cookie3 %s: %s", domain_filter, exc)
            continue
        for c in jar:
            if not c.domain:
                continue
            d = c.domain.lower()
            if "amazon" not in d and "audible" not in d:
                continue
            cookies.append(
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path or "/",
                    "secure": bool(c.secure),
                    "httpOnly": bool(getattr(c, "_rest", {}).get("HttpOnly", False)),
                    "expires": (int(c.expires) if c.expires and c.expires > 0 else -1),
                    "sameSite": "Lax",
                }
            )
    return cookies


async def _auth_auto_playwright(
    locale_code: str, headless: bool, timeout_seconds: int
) -> Dict[str, Any]:
    """Open the Audible OAuth URL in a Playwright-driven Chromium and
    capture the redirect.

    UX note: when `headless` is False (the default) the user sees a real
    browser window. They sign into Amazon there if not already signed in,
    and Playwright captures the post-login redirect URL automatically —
    no copy/paste step. When `headless` is True we need an existing
    Amazon session in the profile, otherwise the login form blocks and
    we time out.
    """
    _require_audible_pkg()
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Playwright is not installed on this server. Use the manual "
                "POST /v1/audible/auth/url + /v1/audible/auth/complete flow "
                "instead."
            ),
        )

    locale = _make_locale(locale_code)
    code_verifier = create_code_verifier()
    oauth_url, serial = build_oauth_url(
        country_code=locale.country_code,
        domain=locale.domain,
        market_place_id=locale.market_place_id,
        code_verifier=code_verifier,
        with_username=False,
    )

    user_data_dir = _audible_browser_dir()
    captured_url: Dict[str, str] = {}
    timeout_ms = max(30, min(int(timeout_seconds), 1800)) * 1000

    # If the user has `browser_cookie3` installed, seed the Playwright
    # context with their default-browser amazon cookies on first run so
    # the OAuth URL bounces straight to the redirect with no human input.
    seed_cookies = _amazon_cookies_from_default_browser()
    seeded_marker = user_data_dir / ".cookies_seeded"

    try:
        async with async_playwright() as pw:
            try:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Could not launch the embedded Chromium. Install the "
                        "Playwright browsers with "
                        "`/home/josh/repos/xtsys/.venv/bin/playwright install chromium`. "
                        f"({exc})"
                    ),
                )

            if seed_cookies and not seeded_marker.exists():
                try:
                    await context.add_cookies(seed_cookies)
                    seeded_marker.write_text(
                        f"seeded {len(seed_cookies)} cookies at "
                        f"{datetime.utcnow().isoformat()}Z\n",
                        encoding="utf-8",
                    )
                    logging.info(
                        "audible: seeded %d default-browser cookies into "
                        "Playwright profile",
                        len(seed_cookies),
                    )
                except Exception as exc:
                    logging.warning("audible: cookie seeding failed: %s", exc)

            page = await context.new_page()

            async def _on_request(request):
                # Audible's post-login redirect lands at a `/ap/maplanding`
                # path that includes `openid.oa2.authorization_code=...`
                # in the query. We capture the first such URL we see and
                # stop the navigation by closing the page.
                if "openid.oa2.authorization_code=" in request.url and not captured_url:
                    captured_url["url"] = request.url

            page.on("request", _on_request)

            try:
                await page.goto(oauth_url, wait_until="commit", timeout=15000)
            except Exception as exc:
                logging.warning("audible: oauth navigation issue: %s", exc)

            # Spin the event loop until either we get the code or the
            # user closes the page or we time out.
            deadline = time.time() + (timeout_ms / 1000.0)
            while time.time() < deadline:
                if captured_url:
                    break
                if page.is_closed():
                    break
                cur = page.url or ""
                if "openid.oa2.authorization_code=" in cur:
                    captured_url["url"] = cur
                    break
                await asyncio.sleep(0.5)

            try:
                await context.close()
            except Exception:
                pass

        if not captured_url:
            raise HTTPException(
                status_code=408,
                detail=(
                    "Timed out waiting for Amazon login. Try again with "
                    "`headless=false` so you can complete the sign-in form, "
                    "or use the paste-the-redirect-URL fallback."
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logging.error("audible: playwright auth failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Playwright login failed: {exc}")

    # We now have the redirect URL; finish the flow as if the user had
    # pasted it manually. This re-uses the same exchange code path so
    # behaviour stays consistent across the two entry points.
    pending_id = secrets.token_urlsafe(16)
    _PENDING_LOGINS[pending_id] = {
        "locale_code": locale.country_code,
        "domain": locale.domain,
        "market_place_id": locale.market_place_id,
        "code_verifier": code_verifier,
        "serial": serial,
        "with_username": False,
        "created_at": time.time(),
    }
    return _complete_audible_login(pending_id, captured_url["url"])


def _audible_auth_status() -> Dict[str, Any]:
    if not AUDIBLE_AVAILABLE:
        return {
            "package_installed": False,
            "configured": False,
            "loadable": False,
            "auth_file": _AUTH_FILE,
            "error": "audible package not installed",
        }
    if not os.path.exists(_AUTH_FILE):
        return {
            "package_installed": True,
            "configured": False,
            "loadable": False,
            "auth_file": _AUTH_FILE,
        }
    try:
        auth = Authenticator.from_file(_AUTH_FILE)
        # `customer_info` is set after register and contains the user's
        # Amazon name/email if available.
        customer_info = getattr(auth, "customer_info", {}) or {}
        return {
            "package_installed": True,
            "configured": True,
            "loadable": True,
            "auth_file": _AUTH_FILE,
            "name": customer_info.get("name"),
            "given_name": customer_info.get("given_name"),
            "locale": getattr(getattr(auth, "locale", None), "country_code", None),
        }
    except Exception as exc:
        return {
            "package_installed": True,
            "configured": True,
            "loadable": False,
            "auth_file": _AUTH_FILE,
            "error": str(exc),
        }


def _book_brief(b: Dict[str, Any]) -> Dict[str, Any]:
    images = b.get("product_images") or {}
    series = (b.get("series") or [{}])[0] if b.get("series") else {}
    return {
        "asin": b.get("asin"),
        "title": b.get("title") or "Untitled",
        "subtitle": b.get("subtitle") or "",
        "authors": [a.get("name") for a in (b.get("authors") or []) if a.get("name")],
        "narrators": [
            n.get("name") for n in (b.get("narrators") or []) if n.get("name")
        ],
        "runtime_minutes": b.get("runtime_length_min") or 0,
        "percent_complete": b.get("percent_complete"),
        "is_finished": bool(b.get("is_finished")),
        "release_date": b.get("release_date") or "",
        "language": b.get("language") or "",
        "publisher": b.get("publisher_name") or "",
        "series_title": series.get("title") or "",
        "series_sequence": series.get("sequence") or "",
        "cover_url": images.get("500") or images.get("252") or images.get("180") or "",
    }


def _book_full(b: Dict[str, Any]) -> Dict[str, Any]:
    out = _book_brief(b)
    rating = (b.get("rating") or {}).get("overall_distribution") or {}
    categories: List[str] = []
    for ladder in b.get("category_ladders") or []:
        for cat in ladder.get("ladder") or []:
            name = cat.get("name")
            if name and name not in categories:
                categories.append(name)
    desc = b.get("publisher_summary") or ""
    desc = re.sub(r"<[^>]+>", "", desc).strip()
    out.update(
        {
            "description": desc,
            "rating_avg": rating.get("display_average_rating"),
            "rating_count": rating.get("num_ratings") or 0,
            "categories": categories,
        }
    )
    return out


def _audio_cache_paths(asin: str) -> Tuple[Path, Path]:
    base = _AUDIO_CACHE_ROOT / asin
    base.mkdir(parents=True, exist_ok=True)
    return base, base / "audio.aax"


def _find_playable_audio(asin: str) -> Optional[Path]:
    """Return a browser-playable audio file for `asin`, or None.

    Falls back to the kids-app cache directory if no AGiXT-side cache
    has been populated yet — both stores use the same `<asin>/audio.m4a`
    layout, so prior downloads are reused for free.
    """
    bases = [_AUDIO_CACHE_ROOT / asin]
    kids_cache = Path("/home/josh/repos/xtsys/kids/data/audiobooks") / asin
    if kids_cache.is_dir():
        bases.append(kids_cache)
    for base in bases:
        if not base.is_dir():
            continue
        for name in ("audio.m4a", "audio.m4b", "audio.mp3", "audio.mp4"):
            p = base / name
            if not (p.is_file() and p.stat().st_size > 0):
                continue
            err_marker = base / f"{name}.decode_error"
            ok_marker = base / f"{name}.decode_ok"
            if err_marker.is_file() and not ok_marker.is_file():
                continue
            return p
    return None


def _extract_download_url(license_response: Any) -> Optional[str]:
    if not isinstance(license_response, dict):
        return None
    cl = license_response.get("content_license") or {}
    cm = cl.get("content_metadata") or {}
    cu = cm.get("content_url") or {}
    if isinstance(cu, dict) and cu.get("offline_url"):
        return cu["offline_url"]
    for key in ("content_metadata", "content_url", "license_response"):
        v = cl.get(key)
        if isinstance(v, dict):
            for sub in ("content_url", "offline_url", "manifest_url"):
                u = v.get(sub)
                if isinstance(u, dict) and u.get("offline_url"):
                    return u["offline_url"]
                if isinstance(u, str) and u.startswith("http"):
                    return u
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


async def _download_audio(client, asin: str) -> Optional[Path]:
    """Best-effort license-request + download to the AGiXT-side cache."""
    base, aax_path = _audio_cache_paths(asin)
    license_bodies = [
        {
            "drm_type": "Adrm",
            "consumption_type": "Download",
            "quality": "High",
            "num_active_offline_licenses": 1,
        },
        {
            "quality": "High",
            "response_groups": (
                "chapter_info,content_reference,last_position_heard,pdf_url,"
                "ad_insertion,certificate"
            ),
            "consumption_type": "Download",
            "supported_media_features": {
                "codecs": ["mp4a.40.2", "mp4a.40.42", "ec+3", "ac-4"],
                "drm_types": ["Mpeg", "Adrm", "Hls", "Dash"],
            },
            "spatial": False,
            "num_active_offline_licenses": 1,
        },
    ]
    last_err = "no attempts"
    for body in license_bodies:
        try:
            license_resp = await asyncio.to_thread(
                client.post, f"1.0/content/{asin}/licenserequest", body=body
            )
        except Exception as exc:
            last_err = f"license: {exc}"
            continue
        url = _extract_download_url(license_resp)
        if not url:
            last_err = "license response had no download URL"
            continue
        try:
            async with httpx.AsyncClient(
                timeout=None,
                follow_redirects=True,
                headers={
                    "User-Agent": "Audible/3.56.2 iOS/15.0.0",
                    "Accept": "*/*",
                },
            ) as hc:
                async with hc.stream("GET", url) as r:
                    if r.status_code >= 400:
                        body_bytes = await r.aread()
                        last_err = (
                            f"download HTTP {r.status_code}: "
                            f"{body_bytes[:200].decode('utf-8', errors='replace')}"
                        )
                        continue
                    with aax_path.open("wb") as fh:
                        async for chunk in r.aiter_bytes(chunk_size=65536):
                            fh.write(chunk)
            return aax_path
        except Exception as exc:
            last_err = f"download: {exc}"
            continue
    logging.warning("audible: download failed for %s — %s", asin, last_err)
    (base / "download_error.txt").write_text(last_err, encoding="utf-8")
    return None


class audible(Extensions):
    """
    Browse and listen to your Audible audiobook library straight from
    AGiXT. Once connected, the assistant can pull up your reading
    progress, book details, chapters, and notes to ground conversations
    in what you're actually reading.

    To get started, open the **Audible** page in the AGiXT desktop
    sidebar and click **Connect**. You'll sign in with your Amazon
    account in your default browser the same way the Audible app does;
    no password is stored in AGiXT. The connection persists across
    restarts — reconnect any time from the same page if you switch
    Audible accounts or hit a stale-token error.
    """

    CATEGORY = "Productivity"

    def __init__(self, **kwargs):
        # No agent-level settings: marketplace + credentials are baked
        # into the auth file generated by the OAuth flow. Anything the
        # constructor still references is left as a no-op default to
        # avoid AttributeErrors in code paths that haven't been
        # refactored yet.
        self.AUDIBLE_LOCALE = "us"
        self.AUDIBLE_EMAIL = ""
        self.AUDIBLE_PASSWORD = ""
        self.auth = None
        self.client = None
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        # Auth file shared with the desktop UI router and the CLI helper.
        self.auth_file = _AUTH_FILE
        self.ApiClient = kwargs.get("ApiClient", None)
        self.commands = {
            "Get Audible Library": self.get_library,
            "Get Current Reading Progress": self.get_reading_progress,
            "Get Audible Book Details": self.get_book_details,
            "Get Audible Book Chapters": self.get_book_chapters,
            "Get Audible Reading Statistics": self.get_reading_statistics,
            "Search Audible Library": self.search_library,
            "Get Audible Wishlist": self.get_wishlist,
            "Get Audible Book Annotations": self.get_book_annotations,
        }

        # FastAPI router that powers the desktop "Audible" page extension.
        # The main app picks this up via Extensions.get_extension_routers()
        # and mounts it during startup, same flow github.py uses.
        self.router = APIRouter(prefix="/v1/audible", tags=["Audible"])
        self._register_routes()

    # ------------------------------------------------------------------
    # Desktop UI router — JSON endpoints consumed by
    # extensions/desktop/audible/main.js. Auth is per-request:
    # MagicalAuth(token=authorization) identifies the user, and the
    # cached Audible auth file at ~/.agixt/audible_auth.json provides
    # the audiobook account. The `agent_id` query param is used only
    # to pick a default marketplace locale when starting a fresh
    # OAuth login.
    # ------------------------------------------------------------------

    def _register_routes(self) -> None:
        router = self.router

        def _resolve_agent(authorization: Optional[str], agent_id: Optional[str], user):
            api_client = get_api_client(authorization=authorization)
            if agent_id:
                return ApiAgent(agent_id=agent_id, user=user, ApiClient=api_client)
            auth = MagicalAuth(token=authorization)
            user_email = auth.email if auth.email else user
            return ApiAgent(agent_name=None, user=user_email, ApiClient=api_client)

        def _client_for(agent) -> Any:
            cache_key = f"{agent.user_id}:{agent.agent_id}"
            return _audible_client_for_settings(cache_key)

        # ----- Authentication: external-browser OAuth flow -----------
        # Username/password login is too brittle (CAPTCHA, 2FA, MFA
        # forwarding); we drive Amazon's standard OAuth-via-browser
        # flow instead. Two-phase API:
        #   POST /auth/url       -> { pending_id, login_url }
        #   POST /auth/complete  -> { ... auth/status payload ... }
        # The user opens `login_url` in their default browser, signs
        # in, lands on Amazon's "page not found" with the auth code
        # in the address bar, and pastes that URL back to /complete.
        # `/auth/auto` automates the round trip via Playwright when a
        # browser binary is available — falls back to manual paste
        # when not.

        @router.get("/auth/status", summary="Audible auth state on this server")
        async def auth_status(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            return _audible_auth_status()

        @router.post("/auth/url", summary="Start external-browser Audible login")
        async def auth_url(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
            payload: Dict[str, Any] = Body(default_factory=dict),
        ):
            locale = (payload.get("locale") or "").strip().lower()
            if not locale:
                # Default to the agent's configured locale, fall back to "us".
                try:
                    agent = _resolve_agent(authorization, agent_id, user)
                    locale = (
                        (
                            (agent.AGENT_CONFIG or {})
                            .get("settings", {})
                            .get("AUDIBLE_LOCALE")
                            or "us"
                        )
                        .strip()
                        .lower()
                    )
                except Exception:
                    locale = "us"
            with_username = bool(payload.get("with_username", False))
            return _start_audible_login(locale, with_username=with_username)

        @router.post("/auth/complete", summary="Finish external-browser Audible login")
        async def auth_complete(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            payload: Dict[str, Any] = Body(...),
        ):
            pending_id = (payload.get("pending_id") or "").strip()
            redirect_url = (payload.get("redirect_url") or "").strip()
            if not pending_id:
                raise HTTPException(status_code=400, detail="pending_id is required")
            if not redirect_url:
                raise HTTPException(status_code=400, detail="redirect_url is required")
            return _complete_audible_login(pending_id, redirect_url)

        @router.post("/auth/disconnect", summary="Forget cached Audible auth")
        async def auth_disconnect(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            removed = False
            try:
                if os.path.exists(_AUTH_FILE):
                    os.remove(_AUTH_FILE)
                    removed = True
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"could not remove auth file: {exc}"
                )
            _CLIENT_CACHE.clear()
            return {"removed": removed, "auth_file": _AUTH_FILE}

        @router.post(
            "/auth/auto",
            summary=(
                "Drive the OAuth round-trip end-to-end via Playwright using a "
                "browser profile (reuses user's signed-in Amazon cookies if "
                "available)."
            ),
        )
        async def auth_auto(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
            payload: Dict[str, Any] = Body(default_factory=dict),
        ):
            locale = (payload.get("locale") or "").strip().lower()
            headless = bool(payload.get("headless", False))
            timeout_seconds = int(payload.get("timeout_seconds") or 300)
            if not locale:
                try:
                    agent = _resolve_agent(authorization, agent_id, user)
                    locale = (
                        (
                            (agent.AGENT_CONFIG or {})
                            .get("settings", {})
                            .get("AUDIBLE_LOCALE")
                            or "us"
                        )
                        .strip()
                        .lower()
                    )
                except Exception:
                    locale = "us"
            return await _auth_auto_playwright(locale, headless, timeout_seconds)

        @router.get("/library", summary="List the user's Audible library")
        async def list_library(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
            limit: int = Query(1000, ge=1, le=1000),
            sort_by: str = Query("-PurchaseDate"),
            q: Optional[str] = Query(None),
        ):
            agent = _resolve_agent(authorization, agent_id, user)
            client = _client_for(agent)
            try:
                resp = await asyncio.to_thread(
                    client.get,
                    "1.0/library",
                    params={
                        "num_results": limit,
                        "sort_by": sort_by,
                        "response_groups": (
                            "product_attrs,product_desc,contributors,series,rating,"
                            "media,listening_status,percent_complete,is_finished"
                        ),
                    },
                )
            except Exception as exc:
                logging.error("audible: library fetch failed: %s", exc)
                raise HTTPException(status_code=502, detail=str(exc))
            items = [_book_brief(b) for b in resp.get("items", []) if b.get("asin")]
            if q:
                ql = q.lower()
                items = [
                    b
                    for b in items
                    if ql in b["title"].lower()
                    or any(ql in (a or "").lower() for a in b["authors"])
                    or any(ql in (n or "").lower() for n in b["narrators"])
                    or ql in (b.get("series_title") or "").lower()
                ]
            return {"items": items, "count": len(items)}

        @router.get("/progress", summary="Books currently in progress")
        async def list_progress(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
        ):
            agent = _resolve_agent(authorization, agent_id, user)
            client = _client_for(agent)
            try:
                resp = await asyncio.to_thread(
                    client.get,
                    "1.0/library",
                    params={
                        "num_results": 1000,
                        "response_groups": (
                            "product_attrs,contributors,series,listening_status,"
                            "percent_complete,is_finished,media"
                        ),
                    },
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc))

            in_progress = []
            for b in resp.get("items", []):
                pc = b.get("percent_complete")
                if pc and pc > 0 and not b.get("is_finished"):
                    in_progress.append(_book_brief(b))
            in_progress.sort(key=lambda x: x.get("percent_complete") or 0, reverse=True)
            asins = [b["asin"] for b in in_progress if b.get("asin")][:50]
            positions: Dict[str, int] = {}
            if asins:
                try:
                    pr = await asyncio.to_thread(
                        client.get,
                        "1.0/annotations/lastpositions",
                        params={"asins": ",".join(asins)},
                    )
                    for p in pr.get("last_positions", []):
                        if p.get("asin"):
                            positions[p["asin"]] = int(p.get("position_ms") or 0)
                except Exception as exc:
                    logging.warning("audible: lastpositions failed: %s", exc)
            for b in in_progress:
                b["last_position_ms"] = positions.get(b["asin"], 0)
            return {"items": in_progress, "count": len(in_progress)}

        @router.get("/wishlist", summary="The user's Audible wishlist")
        async def list_wishlist(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
            limit: int = Query(50, ge=1, le=50),
        ):
            agent = _resolve_agent(authorization, agent_id, user)
            client = _client_for(agent)
            try:
                resp = await asyncio.to_thread(
                    client.get,
                    "1.0/wishlist",
                    params={
                        "num_results": limit,
                        "page": 0,
                        "response_groups": (
                            "contributors,product_attrs,product_desc,rating,series,media"
                        ),
                        "sort_by": "-DateAdded",
                    },
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc))
            items = [_book_brief(b) for b in resp.get("products", []) if b.get("asin")]
            return {"items": items, "count": len(items)}

        @router.get("/book/{asin}", summary="Detailed metadata for a single book")
        async def book_details(
            asin: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
        ):
            asin = _validate_asin(asin)
            agent = _resolve_agent(authorization, agent_id, user)
            client = _client_for(agent)
            try:
                resp = await asyncio.to_thread(
                    client.get,
                    f"1.0/catalog/products/{asin}",
                    params={
                        "response_groups": (
                            "contributors,media,product_attrs,product_desc,"
                            "product_extended_attrs,product_plan_details,rating,series,"
                            "reviews,category_ladders"
                        ),
                    },
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc))
            product = resp.get("product") or resp
            out = _book_full(product)
            try:
                lib = await asyncio.to_thread(
                    client.get,
                    f"1.0/library/{asin}",
                    params={
                        "response_groups": "listening_status,percent_complete,is_finished",
                    },
                )
                item = lib.get("item") or {}
                out["percent_complete"] = item.get("percent_complete")
                out["is_finished"] = bool(item.get("is_finished"))
                out["owned"] = True
            except Exception:
                out["owned"] = False
            try:
                pr = await asyncio.to_thread(
                    client.get,
                    "1.0/annotations/lastpositions",
                    params={"asins": asin},
                )
                positions = pr.get("last_positions") or []
                if positions:
                    out["last_position_ms"] = int(positions[0].get("position_ms") or 0)
            except Exception:
                out["last_position_ms"] = 0
            return out

        @router.get("/book/{asin}/chapters", summary="Chapter timing data")
        async def book_chapters(
            asin: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
        ):
            asin = _validate_asin(asin)
            agent = _resolve_agent(authorization, agent_id, user)
            client = _client_for(agent)
            try:
                resp = await asyncio.to_thread(
                    client.get,
                    f"1.0/content/{asin}/metadata",
                    params={
                        "response_groups": "chapter_info",
                        "chapter_titles_type": "Tree",
                    },
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc))
            info = (resp.get("content_metadata") or {}).get("chapter_info") or {}
            chapters_in = info.get("chapters") or []
            out_chapters = []
            cumulative = 0
            for i, ch in enumerate(chapters_in):
                length_ms = int(ch.get("length_ms") or 0)
                start_ms = int(ch.get("start_offset_ms") or cumulative)
                out_chapters.append(
                    {
                        "index": i,
                        "title": ch.get("title") or f"Chapter {i + 1}",
                        "start_ms": start_ms,
                        "length_ms": length_ms,
                    }
                )
                cumulative += length_ms
            last_position_ms = 0
            try:
                pr = await asyncio.to_thread(
                    client.get,
                    "1.0/annotations/lastpositions",
                    params={"asins": asin},
                )
                positions = pr.get("last_positions") or []
                if positions:
                    last_position_ms = int(positions[0].get("position_ms") or 0)
            except Exception:
                pass
            return {
                "asin": asin,
                "chapters": out_chapters,
                "total_ms": cumulative,
                "last_position_ms": last_position_ms,
            }

        @router.get("/cover/{asin}", summary="Cover image (JWT-protected proxy)")
        async def cover_image(
            asin: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
            size: int = Query(500),
        ):
            asin = _validate_asin(asin)
            agent = _resolve_agent(authorization, agent_id, user)
            client = _client_for(agent)
            cache_dir = _AUDIO_CACHE_ROOT / asin
            cache_dir.mkdir(parents=True, exist_ok=True)
            cover_path = cache_dir / f"cover_{size}.jpg"
            if cover_path.is_file() and cover_path.stat().st_size > 0:
                return FileResponse(str(cover_path), media_type="image/jpeg")
            try:
                resp = await asyncio.to_thread(
                    client.get,
                    f"1.0/catalog/products/{asin}",
                    params={
                        "response_groups": "media,product_attrs",
                        "image_sizes": str(size),
                    },
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc))
            product = resp.get("product") or resp
            images = product.get("product_images") or {}
            url = images.get(str(size)) or images.get("500") or images.get("252")
            if not url:
                raise HTTPException(status_code=404, detail="cover not available")
            try:
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as hc:
                    r = await hc.get(url)
                    r.raise_for_status()
                    cover_path.write_bytes(r.content)
            except Exception as exc:
                raise HTTPException(
                    status_code=502, detail=f"cover fetch failed: {exc}"
                )
            return FileResponse(str(cover_path), media_type="image/jpeg")

        @router.get(
            "/audio/{asin}/status",
            summary="Cached audio status for an audiobook",
        )
        async def audio_status(
            asin: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
        ):
            asin = _validate_asin(asin)
            playable = _find_playable_audio(asin)
            base, aax_path = _audio_cache_paths(asin)
            err_path = base / "download_error.txt"
            is_downloading = (
                asin in _DOWNLOAD_TASKS and not _DOWNLOAD_TASKS[asin].done()
            )
            return {
                "asin": asin,
                "playable": bool(playable),
                "playable_path": str(playable) if playable else None,
                "encrypted_only": aax_path.is_file() and not playable,
                "downloading": is_downloading,
                "last_error": (
                    err_path.read_text(encoding="utf-8") if err_path.is_file() else None
                ),
            }

        @router.post(
            "/audio/{asin}/download", summary="Kick off background audio download"
        )
        async def audio_download(
            asin: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
        ):
            asin = _validate_asin(asin)
            if _find_playable_audio(asin):
                return {"started": False, "reason": "already_cached"}
            existing = _DOWNLOAD_TASKS.get(asin)
            if existing and not existing.done():
                return {"started": False, "reason": "in_progress"}
            agent = _resolve_agent(authorization, agent_id, user)
            client = _client_for(agent)
            task = asyncio.create_task(_download_audio(client, asin))
            _DOWNLOAD_TASKS[asin] = task
            return {"started": True}

        @router.get("/audio/{asin}", summary="Stream cached audio bytes")
        async def audio_stream(
            asin: str,
            request: Request,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
            agent_id: Optional[str] = Query(None),
        ):
            asin = _validate_asin(asin)
            playable = _find_playable_audio(asin)
            if not playable:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Audio not available locally. POST /v1/audible/audio/"
                        "{asin}/download to attempt fetching it. DRM-protected "
                        "files may need manual decryption with audible-cli "
                        "before they become playable."
                    ),
                )
            file_size = playable.stat().st_size
            range_hdr = request.headers.get("range") or request.headers.get("Range")
            media_type = "audio/mp4"
            if playable.suffix.lower() == ".mp3":
                media_type = "audio/mpeg"
            if range_hdr and range_hdr.startswith("bytes="):
                try:
                    spec = range_hdr.split("=", 1)[1]
                    start_s, end_s = (spec.split("-", 1) + [""])[:2]
                    start = int(start_s) if start_s else 0
                    end = int(end_s) if end_s else file_size - 1
                    start = max(0, start)
                    end = min(file_size - 1, end)
                    if start > end:
                        raise ValueError("invalid range")

                    def iter_range():
                        with playable.open("rb") as fh:
                            fh.seek(start)
                            remaining = end - start + 1
                            while remaining > 0:
                                chunk = fh.read(min(65536, remaining))
                                if not chunk:
                                    break
                                remaining -= len(chunk)
                                yield chunk

                    headers = {
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(end - start + 1),
                        "Cache-Control": "private, max-age=0",
                    }
                    return StreamingResponse(
                        iter_range(),
                        status_code=206,
                        media_type=media_type,
                        headers=headers,
                    )
                except Exception:
                    pass
            return FileResponse(
                str(playable),
                media_type=media_type,
                headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "private, max-age=0",
                },
            )

    def _format_duration(self, minutes: int) -> str:
        """Convert minutes to human readable duration."""
        if not minutes:
            return "Unknown"
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    def _format_progress(self, percent: float) -> str:
        """Format progress percentage with emoji indicator."""
        if percent is None:
            return "📖 Not started"
        elif percent >= 100:
            return "✅ Finished"
        elif percent > 0:
            return f"📚 {percent:.1f}% complete"
        else:
            return "📖 Not started"

    def _ensure_authenticated(self):
        """Load the Audible auth saved by the desktop Connect flow.

        Sign-in is driven from the AGiXT desktop client's Audible page;
        we just read whatever it wrote to disk. Headless username/
        password login was removed because Amazon's CAPTCHA + 2FA
        gauntlet made it too unreliable in practice.
        """
        if not AUDIBLE_AVAILABLE:
            raise ImportError(
                "The 'audible' package is not installed. Please install it with: pip install audible"
            )
        if self.client is not None:
            return
        if not os.path.exists(self.auth_file):
            raise ValueError(
                "Not connected to Audible. Open the Audible page in the "
                "AGiXT desktop sidebar and click Connect to sign in with "
                "your Amazon account, then ask again."
            )
        try:
            self.auth = Authenticator.from_file(self.auth_file)
            self.client = audible_api.Client(auth=self.auth)
            logging.info("Loaded cached Audible authentication")
        except Exception as e:
            logging.error(f"Cached Audible auth invalid: {e}")
            raise ValueError(
                "Your Audible session has expired. Open the Audible page "
                "in the AGiXT desktop sidebar and click Connect to sign "
                "in again."
            )

    async def get_library(
        self,
        limit: int = 50,
        sort_by: str = "-PurchaseDate",
    ) -> str:
        """
        Get your Audible library with all audiobooks and their current status.

        Args:
        limit (int): Maximum number of books to return (default: 50, max: 1000)
        sort_by (str): Sort order - options: -PurchaseDate, PurchaseDate, -Title, Title, -Author, Author, -Length, Length (default: -PurchaseDate for newest first)

        Returns:
        str: Formatted list of audiobooks with title, author, progress status, and length

        Notes: This shows your complete audiobook library with reading progress for each book.
        """
        self._ensure_authenticated()

        try:
            response = self.client.get(
                "1.0/library",
                params={
                    "num_results": min(limit, 1000),
                    "sort_by": sort_by,
                    "response_groups": "product_attrs,product_desc,contributors,series,rating,media,listening_status,percent_complete,is_finished",
                },
            )

            items = response.get("items", [])
            if not items:
                return "📚 Your Audible library is empty."

            output = [f"📚 **Audible Library** ({len(items)} audiobooks)\n"]
            output.append("=" * 50 + "\n")

            for book in items:
                title = book.get("title", "Unknown Title")
                authors = (
                    ", ".join([a.get("name", "") for a in book.get("authors", [])])
                    or "Unknown Author"
                )
                narrators = (
                    ", ".join([n.get("name", "") for n in book.get("narrators", [])])
                    or "Unknown"
                )

                # Get progress info
                percent_complete = book.get("percent_complete")
                is_finished = book.get("is_finished", False)

                if is_finished:
                    progress = "✅ Finished"
                else:
                    progress = self._format_progress(percent_complete)

                # Get runtime
                runtime_minutes = book.get("runtime_length_min", 0)
                duration = self._format_duration(runtime_minutes)

                # Get series info
                series_info = ""
                series = book.get("series", [])
                if series:
                    series_name = series[0].get("title", "")
                    series_seq = series[0].get("sequence", "")
                    if series_name:
                        series_info = f"\n   📖 Series: {series_name}"
                        if series_seq:
                            series_info += f" (Book {series_seq})"

                asin = book.get("asin", "")

                output.append(f"**{title}**")
                output.append(f"   👤 By: {authors}")
                output.append(f"   🎧 Narrated by: {narrators}")
                output.append(f"   ⏱️ Length: {duration}")
                output.append(f"   {progress}")
                if series_info:
                    output.append(series_info)
                output.append(f"   🔖 ASIN: {asin}")
                output.append("")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting Audible library: {str(e)}")
            return f"Error retrieving library: {str(e)}"

    async def get_reading_progress(self) -> str:
        """
        Get your current reading progress for books you're actively listening to.

        Returns:
        str: Detailed progress information for books currently in progress, including chapter position

        Notes: Shows only books that have been started but not finished, with detailed progress info.
        """
        self._ensure_authenticated()

        try:
            # Get library with progress info
            response = self.client.get(
                "1.0/library",
                params={
                    "num_results": 1000,
                    "response_groups": "product_attrs,contributors,series,listening_status,percent_complete,is_finished",
                },
            )

            items = response.get("items", [])

            # Filter to in-progress books
            in_progress = []
            for book in items:
                percent = book.get("percent_complete")
                is_finished = book.get("is_finished", False)
                if percent and percent > 0 and not is_finished:
                    in_progress.append(book)

            if not in_progress:
                return "📚 No books currently in progress. Start listening to see your progress here!"

            # Sort by most recently listened (highest progress first as proxy)
            in_progress.sort(key=lambda x: x.get("percent_complete", 0), reverse=True)

            output = [
                f"📖 **Currently Reading** ({len(in_progress)} books in progress)\n"
            ]
            output.append("=" * 50 + "\n")

            # Get last positions for all in-progress books
            asins = [b.get("asin") for b in in_progress if b.get("asin")]
            positions = {}

            if asins:
                try:
                    pos_response = self.client.get(
                        "1.0/annotations/lastpositions",
                        params={"asins": ",".join(asins[:50])},  # API limit
                    )
                    for pos in pos_response.get("last_positions", []):
                        positions[pos.get("asin")] = pos
                except Exception as e:
                    logging.warning(f"Could not fetch last positions: {e}")

            for book in in_progress:
                title = book.get("title", "Unknown Title")
                authors = (
                    ", ".join([a.get("name", "") for a in book.get("authors", [])])
                    or "Unknown Author"
                )

                percent_complete = book.get("percent_complete", 0)
                runtime_minutes = book.get("runtime_length_min", 0)

                # Calculate time listened and remaining
                if runtime_minutes:
                    listened_minutes = int(runtime_minutes * percent_complete / 100)
                    remaining_minutes = runtime_minutes - listened_minutes
                    time_info = f"⏱️ {self._format_duration(listened_minutes)} listened, {self._format_duration(remaining_minutes)} remaining"
                else:
                    time_info = ""

                # Get series info
                series_info = ""
                series = book.get("series", [])
                if series:
                    series_name = series[0].get("title", "")
                    series_seq = series[0].get("sequence", "")
                    if series_name:
                        series_info = f"📖 {series_name}"
                        if series_seq:
                            series_info += f" (Book {series_seq})"

                # Progress bar
                bar_length = 20
                filled = int(bar_length * percent_complete / 100)
                bar = "█" * filled + "░" * (bar_length - filled)

                asin = book.get("asin", "")

                output.append(f"**{title}**")
                output.append(f"   👤 {authors}")
                if series_info:
                    output.append(f"   {series_info}")
                output.append(f"   [{bar}] {percent_complete:.1f}%")
                if time_info:
                    output.append(f"   {time_info}")

                # Add position info if available
                if asin in positions:
                    pos = positions[asin]
                    pos_ms = pos.get("position_ms", 0)
                    if pos_ms:
                        pos_minutes = pos_ms // 60000
                        output.append(
                            f"   📍 Last position: {self._format_duration(pos_minutes)} in"
                        )

                output.append(f"   🔖 ASIN: {asin}")
                output.append("")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting reading progress: {str(e)}")
            return f"Error retrieving reading progress: {str(e)}"

    async def get_book_details(self, asin: str) -> str:
        """
        Get detailed information about a specific audiobook.

        Args:
        asin (str): The ASIN (Amazon Standard Identification Number) of the book. You can find this from the library listing.

        Returns:
        str: Comprehensive book details including synopsis, narrator, series info, ratings, and your progress

        Notes: Use this to get full context about a book for discussion, including the description and your reading status.
        """
        self._ensure_authenticated()

        if not asin:
            return "Error: Please provide an ASIN (book identifier). You can find ASINs by listing your library first."

        try:
            # Get product details from catalog
            response = self.client.get(
                f"1.0/catalog/products/{asin}",
                params={
                    "response_groups": "contributors,media,product_attrs,product_desc,product_extended_attrs,product_plan_details,rating,series,reviews,category_ladders",
                },
            )

            product = response.get("product", response)

            title = product.get("title", "Unknown Title")
            subtitle = product.get("subtitle", "")

            authors = (
                ", ".join([a.get("name", "") for a in product.get("authors", [])])
                or "Unknown Author"
            )

            narrators = (
                ", ".join([n.get("name", "") for n in product.get("narrators", [])])
                or "Unknown"
            )

            # Get description
            description = product.get("publisher_summary", "No description available.")
            # Clean HTML from description
            import re

            description = re.sub(r"<[^>]+>", "", description)
            if len(description) > 1000:
                description = description[:1000] + "..."

            # Runtime
            runtime_minutes = product.get("runtime_length_min", 0)
            duration = self._format_duration(runtime_minutes)

            # Release date
            release_date = product.get("release_date", "Unknown")

            # Publisher
            publisher = product.get("publisher_name", "Unknown")

            # Language
            language = product.get("language", "Unknown")

            # Rating
            rating = product.get("rating", {})
            avg_rating = rating.get("overall_distribution", {}).get(
                "display_average_rating", "N/A"
            )
            num_ratings = rating.get("overall_distribution", {}).get("num_ratings", 0)

            # Series info
            series_info = ""
            series = product.get("series", [])
            if series:
                series_name = series[0].get("title", "")
                series_seq = series[0].get("sequence", "")
                if series_name:
                    series_info = f"\n📖 **Series:** {series_name}"
                    if series_seq:
                        series_info += f" (Book {series_seq})"

            # Categories
            categories = []
            ladders = product.get("category_ladders", [])
            for ladder in ladders:
                for cat in ladder.get("ladder", []):
                    cat_name = cat.get("name", "")
                    if cat_name and cat_name not in categories:
                        categories.append(cat_name)
            categories_str = (
                ", ".join(categories[:5]) if categories else "Uncategorized"
            )

            # Try to get user's progress from library
            progress_info = ""
            try:
                lib_response = self.client.get(
                    f"1.0/library/{asin}",
                    params={
                        "response_groups": "listening_status,percent_complete,is_finished",
                    },
                )
                lib_item = lib_response.get("item", {})
                percent = lib_item.get("percent_complete")
                is_finished = lib_item.get("is_finished", False)

                if is_finished:
                    progress_info = "\n\n📊 **Your Progress:** ✅ Finished"
                elif percent and percent > 0:
                    progress_info = f"\n\n📊 **Your Progress:** {percent:.1f}% complete"
                else:
                    progress_info = "\n\n📊 **Your Progress:** Not started"
            except:
                progress_info = (
                    "\n\n📊 **Your Progress:** (Book may not be in your library)"
                )

            output = f"""📖 **{title}**
{f'*{subtitle}*' if subtitle else ''}

👤 **Author:** {authors}
🎧 **Narrator:** {narrators}
⏱️ **Length:** {duration}
📅 **Released:** {release_date}
🏢 **Publisher:** {publisher}
🌐 **Language:** {language}
⭐ **Rating:** {avg_rating}/5 ({num_ratings:,} ratings)
🏷️ **Categories:** {categories_str}
🔖 **ASIN:** {asin}{series_info}{progress_info}

📝 **Description:**
{description}
"""
            return output

        except Exception as e:
            logging.error(f"Error getting book details for {asin}: {str(e)}")
            return f"Error retrieving book details: {str(e)}"

    async def get_book_chapters(self, asin: str) -> str:
        """
        Get the chapter list for a specific audiobook.

        Args:
        asin (str): The ASIN of the book to get chapters for

        Returns:
        str: List of chapters with titles and timestamps

        Notes: Useful for understanding book structure and discussing specific sections. Requires the book to be in your library.
        """
        self._ensure_authenticated()

        if not asin:
            return "Error: Please provide an ASIN (book identifier)."

        try:
            response = self.client.get(
                f"1.0/content/{asin}/metadata",
                params={
                    "response_groups": "chapter_info",
                    "chapter_titles_type": "Tree",
                },
            )

            content_metadata = response.get("content_metadata", {})
            chapter_info = content_metadata.get("chapter_info", {})
            chapters = chapter_info.get("chapters", [])

            if not chapters:
                return (
                    f"📚 No chapter information available for this book (ASIN: {asin})"
                )

            # Try to get book title
            title = "Unknown Book"
            try:
                lib_response = self.client.get(
                    f"1.0/library/{asin}",
                    params={"response_groups": "product_attrs"},
                )
                title = lib_response.get("item", {}).get("title", "Unknown Book")
            except:
                pass

            # Get user's current position
            current_chapter = None
            try:
                pos_response = self.client.get(
                    "1.0/annotations/lastpositions",
                    params={"asins": asin},
                )
                positions = pos_response.get("last_positions", [])
                if positions:
                    pos_ms = positions[0].get("position_ms", 0)
                    # Find which chapter this corresponds to
                    cumulative_ms = 0
                    for i, ch in enumerate(chapters):
                        ch_length = ch.get("length_ms", 0)
                        if cumulative_ms + ch_length > pos_ms:
                            current_chapter = i
                            break
                        cumulative_ms += ch_length
            except:
                pass

            output = [f"📖 **Chapters for: {title}**"]
            output.append(f"🔖 ASIN: {asin}")
            output.append(f"📚 Total chapters: {len(chapters)}")
            output.append("=" * 50 + "\n")

            total_ms = 0
            for i, chapter in enumerate(chapters):
                ch_title = chapter.get("title", f"Chapter {i + 1}")
                ch_length_ms = chapter.get("length_ms", 0)
                ch_start_ms = chapter.get("start_offset_ms", total_ms)

                # Format timestamps
                start_time = self._format_duration(ch_start_ms // 60000)
                ch_duration = self._format_duration(ch_length_ms // 60000)

                # Mark current chapter
                marker = "📍 " if current_chapter == i else "   "
                current_indicator = " ← YOU ARE HERE" if current_chapter == i else ""

                output.append(f"{marker}{i + 1}. {ch_title}")
                output.append(
                    f"      ⏱️ {start_time} ({ch_duration}){current_indicator}"
                )

                total_ms += ch_length_ms

            total_duration = self._format_duration(total_ms // 60000)
            output.append(f"\n📊 **Total runtime:** {total_duration}")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting chapters for {asin}: {str(e)}")
            return f"Error retrieving chapter info: {str(e)}. Make sure the book is in your library."

    async def get_reading_statistics(self) -> str:
        """
        Get your Audible listening statistics and achievements.

        Returns:
        str: Listening statistics including time listened, books finished, and listening patterns

        Notes: Provides an overview of your listening habits and accomplishments.
        """
        self._ensure_authenticated()

        try:
            response = self.client.get(
                "1.0/stats/aggregates",
                params={
                    "response_groups": "total_listening_stats",
                    "store": "Audible",
                },
            )

            stats = response.get("aggregated_stats", {})

            # Total listening time
            total_ms = stats.get("total_listening_time_ms", 0)
            total_hours = total_ms / (1000 * 60 * 60)

            output = ["📊 **Audible Listening Statistics**"]
            output.append("=" * 50 + "\n")

            output.append(f"🎧 **Total Listening Time:** {total_hours:.1f} hours")

            # Get library counts
            try:
                lib_response = self.client.get(
                    "1.0/library",
                    params={
                        "num_results": 1000,
                        "response_groups": "percent_complete,is_finished",
                    },
                )
                items = lib_response.get("items", [])

                total_books = len(items)
                finished_books = sum(1 for b in items if b.get("is_finished", False))
                in_progress = sum(
                    1
                    for b in items
                    if not b.get("is_finished", False)
                    and b.get("percent_complete", 0) > 0
                )
                not_started = total_books - finished_books - in_progress

                output.append(f"\n📚 **Library Overview:**")
                output.append(f"   📖 Total books: {total_books}")
                output.append(f"   ✅ Finished: {finished_books}")
                output.append(f"   📖 In progress: {in_progress}")
                output.append(f"   📕 Not started: {not_started}")

                if total_books > 0:
                    completion_rate = (finished_books / total_books) * 100
                    output.append(f"\n   📈 Completion rate: {completion_rate:.1f}%")

            except Exception as e:
                logging.warning(f"Could not fetch library stats: {e}")

            # Try to get badges/achievements
            try:
                badges_response = self.client.get(
                    "1.0/badges/progress",
                    params={
                        "locale": "en_US",
                        "response_groups": "brag_message",
                        "store": "Audible",
                    },
                )
                # Badge info varies by user
            except:
                pass

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting statistics: {str(e)}")
            return f"Error retrieving statistics: {str(e)}"

    async def search_library(
        self,
        query: str,
        search_type: str = "all",
    ) -> str:
        """
        Search your Audible library by title, author, or narrator.

        Args:
        query (str): The search term to look for
        search_type (str): What to search - options: all, title, author, narrator (default: all)

        Returns:
        str: Matching books from your library with progress status

        Notes: Searches only within your owned library, not the full Audible catalog.
        """
        self._ensure_authenticated()

        if not query:
            return "Error: Please provide a search query."

        try:
            params = {
                "num_results": 1000,
                "response_groups": "product_attrs,contributors,series,percent_complete,is_finished",
            }

            # Add search parameter based on type
            if search_type.lower() == "title":
                params["title"] = query
            elif search_type.lower() == "author":
                params["author"] = query
            else:
                # For 'all' or 'narrator', we'll filter client-side
                pass

            response = self.client.get("1.0/library", params=params)
            items = response.get("items", [])

            # Client-side filtering for 'all' search
            query_lower = query.lower()
            matching = []

            for book in items:
                title = book.get("title", "").lower()
                authors = " ".join(
                    [a.get("name", "").lower() for a in book.get("authors", [])]
                )
                narrators = " ".join(
                    [n.get("name", "").lower() for n in book.get("narrators", [])]
                )

                if search_type.lower() == "narrator":
                    if query_lower in narrators:
                        matching.append(book)
                elif search_type.lower() == "all":
                    if (
                        query_lower in title
                        or query_lower in authors
                        or query_lower in narrators
                    ):
                        matching.append(book)
                else:
                    # Title or author search already filtered by API
                    matching.append(book)

            if not matching:
                return f"🔍 No books found matching '{query}' in your library."

            output = [f"🔍 **Search Results for '{query}'** ({len(matching)} found)\n"]
            output.append("=" * 50 + "\n")

            for book in matching:
                title = book.get("title", "Unknown Title")
                authors = (
                    ", ".join([a.get("name", "") for a in book.get("authors", [])])
                    or "Unknown"
                )
                narrators = (
                    ", ".join([n.get("name", "") for n in book.get("narrators", [])])
                    or "Unknown"
                )

                percent = book.get("percent_complete")
                is_finished = book.get("is_finished", False)

                if is_finished:
                    progress = "✅ Finished"
                else:
                    progress = self._format_progress(percent)

                asin = book.get("asin", "")

                output.append(f"**{title}**")
                output.append(f"   👤 By: {authors}")
                output.append(f"   🎧 Narrator: {narrators}")
                output.append(f"   {progress}")
                output.append(f"   🔖 ASIN: {asin}")
                output.append("")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error searching library: {str(e)}")
            return f"Error searching library: {str(e)}"

    async def get_wishlist(self, limit: int = 50) -> str:
        """
        Get your Audible wishlist of books you want to read.

        Args:
        limit (int): Maximum number of wishlist items to return (default: 50)

        Returns:
        str: List of books on your wishlist with details

        Notes: Shows books you've saved to your wishlist for future purchase.
        """
        self._ensure_authenticated()

        try:
            response = self.client.get(
                "1.0/wishlist",
                params={
                    "num_results": min(limit, 50),
                    "page": 0,
                    "response_groups": "contributors,product_attrs,product_desc,rating,series,media",
                    "sort_by": "-DateAdded",
                },
            )

            products = response.get("products", [])

            if not products:
                return "💭 Your Audible wishlist is empty."

            output = [f"💭 **Audible Wishlist** ({len(products)} books)\n"]
            output.append("=" * 50 + "\n")

            for book in products:
                title = book.get("title", "Unknown Title")
                authors = (
                    ", ".join([a.get("name", "") for a in book.get("authors", [])])
                    or "Unknown Author"
                )
                narrators = (
                    ", ".join([n.get("name", "") for n in book.get("narrators", [])])
                    or "Unknown"
                )

                runtime_minutes = book.get("runtime_length_min", 0)
                duration = self._format_duration(runtime_minutes)

                # Rating
                rating = book.get("rating", {})
                avg_rating = rating.get("overall_distribution", {}).get(
                    "display_average_rating", "N/A"
                )

                # Series
                series_info = ""
                series = book.get("series", [])
                if series:
                    series_name = series[0].get("title", "")
                    series_seq = series[0].get("sequence", "")
                    if series_name:
                        series_info = f"\n   📖 Series: {series_name}"
                        if series_seq:
                            series_info += f" (Book {series_seq})"

                asin = book.get("asin", "")

                output.append(f"**{title}**")
                output.append(f"   👤 By: {authors}")
                output.append(f"   🎧 Narrated by: {narrators}")
                output.append(f"   ⏱️ Length: {duration}")
                output.append(f"   ⭐ Rating: {avg_rating}/5")
                if series_info:
                    output.append(series_info)
                output.append(f"   🔖 ASIN: {asin}")
                output.append("")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting wishlist: {str(e)}")
            return f"Error retrieving wishlist: {str(e)}"

    async def get_book_annotations(self, asin: str) -> str:
        """
        Get your bookmarks, notes, and clips for a specific audiobook.

        Args:
        asin (str): The ASIN of the book to get annotations for

        Returns:
        str: Your bookmarks, notes, and clips from the book

        Notes: Perfect for reviewing what you've marked as important or want to discuss.
        """
        self._ensure_authenticated()

        if not asin:
            return "Error: Please provide an ASIN (book identifier)."

        try:
            # The annotations endpoint is at a different domain
            # This uses the FionaCDEServiceEngine
            # Note: This may require additional auth handling

            # Try to get book title first
            title = "Unknown Book"
            try:
                lib_response = self.client.get(
                    f"1.0/library/{asin}",
                    params={"response_groups": "product_attrs"},
                )
                title = lib_response.get("item", {}).get("title", "Unknown Book")
            except:
                pass

            # Annotations endpoint may not be accessible through standard client
            # This is a best-effort attempt
            try:
                # Try standard library endpoint with annotation response groups
                response = self.client.get(
                    f"1.0/library/{asin}",
                    params={
                        "response_groups": "product_attrs",
                    },
                )
            except:
                pass

            output = [f"📝 **Annotations for: {title}**"]
            output.append(f"🔖 ASIN: {asin}")
            output.append("=" * 50 + "\n")

            # Note: The annotations endpoint (cde-ta-g7g.amazon.com) requires special auth
            # that may not be available through the standard audible package
            output.append(
                "⚠️ **Note:** Direct annotation retrieval requires additional "
            )
            output.append("authentication that may not be supported yet.")
            output.append("")
            output.append(
                "**Workaround:** You can view your annotations in the Audible app"
            )
            output.append("or on audible.com under your library > Notes & Bookmarks.")
            output.append("")
            output.append("If you'd like to discuss specific parts of the book,")
            output.append("please share the relevant bookmarks or quotes manually,")
            output.append("and I'll be happy to discuss them with you!")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting annotations for {asin}: {str(e)}")
            return f"Error retrieving annotations: {str(e)}"
