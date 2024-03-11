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
    User,
    get_session,
)
from Providers import Providers
from Extensions import Extensions
from Defaults import DEFAULT_SETTINGS, DEFAULT_USER
import logging
import json
import os


def add_agent(agent_name, provider_settings=None, commands=None, user=DEFAULT_USER):
    session = get_session()
    if not agent_name:
        return {"message": "Agent name cannot be empty."}
    # Check if agent already exists
    agent = (
        session.query(AgentModel)
        .filter(AgentModel.name == agent_name, AgentModel.user.has(email=user))
        .first()
    )
    if agent:
        return {"message": f"Agent {agent_name} already exists."}
    agent = (
        session.query(AgentModel)
        .filter(AgentModel.name == agent_name, AgentModel.user.has(email=DEFAULT_USER))
        .first()
    )
    if agent:
        return {"message": f"Agent {agent_name} already exists."}
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id

    if provider_settings is None or provider_settings == "" or provider_settings == {}:
        provider_settings = DEFAULT_SETTINGS
    if commands is None or commands == "" or commands == {}:
        commands = {}
    # Get provider ID based on provider name from provider_settings["provider"]
    provider = (
        session.query(ProviderModel)
        .filter_by(name=provider_settings["provider"])
        .first()
    )
    agent = AgentModel(name=agent_name, user_id=user_id, provider_id=provider.id)
    session.add(agent)
    session.commit()

    for key, value in provider_settings.items():
        agent_setting = AgentSettingModel(
            agent_id=agent.id,
            name=key,
            value=value,
        )
        session.add(agent_setting)
    if commands:
        for command_name, enabled in commands.items():
            command = session.query(Command).filter_by(name=command_name).first()
            if command:
                agent_command = AgentCommand(
                    agent_id=agent.id, command_id=command.id, state=enabled
                )
                session.add(agent_command)
    session.commit()

    return {"message": f"Agent {agent_name} created."}


def delete_agent(agent_name, user=DEFAULT_USER):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id
    agent = (
        session.query(AgentModel)
        .filter(AgentModel.name == agent_name, AgentModel.user_id == user_id)
        .first()
    )
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


def rename_agent(agent_name, new_name, user=DEFAULT_USER):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id
    agent = (
        session.query(AgentModel)
        .filter(AgentModel.name == agent_name, AgentModel.user_id == user_id)
        .first()
    )
    if not agent:
        return {"message": f"Agent {agent_name} not found."}, 404

    agent.name = new_name
    session.commit()

    return {"message": f"Agent {agent_name} renamed to {new_name}."}, 200


def get_agents(user=DEFAULT_USER):
    session = get_session()
    agents = session.query(AgentModel).filter(AgentModel.user.has(email=user)).all()
    output = []

    for agent in agents:
        output.append({"name": agent.name, "status": False})

    # Get global agents that belong to DEFAULT_USER
    global_agents = (
        session.query(AgentModel).filter(AgentModel.user.has(email=DEFAULT_USER)).all()
    )
    for agent in global_agents:
        output.append({"name": agent.name, "status": False})
    return output


