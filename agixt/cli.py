#!/usr/bin/env python3
"""Command line helper for common AGiXT workflows."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
import platform
import random
import socket
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
XTSYS_ROOT = REPO_ROOT.parent  # Parent of AGiXT folder
LOCAL_SCRIPT = Path(__file__).resolve().parent / "run-local.py"
DOCKER_COMPOSE_FILE_STABLE = REPO_ROOT / "docker-compose.yml"
DOCKER_COMPOSE_FILE_DEV = REPO_ROOT / "docker-compose-dev.yml"
ENV_FILE = REPO_ROOT / ".env"
WEB_DIR = XTSYS_ROOT / "web"
STATE_DIR = Path.home() / ".agixt"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_PID_FILE = STATE_DIR / "agixt-local.pid"
LOCAL_LOG_FILE = STATE_DIR / f"agixt-local-{int(time.time())}.log"
WEB_PID_FILE = STATE_DIR / "agixt-web.pid"


class CLIError(RuntimeError):
    """Raised for recoverable CLI errors."""


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


def get_default_env_vars():
    workspace_folder = os.path.normpath(os.path.join(os.getcwd(), "WORKSPACE"))
    return {
        # Core AGiXT configuration
        "AGIXT_API_KEY": "",
        "AGIXT_URI": "http://localhost:7437",
        "AGIXT_PORT": "7437",
        "AGIXT_INTERACTIVE_PORT": "3437",
        "APP_PORT": "3437",
        "AGIXT_AGENT": "XT",
        "AGIXT_BRANCH": "stable",
        "AGIXT_RUN_TYPE": "docker",
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
        "AGIXT_HEALTH_URL": "http://localhost:7437/health",
        # App configuration
        "APP_DESCRIPTION": "AGiXT is an advanced artificial intelligence agent orchestration agent.",
        "APP_NAME": "AGiXT",
        "APP_URI": "http://localhost:3437",
        "ALLOW_EMAIL_SIGN_IN": "true",
        "ALLOWED_DOMAINS": "*",
        # System configuration
        "DATABASE_TYPE": "sqlite",
        "DATABASE_NAME": "models/agixt",
        "DATABASE_USER": "postgres",
        "DATABASE_PASSWORD": "postgres",
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        "DEFAULT_USER": "user",
        "USING_JWT": "false",
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(asctime)s | %(levelname)s | %(message)s",
        "LOG_VERBOSITY_SERVER": "3",
        "UVICORN_WORKERS": "10",
        "WORKING_DIRECTORY": workspace_folder.replace("\\", "/"),
        "TZ": "UTC",
        "DISABLED_PROVIDERS": "",
        "DISABLED_EXTENSIONS": "",
        "REGISTRATION_DISABLED": "false",
        "CREATE_AGENT_ON_REGISTER": "true",
        "CREATE_AGIXT_AGENT": "true",
        "GRAPHIQL": "true",
        "EMAIL_SERVER": "",
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
        # Health check configuration
        "HEALTH_CHECK_INTERVAL": "15",
        "HEALTH_CHECK_TIMEOUT": "10",
        "HEALTH_CHECK_MAX_FAILURES": "3",
        "RESTART_COOLDOWN": "60",
        "INITIAL_STARTUP_DELAY": "180",
        # Extensions configuration
        "EXTENSIONS_HUB": "",
        "EXTENSIONS_HUB_TOKEN": "",
        # Payment configuration
        "PAYMENT_WALLET_ADDRESS": "BavSLrHbzcq5QdY491Fo6uC9rqvfKgszVcj661zqJogS",
        "PAYMENT_SOLANA_RPC_URL": "https://api.mainnet-beta.solana.com",
        "TOKEN_PRICE_PER_MILLION_USD": "0",
        "MIN_TOKEN_TOPUP_USD": "10.00",
        "STRIPE_API_KEY": "",
        "STRIPE_PUBLISHABLE_KEY": "",
        # AI Model configuration
        "EZLOCALAI_URI": f"http://{get_local_ip()}:8091/v1/",
        "EZLOCALAI_VOICE": "DukeNukem",
        "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        "DEEPSEEK_MODEL": "deepseek-chat",
        "AZURE_MODEL": "gpt-4o",
        "GOOGLE_MODEL": "gemini-2.0-flash-exp",
        "OPENAI_MODEL": "chatgpt-4o-latest",
        "XAI_MODEL": "grok-beta",
        "EZLOCALAI_MAX_TOKENS": "16000",
        "DEEPSEEK_MAX_TOKENS": "60000",
        "AZURE_MAX_TOKENS": "100000",
        "XAI_MAX_TOKENS": "120000",
        "OPENAI_MAX_TOKENS": "128000",
        "ANTHROPIC_MAX_TOKENS": "140000",
        "GOOGLE_MAX_TOKENS": "1048000",
        # ezLocalai Configuration
        "GPU_LAYERS": "-1",
        "MAIN_GPU": "0",
        "NGROK_TOKEN": "",
        "EZLOCALAI_URL": "http://localhost:8091",
        "DEFAULT_MODEL": "unsloth/Qwen3-4B-Instruct-2507-GGUF",
        "VISION_MODEL": "",
        "IMG_MODEL": "",
        "WHISPER_MODEL": "base",
        "MAX_CONCURRENT_REQUESTS": "2",
        "MAX_QUEUE_SIZE": "100",
        "REQUEST_TIMEOUT": "300",
        # API Keys
        "AZURE_API_KEY": "",
        "GOOGLE_API_KEY": "",
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URI": "https://api.openai.com/v1",
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
        "META_APP_ID": "",
        "META_APP_SECRET": "",
        "META_BUSINESS_ID": "",
        "MICROSOFT_CLIENT_ID": "",
        "MICROSOFT_CLIENT_SECRET": "",
        "TESLA_CLIENT_ID": "",
        "TESLA_CLIENT_SECRET": "",
        "WALMART_CLIENT_ID": "",
        "WALMART_CLIENT_SECRET": "",
        "WALMART_MARKETPLACE_ID": "",
        "X_CLIENT_ID": "",
        "X_CLIENT_SECRET": "",
        "WITH_EZLOCALAI": "true",
    }


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


def set_environment(env_updates=None, mode="docker"):
    """
    Set up environment variables and write to .env file.

    Args:
        env_updates: Dictionary of environment variable updates
        mode: Either "local" or "docker" to determine update behavior
    """
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
    # Write to .env file without destroying comments/custom entries
    env_file_path = REPO_ROOT / ".env"
    existing_lines: list[str] = []
    if env_file_path.exists():
        existing_lines = env_file_path.read_text(encoding="utf-8").splitlines()

    if existing_lines:
        line_lookup: dict[str, int] = {}
        pattern = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=")
        for idx, line in enumerate(existing_lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = pattern.match(stripped)
            if match:
                line_lookup[match.group(1)] = idx

        pending_additions: list[str] = []
        for key, value in env_vars.items():
            new_line = f'{key}="{value}"'
            if key in line_lookup:
                existing_lines[line_lookup[key]] = new_line
            else:
                pending_additions.append(new_line)

        if pending_additions:
            if existing_lines and existing_lines[-1].strip() != "":
                existing_lines.append("")
            existing_lines.extend(pending_additions)
        env_file_content = "\n".join(existing_lines)
    else:
        env_file_content = "\n".join(
            [f'{key}="{value}"' for key, value in env_vars.items()]
        )

    with open(env_file_path, "w", encoding="utf-8") as file:
        file.write(env_file_content + "\n")

    # Handle auto-update based on mode
    if str(env_vars["AGIXT_AUTO_UPDATE"]).lower() == "true":
        if mode == "local":
            print("Updating AGiXT from git...")
            try:
                subprocess.run(
                    ["git", "pull"],
                    cwd=REPO_ROOT,
                    check=True,
                    capture_output=False,
                )
                print("AGiXT updated successfully.")
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to update from git: {e}")
        else:  # docker mode
            dockerfile = "docker-compose.yml"
            if env_vars["AGIXT_BRANCH"] != "stable":
                dockerfile = "docker-compose-dev.yml"
            print("Pulling latest Docker images...")
            try:
                subprocess.run(
                    ["docker", "compose", "-f", dockerfile, "pull"],
                    cwd=REPO_ROOT,
                    check=True,
                )
                print("Docker images updated successfully.")
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to pull Docker images: {e}")

    if str(env_vars["WITH_EZLOCALAI"]).lower() == "true":
        print("Starting ezLocalai, this can take several minutes...")
        start_ezlocalai()

    return env_vars


def start_ezlocalai():
    """Start ezLocalai using the ezlocalai CLI."""
    print("Starting ezLocalai...")
    try:
        subprocess.run(["ezlocalai", "start"], check=True)
    except FileNotFoundError:
        raise CLIError(
            "ezlocalai CLI not found. Install it with: pip install ezlocalai"
        )
    except subprocess.CalledProcessError as e:
        raise CLIError(f"Failed to start ezLocalai: {e}")


def stop_ezlocalai():
    """Stop ezLocalai using the ezlocalai CLI."""
    print("Stopping ezLocalai...")
    try:
        subprocess.run(["ezlocalai", "stop"], check=True)
    except FileNotFoundError:
        raise CLIError(
            "ezlocalai CLI not found. Install it with: pip install ezlocalai"
        )
    except subprocess.CalledProcessError as e:
        print(f"Error stopping ezLocalai: {e}")


def restart_ezlocalai():
    """Restart ezLocalai using the ezlocalai CLI."""
    print("Restarting ezLocalai...")
    try:
        subprocess.run(["ezlocalai", "restart"], check=True)
    except FileNotFoundError:
        raise CLIError(
            "ezlocalai CLI not found. Install it with: pip install ezlocalai"
        )
    except subprocess.CalledProcessError as e:
        raise CLIError(f"Failed to restart ezLocalai: {e}")


def _is_ezlocalai_enabled() -> bool:
    """Check if ezLocalai integration is enabled via environment."""
    load_dotenv(ENV_FILE)
    return os.getenv("WITH_EZLOCALAI", "true").lower() == "true"


def _create_web_env() -> None:
    """Create .env file for web interface with values from backend .env or defaults."""
    web_env_path = WEB_DIR / ".env"

    # Load backend .env to get values
    load_dotenv(ENV_FILE)

    # Define web env variables with backend inheritance or defaults
    web_env_vars = {
        "AGIXT_SERVER": os.getenv("AGIXT_SERVER", "http://localhost:7437"),
        "APP_URI": os.getenv("APP_URI", "http://localhost:3437"),
        "APP_NAME": os.getenv("APP_NAME", "AGiXT"),
        "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY": os.getenv("STRIPE_PUBLISHABLE_KEY", ""),
        "STRIPE_PRICING_TABLE_ID": os.getenv("STRIPE_PRICING_TABLE_ID", ""),
        "AGIXT_AGENT": os.getenv("AGIXT_AGENT", "XT"),
        "ALLOW_EMAIL_SIGN_IN": os.getenv("ALLOW_EMAIL_SIGN_IN", "true"),
    }

    # Write to web .env file
    print(f"Creating web .env file at {web_env_path}...")
    with web_env_path.open("w", encoding="utf-8") as f:
        for key, value in web_env_vars.items():
            f.write(f"{key}={value}\n")
    print("Web .env file created successfully.")


def _start_web_local() -> None:
    """Start web interface locally (npm run dev)."""
    web_path = WEB_DIR

    # Check if already running
    existing_pid = _read_pid(WEB_PID_FILE)
    if existing_pid and _is_process_running(existing_pid):
        raise CLIError(f"Web interface already running with PID {existing_pid}.")

    # Clone or update web repo
    if not web_path.exists():
        print(f"Cloning web repo to {web_path}...")
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/AGiXT/web",
                str(XTSYS_ROOT / "AGiXT-web-temp"),
            ],
            check=True,
        )
        # Move only the web folder
        import shutil

        shutil.move(str(XTSYS_ROOT / "AGiXT-web-temp" / "web"), str(web_path))
        shutil.rmtree(str(XTSYS_ROOT / "AGiXT-web-temp"))
    else:
        print(f"Updating web repo at {web_path}...")
        subprocess.run(["git", "pull"], cwd=web_path, check=True)

    # Create web .env file with backend values
    _create_web_env()

    # Install dependencies if needed
    if not (web_path / "node_modules").exists():
        print("Installing web dependencies...")
        subprocess.run(["npm", "install"], cwd=web_path, check=True)

    # Kill anything on port 3437
    pids_on_port = _find_processes_on_port(3437)
    for pid in pids_on_port:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"Killed existing process on port 3437 (PID {pid})")
        except (ProcessLookupError, PermissionError):
            pass

    print("Starting web interface...")
    log_file = STATE_DIR / f"agixt-web-{int(time.time())}.log"
    log_file.touch()

    with log_file.open("a", encoding="utf-8") as lf:
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=web_path,
            stdout=lf,
            stderr=lf,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    WEB_PID_FILE.write_text(str(process.pid))
    print(f"Web interface started successfully! (PID {process.pid})")
    print(f"View logs at: {log_file}")
    print("Web interface will be available at http://localhost:3437")


def _stop_web_local() -> None:
    """Stop locally running web interface."""
    pid = _read_pid(WEB_PID_FILE)
    stopped_by_pid = False

    if pid and _is_process_running(pid):
        print("Stopping web interface...")
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            if _is_process_running(pid):
                os.kill(pid, signal.SIGKILL)
            print(f"Stopped web interface (PID {pid}).")
            stopped_by_pid = True
        except (ProcessLookupError, PermissionError) as e:
            print(f"Error stopping process {pid}: {e}")

    # Also check for processes on port 3437
    pids_on_port = _find_processes_on_port(3437)
    if pids_on_port:
        for port_pid in pids_on_port:
            if port_pid != pid:
                try:
                    os.kill(port_pid, signal.SIGKILL)
                    print(f"Killed process on port 3437 (PID {port_pid})")
                except (ProcessLookupError, PermissionError):
                    pass
    elif not stopped_by_pid:
        print("No web interface processes found running.")

    WEB_PID_FILE.unlink(missing_ok=True)


def _restart_web_local() -> None:
    """Restart locally running web interface."""
    _stop_web_local()
    _start_web_local()


def _start_web_docker() -> None:
    """Start web interface via Docker (interactive service)."""
    # Create web .env file with backend values
    _create_web_env()

    compose_file = _determine_compose_file()
    print("Starting web interface (interactive service)...")
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d", "interactive"],
            cwd=REPO_ROOT,
            check=True,
        )
        print("Web interface started successfully!")
    except subprocess.CalledProcessError as e:
        raise CLIError(f"Failed to start web interface: {e}")


def _stop_web_docker() -> None:
    """Stop web interface Docker service."""
    compose_file = _determine_compose_file()
    print("Stopping web interface (interactive service)...")
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "stop", "interactive"],
            cwd=REPO_ROOT,
            check=True,
        )
        print("Web interface stopped successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error stopping web interface: {e}")


def _restart_web_docker() -> None:
    """Restart web interface Docker service."""
    _stop_web_docker()
    _start_web_docker()


def _start_all(local: bool = False, env_updates: Optional[dict] = None) -> None:
    """Start all services (AGiXT + ezLocalai + web)."""
    print("=" * 80)
    print("Starting all services...")
    print("=" * 80)

    # Start AGiXT first
    if local:
        print("\n[1/3] Starting AGiXT locally...")
        _start_local(env_updates=env_updates)
    else:
        print("\n[1/3] Starting AGiXT via Docker...")
        _start_docker(env_updates=env_updates)

    # Start ezLocalai (always Docker)
    print("\n[2/3] Starting ezLocalai...")
    start_ezlocalai()

    # Start web interface
    if local:
        print("\n[3/3] Starting web interface locally (npm run dev)...")
        _start_web_local()
    else:
        print("\n[3/3] Starting web interface via Docker...")
        _start_web_docker()

    print("\n" + "=" * 80)
    print("All services started successfully!")
    print("=" * 80)
    print("\nService URLs:")
    print(f"  AGiXT API:        http://localhost:7437")
    print(f"  Web Interface:    http://localhost:3437")
    print(f"  ezLocalai API:    http://localhost:8091")
    print("=" * 80)


def _stop_all(local: bool = False) -> None:
    """Stop all services (AGiXT + ezLocalai + web)."""
    print("=" * 80)
    print("Stopping all services...")
    print("=" * 80)

    # Stop in reverse order
    # Stop web interface
    if local:
        print("\n[1/3] Stopping web interface (local)...")
        _stop_web_local()
    else:
        print("\n[1/3] Stopping web interface (Docker)...")
        _stop_web_docker()

    # Stop ezLocalai (always Docker)
    print("\n[2/3] Stopping ezLocalai...")
    stop_ezlocalai()

    # Stop AGiXT
    if local:
        print("\n[3/3] Stopping AGiXT (local)...")
        _stop_local()
    else:
        print("\n[3/3] Stopping AGiXT (Docker)...")
        _stop_docker()

    print("\n" + "=" * 80)
    print("All services stopped successfully!")
    print("=" * 80)


def _restart_all(local: bool = False, env_updates: Optional[dict] = None) -> None:
    """Restart all services (AGiXT + ezLocalai + web)."""
    print("=" * 80)
    print("Restarting all services...")
    print("=" * 80)

    # Stop all first
    _stop_all(local=local)

    # Wait a moment for clean shutdown
    print("\nWaiting for clean shutdown...")
    time.sleep(2)

    # Start all
    _start_all(local=local, env_updates=env_updates)


def cleanup_log_files(max_files: int = 5) -> None:
    """Keep only the most recent `max_files` log files in the STATE_DIR."""
    log_files = sorted(
        STATE_DIR.glob("agixt-local-*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old_log in log_files[max_files:]:
        try:
            old_log.unlink()
        except OSError:
            pass


def _ensure_local_requirements() -> None:
    if not LOCAL_SCRIPT.exists():
        raise CLIError(
            f"Local startup script not found at {LOCAL_SCRIPT}. "
            "Reinstall AGiXT or run the command from the repository root."
        )


def _ensure_docker_requirements() -> None:
    # Check for docker-compose.yml to verify we're in AGiXT repository
    if not DOCKER_COMPOSE_FILE_STABLE.exists() and not DOCKER_COMPOSE_FILE_DEV.exists():
        raise CLIError(
            f"Docker compose files not found in {REPO_ROOT}. "
            "Run this command from the AGiXT repository checkout."
        )
    if not shutil.which("docker"):
        raise CLIError(
            "Docker is not available on PATH. Install Docker to use this command."
        )


def _read_pid(pid_file: Path) -> Optional[int]:
    try:
        pid = int(pid_file.read_text().strip())
        if pid <= 0:
            return None
        return pid
    except FileNotFoundError:
        return None
    except ValueError:
        return None


def _is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _find_processes_on_port(port: int) -> list[int]:
    """Find all process IDs listening on the specified port."""
    pids = []

    # Try using lsof first (common on Unix-like systems)
    if shutil.which("lsof"):
        try:
            result = subprocess.run(
                ["lsof", "-t", f"-i:{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    try:
                        pid = int(line.strip())
                        if pid > 0:
                            pids.append(pid)
                    except ValueError:
                        pass
        except (subprocess.SubprocessError, OSError):
            pass

    # Fallback to netstat/ss if lsof is not available
    if not pids:
        if shutil.which("ss"):
            try:
                result = subprocess.run(
                    ["ss", "-tlnp"], capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if f":{port}" in line:
                            # Extract PID from lines like "users:(("python",pid=12345,fd=3))"
                            match = re.search(r"pid=(\d+)", line)
                            if match:
                                try:
                                    pid = int(match.group(1))
                                    if pid > 0 and pid not in pids:
                                        pids.append(pid)
                                except ValueError:
                                    pass
            except (subprocess.SubprocessError, OSError):
                pass

        elif shutil.which("netstat"):
            try:
                result = subprocess.run(
                    ["netstat", "-tlnp"], capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if f":{port}" in line:
                            # Extract PID from lines like "12345/python"
                            parts = line.split()
                            for part in parts:
                                if "/" in part:
                                    try:
                                        pid = int(part.split("/")[0])
                                        if pid > 0 and pid not in pids:
                                            pids.append(pid)
                                    except (ValueError, IndexError):
                                        pass
            except (subprocess.SubprocessError, OSError):
                pass

    return pids


def _start_local(env_updates: Optional[dict] = None) -> None:
    _ensure_local_requirements()

    existing_pid = _read_pid(LOCAL_PID_FILE)
    if existing_pid and _is_process_running(existing_pid):
        raise CLIError(f"AGiXT local already running with PID {existing_pid}.")

    # Set up environment
    set_environment(env_updates=env_updates, mode="local")

    print("Starting AGiXT...")
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    LOCAL_LOG_FILE.touch()
    process: Optional[subprocess.Popen] = None
    try:
        with LOCAL_LOG_FILE.open("a", encoding="utf-8") as log_file:
            # Properly daemonize the process to prevent terminal locking
            process = subprocess.Popen(
                [sys.executable, str(LOCAL_SCRIPT)],
                cwd=LOCAL_SCRIPT.parent,
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,  # Create new process group for proper backgrounding
            )
    except OSError as exc:
        raise CLIError(f"Failed to start AGiXT locally: {exc}")

    if process is None:
        raise CLIError("Failed to start AGiXT locally.")

    LOCAL_PID_FILE.write_text(str(process.pid))

    requests_imported = False
    try:
        import requests

        requests_imported = True
    except ImportError:
        print("Unable to import requests library, skipping health check.")

    if requests_imported:
        time.sleep(6)
        try:
            response = requests.get("http://localhost:7437/health")
        except requests.RequestException:
            response = requests.Response()
            response.status_code = 500
        while response.status_code != 200:
            time.sleep(2)
            try:
                response = requests.get("http://localhost:7437/health")
            except requests.RequestException:
                response = requests.Response()
                response.status_code = 500
    print(f"AGiXT started successfully!")
    print(f"View logs at: {LOCAL_LOG_FILE}")
    cleanup_log_files()


def _stop_local(stop_ezlocalai_too: bool = True) -> None:
    # First, try to stop using the PID file
    pid = _read_pid(LOCAL_PID_FILE)
    stopped_by_pid = False

    if pid and _is_process_running(pid):
        print("Stopping AGiXT...")
        os.kill(pid, signal.SIGTERM)
        start_time = time.time()
        timeout = 10
        while _is_process_running(pid) and (time.time() - start_time) < timeout:
            time.sleep(0.5)

        if _is_process_running(pid):
            os.kill(pid, signal.SIGKILL)
        else:
            print(f"Stopped AGiXT local (PID {pid}).")
        stopped_by_pid = True

    # Also check for processes on port 7437
    pids_on_port = _find_processes_on_port(7437)
    if pids_on_port:
        for port_pid in pids_on_port:
            if port_pid != pid:  # Don't kill the same PID twice
                try:
                    os.kill(port_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Process already gone
                except PermissionError as e:
                    print(f"Permission denied killing process {port_pid}: {e}")

    elif not stopped_by_pid:
        print("No AGiXT local processes found running.")

    # Clean up PID file
    LOCAL_PID_FILE.unlink(missing_ok=True)

    # Stop ezLocalai if enabled and requested
    if stop_ezlocalai_too and _is_ezlocalai_enabled():
        try:
            stop_ezlocalai()
        except CLIError as e:
            print(f"Warning: {e}")


def _restart_local(env_updates: Optional[dict] = None) -> None:
    # Don't stop ezlocalai during restart - only stop AGiXT
    _stop_local(stop_ezlocalai_too=False)
    _start_local(env_updates=env_updates)


def _read_env_var_from_file(name: str) -> Optional[str]:
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.startswith(f"{name}="):
            continue
        value = stripped.split("=", 1)[1].strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')):
            value = value[1:-1]
        return value
    return None


def _determine_compose_file() -> Path:
    branch = os.environ.get("AGIXT_BRANCH")
    if branch is None:
        branch = _read_env_var_from_file("AGIXT_BRANCH")
    if branch and branch.lower() != "stable" and DOCKER_COMPOSE_FILE_DEV.exists():
        return DOCKER_COMPOSE_FILE_DEV
    return DOCKER_COMPOSE_FILE_STABLE


def _docker_compose(compose_file: Path, *args: str) -> None:
    _ensure_docker_requirements()
    if not compose_file.exists():
        raise CLIError(f"Compose file not found: {compose_file}")
    command = ["docker", "compose", "-f", str(compose_file), *args]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def _start_docker(env_updates: Optional[dict] = None) -> None:
    _ensure_docker_requirements()
    check_prerequisites()  # Check for docker installation

    # Set up environment
    env_vars = set_environment(env_updates=env_updates, mode="docker")

    # Determine which compose file to use
    dockerfile = "docker-compose.yml"
    if env_vars["AGIXT_BRANCH"] != "stable":
        dockerfile = "docker-compose-dev.yml"

    print("Starting AGiXT via Docker...")
    print("Press Ctrl+C to stop the containers and exit.")
    try:
        command = f"docker compose -f {dockerfile} up -d"
        subprocess.run(command, shell=True, cwd=REPO_ROOT, check=True)
        print("AGiXT Docker services started successfully.")
    except KeyboardInterrupt:
        print("\nStopping AGiXT containers...")
        subprocess.run(
            f"docker compose -f {dockerfile} stop",
            shell=True,
            cwd=REPO_ROOT,
            check=True,
        )
        print("AGiXT containers stopped.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")


def _stop_docker(stop_ezlocalai_too: bool = True) -> None:
    compose_file = _determine_compose_file()
    _docker_compose(compose_file, "stop")
    print(f"Stopped AGiXT Docker services ({compose_file.name}).")

    # Stop ezLocalai if enabled and requested
    if stop_ezlocalai_too and _is_ezlocalai_enabled():
        try:
            stop_ezlocalai()
        except CLIError as e:
            print(f"Warning: {e}")


def _restart_docker(env_updates: Optional[dict] = None) -> None:
    try:
        # Don't stop ezlocalai during restart - only stop AGiXT
        _stop_docker(stop_ezlocalai_too=False)
    except (CLIError, subprocess.CalledProcessError) as exc:
        print(f"Warning: failed to stop containers cleanly: {exc}")
    _start_docker(env_updates=env_updates)


def _logs_local(follow: bool = False) -> None:
    """Display logs from the most recent local log file."""
    log_files = sorted(
        STATE_DIR.glob("agixt-local-*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not log_files:
        print("No local log files found.")
        return

    newest_log = log_files[0]
    print(f"Showing logs from: {newest_log}")
    print("-" * 80)

    if follow:
        # Use tail -f to follow the log file
        try:
            subprocess.run(["tail", "-f", str(newest_log)], check=True)
        except KeyboardInterrupt:
            print("\nStopped following logs.")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise CLIError(f"Failed to follow logs: {exc}")
    else:
        # Just print the contents
        try:
            print(newest_log.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CLIError(f"Failed to read log file: {exc}")


def _logs_docker(follow: bool = False) -> None:
    """Display Docker compose logs."""
    compose_file = _determine_compose_file()
    args = ["logs"]
    if follow:
        args.append("-f")
    try:
        _docker_compose(compose_file, *args)
    except KeyboardInterrupt:
        if follow:
            print("\nStopped following logs.")
    except subprocess.CalledProcessError as exc:
        raise CLIError(f"Failed to retrieve Docker logs: {exc}")


def _logs_ezlocalai(follow: bool = False) -> None:
    """Display ezLocalai logs using the ezlocalai CLI."""
    try:
        cmd = ["ezlocalai", "logs"]
        if follow:
            cmd.append("-f")
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        raise CLIError(
            "ezlocalai CLI not found. Install it with: pip install ezlocalai"
        )
    except KeyboardInterrupt:
        if follow:
            print("\nStopped following logs.")
    except subprocess.CalledProcessError as exc:
        raise CLIError(f"Failed to retrieve ezLocalai logs: {exc}")


def _logs_web_local(follow: bool = False) -> None:
    """Display web local logs (npm run dev output)."""
    if not WEB_PID_FILE.exists():
        print("Web interface is not running locally.")
        print("No log file available for local web (logs go to stdout when running).")
        return

    print(
        "Web interface running locally - logs are in the terminal where it was started."
    )
    print("To see live logs, the web interface must be running in a visible terminal.")
    print("Tip: Run 'agixt start --web --local' in a dedicated terminal to see logs.")


def _logs_web_docker(follow: bool = False) -> None:
    """Display web Docker logs."""
    compose_file = _determine_compose_file()
    args = ["logs", "agixt-interactive"]
    if follow:
        args.append("-f")

    try:
        _docker_compose(compose_file, *args)
    except KeyboardInterrupt:
        if follow:
            print("\nStopped following logs.")
    except subprocess.CalledProcessError as exc:
        raise CLIError(f"Failed to retrieve web Docker logs: {exc}")


def _show_env_help() -> None:
    """Display all available environment variables with their current values."""
    print("Available Environment Variables:")
    print("=" * 80)
    print("\nUsage: agixt env KEY=VALUE [KEY2=VALUE2 ...]")
    print("       agixt env help  (to show this message)\n")

    load_dotenv()
    env_vars = get_default_env_vars()

    # Group variables by category
    categories = {
        "Core Configuration": [
            "AGIXT_API_KEY",
            "AGIXT_URI",
            "AGIXT_PORT",
            "AGIXT_INTERACTIVE_PORT",
            "AGIXT_AGENT",
            "AGIXT_BRANCH",
            "AGIXT_RUN_TYPE",
            "AGIXT_AUTO_UPDATE",
            "AGIXT_HEALTH_URL",
        ],
        "Application Settings": [
            "APP_NAME",
            "APP_DESCRIPTION",
            "APP_URI",
            "APP_PORT",
            "ALLOW_EMAIL_SIGN_IN",
            "ALLOWED_DOMAINS",
            "AGIXT_FILE_UPLOAD_ENABLED",
            "AGIXT_VOICE_INPUT_ENABLED",
            "AGIXT_RLHF",
            "AGIXT_FOOTER_MESSAGE",
            "AGIXT_SERVER",
            "AGIXT_CONVERSATION_MODE",
            "AGIXT_SHOW_OVERRIDE_SWITCHES",
            "AGIXT_ALLOW_MESSAGE_EDITING",
            "AGIXT_ALLOW_MESSAGE_DELETION",
        ],
        "Database Configuration": [
            "DATABASE_TYPE",
            "DATABASE_NAME",
            "DATABASE_USER",
            "DATABASE_PASSWORD",
            "DATABASE_HOST",
            "DATABASE_PORT",
            "DEFAULT_USER",
            "USING_JWT",
        ],
        "Server Configuration": [
            "LOG_LEVEL",
            "LOG_FORMAT",
            "LOG_VERBOSITY_SERVER",
            "UVICORN_WORKERS",
            "WORKING_DIRECTORY",
            "TZ",
            "REGISTRATION_DISABLED",
            "CREATE_AGENT_ON_REGISTER",
            "CREATE_AGIXT_AGENT",
            "GRAPHIQL",
            "EMAIL_SERVER",
        ],
        "Health Check Configuration": [
            "HEALTH_CHECK_INTERVAL",
            "HEALTH_CHECK_TIMEOUT",
            "HEALTH_CHECK_MAX_FAILURES",
            "RESTART_COOLDOWN",
            "INITIAL_STARTUP_DELAY",
        ],
        "Storage Configuration": [
            "STORAGE_BACKEND",
            "STORAGE_CONTAINER",
            "B2_KEY_ID",
            "B2_APPLICATION_KEY",
            "B2_REGION",
            "S3_BUCKET",
            "S3_ENDPOINT",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_STORAGE_REGION",
            "AZURE_STORAGE_ACCOUNT_NAME",
            "AZURE_STORAGE_KEY",
        ],
        "AI Model Configuration": [
            "EZLOCALAI_URI",
            "EZLOCALAI_VOICE",
            "EZLOCALAI_MAX_TOKENS",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_MAX_TOKENS",
            "DEEPSEEK_MODEL",
            "DEEPSEEK_MAX_TOKENS",
            "AZURE_MODEL",
            "AZURE_MAX_TOKENS",
            "GOOGLE_MODEL",
            "GOOGLE_MAX_TOKENS",
            "OPENAI_MODEL",
            "OPENAI_MAX_TOKENS",
            "OPENAI_BASE_URI",
            "XAI_MODEL",
            "XAI_MAX_TOKENS",
            "DEFAULT_MODEL",
            "VISION_MODEL",
            "WHISPER_MODEL",
            "WITH_EZLOCALAI",
        ],
        "ezLocalai Configuration": [
            "EZLOCALAI_URL",
            "MAIN_GPU",
            "NGROK_TOKEN",
            "IMG_MODEL",
            "MAX_CONCURRENT_REQUESTS",
            "MAX_QUEUE_SIZE",
            "REQUEST_TIMEOUT",
        ],
        "API Keys": [
            "AZURE_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "EZLOCALAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "XAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
        ],
        "Extensions Configuration": [
            "EXTENSIONS_HUB",
            "EXTENSIONS_HUB_TOKEN",
            "DISABLED_EXTENSIONS",
            "DISABLED_PROVIDERS",
        ],
        "Payment Configuration": [
            "PAYMENT_WALLET_ADDRESS",
            "PAYMENT_SOLANA_RPC_URL",
            "MONTHLY_PRICE_PER_USER_USD",
        ],
        "OAuth Configuration": [
            "ALEXA_CLIENT_ID",
            "ALEXA_CLIENT_SECRET",
            "AWS_CLIENT_ID",
            "AWS_CLIENT_SECRET",
            "AWS_REGION",
            "AWS_USER_POOL_ID",
            "DISCORD_CLIENT_ID",
            "DISCORD_CLIENT_SECRET",
            "FITBIT_CLIENT_ID",
            "FITBIT_CLIENT_SECRET",
            "GARMIN_CLIENT_ID",
            "GARMIN_CLIENT_SECRET",
            "GITHUB_CLIENT_ID",
            "GITHUB_CLIENT_SECRET",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "META_APP_ID",
            "META_APP_SECRET",
            "META_BUSINESS_ID",
            "MICROSOFT_CLIENT_ID",
            "MICROSOFT_CLIENT_SECRET",
            "TESLA_CLIENT_ID",
            "TESLA_CLIENT_SECRET",
            "WALMART_CLIENT_ID",
            "WALMART_CLIENT_SECRET",
            "WALMART_MARKETPLACE_ID",
            "X_CLIENT_ID",
            "X_CLIENT_SECRET",
        ],
        "Agent Configuration": [
            "SEED_DATA",
            "AGENT_NAME",
            "AGENT_PERSONA",
            "TRAINING_URLS",
            "ENABLED_COMMANDS",
            "ROTATION_EXCLUSIONS",
        ],
    }

    for category, keys in categories.items():
        print(f"\n{category}:")
        print("-" * 80)
        for key in keys:
            if key in env_vars:
                current_value = os.getenv(key, env_vars[key])
                # Mask sensitive values
                if any(
                    secret in key.lower()
                    for secret in ["key", "secret", "password", "token"]
                ):
                    if current_value and current_value != "":
                        masked = (
                            current_value[:4] + "..." + current_value[-4:]
                            if len(current_value) > 8
                            else "***"
                        )
                        print(f"  {key:40} = {masked}")
                    else:
                        print(f"  {key:40} = (not set)")
                else:
                    print(f"  {key:40} = {current_value}")

    print("\n" + "=" * 80)
    print("\nExamples:")
    print('  agixt env OPENAI_API_KEY="sk-xxxxx"')
    print('  agixt env LOG_LEVEL="DEBUG" UVICORN_WORKERS="20"')
    print('  agixt env AGIXT_BRANCH="dev" AGIXT_AUTO_UPDATE="true"')
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AGiXT helper commands")
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "logs", "env"],
        help="Action to perform",
    )
    parser.add_argument(
        "env_vars",
        nargs="*",
        help="For env command: KEY=VALUE pairs or 'help' to list all variables",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Operate on the local Python process (saved to AGIXT_RUN_TYPE for future commands)",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Operate on the Docker stack (saved to AGIXT_RUN_TYPE for future commands; default when no mode is specified)",
    )
    parser.add_argument(
        "--ezlocalai",
        action="store_true",
        help="Operate on ezLocalai only (start/stop/restart)",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Operate on web interface only (start/stop/restart)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Operate on all services (AGiXT + ezLocalai + web)",
    )
    parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow log output (tail -f for local, docker compose logs -f for docker)",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        # Handle env command separately
        if args.action == "env":
            # Check if help was requested
            if args.env_vars and args.env_vars[0].lower() == "help":
                _show_env_help()
                return 0

            # Parse KEY=VALUE pairs
            if not args.env_vars:
                print("No environment variables specified.")
                print("Usage: agixt env KEY=VALUE [KEY2=VALUE2 ...]")
                print("       agixt env help  (to show all available variables)")
                print("\nExamples:")
                print('  agixt env OPENAI_API_KEY="sk-xxxxx"')
                print('  agixt env LOG_LEVEL="DEBUG" UVICORN_WORKERS="20"')
                return 1

            env_updates = {}
            for pair in args.env_vars:
                if "=" not in pair:
                    print(f"Error: Invalid format '{pair}'. Use KEY=VALUE format.")
                    print('Example: agixt env OPENAI_API_KEY="sk-xxxxx"')
                    return 1

                key, value = pair.split("=", 1)
                key = key.strip().upper()
                value = value.strip().strip('"').strip("'")  # Remove quotes if present

                # Validate key exists in default env vars
                default_vars = get_default_env_vars()
                if key not in default_vars:
                    print(f"Warning: '{key}' is not a recognized environment variable.")
                    print(f"Use 'agixt env help' to see all available variables.")
                    response = prompt_user("Set it anyway? (y/n)", "n")
                    if response.lower() not in ["y", "yes"]:
                        continue

                env_updates[key] = value

            if not env_updates:
                print("No valid environment variables to update.")
                return 1

            # Determine mode for set_environment based on AGIXT_RUN_TYPE
            mode = "docker"  # default
            if "AGIXT_RUN_TYPE" in env_updates:
                mode = env_updates["AGIXT_RUN_TYPE"].lower()
            else:
                # Check existing .env for AGIXT_RUN_TYPE
                load_dotenv(ENV_FILE)
                run_type = os.getenv("AGIXT_RUN_TYPE", "docker").lower()
                mode = run_type

            print("Updating environment variables...")
            set_environment(env_updates=env_updates, mode=mode)
            print("Environment variables updated successfully!")
            print("\nUpdated variables:")
            for key, value in env_updates.items():
                # Mask sensitive values
                if any(
                    secret in key.lower()
                    for secret in ["key", "secret", "password", "token"]
                ):
                    masked_value = (
                        value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
                    )
                    print(f"  {key}={masked_value}")
                else:
                    print(f"  {key}={value}")
            return 0

        # Handle mode conflicts
        if args.local and args.docker:
            parser.error("Choose either --local or --docker, not both.")

        # Determine run type (local or docker)
        run_local = False
        env_updates = {}

        if args.local:
            # --local flag explicitly set
            run_local = True
            env_updates["AGIXT_RUN_TYPE"] = "local"
        elif args.docker:
            # --docker flag explicitly set
            run_local = False
            env_updates["AGIXT_RUN_TYPE"] = "docker"
        else:
            # No flag set, check environment variable
            load_dotenv(ENV_FILE)
            run_type = os.getenv("AGIXT_RUN_TYPE", "docker").lower()
            run_local = run_type == "local"

        # Count service flags
        service_flags = sum([args.ezlocalai, args.web, args.all])
        if service_flags > 1:
            parser.error("Choose only one of --ezlocalai, --web, or --all.")

        # Logs command restrictions
        if args.all and args.action == "logs":
            parser.error(
                "Logs command not supported for --all flag. Use individual flags: --ezlocalai or --web"
            )

        # Handle ezlocalai-only operations
        if args.ezlocalai:
            if args.action == "start":
                start_ezlocalai()
            elif args.action == "stop":
                stop_ezlocalai()
            elif args.action == "restart":
                restart_ezlocalai()
            elif args.action == "logs":
                _logs_ezlocalai(follow=args.follow)
            return 0

        # Handle web-only operations
        if args.web:
            if run_local:
                if args.action == "start":
                    _start_web_local()
                elif args.action == "stop":
                    _stop_web_local()
                elif args.action == "restart":
                    _restart_web_local()
                elif args.action == "logs":
                    _logs_web_local(follow=args.follow)
            else:
                if args.action == "start":
                    _start_web_docker()
                elif args.action == "stop":
                    _stop_web_docker()
                elif args.action == "restart":
                    _restart_web_docker()
                elif args.action == "logs":
                    _logs_web_docker(follow=args.follow)
            return 0

        # Handle --all flag (all services)
        if args.all:
            if args.action == "start":
                _start_all(
                    local=run_local, env_updates=env_updates if env_updates else None
                )
            elif args.action == "stop":
                _stop_all(local=run_local)
            elif args.action == "restart":
                _restart_all(
                    local=run_local, env_updates=env_updates if env_updates else None
                )
            return 0

        # Convert args to a dictionary, filtering out None values and action/mode flags
        arg_dict = {
            k: v
            for k, v in vars(args).items()
            if v is not None
            and k
            not in [
                "action",
                "local",
                "docker",
                "follow",
                "ezlocalai",
                "web",
                "all",
                "env_vars",
            ]
        }
        # Convert hyphenated arg names back to underscore format and merge with existing env_updates
        additional_updates = {
            k.upper().replace("-", "_"): v for k, v in arg_dict.items()
        }
        env_updates.update(additional_updates)

        # Check if .env file exists and if AGIXT_AUTO_UPDATE is not set via command line
        env_file_path = REPO_ROOT / ".env"
        if (
            not env_file_path.exists()
            and "AGIXT_AUTO_UPDATE" not in env_updates
            and args.action in ["start", "restart"]
        ):
            auto_update = prompt_user(
                "Would you like AGiXT to auto update when this script is run in the future? (Y for yes, N for no)",
                "y",
            )
            if auto_update.lower() in ["y", "yes"]:
                auto_update = "true"
            else:
                auto_update = "false"
            env_updates["AGIXT_AUTO_UPDATE"] = auto_update

        # Handle regular AGiXT operations
        if run_local:
            if args.action == "start":
                _start_local(env_updates=env_updates if env_updates else None)
            elif args.action == "stop":
                _stop_local()
            elif args.action == "restart":
                _restart_local(env_updates=env_updates if env_updates else None)
            elif args.action == "logs":
                _logs_local(follow=args.follow)
        else:
            if args.action == "start":
                _start_docker(env_updates=env_updates if env_updates else None)
            elif args.action == "stop":
                _stop_docker()
            elif args.action == "restart":
                _restart_docker(env_updates=env_updates if env_updates else None)
            elif args.action == "logs":
                _logs_docker(follow=args.follow)
    except CLIError as exc:
        parser.error(str(exc))
    except subprocess.CalledProcessError as exc:
        parser.error(f"Command failed with exit code {exc.returncode}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
