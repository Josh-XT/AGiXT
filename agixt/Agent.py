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
    Chain as ChainDB,
    Provider as ProviderModel,
    User,
    Extension,
    UserPreferences,
    get_session,
    UserOAuth,
    OAuthProvider,
    TaskItem,
    WebhookIncoming,
    WebhookOutgoing,
)
from Providers import Providers, get_provider_services
from Extensions import Extensions
from Globals import getenv, get_tokens, DEFAULT_SETTINGS, DEFAULT_USER
from MagicalAuth import MagicalAuth, get_user_id
from agixtsdk import AGiXTSDK
from fastapi import HTTPException
from datetime import datetime, timezone, timedelta
import logging
import json
import numpy as np
import base64
import jwt
import os
import re
from solders.keypair import Keypair
from typing import Tuple
import binascii
from WebhookManager import WebhookEventEmitter
from sqlalchemy.exc import IntegrityError

# Initialize webhook event emitter
webhook_emitter = WebhookEventEmitter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


# Define the standalone wallet creation function
def create_solana_wallet() -> Tuple[str, str, str]:
    """
    Creates a new Solana wallet keypair and generates a secure passphrase.

    Returns:
        Tuple[str, str, str]: A tuple containing the private key (hex string),
                              a generated passphrase (hex string), and the public key (string).
    """
    new_keypair = Keypair()
    private_key_hex = new_keypair.secret().hex()
    public_key_str = str(new_keypair.pubkey())
    # Generate a secure random passphrase (e.g., 16 bytes hex encoded)
    passphrase_hex = binascii.hexlify(os.urandom(16)).decode("utf-8")
    return private_key_hex, passphrase_hex, public_key_str


def impersonate_user(user_id: str):
    AGIXT_API_KEY = getenv("AGIXT_API_KEY")
    # Get users email
    session = get_session()
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        session.close()
        raise HTTPException(status_code=404, detail="User not found.")
    user_id = str(user.id)
    email = user.email
    session.close()
    token = jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "exp": datetime.now() + timedelta(days=1),
        },
        AGIXT_API_KEY,
        algorithm="HS256",
    )
    return token


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
        i = 1
        while not agent:
            agent_name = f"{agent_name} {i}"
            agent = (
                session.query(AgentModel)
                .filter(AgentModel.name == agent_name, AgentModel.user.has(email=user))
                .first()
            )
            i += 1
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id

    if provider_settings is None or provider_settings == "" or provider_settings == {}:
        provider_settings = DEFAULT_SETTINGS
    if "company_id" not in provider_settings:
        token = impersonate_user(user_id=str(user_id))
        auth = MagicalAuth(token=token)
        provider_settings["company_id"] = (
            str(auth.company_id) if auth.company_id is not None else None
        )
    # Iterate over DEFAULT_SETTINGS and add any missing keys
    for key in DEFAULT_SETTINGS:
        if key not in provider_settings:
            provider_settings[key] = DEFAULT_SETTINGS[key]
    if commands is None or commands == "" or commands == {}:
        commands = {}
    # Get provider ID based on provider name from provider_settings["provider"]
    if "provider" not in provider_settings:
        logging.info(f"Provider settings: {provider_settings}")
        provider_settings["provider"] = "rotation"
    provider = (
        session.query(ProviderModel)
        .filter_by(name=provider_settings["provider"])
        .first()
    )
    agent = AgentModel(name=agent_name, user_id=user_id, provider_id=provider.id)
    session.add(agent)
    session.commit()

    # Emit webhook event for agent creation (async without await since this is sync function)
    import asyncio
    from DB import UserCompany

    # Try to get the user's company_id
    company_id = None
    try:
        user_company = (
            session.query(UserCompany)
            .filter(UserCompany.user_id == str(user_id))
            .first()
        )
        company_id = (
            str(user_company.company_id)
            if user_company and user_company.company_id is not None
            else None
        )
    except:
        pass

    try:
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="agent.created",
                data={
                    "agent_id": str(agent.id),
                    "agent_name": agent_name,
                    "user_id": str(user_id),
                    "provider": provider_settings.get("provider", "rotation"),
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=str(user_id),
                company_id=company_id,
            )
        )
    except:
        # If we're not in an async context, just log it
        logging.debug(f"Could not emit webhook event for agent creation: {agent_name}")

    for key, value in provider_settings.items():
        agent_setting = AgentSettingModel(
            agent_id=agent.id,
            name=key,
            value=value,
        )
        session.add(agent_setting)

    # Auto-enable commands from essential_abilities and notes extensions
    essential_extensions = ["Essential Abilities", "Notes"]
    for extension_name in essential_extensions:
        extension = (
            session.query(Extension).filter(Extension.name == extension_name).first()
        )
        if extension:
            # Get all commands from this extension
            extension_commands = (
                session.query(Command)
                .filter(Command.extension_id == extension.id)
                .all()
            )
            # Enable all commands from these extensions
            for command in extension_commands:
                # Check if agent command already exists (from commands parameter)
                existing_agent_command = (
                    session.query(AgentCommand)
                    .filter(
                        AgentCommand.agent_id == agent.id,
                        AgentCommand.command_id == command.id,
                    )
                    .first()
                )
                if not existing_agent_command:
                    agent_command = AgentCommand(
                        agent_id=agent.id, command_id=command.id, state=True
                    )
                    session.add(agent_command)

    # Handle any additional commands passed in the commands parameter
    if commands:
        for command_name, enabled in commands.items():
            command = session.query(Command).filter_by(name=command_name).first()
            if command:
                # Check if agent command already exists (from auto-enabled extensions)
                existing_agent_command = (
                    session.query(AgentCommand)
                    .filter(
                        AgentCommand.agent_id == agent.id,
                        AgentCommand.command_id == command.id,
                    )
                    .first()
                )
                if existing_agent_command:
                    # Update existing command state
                    existing_agent_command.state = enabled
                else:
                    # Create new agent command
                    agent_command = AgentCommand(
                        agent_id=agent.id, command_id=command.id, state=enabled
                    )
                    session.add(agent_command)

    # Set onboarded2agixt to true for new agents since we auto-enabled essential commands
    onboarded_setting = AgentSettingModel(
        agent_id=agent.id,
        name="onboarded2agixt",
        value="true",
    )
    session.add(onboarded_setting)

    session.commit()
    session.close()
    return {"message": f"Agent {agent_name} created."}


