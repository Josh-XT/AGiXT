import os
import time
import datetime

try:
    import git
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "GitPython==3.1.42"])
    import git

try:
    from github import Github, RateLimitExceededException
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyGithub==2.2.0"])
    from github import Github, RateLimitExceededException

from Extensions import Extensions


class github(Extensions):
    def __init__(
        self,
        GITHUB_USERNAME: str = "",
        GITHUB_API_KEY: str = "",
        **kwargs,
    ):
        self.GITHUB_USERNAME = GITHUB_USERNAME
        self.GITHUB_API_KEY = GITHUB_API_KEY
        if self.GITHUB_USERNAME and self.GITHUB_API_KEY:
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
            }
            try:
                self.gh = Github(self.GITHUB_API_KEY)
            except Exception as e:
                self.gh = None
                self.commands = {}
                print(f"GitHub Error: {str(e)}")
        else:
            self.commands = {}
            self.gh = None
        self.failures = 0

    async def clone_repo(self, repo_url: str) -> str:
        split_url = repo_url.split("//")
        if self.GITHUB_USERNAME is not None and self.GITHUB_API_KEY is not None:
            auth_repo_url = f"//{self.GITHUB_USERNAME}:{self.GITHUB_API_KEY}@".join(
                split_url
            )
        else:
            auth_repo_url = "//".join(split_url)
        try:
            repo_name = repo_url.split("/")[-1]
            repo_dir = os.path.join("./WORKSPACE", repo_name)
            if os.path.exists(repo_dir):
                # Pull the latest changes
                repo = git.Repo(repo_dir)
                repo.remotes.origin.pull()
                self.failures = 0
                return f"Pulled latest changes for {repo_url} to {repo_dir}"
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

    async def create_repo(self, repo_name: str, content_of_readme: str) -> str:
        try:
            user = self.gh.get_user(self.GITHUB_USERNAME)
            repo = user.create_repo(repo_name, private=True)
            repo_url = repo.clone_url
            repo_dir = f"./{repo_name}"
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
        repo_name = repo_url.split("/")[-1]
        await self.clone_repo(repo_url)
        python_files = []
        powershell_files = []
        js_files = []
        ts_files = []
        other_files = []
        for root, dirs, files in os.walk(
            os.path.join(os.getcwd(), "WORKSPACE", repo_name)
        ):
            for file in files:
                if file.endswith(".py"):
                    python_files.append(os.path.join(root, file))
                if file.endswith(".ps1"):
                    powershell_files.append(os.path.join(root, file))
                if (
                    file == "Dockerfile"
                    or file.endswith(".yml")
                    or file == "requirements.txt"
                    or file == "static-requirements.txt"
                ):
                    other_files.append(os.path.join(root, file))
                if file.endswith(".js") or file.endswith(".jsx"):
                    js_files.append(os.path.join(root, file))
                if file.endswith(".ts") or file.endswith(".tsx"):
                    ts_files.append(os.path.join(root, file))
        if os.path.exists(os.path.join(os.getcwd(), "WORKSPACE", f"{repo_name}.md")):
            os.remove(os.path.join(os.getcwd(), "WORKSPACE", f"{repo_name}.md"))
        with open(
            os.path.join(os.getcwd(), "WORKSPACE", f"{repo_name}.md"), "w"
        ) as markdown_file:
            for file_path in other_files:
                markdown_file.write(f"**{file_path}**\n")
                with open(file_path, "r") as other_file:
                    content = other_file.read()
                    markdown_file.write(f"```yaml\n{content}\n```\n\n")
            for file_path in powershell_files:
                markdown_file.write(f"**{file_path}**\n")
                with open(file_path, "r") as powershell_file:
                    content = powershell_file.read()
                    markdown_file.write(f"```powershell\n{content}\n```\n\n")
            for file_path in python_files:
                markdown_file.write(f"**{file_path}**\n")
                with open(file_path, "r") as python_file:
                    content = python_file.read()
                    markdown_file.write(f"```python\n{content}\n```\n\n")
            for file_path in js_files:
                markdown_file.write(f"**{file_path}**\n")
                with open(file_path, "r") as js_file:
                    content = js_file.read()
                    markdown_file.write(f"```javascript\n{content}\n```\n\n")
            for file_path in ts_files:
                markdown_file.write(f"**{file_path}**\n")
                with open(file_path, "r") as ts_file:
                    content = ts_file.read()
                    markdown_file.write(f"```typescript\n{content}\n```\n\n")
        with open(
            os.path.join(os.getcwd(), "WORKSPACE", f"{repo_name}.md"), "r"
        ) as markdown_file:
            content = markdown_file.read()
        return content

    async def get_repo_issues(self, repo_url: str) -> str:
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

    async def create_repo_issue(self, repo_url: str, title: str, body: str) -> str:
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.create_issue(title=title, body=body)
            self.failures = 0
            return f"Created new issue in GitHub Repository at {repo_url}\n\n{issue.number}: {issue.title}\n\n{issue.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.create_repo_issue(repo_url, title, body)
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def update_repo_issue(
        self, repo_url: str, issue_number: int, title: str, body: str
    ) -> str:
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)
            issue.edit(title=title, body=body)
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
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            pull_request = repo.create_pull(
                title=title, body=body, head=head, base=base
            )
            self.failures = 0
            return f"Created new pull request in GitHub Repository at {repo_url}\n\n#{pull_request.number}: {pull_request.title}\n\n{pull_request.body}"
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
        self, repo_url: str, issue_number: int, comment_body: str
    ) -> str:
        try:
            repo = self.gh.get_repo(repo_url.split("github.com/")[-1])
            issue = repo.get_issue(issue_number)
            comment = issue.create_comment(comment_body)
            self.failures = 0
            return f"Added comment to issue #{issue.number} in GitHub Repository at {repo_url}\n\n{comment.body}"
        except RateLimitExceededException:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.add_comment_to_repo_issue(
                    repo_url, issue_number, comment_body
                )
            return "Error: GitHub API rate limit exceeded. Please try again later."
        except Exception as e:
            return f"Error: {str(e)}"

    async def add_comment_to_repo_pull_request(
        self, repo_url: str, pull_request_number: int, comment_body: str
    ) -> str:
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
