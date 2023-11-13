from typing import List
from Extensions import Extensions
import os
import subprocess
from safeexecute import execute_python_code
import logging
import re


class file_system(Extensions):
    def __init__(
        self,
        WORKING_DIRECTORY: str = "./WORKSPACE",
        WORKING_DIRECTORY_RESTRICTED: bool = True,
        **kwargs,
    ):
        self.WORKING_DIRECTORY = WORKING_DIRECTORY
        self.WORKING_DIRECTORY_RESTRICTED = WORKING_DIRECTORY_RESTRICTED
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
        self.WORKING_DIRECTORY = WORKING_DIRECTORY

    async def execute_python_file(self, file: str):
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

    def safe_join(self, base: str, paths) -> str:
        if "/path/to/" in paths:
            paths = paths.replace("/path/to/", "")
        if str(self.WORKING_DIRECTORY_RESTRICTED).lower() == "true":
            new_path = os.path.normpath(os.path.join(base, *paths.split("/")))
            if not os.path.exists(new_path):
                if "." not in new_path:
                    os.makedirs(new_path)
        else:
            new_path = os.path.normpath(os.path.join("/", *paths))
            if not os.path.exists(new_path):
                os.makedirs(new_path)
        return new_path

    async def read_file(self, filename: str) -> str:
        try:
            filepath = self.safe_join(base=self.WORKING_DIRECTORY, paths=filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except Exception as e:
            return f"Error: {str(e)}"

    async def write_to_file(self, filename: str, text: str) -> str:
        try:
            filepath = self.safe_join(base=self.WORKING_DIRECTORY, paths=filename)
            directory = os.path.dirname(filepath)
            if not os.path.exists(directory):
                os.makedirs(directory)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            return "File written to successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    async def append_to_file(self, filename: str, text: str) -> str:
        try:
            filepath = self.safe_join(base=self.WORKING_DIRECTORY, paths=filename)
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
        try:
            filepath = self.safe_join(base=self.WORKING_DIRECTORY, paths=filename)
            os.remove(filepath)
            return "File deleted successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    async def search_files(self, directory: str) -> List[str]:
        found_files = []

        if directory in {"", "/"}:
            search_directory = self.WORKING_DIRECTORY
        else:
            search_directory = self.safe_join(
                base=self.WORKING_DIRECTORY, paths=directory
            )

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
        if indents == 1:
            indent = "    "
        else:
            indent = "    " * indents
        lines = string.split("\n")
        indented_lines = [(indent + line) for line in lines]
        indented_string = "\n".join(indented_lines)
        return indented_string

    async def generate_commands_dict(self, python_file_content):
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
