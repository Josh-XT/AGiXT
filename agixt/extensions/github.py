import git
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

    def clone_repo(self, repo_url: str, clone_path: str) -> str:
        split_url = repo_url.split("//")
        if self.GITHUB_USERNAME is not None and self.GITHUB_API_KEY is not None:
            auth_repo_url = f"//{self.GITHUB_USERNAME}:{self.GITHUB_API_KEY}@".join(
                split_url
            )
        else:
            auth_repo_url = "//".join(split_url)
        try:
            git.Repo.clone_from(auth_repo_url, self.WORKING_DIRECTORY + clone_path)
            return f"""Cloned {repo_url} to {self.WORKING_DIRECTORY + clone_path}"""
        except Exception as e:
            return f"Error: {str(e)}"

    def create_repo(self, repo_name: str, readme: str) -> str:
        g = Github(self.GITHUB_API_KEY)
        user = g.get_user(self.GITHUB_USERNAME)
        repo = user.create_repo(repo_name, private=True)
        repo_url = repo.clone_url
        repo_dir = f"./{repo_name}"
        repo = git.Repo.init(repo_dir)
        with open(f"{repo_dir}/README.md", "w") as f:
            f.write(readme)
        repo.git.add(A=True)
        repo.git.commit(m="Added README")
        repo.create_remote("origin", repo_url)
        repo.git.push("origin", "HEAD:main")
        return repo_url
