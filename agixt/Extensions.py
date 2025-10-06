import importlib
import os
import glob
from inspect import signature, Parameter
import logging
import inspect
from Globals import getenv, DEFAULT_USER
from MagicalAuth import get_user_id, get_sso_credentials
from agixtsdk import AGiXTSDK
from Prompts import Prompts
from DB import (
    get_session,
    Chain as ChainDB,
    ChainStep,
    Agent,
    Argument,
    ChainStepArgument,
    Prompt,
    Command,
    User,
)
from WebhookManager import webhook_emitter
from ExtensionsHub import (
    find_extension_files,
    import_extension_module,
    get_extension_class_name,
)

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
DISABLED_EXTENSIONS = getenv("DISABLED_EXTENSIONS").replace(" ", "").split(",")

# Cache for extension modules to prevent multiple imports
_extension_module_cache = {}
_extension_discovery_cache = None


def _get_cached_extension_module(command_file):
    """Get extension module from cache or import if not cached"""
    global _extension_module_cache

    if command_file in _extension_module_cache:
        return _extension_module_cache[command_file]

    module = import_extension_module(command_file)
    if module is not None:
        _extension_module_cache[command_file] = module

    return module


def _get_cached_extension_files():
    """Get extension files from cache or discover if not cached"""
    global _extension_discovery_cache

    if _extension_discovery_cache is None:
        _extension_discovery_cache = find_extension_files()

    return _extension_discovery_cache


def invalidate_extension_cache():
    """Invalidate the extension discovery cache to force rediscovery"""
    global _extension_discovery_cache, _extension_module_cache
    _extension_discovery_cache = None
    _extension_module_cache.clear()

    # Reset router registration flag to force re-registration with hub extensions
    try:
        import app

        app._extension_routers_registered = False
        logging.info("Extension router registration flag reset")
    except Exception as e:
        logging.debug(f"Could not reset router registration flag: {e}")

    logging.info("Extension cache invalidated - will rediscover extensions")


