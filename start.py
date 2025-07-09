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
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "tzlocal", "--break-system-packages"],
        check=True,
    )
    print("Installed tzlocal package.")
    from tzlocal import get_localzone
try:
    from dotenv import load_dotenv
except ImportError:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "python-dotenv",
            "--break-system-packages",
        ],
        check=True,
    )
    from dotenv import load_dotenv
try:
    import win32com.client as wim  # type: ignore
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
    unsupported_message = "Docker is required to run AGiXT. Please install Docker manually from https://www.docker.com/products/docker-desktop"
    if system == "linux":
        install = prompt_user(
            "Docker is not installed. Would you like to install Docker? (y/n)", "y"
        )
        if install.lower() != "y":
            print("Docker is required to run AGiXT. Exiting.")
            return False
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
            print(unsupported_message)
            return False
    else:
        print(unsupported_message)
        return False

    for command in commands:
        subprocess.run(command, shell=True, check=True)
    return True


def check_prerequisites():
    if not is_tool_installed("docker"):
        if not install_docker():
            print(
                "Failed to install Docker. Please install it manually from https://www.docker.com/products/docker-desktop"
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
        # Core AGiXT configuration
        "AGIXT_API_KEY": "",
        "AGIXT_URI": "http://localhost:7437",
        "AGIXT_PORT": "7437",
        "AGIXT_INTERACTIVE_PORT": "3437",
        "APP_PORT": "3437",
        "AGIXT_AGENT": "XT",
        "AGIXT_BRANCH": "stable",
        "AGIXT_FILE_UPLOAD_ENABLED": "true",
        "AGIXT_VOICE_INPUT_ENABLED": "true",
        "AGIXT_FOOTER_MESSAGE": "AGiXT 2025",
        "AGIXT_SERVER": "http://localhost:7437",
        "AGIXT_RLHF": "true",
        "AGIXT_CONVERSATION_MODE": "select",
        "AGIXT_SHOW_OVERRIDE_SWITCHES": "tts,websearch,analyze-user-input",
        "AGIXT_ALLOW_MESSAGE_EDITING": "true",
        "AGIXT_ALLOW_MESSAGE_DELETION": "true",
        "AGIXT_AUTO_UPDATE": "true",
        # App configuration
        "APP_DESCRIPTION": "AGiXT is an advanced artificial intelligence agent orchestration agent.",
        "APP_NAME": "AGiXT",
        "APP_URI": "http://localhost:3437",
        "ALLOW_EMAIL_SIGN_IN": "true",
        # System configuration
        "DATABASE_TYPE": "sqlite",
        "DATABASE_NAME": "models/agixt",
        "LOG_LEVEL": "INFO",
        "LOG_VERBOSITY_SERVER": "3",
        "UVICORN_WORKERS": "10",
        "WORKING_DIRECTORY": workspace_folder.replace("\\", "/"),
        "TZ": str(machine_tz),
        "DISABLED_PROVIDERS": "",
        "DISABLED_EXTENSIONS": "",
        "REGISTRATION_DISABLED": "false",
        "GRAPHIQL": "true",
        # Storage configuration
        "STORAGE_BACKEND": "local",
        "STORAGE_CONTAINER": "agixt-workspace",
        "B2_KEY_ID": "",
        "B2_APPLICATION_KEY": "",
        "B2_REGION": "us-west-002",
        "S3_BUCKET": "agixt-workspace",
        "S3_ENDPOINT": "http://minio:9000",
        "AWS_ACCESS_KEY_ID": "minioadmin",
        "AWS_SECRET_ACCESS_KEY": "minioadmin",
        "AWS_STORAGE_REGION": "us-east-1",
        "AZURE_STORAGE_ACCOUNT_NAME": "",
        "AZURE_STORAGE_KEY": "",
        # Agent configuration
        "SEED_DATA": "true",
        "AGENT_NAME": "XT",
        "AGENT_PERSONA": "",
        "TRAINING_URLS": "",
        "ENABLED_COMMANDS": "",
        "ROTATION_EXCLUSIONS": "",
        # AI Model configuration
        "EZLOCALAI_URI": f"http://{get_local_ip()}:8091/v1/",
        "EZLOCALAI_VOICE": "",
        "ANTHROPIC_MODEL": "",
        "DEEPSEEK_MODEL": "",
        "AZURE_MODEL": "",
        "GOOGLE_MODEL": "",
        "OPENAI_MODEL": "",
        "XAI_MODEL": "",
        "EZLOCALAI_MAX_TOKENS": "",
        "DEEPSEEK_MAX_TOKENS": "",
        "AZURE_MAX_TOKENS": "",
        "XAI_MAX_TOKENS": "",
        "OPENAI_MAX_TOKENS": "",
        "ANTHROPIC_MAX_TOKENS": "",
        "GOOGLE_MAX_TOKENS": "",
        # API Keys
        "AZURE_API_KEY": "",
        "GOOGLE_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "EZLOCALAI_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "XAI_API_KEY": "",
        "AZURE_OPENAI_ENDPOINT": "",
        # OAuth Client IDs and Secrets
        "ALEXA_CLIENT_ID": "",
        "ALEXA_CLIENT_SECRET": "",
        "AWS_CLIENT_ID": "",
        "AWS_CLIENT_SECRET": "",
        "AWS_REGION": "",
        "AWS_USER_POOL_ID": "",
        "DISCORD_CLIENT_ID": "",
        "DISCORD_CLIENT_SECRET": "",
        "FITBIT_CLIENT_ID": "",
        "FITBIT_CLIENT_SECRET": "",
        "GARMIN_CLIENT_ID": "",
        "GARMIN_CLIENT_SECRET": "",
        "GITHUB_CLIENT_ID": "",
        "GITHUB_CLIENT_SECRET": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "MICROSOFT_CLIENT_ID": "",
        "MICROSOFT_CLIENT_SECRET": "",
        "TESLA_CLIENT_ID": "",
        "TESLA_CLIENT_SECRET": "",
        "WALMART_CLIENT_ID": "",
        "WALMART_CLIENT_SECRET": "",
        "WALMART_MARKETPLACE_ID": "",
        "X_CLIENT_ID": "",
        "X_CLIENT_SECRET": "",
        # Local configuration (not in docker-compose but needed for local setup)
        "DEFAULT_MODEL": "bartowski/deepseek-ai_DeepSeek-R1-0528-Qwen3-8B-GGUF",
        "VISION_MODEL": "deepseek-ai/deepseek-vl-1.3b-chat",
        "LLM_MAX_TOKENS": "32768",
        "WHISPER_MODEL": "base",
        "GPU_LAYERS": "0",
        "WITH_EZLOCALAI": "false",
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
    if env_vars["AGIXT_BRANCH"] != "stable":
        dockerfile = "docker-compose-dev.yml"
    else:
        dockerfile = "docker-compose.yml"
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
