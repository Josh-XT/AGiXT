from Memories import Memories
import requests
import os


class GithubReader(Memories):
    def __init__(self, agent_name):
        super().__init__(agent_name=agent_name)

    async def read_github_repo(
        self,
        github_repo="Josh-XT/AGiXT",
        github_user=None,
        github_token=None,
        github_branch="main",
    ):
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
        repo_url = (
            f"https://github.com/{user}/{repo}/archive/refs/heads/{github_branch}.zip"
        )
        try:
            response = requests.get(repo_url, auth=(github_user, github_token))
        except:
            if github_branch != "master":
                return await self.read_github_repo(
                    github_repo=github_repo,
                    github_user=github_user,
                    github_token=github_token,
                    github_branch="master",
                )
            else:
                return False
        zip_file_name = f"{repo}_{github_branch}.zip"
        with open(zip_file_name, "wb") as f:
            f.write(response.content)
        await self.read_file(file_path=zip_file_name)
        os.remove(zip_file_name)
        return True
