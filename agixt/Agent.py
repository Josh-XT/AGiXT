import os
import json
import glob
import shutil
import importlib
from inspect import signature, Parameter
from DBConnection import (
    Agent as AgentModel,
    AgentSetting as AgentSettingModel,
    Message as MessageModel,
    session,
)
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
    "AUTONOMOUS_EXECUTION": False,
}


def add_agent(agent_name, provider_settings=None, commands={}):
    if not agent_name:
        return {"message": "Agent name cannot be empty."}

    agent = AgentModel(name=agent_name)
    session.add(agent)
    session.commit()

    if provider_settings is None or provider_settings == "" or provider_settings == {}:
        provider_settings = DEFAULT_SETTINGS

    settings = json.dumps(
        {
            "commands": commands,
            "settings": provider_settings,
        }
    )
    agent_setting = AgentSettingModel(
        agent_id=agent.id,
        name="config",
        value=settings,
    )
    session.add(agent_setting)
    session.commit()

    return {"message": f"Agent {agent_name} created."}


def delete_agent(agent_name):
    agent = session.query(AgentModel).filter_by(name=agent_name).first()
    if not agent:
        return {"message": f"Agent {agent_name} not found."}, 404

    session.delete(agent)
    session.commit()

    return {"message": f"Agent {agent_name} deleted."}, 200


def rename_agent(agent_name, new_name):
    agent = session.query(AgentModel).filter_by(name=agent_name).first()
    if not agent:
        return {"message": f"Agent {agent_name} not found."}, 404

    agent.name = new_name
    session.commit()

    return {"message": f"Agent {agent_name} renamed to {new_name}."}, 200


def get_agents():
    agents = session.query(AgentModel).all()
    output = []

    for agent in agents:
        output.append({"name": agent.name, "status": False})

    return output