def delete_agent(agent_name=None, agent_id=None, user=DEFAULT_USER):
    """Delete an agent and all dependent data.

    Supports targeting by either agent name or agent ID to avoid ambiguity.
    Returns a tuple of ({"message": str}, http_status_code).
    """

    if agent_name is None and agent_id is None:
        return {"message": "agent_name or agent_id is required."}, 400

    session = get_session()
    deleted = False
    agent_name_value = agent_name
    agent_id_value = agent_id
    user_id = None

    try:
        user_data = session.query(User).filter(User.email == user).first()
        if not user_data:
            logging.warning(f"User {user} not found while deleting agent.")
            return {"message": f"User {user} not found."}, 404

        user_id = user_data.id

        agent_query = session.query(AgentModel).filter(AgentModel.user_id == user_id)
        if agent_id is not None:
            agent = agent_query.filter(AgentModel.id == agent_id).first()
        else:
            agent = agent_query.filter(AgentModel.name == agent_name).first()

        if not agent:
            return {
                "message": (
                    f"Agent {agent_name or agent_id} not found for user {user}."
                )
            }, 404

        agent_name_value = agent.name
        agent_id_value = str(agent.id)

        total_agents = agent_query.count()
        if total_agents <= 1:
            return {"message": "You cannot delete your last agent."}, 401

        # Delete associated browsed links
        session.query(AgentBrowsedLink).filter_by(agent_id=agent.id).delete(
            synchronize_session=False
        )

        # Delete associated chain steps, arguments, and responses
        chain_steps = session.query(ChainStep).filter_by(agent_id=agent.id).all()
        for chain_step in chain_steps:
            session.query(ChainStepArgument).filter_by(
                chain_step_id=chain_step.id
            ).delete(synchronize_session=False)
            session.query(ChainStepResponse).filter_by(
                chain_step_id=chain_step.id
            ).delete(synchronize_session=False)
            session.delete(chain_step)

        # Delete associated agent commands
        agent_commands = session.query(AgentCommand).filter_by(agent_id=agent.id).all()
        for agent_command in agent_commands:
            session.delete(agent_command)

        # Delete associated agent provider records and settings
        agent_providers = (
            session.query(AgentProvider).filter_by(agent_id=agent.id).all()
        )
        for agent_provider in agent_providers:
            session.query(AgentProviderSetting).filter_by(
                agent_provider_id=agent_provider.id
            ).delete(synchronize_session=False)
            session.delete(agent_provider)

        # Delete associated agent settings
        session.query(AgentSettingModel).filter_by(agent_id=agent.id).delete(
            synchronize_session=False
        )

        # Null out optional relationships referencing the agent
        session.query(TaskItem).filter(TaskItem.agent_id == agent.id).update(
            {TaskItem.agent_id: None}, synchronize_session=False
        )
        session.query(WebhookOutgoing).filter(
            WebhookOutgoing.agent_id == agent.id
        ).update({WebhookOutgoing.agent_id: None}, synchronize_session=False)

        # Delete dependent records that require the agent
        session.query(WebhookIncoming).filter_by(agent_id=agent.id).delete(
            synchronize_session=False
        )

        # Finally delete the agent
        session.delete(agent)
        session.commit()
        deleted = True
    except IntegrityError as e:
        session.rollback()
        logging.error(
            f"Integrity error deleting agent {agent_name or agent_id}: {str(e)}"
        )
        return {
            "message": "Failed to delete agent due to related records.",
            "details": str(e),
        }, 500
    finally:
        session.close()

    if not deleted:
        return {"message": "Agent deletion was not completed."}, 500

    # Emit webhook event for agent deletion
    import asyncio

    try:
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="agent.deleted",
                data={
                    "agent_id": agent_id_value,
                    "agent_name": agent_name_value,
                    "user_id": str(user_id) if user_id else None,
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=str(user_id) if user_id else None,
            )
        )
    except Exception:
        logging.debug(
            f"Could not emit webhook event for agent deletion: {agent_name_value}"
        )

    return {"message": f"Agent {agent_name_value} deleted."}, 200


def rename_agent(agent_name, new_name, user=DEFAULT_USER, company_id=None):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id
    if not company_id:
        agent = (
            session.query(AgentModel)
            .filter(AgentModel.name == agent_name, AgentModel.user_id == user_id)
            .first()
        )
    else:
        agent = (
            session.query(AgentModel)
            .filter(AgentModel.name == agent_name, AgentModel.user_id == user_id)
            .filter(AgentModel.company_id == company_id)
            .first()
        )
    if not agent:
        session.close()
        return {"message": f"Agent {agent_name} not found."}, 404
    old_name = agent.name
    agent.name = new_name
    session.commit()

    # Emit webhook event for agent rename
    import asyncio

    try:
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="agent.updated",
                data={
                    "agent_id": str(agent.id),
                    "old_name": old_name,
                    "new_name": new_name,
                    "user_id": str(user_id),
                    "update_type": "rename",
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=str(user_id),
            )
        )
    except:
        logging.debug(
            f"Could not emit webhook event for agent rename: {old_name} -> {new_name}"
        )

    session.close()
    return {"message": f"Agent {agent_name} renamed to {new_name}."}, 200


def get_agents(user=DEFAULT_USER, company=None):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    try:
        default_agent_id = str(
            session.query(UserPreferences)
            .filter(UserPreferences.user_id == user_data.id)
            .filter(UserPreferences.pref_key == "agent_id")
            .first()
            .pref_value
        )
    except:
        default_agent_id = ""
    agents = session.query(AgentModel).filter(AgentModel.user_id == user_data.id).all()
    if default_agent_id == "":
        # Add a user preference of the first agent's ID in the agent list
        if agents:
            user_preference = UserPreferences(
                user_id=user_data.id, pref_key="agent_id", pref_value=agents[0].id
            )
            session.add(user_preference)
            session.commit()
            default_agent_id = str(agents[0].id)
        else:
            session.close()
            return []
    output = []
    for agent in agents:
        # Check if the agent is in the output already
        if agent.name in [a["name"] for a in output]:
            continue
        # Get the agent settings `company_id` and `onboarded2agixt` if defined
        company_id = None
        onboarded2agixt = None
        agent_settings = (
            session.query(AgentSettingModel)
            .filter(AgentSettingModel.agent_id == agent.id)
            .all()
        )
        for setting in agent_settings:
            if setting.name == "company_id":
                company_id = setting.value
            elif setting.name == "onboarded2agixt":
                onboarded2agixt = setting.value
        if company_id and company:
            if company_id != company:
                continue
        if not company_id:
            auth = MagicalAuth(token=impersonate_user(user_id=str(user_data.id)))
            company_id = str(auth.company_id) if auth.company_id is not None else None
            # update agent settings
            agent_setting = AgentSettingModel(
                agent_id=agent.id,
                name="company_id",
                value=company_id,
            )
            session.add(agent_setting)
            session.commit()

        # Check if agent needs onboarding (enable essential_abilities and notes commands)
        if not onboarded2agixt or onboarded2agixt.lower() != "true":
            # Auto-enable commands from essential_abilities and notes extensions
            essential_extensions = ["Essential Abilities", "Notes"]
            for extension_name in essential_extensions:
                extension = (
                    session.query(Extension)
                    .filter(Extension.name == extension_name)
                    .first()
                )
                if extension:
                    # Get all commands from this extension
                    extension_commands = (
                        session.query(Command)
                        .filter(Command.extension_id == extension.id)
                        .all()
                    )
                    # Enable all commands from these extensions
                    for command in extension_commands:
                        # Check if agent command already exists
                        existing_agent_command = (
                            session.query(AgentCommand)
                            .filter(
                                AgentCommand.agent_id == agent.id,
                                AgentCommand.command_id == command.id,
                            )
                            .first()
                        )
                        if not existing_agent_command:
                            agent_command = AgentCommand(
                                agent_id=agent.id, command_id=command.id, state=True
                            )
                            session.add(agent_command)
                        elif not existing_agent_command.state:
                            # Enable the command if it was disabled
                            existing_agent_command.state = True

            # Create the onboarded2agixt setting
            agent_setting = AgentSettingModel(
                agent_id=agent.id,
                name="onboarded2agixt",
                value="true",
            )
            session.add(agent_setting)
            session.commit()
        output.append(
            {
                "name": agent.name,
                "id": agent.id,
                "status": False,
                "company_id": company_id,
                "default": str(agent.id) == str(default_agent_id),
            }
        )
    session.close()
    return output


