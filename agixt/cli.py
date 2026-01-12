#!/usr/bin/env python3
"""Command line helper for common AGiXT workflows.

This CLI supports two modes:
1. Server management (start/stop/restart/logs) - Requires full dependencies when using --local
2. Client mode (login/prompt) - Lightweight, only requires requests package

When using `agixt login` and `agixt prompt`, no heavy dependencies are needed.
These commands communicate with a remote AGiXT server via HTTP/WebSocket.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request
import uuid
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
ENV_FILE = REPO_ROOT / ".env"
WEB_DIR = XTSYS_ROOT / "web"
STATE_DIR = Path.home() / ".agixt"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_PID_FILE = STATE_DIR / "agixt-local.pid"
LOCAL_LOG_FILE = STATE_DIR / f"agixt-local-{int(time.time())}.log"
WEB_PID_FILE = STATE_DIR / "agixt-web.pid"
CREDENTIALS_FILE = STATE_DIR / "credentials.json"


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


# ========== Credential Management ==========


def load_credentials() -> dict:
    """Load saved credentials from ~/.agixt/credentials.json"""
    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_credentials(credentials: dict) -> None:
    """Save credentials to ~/.agixt/credentials.json"""
    CREDENTIALS_FILE.write_text(json.dumps(credentials, indent=2), encoding="utf-8")
    # Restrict permissions to owner only
    try:
        CREDENTIALS_FILE.chmod(0o600)
    except OSError:
        pass


def get_server_url() -> str:
    """Get the AGiXT server URL from credentials or default."""
    creds = load_credentials()
    return creds.get("server", "http://localhost:7437")


def get_auth_token() -> Optional[str]:
    """Get the JWT token from credentials."""
    creds = load_credentials()
    return creds.get("token")


def get_default_agent() -> str:
    """Get the default agent name from credentials or default."""
    creds = load_credentials()
    return creds.get("agent", "XT")


def get_default_conversation() -> str:
    """Get the default conversation ID from credentials or default."""
    creds = load_credentials()
    return creds.get("conversation", "-")


# ========== Login Command ==========


def _login(server: str, email: str, otp: str) -> int:
    """
    Login to an AGiXT server with email and OTP.

    This uses the AGiXT login endpoint to authenticate and stores
    the JWT token for future use.
    """
    # Normalize server URL
    if not server.startswith(("http://", "https://")):
        server = f"http://{server}"
    server = server.rstrip("/")

    print(f"🔐 Logging in to {server}...")

    try:
        # Make login request
        login_data = json.dumps({"email": email, "token": otp}).encode("utf-8")
        req = urllib.request.Request(
            f"{server}/v1/login",
            data=login_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))

        # Extract token from response
        if "detail" in response_data:
            detail = response_data["detail"]
            if "?token=" in detail:
                token = detail.split("token=")[1]

                # Save credentials
                creds = load_credentials()
                creds["server"] = server
                creds["token"] = token
                creds["email"] = email
                save_credentials(creds)

                print(f"✅ Successfully logged in as {email}")
                print(f"   Server: {server}")
                print(f"   Credentials saved to: {CREDENTIALS_FILE}")
                return 0
            else:
                print(f"ℹ️  Server response: {detail}")
                return 1
        else:
            print(f"❌ Unexpected response: {response_data}")
            return 1

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        if error_body:
            try:
                error_json = json.loads(error_body)
                print(f"   {error_json.get('detail', error_body)}")
            except json.JSONDecodeError:
                print(f"   {error_body}")
        return 1
    except urllib.error.URLError as e:
        print(f"❌ Connection error: {e.reason}")
        print(f"   Could not connect to {server}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


# ========== Register Command ==========


def _register(server: str, email: str, first_name: str, last_name: str) -> int:
    """
    Register a new user on an AGiXT server.

    This creates a new user account and automatically logs in using the
    generated TOTP secret. The magic link URL is also printed for web login.
    """
    # Normalize server URL
    if not server.startswith(("http://", "https://")):
        server = f"http://{server}"
    server = server.rstrip("/")

    print(f"📝 Registering new user on {server}...")

    try:
        # Make registration request
        register_data = json.dumps(
            {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{server}/v1/user",
            data=register_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))

        # Check for otp_uri in response (successful registration)
        if "otp_uri" in response_data:
            otp_uri = response_data["otp_uri"]

            # Extract the TOTP secret from the otp_uri
            # Format: otpauth://totp/AGiXT:email?secret=XXXXX&issuer=AGiXT
            if "secret=" in otp_uri:
                mfa_secret = otp_uri.split("secret=")[1].split("&")[0]

                print(f"✅ User registered successfully!")
                print(f"   Email: {email}")
                print(f"   Name: {first_name} {last_name}")
                print()

                # Generate OTP and login
                try:
                    import pyotp

                    totp = pyotp.TOTP(mfa_secret)
                    otp = totp.now()

                    print("🔐 Logging in with generated OTP...")
                    return _login(server, email, otp)

                except ImportError:
                    # pyotp not available, provide manual instructions
                    print("⚠️  pyotp not installed - cannot auto-login")
                    print()
                    print("📱 To set up 2FA, scan this QR code or add manually:")
                    print(f"   {otp_uri}")
                    print()
                    print("Then login with:")
                    print(
                        f"   agixt login --server {server} --email {email} --otp <YOUR_OTP>"
                    )

                    # Save server to credentials for convenience
                    creds = load_credentials()
                    creds["server"] = server
                    creds["email"] = email
                    save_credentials(creds)

                    return 0
            else:
                print(f"⚠️  Unexpected otp_uri format: {otp_uri}")
                return 1

        # Check for magic link response (alternative registration flow)
        elif "detail" in response_data:
            detail = response_data["detail"]
            print(f"✅ Registration initiated!")
            print(f"   {detail}")

            # If there's a magic link, extract and show it
            if "?token=" in detail:
                print()
                print("🔗 Magic link for web login:")
                print(f"   {detail}")

            return 0
        else:
            print(f"❌ Unexpected response: {response_data}")
            return 1

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        if error_body:
            try:
                error_json = json.loads(error_body)
                detail = error_json.get("detail", error_body)
                print(f"   {detail}")

                # If user already exists, suggest login instead
                if "already" in str(detail).lower() or "exists" in str(detail).lower():
                    print()
                    print("💡 User may already exist. Try logging in:")
                    print(
                        f"   agixt login --server {server} --email {email} --otp <YOUR_OTP>"
                    )
            except json.JSONDecodeError:
                print(f"   {error_body}")
        return 1
    except urllib.error.URLError as e:
        print(f"❌ Connection error: {e.reason}")
        print(f"   Could not connect to {server}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


# ========== Conversations Command ==========


def _conversations() -> int:
    """
    List and select conversations interactively.

    Fetches conversations from the server and allows the user to select one
    to use as the default for future prompts.
    """
    server_url = get_server_url()
    token = get_auth_token()

    if not token:
        print("❌ Not logged in. Run 'agixt login' first.")
        return 1

    print(f"📋 Fetching conversations from {server_url}...")

    try:
        # Make request to get conversations
        req = urllib.request.Request(
            f"{server_url}/v1/conversations",
            headers={
                "Content-Type": "application/json",
                "Authorization": token,
            },
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))

        conversations = response_data.get("conversations", {})

        if not conversations:
            print("\n📭 No conversations found.")
            print('   Start a new conversation with: agixt prompt "Hello!"')
            return 0

        # Get current conversation from credentials
        creds = load_credentials()
        current_conv = creds.get("conversation", "-")

        # Build list of conversations sorted by updated_at (most recent first)
        conv_list = []
        for conv_id, conv_data in conversations.items():
            conv_list.append(
                {
                    "id": conv_id,
                    "name": conv_data.get("name", "Unnamed"),
                    "created_at": conv_data.get("created_at", ""),
                    "updated_at": conv_data.get("updated_at", ""),
                }
            )

        # Sort by updated_at descending (most recent first)
        conv_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        # Display conversations
        print()
        print("=" * 60)
        print("  Select a conversation (or Ctrl+C to cancel)")
        print("=" * 60)
        print()

        # Option 0 is always "New conversation"
        new_marker = "→" if (not current_conv or current_conv == "-") else " "
        print(f"  [0]{new_marker} ✨ New conversation")
        print(f"       Start fresh with a new conversation")
        print()

        # Show up to 20 conversations
        max_display = 20
        for i, conv in enumerate(conv_list[:max_display], 1):
            name = conv["name"]
            conv_id = conv["id"]
            updated = conv.get("updated_at", "")[:10]  # Just the date part

            # Truncate long names
            if len(name) > 40:
                name = name[:37] + "..."

            # Mark if this is the current conversation
            is_current = conv_id == current_conv
            marker = "→" if is_current else " "
            current_label = " 📌" if is_current else ""

            print(f"  [{i}]{marker} {name}{current_label}")
            print(f"       ID: {conv_id[:8]}...  Updated: {updated}")

        if len(conv_list) > max_display:
            print(f"\n  ... and {len(conv_list) - max_display} more conversations")

        print()
        print("-" * 60)

        # Get user selection
        try:
            selection = input("Enter number (or Ctrl+C to cancel): ").strip()

            if not selection:
                print("❌ No selection made.")
                return 1

            try:
                sel_num = int(selection)
            except ValueError:
                print(f"❌ Invalid selection: {selection}")
                return 1

            if sel_num == 0:
                # Set to new conversation
                creds["conversation"] = "-"
                save_credentials(creds)
                print("✅ Set to start new conversations.")
                return 0

            if sel_num < 1 or sel_num > min(len(conv_list), max_display):
                print(f"❌ Invalid selection: {sel_num}")
                return 1

            # Select the conversation
            selected = conv_list[sel_num - 1]
            creds["conversation"] = selected["id"]
            save_credentials(creds)

            print(f"✅ Selected conversation: {selected['name']}")
            print(f"   ID: {selected['id']}")
            return 0

        except KeyboardInterrupt:
            print("\n⚠️  Cancelled.")
            return 0

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        if error_body:
            try:
                error_json = json.loads(error_body)
                print(f"   {error_json.get('detail', error_body)}")
            except json.JSONDecodeError:
                print(f"   {error_body}")
        return 1
    except urllib.error.URLError as e:
        print(f"❌ Connection error: {e.reason}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def _conversation_set(conversation_id: str) -> int:
    """
    Set the current conversation by ID.

    Use "-" to start a new conversation.
    """
    creds = load_credentials()

    if conversation_id == "-":
        creds["conversation"] = "-"
        save_credentials(creds)
        print("✅ Set to start new conversations.")
        return 0

    # Validate the conversation exists (optional - just set it)
    creds["conversation"] = conversation_id
    save_credentials(creds)

    print(f"✅ Conversation set to: {conversation_id}")
    return 0


# ========== Prompt Command ==========


def encode_image_to_base64(image_path: str) -> str:
    """Encode a local image file to base64."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """Get the MIME type based on file extension."""
    ext = Path(image_path).suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mime_types.get(ext, "image/jpeg")


def is_url(path: str) -> bool:
    """Check if the path is a URL."""
    return path.startswith("http://") or path.startswith("https://")


class ActivityTracker:
    """Thread-safe activity tracker for WebSocket streaming.

    Handles two types of activities:
    1. Streaming activities (thinking, reflection) - accumulated until complete
    2. Status activities (info, error, activity, subactivity) - shown immediately
    """

    def __init__(self):
        self._activities = {}  # Current activities for display
        self._streaming_buffer = (
            {}
        )  # Buffer for streaming content (thinking, reflection)
        self._lock = threading.Lock()
        self._last_activity_line_count = 0
        self._completed_activities = (
            []
        )  # List of (type, content) for completed activities

    def update(self, activity_type: str, content: str, complete: bool = False):
        """Update an activity's content.

        For streaming activities (thinking, reflection):
        - Accumulate content until complete=True
        - Only add to completed list when done

        For status activities:
        - Show immediately (replace previous of same type)
        """
        with self._lock:
            # Streaming activities that accumulate (thinking/reflection)
            if activity_type in ("thinking", "reflection"):
                if activity_type not in self._streaming_buffer:
                    self._streaming_buffer[activity_type] = ""

                # Append new content
                self._streaming_buffer[activity_type] += content

                if complete:
                    # Move completed streaming activity to completed list
                    full_content = self._streaming_buffer[activity_type].strip()
                    if full_content:
                        self._completed_activities.append((activity_type, full_content))
                    # Clear the buffer
                    del self._streaming_buffer[activity_type]
                    if activity_type in self._activities:
                        del self._activities[activity_type]
                else:
                    # Update current display with accumulated content
                    self._activities[activity_type] = self._streaming_buffer[
                        activity_type
                    ]
            else:
                # Non-streaming activities - show immediately or remove
                if complete:
                    if activity_type in self._activities:
                        del self._activities[activity_type]
                else:
                    self._activities[activity_type] = content

    def get_completed(self) -> list:
        """Get and clear the list of completed activities."""
        with self._lock:
            completed = self._completed_activities.copy()
            self._completed_activities.clear()
            return completed

    def get_current_streaming(self) -> dict:
        """Get current streaming activities (in-progress thinking/reflection)."""
        with self._lock:
            return {
                k: v
                for k, v in self._activities.items()
                if k in ("thinking", "reflection")
            }

    def get_display(self) -> str:
        """Get formatted display string for all activities."""
        with self._lock:
            if not self._activities:
                return ""
            lines = []

            # Activity type icons and labels
            icon_map = {
                "thinking": "🤔",
                "reflection": "🔄",
                "activity": "⚙️",
                "subactivity": "└─",
                "info": "ℹ️",
                "error": "❌",
            }

            for activity_type, content in self._activities.items():
                # Format activity type nicely
                icon = icon_map.get(activity_type, "⚙️")
                label = activity_type.replace("_", " ").title()
                # Truncate long content for display
                display_content = content
                if len(display_content) > 80:
                    display_content = display_content[:77] + "..."
                lines.append(f"{icon} {label}: {display_content}")
            return "\n".join(lines)

    def clear(self):
        """Clear all activities."""
        with self._lock:
            self._activities.clear()
            self._streaming_buffer.clear()
            self._completed_activities.clear()


class TerminalSession:
    """Manages a single terminal session for remote command execution."""

    # Default timeout before returning partial output (30 seconds)
    DEFAULT_PARTIAL_TIMEOUT = 30

    def __init__(self, session_id: str, working_directory: Optional[str] = None):
        self.session_id = session_id
        self.working_directory = working_directory or os.getcwd()
        self.env = os.environ.copy()
        self.history = []
        # Track running processes by command for get_output later
        self._running_processes: dict = (
            {}
        )  # {command_id: (process, output_buffer, start_time)}

    def execute(
        self,
        command: str,
        timeout: int = 300,
        is_background: bool = False,
        partial_timeout: int = None,
    ) -> dict:
        """
        Execute a command in this terminal session.

        Args:
            command: The shell command to execute
            timeout: Maximum seconds to wait before killing process (default: 300)
            is_background: If True, run command in background and return immediately
            partial_timeout: Seconds to wait before returning partial output (default: 30).
                           If the command is still running after this time, return what
                           output we have so far. The process continues in background.
                           Set to 0 to disable partial timeout.

        Returns:
            dict with keys: exit_code, stdout, stderr, working_directory, execution_time_seconds
            If partial timeout triggered, also includes:
                - timed_out: True
                - still_running: True if process is still running
                - terminal_id: ID to use with get_output() to check later
        """
        start_time = time.time()

        # Use default partial timeout if not specified
        if partial_timeout is None:
            partial_timeout = self.DEFAULT_PARTIAL_TIMEOUT

        # Handle cd commands specially to update working directory
        if command.strip().startswith("cd "):
            new_dir = command.strip()[3:].strip()
            if new_dir.startswith("~"):
                new_dir = os.path.expanduser(new_dir)
            if not os.path.isabs(new_dir):
                new_dir = os.path.normpath(
                    os.path.join(self.working_directory, new_dir)
                )

            if os.path.isdir(new_dir):
                self.working_directory = new_dir
                return {
                    "exit_code": 0,
                    "stdout": f"Changed directory to {self.working_directory}",
                    "stderr": "",
                    "working_directory": self.working_directory,
                    "execution_time_seconds": time.time() - start_time,
                }
            else:
                return {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": f"cd: no such file or directory: {new_dir}",
                    "working_directory": self.working_directory,
                    "execution_time_seconds": time.time() - start_time,
                }

        try:
            # Determine shell based on platform
            if platform.system() == "Windows":
                shell_cmd = ["cmd", "/c", command]
            else:
                shell_cmd = ["/bin/bash", "-c", command]

            if is_background:
                # Start background process
                process = subprocess.Popen(
                    shell_cmd,
                    cwd=self.working_directory,
                    env=self.env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
                # Track for later retrieval
                command_id = str(uuid.uuid4())[:8]
                self._running_processes[command_id] = {
                    "process": process,
                    "command": command,
                    "start_time": start_time,
                    "stdout_buffer": [],
                    "stderr_buffer": [],
                }
                return {
                    "exit_code": 0,
                    "stdout": f"Background process started with PID {process.pid}",
                    "stderr": "",
                    "working_directory": self.working_directory,
                    "execution_time_seconds": time.time() - start_time,
                    "pid": process.pid,
                    "terminal_id": self.session_id,
                    "command_id": command_id,
                }
            else:
                # Start process with non-blocking I/O so we can collect partial output
                process = subprocess.Popen(
                    shell_cmd,
                    cwd=self.working_directory,
                    env=self.env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                stdout_chunks = []
                stderr_chunks = []

                # Use select for non-blocking reads (or threads on Windows)
                import select

                def read_output_with_timeout(
                    proc, partial_timeout_secs, hard_timeout_secs
                ):
                    """Read output with partial timeout - return what we have after partial_timeout."""
                    nonlocal stdout_chunks, stderr_chunks

                    partial_deadline = (
                        time.time() + partial_timeout_secs
                        if partial_timeout_secs > 0
                        else None
                    )
                    hard_deadline = time.time() + hard_timeout_secs

                    while True:
                        # Check if process has finished
                        exit_code = proc.poll()
                        if exit_code is not None:
                            # Process finished - read any remaining output
                            remaining_stdout = proc.stdout.read()
                            remaining_stderr = proc.stderr.read()
                            if remaining_stdout:
                                stdout_chunks.append(remaining_stdout)
                            if remaining_stderr:
                                stderr_chunks.append(remaining_stderr)
                            return {
                                "completed": True,
                                "exit_code": exit_code,
                                "timed_out": False,
                            }

                        # Check timeouts
                        now = time.time()
                        if now >= hard_deadline:
                            # Hard timeout - kill process
                            try:
                                proc.kill()
                            except Exception:
                                pass
                            return {
                                "completed": False,
                                "exit_code": -1,
                                "timed_out": True,
                                "killed": True,
                            }

                        if partial_deadline and now >= partial_deadline:
                            # Partial timeout - return what we have, process continues
                            return {
                                "completed": False,
                                "exit_code": None,
                                "timed_out": True,
                                "still_running": True,
                            }

                        # Try to read available output (non-blocking)
                        try:
                            # Use select on Unix for non-blocking reads
                            if hasattr(select, "select"):
                                readable, _, _ = select.select(
                                    [proc.stdout, proc.stderr], [], [], 0.1
                                )
                                for stream in readable:
                                    chunk = stream.read(4096)
                                    if chunk:
                                        if stream == proc.stdout:
                                            stdout_chunks.append(chunk)
                                        else:
                                            stderr_chunks.append(chunk)
                            else:
                                # Windows fallback - just wait briefly
                                time.sleep(0.1)
                        except Exception:
                            time.sleep(0.1)

                result = read_output_with_timeout(process, partial_timeout, timeout)

                stdout_text = "".join(stdout_chunks)
                stderr_text = "".join(stderr_chunks)

                if result["completed"]:
                    # Process finished normally
                    self.history.append(
                        {
                            "command": command,
                            "exit_code": result["exit_code"],
                            "timestamp": time.time(),
                        }
                    )
                    return {
                        "exit_code": result["exit_code"],
                        "stdout": stdout_text,
                        "stderr": stderr_text,
                        "working_directory": self.working_directory,
                        "execution_time_seconds": time.time() - start_time,
                    }
                elif result.get("still_running"):
                    # Partial timeout - process still running
                    # Track for later retrieval
                    command_id = str(uuid.uuid4())[:8]
                    self._running_processes[command_id] = {
                        "process": process,
                        "command": command,
                        "start_time": start_time,
                        "stdout_buffer": stdout_chunks,
                        "stderr_buffer": stderr_chunks,
                    }
                    return {
                        "exit_code": None,
                        "stdout": stdout_text
                        + f"\n\n[Command still running after {partial_timeout}s - use get_terminal_output with terminal_id='{self.session_id}' and command_id='{command_id}' to check progress]",
                        "stderr": stderr_text,
                        "working_directory": self.working_directory,
                        "execution_time_seconds": time.time() - start_time,
                        "timed_out": True,
                        "still_running": True,
                        "terminal_id": self.session_id,
                        "command_id": command_id,
                        "pid": process.pid,
                    }
                else:
                    # Hard timeout - process was killed
                    return {
                        "exit_code": -1,
                        "stdout": stdout_text,
                        "stderr": stderr_text
                        + f"\n\nProcess killed after {timeout}s hard timeout",
                        "working_directory": self.working_directory,
                        "execution_time_seconds": timeout,
                        "timed_out": True,
                        "killed": True,
                    }

        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "working_directory": self.working_directory,
                "execution_time_seconds": time.time() - start_time,
            }

    def get_output(self, command_id: str) -> dict:
        """
        Get output from a running or completed background process.

        Args:
            command_id: The command_id returned from execute() when process is still running

        Returns:
            dict with current output, whether process is still running, etc.
        """
        if command_id not in self._running_processes:
            return {
                "error": f"No tracked process with command_id '{command_id}'",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
            }

        proc_info = self._running_processes[command_id]
        process = proc_info["process"]
        command = proc_info["command"]
        start_time = proc_info["start_time"]
        stdout_buffer = proc_info["stdout_buffer"]
        stderr_buffer = proc_info["stderr_buffer"]

        # Check if process has finished
        exit_code = process.poll()

        # Try to read any new output
        import select

        try:
            if hasattr(select, "select"):
                readable, _, _ = select.select(
                    [process.stdout, process.stderr], [], [], 0
                )
                for stream in readable:
                    chunk = stream.read(4096)
                    if chunk:
                        if stream == process.stdout:
                            stdout_buffer.append(chunk)
                        else:
                            stderr_buffer.append(chunk)
        except Exception:
            pass

        # If finished, read any remaining output
        if exit_code is not None:
            try:
                remaining_stdout = process.stdout.read()
                remaining_stderr = process.stderr.read()
                if remaining_stdout:
                    stdout_buffer.append(remaining_stdout)
                if remaining_stderr:
                    stderr_buffer.append(remaining_stderr)
            except Exception:
                pass

            # Record in history and clean up
            self.history.append(
                {
                    "command": command,
                    "exit_code": exit_code,
                    "timestamp": time.time(),
                }
            )
            del self._running_processes[command_id]

            return {
                "exit_code": exit_code,
                "stdout": "".join(stdout_buffer),
                "stderr": "".join(stderr_buffer),
                "still_running": False,
                "execution_time_seconds": time.time() - start_time,
                "working_directory": self.working_directory,
            }
        else:
            # Still running
            return {
                "exit_code": None,
                "stdout": "".join(stdout_buffer),
                "stderr": "".join(stderr_buffer),
                "still_running": True,
                "pid": process.pid,
                "execution_time_seconds": time.time() - start_time,
                "working_directory": self.working_directory,
                "terminal_id": self.session_id,
                "command_id": command_id,
            }

    def list_running_processes(self) -> list:
        """List all tracked running processes in this session."""
        result = []
        for cmd_id, info in list(self._running_processes.items()):
            proc = info["process"]
            exit_code = proc.poll()
            if exit_code is not None:
                # Process finished - clean up
                del self._running_processes[cmd_id]
            else:
                result.append(
                    {
                        "command_id": cmd_id,
                        "command": info["command"],
                        "pid": proc.pid,
                        "runtime_seconds": time.time() - info["start_time"],
                    }
                )
        return result


class TerminalSessionManager:
    """Manages multiple terminal sessions for remote command execution."""

    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def get_or_create_session(
        self, session_id: str, working_directory: Optional[str] = None
    ) -> TerminalSession:
        """Get an existing session or create a new one."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = TerminalSession(
                    session_id, working_directory
                )
            elif working_directory:
                # Update working directory if specified
                self._sessions[session_id].working_directory = working_directory
            return self._sessions[session_id]

    def execute_command(
        self,
        command: str,
        terminal_id: str,
        working_directory: Optional[str] = None,
        is_background: bool = False,
        timeout: int = 300,
        partial_timeout: int = 30,
    ) -> dict:
        """
        Execute a command in a terminal session.

        Args:
            command: The shell command to execute
            terminal_id: ID of the terminal session (created if doesn't exist)
            working_directory: Optional directory to run in
            is_background: If True, run in background
            timeout: Maximum seconds before killing process (hard timeout)
            partial_timeout: Seconds before returning partial output (default 30)
                           Process continues in background if not finished.

        Returns:
            dict with execution results
        """
        session = self.get_or_create_session(terminal_id, working_directory)
        return session.execute(command, timeout, is_background, partial_timeout)

    def get_output(
        self,
        terminal_id: str,
        command_id: str,
    ) -> dict:
        """
        Get output from a running or recently completed command.

        Args:
            terminal_id: ID of the terminal session
            command_id: ID of the specific command (returned from execute when still_running=True)

        Returns:
            dict with current output, exit_code, still_running status
        """
        with self._lock:
            if terminal_id not in self._sessions:
                return {
                    "error": f"No terminal session with ID '{terminal_id}'",
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                }
            session = self._sessions[terminal_id]
        return session.get_output(command_id)

    def list_running_processes(self, terminal_id: str = None) -> list:
        """
        List running processes, optionally filtered by terminal ID.

        Args:
            terminal_id: Optional terminal ID to filter by

        Returns:
            list of running process info dicts
        """
        with self._lock:
            if terminal_id:
                if terminal_id not in self._sessions:
                    return []
                return self._sessions[terminal_id].list_running_processes()
            else:
                all_processes = []
                for sid, session in self._sessions.items():
                    for proc in session.list_running_processes():
                        proc["terminal_id"] = sid
                        all_processes.append(proc)
                return all_processes

    def list_sessions(self) -> list:
        """List all active terminal sessions."""
        with self._lock:
            return [
                {
                    "session_id": sid,
                    "working_directory": session.working_directory,
                    "command_count": len(session.history),
                    "running_processes": len(session._running_processes),
                }
                for sid, session in self._sessions.items()
            ]


