import importlib
import os
from inspect import signature, Parameter
from Config.Agent import Agent


class Commands:
    def __init__(self, agent_name: str = "Agent-LLM", load_commands_flag: bool = True):
        if agent_name == "undefined":
            self.agent_name = "Agent-LLM"
        else:
            self.agent_name = agent_name
        self.CFG = Agent(self.agent_name)
        self.agent_folder = self.CFG.create_agent_folder(self.agent_name)
        # self.agent_config_file = self.CFG.create_agent_config_file(self.agent_folder)
        self.agent_config = self.CFG.load_agent_config(self.agent_name)
        if load_commands_flag:
            self.commands = self.load_commands()
        else:
            self.commands = []
        self.available_commands = self.get_available_commands()

    def get_available_commands(self):
        available_commands = []
        for description, _, _, name, params in self.commands:
            if (
                "commands" in self.agent_config
                and description in self.agent_config["commands"]
            ):
                enabled = False
                if (
                    self.agent_config["commands"][description] == "true"
                    or self.agent_config["commands"][description] == True
                ):
                    enabled = True
                available_commands.append({
                    "friendly_name": description,
                    "name": name,
                    "args": params,
                    "enabled": enabled,
                })
        return available_commands

    def load_commands(self):
        commands = []
        command_files = self.CFG.load_command_files()
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            module_class = importlib.import_module(f"commands.{module_name}")
            if issubclass(getattr(module_class, module_name), Commands):
                module = getattr(module_class, module_name)()
                if hasattr(module, "commands"):
                    for (
                        description,
                        command,
                    ) in module.commands.items():
                        params = self.get_command_params(command)
                        commands.append((
                            description,
                            command,
                            module,
                            command.__name__,
                            params,
                        ))
        return commands

    def get_command_params(self, func):
        params = {}
        sig = signature(func)
        for name, param in sig.parameters.items():
            if param.default == Parameter.empty:
                params[name] = None
            else:
                params[name] = param.default
        return params

    def find_command(self, command_name: str):
        for description, command, module, name, params in self.commands:
            if name == command_name or description == command_name:
                return command, module, params
        return None, None, None

    def get_commands_list(self):
        self.commands = self.load_commands(agent_name=self.agent_name)
        commands_list = [description for description, _, _, _, _, in self.commands]
        return commands_list

    def execute_command(self, command_name: str, command_args: dict = None):
        command, _, params = self.find_command(command_name)
        if command is None:
            return "Command not recognized"

        if command_args is None:
            command_args = {}

        if not isinstance(command_args, dict):
            return f"Error: command_args should be a dictionary, but got {type(command_args).__name__}"

        for name, value in command_args.items():
            if name in params:
                params[name] = value

        try:
            output = command(**params)
        except Exception as e:
            output = f"Error: {e}"

        return output