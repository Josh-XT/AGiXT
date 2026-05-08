import asyncio
import base64
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth, get_sso_credentials, verify_api_key

"""
Required environment variables:

- GITHUB_CLIENT_ID: GitHub OAuth client ID
- GITHUB_CLIENT_SECRET: GitHub OAuth client secret

Required scopes for GitHub OAuth (full repository access for AI)

- repo: Full repository access
- user:email: Access user's email address
- read:user: Read user profile information
- workflow: Manage GitHub Actions workflows

Note: For login-only functionality with minimal scopes, use github_sso instead.
This extension grants the AI full access to work with repositories.
"""

SCOPES = ["repo", "user:email", "read:user", "workflow", "read:org"]
AUTHORIZE = "https://github.com/login/oauth/authorize"
PKCE_REQUIRED = False
# No SSO_ONLY - this extension is for AI repository access, not login


class GitHubSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GITHUB_CLIENT_ID")
        self.client_secret = getenv("GITHUB_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        # GitHub tokens do not support refresh tokens directly, we need to re-authorize.
        # GitHub tokens are long-lived and don't typically expire, but if they do,
        # the user needs to re-authenticate.
        if not self.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="GitHub tokens do not support refresh. Please re-authenticate.",
            )

        # This will likely fail since GitHub doesn't support refresh tokens
        # but we'll try anyway in case their API changes
        try:
            response = requests.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )

            if response.status_code != 200:
                raise Exception(f"GitHub token refresh failed: {response.text}")

            token_data = response.json()

            # Update our access token for immediate use
            if "access_token" in token_data:
                self.access_token = token_data["access_token"]

            return token_data
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail="GitHub tokens do not support refresh. Please re-authenticate.",
            )

    def get_user_info(self):
        uri = "https://api.github.com/user"
        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        try:
            data = response.json()
            response = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {self.access_token}"},
            )
            primary_email = response.json()["login"]
            return {
                "email": primary_email,
                "first_name": (
                    data.get("name", "").split()[0] if data.get("name") else ""
                ),
                "last_name": (
                    data.get("name", "").split()[-1] if data.get("name") else ""
                ),
            }
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from GitHub",
            )


def sso(code, redirect_uri=None) -> GitHubSSO:
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )

    response = requests.post(
        f"https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": getenv("GITHUB_CLIENT_ID"),
            "client_secret": getenv("GITHUB_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting GitHub access token: {response.text}")
        return None
    data = response.json()
    if "error" in data:
        logging.error(
            f"GitHub OAuth error: {data.get('error')} - {data.get('error_description', '')} | redirect_uri used: {redirect_uri}"
        )
        return None
    access_token = data.get("access_token")
    if not access_token:
        logging.error(f"No access_token in GitHub response: {data}")
        return None
    refresh_token = data.get("refresh_token", "Not provided")
    return GitHubSSO(access_token=access_token, refresh_token=refresh_token)


# ===========================================================================
# Repo dashboard logic — ports `repo-dashboard/app.py` into AGiXT so the
# desktop client can authenticate via JWT instead of a shared admin token.
# ===========================================================================

# Per-user repo cache, keyed by user_id. Each entry is
# {"repos": [...], "last_updated": iso_str}. We don't share across users
# because each user's GitHub token sees a different set of repos.
_REPO_CACHE: Dict[str, Dict[str, Any]] = {}
_REPO_CACHE_LOCK = threading.Lock()
_REPO_CACHE_TTL_SECS = 300  # 5 minutes


def _load_excluded_owners() -> set:
    """Owners to omit from the dashboard — typically orgs the user is a
    nominal member of but doesn't actually maintain. Configurable via
    `GITHUB_REPO_DASHBOARD_EXCLUDED_OWNERS` (comma-separated). Defaults
    match the original `repo-dashboard/app.py` list so behavior carries
    over for the dev install."""
    raw = getenv("GITHUB_REPO_DASHBOARD_EXCLUDED_OWNERS") or ""
    if raw.strip():
        items = [s.strip() for s in raw.split(",") if s.strip()]
    else:
        items = [
            "EpicGames",
            "nsvec-pg",
            "JADkins-BPS",
            "Alignment-Lab-AI",
            "alt-shreya",
            "nikolai3ldwin",
            "Electrofried",
            "EASE-Logistics",
        ]
    return {s.lower() for s in items}


_EXCLUDED_OWNERS = _load_excluded_owners()


def _gh_token_for_user(user_id: str) -> Optional[str]:
    """Return the user's stored GitHub access token, or None if not connected."""
    if not user_id:
        return None
    try:
        creds = get_sso_credentials(user_id) or {}
    except Exception as exc:
        logging.warning("github: lookup oauth creds failed: %s", exc)
        return None
    return creds.get("GITHUB_ACCESS_TOKEN")


def _gh_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }


def _gh_get_paginated(
    url: str, token: str, params: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """GET a GitHub list endpoint, transparently paging through results."""
    out: List[Dict[str, Any]] = []
    params = dict(params or {})
    params["per_page"] = 100
    page = 1
    while True:
        params["page"] = page
        resp = requests.get(url, headers=_gh_headers(token), params=params, timeout=30)
        if resp.status_code != 200:
            break
        data = resp.json()
        if not isinstance(data, list) or not data:
            break
        out.extend(data)
        if len(data) < 100:
            break
        page += 1
    return out


def _format_relative_time(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        if seconds < 2592000:
            return f"{seconds // 86400}d ago"
        return f"{seconds // 2592000}mo ago"
    except Exception:
        return iso_str


def _fetch_user_repos(token: str) -> List[Dict[str, Any]]:
    """All non-archived repos the authenticated user owns or has access
    to, deduped across `/user/repos` and per-org enumeration.

    `/user/repos?affiliation=...` only returns org repos when the OAuth
    app is approved for the org; sometimes that approval is partial or
    missing, so we *also* list the user's orgs (`/user/orgs`) and pull
    each org's repos. Repos that fail with 403/404 (no access) are
    silently skipped. Owners listed in `_EXCLUDED_OWNERS` are dropped
    so users can hide nominal-membership orgs.
    """
    repos = _gh_get_paginated(
        "https://api.github.com/user/repos",
        token,
        {
            "sort": "updated",
            "direction": "desc",
            "affiliation": "owner,organization_member,collaborator",
        },
    )

    # Best-effort enumerate orgs and pull each org's repo list to catch
    # anything the affiliation filter missed. Requires `read:org` scope.
    seen_full_names = {r.get("full_name") for r in repos if r.get("full_name")}
    try:
        orgs = _gh_get_paginated("https://api.github.com/user/orgs", token, {})
    except Exception:
        orgs = []
    for org in orgs:
        login = (org or {}).get("login")
        if not login or login.lower() in _EXCLUDED_OWNERS:
            continue
        try:
            org_repos = _gh_get_paginated(
                f"https://api.github.com/orgs/{login}/repos",
                token,
                {"sort": "updated", "direction": "desc", "type": "all"},
            )
        except Exception:
            continue
        for r in org_repos:
            fn = r.get("full_name")
            if fn and fn not in seen_full_names:
                seen_full_names.add(fn)
                repos.append(r)

    return [
        r
        for r in repos
        if not r.get("archived", False)
        and (r.get("owner") or {}).get("login", "").lower() not in _EXCLUDED_OWNERS
    ]


def _fetch_repo_security(token: str, repo: Dict[str, Any]) -> Dict[str, Any]:
    """Pull issues/PR counts and security alert counts for one repo."""
    owner_name = repo["owner"]["login"]
    repo_name = repo["name"]
    full_name = repo["full_name"]
    is_admin = repo.get("permissions", {}).get("admin", False)
    headers = _gh_headers(token)

    total_open = repo.get("open_issues_count", 0)

    # Open PR count via Link header trick (avoids paginating).
    open_prs = 0
    pr_resp = requests.get(
        f"https://api.github.com/repos/{owner_name}/{repo_name}/pulls",
        headers=headers,
        params={"state": "open", "per_page": 1},
        timeout=30,
    )
    if pr_resp.status_code == 200:
        link = pr_resp.headers.get("Link", "")
        if 'rel="last"' in link:
            match = re.search(r"page=(\d+)>; rel=\"last\"", link)
            if match:
                open_prs = int(match.group(1))
        else:
            try:
                open_prs = len(pr_resp.json())
            except Exception:
                open_prs = 0
    open_issues = max(0, total_open - open_prs)

    def _get_dependabot():
        r = requests.get(
            f"https://api.github.com/repos/{owner_name}/{repo_name}/dependabot/alerts",
            headers=headers,
            params={"state": "open", "per_page": 100},
            timeout=30,
        )
        enabled = r.status_code == 200
        return (r.json() if enabled else []), enabled

    def _get_code_scanning():
        r = requests.get(
            f"https://api.github.com/repos/{owner_name}/{repo_name}/code-scanning/alerts",
            headers=headers,
            params={"state": "open", "per_page": 100},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json(), True
        # 403 typically means GHAS isn't entitled; treat as "enabled but empty"
        # so we don't show an "enable" button the user can't actually use.
        if r.status_code == 403:
            return [], True
        try:
            msg = r.json().get("message", "").lower()
        except Exception:
            msg = ""
        if "no analysis found" in msg:
            return [], True
        return [], False

    def _get_advisories():
        r = requests.get(
            f"https://api.github.com/repos/{owner_name}/{repo_name}/security-advisories",
            headers=headers,
            params={"per_page": 100},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return [
                    a
                    for a in data
                    if a.get("state") not in ("published", "closed", "withdrawn")
                ]
        return []

    with ThreadPoolExecutor(max_workers=3) as pool:
        f1 = pool.submit(_get_dependabot)
        f2 = pool.submit(_get_code_scanning)
        f3 = pool.submit(_get_advisories)
        dependabot, dependabot_enabled = f1.result()
        code_scanning, code_scanning_enabled = f2.result()
        advisories = f3.result()

    # 404s on dependabot/code-scanning for non-admins mean "no permission",
    # not "not enabled"; only flag a feature as off if the user could fix it.
    if not is_admin:
        dependabot_enabled = True
        code_scanning_enabled = True

    if isinstance(dependabot, dict):
        dependabot = []
    if isinstance(code_scanning, dict):
        code_scanning = []

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for alert in dependabot:
        sev = (
            (alert.get("security_vulnerability", {}) or {}).get("severity", "").lower()
        )
        if not sev:
            sev = (alert.get("security_advisory", {}) or {}).get("severity", "").lower()
        if sev in severity_counts:
            severity_counts[sev] += 1
    for adv in advisories:
        adv_sev = (adv.get("severity") or "").lower()
        if adv_sev in severity_counts:
            severity_counts[adv_sev] += 1

    total_vulns = len(dependabot) + len(code_scanning) + len(advisories)
    updated_at = repo.get("updated_at", "")

    return {
        "full_name": full_name,
        "owner": owner_name,
        "name": repo_name,
        "html_url": repo["html_url"],
        "description": repo.get("description", "") or "",
        "language": repo.get("language", "") or "",
        "updated_at": updated_at,
        "updated_at_display": _format_relative_time(updated_at),
        "open_issues": open_issues,
        "open_prs": open_prs,
        "dependabot_count": len(dependabot),
        "code_scanning_count": len(code_scanning),
        "advisory_count": len(advisories),
        "severity": severity_counts,
        "total_vulns": total_vulns,
        "visibility": repo.get("visibility", "public"),
        "default_branch": repo.get("default_branch", "main"),
        "fork": repo.get("fork", False),
        "stars": repo.get("stargazers_count", 0),
        "is_admin": is_admin,
        "dependabot_enabled": dependabot_enabled,
        "code_scanning_enabled": code_scanning_enabled,
    }


def _build_repo_data(token: str) -> List[Dict[str, Any]]:
    raw = _fetch_user_repos(token)
    out: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_fetch_repo_security, token, r) for r in raw]
        for fut in futures:
            try:
                out.append(fut.result())
            except Exception as exc:
                logging.warning("github repos: per-repo fetch failed: %s", exc)
    # Vulnerable repos first (highest count first), then clean repos by recency.
    vuln = [r for r in out if r["total_vulns"] > 0]
    clean = [r for r in out if r["total_vulns"] == 0]
    vuln.sort(key=lambda r: -r["total_vulns"])
    clean.sort(key=lambda r: r["updated_at"], reverse=True)
    return vuln + clean


def _refresh_user_cache(user_id: str, token: str) -> Tuple[List[Dict[str, Any]], str]:
    data = _build_repo_data(token)
    now_iso = datetime.now(timezone.utc).isoformat()
    with _REPO_CACHE_LOCK:
        _REPO_CACHE[user_id] = {"repos": data, "last_updated": now_iso}
    return data, now_iso


def _get_user_cache(user_id: str, token: str) -> Tuple[List[Dict[str, Any]], str]:
    with _REPO_CACHE_LOCK:
        entry = _REPO_CACHE.get(user_id)
        if entry and entry.get("last_updated"):
            try:
                last = datetime.fromisoformat(entry["last_updated"])
                age = (datetime.now(timezone.utc) - last).total_seconds()
                if age < _REPO_CACHE_TTL_SECS:
                    return entry["repos"], entry["last_updated"]
            except Exception:
                pass
    return _refresh_user_cache(user_id, token)


def _update_cache_field(user_id: str, full_name: str, field: str, value: Any) -> None:
    with _REPO_CACHE_LOCK:
        entry = _REPO_CACHE.get(user_id)
        if not entry:
            return
        for r in entry["repos"]:
            if r["full_name"] == full_name:
                r[field] = value
                break


def _drop_from_cache(user_id: str, full_name: str) -> None:
    with _REPO_CACHE_LOCK:
        entry = _REPO_CACHE.get(user_id)
        if not entry:
            return
        entry["repos"] = [r for r in entry["repos"] if r["full_name"] != full_name]


# ---- alert-detail helpers (per-alert flattening, mirrors Flask app) ----


def _alert_severity(alert_type: str, alert: Dict[str, Any]) -> str:
    if alert_type == "dependabot":
        sev = (alert.get("security_vulnerability", {}) or {}).get("severity", "")
        if not sev:
            sev = (alert.get("security_advisory", {}) or {}).get("severity", "")
        return sev or "unknown"
    if alert_type == "code_scanning":
        rule = alert.get("rule", {}) or {}
        return (
            rule.get("security_severity_level", "")
            or rule.get("severity", "")
            or "unknown"
        )
    if alert_type == "advisory":
        return alert.get("severity", "") or "unknown"
    return "unknown"


def _alert_summary(alert_type: str, alert: Dict[str, Any]) -> str:
    if alert_type == "dependabot":
        return (alert.get("security_advisory", {}) or {}).get(
            "summary", "Dependabot Alert"
        )
    if alert_type == "code_scanning":
        return (alert.get("rule", {}) or {}).get("description", "Code Scanning Alert")
    if alert_type == "advisory":
        return alert.get("summary", "Security Advisory")
    return "Security Alert"


def _flatten_alert(alert_type: str, alert: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one raw GitHub alert into the shape our UI consumes."""
    item: Dict[str, Any] = {"type": alert_type, "html_url": alert.get("html_url", "")}
    if alert_type == "dependabot":
        advisory = alert.get("security_advisory", {}) or {}
        vuln = alert.get("security_vulnerability", {}) or {}
        dep = alert.get("dependency", {}) or {}
        cvss = advisory.get("cvss", {}) or {}
        item["severity"] = vuln.get("severity", "") or advisory.get("severity", "")
        item["summary"] = advisory.get("summary", "")
        item["description"] = advisory.get("description", "")
        item["package"] = (vuln.get("package", {}) or {}).get("name", "")
        item["ecosystem"] = (vuln.get("package", {}) or {}).get("ecosystem", "")
        item["vulnerable_range"] = vuln.get("vulnerable_version_range", "")
        item["patched_version"] = (vuln.get("first_patched_version") or {}).get(
            "identifier", ""
        )
        item["cve"] = ""
        for ident in advisory.get("identifiers", []) or []:
            if ident.get("type") == "CVE":
                item["cve"] = ident.get("value", "")
                break
        item["ghsa"] = advisory.get("ghsa_id", "")
        item["manifest_path"] = dep.get("manifest_path", "")
        item["scope"] = dep.get("scope", "")
        item["relationship"] = dep.get("relationship", "")
        item["cvss_score"] = cvss.get("score", "")
        item["cvss_vector"] = cvss.get("vector_string", "")
        cwes = advisory.get("cwes", []) or []
        item["cwes"] = [f"{c.get('cwe_id', '')}: {c.get('name', '')}" for c in cwes]
        item["published_at"] = advisory.get("published_at", "")
        item["created_at"] = alert.get("created_at", "")
    elif alert_type == "code_scanning":
        rule = alert.get("rule", {}) or {}
        item["severity"] = rule.get("security_severity_level", "") or rule.get(
            "severity", ""
        )
        item["summary"] = rule.get("description", "")
        item["full_description"] = rule.get("full_description", "")
        instance = alert.get("most_recent_instance", {}) or {}
        item["description"] = (instance.get("message", {}) or {}).get("text", "")
        item["tool"] = (alert.get("tool", {}) or {}).get("name", "")
        item["tool_version"] = (alert.get("tool", {}) or {}).get("version", "")
        item["rule_id"] = rule.get("id", "")
        item["rule_tags"] = rule.get("tags", [])
        loc = instance.get("location", {}) or {}
        item["location"] = ""
        item["location_path"] = loc.get("path", "")
        item["location_start"] = loc.get("start_line", "")
        item["location_end"] = loc.get("end_line", "")
        item["location_start_col"] = loc.get("start_column", "")
        item["location_end_col"] = loc.get("end_column", "")
        if loc.get("path"):
            item["location"] = f"{loc['path']}:{loc.get('start_line', '')}"
            if loc.get("end_line") and loc.get("end_line") != loc.get("start_line"):
                item["location"] += f"–{loc['end_line']}"
        item["classifications"] = instance.get("classifications", [])
        item["ref"] = instance.get("ref", "")
        item["created_at"] = alert.get("created_at", "")
    elif alert_type == "advisory":
        item["html_url"] = alert.get("html_url", "")
        item["severity"] = alert.get("severity", "")
        item["summary"] = alert.get("summary", "")
        item["description"] = alert.get("description", "")
        item["ghsa"] = alert.get("ghsa_id", "")
        item["state"] = alert.get("state", "")
        item["created_at"] = alert.get("created_at", "")
        item["updated_at"] = alert.get("updated_at", "")
        item["cve"] = ""
        for ident in alert.get("identifiers", []) or []:
            if ident.get("type") == "CVE":
                item["cve"] = ident.get("value", "")
                break
        cvss_v3 = (alert.get("cvss_severities", {}) or {}).get("cvss_v3", {}) or {}
        item["cvss_score"] = cvss_v3.get("score", "")
        item["cvss_vector"] = cvss_v3.get("vector_string", "")
        cwes = alert.get("cwes", []) or []
        item["cwes"] = [f"{c.get('cwe_id', '')}: {c.get('name', '')}" for c in cwes]
        vulns = alert.get("vulnerabilities", []) or []
        if vulns:
            pkg = vulns[0].get("package", {}) or {}
            item["package"] = pkg.get("name", "")
            item["ecosystem"] = pkg.get("ecosystem", "")
            item["vulnerable_range"] = vulns[0].get("vulnerable_version_range", "")
            item["patched_version"] = vulns[0].get("patched_versions", "")
        author = alert.get("author", {}) or {}
        item["reporter"] = author.get("login", "")
    return item


def _fetch_alerts(token: str, owner: str, repo: str) -> List[Dict[str, Any]]:
    headers = _gh_headers(token)
    alerts: List[Tuple[str, Dict[str, Any]]] = []

    def _fetch(alert_type: str, url: str) -> List[Tuple[str, Dict[str, Any]]]:
        r = requests.get(
            url, headers=headers, params={"state": "open", "per_page": 100}, timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return [(alert_type, a) for a in data]
        return []

    def _fetch_advisories() -> List[Tuple[str, Dict[str, Any]]]:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/security-advisories",
            headers=headers,
            params={"per_page": 100},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return [
                    ("advisory", a)
                    for a in data
                    if a.get("state") not in ("published", "closed", "withdrawn")
                ]
        return []

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(
                _fetch,
                "dependabot",
                f"https://api.github.com/repos/{owner}/{repo}/dependabot/alerts",
            ),
            pool.submit(
                _fetch,
                "code_scanning",
                f"https://api.github.com/repos/{owner}/{repo}/code-scanning/alerts",
            ),
            pool.submit(_fetch_advisories),
        ]
        for f in futures:
            alerts.extend(f.result())
    return alerts


# ---- AI streaming: forward to local /v1/chat/completions over HTTP ----


def _agixt_base_url() -> str:
    """Local AGiXT URL we self-call for chat completions. Defaults to the
    in-process listener so we don't have to round-trip through any proxy."""
    return getenv("AGIXT_INTERNAL_URL") or "http://localhost:7437"


def _stream_chat_completions(authorization: str, payload: Dict[str, Any]):
    """Forward an OpenAI-style chat-completions request to the local AGiXT
    server using the caller's JWT, and pass the SSE stream through
    untouched. Mirrors the streaming behavior of the standalone Flask app
    (`_stream_agixt`) without the WS conversation polling — clients that
    want execution-message live updates can subscribe to
    `/v1/conversation/{id}/stream` themselves."""
    base = _agixt_base_url()
    url = f"{base}/v1/chat/completions"
    headers = {
        "Authorization": authorization or "",
        "Content-Type": "application/json",
    }

    def _gen():
        try:
            with requests.post(
                url, headers=headers, json=payload, stream=True, timeout=3600
            ) as resp:
                if resp.status_code != 200:
                    logging.warning(
                        "github: AGiXT chat stream returned %s: %s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    yield f"data: {json.dumps({'type': 'error', 'content': f'AGiXT returned {resp.status_code}.'})}\n\n"
                    return
                for raw in resp.iter_lines(decode_unicode=False):
                    if raw is None:
                        continue
                    line = (
                        raw.decode("utf-8", errors="replace")
                        if isinstance(raw, (bytes, bytearray))
                        else raw
                    )
                    if not line:
                        # Preserve SSE event boundaries (blank line between events).
                        yield "\n"
                        continue
                    yield line + "\n"
        except Exception as exc:
            logging.exception("github: AGiXT chat stream proxy failed")
            yield f"data: {json.dumps({'type': 'error', 'content': 'AGiXT chat stream failed.'})}\n\n"

    return _gen()


# ===========================================================================
# Extension class
# ===========================================================================


class github(Extensions):
    """
    The GitHub extension enables the AI agent to interact with the user's GitHub
    repositories via the workspace terminal using ``git`` and the GitHub CLI (``gh``).

    When the user connects their GitHub account through OAuth, the access token is
    automatically injected into the workspace terminal environment as ``GITHUB_TOKEN``
    and ``GH_TOKEN``, so the agent can run authenticated ``git`` and ``gh`` commands
    without any manual configuration.

    The extension also exposes a REST router (`/v1/github/...`) that powers the
    desktop client's "Repos" dashboard tab — read-only repo lists with security
    alert counts, inline issue/PR/alert browsing, and AI-driven actions (fix
    issue, review PR, fix vulnerabilities, security audit) that use the user's
    own AGiXT JWT and OAuth token.
    """

    CATEGORY = "Development & Code"
    friendly_name = "GitHub"

    def __init__(self, **kwargs):
        self.GITHUB_USERNAME = kwargs.get("GITHUB_USERNAME", "")
        self.GITHUB_API_KEY = kwargs.get("GITHUB_API_KEY", "") or kwargs.get(
            "GITHUB_ACCESS_TOKEN", ""
        )
        self.commands = {"List GitHub Repositories": self.list_repositories}

        self.router = APIRouter(prefix="/v1/github", tags=["GitHub"])
        self._register_routes()

    # List repositories for the authenticated user
    async def list_repositories(self):
        """List repositories for the authenticated user using the GitHub API."""
        if not self.GITHUB_API_KEY:
            logging.error("GitHub API key not configured")
            return []
        headers = {"Authorization": f"token {self.GITHUB_API_KEY}"}
        response = requests.get("https://api.github.com/user/repos", headers=headers)
        if response.status_code != 200:
            logging.error(f"Error listing GitHub repositories: {response.text}")
            return []
        return response.json()

    def get_extension_context(self) -> str:
        """Provide context guiding the agent to use git/gh CLI in the workspace terminal."""
        if not self.GITHUB_API_KEY:
            return ""
        username_note = ""
        if self.GITHUB_USERNAME:
            username_note = (
                f"The authenticated GitHub user is **{self.GITHUB_USERNAME}**.\n\n"
            )
        return (
            "## GitHub Integration\n\n"
            + username_note
            + "The user's GitHub account is connected. The workspace terminal has `git` and "
            "the GitHub CLI (`gh`) available with the user's credentials automatically "
            "configured via environment variables (`GITHUB_TOKEN` / `GH_TOKEN`). Use the "
            "**Use Terminal in Workspace** command to run any GitHub operation.\n\n"
            "### Common operations\n\n"
            "**Repositories:**\n"
            "- `gh repo list` — list the user's repos\n"
            "- `gh repo clone owner/repo` — clone a repo (works for private repos)\n"
            "- `gh repo create name --public` — create a new repo\n"
            "- `gh repo view owner/repo` — view repo details\n\n"
            "**Issues:**\n"
            "- `gh issue list -R owner/repo` — list issues\n"
            "- `gh issue view NUMBER -R owner/repo` — view an issue\n"
            "- `gh issue create -R owner/repo --title '...' --body '...'` — create an issue\n"
            "- `gh issue close NUMBER -R owner/repo` — close an issue\n"
            "- `gh issue comment NUMBER -R owner/repo --body '...'` — comment on an issue\n\n"
            "**Pull Requests:**\n"
            "- `gh pr list -R owner/repo` — list PRs\n"
            "- `gh pr view NUMBER -R owner/repo` — view a PR\n"
            "- `gh pr create -R owner/repo --title '...' --body '...'` — create a PR\n"
            "- `gh pr merge NUMBER -R owner/repo` — merge a PR\n"
            "- `gh pr diff NUMBER -R owner/repo` — view PR diff\n\n"
            "**Code & Content:**\n"
            "- `gh api /repos/owner/repo/contents/path` — get file contents via API\n"
            "- `git clone https://github.com/owner/repo && cd repo` — clone and work locally\n"
            "- `git add . && git commit -m '...' && git push` — commit and push changes\n\n"
            "**Other:**\n"
            "- `gh api /user` — get authenticated user info\n"
            "- `gh api /repos/owner/repo/commits` — list commits\n"
            "- `gh api /repos/owner/repo/security-advisories` — list security advisories\n\n"
            "Authentication is handled automatically. Do not ask the user for tokens or credentials."
        )

    # ----------------------------------------------------------------------
    # Router setup — repo dashboard endpoints
    # ----------------------------------------------------------------------

    def _register_routes(self) -> None:
        router = self.router

        def _require_token(authorization: Optional[str]) -> Tuple[MagicalAuth, str]:
            auth = MagicalAuth(token=authorization)
            if not auth.user_id:
                raise HTTPException(status_code=401, detail="Invalid token")
            tok = _gh_token_for_user(auth.user_id)
            if not tok:
                raise HTTPException(
                    status_code=403, detail="GitHub OAuth not connected"
                )
            return auth, tok

        @router.get("/repos", summary="List user repos with security counts")
        async def list_repos(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            auth, token = _require_token(authorization)
            repos, last_updated = _get_user_cache(auth.user_id, token)
            return {"repos": repos, "last_updated": last_updated}

        @router.post("/repos/refresh", summary="Force-refresh the repo cache")
        async def refresh_repos(
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            auth, token = _require_token(authorization)
            repos, last_updated = _refresh_user_cache(auth.user_id, token)
            return {"status": "ok", "count": len(repos), "last_updated": last_updated}

        @router.post("/repos/{owner}/{repo}/archive", summary="Archive a repo")
        async def archive_repo(
            owner: str,
            repo: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            auth, token = _require_token(authorization)
            resp = requests.patch(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=_gh_headers(token),
                json={"archived": True},
                timeout=30,
            )
            if resp.status_code == 200:
                _drop_from_cache(auth.user_id, f"{owner}/{repo}")
                return {"status": "ok", "message": f"{owner}/{repo} archived"}
            try:
                msg = resp.json().get("message", "Failed to archive")
            except Exception:
                msg = resp.text[:300]
            return JSONResponse({"error": msg}, status_code=resp.status_code)

        @router.post(
            "/repos/{owner}/{repo}/enable-security",
            summary="Enable a security feature on a repo",
        )
        async def enable_security(
            owner: str,
            repo: str,
            request: Request,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            auth, token = _require_token(authorization)
            try:
                body = await request.json()
            except Exception:
                body = {}
            feature = (body or {}).get("feature")
            if not feature:
                return JSONResponse({"error": "feature required"}, status_code=400)
            headers = _gh_headers(token)
            try:
                if feature == "dependabot":
                    resp = requests.put(
                        f"https://api.github.com/repos/{owner}/{repo}/vulnerability-alerts",
                        headers=headers,
                        timeout=30,
                    )
                    if resp.status_code == 204:
                        _update_cache_field(
                            auth.user_id, f"{owner}/{repo}", "dependabot_enabled", True
                        )
                        return {
                            "status": "ok",
                            "message": f"Dependabot enabled on {owner}/{repo}",
                        }
                elif feature == "code_scanning":
                    resp = requests.patch(
                        f"https://api.github.com/repos/{owner}/{repo}/code-scanning/default-setup",
                        headers=headers,
                        json={"state": "configured"},
                        timeout=30,
                    )
                    if resp.status_code in (200, 202):
                        _update_cache_field(
                            auth.user_id,
                            f"{owner}/{repo}",
                            "code_scanning_enabled",
                            True,
                        )
                        return {
                            "status": "ok",
                            "message": f"CodeQL enabled on {owner}/{repo}",
                        }
                else:
                    return JSONResponse(
                        {"error": f"Unknown feature: {feature}"}, status_code=400
                    )
                # If we fell through, surface GitHub's error.
                try:
                    msg = resp.json().get("message", "")
                except Exception:
                    msg = resp.text[:300]
                return JSONResponse(
                    {"error": msg or f"Failed ({resp.status_code})"},
                    status_code=resp.status_code,
                )
            except Exception as exc:
                logging.exception(
                    "github: failed to update repository security feature"
                )
                return JSONResponse(
                    {"error": "Failed to update repository security feature."},
                    status_code=500,
                )

        @router.get(
            "/repos/{owner}/{repo}/alerts",
            summary="Detailed security alerts for a repo",
        )
        async def get_alerts(
            owner: str,
            repo: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            _, token = _require_token(authorization)
            raw = _fetch_alerts(token, owner, repo)
            result = [_flatten_alert(t, a) for t, a in raw]
            sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "": 4}
            result.sort(key=lambda a: sev_order.get(a.get("severity", "").lower(), 4))
            return {"alerts": result, "total": len(result)}

        @router.get(
            "/repos/{owner}/{repo}/issues",
            summary="Open issues for a repo (PRs filtered out)",
        )
        async def get_issues(
            owner: str,
            repo: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            _, token = _require_token(authorization)
            raw = _gh_get_paginated(
                f"https://api.github.com/repos/{owner}/{repo}/issues",
                token,
                {"state": "open"},
            )
            issues = [i for i in raw if "pull_request" not in i]
            out = []
            for issue in issues:
                out.append(
                    {
                        "number": issue["number"],
                        "title": issue.get("title", ""),
                        "html_url": issue.get("html_url", ""),
                        "state": issue.get("state", ""),
                        "created_at": issue.get("created_at", ""),
                        "updated_at": issue.get("updated_at", ""),
                        "user": (issue.get("user") or {}).get("login", ""),
                        "labels": [
                            {"name": l.get("name", ""), "color": l.get("color", "ccc")}
                            for l in issue.get("labels", []) or []
                        ],
                        "assignees": [
                            (a or {}).get("login", "")
                            for a in issue.get("assignees", []) or []
                        ],
                        "comments": issue.get("comments", 0),
                        "body": (issue.get("body") or "")[:1000],
                        "milestone": (issue.get("milestone") or {}).get("title", ""),
                    }
                )
            return {"issues": out, "total": len(out)}

        @router.get(
            "/repos/{owner}/{repo}/pulls", summary="Open pull requests for a repo"
        )
        async def get_pulls(
            owner: str,
            repo: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            _, token = _require_token(authorization)
            raw = _gh_get_paginated(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                token,
                {"state": "open"},
            )
            out = []
            for pr in raw:
                out.append(
                    {
                        "number": pr["number"],
                        "title": pr.get("title", ""),
                        "html_url": pr.get("html_url", ""),
                        "state": pr.get("state", ""),
                        "draft": pr.get("draft", False),
                        "created_at": pr.get("created_at", ""),
                        "updated_at": pr.get("updated_at", ""),
                        "user": (pr.get("user") or {}).get("login", ""),
                        "labels": [
                            {"name": l.get("name", ""), "color": l.get("color", "ccc")}
                            for l in pr.get("labels", []) or []
                        ],
                        "head_ref": (pr.get("head") or {}).get("ref", ""),
                        "base_ref": (pr.get("base") or {}).get("ref", ""),
                        "comments": (pr.get("comments", 0) or 0)
                        + (pr.get("review_comments", 0) or 0),
                        "additions": pr.get("additions", 0),
                        "deletions": pr.get("deletions", 0),
                        "changed_files": pr.get("changed_files", 0),
                        "body": (pr.get("body") or "")[:1000],
                        "mergeable_state": pr.get("mergeable_state", ""),
                    }
                )
            return {"pulls": out, "total": len(out)}

        @router.post(
            "/repos/{owner}/{repo}/pulls/{pr_number}/merge",
            summary="Merge a pull request",
        )
        async def merge_pull(
            owner: str,
            repo: str,
            pr_number: int,
            request: Request,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            auth, token = _require_token(authorization)
            try:
                body = await request.json()
            except Exception:
                body = {}
            method = (body or {}).get("merge_method", "merge")
            if method not in ("merge", "squash", "rebase"):
                return JSONResponse({"error": "Invalid merge method"}, status_code=400)
            headers = _gh_headers(token)
            pr_resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=headers,
                timeout=30,
            )
            if pr_resp.status_code != 200:
                return JSONResponse(
                    {"error": "Failed to fetch PR details"},
                    status_code=pr_resp.status_code,
                )
            pr = pr_resp.json()
            resp = requests.put(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge",
                headers=headers,
                json={
                    "merge_method": method,
                    "commit_title": f"Merge PR #{pr_number}: {pr.get('title', '')}",
                },
                timeout=30,
            )
            if resp.status_code == 200:
                # Decrement open PR count in the user's cache so the dashboard
                # updates immediately without waiting for a full refresh.
                with _REPO_CACHE_LOCK:
                    entry = _REPO_CACHE.get(auth.user_id)
                    if entry:
                        for r in entry["repos"]:
                            if r["full_name"] == f"{owner}/{repo}":
                                r["open_prs"] = max(0, r.get("open_prs", 1) - 1)
                                break
                data = resp.json()
                return {
                    "status": "ok",
                    "message": data.get("message", "Pull request merged"),
                    "sha": data.get("sha", ""),
                }
            try:
                msg = resp.json().get("message", "Merge failed")
            except Exception:
                msg = resp.text[:300]
            return JSONResponse({"error": msg}, status_code=resp.status_code)

        @router.get(
            "/repos/{owner}/{repo}/pulls/{pr_number}/files",
            summary="File diffs for a pull request",
        )
        async def get_pr_files(
            owner: str,
            repo: str,
            pr_number: int,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            _, token = _require_token(authorization)
            files = _gh_get_paginated(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files",
                token,
            )
            # GitHub omits per-file `patch` for very large diffs; fall back to
            # the unified diff and re-split it ourselves.
            missing = any("patch" not in f for f in files)
            diff_patches: Dict[str, str] = {}
            if missing:
                diff_resp = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                    headers={
                        **_gh_headers(token),
                        "Accept": "application/vnd.github.v3.diff",
                    },
                    timeout=60,
                )
                if diff_resp.status_code == 200:
                    diff_patches = _parse_unified_diff(diff_resp.text)

            out = []
            for f in files:
                patch = f.get("patch", "")
                if not patch:
                    patch = diff_patches.get(f.get("filename", ""), "")
                out.append(
                    {
                        "filename": f.get("filename", ""),
                        "status": f.get("status", ""),
                        "additions": f.get("additions", 0),
                        "deletions": f.get("deletions", 0),
                        "changes": f.get("changes", 0),
                        "patch": patch,
                        "blob_url": f.get("blob_url", ""),
                        "raw_url": f.get("raw_url", ""),
                        "previous_filename": f.get("previous_filename", ""),
                    }
                )
            return {"files": out, "total": len(out)}

        # ---- AI-driven endpoints (SSE) -----------------------------------

        @router.post(
            "/repos/{owner}/{repo}/issues/{issue_number}/fix",
            summary="Have the XT agent fix a GitHub issue (SSE)",
        )
        async def fix_issue(
            owner: str,
            repo: str,
            issue_number: int,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            _, token = _require_token(authorization)
            headers = _gh_headers(token)
            resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}",
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                return JSONResponse(
                    {"error": "Failed to fetch issue"}, status_code=resp.status_code
                )
            issue = resp.json()
            comments_resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments",
                headers=headers,
                params={"per_page": 50},
                timeout=30,
            )
            comments = comments_resp.json() if comments_resp.status_code == 200 else []

            lines = [
                f"# Issue #{issue_number}: {issue.get('title', '')}",
                "",
                f"**Repository:** https://github.com/{owner}/{repo}",
                f"**URL:** {issue.get('html_url', '')}",
                f"**Author:** {(issue.get('user') or {}).get('login', 'Unknown')}",
                f"**Created:** {issue.get('created_at', '')}",
                f"**Labels:** {', '.join(l.get('name', '') for l in issue.get('labels', []) or [])}",
                "",
                "## Description",
                "",
                issue.get("body") or "No description provided.",
                "",
            ]
            if comments:
                lines.append("## Comments")
                lines.append("")
                for c in comments[:20]:
                    lines.append(
                        f"### {(c.get('user') or {}).get('login', 'Unknown')} ({c.get('created_at', '')})"
                    )
                    lines.append("")
                    lines.append((c.get("body") or "")[:2000])
                    lines.append("")
            issue_md = "\n".join(lines)

            conversation_name = (
                f"Fix Issue #{issue_number} - {owner}/{repo} - "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            )
            file_b64 = base64.b64encode(issue_md.encode("utf-8")).decode("utf-8")
            file_data_uri = f"data:text/markdown;base64,{file_b64}"
            prompt_text = (
                f"I've attached an issue from the GitHub repository `{owner}/{repo}`. "
                f"Issue #{issue_number}: {issue.get('title', '')}. "
                f"IMPORTANT: Do NOT commit directly to the main branch. Create a new branch "
                f"named `fix/issue-{issue_number}` from the default branch, make your changes there, "
                f"then open a pull request back to the default branch. "
                f"Please review the attached issue details and fix it. "
                f"Analyze the issue description and any comments, then implement the necessary changes "
                f"to resolve this issue in the repository. If GitHub Copilot is available, ask it to resolve the issue."
            )
            payload = {
                "model": "XT",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "file_url",
                                "file_url": {"url": file_data_uri},
                                "file_name": f"issue_{issue_number}.md",
                            },
                        ],
                    }
                ],
                "stream": True,
                "user": conversation_name,
            }
            return StreamingResponse(
                _stream_chat_completions(authorization, payload),
                media_type="text/event-stream",
            )

        @router.post(
            "/repos/{owner}/{repo}/pulls/{pr_number}/review",
            summary="Have the XT agent review a pull request (SSE)",
        )
        async def review_pr(
            owner: str,
            repo: str,
            pr_number: int,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            _, token = _require_token(authorization)
            headers = _gh_headers(token)
            resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                return JSONResponse(
                    {"error": "Failed to fetch PR"}, status_code=resp.status_code
                )
            pr = resp.json()

            diff_resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                headers={**headers, "Accept": "application/vnd.github.v3.diff"},
                timeout=30,
            )
            diff_text = (
                diff_resp.text[:50000]
                if diff_resp.status_code == 200
                else "Diff not available"
            )

            comments_resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                headers=headers,
                params={"per_page": 50},
                timeout=30,
            )
            comments = comments_resp.json() if comments_resp.status_code == 200 else []
            ic_resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
                headers=headers,
                params={"per_page": 50},
                timeout=30,
            )
            issue_comments = ic_resp.json() if ic_resp.status_code == 200 else []

            lines = [
                f"# Pull Request #{pr_number}: {pr.get('title', '')}",
                "",
                f"**Repository:** https://github.com/{owner}/{repo}",
                f"**URL:** {pr.get('html_url', '')}",
                f"**Author:** {(pr.get('user') or {}).get('login', 'Unknown')}",
                f"**Branch:** {(pr.get('head') or {}).get('ref', '')} → {(pr.get('base') or {}).get('ref', '')}",
                f"**Created:** {pr.get('created_at', '')}",
                f"**Draft:** {'Yes' if pr.get('draft') else 'No'}",
                f"**Changed Files:** {pr.get('changed_files', 0)} (+{pr.get('additions', 0)} -{pr.get('deletions', 0)})",
                "",
                "## Description",
                "",
                pr.get("body") or "No description provided.",
                "",
                "## Diff",
                "",
                "```diff",
                diff_text,
                "```",
                "",
            ]
            if comments:
                lines.append("## Review Comments")
                lines.append("")
                for c in comments[:30]:
                    path = c.get("path", "")
                    line_num = c.get("line") or c.get("original_line", "")
                    lines.append(
                        f"### {(c.get('user') or {}).get('login', 'Unknown')} on {path}:{line_num}"
                    )
                    lines.append("")
                    lines.append((c.get("body") or "")[:2000])
                    lines.append("")
            if issue_comments:
                lines.append("## Conversation")
                lines.append("")
                for c in issue_comments[:20]:
                    lines.append(
                        f"### {(c.get('user') or {}).get('login', 'Unknown')} ({c.get('created_at', '')})"
                    )
                    lines.append("")
                    lines.append((c.get("body") or "")[:2000])
                    lines.append("")

            pr_md = "\n".join(lines)
            conversation_name = (
                f"Review PR #{pr_number} - {owner}/{repo} - "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            )
            file_b64 = base64.b64encode(pr_md.encode("utf-8")).decode("utf-8")
            file_data_uri = f"data:text/markdown;base64,{file_b64}"
            prompt_text = (
                f"I've attached a pull request from the GitHub repository `{owner}/{repo}`. "
                f"PR #{pr_number}: {pr.get('title', '')}. "
                f"Please perform a thorough code review of this pull request. "
                f"Review the diff, check for bugs, security issues, performance concerns, "
                f"and code quality. Provide your review as a GitHub PR review comment with GitHub Copilot if available. If you identify any issues, suggest specific changes to fix them."
            )
            payload = {
                "model": "XT",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "file_url",
                                "file_url": {"url": file_data_uri},
                                "file_name": f"pr_{pr_number}_review.md",
                            },
                        ],
                    }
                ],
                "stream": True,
                "user": conversation_name,
            }
            return StreamingResponse(
                _stream_chat_completions(authorization, payload),
                media_type="text/event-stream",
            )

        @router.post(
            "/repos/{owner}/{repo}/fix-vulns",
            summary="Have the XT agent fix all open security alerts (SSE)",
        )
        async def fix_vulns(
            owner: str,
            repo: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            _, token = _require_token(authorization)
            alerts = _fetch_alerts(token, owner, repo)
            if not alerts:
                return JSONResponse(
                    {"error": "No open alerts found for this repo"}, status_code=404
                )
            vuln_md = _build_vulnerabilities_md(owner, repo, alerts)
            conversation_name = (
                f"Fix Vulnerabilities - {owner}/{repo} - "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            )
            file_b64 = base64.b64encode(vuln_md.encode("utf-8")).decode("utf-8")
            file_data_uri = f"data:text/markdown;base64,{file_b64}"
            prompt_text = (
                f"I've attached a file called `vulnerabilities.md` that contains {len(alerts)} "
                f"security vulnerabilities for the GitHub repository `{owner}/{repo}`. "
                f"IMPORTANT: Do NOT commit directly to the main branch. Create a new branch "
                f"named `fix/security-vulnerabilities` from the default branch, make all changes there, "
                f"then open a pull request back to the default branch. "
                f"Please review the attached vulnerabilities.md and fix each vulnerability listed in it. "
                f"For dependency vulnerabilities, update the affected packages "
                f"to their patched versions. For code scanning issues, fix the code at the specified locations. "
                f"For security advisories (type 'advisory'), after fixing the underlying vulnerability, "
                f"close the advisory using the 'Close Github Security Advisory' command with the repo URL "
                f"and the GHSA ID listed for each advisory. "
                f"You can ask GitHub Copilot to help fix each one and tell it that it can also "
                f"reference `vulnerabilities.md` in the workspace and update it as issues are resolved. "
                f"Work through them systematically starting with critical and high severity issues first."
            )
            payload = {
                "model": "XT",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "file_url",
                                "file_url": {"url": file_data_uri},
                                "file_name": "vulnerabilities.md",
                            },
                        ],
                    }
                ],
                "stream": True,
                "user": conversation_name,
            }
            return StreamingResponse(
                _stream_chat_completions(authorization, payload),
                media_type="text/event-stream",
            )

        @router.post(
            "/repos/{owner}/{repo}/security-audit",
            summary="Run a comprehensive AI security audit (SSE)",
        )
        async def security_audit(
            owner: str,
            repo: str,
            user=Depends(verify_api_key),
            authorization: str = Header(None),
        ):
            _, token = _require_token(authorization)
            headers = _gh_headers(token)
            repo_resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=headers,
                timeout=30,
            )
            if repo_resp.status_code != 200:
                return JSONResponse(
                    {"error": "Failed to fetch repository"},
                    status_code=repo_resp.status_code,
                )
            repo_data = repo_resp.json()
            language = repo_data.get("language", "Unknown")
            default_branch = repo_data.get("default_branch", "main")
            audit_md = _build_security_audit_md(owner, repo, language, default_branch)
            conversation_name = (
                f"Security Audit - {owner}/{repo} - "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            )
            file_b64 = base64.b64encode(audit_md.encode("utf-8")).decode("utf-8")
            file_data_uri = f"data:text/markdown;base64,{file_b64}"
            prompt_text = (
                f"I've attached a comprehensive security audit checklist for the GitHub repository "
                f"`{owner}/{repo}` (primary language: {language}). "
                f"IMPORTANT: Do NOT commit directly to the `{default_branch}` branch. Create a new branch "
                f"named `fix/security-audit` from `{default_branch}`, make all changes there, "
                f"then open a pull request back to `{default_branch}`. "
                f"Please perform a thorough security audit of the entire codebase following the checklist "
                f"in the attached `security_audit.md` file. Examine every file for each vulnerability category. "
                f"If GitHub Copilot is available, ask it to investigate the codebase systematically for each "
                f"vulnerability type listed. For any issues found, fix them on the branch and include a detailed "
                f"summary in the pull request description."
            )
            payload = {
                "model": "XT",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "file_url",
                                "file_url": {"url": file_data_uri},
                                "file_name": "security_audit.md",
                            },
                        ],
                    }
                ],
                "stream": True,
                "user": conversation_name,
            }
            return StreamingResponse(
                _stream_chat_completions(authorization, payload),
                media_type="text/event-stream",
            )