# Global terminal session manager for CLI
_terminal_manager = TerminalSessionManager()


def execute_remote_command(remote_request: dict) -> dict:
    """
    Execute a remote command request locally.

    Args:
        remote_request: The remote command request from the server containing:
            - command: The shell command to execute
            - terminal_id: ID for the terminal session
            - working_directory: Optional working directory
            - is_background: Whether to run in background
            - timeout_seconds: Hard timeout (kills process)
            - partial_timeout_seconds: Soft timeout (returns partial output, default 30)

    Returns:
        dict with execution results
    """
    command = remote_request.get("command", "")
    terminal_id = remote_request.get("terminal_id", str(uuid.uuid4()))
    working_directory = remote_request.get("working_directory")
    is_background = remote_request.get("is_background", False)
    timeout = remote_request.get("timeout_seconds", 300)
    partial_timeout = remote_request.get("partial_timeout_seconds", 30)
    request_id = remote_request.get("request_id", str(uuid.uuid4()))

    print(f"\n🖥️  Remote command: {command}")
    if working_directory:
        print(f"   📂 Directory: {working_directory}")

    # Execute the command with partial timeout
    result = _terminal_manager.execute_command(
        command=command,
        terminal_id=terminal_id,
        working_directory=working_directory,
        is_background=is_background,
        timeout=timeout,
        partial_timeout=partial_timeout,
    )

    # Add request tracking info
    result["request_id"] = request_id
    result["terminal_id"] = terminal_id

    # Display result
    exit_code = result.get("exit_code")
    still_running = result.get("still_running", False)

    if still_running:
        print(
            f"   ⏳ Command still running after {partial_timeout}s (partial output returned)"
        )
        print(f"      Terminal ID: {terminal_id}")
        if result.get("command_id"):
            print(f"      Command ID: {result['command_id']}")
        if result.get("pid"):
            print(f"      PID: {result['pid']}")
    elif exit_code == 0:
        print(f"   ✅ Exit code: {exit_code}")
    elif exit_code is not None:
        print(f"   ❌ Exit code: {exit_code}")

    if result.get("stdout"):
        stdout_preview = result["stdout"][:500]
        if len(result["stdout"]) > 500:
            stdout_preview += f"\n... ({len(result['stdout'])} chars total)"
        print(f"   📤 Output:\n{stdout_preview}")

    if result.get("stderr"):
        stderr_preview = result["stderr"][:300]
        if len(result["stderr"]) > 300:
            stderr_preview += f"\n... ({len(result['stderr'])} chars total)"
        print(f"   ⚠️  Stderr:\n{stderr_preview}")

    return result


