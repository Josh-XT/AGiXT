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
            print("View the logs in docker with 'docker-compose logs'")
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
        "EZLOCALAI_URI": f"http://{get_local_ip()}:8091/v1/",
        "DEFAULT_MODEL": "QuantFactory/dolphin-2.9.2-qwen2-7b-GGUF",
        "VISION_MODEL": "deepseek-ai/deepseek-vl-1.3b-chat",
        "LLM_MAX_TOKENS": "32768",
        "WHISPER_MODEL": "base.en",
        "GPU_LAYERS": "0",
        "WITH_STREAMLIT": "true",
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
        command = f"docker-compose -f {dockerfile} stop && docker-compose -f {dockerfile} pull && docker-compose -f {dockerfile} up"
    else:
        command = (
            f"docker-compose -f {dockerfile} stop && docker-compose -f {dockerfile} up"
        )
    print("Press Ctrl+C to stop the containers and exit.")
    try:
        run_shell_command(command)
    except KeyboardInterrupt:
        print("\nStopping AGiXT containers...")
        run_shell_command(f"docker-compose -f {dockerfile} stop")
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
    uri = env["EZLOCALAI_URI"]
    api_key = env["AGIXT_API_KEY"]
    default_model = env["DEFAULT_MODEL"]
    vision_model = env["VISION_MODEL"]
    llm_max_tokens = env["LLM_MAX_TOKENS"]
    whisper_model = env["WHISPER_MODEL"]
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
    with open("ezlocalai/.env", "r") as file:
        lines = file.readlines()
    with open("ezlocalai/.env", "w") as file:
        for line in lines:
            if line.startswith("EZLOCALAI_API_KEY="):
                file.write(f"EZLOCALAI_API_KEY={api_key}\n")
            elif line.startswith("EZLOCALAI_URI="):
                file.write(f"EZLOCALAI_URI={uri}\n")
            elif line.startswith("DEFAULT_MODEL="):
                file.write(f"DEFAULT_MODEL={default_model}\n")
            elif line.startswith("VISION_MODEL="):
                file.write(f"VISION_MODEL={vision_model}\n")
            elif line.startswith("LLM_MAX_TOKENS="):
                file.write(f"LLM_MAX_TOKENS={llm_max_tokens}\n")
            elif line.startswith("WHISPER_MODEL="):
                file.write(f"WHISPER_MODEL={whisper_model}\n")
            elif line.startswith("GPU_LAYERS="):
                file.write(f"GPU_LAYERS={gpu_layers}\n")
            else:
                file.write(line)
    set_environment(
        env_updates={
            "EZLOCALAI_URI": uri,
            "EZLOCALAI_API_KEY": api_key,
            "DEFAULT_MODEL": default_model,
            "VISION_MODEL": vision_model,
            "LLM_MAX_TOKENS": llm_max_tokens,
            "WHISPER_MODEL": whisper_model,
            "GPU_LAYERS": gpu_layers,
        }
    )
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
            "cd ezlocalai && docker-compose -f docker-compose-cuda.yml stop && docker-compose -f docker-compose-cuda.yml build && docker-compose -f docker-compose-cuda.yml up -d"
        )
    else:
        run_shell_command(
            "cd ezlocalai && docker-compose stop && docker-compose build && docker-compose up -d"
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