# ---- markdown builders -----------------------------------------------------


def _parse_unified_diff(diff_text: str) -> Dict[str, str]:
    """Split a unified diff into per-file patches keyed by `b/` filename."""
    patches: Dict[str, str] = {}
    current_file: Optional[str] = None
    current_lines: List[str] = []
    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            if current_file and current_lines:
                patches[current_file] = "\n".join(current_lines)
            current_lines = []
            parts = line.split(maxsplit=3)
            target = parts[3] if len(parts) == 4 else ""
            current_file = target[2:] if target.startswith("b/") else None
        elif current_file and (line.startswith("@@") or current_lines):
            if line.startswith("---") or line.startswith("+++"):
                continue
            current_lines.append(line)
    if current_file and current_lines:
        patches[current_file] = "\n".join(current_lines)
    return patches


def _build_vulnerabilities_md(
    owner: str, repo: str, alerts: List[Tuple[str, Dict[str, Any]]]
) -> str:
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts = sorted(
        alerts,
        key=lambda x: sev_order.get(_alert_severity(x[0], x[1]).lower(), 4),
    )
    lines = [
        f"# Security Vulnerabilities for {owner}/{repo}",
        "",
        f"**Repository:** https://github.com/{owner}/{repo}",
        f"**Total Alerts:** {len(alerts)}",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "---",
        "",
    ]
    for i, (alert_type, alert) in enumerate(alerts, 1):
        sev = _alert_severity(alert_type, alert)
        lines.append(f"## {i}. [{sev.upper()}] {_alert_summary(alert_type, alert)}")
        lines.append("")
        lines.append(f"- **Type:** {alert_type.replace('_', ' ').title()}")
        lines.append(f"- **Severity:** {sev}")
        if alert_type == "dependabot":
            vuln = alert.get("security_vulnerability", {}) or {}
            advisory = alert.get("security_advisory", {}) or {}
            dep = alert.get("dependency", {}) or {}
            cvss = advisory.get("cvss", {}) or {}
            pkg = vuln.get("package", {}) or {}
            lines.append(f"- **Package:** {pkg.get('name', 'Unknown')}")
            lines.append(f"- **Ecosystem:** {pkg.get('ecosystem', 'Unknown')}")
            lines.append(
                f"- **Vulnerable Range:** {vuln.get('vulnerable_version_range', 'N/A')}"
            )
            patched = (vuln.get("first_patched_version") or {}).get(
                "identifier", "No patch available"
            )
            lines.append(f"- **Patched Version:** {patched}")
            if dep.get("manifest_path"):
                lines.append(f"- **Manifest File:** {dep['manifest_path']}")
            if dep.get("scope"):
                lines.append(f"- **Scope:** {dep['scope']}")
            if dep.get("relationship"):
                lines.append(f"- **Dependency Type:** {dep['relationship']}")
            if cvss.get("score"):
                lines.append(f"- **CVSS Score:** {cvss['score']}")
            if cvss.get("vector_string"):
                lines.append(f"- **CVSS Vector:** {cvss['vector_string']}")
            for ident in advisory.get("identifiers", []) or []:
                if ident.get("type") == "CVE":
                    lines.append(f"- **CVE:** {ident.get('value', '')}")
            lines.append(f"- **GHSA:** {advisory.get('ghsa_id', 'N/A')}")
            cwes = advisory.get("cwes", []) or []
            if cwes:
                cwe_strs = [f"{c.get('cwe_id', '')}: {c.get('name', '')}" for c in cwes]
                lines.append(f"- **CWEs:** {'; '.join(cwe_strs)}")
            desc = advisory.get("description", "")
            if desc:
                lines.append(f"- **Description:** {desc[:500]}")
            refs = advisory.get("references", []) or []
            if refs:
                lines.append("- **References:**")
                for ref in refs[:5]:
                    lines.append(f"  - {ref.get('url', '')}")
        elif alert_type == "code_scanning":
            rule = alert.get("rule", {}) or {}
            tool = alert.get("tool", {}) or {}
            tool_str = tool.get("name", "Unknown")
            if tool.get("version"):
                tool_str += f" v{tool['version']}"
            lines.append(f"- **Tool:** {tool_str}")
            lines.append(f"- **Rule:** {rule.get('id', 'N/A')}")
            if rule.get("tags"):
                lines.append(f"- **Tags:** {', '.join(rule['tags'][:10])}")
            instance = alert.get("most_recent_instance", {}) or {}
            loc = instance.get("location", {}) or {}
            if loc.get("path"):
                location_str = f"{loc['path']}:{loc.get('start_line', '')}"
                if loc.get("end_line") and loc.get("end_line") != loc.get("start_line"):
                    location_str += f"–{loc['end_line']}"
                if loc.get("start_column"):
                    location_str += f" (col {loc['start_column']}"
                    if loc.get("end_column"):
                        location_str += f"–{loc['end_column']}"
                    location_str += ")"
                lines.append(f"- **Location:** {location_str}")
            classifications = instance.get("classifications", []) or []
            if classifications:
                lines.append(f"- **Classifications:** {', '.join(classifications)}")
            if instance.get("ref"):
                lines.append(f"- **Branch:** {instance['ref']}")
            if rule.get("full_description"):
                lines.append(
                    f"- **Full Description:** {rule['full_description'][:500]}"
                )
            msg = (instance.get("message", {}) or {}).get("text", "")
            if msg:
                lines.append(f"- **Details:** {msg[:500]}")
        elif alert_type == "advisory":
            lines.append(f"- **GHSA:** {alert.get('ghsa_id', 'N/A')}")
            lines.append(f"- **State:** {alert.get('state', 'N/A')}")
            for ident in alert.get("identifiers", []) or []:
                if ident.get("type") == "CVE":
                    lines.append(f"- **CVE:** {ident.get('value', '')}")
            cvss_v3 = (alert.get("cvss_severities", {}) or {}).get("cvss_v3", {}) or {}
            if cvss_v3.get("score"):
                lines.append(f"- **CVSS Score:** {cvss_v3['score']}")
            if cvss_v3.get("vector_string"):
                lines.append(f"- **CVSS Vector:** {cvss_v3['vector_string']}")
            cwes = alert.get("cwes", []) or []
            if cwes:
                cwe_strs = [f"{c.get('cwe_id', '')}: {c.get('name', '')}" for c in cwes]
                lines.append(f"- **CWEs:** {'; '.join(cwe_strs)}")
            for v in alert.get("vulnerabilities", []) or []:
                pkg = v.get("package", {}) or {}
                lines.append(
                    f"- **Package:** {pkg.get('name', 'Unknown')} ({pkg.get('ecosystem', '')})"
                )
                if v.get("vulnerable_version_range"):
                    lines.append(
                        f"- **Vulnerable Range:** {v['vulnerable_version_range']}"
                    )
                if v.get("patched_versions"):
                    lines.append(f"- **Patched Version:** {v['patched_versions']}")
            desc = alert.get("description", "")
            if desc:
                lines.append(f"- **Description:** {desc[:800]}")
            author = alert.get("author", {}) or {}
            if author.get("login"):
                lines.append(f"- **Reported by:** {author['login']}")
        if alert.get("html_url"):
            lines.append(f"- **URL:** {alert['html_url']}")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "IMPORTANT: Do NOT commit directly to the main branch. Create a new branch "
            "named `fix/security-vulnerabilities` from the default branch, make all changes there, "
            "then open a pull request back to the default branch.",
            "",
            "Please fix all of the above vulnerabilities. For dependency vulnerabilities, "
            "update the affected packages to their patched versions. For code scanning issues, "
            "fix the code at the specified locations. For security advisories, review the reported "
            "vulnerability and implement the necessary code fixes to address them.",
        ]
    )
    return "\n".join(lines)


