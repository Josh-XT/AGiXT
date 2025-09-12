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
    AgentCommand,
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

    # Create extension database tables during seed import
    create_extension_tables()

    session = get_session()

    # Clean up orphaned agent command references before importing
    logging.info("Checking for orphaned agent command references...")
    try:
        # Build a map of currently available commands
        current_command_map = {}  # command_name -> extension_name
        for extension_data in extensions_data:
            extension_name = extension_data["extension_name"]
            for command in extension_data.get("commands", []):
                command_name = command["friendly_name"]
                current_command_map[command_name.lower()] = extension_name

        # Find agent commands that reference non-existent or moved commands
        orphaned_count = 0
        updated_count = 0

        all_agent_commands = (
            session.query(AgentCommand).join(Command).join(Extension).all()
        )

        for agent_command in all_agent_commands:
            command_name = agent_command.command.name.lower()
            current_extension = agent_command.command.extension.name

            if command_name in current_command_map:
                correct_extension = current_command_map[command_name]

                # Check if command is in wrong extension (moved or extension renamed)
                if correct_extension.lower() != current_extension.lower():
                    # Find the correct extension and command
                    new_ext = (
                        session.query(Extension)
                        .filter(Extension.name.ilike(correct_extension))
                        .first()
                    )

                    if new_ext:
                        # Find or create the command in the correct extension
                        new_command = (
                            session.query(Command)
                            .filter_by(
                                extension_id=new_ext.id, name=agent_command.command.name
                            )
                            .first()
                        )

                        if not new_command:
                            new_command = Command(
                                extension_id=new_ext.id, name=agent_command.command.name
                            )
                            session.add(new_command)
                            session.flush()

                        # Check if agent already has reference to correct command
                        existing_ref = (
                            session.query(AgentCommand)
                            .filter(
                                AgentCommand.agent_id == agent_command.agent_id,
                                AgentCommand.command_id == new_command.id,
                            )
                            .first()
                        )

                        if existing_ref:
                            # Merge - keep enabled if either was enabled
                            if agent_command.state:
                                existing_ref.state = True
                            session.delete(agent_command)
                        else:
                            # Update reference to correct command
                            agent_command.command_id = new_command.id

                        updated_count += 1
                        logging.info(
                            f"  Fixed reference for '{agent_command.command.name}' from '{current_extension}' to '{correct_extension}'"
                        )
            else:
                # Command no longer exists - remove the reference
                session.delete(agent_command)
                orphaned_count += 1
                logging.info(
                    f"  Removed orphaned reference to '{agent_command.command.name}' in '{current_extension}'"
                )

        if updated_count > 0 or orphaned_count > 0:
            logging.info(
                f"Updated {updated_count} agent command references and removed {orphaned_count} orphaned references"
            )

    except Exception as e:
        logging.error(f"Error cleaning up orphaned agent commands: {e}")

    # Get existing extensions
    existing_extensions = session.query(Extension).all()

    # Process each extension
    for extension_data in extensions_data:
        extension_name = extension_data["extension_name"]
        description = extension_data.get("description", "")

        # Find or create extension - also check for potential renames
        extension = session.query(Extension).filter_by(name=extension_name).first()

        # If extension doesn't exist by exact name, check if it might have been renamed
        # by looking for extensions with similar command sets
        if not extension:
            current_commands = set(
                cmd["friendly_name"].lower()
                for cmd in extension_data.get("commands", [])
            )

            # Look for existing extensions that have significant command overlap
            for existing_ext in existing_extensions:
                existing_commands = set(
                    cmd.name.lower() for cmd in existing_ext.commands
                )

                # Check for significant overlap (at least 50% of commands match)
                if (
                    current_commands
                    and len(current_commands & existing_commands)
                    / len(current_commands)
                    >= 0.5
                ):
                    logging.info(
                        f"Extension '{existing_ext.name}' appears to have been renamed to '{extension_name}' (command overlap detected)"
                    )

                    # Update the extension name
                    old_name = existing_ext.name
                    existing_ext.name = extension_name
                    existing_ext.description = description
                    extension = existing_ext
                    logging.info(
                        f"Renamed extension from '{old_name}' to '{extension_name}'"
                    )
                    break

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

                # Check if this command exists in a different extension (moved command)
                existing_in_other_extension = (
                    session.query(Command)
                    .join(Extension)
                    .filter(Command.name == command_name, Extension.id != extension.id)
                    .first()
                )

                if existing_in_other_extension:
                    logging.info(
                        f"Command '{command_name}' found in extension '{existing_in_other_extension.extension.name}', moving to '{extension_name}'"
                    )

                    # Find or create command in current extension
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
                        logging.info(f"Created new command entry: {command_name}")

                    # Update all agent command references from old to new
                    agent_commands = (
                        session.query(AgentCommand)
                        .filter(
                            AgentCommand.command_id == existing_in_other_extension.id
                        )
                        .all()
                    )

                    for agent_command in agent_commands:
                        # Check if agent already has a reference to the new command
                        existing_ref = (
                            session.query(AgentCommand)
                            .filter(
                                AgentCommand.agent_id == agent_command.agent_id,
                                AgentCommand.command_id == command.id,
                            )
                            .first()
                        )

                        if existing_ref:
                            # Merge - keep enabled if either was enabled
                            if agent_command.state:
                                existing_ref.state = True
                            session.delete(agent_command)
                            logging.info(
                                f"  Merged agent command reference for agent {agent_command.agent_id}"
                            )
                        else:
                            # Update to point to new command
                            agent_command.command_id = command.id
                            logging.info(
                                f"  Updated agent command reference for agent {agent_command.agent_id}"
                            )

                    # Skip deleting the old command for now to avoid foreign key issues
                    # The important part (moving agent references) is done
                    # The old command entry will be cleaned up in a future import or manual cleanup
                    logging.info(
                        f"  Moved agent references from old '{command_name}' entry (will clean up old entry later)"
                    )

                else:
                    # Normal case - find or create command in this extension
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

        # Only delete commands that are truly obsolete
        # Commands should only be deleted if their extension no longer exists
        # or if we're certain the extension no longer provides this command
        imported_command_names = [
            command_data["friendly_name"]
            for command_data in extension_data.get("commands", [])
        ]

        # We should be very conservative about deleting commands since agents depend on them
        # Only delete if we have a confident list of current commands AND the command is missing
        if (
            len(imported_command_names) > 0
        ):  # Only if we successfully discovered commands
            for existing_command in existing_commands:
                if existing_command.name not in imported_command_names:
                    # Log but don't auto-delete - require manual intervention for safety
                    logging.warning(
                        f"Command '{existing_command.name}' exists in DB but not found in extension '{extension_name}' - preserving for agent compatibility"
                    )
                    # Uncomment the next lines only if you want to enable deletion:
                    # session.delete(existing_command)
                    # logging.info(f"Deleted obsolete command: {existing_command.name}")
        else:
            # If no commands were discovered, preserve all existing ones
            logging.info(
                f"No commands discovered for extension '{extension_name}', preserving {len(existing_commands)} existing commands"
            )

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

    # Only delete extensions that we're certain no longer exist
    # Be very conservative about extension deletion since commands depend on them
    imported_extension_names = [
        extension_data["extension_name"] for extension_data in extensions_data
    ]

    if (
        len(imported_extension_names) > 0
    ):  # Only if we successfully discovered extensions
        for existing_extension in existing_extensions:
            if existing_extension.name not in imported_extension_names:
                # Log but don't auto-delete extensions - they may be from hub imports
                logging.warning(
                    f"Extension '{existing_extension.name}' exists in DB but not found in current scan - preserving for safety"
                )
                # Uncomment the next lines only if you want to enable deletion:
                # session.delete(existing_extension)
                # logging.info(f"Deleted extension: {existing_extension.name}")
    else:
        logging.warning(
            "No extensions discovered during import - preserving all existing extensions"
        )

    try:
        session.commit()
        logging.info("Extension import completed successfully")

    except Exception as e:
        session.rollback()
        logging.error(f"Error importing extensions: {str(e)}")
        raise
    finally:
        session.close()


