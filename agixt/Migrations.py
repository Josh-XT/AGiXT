from DBConnection import (
    session,
    Base,
    engine,
    Extension,
    Command,
    Argument,
    PromptCategory,
    Prompt,
    Provider,
    ProviderSetting,
    AgentProvider,
    AgentProviderSetting,
    Agent,
    AgentCommand,
    AgentSetting,
)
import os
import json
import uuid
import logging
from Extensions import Extensions
from provider import get_providers, get_provider_options


def populate_extensions_and_commands():
    extensions_data = Extensions().get_extensions()

    # Get the existing extensions and commands from the database
    existing_extensions = session.query(Extension).all()
    existing_commands = session.query(Command).all()

    # Delete commands that don't exist in the extensions data
    for command in existing_commands:
        command_exists = any(
            extension_data["extension_name"] == command.extension.name
            and any(
                cmd["friendly_name"] == command.name
                for cmd in extension_data["commands"]
            )
            for extension_data in extensions_data
        )
        if not command_exists:
            session.delete(command)

    # Add new extensions and commands, and update existing commands
    for extension_data in extensions_data:
        extension_name = extension_data["extension_name"]
        description = extension_data["description"]

        # Find the existing extension or create a new one
        extension = next(
            (ext for ext in existing_extensions if ext.name == extension_name),
            None,
        )
        if extension is None:
            extension = Extension(name=extension_name, description=description)
            session.add(extension)
            session.flush()
            existing_extensions.append(extension)
            logging.info(f"Adding extension: {extension_name}")

        commands = extension_data["commands"]

        for command_data in commands:
            if "friendly_name" not in command_data:
                continue

            command_name = command_data["friendly_name"]

            # Find the existing command or create a new one
            command = next(
                (
                    cmd
                    for cmd in existing_commands
                    if cmd.extension_id == extension.id and cmd.name == command_name
                ),
                None,
            )
            if command is None:
                command = Command(
                    extension_id=extension.id,
                    name=command_name,
                )
                session.add(command)
                session.flush()
                existing_commands.append(command)
                logging.info(f"Adding command: {command_name}")

            # Add command arguments
            if "command_args" in command_data:
                command_args = command_data["command_args"]
                for arg, arg_type in command_args.items():
                    if (
                        session.query(Argument)
                        .filter_by(command_id=command.id, name=arg)
                        .first()
                    ):
                        continue
                    command_arg = Argument(
                        command_id=command.id,
                        name=arg,
                    )
                    session.add(command_arg)
                    logging.info(f"Adding argument: {arg} to command: {command_name}")

    session.commit()


def populate_prompts():
    # Add default category if it doesn't exist
    default_category = session.query(PromptCategory).filter_by(name="Default").first()

    if not default_category:
        default_category = PromptCategory(
            name="Default", description="Default category"
        )
        session.add(default_category)
        session.commit()
        logging.info("Adding Default prompt category")

    # Get all prompt files in the specified folder
    for root, dirs, files in os.walk("prompts"):
        for file in files:
            prompt_category = None
            if root != "prompts":
                # Use subfolder name as the prompt category
                category_name = os.path.basename(root)
                prompt_category = (
                    session.query(PromptCategory).filter_by(name=category_name).first()
                )
                if not prompt_category:
                    prompt_category = PromptCategory(
                        name=category_name, description=f"{category_name} category"
                    )
                    session.add(prompt_category)
                    session.commit()
            else:
                # Assign to "Uncategorized" category if prompt is in the root folder
                prompt_category = default_category

            # Read the prompt content from the file
            with open(os.path.join(root, file), "r") as f:
                prompt_content = f.read()

            # Check if prompt with the same name and category already exists
            prompt_name = os.path.splitext(file)[0]
            prompt = (
                session.query(Prompt)
                .filter_by(name=prompt_name, prompt_category=prompt_category)
                .first()
            )
            prompt_args = get_prompt_args(prompt_content)
            if not prompt:
                # Create the prompt entry in the database
                prompt = Prompt(
                    name=prompt_name,
                    description="",
                    content=prompt_content,
                    prompt_category=prompt_category,
                )
                session.add(prompt)
                session.commit()
                logging.info(f"Adding prompt: {prompt_name}")

            # Populate prompt arguments
            for arg in prompt_args:
                if (
                    session.query(Argument)
                    .filter_by(prompt_id=prompt.id, name=arg)
                    .first()
                ):
                    continue
                argument = Argument(
                    prompt_id=prompt.id,
                    name=arg,
                )
                session.add(argument)
                session.commit()
                logging.info(f"Adding prompt argument: {arg} for {prompt_name}")


