import io
import os
import time
import stat
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
        # Set permissions for the extracted files and directories
        for root, dirs, files in os.walk(f"{repo_name}-main"):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                os.chmod(
                    dir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO
                )  # Set permissions to read, write, and execute for all
            for file_name in files:
                file_path = os.path.join(root, file_name)
                os.chmod(
                    file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
                )  # Set permissions to read for owner and group, read-only for others

        print(f"Updating AGiXT Hub from {github_repo}")
        # Move the files and directories from the reponame-main directory to the current directory
        for file in os.listdir(f"{repo_name}-main"):
            src_file = os.path.join(f"{repo_name}-main", file)
            dest_file = os.path.join(".", file)

            if os.path.isdir(src_file):
                if os.path.exists(dest_file):
                    for item in os.listdir(dest_file):
                        dest_item = os.path.join(dest_file, item)
                        if os.path.isfile(dest_item) and "config.json" not in dest_item:
                            os.remove(dest_item)
                else:
                    os.makedirs(dest_file, exist_ok=True)

                for item in os.listdir(src_file):
                    src_item = os.path.join(src_file, item)
                    dest_item = os.path.join(dest_file, item)
                    if os.path.isdir(src_item):
                        if os.path.exists(dest_item):
                            shutil.rmtree(dest_item)
                        shutil.copytree(src_item, dest_item)
                    else:
                        if not (
                            "config.json" not in dest_item and os.path.exists(dest_item)
                        ):  # Don't overwrite existing config.json
                            shutil.copy2(src_item, dest_item)
            else:
                if "config.json" not in dest_file and not os.path.exists(
                    dest_file
                ):  # Don't overwrite existing config.json
                    if os.path.exists(dest_file):
                        os.remove(dest_file)
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
