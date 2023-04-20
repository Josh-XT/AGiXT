import importlib
import os
import glob
import json
from inspect import signature, Parameter
from Config import Config

class Commands:
    def __init__(self, agent_name: str = "default", load_commands_flag: bool = True):
        self.CFG = Config()
        if load_commands_flag:
            self.commands = self.load_commands(agent_name)
        else:
            self.commands = []
        self.agent_name = self.CFG.AGENT_NAME if agent_name is None else agent_name
        self.agent_folder = f"agents/{self.agent_name}"
        if not os.path.exists(self.agent_folder):
            os.makedirs(self.agent_folder)
        self.agent_config_file = os.path.join(self.agent_folder, "config.json")
        if not os.path.exists(self.agent_config_file):
            with open(self.agent_config_file, "w") as f:
                f.write(json.dumps({"commands": {command_name: "true" for command_name, _, _ in self.commands}}))
        with open(os.path.join("agents", self.agent_name, "config.json")) as agent_config:
            try:
                self.agent_config = json.load(agent_config)
            except json.JSONDecodeError:
                self.agent_config = {}
                # Populate the agent_config with all commands enabled
                self.agent_config["commands"] = {command_name: "true" for command_name, _, _ in self.load_commands(agent_name)}
                # Save the updated agent_config to the file
                with open(os.path.join("agents", self.agent_name, "config.json"), "w") as agent_config_file:
                    json.dump(self.agent_config, agent_config_file)
        if self.agent_config == {} or "commands" not in self.agent_config:
            # Add all commands to agent/{agent_name}/config.json in this format {"command_name": "true"}
            agent_config_file = os.path.join("agents", self.agent_name, "config.json")
            with open(agent_config_file, "w") as f:
                f.write(json.dumps({"commands": {command_name: "true" for command_name, _, _ in self.commands}}))
        self.available_commands = self.get_available_commands()
        
    def get_available_commands(self):
        available_commands = []
        for command in self.commands:
            command_name, command_function_name, params = command
            # Check content of "commands" agent_config for a list of command names with values of either true or false.
            if "commands" in self.agent_config and command_name in self.agent_config["commands"]:
                if self.agent_config["commands"][command_name] == "true":
                    # Add command to list of commands to return
                    available_commands.append(command)
        return available_commands

    def load_commands(self, agent_name: str = None):
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
        self.commands = self.load_commands(agent_name=self.agent_name)
        commands_str = ""
        for i, (command_name, command_function_name, params) in enumerate(self.commands, 1):
            formatted_params = {f"{k}": repr(v) for k, v in params.items()}
            commands_str += f'{i}. "{command_name}" - {command_function_name} {formatted_params}\n'
        # Get prompt from model-prompts/{CFG.AI_MODEL}/system.txt
        if not os.path.exists(f"model-prompts/{self.CFG.AI_MODEL}"):
            self.CFG.AI_MODEL = "default"
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
        return self.load_commands(agent_name=self.agent_name)