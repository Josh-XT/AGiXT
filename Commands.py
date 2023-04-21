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
        if agent_name == "undefined":
            agent_name = "default"
        self.agent_name = self.CFG.AGENT_NAME if agent_name is None else agent_name
        if not os.path.exists("agents"):
            os.makedirs("agents")
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
            friendly_name, command_name, command_args = command
            if "commands" in self.agent_config and friendly_name in self.agent_config["commands"]:
                if self.agent_config["commands"][friendly_name] == "true" or self.agent_config["commands"][friendly_name] == True:
                    # Add command to list of commands to return
                    available_commands.append({"friendly_name": friendly_name, "name": command_name, "args": command_args, "enabled": True})
                else:
                    available_commands.append({"friendly_name": friendly_name, "name": command_name, "args": command_args, "enabled": False})
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

    def find_command(self, command_name: str):
        for name, function_name, params in self.commands:
            if name == command_name:
                command_function = getattr(self, function_name)
                return command_function, params
        return None, None

    def get_commands_list(self):
        self.commands = self.load_commands(agent_name=self.agent_name)
        commands_list = [command_name for command_name, _, _ in self.commands]
        return commands_list