def get_terminal_output(request: dict) -> dict:
    """
    Get output from a running or completed terminal command.

    Args:
        request: Dict containing:
            - terminal_id: ID of the terminal session
            - command_id: ID of the command to check (optional for listing all)

    Returns:
        dict with current output and status
    """
    terminal_id = request.get("terminal_id")
    command_id = request.get("command_id")

    if not terminal_id:
        # List all sessions and their running processes
        sessions = _terminal_manager.list_sessions()
        running = _terminal_manager.list_running_processes()
        return {
            "sessions": sessions,
            "running_processes": running,
        }

    if not command_id:
        # List running processes in this terminal
        running = _terminal_manager.list_running_processes(terminal_id)
        return {
            "terminal_id": terminal_id,
            "running_processes": running,
        }

    # Get output for specific command
    result = _terminal_manager.get_output(terminal_id, command_id)

    # Display status
    if result.get("error"):
        print(f"\n❌ {result['error']}")
    elif result.get("still_running"):
        print(f"\n⏳ Command still running (PID: {result.get('pid')})")
        print(f"   Runtime: {result.get('execution_time_seconds', 0):.1f}s")
    else:
        exit_code = result.get("exit_code")
        if exit_code == 0:
            print(f"\n✅ Command completed (exit code: {exit_code})")
        else:
            print(f"\n❌ Command completed (exit code: {exit_code})")

    if result.get("stdout"):
        stdout_preview = result["stdout"][-500:]  # Show last 500 chars for get_output
        if len(result["stdout"]) > 500:
            stdout_preview = (
                f"... ({len(result['stdout'])} chars total)\n" + stdout_preview
            )
        print(f"   📤 Output:\n{stdout_preview}")

    return result


