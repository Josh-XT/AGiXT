import os
import requests
from fastapi import HTTPException
from Extensions import Extensions
from Globals import getenv
import logging

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

SCOPES = ["repo", "user:email", "read:user", "workflow"]
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


class github(Extensions):
    """
    The GitHub extension enables the AI agent to interact with the user's GitHub
    repositories via the workspace terminal using ``git`` and the GitHub CLI (``gh``).

    When the user connects their GitHub account through OAuth, the access token is
    automatically injected into the workspace terminal environment as ``GITHUB_TOKEN``
    and ``GH_TOKEN``, so the agent can run authenticated ``git`` and ``gh`` commands
    without any manual configuration.
    """

    CATEGORY = "Development & Code"
    friendly_name = "GitHub"

    def __init__(self, **kwargs):
        self.GITHUB_USERNAME = kwargs.get("GITHUB_USERNAME", "")
        self.GITHUB_API_KEY = kwargs.get("GITHUB_API_KEY", "") or kwargs.get(
            "GITHUB_ACCESS_TOKEN", ""
        )
        self.commands = {"List GitHub Repositories": self.list_repositories}

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
