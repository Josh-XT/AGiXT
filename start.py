import os
import sys
import subprocess
import random
import argparse

try:
    from tzlocal import get_localzone
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "tzlocal"], check=True)
    from tzlocal import get_localzone
try:
    from dotenv import load_dotenv
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "python-dotenv"], check=True
    )
    from dotenv import load_dotenv


def prompt_user(prompt, default=None):
    if default:
        user_input = input(f"{prompt} (default: {default}): ").strip()
    else:
        user_input = input(f"{prompt}: ").strip()
    return user_input if user_input else default


def is_docker_installed():
    try:
        subprocess.run(["docker", "--version"], check=True, stdout=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def run_shell_command(command):
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return result.stdout


def get_default_env_vars():
    workspace_folder = os.path.normpath(os.path.join(os.getcwd(), "WORKSPACE"))
    machine_tz = get_localzone()
    return {
        "AGIXT_API_KEY": "",
        "AGIXT_URI": "http://localhost:7437",
        "AGIXT_AGENT": "AGiXT",
        "AGIXT_BRANCH": "stable",
        "AGIXT_FILE_UPLOAD_ENABLED": "true",
        "AGIXT_VOICE_INPUT_ENABLED": "true",
        "AGIXT_FOOTER_MESSAGE": "Powered by AGiXT",
        "AGIXT_REQUIRE_API_KEY": "false",
        "AGIXT_RLHF": "true",
        "AGIXT_SHOW_SELECTION": "conversation,agent",
        "AGIXT_SHOW_AGENT_BAR": "true",
        "AGIXT_SHOW_APP_BAR": "true",
        "AGIXT_CONVERSATION_MODE": "select",
        "ALLOWED_DOMAINS": "*",
        "APP_DESCRIPTION": "A chat powered by AGiXT.",
        "APP_NAME": "AGiXT Chat",
        "APP_URI": "http://localhost:3437",
        "STREAMLIT_APP_URI": "http://localhost:8501",
        "AUTH_WEB": "http://localhost:3437/user",
        "AUTH_PROVIDER": "magicalauth",
        "DISABLED_PROVIDERS": "",
        "DISABLED_EXTENSIONS": "",
        "WORKING_DIRECTORY": workspace_folder.replace("\\", "/"),
        "GITHUB_CLIENT_ID": "",
        "GITHUB_CLIENT_SECRET": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "MICROSOFT_CLIENT_ID": "",
        "MICROSOFT_CLIENT_SECRET": "",
        "TZ": machine_tz,
        "INTERACTIVE_MODE": "chat",
        "THEME_NAME": "doom",
        "ALLOW_EMAIL_SIGN_IN": "true",
        "DATABASE_TYPE": "sqlite",
        "DATABASE_NAME": "models/agixt",
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(asctime)s | %(levelname)s | %(message)s",
        "UVICORN_WORKERS": "10",
        "AGIXT_AUTO_UPDATE": "true",
    }


def set_environment(env_updates=None):
    load_dotenv()
    env_vars = get_default_env_vars()
    # Update with existing environment variables
    for key in env_vars.keys():
        env_value = os.getenv(key)
        if env_value is not None:
            env_vars[key] = env_value
    # Apply updates
    if env_updates:
        for key, value in env_updates.items():
            if key in env_vars:
                env_vars[key] = value
    # Ensure AGIXT_API_KEY is set
    if env_vars["AGIXT_API_KEY"] == "":
        env_vars["AGIXT_API_KEY"] = "".join(
            random.choice(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            )
            for i in range(64)
        )
    # Write to .env file
    env_file_content = "\n".join(
        [f'{key}="{value}"' for key, value in env_vars.items()]
    )
    with open(".env", "w") as file:
        file.write(env_file_content)
    dockerfile = "docker-compose.yml"
    if env_vars["AGIXT_BRANCH"] != "stable":
        dockerfile = "docker-compose-dev.yml"
    if str(env_vars["AGIXT_AUTO_UPDATE"]).lower() == "true":
        command = f"docker-compose -f {dockerfile} down && docker-compose -f {dockerfile} pull && docker-compose -f {dockerfile} up"
    else:
        command = (
            f"docker-compose -f {dockerfile} down && docker-compose -f {dockerfile} up"
        )
    run_shell_command(command)
    return env_vars


if __name__ == "__main__":
    if not is_docker_installed():
        print("Docker is not installed. Please install Docker and try again.")
        exit(1)
    parser = argparse.ArgumentParser(description="AGiXT Environment Setup")
    # Add arguments for each environment variable
    for key, value in get_default_env_vars().items():
        parser.add_argument(
            f"--{key.lower().replace('_', '-')}",
            help=f"Set {key}",
            type=str,
            default=None,
            required=False,
        )
    args = parser.parse_args()
    # Convert args to a dictionary, filtering out None values
    arg_dict = {k: v for k, v in vars(args).items() if v is not None}
    # Convert hyphenated arg names back to underscore format
    env_updates = {k.upper().replace("-", "_"): v for k, v in arg_dict.items()}
    # Check if .env file exists and if AGIXT_AUTO_UPDATE is not set via command line
    if not os.path.exists(".env") and "AGIXT_AUTO_UPDATE" not in env_updates:
        auto_update = prompt_user(
            "Would you like AGiXT to auto update? (Y for yes, N for no)", "y"
        )
        if auto_update.lower() == "y" or auto_update.lower() == "yes":
            auto_update = "true"
        else:
            auto_update = "false"
        env_updates["AGIXT_AUTO_UPDATE"] = auto_update
    # Apply updates and restart server
    set_environment(env_updates=env_updates)