def _build_security_audit_md(
    owner: str, repo: str, language: str, default_branch: str
) -> str:
    return "\n".join(
        [
            f"# Security Audit for {owner}/{repo}",
            "",
            "## Instructions",
            "",
            f"IMPORTANT: Do NOT commit directly to the `{default_branch}` branch. Create a new branch "
            f"named `fix/security-audit` from `{default_branch}`, make all changes there, "
            f"then open a pull request back to `{default_branch}` with a summary of all findings and fixes.",
            "",
            "If GitHub Copilot is available, ask it to help investigate the codebase for each "
            "vulnerability category below. Have Copilot examine the source code thoroughly and "
            "identify any instances of these security issues. For each issue found, fix it on the branch.",
            "",
            f"**Repository:** https://github.com/{owner}/{repo}",
            f"**Primary Language:** {language}",
            f"**Default Branch:** {default_branch}",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "---",
            "",
            "## Vulnerability Categories to Audit",
            "",
            "Thoroughly review the entire codebase for the following security vulnerability categories. "
            "For each category, search for patterns, anti-patterns, and known vulnerable code constructs.",
            "",
            "### 1. Injection Attacks",
            "",
            "#### SQL Injection",
            "- Look for raw SQL queries constructed with string concatenation or f-strings",
            "- Check for use of unparameterized queries in database calls",
            "- Identify any ORM usage that falls back to raw SQL without proper escaping",
            "- Check stored procedures for dynamic SQL construction",
            "- Look for second-order SQL injection where stored data is later used in queries unsafely",
            "",
            "#### Command Injection",
            "- Search for `os.system()`, `subprocess.Popen()`, `subprocess.run()`, `subprocess.call()` with `shell=True`",
            "- Check for unsanitized user input passed to shell commands",
            "- Look for backtick execution or `eval()`/`exec()` with user-controlled input",
            "- Identify template engines executing system commands",
            "",
            "#### Code Injection",
            "- Look for `eval()`, `exec()`, `compile()` with user-controlled strings",
            "- Check for `Function()` constructor in JavaScript with dynamic input",
            "- Search for deserialization of untrusted data (`pickle.loads()`, `yaml.load()` without SafeLoader, `JSON.parse()` feeding `eval()`)",
            "- Look for dynamic imports or `__import__()` with user input",
            "",
            "#### LDAP Injection",
            "- Check for LDAP queries built with string concatenation from user input",
            "- Look for unescaped special characters in LDAP filter expressions",
            "",
            "#### XPath/XML Injection",
            "- Search for XML parsers without entity expansion disabled (XXE)",
            "- Check for XPath queries with unescaped user input",
            "- Look for XML parsers with `resolve_entities=True` or missing `defusedxml` usage",
            "",
            "### 2. Server-Side Request Forgery (SSRF)",
            "",
            "- Look for HTTP requests where the URL or any part of it is user-controlled",
            "- Check for URL redirect endpoints that fetch remote content",
            "- Identify webhook handlers that make outbound requests to user-supplied URLs",
            "- Look for image/file download features that accept URLs",
            "- Check for DNS rebinding vulnerabilities in URL validation",
            "- Verify that internal/private IP ranges (127.0.0.1, 10.x, 172.16-31.x, 192.168.x, 169.254.x) are blocked",
            "- Check for SSRF via protocol smuggling (file://, gopher://, dict://, etc.)",
            "",
            "### 3. Cross-Site Scripting (XSS)",
            "",
            "- Search for unsanitized user input rendered in HTML templates",
            "- Look for `innerHTML`, `outerHTML`, `document.write()`, `insertAdjacentHTML()` with user data",
            "- Check for template engines with auto-escaping disabled or `| safe` / `{!! !!}` / `<%- %>` usage",
            "- Identify DOM-based XSS through `location.hash`, `location.search`, `document.referrer`",
            "- Look for reflected XSS in error messages, search results, or URL parameters",
            "- Check for stored XSS in user-generated content (comments, profiles, messages)",
            "- Verify Content-Security-Policy headers are properly configured",
            "",
            "### 4. Broken Authentication & Session Management",
            "",
            "- Check for hardcoded credentials, API keys, tokens, or passwords in source code",
            "- Look for weak password hashing (MD5, SHA1, plain text storage)",
            "- Verify bcrypt/scrypt/argon2 is used for password storage",
            "- Check session tokens for sufficient entropy and secure cookie flags (HttpOnly, Secure, SameSite)",
            "- Look for session fixation vulnerabilities",
            "- Check for missing or weak CSRF protection on state-changing endpoints",
            "- Verify JWT tokens are validated properly (algorithm confusion, missing signature verification, expired token acceptance)",
            "- Look for insecure password reset flows",
            "",
            "### 5. Broken Access Control",
            "",
            "- Check for missing authorization checks on API endpoints",
            "- Look for Insecure Direct Object References (IDOR) where user IDs or resource IDs are guessable",
            "- Verify role-based access controls are enforced server-side, not just client-side",
            "- Check for privilege escalation paths (horizontal and vertical)",
            "- Look for directory traversal via `../` in file paths or URL parameters",
            "- Verify that API endpoints enforce proper scoping (users can only access their own data)",
            "- Check for CORS misconfigurations that could allow unauthorized cross-origin access",
            "",
            "### 6. Sensitive Data Exposure",
            "",
            "- Look for sensitive data logged in plaintext (passwords, tokens, SSNs, credit cards)",
            "- Check for missing encryption of data at rest or in transit",
            "- Verify TLS is enforced and HTTP Strict Transport Security (HSTS) is configured",
            "- Look for sensitive information in URL parameters (tokens, passwords)",
            "- Check for overly verbose error messages that reveal stack traces, database schemas, or internal paths",
            "- Verify PII is properly handled and not exposed in API responses unnecessarily",
            "- Look for secrets committed in version control (.env files, config files with credentials)",
            "",
            "### 7. Security Misconfiguration",
            "",
            "- Check for debug mode enabled in production configurations",
            "- Look for default credentials or admin panels left accessible",
            "- Verify security headers are present (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, CSP)",
            "- Check for open directory listings or exposed configuration files",
            "- Look for permissive CORS policies (`Access-Control-Allow-Origin: *` on sensitive endpoints)",
            "- Verify that unnecessary HTTP methods are disabled",
            "- Check for missing rate limiting on authentication and sensitive endpoints",
            "",
            "### 8. Insecure Deserialization",
            "",
            "- Look for `pickle.loads()`, `yaml.load()` (without SafeLoader), `marshal.loads()` on untrusted data",
            "- Check for Java deserialization (ObjectInputStream) with untrusted input",
            "- Look for JSON deserialization that feeds into `eval()` or dynamic object creation",
            "- Check for XML deserialization vulnerabilities (XML bombs, entity expansion)",
            "",
            "### 9. Using Components with Known Vulnerabilities",
            "",
            "- Check dependency files (requirements.txt, package.json, Gemfile, go.mod, Cargo.toml) for outdated packages",
            "- Look for pinned versions of packages with known CVEs",
            "- Check for vendored/copied library code that may be outdated",
            "- Verify that dependency lock files exist and are up to date",
            "",
            "### 10. Insufficient Logging & Monitoring",
            "",
            "- Check if authentication failures are logged",
            "- Verify that security-relevant events (access control failures, input validation failures) are logged",
            "- Look for sensitive data in log output",
            "- Check that logs cannot be tampered with (injection into logs via user input)",
            "",
            "### 11. Cryptographic Failures",
            "",
            "- Look for weak or deprecated cryptographic algorithms (DES, RC4, MD5 for signing, SHA1 for signing)",
            "- Check for hardcoded encryption keys or IVs",
            "- Verify random number generation uses cryptographically secure sources (`secrets` module, not `random`)",
            "- Look for ECB mode usage in block ciphers",
            "- Check for missing or improper certificate validation in HTTPS connections (`verify=False`)",
            "",
            "### 12. Business Logic Vulnerabilities",
            "",
            "- Look for race conditions in financial transactions or resource allocation",
            "- Check for missing validation on quantities, prices, or amounts (negative values, integer overflow)",
            "- Look for time-of-check to time-of-use (TOCTOU) bugs",
            "- Check for abuse of bulk operations or batch endpoints",
            "",
            "### 13. File Upload Vulnerabilities",
            "",
            "- Check for unrestricted file upload types (allowing .php, .jsp, .exe, .sh)",
            "- Look for missing file size limits",
            "- Verify uploaded files are stored outside the web root",
            "- Check for path traversal in uploaded file names",
            "- Look for missing content-type validation (checking magic bytes, not just extension)",
            "",
            "---",
            "",
            "## Output Format",
            "",
            "For each vulnerability found:",
            "1. **Category** — Which of the above categories it falls under",
            "2. **Severity** — Critical / High / Medium / Low",
            "3. **File & Line** — Exact location in the codebase",
            "4. **Description** — What the vulnerability is and how it could be exploited",
            "5. **Fix** — The specific code change to remediate it",
            "",
            "Apply all fixes to the `fix/security-audit` branch and open a pull request with the full report.",
        ]
    )
