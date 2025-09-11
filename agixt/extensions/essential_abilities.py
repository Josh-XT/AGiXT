import json
import os
import subprocess
import logging
import datetime
from typing import Optional
from Extensions import Extensions
from safeexecute import execute_python_code
from agixtsdk import AGiXTSDK
from Globals import getenv


class essential_abilities(Extensions):
    """
    The Essential Abilities extension provides core functionality for agents,
    including file system operations, data analysis, Python code execution,
    and other fundamental capabilities.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "Write to File": self.write_to_file,
            "Read File": self.read_file,
            "Search Files": self.search_files,
            "Search File Content": self.search_file_content,
            "Modify File": self.modify_file,
            "Execute Python File": self.execute_python_file,
            "Delete File": self.delete_file,
            "Execute Shell": self.execute_shell,
            "Run Data Analysis": self.run_data_analysis,
            "Ask for Help or Further Clarification to Complete Task": self.ask_for_help,
            "Execute Python Code": self.execute_python_code_internal,
            "Explain Chain": self.chain_to_mermaid,
            "Get Datetime": self.get_datetime,
            "Create Automation Chain": self.create_agixt_chain,
            "Modify Automation Chain": self.modify_chain,
            "Custom API Endpoint": self.custom_api,
            "Get Mindmap for task to break it down": self.get_mindmap,
        }
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.WORKING_DIRECTORY_RESTRICTED = True
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)

        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.conversation_id = (
            kwargs["conversation_id"] if "conversation_id" in kwargs else ""
        )
        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else AGiXTSDK(
                base_uri=getenv("AGIXT_URI"),
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
            )
        )

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

    @staticmethod
    def we_are_running_in_a_docker_container() -> bool:
        return os.path.exists("/.dockerenv")

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
                        header = f"Lines {actual_start}-{actual_end} of {total_lines} total lines:\\n"
                        content = header + "=" * 40 + "\\n" + content

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
        str: Success message
        """
        try:
            filepath = self.safe_join(filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            return f"File {filename} written successfully."
        except Exception as e:
            return f"Error writing file: {str(e)}"

    async def search_files(self, query: str) -> str:
        """
        Search for files in the workspace that match a pattern

        Args:
        query (str): The search pattern or filename

        Returns:
        str: List of matching files
        """
        import fnmatch

        matches = []
        try:
            for root, dirnames, filenames in os.walk(self.WORKING_DIRECTORY):
                for filename in fnmatch.filter(filenames, f"*{query}*"):
                    relative_path = os.path.relpath(
                        os.path.join(root, filename), self.WORKING_DIRECTORY
                    )
                    matches.append(relative_path)

            if matches:
                return f"Found {len(matches)} matching files:\\n" + "\\n".join(matches)
            else:
                return f"No files found matching pattern: {query}"
        except Exception as e:
            return f"Error searching files: {str(e)}"

    async def search_file_content(self, query: str, filename: str = "") -> str:
        """
        Search for content within files in the workspace

        Args:
        query (str): The text to search for
        filename (str): Optional specific file to search in

        Returns:
        str: Search results showing matching lines
        """
        import re

        matches = []
        try:
            if filename:
                # Search in specific file
                files_to_search = [filename]
            else:
                # Search in all text files
                files_to_search = []
                for root, dirs, files in os.walk(self.WORKING_DIRECTORY):
                    for file in files:
                        if file.endswith(
                            (
                                ".txt",
                                ".py",
                                ".md",
                                ".json",
                                ".yaml",
                                ".yml",
                                ".ini",
                                ".cfg",
                            )
                        ):
                            relative_path = os.path.relpath(
                                os.path.join(root, file), self.WORKING_DIRECTORY
                            )
                            files_to_search.append(relative_path)

            for file_path in files_to_search:
                try:
                    full_path = self.safe_join(file_path)
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()

                    for line_num, line in enumerate(lines, 1):
                        if query.lower() in line.lower():
                            matches.append(f"{file_path}:{line_num}: {line.strip()}")
                except:
                    continue

            if matches:
                return f"Found {len(matches)} matches:\\n" + "\\n".join(
                    matches[:20]
                )  # Limit to first 20 matches
            else:
                return f"No matches found for: {query}"
        except Exception as e:
            return f"Error searching file content: {str(e)}"

    async def modify_file(self, filename: str, old_text: str, new_text: str) -> str:
        """
        Modify a file by replacing old text with new text

        Args:
        filename (str): The name of the file to modify
        old_text (str): The text to replace
        new_text (str): The replacement text

        Returns:
        str: Success message
        """
        try:
            filepath = self.safe_join(filename)

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            if old_text not in content:
                return f"Error: Text '{old_text}' not found in file {filename}"

            modified_content = content.replace(old_text, new_text)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(modified_content)

            return f"File {filename} modified successfully."
        except Exception as e:
            return f"Error modifying file: {str(e)}"

    async def delete_file(self, filename: str) -> str:
        """
        Delete a file from the workspace

        Args:
        filename (str): The name of the file to delete

        Returns:
        str: Success message
        """
        try:
            filepath = self.safe_join(filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                return f"File {filename} deleted successfully."
            else:
                return f"Error: File {filename} does not exist."
        except Exception as e:
            return f"Error deleting file: {str(e)}"

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
        Execute a shell command in a sandboxed environment

        Args:
        command_line (str): The shell command to execute

        Returns:
        str: The output of the shell command
        """
        # Create Python code that will execute the shell command in a sandboxed environment
        sandboxed_code = f"""
import subprocess
import os

# Execute the command
result = subprocess.run(
    {repr(command_line)}, 
    capture_output=True, 
    shell=True,
    text=True,
    timeout=30  # Add timeout for safety
)

# Format output
output = "STDOUT:\\n"
if result.stdout:
    output += result.stdout
else:
    output += "(no output)"
    
output += "\\nSTDERR:\\n"
if result.stderr:
    output += result.stderr
else:
    output += "(no errors)"

output += f"\\nReturn Code: {{result.returncode}}"

print(output)
"""

        # Execute the code in a sandboxed environment
        try:
            result = execute_python_code(
                code=sandboxed_code, working_directory=self.WORKING_DIRECTORY
            )
            return result
        except Exception as e:
            return f"Error executing shell command in sandbox: {str(e)}"

    async def run_data_analysis(self, data: str, query: str):
        """
        Run data analysis on a dataset of any format, including analyzing and solving math problems, and more.
        This should be used if the user's input contains a math problem that the assistant must solve, this includes counting, arithmetic, algebra, geometry, calculus, statistics, and other math-related problems.
        If the assistant mentions a file name that was uploaded in the conversation under `data`, it will reference that file automatically to be injected into the data analysis process.

        With this command, the assistant has the capability to directly manipulate files, convert images, and perform a variety of other tasks. Here are some examples:

        - Image Description and Manipulation: the assistant can directly manipulate images, including zooming, cropping, color grading, and resolution enhancement. It can also convert images from one format to another.
        - QR Code Generation: the assistant can create QR codes for various purposes.
        - Project Management: the assistant can assist in creating Gantt charts and mapping out project steps.
        - Study Scheduling: the assistant can design optimized study schedules for exam preparation.
        - File Conversion: the assistant can directly convert files from one format to another, such as PDF to text or video to audio.
        - Mathematical Computation: the assistant can solve complex math equations and produce graphs.
        - Document Analysis: the assistant can analyze, summarize, or extract information from large documents.
        - Data Visualization: the assistant can analyze datasets, identify trends, and create various types of graphs.
        - Geolocation Visualization: the assistant can provide geolocation maps to showcase specific trends or occurrences.
        - Code Analysis and Creation: the assistant can analyze and critique code, and even create code from scratch.
        - Many other things that can be accomplished running python code in a jupyter environment.
        - Multiple visualizations are allowed as long as the return is a markdown string with the url of the image.

        Args:
        data (str): The dataset
        query (str): The query

        Returns:
        str: The result of the data analysis
        """
        return self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "context": f"## Reference Data\\n{data}",
                "user_input": query,
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": True,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

    async def ask_for_help(self, query: str):
        """
        Ask for help from a helper agent

        Args:
        query (str): The task to ask for help with

        Returns:
        str: The response from the helper agent
        """
        return self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"Please help me with the following task:\\n{query}",
                "websearch": False,
                "websearch_depth": 0,
                "analyze_user_input": False,
                "disable_commands": True,
                "log_user_input": False,
                "log_output": False,
                "browse_links": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

    async def execute_python_code_internal(self, code: str, text: str = "") -> str:
        """
        Execute Python code

        Args:
        code (str): The Python code
        text (str): The text

        Returns:
        str: The result of the Python code
        """
        if text:
            csv_content_header = text.split("\\n")[0]
            # Remove any trailing spaces from any headers
            csv_headers = [header.strip() for header in csv_content_header.split(",")]
            # Replace the first line with the comma separated headers
            text = ",".join(csv_headers) + "\\n" + "\\n".join(text.split("\\n")[1:])
            filename = "data.csv"
            filepath = os.path.join(self.WORKING_DIRECTORY, filename)
            with open(filepath, "w") as f:
                f.write(text)

        agents = self.ApiClient.get_agents()
        agent_id = ""
        for agent in agents:
            if agent["name"] == self.agent_name:
                agent_id = str(agent["id"])

        execution_response = execute_python_code(
            code=code, agent_id=agent_id, conversation_id=self.conversation_id
        )
        return execution_response

    async def chain_to_mermaid(self, chain_name: str):
        """
        Convert a chain to a Mermaid diagram format for visualization

        Args:
        chain_name (str): The name of the chain to explain

        Returns:
        str: A Mermaid diagram representation of the chain
        """
        chain_data = self.ApiClient.get_chain(chain_name=chain_name)
        mermaid_diagram = ["graph TD"]
        steps = chain_data.get("steps", [])

        for i, step in enumerate(steps):
            step_number = step.get("step", i + 1)
            agent_name = step.get("agent_name", "Unknown")
            prompt_type = step.get("prompt_type", "Unknown")
            prompt = step.get("prompt", {})

            # Create node for current step
            node_id = f"S{step_number}"
            node_label = f"{step_number}. {agent_name}"
            mermaid_diagram.append(f'    {node_id}["{node_label}"]')

            # Add details about the prompt or command
            if prompt_type.lower() == "prompt":
                prompt_name = prompt.get("prompt_name", "Unknown")
                mermaid_diagram.append(
                    f'    {node_id}AI["AI Prompt:<br>{prompt_name}"]'
                )
                mermaid_diagram.append(f"    {node_id} --> {node_id}AI")
            else:  # Command or Chain
                command_name = prompt.get("command_name") or prompt.get(
                    "chain_name", "Unknown"
                )
                mermaid_diagram.append(
                    f'    {node_id}Cmd["Command:<br>{command_name}"]'
                )
                mermaid_diagram.append(f"    {node_id} --> {node_id}Cmd")

            # Connect to next step
            if i < len(steps) - 1:
                next_step = steps[i + 1].get("step", i + 2)
                mermaid_diagram.append(f"    {node_id} --> S{next_step}")

            # Add connections for step dependencies
            for key, value in prompt.items():
                if isinstance(value, str) and "{STEP" in value:
                    dep_step = value.split("{STEP")[1].split("}")[0]
                    mermaid_diagram.append(f"    S{dep_step} -.-> {node_id}")

        mermaid = "\\n".join(mermaid_diagram)
        return f"```mermaid\\n{mermaid}\\n```"

    async def get_datetime(self) -> str:
        """
        Get the current date and time

        Returns:
        str: The current date and time in the format "YYYY-MM-DD HH:MM:SS"
        """
        return "Current date and time: " + datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    async def create_agixt_chain(self, natural_language_request: str):
        """
        Create an automation chain from a natural language request

        Args:
        natural_language_request (str): Description of what the chain should do

        Returns:
        str: The name of the created chain
        """
        response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Create Chain",
            prompt_args={
                "user_input": natural_language_request,
                "conversation_name": self.conversation_name,
            },
        )
        return response

    async def modify_chain(self, chain_name: str, description_of_modifications: str):
        """
        Modify an existing automation chain

        Args:
        chain_name (str): The name of the chain to modify
        description_of_modifications (str): Description of the modifications to make

        Returns:
        str: Confirmation of the modifications
        """
        response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Modify Chain",
            prompt_args={
                "chain_name": chain_name,
                "user_input": description_of_modifications,
                "conversation_name": self.conversation_name,
            },
        )
        return response

    async def custom_api(
        self,
        method: str,
        url: str,
        headers: str = "",
        body: str = "",
    ):
        """
        Make a custom API call

        Args:
        method (str): HTTP method (GET, POST, PUT, DELETE, etc.)
        url (str): The URL to call
        headers (str): JSON string of headers to include
        body (str): Request body (for POST, PUT, etc.)

        Returns:
        str: The API response
        """
        import requests

        try:
            # Parse headers if provided
            if headers:
                headers_dict = (
                    json.loads(headers) if isinstance(headers, str) else headers
                )
            else:
                headers_dict = {}

            # Make the API call
            if method.upper() in ["POST", "PUT", "PATCH"] and body:
                response = requests.request(
                    method=method.upper(),
                    url=url,
                    headers=headers_dict,
                    json=json.loads(body) if isinstance(body, str) else body,
                    timeout=30,
                )
            else:
                response = requests.request(
                    method=method.upper(), url=url, headers=headers_dict, timeout=30
                )

            return f"Status: {response.status_code}\\nResponse: {response.text}"
        except Exception as e:
            return f"Error making API call: {str(e)}"

    async def get_mindmap(self, task: str, additional_context: str = ""):
        """
        Get a mindmap for a task

        Args:
        task (str): The task
        additional_context (str): Additional context for the task

        Returns:
        dict: The mindmap
        """
        mindmap = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"Create a mindmap using a mermaid diagram for the users input:\\n{task}",
                "context": f"Additional context for creating the mindmap:\\n{additional_context}",
                "websearch": False,
                "websearch_depth": 0,
                "analyze_user_input": False,
                "disable_commands": True,
                "log_user_input": False,
                "log_output": False,
                "browse_links": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )
        return mindmap
