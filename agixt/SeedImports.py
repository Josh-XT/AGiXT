import os
import json
import logging
from DB import (
    get_session,
    Provider,
    ProviderSetting,
    Prompt,
    PromptCategory,
    Argument,
    Extension,
    Setting,
    Command,
    User,
    Agent,
)
from Providers import get_providers, get_provider_options
from Agent import add_agent
from Globals import getenv, DEFAULT_USER

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


def ensure_default_user():
    """Ensure default admin user exists"""
    session = get_session()
    user = session.query(User).filter_by(email=DEFAULT_USER).first()
    if not user:
        logging.info("Creating default admin user...")
        user = User(email=DEFAULT_USER, admin=True)
        session.add(user)
        session.commit()
        logging.info("Default user created.")
    session.close()
    return user


def import_agents(user=DEFAULT_USER):
    try:
        agents = [
            f.name
            for f in os.scandir("agents")
            if f.is_dir() and not f.name.startswith("__")
        ]
    except:
        return None
    session = get_session()
    for agent_name in agents:
        # Check if agent already exists
        agent_exists = session.query(Agent).filter_by(name=agent_name).first()
        if agent_exists:
            logging.info(f"Agent {agent_name} already exists, skipping...")
            continue

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
    session.close()


def import_extensions():
    import json
    from Extensions import Extensions

    ext = Extensions()
    extensions_data = ext.get_extensions()
    # Delete "AGiXT Chains"
    if "AGiXT Chains" in extensions_data:
        del extensions_data["AGiXT Chains"]
    if "Custom Automation" in extensions_data:
        del extensions_data["Custom Automation"]
    extension_settings_data = Extensions().get_extension_settings()
    session = get_session()

    # Get existing extensions
    existing_extensions = session.query(Extension).all()

    # Process each extension
    for extension_data in extensions_data:
        extension_name = extension_data["extension_name"]
        description = extension_data.get("description", "")

        # Find or create extension
        extension = session.query(Extension).filter_by(name=extension_name).first()
        if extension:
            extension.description = description
            logging.info(f"Updated extension: {extension_name}")
        else:
            extension = Extension(name=extension_name, description=description)
            session.add(extension)
            session.flush()
            logging.info(f"Imported extension: {extension_name}")

        # Get existing commands for this extension
        existing_commands = (
            session.query(Command).filter_by(extension_id=extension.id).all()
        )

        # Process commands for this extension
        if "commands" in extension_data:
            for command_data in extension_data["commands"]:
                if "friendly_name" not in command_data:
                    continue

                command_name = command_data["friendly_name"]
                command_description = command_data.get("description", "")

                # Find or create command
                command = (
                    session.query(Command)
                    .filter_by(extension_id=extension.id, name=command_name)
                    .first()
                )

                if not command:
                    command = Command(
                        extension_id=extension.id,
                        name=command_name,
                    )
                    session.add(command)
                    session.flush()
                    logging.info(f"Imported command: {command_name}")

                # Process command arguments if they exist
                if "command_args" in command_data:
                    for arg_name, arg_type in command_data["command_args"].items():
                        # Check if argument already exists
                        existing_arg = (
                            session.query(Argument)
                            .filter_by(command_id=command.id, name=arg_name)
                            .first()
                        )

                        if not existing_arg:
                            command_arg = Argument(
                                command_id=command.id,
                                name=arg_name,
                            )
                            session.add(command_arg)
                            logging.info(
                                f"Imported argument: {arg_name} for command: {command_name}"
                            )

        # Delete commands that no longer exist
        imported_command_names = [
            command_data["friendly_name"]
            for command_data in extension_data.get("commands", [])
        ]
        for existing_command in existing_commands:
            if existing_command.name not in imported_command_names:
                session.delete(existing_command)
                logging.info(f"Deleted command: {existing_command.name}")

    # Process extension settings
    for extension_name, settings in extension_settings_data.items():
        extension = session.query(Extension).filter_by(name=extension_name).first()
        if not extension:
            extension = Extension(name=extension_name)
            session.add(extension)
            session.flush()
            logging.info(f"Imported extension: {extension_name}")

        for setting_name, setting_value in settings.items():
            # Convert dictionary or list values to JSON strings
            if isinstance(setting_value, (dict, list)):
                setting_value = json.dumps(setting_value)
            else:
                setting_value = str(setting_value)

            # Find or update setting
            setting = (
                session.query(Setting)
                .filter_by(extension_id=extension.id, name=setting_name)
                .first()
            )

            if setting:
                setting.value = setting_value
                logging.info(
                    f"Updated setting: {setting_name} for extension: {extension_name}"
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

    # Delete extensions that no longer exist
    imported_extension_names = [
        extension_data["extension_name"] for extension_data in extensions_data
    ]
    for existing_extension in existing_extensions:
        if existing_extension.name not in imported_extension_names:
            session.delete(existing_extension)
            logging.info(f"Deleted extension: {existing_extension.name}")

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Error importing extensions: {str(e)}")
        raise
    finally:
        session.close()


def check_and_import_chain_steps(chain_name, chain_data, session, user_id=None):
    """
    Helper function to check if a chain exists but has no steps, and imports steps if needed.
    Will check both the specified user's chains and global/default user chains.

    Args:
        chain_name (str): Name of the chain
        chain_data (dict): Chain data containing steps
        session (Session): Database session
        user_id (str, optional): User ID. If None, will only check default user

    Returns:
        bool: True if steps were imported, False if chain already had steps
    """
    from DB import (
        Chain as ChainDB,
        ChainStep,
        Agent,
        Command,
        Prompt,
        Argument,
        ChainStepArgument,
    )

    # Get default user for global chains
    default_user = session.query(User).filter_by(email=DEFAULT_USER).first()
    default_user_id = default_user.id if default_user else None

    # Check both user-specific and default user chains
    chains_to_check = []

    # Add default user chain
    default_chain = (
        session.query(ChainDB)
        .filter_by(name=chain_name, user_id=default_user_id)
        .first()
    )
    if default_chain:
        chains_to_check.append(default_chain)

    # Add user-specific chain if user_id provided
    if user_id and user_id != default_user_id:
        user_chain = (
            session.query(ChainDB).filter_by(name=chain_name, user_id=user_id).first()
        )
        if user_chain:
            chains_to_check.append(user_chain)

    if not chains_to_check:
        return False

    steps_imported = False

    # Process each chain that needs steps
    for existing_chain in chains_to_check:
        # Check if chain has steps
        existing_steps = (
            session.query(ChainStep).filter_by(chain_id=existing_chain.id).count()
        )
        if existing_steps > 0:
            continue

    # Import steps for existing chain
    steps = chain_data.get("steps", [])
    for step_data in steps:
        agent_name = step_data["agent_name"]
        agent = session.query(Agent).filter_by(name=agent_name, user_id=user_id).first()
        if not agent:
            # Try getting default user's agent
            default_user = session.query(User).filter_by(email=DEFAULT_USER).first()
            agent = (
                session.query(Agent)
                .filter_by(name=agent_name, user_id=default_user.id)
                .first()
            )
            if not agent:
                continue

        prompt = step_data["prompt"]
        prompt_type = step_data["prompt_type"].lower()

        # Handle different prompt types
        target_id = None
        if prompt_type == "prompt":
            prompt_category = prompt.get("prompt_category", "Default")
            target = (
                session.query(Prompt)
                .filter(
                    Prompt.name == prompt["prompt_name"],
                    Prompt.user_id == user_id,
                    Prompt.prompt_category.has(name=prompt_category),
                )
                .first()
            )
            if target:
                target_id = target.id
        elif prompt_type == "chain":
            chain_key = "chain_name" if "chain_name" in prompt else "chain"
            target = (
                session.query(ChainDB)
                .filter(
                    ChainDB.name == prompt[chain_key],
                    ChainDB.user_id == user_id,
                )
                .first()
            )
            if target:
                target_id = target.id
        elif prompt_type == "command":
            target = (
                session.query(Command).filter_by(name=prompt["command_name"]).first()
            )
            if target:
                target_id = target.id

        if target_id is None:
            continue

        # Create chain step
        chain_step = ChainStep(
            chain_id=existing_chain.id,
            step_number=step_data["step"],
            agent_id=agent.id,
            prompt_type=step_data["prompt_type"],
            prompt=prompt.get("prompt_name", ""),
            target_chain_id=target_id if prompt_type == "chain" else None,
            target_command_id=target_id if prompt_type == "command" else None,
            target_prompt_id=target_id if prompt_type == "prompt" else None,
        )
        session.add(chain_step)
        session.flush()

        # Handle arguments
        prompt_args = prompt.copy()
        if prompt_type == "prompt":
            del prompt_args["prompt_name"]
            if "prompt_category" in prompt_args:
                del prompt_args["prompt_category"]
        elif prompt_type == "command":
            del prompt_args["command_name"]
        elif prompt_type == "chain":
            if "chain_name" in prompt_args:
                del prompt_args["chain_name"]
            if "chain" in prompt_args:
                del prompt_args["chain"]

        for arg_name, arg_value in prompt_args.items():
            argument = session.query(Argument).filter_by(name=arg_name).first()
            if argument:
                chain_step_arg = ChainStepArgument(
                    chain_step_id=chain_step.id,
                    argument_id=argument.id,
                    value=str(arg_value),
                )
                session.add(chain_step_arg)

        steps_imported = True

    if steps_imported:
        session.commit()
    return steps_imported


# Modified import_chains function
def import_chains(user=DEFAULT_USER):
    """
    Import chains from JSON files, including updating existing chains that have no steps.
    Will handle both user-specific and global/default user chains.
    """
    chain_dir = os.path.abspath("chains")
    chain_files = [
        file
        for file in os.listdir(chain_dir)
        if os.path.isfile(os.path.join(chain_dir, file)) and file.endswith(".json")
    ]
    if not chain_files:
        logging.info("No JSON files found in chains directory.")
        return

    from Chain import Chain
    from DB import Chain as ChainDB, get_session, User

    chain_importer = Chain(user=user)
    session = get_session()

    # Get all users to process chains for
    users = session.query(User).all()

    failures = []
    for file in chain_files:
        chain_name = os.path.splitext(file)[0]
        file_path = os.path.join(chain_dir, file)

        try:
            with open(file_path, "r") as f:
                chain_data = json.load(f)

            # Process chain for default user first
            default_user = session.query(User).filter_by(email=DEFAULT_USER).first()
            if not default_user:
                raise Exception("Default User doesn't exist!")
            steps_imported = check_and_import_chain_steps(
                chain_name=chain_name,
                chain_data=chain_data,
                session=session,
                user_id=default_user.id,
            )

            # Then process for all other users
            for user_data in users:
                if user_data.email != DEFAULT_USER:
                    user_steps_imported = check_and_import_chain_steps(
                        chain_name=chain_name,
                        chain_data=chain_data,
                        session=session,
                        user_id=user_data.id,
                    )
                    steps_imported = steps_imported or user_steps_imported

            if steps_imported:
                logging.info(f"Imported steps for existing chain: {chain_name}")
            else:
                # If chain doesn't exist or already has steps, try normal import
                result = chain_importer.import_chain(chain_name, chain_data)
                if result:
                    logging.info(result)

        except Exception as e:
            logging.error(f"Error importing chain from '{file}': {str(e)}")
            failures.append(file)

    session.close()

    if failures:
        logging.error(f"Failed to import the following chains: {', '.join(failures)}")


def import_prompts(user=DEFAULT_USER):
    session = get_session()
    user_data = session.query(User).filter(User.email == user).first()
    user_id = user_data.id

    # Ensure default category exists
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

    for root, dirs, files in os.walk("prompts"):
        for file in files:
            prompt_category = None
            if root != "prompts":
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
                prompt_category = default_category

            prompt_name = os.path.splitext(file)[0]

            # Check if prompt already exists
            existing_prompt = (
                session.query(Prompt)
                .filter_by(
                    name=prompt_name,
                    prompt_category_id=prompt_category.id,
                    user_id=user_id,
                )
                .first()
            )

            if existing_prompt:
                logging.info(
                    f"Prompt {prompt_name} already exists in category {prompt_category.name}, skipping..."
                )
                continue

            with open(os.path.join(root, file), "r") as f:
                prompt_content = f.read()

            # Create new prompt
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

            # Add prompt arguments
            prompt_args = [
                word[1:-1]
                for word in prompt_content.split()
                if word.startswith("{") and word.endswith("}")
            ]

            for arg in prompt_args:
                if (
                    not session.query(Argument)
                    .filter_by(prompt_id=prompt.id, name=arg)
                    .first()
                ):
                    argument = Argument(
                        prompt_id=prompt.id,
                        name=arg,
                    )
                    session.add(argument)
                    logging.info(f"Imported prompt argument: {arg} for {prompt_name}")

            session.commit()

    session.close()


def import_providers():
    session = get_session()
    providers = get_providers()

    for provider_name in providers:
        provider_options = get_provider_options(provider_name)

        # Find or create provider
        provider = session.query(Provider).filter_by(name=provider_name).first()
        if not provider:
            provider = Provider(name=provider_name)
            session.add(provider)
            session.commit()
            logging.info(f"Imported provider: {provider_name}")

        # Update provider settings
        for option_name, option_value in provider_options.items():
            provider_setting = (
                session.query(ProviderSetting)
                .filter_by(provider_id=provider.id, name=option_name)
                .first()
            )

            if not provider_setting:
                provider_setting = ProviderSetting(
                    provider_id=provider.id,
                    name=option_name,
                    value=str(option_value),
                )
                session.add(provider_setting)
                logging.info(
                    f"Imported provider setting: {option_name} for provider: {provider_name}"
                )
            else:
                provider_setting.value = str(option_value)
                logging.info(
                    f"Updated provider setting: {option_name} for provider: {provider_name}"
                )

    session.commit()
    session.close()


def import_all_data():
    # Ensure default user exists
    ensure_default_user()

    # Import all data types
    logging.info("Importing providers...")
    import_providers()
    logging.info("Importing extensions...")
    import_extensions()
    logging.info("Importing prompts...")
    import_prompts()
    # logging.info("Importing agents...")
    # import_agents()
    # logging.info("Importing chains...")
    # import_chains()
    logging.info("Imports complete.")
