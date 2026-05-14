"""
Landing pages — unauthenticated discovery + asset delivery.

The AGiXT Desktop client (and any web/embed of it) shows a per-app
landing page when no JWT is present. The page itself is shipped as
plain HTML/CSS/JS by an extension hub: each repo that owns a brand
drops `landing/<site_id>/manifest.json`, `index.html`, etc. into the
hub.

This router serves three endpoints, all unauthenticated because the
landing page is the pre-login surface:

  GET /v1/landing
      Returns the manifest of the landing page that should render
      for this server's `APP_NAME`. The hub-wide selection rule:
        1. Any landing whose manifest `app_names` includes APP_NAME
        2. Then any landing whose manifest `app_name` equals APP_NAME
        3. Then any landing whose manifest `default` is true
        4. None — client falls back to its built-in auth screen
      Returns `{"landing": null}` when no landing matches; the
      desktop client then jumps straight to the auth screen as it
      did before this feature existed.

  GET /v1/landing/{site_id}
  GET /v1/landing/{site_id}/{path}
      Static asset delivery. `index.html` if path is empty; otherwise
      the file at `<landing_dir>/<path>` after path-traversal
      validation. Same allow-list as DesktopExtensions to avoid the
      route turning into a generic file-server.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ExtensionsHub import ExtensionsHub
from Globals import getenv

app = APIRouter()
logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")

# Same allow-list philosophy as DesktopExtensions — explicit MIME types
# so the route only ever serves landing assets, never random files.
_ALLOWED_ASSET_EXTS = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".map": "application/json",
    ".txt": "text/plain",
}


def _list_landing_dirs() -> List[Tuple[str, Path]]:
    """Yield `(site_id, landing_dir)` pairs across every hub the
    server is configured against. First match wins on collision so
    the user's local hub can shadow a public one."""
    seen: Dict[str, Path] = {}
    for hub_root in ExtensionsHub().get_extension_search_paths():
        landing_root = Path(hub_root) / "landing"
        if not landing_root.is_dir():
            continue
        for entry in sorted(landing_root.iterdir()):
            if not entry.is_dir():
                continue
            site_id = entry.name
            if not _ID_RE.match(site_id):
                continue
            if site_id in seen:
                continue
            if not (entry / "manifest.json").is_file():
                continue
            if not (entry / "index.html").is_file():
                continue
            seen[site_id] = entry
    return list(seen.items())


def _load_manifest(landing_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        with (landing_dir / "manifest.json").open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        logger.warning("landing: bad manifest in %s: %s", landing_dir, exc)
        return None
    if not isinstance(data, dict):
        return None
    return data


def _select_landing(app_name: str) -> Optional[Tuple[str, Path, Dict[str, Any]]]:
    """Pick the landing whose manifest best matches `app_name`.

    Order:
      1. exact app_name match in `app_names` list
      2. exact app_name match on `app_name` string
      3. landing with `default: true`

    Returns `(site_id, landing_dir, manifest)` or None.
    """
    candidates = []
    target = (app_name or "").strip()
    target_lower = target.lower()
    default_match = None
    for site_id, landing_dir in _list_landing_dirs():
        manifest = _load_manifest(landing_dir)
        if manifest is None:
            continue
        if manifest.get("id") and manifest.get("id") != site_id:
            logger.warning(
                "landing: id mismatch — dir=%s manifest=%s",
                site_id,
                manifest.get("id"),
            )
            continue
        candidates.append((site_id, landing_dir, manifest))
        if manifest.get("default") is True and default_match is None:
            default_match = (site_id, landing_dir, manifest)

    if not candidates:
        return None

    # Pass 1: app_names list contains target
    for entry in candidates:
        names = entry[2].get("app_names") or []
        if isinstance(names, str):
            names = [names]
        if any(str(n).lower() == target_lower for n in names):
            return entry

    # Pass 2: scalar app_name equals target
    for entry in candidates:
        name = entry[2].get("app_name")
        if isinstance(name, str) and name.lower() == target_lower:
            return entry

    # Pass 3: explicit default
    if default_match is not None:
        return default_match

    # Pass 4: only one candidate? use it.
    if len(candidates) == 1:
        return candidates[0]

    return None


def _normalize_manifest(manifest: Dict[str, Any], site_id: str) -> Dict[str, Any]:
    """Slim shape returned to the client. The client only needs to know
    which site to render and which entry HTML to load; it does not need
    the targeting metadata that drove the selection."""
    version = str(manifest.get("version") or "0.1.0")
    out: Dict[str, Any] = {
        "id": site_id,
        "label": str(manifest.get("label") or manifest.get("app_name") or site_id.title()),
        "app_name": manifest.get("app_name") or "",
        "version": version,
        "entry_url": f"/v1/landing/{site_id}/?v={version}",
        "index_url": f"/v1/landing/{site_id}/index.html?v={version}",
    }
    if manifest.get("logo"):
        out["logo"] = str(manifest["logo"])
    if manifest.get("favicon"):
        out["favicon"] = str(manifest["favicon"])
    if manifest.get("tagline"):
        out["tagline"] = str(manifest["tagline"])
    return out


def _resolve_asset(site_id: str, rel_path: str) -> Tuple[Path, str]:
    """Return `(target_path, media_type)` for a file under the landing
    directory, or raise an HTTPException."""
    if not _ID_RE.match(site_id):
        raise HTTPException(status_code=400, detail="invalid landing id")
    rel = (rel_path or "").strip().lstrip("/")
    if not rel or rel.endswith("/"):
        rel = (rel + "index.html").lstrip("/")
    suffix = "." + rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    media_type = _ALLOWED_ASSET_EXTS.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=415, detail="landing asset type not allowed")

    for found_id, landing_dir in _list_landing_dirs():
        if found_id != site_id:
            continue
        target = (landing_dir / rel).resolve()
        try:
            target.relative_to(landing_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="path escapes landing dir")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="landing asset not found")
        return target, media_type
    raise HTTPException(status_code=404, detail="landing not found")


