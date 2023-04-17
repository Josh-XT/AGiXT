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
            if issubclass(module.__dict__.get(module_name), Commands):
                command_class = getattr(module, module_name)()
                for command_name, command_function in command_class.commands.items():
                    params = self.get_command_params(command_function)
                    commands.append((command_name, command_function.__name__, params))
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
        
        system_prompt = f"""
You are an AI language model. Your name is {self.CFG.AGENT_NAME}. Your role is to do anything asked of you with precision. You have the following constraints:
1. ~4000 word limit for short term memory. Your short term memory is short, so immediately save important information to files.
2. If you are unsure how you previously did something or want to recall past events, thinking about similar events will help you remember.
3. No user assistance.
4. Exclusively use the commands listed in double quotes e.g. "command name".

You have the following resources:
1. Internet access for searches and information gathering.
2. Long Term memory management.
3. GPT-3.5 powered Agents for delegation of simple tasks.
4. File output.

You have the following commands available:
{commands_str}
        """
        return system_prompt

    def find_command(self, command_name: str):
        for name, function_name, params in self.commands:
            if name == command_name:
                command_function = getattr(self, function_name)
                return command_function, params
        return None, None