class Extensions:
    # Class attribute for defining webhook events - extensions can override this
    webhook_events = []

    def __init__(
        self,
        agent_name="",
        agent_id=None,
        agent_config=None,
        conversation_name="",
        conversation_id=None,
        ApiClient=None,
        api_key=None,
        user=DEFAULT_USER,
    ):
        self.agent_config = agent_config
        self.agent_name = agent_name if agent_name else "gpt4free"
        self.conversation_name = conversation_name
        self.conversation_id = conversation_id
        self.agent_id = agent_id
        self.ApiClient = (
            ApiClient
            if ApiClient
            else AGiXTSDK(base_uri=getenv("API_URL"), api_key=api_key)
        )
        self.api_key = api_key
        self.user = user
        self.user_id = get_user_id(self.user)
        self.prompts = Prompts(user=self.user)
        self.chains = self.get_chains()
        self.chains_with_args = self.get_chains_with_args()
        if agent_config != None:
            if "commands" not in self.agent_config:
                self.agent_config["commands"] = {}
            if self.agent_config["commands"] == None:
                self.agent_config["commands"] = {}
        else:
            self.agent_config = {
                "settings": {},
                "commands": {},
            }
        self.commands = self.load_commands()
        self.available_commands = self.get_available_commands()

    async def execute_chain(self, **kwargs):
        chain_name = kwargs.get("chain_name", "")
        user_input = kwargs.get("user_input", "")
        if "chain_name" in kwargs:
            del kwargs["chain_name"]
        return self.ApiClient.run_chain(
            chain_name=chain_name,
            user_input=user_input,
            chain_args=kwargs,
        )

    def get_available_commands(self):
        if self.commands == []:
            return []
        available_commands = []
        for command in self.commands:
            friendly_name, command_module, command_name, command_args = command
            if friendly_name not in self.agent_config["commands"]:
                self.agent_config["commands"][friendly_name] = "false"

            # Return all commands with their enabled status, don't filter here
            enabled = (
                str(self.agent_config["commands"][friendly_name]).lower() == "true"
            )
            available_commands.append(
                {
                    "friendly_name": friendly_name,
                    "name": command_name,
                    "args": command_args,
                    "enabled": enabled,
                }
            )
        return available_commands

    def get_enabled_commands(self):
        enabled_commands = []
        for command in self.available_commands:
            if command["enabled"]:
                enabled_commands.append(command)
        return enabled_commands

    def get_command_args(self, command_name: str):
        extensions = self.get_extensions()
        for extension in extensions:
            for command in extension["commands"]:
                if command["friendly_name"] == command_name:
                    return command["command_args"]
        return {}

    def get_chains(self):
        session = get_session()
        chains = session.query(ChainDB).filter(ChainDB.user_id == self.user_id).all()
        chain_list = []
        for chain in chains:
            chain_list.append(chain.name)
        session.close()
        return chain_list

    def get_chain(self, chain_name):
        session = get_session()
        chain_name = chain_name.replace("%20", " ")
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        chain_db = (
            session.query(ChainDB)
            .filter(ChainDB.user_id == user_data.id, ChainDB.name == chain_name)
            .first()
        )
        if chain_db is None:
            chain_db = (
                session.query(ChainDB)
                .filter(
                    ChainDB.name == chain_name,
                    ChainDB.user_id == self.user_id,
                )
                .first()
            )
        if chain_db is None:
            session.close()
            return []
        chain_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain_db.id)
            .order_by(ChainStep.step_number)
            .all()
        )

        steps = []
        for step in chain_steps:
            agent_name = session.query(Agent).get(step.agent_id).name
            prompt = {}
            if step.target_chain_id:
                prompt["chain_name"] = (
                    session.query(ChainDB).get(step.target_chain_id).name
                )
            elif step.target_command_id:
                prompt["command_name"] = (
                    session.query(Command).get(step.target_command_id).name
                )
            elif step.target_prompt_id:
                prompt["prompt_name"] = (
                    session.query(Prompt).get(step.target_prompt_id).name
                )

            # Retrieve argument data for the step
            arguments = (
                session.query(Argument, ChainStepArgument)
                .join(ChainStepArgument, ChainStepArgument.argument_id == Argument.id)
                .filter(ChainStepArgument.chain_step_id == step.id)
                .all()
            )

            prompt_args = {}
            for argument, chain_step_argument in arguments:
                prompt_args[argument.name] = chain_step_argument.value

            prompt.update(prompt_args)

            step_data = {
                "step": step.step_number,
                "agent_name": agent_name,
                "prompt_type": step.prompt_type,
                "prompt": prompt,
            }
            steps.append(step_data)

        chain_data = {
            "id": chain_db.id,
            "chain_name": chain_db.name,
            "steps": steps,
            "description": chain_db.description if chain_db.description else "",
        }
        session.close()
        return chain_data

    def get_chains_with_args(self):
        skip_args = [
            "command_list",
            "context",
            "COMMANDS",
            "date",
            "conversation_history",
            "agent_name",
            "working_directory",
            "helper_agent_name",
        ]
        chains = []
        for chain_name in self.chains:
            chain_data = self.get_chain(chain_name=chain_name)
            description = chain_data["description"]
            steps = chain_data["steps"]
            prompt_args = []
            for step in steps:
                try:
                    prompt = step["prompt"]
                    if "chain_name" in prompt:
                        if "command_name" not in prompt:
                            prompt["command_name"] = prompt["chain_name"]
                    prompt_category = (
                        prompt["category"] if "category" in prompt else "Default"
                    )
                    if "prompt_name" in prompt:
                        prompt_content = self.prompts.get_prompt(
                            prompt_name=prompt["prompt_name"],
                            prompt_category=prompt_category,
                        )
                        args = self.prompts.get_prompt_args(
                            prompt_text=prompt_content,
                        )
                    elif "command_name" in prompt:
                        args = self.get_command_args(
                            command_name=prompt["command_name"]
                        )
                    else:
                        args = []
                    for arg in args:
                        if arg not in prompt_args and arg not in skip_args:
                            prompt_args.append(arg)
                except Exception as e:
                    logging.error(f"Error getting chain args for {chain_name}: {e}")
            chains.append(
                {
                    "chain_name": chain_name,
                    "description": description,
                    "args": prompt_args,
                }
            )
        return chains

    def load_commands(self):
        try:
            settings = self.agent_config["settings"]
        except:
            settings = {}
        commands = []
        # Use cached extension discovery
        command_files = _get_cached_extension_files()
        for command_file in command_files:
            # Import the module using cached helper function
            module = _get_cached_extension_module(command_file)
            if module is None:
                continue

            # Get the expected class name from the module
            class_name = get_extension_class_name(os.path.basename(command_file))

            # Check if module is in disabled extensions
            if class_name in DISABLED_EXTENSIONS:
                continue

            # Check if the class exists and is a subclass of Extensions
            if hasattr(module, class_name) and issubclass(
                getattr(module, class_name), Extensions
            ):
                command_class = getattr(module, class_name)(**settings)
                if hasattr(command_class, "commands"):
                    for (
                        command_name,
                        command_function,
                    ) in command_class.commands.items():
                        params = self.get_command_params(command_function)
                        commands.append(
                            (
                                command_name,
                                getattr(module, class_name),
                                command_function.__name__,
                                params,
                            )
                        )

        # Add chains as commands
        if hasattr(self, "chains_with_args") and self.chains_with_args:
            for chain in self.chains_with_args:
                chain_name = chain["chain_name"]
                commands.append(
                    (
                        chain_name,
                        self.execute_chain,
                        "execute_chain",
                        {
                            "chain_name": chain_name,
                            "user_input": "",
                            **{arg: "" for arg in chain["args"]},
                        },
                    )
                )
        return commands

    def find_command(self, command_name: str):
        # Protect against empty command names
        if not command_name or command_name.strip() == "":
            logging.error("Empty command name provided")
            return None, None, None

        for name, module, function_name, params in self.commands:
            if module.__name__ in DISABLED_EXTENSIONS:
                continue
            if name == command_name:
                if isinstance(module, type):  # It's a class
                    command_function = getattr(module, function_name)
                    return command_function, module, params
                else:  # It's a function (for chains)
                    return module, None, params
        return None, None, None

    def get_extension_settings(self):
        settings = {}
        # Use cached extension discovery
        command_files = _get_cached_extension_files()
        for command_file in command_files:
            # Import the module using cached helper function
            module = _get_cached_extension_module(command_file)
            if module is None:
                continue

            # Get the expected class name from the module
            class_name = get_extension_class_name(os.path.basename(command_file))

            # Check if module is in disabled extensions
            if class_name in DISABLED_EXTENSIONS:
                continue

            # Check if the class exists and is a subclass of Extensions
            if hasattr(module, class_name) and issubclass(
                getattr(module, class_name), Extensions
            ):
                command_class = getattr(module, class_name)()
                params = self.get_command_params(command_class.__init__)
                # Remove self and kwargs from params
                if "self" in params:
                    del params["self"]
                if "kwargs" in params:
                    del params["kwargs"]
                if params != {}:
                    settings[class_name] = params

        # Use self.chains_with_args instead of iterating over self.chains
        if self.chains_with_args:
            settings["Custom Automation"] = {}
            for chain in self.chains_with_args:
                chain_name = chain["chain_name"]
                chain_args = chain["args"]
                if chain_args:
                    settings["Custom Automation"][chain_name] = {
                        "user_input": "",
                        **{arg: "" for arg in chain_args},
                    }

        return settings

    async def execute_command(self, command_name: str, command_args: dict = None):
        credentials = get_sso_credentials(user_id=self.user_id)
        agixt_server = getenv("AGIXT_URI")
        injection_variables = {
            "user": self.user,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "command_name": command_name,
            "conversation_name": self.conversation_name,
            "conversation_id": self.conversation_id,
            "agent_id": self.agent_id,
            "enabled_commands": self.get_enabled_commands(),
            "ApiClient": self.ApiClient,
            "api_key": self.api_key,
            "conversation_directory": os.path.join(
                os.getcwd(), "WORKSPACE", self.agent_id, self.conversation_id
            ),
            "output_url": f"{agixt_server}/outputs/{self.agent_id}/{self.conversation_id}/",
            **self.agent_config["settings"],
            **credentials,
        }
        if "activity_id" in command_args:
            injection_variables["activity_id"] = command_args["activity_id"]
            del command_args["activity_id"]

        # Emit webhook event for command execution started
        import asyncio

        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="command.execution.started",
                user_id=self.user_id,
                agent_id=self.agent_id,
                data={
                    "command_name": command_name,
                    "command_args": command_args,
                    "agent_name": self.agent_name,
                    "conversation_id": self.conversation_id,
                },
            )
        )

        command_function, module, params = self.find_command(command_name=command_name)
        logging.info(
            f"Executing command: {command_name} with args: {command_args}. Command Function: {command_function}"
        )
        if command_function is None:
            # Add more debugging for empty command names
            if not command_name or command_name.strip() == "":
                error_msg = "Empty command name provided"
                logging.error(error_msg)
            else:
                error_msg = f"Command '{command_name}' not found"
                logging.error(error_msg)

            # Emit webhook event for command execution failed
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="command.execution.failed",
                    user_id=self.user_id,
                    agent_id=self.agent_id,
                    data={
                        "command_name": command_name,
                        "command_args": command_args,
                        "agent_name": self.agent_name,
                        "conversation_id": self.conversation_id,
                        "error": error_msg,
                    },
                )
            )

            return error_msg

        if command_args is None:
            command_args = {}

        for param in params:
            if param not in command_args:
                if param != "self" and param != "kwargs":
                    command_args[param] = None
        args = command_args.copy()
        for param in command_args:
            if param not in params:
                del args[param]

        if module is None:  # It's a chain
            try:
                args = args.copy()
                if "chain_name" not in args or not args["chain_name"]:
                    args["chain_name"] = command_name
                if "user_input" not in args or args["user_input"] is None:
                    args["user_input"] = ""

                result = await command_function(**args)

                # Emit webhook event for command execution completed
                import asyncio

                asyncio.create_task(
                    webhook_emitter.emit_event(
                        event_type="command.execution.completed",
                        user_id=self.user_id,
                        agent_id=self.agent_id,
                        data={
                            "command_name": command_name,
                            "command_args": command_args,
                            "agent_name": self.agent_name,
                            "conversation_id": self.conversation_id,
                            "response": (
                                str(result)[:1000] if result else None
                            ),  # Limit response size
                        },
                    )
                )

                return result
            except Exception as e:
                # Emit webhook event for command execution failed
                import asyncio

                asyncio.create_task(
                    webhook_emitter.emit_event(
                        event_type="command.execution.failed",
                        user_id=self.user_id,
                        agent_id=self.agent_id,
                        data={
                            "command_name": command_name,
                            "command_args": command_args,
                            "agent_name": self.agent_name,
                            "conversation_id": self.conversation_id,
                            "error": str(e),
                        },
                    )
                )
                raise
        else:  # It's a regular command
            extension_instance = None
            try:
                extension_instance = module(**injection_variables)
                result = await getattr(extension_instance, command_function.__name__)(
                    **args
                )

                # Emit webhook event for command execution completed
                import asyncio

                asyncio.create_task(
                    webhook_emitter.emit_event(
                        event_type="command.execution.completed",
                        user_id=self.user_id,
                        agent_id=self.agent_id,
                        data={
                            "command_name": command_name,
                            "command_args": command_args,
                            "agent_name": self.agent_name,
                            "conversation_id": self.conversation_id,
                            "response": (
                                str(result)[:1000] if result else None
                            ),  # Limit response size
                        },
                    )
                )

                return result
            except Exception as e:
                # Emit webhook event for command execution failed
                import asyncio

                asyncio.create_task(
                    webhook_emitter.emit_event(
                        event_type="command.execution.failed",
                        user_id=self.user_id,
                        agent_id=self.agent_id,
                        data={
                            "command_name": command_name,
                            "command_args": command_args,
                            "agent_name": self.agent_name,
                            "conversation_id": self.conversation_id,
                            "error": str(e),
                        },
                    )
                )
                raise
            finally:
                # Ensure cleanup for extensions that support it
                if extension_instance and hasattr(extension_instance, "ensure_cleanup"):
                    try:
                        await extension_instance.ensure_cleanup()
                    except Exception as e:
                        logging.error(
                            f"Error during extension cleanup for {command_name}: {e}"
                        )
                elif extension_instance and hasattr(extension_instance, "__aexit__"):
                    try:
                        await extension_instance.__aexit__(None, None, None)
                    except Exception as e:
                        logging.error(
                            f"Error during extension async context cleanup for {command_name}: {e}"
                        )

    def get_command_params(self, func):
        params = {}
        sig = signature(func)
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.default == Parameter.empty:
                params[name] = ""
            else:
                params[name] = param.default
        return params

    def get_extensions(self):
        commands = []
        # Use cached extension discovery
        command_files = _get_cached_extension_files()
        for command_file in command_files:
            # Import the module using cached helper function
            module = _get_cached_extension_module(command_file)
            if module is None:
                continue

            # Get the expected class name from the module
            class_name = get_extension_class_name(os.path.basename(command_file))

            # Check if module is in disabled extensions
            if class_name in DISABLED_EXTENSIONS:
                continue

            # Check if the class exists and is a subclass of Extensions
            if hasattr(module, class_name):
                ext_class = getattr(module, class_name)
                # Use the module's Extensions class reference for comparison
                # since extensions import "from Extensions import Extensions"
                try:
                    extensions_base = getattr(module, "Extensions", None)
                    if extensions_base and issubclass(ext_class, extensions_base):
                        is_extensions_subclass = True
                    else:
                        # Fallback: check if it's a subclass of the current Extensions class
                        is_extensions_subclass = issubclass(ext_class, Extensions)
                except (TypeError, AttributeError):
                    is_extensions_subclass = False

                if is_extensions_subclass:
                    try:
                        command_class = getattr(module, class_name)()
                    except Exception as e:
                        logging.error(
                            f"Error instantiating extension class {class_name}: {e}"
                        )
                        continue

                    extension_name = os.path.basename(command_file).split(".")[0]
                    extension_name = extension_name.replace("_", " ").title()
                    try:
                        extension_description = inspect.getdoc(command_class)
                    except:
                        extension_description = extension_name
                    constructor = inspect.signature(command_class.__init__)
                    params = constructor.parameters
                    extension_settings = [
                        name for name in params if name != "self" and name != "kwargs"
                    ]
                    extension_commands = []
                    if hasattr(command_class, "commands"):
                        try:
                            for (
                                command_name,
                                command_function,
                            ) in command_class.commands.items():
                                params = self.get_command_params(command_function)
                                try:
                                    command_description = inspect.getdoc(
                                        command_function
                                    )
                                except:
                                    command_description = command_name
                                extension_commands.append(
                                    {
                                        "friendly_name": command_name,
                                        "description": command_description,
                                        "command_name": command_function.__name__,
                                        "command_args": params,
                                    }
                                )
                        except Exception as e:
                            logging.error(f"Error getting commands: {e}")
                    if extension_name == "Agixt Actions":
                        extension_name = "AGiXT Actions"

                    # Get category information from database or extension class
                    category_name = "Automation"  # Default category
                    category_description = ""

                    # Try to get category from the extension class
                    if hasattr(command_class, "CATEGORY"):
                        category_name = command_class.CATEGORY

                    # Get category description from database if available
                    try:
                        from DB import get_db_session, ExtensionCategory

                        with get_db_session() as session:
                            category = (
                                session.query(ExtensionCategory)
                                .filter_by(name=category_name)
                                .first()
                            )
                            if category:
                                category_description = category.description or ""
                    except Exception as e:
                        logging.debug(f"Could not get category description: {e}")

                    # Only add extensions that have commands (filters out OAuth extensions without credentials)
                    if extension_commands:
                        commands.append(
                            {
                                "extension_name": extension_name,
                                "description": extension_description,
                                "settings": extension_settings,
                                "commands": extension_commands,
                                "category": category_name,
                                "category_description": category_description,
                            }
                        )

        # Add Custom Automation as an extension only if chains_with_args is initialized
        if hasattr(self, "chains_with_args") and self.chains_with_args:
            chain_commands = []
            for chain in self.chains_with_args:
                chain_commands.append(
                    {
                        "friendly_name": chain["chain_name"],
                        "description": f"Execute custom automation: `{chain['chain_name']}`. The assistant can use the 'user_input' field as a place to summarize what the user needs when running the command.\nDescription: {chain['description']}",
                        "command_name": "run_chain",
                        "command_args": {
                            "chain_name": chain["chain_name"],
                            "user_input": "",
                            **{arg: "" for arg in chain["args"]},
                        },
                    }
                )

            # Get category information for Custom Automation
            category_name = "Core Abilities"
            category_description = ""
            try:
                from DB import get_db_session, ExtensionCategory

                with get_db_session() as session:
                    category = (
                        session.query(ExtensionCategory)
                        .filter_by(name=category_name)
                        .first()
                    )
                    if category:
                        category_description = category.description or ""
            except Exception as e:
                logging.debug(f"Could not get category description: {e}")

            commands.append(
                {
                    "extension_name": "Custom Automation",
                    "description": "Execute a custom automation workflow.",
                    "settings": [],
                    "commands": chain_commands,
                    "category": category_name,
                    "category_description": category_description,
                }
            )

        # Sort extensions by extension name for consistent ordering
        commands.sort(key=lambda x: x["extension_name"])

        return commands

    def get_extension_routers(self):
        """Collect FastAPI routers from extensions that define them"""
        routers = []
        try:
            settings = self.agent_config["settings"]
        except:
            settings = {}

        # Use cached extension discovery
        command_files = _get_cached_extension_files()
        for command_file in command_files:
            # Import the module using cached helper function
            module = _get_cached_extension_module(command_file)
            if module is None:
                continue

            # Get the expected class name from the module
            class_name = get_extension_class_name(os.path.basename(command_file))

            # Check if module is in disabled extensions
            if class_name in DISABLED_EXTENSIONS:
                continue

            try:
                # Check if the class exists and is a subclass of Extensions
                if hasattr(module, class_name) and issubclass(
                    getattr(module, class_name), Extensions
                ):
                    command_class = getattr(module, class_name)(**settings)
                    # Check if the extension has a router attribute
                    if hasattr(command_class, "router"):
                        routers.append(
                            {
                                "extension_name": class_name,
                                "router": command_class.router,
                            }
                        )
                        # logging.info(f"Found router for extension: {class_name}")
            except Exception as e:
                logging.error(f"Error loading router from extension {class_name}: {e}")
                continue

        return routers

    @staticmethod
    def get_extension_webhook_events():
        """Collect webhook events from all extensions"""
        extension_events = []
        # Use cached extension discovery
        command_files = _get_cached_extension_files()

        for command_file in command_files:
            # Import the module using cached helper function
            module = _get_cached_extension_module(command_file)
            if module is None:
                continue

            # Get the expected class name from the module
            class_name = get_extension_class_name(os.path.basename(command_file))

            # Check if module is in disabled extensions
            if class_name in DISABLED_EXTENSIONS:
                continue

            try:
                # Check if the class exists and is a subclass of Extensions
                if hasattr(module, class_name) and issubclass(
                    getattr(module, class_name), Extensions
                ):
                    extension_class = getattr(module, class_name)
                    # Check if the extension defines webhook events
                    if (
                        hasattr(extension_class, "webhook_events")
                        and extension_class.webhook_events
                    ):
                        # Add extension name to each event for context
                        for event in extension_class.webhook_events:
                            event_with_extension = event.copy()
                            event_with_extension["extension"] = class_name
                            extension_events.append(event_with_extension)
                        logging.info(
                            f"Found {len(extension_class.webhook_events)} webhook events for extension: {class_name}"
                        )
            except Exception as e:
                logging.error(
                    f"Error loading webhook events from extension {class_name}: {e}"
                )
                continue

        return extension_events