def create_extension_tables():
    """Create database tables for extensions that have them"""
    import importlib
    import os
    import glob
    from DB import ExtensionDatabaseMixin, engine
    from ExtensionsHub import (
        find_extension_files,
        import_extension_module,
        get_extension_class_name,
    )
    from Extensions import Extensions

    logging.info("Creating extension database tables...")

    # Get all extension files
    try:
        extension_files = find_extension_files()
    except Exception as e:
        logging.error(f"Error finding extension files: {e}")
        return

    created_tables = []
    for extension_file in extension_files:
        try:
            # Import the extension module
            module = import_extension_module(extension_file)
            if module is None:
                continue

            # Get the expected class name
            class_name = get_extension_class_name(os.path.basename(extension_file))

            # Check if the class exists and inherits from both Extensions and ExtensionDatabaseMixin
            if (
                hasattr(module, class_name)
                and issubclass(getattr(module, class_name), Extensions)
                and issubclass(getattr(module, class_name), ExtensionDatabaseMixin)
            ):

                extension_class = getattr(module, class_name)

                # Check if the extension has database models
                if (
                    hasattr(extension_class, "extension_models")
                    and extension_class.extension_models
                ):
                    logging.info(f"Creating tables for extension: {class_name}")

                    # Create tables for this extension
                    for model in extension_class.extension_models:
                        try:
                            model.__table__.create(engine, checkfirst=True)
                            table_name = model.__tablename__
                            created_tables.append(table_name)
                            logging.info(f"Created table: {table_name}")
                        except Exception as e:
                            logging.error(
                                f"Error creating table {model.__tablename__}: {e}"
                            )

                    # Register the models
                    extension_class.register_models()

        except Exception as e:
            logging.debug(f"Could not process extension {extension_file}: {e}")

    if created_tables:
        logging.info(
            f"Successfully created {len(created_tables)} extension tables: {', '.join(created_tables)}"
        )
    else:
        logging.info("No extension tables needed to be created")


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


