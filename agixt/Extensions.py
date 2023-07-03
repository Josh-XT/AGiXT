import importlib
import os
import glob
from inspect import signature, Parameter
import logging
import inspect
from DBConnection import (
    session,
    Extension,
    Command,
    Argument,
    Setting,
)


def import_extensions():
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


class Extensions:
    def __init__(self, agent_config=None, load_commands_flag: bool = True):
        self.agent_config = agent_config
        if load_commands_flag:
            self.commands = self.load_commands()
        else:
            self.commands = []
        if agent_config != None:
            if self.agent_config["commands"] == None:
                self.agent_config["commands"] = {}
            self.available_commands = self.get_available_commands()

    def get_available_commands(self):
        if self.commands == []:
            return []
        available_commands = []
        for command in self.commands:
            friendly_name, command_module, command_name, command_args = command
            if (
                "commands" in self.agent_config
                and friendly_name in self.agent_config["commands"]
            ):
                if (
                    self.agent_config["commands"][friendly_name] == "true"
                    or self.agent_config["commands"][friendly_name] == True
                ):
                    # Add command to list of commands to return
                    available_commands.append(
                        {
                            "friendly_name": friendly_name,
                            "name": command_name,
                            "args": command_args,
                            "enabled": True,
                        }
                    )
        return available_commands

    def get_enabled_commands(self):
        enabled_commands = []
        for command in self.available_commands:
            if command["enabled"]:
                enabled_commands.append(command)
        return enabled_commands

    def get_command_args(self, command_name: str):
        extensions = self.get_extensions()
        for extension in extensions:
            for command in extension["commands"]:
                if command["friendly_name"] == command_name:
                    return command["command_args"]
        return {}

    def load_commands(self):
        try:
            settings = self.agent_config["settings"]
        except:
            settings = {}
        commands = []
        command_files = glob.glob("extensions/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            module = importlib.import_module(f"extensions.{module_name}")
            if issubclass(getattr(module, module_name), Extensions):
                command_class = getattr(module, module_name)(**settings)
                if hasattr(command_class, "commands"):
                    for (
                        command_name,
                        command_function,
                    ) in command_class.commands.items():
                        params = self.get_command_params(command_function)
                        # Store the module along with the function name
                        commands.append(
                            (
                                command_name,
                                getattr(module, module_name),
                                command_function.__name__,
                                params,
                            )
                        )
        # Return the commands list
        logging.debug(f"loaded commands: {commands}")
        return commands

    def get_extension_settings(self):
        settings = {}
        command_files = glob.glob("extensions/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            module = importlib.import_module(f"extensions.{module_name}")
            if issubclass(getattr(module, module_name), Extensions):
                command_class = getattr(module, module_name)()
                params = self.get_command_params(command_class.__init__)
                # Remove self and kwargs from params
                if "self" in params:
                    del params["self"]
                if "kwargs" in params:
                    del params["kwargs"]
                if params != {}:
                    settings[module_name] = params
        return settings

    def find_command(self, command_name: str):
        for name, module, function_name, params in self.commands:
            if name == command_name:
                command_function = getattr(module, function_name)
                return command_function, module, params  # Updated return statement
        return None, None, None  # Updated return statement

    def get_commands_list(self):
        self.commands = self.load_commands()
        commands_list = [command_name for command_name, _, _ in self.commands]
        return commands_list

    async def execute_command(self, command_name: str, command_args: dict = None):
        command_function, module, params = self.find_command(command_name=command_name)
        logging.info(
            f"Executing command: {command_name} with args: {command_args}. Command Function: {command_function}"
        )
        if command_function is None:
            logging.error(f"Command {command_name} not found")
            return False
        for param in params:
            if param not in command_args:
                if param != "self" and param != "kwargs":
                    command_args[param] = None
        args = command_args.copy()
        for param in command_args:
            if param not in params:
                del args[param]
        try:
            output = await getattr(module(), command_function.__name__)(**args)
        except Exception as e:
            output = f"Error: {str(e)}"
        logging.info(f"Command Output: {output}")
        return output

    def get_command_params(self, func):
        params = {}
        sig = signature(func)
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.default == Parameter.empty:
                params[name] = ""
            else:
                params[name] = param.default
        return params

    def get_extensions(self):
        commands = []
        command_files = glob.glob("extensions/*.py")
        for command_file in command_files:
            module_name = os.path.splitext(os.path.basename(command_file))[0]
            module = importlib.import_module(f"extensions.{module_name}")
            command_class = getattr(module, module_name.lower())()
            extension_name = command_file.split("/")[-1].split(".")[0]
            extension_name = extension_name.replace("_", " ").title()
            constructor = inspect.signature(command_class.__init__)
            params = constructor.parameters
            extension_settings = [
                name for name in params if name != "self" and name != "kwargs"
            ]
            extension_commands = []
            if hasattr(command_class, "commands"):
                try:
                    for (
                        command_name,
                        command_function,
                    ) in command_class.commands.items():
                        params = self.get_command_params(command_function)
                        extension_commands.append(
                            {
                                "friendly_name": command_name,
                                "command_name": command_function.__name__,
                                "command_args": params,
                            }
                        )
                except Exception as e:
                    logging.error(f"Error getting commands: {e}")
            commands.append(
                {
                    "extension_name": extension_name,
                    "description": extension_name,
                    "settings": extension_settings,
                    "commands": extension_commands,
                }
            )
        return commands