def submit_remote_command_result(
    server_url: str,
    token: str,
    conversation_id: str,
    result: dict,
) -> bool:
    """
    Submit the result of a remote command execution to the server.

    Args:
        server_url: The AGiXT server URL
        token: Authentication token
        conversation_id: The conversation ID
        result: The execution result dict

    Returns:
        True if successful, False otherwise
    """
    try:
        url = f"{server_url}/v1/conversation/{conversation_id}/remote-command-result"
        data = json.dumps(result).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": token,
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            response.read()
            return True
    except Exception as e:
        print(f"   ⚠️  Failed to submit result: {e}")
        return False


def connect_conversation_websocket(
    server_url: str,
    token: str,
    conversation_id: str,
    activity_tracker: ActivityTracker,
    stop_event: threading.Event,
):
    """
    Connect to the conversation WebSocket to receive real-time updates.

    This runs in a separate thread and updates the activity tracker
    with any streaming activities received from the server.

    Activity message formats:
    - [ACTIVITY][INFO] message
    - [ACTIVITY][ERROR] message
    - [SUBACTIVITY][{activity_id}] message
    - [SUBACTIVITY][THOUGHT] message
    - [SUBACTIVITY][REFLECTION] message
    """
    try:
        import websocket

        has_websocket = True
    except ImportError:
        # websocket-client not available, skip activity streaming
        return

    # Construct WebSocket URL
    protocol = "wss" if server_url.startswith("https") else "ws"
    base_url = server_url.replace("http://", "").replace("https://", "")
    ws_url = f"{protocol}://{base_url}/v1/conversation/{conversation_id}/stream?authorization={urllib.parse.quote(token)}"

    def on_message(ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            # Handle message_added events - these contain activities
            if msg_type == "message_added":
                msg_data = data.get("data", {})
                content = msg_data.get("message", "")
                role = msg_data.get("role", "")

                # Skip user messages
                if role == "user":
                    return

                # Parse activity messages
                if content.startswith("[ACTIVITY]"):
                    # Format: [ACTIVITY][INFO|ERROR] message
                    # Remove [ACTIVITY] prefix
                    remaining = content[10:].strip()  # len("[ACTIVITY]") = 10

                    # Check for activity type tag
                    if remaining.startswith("[INFO]"):
                        activity_content = remaining[6:].strip()
                        activity_tracker.update("info", activity_content)
                    elif remaining.startswith("[ERROR]"):
                        activity_content = remaining[7:].strip()
                        activity_tracker.update("error", activity_content)
                    else:
                        # Remove any other bracket tag
                        if remaining.startswith("[") and "]" in remaining:
                            activity_content = remaining.split("]", 1)[1].strip()
                        else:
                            activity_content = remaining
                        activity_tracker.update("activity", activity_content)

                elif content.startswith("[SUBACTIVITY]"):
                    # Format: [SUBACTIVITY][type|id] message
                    remaining = content[13:].strip()  # len("[SUBACTIVITY]") = 13

                    # Extract subactivity type/id and content
                    if remaining.startswith("[") and "]" in remaining:
                        tag_end = remaining.index("]")
                        tag = remaining[1:tag_end]
                        subactivity_content = remaining[tag_end + 1 :].strip()

                        # Map tag to activity type
                        if tag == "THOUGHT":
                            activity_tracker.update("thinking", subactivity_content)
                        elif tag == "REFLECTION":
                            activity_tracker.update("reflection", subactivity_content)
                        else:
                            # It's an activity ID - still show as subactivity
                            activity_tracker.update("subactivity", subactivity_content)
                    else:
                        activity_tracker.update("subactivity", remaining)

        except (json.JSONDecodeError, KeyError):
            pass

    def on_error(ws, error):
        # Silently handle errors - we don't want to interrupt the main prompt
        pass

    def on_close(ws, close_status_code, close_msg):
        pass

    def on_open(ws):
        pass

    try:
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )

        # Run in a loop until stop_event is set
        while not stop_event.is_set():
            ws.run_forever(ping_interval=30, ping_timeout=10)
            if not stop_event.is_set():
                time.sleep(1)  # Brief pause before reconnecting
    except Exception:
        pass


def stop_conversation_api(server_url: str, token: str, conversation_id: str = None):
    """
    Call the AGiXT API to stop an active conversation.

    This ensures the server stops processing even when the CLI is interrupted.

    Args:
        server_url: The AGiXT server URL
        token: The authentication token
        conversation_id: Optional specific conversation ID to stop (stops all if not provided)
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": token,
        }

        # Try to stop specific conversation if ID provided
        if conversation_id and conversation_id != "-":
            try:
                url = f"{server_url}/v1/conversation/{conversation_id}/stop"
                req = urllib.request.Request(
                    url, data=b"{}", headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    response.read()
            except Exception:
                pass  # Silently ignore specific stop failures

        # Also try to stop all conversations for this user as backup
        try:
            url = f"{server_url}/v1/conversations/stop"
            req = urllib.request.Request(
                url, data=b"{}", headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                response.read()
        except Exception:
            pass  # Silently ignore stop failures

    except Exception:
        # Don't let stop failures interfere with CLI exit
        pass


def _prompt(
    prompt_text: str,
    agent: Optional[str] = None,
    conversation: Optional[str] = None,
    image_path: Optional[str] = None,
    show_stats: bool = False,
    show_activities: bool = True,
) -> int:
    """
    Send a prompt to the AGiXT server and stream the response.

    This connects to the AGiXT chat completions endpoint with streaming
    and optionally connects to the WebSocket to show activities.
    """
    # Get credentials
    server_url = get_server_url()
    token = get_auth_token()

    if not token:
        print("❌ Not logged in. Run 'agixt login' first.")
        print(
            f"   Example: agixt login --server {server_url} --email your@email.com --otp 123456"
        )
        return 1

    # Use defaults if not specified
    if not agent:
        agent = get_default_agent()
    if not conversation:
        conversation = get_default_conversation()

    print(f"💬 Sending to {agent}...")

    # Build the messages array
    content = []

    # Handle image if provided
    if image_path:
        if is_url(image_path):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_path},
                }
            )
        else:
            image_file = Path(image_path)
            if not image_file.exists():
                print(f"❌ Image file not found: {image_path}")
                return 1

            mime_type = get_image_mime_type(image_path)
            base64_image = encode_image_to_base64(image_path)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                }
            )

    # Add the text prompt
    content.append({"type": "text", "text": prompt_text})

    messages = [{"role": "user", "content": content}]

    # Define CLI tools using OpenAI-compatible tool format
    # These tools are executed locally by the CLI, not on the server
    cli_tools = [
        {
            "type": "function",
            "function": {
                "name": "execute_terminal_command",
                "description": """Execute a terminal/shell command on the USER'S LOCAL MACHINE.

