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

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
DISABLED_EXTENSIONS = getenv("DISABLED_EXTENSIONS").replace(" ", "").split(",")


class Extensions:
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

    async def execute_chain(self, chain_name, user_input="", **kwargs):
        return self.ApiClient.run_chain(
            agent_name=self.agent_name,
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

            if str(self.agent_config["commands"][friendly_name]).lower() == "true":
                available_commands.append(
                    {
                        "friendly_name": friendly_name,
                        "name": command_name,
                        "args": command_args,
                        "enabled": True,
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
        command_files = glob.glob("extensions/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            if module_name in DISABLED_EXTENSIONS:
                continue
            module = importlib.import_module(f"extensions.{module_name}")
            if issubclass(getattr(module, module_name), Extensions):
                command_class = getattr(module, module_name)(**settings)
                if hasattr(command_class, "commands"):
                    for (
                        command_name,
                        command_function,
                    ) in command_class.commands.items():
                        params = self.get_command_params(command_function)
                        commands.append(
                            (
                                command_name,
                                getattr(module, module_name),
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
        command_files = glob.glob("extensions/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            if module_name in DISABLED_EXTENSIONS:
                continue
            module = importlib.import_module(f"extensions.{module_name}")
            if issubclass(getattr(module, module_name), Extensions):
                command_class = getattr(module, module_name)()
                params = self.get_command_params(command_class.__init__)
                # Remove self and kwargs from params
                if "self" in params:
                    del params["self"]
                if "kwargs" in params:
                    del params["kwargs"]
                if params != {}:
                    settings[module_name] = params

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
        command_function, module, params = self.find_command(command_name=command_name)
        logging.info(
            f"Executing command: {command_name} with args: {command_args}. Command Function: {command_function}"
        )
        if command_function is None:
            logging.error(f"Command {command_name} not found")
            return f"Command {command_name} not found"

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
            return await command_function(
                chain_name=command_name, user_input="", **args
            )
        else:  # It's a regular command
            return await getattr(
                module(
                    **injection_variables,
                ),
                command_function.__name__,
            )(**args)

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
        command_files = glob.glob("extensions/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            if module_name in DISABLED_EXTENSIONS:
                continue
            module = importlib.import_module(f"extensions.{module_name}")
            command_class = getattr(module, module_name.lower())()
            extension_name = command_file.split("/")[-1].split(".")[0]
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
                            command_description = inspect.getdoc(command_function)
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
            commands.append(
                {
                    "extension_name": extension_name,
                    "description": extension_description,
                    "settings": extension_settings,
                    "commands": extension_commands,
                }
            )

        # Add Custom Automation as an extension only if chains_with_args is initialized
        if hasattr(self, "chains_with_args") and self.chains_with_args:
            chain_commands = []
            for chain in self.chains_with_args:
                logging.info(f"{chain}")
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

            commands.append(
                {
                    "extension_name": "Custom Automation",
                    "description": "Execute a custom automation workflow.",
                    "settings": [],
                    "commands": chain_commands,
                }
            )

        return commands
