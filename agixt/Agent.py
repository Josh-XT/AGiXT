# The Agent class is a Python class that represents an AI agent and provides methods for interacting
# with it, managing its configuration and memory, and executing commands.
# The Agent class is a Python class that represents an AI agent and provides methods for interacting
# with it, managing its configuration and memory, and executing commands.
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

DEFAULT_SETTINGS = {
    "provider": "gpt4free",
    "AI_MODEL": "gpt-4",
    "AI_TEMPERATURE": "0.7",
    "MAX_TOKENS": "4000",
    "embedder": "default",
    "LOG_REQUESTS": False,
}


class Agent:
    def __init__(self, agent_name=None):
        """
        This is the initialization function for an agent, which loads configurations and settings for the
        agent, including AI-related settings.

        :param agent_name: The name of the agent being initialized. If no name is provided, it defaults to
        "AGiXT"
        """
        # General Configuration
        self.agent_name = agent_name if agent_name is not None else "AGiXT"
        # Need to get the following from the agent config file:
        self.AGENT_CONFIG = self.get_agent_config()
        self.commands = self.load_commands()
        self.available_commands = Extensions(self.AGENT_CONFIG).get_available_commands()
        self.clean_agent_config_commands()
        # AI Configuration
        if "settings" in self.AGENT_CONFIG:
            self.PROVIDER_SETTINGS = self.AGENT_CONFIG["settings"]
            if "provider" in self.PROVIDER_SETTINGS:
                self.AI_PROVIDER = self.PROVIDER_SETTINGS["provider"]
                self.PROVIDER = Provider(self.AI_PROVIDER, **self.PROVIDER_SETTINGS)
            self._load_agent_config_keys(["AI_MODEL", "AI_TEMPERATURE", "MAX_TOKENS"])
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

        # Yaml Memory
        self.memory_file = f"agents/{self.agent_name}.yaml"
        self._create_parent_directories(self.memory_file)
        self.memory = self.load_memory()
        self.agent_instances = {}
        self.agent_config = self.load_agent_config(self.agent_name)
        self.commands = self.load_commands()
        if self.LOG_REQUESTS:
            Path(
                os.path.join(
                    "agents",
                    self.agent_name,
                    "requests",
                )
            ).mkdir(parents=True, exist_ok=True)

    def get_memories(self):
        return Memories(self.agent_name, self.AGENT_CONFIG)

    async def execute(self, command_name, command_args):
        return await Extensions(self.AGENT_CONFIG).execute_command(
            command_name=command_name, command_args=command_args, agent=self
        )

    def instruct(self, prompt, tokens):
        """
        This function takes a prompt and tokens as input, sends the prompt to a provider for a response,
        logs the request if enabled, and returns the response.

        :param prompt: a string representing the user's input or request to the coding assistant
        :param tokens: tokens is a list of strings that represent additional information or context that can
        be used to generate a response to the prompt. These tokens can be used by the PROVIDER to better
        understand the user's intent and provide a more accurate response
        :return: The function `instruct` returns the `answer` variable.
        """
        if not prompt:
            return ""
        answer = self.PROVIDER.instruct(prompt, tokens)
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
        """
        This function loads agent configuration keys and sets their values as attributes of the object.

        :param keys: A list of strings representing the keys to be loaded from the agent configuration
        """
        for key in keys:
            if key in self.AGENT_CONFIG:
                setattr(self, key, self.AGENT_CONFIG[key])

    def _create_parent_directories(self, file_path):
        """
        This function creates parent directories for a given file path if they do not already exist.

        :param file_path: The file path is a string that represents the location of a file on the file
        system. It includes the directory path and the file name. For example,
        "/home/user/documents/myfile.txt" is a file path where "/home/user/documents" is the directory path
        and "myfile.txt" is the
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    def clean_agent_config_commands(self):
        """
        This function cleans up the agent configuration commands by adding missing commands and removing
        unnecessary ones.
        """
        for command in self.commands:
            friendly_name = command[0]
            if friendly_name not in self.AGENT_CONFIG["commands"]:
                self.AGENT_CONFIG["commands"][friendly_name] = False
        for command in list(self.AGENT_CONFIG["commands"]):
            if command not in [cmd[0] for cmd in self.commands]:
                del self.AGENT_CONFIG["commands"][command]
        with open(f"agents/{self.agent_name}/config.json", "w") as f:
            json.dump(self.AGENT_CONFIG, f)

    def get_commands_string(self):
        """
        This function returns a string containing a list of available commands for completing a task.
        :return: The function `get_commands_string` returns a string that lists the available commands to
        complete a task. If there are no available commands or all available commands are disabled, it
        returns `None`. Otherwise, it returns a string that lists the friendly name, name, and arguments of
        each enabled command.
        """
        if len(self.available_commands) == 0:
            return None

        enabled_commands = filter(
            lambda command: command.get("enabled", True), self.available_commands
        )
        if not enabled_commands:
            return None

        friendly_names = map(
            lambda command: f"{command['friendly_name']} - {command['name']}({command['args']})",
            enabled_commands,
        )
        command_list = "\n".join(friendly_names)
        return f"Commands Available To Complete Task:\n{command_list}\n\n"

    def get_provider(self):
        """
        This function returns the provider specified in the agent configuration file or "openai" if not
        specified.
        :return: The function `get_provider` returns the value of the key "provider" from the agent
        configuration file if it exists, otherwise it returns the string "openai".
        """
        config_file = self.get_agent_config()
        if "provider" in config_file:
            return config_file["provider"]
        else:
            return "openai"

    def create_agent_folder(self, agent_name):
        """
        This function creates a folder for a given agent name in the "agents" directory if it does not
        already exist.

        :param agent_name: The name of the agent for which a folder needs to be created
        :return: the path of the agent folder that was created or already exists.
        """
        agent_folder = f"agents/{agent_name}"
        if not os.path.exists("agents"):
            os.makedirs("agents")
        if not os.path.exists(agent_folder):
            os.makedirs(agent_folder)
        return agent_folder

    def get_command_params(self, func):
        """
        This function retrieves the parameters and default values of a given function.

        :param func: a function object for which we want to retrieve the parameters and their default values
        :return: The function `get_command_params` returns a dictionary containing the parameters of a given
        function `func`. The keys of the dictionary are the parameter names, and the values are either
        `None` if the parameter has no default value, or the default value of the parameter if it has one.
        """
        params = {}
        sig = signature(func)
        for name, param in sig.parameters.items():
            if param.default == Parameter.empty:
                params[name] = None
            else:
                params[name] = param.default
        return params

    def load_commands(self):
        """
        This function loads commands from Python files in a specific directory and returns a list of tuples
        containing information about each command.
        :return: The function `load_commands` returns a list of tuples, where each tuple contains the name
        of a command, the name of the function that implements the command, and a list of parameters that
        the command function takes.
        """
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

    def create_agent_config_file(self, agent_name, provider_settings, commands):
        """
        This function creates a configuration file for a given agent with specified provider settings and
        commands.

        :param agent_name: a string representing the name of the agent being created
        :param provider_settings: A dictionary containing the settings for the agent's provider. If it is
        None, an empty string, or an empty dictionary, the default settings will be used
        :param commands: a list of commands that the agent can execute
        :return: the path of the agent config file that was created.
        """
        agent_dir = os.path.join("agents", agent_name)
        agent_config_file = os.path.join(agent_dir, "config.json")
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
        if not os.path.exists(agent_dir):
            os.makedirs(agent_dir)

        # Write the settings to the agent config file
        with open(agent_config_file, "w") as f:
            f.write(settings)

        return agent_config_file

    def load_agent_config(self, agent_name):
        """
        This function loads the configuration data for a given agent, and if the configuration file is
        missing or invalid, it creates a new one with default settings and all commands disabled.

        :param agent_name: The name of the agent whose configuration is being loaded
        :return: the agent configuration data as a dictionary. If the configuration file does not exist or
        is invalid, it creates a new configuration file with all commands disabled and default settings, and
        returns the new configuration data. If there is an error while creating the new configuration file,
        it returns an empty dictionary.
        """
        try:
            with open(
                os.path.join("agents", agent_name, "config.json")
            ) as agent_config:
                try:
                    agent_config_data = json.load(agent_config)
                    return agent_config_data
                except json.JSONDecodeError:
                    agent_config_data = {}
                    # Populate the agent_config with all commands enabled
                    agent_config_data["commands"] = {
                        command_name: "false"
                        for command_name, _, _ in self.load_commands(agent_name)
                    }
                    agent_config_data["settings"] = DEFAULT_SETTINGS
                    # Save the updated agent_config to the file
                    with open(
                        os.path.join("agents", agent_name, "config.json"), "w"
                    ) as agent_config_file:
                        json.dump(agent_config_data, agent_config_file)
                    return agent_config_data
        except:
            # Add all commands to agent/{agent_name}/config.json in this format {"command_name": "false"}
            agent_config_file = os.path.join("agents", agent_name, "config.json")
            with open(agent_config_file, "w") as f:
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

    def add_agent(self, agent_name, provider_settings):
        """
        This function adds a new agent with default or provided settings and creates a configuration file
        for the agent.

        :param agent_name: A string representing the name of the agent being added
        :param provider_settings: A dictionary containing settings for the agent's provider. If no settings
        are provided, the function will use default settings
        :return: A dictionary with the key "agent_file" and the value being the name of the agent's YAML
        file.
        """
        if not agent_name:
            return "Agent name cannot be empty."
        provider_settings = (
            DEFAULT_SETTINGS if not provider_settings else provider_settings
        )
        self.create_agent_folder(agent_name)
        commands_list = self.load_commands()
        command_dict = {}
        for command in commands_list:
            friendly_name, command_name, command_args = command
            command_dict[friendly_name] = False
        self.create_agent_config_file(agent_name, provider_settings, command_dict)
        with open(os.path.join("agents", f"{agent_name}.yaml"), "w") as f:
            f.write("")
        return {"agent_file": f"{agent_name}.yaml"}

    def rename_agent(self, agent_name, new_name):
        """
        This function renames an agent by updating the agent's name in a YAML file and renaming the agent's
        folder.

        :param agent_name: The current name of the agent that needs to be renamed
        :param new_name: The new name that the agent will be renamed to
        """
        self.agent_name = new_name
        agent_file = f"agents/{agent_name}.yaml"
        agent_folder = f"agents/{agent_name}/"
        agent_file = os.path.abspath(agent_file)
        agent_folder = os.path.abspath(agent_folder)
        if os.path.exists(agent_file):
            os.rename(agent_file, os.path.join("agents", f"{new_name}.yaml"))
        if os.path.exists(agent_folder):
            os.rename(agent_folder, os.path.join("agents", f"{new_name}"))

    def delete_agent(self, agent_name):
        """
        This function deletes an agent's YAML file and returns an error message if the file is not found.

        :param agent_name: The name of the agent that needs to be deleted
        :return: If the agent file is not found, a dictionary with a "message" key and a 404 status code is
        returned.
        """
        agent_file = f"agents/{agent_name}.yaml"
        agent_folder = f"agents/{agent_name}/"
        agent_file = os.path.abspath(agent_file)
        agent_folder = os.path.abspath(agent_folder)
        try:
            os.remove(agent_file)
        except FileNotFoundError:
            return {"message": f"Agent file {agent_file} not found."}, 404

        if os.path.exists(agent_folder):
            shutil.rmtree(agent_folder)

        return {"message": f"Agent {agent_name} deleted."}, 200

    def get_agent_config(self):
        """
        This function retrieves the configuration file for a specified agent, and if it does not exist,
        creates a new agent with an empty configuration.
        :return: a dictionary object that contains the configuration settings for the agent specified by
        `self.agent_name`. If the configuration file does not exist, the function creates an empty
        configuration file and returns an empty dictionary. If there is an error reading the configuration
        file, the function returns `None`. The function runs in an infinite loop until it is able to
        successfully read the configuration file or create a new one
        """
        while True:
            agent_file = os.path.abspath(f"agents/{self.agent_name}/config.json")
            if os.path.exists(agent_file):
                try:
                    with open(agent_file, "r") as f:
                        file_content = f.read().strip()
                        if file_content:
                            return json.loads(file_content)
                except:
                    None
            self.add_agent(self.agent_name, {})
            return self.get_agent_config()

    def update_agent_config(self, new_config, config_key):
        """
        This function updates the configuration of an agent by modifying a specific key with new values
        while preserving other keys and values.

        :param new_config: A dictionary containing the new configuration values to be updated
        :param config_key: The parameter `config_key` is a string representing the key in the agent's
        configuration file that needs to be updated with the new configuration
        :return: a string message indicating whether the agent configuration was successfully updated or
        not. If the configuration file exists, the function updates the specified key with the new
        configuration and saves the updated configuration back to the file, and returns "Agent {agent_name}
        configuration updated." If the configuration file does not exist, the function returns "Agent
        {agent_name} configuration not found."
        """
        agent_name = self.agent_name
        agent_config_file = os.path.join("agents", agent_name, "config.json")
        if os.path.exists(agent_config_file):
            with open(agent_config_file, "r") as f:
                current_config = json.load(f)

            # Ensure the config_key is present in the current configuration
            if config_key not in current_config:
                current_config[config_key] = {}

            # Update the specified key with new_config while preserving other keys and values
            for key, value in new_config.items():
                current_config[config_key][key] = value

            # Save the updated configuration back to the file
            with open(agent_config_file, "w") as f:
                json.dump(current_config, f)
            return f"Agent {agent_name} configuration updated."
        else:
            return f"Agent {agent_name} configuration not found."

    def get_chat_history(self, agent_name):
        """
        This function retrieves the chat history of a given agent from a YAML file and returns it as a list
        of dictionaries.

        :param agent_name: The name of the agent whose chat history is being retrieved
        :return: a list of dictionaries representing the chat history for a given agent. If the agent's chat
        history file does not exist, an empty list is returned. If there is an error while reading the file,
        an empty list is also returned.
        """
        # If it doesn't exist, create it
        if not os.path.exists(f"agents/{agent_name}.yaml"):
            with open(f"agents/{agent_name}.yaml", "w") as f:
                f.write("")
            return []
        try:
            with open(f"agents/{agent_name}.yaml", "r") as f:
                yaml_history = yaml.safe_load(f)
            chat_history = []
            for interaction in yaml_history["interactions"]:
                role = interaction["role"]
                message = interaction["message"]
                chat_history.append({role: message})
            return chat_history
        except:
            return []

    def wipe_agent_memories(self, agent_name):
        """
        This function deletes the memories folder of a specified agent if it exists.

        :param agent_name: The name of the agent whose memories need to be wiped
        """
        agent_folder = f"agents/{agent_name}/"
        agent_folder = os.path.abspath(agent_folder)
        memories_folder = os.path.join(agent_folder, "memories")
        if os.path.exists(memories_folder):
            shutil.rmtree(memories_folder)

    def load_memory(self):
        """
        This function loads a YAML file containing memory data and returns it, or creates a new file with
        default data if the file does not exist.
        :return: a dictionary object called `memory` which contains a list of interactions. The interactions
        are loaded from a YAML file if it exists, otherwise an empty list is created and saved to the file.
        """
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r") as file:
                memory = yaml.safe_load(file)
        else:
            with open(self.memory_file, "w") as file:
                yaml.safe_dump({"interactions": []}, file)
            memory = {"interactions": []}
        return memory

    def save_memory(self):
        """
        This Python function saves the memory of an object to a YAML file.
        """
        with open(self.memory_file, "w") as file:
            yaml.safe_dump(self.memory, file)

    def log_interaction(self, role: str, message: str):
        """
        This function logs an interaction by appending the role and message to a memory dictionary and
        saving it.

        :param role: The role of the person or entity that is interacting with the program. It could be a
        user, an administrator, a system, etc
        :type role: str
        :param message: The message parameter is a string that represents the interaction message that is
        being logged. It could be a user's input, a system response, or any other message exchanged during
        the interaction
        :type message: str
        """
        if self.memory is None:
            self.memory = {"interactions": []}
        self.memory["interactions"].append({"role": role, "message": message})
        self.save_memory()