This is the PRIMARY command for interacting with the user's computer.
Use this command whenever the user asks you to:
- List files or directories (ls, dir, find, tree)
- Create, move, copy, or delete files/folders (mkdir, mv, cp, rm, touch)
- Check system information (pwd, whoami, uname, hostname, df, du)
- Run build commands (npm, yarn, cargo, make, pip, poetry)
- Execute scripts or programs on their machine
- Manage processes (ps, kill, top)
- Work with git (git status, git log, git diff, git branch)
- Navigate the filesystem (cd, followed by other commands)
- Install packages or dependencies
- ANY terminal or shell operation on the user's system

This command runs on the user's local machine through the CLI client,
NOT on the server. You have access to the user's full filesystem and
any tools they have installed.

IMPORTANT: Commands have a 30-second timeout that returns partial output
if the command is still running. For long-running commands, you can
use get_terminal_output to check progress later.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute. Can be any valid shell command. For multiple commands, chain with && or ;. Examples: 'ls -la', 'git status', 'npm install && npm run build'",
                        },
                        "terminal_id": {
                            "type": "string",
                            "description": "Optional. Reuse an existing terminal session to preserve state like environment variables and working directory. If not specified, a default session is used.",
                        },
                        "working_directory": {
                            "type": "string",
                            "description": "Optional. Directory to run the command in. If not specified, uses the current working directory of the terminal session.",
                        },
                        "is_background": {
                            "type": "boolean",
                            "description": "If true, run the command in background and return immediately. Use get_terminal_output later to check progress. Default: false",
                        },
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_terminal_output",
                "description": """Get output from a running or completed terminal command.

Use this to:
- Check the progress/output of a long-running command
- Get final output after a command finishes
- Check if a background process is still running
- List all running processes in a terminal session

When a command times out (after 30 seconds), you receive partial output
and can use this tool to get more output later.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "terminal_id": {
                            "type": "string",
                            "description": "ID of the terminal session to check. If not provided, lists all sessions.",
                        },
                        "command_id": {
                            "type": "string",
                            "description": "ID of the specific command to check (returned when a command times out or runs in background). If not provided with terminal_id, lists running processes in that session.",
                        },
                    },
                    "required": [],
                },
            },
        },
    ]

    # Build the request payload
    # Include CLI-defined tools so the agent can execute commands on user's machine
    payload = {
        "messages": messages,
        "model": agent,
        "user": conversation,
        "stream": True,
        "tools": cli_tools,
        "tool_choice": "auto",  # Let the model decide when to use tools
    }

    # Set up activity tracking
    activity_tracker = ActivityTracker()
    stop_event = threading.Event()
    ws_thread = None

    # Start WebSocket connection for activities if enabled
    if show_activities:
        try:
            import websocket  # noqa: F401

            ws_thread = threading.Thread(
                target=connect_conversation_websocket,
                args=(server_url, token, conversation, activity_tracker, stop_event),
                daemon=True,
            )
            ws_thread.start()
        except ImportError:
            # websocket-client not available
            pass

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": token,
    }

    # Make the streaming request
    url = f"{server_url}/v1/chat/completions"

    # Track conversation ID outside try block so it's accessible in KeyboardInterrupt handler
    new_conversation_id = None

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        start_time = time.time()
        print()  # Start on a new line for streaming output

        # Track streaming statistics
        completion_tokens = 0
        prompt_tokens = 0
        actual_model = agent
        full_content = ""

        with urllib.request.urlopen(req, timeout=300) as response:
            # Process Server-Sent Events (SSE) stream
            buffer = ""
            response_started = False
            shown_completed = set()  # Track completed activities we've already shown
            current_streaming_type = (
                None  # Track if we're showing a streaming status line
            )

            def update_activity_display(force_clear=False):
                """Update the activity display from the tracker (both SSE and WebSocket).

                Strategy:
                - Print completed activities (thinking, reflection) as permanent lines with full content
                - Show a simple status for in-progress streaming (not every token)
                - Show other activity types (info, error, etc.) immediately
                """
                nonlocal response_started, shown_completed, current_streaming_type

                if force_clear or response_started:
                    # Don't show activities once response content has started
                    return

                # Get icon for activity type
                icon_map = {
                    "thinking": "🤔",
                    "reflection": "🔄",
                    "activity": "⚙️",
                    "subactivity": "└─",
                    "info": "ℹ️",
                    "error": "❌",
                }

                # First, print any completed activities
                completed = activity_tracker.get_completed()
                for activity_type, content in completed:
                    # Create a unique key for this completed activity
                    activity_key = f"{activity_type}:{hash(content)}"
                    if activity_key not in shown_completed:
                        shown_completed.add(activity_key)
                        icon = icon_map.get(activity_type, "⚙️")

                        # For completed thinking/reflection, show a summary
                        # Truncate for display but show it's complete
                        display_content = content
                        if len(display_content) > 150:
                            # Show first 100 chars, then ellipsis
                            display_content = display_content[:147] + "..."

                        # Clear any streaming status line before printing
                        if current_streaming_type:
                            print("\r" + " " * 80 + "\r", end="", flush=True)
                            current_streaming_type = None

                        print(f"\033[90m{icon} {display_content}\033[0m", flush=True)

                # Show status for in-progress streaming activities (but don't spam)
                streaming = activity_tracker.get_current_streaming()
                for activity_type, content in streaming.items():
                    icon = icon_map.get(activity_type, "⚙️")
                    # Just show that we're thinking, not the full content
                    content_preview = (
                        content[:50] + "..." if len(content) > 50 else content
                    )
                    content_preview = content_preview.replace("\n", " ")
                    status = f"\033[90m{icon} {activity_type.title()}...\033[0m"
                    # Overwrite the same line for streaming status
                    print(f"\r{status}" + " " * 30, end="", flush=True)
                    current_streaming_type = activity_type
                    break  # Only show one streaming status

                # Show non-streaming activities (info, error, activity, subactivity)
                with activity_tracker._lock:
                    for activity_type, content in activity_tracker._activities.items():
                        if activity_type in ("thinking", "reflection"):
                            continue  # Handled above as streaming

                        activity_key = f"{activity_type}:{hash(content)}"
                        if activity_key not in shown_completed:
                            shown_completed.add(activity_key)
                            icon = icon_map.get(activity_type, "⚙️")

                            display_content = content
                            if len(display_content) > 100:
                                display_content = display_content[:97] + "..."

                            # Clear any streaming status line before printing
                            if current_streaming_type:
                                print("\r" + " " * 80 + "\r", end="", flush=True)
                                current_streaming_type = None

                            print(
                                f"\033[90m{icon} {display_content}\033[0m", flush=True
                            )

            should_exit_stream = False  # Flag for breaking out of nested loops
            while not should_exit_stream:
                try:
                    chunk = response.read(1024).decode("utf-8")
                except Exception:
                    break
                if not chunk:
                    break
                buffer += chunk

                # Check for activity updates from WebSocket
                update_activity_display()

                # Process complete SSE messages
                while "\n\n" in buffer or "\r\n\r\n" in buffer:
                    if should_exit_stream:
                        break  # Exit the while loop
                    if "\r\n\r\n" in buffer:
                        message, buffer = buffer.split("\r\n\r\n", 1)
                    else:
                        message, buffer = buffer.split("\n\n", 1)

                    for line in message.split("\n"):
                        line = line.strip()
                        if line.startswith("data: "):
                            json_data = line[6:]

                            if json_data == "[DONE]":
                                should_exit_stream = True
                                break  # Exit the for line loop

                            try:
                                chunk_data = json.loads(json_data)

                                # Get conversation ID from first chunk
                                if chunk_data.get("id") and not new_conversation_id:
                                    new_conversation_id = chunk_data["id"]

                                # Get model from chunk
                                if chunk_data.get("model"):
                                    actual_model = chunk_data["model"]

                                # Handle remote command request from SSE
                                if chunk_data.get("object") == "remote_command.request":
                                    # Agent is requesting to execute a command/tool on user's machine
                                    tool_name = chunk_data.get("tool_name")
                                    tool_args = chunk_data.get("tool_args", {})
                                    request_id = chunk_data.get(
                                        "request_id", str(uuid.uuid4())
                                    )

                                    # Handle different tool types
                                    if (
                                        tool_name == "execute_terminal_command"
                                        or chunk_data.get("command")
                                    ):
                                        # Terminal command execution
                                        if tool_name == "execute_terminal_command":
                                            command = tool_args.get(
                                                "command", chunk_data.get("command", "")
                                            )
                                            working_directory = tool_args.get(
                                                "working_directory",
                                                chunk_data.get("working_directory"),
                                            )
                                            terminal_id = tool_args.get(
                                                "terminal_id",
                                                chunk_data.get(
                                                    "terminal_id", str(uuid.uuid4())
                                                ),
                                            )
                                            is_background = tool_args.get(
                                                "is_background", False
                                            )
                                        else:
                                            # Legacy format
                                            command = chunk_data.get("command", "")
                                            working_directory = chunk_data.get(
                                                "working_directory"
                                            )
                                            terminal_id = chunk_data.get(
                                                "terminal_id", str(uuid.uuid4())
                                            )
                                            is_background = False

                                        if command:
                                            print(
                                                f"\n\033[93m🖥️  Agent requesting terminal command:\033[0m"
                                            )
                                            print(f"\033[90m   $ {command}\033[0m")
                                            if working_directory:
                                                print(
                                                    f"\033[90m   in: {working_directory}\033[0m"
                                                )

                                            # Execute the command locally using the remote command handler
                                            remote_request = {
                                                "command": command,
                                                "working_directory": working_directory,
                                                "terminal_id": terminal_id,
                                                "request_id": request_id,
                                                "is_background": is_background,
                                                "timeout_seconds": 300,
                                            }
                                            result = execute_remote_command(
                                                remote_request
                                            )

                                            # Get the output - use stdout primarily, fall back to stderr
                                            output = result.get(
                                                "stdout", ""
                                            ) or result.get("stderr", "")
                                            exit_code = result.get("exit_code", -1)
                                            still_running = result.get(
                                                "still_running", False
                                            )

                                            if still_running:
                                                print(
                                                    f"\033[93m⏳ Command still running (partial output returned after 30s)\033[0m"
                                                )
                                                print(f"   Terminal ID: {terminal_id}")
                                                if result.get("command_id"):
                                                    print(
                                                        f"   Command ID: {result['command_id']}"
                                                    )
                                            elif exit_code == 0:
                                                print(
                                                    f"\033[92m✓ Command completed (exit code: {exit_code})\033[0m"
                                                )
                                            else:
                                                print(
                                                    f"\033[91m✗ Command failed (exit code: {exit_code})\033[0m"
                                                )

                                            if output:
                                                # Print output with indentation
                                                output_lines = output.split("\n")
                                                for line in output_lines[
                                                    :20
                                                ]:  # Limit output display
                                                    print(f"   {line}")
                                                if len(output_lines) > 20:
                                                    print(
                                                        f"   ... ({len(output_lines) - 20} more lines)"
                                                    )

                                            # Submit result back to server
                                            submit_remote_command_result(
                                                server_url=server_url,
                                                token=token,
                                                conversation_id=new_conversation_id
                                                or conversation,
                                                result={
                                                    "command": command,
                                                    "terminal_id": terminal_id,
                                                    "output": output,
                                                    "exit_code": exit_code,
                                                    "request_id": request_id,
                                                    "working_directory": result.get(
                                                        "working_directory"
                                                    ),
                                                    "still_running": still_running,
                                                    "command_id": result.get(
                                                        "command_id"
                                                    ),
                                                },
                                            )
                                            print()  # Add spacing

                                    elif tool_name == "get_terminal_output":
                                        # Get output from a running or completed command
                                        terminal_id = tool_args.get("terminal_id")
                                        command_id = tool_args.get("command_id")

                                        print(
                                            f"\n\033[93m📋 Agent checking terminal output:\033[0m"
                                        )
                                        if terminal_id:
                                            print(
                                                f"\033[90m   Terminal ID: {terminal_id}\033[0m"
                                            )
                                        if command_id:
                                            print(
                                                f"\033[90m   Command ID: {command_id}\033[0m"
                                            )

                                        result = get_terminal_output(
                                            {
                                                "terminal_id": terminal_id,
                                                "command_id": command_id,
                                            }
                                        )

                                        # Format output for server
                                        output = ""
                                        if result.get("stdout"):
                                            output = result["stdout"]
                                        elif result.get("running_processes"):
                                            output = json.dumps(
                                                result["running_processes"], indent=2
                                            )
                                        elif result.get("sessions"):
                                            output = json.dumps(
                                                result["sessions"], indent=2
                                            )
                                        elif result.get("error"):
                                            output = f"Error: {result['error']}"

                                        still_running = result.get(
                                            "still_running", False
                                        )
                                        exit_code = result.get(
                                            "exit_code",
                                            0 if not still_running else None,
                                        )

                                        if still_running:
                                            print(
                                                f"\033[93m⏳ Command still running\033[0m"
                                            )
                                        elif result.get("error"):
                                            print(f"\033[91m✗ {result['error']}\033[0m")
                                        else:
                                            print(f"\033[92m✓ Output retrieved\033[0m")

                                        if output:
                                            output_lines = output.split("\n")
                                            for line in output_lines[:15]:
                                                print(f"   {line}")
                                            if len(output_lines) > 15:
                                                print(
                                                    f"   ... ({len(output_lines) - 15} more lines)"
                                                )

                                        # Submit result back to server
                                        submit_remote_command_result(
                                            server_url=server_url,
                                            token=token,
                                            conversation_id=new_conversation_id
                                            or conversation,
                                            result={
                                                "tool_name": "get_terminal_output",
                                                "terminal_id": terminal_id,
                                                "command_id": command_id,
                                                "output": output,
                                                "exit_code": exit_code,
                                                "request_id": request_id,
                                                "still_running": still_running,
                                            },
                                        )
                                        print()  # Add spacing

                                    else:
                                        # Unknown client tool - log warning
                                        print(
                                            f"\n\033[91m⚠️  Unknown client tool requested: {tool_name}\033[0m"
                                        )
                                        submit_remote_command_result(
                                            server_url=server_url,
                                            token=token,
                                            conversation_id=new_conversation_id
                                            or conversation,
                                            result={
                                                "tool_name": tool_name,
                                                "output": f"Error: Unknown client tool '{tool_name}'",
                                                "exit_code": 1,
                                                "request_id": request_id,
                                            },
                                        )

                                    continue

                                # Handle remote command pending (stream ending after remote command)
                                if chunk_data.get("object") == "remote_command.pending":
                                    # The stream is ending because a remote command was requested
                                    # The result was already submitted - now we're done
                                    print("\n")  # Clean ending
                                    should_exit_stream = True
                                    break  # Exit the while loop (message processing)

                                # Handle activity streaming from SSE
                                if chunk_data.get("object") == "activity.stream":
                                    activity_type = chunk_data.get("type", "activity")
                                    activity_content = chunk_data.get("content", "")
                                    is_complete = chunk_data.get("complete", False)

                                    if activity_content:
                                        activity_tracker.update(
                                            activity_type, activity_content, is_complete
                                        )

                                    # Update display
                                    update_activity_display()
                                    continue

                                # Extract content from delta
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content_chunk = delta.get("content", "")
                                    if content_chunk:
                                        # Mark response as started
                                        if not response_started:
                                            # Clear any streaming status line
                                            if current_streaming_type:
                                                print(
                                                    "\r" + " " * 80 + "\r",
                                                    end="",
                                                    flush=True,
                                                )
                                                current_streaming_type = None
                                            # Print a newline to separate from activities
                                            print()
                                            response_started = True

                                        print(content_chunk, end="", flush=True)
                                        full_content += content_chunk
                                        completion_tokens += 1

                                    # Check for finish reason
                                    if choices[0].get("finish_reason") == "stop":
                                        # Clear any remaining activities
                                        activity_tracker.clear()

                                # Get usage from final chunk if available
                                usage = chunk_data.get("usage")
                                if usage:
                                    prompt_tokens = usage.get("prompt_tokens", 0)
                                    completion_tokens = usage.get(
                                        "completion_tokens", completion_tokens
                                    )

                            except json.JSONDecodeError:
                                pass

        elapsed = time.time() - start_time
        print()  # End with newline
        print()  # Extra line for spacing

        # Stop WebSocket thread
        stop_event.set()

        if not full_content and not should_exit_stream:
            # Only show warning if we didn't handle a remote command
            print("⚠️  Empty response received")

        # Update stored conversation ID if it changed
        if new_conversation_id and new_conversation_id != "-":
            creds = load_credentials()
            creds["conversation"] = new_conversation_id
            save_credentials(creds)
            conversation = new_conversation_id  # Update for potential follow-up

        # Show stats if requested
        if show_stats:
            total_tokens = prompt_tokens + completion_tokens

            print(f"{'─' * 50}")
            print(f"📊 Statistics")
            print(f"{'─' * 50}")
            print(f"   Agent: {actual_model}")
            print(f"   Conversation: {new_conversation_id or conversation}")
            print(f"   Prompt tokens: {prompt_tokens:,}")
            print(f"   Completion tokens: {completion_tokens:,}")
            print(f"   Total tokens: {total_tokens:,}")
            print(f"   Total time: {elapsed:.1f}s")

            if completion_tokens > 0:
                overall_speed = completion_tokens / elapsed
                print(f"   Speed: {overall_speed:.1f} tok/s")
            print()

        # Interactive chat loop - prompt for follow-up with 60s idle timeout
        # Only run interactive loop if stdin is a TTY (not piped)
        if not sys.stdin.isatty():
            # Input is piped, don't enter interactive mode
            return 0

        def input_with_timeout(prompt: str, timeout: int = 60) -> str:
            """Read input with a timeout. Returns None on timeout."""
            import select

            sys.stdout.write(prompt)
            sys.stdout.flush()
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if ready:
                line = sys.stdin.readline()
                if not line:  # EOF
                    return None
                return line.strip()
            else:
                print("\n⏱️  Chat session timed out after 60 seconds of inactivity.")
                return None

        try:
            while True:
                try:
                    follow_up = input_with_timeout("You: ", timeout=60)
                    if follow_up is None:
                        # Timeout or EOF - exit gracefully
                        break
                    if not follow_up:
                        continue

                    # Recursively call _prompt with the follow-up
                    # Use the same conversation to continue the chat
                    return _prompt(
                        prompt_text=follow_up,
                        agent=agent,
                        conversation=conversation,
                        image_path=None,  # No image for follow-ups
                        show_stats=show_stats,
                        show_activities=show_activities,
                    )
                except EOFError:
                    # End of input (e.g., piped input)
                    break
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            return 0

        return 0

    except urllib.error.HTTPError as e:
        stop_event.set()
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        if error_body:
            try:
                error_json = json.loads(error_body)
                print(f"   {error_json.get('detail', error_body)}")
            except json.JSONDecodeError:
                print(f"   {error_body}")
        return 1
    except urllib.error.URLError as e:
        stop_event.set()
        print(f"❌ Connection error: {e.reason}")
        print(f"   Is the AGiXT server running at {server_url}?")
        return 1
    except TimeoutError:
        stop_event.set()
        print("❌ Request timed out after 300 seconds")
        return 1
    except KeyboardInterrupt:
        stop_event.set()
        print("\n⚠️  Interrupted - stopping server-side processing...")
        # Call the stop API to halt any ongoing processing
        stop_conversation_api(server_url, token, new_conversation_id or conversation)
        print("✓ Stop signal sent")
        return 130


def get_default_env_vars():
    workspace_folder = os.path.normpath(os.path.join(os.getcwd(), "WORKSPACE"))
    return {
        # Core AGiXT configuration - required before DB is available
        "AGIXT_API_KEY": "",
        "AGIXT_URI": "http://localhost:7437",
        "AGIXT_PORT": "7437",
        "AGIXT_INTERACTIVE_PORT": "3437",
        "AGIXT_SERVER": "http://localhost:7437",
        "AGIXT_BRANCH": "stable",
        "AGIXT_RUN_TYPE": "docker",
        "AGIXT_AUTO_UPDATE": "true",
        "AGIXT_HEALTH_URL": "http://localhost:7437/health",
        # Database configuration - required before DB is available
        "DATABASE_TYPE": "sqlite",
        "DATABASE_NAME": "models/agixt",
        "DATABASE_USER": "postgres",
        "DATABASE_PASSWORD": "postgres",
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        # Server runtime configuration
        "LOG_LEVEL": "INFO",
        "UVICORN_WORKERS": "10",
        "WORKING_DIRECTORY": workspace_folder.replace("\\", "/"),
        # Health check configuration (for CLI monitoring)
        "HEALTH_CHECK_INTERVAL": "15",
        "HEALTH_CHECK_TIMEOUT": "10",
        "HEALTH_CHECK_MAX_FAILURES": "3",
        "RESTART_COOLDOWN": "60",
        "INITIAL_STARTUP_DELAY": "180",
        # Super admin configuration
        "SUPERADMIN_EMAIL": "josh@devxt.com",
        # ezLocalai Configuration (local AI inference)
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
        "WITH_EZLOCALAI": "true",
        # Note: All other settings (API keys, OAuth, storage, app settings, etc.)
        # are now managed via Server Config in the database UI at /billing/admin/settings
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
                dockerfile = "docker-compose.yml"
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


# Redis container management for local mode
REDIS_CONTAINER_NAME = "agixt-redis"


def _is_redis_running() -> bool:
    """Check if Redis container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", REDIS_CONTAINER_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.SubprocessError, OSError):
        return False


