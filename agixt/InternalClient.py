"""
InternalClient - A direct implementation of the AGiXTSDK interface for internal use.

This class provides the same interface as AGiXTSDK but calls internal methods directly,
avoiding unnecessary HTTP round-trips when the SDK is used within the AGiXT backend itself.

The class implements lazy loading to avoid circular imports - components are only imported
when they are first needed.
"""

import os
import logging
from typing import Dict, List, Any, Optional
from Globals import getenv

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class InternalClient:
    """
    Internal client that provides the same interface as AGiXTSDK but calls
    internal methods directly without HTTP round-trips.

    This is used when AGiXT components need to call each other internally
    rather than going through the REST API.
    """

    def __init__(self, api_key: str = None, user: str = None):
        """
        Initialize the internal client.

        Args:
            api_key: The API key/JWT token for authentication
            user: The user email (if already resolved)
        """
        if api_key:
            api_key = str(api_key).replace("Bearer ", "").replace("bearer ", "")
        self.api_key = api_key
        self._user = user
        # Mimic SDK headers structure for compatibility
        self.headers = {
            "Authorization": api_key or "",
            "Content-Type": "application/json",
        }
        # Lazy-loaded components
        self._agent_class = None
        self._chain_class = None
        self._conversations_class = None
        self._agixt_class = None
        self._prompts_class = None

    @property
    def user(self) -> str:
        """Get the user email from the API key if not already set."""
        if self._user is None and self.api_key:
            from ApiClient import verify_api_key

            try:
                self._user = verify_api_key(self.api_key)
            except:
                from Globals import DEFAULT_USER

                self._user = DEFAULT_USER
        return self._user or getenv("DEFAULT_USER") or "user"

    def _get_agent_class(self):
        """Lazy load Agent class to avoid circular imports."""
        if self._agent_class is None:
            from Agent import Agent

            self._agent_class = Agent
        return self._agent_class

    def _get_chain_class(self):
        """Lazy load Chain class to avoid circular imports."""
        if self._chain_class is None:
            from Chain import Chain

            self._chain_class = Chain
        return self._chain_class

    def _get_conversations_class(self):
        """Lazy load Conversations class to avoid circular imports."""
        if self._conversations_class is None:
            from Conversations import Conversations

            self._conversations_class = Conversations
        return self._conversations_class

    def _get_prompts_class(self):
        """Lazy load Prompts class to avoid circular imports."""
        if self._prompts_class is None:
            from Prompts import Prompts

            self._prompts_class = Prompts
        return self._prompts_class

    def _get_agixt_class(self):
        """Lazy load AGiXT class to avoid circular imports."""
        if self._agixt_class is None:
            from XT import AGiXT

            self._agixt_class = AGiXT
        return self._agixt_class

    def _get_agent(self, agent_id: str = None, agent_name: str = None):
        """Get an Agent instance."""
        Agent = self._get_agent_class()
        if agent_id:
            return Agent(agent_id=agent_id, user=self.user, ApiClient=self)
        elif agent_name:
            return Agent(agent_name=agent_name, user=self.user, ApiClient=self)
        else:
            return Agent(agent_name="AGiXT", user=self.user, ApiClient=self)

    # ========== Agent Methods ==========

    def prompt_agent(
        self,
        agent_id: str = None,
        agent_name: str = None,
        prompt_name: str = "Think About It",
        prompt_args: dict = None,
        parent_activity_id: str = None,
    ) -> str:
        """
        Send a prompt to an agent directly without HTTP round-trip.

        Args:
            agent_id: The agent's UUID (preferred)
            agent_name: The agent's name (fallback)
            prompt_name: Name of the prompt to use
            prompt_args: Arguments to pass to the prompt
            parent_activity_id: Optional ID of parent thinking activity to nest under

        Returns:
            The agent's response as a string
        """
        import asyncio
        from Models import ChatCompletions

        if prompt_args is None:
            prompt_args = {}

        # Get agent name if we only have ID
        if agent_id and not agent_name:
            agent = self._get_agent(agent_id=agent_id)
            agent_name = agent.agent_name
        elif not agent_name:
            agent_name = "AGiXT"

        # Get conversation name from prompt args
        conversation_name = prompt_args.get("conversation_name", "-")
        if "conversation_name" in prompt_args:
            del prompt_args["conversation_name"]

        # Get user input
        user_input = prompt_args.get("user_input", "")

        # Create the AGiXT instance
        AGiXT = self._get_agixt_class()
        agixt = AGiXT(
            user=self.user,
            agent_name=agent_name,
            api_key=self.api_key,
            conversation_name=conversation_name,
        )

        # Handle TTS flag
        if "tts" in prompt_args:
            prompt_args["voice_response"] = str(prompt_args["tts"]).lower() == "true"
            del prompt_args["tts"]

        # Handle context_results -> injected_memories
        if "context_results" in prompt_args:
            prompt_args["injected_memories"] = int(prompt_args["context_results"])
            del prompt_args["context_results"]

        # Set prompt name
        prompt_args["prompt_name"] = prompt_name
        if "prompt_category" not in prompt_args:
            prompt_args["prompt_category"] = "Default"

        # Build messages
        message_data = {
            "role": "user",
            **{k: v for k, v in prompt_args.items() if k != "user_input"},
            "prompt_args": prompt_args,
            "content": user_input,
        }
        # Pass parent_activity_id to keep subactivities within the parent's thinking activity
        if parent_activity_id:
            message_data["parent_activity_id"] = parent_activity_id
        messages = [message_data]

        # Run the prompt
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # We're already in an async context, create a task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    agixt.chat_completions(
                        prompt=ChatCompletions(
                            model=agent_name,
                            user=conversation_name,
                            messages=messages,
                        )
                    ),
                )
                response = future.result()
        else:
            response = loop.run_until_complete(
                agixt.chat_completions(
                    prompt=ChatCompletions(
                        model=agent_name,
                        user=conversation_name,
                        messages=messages,
                    )
                )
            )

        if isinstance(response, dict) and "choices" in response:
            return response["choices"][0]["message"]["content"]
        return str(response)

    def add_agent(
        self,
        agent_name: str,
        settings: Dict[str, Any] = None,
        commands: Dict[str, Any] = None,
        training_urls: List[str] = None,
    ) -> Dict[str, Any]:
        """Create a new agent directly."""
        from Agent import add_agent

        return add_agent(
            agent_name=agent_name,
            provider_settings=settings or {},
            commands=commands or {},
            user=self.user,
        )

    def delete_agent(self, agent_id: str) -> Dict[str, Any]:
        """Delete an agent by ID."""
        from Agent import delete_agent

        result, status = delete_agent(agent_id=agent_id, user=self.user)
        return result

    def rename_agent(self, agent_id: str, new_name: str) -> str:
        """Rename an agent by ID."""
        from Agent import rename_agent, get_agent_name_by_id

        old_name = get_agent_name_by_id(agent_id=agent_id, user=self.user)
        result, status = rename_agent(
            agent_name=old_name, new_name=new_name, user=self.user
        )
        return result.get("message", "")

    def update_agent_settings(
        self, agent_id: str, settings: Dict[str, Any], agent_name: str = ""
    ) -> str:
        """Update agent settings by ID."""
        agent = self._get_agent(agent_id=agent_id)
        return agent.update_agent_config(new_config=settings, config_key="settings")

    def update_agent_commands(
        self,
        agent_id: str = None,
        agent_name: str = None,
        commands: Dict[str, bool] = None,
    ) -> str:
        """Update agent commands."""
        if agent_id:
            agent = self._get_agent(agent_id=agent_id)
        else:
            agent = self._get_agent(agent_name=agent_name)
        return agent.update_agent_config(
            new_config=commands or {}, config_key="commands"
        )

    def get_agent_settings(self, agent_id: str) -> Dict[str, Any]:
        """Get agent settings by ID."""
        agent = self._get_agent(agent_id=agent_id)
        return agent.AGENT_CONFIG.get("settings", {})

    def get_commands(self, agent_id: str) -> Dict[str, bool]:
        """Get agent commands by ID."""
        agent = self._get_agent(agent_id=agent_id)
        return agent.AGENT_CONFIG.get("commands", {})

    # ========== Chain Methods ==========

    def get_chains(self) -> List[str]:
        """Get all available chains."""
        Chain = self._get_chain_class()
        chain = Chain(user=self.user)
        return chain.get_chains()

    def get_chain(self, chain_name: str) -> Dict[str, Any]:
        """Get chain details by name."""
        Chain = self._get_chain_class()
        chain = Chain(user=self.user)
        return chain.get_chain(chain_name=chain_name)

    def add_chain(self, chain_name: str) -> Dict[str, Any]:
        """Create a new chain."""
        Chain = self._get_chain_class()
        chain = Chain(user=self.user)
        return chain.add_chain(chain_name=chain_name)

    def delete_chain(self, chain_name: str) -> Dict[str, Any]:
        """Delete a chain."""
        Chain = self._get_chain_class()
        chain = Chain(user=self.user)
        return chain.delete_chain(chain_name=chain_name)

    def add_step(
        self,
        chain_name: str,
        step_number: int,
        agent_name: str,
        prompt_type: str,
        prompt: dict,
    ) -> Dict[str, Any]:
        """Add a step to a chain."""
        Chain = self._get_chain_class()
        chain = Chain(user=self.user)
        return chain.add_chain_step(
            chain_name=chain_name,
            step_number=step_number,
            agent_name=agent_name,
            prompt_type=prompt_type,
            prompt=prompt,
        )

    def run_chain(
        self,
        chain_name: str,
        user_input: str = "",
        agent_id: str = None,
        agent_name: str = None,
        all_responses: bool = False,
        from_step: int = 1,
        chain_args: dict = None,
    ) -> str:
        """Run a chain directly without HTTP round-trip."""
        import asyncio

        # Get agent name from ID if needed
        if agent_id and not agent_name:
            agent = self._get_agent(agent_id=agent_id)
            agent_name = agent.agent_name
        elif not agent_name:
            agent_name = "AGiXT"

        if chain_args is None:
            chain_args = {}

        # Get conversation name from chain args
        conversation_name = chain_args.get("conversation_name", "-")

        # Extract log_output from chain_args if present (defaults to True)
        # This is important when chains are executed as commands - the caller
        # sets log_output=False to avoid double-logging
        log_output = chain_args.pop("log_output", True)
        if isinstance(log_output, str):
            log_output = log_output.lower() not in ["false", "0", "no"]

        # Create AGiXT instance
        AGiXT = self._get_agixt_class()
        agixt = AGiXT(
            user=self.user,
            agent_name=agent_name,
            api_key=self.api_key,
            conversation_name=conversation_name,
        )

        # Run the chain
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    agixt.execute_chain(
                        chain_name=chain_name,
                        user_input=user_input,
                        agent_override=agent_name,
                        from_step=from_step,
                        chain_args=chain_args,
                        log_output=log_output,
                    ),
                )
                response = future.result()
        else:
            response = loop.run_until_complete(
                agixt.execute_chain(
                    chain_name=chain_name,
                    user_input=user_input,
                    agent_override=agent_name,
                    from_step=from_step,
                    chain_args=chain_args,
                    log_output=log_output,
                )
            )

        return str(response) if response else ""

    # ========== Conversation Methods ==========

    def new_conversation_message(
        self,
        role: str,
        message: str,
        conversation_name: str = "-",
    ) -> Dict[str, Any]:
        """Add a new message to a conversation."""
        Conversations = self._get_conversations_class()
        c = Conversations(conversation_name=conversation_name, user=self.user)
        return c.log_interaction(role=role, message=message)

    def update_conversation_message(
        self,
        message_id: str,
        new_message: str,
        conversation_name: str = "-",
    ) -> None:
        """Update an existing message in a conversation."""
        Conversations = self._get_conversations_class()
        c = Conversations(conversation_name=conversation_name, user=self.user)
        return c.update_message_by_id(message_id=message_id, new_message=new_message)

    def get_conversation(
        self,
        conversation_name: str = None,
        conversation_id: str = None,
        limit: int = 100,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """Get conversation messages."""
        Conversations = self._get_conversations_class()
        c = Conversations(
            conversation_name=conversation_name,
            conversation_id=conversation_id,
            user=self.user,
        )
        return c.get_conversation(limit=limit, page=page)

    def delete_conversation(
        self, conversation_name: str = None, conversation_id: str = None
    ) -> Dict[str, Any]:
        """Delete a conversation."""
        Conversations = self._get_conversations_class()
        c = Conversations(
            conversation_name=conversation_name,
            conversation_id=conversation_id,
            user=self.user,
        )
        return c.delete_conversation()

    # ========== Memory Methods ==========

    def learn_url(
        self, agent_id: str, url: str, collection_number: str = "0"
    ) -> Dict[str, Any]:
        """Learn from a URL."""
        import asyncio
        from Memories import Memories

        agent = self._get_agent(agent_id=agent_id)
        memory = Memories(
            agent_name=agent.agent_name,
            agent_config=agent.AGENT_CONFIG,
            collection_number=collection_number,
            ApiClient=self,
            user=self.user,
        )

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, memory.read_url(url=url))
                result = future.result()
        else:
            result = loop.run_until_complete(memory.read_url(url=url))

        return {"message": f"URL {url} learned successfully"}

    # ========== Prompt Methods ==========

    def get_prompts(self, prompt_category: str = "Default") -> List[str]:
        """Get available prompts."""
        Prompts = self._get_prompts_class()
        p = Prompts(user=self.user)
        return p.get_prompts(prompt_category=prompt_category)

    def get_prompt(self, prompt_name: str, prompt_category: str = "Default") -> str:
        """Get a prompt by name."""
        Prompts = self._get_prompts_class()
        p = Prompts(user=self.user)
        return p.get_prompt(prompt_name=prompt_name, prompt_category=prompt_category)

    def get_prompt_args(
        self, prompt_name: str, prompt_category: str = "Default"
    ) -> List[str]:
        """Get prompt arguments."""
        Prompts = self._get_prompts_class()
        p = Prompts(user=self.user)
        prompt = p.get_prompt(prompt_name=prompt_name, prompt_category=prompt_category)
        return p.get_prompt_args(prompt_text=prompt)

    # ========== Auth Methods ==========

    def login(self, email: str, otp: str) -> str:
        """
        Login with email and OTP, setting the authorization header.

        This directly validates the OTP and generates a JWT token without
        making an HTTP request.

        Args:
            email: User's email address
            otp: One-time password from TOTP

        Returns:
            The JWT token if successful, None otherwise
        """
        from DB import get_session, User
        import pyotp
        import jwt
        from datetime import datetime, timedelta

        session = get_session()
        try:
            user = session.query(User).filter(User.email == email).first()
            if not user:
                return None

            # Verify the OTP
            totp = pyotp.TOTP(user.mfa_token)
            if not totp.verify(otp, valid_window=2):
                return None

            # Generate JWT token - similar to what MagicalAuth.send_magic_link returns
            agixt_api_key = os.getenv("AGIXT_API_KEY", "")
            token_data = {
                "sub": str(user.id),
                "email": user.email,
                "admin": user.admin if hasattr(user, "admin") else False,
                "exp": datetime.utcnow()
                + timedelta(days=365),  # Long-lived internal token
                "iat": datetime.utcnow().timestamp(),
            }
            token = jwt.encode(token_data, agixt_api_key, algorithm="HS256")

            # Update instance state
            self.api_key = token
            self._user = email
            self.headers = {
                "Authorization": token,
                "Content-Type": "application/json",
            }

            return token
        finally:
            session.close()

    async def generate_image(
        self,
        prompt: str,
        model: str = "dall-e-3",
        n: int = 1,
        size: str = "1024x1024",
        response_format: str = "url",
    ) -> Dict[str, Any]:
        """
        Generate an image from a text prompt.

        Args:
            prompt: The text prompt to generate an image from
            model: The model to use (defaults to dall-e-3, but AGiXT uses this as agent name)
            n: Number of images to generate
            size: Size of the generated image
            response_format: Format of the response (url or b64_json)

        Returns:
            Dict containing the generated image URL(s)
        """
        import time

        Agent = self._get_agent_class()
        agent = Agent(agent_name=model, user=self.user, ApiClient=self)

        images = []
        if int(n) > 1:
            for i in range(n):
                image = await agent.generate_image(prompt=prompt)
                images.append({"url": image})
            return {
                "created": int(time.time()),
                "data": images,
            }

        image = await agent.generate_image(prompt=prompt)
        return {
            "created": int(time.time()),
            "data": [{"url": image}],
        }
