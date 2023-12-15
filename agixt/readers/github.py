from Memories import Memories
import requests
import os
from readers.file import FileReader


class GithubReader(Memories):
    def __init__(
        self,
        agent_name: str = "AGiXT",
        agent_config=None,
        collection_number: int = 0,
        use_agent_settings: bool = False,
        ApiClient=None,
        user=None,
        **kwargs,
    ):
        super().__init__(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
            ApiClient=ApiClient,
            user=user,
        )
        self.file_reader = FileReader(
            agent_name=self.agent_name, agent_config=self.agent_config, user=user
        )
        self.use_agent_settings = use_agent_settings
        if (
            use_agent_settings == True
            and "GITHUB_USERNAME" in self.agent_settings
            and "GITHUB_API_KEY" in self.agent_settings
        ):
            self.github_user = self.agent_settings["GITHUB_USERNAME"]
            self.github_token = self.agent_settings["GITHUB_API_KEY"]
        else:
            self.github_user = None
            self.github_token = None

    async def write_github_repository_to_memory(
        self,
        github_repo="Josh-XT/AGiXT",
        github_user=None,
        github_token=None,
        github_branch="main",
    ):
        if self.use_agent_settings == True:
            github_user = self.github_user if self.github_user else github_user
            github_token = self.github_token if self.github_token else github_token
        github_repo = github_repo.replace("https://github.com/", "")
        github_repo = github_repo.replace("https://www.github.com/", "")
        if not github_branch:
            github_branch = "main"
        user = github_repo.split("/")[0]
        repo = github_repo.split("/")[1]
        if " " in repo:
            repo = repo.split(" ")[0]
        if "\n" in repo:
            repo = repo.split("\n")[0]
        # Remove any symbols that would not be in the user, repo, or branch
        for symbol in [" ", "\n", "\t", "\r", "\\", "/", ":", "*", "?", '"', "<", ">"]:
            repo = repo.replace(symbol, "")
            user = user.replace(symbol, "")
            github_branch = github_branch.replace(symbol, "")

        repo_url = (
            f"https://github.com/{user}/{repo}/archive/refs/heads/{github_branch}.zip"
        )
        try:
            # Download zip to zip_file_name
            response = requests.get(repo_url, auth=(github_user, github_token))
        except:
            if github_branch != "master":
                return await self.write_github_repository_to_memory(
                    github_repo=github_repo,
                    github_user=github_user,
                    github_token=github_token,
                    github_branch="master",
                )
            else:
                return False
        zip_file_name = os.path.join(
            os.getcwd(), "WORKSPACE", f"{repo}_{github_branch}.zip"
        )
        with open(zip_file_name, "wb") as f:
            f.write(response.content)
        await self.file_reader.write_file_to_memory(file_path=zip_file_name)
        os.remove(zip_file_name)
        return True
