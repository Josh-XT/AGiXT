import os
import json
import shutil
from DBConnection import (
    Agent as AgentModel,
    AgentSetting as AgentSettingModel,
    Command,
    AgentCommand,
    ProviderSetting,
    AgentProvider,
    AgentProviderSetting,
    ChainStep,
    ChainStepArgument,
    ChainStepResponse,
    Provider as ProviderModel,
    session,
)
from Providers import Providers
from Memories import Memories
from Extensions import Extensions

DEFAULT_SETTINGS = {
    "provider": "openai",
    "embedder": "openai",
    "AI_MODEL": "gpt-3.5-turbo-16k-0613",
    "AI_TEMPERATURE": "0.7",
    "AI_TOP_P": "1",
    "MAX_TOKENS": "16000",
    "helper_agent_name": "OpenAI",
    "WEBSEARCH_TIMEOUT": 0,
    "OPENAI_API_KEY": "YOUR_OPENAI_API_KEY_HERE",
    "WAIT_BETWEEN_REQUESTS": 1,
    "WAIT_AFTER_FAILURE": 3,
    "stream": False,
    "WORKING_DIRECTORY": "./WORKSPACE",
    "WORKING_DIRECTORY_RESTRICTED": True,
    "AUTONOMOUS_EXECUTION": False,
}


def add_agent(agent_name, provider_settings=None, commands=None):
    if not agent_name:
        return {"message": "Agent name cannot be empty."}

    agent = AgentModel(name=agent_name)
    session.add(agent)
    session.commit()

    if provider_settings is None or provider_settings == "" or provider_settings == {}:
        provider_settings = DEFAULT_SETTINGS

    settings = {
        "commands": commands,
        "settings": provider_settings,
    }
    agent_setting = AgentSettingModel(
        agent_id=agent.id,
        name="config",
        value=json.dumps(settings),
    )
    session.add(agent_setting)
    session.commit()

    return {"message": f"Agent {agent_name} created."}


def delete_agent(agent_name):
    agent = session.query(AgentModel).filter_by(name=agent_name).first()
    if not agent:
        return {"message": f"Agent {agent_name} not found."}, 404

    # Delete associated chain steps
    chain_steps = session.query(ChainStep).filter_by(agent_id=agent.id).all()
    for chain_step in chain_steps:
        # Delete associated chain step arguments
        session.query(ChainStepArgument).filter_by(chain_step_id=chain_step.id).delete()
        # Delete associated chain step responses
        session.query(ChainStepResponse).filter_by(chain_step_id=chain_step.id).delete()
        session.delete(chain_step)

    # Delete associated agent commands
    agent_commands = session.query(AgentCommand).filter_by(agent_id=agent.id).all()
    for agent_command in agent_commands:
        session.delete(agent_command)

    # Delete associated agent_provider records
    agent_providers = session.query(AgentProvider).filter_by(agent_id=agent.id).all()
    for agent_provider in agent_providers:
        # Delete associated agent_provider_settings
        session.query(AgentProviderSetting).filter_by(
            agent_provider_id=agent_provider.id
        ).delete()
        session.delete(agent_provider)

    # Delete associated agent settings
    session.query(AgentSettingModel).filter_by(agent_id=agent.id).delete()

    # Delete the agent
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


def import_agent_config(agent_name):
    config_path = f"agents/{agent_name}/config.json"

    # Load the config JSON file
    with open(config_path) as f:
        config = json.load(f)

    # Get the agent from the database
    agent = session.query(AgentModel).filter_by(name=agent_name).first()

    if not agent:
        print(f"Agent '{agent_name}' does not exist in the database.")
        return

    # Get the provider ID based on the provider name in the config
    provider_name = config["settings"]["provider"]
    provider = session.query(ProviderModel).filter_by(name=provider_name).first()

    if not provider:
        print(f"Provider '{provider_name}' does not exist in the database.")
        return

    # Update the agent's provider_id
    agent.provider_id = provider.id

    # Import agent commands
    commands = config.get("commands", {})
    for command_name, enabled in commands.items():
        if enabled:
            command = session.query(Command).filter_by(name=command_name).first()
            if command:
                agent_command = AgentCommand(
                    agent_id=agent.id, command_id=command.id, state=True
                )
                session.add(agent_command)

    # Import agent settings
    settings = config.get("settings", {})
    for setting_name, setting_value in settings.items():
        if provider.id:
            provider_setting = (
                session.query(ProviderSetting)
                .filter_by(provider_id=provider.id, name=setting_name)
                .first()
            )
            if provider_setting:
                agent_provider = (
                    session.query(AgentProvider)
                    .filter_by(provider_id=provider.id, agent_id=agent.id)
                    .first()
                )
                if not agent_provider:
                    agent_provider = AgentProvider(
                        provider_id=provider.id, agent_id=agent.id
                    )
                    session.add(agent_provider)
                    session.flush()  # Save the agent_provider object to generate an ID
                if setting_value:
                    agent_provider_setting = AgentProviderSetting(
                        provider_setting_id=provider_setting.id,
                        agent_provider_id=agent_provider.id,
                        value=setting_value,
                    )
                    session.add(agent_provider_setting)
            else:
                if setting_value:
                    agent_setting = AgentSettingModel(
                        agent_id=agent.id, name=setting_name, value=setting_value
                    )
                    session.add(agent_setting)
    session.commit()
    print(f"Agent config imported successfully for agent: {agent_name}")