def get_prompt_args(prompt_text):
    # Find anything in the file between { and } and add them to a list to return
    prompt_vars = []
    for word in prompt_text.split():
        if word.startswith("{") and word.endswith("}"):
            prompt_vars.append(word[1:-1])
    return prompt_vars


def populate_providers():
    providers = get_providers()
    existing_providers = session.query(Provider).all()
    existing_provider_names = [provider.name for provider in existing_providers]

    for provider in existing_providers:
        if provider.name not in providers:
            session.delete(provider)

    for provider_name in providers:
        provider_options = get_provider_options(provider_name)

        provider = session.query(Provider).filter_by(name=provider_name).one_or_none()

        if provider:
            logging.info(f"Updating provider: {provider_name}")
        else:
            provider = Provider(name=provider_name)
            session.add(provider)
            existing_provider_names.append(provider_name)
            logging.info(f"Adding provider: {provider_name}")

        for option_name, option_value in provider_options.items():
            provider_setting = (
                session.query(ProviderSetting)
                .filter_by(provider_id=provider.id, name=option_name)
                .one_or_none()
            )
            if provider_setting:
                provider_setting.value = option_value
                logging.info(
                    f"Updating provider setting: {option_name} for provider: {provider_name}"
                )
            else:
                provider_setting = ProviderSetting(
                    provider_id=provider.id,
                    name=option_name,
                    value=option_value,
                )
                session.add(provider_setting)
                logging.info(
                    f"Adding provider setting: {option_name} for provider: {provider_name}"
                )

    session.commit()


from sqlalchemy import text


def import_agent_config(agent_name):
    config_path = f"agents/{agent_name}/config.json"

    # Load the config JSON file
    with open(config_path) as f:
        config = json.load(f)

    # Get the agent from the database
    agent = session.query(Agent).filter_by(name=agent_name).first()

    if not agent:
        logging.error(f"Agent '{agent_name}' does not exist in the database.")
        return

    # Get the provider ID based on the provider name in the config
    provider_name = config["settings"]["provider"]
    provider = session.query(Provider).filter_by(name=provider_name).first()

    if not provider:
        logging.error(f"Provider '{provider_name}' does not exist in the database.")
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
                    agent_setting = AgentSetting(
                        agent_id=agent.id, name=setting_name, value=setting_value
                    )
                    session.add(agent_setting)

    session.commit()
    logging.info(f"Agent config imported successfully for agent: {agent_name}")


def populate_agents():
    agent_folder = "agents"
    agents = [
        f.name
        for f in os.scandir(agent_folder)
        if f.is_dir() and not f.name.startswith("__")
    ]
    existing_agents = session.query(Agent).all()
    existing_agent_names = [agent.name for agent in existing_agents]

    for agent_name in agents:
        agent = session.query(Agent).filter_by(name=agent_name).one_or_none()

        if agent:
            logging.info(f"Updating agent: {agent_name}")
        else:
            agent = Agent(name=agent_name)
            session.add(agent)
            session.flush()  # Save the agent object to generate an ID
            existing_agent_names.append(agent_name)
            logging.info(f"Adding agent: {agent_name}")

        import_agent_config(agent_name)

    session.commit()


def Migrations():
    # Create the database tables
    Base.metadata.create_all(engine)

    # Populate the database with data
    populate_extensions_and_commands()
    populate_prompts()
    populate_providers()
    populate_agents()
