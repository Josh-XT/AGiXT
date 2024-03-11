import os
import json
import glob
import shutil
import importlib
import logging
from inspect import signature, Parameter
from Providers import Providers
from Extensions import Extensions
from Defaults import DEFAULT_SETTINGS


def get_agent_file_paths(agent_name, user="USER"):
    base_path = os.path.join(os.getcwd(), "agents")
    folder_path = os.path.normpath(os.path.join(base_path, agent_name))
    config_path = os.path.normpath(os.path.join(folder_path, "config.json"))
    if not config_path.startswith(base_path) or not folder_path.startswith(base_path):
        raise ValueError("Invalid path, agent name must not contain slashes.")
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)
    return config_path, folder_path


def add_agent(agent_name, provider_settings=None, commands={}, user="USER"):
    if not agent_name:
        return "Agent name cannot be empty."
    provider_settings = (
        DEFAULT_SETTINGS
        if not provider_settings or provider_settings == {}
        else provider_settings
    )
    config_path, folder_path = get_agent_file_paths(agent_name=agent_name)
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
    return {"message": f"Agent {agent_name} created."}


def delete_agent(agent_name, user="USER"):
    config_path, folder_path = get_agent_file_paths(agent_name=agent_name)
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
        return {"message": f"Agent {agent_name} deleted."}, 200
    except:
        return {"message": f"Agent {agent_name} could not be deleted."}, 400


def rename_agent(agent_name, new_name, user="USER"):
    config_path, folder_path = get_agent_file_paths(agent_name=agent_name)
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


def get_agents(user="USER"):
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
    def __init__(self, agent_name=None, user="USER", ApiClient=None):
        self.USER = user
        self.agent_name = agent_name if agent_name is not None else "AGiXT"
        self.config_path, self.folder_path = get_agent_file_paths(
            agent_name=self.agent_name
        )
        self.AGENT_CONFIG = self.get_agent_config()
        if "settings" in self.AGENT_CONFIG:
            self.PROVIDER_SETTINGS = self.AGENT_CONFIG["settings"]
            if self.PROVIDER_SETTINGS == {}:
                self.PROVIDER_SETTINGS = DEFAULT_SETTINGS
            if "provider" in self.PROVIDER_SETTINGS:
                self.AI_PROVIDER = self.PROVIDER_SETTINGS["provider"]
                self.PROVIDER = Providers(
                    name=self.AI_PROVIDER, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
                )
                self._load_agent_config_keys(
                    ["AI_MODEL", "AI_TEMPERATURE", "MAX_TOKENS", "AUTONOMOUS_EXECUTION"]
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
            if "AUTONOMOUS_EXECUTION" in self.PROVIDER_SETTINGS:
                self.AUTONOMOUS_EXECUTION = self.PROVIDER_SETTINGS[
                    "AUTONOMOUS_EXECUTION"
                ]
                if isinstance(self.AUTONOMOUS_EXECUTION, str):
                    self.AUTONOMOUS_EXECUTION = self.AUTONOMOUS_EXECUTION.lower()
                    self.AUTONOMOUS_EXECUTION = (
                        False if self.AUTONOMOUS_EXECUTION == "false" else True
                    )
            else:
                self.AUTONOMOUS_EXECUTION = True
            self.commands = self.load_commands()
            self.available_commands = Extensions(
                agent_name=self.agent_name,
                agent_config=self.AGENT_CONFIG,
                ApiClient=ApiClient,
                user=user,
            ).get_available_commands()
            self.clean_agent_config_commands()

    async def inference(self, prompt, tokens):
        if not prompt:
            return ""
        answer = await self.PROVIDER.inference(prompt=prompt, tokens=tokens)
        return answer.replace("\_", "_")

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
            return ""
        working_dir = (
            self.AGENT_CONFIG["WORKING_DIRECTORY"]
            if "WORKING_DIRECTORY" in self.AGENT_CONFIG
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        verbose_commands = f"### Available Commands\n**The assistant has commands available to use if they would be useful to provide a better user experience.**\nIf a file needs saved, the assistant's working directory is {working_dir}, use that as the file path.\n\n"
        verbose_commands += "**See command execution examples of commands that the assistant has access to below:**\n"
        for command in self.available_commands:
            command_args = json.dumps(command["args"])
            command_args = command_args.replace(
                '""',
                '"The assistant will fill in the value based on relevance to the conversation."',
            )
            verbose_commands += (
                f"\n- #execute('{command['friendly_name']}', {command_args})"
            )
        verbose_commands += "\n\n**To execute an available command, the assistant can reference the examples and the command execution response will be replaced with the commands output for the user in the assistants response. The assistant can execute a command anywhere in the response and the commands will be executed in the order they are used.**\n**THE ASSISTANT CANNOT EXECUTE A COMMAND THAT IS NOT ON THE LIST OF EXAMPLES!**\n\n"
        return verbose_commands

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