class Agent:
    def __init__(self, agent_name=None):
        self.agent_name = agent_name if agent_name is not None else "AGiXT"
        self.AGENT_CONFIG = self.get_agent_config()
        self.load_config_keys()
        if "settings" not in self.AGENT_CONFIG:
            self.AGENT_CONFIG["settings"] = {}
        self.PROVIDER_SETTINGS = self.AGENT_CONFIG["settings"]
        for setting in DEFAULT_SETTINGS:
            if setting not in self.PROVIDER_SETTINGS:
                self.PROVIDER_SETTINGS[setting] = DEFAULT_SETTINGS[setting]
        self.AI_PROVIDER = self.AGENT_CONFIG["settings"]["provider"]
        self.PROVIDER = Providers(self.AI_PROVIDER, **self.PROVIDER_SETTINGS)
        self.available_commands = Extensions(
            agent_config=self.AGENT_CONFIG
        ).get_available_commands()

    def load_config_keys(self):
        config_keys = [
            "AI_MODEL",
            "AI_TEMPERATURE",
            "MAX_TOKENS",
            "AUTONOMOUS_EXECUTION",
            "embedder",
        ]
        for key in config_keys:
            if key in self.AGENT_CONFIG:
                setattr(self, key, self.AGENT_CONFIG[key])

    def get_agent_config(self):
        agent = (
            session.query(AgentModel).filter(AgentModel.name == self.agent_name).first()
        )
        if agent:
            agent_setting = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "config",
                )
                .first()
            )
            if agent_setting:
                config = json.loads(agent_setting.value)

                # Retrieve the enabled commands for the agent
                agent_commands = (
                    session.query(AgentCommand)
                    .join(Command)
                    .filter(
                        AgentCommand.agent_id == agent.id,
                        AgentCommand.state == True,  # Only get enabled commands
                    )
                    .all()
                )
                enabled_commands = [ac.command.name for ac in agent_commands]

                # Add the enabled commands to the config
                config["enabled_commands"] = enabled_commands

                return config
        return {}

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

    def update_agent_config(self, new_config, config_key):
        agent = (
            session.query(AgentModel).filter(AgentModel.name == self.agent_name).first()
        )
        if agent:
            if config_key == "commands":
                # Update AgentCommand relation
                for command_name, enabled in new_config.items():
                    command = (
                        session.query(Command).filter_by(name=command_name).first()
                    )
                    if command:
                        agent_command = (
                            session.query(AgentCommand)
                            .filter_by(agent_id=agent.id, command_id=command.id)
                            .first()
                        )
                        if agent_command:
                            agent_command.state = enabled
                        else:
                            agent_command = AgentCommand(
                                agent_id=agent.id, command_id=command.id, state=enabled
                            )
                            session.add(agent_command)
            else:
                provider = (
                    session.query(ProviderModel)
                    .filter_by(name=self.AI_PROVIDER)
                    .first()
                )
                if not provider:
                    print(
                        f"Provider '{self.AI_PROVIDER}' does not exist in the database."
                    )
                    return

                agent_provider = (
                    session.query(AgentProvider)
                    .filter_by(provider_id=provider.id, agent_id=agent.id)
                    .first()
                )
                if not agent_provider:
                    agent_provider = AgentProvider(
                        provider_id=provider.id, agent_id=agent.id
                    )
                    session.add(agent_provider)
                    session.flush()  # Save the agent_provider object to generate an ID

                if config_key in ["provider_settings", "settings"]:
                    config_dict = (
                        agent_provider.provider_settings
                        if config_key == "provider_settings"
                        else agent_provider.settings
                    )

                    for setting_name, setting_value in new_config.items():
                        setting = (
                            session.query(ProviderSetting)
                            .filter_by(provider_id=provider.id, name=setting_name)
                            .first()
                        )
                        if setting:
                            agent_provider_setting = (
                                session.query(AgentProviderSetting)
                                .filter_by(
                                    provider_setting_id=setting.id,
                                    agent_provider_id=agent_provider.id,
                                )
                                .first()
                            )
                            if agent_provider_setting:
                                agent_provider_setting.value = setting_value
                            else:
                                agent_provider_setting = AgentProviderSetting(
                                    provider_setting_id=setting.id,
                                    agent_provider_id=agent_provider.id,
                                    value=setting_value,
                                )
                                session.add(agent_provider_setting)
                else:
                    agent_setting = (
                        session.query(AgentSettingModel)
                        .filter_by(agent_id=agent.id, name=config_key)
                        .first()
                    )
                    if agent_setting:
                        agent_setting.value = new_config
                    else:
                        agent_setting = AgentSettingModel(
                            agent_id=agent.id, name=config_key, value=new_config
                        )
                        session.add(agent_setting)

            session.commit()
            return f"Agent {self.agent_name} configuration updated."
        else:
            return f"Agent {self.agent_name} not found."

    def wipe_agent_memories(self):
        memories_folder = os.path.normpath(
            os.path.join(os.getcwd(), self.agent_name, "memories")
        )
        if not memories_folder.startswith(os.getcwd()):
            raise ValueError("Invalid path, agent name must not contain slashes.")

        if os.path.exists(memories_folder):
            shutil.rmtree(memories_folder)
