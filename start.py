import os
import sys
import subprocess
import random
import argparse
import platform

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


def is_tool_installed(tool):
    try:
        subprocess.run(
            [tool, "--version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_docker():
    system = platform.system().lower()
    if system == "linux":
        if is_tool_installed("apt-get"):
            commands = [
                "sudo apt-get update",
                "sudo apt-get install -y docker.io",
                "sudo systemctl start docker",
                "sudo systemctl enable docker",
                "sudo usermod -aG docker $USER",
            ]
        elif is_tool_installed("yum"):
            commands = [
                "sudo yum install -y docker",
                "sudo systemctl start docker",
                "sudo systemctl enable docker",
                "sudo usermod -aG docker $USER",
            ]
        else:
            print("Unsupported Linux distribution. Please install Docker manually.")
            return False
    elif system == "darwin":
        print(
            "Please install Docker Desktop for Mac from https://www.docker.com/products/docker-desktop"
        )
        return False
    elif system == "windows":
        print(
            "Please install Docker Desktop for Windows from https://www.docker.com/products/docker-desktop"
        )
        return False
    else:
        print(f"Unsupported operating system: {system}")
        return False

    for command in commands:
        subprocess.run(command, shell=True, check=True)
    return True


def install_docker_compose():
    system = platform.system().lower()
    if system == "linux":
        commands = [
            'sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose',
            "sudo chmod +x /usr/local/bin/docker-compose",
        ]
        for command in commands:
            subprocess.run(command, shell=True, check=True)
        return True
    elif system in ["darwin", "windows"]:
        print(
            "Docker Compose is included in Docker Desktop. Please ensure Docker Desktop is installed."
        )
        return False
    else:
        print(f"Unsupported operating system: {system}")
        return False


def check_prerequisites():
    if not is_tool_installed("docker"):
        print("Docker is not installed.")
        install = prompt_user("Would you like to install Docker? (y/n)", "y")
        if install.lower() != "y":
            print("Docker is required to run AGiXT. Exiting.")
            sys.exit(1)
        if not install_docker():
            print("Failed to install Docker. Please install it manually and try again.")
            sys.exit(1)

    if not is_tool_installed("docker-compose"):
        print("Docker Compose is not installed.")
        install = prompt_user("Would you like to install Docker Compose? (y/n)", "y")
        if install.lower() != "y":
            print("Docker Compose is required to run AGiXT. Exiting.")
            sys.exit(1)
        if not install_docker_compose():
            print(
                "Failed to install Docker Compose. Please install it manually and try again."
            )
            sys.exit(1)


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
    check_prerequisites()
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
