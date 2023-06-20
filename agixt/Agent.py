import os
import json
import glob
import shutil
import importlib
import yaml
import time
from pathlib import Path
from inspect import signature, Parameter
from provider import Provider
from Memories import Memories
from Extensions import Extensions
from datetime import datetime

DEFAULT_SETTINGS = {
    "provider": "gpt4free",
    "AI_MODEL": "gpt-3.5-turbo",
    "AI_TEMPERATURE": "0.7",
    "MAX_TOKENS": "4096",
    "embedder": "default",
    "autonomous_execution": "false",
}


def get_agent_file_paths(agent_name):
    base_path = os.path.join(os.getcwd(), "agents")
    folder_path = os.path.normpath(os.path.join(base_path, agent_name))
    config_path = os.path.normpath(os.path.join(folder_path, "config.json"))
    history_path = os.path.normpath(os.path.join(folder_path, "history.yaml"))
    if not config_path.startswith(base_path) or not folder_path.startswith(base_path):
        raise ValueError("Invalid path, agent name must not contain slashes.")
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)
    return config_path, history_path, folder_path


def add_agent(agent_name, provider_settings=None, commands={}):
    if not agent_name:
        return "Agent name cannot be empty."
    provider_settings = (
        DEFAULT_SETTINGS
        if not provider_settings or provider_settings == {}
        else provider_settings
    )
    config_path, history_path, folder_path = get_agent_file_paths(agent_name=agent_name)
    if provider_settings is None or provider_settings == "" or provider_settings == {}:
        provider_settings = DEFAULT_SETTINGS
    settings = json.dumps(
        {
            "commands": commands,
            "settings": provider_settings,
        }
    )
    # Write the settings to the agent config file
    with open(config_path, "w") as f:
        f.write(settings)
    with open(history_path, "w") as f:
        f.write("")
    return {"message": f"Agent {agent_name} created."}


def delete_agent(agent_name):
    config_path, history_path, folder_path = get_agent_file_paths(agent_name=agent_name)
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
        return {"message": f"Agent {agent_name} deleted."}, 200
    except:
        return {"message": f"Agent {agent_name} could not be deleted."}, 400


def rename_agent(agent_name, new_name):
    config_path, history_path, folder_path = get_agent_file_paths(agent_name=agent_name)
    base_path = os.path.join(os.getcwd(), "agents")
    new_agent_folder = os.path.normpath(os.path.join(base_path, new_name))
    if not new_agent_folder.startswith(base_path):
        raise ValueError("Invalid path, agent name must not contain slashes.")

    if os.path.exists(folder_path):
        # Check if the new name is already taken
        if os.path.exists(new_agent_folder):
            # Add a number to the end of the new name
            i = 1
            while os.path.exists(new_agent_folder):
                i += 1
                new_name = f"{new_name}_{i}"
                new_agent_folder = os.path.normpath(os.path.join(base_path, new_name))
            if not new_agent_folder.startswith(base_path):
                raise ValueError("Invalid path, agent name must not contain slashes.")
        os.rename(folder_path, new_agent_folder)
        return {"message": f"Agent {agent_name} renamed to {new_name}."}, 200


def get_agents():
    agents_dir = "agents"
    if not os.path.exists(agents_dir):
        os.makedirs(agents_dir)
    agents = [
        dir_name
        for dir_name in os.listdir(agents_dir)
        if os.path.isdir(os.path.join(agents_dir, dir_name))
    ]
    output = []
    if agents:
        for agent in agents:
            output.append({"name": agent, "status": False})
    return output


