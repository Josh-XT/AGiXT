"""
GitHub Bot Manager for AGiXT

This module manages GitHub webhook-driven bots that can:
- Respond to new issues by attempting to fix them in a new PR
- Review pull requests, suggest changes, write tests
- Use GitHub Copilot integration for code generation
- Support allowlist-based permissions (users, orgs, repos)

The manager:
- Handles GitHub webhooks (issues, pull_requests, issue_comments, pr_review_comments)
- Creates branches and PRs for issue fixes
- Runs in a fix → test → review → commit loop
- Supports single repo, multiple repos, or org-wide deployment
"""

import asyncio
import logging
import re
import hashlib
import hmac
import json
from typing import Dict, Optional, List, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum

# Try to import github library
GITHUB_AVAILABLE = False
try:
    from github import Github, GithubIntegration, Auth
    from github.Repository import Repository
    from github.Issue import Issue
    from github.PullRequest import PullRequest
    from github.GithubException import GithubException
    GITHUB_AVAILABLE = True
    logging.info("Successfully loaded PyGithub library")
except ImportError as e:
    logging.warning(f"PyGithub library not installed: {e}")

from DB import get_session, CompanyExtensionSetting, ServerExtensionSetting
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from Models import ChatCompletions

logger = logging.getLogger(__name__)


class DeploymentScope(Enum):
    """Deployment scope for GitHub bot."""
    SINGLE_REPO = "single_repo"  # Deploy to one specific repo
    MULTI_REPO = "multi_repo"   # Deploy to a list of repos
    ORG = "org"                  # Deploy to all repos in an org
    USER = "user"               # Deploy to all repos owned by a user


@dataclass
class GitHubBotStatus:
    """Status information for a company's GitHub bot."""
    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    repos_monitored: int = 0
    issues_processed: int = 0
    prs_created: int = 0
    prs_reviewed: int = 0
    deployment_scope: str = "single_repo"


@dataclass 
class PRContext:
    """Context for an ongoing PR fix/review cycle."""
    repo_full_name: str
    pr_number: int
    branch_name: str
    issue_number: Optional[int] = None
    fix_attempts: int = 0
    test_attempts: int = 0
    review_cycle: int = 0
    last_commit_sha: Optional[str] = None


