"""
Desktop client extensions — discovery + asset delivery.

The AGiXT Desktop client exposes optional pages in its sidenav (a
"Machines" page, a "GitHub" page, etc.). The pages themselves are
shipped as plain JS modules from the extensions hub: each extension
that wants a UI page drops `desktop/<id>/manifest.json` and
`desktop/<id>/main.js` into the hub.

This router serves two endpoints:

  GET /v1/desktop/extensions
      Returns the manifest of pages the authenticated client should
      render, gated by the per-extension `requires` block:
        company_scope   — list of scopes the user must hold on the
                          requested company (e.g. ["ext:machines:read"])
        user_oauth      — provider name(s) the user must have connected
        agent_extension — Extension class name(s) enabled on the
                          requested agent
      Caller passes optional `?company_id=...&agent_id=...`. When
      missing, the user's primary company / default agent is used.

  GET /v1/desktop/extensions/{id}/main.js
      Returns the raw JS bytes for the page's entry module. The same
      `requires` block is re-checked here so a client can't fetch a
      page it isn't entitled to by guessing the URL.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ApiClient import verify_api_key
from ExtensionsHub import ExtensionsHub
from MagicalAuth import MagicalAuth

app = APIRouter()
logger = logging.getLogger(__name__)

# Only allow these characters in an extension id — guards path traversal
# and keeps URLs predictable.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


def _list_extension_dirs() -> List[Tuple[str, Path]]:
    """Yield `(extension_id, manifest_dir)` pairs across every hub the
    server is configured against. First match wins on collision so the
    user's local hub can shadow a public one."""
    seen: Dict[str, Path] = {}
    for hub_root in ExtensionsHub().get_extension_search_paths():
        desktop_root = Path(hub_root) / "desktop"
        if not desktop_root.is_dir():
            continue
        for entry in sorted(desktop_root.iterdir()):
            if not entry.is_dir():
                continue
            ext_id = entry.name
            if not _ID_RE.match(ext_id):
                continue
            if ext_id in seen:
                continue
            if not (entry / "manifest.json").is_file():
                continue
            seen[ext_id] = entry
    return list(seen.items())


