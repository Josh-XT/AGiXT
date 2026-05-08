"""CLI helper that drives the Audible OAuth-via-browser flow once and
writes ``~/.agixt/audible_auth.json``.

Mirrors the kids-app helper in
`/home/josh/repos/xtsys/kids/tools/sync_browser_cookies.py:create_audible_auth`
so users on either app can use whichever workflow they prefer.

Usage::

    /home/josh/repos/xtsys/.venv/bin/python -m extensions.audible_auth
    /home/josh/repos/xtsys/.venv/bin/python -m extensions.audible_auth --locale uk

After it finishes, every Audible command and the desktop page picks up
the auth file automatically — no AGiXT settings to fill in. Re-run the
script any time the auth file goes stale (Amazon does eventually
expire device registrations).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path


_AUTH_FILE = Path(os.path.expanduser("~/.agixt/audible_auth.json"))


def _open_login_callback(login_url: str) -> str:
    """Open the Amazon OAuth URL in the user's default browser and wait
    for them to paste back the post-login redirect URL.

    Amazon redirects to a "page not found" with the auth code in the
    address bar — copy the FULL URL (it must contain
    ``openid.oa2.authorization_code=...``).
    """
    print()
    print("Opening Amazon login in your default browser…")
    print("Sign in if prompted; Amazon will land on a 'page not found'")
    print("with a URL like https://www.amazon.com/ap/maplanding?...")
    print("openid.oa2.authorization_code=... — copy that URL from the")
    print("address bar and paste it below.")
    print()
    try:
        webbrowser.open(login_url)
    except Exception as exc:
        print(f"(could not auto-open browser: {exc})")
        print("Open this URL manually:")
        print(f"  {login_url}")
    while True:
        try:
            entered = input("Paste the post-login URL: ").strip()
        except EOFError:
            sys.exit("\nAborted.")
        if "openid.oa2.authorization_code=" in entered:
            return entered
        print(
            "That URL doesn't include openid.oa2.authorization_code=. "
            "Copy the FULL address bar URL after Amazon lands on the "
            "'page not found' screen.",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Audible auth file for AGiXT.",
    )
    parser.add_argument(
        "--locale",
        default="us",
        help="Audible marketplace (us / uk / de / fr / au / ca / it / "
        "in / es / jp / br). Default: us.",
    )
    parser.add_argument(
        "--out",
        default=str(_AUTH_FILE),
        help=f"Where to write the auth JSON (default: {_AUTH_FILE}).",
    )
    args = parser.parse_args(argv)

    try:
        import audible
    except ImportError:
        sys.exit(
            "The 'audible' python package is not installed. Install it with:\n"
            "  /home/josh/repos/xtsys/.venv/bin/pip install audible"
        )

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    auth = audible.Authenticator.from_login_external(
        locale=args.locale,
        login_url_callback=_open_login_callback,
    )

    if hasattr(auth, "to_file"):
        auth.to_file(str(out_path))
    else:
        # Fall back to to_dict() then json.dump for older audible package
        # builds that lack to_file.
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(auth.to_dict(), fh, indent=2)

    customer = getattr(auth, "customer_info", {}) or {}
    name = customer.get("name") or customer.get("given_name") or "(unknown)"
    print()
    print(f"✓ Audible auth saved to {out_path}")
    print(f"  Connected as: {name}")
    print(f"  Marketplace:  {args.locale}")
    print()
    print("The desktop Audible page and every Audible LLM command will")
    print("now pick this up automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