def start_redis() -> None:
    """Start Redis container for local mode shared cache."""
    if _is_redis_running():
        print(f"Redis container '{REDIS_CONTAINER_NAME}' is already running.")
        return

    print("Starting Redis container...")

    # Check if container exists but is stopped
    try:
        result = subprocess.run(
            ["docker", "inspect", REDIS_CONTAINER_NAME],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            # Container exists, start it
            subprocess.run(
                ["docker", "start", REDIS_CONTAINER_NAME],
                check=True,
            )
            print(f"Started existing Redis container '{REDIS_CONTAINER_NAME}'.")
            return
    except (subprocess.SubprocessError, OSError):
        pass

    # Create new container
    redis_data_dir = REPO_ROOT / "models" / "redis"
    redis_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                REDIS_CONTAINER_NAME,
                "-p",
                "6379:6379",
                "-v",
                f"{redis_data_dir}:/data",
                "--restart",
                "unless-stopped",
                "redis:alpine",
                "redis-server",
                "--appendonly",
                "yes",
            ],
            check=True,
        )
        print(f"Started new Redis container '{REDIS_CONTAINER_NAME}'.")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to start Redis container: {e}")
        print("SharedCache will fall back to local memory cache.")


def stop_redis() -> None:
    """Stop Redis container."""
    if not _is_redis_running():
        return

    print("Stopping Redis container...")
    try:
        subprocess.run(
            ["docker", "stop", REDIS_CONTAINER_NAME],
            check=True,
            capture_output=True,
        )
        print(f"Stopped Redis container '{REDIS_CONTAINER_NAME}'.")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to stop Redis container: {e}")


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
    if not DOCKER_COMPOSE_FILE_STABLE.exists():
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

    # Start Redis container for shared cache
    start_redis()

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


