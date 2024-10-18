from DB import (
    Agent as AgentModel,
    AgentSetting as AgentSettingModel,
    AgentBrowsedLink,
    Command,
    AgentCommand,
    AgentProvider,
    AgentProviderSetting,
    ChainStep,
    ChainStepArgument,
    ChainStepResponse,
    Provider as ProviderModel,
    User,
    UserPreferences,
    get_session,
)
from Providers import Providers
from Extensions import Extensions
from Globals import getenv, DEFAULT_SETTINGS, DEFAULT_USER
from MagicalAuth import get_user_id, is_agixt_admin
from agixtsdk import AGiXTSDK
from fastapi import HTTPException
from datetime import datetime, timezone, timedelta
import logging
import json
import numpy as np
import os

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


def add_agent(agent_name, provider_settings=None, commands=None, user=DEFAULT_USER):
    if not agent_name:
        return {"message": "Agent name cannot be empty."}
    session = get_session()
    # Check if agent already exists
    agent = (
        session.query(AgentModel)
        .filter(AgentModel.name == agent_name, AgentModel.user.has(email=user))
        .first()
    )
    if agent:
        session.close()
        return {"message": f"Agent {agent_name} already exists."}
    agent = (
        session.query(AgentModel)
        .filter(AgentModel.name == agent_name, AgentModel.user.has(email=DEFAULT_USER))
        .first()
    )
    if agent:
        session.close()
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
    session.close()
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
        session.close()
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
    session.close()
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
        session.close()
        return {"message": f"Agent {agent_name} not found."}, 404
    agent.name = new_name
    session.commit()
    session.close()
    return {"message": f"Agent {agent_name} renamed to {new_name}."}, 200


def get_agents(user=DEFAULT_USER):
    session = get_session()
    agents = session.query(AgentModel).filter(AgentModel.user.has(email=user)).all()
    output = []
    for agent in agents:
        output.append({"name": agent.name, "id": agent.id, "status": False})
    # Get global agents that belong to DEFAULT_USER
    global_agents = (
        session.query(AgentModel).filter(AgentModel.user.has(email=DEFAULT_USER)).all()
    )
    for agent in global_agents:
        # Check if the agent is in the output already
        if agent.name in [a["name"] for a in output]:
            continue
        output.append({"name": agent.name, "id": agent.id, "status": False})
    session.close()
    return output