class Agent:
    def __init__(self, agent_name=None, user=DEFAULT_USER, ApiClient=None):
        self.agent_name = agent_name if agent_name is not None else "AGiXT"
        self.session = get_session()
        self.user = user
        user_data = self.session.query(User).filter(User.email == self.user).first()
        self.user_id = user_data.id
        self.AGENT_CONFIG = self.get_agent_config()
        self.load_config_keys()
        if "settings" not in self.AGENT_CONFIG:
            self.AGENT_CONFIG["settings"] = {}
        self.PROVIDER_SETTINGS = self.AGENT_CONFIG["settings"]
        for setting in DEFAULT_SETTINGS:
            if setting not in self.PROVIDER_SETTINGS:
                self.PROVIDER_SETTINGS[setting] = DEFAULT_SETTINGS[setting]
        self.AI_PROVIDER = self.AGENT_CONFIG["settings"]["provider"]
        self.PROVIDER = Providers(
            name=self.AI_PROVIDER, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
        )
        self.available_commands = Extensions(
            agent_name=self.agent_name,
            agent_config=self.AGENT_CONFIG,
            ApiClient=ApiClient,
            user=self.user,
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
            self.session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            # Check if it is a global agent
            global_user = (
                self.session.query(User).filter(User.email == DEFAULT_USER).first()
            )
            agent = (
                self.session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user_id == global_user.id,
                )
                .first()
            )

        config = {"settings": {}, "commands": {}}
        if agent:
            all_commands = self.session.query(Command).all()
            agent_settings = (
                self.session.query(AgentSettingModel).filter_by(agent_id=agent.id).all()
            )
            agent_commands = (
                self.session.query(AgentCommand)
                .join(Command)
                .filter(
                    AgentCommand.agent_id == agent.id,
                    AgentCommand.state == True,
                )
                .all()
            )
            for command in all_commands:
                config["commands"].update(
                    {
                        command.name: command.name
                        in [ac.command.name for ac in agent_commands]
                    }
                )
            for setting in agent_settings:
                config["settings"][setting.name] = setting.value
            return config
        return {"settings": DEFAULT_SETTINGS, "commands": {}}

    async def inference(self, prompt, tokens):
        if not prompt:
            return ""
        answer = await self.PROVIDER.inference(prompt=prompt, tokens=tokens)
        return answer.replace("\_", "_")

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

    def update_agent_config(self, new_config, config_key):
        agent = (
            self.session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            # Check if it is a global agent
            global_user = (
                self.session.query(User).filter(User.email == DEFAULT_USER).first()
            )
            agent = (
                self.session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user_id == global_user.id,
                )
                .first()
            )
            if not agent:
                print(f"Agent '{self.agent_name}' not found in the database.")
                return

        if config_key == "commands":
            self._update_agent_commands(agent, new_config)
        else:
            self._update_agent_settings(agent, config_key, new_config)

        self.session.commit()
        return f"Agent {self.agent_name} configuration updated."

    def _update_agent_commands(self, agent, commands):
        for command_name, enabled in commands.items():
            command = self.session.query(Command).filter_by(name=command_name).first()
            if command:
                agent_command = (
                    self.session.query(AgentCommand)
                    .filter_by(agent_id=agent.id, command_id=command.id)
                    .first()
                )
                if agent_command:
                    agent_command.state = enabled
                else:
                    agent_command = AgentCommand(
                        agent_id=agent.id, command_id=command.id, state=enabled
                    )
                    self.session.add(agent_command)

    def _update_agent_settings(self, agent, config_key, new_config):
        provider = (
            self.session.query(ProviderModel).filter_by(name=self.AI_PROVIDER).first()
        )
        if not provider:
            logging.error(
                f"Provider '{self.AI_PROVIDER}' does not exist in the database."
            )
            return

        agent_provider = (
            self.session.query(AgentProvider)
            .filter_by(provider_id=provider.id, agent_id=agent.id)
            .first()
        )
        if not agent_provider:
            agent_provider = AgentProvider(provider_id=provider.id, agent_id=agent.id)
            self.session.add(agent_provider)
            self.session.flush()  # Save the agent_provider object to generate an ID

        config_key_handlers = {
            "provider_settings": self._update_provider_settings,
            "settings": self._update_provider_settings,
        }

        handler = config_key_handlers.get(config_key)
        if handler:
            handler(agent_provider, new_config)
        else:
            self._update_agent_setting(agent, config_key, new_config)

    def _update_provider_settings(self, agent_provider, new_config):
        provider = (
            self.session.query(ProviderModel)
            .filter_by(id=agent_provider.provider_id)
            .first()
        )
        for setting_name, setting_value in new_config.items():
            setting = (
                self.session.query(ProviderSetting)
                .filter_by(provider_id=provider.id, name=setting_name)
                .first()
            )
            if not setting:
                logging.error(
                    f"Provider setting '{setting_name}' does not exist for provider '{provider.name}'."
                )
                continue

            agent_provider_setting = (
                self.session.query(AgentProviderSetting)
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
                self.session.add(agent_provider_setting)

    def _update_agent_setting(self, agent, config_key, new_config):
        agent_setting = (
            self.session.query(AgentSettingModel)
            .filter_by(agent_id=agent.id, name=config_key)
            .first()
        )
        if agent_setting:
            agent_setting.value = new_config
        else:
            agent_setting = AgentSettingModel(
                agent_id=agent.id, name=config_key, value=new_config
            )
            self.session.add(agent_setting)
