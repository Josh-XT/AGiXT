import importlib
import os
import glob
import json
import hashlib
from inspect import signature, Parameter
import logging
import inspect
from Globals import getenv, DEFAULT_USER
from MagicalAuth import get_user_id, get_sso_credentials
from InternalClient import InternalClient
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
# Metadata cache: stores extension info without importing modules
_extension_metadata_cache = None
_extension_metadata_cache_file = os.path.join(
    os.path.dirname(__file__), "models", "extension_metadata_cache.json"
)


def _get_newest_extension_mtime():
    """
    Get the newest modification time among all extension files.
    Used to validate if the cache is stale.
    """
    try:
        command_files = _get_cached_extension_files()
        if not command_files:
            return 0
        return max(os.path.getmtime(f) for f in command_files if os.path.exists(f))
    except Exception as e:
        logging.debug(f"Could not get extension file mtimes: {e}")
        return 0


def _get_extension_metadata_cache():
    """
    Get cached extension metadata (commands, settings) without importing modules.
    This enables lazy loading - modules are only imported when commands are executed.

    The cache is automatically invalidated when any extension file has been modified
    since the cache was built.
    """
    global _extension_metadata_cache

    if _extension_metadata_cache is not None:
        return _extension_metadata_cache

    # Try to load from disk cache
    try:
        if os.path.exists(_extension_metadata_cache_file):
            with open(_extension_metadata_cache_file, "r") as f:
                cached = json.load(f)
                # Validate cache has expected structure
                if (
                    isinstance(cached, dict)
                    and "commands" in cached
                    and "extensions" in cached
                ):
                    # Check if cache is stale by comparing against newest extension file mtime
                    cache_built_at = cached.get("built_at", 0)
                    newest_mtime = _get_newest_extension_mtime()

                    if newest_mtime > cache_built_at:
                        logging.info(
                            f"Extension metadata cache is stale (cache built at {cache_built_at}, "
                            f"newest file at {newest_mtime}). Rebuilding..."
                        )
                    else:
                        _extension_metadata_cache = cached
                        logging.debug(
                            f"Loaded extension metadata cache with {len(cached['commands'])} commands"
                        )
                        return _extension_metadata_cache
    except Exception as e:
        logging.debug(f"Could not load extension metadata cache: {e}")

    # Build cache by importing modules (expensive, but only done once)
    _extension_metadata_cache = _build_extension_metadata_cache()
    return _extension_metadata_cache


