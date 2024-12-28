from typing import List
from Extensions import Extensions
import os
import subprocess
from safeexecute import execute_python_code
import logging
import re


class file_system(Extensions):
    """
    The File System extension enables agents to interact with the file system in their workspace.
    """

    def __init__(
        self,
        **kwargs,
    ):
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.WORKING_DIRECTORY_RESTRICTED = True
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)
        self.commands = {
            "Write to File": self.write_to_file,
            "Read File": self.read_file,
            "Search Files": self.search_files,
            "Append to File": self.append_to_file,
            "Execute Python File": self.execute_python_file,
            "Delete File": self.delete_file,
            "Execute Shell": self.execute_shell,
            "Indent String for Python Code": self.indent_string,
            "Generate Commands Dictionary": self.generate_commands_dict,
        }

    async def execute_python_file(self, file: str):
        """
        Execute a Python file in the workspace

        Args:
        file (str): The name of the Python file to execute

        Returns:
        str: The output of the Python file
        """
        logging.info(f"Executing file '{file}' in workspace '{self.WORKING_DIRECTORY}'")

        if not file.endswith(".py"):
            return "Error: Invalid file type. Only .py files are allowed."

        file_path = os.path.join(self.WORKING_DIRECTORY, file)

        if not os.path.isfile(file_path):
            return f"Error: File '{file}' does not exist."

        if self.we_are_running_in_a_docker_container():
            result = subprocess.run(
                f"python {file_path}", capture_output=True, encoding="utf8", shell=True
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error: {result.stderr}"
        with open(file_path, "r") as f:
            code = f.read()
        return execute_python_code(code=code, working_directory=self.WORKING_DIRECTORY)

    async def execute_shell(self, command_line: str) -> str:
        """
        Execute a shell command

        Args:
        command_line (str): The shell command to execute

        Returns:
        str: The output of the shell command
        """
        current_dir = os.getcwd()
        os.chdir(current_dir)
        logging.info(
            f"Executing command '{command_line}' in working directory '{os.getcwd()}'"
        )
        result = subprocess.run(command_line, capture_output=True, shell=True)
        output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

        os.chdir(current_dir)

        return output

    @staticmethod
    def we_are_running_in_a_docker_container() -> bool:
        return os.path.exists("/.dockerenv")

    def safe_join(self, paths) -> str:
        """
        Safely join paths together

        Args:
        paths (str): The paths to join

        Returns:
        str: The joined path
        """
        if "/path/to/" in paths:
            paths = paths.replace("/path/to/", "")
        new_path = os.path.normpath(
            os.path.join(self.WORKING_DIRECTORY, *paths.split("/"))
        )
        path_dir = os.path.dirname(new_path)
        os.makedirs(path_dir, exist_ok=True)
        return new_path

    async def read_file(self, filename: str) -> str:
        """
        Read a file in the workspace

        Args:
        filename (str): The name of the file to read

        Returns:
        str: The content of the file
        """
        try:
            filepath = self.safe_join(filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except Exception as e:
            return f"Error: {str(e)}"

    async def write_to_file(self, filename: str, text: str) -> str:
        """
        Write text to a file in the workspace

        Args:
        filename (str): The name of the file to write to
        text (str): The text to write to the file

        Returns:
        str: The status of the write operation
        """
        try:
            filepath = self.safe_join(filename)
            directory = os.path.dirname(filepath)
            if not os.path.exists(directory):
                os.makedirs(directory)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            return "File written to successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    async def append_to_file(self, filename: str, text: str) -> str:
        """
        Append text to a file in the workspace

        Args:
        filename (str): The name of the file to append to
        text (str): The text to append to the file

        Returns:
        str: The status of the append operation
        """
        try:
            filepath = self.safe_join(filename)
            if not os.path.exists(filepath):
                with open(filepath, "w") as f:
                    f.write(text)
            else:
                with open(filepath, "a") as f:
                    f.write(text)
            return "Text appended successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    async def delete_file(self, filename: str) -> str:
        """
        Delete a file in the workspace

        Args:
        filename (str): The name of the file to delete

        Returns:
        str: The status of the delete operation
        """
        try:
            filepath = self.safe_join(filename)
            os.remove(filepath)
            return "File deleted successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    async def search_files(self, directory: str) -> List[str]:
        """
        Search for files in the workspace

        Args:
        directory (str): The directory to search in

        Returns:
        List[str]: The list of files found
        """
        found_files = []

        if directory in {"", "/"}:
            search_directory = self.WORKING_DIRECTORY
        else:
            search_directory = self.safe_join(directory)

        for root, _, files in os.walk(search_directory):
            for file in files:
                if file.startswith("."):
                    continue
                relative_path = os.path.relpath(
                    os.path.join(root, file), self.WORKING_DIRECTORY
                )
                found_files.append(relative_path)

        return found_files

    async def indent_string(self, string: str, indents: int = 1):
        """
        Indent a string for Python code

        Args:
        string (str): The string to indent
        indents (int): The number of indents to add

        Returns:
        str: The indented string
        """
        try:
            indents = int(indents)
        except:
            indents = 1
        if indents == 1:
            indent = "    "
        else:
            indent = "    " * indents
        lines = string.split("\n")
        indented_lines = [(indent + line) for line in lines]
        indented_string = "\n".join(indented_lines)
        return indented_string

    async def generate_commands_dict(self, python_file_content):
        """
        Generate a dictionary of commands from a Python file

        Args:
        python_file_content (str): The content of the Python file

        Returns:
        str: The dictionary of commands
        """
        function_names = re.findall(r"async def (.*?)\(", python_file_content)
        commands_dict = {
            f_name.replace("_", " "): f"self.{f_name}" for f_name in function_names
        }
        commands_string = "self.commands = {"
        for key, value in commands_dict.items():
            commands_string += f' "{key.capitalize()}": {value},'
        commands_string = commands_string[:-1]
        commands_string += "}"
        return commands_string