class Agent:
    def __init__(self, agent_name=None):
        self.agent_name = agent_name if agent_name is not None else "AGiXT"
        self.config_path, self.history_file, self.folder_path = get_agent_file_paths(
            agent_name=self.agent_name
        )
        self.AGENT_CONFIG = self.get_agent_config()
        if "settings" in self.AGENT_CONFIG:
            self.PROVIDER_SETTINGS = self.AGENT_CONFIG["settings"]
            if "provider" in self.PROVIDER_SETTINGS:
                self.AI_PROVIDER = self.PROVIDER_SETTINGS["provider"]
                self.PROVIDER = Provider(self.AI_PROVIDER, **self.PROVIDER_SETTINGS)
                self._load_agent_config_keys(
                    ["AI_MODEL", "AI_TEMPERATURE", "MAX_TOKENS", "autonomous_execution"]
                )
            if "AI_MODEL" in self.PROVIDER_SETTINGS:
                self.AI_MODEL = self.PROVIDER_SETTINGS["AI_MODEL"]
                if self.AI_MODEL == "":
                    self.AI_MODEL = "default"
            else:
                self.AI_MODEL = "openassistant"
            if "embedder" in self.PROVIDER_SETTINGS:
                self.EMBEDDER = self.PROVIDER_SETTINGS["embedder"]
            else:
                if self.AI_PROVIDER == "openai":
                    self.EMBEDDER = "openai"
                else:
                    self.EMBEDDER = "default"
            if "MAX_TOKENS" in self.PROVIDER_SETTINGS:
                self.MAX_TOKENS = self.PROVIDER_SETTINGS["MAX_TOKENS"]
            else:
                self.MAX_TOKENS = 4000
            if "LOG_REQUESTS" in self.PROVIDER_SETTINGS:
                self.LOG_REQUESTS = self.PROVIDER_SETTINGS["LOG_REQUESTS"]
            else:
                self.LOG_REQUESTS = True
            if "autonomous_execution" in self.PROVIDER_SETTINGS:
                self.AUTONOMOUS_EXECUTION = self.PROVIDER_SETTINGS[
                    "autonomous_execution"
                ]
            else:
                self.AUTONOMOUS_EXECUTION = True
            self.commands = self.load_commands()
            self.available_commands = Extensions(
                agent_config=self.AGENT_CONFIG
            ).get_available_commands()
            self.clean_agent_config_commands()
            self.history = self.load_history()
            self.agent_instances = {}
            self.agent_config = self.load_agent_config()
            if self.LOG_REQUESTS:
                Path(
                    os.path.normpath(
                        os.path.join(
                            self.folder_path,
                            "requests",
                        )
                    )
                ).mkdir(parents=True, exist_ok=True)

    def get_memories(self):
        return Memories(self.agent_name, self.AGENT_CONFIG)

    async def execute(self, command_name, command_args):
        return await Extensions(agent_config=self.AGENT_CONFIG).execute_command(
            command_name=command_name, command_args=command_args
        )

    async def instruct(self, prompt, tokens):
        if not prompt:
            return ""
        answer = await self.PROVIDER.instruct(prompt=prompt, tokens=tokens)
        if self.LOG_REQUESTS:
            log_file = os.path.join(
                "agents", self.agent_name, "requests", f"{time.time()}.txt"
            )
            with open(
                log_file,
                "a" if os.path.exists(log_file) else "w",
                encoding="utf-8",
            ) as f:
                f.write(f"{prompt}\n{answer}")
        return answer

    def _load_agent_config_keys(self, keys):
        for key in keys:
            if key in self.AGENT_CONFIG:
                setattr(self, key, self.AGENT_CONFIG[key])

    def clean_agent_config_commands(self):
        for command in self.commands:
            friendly_name = command[0]
            if friendly_name not in self.AGENT_CONFIG["commands"]:
                self.AGENT_CONFIG["commands"][friendly_name] = False
        for command in list(self.AGENT_CONFIG["commands"]):
            if command not in [cmd[0] for cmd in self.commands]:
                del self.AGENT_CONFIG["commands"][command]
        with open(self.config_path, "w") as f:
            json.dump(self.AGENT_CONFIG, f)

    def get_commands_string(self):
        if len(self.available_commands) == 0:
            return None

        enabled_commands = filter(
            lambda command: command.get("enabled", True), self.available_commands
        )
        if not enabled_commands:
            return None

        friendly_names = map(
            lambda command: f"`{command['friendly_name']}` - Arguments: {command['args']}",
            enabled_commands,
        )
        command_list = "\n".join(friendly_names)
        return f"Commands Available To Complete Task:\n{command_list}\n\n"

    def get_provider(self):
        config_file = self.get_agent_config()
        if "provider" in config_file:
            return config_file["provider"]
        else:
            return "openai"

    def get_command_params(self, func):
        params = {}
        sig = signature(func)
        for name, param in sig.parameters.items():
            if param.default == Parameter.empty:
                params[name] = None
            else:
                params[name] = param.default
        return params

    def load_commands(self):
        commands = []
        command_files = glob.glob("extensions/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            module = importlib.import_module(f"extensions.{module_name}")
            command_class = getattr(module, module_name.lower())()
            if hasattr(command_class, "commands"):
                for command_name, command_function in command_class.commands.items():
                    params = self.get_command_params(command_function)
                    commands.append((command_name, command_function.__name__, params))
        return commands

    def create_agent_config_file(self, provider_settings, commands):
        if (
            provider_settings is None
            or provider_settings == ""
            or provider_settings == {}
        ):
            provider_settings = DEFAULT_SETTINGS
        settings = json.dumps(
            {
                "commands": commands,
                "settings": provider_settings,
            }
        )

        # Check and create agent directory if it doesn't exist
        if not os.path.exists(os.path.join("agents", self.agent_name)):
            os.makedirs(os.path.join("agents", self.agent_name))

        # Write the settings to the agent config file
        with open(self.config_path, "w") as f:
            f.write(settings)

        return self.config_path

    def load_agent_config(self):
        try:
            with open(self.config_path) as agent_config:
                try:
                    agent_config_data = json.load(agent_config)
                    return agent_config_data
                except json.JSONDecodeError:
                    agent_config_data = {}
                    # Populate the agent_config with all commands enabled
                    agent_config_data["commands"] = {
                        command_name: "false"
                        for command_name, _, _ in self.load_commands(self.agent_name)
                    }
                    agent_config_data["settings"] = DEFAULT_SETTINGS
                    # Save the updated agent_config to the file
                    with open(self.config_path, "w") as agent_config_file:
                        json.dump(agent_config_data, agent_config_file)
                    return agent_config_data
        except:
            with open(self.config_path, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "commands": {
                                command_name: "false"
                                for command_name, _, _ in self.load_commands()
                            },
                            "settings": DEFAULT_SETTINGS,
                        }
                    )
                )
        return agent_config_data

    def get_agent_config(self):
        while True:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r") as f:
                        file_content = f.read().strip()
                        if file_content:
                            return json.loads(file_content)
                except:
                    None
            add_agent(agent_name=self.agent_name)
            return self.get_agent_config()

    def update_agent_config(self, new_config, config_key):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                current_config = json.load(f)

            # Ensure the config_key is present in the current configuration
            if config_key not in current_config:
                current_config[config_key] = {}

            # Update the specified key with new_config while preserving other keys and values
            for key, value in new_config.items():
                current_config[config_key][key] = value

            # Save the updated configuration back to the file
            with open(self.config_path, "w") as f:
                json.dump(current_config, f)
            return f"Agent {self.agent_name} configuration updated."
        else:
            return f"Agent {self.agent_name} configuration not found."

    def get_history(self):
        if not os.path.exists(self.history_file):
            with open(self.history_file, "w") as f:
                f.write("")
            return []
        try:
            with open(self.history_file, "r") as f:
                yaml_history = yaml.safe_load(f)
            if "interactions" in yaml_history:
                return yaml_history["interactions"]
            return []
        except:
            return []

    def wipe_agent_memories(self):
        memories_folder = os.path.normpath(
            os.path.join(os.getcwd(), self.agent_name, "memories")
        )
        if not memories_folder.startswith(os.getcwd()):
            raise ValueError("Invalid path, agent name must not contain slashes.")

        if os.path.exists(memories_folder):
            shutil.rmtree(memories_folder)

    def load_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, "r") as file:
                memory = yaml.safe_load(file)
        else:
            with open(self.history_file, "w") as file:
                yaml.safe_dump({"interactions": []}, file)
            memory = {"interactions": []}
        return memory

    def save_history(self):
        with open(self.history_file, "w") as file:
            yaml.safe_dump(self.history, file)

    def log_interaction(self, role: str, message: str):
        if self.history is None:
            self.history = {"interactions": []}
        self.history["interactions"].append(
            {
                "role": role,
                "message": message,
                "timestamp": datetime.now().strftime("%B %d, %Y %I:%M %p"),
            }
        )
        self.save_history()

    def delete_history(self):
        try:
            self.history = {"interactions": []}
            self.save_history()
            return "History deleted."
        except:
            return "History not found."

    def delete_history_message(self, message: str):
        try:
            self.history["interactions"] = [
                interaction
                for interaction in self.history["interactions"]
                if interaction["message"] != message
            ]
            self.save_history()
            return "Message deleted."
        except:
            return "Message not found."