def _load_manifest(manifest_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        with (manifest_dir / "manifest.json").open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        logger.warning("desktop ext: bad manifest in %s: %s", manifest_dir, exc)
        return None
    if not isinstance(data, dict):
        return None
    return data


def _meets_requires(
    auth: MagicalAuth,
    requires: Dict[str, Any],
    company_id: Optional[str],
    agent_id: Optional[str],
) -> bool:
    """Return True iff the authenticated user satisfies `requires`. Each
    block is optional; an empty `requires` means everyone gets it."""
    if not isinstance(requires, dict) or not requires:
        return True

    company_scope = requires.get("company_scope") or []
    if isinstance(company_scope, str):
        company_scope = [company_scope]
    for scope in company_scope:
        if not auth.has_scope(scope, company_id):
            return False

    oauth_providers = requires.get("user_oauth") or []
    if isinstance(oauth_providers, str):
        oauth_providers = [oauth_providers]
    if oauth_providers and not _user_has_oauth(auth, oauth_providers):
        return False

    agent_exts = requires.get("agent_extension") or []
    if isinstance(agent_exts, str):
        agent_exts = [agent_exts]
    if agent_exts and not _agent_has_extension(auth, agent_id, agent_exts):
        return False

    return True


def _user_has_oauth(auth: MagicalAuth, providers: List[str]) -> bool:
    """True iff the authenticated user has connected at least one of
    the listed OAuth providers (case-insensitive on provider name)."""
    if not auth.user_id:
        return False
    from DB import OAuthProvider, UserOAuth, get_db_session

    wanted = {p.lower() for p in providers if isinstance(p, str)}
    if not wanted:
        return False
    try:
        with get_db_session() as session:
            row = (
                session.query(UserOAuth)
                .join(OAuthProvider, OAuthProvider.id == UserOAuth.provider_id)
                .filter(UserOAuth.user_id == auth.user_id)
                .filter(OAuthProvider.name.in_(list(wanted)))
                .first()
            )
            return row is not None
    except Exception as exc:
        logger.warning("desktop ext: oauth lookup failed: %s", exc)
        return False


def _agent_has_extension(
    auth: MagicalAuth, agent_id: Optional[str], ext_names: List[str]
) -> bool:
    """True iff the requested agent has *any* command from one of the
    listed extension class names enabled. Mirrors the agent-commands
    update path used by the rest of AGiXT."""
    if not agent_id:
        return False
    try:
        from ApiClient import Agent
        agent = Agent(agent_name=None, user=auth.email, ApiClient=None)
        # Different deploys expose this differently; use whichever is
        # available without crashing.
        if hasattr(agent, "get_commands"):
            cmds = agent.get_commands(agent_id)
        else:
            cmds = []
        wanted = {n.lower() for n in ext_names if isinstance(n, str)}
        for cmd in cmds or []:
            ext = (cmd.get("extension_name") or cmd.get("extension") or "").lower()
            if ext in wanted and cmd.get("enabled"):
                return True
        return False
    except Exception as exc:
        logger.warning("desktop ext: agent extension lookup failed: %s", exc)
        return False


def _normalize_entry(item: Dict[str, Any], ext_id: str) -> Dict[str, Any]:
    """Produce the slim object the desktop client consumes. We deliberately
    don't echo `requires` back — the server has already filtered the list."""
    version = str(item.get("version") or "0.0.0")
    return {
        "id": ext_id,
        "label": str(item.get("label") or ext_id.title()),
        "icon": item.get("icon") or "",
        "version": version,
        "entry_url": f"/v1/desktop/extensions/{ext_id}/main.js?v={version}",
    }


def _manifest_etag(items: List[Dict[str, Any]]) -> str:
    payload = json.dumps(items, sort_keys=True).encode("utf-8")
    return '"' + hashlib.sha256(payload).hexdigest()[:16] + '"'


@app.get(
    "/v1/desktop/extensions",
    tags=["DesktopExtensions"],
    dependencies=[Depends(verify_api_key)],
    summary="List the extension pages this client is entitled to render.",
)
async def list_desktop_extensions(
    request: Request,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
    company_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
):
    auth = MagicalAuth(token=authorization)
    if auth.user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    items: List[Dict[str, Any]] = []
    for ext_id, manifest_dir in _list_extension_dirs():
        manifest = _load_manifest(manifest_dir)
        if manifest is None:
            continue
        if manifest.get("id") and manifest.get("id") != ext_id:
            # Manifest can reaffirm its id, but it must agree with the
            # directory name. Disagreement is a config error.
            logger.warning(
                "desktop ext: id mismatch — dir=%s manifest=%s",
                ext_id,
                manifest.get("id"),
            )
            continue
        if not _meets_requires(
            auth, manifest.get("requires") or {}, company_id, agent_id
        ):
            continue
        items.append(_normalize_entry(manifest, ext_id))

    etag = _manifest_etag(items)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(
        content={"extensions": items, "etag": etag},
        headers=headers,
    )


@app.get(
    "/v1/desktop/extensions/{ext_id}/main.js",
    tags=["DesktopExtensions"],
    dependencies=[Depends(verify_api_key)],
    summary="Serve an extension's main.js bytes (gated by its requires block).",
)
async def serve_desktop_extension_js(
    ext_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
    company_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
):
    if not _ID_RE.match(ext_id):
        raise HTTPException(status_code=400, detail="invalid extension id")

    auth = MagicalAuth(token=authorization)
    if auth.user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Locate the extension and re-check entitlement so the JS URL can't
    # be used to bypass the manifest's requires block.
    for found_id, manifest_dir in _list_extension_dirs():
        if found_id != ext_id:
            continue
        manifest = _load_manifest(manifest_dir)
        if manifest is None:
            raise HTTPException(status_code=404, detail="manifest unreadable")
        if not _meets_requires(
            auth, manifest.get("requires") or {}, company_id, agent_id
        ):
            raise HTTPException(status_code=403, detail="not entitled")
        entry = manifest.get("entry") or "main.js"
        # Defence-in-depth: the entry is allowed to be a relative path
        # but must resolve inside the extension's own dir.
        target = (manifest_dir / entry).resolve()
        try:
            target.relative_to(manifest_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="entry escapes extension dir")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="entry missing")
        return FileResponse(
            str(target),
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=300"},
        )

    raise HTTPException(status_code=404, detail="extension not found")
