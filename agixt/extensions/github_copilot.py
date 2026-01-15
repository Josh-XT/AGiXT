import os
import logging
from Extensions import Extensions
from InternalClient import InternalClient
from Globals import install_package_if_missing

install_package_if_missing("safeexecute")

from safeexecute import execute_github_copilot

"""
Required environment variables:

- GITHUB_COPILOT_TOKEN: A **fine-grained** GitHub Personal Access Token (PAT) with the 
  "Copilot" account permission enabled.

IMPORTANT: Classic PATs (tokens starting with 'ghp_') are NOT supported!
You MUST use a fine-grained PAT (tokens starting with 'github_pat_').

To create a valid token:
1. Visit https://github.com/settings/personal-access-tokens/new
2. Give your token a name and set expiration (max 1 year)
3. Under "Repository access", select "All repositories" or specific repos you want Copilot to access
4. Under "Permissions" → "Account permissions", find "Copilot" and select "Read and write" access
5. Click "Generate token"
6. Copy the token (starts with 'github_pat_') and use it as GITHUB_COPILOT_TOKEN

Requirements:
- An active GitHub Copilot subscription (Individual, Business, or Enterprise)
- A fine-grained PAT (NOT a classic PAT) with Copilot permissions
- If using Copilot via an organization, the organization admin must enable Copilot CLI
"""


class github_copilot(Extensions):
    """
    The GitHub Copilot extension provides access to GitHub Copilot CLI, an agentic
    coding assistant that can read, modify, create, and delete files in your workspace.

    GitHub Copilot runs in an isolated Docker container (SafeExecute) with your
    workspace mounted, allowing it to safely make changes to the codebase.

    IMPORTANT: This extension requires a **fine-grained** Personal Access Token (PAT)
    that starts with 'github_pat_'. Classic PATs starting with 'ghp_' are NOT supported
    by the Copilot CLI.

    Create a fine-grained PAT at: https://github.com/settings/personal-access-tokens/new
    Enable the "Copilot" permission under "Account permissions".
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
            GITHUB_COPILOT_TOKEN: A fine-grained GitHub PAT (starts with 'github_pat_')
                                  with "Copilot" account permission enabled.
                                  Create one at:
                                  https://github.com/settings/personal-access-tokens/new

                                  NOTE: Classic PATs (ghp_...) are NOT supported!
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
        branch: str = "",
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

        Note: This command requires a **fine-grained** GitHub Personal Access Token (PAT)
        that starts with 'github_pat_'. Classic PATs (ghp_...) are NOT supported.

        Available models: claude-opus-4.5, claude-sonnet-4, gpt-4.1, gpt-5, gpt-5-mini

        To create a compatible token:
        1. Visit https://github.com/settings/personal-access-tokens/new
        2. Under "Repository access", select repos Copilot can access
        3. Under "Account permissions", enable "Copilot" with Read and write access
        4. Use the generated token (starts with 'github_pat_') as your GITHUB_COPILOT_TOKEN

        Args:
            prompt (str): The request or task to send to GitHub Copilot
            branch (str): Optional branch name to work in. If specified, Copilot will checkout
                          or create this branch before making changes. If not specified,
                          Copilot will create a new feature branch based on the task.
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
                "To use GitHub Copilot, you need a **fine-grained** Personal Access Token (PAT) "
                "with the 'Copilot' account permission.\n\n"
                "IMPORTANT: Classic PATs (starting with 'ghp_') are NOT supported!\n"
                "You must use a fine-grained PAT (starting with 'github_pat_').\n\n"
                "To create a compatible token:\n"
                "1. Visit https://github.com/settings/personal-access-tokens/new\n"
                "2. Give your token a name and set an expiration\n"
                "3. Under 'Repository access', select repositories Copilot can access\n"
                "4. Under 'Account permissions', find 'Copilot' and select 'Read and write'\n"
                "5. Generate the token (should start with 'github_pat_')\n"
                "6. Configure it as your GITHUB_COPILOT_TOKEN\n\n"
                "You must also have an active GitHub Copilot subscription."
            )

        # Validate token format
        if self.GITHUB_COPILOT_TOKEN.startswith("ghp_"):
            return (
                "Error: Classic Personal Access Tokens are not supported by GitHub Copilot CLI.\n\n"
                "Your token starts with 'ghp_', which indicates a classic PAT.\n"
                "The Copilot CLI requires a **fine-grained** PAT (starting with 'github_pat_').\n\n"
                "To create a compatible token:\n"
                "1. Visit https://github.com/settings/personal-access-tokens/new\n"
                "2. Give your token a name and set an expiration\n"
                "3. Under 'Repository access', select repositories Copilot can access\n"
                "4. Under 'Account permissions', find 'Copilot' and select 'Read and write'\n"
                "5. Generate the token (should start with 'github_pat_')\n"
                "6. Update your GITHUB_COPILOT_TOKEN setting with the new token"
            )

        # Build system guidelines for GitHub Copilot
        branch_instruction = ""
        if branch and branch.strip():
            branch_instruction = f"""
## Branch Instructions
Work in the branch: `{branch.strip()}`
- If the branch exists, checkout to it
- If the branch does not exist, create it from the current HEAD and checkout to it
"""
        else:
            branch_instruction = """
## Branch Instructions
- Create a new feature branch with a descriptive name based on the task (e.g., `feature/add-user-auth`, `fix/login-bug`)
- Do NOT work directly on `main` or `master` branches
"""

        system_guidelines = f"""
# Development Workflow Guidelines

You are working in a git-enabled workspace. Follow these guidelines for all code changes:

{branch_instruction}

## Git Workflow
1. **Before making changes:**
   - Check current branch with `git branch`
   - Ensure you're on the correct working branch (not main/master)
   - Pull latest changes if the branch exists remotely: `git pull origin <branch> --rebase`

2. **While working:**
   - Make atomic commits with clear, descriptive messages
   - Commit related changes together
   - Test your changes before committing

3. **After completing changes:**
   - Run any available tests to verify changes work correctly
   - Stage and commit all changes: `git add -A && git commit -m "descriptive message"`
   - Push the branch to remote: `git push -u origin <branch-name>`

4. **Create a Pull Request:**
   - After pushing, use the GitHub CLI to create a pull request:
     ```
     gh pr create --title "Brief description of changes" --body "Detailed explanation of what was changed and why"
     ```
   - Include a clear title summarizing the changes
   - Write a detailed description in the PR body explaining:
     - What changes were made
     - Why they were made
     - How to test them
     - Any breaking changes or migration steps needed

## Code Quality
- Follow existing code style and conventions in the repository
- Add or update tests for new functionality
- Update documentation if needed
- Handle errors gracefully

---

# User Request

{prompt}
"""

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
            # Use system_guidelines which includes the workflow instructions + user prompt
            result = execute_github_copilot(
                prompt=system_guidelines,
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
