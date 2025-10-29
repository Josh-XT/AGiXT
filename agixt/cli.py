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

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_SCRIPT = Path(__file__).resolve().parent / "run-local.py"
START_SCRIPT = REPO_ROOT / "start.py"
DOCKER_COMPOSE_FILE_STABLE = REPO_ROOT / "docker-compose.yml"
DOCKER_COMPOSE_FILE_DEV = REPO_ROOT / "docker-compose-dev.yml"
ENV_FILE = REPO_ROOT / ".env"
STATE_DIR = Path.home() / ".agixt"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_PID_FILE = STATE_DIR / "agixt-local.pid"
LOCAL_LOG_FILE = STATE_DIR / f"agixt-local-{int(time.time())}.log"


class CLIError(RuntimeError):
    """Raised for recoverable CLI errors."""


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
    if not START_SCRIPT.exists():
        raise CLIError(
            f"start.py not found at {START_SCRIPT}. "
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


def _start_local() -> None:
    _ensure_local_requirements()

    existing_pid = _read_pid(LOCAL_PID_FILE)
    if existing_pid and _is_process_running(existing_pid):
        raise CLIError(f"AGiXT local already running with PID {existing_pid}.")
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


def _stop_local() -> None:
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


def _restart_local() -> None:
    _stop_local()
    _start_local()


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


def _start_docker(extra_args: Optional[list[str]] = None) -> None:
    _ensure_docker_requirements()
    command = [sys.executable, str(START_SCRIPT)]
    if extra_args:
        command.extend(extra_args)
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    print("Started AGiXT via Docker using start.py.")


def _stop_docker() -> None:
    compose_file = _determine_compose_file()
    _docker_compose(compose_file, "stop")
    print(f"Stopped AGiXT Docker services ({compose_file.name}).")


def _restart_docker() -> None:
    try:
        _stop_docker()
    except (CLIError, subprocess.CalledProcessError) as exc:
        print(f"Warning: failed to stop containers cleanly: {exc}")
    _start_docker()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AGiXT helper commands")
    parser.add_argument(
        "action", choices=["start", "stop", "restart"], help="Action to perform"
    )
    parser.add_argument(
        "--local", action="store_true", help="Operate on the local Python process"
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Operate on the Docker stack (default when no mode is specified)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.local and args.docker:
            parser.error("Choose either --local or --docker, not both.")

        if args.local:
            if args.action == "start":
                _start_local()
            elif args.action == "stop":
                _stop_local()
            elif args.action == "restart":
                _restart_local()
        else:
            if args.action == "start":
                _start_docker()
            elif args.action == "stop":
                _stop_docker()
            elif args.action == "restart":
                _restart_docker()
    except CLIError as exc:
        parser.error(str(exc))
    except subprocess.CalledProcessError as exc:
        parser.error(f"Command failed with exit code {exc.returncode}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
