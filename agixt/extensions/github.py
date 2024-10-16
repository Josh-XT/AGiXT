import os
import re
import time
import datetime
import requests
from pydantic import BaseModel
from typing import List
from Extensions import Extensions
from agixtsdk import AGiXTSDK
from Globals import getenv

try:
    import git
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "GitPython"])
    import git

try:
    from github import Github, RateLimitExceededException
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyGithub"])
    from github import Github, RateLimitExceededException


class Issue(BaseModel):
    issue_title: str
    issue_body: str


class Issues(BaseModel):
    issues: List[Issue]


class github(Extensions):
    def __init__(
        self,
        GITHUB_USERNAME: str = "",
        GITHUB_API_KEY: str = "",
        **kwargs,
    ):
        self.GITHUB_USERNAME = GITHUB_USERNAME
        self.GITHUB_API_KEY = GITHUB_API_KEY
        self.commands = {
            "Clone Github Repository": self.clone_repo,
            "Get Github Repository Code Contents": self.get_repo_code_contents,
            "Get Github Repository Issues": self.get_repo_issues,
            "Get Github Repository Issue": self.get_repo_issue,
            "Create Github Repository": self.create_repo,
            "Create Github Repository Issue": self.create_repo_issue,
            "Update Github Repository Issue": self.update_repo_issue,
            "Get Github Repository Pull Requests": self.get_repo_pull_requests,
            "Get Github Repository Pull Request": self.get_repo_pull_request,
            "Create Github Repository Pull Request": self.create_repo_pull_request,
            "Update Github Repository Pull Request": self.update_repo_pull_request,
            "Get Github Repository Commits": self.get_repo_commits,
            "Get Github Repository Commit": self.get_repo_commit,
            "Add Comment to Github Repository Issue": self.add_comment_to_repo_issue,
            "Add Comment to Github Repository Pull Request": self.add_comment_to_repo_pull_request,
            "Close Github Issue": self.close_issue,
            "Get List of My Github Repositories": self.get_my_repos,
            "Get List of Github Repositories by Username": self.get_user_repos,
            "Upload File to Github Repository": self.upload_file_to_repo,
            "Create and Merge Github Repository Pull Request": self.create_and_merge_pull_request,
            "Improve Github Repository Codebase": self.improve_codebase,
            "Copy Github Repository Contents": self.copy_repo_contents,
        }
        if self.GITHUB_USERNAME and self.GITHUB_API_KEY:
            try:
                self.gh = Github(self.GITHUB_API_KEY)
            except Exception as e:
                self.gh = None
        else:
            self.gh = None
        self.failures = 0
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else AGiXTSDK(
                base_uri=getenv("AGIXT_URI"),
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
            )
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )

    async def clone_repo(self, repo_url: str) -> str:
        """
        Clone a GitHub repository to the local workspace

        Args:
        repo_url (str): The URL of the GitHub repository to clone

        Returns:
        str: The result of the cloning operation
        """
        split_url = repo_url.split("//")
        if self.GITHUB_USERNAME is not None and self.GITHUB_API_KEY is not None:
            auth_repo_url = f"//{self.GITHUB_USERNAME}:{self.GITHUB_API_KEY}@".join(
                split_url
            )
        else:
            auth_repo_url = "//".join(split_url)
        try:
            repo_name = repo_url.split("/")[-1]
            repo_dir = os.path.join(self.WORKING_DIRECTORY, repo_name)
            if os.path.exists(repo_dir):
                # Pull the latest changes
                repo = git.Repo(repo_dir)
                repo.remotes.origin.pull()
                self.failures = 0
                return f"Pulled latest changes for {repo_url} to {repo_dir}"
            else:
                git.Repo.clone_from(
                    url=auth_repo_url,
                    to_path=repo_dir,
                )
            self.failures = 0
            return f"Cloned {repo_url} to {repo_dir}"
        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.clone_repo(repo_url)
            return f"Error: {str(e)}"

    async def create_repo(
        self, repo_name: str, content_of_readme: str, org: str = None
    ) -> str:
        """
        Create a new private GitHub repository

        Args:
        repo_name (str): The name of the repository to create
        content_of_readme (str): The content of the README.md file

        Returns:
        str: The URL of the newly created repository
        """
        try:
            if not org:
                try:
                    user = self.gh.get_organization(self.GITHUB_USERNAME)
                except:
                    user = self.gh.get_user(self.GITHUB_USERNAME)
            else:
                user = self.gh.get_organization(org)
            repo = user.create_repo(repo_name, private=True)
            repo_url = repo.clone_url
            repo_dir = os.path.join(self.WORKING_DIRECTORY, repo_name)
            repo = git.Repo.init(repo_dir)
            with open(f"{repo_dir}/README.md", "w") as f:
                f.write(content_of_readme)
            repo.git.add(A=True)
            repo.git.commit(m="Added README")
            repo.create_remote("origin", repo_url)
            repo.git.push("origin", "HEAD:main")
            self.failures = 0
            return repo_url
        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_repo(repo_name, content_of_readme)
            return f"Error: {str(e)}"

    async def get_repo_code_contents(self, repo_url: str) -> str:
        """
        Get the code contents of a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository

        Returns:
        str: The code contents of the repository in markdown format
        """
        repo_name = repo_url.split("/")[-1]
        await self.clone_repo(repo_url)
        output_file = os.path.join(self.WORKING_DIRECTORY, f"{repo_name}.md")
        python_files = []
        other_files = []
        powershell_files = []
        js_files = []
        ts_files = []
        kt_files = []
        lua_files = []
        xml_files = []
        md_files = []
        json_files = []
        gql_files = []
        sh_files = []

        for root, dirs, files in os.walk(
            os.path.join(self.WORKING_DIRECTORY, repo_name)
        ):
            for file in files:
                if "node_modules" in root or "node_modules" in file:
                    continue
                if "package-lock.json" in file:
                    continue
                if ".stories." in file:
                    continue
                if file.endswith(".py"):
                    python_files.append(os.path.join(root, file))
                elif file.endswith(".ps1"):
                    powershell_files.append(os.path.join(root, file))
                elif file in [
                    "Dockerfile",
                    "requirements.txt",
                    "static-requirements.txt",
                ] or file.endswith(".yml"):
                    other_files.append(os.path.join(root, file))
                elif file.endswith(".js") or file.endswith(".jsx"):
                    js_files.append(os.path.join(root, file))
                elif file.endswith(".ts") or file.endswith(".tsx"):
                    ts_files.append(os.path.join(root, file))
                elif file.endswith(".kt") or file.endswith(".java"):
                    kt_files.append(os.path.join(root, file))
                elif file.endswith(".lua"):
                    lua_files.append(os.path.join(root, file))
                elif file.endswith(".xml"):
                    # if path is app/src/main/res/layout, then we will add the xml files, but not other folders.
                    if "layout" in root.split(os.path.sep):
                        xml_files.append(os.path.join(root, file))
                elif file.endswith(".md"):
                    md_files.append(os.path.join(root, file))
                elif file.endswith(".json"):
                    json_files.append(os.path.join(root, file))
                elif file.endswith(".gql"):
                    gql_files.append(os.path.join(root, file))
                elif file.endswith(".sh"):
                    sh_files.append(os.path.join(root, file))

        if os.path.exists(output_file):
            os.remove(output_file)

        with open(output_file, "w", encoding="utf-8") as markdown_file:
            for file_paths, file_type in [
                (other_files, "yaml"),
                (powershell_files, "powershell"),
                (python_files, "python"),
                (js_files, "javascript"),
                (ts_files, "typescript"),
                (kt_files, "kotlin"),
                (lua_files, "lua"),
                (xml_files, "xml"),
                (md_files, "markdown"),
                (json_files, "json"),
                (gql_files, "graphql"),
                (sh_files, "shell"),
            ]:
                for file_path in file_paths:
                    # Make sure the file isn't output.md
                    if output_file in file_path:
                        continue
                    markdown_file.write(f"**{file_path}**\n")
                    with open(file_path, "r", encoding="utf-8") as code_file:
                        content = code_file.read()
                        markdown_file.write(f"```{file_type}\n{content}\n```\n\n")
        with open(output_file, "r", encoding="utf-8") as markdown_file:
            content = markdown_file.read()

        content = content.replace("<|endoftext|>", "")
        return content

    async def get_repo_issues(self, repo_url: str) -> str:
        """
        Get the open issues for a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository

        Returns:
        str: The open issues for the repository
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issues = repo.get_issues(state="open")
            issue_list = []
            for issue in issues:
                issue_list.append(f"#{issue.number}: {issue.title}")
            self.failures = 0
            return f"Open Issues for GitHub Repository at {repo_url}:\n\n" + "\n".join(
                issue_list
            )
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_issues(repo_url)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_issue(self, repo_url: str, issue_number: int) -> str:
        """
        Get the details of a specific issue in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        issue_number (int): The issue number to retrieve

        Returns:
        str: The details of the issue
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)
            self.failures = 0
            return f"Issue Details for GitHub Repository at {repo_url}\n\n{issue.number}: {issue.title}\n\n{issue.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_issue(repo_url, issue_number)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def create_repo_issue(
        self, repo_url: str, title: str, body: str, assignee: str = None
    ) -> str:
        """
        Create a new issue in a GitHub repository and create a new branch for it

        Args:
        repo_url (str): The URL of the GitHub repository
        title (str): The title of the issue
        body (str): The body of the issue
        assignee (str): The assignee for the issue

        Returns:
        str: The result of the issue creation operation and branch creation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.create_issue(title=title, body=body, assignee=assignee)

            # Create a new branch for the issue
            base_branch = repo.default_branch
            new_branch_name = f"issue-{issue.number}"
            repo.create_git_ref(
                f"refs/heads/{new_branch_name}", repo.get_branch(base_branch).commit.sha
            )

            self.failures = 0
            return f"Created new issue in GitHub Repository at {repo_url}\n\n{issue.number}: {issue.title}\n\n{issue.body}\n\nCreated new branch: {new_branch_name}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_repo_issue(
                    repo_url=repo_url, title=title, body=body, assignee=assignee
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def update_repo_issue(
        self,
        repo_url: str,
        issue_number: int,
        title: str,
        body: str,
        assignee: str = None,
    ) -> str:
        """
        Update an existing issue in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        issue_number (int): The issue number to update
        title (str): The new title of the issue
        body (str): The new body of the issue
        assignee (str): The new assignee for the issue

        Returns:
        str: The result of the issue update operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)
            issue.edit(title=title, body=body, assignee=assignee)
            self.failures = 0
            return f"Updated issue in GitHub Repository at {repo_url}\n\n{issue.number}: {issue.title}\n\n{issue.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.update_repo_issue(repo_url, issue_number, title, body)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_pull_requests(self, repo_url: str) -> str:
        """
        Get the open pull requests for a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository

        Returns:
        str: The open pull requests for the repository
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_requests = repo.get_pulls(state="open")
            pr_list = []
            for pr in pull_requests:
                pr_list.append(f"#{pr.number}: {pr.title}")
            self.failures = 0
            return (
                f"Open Pull Requests for GitHub Repository at {repo_url}:\n\n"
                + "\n".join(pr_list)
            )
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_pull_requests(repo_url)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_pull_request(
        self, repo_url: str, pull_request_number: int
    ) -> str:
        """
        Get the details of a specific pull request in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        pull_request_number (int): The pull request number to retrieve

        Returns:
        str: The details of the pull request
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.get_pull(pull_request_number)
            self.failures = 0
            return f"Pull Request Details for GitHub Repository at {repo_url}\n\n#{pull_request.number}: {pull_request.title}\n\n{pull_request.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_pull_request(repo_url, pull_request_number)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def create_repo_pull_request(
        self, repo_url: str, title: str, body: str, head: str, base: str
    ) -> str:
        """
        Create a new pull request in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        title (str): The title of the pull request
        body (str): The body of the pull request
        head (str): The branch to merge from
        base (str): The branch to merge to

        Returns:
        str: The result of the pull request creation operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.create_pull(
                title=title, body=body, head=head, base=base
            )
            self.failures = 0
            return f"Created new pull request #{pull_request.number} `{pull_request.title}`."
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_repo_pull_request(
                    repo_url, title, body, head, base
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def update_repo_pull_request(
        self, repo_url: str, pull_request_number: int, title: str, body: str
    ) -> str:
        """
        Update an existing pull request in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        pull_request_number (int): The pull request number to update
        title (str): The new title of the pull request
        body (str): The new body of the pull request

        Returns:
        str: The result of the pull request update operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.get_pull(pull_request_number)
            pull_request.edit(title=title, body=body)
            self.failures = 0
            return f"Updated pull request in GitHub Repository at {repo_url}\n\n#{pull_request.number}: {pull_request.title}\n\n{pull_request.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.update_repo_pull_request(
                    repo_url, pull_request_number, title, body
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_commits(self, repo_url: str, days: int = 7) -> str:
        """
        Get the commits for a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        days (int): The number of days to retrieve commits for (default is 7 days)

        Returns:
        str: The commits for the repository
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            if days == 0:
                commits = repo.get_commits()
            else:
                since = datetime.datetime.now() - datetime.timedelta(days=days)
                commits = repo.get_commits(since=since)
            commit_list = []
            for commit in commits:
                commit_list.append(f"{commit.sha}: {commit.commit.message}")
            self.failures = 0
            return (
                f"Commits for GitHub Repository at {repo_url} (last {days} days):\n\n"
                + "\n".join(commit_list)
            )
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_repo_commits(repo_url, days)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_repo_commit(self, repo_url: str, commit_sha: str) -> str:
        """
        Get the details of a specific commit in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        commit_sha (str): The commit SHA to retrieve

        Returns:
        str: The details of the commit
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            commit = repo.get_commit(commit_sha)
            self.failures = 0
            return f"Commit Details for GitHub Repository at {repo_url}\n\n{commit.sha}: {commit.commit.message}\n\n{commit.commit.author.name} ({commit.commit.author.email})\n\n{commit.files}"
        except RateLimitExceededException:
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def add_comment_to_repo_issue(
        self,
        repo_url: str,
        issue_number: int,
        comment_body: str,
        close_issue: bool = False,
    ) -> str:
        """
        Add a comment to an issue in a GitHub repository and optionally close the issue

        Args:
        repo_url (str): The URL of the GitHub repository
        issue_number (int): The issue number to add a comment to
        comment_body (str): The body of the comment
        close_issue (bool): Whether to close the issue after adding the comment (default: False)

        Returns:
        str: The result of the comment addition operation and issue closure if applicable
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)
            comment = issue.create_comment(comment_body)

            result = f"Added comment to issue #{issue.number} in GitHub Repository at {repo_url}\n\n{comment.body}"

            if close_issue:
                issue.edit(state="closed")
                result += f"\n\nIssue #{issue.number} has been closed."

            self.failures = 0
            return result
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.add_comment_to_repo_issue(
                    repo_url, issue_number, comment_body, close_issue
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def add_comment_to_repo_pull_request(
        self, repo_url: str, pull_request_number: int, comment_body: str
    ) -> str:
        """
        Add a comment to a pull request in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        pull_request_number (int): The pull request number to add a comment to
        comment_body (str): The body of the comment

        Returns:
        str: The result of the comment addition operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.get_pull(pull_request_number)
            comment = pull_request.create_issue_comment(comment_body)
            self.failures = 0
            return f"Added comment to pull request #{pull_request.number} in GitHub Repository at {repo_url}\n\n{comment.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.add_comment_to_repo_pull_request(
                    repo_url, pull_request_number, comment_body
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def close_issue(self, repo_url, issue_number):
        """
        Close an issue in a GitHub repository

        Args:
        repo_url (str): The URL of the GitHub repository
        issue_number (int): The issue number to close

        Returns:
        str: The result of the issue closure operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)

            # Close the ticket
            issue.edit(state="closed")

            self.failures = 0
            return (
                f"Closed ticket in GitHub Repository: {repo_url}, Issue #{issue_number}"
            )
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.close_ticket(repo_url, issue_number)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def get_my_repos(self) -> str:
        """
        Get all repositories that the token is associated with the owner owning or collaborating on repositories.

        Returns:
        str: Repository list separated by new lines.
        """
        try:
            all_repos = []
            page = 1
            while True:
                response = requests.get(
                    f"https://api.github.com/user/repos?type=all&page={page}",
                    headers={
                        "Authorization": f"token {self.GITHUB_API_KEY}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                repos = response.json()
                if not repos:
                    break
                all_repos.extend(repos)
                page += 1
            repo_list = []
            for repo in all_repos:
                repo_name = repo["full_name"]
                if not repo["archived"]:
                    repo_list.append(repo_name)
            self.failures = 0
            return f"### Accessible Github Repositories\n\n" + "\n".join(repo_list)
        except requests.exceptions.RequestException as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_my_repos()
            return f"Error: {str(e)}"

    async def get_user_repos(self, username):
        """
        Get all repositories that the user owns or is a collaborator on.

        Args:
        username (str): The username of the user to get repositories for.

        Returns:
        str: Repository list separated by new lines.
        """
        try:
            all_repos = []
            page = 1
            while True:
                response = requests.get(
                    f"https://api.github.com/users/{username}/repos?type=all&page={page}",
                    headers={
                        "Authorization": f"token {self.GITHUB_API_KEY}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                repos = response.json()
                if not repos:
                    break
                all_repos.extend(repos)
                page += 1
            repo_list = []
            for repo in all_repos:
                repo_name = repo["full_name"]
                if not repo["archived"]:
                    repo_list.append(repo_name)
            self.failures = 0
            return f"Repositories for {username}:\n\n" + "\n".join(repo_list)
        except requests.exceptions.RequestException as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.get_user_repos(username)
            return f"Error: {str(e)}"

    async def upload_file_to_repo(
        self,
        repo_url: str,
        file_path: str,
        file_content: str,
        branch: str = "main",
        commit_message: str = "Upload file",
    ) -> str:
        """
        Upload a file to a GitHub repository, creating the branch if it doesn't exist

        Args:
        repo_url (str): The URL of the GitHub repository
        file_path (str): The full path where the file should be stored in the repo
        file_content (str): The content of the file to be uploaded
        branch (str): The branch to upload to (default is "main")
        commit_message (str): The commit message for the file upload

        Returns:
        str: The result of the file upload operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])

            # Check if the branch exists, create it if it doesn't
            try:
                repo.get_branch(branch)
            except Exception:
                # Branch doesn't exist, so create it
                default_branch = repo.default_branch
                source_branch = repo.get_branch(default_branch)
                repo.create_git_ref(
                    ref=f"refs/heads/{branch}", sha=source_branch.commit.sha
                )

            # Check if file already exists
            try:
                contents = repo.get_contents(file_path, ref=branch)
                repo.update_file(
                    contents.path,
                    commit_message,
                    file_content,
                    contents.sha,
                    branch=branch,
                )
                action = "Updated"
            except Exception:
                repo.create_file(file_path, commit_message, file_content, branch=branch)
                action = "Created"

            self.failures = 0
            return f"{action} file '{file_path}' in GitHub Repository at {repo_url} on branch '{branch}'"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.upload_file_to_repo(
                    repo_url, file_path, file_content, branch, commit_message
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def create_and_merge_pull_request(
        self,
        repo_url: str,
        title: str,
        body: str,
        head: str,
        base: str,
        merge_method: str = "squash",
    ) -> str:
        """
        Create a new pull request in a GitHub repository and automatically merge it

        Args:
        repo_url (str): The URL of the GitHub repository
        title (str): The title of the pull request
        body (str): The body of the pull request
        head (str): The branch to merge from
        base (str): The branch to merge to
        merge_method (str): The merge method to use (default is "merge", options are "merge", "squash", "rebase")

        Returns:
        str: The result of the pull request creation and merge operation
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.create_pull(
                title=title, body=body, head=head, base=base
            )
            result = f"Created new pull request #{pull_request.number} `{pull_request.title}`"
            # Check if the pull request can be merged
            if pull_request.mergeable:
                if merge_method == "squash":
                    merge_result = pull_request.merge(merge_method="squash")
                elif merge_method == "rebase":
                    merge_result = pull_request.merge(merge_method="rebase")
                else:
                    merge_result = pull_request.merge()

                if merge_result.merged:
                    result += f" and merged."
                else:
                    result += f". Failed to merge pull request. Reason: {merge_result.message}"
            else:
                result += f". Pull request #{pull_request.number} cannot be merged automatically. Please resolve conflicts and merge manually."
            self.failures = 0
            return result
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_and_merge_pull_request(
                    repo_url, title, body, head, base, merge_method
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def improve_codebase(
        self,
        idea: str,
        repo_org: str,
        repo_name: str,
        additional_context: str = "",
        auto_merge: bool = True,
    ):
        """
        Improve the codebase of a GitHub repository by scoping necessary work to implement changes based on a provided idea.

        Args:
        idea (str): The idea to improve the codebase
        repo_org (str): The organization of the GitHub repository
        repo_name (str): The name of the GitHub repository
        additional_context (str): Additional context to provide for the improvement. Useful for injecting additional documentation or code that isn't in the repository or agent's memory.
        auto_merge (bool): Whether to automatically merge pull requests (default is True)
        """
        repo_url = f"https://github.com/{repo_org}/{repo_name}"
        repo_content = await self.get_repo_code_contents(repo_url=repo_url)
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[ACTIVITY] Scoping necessary work to implement changes to [{repo_org}/{repo_name}]({repo_url}).",
            conversation_name=self.conversation_name,
        )
        scope = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"""### Presented Idea
{idea}

## User
Please take the presented idea and write a detailed scope for a junior developer to build out the remaining code using the provided code from the repository.
Follow all patterns in the current framework to maintain maintainability and consistency.
The developer may have little to no guidance outside of this scope.""",
                "context": f"### Content of {repo_url}\n\n{repo_content}\n{additional_context}",
                "auto_continue": True,
                "log_user_input": False,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )
        issues = self.ApiClient.convert_to_model(
            context=f"### Content of {repo_url}\n\n{repo_content}\n{additional_context}",
            input_string=f"### Scope of Work\n\n{scope}\nPlease create a GitHub issue for each task in the scope of work. Each issue should have detailed instructions for the junior developer to complete the task. The developer may have little to no guidance outside of these issues. The instructions should be clear and concise, and should include any necessary code snippets.",
            model=Issues,
            agent_name=self.agent_name,
        )
        issues = issues.model_dump()
        issue_count = len(issues["issues"])
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[ACTIVITY] Creating {issue_count} issues in the repository.",
            conversation_name=self.conversation_name,
        )
        x = 0
        for issue in issues["issues"]:
            x += 1
            title = issue["issue_title"]
            body = issue["issue_body"]
            new_issue = await self.create_repo_issue(
                repo_url=repo_url, title=title, body=body
            )
            issue_number = new_issue.split(f"{repo_url}\n\n")[-1].split(":")[-1]
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[ACTIVITY] ({x}/{issue_count}) Resolving #{issue_number} `{title}`.",
                conversation_name=self.conversation_name,
            )
            comment_content = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"""GitHub Issue: {title}
{body}

Please review the GitHub issue and show the full content of each modified file to solve this issue. Please do not use placeholders in code as they will break automation causing unintended consequences.

When referencing files in the issue, please use the following format:

## File: `src/pages/example.py`
```python
// Code snippet here
```""",
                    "context": f"""### Content of {repo_url}\n\n{repo_content}\n{additional_context}\n### Scope of Work\n\n{scope}""",
                    "auto_continue": True,
                    "log_user_input": False,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )
            files_to_modify = []
            for file_path, code_snippet in re.findall(
                r"## File: `(.+?)`\n```(.+?)\n(.+?)\n```", comment_content
            ):
                files_to_modify.append(
                    {"file_path": file_path, "code_snippet": code_snippet}
                )
            for file in files_to_modify:
                # Save each of the files to the front end repo folder
                file_path = file["file_path"]
                if file_path.startswith("/"):
                    file_path = file_path[1:]
                if file_path.startswith("./"):
                    file_path = file_path[2:]
                # Upload file to the branch for the issue, the branch name is the issue number
                await self.upload_file_to_repo(
                    repo_url=repo_url,
                    file_path=file_path,
                    file_content=file["code_snippet"],
                    branch=issue_number,
                    commit_message=f"Resolve #{issue_number}",
                )
            # Create and merge the pull request.
            if auto_merge:
                pull_request = await self.create_and_merge_pull_request(
                    repo_url=repo_url,
                    title=f"Resolve #{issue_number}",
                    body=f"Resolves #{issue_number} \n{comment_content}",
                    head=issue_number,
                    base="main",
                    merge_method="squash",
                )
            else:
                pull_request = await self.create_repo_pull_request(
                    repo_url=repo_url,
                    title=f"Resolve #{issue_number}",
                    body=f"Resolves #{issue_number} \n{comment_content}",
                    head=issue_number,
                    base="main",
                )
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[ACTIVITY] ({x}/{issue_count}) {pull_request}",
                conversation_name=self.conversation_name,
            )
        response = f"I have created {issue_count} issues based on the provided information, then resolved each issue by creating a pull request."
        if auto_merge:
            response += " Each pull request was automatically merged."
        return response

    async def copy_repo_contents(
        self,
        source_repo_url: str,
        destination_repo_url: str,
        branch: str = "main",
    ) -> str:
        """
        Copy the contents of a source repository to a destination repository without forking.

        Args:
        source_repo_url (str): The URL of the source GitHub repository
        destination_repo_url (str): The URL of the destination GitHub repository
        branch (str): The branch to copy from and to (default is "main")

        Returns:
        str: The result of the repository content copy operation
        """
        try:
            source_repo = self.gh.get_repo(source_repo_url.split("github.com/")[-1])
            dest_repo = self.gh.get_repo(destination_repo_url.split("github.com/")[-1])

            # Get all files from the source repository
            contents = source_repo.get_contents("", ref=branch)
            files_copied = 0

            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    contents.extend(
                        source_repo.get_contents(file_content.path, ref=branch)
                    )
                else:
                    try:
                        # Get the file content from the source repo
                        file = source_repo.get_contents(file_content.path, ref=branch)
                        file_data = file.decoded_content

                        # Check if file exists in destination repo
                        try:
                            dest_file = dest_repo.get_contents(
                                file_content.path, ref=branch
                            )
                            # Update existing file
                            dest_repo.update_file(
                                file_content.path,
                                f"Update {file_content.path}",
                                file_data,
                                dest_file.sha,
                                branch=branch,
                            )
                        except Exception:
                            # Create new file if it doesn't exist
                            dest_repo.create_file(
                                file_content.path,
                                f"Create {file_content.path}",
                                file_data,
                                branch=branch,
                            )

                        files_copied += 1

                    except Exception as e:
                        return f"Error copying file {file_content.path}: {str(e)}"

            self.failures = 0
            return f"Successfully copied {files_copied} files from {source_repo_url} to {destination_repo_url} on branch '{branch}'"

        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.copy_repo_contents(
                    source_repo_url, destination_repo_url, branch
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"
