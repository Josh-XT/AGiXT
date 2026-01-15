import os
import logging
from Extensions import Extensions
from InternalClient import InternalClient
from Globals import install_package_if_missing

install_package_if_missing("safeexecute")

from safeexecute import execute_github_copilot

"""
Required environment variables:

- GITHUB_COPILOT_TOKEN: A fine-grained GitHub Personal Access Token (PAT) with the 
  "Copilot Requests" permission enabled.

To create a token with Copilot access:
1. Visit https://github.com/settings/personal-access-tokens/new
2. Give your token a name and expiration
3. Under "Permissions", click "Account permissions"
4. Find "Copilot" and select "Read and write" access
5. Generate the token and use it as GITHUB_COPILOT_TOKEN

Note: Standard GitHub OAuth tokens do NOT support Copilot access. You must use a 
fine-grained PAT with the specific Copilot permission.

Requirements:
- An active GitHub Copilot subscription (Individual, Business, or Enterprise)
- If using Copilot via an organization, the organization admin must enable Copilot CLI
  in the organization settings
"""


class github_copilot(Extensions):
    """
    The GitHub Copilot extension provides access to GitHub Copilot CLI, an agentic
    coding assistant that can read, modify, create, and delete files in your workspace.

    GitHub Copilot runs in an isolated Docker container (SafeExecute) with your
    workspace mounted, allowing it to safely make changes to the codebase.

    This extension requires a separate fine-grained Personal Access Token (PAT) with
    the "Copilot Requests" permission - standard GitHub OAuth tokens do not support
    Copilot access.
    """

    CATEGORY = "Development & Code"
    friendly_name = "GitHub Copilot"

    def __init__(
        self,
        GITHUB_COPILOT_TOKEN: str = "",
        **kwargs,
    ):
        """
        Initialize the GitHub Copilot extension.

        Args:
            GITHUB_COPILOT_TOKEN: A fine-grained GitHub PAT with "Copilot Requests"
                                  permission. Create one at:
                                  https://github.com/settings/personal-access-tokens/new
        """
        self.GITHUB_COPILOT_TOKEN = GITHUB_COPILOT_TOKEN
        self.commands = {
            "Ask GitHub Copilot": self.ask_github_copilot,
        }
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else InternalClient(
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
            )
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.activity_id = kwargs["activity_id"] if "activity_id" in kwargs else None

    async def ask_github_copilot(
        self,
        prompt: str,
        model: str = "claude-opus-4.5",
        session_id: str = None,
    ) -> str:
        """
        Send a request to GitHub Copilot CLI, which is an agentic coding assistant.

        GitHub Copilot CLI can read, modify, create, and delete files in the working directory.
        It runs in an isolated Docker container (SafeExecute) with the agent's workspace mounted,
        allowing it to safely make changes to the codebase.

        This is useful for:
        - Complex code refactoring tasks
        - Generating new code files
        - Debugging and fixing issues
        - Code analysis and explanation
        - Any task that requires AI-assisted code manipulation

        Note: This command requires a fine-grained GitHub Personal Access Token (PAT) with
        the "Copilot Requests" permission. Standard OAuth tokens do not support Copilot.

        To create a compatible token:
        1. Visit https://github.com/settings/personal-access-tokens/new
        2. Under "Account permissions", enable "Copilot" with Read and write access
        3. Use the generated token as your GITHUB_COPILOT_TOKEN

        Args:
            prompt (str): The request or task to send to GitHub Copilot
            model (str): The AI model to use (default: claude-opus-4.5). Other options include
                         gpt-5, claude-sonnet-4, etc.
            session_id (str): Optional session ID to resume a previous conversation. If provided,
                              Copilot will continue from where the previous session left off.
                              Leave empty or set to None to start a new session.

        Returns:
            str: The response from GitHub Copilot including any actions taken and their results.
                 The response also includes the session_id which can be used to continue
                 the conversation in future requests.
        """
        if not self.GITHUB_COPILOT_TOKEN:
            return (
                "Error: GitHub Copilot Token is required.\n\n"
                "To use GitHub Copilot, you need a fine-grained Personal Access Token (PAT) "
                "with the 'Copilot Requests' permission. Standard GitHub OAuth tokens do not "
                "support Copilot access.\n\n"
                "To create a compatible token:\n"
                "1. Visit https://github.com/settings/personal-access-tokens/new\n"
                "2. Give your token a name and set an expiration\n"
                "3. Under 'Account permissions', find 'Copilot' and select 'Read and write'\n"
                "4. Generate the token and configure it as your GITHUB_COPILOT_TOKEN\n\n"
                "You must also have an active GitHub Copilot subscription."
            )

        try:
            if self.activity_id:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Sending request to GitHub Copilot...",
                    conversation_name=self.conversation_name,
                )

            # Create a streaming callback that sends thinking messages to AGiXT
            def stream_callback(event: dict):
                event_type = event.get("type", "")
                content = event.get("content", "")

                if self.activity_id and content:
                    if event_type == "thinking":
                        # Stream thinking/delta content wrapped in thinking tags
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] <thinking>{content}</thinking>",
                            conversation_name=self.conversation_name,
                        )
                    elif event_type == "tool_start":
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] <thinking>🔧 {content}</thinking>",
                            conversation_name=self.conversation_name,
                        )
                    elif event_type == "tool_complete":
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] <thinking>✅ {content}</thinking>",
                            conversation_name=self.conversation_name,
                        )
                    elif event_type == "reasoning":
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] <thinking>💭 {content}</thinking>",
                            conversation_name=self.conversation_name,
                        )
                    elif event_type == "error":
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] <thinking>❌ Error: {content}</thinking>",
                            conversation_name=self.conversation_name,
                        )

            # Normalize session_id (treat "None" string as None)
            effective_session_id = None
            if session_id and session_id.lower() not in ("none", "null", ""):
                effective_session_id = session_id

            # Execute GitHub Copilot in the SafeExecute container with streaming
            result = execute_github_copilot(
                prompt=prompt,
                github_token=self.GITHUB_COPILOT_TOKEN,
                working_directory=self.WORKING_DIRECTORY,
                model=model,
                session_id=effective_session_id,
                stream_callback=stream_callback,
            )

            if self.activity_id:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] GitHub Copilot response received.",
                    conversation_name=self.conversation_name,
                )

            # Extract response and session_id from result dict
            response_text = result.get("response", "No response received")
            new_session_id = result.get("session_id", "unknown")
            success = result.get("success", False)

            # Build the response with session information
            status = "✅ Success" if success else "⚠️ Completed with issues"

            return (
                f"### GitHub Copilot Response\n\n"
                f"**Status:** {status}\n"
                f"**Session ID:** `{new_session_id}`\n\n"
                f"---\n\n"
                f"{response_text}\n\n"
                f"---\n\n"
                f"*To continue this conversation, use session_id: `{new_session_id}`*"
            )

        except Exception as e:
            logging.error(f"Error calling GitHub Copilot: {str(e)}")
            return f"Error calling GitHub Copilot: {str(e)}"
