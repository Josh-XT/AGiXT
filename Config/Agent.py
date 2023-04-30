import os
import json
import glob
import uuid
import shutil
import importlib
import yaml
from pathlib import Path
from dotenv import load_dotenv
from inspect import signature, Parameter
from provider import Provider
from Config import Config

load_dotenv()


class Agent(Config):
    def __init__(self, agent_name=None):
        # General Configuration
        self.AGENT_NAME = agent_name if agent_name is not None else "default"
        # Need to get the following from the agent config file:
        self.AGENT_CONFIG = self.get_agent_config()
        # AI Configuration
        if self.AGENT_CONFIG is not None:
            if "provider" in self.AGENT_CONFIG:
                self.AI_PROVIDER = self.AGENT_CONFIG["provider"]
            else:
                self.AI_PROVIDER = "huggingchat"
            if "settings" in self.AGENT_CONFIG:
                self.PROVIDER_SETTINGS = self.AGENT_CONFIG["settings"]
            else:
                self.PROVIDER_SETTINGS = {
                    "AI_MODEL": "openassistant",
                    "AI_TEMPERATURE": 0.9,
                    "MAX_TOKENS": 2096,
                }
            self.PROVIDER = Provider(self.AI_PROVIDER, **self.PROVIDER_SETTINGS)
            self.instruct = self.PROVIDER.instruct
            self._load_agent_config_keys(["AI_MODEL", "AI_TEMPERATURE", "MAX_TOKENS"])
        self.AI_MODEL = self.PROVIDER_SETTINGS["AI_MODEL"]
        if not os.path.exists(f"model-prompts/{self.AI_MODEL}"):
            self.AI_MODEL = "default"
        with open(f"model-prompts/{self.AI_MODEL}/execute.txt", "r") as f:
            self.EXECUTION_PROMPT = f.read()
        with open(f"model-prompts/{self.AI_MODEL}/task.txt", "r") as f:
            self.TASK_PROMPT = f.read()
        with open(f"model-prompts/{self.AI_MODEL}/priority.txt", "r") as f:
            self.PRIORITY_PROMPT = f.read()

        self.COMMANDS_ENABLED = os.getenv("COMMANDS_ENABLED", "true").lower()

        # Memory Settings
        self.NO_MEMORY = os.getenv("NO_MEMORY", "false").lower()
        self.USE_LONG_TERM_MEMORY_ONLY = os.getenv(
            "USE_LONG_TERM_MEMORY_ONLY", "false"
        ).lower()

        # Yaml Memory
        self.memory_folder = "agents"
        self.memory_file = f"{self.memory_folder}/{self.AGENT_NAME}.yaml"
        self._create_parent_directories(self.memory_file)
        self.memory = self.load_memory()
        self.agent_instances = {}
        self.commands = {}

    def _load_agent_config_keys(self, keys):
        for key in keys:
            if key in self.AGENT_CONFIG:
                setattr(self, key, self.AGENT_CONFIG[key])

    def _create_parent_directories(self, file_path):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    def get_provider(self):
        config_file = self.get_agent_config()
        if "provider" in config_file:
            return config_file["provider"]
        else:
            return "openai"

    def create_agent_folder(self, agent_name):
        agent_folder = f"agents/{agent_name}"
        if not os.path.exists("agents"):
            os.makedirs("agents")
        if not os.path.exists(agent_folder):
            os.makedirs(agent_folder)
        return agent_folder

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
        command_files = glob.glob("commands/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            module = importlib.import_module(f"commands.{module_name}")
            command_class = getattr(module, module_name)()
            if hasattr(command_class, "commands"):
                for command_name, command_function in command_class.commands.items():
                    params = self.get_command_params(command_function)
                    commands.append((command_name, command_function.__name__, params))
        return commands

    def load_command_files(self):
        command_files = glob.glob("commands/*.py")
        return command_files

    def create_agent_config_file(self, agent_name, **kwargs):
        agent_config_file = os.path.join(agent_name, "config.json")
        if not os.path.exists(agent_config_file):
            with open(agent_config_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "commands": {
                                command_name: "false"
                                for command_name, _, _ in self.commands
                            },
                            **kwargs,
                        }
                    )
                )
        return agent_config_file

    def load_agent_config(self, agent_name):
        try:
            with open(
                os.path.join("agents", agent_name, "config.json")
            ) as agent_config:
                try:
                    agent_config_data = json.load(agent_config)
                except json.JSONDecodeError:
                    agent_config_data = {}
                    # Populate the agent_config with all commands enabled
                    agent_config_data["commands"] = {
                        command_name: "false"
                        for command_name, _, _ in self.load_commands(agent_name)
                    }
                    agent_config_data["provider"] = "huggingchat"
                    # Save the updated agent_config to the file
                    with open(
                        os.path.join("agents", agent_name, "config.json"), "w"
                    ) as agent_config_file:
                        json.dump(agent_config_data, agent_config_file)
        except:
            # Add all commands to agent/{agent_name}/config.json in this format {"command_name": "false"}
            agent_config_file = os.path.join("agents", agent_name, "config.json")
            with open(agent_config_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "commands": {
                                command_name: "false"
                                for command_name, _, _ in self.commands
                            },
                            "provider": "huggingchat",
                        }
                    )
                )
        return agent_config_data

    def create_agent_yaml_file(self, agent_name):
        memories_dir = "agents"
        if not os.path.exists(memories_dir):
            os.makedirs(memories_dir)
        i = 0
        agent_file = f"{agent_name}.yaml"
        while os.path.exists(os.path.join(memories_dir, agent_file)):
            i += 1
            agent_file = f"{agent_name}_{i}.yaml"
        with open(os.path.join(memories_dir, agent_file), "w") as f:
            f.write("")
        return agent_file

    def write_agent_config(self, agent_config, config_data):
        with open(agent_config, "w") as f:
            json.dump(config_data, f)

    def add_agent(self, agent_name, provider_settings):
        agent_file = self.create_agent_yaml_file(agent_name)
        agent_folder = self.create_agent_folder(agent_name)
        agent_config = self.create_agent_config_file(agent_folder, provider_settings)
        commands_list = self.load_commands()
        command_dict = {}
        for command in commands_list:
            friendly_name, command_name, command_args = command
            command_dict[friendly_name] = True
        self.write_agent_config(agent_config, {"commands": command_dict})
        return {"agent_file": agent_file}

    def rename_agent(self, agent_name, new_name):
        agent_file = f"agents/{agent_name}.yaml"
        agent_folder = f"agents/{agent_name}/"
        agent_file = os.path.abspath(agent_file)
        agent_folder = os.path.abspath(agent_folder)
        if os.path.exists(agent_file):
            os.rename(agent_file, os.path.join("agents", f"{new_name}.yaml"))
        if os.path.exists(agent_folder):
            os.rename(agent_folder, os.path.join("agents", f"{new_name}"))

    def delete_agent(self, agent_name):
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

    def get_agents(self):
        memories_dir = "agents"
        if not os.path.exists(memories_dir):
            os.makedirs(memories_dir)
        agents = []
        for file in os.listdir(memories_dir):
            if file.endswith(".yaml"):
                agents.append(file.replace(".yaml", ""))
        output = []
        if not agents:
            # Create a new agent
            self.add_agent("Agent-LLM")
            agents = ["Agent-LLM"]
        for agent in agents:
            try:
                agent_instance = self.agent_instances[agent]
                status = agent_instance.get_status()
            except:
                status = False
            output.append({"name": agent, "status": status})
        return output

    def get_agent_config(self):
        agent_file = os.path.abspath(f"agents/{self.AGENT_NAME}/config.json")
        if os.path.exists(agent_file):
            with open(agent_file, "r") as f:
                agent_config = json.load(f)
        else:
            self.add_agent(self.AGENT_NAME)
            agent_config = self.get_agent_config()
        return agent_config

    def update_agent_config(self, agent_name, config):
        with open(
            os.path.join("agents", agent_name, "config.json"), "w"
        ) as agent_config:
            json.dump(config, agent_config)

    def get_chat_history(self, agent_name):
        if not os.path.exists(os.path.join("agents", f"{agent_name}.yaml")):
            return ""
        with open(os.path.join("agents", f"{agent_name}.yaml"), "r") as f:
            chat_history = f.read()
        return chat_history

    def wipe_agent_memories(self, agent_name):
        agent_folder = f"agents/{agent_name}/"
        agent_folder = os.path.abspath(agent_folder)
        memories_folder = os.path.join(agent_folder, "memories")
        if os.path.exists(memories_folder):
            shutil.rmtree(memories_folder)

    def load_memory(self):
        if os.path.isfile(self.memory_file):
            with open(self.memory_file, "r") as file:
                memory = yaml.safe_load(file)
                if memory is None:
                    memory = {"interactions": []}
        else:
            memory = {"interactions": []}
        return memory

    def save_memory(self):
        with open(self.memory_file, "w") as file:
            yaml.safe_dump(self.memory, file)

    def log_interaction(self, role: str, message: str):
        self.memory["interactions"].append({"role": role, "message": message})
        self.save_memory()

    def get_task_output(self, agent_name, primary_objective=None):
        if primary_objective is None:
            return "No primary objective specified."
        task_output_file = os.path.join(
            "agents", agent_name, "tasks", f"{primary_objective}.txt"
        )
        if os.path.exists(task_output_file):
            with open(task_output_file, "r") as f:
                task_output = f.read()
        else:
            task_output = ""
        return task_output

    def save_task_output(self, agent_name, task_output, primary_objective=None):
        # Check if agents/{agent_name}/tasks/task_name.txt exists
        # If it does, append to it
        # If it doesn't, create it
        if "tasks" not in os.listdir(os.path.join("agents", agent_name)):
            os.makedirs(os.path.join("agents", agent_name, "tasks"))
        if primary_objective is None:
            primary_objective = str(uuid.uuid4())
        task_output_file = os.path.join(
            "agents", agent_name, "tasks", f"{primary_objective}.txt"
        )
        with open(
            task_output_file,
            "a" if os.path.exists(task_output_file) else "w",
            encoding="utf-8",
        ) as f:
            f.write(task_output)
        return task_output
