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
        **kwargs,
    ):
        self.GITHUB_USERNAME = GITHUB_USERNAME
        self.GITHUB_API_KEY = GITHUB_API_KEY
        self.commands = {
            "Clone Github Repository": self.clone_repo,
            "Get Github Repository Code Contents": self.get_repo_code_contents,
        }
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
            repo_dir = os.path.join("./WORKSPACE", repo_name)
            if os.path.exists(repo_dir):
                # Pull the latest changes
                repo = git.Repo(repo_dir)
                repo.remotes.origin.pull()
                return f"Pulled latest changes for {repo_url} to {repo_dir}"
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
