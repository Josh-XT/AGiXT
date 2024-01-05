import os
import json
from DBConnection import (
    get_session,
    Provider,
    ProviderSetting,
    Conversation,
    Message,
    Prompt,
    PromptCategory,
    Argument,
    Extension,
    Setting,
    Command,
    User,
)
from Providers import get_providers, get_provider_options
from db.Agent import add_agent
from fb.History import get_conversation, get_conversations
from Defaults import DEFAULT_USER


def import_agents(user=DEFAULT_USER):
    agents = [
        f.name
        for f in os.scandir("agents")
        if f.is_dir() and not f.name.startswith("__")
    ]
    for agent_name in agents:
        config_path = f"agents/{agent_name}/config.json"
        with open(config_path) as f:
            config = json.load(f)
        add_agent(
            agent_name=agent_name,
            provider_settings=config["settings"],
            commands=config["commands"],
            user=user,
        )
        print(f"Imported agent: {agent_name}")


def import_extensions():
    from Extensions import Extensions

    extensions_data = Extensions().get_extensions()
    extension_settings_data = Extensions().get_extension_settings()
    session = get_session()
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
                print(f"Imported command: {command_name}")

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
                    print(f"Imported argument: {arg} to command: {command_name}")

    session.commit()

    # Add extensions to the database if they don't exist
    for extension_name in extension_settings_data.keys():
        extension = session.query(Extension).filter_by(name=extension_name).first()
        if not extension:
            extension = Extension(name=extension_name)
            session.add(extension)
            session.flush()
            existing_extensions.append(extension)
            print(f"Imported extension: {extension_name}")

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
                print(
                    f"Imported setting: {setting_name} for extension: {extension_name}"
                )

    session.commit()


def import_chains(user=DEFAULT_USER):
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

    chain_importer = Chain(user=user)
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


def import_prompts(user=DEFAULT_USER):
    session = get_session()
    # Add default category if it doesn't exist
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id
    default_category = (
        session.query(PromptCategory).filter_by(name="Default", user_id=user_id).first()
    )

    if not default_category:
        default_category = PromptCategory(
            name="Default", description="Default category", user_id=user_id
        )
        session.add(default_category)
        session.commit()
        print("Imported Default prompt category")

    # Get all prompt files in the specified folder
    for root, dirs, files in os.walk("prompts"):
        for file in files:
            prompt_category = None
            if root != "prompts":
                # Use subfolder name as the prompt category
                category_name = os.path.basename(root)
                prompt_category = (
                    session.query(PromptCategory)
                    .filter_by(name=category_name, user_id=user_id)
                    .first()
                )
                if not prompt_category:
                    prompt_category = PromptCategory(
                        name=category_name,
                        description=f"{category_name} category",
                        user_id=user_id,
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
                .filter_by(
                    name=prompt_name, prompt_category=prompt_category, user_id=user_id
                )
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
                    user_id=user_id,
                )
                session.add(prompt)
                session.commit()
                print(f"Imported prompt: {prompt_name}")

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
                print(f"Imported prompt argument: {arg} for {prompt_name}")


def import_conversations(user=DEFAULT_USER):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id
    conversations = get_conversations(user=user)
    for conversation_name in conversations:
        conversation = get_conversation(conversation_name=conversation_name, user=user)
        if not conversation:
            print(f"Conversation '{conversation_name}' is empty, skipping.")
            continue
        if "interactions" in conversation:
            for interaction in conversation["interactions"]:
                agent_name = interaction["role"]
                message = interaction["message"]
                timestamp = interaction["timestamp"]
                conversation = (
                    session.query(Conversation)
                    .filter(
                        Conversation.name == conversation_name,
                        Conversation.user_id == user_id,
                    )
                    .first()
                )
                if not conversation:
                    # Create the conversation
                    conversation = Conversation(name=conversation_name, user_id=user_id)
                    session.add(conversation)
                    session.commit()
                message = Message(
                    role=agent_name,
                    content=message,
                    timestamp=timestamp,
                    conversation_id=conversation.id,
                )
                session.add(message)
                session.commit()
            print(f"Imported conversation: {conversation_name}")


def import_providers():
    session = get_session()
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
            print(f"Imported provider: {provider_name}")
            session.commit()

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
                    f"Imported provider setting: {option_name} for provider: {provider_name}"
                )
    session.commit()


def import_all_data():
    session = get_session()
    user_count = session.query(User).count()
    if user_count == 0:
        # Create the default user
        print("Creating default admin user...")
        user = User(email=DEFAULT_USER, role="admin")
        session.add(user)
        session.commit()
        print("Default user created.")
        print("Importing providers...")
        import_providers()
        print("Importing extensions...")
        import_extensions()
        print("Importing prompts...")
        import_prompts()
        print("Importing agents...")
        import_agents()
        print("Importing chains...")
        import_chains()  # Partially works
        print("Importing conversations...")
        import_conversations()
        print("Imports complete.")