class CompanyGitHubBot:
    """
    A GitHub bot instance for a specific company.
    Handles issue fixing, PR creation, code review, and test generation.

    Permission modes:
    - owner_only: Only the bot owner's repos/events are processed
    - allowlist: Only allowlisted users/repos/orgs are processed
    - anyone: All events are processed (not recommended for public bots)
    
    Deployment scopes:
    - single_repo: Monitor a single repository
    - multi_repo: Monitor a list of repositories
    - org: Monitor all repositories in an organization
    - user: Monitor all repositories owned by a user
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        github_token: str = None,
        github_app_id: str = None,
        github_app_private_key: str = None,
        github_webhook_secret: str = None,
        bot_agent_id: str = None,
        bot_permission_mode: str = "allowlist",
        bot_owner_id: str = None,
        bot_allowlist: str = None,
        deployment_scope: str = "single_repo",
        target_repos: str = None,  # Comma-separated list of owner/repo
        target_org: str = None,
        target_user: str = None,
        auto_fix_issues: bool = True,
        auto_review_prs: bool = True,
        auto_write_tests: bool = True,
        max_fix_attempts: int = 3,
    ):
        self.company_id = company_id
        self.company_name = company_name
        
        # GitHub authentication
        self.github_token = github_token
        self.github_app_id = github_app_id
        self.github_app_private_key = github_app_private_key
        self.github_webhook_secret = github_webhook_secret
        
        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
        self.auto_fix_issues = auto_fix_issues
        self.auto_review_prs = auto_review_prs
        self.auto_write_tests = auto_write_tests
        self.max_fix_attempts = max_fix_attempts
        
        # Deployment configuration
        self.deployment_scope = DeploymentScope(deployment_scope)
        self.target_repos: Set[str] = set()
        if target_repos:
            for repo in target_repos.split(","):
                repo = repo.strip()
                if repo:
                    self.target_repos.add(repo.lower())
        self.target_org = target_org
        self.target_user = target_user
        
        # Parse allowlist - can be GitHub usernames, repo names (owner/repo), or org names
        self.bot_allowlist: Set[str] = set()
        if bot_allowlist:
            for item in bot_allowlist.split(","):
                item = item.strip().lower()
                if item:
                    # Remove @ prefix if present
                    if item.startswith("@"):
                        item = item[1:]
                    self.bot_allowlist.add(item)
        
        # GitHub client
        self.github_client: Optional[Github] = None
        self.github_app: Optional[GithubIntegration] = None
        
        # Status tracking
        self._is_ready = False
        self._started_at: Optional[datetime] = None
        self._issues_processed: int = self._load_counter("issues_processed")
        self._prs_created: int = self._load_counter("prs_created")
        self._prs_reviewed: int = self._load_counter("prs_reviewed")
        
        # Active PR contexts (for fix/test/review loops)
        self._active_pr_contexts: Dict[str, PRContext] = {}
        
        # Initialize GitHub client
        self._init_github_client()

    def _init_github_client(self):
        """Initialize the GitHub client based on available credentials."""
        if not GITHUB_AVAILABLE:
            logger.error("PyGithub library not available")
            return
            
        try:
            if self.github_app_id and self.github_app_private_key:
                # Use GitHub App authentication
                auth = Auth.AppAuth(
                    app_id=int(self.github_app_id),
                    private_key=self.github_app_private_key
                )
                self.github_app = GithubIntegration(auth=auth)
                self._is_ready = True
                logger.info(f"GitHub bot for {self.company_name} initialized with App authentication")
            elif self.github_token:
                # Use personal access token
                self.github_client = Github(self.github_token)
                self._is_ready = True
                logger.info(f"GitHub bot for {self.company_name} initialized with token authentication")
            else:
                logger.warning(f"No GitHub credentials configured for {self.company_name}")
        except Exception as e:
            logger.error(f"Failed to initialize GitHub client for {self.company_name}: {e}")
            self._is_ready = False

    def _get_github_client_for_repo(self, repo_full_name: str) -> Optional[Github]:
        """Get a GitHub client for a specific repository (handles App installation tokens)."""
        if self.github_client:
            return self.github_client
            
        if self.github_app:
            try:
                owner = repo_full_name.split("/")[0]
                # Get installation for the owner (org or user)
                installation = self.github_app.get_installation(owner)
                if installation:
                    return installation.get_github_for_installation()
            except Exception as e:
                logger.warning(f"Could not get installation for {owner}: {e}")
        
        return None

    def _load_counter(self, counter_name: str) -> int:
        """Load a counter from the database."""
        try:
            with get_session() as db:
                if self.company_id == "server":
                    setting = (
                        db.query(ServerExtensionSetting)
                        .filter(
                            ServerExtensionSetting.extension_name == "github",
                            ServerExtensionSetting.setting_key == f"github_bot_{counter_name}",
                        )
                        .first()
                    )
                else:
                    setting = (
                        db.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.company_id == self.company_id,
                            CompanyExtensionSetting.extension_name == "github",
                            CompanyExtensionSetting.setting_key == f"github_bot_{counter_name}",
                        )
                        .first()
                    )
                
                if setting and setting.setting_value:
                    return int(setting.setting_value)
        except Exception as e:
            logger.warning(f"Could not load {counter_name} for {self.company_id}: {e}")
        return 0

    def _save_counter(self, counter_name: str, value: int):
        """Save a counter to the database."""
        try:
            with get_session() as db:
                if self.company_id == "server":
                    setting = (
                        db.query(ServerExtensionSetting)
                        .filter(
                            ServerExtensionSetting.extension_name == "github",
                            ServerExtensionSetting.setting_key == f"github_bot_{counter_name}",
                        )
                        .first()
                    )
                    if setting:
                        setting.setting_value = str(value)
                    else:
                        setting = ServerExtensionSetting(
                            extension_name="github",
                            setting_key=f"github_bot_{counter_name}",
                            setting_value=str(value),
                        )
                        db.add(setting)
                else:
                    setting = (
                        db.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.company_id == self.company_id,
                            CompanyExtensionSetting.extension_name == "github",
                            CompanyExtensionSetting.setting_key == f"github_bot_{counter_name}",
                        )
                        .first()
                    )
                    if setting:
                        setting.setting_value = str(value)
                    else:
                        setting = CompanyExtensionSetting(
                            company_id=self.company_id,
                            extension_name="github",
                            setting_key=f"github_bot_{counter_name}",
                            setting_value=str(value),
                        )
                        db.add(setting)
                db.commit()
        except Exception as e:
            logger.warning(f"Could not save {counter_name} for {self.company_id}: {e}")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook signature."""
        if not self.github_webhook_secret:
            logger.warning("No webhook secret configured, skipping signature verification")
            return True
            
        expected_signature = "sha256=" + hmac.new(
            self.github_webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)

    def _is_repo_allowed(self, repo_full_name: str) -> bool:
        """Check if a repository is within the deployment scope."""
        repo_lower = repo_full_name.lower()
        
        if self.deployment_scope == DeploymentScope.SINGLE_REPO:
            return repo_lower in self.target_repos or len(self.target_repos) == 0
        elif self.deployment_scope == DeploymentScope.MULTI_REPO:
            return repo_lower in self.target_repos
        elif self.deployment_scope == DeploymentScope.ORG:
            return repo_lower.startswith(f"{self.target_org.lower()}/") if self.target_org else False
        elif self.deployment_scope == DeploymentScope.USER:
            return repo_lower.startswith(f"{self.target_user.lower()}/") if self.target_user else False
        
        return False

    def _is_user_allowed(self, username: str, repo_full_name: str = None) -> bool:
        """Check if a user is allowed to interact with the bot."""
        if not username:
            return False
            
        username_lower = username.lower()
        
        if self.bot_permission_mode == "owner_only":
            # Only the bot owner can interact
            # We'd need to map bot_owner_id to a GitHub username
            # For now, check if owner is in allowlist
            return username_lower in self.bot_allowlist if self.bot_allowlist else False
            
        elif self.bot_permission_mode == "allowlist":
            # Check if user or their org is in allowlist
            if username_lower in self.bot_allowlist:
                return True
            # Check if the repo's org/owner is in allowlist
            if repo_full_name:
                owner = repo_full_name.lower().split("/")[0]
                if owner in self.bot_allowlist:
                    return True
            return False
            
        elif self.bot_permission_mode == "anyone":
            return True
            
        return False

    async def _get_agent_context(self) -> tuple:
        """Get the appropriate agent context for API calls."""
        if self.bot_owner_id:
            return impersonate_user(self.bot_owner_id)
        return None, {}

    async def _send_to_agent(
        self,
        prompt: str,
        conversation_name: str = None,
        context: str = None,
    ) -> str:
        """Send a prompt to the configured AI agent and get a response."""
        try:
            user_data, headers = await self._get_agent_context()
            if not user_data:
                logger.error("Could not get agent context - no owner configured")
                return "Error: Bot owner not configured"
            
            # Create an internal client to call the agent
            client = InternalClient(headers=headers)
            
            agent_name = self.bot_agent_id or "XT"  # Default to XT agent
            
            # Build the full prompt with context
            full_prompt = prompt
            if context:
                full_prompt = f"Context:\n{context}\n\nTask:\n{prompt}"
            
            # Use chat completions endpoint
            response = await client.chat_completions(
                agent_name=agent_name,
                messages=[{"role": "user", "content": full_prompt}],
                conversation_name=conversation_name or f"github-{self.company_id}",
            )
            
            if response and "choices" in response:
                return response["choices"][0]["message"]["content"]
            
            return "Error: No response from agent"
            
        except Exception as e:
            logger.error(f"Error sending to agent: {e}")
            return f"Error: {str(e)}"

    async def handle_webhook(self, event_type: str, payload: dict) -> dict:
        """
        Handle incoming GitHub webhook events.
        
        Supported events:
        - issues: New issue created or edited
        - pull_request: PR opened, synchronized, or review requested
        - issue_comment: Comment on an issue
        - pull_request_review_comment: Comment on a PR review
        """
        if not self._is_ready:
            return {"status": "error", "message": "GitHub bot not ready"}
        
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        sender = payload.get("sender", {}).get("login", "")
        
        # Check if repo is in scope
        if not self._is_repo_allowed(repo_full_name):
            logger.debug(f"Ignoring event for repo {repo_full_name} - not in scope")
            return {"status": "ignored", "reason": "repo_not_in_scope"}
        
        # Check if sender is allowed
        if not self._is_user_allowed(sender, repo_full_name):
            logger.debug(f"Ignoring event from user {sender} - not allowed")
            return {"status": "ignored", "reason": "user_not_allowed"}
        
        try:
            if event_type == "issues":
                return await self._handle_issue_event(payload)
            elif event_type == "pull_request":
                return await self._handle_pr_event(payload)
            elif event_type == "issue_comment":
                return await self._handle_issue_comment(payload)
            elif event_type == "pull_request_review_comment":
                return await self._handle_pr_review_comment(payload)
            elif event_type == "pull_request_review":
                return await self._handle_pr_review(payload)
            else:
                return {"status": "ignored", "reason": f"unsupported_event_type: {event_type}"}
        except Exception as e:
            logger.error(f"Error handling {event_type} webhook: {e}")
            return {"status": "error", "message": str(e)}

    async def _handle_issue_event(self, payload: dict) -> dict:
        """Handle issue events (opened, edited, labeled)."""
        action = payload.get("action")
        issue = payload.get("issue", {})
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        
        if action not in ["opened", "labeled"]:
            return {"status": "ignored", "reason": f"action_{action}_not_handled"}
        
        # Check for labels that trigger auto-fix
        labels = [l.get("name", "").lower() for l in issue.get("labels", [])]
        
        # Skip if labeled with "no-bot" or similar
        skip_labels = ["no-bot", "no-ai", "manual", "wontfix", "invalid"]
        if any(label in skip_labels for label in labels):
            return {"status": "ignored", "reason": "skip_label_present"}
        
        # Auto-fix if enabled and issue is new or labeled with "fix" type labels
        fix_labels = ["bug", "fix", "autofix", "ai-fix", "help wanted"]
        should_auto_fix = self.auto_fix_issues and (
            action == "opened" or 
            any(label in fix_labels for label in labels)
        )
        
        if should_auto_fix:
            self._issues_processed += 1
            self._save_counter("issues_processed", self._issues_processed)
            return await self._attempt_issue_fix(repo_full_name, issue)
        
        return {"status": "acknowledged", "action": action}

    async def _attempt_issue_fix(self, repo_full_name: str, issue: dict) -> dict:
        """Attempt to fix an issue by creating a PR."""
        issue_number = issue.get("number")
        issue_title = issue.get("title", "")
        issue_body = issue.get("body", "")
        
        logger.info(f"Attempting to fix issue #{issue_number} in {repo_full_name}")
        
        github = self._get_github_client_for_repo(repo_full_name)
        if not github:
            return {"status": "error", "message": "Could not get GitHub client"}
        
        try:
            repo = github.get_repo(repo_full_name)
            gh_issue = repo.get_issue(issue_number)
            
            # Comment that we're working on it
            gh_issue.create_comment(
                "🤖 **AI Assistant**: I'm analyzing this issue and will attempt to create a fix. "
                "Please allow a few minutes for the analysis and PR creation."
            )
            
            # Analyze the issue and get fix suggestions
            analysis_prompt = f"""Analyze this GitHub issue and provide a detailed plan for fixing it.

Issue Title: {issue_title}

Issue Description:
{issue_body}

Repository: {repo_full_name}

Please provide:
1. A summary of what needs to be fixed
2. Which files likely need to be modified
3. A high-level approach to the fix
4. Any questions or clarifications needed before proceeding

If this issue is unclear or requires more information from the user, explain what's needed."""

            analysis = await self._send_to_agent(
                analysis_prompt,
                conversation_name=f"github-issue-{repo_full_name.replace('/', '-')}-{issue_number}"
            )
            
            # Check if we need clarification
            needs_clarification_keywords = [
                "need more information",
                "please clarify",
                "could you provide",
                "not clear",
                "unclear",
                "more details needed",
                "cannot proceed",
            ]
            
            if any(kw in analysis.lower() for kw in needs_clarification_keywords):
                # Post clarification request
                gh_issue.create_comment(
                    f"🤖 **AI Assistant - Clarification Needed**:\n\n{analysis}\n\n"
                    "Please provide the requested information, and I'll continue with the fix."
                )
                return {"status": "waiting_for_clarification", "issue": issue_number}
            
            # Create a branch for the fix
            branch_name = f"ai-fix/issue-{issue_number}"
            default_branch = repo.default_branch
            
            # Get the default branch ref
            ref = repo.get_git_ref(f"heads/{default_branch}")
            sha = ref.object.sha
            
            # Create the new branch
            try:
                repo.create_git_ref(f"refs/heads/{branch_name}", sha)
            except GithubException as e:
                if e.status == 422:  # Branch already exists
                    # Delete and recreate
                    try:
                        repo.get_git_ref(f"heads/{branch_name}").delete()
                        repo.create_git_ref(f"refs/heads/{branch_name}", sha)
                    except:
                        branch_name = f"ai-fix/issue-{issue_number}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        repo.create_git_ref(f"refs/heads/{branch_name}", sha)
            
            # Now generate the actual fix
            fix_prompt = f"""Based on your analysis, now generate the actual code fix.

Issue Title: {issue_title}
Issue Description: {issue_body}
Repository: {repo_full_name}

Your previous analysis:
{analysis}

Please provide the specific code changes needed. For each file that needs to be modified:
1. State the file path
2. Show the exact changes needed (what to add, modify, or remove)
3. Explain why each change is necessary

Format your response with clear file paths and code blocks."""

            fix_response = await self._send_to_agent(
                fix_prompt,
                conversation_name=f"github-issue-{repo_full_name.replace('/', '-')}-{issue_number}"
            )
            
            # Parse the fix response and apply changes
            # This is a simplified version - in practice, we'd need more sophisticated parsing
            changes_made = await self._apply_code_changes(
                repo, branch_name, fix_response, issue_number
            )
            
            if not changes_made:
                gh_issue.create_comment(
                    f"🤖 **AI Assistant**: I analyzed the issue but couldn't determine specific "
                    f"code changes to make. Here's my analysis:\n\n{analysis}\n\n"
                    "Please provide more specific details about where the issue occurs."
                )
                return {"status": "no_changes_identified", "issue": issue_number}
            
            # Create the PR
            pr = repo.create_pull(
                title=f"🤖 Fix: {issue_title}",
                body=f"""## AI-Generated Fix for #{issue_number}

### Issue
{issue_body[:500]}{'...' if len(issue_body) > 500 else ''}

### Changes Made
{changes_made}

### Analysis
{analysis[:1000]}{'...' if len(analysis) > 1000 else ''}

---
*This PR was automatically generated by the AI assistant. Please review carefully before merging.*

Fixes #{issue_number}
""",
                head=branch_name,
                base=default_branch,
            )
            
            self._prs_created += 1
            self._save_counter("prs_created", self._prs_created)
            
            # Comment on the issue with the PR link
            gh_issue.create_comment(
                f"🤖 **AI Assistant**: I've created a pull request with a proposed fix: #{pr.number}\n\n"
                f"Please review the changes and let me know if any adjustments are needed."
            )
            
            # Store PR context for potential fix/test/review loop
            self._active_pr_contexts[f"{repo_full_name}/{pr.number}"] = PRContext(
                repo_full_name=repo_full_name,
                pr_number=pr.number,
                branch_name=branch_name,
                issue_number=issue_number,
            )
            
            # If auto-tests enabled, try to generate tests
            if self.auto_write_tests:
                await self._generate_tests_for_pr(repo, pr, branch_name)
            
            return {"status": "pr_created", "pr_number": pr.number, "issue": issue_number}
            
        except Exception as e:
            logger.error(f"Error fixing issue #{issue_number}: {e}")
            try:
                gh_issue.create_comment(
                    f"🤖 **AI Assistant**: I encountered an error while trying to fix this issue:\n\n"
                    f"```\n{str(e)}\n```\n\n"
                    "I'll need manual assistance with this one."
                )
            except:
                pass
            return {"status": "error", "message": str(e)}

    async def _apply_code_changes(
        self, 
        repo: Repository, 
        branch_name: str, 
        fix_response: str,
        issue_number: int
    ) -> str:
        """Parse the AI response and apply code changes to the repository."""
        # Extract code blocks and file paths from the response
        # This is a simplified parser - in production, use more robust parsing
        
        changes_summary = []
        
        # Pattern to find file paths and code blocks
        # Looking for patterns like:
        # `path/to/file.py`:
        # ```python
        # code
        # ```
        
        file_pattern = r'[`"]?([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]+)[`"]?\s*[:\n]'
        code_block_pattern = r'```[\w]*\n(.*?)```'
        
        import re
        
        # Find all code blocks
        code_blocks = re.findall(code_block_pattern, fix_response, re.DOTALL)
        file_mentions = re.findall(file_pattern, fix_response)
        
        # Try to match files with code blocks (simplified approach)
        for i, (file_path, code) in enumerate(zip(file_mentions[:len(code_blocks)], code_blocks)):
            if not file_path or not code.strip():
                continue
                
            try:
                # Check if file exists
                try:
                    contents = repo.get_contents(file_path, ref=branch_name)
                    # Update existing file
                    repo.update_file(
                        path=file_path,
                        message=f"🤖 AI fix for issue #{issue_number}: Update {file_path}",
                        content=code.strip(),
                        sha=contents.sha,
                        branch=branch_name,
                    )
                    changes_summary.append(f"- Updated `{file_path}`")
                except GithubException as e:
                    if e.status == 404:
                        # Create new file
                        repo.create_file(
                            path=file_path,
                            message=f"🤖 AI fix for issue #{issue_number}: Create {file_path}",
                            content=code.strip(),
                            branch=branch_name,
                        )
                        changes_summary.append(f"- Created `{file_path}`")
                    else:
                        raise
            except Exception as e:
                logger.warning(f"Could not apply change to {file_path}: {e}")
        
        return "\n".join(changes_summary) if changes_summary else ""

    async def _generate_tests_for_pr(
        self, 
        repo: Repository, 
        pr: PullRequest, 
        branch_name: str
    ):
        """Generate tests for the changes in a PR."""
        try:
            # Get the files changed in the PR
            files = pr.get_files()
            changed_files = [f.filename for f in files if not f.filename.startswith("test")]
            
            if not changed_files:
                return
            
            # Ask the agent to generate tests
            test_prompt = f"""Generate unit tests for the following changed files in a pull request.

Repository: {repo.full_name}
PR Title: {pr.title}

Changed files:
{chr(10).join(f'- {f}' for f in changed_files)}

Please generate appropriate test cases that:
1. Test the main functionality added or modified
2. Test edge cases and error handling
3. Follow the testing conventions of the repository

Format your response with the test file path and the test code."""

            test_response = await self._send_to_agent(
                test_prompt,
                conversation_name=f"github-pr-tests-{repo.full_name.replace('/', '-')}-{pr.number}"
            )
            
            # Apply test changes (similar to code changes)
            # This is simplified - would need more sophisticated parsing
            if "```" in test_response:
                # There are code blocks, try to extract and apply
                # For now, just comment with the suggested tests
                pr.create_issue_comment(
                    f"🤖 **AI Assistant - Suggested Tests**:\n\n{test_response[:4000]}"
                )
                
        except Exception as e:
            logger.warning(f"Error generating tests for PR #{pr.number}: {e}")

    async def _handle_pr_event(self, payload: dict) -> dict:
        """Handle pull request events."""
        action = payload.get("action")
        pr_data = payload.get("pull_request", {})
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        
        if action not in ["opened", "synchronize", "review_requested"]:
            return {"status": "ignored", "reason": f"action_{action}_not_handled"}
        
        if not self.auto_review_prs:
            return {"status": "ignored", "reason": "auto_review_disabled"}
        
        # Don't review our own PRs in a loop
        if pr_data.get("user", {}).get("login", "").endswith("[bot]"):
            return {"status": "ignored", "reason": "bot_pr"}
        
        self._prs_reviewed += 1
        self._save_counter("prs_reviewed", self._prs_reviewed)
        
        return await self._review_pr(repo_full_name, pr_data)

    async def _review_pr(self, repo_full_name: str, pr_data: dict) -> dict:
        """Review a pull request and provide feedback."""
        pr_number = pr_data.get("number")
        pr_title = pr_data.get("title", "")
        pr_body = pr_data.get("body", "")
        
        logger.info(f"Reviewing PR #{pr_number} in {repo_full_name}")
        
        github = self._get_github_client_for_repo(repo_full_name)
        if not github:
            return {"status": "error", "message": "Could not get GitHub client"}
        
        try:
            repo = github.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            
            # Get the diff
            files = pr.get_files()
            diff_summary = []
            for f in files:
                diff_summary.append(f"### {f.filename}\n```diff\n{f.patch[:2000] if f.patch else 'Binary file'}...\n```")
            
            diff_text = "\n\n".join(diff_summary[:10])  # Limit to first 10 files
            
            # Ask agent to review
            review_prompt = f"""Review this pull request and provide constructive feedback.

Repository: {repo_full_name}
PR Title: {pr_title}
PR Description: {pr_body}

Changes:
{diff_text}

Please provide:
1. A summary of what this PR does
2. Any issues or bugs you notice
3. Suggestions for improvement
4. Whether tests are adequate (or if more are needed)
5. An overall recommendation (approve, request changes, or comment)

Be constructive and specific in your feedback."""

            review_response = await self._send_to_agent(
                review_prompt,
                conversation_name=f"github-pr-review-{repo_full_name.replace('/', '-')}-{pr_number}"
            )
            
            # Determine review event type based on response
            review_event = "COMMENT"  # Default to comment
            response_lower = review_response.lower()
            
            if "approve" in response_lower and "request changes" not in response_lower:
                review_event = "APPROVE"
            elif "request changes" in response_lower or "needs changes" in response_lower:
                review_event = "REQUEST_CHANGES"
            
            # Create the review
            pr.create_review(
                body=f"🤖 **AI Code Review**\n\n{review_response}",
                event=review_event,
            )
            
            return {"status": "reviewed", "pr_number": pr_number, "event": review_event}
            
        except Exception as e:
            logger.error(f"Error reviewing PR #{pr_number}: {e}")
            return {"status": "error", "message": str(e)}

    async def _handle_issue_comment(self, payload: dict) -> dict:
        """Handle comments on issues (could be commands or requests for help)."""
        action = payload.get("action")
        if action != "created":
            return {"status": "ignored", "reason": f"action_{action}_not_handled"}
        
        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        
        comment_body = comment.get("body", "").lower()
        
        # Check for bot commands
        if "@ai" in comment_body or "@bot" in comment_body or "ai assistant" in comment_body:
            # This is a command/request for the bot
            return await self._handle_bot_command(
                repo_full_name, 
                issue.get("number"),
                comment.get("body", ""),
                is_pr="pull_request" in issue
            )
        
        return {"status": "ignored", "reason": "no_bot_mention"}

    async def _handle_bot_command(
        self, 
        repo_full_name: str, 
        number: int, 
        command: str,
        is_pr: bool = False
    ) -> dict:
        """Handle a command directed at the bot."""
        github = self._get_github_client_for_repo(repo_full_name)
        if not github:
            return {"status": "error", "message": "Could not get GitHub client"}
        
        try:
            repo = github.get_repo(repo_full_name)
            
            if is_pr:
                item = repo.get_pull(number)
            else:
                item = repo.get_issue(number)
            
            # Parse the command
            command_lower = command.lower()
            
            if "fix" in command_lower or "solve" in command_lower:
                # User wants us to attempt a fix
                if not is_pr:
                    return await self._attempt_issue_fix(repo_full_name, {
                        "number": number,
                        "title": item.title,
                        "body": item.body,
                    })
                    
            elif "review" in command_lower:
                # User wants a review
                if is_pr:
                    return await self._review_pr(repo_full_name, {
                        "number": number,
                        "title": item.title,
                        "body": item.body,
                    })
                    
            elif "test" in command_lower:
                # User wants tests generated
                if is_pr:
                    await self._generate_tests_for_pr(repo, item, item.head.ref)
                    return {"status": "tests_suggested", "pr_number": number}
                    
            elif "help" in command_lower:
                # Provide help
                item.create_comment(
                    "🤖 **AI Assistant - Available Commands**:\n\n"
                    "- `@ai fix` - Attempt to fix this issue (creates a PR)\n"
                    "- `@ai review` - Review this PR and provide feedback\n"
                    "- `@ai test` - Suggest tests for this PR\n"
                    "- `@ai help` - Show this help message\n"
                    "- `@ai <question>` - Ask a question about this issue/PR\n"
                )
                return {"status": "help_provided"}
            
            else:
                # General question/request
                response = await self._send_to_agent(
                    f"The user asked about issue/PR #{number}:\n\n{command}\n\n"
                    f"Context - Title: {item.title}\nDescription: {item.body}",
                    conversation_name=f"github-{repo_full_name.replace('/', '-')}-{number}"
                )
                
                item.create_comment(f"🤖 **AI Assistant**:\n\n{response}")
                return {"status": "responded"}
                
        except Exception as e:
            logger.error(f"Error handling bot command: {e}")
            return {"status": "error", "message": str(e)}

    async def _handle_pr_review_comment(self, payload: dict) -> dict:
        """Handle comments on PR reviews."""
        # Similar to issue comments, but in PR review context
        action = payload.get("action")
        if action != "created":
            return {"status": "ignored"}
        
        comment = payload.get("comment", {})
        comment_body = comment.get("body", "").lower()
        
        if "@ai" in comment_body or "@bot" in comment_body:
            pr = payload.get("pull_request", {})
            repo_full_name = payload.get("repository", {}).get("full_name", "")
            return await self._handle_bot_command(
                repo_full_name,
                pr.get("number"),
                comment.get("body", ""),
                is_pr=True
            )
        
        return {"status": "ignored", "reason": "no_bot_mention"}

    async def _handle_pr_review(self, payload: dict) -> dict:
        """Handle PR review events (e.g., changes requested)."""
        action = payload.get("action")
        if action != "submitted":
            return {"status": "ignored"}
        
        review = payload.get("review", {})
        pr = payload.get("pull_request", {})
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        
        # Check if this is one of our PRs
        pr_key = f"{repo_full_name}/{pr.get('number')}"
        if pr_key not in self._active_pr_contexts:
            return {"status": "ignored", "reason": "not_our_pr"}
        
        context = self._active_pr_contexts[pr_key]
        
        # If changes were requested, try to address them
        if review.get("state") == "CHANGES_REQUESTED":
            context.review_cycle += 1
            
            if context.review_cycle > self.max_fix_attempts:
                logger.info(f"Max fix attempts reached for PR {pr_key}")
                return {"status": "max_attempts_reached"}
            
            # Try to address the feedback
            return await self._address_review_feedback(
                repo_full_name, 
                pr.get("number"),
                review.get("body", ""),
                context
            )
        
        return {"status": "acknowledged"}

    async def _address_review_feedback(
        self,
        repo_full_name: str,
        pr_number: int,
        feedback: str,
        context: PRContext
    ) -> dict:
        """Address feedback from a PR review."""
        github = self._get_github_client_for_repo(repo_full_name)
        if not github:
            return {"status": "error", "message": "Could not get GitHub client"}
        
        try:
            repo = github.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            
            # Comment that we're addressing feedback
            pr.create_issue_comment(
                f"🤖 **AI Assistant**: I'm reviewing the feedback and will push updates shortly. "
                f"(Attempt {context.review_cycle}/{self.max_fix_attempts})"
            )
            
            # Get current changes and feedback
            fix_prompt = f"""A reviewer requested changes on our pull request. Please address their feedback.

PR Title: {pr.title}
PR Description: {pr.body}

Reviewer Feedback:
{feedback}

Please provide the specific code changes needed to address this feedback."""

            fix_response = await self._send_to_agent(
                fix_prompt,
                conversation_name=f"github-pr-fix-{repo_full_name.replace('/', '-')}-{pr_number}"
            )
            
            # Apply changes
            changes = await self._apply_code_changes(
                repo, context.branch_name, fix_response, context.issue_number or pr_number
            )
            
            if changes:
                pr.create_issue_comment(
                    f"🤖 **AI Assistant**: I've pushed changes to address the feedback:\n\n{changes}\n\n"
                    "Please review again when ready."
                )
                context.fix_attempts += 1
                return {"status": "changes_pushed", "attempt": context.fix_attempts}
            else:
                pr.create_issue_comment(
                    "🤖 **AI Assistant**: I couldn't automatically address the feedback. "
                    "Could you provide more specific guidance?"
                )
                return {"status": "no_changes_made"}
                
        except Exception as e:
            logger.error(f"Error addressing review feedback: {e}")
            return {"status": "error", "message": str(e)}

    def get_status(self) -> GitHubBotStatus:
        """Get the current status of this bot."""
        return GitHubBotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            started_at=self._started_at,
            is_running=self._is_ready,
            repos_monitored=len(self.target_repos),
            issues_processed=self._issues_processed,
            prs_created=self._prs_created,
            prs_reviewed=self._prs_reviewed,
            deployment_scope=self.deployment_scope.value,
        )

    async def start(self):
        """Start the GitHub bot (verify credentials and set ready state)."""
        if self._is_ready:
            self._started_at = datetime.now(UTC)
            logger.info(f"GitHub bot for {self.company_name} started")
        else:
            logger.warning(f"GitHub bot for {self.company_name} could not start - not ready")

    async def stop(self):
        """Stop the GitHub bot."""
        self._is_ready = False
        self._started_at = None
        logger.info(f"GitHub bot for {self.company_name} stopped")


