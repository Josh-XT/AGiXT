## AGiXT Extensions

Extensions are the way to extend the functionality of AGiXT with other software APIs or Python modules. Extensions are Python files that are placed in the `extensions` folder. AGiXT will automatically load all extensions and commands associated when it starts.

### Creating an Extension

To create an extension, create a new Python file in the `extensions` folder. The file name will be the name of the extension. We will use the `GitHub` extension as an example.

The `GitHub` extension will have two commands:
- `Clone GitHub Repository`
- `Create GitHub Repository`

The `GibHub` extension will require two keys:
- `GITHUB_USERNAME` - The username of the GitHub account to use
- `GITHUB_API_KEY` - The API key of the GitHub account to use

All extensions will inherit from the `Extensions` class. This class will provide the following:
- `self.commands` - A dictionary of commands that the extension provides. The key is the name of the command and the value is the function that will be called when the command is run.
- `WORKING_DIRECTORY` - The directory that AGiXT Agent is allowed to work in.
- Any API Keys for your extension. In this case, `GITHUB_USERNAME` and `GITHUB_API_KEY`. Add these to `__init__` as shown below.
- Any imports that are required for your extension. In this case, `os`, `git`, and `Github`. Add try/excepts to install the modules if they are not already installed.

```python
import os

try:
    import git
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "GitPython==3.1.31"])
    import git

try:
    from github import Github
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyGithub==1.58.2"])
    from github import Github
from Extensions import Extensions


class github(Extensions):
    def __init__(
        self,
        GITHUB_USERNAME: str = "",
        GITHUB_API_KEY: str = "",
        WORKING_DIRECTORY: str = "./WORKSPACE",
        **kwargs,
    ):
        self.GITHUB_USERNAME = GITHUB_USERNAME
        self.GITHUB_API_KEY = GITHUB_API_KEY
        self.WORKING_DIRECTORY = WORKING_DIRECTORY
        self.commands = {"Clone Github Repository": self.clone_repo}
        if self.GITHUB_USERNAME and self.GITHUB_API_KEY:
            self.commands["Create Github Repository"] = self.create_repo

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
            repo_dir = os.path.join(self.WORKING_DIRECTORY, repo_name)
            if os.path.exists(repo_dir):
                return f"""{repo_dir} already exists"""
            git.Repo.clone_from(
                url=auth_repo_url,
                to_path=repo_dir,
            )
            return f"Cloned {repo_url} to {repo_dir}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def create_repo(self, repo_name: str, content_of_readme: str) -> str:
        g = Github(self.GITHUB_API_KEY)
        user = g.get_user(self.GITHUB_USERNAME)
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
        return repo_url
```