class Agent:
    def __init__(self, agent_name=None):
        self.agent_name = agent_name if agent_name is not None else "AGiXT"
        self.AGENT_CONFIG = self.get_agent_config()
        if "settings" in self.AGENT_CONFIG:
            self.PROVIDER_SETTINGS = self.AGENT_CONFIG["settings"]
            if self.PROVIDER_SETTINGS == {}:
                self.PROVIDER_SETTINGS = DEFAULT_SETTINGS
            if "provider" in self.PROVIDER_SETTINGS:
                self.AI_PROVIDER = self.PROVIDER_SETTINGS["provider"]
                self.PROVIDER = Provider(self.AI_PROVIDER, **self.PROVIDER_SETTINGS)
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
                        True if self.AUTONOMOUS_EXECUTION == "true" else False
                    )
            else:
                self.AUTONOMOUS_EXECUTION = True
            self.commands = self.load_commands()
            self.available_commands = Extensions(
                agent_config=self.AGENT_CONFIG
            ).get_available_commands()
            self.clean_agent_config_commands()
            self.history = self.load_history()
            self.agent_instances = {}

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
        agent_setting = (
            session.query(AgentSettingModel)
            .filter(
                AgentSettingModel.agent_id == AgentModel.id,
                AgentSettingModel.name == "config",
                AgentModel.name == self.agent_name,
            )
            .first()
        )
        agent_setting.value = json.dumps(self.AGENT_CONFIG)
        session.commit()

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

    def get_agent_config(self):
        agent_setting = (
            session.query(AgentSettingModel)
            .filter(
                AgentSettingModel.agent_id == AgentModel.id,
                AgentSettingModel.name == "config",
                AgentModel.name == self.agent_name,
            )
            .first()
        )
        if agent_setting:
            return json.loads(agent_setting.value)
        else:
            return {}

    def update_agent_config(self, new_config, config_key):
        agent_setting = (
            session.query(AgentSettingModel)
            .filter(
                AgentSettingModel.agent_id == AgentModel.id,
                AgentSettingModel.name == "config",
                AgentModel.name == self.agent_name,
            )
            .first()
        )
        if agent_setting:
            current_config = json.loads(agent_setting.value)

            # Ensure the config_key is present in the current configuration
            if config_key not in current_config:
                current_config[config_key] = {}

            # Update the specified key with new_config while preserving other keys and values
            for key, value in new_config.items():
                current_config[config_key][key] = value

            agent_setting.value = json.dumps(current_config)
            session.commit()
            return f"Agent {self.agent_name} configuration updated."
        else:
            return f"Agent {self.agent_name} configuration not found."

    def wipe_agent_memories(self):
        memories_folder = os.path.normpath(
            os.path.join(os.getcwd(), self.agent_name, "memories")
        )
        if not memories_folder.startswith(os.getcwd()):
            raise ValueError("Invalid path, agent name must not contain slashes.")

        if os.path.exists(memories_folder):
            shutil.rmtree(memories_folder)

    def load_history(self):
        agent = session.query(AgentModel).filter_by(name=self.agent_name).first()

        if agent:
            messages = (
                session.query(MessageModel)
                .filter(MessageModel.agent_id == agent.id)
                .all()
            )
            history = {"interactions": []}

            for message in messages:
                history["interactions"].append(
                    {
                        "role": message.role,
                        "message": message.content,
                        "timestamp": message.timestamp.strftime("%B %d, %Y %I:%M %p"),
                    }
                )

            return history
        else:
            return {"interactions": []}

    def save_history(self):
        agent = session.query(AgentModel).filter_by(name=self.agent_name).first()

        if agent:
            messages = []
            for interaction in self.history["interactions"]:
                message = MessageModel(
                    role=interaction["role"],
                    content=interaction["message"],
                    timestamp=datetime.strptime(
                        interaction["timestamp"], "%B %d, %Y %I:%M %p"
                    ),
                    conversation_id=None,  # Modify this as per your schema
                    agent_id=agent.id,
                )
                messages.append(message)

            session.add_all(messages)
            session.commit()

    def log_interaction(self, role: str, message: str):
        if self.history is None:
            self.history = {"interactions": []}

        timestamp = datetime.now().strftime("%B %d, %Y %I:%M %p")
        self.history["interactions"].append(
            {"role": role, "message": message, "timestamp": timestamp}
        )

    def save_setting(self, setting_name, setting_value):
        agent_setting = (
            session.query(AgentSettingModel)
            .filter(
                AgentSettingModel.agent_id == AgentModel.id,
                AgentSettingModel.name == setting_name,
                AgentModel.name == self.agent_name,
            )
            .first()
        )
        if agent_setting:
            agent_setting.value = setting_value
            session.commit()
            return f"Agent {self.agent_name} setting {setting_name} updated."
        else:
            agent = session.query(AgentModel).filter_by(name=self.agent_name).first()
            agent_setting = AgentSettingModel(
                agent_id=agent.id, name=setting_name, value=setting_value
            )
            session.add(agent_setting)
            session.commit()
            return f"Agent {self.agent_name} setting {setting_name} created."

    def get_setting(self, setting_name):
        agent_setting = (
            session.query(AgentSettingModel)
            .filter(
                AgentSettingModel.agent_id == AgentModel.id,
                AgentSettingModel.name == setting_name,
                AgentModel.name == self.agent_name,
            )
            .first()
        )
        if agent_setting:
            return agent_setting.value
        else:
            return None

    def delete_setting(self, setting_name):
        agent_setting = (
            session.query(AgentSettingModel)
            .filter(
                AgentSettingModel.agent_id == AgentModel.id,
                AgentSettingModel.name == setting_name,
                AgentModel.name == self.agent_name,
            )
            .first()
        )
        if agent_setting:
            session.delete(agent_setting)
            session.commit()
            return f"Agent {self.agent_name} setting {setting_name} deleted."
        else:
            return f"Agent {self.agent_name} setting {setting_name} not found."