class Agent:
    def __init__(
        self,
        agent_name=None,
        agent_id=None,
        user=DEFAULT_USER,
        ApiClient: AGiXTSDK = None,
    ):
        # Validate that either agent_name or agent_id is provided, but not both
        if agent_name is not None and agent_id is not None:
            raise ValueError(
                "Cannot specify both agent_name and agent_id. Please provide only one."
            )
        if agent_name is None and agent_id is None:
            agent_name = "AGiXT"  # Default fallback

        self.agent_name = agent_name
        self.agent_id = agent_id
        user = user if user is not None else DEFAULT_USER
        self.user = user.lower()
        self.user_id = get_user_id(user=self.user)
        token = impersonate_user(user_id=str(self.user_id))
        self.auth = MagicalAuth(token=token)
        self.company_id = None

        # If agent_id was provided, get the agent_name; if agent_name was provided, get the agent_id
        if self.agent_id is not None:
            self.agent_name = self.get_agent_name_by_id()
        else:
            agent_id_result = self.get_agent_id()
            self.agent_id = (
                str(agent_id_result) if agent_id_result is not None else None
            )

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
        for key in ["name", "ApiClient", "agent_name", "user", "user_id", "api_key"]:
            if key in self.PROVIDER_SETTINGS:
                del self.PROVIDER_SETTINGS[key]
        self.PROVIDER = Providers(
            name=self.AI_PROVIDER,
            ApiClient=ApiClient,
            agent_name=self.agent_name,
            user=self.user,
            api_key=token,
            **self.PROVIDER_SETTINGS,
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
                    name=vision_provider,
                    ApiClient=ApiClient,
                    agent_name=self.agent_name,
                    user=self.user,
                    api_key=token,
                    **self.PROVIDER_SETTINGS,
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
        image_services = get_provider_services(image_provider)
        if "image" in image_services:
            try:
                self.IMAGE_PROVIDER = Providers(
                    name=image_provider, ApiClient=ApiClient, **self.PROVIDER_SETTINGS
                )
            except Exception as e:
                logging.error(
                    f"Error loading image provider '{image_provider}': {str(e)}"
                )
                self.IMAGE_PROVIDER = None
        else:
            if image_provider not in [None, "None", "", "default"]:
                logging.warning(
                    f"Configured image provider '{image_provider}' does not advertise image support; disabling image generation."
                )
            self.IMAGE_PROVIDER = None
        embeddings_provider = (
            self.AGENT_CONFIG["settings"]["embeddings_provider"]
            if "embeddings_provider" in self.AGENT_CONFIG["settings"]
            else "default"
        )
        try:
            self.max_input_tokens = int(self.AGENT_CONFIG["settings"]["MAX_TOKENS"])
        except Exception as e:
            self.max_input_tokens = 32000
        self.chunk_size = 256
        self.extensions = Extensions(
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            agent_config=self.AGENT_CONFIG,
            ApiClient=ApiClient,
            api_key=ApiClient.headers.get("Authorization"),
            user=self.user,
        )
        self.available_commands = self.extensions.get_available_commands()

        # CodeQL ultra-safe pattern: Create secure workspace directory
        base_workspace = "WORKSPACE"
        os.makedirs(base_workspace, exist_ok=True)

        # Create agent-specific directory using hash of agent_id for security
        import hashlib

        if self.agent_id:
            agent_hash = hashlib.sha256(str(self.agent_id).encode()).hexdigest()[:16]
            agent_workspace = f"{base_workspace}/agent_{agent_hash}"
        else:
            agent_workspace = f"{base_workspace}/default_agent"

        os.makedirs(agent_workspace, exist_ok=True)
        self.working_directory = agent_workspace
        if "company_id" in self.AGENT_CONFIG["settings"]:
            company_id_value = self.AGENT_CONFIG["settings"]["company_id"]
            # Handle various None representations
            if company_id_value is None or str(company_id_value).lower() in [
                "none",
                "null",
                "",
            ]:
                self.company_id = None
            else:
                self.company_id = str(company_id_value)
        else:
            self.company_id = None
        self.PROVIDER_SETTINGS["company_id"] = self.company_id
        self.company_agent = None
        if self.company_id:
            self.company_agent = self.get_company_agent()

    def get_company_agent(self):
        # Check for actual None or "None" string
        if self.company_id and str(self.company_id).lower() != "none":
            company_agent_session = self.auth.get_company_agent_session(
                company_id=self.company_id
            )
            if not company_agent_session:
                return None
            # Company agents have email format: {company_id}@{company_id}.xt
            company_email = f"{self.company_id}@{self.company_id}.xt"
            agent = Agent(
                agent_name="AGiXT",
                user=company_email,
                ApiClient=company_agent_session,
            )
            return agent
        else:
            return None

    def get_company_agent_extensions(self):
        agent_extensions = self.get_agent_extensions()
        if self.company_id:
            agent = self.get_company_agent()
            company_extensions = agent.get_agent_extensions()
            # We want to find out if any commands are enabled in company_extensions and set them to enabled for agent_extensions
            for company_extension in company_extensions:
                for agent_extension in agent_extensions:
                    if (
                        company_extension["extension_name"]
                        == agent_extension["extension_name"]
                    ):
                        for company_command in company_extension["commands"]:
                            for agent_command in agent_extension["commands"]:
                                if (
                                    company_command["friendly_name"]
                                    == agent_command["friendly_name"]
                                ):
                                    if (
                                        str(company_command["enabled"]).lower()
                                        == "true"
                                    ):
                                        agent_command["enabled"] = True
            return agent_extensions
        else:
            logging.info("No company_id found.")
            return agent_extensions

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

        # If we have agent_id, use it to find the agent
        if (
            hasattr(self, "agent_id")
            and self.agent_id is not None
            and str(self.agent_id) != "None"
        ):
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.id == self.agent_id, AgentModel.user_id == self.user_id
                )
                .first()
            )
            if not agent:
                # Try to find in global agents (DEFAULT_USER)
                global_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                if global_user:
                    agent = (
                        session.query(AgentModel)
                        .filter(
                            AgentModel.id == self.agent_id,
                            AgentModel.user_id == global_user.id,
                        )
                        .first()
                    )
        else:
            # Use agent_name to find the agent
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user_id == self.user_id,
                )
                .first()
            )
            if not agent:
                agent = (
                    session.query(AgentModel)
                    .filter(AgentModel.user_id == self.user_id)
                    .first()
                )
                if not agent:
                    # Create an agent.
                    add_agent(agent_name=self.agent_name, user=self.user)
                    # Get the agent
                    agent = (
                        session.query(AgentModel)
                        .filter(
                            AgentModel.name == self.agent_name,
                            AgentModel.user_id == self.user_id,
                        )
                        .first()
                    )
            self.agent_id = str(agent.id) if agent else None
        config = {"settings": {}, "commands": {}}

        # Wallet Creation Logic - Runs only if agent exists
        if agent:
            # Check for existing wallet settings
            existing_wallet_address = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_ADDRESS",
                )
                .first()
            )

            existing_private_key = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_API_KEY",
                )
                .first()
            )

            existing_passphrase = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_PASSPHRASE_API_KEY",
                )
                .first()
            )

            # Check if wallet doesn't exist or any of the critical settings are empty
            wallet_needs_creation = (
                not existing_wallet_address
                or not existing_private_key
                or not existing_passphrase
                or not (existing_wallet_address and existing_wallet_address.value)
                or not (existing_private_key and existing_private_key.value)
                or not (existing_passphrase and existing_passphrase.value)
            )

            if wallet_needs_creation:
                # Wallet doesn't exist or is incomplete, create and save it
                logging.info(
                    f"Solana wallet missing or incomplete for agent {agent.name} ({agent.id}). Creating new wallet..."
                )
                try:
                    private_key, passphrase, address = create_solana_wallet()

                    # Update or create the settings
                    if existing_private_key:
                        existing_private_key.value = private_key
                    else:
                        session.add(
                            AgentSettingModel(
                                agent_id=agent.id,
                                name="SOLANA_WALLET_API_KEY",
                                value=private_key,
                            )
                        )

                    if existing_passphrase:
                        existing_passphrase.value = passphrase
                    else:
                        session.add(
                            AgentSettingModel(
                                agent_id=agent.id,
                                name="SOLANA_WALLET_PASSPHRASE_API_KEY",
                                value=passphrase,
                            )
                        )

                    if existing_wallet_address:
                        existing_wallet_address.value = address
                    else:
                        session.add(
                            AgentSettingModel(
                                agent_id=agent.id,
                                name="SOLANA_WALLET_ADDRESS",
                                value=address,
                            )
                        )

                    session.commit()
                    logging.info(
                        f"Successfully created and saved Solana wallet for agent {agent.name} ({agent.id})."
                    )

                    # Refresh agent_settings to include newly created wallet settings
                    agent_settings = (
                        session.query(AgentSettingModel)
                        .filter_by(agent_id=agent.id)
                        .all()
                    )
                except Exception as e:
                    logging.error(
                        f"Error creating/saving Solana wallet for agent {agent.name} ({agent.id}): {e}"
                    )
                    session.rollback()  # Rollback DB changes on error

        if agent:
            all_commands = session.query(Command).all()
            # Only query agent_settings if not already refreshed after wallet creation
            if "agent_settings" not in locals():
                agent_settings = (
                    session.query(AgentSettingModel).filter_by(agent_id=agent.id).all()
                )
            agent_commands = (
                session.query(AgentCommand)
                .filter(AgentCommand.agent_id == agent.id)
                .all()
            )
            # Process all commands, including chains
            for command in all_commands:
                config["commands"][command.name] = any(
                    ac.command_id == command.id and ac.state for ac in agent_commands
                )
            for setting in agent_settings:
                # Don't skip wallet-related settings even if they're empty (they should have been created above)
                # but skip other empty settings as before
                if setting.value == "" and not setting.name.startswith("SOLANA_WALLET"):
                    continue
                config["settings"][setting.name] = setting.value
            user_settings = self.get_registration_requirement_settings()
            for key, value in user_settings.items():
                config["settings"][key] = value
        else:
            config = {"settings": DEFAULT_SETTINGS, "commands": {}}
            user_settings = self.get_registration_requirement_settings()
            for key, value in user_settings.items():
                if value == "":
                    continue
                config["settings"][key] = value
        session.close()
        company_id = config["settings"].get("company_id")
        if company_id:
            self.company_id = company_id
            if str(self.user).endswith(".xt"):
                return config
            company_agent = self.get_company_agent()
            if company_agent:
                company_agent_config = company_agent.get_agent_config()
                company_settings = company_agent_config.get("settings")
                for key, value in company_settings.items():
                    if key not in config["settings"]:
                        if value == "":
                            continue
                        config["settings"][key] = value
                comand_agent_commands = company_agent_config.get("commands")
                for key, value in comand_agent_commands.items():
                    if key not in config["commands"]:
                        config["commands"][key] = value
        else:
            company_id = self.auth.company_id
            self.update_agent_config(
                new_config={"company_id": company_id}, config_key="settings"
            )
        enabled_commands = getenv("ENABLED_COMMANDS")
        if "," in enabled_commands:
            enabled_commands = enabled_commands.split(",")
        else:
            enabled_commands = [enabled_commands]
        for command in enabled_commands:
            config["commands"][command] = True
        session.close()
        return config

    async def inference(
        self,
        prompt: str,
        images: list = [],
        use_smartest: bool = False,
        stream: bool = False,
    ):
        if not prompt:
            return ""
        input_tokens = get_tokens(prompt)
        provider_name = self.AGENT_CONFIG["settings"]["provider"]

        # Emit webhook event for inference start
        await webhook_emitter.emit_event(
            event_type="agent.inference.started",
            data={
                "agent_id": str(self.agent_id),
                "agent_name": self.agent_name,
                "user_id": str(self.user_id),
                "provider": provider_name,
                "input_tokens": input_tokens,
                "use_smartest": use_smartest,
                "has_images": len(images) > 0,
                "timestamp": datetime.now().isoformat(),
            },
            user_id=str(self.user_id),
        )

        try:
            if stream:
                # For streaming, return the stream object for the caller to handle
                if provider_name == "rotation" and use_smartest == True:
                    return await self.PROVIDER.inference(
                        prompt=prompt,
                        tokens=input_tokens,
                        images=images,
                        use_smartest=True,
                        stream=True,
                    )
                else:
                    return await self.PROVIDER.inference(
                        prompt=prompt, tokens=input_tokens, images=images, stream=True
                    )
            else:
                # Non-streaming path
                if provider_name == "rotation" and use_smartest == True:
                    answer = await self.PROVIDER.inference(
                        prompt=prompt,
                        tokens=input_tokens,
                        images=images,
                        use_smartest=True,
                    )
                else:
                    answer = await self.PROVIDER.inference(
                        prompt=prompt, tokens=input_tokens, images=images
                    )
                output_tokens = get_tokens(answer)
                self.auth.increase_token_counts(
                    input_tokens=input_tokens, output_tokens=output_tokens
                )
                answer = str(answer).replace("\_", "_")
                if answer.endswith("\n\n"):
                    answer = answer[:-2]

                # Emit webhook event for successful inference
                await webhook_emitter.emit_event(
                    event_type="agent.inference.completed",
                    data={
                        "agent_id": str(self.agent_id),
                        "agent_name": self.agent_name,
                        "user_id": str(self.user_id),
                        "provider": provider_name,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "timestamp": datetime.now().isoformat(),
                    },
                    user_id=str(self.user_id),
                )
        except Exception as e:
            logging.error(f"Error in inference: {str(e)}")
            answer = "<answer>Unable to process request.</answer>"

            # Emit webhook event for failed inference
            await webhook_emitter.emit_event(
                event_type="agent.inference.failed",
                data={
                    "agent_id": str(self.agent_id),
                    "agent_name": self.agent_name,
                    "user_id": str(self.user_id),
                    "provider": provider_name,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=str(self.user_id),
            )
        return answer

    async def vision_inference(
        self, prompt: str, images: list = [], use_smartest: bool = False
    ):
        if not prompt:
            return ""
        if not self.VISION_PROVIDER:
            return ""
        input_tokens = get_tokens(prompt)
        provider_name = self.AGENT_CONFIG["settings"]["provider"]
        try:
            if provider_name == "rotation" and use_smartest == True:
                answer = await self.PROVIDER.inference(
                    prompt=prompt, tokens=input_tokens, images=images, use_smartest=True
                )
            else:
                answer = await self.PROVIDER.inference(
                    prompt=prompt, tokens=input_tokens, images=images
                )
            output_tokens = get_tokens(answer)
            self.auth.increase_token_counts(
                input_tokens=input_tokens, output_tokens=output_tokens
            )
            answer = str(answer).replace("\_", "_")
            if answer.endswith("\n\n"):
                answer = answer[:-2]
        except Exception as e:
            logging.error(f"Error in inference: {str(e)}")
            answer = "<answer>Unable to process request.</answer>"
        return answer

    def embeddings(self, input) -> np.ndarray:
        from Memories import embed

        return embed(input=input)

    async def transcribe_audio(self, audio_path: str):
        return await self.TRANSCRIPTION_PROVIDER.transcribe_audio(audio_path=audio_path)

    async def translate_audio(self, audio_path: str):
        return await self.TRANSLATION_PROVIDER.translate_audio(audio_path=audio_path)

    async def generate_image(self, prompt: str):
        if not self.IMAGE_PROVIDER or not hasattr(
            self.IMAGE_PROVIDER, "generate_image"
        ):
            raise HTTPException(
                status_code=400,
                detail="This agent is not configured with an image-capable provider.",
            )
        return await self.IMAGE_PROVIDER.generate_image(prompt=prompt)

    async def text_to_speech(self, text: str):
        if self.TTS_PROVIDER is not None:
            if "```" in text:
                text = re.sub(
                    r"```[^```]+```",
                    "See the chat for the full code block.",
                    text,
                )
            # If links are in there, replace them with a placeholder "The link provided in the chat."
            if "https://" in text:
                text = re.sub(
                    r"https://[^\s]+",
                    "The link provided in the chat.",
                    text,
                )
            if "http://" in text:
                text = re.sub(
                    r"http://[^\s]+",
                    "The link provided in the chat.",
                    text,
                )
            tts_content = await self.TTS_PROVIDER.text_to_speech(text=text)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

            # CodeQL ultra-safe pattern: Complete data flow isolation
            import tempfile
            import shutil

            # Create secure temporary directory completely isolated from user input
            with tempfile.TemporaryDirectory() as temp_base:
                # Create secure filename using only system-generated data
                secure_filename = f"agent_{timestamp}.wav"

                # Write audio data to secure temp file
                temp_audio_path = f"{temp_base}/{secure_filename}"
                with open(temp_audio_path, "wb") as f:
                    f.write(base64.b64decode(tts_content))

                # Create final secure location in workspace using hardcoded paths only
                workspace_outputs = "WORKSPACE/outputs"
                os.makedirs(workspace_outputs, exist_ok=True)

                # Move to final location with system-generated filename
                final_audio_path = f"{workspace_outputs}/{secure_filename}"
                shutil.move(temp_audio_path, final_audio_path)

                agixt_uri = getenv("AGIXT_URI")
                output_url = f"{agixt_uri}/outputs/{secure_filename}"
                return output_url

    def get_agent_extensions(self):
        extensions = self.extensions.get_extensions()
        new_extensions = []
        session = get_session()
        user_oauth = (
            session.query(UserOAuth).filter(UserOAuth.user_id == self.user_id).all()
        )
        user = session.query(User).filter(User.id == self.user_id).first()
        sso_providers = {}
        # Get OAuth-enabled extensions by scanning for SSO components
        import importlib.util

        extensions_dir = os.path.join(os.path.dirname(__file__), "extensions")
        extension_files = os.listdir(extensions_dir)
        for extension_file in extension_files:
            if extension_file.endswith(".py") and not extension_file.startswith("__"):
                try:
                    # Load the extension module to check for OAuth components
                    extension_name = extension_file.replace(".py", "")
                    file_path = os.path.join(extensions_dir, extension_file)
                    spec = importlib.util.spec_from_file_location(
                        extension_name, file_path
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Check if the extension has OAuth components (SSO class or sso function)
                    has_sso_class = any(
                        hasattr(module, f"{extension_name.capitalize()}SSO")
                        for extension_name in [extension_name]
                    )
                    has_sso_function = hasattr(module, "sso")
                    has_oauth_scopes = hasattr(module, "SCOPES")

                    if has_sso_class or has_sso_function or has_oauth_scopes:
                        sso_providers[extension_name] = False
                except Exception as e:
                    # Skip extensions that can't be loaded or don't have OAuth components
                    logging.debug(
                        f"Extension {extension_file} does not have OAuth components: {str(e)}"
                    )
                    continue
        if user_oauth:
            for oauth in user_oauth:
                provider = (
                    session.query(OAuthProvider)
                    .filter(OAuthProvider.id == oauth.provider_id)
                    .first()
                )
                if provider:
                    if not str(user.email).lower().endswith(".xt"):
                        if str(provider.name).lower() in sso_providers:
                            sso_providers[str(provider.name).lower()] = True
        for extension in extensions:
            extension_name_lower = str(extension["extension_name"]).lower()
            if extension_name_lower in sso_providers:
                # Special handling for wallet extension
                if extension_name_lower == "wallet":
                    # For wallet extensions, check if user is authenticated via wallet
                    # (user email ends with @crypto.wallet)
                    is_wallet_user = user and str(user.email).endswith("@crypto.wallet")
                    if not is_wallet_user:
                        continue  # Skip wallet extension for non-wallet users
                else:
                    # Regular OAuth provider logic
                    if not sso_providers[extension_name_lower]:
                        continue
                if extension_name_lower == "github":
                    extension["settings"] = []
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
            if new_extension["commands"] == [] and new_extension["settings"] == []:
                continue
            new_extensions.append(new_extension)
        for extension in new_extensions:
            for command in extension["commands"]:
                if command["friendly_name"] in self.AGENT_CONFIG["commands"]:
                    command["enabled"] = (
                        str(
                            self.AGENT_CONFIG["commands"][command["friendly_name"]]
                        ).lower()
                        == "true"
                    )
                else:
                    command["enabled"] = False
        session.close()
        return new_extensions

    def update_agent_config(self, new_config, config_key):
        session = get_session()

        # If we have agent_id, use it to find the agent
        if (
            hasattr(self, "agent_id")
            and self.agent_id is not None
            and str(self.agent_id) != "None"
        ):
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.id == self.agent_id, AgentModel.user_id == self.user_id
                )
                .first()
            )
            if not agent:
                # Try to find in global agents
                global_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                if global_user:
                    agent = (
                        session.query(AgentModel)
                        .filter(
                            AgentModel.id == self.agent_id,
                            AgentModel.user_id == global_user.id,
                        )
                        .first()
                    )
        else:
            # Use agent_name to find the agent
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.name == self.agent_name,
                    AgentModel.user_id == self.user_id,
                )
                .first()
            )
            if not agent:
                if self.user == DEFAULT_USER:
                    return f"Agent {self.agent_name} not found."
                # Check if it is a global agent and copy it if necessary
                global_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                global_agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.name == self.agent_name,
                        AgentModel.user_id == global_user.id,
                    )
                    .first()
                )
                if global_agent:
                    agent = AgentModel(
                        name=self.agent_name,
                        user_id=self.user_id,
                        provider_id=global_agent.provider_id,
                    )
                    session.add(agent)
                    session.commit()
                self.agent_id = str(agent.id)
                # Copy settings and commands from global agent
                for setting in global_agent.settings:
                    new_setting = AgentSettingModel(
                        agent_id=self.agent_id,
                        name=setting.name,
                        value=setting.value,
                    )
                    session.add(new_setting)
                for command in global_agent.commands:
                    new_command = AgentCommand(
                        agent_id=self.agent_id,
                        command_id=command.command_id,
                        state=command.state,
                    )
                    session.add(new_command)
                session.commit()

        if config_key == "commands":
            for command_name, enabled in new_config.items():
                # Protect against empty command names
                if not command_name or command_name.strip() == "":
                    logging.error("Empty command name provided in config, skipping")
                    continue

                # First try to find an existing command
                command = session.query(Command).filter_by(name=command_name).first()

                if not command:
                    # Check if this is a chain command
                    chain = session.query(ChainDB).filter_by(name=command_name).first()
                    if chain:
                        # Find or create the Custom Automation extension
                        extension = (
                            session.query(Extension)
                            .filter_by(name="Custom Automation")
                            .first()
                        )
                        if not extension:
                            extension = Extension(name="Custom Automation")
                            session.add(extension)
                            session.commit()

                        # Create a new command entry for the chain
                        command = Command(name=command_name, extension_id=extension.id)
                        session.add(command)
                        session.commit()
                    else:
                        logging.error(f"Command {command_name} not found.")
                        continue

                # Now handle the agent command association
                try:
                    agent_command = (
                        session.query(AgentCommand)
                        .filter_by(agent_id=self.agent_id, command_id=command.id)
                        .first()
                    )
                except:
                    agent_command = None

                if agent_command:
                    agent_command.state = enabled
                else:
                    agent_command = AgentCommand(
                        agent_id=self.agent_id,
                        command_id=command.id,
                        state=enabled,
                    )
                    session.add(agent_command)
        else:
            for setting_name, setting_value in new_config.items():
                agent_setting = (
                    session.query(AgentSettingModel)
                    .filter_by(agent_id=self.agent_id, name=setting_name)
                    .first()
                )
                if agent_setting:
                    if setting_value == "":
                        session.delete(agent_setting)
                    else:
                        agent_setting.value = str(setting_value)
                else:
                    agent_setting = AgentSettingModel(
                        agent_id=self.agent_id,
                        name=setting_name,
                        value=str(setting_value),
                    )
                    session.add(agent_setting)

        try:
            session.commit()
            logging.info(f"Agent {self.agent_name} configuration updated successfully.")

            # Emit webhook event for agent configuration update
            import asyncio

            try:
                asyncio.create_task(
                    webhook_emitter.emit_event(
                        event_type="agent.settings.updated",
                        data={
                            "agent_id": str(self.agent_id),
                            "agent_name": self.agent_name,
                            "user_id": str(self.user_id),
                            "config_key": config_key,
                            "updated_config": new_config,
                            "timestamp": datetime.now().isoformat(),
                        },
                        user_id=str(self.user_id),
                    )
                )
            except:
                logging.debug(
                    f"Could not emit webhook event for agent configuration update: {self.agent_name}"
                )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating agent configuration: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error updating agent configuration: {str(e)}"
            )
        finally:
            session.close()

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

        # Handle conversation_id conversion - convert "0" or invalid UUIDs to None
        if conversation_id == "0" or conversation_id == 0 or not conversation_id:
            conversation_id = None
        elif conversation_id:
            # Validate that it's a proper UUID string
            try:
                import uuid

                uuid.UUID(str(conversation_id))
                conversation_id = str(conversation_id)
            except (ValueError, TypeError):
                conversation_id = None

        browsed_link = AgentBrowsedLink(
            agent_id=agent.id, link=url, conversation_id=conversation_id
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
            .filter_by(agent_id=agent.id, link=url, conversation_id=conversation_id)
            .first()
        )
        if not browsed_link:
            return f"Link {url} not found."
        session.delete(browsed_link)
        session.commit()
        session.close()
        return f"Link {url} deleted from browsed links."

    def get_agent_name_by_id(self):
        """Get agent name by agent_id"""
        session = get_session()
        try:
            agent = (
                session.query(AgentModel)
                .filter(
                    AgentModel.id == self.agent_id, AgentModel.user_id == self.user_id
                )
                .first()
            )
            if not agent:
                # Try to find in global agents (DEFAULT_USER)
                global_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                if global_user:
                    agent = (
                        session.query(AgentModel)
                        .filter(
                            AgentModel.id == self.agent_id,
                            AgentModel.user_id == global_user.id,
                        )
                        .first()
                    )
            if not agent:
                raise ValueError(
                    f"Agent with ID {self.agent_id} not found for user {self.user}"
                )
            return agent.name
        finally:
            session.close()

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

    @staticmethod
    def sanitize_path_component(component):
        """
        Sanitize a path component to prevent path traversal attacks.
        Implements CodeQL recommended security patterns.

        Args:
            component (str): The path component to sanitize

        Returns:
            str: The sanitized path component

        Raises:
            ValueError: If the component contains invalid characters
        """
        import re
        import os

        if not component or not isinstance(component, str):
            raise ValueError("Path component must be a non-empty string")

        # Strip whitespace
        component = component.strip()

        if not component:
            raise ValueError("Path component is empty after stripping whitespace")

        # Check for any path separators or dangerous sequences
        dangerous_patterns = [
            os.sep,  # OS-specific path separator
            os.altsep,  # Alternative path separator (Windows)
            "/",  # Forward slash
            "\\",  # Backslash
            "..",  # Parent directory
            ".",  # Current directory (except single char names)
            "~",  # Home directory
            "\0",  # Null byte
        ]

        for pattern in dangerous_patterns:
            if pattern and pattern in component:
                raise ValueError(
                    f"Invalid path component contains dangerous pattern: {repr(pattern)}"
                )

        # Use strict allowlist: only alphanumeric, hyphens, and underscores
        # This follows CodeQL recommendation for allowlist validation
        if not re.match(r"^[a-zA-Z0-9_-]+$", component):
            raise ValueError(f"Path component contains invalid characters: {component}")

        # Additional length check for security
        if len(component) > 255:
            raise ValueError("Path component too long")

        return component

    def get_conversation_tasks(self, conversation_id: str) -> str:
        """Get all tasks assigned to an agent"""
        session = None
        try:
            session = get_session()
            tasks = (
                session.query(TaskItem)
                .filter(
                    TaskItem.agent_id == self.agent_id,
                    TaskItem.user_id == self.user_id,
                    TaskItem.completed == False,
                    TaskItem.memory_collection == conversation_id,
                )
                .all()
            )
            if not tasks:
                return ""

            markdown_tasks = "## The Assistant's Scheduled Tasks\n**The assistant currently has the following tasks scheduled:**\n"
            for task in tasks:
                string_due_date = task.due_date.strftime("%Y-%m-%d %H:%M:%S")
                markdown_tasks += (
                    f"### Task: {task.title}\n"
                    f"**Description:** {task.description}\n"
                    f"**Will be completed at:** {string_due_date}\n"
                )
            return markdown_tasks
        except Exception as e:
            logging.error(f"Error getting tasks by agent: {str(e)}")
            return ""
        finally:
            if session:
                try:
                    session.close()
                except Exception as close_e:
                    logging.error(
                        f"Error closing session in get_conversation_tasks: {close_e}"
                    )

    def get_all_pending_tasks(self) -> list:
        """Get all tasks assigned to an agent"""
        session = None
        try:
            session = get_session()
            tasks = (
                session.query(TaskItem)
                .filter(
                    TaskItem.agent_id == self.agent_id,
                    TaskItem.user_id == self.user_id,
                    TaskItem.completed == False,
                )
                .all()
            )
            return tasks
        except Exception as e:
            logging.error(f"Error getting tasks by agent: {str(e)}")
            return []
        finally:
            if session:
                try:
                    session.close()
                except Exception as close_e:
                    logging.error(
                        f"Error closing session in get_all_pending_tasks: {close_e}"
                    )

    def get_all_commands_markdown(self):
        command_list = [
            available_command["friendly_name"]
            for available_command in self.available_commands
            if available_command["enabled"] == True
        ]
        if self.company_id and self.company_agent:
            company_command_list = [
                available_command["friendly_name"]
                for available_command in self.company_agent.available_commands
                if available_command["enabled"] == True
            ]
            # Check if anything enabled in company commands
            if len(company_command_list) > 0:
                # Check if the enabled items are already enabled for the user available commands
                for company_command in company_command_list:
                    if company_command not in command_list:
                        command_list.append(company_command)
        if len(command_list) > 0:
            try:
                agent_extensions = self.get_company_agent_extensions()
                if agent_extensions == "":
                    agent_extensions = self.get_agent_extensions()
            except Exception as e:
                logging.error(f"Error getting agent extensions: {str(e)}")
                agent_extensions = self.get_agent_extensions()
            agent_commands = "## Available Commands\n\n**See command examples of commands that the assistant has access to below:**\n"
            for extension in agent_extensions:
                if extension["commands"] == []:
                    continue
                extension_name = extension["extension_name"]
                extension_description = extension["description"]
                agent_commands += (
                    f"\n### {extension_name}\nDescription: {extension_description}\n"
                )
                for command in extension["commands"]:
                    command_friendly_name = command["friendly_name"]
                    command_description = command["description"]
                    agent_commands += f"\n#### {command_friendly_name}\nDescription: {command_description}\n"
                    for arg_name in command["command_args"].keys():
                        if arg_name != "chain_name":
                            agent_commands += f"<{arg_name}>The assistant will fill in the value based on relevance to the conversation.</{arg_name}>\n"
                        else:
                            agent_commands += (
                                f"<chain_name>{command_friendly_name}</chain_name>\n"
                            )
                    agent_commands += "</execute>\n"
            agent_commands += f"""## Command Usage Guidelines
- **The assistant has commands available to use if they would be useful to provide a better user experience.**
- Reference examples for correct syntax and usage of commands.
- All inputs are strings and must be appropriately filled in with the correct values.
- The assistant can execute a command anywhere in the response, and the commands will be executed in the order they appear.
- The assistant will receive the command output before the user does and will be able to reference the output in the response.
- The assistant can choose to execute as many commands as needed in the response in the order that they should be executed.
- Once the assistant executes a command, it should stop at </execute> and wait for the command output before continuing.
- If the command output indicates a failure status, try changing your approach and trying again, don't try to execute it with the same parameters if it fails, try something different.
- The assistant should never generate a <output> tag in the response. The assistant will receive the command output and will be able to reference the output in the response.
- If there is an <output> tag in the assistants previous responses in context, it refers to the command execution output. Use this output to determine if the command was successful, and to course correct if needed.
- Any time the assistant executes a command, the text generation should end with </execute>. The assistant will be informed of the command output before the user receives the response to give the assistant the opportunity to evaluate the output and ensure it is correct, exploring different options if needed.
- After command execution, increase step budget by 5, continue thinking, executing more commands if necessary for self-error correct unless user intervention is required, and then respond to the user.
- Command executions should all take place BEFORE the <answer> block! Never inside the <answer> block. Only the response to the user goes inside the <answer> block.
- Ensure that command names are EXACTLY as written in the command execution examples. A natural language friendly name is used.
- **THE ASSISTANT CANNOT EXECUTE A COMMAND THAT IS NOT ON THE LIST OF EXAMPLES!**"""
            return agent_commands
        return ""

    def get_commands_prompt(self, conversation_id, running_command=None):
        command_list = [
            available_command["friendly_name"]
            for available_command in self.available_commands
            if available_command["enabled"] == True
        ]
        if self.company_id and self.company_agent:
            company_command_list = [
                available_command["friendly_name"]
                for available_command in self.company_agent.available_commands
                if available_command["enabled"] == True
            ]
            # Check if anything enabled in company commands
            if len(company_command_list) > 0:
                # Check if the enabled items are already enabled for the user available commands
                for company_command in company_command_list:
                    if company_command not in command_list:
                        command_list.append(company_command)
        if len(command_list) > 0:
            working_directory = f"{self.working_directory}/{conversation_id}"
            conversation_outputs = (
                f"http://localhost:7437/outputs/{self.agent_id}/{conversation_id}/"
            )
            try:
                agent_extensions = self.get_company_agent_extensions()
                if agent_extensions == "":
                    agent_extensions = self.get_agent_extensions()
            except Exception as e:
                logging.error(f"Error getting agent extensions: {str(e)}")
                agent_extensions = self.get_agent_extensions()
            agent_commands = "## Available Commands\n\n**See command execution examples of commands that the assistant has access to below:**\n"
            for extension in agent_extensions:
                if extension["commands"] == []:
                    continue
                extension_name = extension["extension_name"]
                extension_description = extension["description"]
                enabled_commands = [
                    command
                    for command in extension["commands"]
                    if command["enabled"] == True
                ]
                if running_command:
                    # Remove the running command from enabled commands
                    enabled_commands = [
                        command
                        for command in enabled_commands
                        if command["friendly_name"] != running_command
                    ]
                if enabled_commands == []:
                    continue
                agent_commands += (
                    f"\n### {extension_name}\nDescription: {extension_description}\n"
                )
                for command in enabled_commands:
                    command_friendly_name = command["friendly_name"]
                    command_description = command["description"]
                    agent_commands += f"\n#### {command_friendly_name}\nDescription: {command_description}\nCommand execution format:\n"
                    agent_commands += (
                        f"<execute>\n<name>{command_friendly_name}</name>\n"
                    )
                    for arg_name in command["command_args"].keys():
                        if arg_name != "chain_name":
                            agent_commands += f"<{arg_name}>The assistant will fill in the value based on relevance to the conversation.</{arg_name}>\n"
                        else:
                            agent_commands += (
                                f"<chain_name>{command_friendly_name}</chain_name>\n"
                            )
                    agent_commands += "</execute>\n"
            agent_commands += f"""## Command Execution Guidelines
- **The assistant has commands available to use if they would be useful to provide a better user experience.**
- Reference examples for correct syntax and usage of commands.
- To execute a command, the assistant should use the following format:

<execute>
<name>FULL COMMAND NAME</name>
<ARG1_NAME>ARG1_VALUE</ARG1_NAME>
<ARG2_NAME>ARG2_VALUE</ARG2_NAME>
...
</execute>

- All inputs are strings and must be appropriately filled in with the correct values.
- The assistant can execute a command anywhere in the response, and the commands will be executed in the order they appear.
- If referencing a file path, use the assistant's working directory as the file path. The assistant's working directory is {working_directory}.
- Only reference files in the working directory! The assistant cannot access files outside of the working directory.
- All files in the working directory will be immediately available to the user and agent in this folder: {conversation_outputs}
- The assistant will receive the command output before the user does and will be able to reference the output in the response.
- The assistant can choose to execute as many commands as needed in the response in the order that they should be executed.
- Once the assistant executes a command, it should stop at </execute> and wait for the command output before continuing.
- The assistant should never generate a <output> tag in the response. The assistant will receive the command output and will be able to reference the output in the response.
- If there is an <output> tag in the assistants previous responses in context, it refers to the command execution output. Use this output to determine if the command was successful, and to course correct if needed.
- Any time the assistant executes a command, the text generation should end with </execute>. The assistant will be informed of the command output before the user receives the response to give the assistant the opportunity to evaluate the output and ensure it is correct, exploring different options if needed.
- After command execution, increase step budget by 5, continue thinking, executing more commands if necessary for self-error correct unless user intervention is required, and then respond to the user.
- Command executions should all take place BEFORE the <answer> block! Never inside the <answer> block. Only the response to the user goes inside the <answer> block.
- Ensure that command names are EXACTLY as written in the command execution examples. A natural language friendly name is used.
- **THE ASSISTANT CANNOT EXECUTE A COMMAND THAT IS NOT ON THE LIST OF EXAMPLES!**"""
            return agent_commands
        return ""

    def get_agent_wallet(self):
        """
        Retrieves the private key and passphrase for the agent's Solana wallet.
        If wallet doesn't exist or is empty, creates a new one.
        Strictly enforces one wallet per agent.
        Authenticates using the provided API key.
        """
        session = get_session()
        try:
            # Find the agent first to ensure it belongs to the user
            if (
                hasattr(self, "agent_id")
                and self.agent_id is not None
                and str(self.agent_id) != "None"
            ):
                agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.id == self.agent_id,
                        AgentModel.user_id == self.user_id,
                    )
                    .first()
                )
                if not agent:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Agent with ID '{self.agent_id}' not found for this user.",
                    )
            else:
                agent = (
                    session.query(AgentModel)
                    .filter(
                        AgentModel.name == self.agent_name,
                        AgentModel.user_id == self.user_id,
                    )
                    .first()
                )
                if not agent:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Agent '{self.agent_name}' not found for this user.",
                    )

            # Retrieve wallet settings using the agent_id
            private_key_setting = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_API_KEY",
                )
                .first()
            )

            passphrase_setting = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_PASSPHRASE_API_KEY",
                )
                .first()
            )

            address_setting = (
                session.query(AgentSettingModel)
                .filter(
                    AgentSettingModel.agent_id == agent.id,
                    AgentSettingModel.name == "SOLANA_WALLET_ADDRESS",
                )
                .first()
            )

            # Check if wallet settings are missing or empty
            wallet_incomplete = (
                not private_key_setting
                or not passphrase_setting
                or not address_setting
                or not (private_key_setting and private_key_setting.value)
                or not (passphrase_setting and passphrase_setting.value)
                or not (address_setting and address_setting.value)
            )

            if wallet_incomplete:
                # Create a new wallet
                logging.info(
                    f"Wallet missing or incomplete for agent {self.agent_name} ({agent.id}). Creating new wallet..."
                )
                try:
                    private_key, passphrase, address = create_solana_wallet()

                    # Update or create the settings
                    if private_key_setting:
                        private_key_setting.value = private_key
                    else:
                        private_key_setting = AgentSettingModel(
                            agent_id=agent.id,
                            name="SOLANA_WALLET_API_KEY",
                            value=private_key,
                        )
                        session.add(private_key_setting)

                    if passphrase_setting:
                        passphrase_setting.value = passphrase
                    else:
                        passphrase_setting = AgentSettingModel(
                            agent_id=agent.id,
                            name="SOLANA_WALLET_PASSPHRASE_API_KEY",
                            value=passphrase,
                        )
                        session.add(passphrase_setting)

                    if address_setting:
                        address_setting.value = address
                    else:
                        address_setting = AgentSettingModel(
                            agent_id=agent.id,
                            name="SOLANA_WALLET_ADDRESS",
                            value=address,
                        )
                        session.add(address_setting)

                    session.commit()
                    logging.info(
                        f"Successfully created new wallet for agent {self.agent_name} ({agent.id})."
                    )

                    # Refresh the variables after successful creation
                    private_key_value = private_key_setting.value
                    passphrase_value = passphrase_setting.value

                except Exception as wallet_creation_error:
                    session.rollback()
                    logging.error(
                        f"Error creating wallet for agent {self.agent_name}: {wallet_creation_error}"
                    )
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to create wallet for agent.",
                    )
            else:
                # Wallet exists and is complete
                private_key_value = private_key_setting.value
                passphrase_value = passphrase_setting.value

            return {
                "private_key": private_key_value,
                "passphrase": passphrase_value,
            }
        except HTTPException as e:
            session.rollback()
            logging.error(f"HTTPException: {e.detail}")
            raise e  # Re-raise HTTPException
        except Exception as e:
            session.rollback()
            logging.error(f"Error retrieving wallet for agent {self.agent_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error retrieving wallet details.",
            )
        finally:
            session.close()
