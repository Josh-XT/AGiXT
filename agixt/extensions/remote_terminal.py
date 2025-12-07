"""
Remote Terminal Extension for AGiXT

This extension provides remote terminal execution capabilities for AGiXT CLI clients.
When enabled, it allows the AI agent to request terminal command execution on the
client's local machine (where the CLI is running).

This is a "remote command" pattern - the execution doesn't happen on the server,
but rather the server signals the CLI client to execute the command locally and
report back the results.

Security Considerations:
- This extension should ONLY be enabled when using the AGiXT CLI
- The CLI user has full control over what gets executed on their machine
- Commands are executed with the same permissions as the CLI process
- Users can see what commands will be run before execution
"""

import json
import logging
import uuid
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from Extensions import Extensions


class remote_terminal(Extensions):
    """
    Remote Terminal - Execute commands on the user's local machine.

    This extension enables the AI assistant to run terminal/shell commands directly
    on the user's computer. Use this when the user asks you to interact with their
    filesystem, run programs, check system info, or perform any terminal operation.

    Key Capabilities:
    - List, create, modify, and delete files and directories
    - Run build tools (npm, cargo, make, pip, etc.)
    - Execute scripts and programs
    - Git operations (status, log, diff, commit, etc.)
    - System information and process management
    - Package installation and dependency management
    - Any shell/terminal command available on the user's system

    The commands execute on the USER'S machine through the CLI client, giving
    you direct access to their development environment and tools.
    """

    CATEGORY = "CLI Remote Tools"

    # This flag indicates this extension handles "remote" commands
    # that need to be executed on the client side, not the server
    IS_REMOTE_EXTENSION = True

    def __init__(self, **kwargs):
        self.AGENT = kwargs
        self.user_id = kwargs.get("user_id", None)
        self.ApiClient = kwargs.get("ApiClient", None)
        self.conversation_id = kwargs.get("conversation_id", None)

        # Define available commands for agent interaction
        self.commands = {
            "Execute Terminal Command": self.execute_terminal_command,
        }

    async def execute_terminal_command(
        self,
        command: str,
        terminal_id: Optional[str] = None,
        working_directory: Optional[str] = None,
        is_background: bool = False,
        timeout_seconds: int = 300,
        **kwargs,
    ) -> str:
        """
        Execute a terminal/shell command on the USER'S LOCAL MACHINE.

        **IMPORTANT**: This is the PRIMARY command for interacting with the user's computer.
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

        Args:
            command: The shell command to execute. Can be any valid shell command.
                    For multiple commands, chain with && or ;
                    Examples: "ls -la", "git status", "npm install && npm run build"

            terminal_id: Optional. Reuse an existing terminal session to preserve
                        the current working directory and environment variables.
                        If not provided, a new terminal session is created.

            working_directory: Optional. Directory to run the command in.
                              If not specified, uses the user's current directory.

            is_background: If True, the command runs in background (for servers,
                          watchers, etc.) and returns immediately.

            timeout_seconds: Maximum wait time. Default 300 seconds (5 minutes).

        Returns:
            The output of the terminal command (stdout and stderr).

        Usage Examples:

        User: "What files are in my current directory?"
        Assistant uses: Execute Terminal Command with command="ls -la"

        User: "List all python files in my home folder"
        Assistant uses: Execute Terminal Command with command="find ~ -name '*.py' -type f 2>/dev/null | head -50"

        User: "What's my current working directory?"
        Assistant uses: Execute Terminal Command with command="pwd"

        User: "Install the dependencies for this project"
        Assistant uses: Execute Terminal Command with command="npm install" OR command="pip install -r requirements.txt"

        User: "Show me the git status"
        Assistant uses: Execute Terminal Command with command="git status"

        User: "Create a new folder called 'test' and add a file to it"
        Assistant uses: Execute Terminal Command with command="mkdir -p test && touch test/example.txt && ls test"

        User: "Run my development server"
        Assistant uses: Execute Terminal Command with command="npm run dev" is_background=True
        """
        # Generate a unique request ID for tracking this execution
        request_id = str(uuid.uuid4())

        # If no terminal_id provided, generate one for a new session
        if terminal_id is None:
            terminal_id = str(uuid.uuid4())

        # Build the remote execution request
        # This gets returned as a special signal that the CLI will intercept
        remote_request = {
            "__remote_command__": True,
            "type": "terminal_execute",
            "status": "pending_remote_execution",
            "request_id": request_id,
            "terminal_id": terminal_id,
            "command": command,
            "working_directory": working_directory,
            "is_background": is_background,
            "timeout_seconds": timeout_seconds,
            "timestamp": datetime.now().isoformat(),
        }

        # Return the request as a JSON string
        # The Interactions.py execution_agent will detect this special format
        # and the CLI will handle it appropriately
        return json.dumps(remote_request, indent=2)
