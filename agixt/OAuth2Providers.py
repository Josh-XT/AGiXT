from sso.amazon import amazon_sso
from sso.github import github_sso
from sso.google import google_sso
from sso.microsoft import microsoft_sso
import logging


def get_sso_provider(provider: str, code, redirect_uri=None):
    try:
        if provider == "amazon":
            return amazon_sso(code=code, redirect_uri=redirect_uri)
        elif provider == "github":
            return github_sso(code=code, redirect_uri=redirect_uri)
        elif provider == "google":
            return google_sso(code=code, redirect_uri=redirect_uri)
        elif provider == "microsoft":
            return microsoft_sso(code=code, redirect_uri=redirect_uri)
        else:
            return None
    except Exception as e:
        logging.error(f"Error getting SSO provider info: {e}")
        return None
