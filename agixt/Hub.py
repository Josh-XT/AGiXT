import io
import os
import time
import stat
import shutil
import requests
import zipfile
import hashlib
import tarfile
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
    github_repo = os.getenv("AGIXT_HUB", "AGiXT/hub")
    if github_repo == "AGiXT/light-hub":
        github_repo = "AGiXT/hub"
    repo_name = github_repo.split("/")[1]
    repo_url = f"https://github.com/{github_repo}/archive/refs/heads/main.zip"
    zip_file_name = f"{repo_name}_main.zip"
    # If there are folders under the conversations folder, move all .yaml files in them to the conversations folder and delete the folders
    try:
        conversations_folder = os.path.join(".", "conversations")
        if os.path.exists(conversations_folder):
            for item in os.listdir(conversations_folder):
                item_path = os.path.join(conversations_folder, item)
                if os.path.isdir(item_path):
                    for dirpath, dirnames, filenames in os.walk(item_path):
                        for filename in filenames:
                            if filename.endswith(".yaml"):
                                shutil.move(
                                    os.path.join(dirpath, filename),
                                    os.path.join(conversations_folder, filename),
                                )
                    shutil.rmtree(item_path)
    except Exception as e:
        print(f"Error moving conversations: {e}")
    onnx_folder = os.path.join(os.getcwd(), "onnx")
    if not os.path.exists(os.path.join(onnx_folder, "model.onnx")):
        with tarfile.open(
            name=os.path.join(os.getcwd(), "onnx.tar.gz"),
            mode="r:gz",
        ) as tar:
            tar.extractall(path=os.getcwd())
    try:
        response = requests.get(repo_url, auth=(github_user, github_token))
        response.raise_for_status()

        new_zip_hash = hashlib.sha256(response.content).hexdigest()
        if os.path.exists(zip_file_name):
            with open(zip_file_name, "rb") as f:
                old_zip_hash = hashlib.sha256(f.read()).hexdigest()
            if old_zip_hash == new_zip_hash:
                print(
                    f"No changes detected in the AGiXT Hub at {github_repo}, moving on..."
                )
                return

        with open(zip_file_name, "wb") as f:
            f.write(response.content)

        zip_ref = zipfile.ZipFile(io.BytesIO(response.content))
        zip_ref.extractall(".")
        zip_ref.close()

        for root, dirs, files in os.walk(f"{repo_name}-main"):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                os.chmod(dir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            for file_name in files:
                file_path = os.path.join(root, file_name)
                os.chmod(
                    file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
                )

        print(f"Updating AGiXT Hub from {github_repo}")

        for file in os.listdir(f"{repo_name}-main"):
            src_file = os.path.join(f"{repo_name}-main", file)
            dest_file = os.path.join(".", file)

            if os.path.isdir(src_file):
                if not os.path.exists(dest_file):
                    os.makedirs(dest_file, exist_ok=True)
                for item in os.listdir(src_file):
                    src_item = os.path.join(src_file, item)
                    dest_item = os.path.join(dest_file, item)
                    if os.path.isdir(src_item):
                        if not os.path.exists(dest_item):
                            os.makedirs(dest_item, exist_ok=True)
                        for dirpath, dirnames, filenames in os.walk(src_item):
                            destination = dirpath.replace(src_item, dest_item, 1)
                            if not os.path.exists(destination):
                                os.makedirs(destination)
                            for filename in filenames:
                                if filename != "config.json" or not os.path.exists(
                                    os.path.join(destination, filename)
                                ):
                                    shutil.copy2(
                                        os.path.join(dirpath, filename), destination
                                    )
                    else:
                        if not (
                            dest_item.endswith("config.json")
                            and os.path.exists(dest_item)
                        ):
                            shutil.copy2(src_item, dest_item)
            else:
                if not (
                    dest_file.endswith("config.json") and os.path.exists(dest_file)
                ):
                    shutil.move(src_file, dest_file)

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