def _build_extension_metadata_cache():
    """
    Build extension metadata cache using AST parsing (no imports needed).
    This is fast because it just parses Python files without executing them.
    """
    import time
    import ast

    start = time.time()

    metadata = {
        "commands": {},  # command_name -> {module_file, class_name, function_name, params, description}
        "extensions": {},  # class_name -> {file, settings, commands, friendly_name, description, category}
        "built_at": time.time(),
    }

    command_files = _get_cached_extension_files()
    for command_file in command_files:
        try:
            with open(command_file, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=command_file)
        except Exception as e:
            logging.debug(f"Could not parse {command_file}: {e}")
            continue

        class_name = get_extension_class_name(os.path.basename(command_file))
        if class_name in DISABLED_EXTENSIONS:
            continue

        # Find the extension class in the AST
        extension_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                extension_class = node
                break

        if extension_class is None:
            continue

        # Extract class docstring
        class_docstring = ast.get_docstring(extension_class) or ""

        # Extract friendly_name and CATEGORY class attributes
        friendly_name = None
        category = "Automation"  # Default
        for item in extension_class.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "friendly_name" and isinstance(
                            item.value, ast.Constant
                        ):
                            friendly_name = item.value.value
                        elif target.id == "CATEGORY" and isinstance(
                            item.value, ast.Constant
                        ):
                            category = item.value.value

        # Extract __init__ parameters (settings)
        settings = []
        for item in extension_class.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for arg in item.args.args:
                    if arg.arg not in ("self", "kwargs"):
                        settings.append(arg.arg)
                # Also check **kwargs in kwonlyargs
                for arg in item.args.kwonlyargs:
                    if arg.arg not in ("self", "kwargs"):
                        settings.append(arg.arg)
                break

        extension_info = {
            "file": command_file,
            "settings": settings,
            "commands": [],
            "friendly_name": friendly_name,
            "description": class_docstring,
            "category": category,
        }

        # Find self.commands assignments in __init__
        # Look for self.commands = { ... } dictionary
        commands_dict = {}
        for item in extension_class.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in ast.walk(item):
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if (
                                isinstance(target, ast.Attribute)
                                and isinstance(target.value, ast.Name)
                                and target.value.id == "self"
                                and target.attr == "commands"
                            ):
                                # Found self.commands = {...}
                                if isinstance(stmt.value, ast.Dict):
                                    for key, val in zip(
                                        stmt.value.keys, stmt.value.values
                                    ):
                                        if isinstance(key, ast.Constant) and isinstance(
                                            val, ast.Attribute
                                        ):
                                            cmd_name = key.value
                                            func_name = val.attr
                                            commands_dict[cmd_name] = func_name

        # Extract function parameters and docstrings for each command
        for cmd_name, func_name in commands_dict.items():
            params = {}
            cmd_docstring = ""
            for item in extension_class.body:
                # Check both sync and async function definitions
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == func_name
                ):
                    cmd_docstring = ast.get_docstring(item) or cmd_name
                    for arg in item.args.args:
                        if arg.arg != "self":
                            # Get annotation if present
                            annotation = ""
                            if arg.annotation:
                                if isinstance(arg.annotation, ast.Name):
                                    annotation = f"<class '{arg.annotation.id}'>"
                                elif isinstance(arg.annotation, ast.Constant):
                                    annotation = str(arg.annotation.value)
                            params[arg.arg] = annotation
                    break

            cmd_info = {
                "module_file": command_file,
                "class_name": class_name,
                "function_name": func_name,
                "params": params,
                "description": cmd_docstring,
            }
            metadata["commands"][cmd_name] = cmd_info
            extension_info["commands"].append(cmd_name)

        metadata["extensions"][class_name] = extension_info

    # Save to disk cache
    try:
        os.makedirs(os.path.dirname(_extension_metadata_cache_file), exist_ok=True)
        with open(_extension_metadata_cache_file, "w") as f:
            json.dump(metadata, f, indent=2)
        logging.info(
            f"Saved extension metadata cache with {len(metadata['commands'])} commands"
        )
    except Exception as e:
        logging.debug(f"Could not save extension metadata cache: {e}")

    elapsed = time.time() - start
    logging.info(f"Built extension metadata cache in {elapsed:.2f}s (AST parsing)")

    return metadata


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
    global _extension_discovery_cache, _extension_module_cache, _extension_metadata_cache
    _extension_discovery_cache = None
    _extension_module_cache.clear()
    _extension_metadata_cache = None

    # Remove disk cache
    try:
        if os.path.exists(_extension_metadata_cache_file):
            os.remove(_extension_metadata_cache_file)
            logging.info("Removed extension metadata cache file")
    except Exception as e:
        logging.debug(f"Could not remove metadata cache file: {e}")

    # Also invalidate ExtensionsHub path cache
    try:
        from ExtensionsHub import ExtensionsHub

        hub = ExtensionsHub()
        hub._extension_paths_cache = None
        logging.info("Extension hub path cache invalidated")
    except Exception as e:
        logging.debug(f"Could not invalidate hub path cache: {e}")

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
            ApiClient if ApiClient else InternalClient(api_key=api_key, user=user)
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

        # Extract nested chain_args if present and merge with kwargs
        # This handles the case where execute_command sets log_output=False in chain_args
        nested_chain_args = kwargs.pop("chain_args", {}) or {}

        # Merge nested chain_args into kwargs, preferring nested values
        for key, value in nested_chain_args.items():
            if key not in kwargs or kwargs[key] is None:
                kwargs[key] = value

        return self.ApiClient.run_chain(
            chain_name=chain_name,
            user_input=user_input,
            agent_name=self.agent_name,  # Use the current agent executing the chain
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

        if not chain_steps:
            chain_data = {
                "id": chain_db.id,
                "chain_name": chain_db.name,
                "steps": [],
                "description": chain_db.description if chain_db.description else "",
            }
            session.close()
            return chain_data

        # Batch load all related data to avoid N+1 queries
        agent_ids = {step.agent_id for step in chain_steps if step.agent_id}
        chain_ids = {
            step.target_chain_id for step in chain_steps if step.target_chain_id
        }
        command_ids = {
            step.target_command_id for step in chain_steps if step.target_command_id
        }
        prompt_ids = {
            step.target_prompt_id for step in chain_steps if step.target_prompt_id
        }
        step_ids = {step.id for step in chain_steps}

        # Batch queries
        agents_map = {}
        if agent_ids:
            agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            agents_map = {a.id: a.name for a in agents}

        chains_map = {}
        if chain_ids:
            chains = session.query(ChainDB).filter(ChainDB.id.in_(chain_ids)).all()
            chains_map = {c.id: c.name for c in chains}

        commands_map = {}
        if command_ids:
            commands = session.query(Command).filter(Command.id.in_(command_ids)).all()
            commands_map = {c.id: c.name for c in commands}

        prompts_map = {}
        if prompt_ids:
            prompts = session.query(Prompt).filter(Prompt.id.in_(prompt_ids)).all()
            prompts_map = {p.id: p.name for p in prompts}

        # Batch load all arguments for all steps
        step_arguments = {}
        if step_ids:
            all_args = (
                session.query(Argument, ChainStepArgument)
                .join(ChainStepArgument, ChainStepArgument.argument_id == Argument.id)
                .filter(ChainStepArgument.chain_step_id.in_(step_ids))
                .all()
            )
            for argument, chain_step_argument in all_args:
                if chain_step_argument.chain_step_id not in step_arguments:
                    step_arguments[chain_step_argument.chain_step_id] = {}
                step_arguments[chain_step_argument.chain_step_id][
                    argument.name
                ] = chain_step_argument.value

        steps = []
        for step in chain_steps:
            agent_name = agents_map.get(step.agent_id, "Unknown")
            prompt = {}
            if step.target_chain_id:
                prompt["chain_name"] = chains_map.get(step.target_chain_id, "Unknown")
            elif step.target_command_id:
                prompt["command_name"] = commands_map.get(
                    step.target_command_id, "Unknown"
                )
            elif step.target_prompt_id:
                prompt["prompt_name"] = prompts_map.get(
                    step.target_prompt_id, "Unknown"
                )

            prompt_args = step_arguments.get(step.id, {})
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
        """
        Get all chains with their argument requirements.
        OPTIMIZED: Batch loads all chain data in a single pass instead of N queries.
        """
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

        if not self.chains:
            return []

        # Batch load all chains data in one go
        session = get_session()
        try:
            user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
            default_user_id = user_data.id if user_data else None

            # Get all chains we need
            chain_names = self.chains
            all_chain_dbs = (
                session.query(ChainDB)
                .filter(
                    ChainDB.name.in_(chain_names),
                    (ChainDB.user_id == self.user_id)
                    | (ChainDB.user_id == default_user_id),
                )
                .all()
            )

            # Build lookup: name -> chain_db (prefer user's chains over default)
            chain_lookup = {}
            for cdb in all_chain_dbs:
                if cdb.name not in chain_lookup or cdb.user_id == self.user_id:
                    chain_lookup[cdb.name] = cdb

            if not chain_lookup:
                return []

            # Batch load all chain steps
            chain_ids = [cdb.id for cdb in chain_lookup.values()]
            all_chain_steps = (
                session.query(ChainStep)
                .filter(ChainStep.chain_id.in_(chain_ids))
                .order_by(ChainStep.chain_id, ChainStep.step_number)
                .all()
            )

            # Group steps by chain_id
            steps_by_chain = {}
            for step in all_chain_steps:
                if step.chain_id not in steps_by_chain:
                    steps_by_chain[step.chain_id] = []
                steps_by_chain[step.chain_id].append(step)

            # Batch load all agents, chains, commands, prompts for all steps
            agent_ids = {s.agent_id for s in all_chain_steps if s.agent_id}
            target_chain_ids = {
                s.target_chain_id for s in all_chain_steps if s.target_chain_id
            }
            command_ids = {
                s.target_command_id for s in all_chain_steps if s.target_command_id
            }
            prompt_ids = {
                s.target_prompt_id for s in all_chain_steps if s.target_prompt_id
            }
            step_ids = {s.id for s in all_chain_steps}

            agents_map = {}
            if agent_ids:
                agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
                agents_map = {a.id: a.name for a in agents}

            chains_map = {}
            if target_chain_ids:
                chains = (
                    session.query(ChainDB)
                    .filter(ChainDB.id.in_(target_chain_ids))
                    .all()
                )
                chains_map = {c.id: c.name for c in chains}

            commands_map = {}
            if command_ids:
                commands = (
                    session.query(Command).filter(Command.id.in_(command_ids)).all()
                )
                commands_map = {c.id: c.name for c in commands}

            prompts_map = {}
            if prompt_ids:
                prompts = session.query(Prompt).filter(Prompt.id.in_(prompt_ids)).all()
                prompts_map = {p.id: p.name for p in prompts}

            # Batch load all arguments
            step_arguments = {}
            if step_ids:
                all_args = (
                    session.query(Argument, ChainStepArgument)
                    .join(
                        ChainStepArgument, ChainStepArgument.argument_id == Argument.id
                    )
                    .filter(ChainStepArgument.chain_step_id.in_(step_ids))
                    .all()
                )
                for argument, chain_step_argument in all_args:
                    if chain_step_argument.chain_step_id not in step_arguments:
                        step_arguments[chain_step_argument.chain_step_id] = {}
                    step_arguments[chain_step_argument.chain_step_id][
                        argument.name
                    ] = chain_step_argument.value

        finally:
            session.close()

        # Now build results without any additional DB queries
        chains_result = []
        for chain_name in chain_names:
            chain_db = chain_lookup.get(chain_name)
            if not chain_db:
                continue

            description = chain_db.description or ""
            steps = steps_by_chain.get(chain_db.id, [])
            prompt_args = []

            for step in steps:
                try:
                    prompt = {}
                    prompt_args_for_step = step_arguments.get(step.id, {})
                    prompt.update(prompt_args_for_step)

                    if step.target_chain_id:
                        prompt["chain_name"] = chains_map.get(
                            step.target_chain_id, "Unknown"
                        )
                        prompt["command_name"] = prompt["chain_name"]
                    elif step.target_command_id:
                        prompt["command_name"] = commands_map.get(
                            step.target_command_id, "Unknown"
                        )
                    elif step.target_prompt_id:
                        prompt_name = prompts_map.get(step.target_prompt_id, "")
                        prompt["prompt_name"] = prompt_name

                    prompt_category = prompt.get("category", "Default")

                    if "prompt_name" in prompt and prompt["prompt_name"]:
                        prompt_content = self.prompts.get_prompt(
                            prompt_name=prompt["prompt_name"],
                            prompt_category=prompt_category,
                        )
                        args = self.prompts.get_prompt_args(prompt_text=prompt_content)
                    elif "command_name" in prompt:
                        args = self.get_command_args(
                            command_name=prompt["command_name"]
                        )
                    else:
                        args = []

                    for arg in args:
                        if arg not in prompt_args and arg not in skip_args:
                            existing_value = prompt.get(arg)
                            if existing_value is None or existing_value == "":
                                prompt_args.append(arg)
                except Exception as e:
                    logging.error(f"Error getting chain args for {chain_name}: {e}")

            chains_result.append(
                {
                    "chain_name": chain_name,
                    "description": description,
                    "args": prompt_args,
                }
            )

        return chains_result

    def load_commands(self):
        """
        Load commands using cached metadata for fast discovery.
        Modules are only imported when commands are actually executed (lazy loading).
        """
        try:
            settings = self.agent_config["settings"]
        except:
            settings = {}
        commands = []

        # Use metadata cache for fast command discovery
        metadata = _get_extension_metadata_cache()

        for cmd_name, cmd_info in metadata.get("commands", {}).items():
            class_name = cmd_info["class_name"]
            if class_name in DISABLED_EXTENSIONS:
                continue

            # Store command info for lazy loading - don't import module yet
            commands.append(
                (
                    cmd_name,
                    cmd_info,  # Store metadata instead of actual class
                    cmd_info["function_name"],
                    cmd_info["params"],
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
        """
        Find a command by name. Uses lazy loading - only imports the module
        when the command is actually being executed.
        """
        # Protect against empty command names
        if not command_name or command_name.strip() == "":
            logging.error("Empty command name provided")
            return None, None, None

        try:
            settings = self.agent_config.get("settings", {})
        except:
            settings = {}

        for name, module_or_info, function_name, params in self.commands:
            if name == command_name:
                # Check if this is a chain (callable) or extension metadata (dict)
                if callable(module_or_info):
                    # It's a chain function
                    return module_or_info, None, params

                if isinstance(module_or_info, dict):
                    # Lazy loading: import module now that we need it
                    cmd_info = module_or_info
                    class_name = cmd_info["class_name"]

                    if class_name in DISABLED_EXTENSIONS:
                        continue

                    module_file = cmd_info["module_file"]
                    module = _get_cached_extension_module(module_file)
                    if module is None:
                        logging.error(
                            f"Could not import module for command {command_name}"
                        )
                        return None, None, None

                    ext_class = getattr(module, class_name, None)
                    if ext_class is None:
                        logging.error(f"Class {class_name} not found in module")
                        return None, None, None

                    command_function = getattr(ext_class, function_name, None)
                    if command_function is None:
                        logging.error(
                            f"Function {function_name} not found in class {class_name}"
                        )
                        return None, None, None

                    return command_function, ext_class, params
                else:
                    # Legacy: it's already an imported class
                    module = module_or_info
                    if (
                        hasattr(module, "__name__")
                        and module.__name__ in DISABLED_EXTENSIONS
                    ):
                        continue
                    if isinstance(module, type):
                        command_function = getattr(module, function_name)
                        return command_function, module, params

        return None, None, None

    def get_extension_settings(self):
        """
        Get extension settings using cached metadata (no module imports needed).
        """
        settings = {}

        # Use metadata cache - no module imports needed
        metadata = _get_extension_metadata_cache()

        for class_name, ext_info in metadata.get("extensions", {}).items():
            if class_name in DISABLED_EXTENSIONS:
                continue

            ext_settings = ext_info.get("settings", [])
            if ext_settings:
                # Get extension name from file path (same format as get_extensions)
                extension_file = os.path.basename(ext_info["file"])
                extension_name = extension_file.split(".")[0]
                extension_name = extension_name.replace("_", " ").title()
                if extension_name == "Agixt Actions":
                    extension_name = "AGiXT Actions"
                # Convert list of setting names to dict format
                settings[extension_name] = {name: "" for name in ext_settings}

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
        # Use hash-based agent workspace (matches Agent.working_directory)
        agent_hash = hashlib.sha256(str(self.agent_id).encode()).hexdigest()[:16]
        agent_workspace = os.path.join(os.getcwd(), "WORKSPACE", f"agent_{agent_hash}")
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
                agent_workspace, self.conversation_id
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
        # logging.info(f"Executing command: {command_name} with args: {command_args}")
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

        # Convert argument types based on function signature
        if command_function is not None:
            sig = signature(command_function)
            converted_args = {}
            for arg_name, arg_value in args.items():
                if arg_name in sig.parameters:
                    param_info = sig.parameters[arg_name]
                    if param_info.annotation != Parameter.empty:
                        # Convert the argument to the expected type
                        converted_args[arg_name] = self._convert_arg_type(
                            arg_value, param_info.annotation, arg_name
                        )
                    else:
                        converted_args[arg_name] = arg_value
                else:
                    converted_args[arg_name] = arg_value
            args = converted_args

        if module is None:  # It's a chain
            try:
                args = args.copy()
                if "chain_name" not in args or not args["chain_name"]:
                    args["chain_name"] = command_name
                if "user_input" not in args or args["user_input"] is None:
                    args["user_input"] = ""
                if (
                    "chain_args" not in args
                    or args["chain_args"] is None
                    or not isinstance(args["chain_args"], dict)
                ):
                    args["chain_args"] = {}
                chain_args = args["chain_args"]
                if "log_output" not in chain_args:
                    chain_args["log_output"] = False
                if self.conversation_name and not chain_args.get("conversation_name"):
                    chain_args["conversation_name"] = self.conversation_name
                if self.conversation_id and not chain_args.get("conversation_id"):
                    chain_args["conversation_id"] = self.conversation_id
                args["chain_args"] = chain_args
                if "running_command" not in command_args or not command_args.get(
                    "running_command"
                ):
                    command_args["running_command"] = command_name
                if "running_command" not in args or not args.get("running_command"):
                    args["running_command"] = command_args["running_command"]

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

    def _convert_arg_type(self, value, param_annotation, param_name: str = ""):
        """
        Convert argument value to the expected type based on parameter annotation.

        Args:
            value: The value to convert (typically a string from API)
            param_annotation: The type annotation from the function signature
            param_name: Name of the parameter (for logging)

        Returns:
            Converted value or original value if conversion not possible/needed
        """
        # If value is None or already the correct type, return as-is
        if value is None or param_annotation == Parameter.empty:
            return value

        # Get the actual type if it's wrapped in Optional, Union, etc.
        actual_type = param_annotation

        # Handle typing module types (Optional, Union, etc.)
        if hasattr(param_annotation, "__origin__"):
            # For Optional[T] or Union[T, None], extract T
            if (
                param_annotation.__origin__ is type(None)
                or str(param_annotation.__origin__) == "typing.Union"
            ):
                args = getattr(param_annotation, "__args__", ())
                if args:
                    # Get first non-None type
                    actual_type = next(
                        (arg for arg in args if arg is not type(None)), str
                    )
            else:
                actual_type = param_annotation.__origin__

        # If already correct type, return as-is
        if type(value) == actual_type:
            return value

        # Convert string values to appropriate types
        if isinstance(value, str):
            try:
                # Handle boolean conversion
                if actual_type == bool:
                    if value.lower() in ("true", "1", "yes", "on"):
                        return True
                    elif value.lower() in ("false", "0", "no", "off", ""):
                        return False
                    else:
                        return bool(value)

                # Handle integer conversion
                elif actual_type == int:
                    # Handle float strings by converting to float first, then int
                    if "." in value:
                        return int(float(value))
                    return int(value)

                # Handle float conversion
                elif actual_type == float:
                    return float(value)

                # Handle list/tuple conversion (basic JSON-like strings)
                elif actual_type in (list, tuple):
                    try:
                        result = json.loads(value)
                        return (
                            actual_type(result)
                            if isinstance(result, (list, tuple))
                            else [result]
                        )
                    except:
                        # If not JSON, split by comma
                        return actual_type(
                            v.strip() for v in value.split(",") if v.strip()
                        )

                # Handle dict conversion
                elif actual_type == dict:
                    return json.loads(value)

            except (ValueError, TypeError, json.JSONDecodeError) as e:
                logging.warning(
                    f"Could not convert parameter '{param_name}' value '{value}' to type {actual_type}: {e}. "
                    f"Using original value."
                )
                return value

        # For non-string values, try direct conversion
        try:
            if actual_type in (int, float, bool, str, list, tuple, dict):
                return actual_type(value)
        except (ValueError, TypeError) as e:
            logging.warning(
                f"Could not convert parameter '{param_name}' value '{value}' to type {actual_type}: {e}. "
                f"Using original value."
            )

        return value

    def get_extensions(self):
        """
        Get list of extensions with their commands using cached metadata.
        No module imports needed - uses AST-parsed metadata cache.
        """
        commands = []
        metadata = _get_extension_metadata_cache()

        # Get category descriptions in one batch query
        category_descriptions = {}
        try:
            from DB import get_db_session, ExtensionCategory

            with get_db_session() as session:
                categories = session.query(ExtensionCategory).all()
                category_descriptions = {
                    c.name: c.description or "" for c in categories
                }
        except Exception as e:
            logging.debug(f"Could not get category descriptions: {e}")

        for class_name, ext_info in metadata.get("extensions", {}).items():
            if class_name in DISABLED_EXTENSIONS:
                continue

            # Get extension name from file path
            extension_file = os.path.basename(ext_info["file"])
            extension_name = extension_file.split(".")[0]
            extension_name = extension_name.replace("_", " ").title()
            if extension_name == "Agixt Actions":
                extension_name = "AGiXT Actions"

            # Build commands list from cached metadata
            extension_commands = []
            for cmd_name in ext_info.get("commands", []):
                cmd_info = metadata["commands"].get(cmd_name, {})
                extension_commands.append(
                    {
                        "friendly_name": cmd_name,
                        "description": cmd_info.get("description", cmd_name),
                        "command_name": cmd_info.get("function_name", ""),
                        "command_args": cmd_info.get("params", {}),
                    }
                )

            # Only add extensions that have commands
            if extension_commands:
                category_name = ext_info.get("category", "Automation")
                commands.append(
                    {
                        "extension_name": extension_name,
                        "friendly_name": ext_info.get("friendly_name"),
                        "description": ext_info.get("description", extension_name),
                        "settings": ext_info.get("settings", []),
                        "commands": extension_commands,
                        "category": category_name,
                        "category_description": category_descriptions.get(
                            category_name, ""
                        ),
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

            category_name = "Core Abilities"
            commands.append(
                {
                    "extension_name": "Custom Automation",
                    "friendly_name": "Custom Automation",
                    "description": "Execute a custom automation workflow.",
                    "settings": [],
                    "commands": chain_commands,
                    "category": category_name,
                    "category_description": category_descriptions.get(
                        category_name, ""
                    ),
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
                attr = getattr(module, class_name, None)
                if (
                    attr is not None
                    and inspect.isclass(attr)
                    and issubclass(attr, Extensions)
                ):
                    command_class = attr(**settings)
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
                attr = getattr(module, class_name, None)
                if (
                    attr is not None
                    and inspect.isclass(attr)
                    and issubclass(attr, Extensions)
                ):
                    extension_class = attr
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
            except Exception as e:
                logging.error(
                    f"Error loading webhook events from extension {class_name}: {e}"
                )
                continue

        return extension_events
