"""
OpenAI Codex CLI extension for AGiXT.

Required configuration:

- OPENAI_CODEX_AUTH_JSON_SECRET: The contents of ~/.codex/auth.json from a
  ChatGPT-based `codex login`, or a base64-encoded copy of that file.

Optional configuration:

- OPENAI_CODEX_MODEL: Codex model to use. Defaults to gpt-5.5.
- OPENAI_CODEX_REASONING_EFFORT: low, medium, high, or xhigh. Defaults to medium.
"""

import os
import logging
from Extensions import Extensions
from InternalClient import InternalClient
from safeexecute import execute_openai_codex


class openai_codex(Extensions):
    """
    The OpenAI Codex extension provides access to Codex CLI, OpenAI's agentic
    coding assistant, using ChatGPT login credentials.

    Codex runs in an isolated SafeExecute Docker container with the agent's
    workspace mounted, allowing it to read, modify, create, and delete files in
    that workspace. The default model is gpt-5.5 with medium reasoning effort.

    To configure ChatGPT login, run `codex login` on a trusted machine, then put
    the contents of ~/.codex/auth.json, or a base64-encoded copy of it, into
    OPENAI_CODEX_AUTH_JSON_SECRET.
    """

    CATEGORY = "Development & Code"
    friendly_name = "OpenAI Codex"

    def __init__(
        self,
        OPENAI_CODEX_AUTH_JSON_SECRET: str = "",
        OPENAI_CODEX_MODEL: str = "gpt-5.5",
        OPENAI_CODEX_REASONING_EFFORT: str = "medium",
        **kwargs,
    ):
        """
        Initialize the OpenAI Codex extension.

        Args:
            OPENAI_CODEX_AUTH_JSON_SECRET: Raw or base64-encoded Codex auth.json
                                          created by `codex login` with ChatGPT.
            OPENAI_CODEX_MODEL: Codex model to use. Defaults to gpt-5.5.
            OPENAI_CODEX_REASONING_EFFORT: Reasoning effort. Defaults to medium.
        """
        self.OPENAI_CODEX_AUTH_JSON_SECRET = OPENAI_CODEX_AUTH_JSON_SECRET or os.getenv(
            "OPENAI_CODEX_AUTH_JSON_SECRET",
            os.getenv("OPENAI_CODEX_AUTH_JSON", ""),
        )
        self.OPENAI_CODEX_MODEL = (
            OPENAI_CODEX_MODEL
            or os.getenv("OPENAI_CODEX_MODEL", "gpt-5.5")
            or "gpt-5.5"
        )
        self.OPENAI_CODEX_REASONING_EFFORT = (
            OPENAI_CODEX_REASONING_EFFORT
            or os.getenv("OPENAI_CODEX_REASONING_EFFORT", "medium")
            or "medium"
        )
        self.GITHUB_GIT_TOKEN = kwargs.get("GITHUB_GIT_TOKEN") or os.getenv(
            "GITHUB_GIT_TOKEN", ""
        )
        self.commands = {
            "Ask OpenAI Codex": self.ask_openai_codex,
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

    async def ask_openai_codex(
        self,
        prompt: str = "",
        branch: str = "",
        session_id: str = None,
        **kwargs,
    ) -> str:
        """
        Send a request to OpenAI Codex CLI.

        Args:
            prompt (str): The detailed instructions to send to Codex describing
                          what you want it to do. Always pass this as `prompt`.
                          Aliases `task`, `instructions`, `request`, `query`,
                          `message`, and `input` are accepted for robustness.
            branch (str): Optional branch name to work in. If specified, Codex
                          will be instructed to checkout or create it before
                          making changes.
            session_id (str): Optional Codex session ID to resume. Leave empty
                              to start a new session.

        Returns:
            str: The response from Codex, including the session_id when available.

        Use this command for codebase changes, debugging, refactoring, tests,
        repository work, file edits, and other AI-assisted coding tasks where
        OpenAI Codex should operate on the agent's workspace.

        Argument names matter. When emitting the execute block for this command,
        the XML tag for the instructions MUST be `<prompt>`. Valid argument tags
        are `<prompt>`, `<branch>`, and `<session_id>`.
        """
        if (not prompt) or (
            isinstance(prompt, str) and prompt.strip().lower() in ("", "none", "null")
        ):
            for alias in (
                "task",
                "instructions",
                "instruction",
                "request",
                "query",
                "message",
                "input",
                "user_input",
                "description",
                "details",
                "content",
            ):
                value = kwargs.get(alias)
                if value and str(value).strip().lower() not in ("none", "null"):
                    logging.info(
                        f"[OpenAI Codex] Received '{alias}' arg; treating as 'prompt'. "
                        "Please call this command with the canonical 'prompt' parameter."
                    )
                    prompt = value
                    break

        prompt_str = str(prompt).strip() if prompt else ""
        if not prompt_str or prompt_str.lower() in ("none", "null"):
            try:
                conversation = self.ApiClient.get_conversation(
                    conversation_name=self.conversation_name,
                    conversation_id=self.conversation_id,
                    limit=20,
                    page=1,
                )
                interactions = conversation.get("interactions", [])
                for msg in reversed(interactions):
                    if msg.get("role", "").upper() == "USER":
                        user_message = msg.get("message", "").strip()
                        if user_message:
                            prompt = user_message
                            break
            except Exception as e:
                logging.warning(f"Failed to retrieve user input for empty prompt: {e}")

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
- If code changes are needed in a git repository, create a descriptive feature branch
- Do not work directly on `main` or `master` branches for repository changes
"""

        system_guidelines = f"""
# Development Workflow Guidelines

You are working in a git-enabled workspace through AGiXT and SafeExecute.
Follow these guidelines for all code changes:

{branch_instruction}

## Workflow
1. Inspect the relevant files before editing.
2. Follow the repository's existing style and conventions.
3. Keep changes scoped to the user's request.
4. Add or update tests when the change warrants it.
5. Run appropriate validation when feasible.
6. If repository changes are made, commit them with a clear message.

## Safety
- Do not expose credentials or tokens in output.
- Do not modify files outside the requested workspace.
- If a request requires unavailable external credentials, explain what remains untested.

---

# User Request

{prompt}
"""

        try:
            streaming_content = []
            message_id = [None]

            def send_streaming_update():
                if not self.activity_id or not streaming_content:
                    return

                content_str = "\n".join(streaming_content)
                full_message = (
                    f"[SUBACTIVITY][{self.activity_id}] **Codex Activity:**\n"
                    f"{content_str}"
                )

                try:
                    if message_id[0] is None:
                        message_id[0] = self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=full_message,
                            conversation_name=self.conversation_name,
                        )
                        if self.conversation_id:
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
                        self.ApiClient.update_conversation_message(
                            message_id=message_id[0],
                            new_message=full_message,
                            conversation_name=self.conversation_name,
                        )
                        if self.conversation_id:
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
                    logging.warning(f"Error sending Codex streaming update: {e}")

            last_update_time = [0]

            def stream_callback(event: dict):
                import time

                content = event.get("content", "")
                if not content:
                    return

                event_type = event.get("type", "")
                if event_type == "tool_start":
                    streaming_content.append(f"Tool: {content}")
                    send_streaming_update()
                    last_update_time[0] = time.time()
                elif event_type == "tool_complete":
                    streaming_content.append(f"Done: {content}")
                    send_streaming_update()
                    last_update_time[0] = time.time()
                elif event_type == "error":
                    streaming_content.append(f"Error: {content}")
                    send_streaming_update()
                    last_update_time[0] = time.time()
                elif event_type == "info":
                    streaming_content.append(content)
                    send_streaming_update()
                    last_update_time[0] = time.time()
                else:
                    streaming_content.append(content)
                    current_time = time.time()
                    if current_time - last_update_time[0] >= 0.5:
                        send_streaming_update()
                        last_update_time[0] = current_time

            effective_session_id = None
            if session_id and session_id.lower() not in ("none", "null", ""):
                effective_session_id = session_id

            import asyncio
            import concurrent.futures

            def run_codex():
                return execute_openai_codex(
                    prompt=system_guidelines,
                    codex_auth_json=self.OPENAI_CODEX_AUTH_JSON_SECRET,
                    working_directory=self.WORKING_DIRECTORY,
                    model=self.OPENAI_CODEX_MODEL,
                    reasoning_effort=self.OPENAI_CODEX_REASONING_EFFORT,
                    session_id=effective_session_id,
                    stream_callback=stream_callback,
                    conversation_id=self.conversation_id,
                    git_token=self.GITHUB_GIT_TOKEN,
                )

            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(executor, run_codex)

            if streaming_content:
                send_streaming_update()

            response_text = result.get("response", "No response received")
            new_session_id = result.get("session_id", "unknown")
            success = result.get("success", False)
            status = "Success" if success else "Completed with issues"

            return (
                f"### OpenAI Codex Response\n\n"
                f"**Status:** {status}\n"
                f"**Session ID:** `{new_session_id}`\n\n"
                f"---\n\n"
                f"{response_text}\n\n"
                f"---\n\n"
                f"*To continue this conversation, use session_id: `{new_session_id}`*"
            )

        except Exception as e:
            logging.error(f"Error calling OpenAI Codex: {e}")
            return f"Error calling OpenAI Codex: {e}"
