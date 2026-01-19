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
        GITHUB_GIT_TOKEN: str = "",
        GITHUB_COPILOT_MODEL: str = "claude-opus-4.5",
        **kwargs,
    ):
        """
        Initialize the GitHub Copilot extension.

        Args:
            GITHUB_COPILOT_TOKEN: A fine-grained GitHub PAT (starts with 'github_pat_')
                                  with "Copilot" account permission enabled.
                                  Create one at:
                                  https://github.com/settings/personal-access-tokens/new

                                  NOTE: Classic PATs (ghp_...) are NOT supported for Copilot!

            GITHUB_GIT_TOKEN: Optional separate token for git/gh CLI operations.
                              Use this if you need to access organization repositories
                              that your Copilot token doesn't have access to.
                              Can be a classic PAT (ghp_...) or org-scoped fine-grained PAT.
                              If not provided, GITHUB_COPILOT_TOKEN will be used for git operations.
        """
        self.GITHUB_COPILOT_TOKEN = GITHUB_COPILOT_TOKEN
        # Use separate git token if provided, otherwise fall back to copilot token
        self.GITHUB_GIT_TOKEN = (
            GITHUB_GIT_TOKEN if GITHUB_GIT_TOKEN else GITHUB_COPILOT_TOKEN
        )
        self.GITHUB_COPILOT_MODEL = (
            GITHUB_COPILOT_MODEL if GITHUB_COPILOT_MODEL else "claude-opus-4.5"
        )
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
        self.conversation_id = kwargs.get("conversation_id", None)
        # Only log when actually being used (not during metadata caching)
        if self.conversation_id:
            logging.info(
                f"GitHub Copilot extension ready: conversation_id={self.conversation_id}, activity_id={self.activity_id}"
            )

    async def ask_github_copilot(
        self,
        prompt: str,
        branch: str = "",
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

        To create a compatible token:
        1. Visit https://github.com/settings/personal-access-tokens/new
        2. Under "Repository access", select repos Copilot can access
        3. Under "Account permissions", enable "Copilot" with Read and write access
        4. Use the generated token (starts with 'github_pat_') as your GITHUB_COPILOT_TOKEN

        Args:
            prompt (str): The detailed request or task to send to GitHub Copilot
            branch (str): Optional branch name to work in. If specified, Copilot will checkout
                          or create this branch before making changes. If not specified,
                          Copilot will create a new feature branch based on the task.
            session_id (str): Optional session ID to resume a previous conversation. If provided,
                              Copilot will continue from where the previous session left off.
                              Leave empty or set to None to start a new session.

        Returns:
            str: The response from GitHub Copilot including any actions taken and their results.
                 The response also includes the session_id which can be used to continue
                 the conversation in future requests.

        Note: If the users request might require coding, use "Ask GitHub Copilot" with a detailed request including links to which repositories to work in if applicable.
        The agent's workspace will be shared with GitHub Copilot. Any data manipulation or coding tasks should use GitHub Copilot.
        """
        model = self.GITHUB_COPILOT_MODEL
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
1. **Before making changes to any repository:**
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

If no changes are made to the repository, there is no need to go through this workflow.     

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
            # Accumulator for streaming content
            streaming_content = []
            message_id = [None]  # Use list to allow modification in nested function

            def send_streaming_update():
                """Send or update the streaming subactivity message."""
                if not self.activity_id or not streaming_content:
                    logging.debug(
                        f"send_streaming_update: skipping (activity_id={self.activity_id}, content_count={len(streaming_content)})"
                    )
                    return

                # Build the accumulated message
                content_str = "\n".join(streaming_content)
                full_message = f"[SUBACTIVITY][{self.activity_id}] **Copilot Activity:**\n{content_str}"

                logging.debug(
                    f"send_streaming_update: conversation_id={self.conversation_id}, message_id={message_id[0]}"
                )

                try:
                    if message_id[0] is None:
                        # First message - create it and store the ID
                        message_id[0] = self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=full_message,
                            conversation_name=self.conversation_name,
                        )
                        logging.info(
                            f"Created streaming message with ID: {message_id[0]}"
                        )
                        # Also broadcast directly to WebSocket for real-time updates
                        if self.conversation_id:
                            logging.info(
                                f"Broadcasting message_added for {message_id[0]} to conversation {self.conversation_id}"
                            )
                            from Conversations import broadcast_message_sync

                            broadcast_message_sync(
                                conversation_id=self.conversation_id,
                                event_type="message_added",
                                message_data={
                                    "id": message_id[0],
                                    "role": self.agent_name,
                                    "message": full_message,
                                },
                            )
                        else:
                            logging.warning(
                                f"No conversation_id available for broadcasting"
                            )
                    else:
                        # Update existing message with accumulated content
                        self.ApiClient.update_conversation_message(
                            message_id=message_id[0],
                            new_message=full_message,
                            conversation_name=self.conversation_name,
                        )
                        # Also broadcast directly to WebSocket for real-time updates
                        if self.conversation_id:
                            logging.debug(
                                f"Broadcasting message_updated for {message_id[0]}"
                            )
                            from Conversations import broadcast_message_sync

                            broadcast_message_sync(
                                conversation_id=self.conversation_id,
                                event_type="message_updated",
                                message_data={
                                    "id": message_id[0],
                                    "role": self.agent_name,
                                    "message": full_message,
                                },
                            )
                except Exception as e:
                    logging.warning(f"Error sending streaming update: {e}")

            # Create a streaming callback that accumulates and updates
            last_update_time = [0]
            callback_count = [0]

            def stream_callback(event: dict):
                import time

                callback_count[0] += 1
                event_type = event.get("type", "")
                content = event.get("content", "")

                if not content:
                    return

                logging.debug(
                    f"Stream callback #{callback_count[0]}: type={event_type}, content={content[:50]}..."
                )

                # Format based on event type
                if event_type == "tool_start":
                    streaming_content.append(f"🔧 {content}")
                    # Immediately update for tool starts so user knows what's happening
                    send_streaming_update()
                    last_update_time[0] = time.time()
                elif event_type == "tool_complete":
                    streaming_content.append(f"✅ {content}")
                    # Immediately update for tool completions
                    send_streaming_update()
                    last_update_time[0] = time.time()
                elif event_type == "error":
                    streaming_content.append(f"❌ Error: {content}")
                    send_streaming_update()
                    last_update_time[0] = time.time()
                else:
                    # thinking, reasoning, output, etc.
                    streaming_content.append(content)
                    # Rate-limit non-tool updates to every 0.5 seconds
                    current_time = time.time()
                    if current_time - last_update_time[0] >= 0.5:
                        send_streaming_update()
                        last_update_time[0] = current_time

            # Normalize session_id (treat "None" string as None)
            effective_session_id = None
            if session_id and session_id.lower() not in ("none", "null", ""):
                effective_session_id = session_id

            # Execute GitHub Copilot in a thread pool to avoid blocking the event loop
            # This allows async broadcasts to happen during execution
            import asyncio
            import concurrent.futures

            def run_copilot():
                return execute_github_copilot(
                    prompt=system_guidelines,
                    github_token=self.GITHUB_COPILOT_TOKEN,
                    working_directory=self.WORKING_DIRECTORY,
                    model=model,
                    session_id=effective_session_id,
                    stream_callback=stream_callback,
                    conversation_id=self.conversation_id,  # Enables persistent containers per conversation
                    git_token=self.GITHUB_GIT_TOKEN,  # Separate token for git/gh operations (org repos)
                )

            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(executor, run_copilot)

            # Send final update with all accumulated content
            if streaming_content:
                send_streaming_update()

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