class Agent:
    def __init__(self, agent_name=None, user=DEFAULT_USER, ApiClient: AGiXTSDK = None):
        self.agent_name = agent_name if agent_name is not None else "AGiXT"
        user = user if user is not None else DEFAULT_USER
        self.user = user.lower()
        self.user_id = get_user_id(user=self.user)
        self.AGENT_CONFIG = self.get_agent_config()
        self.load_config_keys()
        if "settings" not in self.AGENT_CONFIG:
            self.AGENT_CONFIG["settings"] = {}
        self.PROVIDER_SETTINGS = (
            self.AGENT_CONFIG["settings"] if "settings" in self.AGENT_CONFIG else {}
        )
        for setting in DEFAULT_SETTINGS:
            if setting not in self.PROVIDER_SETTINGS:
                self.PROVIDER_SETTINGS[setting] = DEFAULT_SETTINGS[setting]
        self.AI_PROVIDER = self.AGENT_CONFIG["settings"]["provider"]
        self.PROVIDER = Providers(
            name=self.AI_PROVIDER, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
        )
        vision_provider = (
            self.AGENT_CONFIG["settings"]["vision_provider"]
            if "vision_provider" in self.AGENT_CONFIG["settings"]
            else "None"
        )
        if (
            vision_provider != "None"
            and vision_provider != None
            and vision_provider != ""
        ):
            try:
                self.VISION_PROVIDER = Providers(
                    name=vision_provider, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
                )
            except Exception as e:
                logging.error(f"Error loading vision provider: {str(e)}")
                self.VISION_PROVIDER = None
        else:
            self.VISION_PROVIDER = None
        tts_provider = (
            self.AGENT_CONFIG["settings"]["tts_provider"]
            if "tts_provider" in self.AGENT_CONFIG["settings"]
            else "None"
        )
        if tts_provider != "None" and tts_provider != None and tts_provider != "":
            self.TTS_PROVIDER = Providers(
                name=tts_provider, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
            )
        else:
            self.TTS_PROVIDER = None
        transcription_provider = (
            self.AGENT_CONFIG["settings"]["transcription_provider"]
            if "transcription_provider" in self.AGENT_CONFIG["settings"]
            else "default"
        )
        self.TRANSCRIPTION_PROVIDER = Providers(
            name=transcription_provider, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
        )
        translation_provider = (
            self.AGENT_CONFIG["settings"]["translation_provider"]
            if "translation_provider" in self.AGENT_CONFIG["settings"]
            else "default"
        )
        self.TRANSLATION_PROVIDER = Providers(
            name=translation_provider, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
        )
        image_provider = (
            self.AGENT_CONFIG["settings"]["image_provider"]
            if "image_provider" in self.AGENT_CONFIG["settings"]
            else "default"
        )
        self.IMAGE_PROVIDER = Providers(
            name=image_provider, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
        )
        embeddings_provider = (
            self.AGENT_CONFIG["settings"]["embeddings_provider"]
            if "embeddings_provider" in self.AGENT_CONFIG["settings"]
            else "default"
        )
        self.EMBEDDINGS_PROVIDER = Providers(
            name=embeddings_provider, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
        )
        self.embedder = (
            self.EMBEDDINGS_PROVIDER.embedder
            if self.EMBEDDINGS_PROVIDER
            else Providers(
                name="default", ApiClient=ApiClient, **self.PROVIDER_SETTINGS
            ).embedder
        )
        try:
            self.max_input_tokens = int(self.AGENT_CONFIG["settings"]["MAX_TOKENS"])
        except Exception as e:
            self.max_input_tokens = 32000
        if hasattr(self.EMBEDDINGS_PROVIDER, "chunk_size"):
            self.chunk_size = self.EMBEDDINGS_PROVIDER.chunk_size
        else:
            self.chunk_size = 256
        self.extensions = Extensions(
            agent_name=self.agent_name,
            agent_config=self.AGENT_CONFIG,
            ApiClient=ApiClient,
            user=self.user,
        )
        self.available_commands = self.extensions.get_available_commands()
        self.agent_id = str(self.get_agent_id())
        self.working_directory = os.path.join(os.getcwd(), "WORKSPACE", self.agent_id)
        os.makedirs(self.working_directory, exist_ok=True)

    def load_config_keys(self):
        config_keys = [
            "AI_MODEL",
            "AI_TEMPERATURE",
            "MAX_TOKENS",
            "embedder",
        ]
        for key in config_keys:
            if key in self.AGENT_CONFIG:
                setattr(self, key, self.AGENT_CONFIG[key])

    def get_registration_requirement_settings(self):
        with open("registration_requirements.json", "r") as read_file:
            data = json.load(read_file)
        agent_settings = {}
        user_preferences_keys = []
        for key in data:
            user_preferences_keys.append(key)
        session = get_session()
        user_preferences = (
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == self.user_id)
            .all()
        )
        for user_preference in user_preferences:
            if user_preference.pref_key in user_preferences_keys:
                agent_settings[user_preference.pref_key] = str(
                    user_preference.pref_value
                )
        session.close()
        return agent_settings

    def get_agent_config(self):
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            # Check if it is a global agent
            global_user = session.query(User).filter(User.email == DEFAULT_USER).first()
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user_id == global_user.id,
                )
                .first()
            )
        config = {"settings": {}, "commands": {}}
        if agent:
            all_commands = session.query(Command).all()
            agent_settings = (
                session.query(AgentSettingModel).filter_by(agent_id=agent.id).all()
            )
            agent_commands = (
                session.query(AgentCommand)
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
            session.commit()
            session.close()
            user_settings = self.get_registration_requirement_settings()
            for key, value in user_settings.items():
                config["settings"][key] = value
            return config
        config = {"settings": DEFAULT_SETTINGS, "commands": {}}
        user_settings = self.get_registration_requirement_settings()
        for key, value in user_settings.items():
            config["settings"][key] = value
        session.close()
        return config

    async def inference(self, prompt: str, tokens: int = 0, images: list = []):
        if not prompt:
            return ""
        answer = await self.PROVIDER.inference(
            prompt=prompt, tokens=tokens, images=images
        )
        answer = str(answer).replace("\_", "_")
        if answer.endswith("\n\n"):
            answer = answer[:-2]
        return answer

    async def vision_inference(self, prompt: str, tokens: int = 0, images: list = []):
        if not prompt:
            return ""
        if not self.VISION_PROVIDER:
            return ""
        answer = await self.VISION_PROVIDER.inference(
            prompt=prompt, tokens=tokens, images=images
        )
        answer = str(answer).replace("\_", "_")
        if answer.endswith("\n\n"):
            answer = answer[:-2]
        return answer

    def embeddings(self, input) -> np.ndarray:
        return self.embedder(input=input)

    async def transcribe_audio(self, audio_path: str):
        return await self.TRANSCRIPTION_PROVIDER.transcribe_audio(audio_path=audio_path)

    async def translate_audio(self, audio_path: str):
        return await self.TRANSLATION_PROVIDER.translate_audio(audio_path=audio_path)

    async def generate_image(self, prompt: str):
        return await self.IMAGE_PROVIDER.generate_image(prompt=prompt)

    async def text_to_speech(self, text: str):
        if self.TTS_PROVIDER is not None:
            return await self.TTS_PROVIDER.text_to_speech(text=text)

    def get_agent_extensions(self):
        extensions = self.extensions.get_extensions()
        new_extensions = []
        for extension in extensions:
            required_keys = extension["settings"]
            new_extension = extension.copy()
            for key in required_keys:
                if key not in self.AGENT_CONFIG["settings"]:
                    if "missing_keys" not in new_extension:
                        new_extension["missing_keys"] = []
                    new_extension["missing_keys"].append(key)
                    new_extension["commands"] = []
                else:
                    if (
                        self.AGENT_CONFIG["settings"][key] == ""
                        or self.AGENT_CONFIG["settings"][key] == None
                    ):
                        new_extension["commands"] = []
            new_extensions.append(new_extension)
        for extension in new_extensions:
            for command in extension["commands"]:
                if command["friendly_name"] in self.AGENT_CONFIG["commands"]:
                    command["enabled"] = self.AGENT_CONFIG["commands"][
                        command["friendly_name"]
                    ]
                else:
                    command["enabled"] = False
        return new_extensions

    def update_agent_config(self, new_config, config_key):
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            if self.user == DEFAULT_USER:
                return f"Agent {self.agent_name} not found."
            # Check if it is a global agent.
            global_user = session.query(User).filter(User.email == DEFAULT_USER).first()
            global_agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user_id == global_user.id,
                )
                .first()
            )
            # if it is a global agent, copy it to the user's agents.
            if global_agent:
                agent = AgentModel(
                    name=self.agent_name,
                    user_id=self.user_id,
                    provider_id=global_agent.provider_id,
                )
                session.add(agent)
                session.commit()
                agent_settings = (
                    session.query(AgentSettingModel)
                    .filter_by(agent_id=global_agent.id)
                    .all()
                )
                for setting in agent_settings:
                    agent_setting = AgentSettingModel(
                        agent_id=agent.id,
                        name=setting.name,
                        value=setting.value,
                    )
                    session.add(agent_setting)
                session.commit()
                agent_commands = (
                    session.query(AgentCommand)
                    .filter_by(agent_id=global_agent.id)
                    .all()
                )
                for agent_command in agent_commands:
                    agent_command = AgentCommand(
                        agent_id=agent.id,
                        command_id=agent_command.command_id,
                        state=agent_command.state,
                    )
                    session.add(agent_command)
                session.commit()
                session.close()
                return f"Agent {self.agent_name} configuration updated successfully."
        if config_key == "commands":
            for command_name, enabled in new_config.items():
                command = session.query(Command).filter_by(name=command_name).first()
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
            for setting_name, setting_value in new_config.items():
                logging.info(f"Setting {setting_name} to {setting_value}.")
                agent_setting = (
                    session.query(AgentSettingModel)
                    .filter_by(agent_id=agent.id, name=setting_name)
                    .first()
                )
                if agent_setting:
                    agent_setting.value = str(setting_value)
                else:
                    agent_setting = AgentSettingModel(
                        agent_id=agent.id, name=setting_name, value=str(setting_value)
                    )
                    session.add(agent_setting)
        try:
            session.commit()
            session.close()
            logging.info(f"Agent {self.agent_name} configuration updated successfully.")
        except Exception as e:
            session.rollback()
            session.close()
            logging.error(f"Error updating agent configuration: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error updating agent configuration: {str(e)}"
            )
        return f"Agent {self.agent_name} configuration updated."

    def get_browsed_links(self, conversation_id=None):
        """
        Get the list of URLs that have been browsed by the agent.

        Returns:
            list: The list of URLs that have been browsed by the agent.
        """
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            session.close()
            return []
        browsed_links = (
            session.query(AgentBrowsedLink)
            .filter_by(agent_id=agent.id, conversation_id=conversation_id)
            .order_by(AgentBrowsedLink.id.desc())
            .all()
        )
        session.close()
        if not browsed_links:
            return []
        return browsed_links

    def browsed_recently(self, url, conversation_id=None) -> bool:
        """
        Check if the given URL has been browsed by the agent within the last 24 hours.

        Args:
            url (str): The URL to check.

        Returns:
            bool: True if the URL has been browsed within the last 24 hours, False otherwise.
        """
        browsed_links = self.get_browsed_links(conversation_id=conversation_id)
        if not browsed_links:
            return False
        for link in browsed_links:
            if link["url"] == url:
                if link["timestamp"] >= datetime.now(timezone.utc) - timedelta(days=1):
                    return True
        return False

    def add_browsed_link(self, url, conversation_id=None):
        """
        Add a URL to the list of browsed links for the agent.

        Args:
            url (str): The URL to add.

        Returns:
            str: The response message.
        """
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            return f"Agent {self.agent_name} not found."
        browsed_link = AgentBrowsedLink(
            agent_id=agent.id, url=url, conversation_id=conversation_id
        )
        session.add(browsed_link)
        session.commit()
        session.close()
        return f"Link {url} added to browsed links."

    def delete_browsed_link(self, url, conversation_id=None):
        """
        Delete a URL from the list of browsed links for the agent.

        Args:
            url (str): The URL to delete.

        Returns:
            str: The response message.
        """
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name,
                AgentModel.user_id == self.user_id,
            )
            .first()
        )
        if not agent:
            return f"Agent {self.agent_name} not found."
        browsed_link = (
            session.query(AgentBrowsedLink)
            .filter_by(agent_id=agent.id, url=url, conversation_id=conversation_id)
            .first()
        )
        if not browsed_link:
            return f"Link {url} not found."
        session.delete(browsed_link)
        session.commit()
        session.close()
        return f"Link {url} deleted from browsed links."

    def get_agent_id(self):
        session = get_session()
        agent = (
            session.query(AgentModel)
            .filter(
                AgentModel.name == self.agent_name, AgentModel.user_id == self.user_id
            )
            .first()
        )
        if not agent:
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user.has(email=DEFAULT_USER),
                )
                .first()
            )
            session.close()
            if not agent:
                return None
        session.close()
        return agent.id