def cleanup_orphaned_data():
    """
    Manually clean up truly orphaned commands and extensions.
    This should be called manually when you're certain that extensions/commands
    should be removed (e.g., after permanently removing extension files).
    """
    import os
    from Extensions import Extensions
    from ExtensionsHub import find_extension_files, get_extension_class_name

    session = get_session()

    try:
        # Get currently available extensions
        ext = Extensions()
        available_extensions_data = ext.get_extensions()
        available_extension_names = {
            ext_data["extension_name"] for ext_data in available_extensions_data
        }

        if not available_extension_names:
            logging.warning(
                "No extensions discovered - aborting cleanup to prevent accidental deletion"
            )
            return

        # Find truly orphaned extensions (those not found in file system)
        orphaned_extensions = []
        all_extensions = session.query(Extension).all()

        for db_extension in all_extensions:
            if db_extension.name not in available_extension_names:
                # Double-check by trying to find the extension file
                extension_files = find_extension_files()
                found = False
                for file_path in extension_files:
                    expected_name = get_extension_class_name(
                        os.path.basename(file_path)
                    )
                    if (
                        expected_name.lower().replace("_", " ")
                        == db_extension.name.lower()
                    ):
                        found = True
                        break

                if not found:
                    orphaned_extensions.append(db_extension)

        if orphaned_extensions:
            logging.info(f"Found {len(orphaned_extensions)} truly orphaned extensions")
            for ext in orphaned_extensions:
                # This will cascade delete commands due to foreign key relationships
                session.delete(ext)
                logging.info(f"Deleted orphaned extension: {ext.name}")

        session.commit()
        logging.info("Orphaned data cleanup completed")

    except Exception as e:
        session.rollback()
        logging.error(f"Error during orphaned data cleanup: {e}")
    finally:
        session.close()


def import_all_data():
    # Ensure default user exists
    ensure_default_user()

    # Initialize extensions hub first to clone external extensions
    logging.info("Initializing extensions hub...")
    try:
        from ExtensionsHub import ExtensionsHub

        hub = ExtensionsHub()
        # Use the synchronous version to avoid event loop conflicts
        hub_success = hub.clone_or_update_hub_sync()

        # If hub was successful, invalidate extension cache to force rediscovery
        if hub_success:
            from Extensions import invalidate_extension_cache

            invalidate_extension_cache()
            logging.info("Extension cache invalidated after hub update")
    except Exception as e:
        logging.warning(f"Failed to initialize extensions hub: {e}")

    # Import extensions BEFORE providers to ensure all extensions are available
    logging.info("Importing extensions...")
    import_extensions()

    # Import providers after extensions
    logging.info("Importing providers...")
    import_providers()

    logging.info("Importing prompts...")
    import_prompts()
    # logging.info("Importing agents...")
    # import_agents()
    # logging.info("Importing chains...")
    # import_chains()

    # Register extension routers after all extensions are imported
    # This ensures hub extensions are available for router registration
    logging.info("Registering extension routers...")
    try:
        from app import register_extension_routers

        register_extension_routers()
    except Exception as e:
        logging.warning(f"Failed to register extension routers: {e}")

    logging.info("Imports complete.")
