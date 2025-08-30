from typing import List, Optional, Dict, Any
from Extensions import Extensions
import os
import subprocess
from safeexecute import execute_python_code
import logging
import re
from pathlib import Path
import fnmatch


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
            "Search File Content": self.search_file_content,
            "Modify File": self.modify_file,
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

    async def read_file(
        self,
        filename: str,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
    ) -> str:
        """
        Read a file in the workspace, optionally reading only specific line ranges

        Args:
        filename (str): The name of the file to read
        line_start (Optional[int]): The starting line number (1-indexed). If None, starts from beginning
        line_end (Optional[int]): The ending line number (1-indexed, inclusive). If None, reads to end

        Returns:
        str: The content of the file or specified line range
        """
        try:
            filepath = self.safe_join(filename)

            # Read the entire file or specific lines
            with open(filepath, "r", encoding="utf-8") as f:
                if line_start is None and line_end is None:
                    # Read entire file
                    content = f.read()
                else:
                    # Read specific line range
                    lines = f.readlines()
                    total_lines = len(lines)

                    # Convert to 0-indexed and handle bounds
                    start_idx = 0 if line_start is None else max(0, line_start - 1)
                    end_idx = (
                        total_lines if line_end is None else min(total_lines, line_end)
                    )

                    # Extract the requested lines
                    selected_lines = lines[start_idx:end_idx]
                    content = "".join(selected_lines)

                    # Add line number information if reading a range
                    if line_start is not None or line_end is not None:
                        actual_start = start_idx + 1
                        actual_end = min(end_idx, total_lines)
                        header = f"Lines {actual_start}-{actual_end} of {total_lines} total lines:\n"
                        content = header + "=" * 40 + "\n" + content

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

    async def modify_file(self, filename: str, diff: str) -> str:
        """
        Modify a file using SEARCH/REPLACE blocks for precise changes.

        Args:
        filename (str): The name of the file to modify
        diff (str): One or more SEARCH/REPLACE blocks in the format:
            ------- SEARCH
            [exact content to find]
            =======
            [new content to replace with]
            +++++++ REPLACE

        Returns:
        str: The status of the modification operation
        """
        try:
            filepath = self.safe_join(filename)

            if not os.path.exists(filepath):
                return f"Error: File '{filename}' does not exist."

            # Read the current file content
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse the diff blocks
            diff_blocks = self._parse_diff_blocks(diff)

            if not diff_blocks:
                return "Error: No valid SEARCH/REPLACE blocks found in diff."

            # Apply each diff block
            modified_content = content
            replacements_made = []

            for i, block in enumerate(diff_blocks, 1):
                search_content = block["search"]
                replace_content = block["replace"]

                # Check if the search content exists in the file
                if search_content in modified_content:
                    # Replace only the first occurrence
                    modified_content = modified_content.replace(
                        search_content, replace_content, 1
                    )
                    replacements_made.append(f"Block {i}: Found and replaced")
                else:
                    # Try to provide helpful error message
                    lines = search_content.split("\n")
                    partial_match = False
                    for line in lines:
                        if line.strip() and line.strip() in modified_content:
                            partial_match = True
                            break

                    if partial_match:
                        replacements_made.append(
                            f"Block {i}: Failed - partial match found, check exact formatting"
                        )
                    else:
                        replacements_made.append(
                            f"Block {i}: Failed - search content not found"
                        )

            # Write the modified content back to the file
            if any("Found and replaced" in r for r in replacements_made):
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(modified_content)

                result = "File modified successfully.\n"
                result += "Replacement results:\n"
                result += "\n".join(replacements_made)
                return result
            else:
                return "Error: No replacements were made.\n" + "\n".join(
                    replacements_made
                )

        except Exception as e:
            return f"Error: {str(e)}"

    def _parse_diff_blocks(self, diff: str) -> List[Dict[str, str]]:
        """
        Parse SEARCH/REPLACE blocks from a diff string.

        Args:
        diff (str): The diff string containing SEARCH/REPLACE blocks

        Returns:
        List[Dict[str, str]]: List of parsed diff blocks with 'search' and 'replace' keys
        """
        blocks = []

        # Split by the SEARCH marker
        parts = re.split(r"-{7}\s*SEARCH\s*\n", diff)

        for part in parts[1:]:  # Skip the first empty part
            # Split by the separator and REPLACE marker
            if "=======" in part and "+++++++ REPLACE" in part:
                # Find the positions of the separators
                separator_match = re.search(r"\n={7}\s*\n", part)
                replace_match = re.search(r"\n\+{7}\s*REPLACE\s*(?:\n|$)", part)

                if separator_match and replace_match:
                    search_content = part[: separator_match.start()]
                    replace_content = part[
                        separator_match.end() : replace_match.start()
                    ]

                    blocks.append(
                        {"search": search_content, "replace": replace_content}
                    )

        return blocks

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

    async def search_files(
        self,
        directory: str,
        pattern: Optional[str] = None,
        file_type: Optional[str] = None,
        recursive: bool = True,
    ) -> List[str]:
        """
        Search for files in the workspace with optional filtering

        Args:
        directory (str): The directory to search in
        pattern (Optional[str]): Glob pattern to match file names (e.g., "*.py", "test_*.js")
        file_type (Optional[str]): File extension to filter by (e.g., ".py", ".txt")
        recursive (bool): Whether to search recursively in subdirectories (default: True)

        Returns:
        List[str]: The list of files found matching the criteria
        """
        found_files = []

        if directory in {"", "/"}:
            search_directory = self.WORKING_DIRECTORY
        else:
            search_directory = self.safe_join(directory)

        # Prepare the file type filter
        if file_type and not file_type.startswith("."):
            file_type = "." + file_type

        # Use os.walk for recursive search or os.listdir for non-recursive
        if recursive:
            for root, _, files in os.walk(search_directory):
                for file in files:
                    if file.startswith("."):
                        continue

                    # Apply pattern matching if specified
                    if pattern and not fnmatch.fnmatch(file, pattern):
                        continue

                    # Apply file type filter if specified
                    if file_type and not file.endswith(file_type):
                        continue

                    relative_path = os.path.relpath(
                        os.path.join(root, file), self.WORKING_DIRECTORY
                    )
                    found_files.append(relative_path)
        else:
            # Non-recursive search
            try:
                files = os.listdir(search_directory)
                for file in files:
                    file_path = os.path.join(search_directory, file)
                    if os.path.isfile(file_path) and not file.startswith("."):
                        # Apply pattern matching if specified
                        if pattern and not fnmatch.fnmatch(file, pattern):
                            continue

                        # Apply file type filter if specified
                        if file_type and not file.endswith(file_type):
                            continue

                        relative_path = os.path.relpath(
                            file_path, self.WORKING_DIRECTORY
                        )
                        found_files.append(relative_path)
            except Exception as e:
                logging.error(f"Error listing directory: {str(e)}")

        return found_files

    async def search_file_content(
        self,
        directory: str,
        search_term: str,
        file_pattern: Optional[str] = None,
        case_sensitive: bool = False,
        max_results: int = 100,
    ) -> Dict[str, Any]:
        """
        Search for content within files in the workspace

        Args:
        directory (str): The directory to search in
        search_term (str): The text or regex pattern to search for
        file_pattern (Optional[str]): Glob pattern to filter files (e.g., "*.py")
        case_sensitive (bool): Whether the search should be case-sensitive (default: False)
        max_results (int): Maximum number of results to return (default: 100)

        Returns:
        Dict[str, Any]: Dictionary containing search results with file paths and matching lines
        """
        results = {"total_matches": 0, "files_searched": 0, "matches": []}

        if directory in {"", "/"}:
            search_directory = self.WORKING_DIRECTORY
        else:
            search_directory = self.safe_join(directory)

        # Compile the search pattern
        try:
            if case_sensitive:
                search_pattern = re.compile(search_term)
            else:
                search_pattern = re.compile(search_term, re.IGNORECASE)
        except re.error:
            # If regex is invalid, treat as literal string
            escaped_term = re.escape(search_term)
            if case_sensitive:
                search_pattern = re.compile(escaped_term)
            else:
                search_pattern = re.compile(escaped_term, re.IGNORECASE)

        # Search through files
        for root, _, files in os.walk(search_directory):
            for file in files:
                if file.startswith("."):
                    continue

                # Apply file pattern filter if specified
                if file_pattern and not fnmatch.fnmatch(file, file_pattern):
                    continue

                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, self.WORKING_DIRECTORY)

                # Skip binary files
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        results["files_searched"] += 1
                        lines = f.readlines()

                        file_matches = []
                        for line_num, line in enumerate(lines, 1):
                            if search_pattern.search(line):
                                # Get context (previous and next line)
                                context = {
                                    "line_number": line_num,
                                    "line": line.rstrip(),
                                    "context_before": (
                                        lines[line_num - 2].rstrip()
                                        if line_num > 1
                                        else None
                                    ),
                                    "context_after": (
                                        lines[line_num].rstrip()
                                        if line_num < len(lines)
                                        else None
                                    ),
                                }
                                file_matches.append(context)
                                results["total_matches"] += 1

                                if results["total_matches"] >= max_results:
                                    break

                        if file_matches:
                            results["matches"].append(
                                {"file": relative_path, "matches": file_matches}
                            )

                        if results["total_matches"] >= max_results:
                            results["truncated"] = True
                            return results

                except (UnicodeDecodeError, PermissionError) as e:
                    # Skip files that can't be read as text
                    logging.debug(f"Skipping file {relative_path}: {str(e)}")
                    continue

        return results

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
