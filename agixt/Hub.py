import io
import os
import time
import shutil
import requests
import zipfile
import hashlib
from dotenv import load_dotenv

load_dotenv()

db_connected = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False

if db_connected:
    from db.imports import (
        import_extensions,
        import_prompts,
        import_providers,
        import_agents,
        import_chains,
        import_conversations,
    )
else:
    import_extensions = lambda: None
    import_prompts = lambda: None
    import_providers = lambda: None
    import_agents = lambda: None
    import_chains = lambda: None
    import_conversations = lambda: None


def import_agixt_hub():
    github_user = os.getenv("GITHUB_USER")
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("AGIXT_HUB", "AGiXT/light-hub")
    repo_name = github_repo.split("/")[1]
    repo_url = f"https://github.com/{github_repo}/archive/refs/heads/main.zip"
    zip_file_name = f"{repo_name}_main.zip"

    try:
        response = requests.get(repo_url, auth=(github_user, github_token))
        response.raise_for_status()

        # Check if previous zip exists and compare it with the new one
        new_zip_hash = hashlib.sha256(response.content).hexdigest()
        if os.path.exists(zip_file_name):
            with open(zip_file_name, "rb") as f:
                old_zip_hash = hashlib.sha256(f.read()).hexdigest()
            if old_zip_hash == new_zip_hash:
                print(
                    f"No changes detected in the AGiXT Hub at {github_repo}, moving on..."
                )
                return

        # Save the new zip file
        with open(zip_file_name, "wb") as f:
            f.write(response.content)

        zip_ref = zipfile.ZipFile(io.BytesIO(response.content))
        zip_ref.extractall(".")
        zip_ref.close()
        print(f"Updating AGiXT Hub from {github_repo}")
        # Move the files and directories from the reponame-main directory to the current directory
        for file in os.listdir(f"{repo_name}-main"):
            src_file = os.path.join(f"{repo_name}-main", file)
            dest_file = os.path.join(".", file)

            if os.path.isdir(src_file):
                if os.path.isdir(dest_file):
                    shutil.rmtree(dest_file)
                shutil.move(src_file, dest_file)
            else:
                shutil.move(src_file, dest_file)

        # Remove the reponame-main directory
        shutil.rmtree(f"{repo_name}-main")
        print(f"Updated AGiXT Hub from {github_repo}")
    except Exception as e:
        print(f"AGiXT Hub Import Error: {e}")
    if db_connected:
        print(f"DB Connected: {db_connected}")
        time.sleep(5)
        import_extensions()
        import_prompts()
        import_providers()
        import_agents()
        import_chains()
        import_conversations()


if __name__ == "__main__":
    import_agixt_hub()
