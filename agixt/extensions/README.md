# AGiXT Extensions

Extensions are the way to extend the functionality of AGiXT with other software APIs or Python modules. Extensions are Python files that are placed in the `extensions` folder. AGiXT will automatically load all extensions and commands associated when it starts.

## Creating an Extension

To create an extension, create a new Python file in the `extensions` folder. The file name will be the name of the extension. We will make a smaller version of our `GitHub` extension as an example.

The example `GitHub` extension will have two commands:

- `Clone GitHub Repository`
- `Create GitHub Repository`

The `GibHub` extension will require two keys:

- `GITHUB_USERNAME` - The username of the GitHub account to use
- `GITHUB_API_KEY` - The API key of the GitHub account to use

All extensions will inherit from the `Extensions` class. This class will provide the following:

- `self.commands` - A dictionary of commands that the extension provides. The key is the name of the command and the value is the function that will be called when the command is run.
- Any API Keys for your extension. In this case, `GITHUB_USERNAME` and `GITHUB_API_KEY`. Add these to `__init__` as shown below.
- Any imports that are required for your extension that are not built into Python. In this case, `GitPython`, and `PyGithub`. Add try/excepts to install the modules if they are not already installed.

```python
import os
import time
import datetime
from Extensions import Extensions

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
                "Create Github Repository": self.create_repo,
            }
            try:
                self.gh = Github(self.GITHUB_API_KEY)
            except Exception as e:
                self.gh = None
        else:
            self.gh = None
        self.failures = 0

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
        """
        Create a new private GitHub repository

        Args:
        repo_name (str): The name of the repository to create
        content_of_readme (str): The content of the README.md file

        Returns:
        str: The URL of the newly created repository
        """
        try:
            try:
                user = self.gh.get_organization(self.GITHUB_USERNAME)
            except:
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
```
