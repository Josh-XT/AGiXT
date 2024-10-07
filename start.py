import os
import re
import sys
import subprocess
import random
import argparse
import platform
import socket

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
try:
    import win32com.client as wim
except ImportError:
    wim = None


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
    print(f"Executing: {command}")
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    while True:
        try:
            output = process.stdout.readline()
        except:
            print("View the logs in docker with 'docker compose logs'")
            break
        if output == "" and process.poll() is not None:
            break
        if output:
            print(output.strip())

    return_code = process.poll()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)


def get_default_env_vars():
    workspace_folder = os.path.normpath(os.path.join(os.getcwd(), "WORKSPACE"))
    machine_tz = get_localzone()
    return {
        "AGIXT_API_KEY": "",
        "STREAMLIT_AGIXT_URI": "http://agixt:7437",
        "AGIXT_URI": "http://localhost:7437",
        "AGIXT_PORT": "7437",
        "AGIXT_INTERACTIVE_PORT": "3437",
        "AGIXT_STREAMLIT_PORT": "8501",
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
        "AGIXT_SHOW_OVERRIDE_SWITCHES": "tts,websearch,analyze-user-input",
        "ALLOWED_DOMAINS": "*",
        "APP_DESCRIPTION": "A chat powered by AGiXT.",
        "APP_NAME": "AGiXT Chat",
        "APP_URI": "http://localhost:3437",
        "STREAMLIT_APP_URI": "http://localhost:8501",
        "AUTH_WEB": "http://localhost:3437/user",
        "AUTH_PROVIDER": "magicalauth",
        "CREATE_AGENT_ON_REGISTER": "true",
        "CREATE_AGIXT_AGENT": "true",
        "DISABLED_PROVIDERS": "",
        "DISABLED_EXTENSIONS": "",
        "WORKING_DIRECTORY": workspace_folder.replace("\\", "/"),
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
        "EZLOCALAI_URI": f"http://{get_local_ip()}:8091/v1/",
        "DEFAULT_MODEL": "QuantFactory/dolphin-2.9.2-qwen2-7b-GGUF",
        "VISION_MODEL": "deepseek-ai/deepseek-vl-1.3b-chat",
        "LLM_MAX_TOKENS": "32768",
        "WHISPER_MODEL": "base.en",
        "GPU_LAYERS": "0",
        "WITH_STREAMLIT": "true",
        "WITH_EZLOCALAI": "false",
        "REGISTRATION_DISABLED": "false",
        "AGIXT_ALLOW_MESSAGE_EDITING": "true",
        "AGIXT_ALLOW_MESSAGE_DELETION": "true",
        "AGIXT_SHOW_CHAT_THEME_TOGGLES": "",
        "LOG_VERBOSITY_SERVER": "3",
        "AOL_CLIENT_ID": "",
        "AOL_CLIENT_SECRET": "",
        "APPLE_CLIENT_ID": "",
        "APPLE_CLIENT_SECRET": "",
        "AUTODESK_CLIENT_ID": "",
        "AUTODESK_CLIENT_SECRET": "",
        "AWS_CLIENT_ID": "",
        "AWS_CLIENT_SECRET": "",
        "AWS_REGION": "",
        "AWS_USER_POOL_ID": "",
        "BATTLENET_CLIENT_ID": "",
        "BATTLENET_CLIENT_SECRET": "",
        "BITBUCKET_CLIENT_ID": "",
        "BITBUCKET_CLIENT_SECRET": "",
        "BITLY_ACCESS_TOKEN": "",
        "BITLY_CLIENT_ID": "",
        "BITLY_CLIENT_SECRET": "",
        "CF_CLIENT_ID": "",
        "CF_CLIENT_SECRET": "",
        "CLEAR_SCORE_CLIENT_ID": "",
        "CLEAR_SCORE_CLIENT_SECRET": "",
        "DEUTSCHE_TELKOM_CLIENT_ID": "",
        "DEUTSCHE_TELKOM_CLIENT_SECRET": "",
        "DEVIANTART_CLIENT_ID": "",
        "DEVIANTART_CLIENT_SECRET": "",
        "DISCORD_CLIENT_ID": "",
        "DISCORD_CLIENT_SECRET": "",
        "DROPBOX_CLIENT_ID": "",
        "DROPBOX_CLIENT_SECRET": "",
        "FACEBOOK_CLIENT_ID": "",
        "FACEBOOK_CLIENT_SECRET": "",
        "FATSECRET_CLIENT_ID": "",
        "FATSECRET_CLIENT_SECRET": "",
        "FITBIT_CLIENT_ID": "",
        "FITBIT_CLIENT_SECRET": "",
        "FORMSTACK_CLIENT_ID": "",
        "FORMSTACK_CLIENT_SECRET": "",
        "FOURSQUARE_CLIENT_ID": "",
        "FOURSQUARE_CLIENT_SECRET": "",
        "GITHUB_CLIENT_ID": "",
        "GITHUB_CLIENT_SECRET": "",
        "GITLAB_CLIENT_ID": "",
        "GITLAB_CLIENT_SECRET": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "HUDDLE_CLIENT_ID": "",
        "HUDDLE_CLIENT_SECRET": "",
        "IMGUR_CLIENT_ID": "",
        "IMGUR_CLIENT_SECRET": "",
        "INSTAGRAM_CLIENT_ID": "",
        "INSTAGRAM_CLIENT_SECRET": "",
        "INTEL_CLIENT_ID": "",
        "INTEL_CLIENT_SECRET": "",
        "JIVE_CLIENT_ID": "",
        "JIVE_CLIENT_SECRET": "",
        "KEYCLOAK_CLIENT_ID": "",
        "KEYCLOAK_CLIENT_SECRET": "",
        "KEYCLOAK_REALM": "",
        "KEYCLOAK_SERVER_URL": "",
        "LINKEDIN_CLIENT_ID": "",
        "LINKEDIN_CLIENT_SECRET": "",
        "MICROSOFT_CLIENT_ID": "",
        "MICROSOFT_CLIENT_SECRET": "",
        "NETIQ_CLIENT_ID": "",
        "NETIQ_CLIENT_SECRET": "",
        "OKTA_CLIENT_ID": "",
        "OKTA_CLIENT_SECRET": "",
        "OKTA_DOMAIN": "",
        "OPENAM_BASE_URL": "",
        "OPENAM_CLIENT_ID": "",
        "OPENAM_CLIENT_SECRET": "",
        "ORCID_CLIENT_ID": "",
        "ORCID_CLIENT_SECRET": "",
        "OSM_CLIENT_ID": "",
        "OSM_CLIENT_SECRET": "",
        "PAYPAL_CLIENT_ID": "",
        "PAYPAL_CLIENT_SECRET": "",
        "PING_IDENTITY_CLIENT_ID": "",
        "PING_IDENTITY_CLIENT_SECRET": "",
        "PIXIV_CLIENT_ID": "",
        "PIXIV_CLIENT_SECRET": "",
        "REDDIT_CLIENT_ID": "",
        "REDDIT_CLIENT_SECRET": "",
        "SALESFORCE_CLIENT_ID": "",
        "SALESFORCE_CLIENT_SECRET": "",
        "SPOTIFY_CLIENT_ID": "",
        "SPOTIFY_CLIENT_SECRET": "",
        "STACKEXCHANGE_CLIENT_ID": "",
        "STACKEXCHANGE_CLIENT_SECRET": "",
        "STRAVA_CLIENT_ID": "",
        "STRAVA_CLIENT_SECRET": "",
        "STRIPE_CLIENT_ID": "",
        "STRIPE_CLIENT_SECRET": "",
        "STRIPE_PUBLISHABLE_KEY": "",
        "STRIPE_PRICING_TABLE_ID": "",
        "STRIPE_API_KEY": "",
        "STRIPE_WEBHOOK_SECRET": "",
        "TWITCH_CLIENT_ID": "",
        "TWITCH_CLIENT_SECRET": "",
        "VIADEO_CLIENT_ID": "",
        "VIADEO_CLIENT_SECRET": "",
        "VIMEO_CLIENT_ID": "",
        "VIMEO_CLIENT_SECRET": "",
        "VK_CLIENT_ID": "",
        "VK_CLIENT_SECRET": "",
        "WECHAT_CLIENT_ID": "",
        "WECHAT_CLIENT_SECRET": "",
        "WEIBO_CLIENT_ID": "",
        "WEIBO_CLIENT_SECRET": "",
        "WITHINGS_CLIENT_ID": "",
        "WITHINGS_CLIENT_SECRET": "",
        "XERO_CLIENT_ID": "",
        "XERO_CLIENT_SECRET": "",
        "XING_CLIENT_ID": "",
        "XING_CLIENT_SECRET": "",
        "YAHOO_CLIENT_ID": "",
        "YAHOO_CLIENT_SECRET": "",
        "YAMMER_CLIENT_ID": "",
        "YAMMER_CLIENT_SECRET": "",
        "YANDEX_CLIENT_ID": "",
        "YANDEX_CLIENT_SECRET": "",
        "YELP_CLIENT_ID": "",
        "YELP_CLIENT_SECRET": "",
        "ZENDESK_CLIENT_ID": "",
        "ZENDESK_CLIENT_SECRET": "",
        "ZENDESK_SUBDOMAIN": "",
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
    if str(env_vars["WITH_EZLOCALAI"]).lower() == "true":
        print("Starting ezLocalai, this can take several minutes...")
        start_ezlocalai()
    dockerfile = "docker-compose.yml"
    if env_vars["AGIXT_BRANCH"] != "stable":
        dockerfile = "docker-compose-dev.yml"
    if str(env_vars["WITH_STREAMLIT"]).lower() == "true":
        if env_vars["AGIXT_BRANCH"] != "stable":
            dockerfile = "docker-compose-dev.yml"
        else:
            dockerfile = "docker-compose.yml"
    else:
        if env_vars["AGIXT_BRANCH"] != "stable":
            dockerfile = "docker-compose-nostreamlit-dev.yml"
        else:
            dockerfile = "docker-compose-nostreamlit.yml"
    if str(env_vars["AGIXT_AUTO_UPDATE"]).lower() == "true":
        command = f"docker compose -f {dockerfile} stop && docker compose -f {dockerfile} pull && docker compose -f {dockerfile} up -d"
    else:
        command = f"docker compose -f {dockerfile} stop && docker compose -f {dockerfile} up -d"
    print("Press Ctrl+C to stop the containers and exit.")
    try:
        run_shell_command(command)
    except KeyboardInterrupt:
        print("\nStopping AGiXT containers...")
        run_shell_command(f"docker compose -f {dockerfile} stop")
        print("AGiXT containers stopped.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
    return env_vars


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip
    except Exception as e:
        return "localhost"


def get_cuda_vram():
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) == 0:
            return 0, 0
        total_vram, free_vram = map(int, lines[0].split(","))
        return total_vram, free_vram
    except FileNotFoundError:
        print("nvidia-smi not found. No CUDA support.")
        return 0, 0
    except subprocess.CalledProcessError as e:
        print(f"nvidia-smi failed with error: {e.stderr}")
        return 0, 0
    except Exception as e:
        print(f"Error getting CUDA information: {e}")
        return 0, 0


def start_ezlocalai():
    load_dotenv()
    env = get_default_env_vars()
    nvidia_gpu = False
    if not os.path.exists("ezlocalai"):
        run_shell_command("git clone https://github.com/DevXT-LLC/ezlocalai ezlocalai")
    else:
        run_shell_command("cd ezlocalai && git pull && cd ..")
    total_vram, free_vram = get_cuda_vram()
    # if free vram is greater than 16gb, use 33 GPU layers
    gpu_layers = int(env["GPU_LAYERS"])
    if free_vram == 0:
        gpu_layers = 0
    if free_vram > 0 and gpu_layers == -1:
        if free_vram > 16 * 1024:
            gpu_layers = 33
        elif free_vram > 8 * 1024:
            gpu_layers = 16
        elif free_vram > 4 * 1024:
            gpu_layers = 8
        elif free_vram > 2 * 1024:
            gpu_layers = 0
    with open(".env", "r") as file:
        env_content = file.read()
    with open("ezlocalai/.env", "w") as file:
        file.write(env_content)
    if platform.system() == "Windows":
        wmi = wim.GetObject("winmgmts:")
        for video_controller in wmi.InstancesOf("Win32_VideoController"):
            if "NVIDIA" in video_controller.Name:
                nvidia_gpu = True
    elif platform.system() == "Linux":
        cmd = "lspci | grep 'VGA' | grep 'NVIDIA'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        gpu_name_match = re.search(r"NVIDIA\s+([^:]+)", result.stdout)
        if gpu_name_match:
            nvidia_gpu = True
    if nvidia_gpu and total_vram > 0:
        run_shell_command(
            "cd ezlocalai && docker compose -f docker-compose-cuda.yml stop && docker compose -f docker-compose-cuda.yml build && docker compose -f docker-compose-cuda.yml up -d"
        )
    else:
        run_shell_command(
            "cd ezlocalai && docker compose stop && docker compose build && docker compose up -d"
        )


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
            "Would you like AGiXT to auto update when this script is run in the future? (Y for yes, N for no)",
            "y",
        )
        if auto_update.lower() == "y" or auto_update.lower() == "yes":
            auto_update = "true"
        else:
            auto_update = "false"
        env_updates["AGIXT_AUTO_UPDATE"] = auto_update
    # Apply updates and restart server
    print("Please wait while AGiXT is starting, this can take several minutes...")
    set_environment(env_updates=env_updates)
