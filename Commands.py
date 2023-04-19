import importlib
import os
import glob
from inspect import signature, Parameter
from Config import Config

class Commands:
    def __init__(self):
        self.CFG = Config()
        self.commands = {}

    def load_commands(self):
        commands = []
        command_files = glob.glob("commands/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            module = importlib.import_module(f"commands.{module_name}")
            if issubclass(getattr(module, module_name), Commands):
                command_class = getattr(module, module_name)()
                if hasattr(command_class, 'commands'):
                    for command_name, command_function in command_class.commands.items():
                        params = self.get_command_params(command_function)
                        commands.append((command_name, command_function.__name__, params))
        if not commands:
            # No commands imported for {module_name} due to missing configuration requirements.
            return []
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

    def get_prompt(self):
        self.commands = self.load_commands()
        commands_str = ""
        for i, (command_name, command_function_name, params) in enumerate(self.commands, 1):
            formatted_params = {f"{k}": repr(v) for k, v in params.items()}
            commands_str += f'{i}. "{command_name}" - {command_function_name} {formatted_params}\n'
        # Get prompt from model-prompts/{CFG.AI_MODEL}/system.txt
        with open(f"model-prompts/{self.CFG.AI_MODEL}/system.txt", "r") as f:
            system_prompt = f.read()
        system_prompt = system_prompt.replace("{COMMANDS}", commands_str)
        system_prompt = system_prompt.replace("{AGENT_NAME}", self.CFG.AGENT_NAME)
        return system_prompt

    def find_command(self, command_name: str):
        for name, function_name, params in self.commands:
            if name == command_name:
                command_function = getattr(self, function_name)
                return command_function, params
        return None, None

    def get_commands_list(self):
        self.commands = self.load_commands()
        commands_list = [command_name for command_name, _, _ in self.commands]
        return commands_list
