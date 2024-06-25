import os
import json
import yaml
import logging
from DB import (
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
from Agent import add_agent
from Globals import getenv, DEFAULT_USER

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


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
        logging.info(f"Imported agent: {agent_name}")


def import_extensions():
    from Extensions import Extensions

    extensions_data = Extensions().get_extensions()
    extension_settings_data = Extensions().get_extension_settings()
    session = get_session()
    # Get the existing extensions and commands from the database
    existing_extensions = session.query(Extension).all()
    existing_commands = session.query(Command).all()
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
                logging.info(f"Imported command: {command_name}")
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
                    logging.info(f"Imported argument: {arg} to command: {command_name}")
    session.commit()
    # Add extensions to the database if they don't exist
    for extension_name in extension_settings_data.keys():
        extension = session.query(Extension).filter_by(name=extension_name).first()
        if not extension:
            extension = Extension(name=extension_name)
            session.add(extension)
            session.flush()
            existing_extensions.append(extension)
            logging.info(f"Imported extension: {extension_name}")
    session.commit()
    # Migrate extension settings
    for extension_name, settings in extension_settings_data.items():
        extension = session.query(Extension).filter_by(name=extension_name).first()
        if not extension:
            logging.info(f"Extension '{extension_name}' not found.")
            continue

        for setting_name, setting_value in settings.items():
            setting = (
                session.query(Setting)
                .filter_by(extension_id=extension.id, name=setting_name)
                .first()
            )
            if setting:
                setting.value = setting_value
                logging.info(
                    f"Updating setting: {setting_name} for extension: {extension_name}"
                )
            else:
                setting = Setting(
                    extension_id=extension.id,
                    name=setting_name,
                    value=setting_value,
                )
                session.add(setting)
                logging.info(
                    f"Imported setting: {setting_name} for extension: {extension_name}"
                )
    session.commit()
    session.close()


def import_chains(user=DEFAULT_USER):
    chain_dir = os.path.abspath("chains")
    chain_files = [
        file
        for file in os.listdir(chain_dir)
        if os.path.isfile(os.path.join(chain_dir, file)) and file.endswith(".json")
    ]
    if not chain_files:
        logging.info(f"No JSON files found in chains directory.")
        return
    from Chain import Chain

    chain_importer = Chain(user=user)
    failures = []
    for file in chain_files:
        chain_name = os.path.splitext(file)[0]
        file_path = os.path.join(chain_dir, file)
        with open(file_path, "r") as f:
            try:
                chain_data = json.load(f)
                result = chain_importer.import_chain(chain_name, chain_data)
                if result:
                    logging.info(result)
            except Exception as e:
                logging.info(f"(1/3) Error importing chain from '{file}': {str(e)}")
                failures.append(file)
    if failures:
        # Try each that failed again just in case it had a dependency on another chain
        for file in failures:
            chain_name = os.path.splitext(file)[0]
            file_path = os.path.join(chain_dir, file)
            with open(file_path, "r") as f:
                try:
                    chain_data = json.load(f)
                    result = chain_importer.import_chain(chain_name, chain_data)
                    logging.info(result)
                    failures.remove(file)
                except Exception as e:
                    logging.info(f"(2/3) Error importing chain from '{file}': {str(e)}")
        if failures:
            # Try one more time.
            for file in failures:
                chain_name = os.path.splitext(file)[0]
                file_path = os.path.join(chain_dir, file)
                with open(file_path, "r") as f:
                    try:
                        chain_data = json.load(f)
                        result = chain_importer.import_chain(chain_name, chain_data)
                        logging.info(result)
                        failures.remove(file)
                    except Exception as e:
                        logging.info(
                            f"(3/3) Error importing chain from '{file}': {str(e)}"
                        )
    if failures:
        logging.info(
            f"Failed to import the following chains: {', '.join([os.path.splitext(file)[0] for file in failures])}"
        )


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
        logging.info("Imported Default prompt category")

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
                logging.info(f"Imported prompt: {prompt_name}")

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
                logging.info(f"Imported prompt argument: {arg} for {prompt_name}")
    session.close()


def get_conversations():
    conversation_dir = os.path.join("conversations")
    if os.path.exists(conversation_dir):
        conversations = os.listdir(conversation_dir)
        return [conversation.split(".")[0] for conversation in conversations]
    return []


def get_conversation(conversation_name):
    history = {"interactions": []}
    try:
        history_file = os.path.join("conversations", f"{conversation_name}.yaml")
        if os.path.exists(history_file):
            with open(history_file, "r") as file:
                history = yaml.safe_load(file)
    except:
        history = {"interactions": []}
    return history


def import_conversations(user=DEFAULT_USER):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id
    conversations = get_conversations()
    for conversation_name in conversations:
        conversation = get_conversation(conversation_name=conversation_name)
        if not conversation:
            logging.info(f"Conversation '{conversation_name}' is empty, skipping.")
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
            logging.info(f"Imported conversation: {conversation_name}")
    session.close()


def import_providers():
    session = get_session()
    providers = get_providers()
    for provider_name in providers:
        provider_options = get_provider_options(provider_name)
        provider = session.query(Provider).filter_by(name=provider_name).one_or_none()
        if provider:
            logging.info(f"Updating provider: {provider_name}")
        else:
            provider = Provider(name=provider_name)
            session.add(provider)
            logging.info(f"Imported provider: {provider_name}")
            session.commit()

        for option_name, option_value in provider_options.items():
            provider_setting = (
                session.query(ProviderSetting)
                .filter_by(provider_id=provider.id, name=option_name)
                .one_or_none()
            )
            if provider_setting:
                provider_setting.value = str(option_value)
                logging.info(
                    f"Updating provider setting: {option_name} for provider: {provider_name}"
                )
            else:
                provider_setting = ProviderSetting(
                    provider_id=provider.id,
                    name=option_name,
                    value=str(option_value),
                )
                session.add(provider_setting)
                logging.info(
                    f"Imported provider setting: {option_name} for provider: {provider_name}"
                )
    session.commit()
    session.close()


def import_all_data():
    session = get_session()
    user_count = session.query(User).count()
    if user_count == 0:
        # Create the default user
        logging.info("Creating default admin user...")
        user = User(email=DEFAULT_USER, admin=True)
        session.add(user)
        session.commit()
        logging.info("Default user created.")
        logging.info("Importing providers...")
        import_providers()
        logging.info("Importing extensions...")
        import_extensions()
        logging.info("Importing prompts...")
        import_prompts()
        logging.info("Importing agents...")
        import_agents()
        logging.info("Importing chains...")
        import_chains()
        logging.info("Imports complete.")
    session.close()
