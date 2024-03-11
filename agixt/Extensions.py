import importlib
import os
import glob
from inspect import signature, Parameter
import logging
import inspect
from Defaults import DEFAULT_USER
from dotenv import load_dotenv

load_dotenv()

DISABLED_EXTENSIONS = os.getenv("DISABLED_EXTENSIONS", "").replace(" ", "").split(",")


class Extensions:
    def __init__(
        self,
        agent_name="",
        agent_config=None,
        conversation_name="",
        ApiClient=None,
        api_key=None,
        user=DEFAULT_USER,
    ):
        self.agent_config = agent_config
        self.agent_name = agent_name if agent_name else "gpt4free"
        self.conversation_name = conversation_name
        self.ApiClient = ApiClient
        self.api_key = api_key
        self.commands = self.load_commands()
        self.user = user
        if agent_config != None:
            if "commands" not in self.agent_config:
                self.agent_config["commands"] = {}
            if self.agent_config["commands"] == None:
                self.agent_config["commands"] = {}
            self.available_commands = self.get_available_commands()
        else:
            self.agent_config = {
                "settings": {},
                "commands": {},
            }

    def get_available_commands(self):
        if self.commands == []:
            return []
        available_commands = []
        for command in self.commands:
            friendly_name, command_module, command_name, command_args = command
            if (
                "commands" in self.agent_config
                and friendly_name in self.agent_config["commands"]
            ):
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
                        # Store the module along with the function name
                        commands.append(
                            (
                                command_name,
                                getattr(module, module_name),
                                command_function.__name__,
                                params,
                            )
                        )
        # Return the commands list
        logging.debug(f"loaded commands: {commands}")
        return commands

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
        return settings

    def find_command(self, command_name: str):
        for name, module, function_name, params in self.commands:
            if module.__name__ in DISABLED_EXTENSIONS:
                continue
            if name == command_name:
                command_function = getattr(module, function_name)
                return command_function, module, params  # Updated return statement
        return None, None, None  # Updated return statement

    def get_commands_list(self):
        self.commands = self.load_commands()
        commands_list = [command_name for command_name, _, _ in self.commands]
        return commands_list

    async def execute_command(self, command_name: str, command_args: dict = None):
        if command_args:
            if "is_m4a_audio" in command_args or "is_wav_audio" in command_args:
                new_command_args = {}
                for arg in command_args:
                    if "is_m4a_audio" in command_args:
                        if arg == command_args["is_m4a_audio"]:
                            new_command_args[arg] = await self.execute_command(
                                command_name="Transcribe M4A Audio",
                                command_args={"base64_audio": command_args[arg]},
                            )
                    if "is_wav_audio" in command_args:
                        if arg == command_args["is_wav_audio"]:
                            new_command_args[arg] = await self.execute_command(
                                command_name="Transcribe WAV Audio",
                                command_args={"base64_audio": command_args[arg]},
                            )
                    if arg not in new_command_args:
                        new_command_args[arg] = command_args[arg]
                command_args = new_command_args
        injection_variables = {
            "user": self.user,
            "agent_name": self.agent_name,
            "command_name": command_name,
            "conversation_name": self.conversation_name,
            "enabled_commands": self.get_enabled_commands(),
            "ApiClient": self.ApiClient,
            "api_key": self.api_key,
            **self.agent_config["settings"],
        }
        command_function, module, params = self.find_command(command_name=command_name)
        logging.info(
            f"Executing command: {command_name} with args: {command_args}. Command Function: {command_function}"
        )
        if command_function is None:
            logging.error(f"Command {command_name} not found")
            return f"Command {command_name} not found"

        for param in params:
            if param not in command_args:
                if param != "self" and param != "kwargs":
                    command_args[param] = None
        args = command_args.copy()
        for param in command_args:
            if param not in params:
                del args[param]
        # try:
        output = await getattr(
            module(
                **injection_variables,
            ),
            command_function.__name__,
        )(**args)
        # except Exception as e:
        #    output = f"Error: {str(e)}"
        logging.info(f"Command Output: {output}")
        return output

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
                        extension_commands.append(
                            {
                                "friendly_name": command_name,
                                "command_name": command_function.__name__,
                                "command_args": params,
                            }
                        )
                except Exception as e:
                    logging.error(f"Error getting commands: {e}")
            commands.append(
                {
                    "extension_name": extension_name,
                    "description": extension_name,
                    "settings": extension_settings,
                    "commands": extension_commands,
                }
            )
        return commands