class GitHubBotManager:
    """
    Manager for multiple GitHub bots across companies.
    Handles webhook routing and bot lifecycle management.
    """

    _instance: Optional["GitHubBotManager"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._bots: Dict[str, CompanyGitHubBot] = {}  # company_id -> bot
        self._server_bot: Optional[CompanyGitHubBot] = None
        self._started = False

    @classmethod
    async def get_instance(cls) -> "GitHubBotManager":
        """Get the singleton instance of the GitHub bot manager."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def start(self):
        """Start the GitHub bot manager."""
        if self._started:
            return
        
        self._started = True
        logger.info("GitHub Bot Manager started")
        
        # Load and start bots from database
        await self._load_bots()

    async def stop(self):
        """Stop all bots and the manager."""
        for bot in self._bots.values():
            await bot.stop()
        
        if self._server_bot:
            await self._server_bot.stop()
        
        self._bots.clear()
        self._server_bot = None
        self._started = False
        logger.info("GitHub Bot Manager stopped")

    async def _load_bots(self):
        """Load bot configurations from database and start enabled bots."""
        with get_session() as db:
            # Load server-level bot
            server_settings = (
                db.query(ServerExtensionSetting)
                .filter(ServerExtensionSetting.extension_name == "github")
                .all()
            )
            
            server_config = {}
            for setting in server_settings:
                server_config[setting.setting_key] = setting.setting_value
            
            if server_config.get("github_bot_enabled") == "true":
                await self._start_server_bot(server_config)
            
            # Load company-level bots
            # Group settings by company
            company_settings = (
                db.query(CompanyExtensionSetting)
                .filter(CompanyExtensionSetting.extension_name == "github")
                .all()
            )
            
            companies: Dict[str, dict] = {}
            for setting in company_settings:
                if setting.company_id not in companies:
                    companies[setting.company_id] = {}
                companies[setting.company_id][setting.setting_key] = setting.setting_value
            
            for company_id, config in companies.items():
                if config.get("github_bot_enabled") == "true":
                    company = db.query(Company).filter(Company.id == company_id).first()
                    company_name = company.name if company else company_id
                    await self._start_company_bot(company_id, company_name, config)

    async def _start_server_bot(self, config: dict):
        """Start the server-level GitHub bot."""
        try:
            self._server_bot = CompanyGitHubBot(
                company_id="server",
                company_name="Server",
                github_token=config.get("GITHUB_TOKEN"),
                github_app_id=config.get("GITHUB_APP_ID"),
                github_app_private_key=config.get("GITHUB_APP_PRIVATE_KEY"),
                github_webhook_secret=config.get("GITHUB_WEBHOOK_SECRET"),
                bot_agent_id=config.get("github_bot_agent_id"),
                bot_permission_mode=config.get("github_bot_permission_mode", "allowlist"),
                bot_owner_id=config.get("github_bot_owner_id"),
                bot_allowlist=config.get("github_bot_allowlist"),
                deployment_scope=config.get("github_bot_deployment_scope", "single_repo"),
                target_repos=config.get("github_bot_target_repos"),
                target_org=config.get("github_bot_target_org"),
                target_user=config.get("github_bot_target_user"),
                auto_fix_issues=config.get("github_bot_auto_fix", "true") == "true",
                auto_review_prs=config.get("github_bot_auto_review", "true") == "true",
                auto_write_tests=config.get("github_bot_auto_tests", "true") == "true",
            )
            await self._server_bot.start()
            logger.info("Server-level GitHub bot started")
        except Exception as e:
            logger.error(f"Failed to start server-level GitHub bot: {e}")

    async def _start_company_bot(self, company_id: str, company_name: str, config: dict):
        """Start a company-level GitHub bot."""
        try:
            bot = CompanyGitHubBot(
                company_id=company_id,
                company_name=company_name,
                github_token=config.get("GITHUB_TOKEN"),
                github_app_id=config.get("GITHUB_APP_ID"),
                github_app_private_key=config.get("GITHUB_APP_PRIVATE_KEY"),
                github_webhook_secret=config.get("GITHUB_WEBHOOK_SECRET"),
                bot_agent_id=config.get("github_bot_agent_id"),
                bot_permission_mode=config.get("github_bot_permission_mode", "allowlist"),
                bot_owner_id=config.get("github_bot_owner_id"),
                bot_allowlist=config.get("github_bot_allowlist"),
                deployment_scope=config.get("github_bot_deployment_scope", "single_repo"),
                target_repos=config.get("github_bot_target_repos"),
                target_org=config.get("github_bot_target_org"),
                target_user=config.get("github_bot_target_user"),
                auto_fix_issues=config.get("github_bot_auto_fix", "true") == "true",
                auto_review_prs=config.get("github_bot_auto_review", "true") == "true",
                auto_write_tests=config.get("github_bot_auto_tests", "true") == "true",
            )
            self._bots[company_id] = bot
            await bot.start()
            logger.info(f"GitHub bot for {company_name} started")
        except Exception as e:
            logger.error(f"Failed to start GitHub bot for {company_name}: {e}")

    async def handle_webhook(
        self, 
        event_type: str, 
        payload: dict, 
        signature: str = None,
        company_id: str = None,
        skip_signature_check: bool = False,
    ) -> dict:
        """
        Route a webhook to the appropriate bot.
        
        If company_id is provided, route to that company's bot.
        Otherwise, try server bot first, then match by repo.
        
        Args:
            event_type: GitHub event type (issues, pull_request, etc.)
            payload: Webhook payload data
            signature: Webhook signature for verification (optional if skip_signature_check=True)
            company_id: Company ID to route webhook to
            skip_signature_check: Skip signature verification (use when already verified in endpoint)
        """
        # Determine which bot should handle this
        bot = None
        
        if company_id and company_id in self._bots:
            bot = self._bots[company_id]
        elif self._server_bot:
            bot = self._server_bot
        
        if not bot:
            # Try to start the bot on-demand if company_id is provided
            if company_id:
                await self._start_company_bot(company_id)
                if company_id in self._bots:
                    bot = self._bots[company_id]
        
        if not bot:
            return {"status": "error", "message": "No bot configured for this webhook"}
        
        # Verify signature unless already verified
        if not skip_signature_check and signature:
            payload_bytes = json.dumps(payload).encode() if isinstance(payload, dict) else payload
            if not bot.verify_webhook_signature(payload_bytes, signature):
                return {"status": "error", "message": "Invalid webhook signature"}
        
        return await bot.handle_webhook(event_type, payload)

    def get_bot_status(self, company_id: str) -> Optional[GitHubBotStatus]:
        """Get status for a specific company's bot."""
        if company_id == "server":
            return self._server_bot.get_status() if self._server_bot else None
        return self._bots[company_id].get_status() if company_id in self._bots else None

    def get_all_statuses(self) -> List[GitHubBotStatus]:
        """Get statuses for all bots."""
        statuses = []
        if self._server_bot:
            statuses.append(self._server_bot.get_status())
        for bot in self._bots.values():
            statuses.append(bot.get_status())
        return statuses


# Global instance getter
async def get_github_bot_manager() -> GitHubBotManager:
    """Get the global GitHub bot manager instance."""
    return await GitHubBotManager.get_instance()
