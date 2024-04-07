import re
import os
import subprocess
import platform
from dotenv import load_dotenv
import socket
import json

try:
    import win32com.client as wim
except ImportError:
    wim = None


def run_shell_command(command):
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return result.stdout


def is_docker_installed():
    try:
        subprocess.run(["docker", "--version"], check=True, stdout=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def prompt_user(prompt, default=None):
    user_input = input(f"{prompt} (default: {default}): ").strip()
    return user_input if user_input else default


def start_ezlocalai():
    load_dotenv()
    uri = os.getenv("EZLOCALAI_URI", f"http://{get_local_ip()}:8091")
    api_key = os.getenv("AGIXT_API_KEY", api_key)
    nvidia_gpu = False
    if not os.path.exists("ezlocalai"):
        run_shell_command("git clone https://github.com/DevXT-LLC/ezlocalai ezlocalai")
    else:
        run_shell_command("cd ezlocalai && git pull && cd ..")
    with open("ezlocalai/.env", "r") as file:
        lines = file.readlines()
    with open("ezlocalai/.env", "w") as file:
        for line in lines:
            if line.startswith("EZLOCALAI_API_KEY="):
                file.write(f"EZLOCALAI_API_KEY={api_key}\n")
            elif line.startswith("EZLOCALAI_URI="):
                file.write(f"EZLOCALAI_URI={uri}\n")
            else:
                file.write(line)
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
    if nvidia_gpu:
        run_shell_command(
            "cd ezlocalai && docker-compose -f docker-compose-cuda.yml down && docker-compose -f docker-compose-cuda.yml build && docker-compose -f docker-compose-cuda.yml up -d"
        )
    else:
        run_shell_command(
            "cd ezlocalai && docker-compose down && docker-compose build && docker-compose up -d"
        )


if not is_docker_installed():
    print("Docker is not installed. Please install Docker and try again.")
    exit(1)

print("\033[1m\033[96m")
print("    ___   _______ _  ________")
print("   /   | / ____(_) |/ /_  __/")
print("  / /| |/ / __/ /|   / / /   ")
print(" / ___ / /_/ / //   | / /    ")
print("/_/  |_\____/_//_/|_|/_/     ")
print(" ")
print("----------------------------------------------------\033[0m")
print("\033[1m\033[95mVisit our documentation at https://AGiXT.com \033[0m")

if not os.path.isfile(".env"):
    print("\033[1m\033[95mWelcome to the AGiXT Environment Setup!\033[0m")
    local_ip = get_local_ip()
    api_key = prompt_user("Set your AGiXT API key", "None")
    agixt_uri = prompt_user(
        "Set your AGiXT URI (This does not change the port)", f"http://{local_ip}:7437"
    )
    if api_key.lower() == "none":
        api_key = ""
    with open(".env", "w") as env_file:
        env_file.write(f"AGIXT_URI={agixt_uri}\n")
        env_file.write(f"AGIXT_API_KEY={api_key}\n")
        env_file.write("UVICORN_WORKERS=10\n")
load_dotenv()
use_ezlocalai = os.getenv("USE_EZLOCALAI", None)
if use_ezlocalai == None:
    # Ask user if they want to use ezLocalai
    use_ezlocalai = prompt_user(
        "Would you like to use ezLocalai to run local models? (Y/N)", "Yes"
    )
    if use_ezlocalai.lower() in ["y", "yes"]:
        use_ezlocalai = True
        with open(".env", "a") as env_file:
            env_file.write("USE_EZLOCALAI=true\n")
        if not os.path.exists("ezlocalai"):
            run_shell_command(
                "git clone https://github.com/DevXT-LLC/ezlocalai ezlocalai"
            )
        else:
            run_shell_command("cd ezlocalai && git pull && cd ..")
        ezlocalai_uri = prompt_user("Set your ezLocalai URI", f"http://{local_ip}:8091")
        default_llm = prompt_user("Default LLM to use", "Mistral-7B-Instruct-v0.2")
        default_vlm = prompt_user(
            "Use vision model? Enter model from Hugging Face or 'None' for no vision model",
            "deepseek-ai/deepseek-vl-1.3b-chat",
        )
        if default_vlm.lower() == "none":
            default_vlm = ""
        img_enabled = prompt_user("Enable image generation? (Y/N)", "No")
        if img_enabled.lower() in ["y", "yes"]:
            img_enabled = True
        else:
            img_enabled = False
        with open(".env", "a") as env_file:
            env_file.write("USE_EZLOCALAI=true\n")
        with open("ezlocalai/.env", "w") as env_file:
            env_file.write(f"EZLOCALAI_URI={ezlocalai_uri}\n")
            env_file.write(f"DEFAULT_LLM={default_llm}\n")
            env_file.write(f"DEFAULT_VLM={default_vlm}\n")
            env_file.write(f"IMG_ENABLED={img_enabled}\n")
        # Create a default ezlocalai agent that will work with AGiXT out of the box
        ezlocalai_agent_settings = {
            "commands": {},
            "settings": {
                "provider": "ezlocalai",
                "tts_provider": "ezlocalai",
                "transcription_provider": "ezlocalai",
                "translation_provider": "ezlocalai",
                "embeddings_provider": "default",
                "image_provider": "ezlocalai" if img_enabled else "default",
                "EZLOCALAI_API_KEY": api_key,
                "AI_MODEL": "Mistral-7B-Instruct-v0.2",
                "API_URI": f"{ezlocalai_uri}/v1/",
                "MAX_TOKENS": "4096",
                "AI_TEMPERATURE": 0.5,
                "AI_TOP_P": 0.9,
                "SYSTEM_MESSAGE": "",
                "VOICE": "HAL9000",
                "mode": "prompt",
                "prompt_category": "Default",
                "prompt_name": "Chat",
                "helper_agent_name": "AGiXT",
                "WEBSEARCH_TIMEOUT": 0,
                "WAIT_BETWEEN_REQUESTS": 1,
                "WAIT_AFTER_FAILURE": 3,
                "WORKING_DIRECTORY": "./WORKSPACE",
                "WORKING_DIRECTORY_RESTRICTED": True,
                "AUTONOMOUS_EXECUTION": True,
                "PERSONA": "",
            },
        }
        os.makedirs("agixt/agents/AGiXT", exist_ok=True)
        with open("agixt/agents/AGiXT/config.json", "w") as file:
            file.write(json.dumps(ezlocalai_agent_settings, indent=4))
    else:
        use_ezlocalai = False
        env_file = open(".env", "a")
        env_file.write("USE_EZLOCALAI=false\n")
        env_file.close()
else:
    use_ezlocalai = use_ezlocalai.lower() == "true"
print("\033[1m\033[95mWelcome to the AGiXT! \033[0m")
ops = prompt_user(
    f"""Choose from the following options:
1. Start AGiXT {'and ezLocalai ' if use_ezlocalai else ''}(Stable)
2. Start AGiXT {'and ezLocalai ' if use_ezlocalai else ''}(Development)
3. Exit
""",
    "1",
)
if ops == "1":
    if use_ezlocalai:
        start_ezlocalai()
    run_shell_command(
        "docker-compose down && docker-compose pull && docker-compose up -d"
    )
elif ops == "2":
    if use_ezlocalai:
        start_ezlocalai()
    run_shell_command(
        "docker-compose -f docker-compose-dev.yml down && docker-compose -f docker-compose-dev.yml pull && docker-compose -f docker-compose-dev.yml up -d"
    )
else:
    print("Exiting...")
    exit(1)
