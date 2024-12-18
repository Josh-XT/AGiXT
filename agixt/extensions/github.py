import os
import re
import time
import datetime
import requests
import difflib
from pydantic import BaseModel
from typing import List, Literal, Union
from Extensions import Extensions
from agixtsdk import AGiXTSDK
from Globals import getenv
from dataclasses import dataclass
import logging

try:
    import black
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "black"])
    import black

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
import xml.etree.ElementTree as ET


class Issue(BaseModel):
    issue_title: str
    issue_body: str


class Issues(BaseModel):
    issues: List[Issue]


@dataclass
class CodeBlock:
    start_line: int
    end_line: int
    content: str


@dataclass
class FileModification:
    operation: Literal["replace", "insert", "delete"]
    target: Union[str, CodeBlock]
    new_content: str = None
    context_lines: int = 3
    fuzzy_match: bool = True


class GitHubErrorRecovery:
    def __init__(self, api_client, agent_name: str, conversation_name: str = ""):
        self.api_client = api_client
        self.agent_name = agent_name
        self.conversation_name = conversation_name

    async def retry_with_context(
        self,
        error_msg: str,
        repo_url: str,
        file_path: str,
        original_modifications: str,
        activity_id: str = None,
        retry_count: int = 0,
    ) -> str:
        """
        Retry a failed modification by providing the error context back to the model.
        """
        # Log the retry attempt
        logging.info(f"Retry attempt #{retry_count + 1} for {file_path}")
        if activity_id:
            self.api_client.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{activity_id}] Retry attempt #{retry_count + 1} for {file_path}: {error_msg}",
                conversation_name=self.conversation_name,
            )

        # Extract the useful parts of the error message
        error_context = self._parse_error_message(error_msg)

        # If we received an empty error context or hit retry limit, raise an error
        if not error_context:
            raise ValueError(
                f"[Attempt #{retry_count + 1}] Unable to process modifications: {error_msg}"
            )

        # Check if the modifications are already in the correct format
        if self._is_valid_modification_format(original_modifications):
            raise ValueError(f"Invalid modification result: {error_msg}")

        # Construct the retry prompt with improved context
        retry_prompt = f"""Retry attempt #{retry_count + 1}. The previous modification attempt failed. Here's what I found:

{error_context}

Please provide new modification commands that:
1. Only use existing functions/classes as targets
2. Maintain the same intended functionality
3. Use the correct syntax and indentation
4. Only reference existing dependencies and functions
5. Ensure the file path is correct
6. Try something else, like a shorter target that will fit and match better

Please provide the modifications in the same XML format:
<modification>
<file>{file_path}</file>
<operation>insert|replace|delete</operation>
<target>[one of the existing functions shown above]</target>
<content>
[your new code here]
</content>
<fuzzy_match>true|false</fuzzy_match>
</modification>

Original intended changes were:
{original_modifications}"""

        try:
            # Get new modifications from the model with a timeout
            new_modifications = self.api_client.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": retry_prompt,
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )

            if activity_id:
                self.api_client.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{activity_id}] Retrying modification with corrected targets",
                    conversation_name=self.conversation_name,
                )
            return new_modifications

        except Exception as e:
            # If prompt fails, raise a clear error
            raise ValueError(f"Failed to generate new modifications: {str(e)}")

    def _parse_error_message(self, error_msg: str) -> str:
        """
        Parse the error message to extract the most useful information for the model.
        """
        # If it's our detailed error format with available functions
        if "Available function definitions:" in error_msg:
            return error_msg

        # If it's a match score error
        if "Best match score" in error_msg:
            return error_msg

        # For other errors, provide a more structured message
        return f"Error encountered: {error_msg}\n\nPlease ensure the target exists in the file and the modification is valid."

    def _is_valid_modification_format(self, modifications: str) -> bool:
        """
        Check if the modifications string is already in the correct XML format.
        """
        required_tags = ["<modification>", "<file>", "<operation>", "<target>"]
        return all(tag in modifications for tag in required_tags)


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
            "Modify File Content on Github": self.modify_file_content,
            "Replace in File on Github": self.replace_in_file,
            "Insert in File on Github": self.insert_in_file,
            "Delete from File on Github": self.delete_from_file,
            "Fix GitHub Issue": self.fix_github_issue,
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
        self.activity_id = kwargs["activity_id"] if "activity_id" in kwargs else None

    def _is_python_file(self, file_path: str) -> bool:
        """
        Check if a file is a Python file based on its extension.

        Args:
            file_path (str): Path to the file

        Returns:
            bool: True if the file is a Python file, False otherwise
        """
        return file_path.endswith(".py")

    def _format_python_code(self, content: str) -> str:
        """
        Format Python code using Black.

        Args:
            content (str): Python code content to format

        Returns:
            str: Formatted Python code
        """
        try:
            mode = black.Mode(
                target_versions={black.TargetVersion.PY37},
                line_length=88,
                string_normalization=True,
                is_pyi=False,
            )
            formatted_content = black.format_str(content, mode=mode)
            return formatted_content
        except Exception as e:
            logging.warning(f"Failed to format Python code with Black: {str(e)}")
            return content

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
        branch = None
        if "/tree/" in repo_url:
            # Extract branch name and clean up repo URL
            base_url, branch_path = repo_url.split("/tree/", 1)
            branch = branch_path.split("/")[0]
            repo_url = base_url
            repo_name = repo_url.split("/")[-1]
        else:
            repo_name = repo_url.split("/")[-1]

        # Clone the repository (with branch if specified)
        clone_result = await self.clone_repo(repo_url)
        if "Error:" in clone_result:
            return f"Error cloning repository: {clone_result}"

        # If a branch was specified, checkout that branch
        if branch:
            repo_dir = os.path.join(self.WORKING_DIRECTORY, repo_name)
            try:
                repo = git.Repo(repo_dir)
                repo.git.checkout(branch)
            except Exception as e:
                return f"Error checking out branch {branch}: {str(e)}"

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
        Create a new issue in a GitHub repository with an optional assignee

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
            try:
                issue = repo.create_issue(title=title, body=body, assignee=assignee)
            except Exception as e:
                issue = repo.create_issue(title=title, body=body)
            self.failures = 0
            return f"Created new issue in GitHub Repository at {repo_url}\n\n{issue.number}: {issue.title}\n\n{issue.body}"
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
            if "/WORKSPACE/" in file_path:
                file_path = file_path.split("/WORKSPACE/")[-1]
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
            return f"{action} file '{file_path}' in GitHub Repository at {repo_url} on branch [{branch}]({repo_url}/tree/{branch})"
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
        auto_merge: bool = False,
    ) -> str:
        """
            Improve the codebase of a GitHub repository by:

            1. Taking an initial idea and producing a set of issues that detail the tasks needed.
            2. For each generated issue, prompting the model to produce minimal code modifications using the <modification> XML format.
            3. Applying those modifications to a branch associated with the issue.
            4. Creating a pull request for each issue, optionally merging it automatically.

            Args:
                idea (str): The idea to improve the codebase.
                repo_org (str): The organization or username for the GitHub repository.
                repo_name (str): The repository name.
                additional_context (str): Additional context to provide to the model.
                auto_merge (bool): If True, automatically merges the created pull requests after applying changes.

            Returns:
                str: A summary message indicating the number of issues and pull requests created.

            Model Behavior:
                - Initially, the model is asked to produce a scope of work and then create issues.
                - For each issue, we prompt the model again to provide minimal code modifications as <modification> blocks.
                - We apply those modifications with `modify_file_content`.

            Example of Expected Model Output for the second prompt per issue:
                <modification>
                    <operation>replace</operation>
                    <target>def old_function():
        pass</target>
                    <content>def old_function():
        return "fixed"</content>
                    <fuzzy_match>true</fuzzy_match>
                </modification>
        """
        repo_url = f"https://github.com/{repo_org}/{repo_name}"
        repo_content = await self.get_repo_code_contents(repo_url=repo_url)
        self.activity_id = self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{self.activity_id}] Improving [{repo_org}/{repo_name}]({repo_url}).",
            conversation_name=self.conversation_name,
        )

        # Prompt the model for a scope of work
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{self.activity_id}] Scoping necessary work to implement changes to [{repo_org}/{repo_name}]({repo_url}).",
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
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

        # Convert the scope into issues
        issues = self.ApiClient.convert_to_model(
            context=f"### Content of {repo_url}\n\n{repo_content}\n{additional_context}",
            input_string=(
                f"### Scope of Work\n\n{scope}\n"
                "Please create a GitHub issue for each task in the scope of work. "
                "Each issue should have detailed instructions for the junior developer to complete the task. "
                "The developer may have little to no guidance outside of these issues. "
                "The instructions should be clear and concise, and should include any necessary code snippets."
            ),
            model=Issues,
            agent_name=self.agent_name,
            disable_commands=True,
            tts=False,
            browse_links=False,
            websearch=False,
            analyze_user_input=False,
            log_user_input=False,
            log_output=False,
            conversation_name=self.conversation_name,
        )
        issues = issues.model_dump()
        issue_count = len(issues["issues"])
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{self.activity_id}] Creating {issue_count} issues in the repository.",
            conversation_name=self.conversation_name,
        )

        # Process each issue: create it, then fix it
        x = 0
        for issue in issues["issues"]:
            x += 1
            title = issue["issue_title"]
            body = issue["issue_body"]
            new_issue = await self.create_repo_issue(
                repo_url=repo_url, title=title, body=body
            )
            # Parse issue number
            issue_number_line = new_issue.split("\n")[
                3
            ]  # The line that contains issue number
            # Example line: "{issue_number}: {issue.title}"
            # We'll extract the issue number:
            issue_number = issue_number_line.split(":")[0].strip()

            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] ({x}/{issue_count}) Resolving #{issue_number} `{title}`.",
                conversation_name=self.conversation_name,
            )

            # Prompt the model for minimal modifications in <modification> format to fix this issue
            modifications_xml = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"""GitHub Issue: {title}
{body}

Below is the repository code and additional context. Identify the minimal code changes needed to solve this issue. 
You must ONLY return the necessary modifications in the following XML format:

<modification>
<operation>replace|insert|delete</operation>
<target>original_code_block_or_line_number</target>
<content>new_code_block_if_needed</content>
<fuzzy_match>true|false</fuzzy_match>
</modification>

If multiple modifications are needed, repeat the <modification> block. Do not return anything other than <modification> blocks.

### Important:
- Do not return entire files, only the minimal code modifications required.
- For replace, insert, and delete operations:
  - "target" can be a code snippet or a line number.
  - "content" is required for replace and insert, optional for delete.
  - "fuzzy_match" defaults to true if not provided.
""",
                    "context": f"""### Content of {repo_url}\n\n{repo_content}\n{additional_context}\n### Scope of Work\n\n{scope}""",
                    "log_user_input": False,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "disable_commands": True,
                    "conversation_name": self.conversation_name,
                },
            )

            # The issue branch created by create_repo_issue should be "issue-{issue_number}"
            # Since we have issue_number extracted from the string, we should ensure the branch name matches.
            # The create_repo_issue method uses "issue-{issue_number}" as the branch name.
            # We'll confirm that and use that branch.
            issue_branch = f"issue-{issue_number}"

            # Since no file_path is directly known, we rely on modify_file_content to parse the target code blocks.
            # If the modification blocks reference code that can be found, it will work.
            # If the model includes file paths in the target, you can adjust modify_file_content or prompt strategy accordingly.
            modification_result = await self.modify_file_content(
                repo_url=repo_url,
                file_path="",  # If needed, the prompt can be updated to include file paths in <modification> blocks.
                modification_commands=modifications_xml,
                branch=issue_branch,
            )

            # Create and optionally merge the pull request
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] ({x}/{issue_count}) Creating pull request to resolve #{issue_number}.",
                conversation_name=self.conversation_name,
            )
            pr_body = f"Resolves #{issue_number}\n\nThe following modifications were applied:\n\n{modifications_xml}"
            if auto_merge:
                pull_request = await self.create_and_merge_pull_request(
                    repo_url=repo_url,
                    title=f"Resolve #{issue_number}",
                    body=pr_body,
                    head=issue_branch,
                    base="main",
                    merge_method="squash",
                )
            else:
                pull_request = await self.create_repo_pull_request(
                    repo_url=repo_url,
                    title=f"Resolve #{issue_number}",
                    body=pr_body,
                    head=issue_branch,
                    base="main",
                )

            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] ({x}/{issue_count}) {pull_request}",
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
            return f"Successfully copied {files_copied} files from {source_repo_url} to {destination_repo_url} on branch [{branch}]({destination_repo_url}/tree/{branch})"

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

    def _normalize_code(self, code: str, preserve_indent: bool = False) -> str:
        """Normalize code for comparison while preserving language-specific formatting.

        Args:
            code (str): The code to normalize
            preserve_indent (bool): Whether to preserve indentation (True for Python)

        Returns:
            str: Normalized code string
        """
        # Split into lines, optionally preserving indentation
        if preserve_indent:
            lines = [line.rstrip() for line in code.splitlines()]
        else:
            lines = [line.strip() for line in code.splitlines()]

        # Remove empty lines at start and end while preserving internal empty lines
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        # Detect if this is Python code
        is_python = any(re.match(r"^\s*(def|class)\s+", line) for line in lines)

        # Track base indentation if preserving
        if preserve_indent and lines:
            base_indent = len(lines[0]) - len(lines[0].lstrip())
        else:
            base_indent = 0

        # Normalize with language-specific rules
        normalized = []
        for line in lines:
            if line.strip():
                normalized_line = line

                if is_python:
                    # For Python, preserve spaces after commas and preserve string quotes
                    if preserve_indent:
                        # Calculate relative indentation
                        current_indent = len(line) - len(line.lstrip())
                        indent_level = current_indent - base_indent
                        # Normalize the non-whitespace part
                        content = line.lstrip()
                        content = re.sub(r",(?=\S)", ", ", content)
                        content = re.sub(r"\s+,", ",", content)
                        # Preserve the correct indentation
                        normalized_line = " " * max(0, indent_level) + content
                    else:
                        normalized_line = re.sub(r",(?=\S)", ", ", line.strip())
                        normalized_line = re.sub(r"\s+,", ",", normalized_line)
                else:
                    # For other languages (JS/TS), apply more aggressive normalization
                    content = line.strip()
                    content = re.sub(r"`\${(.*?)}`", r"'" + r"\1" + r"'", content)
                    content = re.sub(r"`([^`]*?)`", r"'\1'", content)
                    content = re.sub(r'"([^"]*?)"', r"'\1'", content)
                    content = re.sub(r"\s*([=!<>+\-*/])\s*", r"\1", content)
                    content = re.sub(r",\s+", ",", content)
                    if preserve_indent:
                        current_indent = len(line) - len(line.lstrip())
                        indent_level = current_indent - base_indent
                        normalized_line = " " * max(0, indent_level) + content
                    else:
                        normalized_line = content

                normalized.append(normalized_line)
            else:
                normalized.append("")

        return "\n".join(normalized)

    def _find_pattern_boundaries(
        self,
        file_lines: List[str],
        target: str,
        fuzzy_match: bool = True,
        operation: str = None,
    ) -> tuple[int, int, int]:
        """Find start and end line indices of the target code block in file lines."""
        # Detect if this is Python code
        is_python = any(
            re.match(r"^\s*(def|class)\s+", line) for line in target.splitlines()
        )

        # Normalize target preserving indentation for Python
        target_normalized = self._normalize_code(target, preserve_indent=is_python)
        target_lines = target_normalized.splitlines()
        target_first_line = next((line for line in target_lines if line.strip()), "")

        # Get base indentation of target
        target_base_indent = (
            len(target_first_line) - len(target_first_line.lstrip())
            if target_first_line
            else 0
        )

        # Special handling for insertions after top-level definitions
        if operation == "insert" and re.match(
            r"^(\s*)(@.*\n)?(async\s+)?(?:def|class)\s+\w+", target_first_line
        ):
            return self._handle_insertion_point(file_lines, target_first_line.lstrip())

        # For replace/delete operations
        best_matches = []
        window_size = len(target_lines)

        # Slide through the file looking for matches
        for i in range(len(file_lines) - window_size + 1):
            # Get a window of lines and normalize them the same way
            window = "\n".join(file_lines[i : i + window_size])
            window_normalized = self._normalize_code(window, preserve_indent=is_python)

            # For Python code, check indentation consistency
            if is_python:
                window_first_line = next(
                    (line for line in window_normalized.splitlines() if line.strip()),
                    "",
                )
                window_indent = (
                    len(window_first_line) - len(window_first_line.lstrip())
                    if window_first_line
                    else 0
                )
                if (
                    abs(window_indent - target_base_indent) > 4
                ):  # Allow for one level of indentation difference
                    continue

            # Calculate similarity using SequenceMatcher
            similarity = difflib.SequenceMatcher(
                None, window_normalized, target_normalized
            ).ratio()

            if similarity > 0:
                # Get indentation of first line
                indent = (
                    len(file_lines[i]) - len(file_lines[i].lstrip())
                    if file_lines[i]
                    else 0
                )

                best_matches.append(
                    {
                        "start_line": i,
                        "score": similarity,
                        "segment": file_lines[i : i + window_size],
                        "indent": indent,
                    }
                )

        if not best_matches:
            # Provide detailed error message with available functions
            error_msg = self._generate_error_message(file_lines, target_first_line)
            raise ValueError(error_msg)

        # Sort by match score and line count similarity
        best_matches.sort(
            key=lambda x: (x["score"], -abs(len(x["segment"]) - len(target_lines))),
            reverse=True,
        )
        best_match = best_matches[0]

        # For fuzzy matches, require minimum threshold
        threshold = 0.4 if fuzzy_match else 0.9
        if best_match["score"] < threshold:
            error_msg = [
                f"Best match score ({best_match['score']:.2f}) below threshold ({threshold}).",
                "",
                "Target:",
                target,
                "",
                "Best matching segment found:",
                "\n".join(best_match["segment"]),
                "",
                "Please provide a more accurate target.",
            ]
            raise ValueError("\n".join(error_msg))

        return (
            best_match["start_line"],
            best_match["start_line"] + len(target_lines),
            best_match["indent"] // 4,  # Assuming 4-space indentation
        )

    def _handle_insertion_point(
        self, file_lines: List[str], target_first_line: str
    ) -> tuple[int, int, int]:
        """Handle finding insertion points for new code blocks.

        Args:
            file_lines: List of lines from the file
            target_first_line: The first line of the target block

        Returns:
            tuple: (insertion_line, insertion_line, indent_level)
        """
        function_matches = []

        # First try exact match
        for i, line in enumerate(file_lines):
            if line.strip() == target_first_line:
                function_matches.append(i)

        # If no exact match found, try fuzzy matching
        if not function_matches:
            similar_functions = []
            highest_score = 0
            best_match_index = -1

            # Try to match function/class definitions
            target_func_name = re.search(r"(?:def|class)\s+(\w+)", target_first_line)
            if target_func_name:
                func_name = target_func_name.group(1)
                for i, line in enumerate(file_lines):
                    if re.match(r"^(\s*)(async\s+)?(def|class)\s+\w+", line):
                        other_func = re.search(r"(?:def|class)\s+(\w+)", line.strip())
                        if other_func:
                            other_name = other_func.group(1)
                            score = difflib.SequenceMatcher(
                                None, func_name, other_name
                            ).ratio()
                            if score > 0.6 and score > highest_score:
                                highest_score = score
                                best_match_index = i
                                similar_functions.append(line.strip())

            # If we found a good match, use it
            if best_match_index != -1:
                function_matches.append(best_match_index)
            else:
                # If still no matches found, provide helpful error
                error_msg = [
                    f"Function/class definition not found: {target_first_line}",
                ]
                if similar_functions:
                    error_msg.extend(
                        [
                            "",
                            "Did you mean one of these?",
                            *[f"- {func}" for func in similar_functions],
                        ]
                    )
                error_msg.extend(
                    [
                        "",
                        "Please use an existing function/class definition as the target.",
                    ]
                )
                raise ValueError("\n".join(error_msg))

        # Find the end of the function scope
        i = function_matches[
            0
        ]  # Now safe since we either have matches or raised an error
        target_indent = len(file_lines[i]) - len(file_lines[i].lstrip())

        # Look for the end of the current scope
        while i + 1 < len(file_lines):
            next_line = file_lines[i + 1]
            if not next_line.strip():  # Skip empty lines
                i += 1
                continue
            next_indent = len(next_line) - len(next_line.lstrip())
            if next_indent <= target_indent:  # Found end of scope
                break
            i += 1

        return i + 1, i + 1, target_indent // 4

    def _parse_modification_block(self, modification_block: str) -> dict:
        """Parse a single modification block into its components.

        Args:
            modification_block (str): Raw XML string containing a single modification

        Returns:
            dict: Parsed modification with operation, target, content, and fuzzy_match
        """
        try:
            # Debug logging
            logging.debug(f"Parsing modification block:\n{modification_block}")

            def escape_code_content(xml_str: str) -> str:
                """Escape code content by wrapping in CDATA sections."""

                def wrap_in_cdata(match):
                    tag_name = match.group(1)
                    content = match.group(2)
                    # Always wrap code content in CDATA
                    return f"<{tag_name}><![CDATA[{content}]]></{tag_name}>"

                # Use a more precise regex that captures the entire tag content
                pattern = r"<(target|content)>(.*?)</\1>"
                return re.sub(pattern, wrap_in_cdata, xml_str, flags=re.DOTALL)

            # First, normalize the XML structure
            clean_xml = re.sub(r"\s+<", "<", modification_block.strip())
            clean_xml = re.sub(r">\s+", ">", clean_xml)
            clean_xml = re.sub(r"\s+</modification>", "</modification>", clean_xml)

            # Then escape the code content
            clean_xml = escape_code_content(clean_xml)

            try:
                root = ET.fromstring(clean_xml)
            except ET.ParseError as xml_error:
                # Enhanced error reporting
                lines = clean_xml.split("\n")
                position = (
                    xml_error.position[0]
                    if isinstance(xml_error.position, tuple)
                    else xml_error.position
                )
                line_num = sum(1 for _ in clean_xml[:position].splitlines())

                # Find the problematic line and show context
                context_lines = []
                for i in range(max(0, line_num - 2), min(len(lines), line_num + 3)):
                    prefix = ">>> " if i == line_num - 1 else "    "
                    context_lines.append(f"{prefix}{lines[i]}")

                error_context = "\n".join(
                    [
                        f"XML Parse Error near line {line_num}:",
                        *context_lines,
                        f"Error details: {str(xml_error)}",
                    ]
                )

                raise ValueError(error_context)

            # Extract components
            try:
                operation = root.find("operation").text.strip()
                if operation not in ["replace", "insert", "delete"]:
                    raise ValueError(f"Invalid operation '{operation}'")

                target = root.find("target").text
                if not target:
                    raise ValueError("Empty target tag")

                content = root.find("content")
                content = content.text if content is not None else None
                if operation in ["replace", "insert"] and not content:
                    raise ValueError(f"Content required for {operation} operation")

                fuzzy_match = True
                fuzzy_elem = root.find("fuzzy_match")
                if fuzzy_elem is not None:
                    fuzzy_match = fuzzy_elem.text.lower() != "false"

                return {
                    "operation": operation,
                    "target": target,
                    "content": content,
                    "fuzzy_match": fuzzy_match,
                }

            except AttributeError as e:
                raise ValueError(f"Invalid XML structure: {str(e)}")

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Error parsing modification block: {str(e)}")

    def clean_content(self, content: str) -> str:
        """Clean content by normalizing line endings and removing any leading/trailing whitespace.

        Args:
            content (str): The content to clean

        Returns:
            str: The cleaned content with normalized line endings
        """
        if not content:
            return content

        # Split into lines and clean each one
        lines = content.splitlines()

        # Clean up each line but preserve empty lines and indentation
        cleaned_lines = []
        for line in lines:
            # Only strip trailing whitespace, preserve leading whitespace for indentation
            line = line.rstrip()
            cleaned_lines.append(line)

        # Join lines back together with normalized line endings
        return "\n".join(cleaned_lines)

    async def modify_file_content(
        self,
        repo_url: str,
        file_path: str,
        modification_commands: str,
        branch: str = None,
    ) -> str:
        """
            Apply a series of modifications to a file while preserving formatting and context.

            Args:
                repo_url (str): The URL of the GitHub repository (e.g., "https://github.com/username/repo")
                file_path (str): Path to the file within the repository (e.g., "src/example.py")
                modification_commands (str): XML formatted string containing one or more modification commands.
                                             The expected XML format:

                                             <modification>
                                                 <operation>replace|insert|delete</operation>
                                                 <target>code_block_or_line_number</target>
                                                 <content>new_content (required for replace and insert)</content>
                                                 <fuzzy_match>true|false</fuzzy_match>
                                             </modification>

                                             Multiple <modification> blocks can be provided in a single string.

                branch (str, optional): The branch to modify. Defaults to the repository's default branch.

            Returns:
                str: A unified diff of the changes made, or an error message if something goes wrong.

            Operation Types:
                - replace: Replaces the target code block with new content.
                - insert: Inserts new content at the target location (line number or after a code block).
                - delete: Removes the target code block or line.

            Target Options:
                1. Code block: A string of code to match in the file.
                2. Line number: A specific line number where the operation should occur.

            Fuzzy Matching:
                - "true": Enables smart matching ignoring whitespace differences (default).
                - "false": Requires exact match including whitespace.

            Example:
                <modification>
                    <operation>replace</operation>
                    <target>def old_function():
        pass</target>
                    <content>def old_function():
        return "fixed"</content>
                    <fuzzy_match>true</fuzzy_match>
                </modification>

            The method handles indentation and attempts to maintain code style. It returns a diff
            so you can review the changes made.

            Notes:
            - If multiple modifications are requested, they are applied in sequence.
            - If any modification cannot find its target, an exception is raised.

            Returns:
                str: A unified diff showing the changes made or error message
        """
        try:
            error_recovery = GitHubErrorRecovery(
                api_client=self.ApiClient,
                agent_name=self.agent_name,
                conversation_name=self.conversation_name,
            )

            retry_count = 0
            max_retries = 3
            errors = []

            while retry_count < max_retries:
                try:
                    # Log attempt
                    logging.info(
                        f"Modification attempt #{retry_count + 1} for {file_path}"
                    )
                    if self.activity_id:
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] Modifying [{file_path}]({repo_url}/blob/{branch}/{file_path}) on branch [{branch}]({repo_url}/tree/{branch}).\n```xml\n{modification_commands}\n```",
                            conversation_name=self.conversation_name,
                        )

                    # Extract and parse each modification block
                    modifications = re.findall(
                        r"<modification>(.*?)</modification>",
                        modification_commands,
                        re.DOTALL,
                    )

                    if not modifications:
                        raise ValueError("No modification blocks found")

                    # Parse each modification into structured data
                    parsed_mods = []
                    for i, mod in enumerate(modifications, 1):
                        try:
                            mod_xml = f"<modification>{mod}</modification>"
                            parsed_mod = self._parse_modification_block(mod_xml)
                            parsed_mods.append(parsed_mod)
                            logging.debug(
                                f"Successfully parsed modification {i}: {parsed_mod['operation']} operation"
                            )
                        except ValueError as e:
                            logging.error(f"Failed to parse modification {i}: {str(e)}")
                            raise ValueError(
                                f"Error in modification block {i}: {str(e)}"
                            )

                    # Get repository and file content
                    repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
                    if not branch:
                        branch = repo.default_branch

                    file_content_obj = repo.get_contents(file_path, ref=branch)
                    file_content = file_content_obj.decoded_content.decode("utf-8")

                    # Process modifications
                    original_content = file_content
                    modified_content = file_content
                    has_changes = False

                    for mod in parsed_mods:
                        operation = mod["operation"]
                        target = mod["target"]
                        content = mod.get("content")
                        fuzzy_match = True

                        if (operation in ["replace", "insert"]) and not content:
                            raise ValueError(
                                f"Content is required for {operation} operation"
                            )

                        # Split content into lines while preserving empty lines
                        modified_lines = modified_content.splitlines(keepends=True)

                        # Find target location
                        start_line, end_line, indent_level = (
                            self._find_pattern_boundaries(
                                [line.rstrip("\n") for line in modified_lines],
                                target,
                                fuzzy_match=fuzzy_match,
                                operation=operation,
                            )
                        )

                        # Apply modification
                        if content:
                            content = self.clean_content(content)

                        new_lines = modified_lines[:]
                        if operation == "replace" and content:
                            # Ensure content ends with newline if the replaced content did
                            content_lines = content.splitlines(keepends=True)
                            if modified_lines[end_line - 1].endswith("\n"):
                                if not content_lines[-1].endswith("\n"):
                                    content_lines[-1] += "\n"
                            new_lines[start_line:end_line] = content_lines
                            has_changes = True

                        elif operation == "insert" and content:
                            insert_lines = content.splitlines(keepends=True)
                            if not insert_lines:
                                insert_lines = ["\n"]

                            # Add indentation to all non-empty lines
                            if indent_level > 0:
                                indent = " " * (4 * indent_level)
                                insert_lines = [
                                    f"{indent}{line}" if line.strip() else line
                                    for line in insert_lines
                                ]

                            # Ensure proper line endings
                            if not insert_lines[-1].endswith("\n"):
                                insert_lines[-1] += "\n"

                            # Handle spacing around insertion
                            if (
                                start_line > 0
                                and modified_lines[start_line - 1].strip()
                            ):
                                insert_lines.insert(0, "\n")
                            if (
                                start_line < len(modified_lines)
                                and modified_lines[start_line].strip()
                            ):
                                insert_lines.append("\n")

                            # Insert the new lines
                            new_lines[start_line:start_line] = insert_lines
                            has_changes = True

                        elif operation == "delete":
                            del new_lines[start_line:end_line]
                            has_changes = True

                        modified_content = "".join(new_lines)

                    if not has_changes:
                        return "No changes needed"

                    # Generate diff from the original content to modified content
                    diff = list(
                        difflib.unified_diff(
                            original_content.splitlines(),
                            modified_content.splitlines(),
                            fromfile=file_path,
                            tofile=file_path,
                            lineterm="",
                            n=3,
                        )
                    )

                    # Format Python files
                    if self._is_python_file(file_path):
                        modified_content = self._format_python_code(modified_content)

                    # Ensure final newline
                    if not modified_content.endswith("\n"):
                        modified_content += "\n"

                    commit_message = f"Modified {file_path}"
                    repo.update_file(
                        file_path,
                        commit_message,
                        modified_content,
                        file_content_obj.sha,
                        branch=branch,
                    )

                    return "\n".join(diff)

                except Exception as e:
                    error_msg = str(e)
                    errors.append(f"Attempt #{retry_count + 1}: {error_msg}")

                    if retry_count >= max_retries - 1:
                        error_history = "\n\nError history:\n" + "\n".join(errors)
                        raise ValueError(
                            f"Failed to apply modifications after {max_retries} attempts. {error_history}"
                        )

                    retry_count += 1
                    logging.warning(
                        f"Modification attempt #{retry_count} failed: {error_msg}"
                    )

                    try:
                        modification_commands = await error_recovery.retry_with_context(
                            error_msg=error_msg,
                            repo_url=repo_url,
                            file_path=file_path,
                            original_modifications=modification_commands,
                            activity_id=self.activity_id,
                            retry_count=retry_count - 1,
                        )
                    except ValueError as ve:
                        error_history = "\n\nError history:\n" + "\n".join(errors)
                        raise ValueError(
                            f"Error recovery failed: {str(ve)}{error_history}"
                        )

        except Exception as e:
            logging.error(f"Modification failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"

    # Helper command methods for individual operations
    async def replace_in_file(
        self,
        repo_url: str,
        file_path: str,
        target: str,
        content: str,
        fuzzy_match: str = "true",
        branch: str = None,
    ) -> str:
        """
        Replace a code block in a file while preserving formatting and indentation.

        Args:
            repo_url (str): The URL of the GitHub repository
            file_path (str): Path to the file within the repository
            target (str): Code block to replace or line number
            content (str): New code to insert in place of target
            fuzzy_match (str): "true" for smart matching ignoring whitespace, "false" for exact match
            branch (str, optional): Branch to modify. Defaults to repository's default branch

        The target can be either:
        1. A code block:
           target="def old_function():
                     pass"
        2. A line number:
           target="42"

        Examples:
            Replace a function:
            <execute>
            <name>Replace in File</name>
            <repo_url>https://github.com/username/repo</repo_url>
            <file_path>src/example.py</file_path>
            <target>def old_function():
                pass</target>
            <content>def new_function(param: str):
                return param.upper()</content>
            <fuzzy_match>true</fuzzy_match>
            </execute>

        Returns:
            str: A unified diff showing the changes made or error message
        """
        modification = f"""
        <modification>
        <operation>replace</operation>
        <target>{target}</target>
        <content>{content}</content>
        <fuzzy_match>{fuzzy_match}</fuzzy_match>
        </modification>
        """
        return await self.modify_file_content(repo_url, file_path, modification, branch)

    async def insert_in_file(
        self,
        repo_url: str,
        file_path: str,
        target: str,
        content: str,
        fuzzy_match: str = "true",
        branch: str = None,
    ) -> str:
        """
        Insert new code at a specific location in a file while preserving formatting.

        Args:
            repo_url (str): The URL of the GitHub repository
            file_path (str): Path to the file within the repository
            target (str): Location to insert code (line number or code block to insert after)
            content (str): New code to insert
            fuzzy_match (str): "true" for smart matching ignoring whitespace, "false" for exact match
            branch (str, optional): Branch to modify. Defaults to repository's default branch

        The target can be either:
        1. A line number where the code should be inserted:
           target="10"
        2. A code block to insert after:
           target="class ExampleClass:"

        Examples:
            Insert a new method:
            <execute>
            <name>Insert in File</name>
            <repo_url>https://github.com/username/repo</repo_url>
            <file_path>src/example.py</file_path>
            <target>class MyClass:</target>
            <content>    def new_method(self):
                return "Hello World"</content>
            <fuzzy_match>true</fuzzy_match>
            </execute>

        Returns:
            str: A unified diff showing the changes made or error message
        """
        modification = f"""
        <modification>
        <operation>insert</operation>
        <target>{target}</target>
        <content>{content}</content>
        <fuzzy_match>{fuzzy_match}</fuzzy_match>
        </modification>
        """
        return await self.modify_file_content(repo_url, file_path, modification, branch)

    async def delete_from_file(
        self,
        repo_url: str,
        file_path: str,
        target: str,
        fuzzy_match: str = "true",
        branch: str = None,
    ) -> str:
        """
        Delete a code block from a file.

        Args:
            repo_url (str): The URL of the GitHub repository
            file_path (str): Path to the file within the repository
            target (str): Code block to delete or line number range
            fuzzy_match (str): "true" for smart matching ignoring whitespace, "false" for exact match
            branch (str, optional): Branch to modify. Defaults to repository's default branch

        The target can be either:
        1. A code block to remove:
           target="    # Old comment
                      old_variable = None"
        2. A specific line:
           target="42"

        Examples:
            Delete an obsolete function:
            <execute>
            <name>Delete from File</name>
            <repo_url>https://github.com/username/repo</repo_url>
            <file_path>src/example.py</file_path>
            <target>def deprecated_function():
                # This function is no longer used
                pass</target>
            <fuzzy_match>true</fuzzy_match>
            </execute>

        Returns:
            str: A unified diff showing the changes made or error message
        """
        modification = f"""
        <modification>
        <operation>delete</operation>
        <target>{target}</target>
        <fuzzy_match>{fuzzy_match}</fuzzy_match>
        </modification>
        """
        return await self.modify_file_content(repo_url, file_path, modification, branch)

    async def review_pull_request(
        self,
        repo_url: str,
        pull_request_number: int,
        code_content: str = None,
        review_context: str = "",
    ) -> str:
        """
        Review a pull request and provide feedback based on code changes and project standards.

        Args:
            repo_url (str): The URL of the GitHub repository
            pull_request_number (int): The PR number to review
            code_content (str): Optional pre-fetched code content to avoid redundant fetches
            review_context (str): Additional context for the review (e.g., issue details)

        Returns:
            str: The review feedback and any suggested changes
        """
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.get_pull(pull_request_number)

            # Get the PR's changes if code_content wasn't provided
            if not code_content:
                code_content = await self.get_repo_code_contents(
                    f"{repo_url}/tree/{pull_request.head.ref}"
                )

            # Get the PR's files for focused review
            changed_files = pull_request.get_files()
            files_context = []
            for file in changed_files:
                files_context.append(f"Modified file: {file.filename}")
                files_context.append(f"Changes: +{file.additions} -{file.deletions}")
                if file.patch:
                    files_context.append(f"Patch:\n{file.patch}")

            # Construct review prompt
            review_prompt = f"""Review the following pull request changes and provide feedback:

PR #{pull_request_number}: {pull_request.title}
{pull_request.body}

Changed Files:
{chr(10).join(files_context)}

Additional Context:
{review_context}

Repository Code:
{code_content}

Please analyze the changes and provide:
1. Critical issues or bugs with the code changes
2. That the changes resolve the issue requiring no further modifications. If any changes are needed, provide specific details.
3. If no changes are needed, give feedback without suggesting modifications.
4. XML modification blocks for any necessary changes in the format:

<modification>
<file>path/to/file</file>
<operation>replace|insert|delete</operation>
<target>code_block_or_line</target>
<content>new_code</content>
</modification>

Focus on:
- Code correctness and functionality
- Adherence to project patterns and standards
- Security considerations
- Performance implications"""

            # Get review feedback
            review_feedback = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": review_prompt,
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )

            # Extract any modification blocks for automated fixes
            modifications = re.findall(
                r"<modification>.*?</modification>", review_feedback, re.DOTALL
            )

            # Add review comment to PR
            comment_body = review_feedback
            if modifications:
                comment_body += "\n\nI'll automatically apply these suggested changes."

            pull_request.create_issue_comment(comment_body)

            return review_feedback

        except Exception as e:
            return f"Error reviewing pull request: {str(e)}"

    async def fix_github_issue(
        self,
        repo_org: str,
        repo_name: str,
        issue_number: str,
        additional_context: str = "",
    ) -> str:
        """
        Fix a given GitHub issue by applying minimal code modifications to the repository.
        If a PR is already open for this issue's branch, it will not create a new one.
        Instead, it will apply changes to the existing branch and comment on the PR and issue.
        If no PR is open, it creates a new PR and comments on the issue.
        If there was an error previously or revisions need made on the same PR or issue, the assistant can use this same function to retry fixing the issue while providing additional context in additional_context.

        Args:
        repo_org (str): The organization or username for the GitHub repository
        repo_name (str): The repository name
        issue_number (str): The issue number to fix
        additional_context (str): Additional context to provide to the model, if a user mentions anything that could be useful to pass to the coding model, mention it here.

        Returns:
        str: A message indicating the result of the operation
        """
        repo_url = f"https://github.com/{repo_org}/{repo_name}"
        repo = self.gh.get_repo(f"{repo_org}/{repo_name}")
        base_branch = repo.default_branch
        issue_branch = f"issue-{issue_number}"
        # Ensure the issue branch exists
        try:
            repo.get_branch(issue_branch)
        except Exception:
            # Branch doesn't exist, so create it from base_branch
            source_branch = repo.get_branch(base_branch)
            repo.create_git_ref(f"refs/heads/{issue_branch}", source_branch.commit.sha)
        repo_content = await self.get_repo_code_contents(
            repo_url=f"{repo_url}/tree/{issue_branch}"
        )
        # Ensure issue_number is numeric
        issue_number = "".join(filter(str.isdigit, issue_number))
        issue = repo.get_issue(int(issue_number))
        issue_title = issue.title
        issue_body = issue.body
        # Prompt the model for modifications with file paths
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{self.activity_id}] Analyzing code to fix [#{issue_number}]({repo_url}/issues/{issue_number})",
            conversation_name=self.conversation_name,
        )

        modifications_xml = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"""### Issue #{issue_number}: {issue_title}
{issue_body}

## User
Below is the repository code and additional context. Identify the minimal code changes needed to fix this issue. 
You must ONLY return the necessary modifications in the following XML format:

<modification>
<file>path/to/file.py</file>
<operation>replace|insert|delete</operation>
<target>original_code_block_or_line_number</target>
<content>new_code_block_if_needed</content>
<fuzzy_match>true|false</fuzzy_match>
</modification>

If multiple modifications are needed, repeat the <modification> block.

### Important:
- Each <modification> block must include a <file> tag specifying which file to modify.
- For <target>, you must use one of these formats:
  1. For inserting after a function/method:
     - Use the complete function definition line, e.g., "def verify_email_address(self, code: str = None):"
     - The new content will be inserted after the entire function
  2. For replacing code:
     - Include the exact code block to replace, including correct indentation
     - The first and last lines are especially important for matching
  3. For specific line numbers:
     - Use the line number as a string, e.g., "42"
- Do not use the repository name or WORKSPACE path in file paths
- The file path should be relative to the repository root
- Content must match the indentation style of the target location
- For replace and insert operations, <content> is required
- For delete operations, <content> is not required
- Put your <modification> blocks inside of the <answer> block!
- Ensure indentation is correct in the <content> tag, it is critical for Python code and other languages with strict indentation rules.
- If working with NextJS, remember to include "use client" as the first line of all files declaring components that use client side hooks such as useEffect and useState.

Example modifications:
1. Insert after a function:
<modification>
<file>auth.py</file>
<operation>insert</operation>
<target>def verify_email_address(self, code: str = None):</target>
<content>
def verify_mfa(self, token: str):
    # Verify MFA token
    pass</content>
</modification>

2. Replace a code block:
<modification>
<file>auth.py</file>
<operation>replace</operation>
<target>    def verify_token(self):
    return True</target>
<content>    def verify_token(self):
    return self.validate_jwt()</content>
</modification>""",
                "context": f"### Content of {repo_url}\n\n{repo_content}\n{additional_context}",
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

        # Parse modifications by file
        modifications_blocks = re.findall(
            r"<modification>(.*?)</modification>", modifications_xml, re.DOTALL
        )

        if not modifications_blocks:
            # No modifications needed
            issue.create_comment(
                f"No changes needed for issue [#{issue_number}]({repo_url}/issues/{issue_number}) based on the model's analysis."
            )
            return f"No changes needed for issue [#{issue_number}]({repo_url}/issues/{issue_number})."

        file_mod_map = {}
        for block in modifications_blocks:
            file_match = re.search(r"<file>(.*?)</file>", block, re.DOTALL)
            if not file_match:
                raise Exception("No <file> tag found in a modification block.")
            file_path = file_match.group(1).strip()
            # if it start with the repo name, remove that.
            if file_path.startswith(repo_name):
                file_path = file_path[len(repo_name) + 1 :]

            # Wrap this single block with <modification> for use in modify_file_content
            single_mod_xml = f"<modification>{block}</modification>"

            if file_path not in file_mod_map:
                file_mod_map[file_path] = []
            file_mod_map[file_path].append(single_mod_xml)
        error_recovery = GitHubErrorRecovery(
            api_client=self.ApiClient,
            agent_name=self.agent_name,
            conversation_name=self.conversation_name,
        )
        # Apply modifications file by file
        for file_path, mods in file_mod_map.items():
            combined_mods = "".join(mods)
            try:
                result = await self.modify_file_content(
                    repo_url=repo_url,
                    file_path=file_path,
                    modification_commands=combined_mods,
                    branch=issue_branch,
                )
            except Exception as e:
                # If something went wrong, comment on the issue and exit
                result = f"Error: {str(e)}"

            if "Error:" in result:
                # Try again up to 3 times feeding result back to the model
                for i in range(3):
                    if result.startswith("Error:"):
                        try:
                            combined_mods = await error_recovery.retry_with_context(
                                error_msg=result,
                                repo_url=repo_url,
                                file_path=file_path,
                                original_modifications=combined_mods,
                                activity_id=self.activity_id,
                                retry_count=i,
                            )
                            result = await self.modify_file_content(
                                repo_url=repo_url,
                                file_path=file_path,
                                modification_commands=combined_mods,
                                branch=issue_branch,
                            )
                        except Exception as e:
                            result = f"Error: {str(e)}"
                        if "Error:" not in result:
                            break
            if "Error:" in result:
                # If something went wrong, comment on the issue and exit
                issue.create_comment(
                    f"Failed to apply changes to `{file_path}` for issue #{issue_number}. Error: {result}"
                )
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=(
                        f"[SUBACTIVITY][{self.activity_id}][ERROR] Failed to fix issue [#{issue_number}]({repo_url}/issues/{issue_number}). "
                        f"Error: {result}"
                    ),
                    conversation_name=self.conversation_name,
                )
                return f"Error applying modifications: {result}"

        # Check if a PR already exists for this branch
        open_pulls = repo.get_pulls(state="open", head=f"{repo_org}:{issue_branch}")
        if open_pulls.totalCount > 0:
            # A PR already exists for this branch
            existing_pr = open_pulls[0]

            # Comment on the PR and the issue about the new changes
            comment_body = (
                f"Additional changes have been pushed to the `{issue_branch}` branch:\n\n"
                f"{modifications_xml}"
            )
            existing_pr.create_issue_comment(comment_body)
            issue.create_comment(
                f"Additional changes have been applied to resolve issue [#{issue_number}]({repo_url}/issues/{issue_number}). See [PR #{existing_pr.number}]({repo_url}/pull/{existing_pr.number})."
            )

            # Review the updated PR
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Reviewing updated PR #{existing_pr.number}",
                conversation_name=self.conversation_name,
            )
            try:
                repo_content = await self.get_repo_code_contents(
                    repo_url=f"{repo_url}/tree/{issue_branch}"
                )
                review_feedback = await self.review_pull_request(
                    repo_url=repo_url,
                    pull_request_number=existing_pr.number,
                    code_content=repo_content,
                    review_context=f"Issue #{issue_number}: {issue_title}\n{issue_body}\n\nAdditional Context:\n{additional_context}",
                )
            except Exception as e:
                review_feedback = f"Ran into an error reviewing [PR #{existing_pr.number}]({repo_url}/pull/{existing_pr.number})\n{str(e)}"
            self.ApiClient.update_conversation_message(
                agent_name=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Reviewing updated PR #{existing_pr.number}",
                new_message=f"[SUBACTIVITY][{self.activity_id}] Reviewed updated PR #{existing_pr.number}\n{review_feedback}",
                conversation_name=self.conversation_name,
            )
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=(
                    f"[SUBACTIVITY][{self.activity_id}] Updated the branch [{issue_branch}]({repo_url}/tree/{issue_branch}) for [#{issue_number}]({repo_url}/issues/{issue_number}). "
                    f"Changes are reflected in [PR #{existing_pr.number}]({repo_url}/pull/{existing_pr.number})."
                ),
                conversation_name=self.conversation_name,
            )

            # If review suggests changes, apply them recursively
            if "<modification>" in review_feedback:
                return await self.fix_github_issue(
                    repo_org=repo_org,
                    repo_name=repo_name,
                    issue_number=issue_number,
                    additional_context=f"Review Feedback:\n{review_feedback}",
                )

            return f"Updated and reviewed [PR #{existing_pr.number}]({repo_url}/pull/{existing_pr.number}) for issue [#{issue_number}]({repo_url}/issues/{issue_number}) with new changes."
        else:
            # No PR exists, create a new one
            pr_body = f"Resolves #{issue_number}\n\nThe following modifications were applied:\n\n{modifications_xml}"
            pr_body = pr_body.replace(
                "<modification>", "```xml\n<modification>"
            ).replace("</modification>", "</modification>\n```")
            new_pr = repo.create_pull(
                title=f"Fix #{issue_number}: {issue_title}",
                body=pr_body,
                head=issue_branch,
                base=base_branch,
            )

            # Comment on the issue about the new PR
            issue.create_comment(
                f"Created PR #{new_pr.number} to resolve issue #{issue_number}:\n{repo_url}/pull/{new_pr.number}"
            )

            # Review the new PR
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Reviewing new PR #{new_pr.number}",
                conversation_name=self.conversation_name,
            )
            try:
                repo_content = await self.get_repo_code_contents(
                    repo_url=f"{repo_url}/tree/{issue_branch}"
                )
                review_feedback = await self.review_pull_request(
                    repo_url=repo_url,
                    pull_request_number=new_pr.number,
                    code_content=repo_content,
                    review_context=f"Issue #{issue_number}: {issue_title}\n{issue_body}\n\nAdditional Context:\n{additional_context}",
                )
            except Exception as e:
                review_feedback = f"Ran into an error reviewing [PR #{new_pr.number}]({repo_url}/pull/{new_pr.number})\n{str(e)}"
            self.ApiClient.update_conversation_message(
                agent_name=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Reviewing new PR #{new_pr.number}",
                new_message=f"[SUBACTIVITY][{self.activity_id}] Reviewed new PR #{new_pr.number}\n{review_feedback}",
                conversation_name=self.conversation_name,
            )
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Fixed issue [#{issue_number}]({repo_url}/issues/{issue_number}) in [{repo_org}/{repo_name}]({repo_url}) with pull request [#{new_pr.number}]({repo_url}/pull/{new_pr.number}).",
                conversation_name=self.conversation_name,
            )

            # If review suggests changes, apply them recursively
            if "<modification>" in review_feedback:
                return await self.fix_github_issue(
                    repo_org=repo_org,
                    repo_name=repo_name,
                    issue_number=issue_number,
                    additional_context=f"Review Feedback:\n{review_feedback}",
                )
            response = f"""### Issue #{issue_number}
Title: {issue_title}
Body: 
{issue_body}

### Pull Request #{new_pr.number}
Title: {new_pr.title}
Body: 
{pr_body}

Review Feedback:
{review_feedback}

I have created and reviewed pull request [#{new_pr.number}]({repo_url}/pull/{new_pr.number}) to fix issue [#{issue_number}]({repo_url}/issues/{issue_number})."""
            # Check if <modification> tag is present in response
            if "<modification>" in response:
                # Check if the characters before it are "```xml\n", if it isn't, add it.
                if response.find("```xml\n<modification>") == -1:
                    response = response.replace(
                        "<modification>", "```xml\n<modification>"
                    ).replace("</modification>", "</modification>\n```")

            return response
