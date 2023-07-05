import os
import yaml
import json
from DBConnection import (
    session,
    Provider,
    ProviderSetting,
    Conversation,
    Message,
    Agent,
    Prompt,
    PromptCategory,
    Argument,
    Agent,
    Argument,
    Prompt,
    Extension,
    Setting,
    Command,
    Agent,
    session,
)
from Providers import get_providers, get_provider_options
from db.Agent import import_agent_config


def import_agents():
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
            print(f"Updating agent: {agent_name}")
        else:
            agent = Agent(name=agent_name)
            session.add(agent)
            session.flush()  # Save the agent object to generate an ID
            existing_agent_names.append(agent_name)
            print(f"Adding agent: {agent_name}")
        import_agent_config(agent_name)
    session.commit()


def import_extensions():
    from Extensions import Extensions

    extensions_data = Extensions().get_extensions()
    extension_settings_data = Extensions().get_extension_settings()

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
        description = extension_data.get(
            "description", ""
        )  # Assign an empty string if description is missing

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
                print(f"Adding command: {command_name}")

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
                    print(f"Adding argument: {arg} to command: {command_name}")

    session.commit()

    # Add extensions to the database if they don't exist
    for extension_name in extension_settings_data.keys():
        extension = session.query(Extension).filter_by(name=extension_name).first()
        if not extension:
            extension = Extension(name=extension_name)
            session.add(extension)
            session.flush()
            existing_extensions.append(extension)
            print(f"Adding extension: {extension_name}")

    session.commit()

    # Migrate extension settings
    for extension_name, settings in extension_settings_data.items():
        extension = session.query(Extension).filter_by(name=extension_name).first()
        if not extension:
            print(f"Extension '{extension_name}' not found.")
            continue

        for setting_name, setting_value in settings.items():
            setting = (
                session.query(Setting)
                .filter_by(extension_id=extension.id, name=setting_name)
                .first()
            )
            if setting:
                setting.value = setting_value
                print(
                    f"Updating setting: {setting_name} for extension: {extension_name}"
                )
            else:
                setting = Setting(
                    extension_id=extension.id,
                    name=setting_name,
                    value=setting_value,
                )
                session.add(setting)
                print(f"Adding setting: {setting_name} for extension: {extension_name}")

    session.commit()


def import_chains():
    chain_dir = os.path.abspath("chains")
    chain_files = [
        file
        for file in os.listdir(chain_dir)
        if os.path.isfile(os.path.join(chain_dir, file)) and file.endswith(".json")
    ]
    if not chain_files:
        print(f"No JSON files found in chains directory.")
        return
    from db.Chain import Chain

    chain_importer = Chain()
    for file in chain_files:
        chain_name = os.path.splitext(file)[0]
        file_path = os.path.join(chain_dir, file)

        with open(file_path, "r") as f:
            try:
                chain_data = json.load(f)
                result = chain_importer.import_chain(chain_name, chain_data)
                print(result)
            except json.JSONDecodeError as e:
                print(f"Error importing chain from '{file}': Invalid JSON format.")
            except Exception as e:
                print(f"Error importing chain from '{file}': {str(e)}")


def import_prompts():
    # Add default category if it doesn't exist
    default_category = session.query(PromptCategory).filter_by(name="Default").first()

    if not default_category:
        default_category = PromptCategory(
            name="Default", description="Default category"
        )
        session.add(default_category)
        session.commit()
        print("Adding Default prompt category")

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
            prompt_args = []
            for word in prompt_content.split():
                if word.startswith("{") and word.endswith("}"):
                    prompt_args.append(word[1:-1])
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
                print(f"Adding prompt: {prompt_name}")

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
                print(f"Adding prompt argument: {arg} for {prompt_name}")


def import_conversations():
    agents_dir = "agents"  # Directory containing agent folders
    for agent_name in os.listdir(agents_dir):
        agent_dir = os.path.join(agents_dir, agent_name)
        history_file = os.path.join(agent_dir, "history.yaml")

        if not os.path.exists(history_file):
            continue  # Skip agent if history file doesn't exist

        # Get agent ID from the database based on agent name
        agent = session.query(Agent).filter(Agent.name == agent_name).first()
        if not agent:
            print(f"Agent '{agent_name}' not found in the database.")
            continue

        # Load conversation history from the YAML file
        with open(history_file, "r") as file:
            history = yaml.safe_load(file)

        # Check if the conversation already exists for the agent
        existing_conversation = (
            session.query(Conversation)
            .filter(
                Conversation.agent_id == agent.id,
                Conversation.name == f"{agent_name} History",
            )
            .first()
        )
        if existing_conversation:
            continue

        # Create a new conversation
        conversation = Conversation(agent_id=agent.id, name=f"{agent_name} History")
        session.add(conversation)
        session.commit()

        for conversation_data in history["interactions"]:
            # Create a new message for the conversation
            try:
                role = conversation_data["role"]
                content = conversation_data["message"]
                timestamp = conversation_data["timestamp"]
            except KeyError:
                continue
            message = Message(
                role=role,
                content=content,
                timestamp=timestamp,
                conversation_id=conversation.id,
            )
            session.add(message)
            session.commit()

        print(f"Imported `{agent_name} History` conversation for agent '{agent_name}'.")


def import_providers():
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
            print(f"Updating provider: {provider_name}")
        else:
            provider = Provider(name=provider_name)
            session.add(provider)
            existing_provider_names.append(provider_name)
            print(f"Adding provider: {provider_name}")

        for option_name, option_value in provider_options.items():
            provider_setting = (
                session.query(ProviderSetting)
                .filter_by(provider_id=provider.id, name=option_name)
                .one_or_none()
            )
            if provider_setting:
                provider_setting.value = option_value
                print(
                    f"Updating provider setting: {option_name} for provider: {provider_name}"
                )
            else:
                provider_setting = ProviderSetting(
                    provider_id=provider.id,
                    name=option_name,
                    value=option_value,
                )
                session.add(provider_setting)
                print(
                    f"Adding provider setting: {option_name} for provider: {provider_name}"
                )
    session.commit()