def _stop_local(stop_ezlocalai_too: bool = True, stop_redis_too: bool = False) -> None:
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

    # Stop Redis if requested (usually keep running between restarts)
    if stop_redis_too:
        try:
            stop_redis()
        except Exception as e:
            print(f"Warning: Failed to stop Redis: {e}")

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
        dockerfile = "docker-compose.yml"

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
    print("Note: Most settings (API keys, OAuth, storage, app settings) are now")
    print(
        "      managed via Server Config in the database UI at /billing/admin/settings\n"
    )

    load_dotenv()
    env_vars = get_default_env_vars()

    # Group variables by category - only CLI-relevant vars
    categories = {
        "Core Configuration": [
            "AGIXT_API_KEY",
            "AGIXT_URI",
            "AGIXT_PORT",
            "AGIXT_INTERACTIVE_PORT",
            "AGIXT_SERVER",
            "AGIXT_BRANCH",
            "AGIXT_RUN_TYPE",
            "AGIXT_AUTO_UPDATE",
            "AGIXT_HEALTH_URL",
        ],
        "Database Configuration": [
            "DATABASE_TYPE",
            "DATABASE_NAME",
            "DATABASE_USER",
            "DATABASE_PASSWORD",
            "DATABASE_HOST",
            "DATABASE_PORT",
        ],
        "Server Runtime": [
            "LOG_LEVEL",
            "UVICORN_WORKERS",
            "WORKING_DIRECTORY",
        ],
        "Health Check Configuration": [
            "HEALTH_CHECK_INTERVAL",
            "HEALTH_CHECK_TIMEOUT",
            "HEALTH_CHECK_MAX_FAILURES",
            "RESTART_COOLDOWN",
            "INITIAL_STARTUP_DELAY",
        ],
        "ezLocalai Configuration": [
            "EZLOCALAI_URL",
            "DEFAULT_MODEL",
            "VISION_MODEL",
            "IMG_MODEL",
            "WHISPER_MODEL",
            "GPU_LAYERS",
            "MAIN_GPU",
            "MAX_CONCURRENT_REQUESTS",
            "MAX_QUEUE_SIZE",
            "REQUEST_TIMEOUT",
            "NGROK_TOKEN",
            "WITH_EZLOCALAI",
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
    parser = argparse.ArgumentParser(
        description="AGiXT - AI Agent Orchestration Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Server management (requires full dependencies for --local)
  agixt start                              Start AGiXT via Docker
  agixt start --local                      Start AGiXT locally (Python)
  agixt stop                               Stop AGiXT
  agixt logs -f                            Follow AGiXT logs

  # Client mode (lightweight - works with remote server)
  agixt register --email user@example.com --firstname John --lastname Doe
  agixt login --email user@example.com --otp 123456
  agixt conversations                      List and select a conversation
  agixt conversations -                    Start a new conversation
  agixt prompt "Hello, how are you?"
  agixt prompt "Describe this image" --image ./photo.jpg

  # Environment management
  agixt env OPENAI_API_KEY="sk-xxxxx"
  agixt env help

Configuration:
  Server credentials are stored in ~/.agixt/credentials.json
  Environment variables are stored in AGiXT/.env
""",
    )

    subparsers = parser.add_subparsers(dest="action", help="Commands")

    # ===== Server Management Commands =====

    # Start command
    start_parser = subparsers.add_parser("start", help="Start AGiXT server")
    start_parser.add_argument(
        "--local",
        action="store_true",
        help="Run locally (Python) instead of Docker",
    )
    start_parser.add_argument(
        "--docker",
        action="store_true",
        help="Run via Docker (default)",
    )
    start_parser.add_argument(
        "--ezlocalai",
        action="store_true",
        help="Start ezLocalai only",
    )
    start_parser.add_argument(
        "--web",
        action="store_true",
        help="Start web interface only",
    )
    start_parser.add_argument(
        "--all",
        action="store_true",
        help="Start all services (AGiXT + ezLocalai + web)",
    )

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop AGiXT server")
    stop_parser.add_argument(
        "--local",
        action="store_true",
        help="Stop local Python process",
    )
    stop_parser.add_argument(
        "--docker",
        action="store_true",
        help="Stop Docker containers",
    )
    stop_parser.add_argument(
        "--ezlocalai",
        action="store_true",
        help="Stop ezLocalai only",
    )
    stop_parser.add_argument(
        "--web",
        action="store_true",
        help="Stop web interface only",
    )
    stop_parser.add_argument(
        "--all",
        action="store_true",
        help="Stop all services",
    )

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart AGiXT server")
    restart_parser.add_argument(
        "--local",
        action="store_true",
        help="Restart local Python process",
    )
    restart_parser.add_argument(
        "--docker",
        action="store_true",
        help="Restart Docker containers",
    )
    restart_parser.add_argument(
        "--ezlocalai",
        action="store_true",
        help="Restart ezLocalai only",
    )
    restart_parser.add_argument(
        "--web",
        action="store_true",
        help="Restart web interface only",
    )
    restart_parser.add_argument(
        "--all",
        action="store_true",
        help="Restart all services",
    )

    # Logs command
    logs_parser = subparsers.add_parser("logs", help="View AGiXT logs")
    logs_parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow log output",
    )
    logs_parser.add_argument(
        "--local",
        action="store_true",
        help="View local logs",
    )
    logs_parser.add_argument(
        "--docker",
        action="store_true",
        help="View Docker logs",
    )
    logs_parser.add_argument(
        "--ezlocalai",
        action="store_true",
        help="View ezLocalai logs",
    )
    logs_parser.add_argument(
        "--web",
        action="store_true",
        help="View web interface logs",
    )

    # Env command
    env_parser = subparsers.add_parser("env", help="Manage environment variables")
    env_parser.add_argument(
        "env_vars",
        nargs="*",
        help="KEY=VALUE pairs to set, or 'help' to list all variables",
    )

    # ===== Client Commands (Lightweight) =====

    # Register command
    register_parser = subparsers.add_parser(
        "register",
        help="Register a new user on an AGiXT server",
        description="Create a new user account on an AGiXT server. "
        "After registration, automatically logs in using the generated TOTP.",
    )
    register_parser.add_argument(
        "--server",
        "-s",
        default="http://localhost:7437",
        help="AGiXT server URL (default: http://localhost:7437)",
    )
    register_parser.add_argument(
        "--email",
        "-e",
        required=True,
        help="Email address for the new account",
    )
    register_parser.add_argument(
        "--firstname",
        "-f",
        required=True,
        help="First name",
    )
    register_parser.add_argument(
        "--lastname",
        "-l",
        required=True,
        help="Last name",
    )

    # Login command
    login_parser = subparsers.add_parser(
        "login",
        help="Login to an AGiXT server",
        description="Authenticate with an AGiXT server using email and OTP. "
        "Credentials are saved for future use with 'agixt prompt'.",
    )
    login_parser.add_argument(
        "--server",
        "-s",
        default=None,
        help="AGiXT server URL (default: http://localhost:7437 or saved server)",
    )
    login_parser.add_argument(
        "--email",
        "-e",
        required=True,
        help="Your email address",
    )
    login_parser.add_argument(
        "--otp",
        "-o",
        required=True,
        help="One-time password from your authenticator app",
    )

    # Prompt command
    prompt_parser = subparsers.add_parser(
        "prompt",
        help="Send a prompt to an AGiXT agent",
        description="Send a prompt to an AGiXT agent and stream the response. "
        "Requires prior login with 'agixt login'.",
    )
    prompt_parser.add_argument(
        "text",
        help="The prompt text to send",
    )
    prompt_parser.add_argument(
        "-a",
        "--agent",
        help="Agent to use (default: from config or 'XT')",
        default=None,
    )
    prompt_parser.add_argument(
        "-c",
        "--conversation",
        help="Conversation ID to continue (default: '-' for new)",
        default=None,
    )
    prompt_parser.add_argument(
        "-i",
        "--image",
        help="Path to an image file or URL to include with the prompt",
        default=None,
    )
    prompt_parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics (tokens, timing) after the response",
    )
    prompt_parser.add_argument(
        "--no-activities",
        action="store_true",
        help="Don't show streaming activities (thinking, etc.)",
    )

    # Conversations command
    conversations_parser = subparsers.add_parser(
        "conversations",
        help="List and select conversations",
        description="List your conversations and interactively select one to use for future prompts. "
        "The selected conversation will be used by default with 'agixt prompt'.",
    )
    conversations_parser.add_argument(
        "conversation_id",
        nargs="?",
        default=None,
        help="Directly set conversation ID (use '-' for new conversation)",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Show help if no command provided
    if not args.action:
        parser.print_help()
        return 0

    try:
        # ===== Client Commands (Lightweight - no heavy deps needed) =====

        # Handle register command
        if args.action == "register":
            return _register(
                server=args.server,
                email=args.email,
                first_name=args.firstname,
                last_name=args.lastname,
            )

        # Handle login command
        if args.action == "login":
            # Use saved server, or default to localhost if not provided
            server = args.server
            if not server:
                creds = load_credentials()
                server = creds.get("server", "http://localhost:7437")
            return _login(
                server=server,
                email=args.email,
                otp=args.otp,
            )

        # Handle prompt command
        if args.action == "prompt":
            return _prompt(
                prompt_text=args.text,
                agent=args.agent,
                conversation=args.conversation,
                image_path=args.image,
                show_stats=args.stats,
                show_activities=not args.no_activities,
            )

        # Handle conversations command
        if args.action == "conversations":
            if args.conversation_id is not None:
                # Direct set mode
                return _conversation_set(args.conversation_id)
            else:
                # Interactive selection mode
                return _conversations()

        # ===== Server Management Commands =====

        # Handle env command separately
        if args.action == "env":
            # Check if help was requested
            if (
                hasattr(args, "env_vars")
                and args.env_vars
                and args.env_vars[0].lower() == "help"
            ):
                _show_env_help()
                return 0

            # Parse KEY=VALUE pairs
            if not hasattr(args, "env_vars") or not args.env_vars:
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

        # Handle mode conflicts for server management commands
        has_local = hasattr(args, "local") and args.local
        has_docker = hasattr(args, "docker") and args.docker
        has_ezlocalai = hasattr(args, "ezlocalai") and args.ezlocalai
        has_web = hasattr(args, "web") and args.web
        has_all = hasattr(args, "all") and args.all
        has_follow = hasattr(args, "follow") and args.follow

        if has_local and has_docker:
            parser.error("Choose either --local or --docker, not both.")

        # Determine run type (local or docker)
        run_local = False
        env_updates = {}

        if has_local:
            run_local = True
            env_updates["AGIXT_RUN_TYPE"] = "local"
        elif has_docker:
            run_local = False
            env_updates["AGIXT_RUN_TYPE"] = "docker"
        else:
            # No flag set, check environment variable
            load_dotenv(ENV_FILE)
            run_type = os.getenv("AGIXT_RUN_TYPE", "docker").lower()
            run_local = run_type == "local"

        # Count service flags
        service_flags = sum([has_ezlocalai, has_web, has_all])
        if service_flags > 1:
            parser.error("Choose only one of --ezlocalai, --web, or --all.")

        # Logs command restrictions
        if has_all and args.action == "logs":
            parser.error(
                "Logs command not supported for --all flag. Use individual flags: --ezlocalai or --web"
            )

        # Handle ezlocalai-only operations
        if has_ezlocalai:
            if args.action == "start":
                start_ezlocalai()
            elif args.action == "stop":
                stop_ezlocalai()
            elif args.action == "restart":
                restart_ezlocalai()
            elif args.action == "logs":
                _logs_ezlocalai(follow=has_follow)
            return 0

        # Handle web-only operations
        if has_web:
            if run_local:
                if args.action == "start":
                    _start_web_local()
                elif args.action == "stop":
                    _stop_web_local()
                elif args.action == "restart":
                    _restart_web_local()
                elif args.action == "logs":
                    _logs_web_local(follow=has_follow)
            else:
                if args.action == "start":
                    _start_web_docker()
                elif args.action == "stop":
                    _stop_web_docker()
                elif args.action == "restart":
                    _restart_web_docker()
                elif args.action == "logs":
                    _logs_web_docker(follow=has_follow)
            return 0

        # Handle --all flag (all services)
        if has_all:
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
                _logs_local(follow=has_follow)
        else:
            if args.action == "start":
                _start_docker(env_updates=env_updates if env_updates else None)
            elif args.action == "stop":
                _stop_docker()
            elif args.action == "restart":
                _restart_docker(env_updates=env_updates if env_updates else None)
            elif args.action == "logs":
                _logs_docker(follow=has_follow)
    except CLIError as exc:
        parser.error(str(exc))
    except subprocess.CalledProcessError as exc:
        parser.error(f"Command failed with exit code {exc.returncode}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