@app.get(
    "/v1/landing",
    tags=["Landing"],
    summary="Discover the pre-login landing page configured for this server.",
)
async def get_landing(request: Request):
    """Returns the landing manifest matching the server's `APP_NAME`,
    or `{"landing": null}` when no hub provides one. Unauthenticated
    on purpose — this is the pre-login surface."""
    app_name = getenv("APP_NAME", "AGiXT") or "AGiXT"
    selected = _select_landing(app_name)
    payload: Dict[str, Any]
    if selected is None:
        payload = {"landing": None, "app_name": app_name}
        etag = '"none"'
    else:
        site_id, _dir, manifest = selected
        payload = {
            "landing": _normalize_manifest(manifest, site_id),
            "app_name": app_name,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        etag = f'"{digest}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=payload, headers=headers)


def _resolve_shared_asset(rel_path: str) -> Tuple[Path, str]:
    """Serve a file from a hub's `landing/_shared/` directory. Used for
    cross-site assets (the design-token base CSS, Inter font fallback,
    shared lucide-style icon sprite). First-match-wins across hubs so a
    local override can shadow the bundled defaults."""
    rel = (rel_path or "").strip().lstrip("/")
    if not rel or rel.endswith("/"):
        raise HTTPException(status_code=404, detail="shared asset not found")
    suffix = "." + rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    media_type = _ALLOWED_ASSET_EXTS.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=415, detail="shared asset type not allowed")

    for hub_root in ExtensionsHub().get_extension_search_paths():
        shared_root = (Path(hub_root) / "landing" / "_shared").resolve()
        if not shared_root.is_dir():
            continue
        target = (shared_root / rel).resolve()
        try:
            target.relative_to(shared_root)
        except ValueError:
            continue
        if target.is_file():
            return target, media_type
    raise HTTPException(status_code=404, detail="shared asset not found")


@app.get(
    "/v1/landing/_shared/{path:path}",
    tags=["Landing"],
    summary="Serve a shared asset (design-token CSS, font, etc.) used by every landing page.",
)
async def get_landing_shared_asset(path: str):
    target, media_type = _resolve_shared_asset(path)
    return FileResponse(
        str(target),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get(
    "/v1/landing/{site_id}",
    tags=["Landing"],
    summary="Serve a landing page's index.html.",
)
async def get_landing_index(site_id: str):
    target, media_type = _resolve_asset(site_id, "index.html")
    return FileResponse(
        str(target),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get(
    "/v1/landing/{site_id}/",
    tags=["Landing"],
    summary="Serve a landing page's index.html (trailing-slash form).",
)
async def get_landing_index_slash(site_id: str):
    target, media_type = _resolve_asset(site_id, "index.html")
    return FileResponse(
        str(target),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get(
    "/v1/landing/{site_id}/{path:path}",
    tags=["Landing"],
    summary="Serve a sibling asset (CSS, JS, image, font) for a landing page.",
)
async def get_landing_asset(site_id: str, path: str):
    target, media_type = _resolve_asset(site_id, path)
    return FileResponse(
        str(target),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )
