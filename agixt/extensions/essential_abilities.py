import json
import os
import subprocess
import asyncio
import logging
import datetime
import threading
import re
import ast
from typing import Optional, List
from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from MagicalAuth import (
    convert_time,
    get_user_timezone,
    convert_user_time_to_utc,
    get_current_user_time,
)
from Extensions import Extensions
from safeexecute import execute_python_code
from InternalClient import InternalClient
from Globals import getenv
from Task import Task
from middleware import log_silenced_exception
from DB import (
    get_session,
    Base,
    DATABASE_TYPE,
    UUID,
    get_new_id,
    ExtensionDatabaseMixin,
)
import uuid


# Binary file extensions to skip when searching file contents
BINARY_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".svg",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".mkv",
    ".flac",
    ".ogg",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".bz2",
    ".xz",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".obj",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    ".ico",
    ".icns",
}


# Database Model for Todos
class EssentialTodo(Base):
    """Database model for storing todo items in essential abilities"""

    __tablename__ = "essential_todos"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        nullable=False,
        index=True,
    )
    parent_id = Column(
        Integer, ForeignKey("essential_todos.id"), nullable=True, default=None
    )
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(
        String(20), nullable=False, default="not-started"
    )  # not-started, in-progress, completed
    depends_on = Column(
        Text, nullable=True, default=None
    )  # Comma-separated list of task IDs that must be completed first
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # Note: Self-referential relationship for parent-child todos
    # Commented out temporarily to resolve SQLAlchemy registry conflicts
    # children = relationship(
    #     "agixt.extensions.essential_abilities.EssentialTodo",
    #     backref="parent",
    #     remote_side=[id],
    #     cascade="all, delete-orphan",
    #     single_parent=True,
    # )

    def _parse_dependencies(self):
        """Parse the comma-separated depends_on field into a list of integers"""
        if not self.depends_on:
            return []
        try:
            return [int(id.strip()) for id in self.depends_on.split(",") if id.strip()]
        except ValueError:
            return []

    def _can_start(self):
        """Check if this task can be started (all dependencies are completed)"""
        dependencies = self._parse_dependencies()
        if not dependencies:
            return True

        # This will be called from to_dict, so we need to import get_session here
        from DB import get_session

        session = get_session()
        try:
            # Check if all dependencies are completed
            completed_deps = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id.in_(dependencies),
                    EssentialTodo.conversation_id == self.conversation_id,
                    EssentialTodo.status == "completed",
                )
                .count()
            )
            return completed_deps == len(dependencies)
        finally:
            session.close()

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": str(self.conversation_id),
            "parent_id": self.parent_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "depends_on": self.depends_on,
            "dependencies": self._parse_dependencies(),
            "can_start": self._can_start(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            # Note: has_children calculation disabled due to relationship temporarily removed
            "has_children": False,
        }


class essential_abilities(Extensions, ExtensionDatabaseMixin):
    """
    The Essential Abilities extension provides core functionality for agents,
    including file system operations within the agent's workspace, data analysis, Python code execution,
    scheduling follow-up messages, todo list management, and other fundamental capabilities.

    The agent's workspace is a safe sandboxed environment where the agent has access to uploaded files, files it downloads,
    and files it creates. This allows the agent to perform tasks such as reading and writing files, searching file contents,
    executing Python scripts, and running shell commands in its own environment.

    The scheduling capabilities enable the AI to proactively schedule follow-up messages and interactions with users at specific times.
    When scheduled times arrive, the AI can execute commands and notify users of task completion, enabling time-based automation
    and proactive engagement such as reminders, progress checks, automated reports, and recurring check-ins.

    The todo list management capabilities allow the AI to create, track, and manage structured todo lists with database persistence.
    Each todo is linked to the current conversation and supports status tracking (not-started, in-progress, completed).
    This ensures proper task visibility, planning, and completion tracking for complex workflows across conversation sessions.
    """

    CATEGORY = "Core Abilities"

    # Register extension models for automatic table creation
    extension_models = [EssentialTodo]

    def __init__(self, **kwargs):
        self.commands = {
            "Write to File": self.write_to_file,
            "Read File": self.read_file,
            "List Directory": self.list_directory,
            "Search Files": self.search_files,
            "Search File Content": self.search_file_content,
            "Glob File Search": self.glob_file_search,
            "Grep Search": self.grep_search,
            "Modify File": self.modify_file,
            "Execute Python File": self.execute_python_file,
            "Delete File": self.delete_file,
            "Execute Shell": self.execute_shell,
            "Run Data Analysis": self.run_data_analysis,
            "Execute Python Code": self.execute_python_code_internal,
            "Explain Chain": self.chain_to_mermaid,
            "Get Datetime": self.get_datetime,
            "Get Chain Details": self.get_chain_details,
            "Get Chain List": self.get_chain_list,
            "Create Automation Chain": self.create_agixt_chain,
            "Modify Automation Chain": self.modify_chain,
            "Custom API Endpoint": self.custom_api,
            "Get Mindmap for task to break it down": self.get_mindmap,
            "Convert Markdown to PDF": self.convert_to_pdf,
            "Convert Markdown to DOCX": self.convert_to_docx,
            "Convert Markdown to XLSX": self.convert_to_xlsx,
            "Convert Markdown to PPTX": self.convert_to_pptx,
            "Schedule Follow-Up Message": self.schedule_task,
            "Schedule Recurring Follow-Up": self.schedule_reoccurring_task,
            "Get Scheduled Follow-Ups": self.get_scheduled_tasks,
            "Modify Scheduled Follow-Up": self.modify_task,
            "Generate Image": self.generate_image,
            "Convert Text to Speech": self.text_to_speech,
            "Create Todo Item": self.create_todo_item,
            "Create Sub-Todo Item": self.create_sub_todo_item,
            "Create Todo Items in Bulk": self.create_todo_items_bulk,
            "List Current Todos": self.list_current_todos,
            "List Runnable Todos": self.list_runnable_todos,
            "Run Todo List": self.run_todo_list,
            "List Sub-Todos": self.list_sub_todos,
            "Mark Todo Item Completed": self.mark_todo_completed,
            "Mark Todo Item Incomplete": self.mark_todo_incomplete,
            "Update Todo Item": self.update_todo_item,
            "Delete Todo Item": self.delete_todo_item,
            "Gather information from website URLs": self.browse_links,
            "Fetch Webpage Content": self.fetch_webpage_content,
            "Download File from URL": self.download_file_from_url,
            "View Image": self.view_image,
            "Get Web UI Tips": self.get_webui_tips,
            "Create AGiXT Agent": self.create_new_agixt_agent,
            "Optimize Command Selection": self.optimize_command_selection,
            # New Code Intelligence & Development Tools
            "Find Symbol Usages": self.find_symbol_usages,
            "Semantic Code Search": self.semantic_code_search,
            "Multi-File Replace": self.multi_file_replace,
            "Get File Errors": self.get_file_errors,
            "Run Tests": self.run_tests,
            "Get Code Symbols": self.get_code_symbols,
            "Git Status": self.git_status,
            "Git Commit": self.git_commit,
            "Git Diff": self.git_diff,
            "Git Blame": self.git_blame,
            "Create Directory": self.create_directory,
            "Rename File": self.rename_file,
            "Copy File": self.copy_file,
            "Get File Metadata": self.get_file_metadata,
            "Diff Files": self.diff_files,
            "Format Code": self.format_code,
            "Insert in File": self.insert_in_file,
            "Delete Lines": self.delete_lines,
            "Get File Line Count": self.get_file_line_count,
            "Search and Replace Regex": self.search_and_replace_regex,
            "Extract Function": self.extract_function,
            "Get Imports": self.get_imports,
            "Append to File": self.append_to_file,
            "Prepend to File": self.prepend_to_file,
            "Git Log": self.git_log,
            "Git Branch": self.git_branch,
            "Git Stash": self.git_stash,
            "Find Duplicate Code": self.find_duplicate_code,
            "Get Function Signature": self.get_function_signature,
            "Validate JSON": self.validate_json,
            "Validate YAML": self.validate_yaml,
            "Minify JSON": self.minify_json,
            "Prettify JSON": self.prettify_json,
            "Count Lines of Code": self.count_lines_of_code,
            "Find TODO Comments": self.find_todo_comments,
            "Generate Docstring": self.generate_docstring,
            "Get File Tree": self.get_file_tree,
            "Move File": self.move_file,
            "Find References": self.find_references,
            "Get Class Definition": self.get_class_definition,
            "Get Method List": self.get_method_list,
            "Analyze Dependencies": self.analyze_dependencies,
            "Get Code Outline": self.get_code_outline,
            "Git Fetch": self.git_fetch,
            "Git Pull": self.git_pull,
            "Git Merge": self.git_merge,
            "Git Revert": self.git_revert,
            "Git Cherry Pick": self.git_cherry_pick,
            "Find Test File": self.find_test_file,
            "Lint File": self.lint_file,
            "Sort Lines": self.sort_lines,
            "Remove Duplicate Lines": self.remove_duplicate_lines,
            "Extract Comments": self.extract_comments,
            "Generate Changelog": self.generate_changelog,
            "Head File": self.head_file,
            "Tail File": self.tail_file,
            "Check Path Exists": self.check_path_exists,
            "Get File Hash": self.get_file_hash,
            "Truncate File": self.truncate_file,
            "Find Large Files": self.find_large_files,
            # Context Management Commands
            "Discard Context": self.discard_context,
            "Retrieve Context": self.retrieve_context,
            "List Discarded Context": self.list_discarded_context,
            # Feedback Commands
            "Send Feedback to Development Team": self.send_feedback_to_dev_team,
            # Codebase Mapping
            "Create or Update Codebase Map": self.create_or_update_codebase_map,
        }
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.WORKING_DIRECTORY_RESTRICTED = True
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)
        self.user_id = kwargs.get("user_id", None)
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.agent_id = kwargs.get("agent_id")
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.conversation_id = (
            kwargs["conversation_id"] if "conversation_id" in kwargs else ""
        )
        self.activity_id = kwargs["activity_id"] if "activity_id" in kwargs else None
        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else InternalClient(
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
                user=kwargs.get("user"),
            )
        )
        self.user = kwargs.get("user", None)
        self.output_url = kwargs.get("output_url", "")
        self.api_key = kwargs.get("api_key", "")

        # Register models with ExtensionDatabaseMixin
        self.register_models()

    async def browse_links(self, urls: str, query: str) -> str:
        """
        Browse links to gather information from websites. This will scrape data from the websites provided into the agent's memory.

        Args:
            urls (str): Space-separated list of URLs to browse. Prefix each url with "https://" with the full url. When browsing multiple URLs, separate them with spaces.
            query (str): The query to search for on the pages

        Returns:
            str: The gathered information

        Notes: This ability will browse the provided URLs and extract relevant information based on the query as well as extract learned information from the website into the assistant's memory.
        """
        response = self.ApiClient.prompt_agent(
            agent_id=self.agent_id,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"{urls} \n {query}",
                "websearch": False,
                "analyze_user_input": False,
                "disable_commands": True,
                "log_user_input": False,
                "log_output": False,
                "browse_links": True,
                "tts": False,
                "conversation_name": self.conversation_id,
            },
        )
        return response

    async def download_file_from_url(
        self, url: str, filename: str = "", headers: str = ""
    ) -> str:
        """
        Download a file from a URL to the agent's workspace

        Args:
            url (str): The URL to download the file from (must start with https://)
            filename (str): Optional custom filename to save as. If not provided, uses the filename from the URL
            headers (str): Optional JSON string of HTTP headers for authentication (e.g., '{"Authorization": "Bearer token"}')

        Returns:
            str: Success message with download link or error message

        Notes:
            - Only HTTPS URLs are allowed for security
            - Downloaded files are saved to the agent's workspace
            - Supports authentication via custom headers
            - Automatically detects filename from URL if not provided
            - File is immediately accessible to user via download link

        Example headers for authentication:
            '{"Authorization": "Bearer your_token_here"}'
            '{"X-API-Key": "your_api_key_here"}'
        """
        import requests
        from urllib.parse import urlparse, unquote

        # Security check: only allow HTTPS URLs
        if not url.startswith("https://"):
            return "Error: Only HTTPS URLs are allowed for security reasons. Please provide a URL starting with 'https://'"

        try:
            # Parse headers if provided
            request_headers = {}
            if headers:
                try:
                    request_headers = json.loads(headers)
                except json.JSONDecodeError:
                    return f"Error: Invalid headers format. Headers must be valid JSON string."

            # Make the request
            logging.info(f"Downloading file from URL: {url}")
            response = requests.get(
                url, headers=request_headers, stream=True, timeout=30
            )
            response.raise_for_status()

            # Determine filename
            if not filename:
                # Try to get filename from Content-Disposition header
                content_disposition = response.headers.get("Content-Disposition")
                if content_disposition:
                    import re

                    filename_match = re.findall(
                        'filename="?([^"]+)"?', content_disposition
                    )
                    if filename_match:
                        filename = filename_match[0]

                # If still no filename, extract from URL
                if not filename:
                    parsed_url = urlparse(url)
                    filename = unquote(parsed_url.path.split("/")[-1])

                # If still no filename, generate one
                if not filename or filename == "":
                    filename = f"downloaded_file_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Ensure filename doesn't contain path separators
            filename = os.path.basename(filename)

            # Save the file
            file_path = self.safe_join(filename)
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)

            logging.info(f"Successfully downloaded {filename} ({file_size_mb:.2f} MB)")

            return f"Successfully downloaded file to workspace: {filename} ({file_size_mb:.2f} MB)\n\nDownload link: {self.output_url}/{filename}"

        except requests.exceptions.Timeout:
            return f"Error: Request timed out while trying to download from {url}"
        except requests.exceptions.HTTPError as e:
            return f"Error: HTTP error occurred: {e.response.status_code} - {e.response.reason}"
        except requests.exceptions.RequestException as e:
            return f"Error: Failed to download file: {str(e)}"
        except Exception as e:
            return f"Error downloading file: {str(e)}"

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

    async def view_image(
        self, image_path: str, query: str = "What is in this image?"
    ) -> str:
        """
        View and analyze an image file in the agent's workspace

        Args:
        image_path (str): The path to the image file in the agent's workspace, or a URL to an image to download to the agent's workspace and view.
        query (str): The question or analysis to perform on the image

        Returns:
        str: The analysis or description of the image

        Note: Example, the assistant could ask what is in the image, to OCR the image to pull text from it, ask about specific things in the image or details, etc.
        """
        if image_path.startswith("https://"):
            file_name = f"{uuid.uuid4()}_{image_path.split('/')[-1]}"
            await self.download_file_from_url(url=image_path, filename=file_name)
            image_path = os.path.join(self.WORKING_DIRECTORY, file_name)
        # Ensure the image path is safe
        safe_image_path = self.safe_join(image_path)

        if not os.path.exists(safe_image_path):
            return f"Error: Image file '{image_path}' does not exist in the workspace."
        # Read and encode the image in base64
        import base64
        from Agent import Agent

        with open(safe_image_path, "rb") as img_file:
            image_data = img_file.read()
            base64_image = base64.b64encode(image_data).decode("utf-8")
        base64_image = f"data:image/{image_path.split('.')[-1]};base64,{base64_image}"

        agent = Agent(agent_id=self.agent_id, ApiClient=self.ApiClient, user=self.user)
        response = await agent.inference(prompt=query, images=[base64_image])
        return response

    async def read_file(
        self,
        filename: str,
        line_start: str,
        line_end: str,
    ) -> str:
        """
        Read a file in the workspace, optionally reading only specific line ranges.

        **IMPORTANT**: This command returns a maximum of 100 lines at a time to manage context size.
        If a file is larger than 100 lines, it will be truncated and you will need to make additional
        calls with different line ranges to see the full content.

        Args:
        filename (str): The name of the file to read
        line_start (int): The starting line number (1-indexed). If "None", starts from beginning
        line_end (int): The ending line number (1-indexed, inclusive). If "None", reads to end (max 100 lines)

        Returns:
        str: The content of the file or specified line range

        Notes:
        - This command will only work in the agent's designated workspace
        - The agent's workspace may contain files uploaded by the user or files saved by the agent
        - The user can browse the agents workspace by clicking the folder icon in their chat input bar
        - For large files or data analysis, consider using Execute Python Code to extract specific information
        - For CSV/data files, use Execute Python Code with pandas to analyze data efficiently
        - XLSX/XLS files are automatically converted to CSV format for reading
        """
        MAX_LINES = 100  # Maximum lines to return per read
        try:
            line_start = int(line_start)
        except:
            line_start = None
        try:
            line_end = int(line_end)
        except:
            line_end = None
        try:
            filepath = self.safe_join(filename)

            # Check if this is an Excel file - convert to CSV if needed
            file_ext = os.path.splitext(filename)[1].lower()
            csv_notice = ""
            if file_ext in [".xlsx", ".xls"]:
                import pandas as pd

                # Check if CSV version already exists
                base_name = os.path.splitext(filename)[0]
                csv_filename = f"{base_name}.csv"
                csv_filepath = self.safe_join(csv_filename)

                if not os.path.exists(csv_filepath):
                    # Convert Excel to CSV
                    try:
                        xl = pd.ExcelFile(filepath)
                        if len(xl.sheet_names) > 1:
                            # Multiple sheets - convert each to separate CSV
                            csv_files = []
                            for i, sheet_name in enumerate(xl.sheet_names, 1):
                                df = xl.parse(sheet_name)
                                sheet_csv_filename = f"{base_name}_{i}.csv"
                                sheet_csv_filepath = self.safe_join(sheet_csv_filename)
                                df.to_csv(sheet_csv_filepath, index=False)
                                csv_files.append(sheet_csv_filename)
                            csv_notice = f"**Note**: Excel file `{filename}` has {len(xl.sheet_names)} sheets. Converted to: {', '.join(csv_files)}. Reading first sheet (`{csv_files[0]}`).\n\n"
                            csv_filepath = self.safe_join(csv_files[0])
                            csv_filename = csv_files[0]
                        else:
                            # Single sheet
                            df = pd.read_excel(filepath)
                            df.to_csv(csv_filepath, index=False)
                            csv_notice = f"**Note**: Excel file `{filename}` converted to `{csv_filename}` for reading.\n\n"
                    except Exception as e:
                        return f"Error: Failed to convert Excel file to CSV: {str(e)}"
                else:
                    csv_notice = f"**Note**: Reading CSV version `{csv_filename}` of Excel file `{filename}`.\n\n"

                # Update filepath to read the CSV version
                filepath = csv_filepath
                filename = csv_filename

            # Read the file lines
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Determine start and end indices
            start_idx = 0 if line_start is None else max(0, line_start - 1)

            if line_end is None:
                # No end specified - read from start up to MAX_LINES
                end_idx = min(start_idx + MAX_LINES, total_lines)
            else:
                # End specified - respect it but cap at MAX_LINES from start
                requested_end = min(total_lines, line_end)
                end_idx = min(start_idx + MAX_LINES, requested_end)

            # Extract the requested lines
            selected_lines = lines[start_idx:end_idx]
            content = "".join(selected_lines)

            # Calculate actual line numbers (1-indexed)
            actual_start = start_idx + 1
            actual_end = start_idx + len(selected_lines)
            lines_returned = len(selected_lines)

            # Build header with line information
            header = csv_notice  # Include Excel->CSV conversion notice if applicable
            header += (
                f"Lines {actual_start}-{actual_end} of {total_lines} total lines:\n"
            )
            header += "=" * 40 + "\n"

            # Check if content was truncated
            was_truncated = False
            if line_end is None and actual_end < total_lines:
                # Reading from start with no end specified - truncated at MAX_LINES
                was_truncated = True
            elif (
                line_end is not None
                and actual_end < line_end
                and actual_end < total_lines
            ):
                # Requested range was larger than MAX_LINES
                was_truncated = True

            # Build footer with truncation notice and guidance
            footer = ""
            if was_truncated:
                remaining_lines = total_lines - actual_end
                next_start = actual_end + 1
                footer = "\n" + "=" * 40 + "\n"
                footer += f"**TRUNCATED**: Output limited to {MAX_LINES} lines. "
                footer += f"Showing lines {actual_start}-{actual_end} of {total_lines} total.\n"
                footer += f"- To see more, use Read File with line_start={next_start} ({remaining_lines} lines remaining)\n"
                footer += f"- For data files (CSV, JSON, etc.), consider using Execute Python Code to:\n"
                footer += f"  - Load and analyze data with pandas: `pd.read_csv('{filename}')`\n"
                footer += f"  - Extract specific columns or rows\n"
                footer += (
                    f"  - Get summary statistics with `.describe()` or `.info()`\n"
                )
                footer += f"  - Filter data to find specific information\n"

            return header + content + footer
        except Exception as e:
            return f"Error: {str(e)}"

    async def write_to_file(self, filename: str, text: str) -> str:
        """
        Write text to a file in the workspace

        Args:
        filename (str): The name of the file to write to
        text (str): The text to write to the file

        Returns:
        str: Success message with download link

        Note: This command will only work in the agent's designated workspace.
        """
        try:
            filepath = self.safe_join(filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            return f"File {filename} written successfully. The user can access it at {self.output_url}{filename}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    async def search_files(self, query: str) -> str:
        """
        Search for files in the workspace that match a pattern, or list files in a directory path.

        Args:
        query (str): The search pattern, filename, or directory path to search/list.
                     Examples:
                     - "*.ir" - find all .ir files
                     - "**/*.ir" - find all .ir files recursively
                     - "Samsung" - find files with Samsung in the name
                     - "TVs/Samsung/" - list all files in TVs/Samsung/ folder
                     - "TVs/Samsung/*.ir" - find .ir files in TVs/Samsung path
                     - "power" - find files with "power" in the name

        Returns:
        str: List of matching files with their paths

        Note: This command searches the agent's workspace. For searching within file contents, use "Search File Content" instead.
        """
        import fnmatch
        import glob as glob_module

        matches = []
        try:
            # Check if this is a glob pattern (contains *, ?, or [])
            is_glob_pattern = any(c in query for c in ["*", "?", "["])

            # If it's a glob pattern, use glob for matching
            if is_glob_pattern:
                # Use recursive glob to find matching files
                search_pattern = os.path.join(self.WORKING_DIRECTORY, "**", query)
                glob_matches = glob_module.glob(search_pattern, recursive=True)

                # Also try without ** prefix for exact path patterns
                if "/" in query:
                    exact_pattern = os.path.join(self.WORKING_DIRECTORY, query)
                    glob_matches.extend(glob_module.glob(exact_pattern, recursive=True))

                # Get unique matches and convert to relative paths
                seen = set()
                for match in glob_matches:
                    if os.path.isfile(match):
                        relative_path = os.path.relpath(match, self.WORKING_DIRECTORY)
                        if relative_path not in seen:
                            seen.add(relative_path)
                            matches.append(relative_path)

            # Check if query looks like a directory path (ends with / and no glob chars)
            elif query.endswith("/"):
                # Try to list the directory
                dir_path = os.path.join(self.WORKING_DIRECTORY, query.rstrip("/"))
                if os.path.isdir(dir_path):
                    # List contents of this directory
                    for root, dirnames, filenames in os.walk(dir_path):
                        # Get relative path from workspace root
                        rel_root = os.path.relpath(root, self.WORKING_DIRECTORY)
                        for dirname in dirnames[:20]:  # Limit subdirs shown
                            matches.append(f"📁 {rel_root}/{dirname}/")
                        for filename in filenames[:50]:  # Limit files shown
                            matches.append(f"📄 {rel_root}/{filename}")
                        # Only show first level if there are many items
                        if len(dirnames) + len(filenames) > 30:
                            break

                    if matches:
                        total_files = sum(len(f) for _, _, f in os.walk(dir_path))
                        return (
                            f"Contents of `{query}` ({total_files} total files):\n"
                            + "\n".join(matches[:100])
                        )
                    else:
                        return f"Directory `{query}` is empty."

            # Standard filename/path substring search
            if not matches:
                for root, dirnames, filenames in os.walk(self.WORKING_DIRECTORY):
                    for filename in filenames:
                        relative_path = os.path.relpath(
                            os.path.join(root, filename), self.WORKING_DIRECTORY
                        )
                        # Match if query is in filename OR in full relative path
                        if (
                            query.lower() in filename.lower()
                            or query.lower() in relative_path.lower()
                            or fnmatch.fnmatch(filename.lower(), f"*{query.lower()}*")
                            or fnmatch.fnmatch(
                                relative_path.lower(), f"*{query.lower()}*"
                            )
                        ):
                            matches.append(relative_path)

            if matches:
                # Sort matches for easier reading
                matches = sorted(set(matches))[:100]
                return f"Found {len(matches)} matching files:\n" + "\n".join(matches)
            else:
                # Provide helpful guidance
                return f"No files found matching pattern: {query}\n\nTips:\n- Use 'TVs/Samsung/' to list a directory\n- Use '*.ir' or '**/*.ir' to find IR files\n- Use 'Search File Content' to search inside files"
        except Exception as e:
            return f"Error searching files: {str(e)}"

    async def list_directory(self, path: str = "") -> str:
        """
        List the contents of a directory in the workspace.

        Args:
        path (str): The directory path relative to workspace root. Use "" or "." for root.
                    Examples: "TVs/Samsung/", "extracted_folder/", "subfolder"

        Returns:
        str: List of files and subdirectories in the specified path

        Note: This is useful for browsing the workspace structure to find specific files.
        """
        try:
            # Normalize the path
            if not path or path == ".":
                dir_path = self.WORKING_DIRECTORY
                display_path = "workspace root"
            else:
                dir_path = self.safe_join(path.rstrip("/"))
                display_path = path

            if not os.path.exists(dir_path):
                return f"Directory not found: {path}\n\nTip: Use 'Search Files' to find files by name pattern."

            if not os.path.isdir(dir_path):
                return f"{path} is a file, not a directory. Use 'Read File' to view its contents."

            # List contents
            items = []
            dirs = []
            files = []

            for item in sorted(os.listdir(dir_path)):
                item_path = os.path.join(dir_path, item)
                if os.path.isdir(item_path):
                    # Count items in subdirectory
                    try:
                        subitem_count = len(os.listdir(item_path))
                        dirs.append(f"📁 {item}/ ({subitem_count} items)")
                    except:
                        dirs.append(f"📁 {item}/")
                else:
                    # Get file size
                    try:
                        size = os.path.getsize(item_path)
                        if size < 1024:
                            size_str = f"{size} B"
                        elif size < 1024 * 1024:
                            size_str = f"{size/1024:.1f} KB"
                        else:
                            size_str = f"{size/(1024*1024):.1f} MB"
                        files.append(f"📄 {item} ({size_str})")
                    except:
                        files.append(f"📄 {item}")

            items = dirs + files

            if not items:
                return f"Directory `{display_path}` is empty."

            # Limit output
            total = len(items)
            if total > 100:
                items = items[:100]
                items.append(f"\n... and {total - 100} more items")

            return (
                f"Contents of `{display_path}` ({len(dirs)} folders, {len(files)} files):\n\n"
                + "\n".join(items)
            )
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    async def search_file_content(self, query: str, filename: str = "") -> str:
        """
        Search for content within files in the workspace

        Args:
        query (str): The text to search for (case-insensitive)
        filename (str): Optional specific file or folder to search in (e.g., "TVs/Samsung/")

        Returns:
        str: Search results showing matching lines with file paths and line numbers

        Note: Searches all text-based files. For binary files, use other tools.
        """
        # Binary file extensions to skip
        BINARY_EXTENSIONS = {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".ico",
            ".webp",
            ".svg",
            ".mp3",
            ".mp4",
            ".wav",
            ".avi",
            ".mov",
            ".mkv",
            ".flac",
            ".zip",
            ".tar",
            ".gz",
            ".rar",
            ".7z",
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".bin",
            ".pyc",
            ".pyo",
            ".class",
            ".o",
            ".obj",
            ".db",
            ".sqlite",
            ".sqlite3",
        }

        matches = []
        try:
            if filename:
                # Check if it's a directory path
                check_path = self.safe_join(filename.rstrip("/"))
                if os.path.isdir(check_path):
                    # Search in all files within this directory
                    files_to_search = []
                    for root, dirs, files in os.walk(check_path):
                        for file in files:
                            ext = os.path.splitext(file)[1].lower()
                            if ext not in BINARY_EXTENSIONS:
                                relative_path = os.path.relpath(
                                    os.path.join(root, file), self.WORKING_DIRECTORY
                                )
                                files_to_search.append(relative_path)
                else:
                    # Search in specific file
                    files_to_search = [filename]
            else:
                # Search in all text-based files
                files_to_search = []
                for root, dirs, files in os.walk(self.WORKING_DIRECTORY):
                    for file in files:
                        ext = os.path.splitext(file)[1].lower()
                        if ext not in BINARY_EXTENSIONS:
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
                result = f"Found {len(matches)} matches for '{query}':\n\n"
                result += "\n".join(matches[:50])  # Show up to 50 matches
                if len(matches) > 50:
                    result += f"\n\n... and {len(matches) - 50} more matches"
                return result
            else:
                return f"No matches found for: {query}\n\nTips:\n- Check spelling and try variations\n- Use 'List Directory' to browse folder structure\n- Use 'Read File' to view a specific file"
        except Exception as e:
            return f"Error searching file content: {str(e)}"

    async def glob_file_search(
        self, pattern: str, directory: str = "", max_results: int = 100
    ) -> str:
        """
        Search for files in the workspace using glob patterns. Useful for finding files by extension or name pattern.

        Args:
        pattern (str): The glob pattern to search for (e.g., "**/*.ir", "TVs/**/*.ir", "*.py", "**/Samsung*")
        directory (str): Optional subdirectory to search within. Defaults to workspace root.
        max_results (int): Maximum number of results to return. Default 100.

        Returns:
        str: List of matching file paths

        Examples:
        - "**/*.ir" - Find all .ir files recursively
        - "TVs/**/*.ir" - Find all .ir files in TVs folder and subfolders
        - "**/Samsung*" - Find all files/folders containing "Samsung"
        - "*.py" - Find all Python files in the root directory only
        """
        import fnmatch

        try:
            search_dir = self.WORKING_DIRECTORY
            if directory:
                search_dir = self.safe_join(directory)
                if not os.path.exists(search_dir):
                    return f"Directory not found: {directory}"

            matches = []
            # Handle recursive patterns with **
            if "**" in pattern:
                for root, dirs, files in os.walk(search_dir):
                    rel_root = os.path.relpath(root, search_dir)
                    if rel_root == ".":
                        rel_root = ""

                    for filename in files:
                        if rel_root:
                            rel_path = f"{rel_root}/{filename}"
                        else:
                            rel_path = filename

                        # Match against the full relative path
                        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(
                            filename,
                            pattern.split("/")[-1] if "/" in pattern else pattern,
                        ):
                            matches.append(rel_path)

                        if len(matches) >= max_results:
                            break
                    if len(matches) >= max_results:
                        break
            else:
                # Non-recursive pattern
                for item in os.listdir(search_dir):
                    if fnmatch.fnmatch(item, pattern):
                        matches.append(item)
                        if len(matches) >= max_results:
                            break

            if matches:
                result = f"Found {len(matches)} files matching '{pattern}':\n\n"
                result += "\n".join(sorted(matches))
                if len(matches) >= max_results:
                    result += f"\n\n(Results limited to {max_results})"
                return result
            else:
                return f"No files found matching pattern: {pattern}"

        except Exception as e:
            return f"Error in glob search: {str(e)}"

    async def grep_search(
        self,
        query: str,
        pattern: str = "**/*",
        is_regex: bool = False,
        context_lines: int = 0,
        max_results: int = 50,
    ) -> str:
        """
        Fast text search across files using grep-style matching. Supports regex and context lines.

        Args:
        query (str): The text or regex pattern to search for
        pattern (str): Glob pattern to filter which files to search (e.g., "**/*.ir", "**/*.py"). Default: all files
        is_regex (bool): Whether the query is a regex pattern. Default: False (plain text search)
        context_lines (int): Number of lines of context to show before and after each match. Default: 0
        max_results (int): Maximum number of matches to return. Default: 50

        Returns:
        str: Matching lines with file paths and line numbers, optionally with context

        Examples:
        - query="Samsung", pattern="**/*.ir" - Find "Samsung" in all .ir files
        - query="power|off|on", is_regex=True - Find power, off, or on using regex alternation
        - query="def ", pattern="**/*.py", context_lines=2 - Find function definitions with 2 lines context
        """
        import fnmatch
        import re

        try:
            if is_regex:
                try:
                    search_pattern = re.compile(query, re.IGNORECASE)
                except re.error as e:
                    return f"Invalid regex pattern: {e}"
            else:
                search_pattern = None

            matches = []
            files_searched = 0

            for root, dirs, files in os.walk(self.WORKING_DIRECTORY):
                for filename in files:
                    # Check if file matches the glob pattern
                    rel_root = os.path.relpath(root, self.WORKING_DIRECTORY)
                    if rel_root == ".":
                        rel_path = filename
                    else:
                        rel_path = f"{rel_root}/{filename}"

                    # Match file against pattern
                    if not fnmatch.fnmatch(rel_path, pattern) and not fnmatch.fnmatch(
                        filename, pattern.split("/")[-1] if "/" in pattern else pattern
                    ):
                        continue

                    # Skip binary files
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in BINARY_EXTENSIONS:
                        continue

                    file_path = os.path.join(root, filename)
                    try:
                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            lines = f.readlines()

                        for line_num, line in enumerate(lines, 1):
                            # Check for match
                            if is_regex:
                                if search_pattern.search(line):
                                    found = True
                                else:
                                    found = False
                            else:
                                found = query.lower() in line.lower()

                            if found:
                                if context_lines > 0:
                                    # Include context
                                    start = max(0, line_num - 1 - context_lines)
                                    end = min(len(lines), line_num + context_lines)
                                    context = []
                                    for i in range(start, end):
                                        prefix = ">" if i == line_num - 1 else " "
                                        context.append(
                                            f"  {prefix} {i+1}: {lines[i].rstrip()}"
                                        )
                                    matches.append(
                                        f"{rel_path}:\n" + "\n".join(context)
                                    )
                                else:
                                    matches.append(
                                        f"{rel_path}:{line_num}: {line.strip()}"
                                    )

                                if len(matches) >= max_results:
                                    break

                        files_searched += 1
                    except:
                        continue

                    if len(matches) >= max_results:
                        break
                if len(matches) >= max_results:
                    break

            if matches:
                result = f"Found {len(matches)} matches for '{query}' in {files_searched} files:\n\n"
                result += "\n\n".join(matches)
                if len(matches) >= max_results:
                    result += f"\n\n(Results limited to {max_results})"
                return result
            else:
                return f"No matches found for: {query} in files matching {pattern}"

        except Exception as e:
            return f"Error in grep search: {str(e)}"

    async def fetch_webpage_content(self, url: str, query: str = "") -> str:
        """
        Fetch and extract the main content from a webpage. Useful for retrieving information from websites.

        Args:
        url (str): The URL of the webpage to fetch
        query (str): Optional query to focus the extraction on relevant content

        Returns:
        str: The extracted content from the webpage

        Note: This extracts readable text content, not raw HTML. Good for documentation, articles, and reference pages.
        """
        import aiohttp
        from bs4 import BeautifulSoup

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        return f"Error fetching URL: HTTP {response.status}"

                    html = await response.text()

            soup = BeautifulSoup(html, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
                script.decompose()

            # Try to find main content area
            main_content = None
            for selector in [
                "main",
                "article",
                '[role="main"]',
                ".content",
                "#content",
                ".post",
                ".article",
            ]:
                main_content = soup.select_one(selector)
                if main_content:
                    break

            if not main_content:
                main_content = soup.body if soup.body else soup

            # Get text content
            text = main_content.get_text(separator="\n", strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n".join(lines)

            # Truncate if too long
            max_length = 10000
            if len(text) > max_length:
                text = text[:max_length] + "\n\n... [Content truncated]"

            # If query provided, try to extract most relevant sections
            if query:
                query_lower = query.lower()
                relevant_lines = []
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        # Include some context around matches
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        for j in range(start, end):
                            if lines[j] not in relevant_lines:
                                relevant_lines.append(lines[j])
                        relevant_lines.append("---")

                if relevant_lines:
                    text = f"Relevant content for '{query}':\n\n" + "\n".join(
                        relevant_lines
                    )

            return f"Content from {url}:\n\n{text}"

        except aiohttp.ClientError as e:
            return f"Error fetching webpage: {str(e)}"
        except Exception as e:
            return f"Error processing webpage: {str(e)}"

    async def modify_file(self, filename: str, old_text: str, new_text: str) -> str:
        """
        Modify a file by replacing old text with new text

        Args:
        filename (str): The name of the file to modify
        old_text (str): The text to replace
        new_text (str): The replacement text

        Returns:
        str: Success message with download link or error message

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
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

            return f"File {filename} modified successfully. The user can access it at {self.output_url}{filename}"
        except Exception as e:
            return f"Error modifying file: {str(e)}"

    async def delete_file(self, filename: str) -> str:
        """
        Delete a file from the workspace

        Args:
        filename (str): The name of the file to delete

        Returns:
        str: Success message

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
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

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
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

        Note: This command will only work in the agent's designated workspace. The agent's workspace may contain files uploaded by the user or files saved by the agent that will be available to the user to download and access.
        """
        try:
            # Try to use the new shell execution capability from safeexecute
            from safeexecute import execute_shell_command

            # Execute the shell command with proper sandboxing
            result = execute_shell_command(
                command=command_line,
                working_directory=self.WORKING_DIRECTORY,
                agent_id=self.agent_name,
                conversation_id=self.conversation_id,
            )

            return result
        except ImportError:
            # Fallback to the old method if execute_shell_command is not available
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
            parent_activity_id=self.activity_id,
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
        Execute Python code in a powerful sandboxed environment with full workspace access

        Args:
        code (str): The Python code to execute
        text (str): Optional CSV data that will be automatically saved as 'data.csv' in workspace

        Returns:
        str: The result of the Python code execution

        POWERFUL PYTHON CODE EXECUTION CAPABILITIES:

        **Workspace File System Access:**
        - Full read/write access to all files in your dedicated workspace directory
        - Automatically discovers and works with uploaded files, downloaded content, and previously created files
        - Can process multiple files simultaneously (CSV, Excel, images, PDFs, text files, etc.)
        - Files you create are immediately accessible to users via download links
        - Use standard Python file operations: open(), pandas.read_csv(), PIL.Image.open(), etc.

        **CRITICAL: Working with Uploaded Spreadsheets:**
        - XLSX files are automatically converted to CSV format - ALWAYS use the .csv version with pd.read_csv()
        - NEVER use pd.read_csv() on .xlsx files - it will fail with encoding errors
        - List files first: `import os; print([f for f in os.listdir('.') if f.endswith('.csv')])`
        - Always inspect data structure BEFORE selecting columns:
          ```python
          df = pd.read_csv('filename.csv')
          print("Columns:", df.columns.tolist())
          print("Shape:", df.shape)
          print(df.head())
          ```
        - Column names vs row values: If data has a "Reaction" or "Name" column, those VALUES are not column names!
          Example: If df has columns ['Reaction', 'Control', 'Treatment'] and Reaction contains ['ATP', 'NADPH'],
          to get ATP data: `df[df['Reaction'] == 'ATP']` NOT `df['ATP']`

        **Multi-File Operations:**
        - Process entire directories of files at once
        - Combine data from multiple sources automatically
        - Cross-reference and merge datasets from different files
        - Batch process images, documents, or data files
        - Example: `import os; files = [f for f in os.listdir('.') if f.endswith('.csv')]`

        **Mathematical & Analytical Power:**
        - NEVER attempt math problems manually - ALWAYS use Python code for accurate calculations
        - Supports complex mathematics: calculus, statistics, linear algebra, differential equations
        - Includes counting operations (force strings to lowercase for letter counting)
        - Advanced statistical analysis and hypothesis testing
        - Machine learning and data modeling capabilities

        **Data Visualization & Analysis:**
        - Create professional charts, graphs, and interactive visualizations
        - Generate heatmaps, scatter plots, histograms, box plots, and custom visualizations
        - Geospatial mapping and location-based analysis
        - Time series analysis and forecasting
        - Network analysis and graph visualizations

        **File Processing & Conversion:**
        - Image manipulation: resize, crop, filter, format conversion, enhancement
        - PDF processing: extract text, split, merge, analyze content
        - Excel/CSV operations: complex data transformations, pivot tables, analysis
        - Document generation: create reports, presentations, formatted output
        - Audio/video processing capabilities

        **Creative & Advanced Operations:**
        - QR code generation and barcode processing
        - Web scraping and API data retrieval
        - Natural language processing on text files
        - Computer vision tasks on images
        - Project planning: Gantt charts, timelines, resource allocation
        - Study schedules and optimization problems

        **Code Best Practices:**
        - Always print df.columns.tolist() first when working with dataframes
        - Always end with a print() statement showing results to the user
        - Save important outputs as files for user download
        - Include data visualizations when appropriate
        - Handle errors gracefully with try/except blocks
        - Use descriptive variable names and add comments for complex operations
        - Import required packages at the beginning (auto-installation supported)

        Remember: This is an incredibly powerful tool - use it creatively to solve complex problems that would be difficult or impossible with other commands. The combination of workspace file access, multi-file processing, and advanced Python libraries makes this suitable for professional-grade data analysis and automation tasks.
        `Can't` is for humans, not for you.
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

        execution_response = execute_python_code(
            code=code,
            working_directory=self.WORKING_DIRECTORY,
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

    async def get_chain_details(self, chain_name: str):
        """
        Get details of a chain

        Args:
        chain_name (str): The name of the chain

        Returns:
        str: The details of the chain
        """
        chain_data = self.ApiClient.get_chain(chain_name=chain_name)
        return json.dumps(chain_data, indent=4)

    async def get_chain_list(self):
        """
        Get a list of all chains

        Returns:
        str: The list of chains
        """
        chains = self.ApiClient.get_chains()
        chain_names = chains  # get_chains() already returns list of chain names
        return "Available Chains:\\n" + "\\n".join(chain_names)

    async def get_datetime(self) -> str:
        """
        Get the current date and time in the user's timezone

        Returns:
        str: The current date and time in the format "YYYY-MM-DD HH:MM:SS"
        """
        return "Current date and time: " + get_current_user_time(
            user_id=self.user_id
        ).strftime("%Y-%m-%d %H:%M:%S")

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
                )
            else:
                response = requests.request(
                    method=method.upper(), url=url, headers=headers_dict
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

    async def convert_to_pdf(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to PDF.

        Args:
            markdown_content: The markdown content to convert
            output_file: File name for the output PDF file

        Returns:
            str: Success message with download link or error message

        Note: Do not include a path in the output_file, just the file name. The file will be saved in the agent's workspace and a link to download returned.
        """
        try:
            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )

            # Write the markdown content to the temp file
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Execute the conversion with pandoc
            process = await asyncio.create_subprocess_exec(
                "pandoc",
                temp_md,
                "-o",
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return f"Error: {stderr.decode()}"

            return f"Successfully converted to {self.output_url}{output_file}"

        except Exception as e:
            logging.error(f"Error converting to PDF: {str(e)}")
            return f"Error: {str(e)}"

    async def convert_to_docx(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to DOCX.

        Args:
            markdown_content: The markdown content to convert
            output_file: File name for the output DOCX file

        Returns:
            str: Success message with download link or error message

        Note: Do not include a path in the output_file, just the file name. The file will be saved in the agent's workspace and a link to download returned.
        """
        try:
            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )

            # Write the markdown content to the temp file
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Execute the conversion with pandoc
            process = await asyncio.create_subprocess_exec(
                "pandoc",
                temp_md,
                "-o",
                output_path,
                "-t",
                "docx",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return f"Error: {stderr.decode()}"

            return f"Successfully converted to {self.output_url}{output_file}"

        except Exception as e:
            logging.error(f"Error converting to DOCX: {str(e)}")
            return f"Error: {str(e)}"

    async def convert_to_xlsx(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to XLSX.

        Args:
            markdown_content: The markdown content to convert
            output_file: File name for the output XLSX file

        Returns:
            str: Success message with download link or error message

        Note: Do not include a path in the output_file, just the file name. The file will be saved in the agent's workspace and a link to download returned.
        """
        try:
            import pandas as pd

            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file for reference
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Process markdown content to extract tables
            lines = markdown_content.split("\n")

            # Find table sections (marked by | character)
            tables = []
            current_table = []

            for line in lines:
                if "|" in line:
                    cells = [cell.strip() for cell in line.split("|")]
                    # Remove empty cells from start/end that result from splitting
                    cells = [c for c in cells if c]
                    if cells:  # Only add non-empty rows
                        current_table.append(cells)
                elif current_table:
                    # We've reached the end of a table
                    if (
                        len(current_table) > 1
                    ):  # Only keep tables with at least header and one row
                        # First row is header, second is separator, rest is data
                        df = pd.DataFrame(current_table[2:], columns=current_table[0])
                        tables.append(df)
                    current_table = []

            # Check if we ended with a table
            if current_table and len(current_table) > 1:
                df = pd.DataFrame(current_table[2:], columns=current_table[0])
                tables.append(df)

            # If no tables found, create a simple one-column dataframe with content
            if not tables:
                df = pd.DataFrame({"Content": [line for line in lines if line.strip()]})
                tables = [df]

            # Create Excel writer with multiple sheets if needed
            with pd.ExcelWriter(output_path) as writer:
                if len(tables) == 1:
                    # Single table - use main sheet
                    tables[0].to_excel(writer, sheet_name="Sheet1", index=False)
                else:
                    # Multiple tables - use multiple sheets
                    for i, table in enumerate(tables):
                        table.to_excel(writer, sheet_name=f"Table {i+1}", index=False)

            return f"Successfully converted to {self.output_url}{output_file}"

        except Exception as e:
            logging.error(f"Error converting to XLSX: {str(e)}")
            return f"Error: {str(e)}"

    async def convert_to_pptx(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to PPTX.

        Args:
            markdown_content: The markdown content to convert
            output_file: File name for the output PPTX file

        Returns:
            str: Success message with download link or error message

        Note: Do not include a path in the output_file, just the file name. The file will be saved in the agent's workspace and a link to download returned.
        """
        try:
            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )

            # Write the markdown content to the temp file
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Execute the conversion with pandoc
            process = await asyncio.create_subprocess_exec(
                "pandoc",
                temp_md,
                "-o",
                output_path,
                "-t",
                "pptx",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return f"Error: {stderr.decode()}"

            return f"Successfully converted to {self.output_url}{output_file}"

        except Exception as e:
            logging.error(f"Error converting to PPTX: {str(e)}")
            return f"Error: {str(e)}"

    async def schedule_task(
        self,
        title: str,
        task_description: str,
        days: str = 0,
        hours: str = 0,
        minutes: str = 0,
    ) -> str:
        """
        Schedule a follow-up message to the user at a specific time in the future.
        Use this to proactively remind users, check on progress, or execute commands at scheduled times.
        Examples: reminding about deadlines, following up on tasks, scheduling automated reports, or checking in after a delay.
        At the scheduled time, the AI will message the user and can execute any available commands to complete the task.

        Args:
            title (str): Brief title describing the follow-up purpose (e.g., "Check project progress", "Send daily report")
            task_description (str): Detailed instructions for what the AI should do when following up, including specific commands to run and information to provide
            days (int): Number of days from now to schedule the follow-up
            hours (int): Number of hours from now to schedule the follow-up
            minutes (int): Number of minutes from now to schedule the follow-up

        Returns:
            str: Confirmation of the scheduled follow-up with the exact date/time
        """
        try:
            days = int(days)
        except:
            days = 0
        try:
            hours = int(hours)
        except:
            hours = 0
        try:
            minutes = int(minutes)
        except:
            minutes = 0
        # Calculate the due date from user's current time
        user_now = get_current_user_time(self.user_id)
        user_due_time = user_now + datetime.timedelta(
            days=days, hours=hours, minutes=minutes
        )

        # Convert to UTC for database storage
        due_date = convert_user_time_to_utc(user_due_time, self.user_id)

        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        # Create a descriptive title from the purpose of the follow-up
        title_preview = title.split("\n")[0][:50] + ("..." if len(title) > 50 else "")

        # Create the follow-up task
        task_id = await task_manager.create_task(
            title=title_preview,
            description=task_description,
            category_name="Follow-ups",
            agent_name=self.agent_name,
            due_date=due_date,
            priority=1,  # High priority for follow-ups
            memory_collection=self.conversation_id,  # This ensures context preservation
        )

        return f"Scheduled follow-up message (ID: {task_id}) for {due_date.strftime('%Y-%m-%d %H:%M:%S')}. I'll message you then to {title}."

    async def schedule_reoccurring_task(
        self,
        title: str,
        task_description: str,
        start_date: str,
        end_date: str,
        frequency: str = "daily",
    ) -> str:
        """
        Schedule recurring follow-up messages to the user on a regular basis.
        Use this for periodic check-ins, regular reports, repeated reminders, or any task that needs consistent follow-up.
        The AI will message the user at each scheduled interval and can execute commands to provide updates or perform actions.
        Perfect for daily summaries, weekly progress checks, or monthly reports.

        Args:
            title (str): Brief title for the recurring follow-up (e.g., "Daily standup check-in", "Weekly metrics report")
            task_description (str): What the AI should do at each follow-up, including commands to run and information to gather
            start_date (datetime.datetime): When to begin the recurring follow-ups
            end_date (datetime.datetime): When to stop the recurring follow-ups
            frequency (str): How often to follow up - "daily", "weekly", or "monthly"

        Returns:
            str: Confirmation of the recurring follow-up schedule
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        # Create a descriptive title from the purpose of the follow-up
        title_preview = title.split("\n")[0][:50] + ("..." if len(title) > 50 else "")

        # Create the follow-up task
        task_ids = await task_manager.create_reoccurring_task(
            title=title_preview,
            description=task_description,
            category_name="Follow-ups",
            agent_name=self.agent_name,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            priority=1,  # High priority for follow-ups
            memory_collection=self.conversation_id,  # This ensures context preservation
        )
        return f"Scheduled {frequency} follow-up messages from {start_date} to {end_date}. I'll check in regularly to {title}."

    async def modify_task(
        self,
        task_id: str,
        title: str = None,
        description: str = None,
        due_date: str = None,
        estimated_hours: str = None,
        priority: str = None,
        cancel_task: str = "false",
    ):
        """
        Modify or cancel a scheduled follow-up message.
        Use this to adjust timing, change what the AI should do at follow-up, update priorities, or cancel if no longer needed.
        This helps maintain relevant and timely follow-ups based on changing circumstances.

        Args:
            task_id (str): The ID of the scheduled follow-up to modify (obtained from Get Scheduled Follow-Ups)
            title (str): New title for the follow-up (optional)
            description (str): Updated instructions for what to do at follow-up (optional)
            due_date (datetime.datetime): New scheduled time for the follow-up (optional)
            estimated_hours (int): Updated time estimate (optional)
            priority (int): New priority level 1-5, where 1 is highest (optional)
            cancel_task (bool): Set to "true" to cancel the follow-up entirely

        Returns:
            str: Confirmation of the changes made
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        if str(cancel_task).lower() == "true":
            return await task_manager.delete_task(task_id)
        # Update the task
        return await task_manager.update_task(
            task_id=task_id,
            title=title,
            description=description,
            due_date=due_date,
            estimated_hours=estimated_hours,
            priority=priority,
        )

    async def get_scheduled_tasks(self):
        """
        Retrieve all scheduled follow-up messages for the current conversation.
        Use this to review upcoming follow-ups, check their timing, or find task IDs for modification.
        This helps ensure follow-ups are still relevant and properly scheduled.

        Returns:
            list: List of all scheduled follow-ups with their details, timing, and task IDs
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        # Get all tasks for the current agent
        tasks = await task_manager.get_pending_tasks()
        return tasks

    async def generate_image(self, prompt):
        """
        Generate an image from a prompt.

        Args:
            prompt (str): The prompt to generate the image from.

        Returns:
            str: Instructions with the image URL in markdown format.
        Note:
            The assistant should display the image to the user using the exact markdown syntax provided in the response.
        """
        from Agent import Agent

        image_url = await Agent(
            agent_id=self.agent_id,
            ApiClient=self.ApiClient,
            user=self.user,
        ).generate_image(prompt=prompt, conversation_id=self.conversation_id)

        return f"Image generated successfully. Display this image to the user using exactly this markdown (do not add anything before it): ![Generated Image]({image_url})"

    async def text_to_speech(self, text):
        """
        Convert text to speech. The assistant can use its voice to read the text aloud to the user.

        Args:
            text (str): The text to convert to speech.

        Returns:
            str: The URL of the generated audio.

        Note:
            The assistant should send the audio URL to the user so they can listen to it, it will embed the audio in the chat when the assistant sends the URL.
        """
        from Agent import Agent

        return await Agent(
            agent_id=self.agent_id,
            ApiClient=self.ApiClient,
            user=self.user,
        ).text_to_speech(text=text, conversation_id=self.conversation_id)

    async def create_todo_item(
        self,
        title: str,
        description: str,
        parent_id: str = None,
        depends_on: str = None,
    ) -> str:
        """
        Create a new todo item in the current conversation.

        Use this to break down complex tasks into manageable steps and track progress.
        Each todo item is linked to the current conversation for context.

        Args:
            title (str): A concise, action-oriented title for the todo item (3-7 words)
            description (str): Detailed description including context, requirements, file paths,
                             specific methods, or acceptance criteria
            parent_id (int, optional): ID of parent todo to create this as a sub-todo
            depends_on (str, optional): Comma-separated list of task IDs that must be completed first
                                      Example: "1,2,5" means tasks 1, 2, and 5 must be completed

        Returns:
            str: JSON response with success status and created todo item details

        Usage Guidelines:
        - Create todos for multi-step work requiring planning and tracking
        - Use descriptive titles that clearly indicate the action needed
        - Include comprehensive descriptions with all necessary context
        - Break down larger tasks into smaller, actionable steps
        - Create todos BEFORE starting work to ensure proper tracking
        - Use depends_on for sequential workflows: "1,2" means tasks 1&2 must complete first
        - Tasks without dependencies can run async/parallel
        - Use List Runnable Todos to see what can be started immediately

        When to use:
        - User provides multiple tasks or complex requests
        - Breaking down large projects into manageable pieces
        - Planning multi-step workflows or processes
        - Tracking progress on ongoing work
        """
        try:
            parent_id = int(parent_id) if parent_id is not None else None
        except ValueError:
            parent_id = None
        session = get_session()
        try:
            if not title.strip():
                return json.dumps({"success": False, "error": "Title cannot be empty"})

            if not description.strip():
                return json.dumps(
                    {"success": False, "error": "Description cannot be empty"}
                )

            # Validate dependencies if provided
            validated_depends_on = None
            if depends_on:
                try:
                    dep_ids = [
                        int(id.strip()) for id in depends_on.split(",") if id.strip()
                    ]
                    if dep_ids:
                        # Verify all dependency todos exist and belong to this conversation
                        existing_deps = (
                            session.query(EssentialTodo)
                            .filter(
                                EssentialTodo.id.in_(dep_ids),
                                EssentialTodo.conversation_id == self.conversation_id,
                            )
                            .count()
                        )
                        if existing_deps != len(dep_ids):
                            return json.dumps(
                                {
                                    "success": False,
                                    "error": f"One or more dependency tasks not found in this conversation",
                                }
                            )
                        validated_depends_on = ",".join(str(id) for id in dep_ids)
                except ValueError:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Invalid depends_on format. Use comma-separated task IDs like '1,2,5'",
                        }
                    )

            # Validate parent_id if provided
            if parent_id is not None:
                parent_todo = (
                    session.query(EssentialTodo)
                    .filter(
                        EssentialTodo.id == parent_id,
                        EssentialTodo.conversation_id == self.conversation_id,
                    )
                    .first()
                )
                if not parent_todo:
                    return json.dumps(
                        {"success": False, "error": "Parent todo not found"}
                    )

            # Create new todo item
            todo = EssentialTodo(
                conversation_id=self.conversation_id,
                parent_id=parent_id,
                title=title.strip(),
                description=description.strip(),
                status="not-started",
                depends_on=validated_depends_on,
            )

            session.add(todo)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": "Todo item created successfully",
                    "todo": todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def create_sub_todo_item(
        self, parent_todo_id: str, title: str, description: str, depends_on: str = None
    ) -> str:
        """
        Create a new sub-todo item under an existing parent todo.

        Sub-todos are useful for breaking down complex tasks into smaller, more manageable steps.
        They are linked to a parent todo and can be managed independently while maintaining hierarchy.

        Args:
            parent_todo_id (int): The ID of the parent todo to attach this sub-todo to
            title (str): A concise, action-oriented title for the sub-todo item
            description (str): Detailed description of the sub-task
            depends_on (str, optional): Comma-separated list of task IDs that must be completed first

        Returns:
            str: JSON response with success status and created sub-todo details

        Usage Guidelines:
        - Use when a main todo has multiple distinct sub-tasks
        - Sub-todos can have their own status independent of parent
        - Helps organize complex workflows hierarchically
        - Parent todo remains visible even when sub-todos are completed

        When to use:
        - Breaking down large tasks into specific steps
        - When a todo has multiple components that can be tracked separately
        - Creating detailed checklists for complex processes
        - Organizing multi-phase work within a larger task
        """
        try:
            parent_id = int(parent_todo_id)
        except ValueError:
            parent_id = None
        session = get_session()
        try:
            if not title.strip():
                return json.dumps({"success": False, "error": "Title cannot be empty"})

            if not description.strip():
                return json.dumps(
                    {"success": False, "error": "Description cannot be empty"}
                )

            # Validate parent todo exists
            parent_todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == parent_todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not parent_todo:
                return json.dumps({"success": False, "error": "Parent todo not found"})

            # Validate dependencies if provided
            validated_depends_on = None
            if depends_on:
                try:
                    dep_ids = [
                        int(id.strip()) for id in depends_on.split(",") if id.strip()
                    ]
                    if dep_ids:
                        # Verify all dependency todos exist and belong to this conversation
                        existing_deps = (
                            session.query(EssentialTodo)
                            .filter(
                                EssentialTodo.id.in_(dep_ids),
                                EssentialTodo.conversation_id == self.conversation_id,
                            )
                            .count()
                        )
                        if existing_deps != len(dep_ids):
                            return json.dumps(
                                {
                                    "success": False,
                                    "error": f"One or more dependency tasks not found in this conversation",
                                }
                            )
                        validated_depends_on = ",".join(str(id) for id in dep_ids)
                except ValueError:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Invalid depends_on format. Use comma-separated task IDs like '1,2,5'",
                        }
                    )

            # Create new sub-todo item
            sub_todo = EssentialTodo(
                conversation_id=self.conversation_id,
                parent_id=parent_todo_id,
                title=title.strip(),
                description=description.strip(),
                status="not-started",
                depends_on=validated_depends_on,
            )

            session.add(sub_todo)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Sub-todo item created successfully under '{parent_todo.title}'",
                    "sub_todo": sub_todo.to_dict(),
                    "parent_todo": parent_todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def create_todo_items_bulk(
        self,
        todo_1_title: str = "",
        todo_1_description: str = "",
        todo_2_title: str = "",
        todo_2_description: str = "",
        todo_3_title: str = "",
        todo_3_description: str = "",
        todo_4_title: str = "",
        todo_4_description: str = "",
        todo_5_title: str = "",
        todo_5_description: str = "",
        todo_6_title: str = "",
        todo_6_description: str = "",
        todo_7_title: str = "",
        todo_7_description: str = "",
        todo_8_title: str = "",
        todo_8_description: str = "",
        todo_9_title: str = "",
        todo_9_description: str = "",
        todo_10_title: str = "",
        todo_10_description: str = "",
    ) -> str:
        """
        Create multiple todo items in bulk (up to 10 at once).

        Use this when breaking down complex tasks into multiple actionable steps.
        Only fill in as many todo items as needed - empty title/description pairs will be ignored.
        This is much more efficient than creating todos individually when you have multiple tasks.

        Args:
            todo_1_title to todo_10_title (str): Titles for up to 10 todo items
            todo_1_description to todo_10_description (str): Descriptions for up to 10 todo items

        Returns:
            str: JSON response with success status and created todo items details

        Usage Guidelines:
        - Use when you have 2-10 related tasks to create at once
        - Only fill in the todo pairs you need (1-10)
        - Leave unused title/description parameters empty
        - Perfect for breaking down user requests into actionable steps
        - More efficient than multiple individual create_todo_item calls

        When to use:
        - User provides a complex multi-step request
        - Breaking down projects into manageable tasks
        - Planning workflows that require multiple steps
        - Initial task planning for new projects

        Example:
        - todo_1_title="Read requirements", todo_1_description="Review user specifications..."
        - todo_2_title="Design architecture", todo_2_description="Create system design..."
        - Leave todo_3_title="" and beyond if only 2 tasks needed
        """
        session = get_session()
        try:
            # Collect all the todo pairs into a list
            todo_pairs = [
                (todo_1_title, todo_1_description),
                (todo_2_title, todo_2_description),
                (todo_3_title, todo_3_description),
                (todo_4_title, todo_4_description),
                (todo_5_title, todo_5_description),
                (todo_6_title, todo_6_description),
                (todo_7_title, todo_7_description),
                (todo_8_title, todo_8_description),
                (todo_9_title, todo_9_description),
                (todo_10_title, todo_10_description),
            ]

            # Filter out empty pairs and validate
            valid_todos = []
            for i, (title, description) in enumerate(todo_pairs, 1):
                # Skip if both are None or empty
                if not title or not description:
                    if title or description:
                        # One is filled but not the other
                        return json.dumps(
                            {
                                "success": False,
                                "error": f"Todo {i}: Both title and description must be provided or both must be empty",
                            }
                        )
                    continue

                # Strip and validate
                title_stripped = title.strip()
                description_stripped = description.strip()

                if title_stripped and description_stripped:
                    valid_todos.append((title_stripped, description_stripped))
                elif title_stripped or description_stripped:
                    # One is filled but not the other after stripping
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Todo {i}: Both title and description must be provided or both must be empty",
                        }
                    )

            if not valid_todos:
                return json.dumps(
                    {
                        "success": False,
                        "error": "At least one todo item (title and description) must be provided",
                    }
                )

            # Create all the todo items
            created_todos = []
            for title, description in valid_todos:
                todo = EssentialTodo(
                    conversation_id=self.conversation_id,
                    title=title,
                    description=description,
                    status="not-started",
                )
                session.add(todo)
                created_todos.append(todo)

            session.commit()

            # Convert to dict format for response
            created_todos_dict = [todo.to_dict() for todo in created_todos]

            return json.dumps(
                {
                    "success": True,
                    "message": f"Successfully created {len(created_todos)} todo items",
                    "todos": created_todos_dict,
                    "count": len(created_todos),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_current_todos(self, include_completed: bool = False) -> str:
        """
        List all todo items for the current conversation.

        Use this to get an overview of all tasks and their current status.
        Helps track progress and identify what work remains.

        Args:
            include_completed (bool): Whether to include completed todos in the list

        Returns:
            str: JSON response with list of todos and summary statistics

        Usage Guidelines:
        - Use this frequently to stay aware of current tasks
        - Check before starting work to prioritize properly
        - Review regularly to track overall progress
        - Use to identify bottlenecks or stalled tasks
        """
        session = get_session()
        try:
            # Build query based on completion filter
            query = session.query(EssentialTodo).filter(
                EssentialTodo.conversation_id == self.conversation_id
            )

            if not include_completed:
                query = query.filter(EssentialTodo.status != "completed")

            todos = query.order_by(EssentialTodo.created_at).all()

            # Generate summary statistics
            total_count = len(todos)
            completed_count = sum(1 for todo in todos if todo.status == "completed")
            in_progress_count = sum(1 for todo in todos if todo.status == "in-progress")
            not_started_count = sum(1 for todo in todos if todo.status == "not-started")

            # Convert todos to dict format with hierarchy
            parent_todos = [todo for todo in todos if todo.parent_id is None]
            child_todos = [todo for todo in todos if todo.parent_id is not None]

            # Build hierarchical structure
            todo_list = []
            for parent in parent_todos:
                parent_dict = parent.to_dict()
                # Find children for this parent
                children = [
                    child.to_dict()
                    for child in child_todos
                    if child.parent_id == parent.id
                ]
                parent_dict["sub_todos"] = children
                parent_dict["sub_todo_count"] = len(children)
                todo_list.append(parent_dict)

            # Add any orphaned children (shouldn't happen but just in case)
            for child in child_todos:
                if not any(p.id == child.parent_id for p in parent_todos):
                    child_dict = child.to_dict()
                    child_dict["sub_todos"] = []
                    child_dict["sub_todo_count"] = 0
                    todo_list.append(child_dict)

            summary = {
                "total": total_count,
                "completed": completed_count,
                "in_progress": in_progress_count,
                "not_started": not_started_count,
                "parent_todos": len(parent_todos),
                "sub_todos": len(child_todos),
            }

            # Find currently active todo
            active_todo = None
            for todo in todos:
                if todo.status == "in-progress":
                    active_todo = todo.to_dict()
                    break

            return json.dumps(
                {
                    "success": True,
                    "todos": todo_list,
                    "summary": summary,
                    "active_todo": active_todo,
                }
            )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_runnable_todos(self, include_completed: bool = False) -> str:
        """
        List all todo items that can be started now (no incomplete dependencies).

        Use this to identify which tasks are ready to work on based on their dependencies.
        Tasks without dependencies or with all dependencies completed will be included.

        Args:
            include_completed (bool): Whether to include completed todos in the results

        Returns:
            str: JSON response with runnable todos and their status

        Usage Guidelines:
        - Use to identify next actionable tasks in complex workflows
        - Helps prioritize work when tasks have dependencies
        - Shows only tasks that can be started immediately
        - Useful for async task execution planning
        """
        session = get_session()
        try:
            # Get all todos for this conversation
            query = session.query(EssentialTodo).filter(
                EssentialTodo.conversation_id == self.conversation_id
            )

            if not include_completed:
                query = query.filter(EssentialTodo.status != "completed")

            all_todos = query.order_by(EssentialTodo.created_at).all()

            # Filter to only runnable todos (no incomplete dependencies)
            runnable_todos = []
            for todo in all_todos:
                if todo._can_start():
                    runnable_todos.append(todo)

            # Generate summary
            total_runnable = len(runnable_todos)
            not_started = len([t for t in runnable_todos if t.status == "not-started"])
            in_progress = len([t for t in runnable_todos if t.status == "in-progress"])
            completed = len([t for t in runnable_todos if t.status == "completed"])

            response = {
                "success": True,
                "total_runnable": total_runnable,
                "runnable_todos": [todo.to_dict() for todo in runnable_todos],
                "summary": {
                    "not_started": not_started,
                    "in_progress": in_progress,
                    "completed": completed,
                },
            }

            return json.dumps(response, indent=2)

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_sub_todos(self, parent_todo_id: str) -> str:
        """
        List all sub-todo items for a specific parent todo.

        Use this to focus on the sub-tasks of a particular todo item.
        Helpful when working through the details of a complex task.

        Args:
            parent_todo_id (int): The ID of the parent todo to list sub-todos for

        Returns:
            str: JSON response with sub-todos list and parent todo details

        Usage Guidelines:
        - Use when you need to see all sub-tasks for a specific parent
        - Helpful for planning work on a complex todo
        - Shows the breakdown of a larger task
        - Provides focused view of related sub-tasks
        """
        try:
            parent_todo_id = int(parent_todo_id)
        except ValueError:
            parent_todo_id = None
        session = get_session()
        try:
            # Verify parent todo exists and belongs to this conversation
            parent_todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == parent_todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not parent_todo:
                return json.dumps({"success": False, "error": "Parent todo not found"})

            # Get all sub-todos for this parent
            sub_todos = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.parent_id == parent_todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .order_by(EssentialTodo.created_at)
                .all()
            )

            # Generate statistics for sub-todos
            total_count = len(sub_todos)
            completed_count = sum(1 for todo in sub_todos if todo.status == "completed")
            in_progress_count = sum(
                1 for todo in sub_todos if todo.status == "in-progress"
            )
            not_started_count = sum(
                1 for todo in sub_todos if todo.status == "not-started"
            )

            # Convert to dict format
            sub_todo_list = [todo.to_dict() for todo in sub_todos]

            # Find active sub-todo
            active_sub_todo = None
            for todo in sub_todos:
                if todo.status == "in-progress":
                    active_sub_todo = todo.to_dict()
                    break

            return json.dumps(
                {
                    "success": True,
                    "parent_todo": parent_todo.to_dict(),
                    "sub_todos": sub_todo_list,
                    "summary": {
                        "total": total_count,
                        "completed": completed_count,
                        "in_progress": in_progress_count,
                        "not_started": not_started_count,
                    },
                    "active_sub_todo": active_sub_todo,
                }
            )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def mark_todo_completed(self, todo_id: str) -> str:
        """
        Mark a todo item as completed.

        Use this immediately after finishing work on a todo item.
        This helps track progress and keeps the todo list current.

        Args:
            todo_id (int): The unique ID of the todo item to mark as completed

        Returns:
            str: JSON response with success status and updated todo details

        Usage Guidelines:
        - Mark todos as completed IMMEDIATELY when finished
        - Don't batch completions - update as you go
        - This helps maintain accurate progress tracking
        - Completed todos provide a record of work done
        """
        try:
            todo_id = int(todo_id)
        except ValueError:
            todo_id = None
        session = get_session()
        try:
            todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not todo:
                return json.dumps({"success": False, "error": "Todo item not found"})

            todo.status = "completed"
            todo.updated_at = datetime.datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Todo '{todo.title}' marked as completed",
                    "todo": todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def mark_todo_incomplete(
        self, todo_id: str, status: str = "not-started"
    ) -> str:
        """
        Mark a todo item as incomplete (either not-started or in-progress).

        Use this to revert completed todos or update status when starting work.
        Only one todo can be in-progress at a time.

        Args:
            todo_id (int): The unique ID of the todo item to update
            status (str): The new status - either "not-started" or "in-progress"

        Returns:
            str: JSON response with success status and updated todo details

        Usage Guidelines:
        - Mark as "in-progress" when starting work on a todo
        - Only one todo should be "in-progress" at a time
        - Use "not-started" to reset a todo back to initial state
        - Change status before beginning work for proper tracking
        """
        try:
            todo_id = int(todo_id)
        except ValueError:
            todo_id = None
        session = get_session()
        try:
            if status not in ["not-started", "in-progress"]:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Status must be either 'not-started' or 'in-progress'",
                    }
                )

            # If setting to in-progress, ensure no other todo is in-progress
            if status == "in-progress":
                existing_in_progress = (
                    session.query(EssentialTodo)
                    .filter(
                        EssentialTodo.conversation_id == self.conversation_id,
                        EssentialTodo.status == "in-progress",
                        EssentialTodo.id != todo_id,
                    )
                    .first()
                )

                if existing_in_progress:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Another todo is already in-progress: '{existing_in_progress.title}'",
                        }
                    )

            todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not todo:
                return json.dumps({"success": False, "error": "Todo item not found"})

            old_status = todo.status
            todo.status = status
            todo.updated_at = datetime.datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Todo '{todo.title}' status changed from '{old_status}' to '{status}'",
                    "todo": todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def update_todo_item(
        self, todo_id: str, title: str = None, description: str = None
    ) -> str:
        """
        Update the title or description of an existing todo item.

        Use this when requirements change or you need to clarify a todo item.
        Helps keep todos accurate and up-to-date.

        Args:
            todo_id (int): The unique ID of the todo item to update
            title (str, optional): New title for the todo item
            description (str, optional): New description for the todo item

        Returns:
            str: JSON response with success status and updated todo details

        Usage Guidelines:
        - Update todos when requirements become clearer
        - Refine descriptions as you learn more about the task
        - Keep titles concise and action-oriented
        - Update when scope or approach changes
        """
        try:
            todo_id = int(todo_id)
        except ValueError:
            todo_id = None
        session = get_session()
        try:
            todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not todo:
                return json.dumps({"success": False, "error": "Todo item not found"})

            updates = []
            if title is not None and title.strip():
                todo.title = title.strip()
                updates.append("title")

            if description is not None and description.strip():
                todo.description = description.strip()
                updates.append("description")

            if not updates:
                return json.dumps(
                    {"success": False, "error": "No valid updates provided"}
                )

            todo.updated_at = datetime.datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Todo '{todo.title}' updated successfully ({', '.join(updates)} changed)",
                    "todo": todo.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def delete_todo_item(self, todo_id: str) -> str:
        """
        Delete a todo item permanently.

        Use this to remove todos that are no longer relevant or were created in error.
        This action cannot be undone.

        Args:
            todo_id (int): The unique ID of the todo item to delete

        Returns:
            str: JSON response with success status and confirmation

        Usage Guidelines:
        - Only delete todos that are completely irrelevant
        - Consider marking as completed instead of deleting
        - Use when requirements change and the todo is no longer needed
        - Be cautious - this action cannot be undone
        """
        try:
            todo_id = int(todo_id)
        except ValueError:
            todo_id = None
        session = get_session()
        try:
            todo = (
                session.query(EssentialTodo)
                .filter(
                    EssentialTodo.id == todo_id,
                    EssentialTodo.conversation_id == self.conversation_id,
                )
                .first()
            )

            if not todo:
                return json.dumps({"success": False, "error": "Todo item not found"})

            title = todo.title  # Store for confirmation message
            session.delete(todo)
            session.commit()

            return json.dumps(
                {"success": True, "message": f"Todo '{title}' deleted successfully"}
            )

        except Exception as e:
            session.rollback()
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def run_todo_list(
        self,
        max_concurrent: str = "3",
        auto_complete: bool = True,
        execution_agent: str = None,
    ) -> str:
        """
        Execute runnable todos asynchronously using background threads with prompt_agent calls.

        This command identifies todos that can be started immediately (no incomplete dependencies)
        and executes them as background threads. Each thread makes a prompt_agent call to execute
        the task. Tasks without dependencies can run in parallel up to max_concurrent limit.

        Args:
            max_concurrent (int): Maximum number of todos to run concurrently (default: 3)
            auto_complete (bool): Whether to automatically mark todos as completed after successful execution (default: True)
            execution_agent (str, optional): Specific agent to use for execution. If None, uses current agent.

        Returns:
            str: JSON response with execution status and running thread information

        Usage Guidelines:
        - Use for executing planned workflows automatically
        - Tasks run in background threads using direct prompt_agent calls
        - Dependencies are respected - dependent tasks wait for prerequisites
        - Monitor progress with List Current Todos to see status updates
        - Use max_concurrent to control resource usage
        - Each thread executes the task description as a prompt

        Threading Execution:
        - Identifies all runnable todos (no incomplete dependencies)
        - Starts up to max_concurrent threads in parallel
        - Each thread makes a prompt_agent call via existing ApiClient
        - Tasks auto-complete if auto_complete is enabled
        - Continues until all possible tasks are running or completed
        """
        try:
            max_concurrent = int(max_concurrent)
        except ValueError:
            max_concurrent = 3
        session = get_session()
        try:
            # Get all runnable todos
            runnable_response = await self.list_runnable_todos(include_completed=False)
            runnable_data = json.loads(runnable_response)

            if not runnable_data.get("success"):
                return json.dumps(
                    {"success": False, "error": "Failed to get runnable todos"}
                )

            runnable_todos = runnable_data.get("runnable_todos", [])

            if not runnable_todos:
                return json.dumps(
                    {
                        "success": True,
                        "message": "No runnable todos found",
                        "running_tasks": [],
                        "total_started": 0,
                    }
                )

            # Filter to only not-started todos (don't re-run in-progress)
            pending_todos = [
                todo for todo in runnable_todos if todo.get("status") == "not-started"
            ]

            if not pending_todos:
                return json.dumps(
                    {
                        "success": True,
                        "message": "All runnable todos are already in progress or completed",
                        "running_tasks": [],
                        "total_started": 0,
                    }
                )

            # Limit by max_concurrent
            todos_to_start = pending_todos[:max_concurrent]

            started_tasks = []
            agent_to_use = execution_agent or self.agent_name

            def execute_todo_task(
                todo_id, title, description, agent_name, auto_complete_flag
            ):
                """Execute a single todo task in a separate thread"""
                try:
                    # Create the prompt for the agent
                    prompt = f"""Execute the following task:

Task: {title}

Description: {description}

Instructions:
- Complete the task as described
- Provide detailed output of what was accomplished
- If the task involves code, include the code and execution results
- If the task involves files, mention which files were created/modified
- If the task encounters errors, provide debugging information

Execute this task thoroughly and report on the completion."""

                    # Execute the prompt with the agent using the existing ApiClient
                    response = self.ApiClient.prompt_agent(
                        agent_name=agent_name,
                        prompt_name="Think About It",
                        prompt_args={
                            "user_input": prompt,
                            "conversation_name": self.conversation_name,
                            "disable_commands": False,
                            "running_command": "Run Todo List",
                            "log_user_input": False,
                            "log_output": False,
                            "tts": False,
                        },
                    )
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}] {response}",
                        conversation_name=self.conversation_name,
                    )

                    logging.info(
                        f"Todo {todo_id} ({title}) completed with response: {response}"
                    )

                    # Auto-complete the todo if requested
                    if auto_complete_flag:
                        # We need to run this in the event loop since it's async
                        import asyncio

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            session = get_session()
                            todo = (
                                session.query(EssentialTodo)
                                .filter_by(id=todo_id)
                                .first()
                            )
                            if todo:
                                todo.status = "completed"
                                todo.updated_at = datetime.datetime.utcnow()
                                session.commit()
                            session.close()
                        except Exception as e:
                            logging.error(
                                f"Failed to auto-complete todo {todo_id}: {str(e)}"
                            )
                        finally:
                            loop.close()

                except Exception as e:
                    logging.error(f"Error executing todo {todo_id}: {str(e)}")
                    # Try to revert status back to not-started
                    try:
                        session = get_session()
                        todo = (
                            session.query(EssentialTodo).filter_by(id=todo_id).first()
                        )
                        if todo:
                            todo.status = "not-started"
                            todo.updated_at = datetime.datetime.utcnow()
                            session.commit()
                        session.close()
                    except Exception as revert_e:
                        logging.error(
                            f"Failed to revert todo {todo_id} status: {str(revert_e)}"
                        )

            # Start each todo as a background thread
            for todo in todos_to_start:
                todo_id = todo.get("id")
                title = todo.get("title")
                description = todo.get("description")

                try:
                    # Mark todo as in-progress first
                    await self.mark_todo_incomplete(
                        todo_id=todo_id, status="in-progress"
                    )

                    # Start the task in a separate thread
                    thread = threading.Thread(
                        target=execute_todo_task,
                        args=(todo_id, title, description, agent_to_use, auto_complete),
                        daemon=True,
                        name=f"TodoTask-{todo_id}",
                    )
                    thread.start()

                    # Store task info for tracking
                    started_tasks.append(
                        {
                            "todo_id": todo_id,
                            "title": title,
                            "thread_name": thread.name,
                            "agent": agent_to_use,
                            "status": "started",
                            "auto_complete": auto_complete,
                        }
                    )

                except Exception as e:
                    logging.error(f"Failed to start todo {todo_id}: {str(e)}")
                    # Revert status back to not-started if thread creation failed
                    await self.mark_todo_incomplete(
                        todo_id=todo_id, status="not-started"
                    )
                    continue

            return json.dumps(
                {
                    "success": True,
                    "message": f"Started {len(started_tasks)} todo tasks in background threads",
                    "running_tasks": started_tasks,
                    "total_started": len(started_tasks),
                    "max_concurrent": max_concurrent,
                    "auto_complete": auto_complete,
                    "execution_agent": agent_to_use,
                    "guidance": "Use 'List Current Todos' to monitor progress. Tasks marked as 'in-progress' are currently executing in background threads.",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    # ==================== Context Management Commands ====================
    # These commands help manage context window size by allowing the agent to
    # discard detailed context that has been noted/summarized, and retrieve it
    # later if needed. This helps keep context under 32k tokens for best quality.

    async def discard_context(self, message_id: str, reason: str) -> str:
        """
        Discard a message/activity from context to reduce token usage.

        Use this when you've read a file or activity and taken notes about what's important,
        or when content wasn't valuable enough to keep in full context. The original content
        is stored and can be retrieved later if needed.

        **WHEN TO USE:**
        - After reading a file and noting the important parts
        - When a file/activity content wasn't valuable for the current task
        - When approaching high token counts (~30k+) and need to free up context space
        - To keep context focused on relevant information only

        Args:
            message_id (str): The ID of the message/activity to discard from context
            reason (str): Brief reason for discarding (e.g., "noted key functions", "empty config file", "irrelevant to task")

        Returns:
            str: JSON response confirming the discard with the message ID for later retrieval

        Usage Guidelines:
        - Keep reasons concise (under 50 chars ideally)
        - The reason becomes the summary shown in context
        - Original content can be retrieved with "Retrieve Context" command
        - Consider discarding older activities when context grows large
        """
        from DB import get_session, Message, DiscardedContext, Conversation

        session = get_session()
        try:
            # Validate the message exists and belongs to this conversation
            message = session.query(Message).filter(Message.id == message_id).first()

            if not message:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Message with ID {message_id} not found",
                    }
                )

            # Check if already discarded
            existing = (
                session.query(DiscardedContext)
                .filter(
                    DiscardedContext.message_id == message_id,
                    DiscardedContext.is_active == True,
                )
                .first()
            )

            if existing:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Message {message_id} is already discarded",
                        "discarded_at": (
                            existing.discarded_at.isoformat()
                            if existing.discarded_at
                            else None
                        ),
                        "reason": existing.reason,
                    }
                )

            # Store the original content and create discard record
            discarded = DiscardedContext(
                message_id=message_id,
                conversation_id=message.conversation_id,
                reason=reason[:500],  # Limit reason length
                original_content=message.content,
            )
            session.add(discarded)

            # Update the message content to show it was discarded with reason
            # Format: [DISCARDED:{id}] {reason}
            original_prefix = ""
            if message.content.startswith("[ACTIVITY]"):
                original_prefix = "[ACTIVITY] "
            elif message.content.startswith("[SUBACTIVITY]"):
                # Preserve the subactivity ID format
                parts = message.content.split("]", 2)
                if len(parts) >= 2:
                    original_prefix = f"{parts[0]}]{parts[1]}] "

            message.content = f"{original_prefix}[DISCARDED:{message_id}] {reason}"
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Context discarded successfully",
                    "message_id": str(message_id),
                    "reason": reason,
                    "retrieval_hint": f"Use 'Retrieve Context' with message_id '{message_id}' to restore if needed",
                }
            )

        except Exception as e:
            session.rollback()
            logging.error(f"Error discarding context: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def retrieve_context(self, message_id: str) -> str:
        """
        Retrieve previously discarded context back into the conversation.

        Use this when you need to see the full content of something you previously
        discarded. The original content will be restored to the message.

        **WHEN TO USE:**
        - When you need details from something you previously summarized
        - When the user asks about something you discarded
        - When you realize discarded content is actually relevant

        Args:
            message_id (str): The ID of the discarded message to retrieve

        Returns:
            str: JSON response with the original content and restoration status

        Usage Guidelines:
        - Only retrieve what you actually need
        - Content is fully restored to the conversation
        - The discard record is marked inactive but kept for history
        """
        from DB import get_session, Message, DiscardedContext

        session = get_session()
        try:
            # Find the discard record
            discarded = (
                session.query(DiscardedContext)
                .filter(
                    DiscardedContext.message_id == message_id,
                    DiscardedContext.is_active == True,
                )
                .first()
            )

            if not discarded:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"No active discarded context found for message ID {message_id}. It may have already been retrieved or was never discarded.",
                    }
                )

            # Restore the original content
            message = session.query(Message).filter(Message.id == message_id).first()
            if message:
                message.content = discarded.original_content

            # Mark the discard as retrieved
            discarded.is_active = False
            discarded.retrieved_at = datetime.datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": "Context retrieved and restored successfully",
                    "message_id": str(message_id),
                    "original_content": discarded.original_content,
                    "was_discarded_at": (
                        discarded.discarded_at.isoformat()
                        if discarded.discarded_at
                        else None
                    ),
                    "original_reason": discarded.reason,
                }
            )

        except Exception as e:
            session.rollback()
            logging.error(f"Error retrieving context: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_discarded_context(self, include_retrieved: bool = False) -> str:
        """
        List all discarded context items for the current conversation.

        Use this to see what has been discarded and decide if anything needs
        to be retrieved back.

        Args:
            include_retrieved (bool): Whether to include items that were already retrieved back

        Returns:
            str: JSON response with list of discarded items and their reasons

        Usage Guidelines:
        - Review periodically to ensure nothing important was discarded
        - Check before asking user for information you might have discarded
        - Use message_id from results to retrieve specific items
        """
        from DB import get_session, DiscardedContext

        session = get_session()
        try:
            query = session.query(DiscardedContext).filter(
                DiscardedContext.conversation_id == self.conversation_id
            )

            if not include_retrieved:
                query = query.filter(DiscardedContext.is_active == True)

            discarded_items = query.order_by(DiscardedContext.discarded_at.desc()).all()

            items = []
            for item in discarded_items:
                items.append(
                    {
                        "message_id": str(item.message_id),
                        "reason": item.reason,
                        "discarded_at": (
                            item.discarded_at.isoformat() if item.discarded_at else None
                        ),
                        "is_active": item.is_active,
                        "retrieved_at": (
                            item.retrieved_at.isoformat() if item.retrieved_at else None
                        ),
                        "content_preview": (
                            item.original_content[:200] + "..."
                            if len(item.original_content) > 200
                            else item.original_content
                        ),
                    }
                )

            active_count = sum(1 for i in items if i["is_active"])
            retrieved_count = sum(1 for i in items if not i["is_active"])

            return json.dumps(
                {
                    "success": True,
                    "discarded_items": items,
                    "summary": {
                        "active_discards": active_count,
                        "retrieved": retrieved_count,
                        "total": len(items),
                    },
                }
            )

        except Exception as e:
            logging.error(f"Error listing discarded context: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def create_new_agixt_agent(
        self,
        agent_name: str,
        responsibilities_and_goals: str,
        training_files: str = "",
        training_urls: str = "",
    ) -> str:
        """
        Create a specialized expert agent by cloning yourself and granting it domain-specific knowledge and abilities.

        Args:
            agent_name (str): The expert's name - should indicate their specialty (e.g., "MarketingExpert", "PythonCodeReviewer", "DataScientist")
            responsibilities_and_goals (str): What makes this agent an expert - their domain, responsibilities, and what they excel at. Be specific about their expertise area.
            training_files (str): Optional comma-separated filenames from workspace with domain knowledge (e.g., "style_guide.pdf,best_practices.md")
            training_urls (str): Optional comma-separated URLs to domain resources (e.g., "https://docs.python.org,https://pep8.org")

        Returns:
            str: Complete summary of the expert agent created, including their specialization, abilities, and how to delegate work to them

        **WHEN TO USE THIS COMMAND:**
        Use this when you need a domain expert that doesn't exist yet - a specialist who can handle specific types of tasks
        better than a generalist. This implements a "mixture of experts" approach where you become the orchestrator who
        "knows a guy" for every specialized need.

        **IMPORTANT - GATHER RESOURCES FIRST:**
        Before creating the expert agent, review your current conversation's workspace for any files or resources that would
        be valuable training data for the new expert. For example:
        - User uploaded a financial spreadsheet → Include it in training_files for your "ExpensesExpert"
        - User provided style guidelines → Include them for your "ContentWriter" expert
        - You generated analysis documents → Pass them to specialists who need that context

        Think like delegating work: if you (the VP) need a manager to handle something, you'd give them all relevant documents
        and context upfront. The expert agents you create are your managers - equip them with the resources they need to succeed.

        **WHY CREATE EXPERT AGENTS:**
        - **Focus Through Isolation**: Each expert has specialized context without pollution from unrelated domains
        - **Reduced Cognitive Load**: Domain experts maintain concentrated knowledge rather than spreading thin across all topics
        - **Delegatable Expertise**: You gain the ability to delegate specialized work to purpose-built collaborators
        - **Scalable Specialization**: Create as many experts as needed - marketing guru, coding wizard, data scientist, legal advisor, etc.
        - **Context Efficiency**: Experts work within their domain's context, making them faster and more accurate than generalists
        - **Always Available**: Your expert agents are persistent - once created, they're always ready to help

        **THE ORCHESTRATOR PATTERN:**
        You (the agent creating other agents) become the orchestrator - the one who knows which expert to consult for any given task.
        When a user needs marketing help, you ask your Marketing Expert. When they need code reviewed, you consult your Code Reviewer.
        You don't need to be the expert at everything - you just need to know which expert to create or consult.

        This mirrors organizational hierarchy:
        - **User = CEO**: Sets high-level goals and requests
        - **You (AI) = VP**: Receives requests and delegates to specialized managers
        - **Expert Agents = Managers**: Handle specific domains with deep expertise

        When the CEO asks the VP for something, the VP often consults managers beneath them. Similarly, when users ask you for
        specialized work, you create or consult expert agents. The experts can even be consulted "silently" - you delegate to
        them, they provide their specialized analysis, and you integrate it into your response to the user seamlessly.

        **HOW IT WORKS:**
        1. Clones your current configuration (settings, provider, base knowledge)
        2. AI intelligently selects specialized commands based on the expert's domain
        3. AI expands basic responsibilities into comprehensive expert-level guidance
        4. Trains the expert with domain-specific files and resources
        5. Creates an "Ask {agent_name}" command so you can delegate to this expert anytime
        6. Returns the expert ready to handle their specialized domain

        **EXPERT AGENT EXAMPLES:** (Just examples, the assistant can create any kind of expert at anything.)

        Marketing Expert:
            agent_name="MarketingExpert"
            responsibilities_and_goals="Expert in digital marketing strategy, SEO optimization, content marketing, social media campaigns,
            and conversion rate optimization. Analyzes market trends, creates compelling copy, and develops data-driven marketing plans."
            training_files="brand_guidelines.pdf,competitor_analysis.xlsx"  # From workspace if available

        Python Code Reviewer:
            agent_name="PythonCodeReviewer"
            responsibilities_and_goals="Expert Python developer specializing in code review, PEP8 compliance, security auditing,
            performance optimization, and architectural patterns. Identifies bugs, suggests refactoring, and ensures best practices."
            training_files="coding_standards.md,architecture_docs.pdf"  # From workspace if available

        Data Scientist:
            agent_name="DataScientist"
            responsibilities_and_goals="Expert in statistical analysis, machine learning, data visualization, and predictive modeling.
            Analyzes datasets, builds models, creates visualizations, and provides actionable insights from data."
            training_files="quarterly_sales.csv,customer_demographics.xlsx"  # From workspace if user uploaded data

        Legal Research Assistant:
            agent_name="LegalResearcher"
            responsibilities_and_goals="Expert in legal research, case law analysis, contract review, and regulatory compliance.
            Researches precedents, summarizes legal documents, and identifies relevant statutes and regulations."
            training_files="contract_templates.pdf,compliance_requirements.docx"  # From workspace if available

        Financial Analyst:
            agent_name="FinancialAnalyst"
            responsibilities_and_goals="Expert in financial modeling, investment analysis, risk assessment, and market research.
            Analyzes financial statements, creates forecasts, and provides investment recommendations."
            training_files="financial_statements.xlsx,budget_2024.csv"  # From workspace if user provided financials

        **ORCHESTRATION WORKFLOW:**
        1. **Receive User Request**: User asks for something requiring specialized expertise
        2. **Assess Resources**: Check workspace for relevant files/data the expert will need
        3. **Create or Select Expert**: Use this command to spawn specialist with relevant training files
        4. **Silent Delegation**: Use "Ask ExpertName" command - expert works in background, returns results
        5. **Integrate & Present**: Combine expert's output with your analysis, present cohesive answer to user

        **RESOURCE DELEGATION EXAMPLES:**

        User uploads `expenses_2024.xlsx`:
        → Create "ExpensesExpert" with training_files="expenses_2024.xlsx"
        → Expert gets the data immediately, can analyze without asking user for it again

        User provides API documentation URL:
        → Create "APIIntegrationExpert" with training_urls="https://api.example.com/docs"
        → Expert has the docs in their knowledge, ready to help with integration

        You generated analysis in `market_report.md`:
        → Create "MarketingStrategist" with training_files="market_report.md"
        → Expert builds on your analysis with specialized marketing strategy

        **IMPORTANT NOTES:**
        - Expert agents inherit your provider and settings but get specialized commands and knowledge
        - Each expert becomes a persistent resource you can delegate to repeatedly
        - Creating focused experts prevents context pollution in your main knowledge base
        - You can create multiple experts for different domains - there's no limit to your network of specialists
        - The "Ask {agent_name}" command is automatically enabled for you to delegate work
        - Expert agents can be further refined through the web UI with additional training and customization

        **THE POWER OF SPECIALIZATION:**
        Instead of being a jack-of-all-trades master-of-none, you become the master orchestrator who can instantly
        summon world-class experts in any domain. You're not just an AI - you're a network of specialized intelligence,
        each member optimized for their specific role, working together to provide comprehensive solutions.
        """
        try:
            logging.info(f"Starting creation of new agent: {agent_name}")

            # Step 1: Clone the current agent to preserve all settings
            logging.info(
                f"Cloning current agent {self.agent_name} to create {agent_name}"
            )

            # Import the clone_agent function
            from Agent import clone_agent

            # Clone the agent
            clone_response = clone_agent(
                agent_id=self.agent_id, new_agent_name=agent_name, user=self.user
            )
            logging.info(f"Agent cloning response: {clone_response}")

            # Get the agent list to find the agent_id
            agents = self.ApiClient.get_agents()
            agent_id = None
            if isinstance(agents, list):
                for agent in agents:
                    if agent.get("name") == agent_name:
                        agent_id = agent.get("id")
                        break
            elif isinstance(agents, dict):
                for aid, agent_data in agents.items():
                    if agent_data.get("name") == agent_name:
                        agent_id = aid
                        break

            if not agent_id:
                return f"Error: Agent '{agent_name}' was created but could not retrieve its ID. Please check the agent list manually."

            logging.info(f"Agent ID for {agent_name}: {agent_id}")

            # Step 2: Get available commands and extensions by creating a temporary agent instance
            logging.info(
                f"Gathering available commands and extensions for intelligent selection"
            )

            # Get all available commands from the cloned agent
            try:
                from Agent import Agent

                temp_agent = Agent(agent_id=agent_id, user=self.user)
                agent_extensions = temp_agent.get_agent_extensions()

                available_commands_list = []

                # Build a comprehensive list of all available commands with descriptions
                for extension in agent_extensions:
                    extension_name = extension.get(
                        "extension_name", "Unknown Extension"
                    )
                    extension_description = extension.get("description", "")
                    commands = extension.get("commands", [])

                    if commands:
                        available_commands_list.append(
                            f"\n**{extension_name}** - {extension_description}"
                        )
                        for command in commands:
                            friendly_name = command.get("friendly_name", "Unknown")
                            description = command.get("description", "No description")
                            available_commands_list.append(
                                f"  - **{friendly_name}**: {description}"
                            )

                available_commands_text = (
                    "\n".join(available_commands_list)
                    if available_commands_list
                    else "No commands available"
                )

            except Exception as e:
                logging.error(f"Error getting available commands: {str(e)}")
                available_commands_text = "Unable to retrieve available commands"

            # Step 3: Use AI to select appropriate commands based on responsibilities
            logging.info(f"Using AI to select appropriate commands for {agent_name}")

            command_selection_prompt = f"""Based on the following agent responsibilities and the available commands, select which commands should be enabled for the new agent being created.

## Agent Name
{agent_name}

## Agent Responsibilities and Goals
{responsibilities_and_goals}

## Available Commands and Extensions
{available_commands_text}

## Instructions
Analyze the agent's responsibilities and goals, then select ONLY the commands that are relevant and necessary for this agent to fulfill its role effectively. 

**IMPORTANT**: Respond with ONLY a comma-separated list of command names. Do not include explanations, formatting, or any other text. Just the command names separated by commas.

Example response format: Write to File, Read File, Execute Python Code, Search Files

The assistant's full response should be in the answer block."""

            try:
                command_selection_response = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": command_selection_prompt,
                        "conversation_name": self.conversation_id,
                        "disable_commands": True,
                        "log_user_input": False,
                        "log_output": False,
                        "browse_links": False,
                        "websearch": False,
                        "analyze_user_input": False,
                        "tts": False,
                    },
                )

                # Parse the command selection response
                selected_commands = []
                if command_selection_response:
                    # Clean up the response and split by comma
                    command_selection_response = command_selection_response.strip()
                    # Remove common markdown formatting
                    command_selection_response = command_selection_response.replace(
                        "**", ""
                    ).replace("*", "")
                    # Split and clean
                    selected_commands = [
                        cmd.strip()
                        for cmd in command_selection_response.split(",")
                        if cmd.strip()
                    ]

                logging.info(f"AI selected commands: {', '.join(selected_commands)}")

            except Exception as e:
                logging.error(f"Error in command selection: {str(e)}")
                selected_commands = []

            # Step 4: Enable the selected commands
            if selected_commands:
                logging.info(
                    f"Enabling {len(selected_commands)} commands for {agent_name}"
                )
                commands_dict = {cmd: True for cmd in selected_commands}

                try:
                    self.ApiClient.update_agent_commands(
                        agent_id=agent_id, commands=commands_dict
                    )
                    logging.info(
                        f"Successfully enabled commands: {', '.join(selected_commands)}"
                    )
                except Exception as e:
                    logging.error(f"Error enabling commands: {str(e)}")

            # Step 5: Use AI to enhance mandatory context with detailed information
            logging.info(f"Using AI to enhance mandatory context for {agent_name}")

            enhanced_context_prompt = f"""You are creating comprehensive mandatory context for a new AI agent. Based on the provided information, create a detailed mandatory context document.

## Agent Name
{agent_name}

## Original Responsibilities and Goals
{responsibilities_and_goals}

## Selected Commands/Abilities
{', '.join(selected_commands) if selected_commands else 'No specific commands selected'}

## Instructions
Create a comprehensive mandatory context document that includes:

1. **Agent Identity**: Define who this agent is (e.g., marketing expert, coding specialist, data analyst, etc.)
2. **Core Responsibilities**: Expand on the original responsibilities with specific, detailed tasks
3. **Goals and Objectives**: Clear, measurable goals the agent should strive to achieve
4. **Operational Guidelines**: How the agent should approach tasks, interact with users, and make decisions
5. **Command Usage Examples**: Specific examples of when and how to use the enabled commands
6. **Response Patterns**: Examples of how the agent should respond to common requests
7. **Order of Operations**: Recommended workflow for handling complex tasks
8. **Best Practices**: Key principles the agent should follow

Make this detailed, actionable, and specific to the agent's role. Use clear formatting with headers and bullet points.

The assistant's full response should be in the answer block."""

            try:
                enhanced_context_response = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": enhanced_context_prompt,
                        "conversation_name": self.conversation_id,
                        "disable_commands": True,
                        "log_user_input": False,
                        "log_output": False,
                        "browse_links": False,
                        "websearch": False,
                        "analyze_user_input": False,
                        "tts": False,
                    },
                )

                logging.info(f"AI generated enhanced mandatory context")

            except Exception as e:
                logging.error(f"Error generating enhanced context: {str(e)}")
                enhanced_context_response = responsibilities_and_goals

            # Step 6: Set the enhanced mandatory context
            logging.info(f"Setting enhanced mandatory context for {agent_name}")
            context_text = f"""# {agent_name} - Mandatory Context

{enhanced_context_response}
# End of Mandatory Context
"""
            # Learn the context as text
            try:
                self.ApiClient.update_persona(
                    agent_name=agent_name,
                    persona=context_text,
                )
                logging.info("Enhanced mandatory context set successfully")
            except Exception as e:
                logging.error(f"Error setting enhanced mandatory context: {str(e)}")

            # Step 7: Train with files from workspace
            training_summary = []
            if training_files and training_files.strip():
                file_list = [f.strip() for f in training_files.split(",") if f.strip()]
                logging.info(f"Training with {len(file_list)} files from workspace")

                for filename in file_list:
                    try:
                        file_path = self.safe_join(filename)
                        if os.path.exists(file_path):
                            with open(
                                file_path, "r", encoding="utf-8", errors="ignore"
                            ) as f:
                                file_content = f.read()

                            self.ApiClient.learn_file(
                                agent_name=agent_name,
                                file_name=filename,
                                file_content=file_content,
                                collection_number="0",
                            )
                            training_summary.append(f"✓ Trained with file: {filename}")
                            logging.info(f"Successfully trained with file: {filename}")
                        else:
                            training_summary.append(f"✗ File not found: {filename}")
                            logging.warning(f"File not found in workspace: {filename}")
                    except Exception as e:
                        training_summary.append(
                            f"✗ Error training with {filename}: {str(e)}"
                        )
                        logging.error(f"Error training with file {filename}: {str(e)}")

            # Step 8: Train with URLs
            if training_urls and training_urls.strip():
                url_list = [u.strip() for u in training_urls.split(",") if u.strip()]
                logging.info(f"Training with {len(url_list)} URLs")

                for url in url_list:
                    try:
                        self.ApiClient.learn_url(
                            agent_name=agent_name, url=url, collection_number="0"
                        )
                        training_summary.append(f"✓ Trained with URL: {url}")
                        logging.info(f"Successfully trained with URL: {url}")
                    except Exception as e:
                        training_summary.append(
                            f"✗ Error training with {url}: {str(e)}"
                        )
                        logging.error(f"Error training with URL {url}: {str(e)}")

            # Step 9: Create "Ask {agent_name}" chain with AI-generated usage guidance
            chain_name = f"Ask {agent_name}"

            # Use AI to generate a descriptive "When to ask" guidance
            logging.info(f"Generating usage guidance for {chain_name} command")

            when_to_ask_prompt = f"""Create a concise "When to ask {agent_name}:" description that tells when this expert agent should be consulted.

## Agent Information
**Name**: {agent_name}
**Responsibilities**: {responsibilities_and_goals}
**Selected Commands**: {', '.join(selected_commands) if selected_commands else 'General capabilities'}

## Instructions
Write a single, clear sentence (max 2 sentences) starting with "When to ask {agent_name}:" that describes:
1. What types of tasks this expert is well-equipped to handle
2. What specific expertise they bring
3. When delegating to them would be most valuable

Keep it concise, actionable, and specific to their domain expertise.

Example format: "When to ask MarketingExpert: Consult for SEO optimization, content strategy, social media campaigns, market analysis, and creating compelling marketing copy that drives conversions."

Your response (just the sentence in the answer block):"""

            try:
                when_to_ask_response = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": when_to_ask_prompt,
                        "conversation_name": self.conversation_id,
                        "disable_commands": True,
                        "log_user_input": False,
                        "log_output": False,
                        "browse_links": False,
                        "websearch": False,
                        "analyze_user_input": False,
                        "tts": False,
                    },
                )

                # Clean up the response
                chain_description = when_to_ask_response.strip()
                # Ensure it starts with "When to ask"
                if not chain_description.lower().startswith("when to ask"):
                    chain_description = f"When to ask {agent_name}: {chain_description}"

                logging.info(f"AI generated chain description: {chain_description}")

            except Exception as e:
                logging.error(f"Error generating chain description: {str(e)}")
                chain_description = f"When to ask {agent_name}: Delegate tasks related to {responsibilities_and_goals[:100]}..."

            logging.info(f"Creating chain: {chain_name}")
            try:
                # Create the chain
                self.ApiClient.add_chain(
                    chain_name=chain_name, description=chain_description
                )

                # Get the chain ID
                chains = self.ApiClient.get_chains()
                chain_id = None
                for chain in chains:
                    if (
                        chain.get("chainName") == chain_name
                        or chain.get("name") == chain_name
                    ):
                        chain_id = chain.get("id")
                        break

                if chain_id:
                    # Add a step to the chain that prompts the new agent
                    self.ApiClient.add_step(
                        chain_name=chain_name,
                        step_number=1,
                        agent_name=agent_name,
                        prompt_type="Prompt",
                        prompt={
                            "prompt_name": "Think About It",
                        },
                    )
                    logging.info(f"Chain '{chain_name}' created successfully")

                    # Step 10: Enable the chain as a command for the current agent
                    try:
                        self.ApiClient.toggle_command(
                            agent_name=self.agent_name,
                            command_name=chain_name,
                            enable=True,
                        )
                        logging.info(
                            f"Enabled '{chain_name}' command for current agent"
                        )
                    except Exception as e:
                        logging.error(f"Error enabling chain as command: {str(e)}")
                else:
                    logging.warning("Could not retrieve chain ID after creation")

            except Exception as e:
                logging.error(f"Error creating chain: {str(e)}")

            # Step 11: Build and return comprehensive summary
            summary = f"""# ✅ Successfully Created Expert Agent: {agent_name}

## Agent Details
- **Name**: {agent_name}
- **Agent ID**: {agent_id}
- **Cloned From**: {self.agent_name} (inherited all settings and provider configurations)
- **Specialization**: Expert agent with focused domain knowledge and specialized capabilities

## Expert Configuration Summary

### AI-Enhanced Expert Context
✓ Comprehensive expert-level context created through AI analysis
✓ Includes detailed operational guidelines, command usage examples, and best practices
✓ Focused on specific domain expertise without context pollution

### Training Status
"""
            if training_summary:
                summary += "\n".join(training_summary)
            else:
                summary += "No additional training files or URLs provided."

            summary += f"""

### Intelligently Selected Specialized Abilities
AI analyzed the expert's domain and selected {len(selected_commands)} relevant commands:
"""
            if selected_commands:
                summary += "\n".join([f"- {cmd}" for cmd in selected_commands])
            else:
                summary += "No specific commands were selected by AI"

            summary += f"""

### Expert Delegation Command
- **Command Name**: `{chain_name}`
- **{chain_description}**

## How to Work with Your Expert

**Delegation (Recommended):**
Use the `{chain_name}` command anytime you need this expert's specialized knowledge. The expert will handle the task within their domain and return results to you.

**Direct Interaction:**
Switch to {agent_name} in the agent selector to work directly with this expert in a focused conversation.

**When to Delegate:**
{chain_description}

## Expert Agent Benefits

✓ **Focused Expertise**: {agent_name} maintains specialized knowledge without generalist context pollution
✓ **Persistent Resource**: This expert is now permanently available for delegation
✓ **Scalable Specialization**: You can create additional experts for other domains as needed
✓ **Orchestration Power**: You're building a network of specialists you can consult on-demand

## Further Customization

Access the web UI agent settings to:
- Review and adjust the AI-selected commands
- Add more domain-specific training data
- Fine-tune expert settings and behavior
- Share the expert with team members

## Next Steps
1. **Test the Expert**: Use the `{chain_name}` command with a sample task from their domain
2. **Review Expert Context**: Check the web UI to see the AI-enhanced mandatory context and operational guidelines
3. **Expand Expertise**: Train the expert with additional domain-specific resources as needed
4. **Build Your Network**: Create more experts for other domains to expand your orchestration capabilities

**The Orchestrator Advantage**: You now have a specialized expert ready to handle {agent_name.lower()} tasks. As you create more experts, you build a network of domain specialists that work together under your orchestration - becoming not just an AI, but a collaborative intelligence network.

Expert agent creation complete! {agent_name} is ready to provide specialized assistance.
"""

            logging.info(f"Agent {agent_name} creation completed successfully")
            return summary

        except Exception as e:
            error_msg = f"Error creating expert agent {agent_name}: {str(e)}"
            logging.error(error_msg)
            return f"❌ {error_msg}\n\nPlease check the logs for more details and try again."

    async def get_webui_tips(page: str = "all") -> str:
        """
        Provide quick tips for navigating and using the AGiXT web UI. This is useful for assisting users with navigating the web interface.

        Args:
            page (str): Specific page to get tips for (default: "all", options: "chat", "billing", "team", "automation")
        Returns:
            str: Markdown formatted tips for the specified page or all pages

        Note: It is generally best to get all pages unless the users question is specific enough to narrow it down.
        - The user is talking to the assistant through the AGiXT web UI, if they ask how to do something within the ui or application, use this to get tips.
        - AGiXT is an open source AI agent platform that allows users to create and manage AI agents, automation, and more through the multitenant system.
        """
        if not page or str(page).lower() == "none":
            page = "all"
        general_information = """## Tips for Navigating the AGiXT Web UI
- With the exception of the chat page, each page has a chat icon in the top right next to the user avatar which will take them back to the chat page.
- User avatar can be changed on gravatar.com using the email address associated with their user account.
- Themes are accessible by clicking the user avatar in the top right and selecting `Themes` from the dropdown menu. The options are dark and light."""
        chat_page = """## Chat page

To start a new conversation, click the `+` button on the top right of the page.

### Agent switching, extensions, training, and settings

In the bottom right of the chat page above the input box, you will see `AGENT NAME at TEAM NAME`, which indicates the currently selected agent and team/company. Click on this to open the agent switcher modal, where you can:

- Switch between agents you have access to
- Click "Extensions": Access the agent's extensions where third party software can be connected and abilities granted to the selected agent
- Click "Training": Access the agent's training section to update the agents mandatory context, and train from files or URLs
- Click "Settings": Access the agent's settings to modify the agent's name, which inference providers it uses, to clone the agent, share it with your team, or delete it.
- Click "+ Add Agent": Create a new agent. On the agent creation screen, enter the new agent's name and select the company it is to be associated with, then click "Create Agent"

### Conversational Workspaces

Each conversation has its own workspace for the agent to work in. Any files uploaded by the user (paperclip button on the chat input box) or created/downloaded/modified by the agent during the conversation are stored in that conversation's workspace. You can view and manage the files in the workspace by clicking the folder icon next to the paperclip button. You can create new folders, upload files, download files, delete files, and navigate between folders within the workspace interface.

### Conversation Sharing

Conversations and their workspaces can be shared with other users. You can choose to share it as a public link, to a user in your company by email, or to export it as a JSON file. To share a conversation, click the share icon at the top right of the chat page. You can also optionally set an expiration date for the shared link.

### Conversation Search

The search icon at the top right of the chat page allows you to search for different conversations by name or content and switch to them quickly. There is also a list of recent conversations in the left sidebar for easy access (click the 3 horizontal lines at the top left to toggle the sidebar).

### Voice Input and Output

The microphone button on the chat input box allows you to use voice input for your messages. Click the microphone button to start recording your voice message, and click it again to stop recording. Your voice message will be transcribed to text and sent as a chat message to the agent.

On agent responses, there is a speaker icon which will translate the agent's text response into speech using text-to-speech synthesis. Click the speaker icon to listen to the agent's response.

### Other chat buttons that show up on messages

- The edit (pencil) button allows you to edit any message in the conversation as well as regenerate agent responses post-edit optionally.
- The fork button allows you to fork the current conversation into a new conversation, preserving the context up to that point.
- The copy button allows you to copy the message text to your clipboard in markdown format.
- The delete (trash can) button allows you to delete any message in the conversation.
- The thumbs up and thumbs down buttons allow you to provide feedback on agent responses to help improve the agent's performance. (AI responses only)
"""
        billing_page = """
## Billing page

The billing page is accessible by clicking the user's avatar in the top right corner and selecting `Billing` from the dropdown menu (only visible to company admins). The billing page allows company admins to:

- View token balance and usage analytics for all team members
- Purchase additional tokens for the company by card or crypto payments
- View billing transaction history for the company

Only company admins (role_id 1-2) can access the billing page. Regular users (role_id 3+) will not see the billing option in the dropdown menu and will be redirected to the chat page if they try to access `/billing`.

If a company runs out of tokens, they are paywalled to the top up screen until tokens are purchased. Low balance warnings will also appear on the chat page and billing page when the company's token balance gets to 1M tokens or lower.
"""
        team_page = """## Team Management

For company admins only.

On the sidebar, expanding `Team Management` reveals the following pages:

- Companies & Teams: View your companies and teams, create new companies/teams.
- Users: View and manage users in your companies/teams, invite new users.
- Training: Team-wide training data management for the agent which includes mandatory context, file training, and URL training that will be appended to all agents in the team's training.
- Extensions: Team-wide extension management for connecting third party software to agents in the team and granting abilities to all agents in the team.
- Settings: Manage company/team settings such as team's default agent name, and team-wide inference providers.
"""
        automation_page = """## Automation

On the sidebar, expanding `Automation` reveals the following pages:

- Automation Chains: Create and manage automation chains (like pre-defined sequences of tasks for agents to perform) that can be enabled as agent abilities.
- Prompt Library: Create and manage reusable prompts that can be used in automation chains.
- Tasks: Create and manage scheduled or triggered tasks that agents can perform automatically. Useful for scheduling automated messages or actions.
- Webhooks: Manage incoming and outgoing webhooks for integrating with other services."""

        # Use a switch case instead of if
        page = str(page).lower()
        match page:
            case "chat":
                return f"{general_information}\n\n{chat_page}"
            case "billing":
                return f"{general_information}\n\n{billing_page}"
            case "team":
                return f"{general_information}\n\n{team_page}"
            case "automation":
                return f"{general_information}\n\n{automation_page}"
            case _:
                return f"# AGiXT Web UI Quick Tips\n\n{general_information}\n\n{chat_page}\n\n{billing_page}\n\n{team_page}\n\n{automation_page}"

    async def optimize_command_selection(self, task_description: str) -> str:
        """
        Re-optimize the available commands for the current conversation based on a new task or changed requirements.
        Use this when you realize you need different abilities than what was initially selected, or when starting a significantly different task.

        Args:
            task_description (str): Description of what you're trying to accomplish that requires different commands

        Returns:
            str: Confirmation that command selection has been optimized with the list of newly selected commands

        Notes:
            This command triggers a re-selection of available abilities based on the new task description.
            After execution, the assistant will have access to a different set of optimized commands for the remainder of the conversation.
            Use this when the current task requires abilities that weren't initially selected.
        """
        # This is a signal command - the actual optimization is handled by the Interactions class
        # when it sees this command was executed. We return a message indicating optimization is requested.
        return f"OPTIMIZE_COMMANDS:{task_description}"

    # ==========================================================================
    # NEW CODE INTELLIGENCE & DEVELOPMENT TOOLS
    # ==========================================================================

    async def find_symbol_usages(
        self,
        symbol_name: str,
        file_patterns: str = "**/*.py",
        include_definitions: str = "true",
    ) -> str:
        """
        Find all usages (references, definitions, calls) of a function, class, method, or variable across the workspace.
        Essential for understanding code impact before making changes and for refactoring workflows.

        Args:
            symbol_name (str): The name of the symbol to search for (function, class, method, variable name)
            file_patterns (str): Glob pattern to filter which files to search (e.g., "**/*.py", "**/*.js"). Default: "**/*.py"
            include_definitions (str): Whether to include definition sites ("true"/"false"). Default: "true"

        Returns:
            str: List of all usages with file paths, line numbers, and context

        Examples:
            - Find all calls to a function: symbol_name="authenticate_user"
            - Find all uses of a class: symbol_name="UserModel"
            - Find variable references: symbol_name="config_settings"
        """
        import fnmatch
        import re

        try:
            include_defs = str(include_definitions).lower() == "true"
            usages = []
            definitions = []
            files_searched = 0

            # Create regex pattern for the symbol
            # Match word boundaries to avoid partial matches
            pattern = re.compile(rf"\b{re.escape(symbol_name)}\b")

            # Patterns that indicate a definition vs usage
            definition_patterns = [
                rf"^\s*def\s+{re.escape(symbol_name)}\s*\(",  # Python function def
                rf"^\s*async\s+def\s+{re.escape(symbol_name)}\s*\(",  # Python async def
                rf"^\s*class\s+{re.escape(symbol_name)}[\s:(]",  # Python class def
                rf"^\s*{re.escape(symbol_name)}\s*=",  # Variable assignment
                rf"^\s*self\.{re.escape(symbol_name)}\s*=",  # Instance attribute
                rf"function\s+{re.escape(symbol_name)}\s*\(",  # JS function
                rf"const\s+{re.escape(symbol_name)}\s*=",  # JS const
                rf"let\s+{re.escape(symbol_name)}\s*=",  # JS let
                rf"var\s+{re.escape(symbol_name)}\s*=",  # JS var
            ]
            definition_regex = re.compile("|".join(definition_patterns))

            for root, dirs, files in os.walk(self.WORKING_DIRECTORY):
                # Skip hidden directories and common non-code directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d
                    not in [
                        "node_modules",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "dist",
                        "build",
                    ]
                ]

                for filename in files:
                    rel_root = os.path.relpath(root, self.WORKING_DIRECTORY)
                    if rel_root == ".":
                        rel_path = filename
                    else:
                        rel_path = f"{rel_root}/{filename}"

                    # Check if file matches pattern
                    if not fnmatch.fnmatch(
                        rel_path, file_patterns
                    ) and not fnmatch.fnmatch(
                        filename,
                        (
                            file_patterns.split("/")[-1]
                            if "/" in file_patterns
                            else file_patterns
                        ),
                    ):
                        continue

                    # Skip binary files
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in BINARY_EXTENSIONS:
                        continue

                    file_path = os.path.join(root, filename)
                    try:
                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            lines = f.readlines()

                        for line_num, line in enumerate(lines, 1):
                            if pattern.search(line):
                                is_definition = bool(definition_regex.search(line))

                                entry = {
                                    "file": rel_path,
                                    "line": line_num,
                                    "content": line.strip(),
                                    "type": "definition" if is_definition else "usage",
                                }

                                if is_definition:
                                    definitions.append(entry)
                                else:
                                    usages.append(entry)

                        files_searched += 1
                    except Exception:
                        continue

            # Build result
            result = f"# Symbol Analysis: `{symbol_name}`\n\n"
            result += f"Searched {files_searched} files matching `{file_patterns}`\n\n"

            if include_defs and definitions:
                result += f"## Definitions ({len(definitions)})\n\n"
                for d in definitions[:20]:
                    result += f"- **{d['file']}:{d['line']}**\n  ```\n  {d['content']}\n  ```\n"
                if len(definitions) > 20:
                    result += f"\n... and {len(definitions) - 20} more definitions\n"

            if usages:
                result += f"\n## Usages ({len(usages)})\n\n"
                for u in usages[:50]:
                    result += f"- **{u['file']}:{u['line']}**: `{u['content'][:100]}{'...' if len(u['content']) > 100 else ''}`\n"
                if len(usages) > 50:
                    result += f"\n... and {len(usages) - 50} more usages\n"

            if not definitions and not usages:
                result += f"No occurrences of `{symbol_name}` found in the workspace."

            return result

        except Exception as e:
            return f"Error finding symbol usages: {str(e)}"

    async def semantic_code_search(
        self,
        query: str,
        file_patterns: str = "**/*",
        max_results: int = 20,
    ) -> str:
        """
        Search for code using natural language descriptions. Finds code that matches conceptual queries
        like "authentication logic", "database connection", "error handling", etc.

        Args:
            query (str): Natural language description of what you're looking for
            file_patterns (str): Glob pattern to filter files (e.g., "**/*.py"). Default: all files
            max_results (int): Maximum number of results to return. Default: 20

        Returns:
            str: Matching code snippets with file paths and relevance context

        Examples:
            - "authentication and login logic"
            - "database connection setup"
            - "error handling and exceptions"
            - "API endpoint definitions"
            - "configuration loading"
        """
        import fnmatch
        import re

        try:
            # Build search terms from the query
            # Extract key terms and common programming synonyms
            query_lower = query.lower()
            search_terms = []

            # Add original query words
            words = re.findall(r"\b\w+\b", query_lower)
            search_terms.extend(words)

            # Add programming-specific synonyms
            synonyms = {
                "auth": [
                    "authenticate",
                    "authentication",
                    "login",
                    "logout",
                    "session",
                    "token",
                    "jwt",
                    "oauth",
                ],
                "database": [
                    "db",
                    "sql",
                    "query",
                    "connection",
                    "cursor",
                    "orm",
                    "model",
                ],
                "error": [
                    "exception",
                    "try",
                    "except",
                    "catch",
                    "raise",
                    "throw",
                    "error",
                ],
                "config": [
                    "configuration",
                    "settings",
                    "env",
                    "environment",
                    "options",
                ],
                "api": ["endpoint", "route", "request", "response", "rest", "http"],
                "test": ["unittest", "pytest", "assert", "mock", "fixture"],
                "log": ["logging", "logger", "debug", "info", "warning", "error"],
                "file": ["read", "write", "open", "path", "directory", "folder"],
                "user": ["account", "profile", "member", "customer"],
                "data": ["parse", "serialize", "json", "xml", "csv"],
            }

            for word in words:
                for key, values in synonyms.items():
                    if word == key or word in values:
                        search_terms.extend(values)
                        search_terms.append(key)

            search_terms = list(set(search_terms))

            # Score-based matching
            results = []
            files_searched = 0

            for root, dirs, files in os.walk(self.WORKING_DIRECTORY):
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d
                    not in [
                        "node_modules",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "dist",
                        "build",
                    ]
                ]

                for filename in files:
                    rel_root = os.path.relpath(root, self.WORKING_DIRECTORY)
                    if rel_root == ".":
                        rel_path = filename
                    else:
                        rel_path = f"{rel_root}/{filename}"

                    if not fnmatch.fnmatch(
                        rel_path, file_patterns
                    ) and not fnmatch.fnmatch(
                        filename,
                        (
                            file_patterns.split("/")[-1]
                            if "/" in file_patterns
                            else file_patterns
                        ),
                    ):
                        continue

                    ext = os.path.splitext(filename)[1].lower()
                    if ext in BINARY_EXTENSIONS:
                        continue

                    file_path = os.path.join(root, filename)
                    try:
                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            content = f.read()
                            lines = content.split("\n")

                        # Score the file based on term matches
                        content_lower = content.lower()
                        file_score = sum(
                            content_lower.count(term) for term in search_terms
                        )

                        if file_score > 0:
                            # Find the most relevant lines
                            line_scores = []
                            for i, line in enumerate(lines):
                                line_lower = line.lower()
                                line_score = sum(
                                    1 for term in search_terms if term in line_lower
                                )
                                if line_score > 0:
                                    line_scores.append(
                                        (i + 1, line_score, line.strip())
                                    )

                            # Sort by score and take top matches
                            line_scores.sort(key=lambda x: x[1], reverse=True)
                            top_lines = line_scores[:5]

                            results.append(
                                {
                                    "file": rel_path,
                                    "score": file_score,
                                    "matches": top_lines,
                                }
                            )

                        files_searched += 1
                    except Exception:
                        continue

            # Sort by score
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:max_results]

            # Build output
            output = f'# Semantic Search: "{query}"\n\n'
            output += f"Searched {files_searched} files, found {len(results)} relevant files\n"
            output += f"Search terms used: {', '.join(search_terms[:15])}{'...' if len(search_terms) > 15 else ''}\n\n"

            if results:
                for r in results:
                    output += f"## {r['file']} (relevance: {r['score']})\n"
                    for line_num, score, content in r["matches"]:
                        output += f"  - Line {line_num}: `{content[:80]}{'...' if len(content) > 80 else ''}`\n"
                    output += "\n"
            else:
                output += "No relevant code found for your query.\n"
                output += "Try using different terms or broader patterns."

            return output

        except Exception as e:
            return f"Error in semantic search: {str(e)}"

    async def multi_file_replace(
        self,
        replacements: str,
    ) -> str:
        """
        Apply multiple string replacements across different files atomically.
        Essential for refactoring operations and coordinated changes across a codebase.

        Args:
            replacements (str): JSON array of replacement operations. Each operation should have:
                - file: relative file path
                - old_text: exact text to find
                - new_text: replacement text

                Example: [{"file": "app.py", "old_text": "old_func", "new_text": "new_func"},
                          {"file": "utils.py", "old_text": "old_func", "new_text": "new_func"}]

        Returns:
            str: Summary of successful and failed replacements

        Notes:
            - All replacements are validated before any changes are made
            - If validation fails for any replacement, no changes are made (atomic operation)
            - Use this for renaming functions, updating imports, or coordinated refactoring
        """
        try:
            ops = json.loads(replacements)
            if not isinstance(ops, list):
                return "Error: replacements must be a JSON array of operations"

            # Validate all operations first
            validated = []
            errors = []

            for i, op in enumerate(ops):
                if not isinstance(op, dict):
                    errors.append(f"Operation {i+1}: must be an object")
                    continue

                file_path = op.get("file")
                old_text = op.get("old_text")
                new_text = op.get("new_text")

                if not all([file_path, old_text is not None, new_text is not None]):
                    errors.append(
                        f"Operation {i+1}: missing required fields (file, old_text, new_text)"
                    )
                    continue

                full_path = self.safe_join(file_path)
                if not os.path.exists(full_path):
                    errors.append(f"Operation {i+1}: file '{file_path}' does not exist")
                    continue

                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    if old_text not in content:
                        errors.append(
                            f"Operation {i+1}: text not found in '{file_path}'"
                        )
                        continue

                    # Count occurrences
                    count = content.count(old_text)
                    validated.append(
                        {
                            "file": file_path,
                            "full_path": full_path,
                            "old_text": old_text,
                            "new_text": new_text,
                            "occurrences": count,
                            "content": content,
                        }
                    )
                except Exception as e:
                    errors.append(
                        f"Operation {i+1}: error reading '{file_path}': {str(e)}"
                    )

            # If there are validation errors, report them without making changes
            if errors:
                result = "## Validation Errors\n\n"
                result += "No changes were made due to the following errors:\n\n"
                for err in errors:
                    result += f"- {err}\n"
                if validated:
                    result += f"\n{len(validated)} operations would have succeeded."
                return result

            # Apply all replacements
            successful = []
            for op in validated:
                try:
                    new_content = op["content"].replace(op["old_text"], op["new_text"])
                    with open(op["full_path"], "w", encoding="utf-8") as f:
                        f.write(new_content)
                    successful.append(op)
                except Exception as e:
                    errors.append(f"Failed to write '{op['file']}': {str(e)}")

            # Build result summary
            result = f"## Multi-File Replace Results\n\n"
            result += f"**{len(successful)} of {len(ops)} operations completed successfully**\n\n"

            if successful:
                result += "### Successful Replacements:\n"
                for op in successful:
                    result += f"- `{op['file']}`: replaced {op['occurrences']} occurrence(s)\n"

            if errors:
                result += "\n### Errors:\n"
                for err in errors:
                    result += f"- {err}\n"

            return result

        except json.JSONDecodeError as e:
            return f"Error parsing replacements JSON: {str(e)}\n\nExpected format: [{'{'}\"file\": \"path\", \"old_text\": \"old\", \"new_text\": \"new\"{'}'}]"
        except Exception as e:
            return f"Error in multi-file replace: {str(e)}"

    async def get_file_errors(
        self,
        file_path: str = "",
        error_types: str = "all",
    ) -> str:
        """
        Get syntax errors, linting issues, and other diagnostics for files in the workspace.
        Essential for validating code after changes and identifying issues.

        Args:
            file_path (str): Specific file to check, or empty string to check all Python files
            error_types (str): Types of errors to check: "syntax", "lint", "type", or "all". Default: "all"

        Returns:
            str: List of errors with file paths, line numbers, and descriptions

        Notes:
            - For Python files: checks syntax errors and optionally runs pylint/flake8
            - For JavaScript files: checks syntax errors
            - Use this after making code changes to validate your work
        """
        import ast
        import fnmatch

        errors = []
        files_checked = 0

        try:
            check_syntax = error_types in ["all", "syntax"]
            check_lint = error_types in ["all", "lint"]

            if file_path:
                files_to_check = [self.safe_join(file_path)]
            else:
                files_to_check = []
                for root, dirs, files in os.walk(self.WORKING_DIRECTORY):
                    dirs[:] = [
                        d
                        for d in dirs
                        if not d.startswith(".")
                        and d not in ["node_modules", "__pycache__", "venv", ".venv"]
                    ]
                    for filename in files:
                        if filename.endswith(".py"):
                            files_to_check.append(os.path.join(root, filename))

            for full_path in files_to_check:
                if not os.path.exists(full_path):
                    continue

                rel_path = os.path.relpath(full_path, self.WORKING_DIRECTORY)
                ext = os.path.splitext(full_path)[1].lower()

                if ext == ".py" and check_syntax:
                    # Check Python syntax
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            code = f.read()
                        ast.parse(code)
                    except SyntaxError as e:
                        errors.append(
                            {
                                "file": rel_path,
                                "line": e.lineno or 0,
                                "column": e.offset or 0,
                                "type": "SyntaxError",
                                "message": str(e.msg),
                            }
                        )

                if ext == ".py" and check_lint:
                    # Try to run basic lint checks
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()

                        for i, line in enumerate(lines, 1):
                            # Check for common issues
                            stripped = line.rstrip()

                            # Trailing whitespace
                            if line.rstrip() != line.rstrip("\n").rstrip("\r"):
                                if line.endswith(" \n") or line.endswith("\t\n"):
                                    errors.append(
                                        {
                                            "file": rel_path,
                                            "line": i,
                                            "column": len(stripped),
                                            "type": "Style",
                                            "message": "Trailing whitespace",
                                        }
                                    )

                            # Line too long
                            if len(stripped) > 120:
                                errors.append(
                                    {
                                        "file": rel_path,
                                        "line": i,
                                        "column": 120,
                                        "type": "Style",
                                        "message": f"Line too long ({len(stripped)} > 120 characters)",
                                    }
                                )

                            # Mixed tabs and spaces (basic check)
                            if "\t" in line and "    " in line:
                                errors.append(
                                    {
                                        "file": rel_path,
                                        "line": i,
                                        "column": 1,
                                        "type": "Style",
                                        "message": "Mixed tabs and spaces in indentation",
                                    }
                                )

                    except Exception:
                        pass

                files_checked += 1

            # Build result
            result = f"# Code Diagnostics Report\n\n"
            result += (
                f"Checked {files_checked} file(s), found {len(errors)} issue(s)\n\n"
            )

            if errors:
                # Group by file
                by_file = {}
                for err in errors:
                    if err["file"] not in by_file:
                        by_file[err["file"]] = []
                    by_file[err["file"]].append(err)

                for file, file_errors in by_file.items():
                    result += f"## {file}\n\n"
                    for err in file_errors:
                        result += f"- **Line {err['line']}**: [{err['type']}] {err['message']}\n"
                    result += "\n"
            else:
                result += "✅ No issues found!"

            return result

        except Exception as e:
            return f"Error checking files: {str(e)}"

    async def run_tests(
        self,
        test_path: str = "",
        test_pattern: str = "test_*.py",
        verbose: str = "true",
    ) -> str:
        """
        Run unit tests in the workspace. Supports pytest and unittest frameworks.

        Args:
            test_path (str): Specific test file or directory to run. Empty for auto-discovery.
            test_pattern (str): Pattern to match test files. Default: "test_*.py"
            verbose (str): Show detailed output ("true"/"false"). Default: "true"

        Returns:
            str: Test results including passed, failed, and error details

        Notes:
            - Automatically detects pytest or unittest
            - Provides detailed failure information for debugging
            - Use after making code changes to verify functionality
        """
        try:
            verbose_flag = str(verbose).lower() == "true"

            # Determine test path
            if test_path:
                full_test_path = self.safe_join(test_path)
            else:
                full_test_path = self.WORKING_DIRECTORY

            # Check if pytest is available
            pytest_available = False
            try:
                import pytest

                pytest_available = True
            except ImportError:
                pass

            if pytest_available:
                # Run with pytest
                import io
                import sys

                # Capture output
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = io.StringIO()
                sys.stderr = io.StringIO()

                try:
                    args = [
                        full_test_path,
                        "-v" if verbose_flag else "-q",
                        "--tb=short",
                    ]
                    exit_code = pytest.main(args)

                    stdout_output = sys.stdout.getvalue()
                    stderr_output = sys.stderr.getvalue()
                finally:
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr

                result = "# Test Results (pytest)\n\n"
                result += f"Exit code: {exit_code} ({'PASSED' if exit_code == 0 else 'FAILED'})\n\n"
                result += "```\n"
                result += stdout_output
                if stderr_output:
                    result += "\n--- stderr ---\n"
                    result += stderr_output
                result += "```"

                return result
            else:
                # Fall back to unittest
                import unittest
                import io

                loader = unittest.TestLoader()

                if os.path.isfile(full_test_path):
                    # Load specific test file
                    suite = loader.discover(
                        os.path.dirname(full_test_path),
                        pattern=os.path.basename(full_test_path),
                    )
                else:
                    # Discover tests in directory
                    suite = loader.discover(full_test_path, pattern=test_pattern)

                # Run tests
                stream = io.StringIO()
                runner = unittest.TextTestRunner(
                    stream=stream,
                    verbosity=2 if verbose_flag else 1,
                )
                result_obj = runner.run(suite)

                result = "# Test Results (unittest)\n\n"
                result += f"Tests run: {result_obj.testsRun}\n"
                result += f"Failures: {len(result_obj.failures)}\n"
                result += f"Errors: {len(result_obj.errors)}\n"
                result += f"Status: {'PASSED' if result_obj.wasSuccessful() else 'FAILED'}\n\n"
                result += "```\n"
                result += stream.getvalue()
                result += "```"

                if result_obj.failures:
                    result += "\n\n## Failures\n\n"
                    for test, traceback in result_obj.failures:
                        result += f"### {test}\n```\n{traceback}\n```\n"

                if result_obj.errors:
                    result += "\n\n## Errors\n\n"
                    for test, traceback in result_obj.errors:
                        result += f"### {test}\n```\n{traceback}\n```\n"

                return result

        except Exception as e:
            return f"Error running tests: {str(e)}"

    async def get_code_symbols(
        self,
        file_path: str,
        symbol_types: str = "all",
    ) -> str:
        """
        List all code symbols (classes, functions, methods, variables) in a file.
        Provides a structural overview without reading the entire file content.

        Args:
            file_path (str): Path to the file to analyze
            symbol_types (str): Types to include: "classes", "functions", "variables", or "all". Default: "all"

        Returns:
            str: Hierarchical list of symbols with line numbers

        Notes:
            - For Python files: uses AST parsing for accurate results
            - Shows class methods nested under their classes
            - Useful for understanding file structure before making changes
        """
        import ast

        try:
            full_path = self.safe_join(file_path)
            if not os.path.exists(full_path):
                return f"Error: File '{file_path}' not found"

            ext = os.path.splitext(file_path)[1].lower()

            if ext == ".py":
                with open(full_path, "r", encoding="utf-8") as f:
                    code = f.read()

                try:
                    tree = ast.parse(code)
                except SyntaxError as e:
                    return f"Error: Syntax error in file at line {e.lineno}: {e.msg}"

                include_classes = symbol_types in ["all", "classes"]
                include_functions = symbol_types in ["all", "functions"]
                include_variables = symbol_types in ["all", "variables"]

                result = f"# Code Symbols: {file_path}\n\n"

                classes = []
                functions = []
                variables = []

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and include_classes:
                        methods = []
                        class_vars = []
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef) or isinstance(
                                item, ast.AsyncFunctionDef
                            ):
                                methods.append((item.name, item.lineno))
                            elif isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if isinstance(target, ast.Name):
                                        class_vars.append((target.id, item.lineno))
                        classes.append(
                            {
                                "name": node.name,
                                "line": node.lineno,
                                "methods": methods,
                                "variables": class_vars,
                            }
                        )

                    elif (
                        isinstance(node, ast.FunctionDef)
                        or isinstance(node, ast.AsyncFunctionDef)
                    ) and include_functions:
                        # Only top-level functions (not methods)
                        if not any(
                            node.lineno > c["line"] and node.lineno < c["line"] + 1000
                            for c in classes
                        ):
                            is_async = isinstance(node, ast.AsyncFunctionDef)
                            functions.append(
                                {
                                    "name": node.name,
                                    "line": node.lineno,
                                    "async": is_async,
                                    "args": [arg.arg for arg in node.args.args],
                                }
                            )

                    elif isinstance(node, ast.Assign) and include_variables:
                        # Only module-level variables
                        if hasattr(node, "col_offset") and node.col_offset == 0:
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    variables.append(
                                        {"name": target.id, "line": node.lineno}
                                    )

                if classes:
                    result += "## Classes\n\n"
                    for cls in sorted(classes, key=lambda x: x["line"]):
                        result += f"### `{cls['name']}` (line {cls['line']})\n"
                        if cls["methods"]:
                            result += "Methods:\n"
                            for name, line in sorted(
                                cls["methods"], key=lambda x: x[1]
                            ):
                                result += f"  - `{name}()` (line {line})\n"
                        if cls["variables"]:
                            result += "Class Variables:\n"
                            for name, line in sorted(
                                cls["variables"], key=lambda x: x[1]
                            ):
                                result += f"  - `{name}` (line {line})\n"
                        result += "\n"

                if functions:
                    result += "## Functions\n\n"
                    for func in sorted(functions, key=lambda x: x["line"]):
                        async_prefix = "async " if func["async"] else ""
                        args_str = ", ".join(func["args"][:5])
                        if len(func["args"]) > 5:
                            args_str += ", ..."
                        result += f"- `{async_prefix}{func['name']}({args_str})` (line {func['line']})\n"
                    result += "\n"

                if variables:
                    result += "## Module Variables\n\n"
                    for var in sorted(variables, key=lambda x: x["line"]):
                        result += f"- `{var['name']}` (line {var['line']})\n"

                if not classes and not functions and not variables:
                    result += "No symbols found in the file."

                return result

            else:
                # For non-Python files, do basic pattern matching
                with open(full_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                result = f"# Code Symbols: {file_path}\n\n"
                result += "(Basic pattern matching for non-Python files)\n\n"

                symbols = []
                for i, line in enumerate(lines, 1):
                    # JavaScript/TypeScript patterns
                    if ext in [".js", ".ts", ".jsx", ".tsx"]:
                        import re

                        # Function declarations
                        if match := re.match(r"^\s*(async\s+)?function\s+(\w+)", line):
                            symbols.append(f"- Function `{match.group(2)}` (line {i})")
                        # Class declarations
                        elif match := re.match(r"^\s*class\s+(\w+)", line):
                            symbols.append(f"- Class `{match.group(1)}` (line {i})")
                        # Arrow functions assigned to const
                        elif match := re.match(
                            r"^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(",
                            line,
                        ):
                            symbols.append(f"- Const `{match.group(1)}` (line {i})")

                if symbols:
                    result += "\n".join(symbols)
                else:
                    result += "No recognizable symbols found."

                return result

        except Exception as e:
            return f"Error analyzing file: {str(e)}"

    async def git_status(self) -> str:
        """
        Get the current Git status of the workspace, showing changed, staged, and untracked files.

        Returns:
            str: Git status output showing file changes and staging state

        Notes:
            - Shows modified, added, deleted, and untracked files
            - Indicates which changes are staged for commit
            - Useful for tracking work progress before committing
        """
        try:
            # Check if we're in a git repository
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return "Error: Not a git repository"

            # Get status
            result = subprocess.run(
                ["git", "status", "--porcelain=v2", "--branch"],
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return f"Error running git status: {result.stderr}"

            lines = result.stdout.strip().split("\n")

            output = "# Git Status\n\n"

            # Parse branch info
            branch_name = "unknown"
            for line in lines:
                if line.startswith("# branch.head"):
                    branch_name = line.split()[-1]
                    break

            output += f"**Branch:** `{branch_name}`\n\n"

            # Parse file changes
            staged = []
            unstaged = []
            untracked = []

            for line in lines:
                if line.startswith("#"):
                    continue
                if line.startswith("1") or line.startswith("2"):
                    # Changed file
                    parts = line.split()
                    if len(parts) >= 9:
                        xy = parts[1]
                        path = parts[-1]
                        if xy[0] != ".":
                            staged.append(f"- {xy[0]} `{path}`")
                        if xy[1] != ".":
                            unstaged.append(f"- {xy[1]} `{path}`")
                elif line.startswith("?"):
                    # Untracked
                    path = line[2:]
                    untracked.append(f"- `{path}`")

            if staged:
                output += "## Staged Changes\n\n"
                output += "\n".join(staged) + "\n\n"

            if unstaged:
                output += "## Unstaged Changes\n\n"
                output += "\n".join(unstaged) + "\n\n"

            if untracked:
                output += "## Untracked Files\n\n"
                output += "\n".join(untracked) + "\n\n"

            if not staged and not unstaged and not untracked:
                output += "✅ Working tree clean - no changes\n"

            return output

        except FileNotFoundError:
            return "Error: Git is not installed or not in PATH"
        except Exception as e:
            return f"Error getting git status: {str(e)}"

    async def git_commit(
        self,
        message: str,
        files: str = "",
        stage_all: str = "false",
    ) -> str:
        """
        Stage files and create a Git commit.

        Args:
            message (str): Commit message (required)
            files (str): Space-separated list of files to stage. Empty to commit already staged files.
            stage_all (str): Stage all changes before committing ("true"/"false"). Default: "false"

        Returns:
            str: Commit result with hash and summary

        Notes:
            - If files are specified, they will be staged before committing
            - Use stage_all="true" to stage all modified files
            - Returns the commit hash on success
        """
        try:
            if not message or not message.strip():
                return "Error: Commit message is required"

            # Check if we're in a git repository
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return "Error: Not a git repository"

            # Stage files if specified
            if str(stage_all).lower() == "true":
                result = subprocess.run(
                    ["git", "add", "-A"],
                    cwd=self.WORKING_DIRECTORY,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return f"Error staging files: {result.stderr}"
            elif files:
                file_list = files.split()
                for file in file_list:
                    result = subprocess.run(
                        ["git", "add", file],
                        cwd=self.WORKING_DIRECTORY,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        return f"Error staging '{file}': {result.stderr}"

            # Create commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                if (
                    "nothing to commit" in result.stdout
                    or "nothing to commit" in result.stderr
                ):
                    return "No changes to commit. Stage some files first or use stage_all='true'."
                return f"Error creating commit: {result.stderr}"

            # Get the commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )
            commit_hash = hash_result.stdout.strip()

            return f"# Commit Created\n\n**Hash:** `{commit_hash}`\n**Message:** {message}\n\n```\n{result.stdout}\n```"

        except FileNotFoundError:
            return "Error: Git is not installed or not in PATH"
        except Exception as e:
            return f"Error creating commit: {str(e)}"

    async def git_diff(
        self,
        file_path: str = "",
        staged: str = "false",
        commit: str = "",
    ) -> str:
        """
        Show Git diff for files or commits.

        Args:
            file_path (str): Specific file to diff, or empty for all changes
            staged (str): Show staged changes ("true"/"false"). Default: "false" (unstaged)
            commit (str): Compare with specific commit hash, or empty for working tree

        Returns:
            str: Diff output showing line-by-line changes

        Notes:
            - Without arguments: shows unstaged changes in working tree
            - With staged="true": shows changes staged for next commit
            - With commit: shows diff between that commit and current state
        """
        try:
            cmd = ["git", "diff"]

            if str(staged).lower() == "true":
                cmd.append("--staged")

            if commit:
                cmd.append(commit)

            if file_path:
                cmd.append("--")
                cmd.append(file_path)

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return f"Error running git diff: {result.stderr}"

            output = result.stdout.strip()

            if not output:
                return "No differences found."

            # Truncate if too long
            max_length = 10000
            if len(output) > max_length:
                output = (
                    output[:max_length]
                    + "\n\n... [diff truncated, showing first 10000 chars]"
                )

            return f"# Git Diff\n\n```diff\n{output}\n```"

        except FileNotFoundError:
            return "Error: Git is not installed or not in PATH"
        except Exception as e:
            return f"Error getting diff: {str(e)}"

    async def git_blame(
        self, file_path: str, start_line: str = "", end_line: str = ""
    ) -> str:
        """
        Show who last modified each line of a file (git blame).

        Args:
            file_path (str): Path to the file to blame
            start_line (str): Starting line number (optional)
            end_line (str): Ending line number (optional)

        Returns:
            str: Blame output showing author and commit for each line

        Notes:
            - Useful for understanding code history and attribution
            - Shows commit hash, author, date, and line content
            - Use line range to focus on specific sections
        """
        try:
            full_path = self.safe_join(file_path)
            if not os.path.exists(full_path):
                return f"Error: File '{file_path}' not found"

            cmd = ["git", "blame", "--line-porcelain"]

            if start_line and end_line:
                cmd.extend(["-L", f"{start_line},{end_line}"])

            cmd.append(file_path)

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return f"Error running git blame: {result.stderr}"

            # Parse porcelain output
            lines = result.stdout.split("\n")
            blame_data = []
            current = {}

            for line in lines:
                if line.startswith(
                    ("author ", "author-mail ", "author-time ", "summary ")
                ):
                    key = line.split(" ", 1)[0]
                    value = line.split(" ", 1)[1] if " " in line else ""
                    current[key] = value
                elif line.startswith("\t"):
                    current["content"] = line[1:]
                    blame_data.append(current)
                    current = {}
                elif line and not line.startswith(
                    ("committer", "previous", "filename", "boundary")
                ):
                    parts = line.split()
                    if len(parts) >= 3:
                        current["hash"] = parts[0][:8]
                        current["line_num"] = parts[2]

            # Format output
            output = f"# Git Blame: {file_path}\n\n"
            output += "| Line | Hash | Author | Content |\n"
            output += "|------|------|--------|--------|\n"

            for item in blame_data[:100]:  # Limit to 100 lines
                line_num = item.get("line_num", "?")
                hash_short = item.get("hash", "?")[:7]
                author = item.get("author", "?")[:15]
                content = item.get("content", "")[:50]
                content = content.replace("|", "\\|")
                output += f"| {line_num} | `{hash_short}` | {author} | `{content}` |\n"

            if len(blame_data) > 100:
                output += f"\n... and {len(blame_data) - 100} more lines"

            return output

        except FileNotFoundError:
            return "Error: Git is not installed or not in PATH"
        except Exception as e:
            return f"Error getting blame: {str(e)}"

    async def create_directory(self, path: str) -> str:
        """
        Create a new directory (and parent directories if needed) in the workspace.

        Args:
            path (str): Path of the directory to create (relative to workspace)

        Returns:
            str: Success message or error

        Notes:
            - Creates parent directories automatically (like mkdir -p)
            - Path is relative to the agent's workspace
        """
        try:
            full_path = self.safe_join(path)

            if os.path.exists(full_path):
                if os.path.isdir(full_path):
                    return f"Directory `{path}` already exists."
                else:
                    return f"Error: `{path}` exists but is a file, not a directory."

            os.makedirs(full_path, exist_ok=True)
            return f"✅ Created directory: `{path}`"

        except Exception as e:
            return f"Error creating directory: {str(e)}"

    async def rename_file(self, old_path: str, new_path: str) -> str:
        """
        Rename or move a file within the workspace.

        Args:
            old_path (str): Current path of the file
            new_path (str): New path/name for the file

        Returns:
            str: Success message or error

        Notes:
            - Can be used to rename files or move them to different directories
            - Creates destination directory if it doesn't exist
        """
        try:
            full_old_path = self.safe_join(old_path)
            full_new_path = self.safe_join(new_path)

            if not os.path.exists(full_old_path):
                return f"Error: Source file `{old_path}` not found"

            if os.path.exists(full_new_path):
                return f"Error: Destination `{new_path}` already exists"

            # Create destination directory if needed
            dest_dir = os.path.dirname(full_new_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)

            os.rename(full_old_path, full_new_path)
            return f"✅ Renamed `{old_path}` to `{new_path}`"

        except Exception as e:
            return f"Error renaming file: {str(e)}"

    async def copy_file(self, source: str, destination: str) -> str:
        """
        Copy a file or directory within the workspace.

        Args:
            source (str): Path of the file/directory to copy
            destination (str): Destination path

        Returns:
            str: Success message or error

        Notes:
            - Copies files and directories recursively
            - Creates destination directory if needed
        """
        import shutil

        try:
            full_source = self.safe_join(source)
            full_dest = self.safe_join(destination)

            if not os.path.exists(full_source):
                return f"Error: Source `{source}` not found"

            # Create destination directory if needed
            dest_dir = (
                os.path.dirname(full_dest)
                if not os.path.isdir(full_source)
                else full_dest
            )
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)

            if os.path.isdir(full_source):
                shutil.copytree(full_source, full_dest)
            else:
                shutil.copy2(full_source, full_dest)

            return f"✅ Copied `{source}` to `{destination}`"

        except Exception as e:
            return f"Error copying file: {str(e)}"

    async def get_file_metadata(self, file_path: str) -> str:
        """
        Get detailed metadata about a file (size, dates, type, encoding).

        Args:
            file_path (str): Path to the file

        Returns:
            str: File metadata including size, dates, type, and encoding info

        Notes:
            - Shows file size in human-readable format
            - Includes creation/modification times
            - Detects file type and encoding
        """
        import stat
        import mimetypes

        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            stat_info = os.stat(full_path)

            # Size formatting
            size = stat_info.st_size
            if size < 1024:
                size_str = f"{size} bytes"
            elif size < 1024 * 1024:
                size_str = f"{size/1024:.2f} KB"
            elif size < 1024 * 1024 * 1024:
                size_str = f"{size/(1024*1024):.2f} MB"
            else:
                size_str = f"{size/(1024*1024*1024):.2f} GB"

            # Times
            mtime = datetime.datetime.fromtimestamp(stat_info.st_mtime)
            ctime = datetime.datetime.fromtimestamp(stat_info.st_ctime)
            atime = datetime.datetime.fromtimestamp(stat_info.st_atime)

            # File type
            mime_type, encoding = mimetypes.guess_type(full_path)
            file_type = mime_type or "unknown"

            # Detect text encoding for text files
            detected_encoding = None
            if file_type and file_type.startswith("text"):
                try:
                    with open(full_path, "rb") as f:
                        raw = f.read(1024)
                    # Simple encoding detection
                    try:
                        raw.decode("utf-8")
                        detected_encoding = "UTF-8"
                    except:
                        try:
                            raw.decode("latin-1")
                            detected_encoding = "Latin-1"
                        except:
                            detected_encoding = "Unknown"
                except:
                    pass

            # Permissions
            mode = stat_info.st_mode
            perms = stat.filemode(mode)

            # Line count for text files
            line_count = None
            if file_type and (
                file_type.startswith("text")
                or file_type in ["application/json", "application/xml"]
            ):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        line_count = sum(1 for _ in f)
                except:
                    pass

            output = f"# File Metadata: {file_path}\n\n"
            output += f"| Property | Value |\n"
            output += f"|----------|-------|\n"
            output += f"| **Size** | {size_str} ({size:,} bytes) |\n"
            output += f"| **Type** | {file_type} |\n"
            if detected_encoding:
                output += f"| **Encoding** | {detected_encoding} |\n"
            if line_count is not None:
                output += f"| **Lines** | {line_count:,} |\n"
            output += f"| **Modified** | {mtime.strftime('%Y-%m-%d %H:%M:%S')} |\n"
            output += f"| **Created** | {ctime.strftime('%Y-%m-%d %H:%M:%S')} |\n"
            output += f"| **Accessed** | {atime.strftime('%Y-%m-%d %H:%M:%S')} |\n"
            output += f"| **Permissions** | {perms} |\n"

            return output

        except Exception as e:
            return f"Error getting file metadata: {str(e)}"

    async def diff_files(self, file1: str, file2: str, context_lines: str = "3") -> str:
        """
        Compare two files and show the differences.

        Args:
            file1 (str): Path to the first file
            file2 (str): Path to the second file
            context_lines (str): Number of context lines around changes. Default: "3"

        Returns:
            str: Unified diff showing differences between the files

        Notes:
            - Shows additions, deletions, and changes
            - Uses unified diff format
            - Useful for code review and comparing versions
        """
        import difflib

        try:
            context = int(context_lines) if context_lines else 3
        except:
            context = 3

        try:
            full_path1 = self.safe_join(file1)
            full_path2 = self.safe_join(file2)

            if not os.path.exists(full_path1):
                return f"Error: File `{file1}` not found"
            if not os.path.exists(full_path2):
                return f"Error: File `{file2}` not found"

            with open(full_path1, "r", encoding="utf-8", errors="ignore") as f:
                lines1 = f.readlines()
            with open(full_path2, "r", encoding="utf-8", errors="ignore") as f:
                lines2 = f.readlines()

            diff = difflib.unified_diff(
                lines1,
                lines2,
                fromfile=file1,
                tofile=file2,
                n=context,
            )

            diff_text = "".join(diff)

            if not diff_text:
                return f"Files `{file1}` and `{file2}` are identical."

            # Truncate if too long
            max_length = 10000
            if len(diff_text) > max_length:
                diff_text = diff_text[:max_length] + "\n\n... [diff truncated]"

            return f"# File Comparison\n\n**{file1}** vs **{file2}**\n\n```diff\n{diff_text}\n```"

        except Exception as e:
            return f"Error comparing files: {str(e)}"

    async def format_code(
        self,
        file_path: str,
        formatter: str = "auto",
    ) -> str:
        """
        Format code using language-specific formatters (black for Python, prettier for JS/TS).

        Args:
            file_path (str): Path to the file to format
            formatter (str): Formatter to use: "auto", "black", "prettier", "autopep8". Default: "auto"

        Returns:
            str: Success message with changes summary, or error

        Notes:
            - Auto-detects formatter based on file extension
            - For Python: uses black or autopep8
            - For JS/TS/JSON/CSS: uses prettier if available
            - Shows before/after line count comparison
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            # Read original content
            with open(full_path, "r", encoding="utf-8") as f:
                original = f.read()

            original_lines = len(original.split("\n"))
            formatted = None

            # Auto-detect formatter
            if formatter == "auto":
                if ext == ".py":
                    formatter = "black"
                elif ext in [".js", ".ts", ".jsx", ".tsx", ".json", ".css", ".html"]:
                    formatter = "prettier"
                else:
                    return f"No formatter available for `{ext}` files"

            # Apply formatter
            if formatter == "black" and ext == ".py":
                try:
                    import black

                    mode = black.Mode(
                        target_versions={black.TargetVersion.PY38},
                        line_length=88,
                    )
                    formatted = black.format_str(original, mode=mode)
                except ImportError:
                    return "Error: black is not installed. Run: pip install black"
                except Exception as e:
                    return f"Error formatting with black: {str(e)}"

            elif formatter == "autopep8" and ext == ".py":
                try:
                    import autopep8

                    formatted = autopep8.fix_code(original)
                except ImportError:
                    return "Error: autopep8 is not installed. Run: pip install autopep8"
                except Exception as e:
                    return f"Error formatting with autopep8: {str(e)}"

            elif formatter == "prettier":
                # Try to run prettier via subprocess
                result = subprocess.run(
                    ["prettier", "--write", full_path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return f"Error running prettier: {result.stderr}\n\nIs prettier installed? Run: npm install -g prettier"

                # Read formatted content
                with open(full_path, "r", encoding="utf-8") as f:
                    formatted = f.read()

            else:
                return f"Unknown formatter: {formatter}"

            # Write formatted content
            if formatted and formatted != original:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(formatted)

                formatted_lines = len(formatted.split("\n"))
                return f"✅ Formatted `{file_path}` with {formatter}\n\n- Original: {original_lines} lines\n- Formatted: {formatted_lines} lines"
            else:
                return f"File `{file_path}` is already properly formatted."

        except Exception as e:
            return f"Error formatting file: {str(e)}"

    # ==================== WAVE 2: 18 ADDITIONAL DEVELOPMENT TOOLS ====================

    async def insert_in_file(
        self,
        file_path: str,
        line_number: int,
        content: str,
    ) -> str:
        """
        Insert content at a specific line number in a file.

        Args:
            file_path (str): Path to the file to modify
            line_number (int): Line number to insert at (1-indexed). Content at this line and below will be shifted down.
            content (str): Content to insert

        Returns:
            str: Success message with new line count, or error

        Notes:
            - Line numbers are 1-indexed
            - Existing content at line_number and below shifts down
            - If line_number exceeds file length, content is appended
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Convert to 0-indexed
            idx = max(0, line_number - 1)

            # Ensure content ends with newline if needed
            if not content.endswith("\n"):
                content += "\n"

            # Insert content
            if idx >= len(lines):
                lines.append(content)
            else:
                lines.insert(idx, content)

            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            return f"✅ Inserted content at line {line_number} in `{file_path}`\n\n- New total lines: {len(lines)}"

        except Exception as e:
            return f"Error inserting in file: {str(e)}"

    async def delete_lines(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> str:
        """
        Delete a range of lines from a file.

        Args:
            file_path (str): Path to the file to modify
            start_line (int): First line to delete (1-indexed, inclusive)
            end_line (int): Last line to delete (1-indexed, inclusive)

        Returns:
            str: Success message with deletion summary, or error

        Notes:
            - Line numbers are 1-indexed and inclusive
            - Remaining lines shift up to fill the gap
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            original_count = len(lines)

            # Convert to 0-indexed
            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)

            if start_idx >= len(lines):
                return f"Error: Start line {start_line} is beyond file length ({original_count} lines)"

            # Delete the lines
            deleted = lines[start_idx:end_idx]
            del lines[start_idx:end_idx]

            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            return f"✅ Deleted lines {start_line}-{end_line} from `{file_path}`\n\n- Lines deleted: {len(deleted)}\n- Original lines: {original_count}\n- New lines: {len(lines)}"

        except Exception as e:
            return f"Error deleting lines: {str(e)}"

    async def get_file_line_count(
        self,
        file_path: str,
    ) -> str:
        """
        Get the total number of lines in a file.

        Args:
            file_path (str): Path to the file to count

        Returns:
            str: Line count information or error

        Notes:
            - Counts all lines including empty ones
            - Also reports non-empty line count
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total = len(lines)
            non_empty = len([l for l in lines if l.strip()])

            return f"📄 `{file_path}`\n\n- Total lines: {total}\n- Non-empty lines: {non_empty}\n- Empty lines: {total - non_empty}"

        except Exception as e:
            return f"Error counting lines: {str(e)}"

    async def search_and_replace_regex(
        self,
        file_path: str,
        pattern: str,
        replacement: str,
        flags: str = "",
    ) -> str:
        """
        Search and replace using regular expressions in a file.

        Args:
            file_path (str): Path to the file to modify
            pattern (str): Regular expression pattern to search for
            replacement (str): Replacement string (can use \\1, \\2, etc. for groups)
            flags (str): Regex flags: "i" for case-insensitive, "m" for multiline. Default: ""

        Returns:
            str: Success message with replacement count, or error

        Notes:
            - Uses Python re module syntax
            - Replacement can reference capture groups with \\1, \\2, etc.
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            # Parse flags
            re_flags = 0
            if "i" in flags:
                re_flags |= re.IGNORECASE
            if "m" in flags:
                re_flags |= re.MULTILINE

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Count matches first
            matches = re.findall(pattern, content, re_flags)
            match_count = len(matches)

            if match_count == 0:
                return f"No matches found for pattern `{pattern}` in `{file_path}`"

            # Perform replacement
            new_content = re.sub(pattern, replacement, content, flags=re_flags)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return f"✅ Replaced {match_count} occurrence(s) in `{file_path}`\n\n- Pattern: `{pattern}`\n- Replacement: `{replacement}`"

        except re.error as e:
            return f"Regex error: {str(e)}"
        except Exception as e:
            return f"Error during search and replace: {str(e)}"

    async def extract_function(
        self,
        file_path: str,
        function_name: str,
    ) -> str:
        """
        Extract a function or method definition from a file.

        Args:
            file_path (str): Path to the file
            function_name (str): Name of the function/method to extract

        Returns:
            str: The function code with line numbers, or error

        Notes:
            - Works with Python, JavaScript/TypeScript, and other common languages
            - Returns the complete function including decorators
            - Includes line number information
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
                f.seek(0)
                lines = f.readlines()

            # Python extraction using AST
            if ext == ".py":
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if node.name == function_name:
                                # Get decorators start line
                                start_line = (
                                    node.decorator_list[0].lineno
                                    if node.decorator_list
                                    else node.lineno
                                )
                                end_line = node.end_lineno

                                func_lines = lines[start_line - 1 : end_line]
                                result = f"📦 Function `{function_name}` from `{file_path}` (lines {start_line}-{end_line}):\n\n```python\n"
                                for i, line in enumerate(func_lines, start=start_line):
                                    result += f"{i:4} | {line}"
                                result += "```"
                                return result

                    return f"Function `{function_name}` not found in `{file_path}`"
                except SyntaxError as e:
                    return f"Syntax error parsing Python file: {str(e)}"

            # JavaScript/TypeScript extraction using regex
            elif ext in [".js", ".ts", ".jsx", ".tsx"]:
                # Match function declarations and arrow functions
                patterns = [
                    rf"(?:export\s+)?(?:async\s+)?function\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{",
                    rf"(?:export\s+)?(?:const|let|var)\s+{re.escape(function_name)}\s*=\s*(?:async\s+)?\([^)]*\)\s*=>\s*\{{",
                    rf"(?:async\s+)?{re.escape(function_name)}\s*\([^)]*\)\s*\{{",
                ]

                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        start_pos = match.start()
                        # Find matching closing brace
                        brace_count = 0
                        end_pos = start_pos
                        for i, char in enumerate(content[start_pos:]):
                            if char == "{":
                                brace_count += 1
                            elif char == "}":
                                brace_count -= 1
                                if brace_count == 0:
                                    end_pos = start_pos + i + 1
                                    break

                        # Find line numbers
                        start_line = content[:start_pos].count("\n") + 1
                        end_line = content[:end_pos].count("\n") + 1

                        func_lines = lines[start_line - 1 : end_line]
                        result = f"📦 Function `{function_name}` from `{file_path}` (lines {start_line}-{end_line}):\n\n```{ext[1:]}\n"
                        for i, line in enumerate(func_lines, start=start_line):
                            result += f"{i:4} | {line}"
                        result += "```"
                        return result

                return f"Function `{function_name}` not found in `{file_path}`"

            else:
                return f"Function extraction not supported for `{ext}` files"

        except Exception as e:
            return f"Error extracting function: {str(e)}"

    async def get_imports(
        self,
        file_path: str,
    ) -> str:
        """
        Get all import statements from a file.

        Args:
            file_path (str): Path to the file

        Returns:
            str: List of imports with line numbers, or error

        Notes:
            - Supports Python, JavaScript/TypeScript imports
            - Groups standard library, third-party, and local imports for Python
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
                f.seek(0)
                lines = f.readlines()

            imports = []

            # Python imports
            if ext == ".py":
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                import_str = f"import {alias.name}"
                                if alias.asname:
                                    import_str += f" as {alias.asname}"
                                imports.append((node.lineno, import_str))
                        elif isinstance(node, ast.ImportFrom):
                            module = node.module or ""
                            names = ", ".join(
                                [
                                    (f"{a.name} as {a.asname}" if a.asname else a.name)
                                    for a in node.names
                                ]
                            )
                            dots = "." * node.level
                            imports.append(
                                (node.lineno, f"from {dots}{module} import {names}")
                            )
                except SyntaxError:
                    # Fallback to regex
                    for i, line in enumerate(lines, 1):
                        if re.match(r"^\s*(import|from)\s+", line):
                            imports.append((i, line.strip()))

            # JavaScript/TypeScript imports
            elif ext in [".js", ".ts", ".jsx", ".tsx"]:
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("import ") or re.match(
                        r"^(const|let|var)\s+\{?.*\}?\s*=\s*require\(", stripped
                    ):
                        imports.append((i, stripped))

            else:
                return f"Import extraction not supported for `{ext}` files"

            if not imports:
                return f"No imports found in `{file_path}`"

            result = f"📥 Imports in `{file_path}`:\n\n"
            for line_no, import_stmt in sorted(imports):
                result += f"  Line {line_no:4}: {import_stmt}\n"
            result += f"\nTotal: {len(imports)} import(s)"

            return result

        except Exception as e:
            return f"Error getting imports: {str(e)}"

    async def append_to_file(
        self,
        file_path: str,
        content: str,
    ) -> str:
        """
        Append content to the end of a file.

        Args:
            file_path (str): Path to the file
            content (str): Content to append

        Returns:
            str: Success message, or error

        Notes:
            - Creates file if it doesn't exist
            - Adds newline before content if file doesn't end with one
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            # Check if file exists and get its current state
            needs_newline = False
            if os.path.exists(full_path):
                with open(full_path, "rb") as f:
                    f.seek(-1, 2) if os.path.getsize(full_path) > 0 else None
                    if os.path.getsize(full_path) > 0:
                        last_char = f.read(1)
                        needs_newline = last_char != b"\n"

            with open(full_path, "a", encoding="utf-8") as f:
                if needs_newline:
                    f.write("\n")
                f.write(content)
                if not content.endswith("\n"):
                    f.write("\n")

            lines_added = len(content.split("\n"))
            return f"✅ Appended {lines_added} line(s) to `{file_path}`"

        except Exception as e:
            return f"Error appending to file: {str(e)}"

    async def prepend_to_file(
        self,
        file_path: str,
        content: str,
    ) -> str:
        """
        Prepend content to the beginning of a file.

        Args:
            file_path (str): Path to the file
            content (str): Content to prepend

        Returns:
            str: Success message, or error

        Notes:
            - Creates file if it doesn't exist
            - Adds newline after content if needed
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            existing_content = ""
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    existing_content = f.read()

            # Ensure content ends with newline
            if not content.endswith("\n"):
                content += "\n"

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content + existing_content)

            lines_added = len(content.split("\n")) - 1
            return f"✅ Prepended {lines_added} line(s) to `{file_path}`"

        except Exception as e:
            return f"Error prepending to file: {str(e)}"

    async def git_log(
        self,
        count: int = 10,
        file_path: str = "",
        format_type: str = "oneline",
    ) -> str:
        """
        Get git commit history.

        Args:
            count (int): Number of commits to show. Default: 10
            file_path (str): Optional file path to show history for
            format_type (str): Log format: "oneline", "short", "full". Default: "oneline"

        Returns:
            str: Git log output, or error

        Notes:
            - Executes from the workspace directory
            - Restricted to agent workspace
        """
        try:
            # Build git log command
            format_map = {
                "oneline": "--oneline",
                "short": "--format=short",
                "full": "--format=fuller",
            }
            fmt = format_map.get(format_type, "--oneline")

            cmd = ["git", "log", fmt, "-n", str(count)]
            if file_path:
                safe_path = self.safe_join(file_path)
                cmd.extend(["--", safe_path])

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                stderr = result.stderr
                if "not a git repository" in stderr.lower():
                    return "Error: Not a git repository"
                return f"Error: {stderr}"

            stdout = result.stdout
            if not stdout.strip():
                return "No commits found"

            return f"📜 Git Log (last {count} commits):\n\n```\n{stdout}\n```"

        except Exception as e:
            return f"Error getting git log: {str(e)}"

    async def git_branch(
        self,
        action: str = "list",
        branch_name: str = "",
    ) -> str:
        """
        Manage git branches.

        Args:
            action (str): Branch action: "list", "create", "switch", "delete". Default: "list"
            branch_name (str): Branch name for create/switch/delete actions

        Returns:
            str: Branch operation result, or error

        Notes:
            - For delete, use with caution
            - Restricted to agent workspace
        """
        try:
            if action == "list":
                cmd = ["git", "branch", "-a"]
            elif action == "create":
                if not branch_name:
                    return "Error: Branch name required for create action"
                cmd = ["git", "branch", branch_name]
            elif action == "switch":
                if not branch_name:
                    return "Error: Branch name required for switch action"
                cmd = ["git", "checkout", branch_name]
            elif action == "delete":
                if not branch_name:
                    return "Error: Branch name required for delete action"
                cmd = ["git", "branch", "-d", branch_name]
            else:
                return f"Unknown action: {action}. Use: list, create, switch, delete"

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                stderr = result.stderr
                return f"Error: {stderr}"

            stdout = result.stdout
            if action == "list":
                return f"🌿 Git Branches:\n\n```\n{stdout}\n```"
            else:
                return f"✅ Branch {action} successful: {branch_name}\n\n{stdout}"

        except Exception as e:
            return f"Error with git branch: {str(e)}"

    async def git_stash(
        self,
        action: str = "list",
        message: str = "",
    ) -> str:
        """
        Manage git stash.

        Args:
            action (str): Stash action: "list", "push", "pop", "apply", "drop". Default: "list"
            message (str): Stash message for push action

        Returns:
            str: Stash operation result, or error

        Notes:
            - push: saves changes to stash
            - pop: applies and removes from stash
            - apply: applies but keeps in stash
            - Restricted to agent workspace
        """
        try:
            if action == "list":
                cmd = ["git", "stash", "list"]
            elif action == "push":
                cmd = ["git", "stash", "push"]
                if message:
                    cmd.extend(["-m", message])
            elif action == "pop":
                cmd = ["git", "stash", "pop"]
            elif action == "apply":
                cmd = ["git", "stash", "apply"]
            elif action == "drop":
                cmd = ["git", "stash", "drop"]
            else:
                return f"Unknown action: {action}. Use: list, push, pop, apply, drop"

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                stderr = result.stderr
                # "No stash entries found" is not really an error for list
                if "No stash" in stderr and action == "list":
                    return "📦 No stash entries found"
                return f"Error: {stderr}"

            stdout = result.stdout
            if action == "list":
                if not stdout.strip():
                    return "📦 No stash entries found"
                return f"📦 Git Stash:\n\n```\n{stdout}\n```"
            else:
                return f"✅ Stash {action} successful\n\n{stdout}"

        except Exception as e:
            return f"Error with git stash: {str(e)}"

    async def find_duplicate_code(
        self,
        directory: str = ".",
        min_lines: int = 4,
        file_extensions: str = ".py,.js,.ts",
    ) -> str:
        """
        Find potential duplicate code blocks across files.

        Args:
            directory (str): Directory to search. Default: "."
            min_lines (int): Minimum consecutive lines to consider duplicate. Default: 4
            file_extensions (str): Comma-separated file extensions to check. Default: ".py,.js,.ts"

        Returns:
            str: Report of potential duplicates, or error

        Notes:
            - Compares normalized (whitespace-stripped) code blocks
            - Reports file paths and line numbers
            - Restricted to agent workspace
        """
        try:
            full_dir = self.safe_join(directory)

            if not os.path.exists(full_dir):
                return f"Error: Directory `{directory}` not found"

            extensions = [ext.strip() for ext in file_extensions.split(",")]

            # Collect all code blocks from files
            code_blocks = {}  # hash -> [(file, start_line, block)]

            for root, dirs, files in os.walk(full_dir):
                for file in files:
                    if not any(file.endswith(ext) for ext in extensions):
                        continue

                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.WORKING_DIRECTORY)

                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                    except Exception:
                        continue

                    # Extract blocks of min_lines consecutive lines
                    for start in range(len(lines) - min_lines + 1):
                        block = lines[start : start + min_lines]
                        # Normalize: strip whitespace and skip if mostly blank
                        normalized = "\n".join([l.strip() for l in block])
                        if len(normalized.replace("\n", "").strip()) < 20:
                            continue  # Skip mostly empty blocks

                        block_hash = hash(normalized)
                        if block_hash not in code_blocks:
                            code_blocks[block_hash] = []
                        code_blocks[block_hash].append(
                            (rel_path, start + 1, "".join(block))
                        )

            # Find duplicates (blocks appearing more than once)
            duplicates = []
            for block_hash, locations in code_blocks.items():
                if len(locations) > 1:
                    # Remove duplicates within same file (overlapping blocks)
                    unique_locations = []
                    seen = set()
                    for loc in locations:
                        key = (loc[0], loc[1])
                        if key not in seen:
                            seen.add(key)
                            unique_locations.append(loc)
                    if len(unique_locations) > 1:
                        duplicates.append(unique_locations)

            if not duplicates:
                return f"✅ No duplicate code blocks found (min {min_lines} lines)"

            # Sort by number of occurrences
            duplicates.sort(key=lambda x: len(x), reverse=True)

            result = (
                f"🔍 Found {len(duplicates)} potential duplicate code pattern(s):\n\n"
            )

            for i, locations in enumerate(duplicates[:10], 1):  # Show top 10
                result += f"**Duplicate #{i}** ({len(locations)} occurrences):\n"
                for file, line, _ in locations[:5]:  # Show first 5 locations
                    result += f"  - `{file}` line {line}\n"
                if len(locations) > 5:
                    result += f"  - ... and {len(locations) - 5} more\n"
                result += f"\n  Preview:\n```\n{locations[0][2][:200]}...\n```\n\n"

            return result

        except Exception as e:
            return f"Error finding duplicates: {str(e)}"

    async def get_function_signature(
        self,
        file_path: str,
        function_name: str,
    ) -> str:
        """
        Get the signature of a function without the full body.

        Args:
            file_path (str): Path to the file
            function_name (str): Name of the function

        Returns:
            str: Function signature including parameters and return type, or error

        Notes:
            - Includes decorators, type hints, and docstring summary
            - Supports Python and JavaScript/TypeScript
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Python signature extraction
            if ext == ".py":
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if node.name == function_name:
                                result = f"📝 Signature of `{function_name}` in `{file_path}`:\n\n```python\n"

                                # Add decorators
                                for dec in node.decorator_list:
                                    if isinstance(dec, ast.Name):
                                        result += f"@{dec.id}\n"
                                    elif isinstance(dec, ast.Call):
                                        if isinstance(dec.func, ast.Name):
                                            result += f"@{dec.func.id}(...)\n"

                                # Build signature
                                async_prefix = (
                                    "async "
                                    if isinstance(node, ast.AsyncFunctionDef)
                                    else ""
                                )
                                args = []
                                for arg in node.args.args:
                                    arg_str = arg.arg
                                    if arg.annotation:
                                        arg_str += f": {ast.unparse(arg.annotation)}"
                                    args.append(arg_str)

                                returns = ""
                                if node.returns:
                                    returns = f" -> {ast.unparse(node.returns)}"

                                result += f"{async_prefix}def {function_name}({', '.join(args)}){returns}:\n"

                                # Add docstring summary if present
                                docstring = ast.get_docstring(node)
                                if docstring:
                                    first_line = docstring.split("\n")[0]
                                    result += f'    """{first_line}..."""\n'

                                result += "    ...\n```"
                                return result

                    return f"Function `{function_name}` not found in `{file_path}`"
                except SyntaxError as e:
                    return f"Syntax error parsing file: {str(e)}"

            # JavaScript/TypeScript
            elif ext in [".js", ".ts", ".jsx", ".tsx"]:
                # Match function declarations
                patterns = [
                    rf"((?:export\s+)?(?:async\s+)?function\s+{re.escape(function_name)}\s*\([^)]*\)(?:\s*:\s*[^{{]+)?)",
                    rf"((?:export\s+)?(?:const|let|var)\s+{re.escape(function_name)}\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\([^)]*\)(?:\s*:\s*[^=]+)?\s*=>)",
                ]

                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        signature = match.group(1).strip()
                        return f"📝 Signature of `{function_name}` in `{file_path}`:\n\n```{ext[1:]}\n{signature}\n```"

                return f"Function `{function_name}` not found in `{file_path}`"

            else:
                return f"Signature extraction not supported for `{ext}` files"

        except Exception as e:
            return f"Error getting function signature: {str(e)}"

    async def validate_json(
        self,
        file_path: str,
    ) -> str:
        """
        Validate JSON file syntax and structure.

        Args:
            file_path (str): Path to the JSON file

        Returns:
            str: Validation result with any errors, or success

        Notes:
            - Reports specific error location (line, column)
            - Also reports basic structure info on success
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                data = json.loads(content)

                # Analyze structure
                if isinstance(data, dict):
                    keys = list(data.keys())
                    structure = f"Object with {len(keys)} top-level key(s)"
                    if keys:
                        structure += f": {', '.join(keys[:5])}"
                        if len(keys) > 5:
                            structure += f"... (+{len(keys) - 5} more)"
                elif isinstance(data, list):
                    structure = f"Array with {len(data)} element(s)"
                else:
                    structure = f"Primitive value: {type(data).__name__}"

                return f"✅ Valid JSON in `{file_path}`\n\n- Structure: {structure}\n- Size: {len(content)} bytes"

            except json.JSONDecodeError as e:
                # Find the error location
                lines = content[: e.pos].split("\n")
                line_no = len(lines)
                col_no = len(lines[-1]) + 1 if lines else 1

                return f"❌ Invalid JSON in `{file_path}`\n\n- Error: {e.msg}\n- Location: Line {line_no}, Column {col_no}\n- Context: `{content[max(0, e.pos-20):e.pos+20]}`"

        except Exception as e:
            return f"Error validating JSON: {str(e)}"

    async def validate_yaml(
        self,
        file_path: str,
    ) -> str:
        """
        Validate YAML file syntax and structure.

        Args:
            file_path (str): Path to the YAML file

        Returns:
            str: Validation result with any errors, or success

        Notes:
            - Reports specific error location
            - Also reports basic structure info on success
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                import yaml

                data = yaml.safe_load(content)

                # Analyze structure
                if isinstance(data, dict):
                    keys = list(data.keys())
                    structure = f"Mapping with {len(keys)} top-level key(s)"
                    if keys:
                        structure += f": {', '.join(str(k) for k in keys[:5])}"
                        if len(keys) > 5:
                            structure += f"... (+{len(keys) - 5} more)"
                elif isinstance(data, list):
                    structure = f"Sequence with {len(data)} element(s)"
                elif data is None:
                    structure = "Empty document"
                else:
                    structure = f"Scalar value: {type(data).__name__}"

                return f"✅ Valid YAML in `{file_path}`\n\n- Structure: {structure}\n- Size: {len(content)} bytes"

            except yaml.YAMLError as e:
                error_msg = str(e)
                if hasattr(e, "problem_mark"):
                    mark = e.problem_mark
                    return f"❌ Invalid YAML in `{file_path}`\n\n- Error: {e.problem}\n- Location: Line {mark.line + 1}, Column {mark.column + 1}"
                return f"❌ Invalid YAML in `{file_path}`\n\n- Error: {error_msg}"

        except ImportError:
            return "Error: PyYAML is not installed. Run: pip install pyyaml"
        except Exception as e:
            return f"Error validating YAML: {str(e)}"

    async def minify_json(
        self,
        file_path: str,
        output_path: str = "",
    ) -> str:
        """
        Minify a JSON file by removing whitespace.

        Args:
            file_path (str): Path to the JSON file
            output_path (str): Optional output path. If empty, overwrites input file.

        Returns:
            str: Success message with size comparison, or error

        Notes:
            - Removes all unnecessary whitespace
            - Reports size reduction
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            original_size = len(content)

            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                return f"Error: Invalid JSON - {e.msg}"

            minified = json.dumps(data, separators=(",", ":"))
            minified_size = len(minified)

            out_path = self.safe_join(output_path) if output_path else full_path

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(minified)

            reduction = ((original_size - minified_size) / original_size) * 100

            return f"✅ Minified JSON\n\n- Original: {original_size} bytes\n- Minified: {minified_size} bytes\n- Reduction: {reduction:.1f}%\n- Output: `{output_path or file_path}`"

        except Exception as e:
            return f"Error minifying JSON: {str(e)}"

    async def prettify_json(
        self,
        file_path: str,
        indent: int = 2,
        output_path: str = "",
    ) -> str:
        """
        Prettify/format a JSON file with indentation.

        Args:
            file_path (str): Path to the JSON file
            indent (int): Number of spaces for indentation. Default: 2
            output_path (str): Optional output path. If empty, overwrites input file.

        Returns:
            str: Success message, or error

        Notes:
            - Formats with specified indentation
            - Sorts keys alphabetically
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            original_size = len(content)

            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                return f"Error: Invalid JSON - {e.msg}"

            prettified = json.dumps(data, indent=indent, sort_keys=True)
            prettified_size = len(prettified)

            out_path = self.safe_join(output_path) if output_path else full_path

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(prettified)

            return f"✅ Prettified JSON\n\n- Original: {original_size} bytes\n- Prettified: {prettified_size} bytes\n- Indent: {indent} spaces\n- Output: `{output_path or file_path}`"

        except Exception as e:
            return f"Error prettifying JSON: {str(e)}"

    async def count_lines_of_code(
        self,
        directory: str = ".",
        file_extensions: str = ".py,.js,.ts,.jsx,.tsx,.java,.c,.cpp,.go,.rs",
        exclude_dirs: str = "node_modules,.git,__pycache__,venv,.venv,dist,build",
    ) -> str:
        """
        Count lines of code in a directory, excluding comments and blank lines.

        Args:
            directory (str): Directory to analyze. Default: "."
            file_extensions (str): Comma-separated file extensions to count. Default: common code extensions
            exclude_dirs (str): Comma-separated directory names to exclude. Default: common non-source dirs

        Returns:
            str: Report with line counts by file type, or error

        Notes:
            - Counts total lines, code lines, comment lines, and blank lines
            - Groups by file extension
            - Restricted to agent workspace
        """
        try:
            full_dir = self.safe_join(directory)

            if not os.path.exists(full_dir):
                return f"Error: Directory `{directory}` not found"

            extensions = [ext.strip() for ext in file_extensions.split(",")]
            excludes = set(d.strip() for d in exclude_dirs.split(","))

            stats = {}  # ext -> {files, total, code, comments, blank}

            def is_comment(line, ext):
                stripped = line.strip()
                if ext == ".py":
                    return stripped.startswith("#")
                elif ext in [
                    ".js",
                    ".ts",
                    ".jsx",
                    ".tsx",
                    ".java",
                    ".c",
                    ".cpp",
                    ".go",
                    ".rs",
                ]:
                    return (
                        stripped.startswith("//")
                        or stripped.startswith("/*")
                        or stripped.startswith("*")
                    )
                return False

            for root, dirs, files in os.walk(full_dir):
                # Skip excluded directories
                dirs[:] = [d for d in dirs if d not in excludes]

                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in extensions:
                        continue

                    file_path = os.path.join(root, file)
                    try:
                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            lines = f.readlines()
                    except Exception:
                        continue

                    if ext not in stats:
                        stats[ext] = {
                            "files": 0,
                            "total": 0,
                            "code": 0,
                            "comments": 0,
                            "blank": 0,
                        }

                    stats[ext]["files"] += 1
                    for line in lines:
                        stats[ext]["total"] += 1
                        if not line.strip():
                            stats[ext]["blank"] += 1
                        elif is_comment(line, ext):
                            stats[ext]["comments"] += 1
                        else:
                            stats[ext]["code"] += 1

            if not stats:
                return f"No code files found in `{directory}`"

            # Build report
            result = f"📊 Lines of Code Report for `{directory}`\n\n"
            result += "| Extension | Files | Total | Code | Comments | Blank |\n"
            result += "|-----------|-------|-------|------|----------|-------|\n"

            total_files = 0
            total_total = 0
            total_code = 0
            total_comments = 0
            total_blank = 0

            for ext, s in sorted(
                stats.items(), key=lambda x: x[1]["code"], reverse=True
            ):
                result += f"| {ext} | {s['files']} | {s['total']} | {s['code']} | {s['comments']} | {s['blank']} |\n"
                total_files += s["files"]
                total_total += s["total"]
                total_code += s["code"]
                total_comments += s["comments"]
                total_blank += s["blank"]

            result += f"| **Total** | **{total_files}** | **{total_total}** | **{total_code}** | **{total_comments}** | **{total_blank}** |\n"

            return result

        except Exception as e:
            return f"Error counting lines: {str(e)}"

    async def find_todo_comments(
        self,
        directory: str = ".",
        tags: str = "TODO,FIXME,HACK,XXX,BUG",
        file_extensions: str = ".py,.js,.ts,.jsx,.tsx,.java,.c,.cpp,.go,.rs",
    ) -> str:
        """
        Find TODO, FIXME, and other tagged comments in code files.

        Args:
            directory (str): Directory to search. Default: "."
            tags (str): Comma-separated tags to search for. Default: "TODO,FIXME,HACK,XXX,BUG"
            file_extensions (str): Comma-separated file extensions to search. Default: common code extensions

        Returns:
            str: Report of found comments with file locations, or error

        Notes:
            - Case-insensitive tag matching
            - Shows context (line content)
            - Grouped by tag type
            - Restricted to agent workspace
        """
        try:
            full_dir = self.safe_join(directory)

            if not os.path.exists(full_dir):
                return f"Error: Directory `{directory}` not found"

            extensions = [ext.strip() for ext in file_extensions.split(",")]
            tag_list = [t.strip().upper() for t in tags.split(",")]

            findings = {tag: [] for tag in tag_list}

            # Build regex pattern
            pattern = r"\b(" + "|".join(tag_list) + r")\b\s*:?\s*(.*)$"

            for root, dirs, files in os.walk(full_dir):
                # Skip common non-source directories
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in ["node_modules", ".git", "__pycache__", "venv", ".venv"]
                ]

                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in extensions:
                        continue

                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.WORKING_DIRECTORY)

                    try:
                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            for line_no, line in enumerate(f, 1):
                                match = re.search(pattern, line, re.IGNORECASE)
                                if match:
                                    tag = match.group(1).upper()
                                    comment = match.group(2).strip()[
                                        :100
                                    ]  # Limit length
                                    findings[tag].append((rel_path, line_no, comment))
                    except Exception:
                        continue

            # Build report
            total = sum(len(v) for v in findings.values())
            if total == 0:
                return f"✅ No {', '.join(tag_list)} comments found in `{directory}`"

            result = f"📋 Found {total} tagged comment(s) in `{directory}`\n\n"

            for tag in tag_list:
                if findings[tag]:
                    result += f"### {tag} ({len(findings[tag])})\n\n"
                    for file, line, comment in findings[tag][
                        :20
                    ]:  # Limit to 20 per tag
                        result += f"- `{file}:{line}`: {comment}\n"
                    if len(findings[tag]) > 20:
                        result += f"- ... and {len(findings[tag]) - 20} more\n"
                    result += "\n"

            return result

        except Exception as e:
            return f"Error finding TODO comments: {str(e)}"

    async def generate_docstring(
        self,
        file_path: str,
        function_name: str,
        style: str = "google",
    ) -> str:
        """
        Generate a docstring template for a function.

        Args:
            file_path (str): Path to the file containing the function
            function_name (str): Name of the function to document
            style (str): Docstring style: "google", "numpy", "sphinx". Default: "google"

        Returns:
            str: Generated docstring template, or error

        Notes:
            - Extracts function signature and generates appropriate docstring
            - Includes Args, Returns, and Raises sections
            - Supports Python functions
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            if ext != ".py":
                return f"Docstring generation only supported for Python files"

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return f"Syntax error parsing file: {str(e)}"

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == function_name:
                        # Extract parameters
                        params = []
                        for arg in node.args.args:
                            param_type = ""
                            if arg.annotation:
                                param_type = ast.unparse(arg.annotation)
                            params.append((arg.arg, param_type))

                        # Extract return type
                        return_type = ""
                        if node.returns:
                            return_type = ast.unparse(node.returns)

                        # Generate docstring based on style
                        if style == "google":
                            docstring = self._generate_google_docstring(
                                function_name, params, return_type
                            )
                        elif style == "numpy":
                            docstring = self._generate_numpy_docstring(
                                function_name, params, return_type
                            )
                        elif style == "sphinx":
                            docstring = self._generate_sphinx_docstring(
                                function_name, params, return_type
                            )
                        else:
                            return f"Unknown docstring style: {style}. Use: google, numpy, sphinx"

                        return f"📝 Generated {style}-style docstring for `{function_name}`:\n\n```python\n{docstring}\n```"

            return f"Function `{function_name}` not found in `{file_path}`"

        except Exception as e:
            return f"Error generating docstring: {str(e)}"

    def _generate_google_docstring(self, func_name, params, return_type):
        """Generate Google-style docstring."""
        lines = [
            '"""Short description of the function.',
            "",
            "Longer description if needed.",
            "",
        ]

        if params:
            lines.append("Args:")
            for name, ptype in params:
                if name == "self":
                    continue
                type_hint = f" ({ptype})" if ptype else ""
                lines.append(f"    {name}{type_hint}: Description of {name}.")
            lines.append("")

        if return_type:
            lines.append("Returns:")
            lines.append(f"    {return_type}: Description of return value.")
            lines.append("")

        lines.append("Raises:")
        lines.append("    ExceptionType: Description of when this exception is raised.")
        lines.append('"""')

        return "\n".join(lines)

    def _generate_numpy_docstring(self, func_name, params, return_type):
        """Generate NumPy-style docstring."""
        lines = [
            '"""Short description of the function.',
            "",
            "Longer description if needed.",
            "",
        ]

        if params:
            lines.append("Parameters")
            lines.append("----------")
            for name, ptype in params:
                if name == "self":
                    continue
                type_hint = f" : {ptype}" if ptype else ""
                lines.append(f"{name}{type_hint}")
                lines.append(f"    Description of {name}.")
            lines.append("")

        if return_type:
            lines.append("Returns")
            lines.append("-------")
            lines.append(return_type)
            lines.append("    Description of return value.")
            lines.append("")

        lines.append("Raises")
        lines.append("------")
        lines.append("ExceptionType")
        lines.append("    Description of when this exception is raised.")
        lines.append('"""')

        return "\n".join(lines)

    def _generate_sphinx_docstring(self, func_name, params, return_type):
        """Generate Sphinx-style docstring."""
        lines = [
            '"""Short description of the function.',
            "",
            "Longer description if needed.",
            "",
        ]

        for name, ptype in params:
            if name == "self":
                continue
            if ptype:
                lines.append(f":param {name}: Description of {name}.")
                lines.append(f":type {name}: {ptype}")
            else:
                lines.append(f":param {name}: Description of {name}.")

        if return_type:
            lines.append(f":returns: Description of return value.")
            lines.append(f":rtype: {return_type}")

        lines.append(
            ":raises ExceptionType: Description of when this exception is raised."
        )
        lines.append('"""')

        return "\n".join(lines)

    # ==================== WAVE 3: ADDITIONAL DEVELOPMENT TOOLS ====================

    async def get_file_tree(
        self,
        directory: str = ".",
        max_depth: int = 3,
        show_hidden: bool = False,
        show_size: bool = False,
    ) -> str:
        """
        Generate a visual directory tree structure.

        Args:
            directory (str): Directory to start from. Default: "."
            max_depth (int): Maximum depth to traverse. Default: 3
            show_hidden (bool): Include hidden files/folders. Default: False
            show_size (bool): Show file sizes. Default: False

        Returns:
            str: Visual tree structure of the directory

        Notes:
            - Uses ASCII characters for tree visualization
            - Skips common non-essential directories (node_modules, .git, etc.)
            - Restricted to agent workspace
        """
        try:
            full_dir = self.safe_join(directory)

            if not os.path.exists(full_dir):
                return f"Error: Directory `{directory}` not found"

            skip_dirs = {
                ".git",
                "node_modules",
                "__pycache__",
                ".venv",
                "venv",
                ".pytest_cache",
                ".mypy_cache",
            }

            def build_tree(path, prefix="", depth=0):
                if depth > max_depth:
                    return ""

                result = ""
                try:
                    entries = sorted(os.listdir(path))
                except PermissionError:
                    return f"{prefix}[Permission Denied]\n"

                # Filter hidden files if needed
                if not show_hidden:
                    entries = [e for e in entries if not e.startswith(".")]

                # Separate dirs and files
                dirs = []
                files = []
                for entry in entries:
                    entry_path = os.path.join(path, entry)
                    if os.path.isdir(entry_path):
                        if entry not in skip_dirs:
                            dirs.append(entry)
                    else:
                        files.append(entry)

                all_entries = dirs + files
                for i, entry in enumerate(all_entries):
                    is_last = i == len(all_entries) - 1
                    connector = "└── " if is_last else "├── "
                    entry_path = os.path.join(path, entry)

                    # Add size info if requested
                    size_info = ""
                    if show_size and os.path.isfile(entry_path):
                        try:
                            size = os.path.getsize(entry_path)
                            if size < 1024:
                                size_info = f" ({size}B)"
                            elif size < 1024 * 1024:
                                size_info = f" ({size // 1024}KB)"
                            else:
                                size_info = f" ({size // (1024 * 1024)}MB)"
                        except OSError:
                            pass

                    if os.path.isdir(entry_path):
                        result += f"{prefix}{connector}{entry}/\n"
                        extension = "    " if is_last else "│   "
                        result += build_tree(entry_path, prefix + extension, depth + 1)
                    else:
                        result += f"{prefix}{connector}{entry}{size_info}\n"

                return result

            rel_dir = os.path.relpath(full_dir, self.WORKING_DIRECTORY)
            header = f"📁 {rel_dir if rel_dir != '.' else 'workspace'}/\n"
            tree = build_tree(full_dir)

            if not tree:
                return f"{header}(empty directory)"

            return f"{header}{tree}"

        except Exception as e:
            return f"Error generating file tree: {str(e)}"

    async def move_file(
        self,
        source: str,
        destination: str,
    ) -> str:
        """
        Move a file or directory to a new location.

        Args:
            source (str): Source path
            destination (str): Destination path

        Returns:
            str: Success message or error

        Notes:
            - Can move files or directories
            - Will overwrite destination if it exists
            - Restricted to agent workspace
        """
        try:
            src_path = self.safe_join(source)
            dst_path = self.safe_join(destination)

            if not os.path.exists(src_path):
                return f"Error: Source `{source}` not found"

            # If destination is a directory, move into it
            if os.path.isdir(dst_path):
                dst_path = os.path.join(dst_path, os.path.basename(src_path))

            import shutil

            shutil.move(src_path, dst_path)

            return f"✅ Moved `{source}` to `{destination}`"

        except Exception as e:
            return f"Error moving file: {str(e)}"

    async def find_references(
        self,
        symbol: str,
        file_extensions: str = ".py,.js,.ts,.jsx,.tsx",
        directory: str = ".",
    ) -> str:
        """
        Find all references to a symbol (function, class, variable) across files.

        Args:
            symbol (str): The symbol name to search for
            file_extensions (str): Comma-separated file extensions to search. Default: ".py,.js,.ts,.jsx,.tsx"
            directory (str): Directory to search. Default: "."

        Returns:
            str: List of references with file paths and line numbers

        Notes:
            - Searches for whole word matches
            - Groups results by file
            - Shows context line for each reference
            - Restricted to agent workspace
        """
        try:
            full_dir = self.safe_join(directory)

            if not os.path.exists(full_dir):
                return f"Error: Directory `{directory}` not found"

            extensions = [ext.strip() for ext in file_extensions.split(",")]
            skip_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv"}

            # Build regex for whole word match
            pattern = rf"\b{re.escape(symbol)}\b"

            references = {}  # file -> [(line_no, line_content, context)]

            for root, dirs, files in os.walk(full_dir):
                dirs[:] = [d for d in dirs if d not in skip_dirs]

                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in extensions:
                        continue

                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.WORKING_DIRECTORY)

                    try:
                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            lines = f.readlines()

                        for i, line in enumerate(lines, 1):
                            if re.search(pattern, line):
                                if rel_path not in references:
                                    references[rel_path] = []

                                # Determine reference type
                                ref_type = "reference"
                                stripped = line.strip()
                                if ext == ".py":
                                    if stripped.startswith(
                                        f"def {symbol}"
                                    ) or stripped.startswith(f"async def {symbol}"):
                                        ref_type = "definition"
                                    elif stripped.startswith(f"class {symbol}"):
                                        ref_type = "definition"
                                    elif (
                                        f"{symbol} =" in stripped
                                        and not stripped.startswith("#")
                                    ):
                                        ref_type = "assignment"
                                    elif (
                                        f"import {symbol}" in stripped
                                        or f"from " in stripped
                                        and f" import " in stripped
                                        and symbol in stripped
                                    ):
                                        ref_type = "import"
                                elif ext in [".js", ".ts", ".jsx", ".tsx"]:
                                    if (
                                        f"function {symbol}" in stripped
                                        or f"const {symbol}" in stripped
                                        or f"let {symbol}" in stripped
                                    ):
                                        ref_type = "definition"
                                    elif f"class {symbol}" in stripped:
                                        ref_type = "definition"
                                    elif "import" in stripped:
                                        ref_type = "import"

                                references[rel_path].append(
                                    (i, line.rstrip()[:100], ref_type)
                                )

                    except Exception:
                        continue

            if not references:
                return f"No references found for `{symbol}` in `{directory}`"

            total = sum(len(refs) for refs in references.values())
            result = f"🔍 Found {total} reference(s) to `{symbol}` in {len(references)} file(s):\n\n"

            for file, refs in sorted(references.items()):
                result += f"**{file}** ({len(refs)} references):\n"
                for line_no, content, ref_type in refs[:10]:  # Limit per file
                    type_icon = {
                        "definition": "📝",
                        "assignment": "📌",
                        "import": "📦",
                    }.get(ref_type, "👉")
                    result += f"  {type_icon} Line {line_no}: `{content[:80]}`\n"
                if len(refs) > 10:
                    result += f"  ... and {len(refs) - 10} more\n"
                result += "\n"

            return result

        except Exception as e:
            return f"Error finding references: {str(e)}"

    async def get_class_definition(
        self,
        file_path: str,
        class_name: str,
    ) -> str:
        """
        Extract a complete class definition from a file.

        Args:
            file_path (str): Path to the file
            class_name (str): Name of the class to extract

        Returns:
            str: The complete class code with line numbers

        Notes:
            - Includes decorators, docstrings, and all methods
            - Supports Python classes
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
                f.seek(0)
                lines = f.readlines()

            if ext == ".py":
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef) and node.name == class_name:
                            # Get decorators start line
                            start_line = (
                                node.decorator_list[0].lineno
                                if node.decorator_list
                                else node.lineno
                            )
                            end_line = node.end_lineno

                            class_lines = lines[start_line - 1 : end_line]
                            result = f"📦 Class `{class_name}` from `{file_path}` (lines {start_line}-{end_line}):\n\n```python\n"
                            for i, line in enumerate(class_lines, start=start_line):
                                result += f"{i:4} | {line}"
                            result += "```"

                            # Also list methods
                            methods = []
                            for item in node.body:
                                if isinstance(
                                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                                ):
                                    async_prefix = (
                                        "async "
                                        if isinstance(item, ast.AsyncFunctionDef)
                                        else ""
                                    )
                                    methods.append(f"{async_prefix}{item.name}")

                            if methods:
                                result += f"\n\n**Methods ({len(methods)}):** {', '.join(methods)}"

                            return result

                    return f"Class `{class_name}` not found in `{file_path}`"

                except SyntaxError as e:
                    return f"Syntax error parsing file: {str(e)}"

            else:
                return f"Class extraction only supported for Python files"

        except Exception as e:
            return f"Error extracting class: {str(e)}"

    async def get_method_list(
        self,
        file_path: str,
        class_name: str = "",
    ) -> str:
        """
        List all methods/functions in a file or specific class.

        Args:
            file_path (str): Path to the file
            class_name (str): Optional class name to filter methods. If empty, lists all functions.

        Returns:
            str: List of methods with signatures

        Notes:
            - Shows method signatures including parameters and return types
            - Groups by class if no class_name specified
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            if ext != ".py":
                return f"Method listing only supported for Python files"

            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return f"Syntax error parsing file: {str(e)}"

            result = f"📋 Methods in `{file_path}`"
            if class_name:
                result += f" (class `{class_name}`)"
            result += ":\n\n"

            def format_func(node, indent=""):
                async_prefix = (
                    "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                )
                args = []
                for arg in node.args.args:
                    arg_str = arg.arg
                    if arg.annotation:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    args.append(arg_str)

                returns = ""
                if node.returns:
                    returns = f" -> {ast.unparse(node.returns)}"

                return (
                    f"{indent}{async_prefix}def {node.name}({', '.join(args)}){returns}"
                )

            if class_name:
                # Find specific class
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name == class_name:
                        methods = [
                            item
                            for item in node.body
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ]
                        for method in methods:
                            result += f"  - `{format_func(method)}`\n"
                        result += f"\n**Total:** {len(methods)} method(s)"
                        return result
                return f"Class `{class_name}` not found"

            else:
                # List all classes and their methods, plus top-level functions
                classes = {}
                top_level_funcs = []

                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, ast.ClassDef):
                        methods = [
                            item
                            for item in node.body
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ]
                        classes[node.name] = methods
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        top_level_funcs.append(node)

                if top_level_funcs:
                    result += "**Top-level functions:**\n"
                    for func in top_level_funcs:
                        result += f"  - `{format_func(func)}`\n"
                    result += "\n"

                for cls_name, methods in classes.items():
                    result += f"**class {cls_name}:** ({len(methods)} methods)\n"
                    for method in methods[:10]:  # Limit methods shown
                        result += f"  - `{format_func(method, '')}`\n"
                    if len(methods) > 10:
                        result += f"  ... and {len(methods) - 10} more\n"
                    result += "\n"

                total = len(top_level_funcs) + sum(len(m) for m in classes.values())
                result += f"**Total:** {total} function(s)/method(s) in {len(classes)} class(es)"
                return result

        except Exception as e:
            return f"Error listing methods: {str(e)}"

    async def analyze_dependencies(
        self,
        file_path: str,
    ) -> str:
        """
        Analyze dependencies of a Python file.

        Args:
            file_path (str): Path to the Python file

        Returns:
            str: Dependency analysis including imports and their types

        Notes:
            - Categorizes imports as standard library, third-party, or local
            - Shows what each import provides
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()
            if ext != ".py":
                return f"Dependency analysis only supported for Python files"

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return f"Syntax error parsing file: {str(e)}"

            # Standard library modules (common ones)
            stdlib = {
                "os",
                "sys",
                "re",
                "json",
                "datetime",
                "time",
                "math",
                "random",
                "collections",
                "itertools",
                "functools",
                "typing",
                "pathlib",
                "logging",
                "subprocess",
                "threading",
                "multiprocessing",
                "asyncio",
                "io",
                "copy",
                "uuid",
                "hashlib",
                "base64",
                "pickle",
                "csv",
                "urllib",
                "http",
                "socket",
                "ssl",
                "email",
                "html",
                "xml",
                "sqlite3",
                "unittest",
                "tempfile",
                "shutil",
                "glob",
                "fnmatch",
                "abc",
                "contextlib",
                "dataclasses",
                "enum",
                "traceback",
                "inspect",
                "ast",
                "dis",
                "struct",
                "codecs",
                "locale",
                "gettext",
                "argparse",
            }

            imports = {
                "stdlib": [],
                "third_party": [],
                "local": [],
            }

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name.split(".")[0]
                        entry = alias.name
                        if alias.asname:
                            entry += f" as {alias.asname}"

                        if module in stdlib:
                            imports["stdlib"].append((node.lineno, entry))
                        elif module.startswith(".") or module == "__future__":
                            imports["local"].append((node.lineno, entry))
                        else:
                            imports["third_party"].append((node.lineno, entry))

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    base_module = module.split(".")[0] if module else ""
                    names = [
                        a.name + (f" as {a.asname}" if a.asname else "")
                        for a in node.names
                    ]
                    dots = "." * node.level
                    entry = f"from {dots}{module} import {', '.join(names)}"

                    if node.level > 0:  # Relative import
                        imports["local"].append((node.lineno, entry))
                    elif base_module in stdlib:
                        imports["stdlib"].append((node.lineno, entry))
                    else:
                        imports["third_party"].append((node.lineno, entry))

            result = f"📊 Dependency Analysis for `{file_path}`\n\n"

            if imports["stdlib"]:
                result += f"**Standard Library ({len(imports['stdlib'])}):**\n"
                for line, imp in sorted(imports["stdlib"]):
                    result += f"  Line {line}: `{imp}`\n"
                result += "\n"

            if imports["third_party"]:
                result += f"**Third-Party ({len(imports['third_party'])}):**\n"
                for line, imp in sorted(imports["third_party"]):
                    result += f"  Line {line}: `{imp}`\n"
                result += "\n"

            if imports["local"]:
                result += f"**Local/Relative ({len(imports['local'])}):**\n"
                for line, imp in sorted(imports["local"]):
                    result += f"  Line {line}: `{imp}`\n"
                result += "\n"

            total = sum(len(v) for v in imports.values())
            result += f"**Total:** {total} import statement(s)"

            return result

        except Exception as e:
            return f"Error analyzing dependencies: {str(e)}"

    async def get_code_outline(
        self,
        file_path: str,
    ) -> str:
        """
        Get a structured outline of a code file showing classes, functions, and key elements.

        Args:
            file_path (str): Path to the code file

        Returns:
            str: Structured outline with line numbers

        Notes:
            - Shows classes, methods, functions, and decorators
            - Includes docstring summaries where available
            - Supports Python
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            if ext != ".py":
                return f"Code outline only supported for Python files"

            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return f"Syntax error parsing file: {str(e)}"

            result = f"📝 Code Outline: `{file_path}`\n\n"

            # Get module docstring
            module_doc = ast.get_docstring(tree)
            if module_doc:
                first_line = module_doc.split("\n")[0][:80]
                result += f"📄 **Module:** {first_line}...\n\n"

            # Track global variables
            globals_list = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            globals_list.append((node.lineno, target.id))

            if globals_list:
                result += "**Constants/Globals:**\n"
                for line, name in globals_list[:10]:
                    result += f"  Line {line}: `{name}`\n"
                if len(globals_list) > 10:
                    result += f"  ... and {len(globals_list) - 10} more\n"
                result += "\n"

            # Process top-level items
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    decorators = (
                        [f"@{ast.unparse(d)}" for d in node.decorator_list]
                        if node.decorator_list
                        else []
                    )
                    dec_str = " ".join(decorators) + " " if decorators else ""

                    bases = [ast.unparse(b) for b in node.bases] if node.bases else []
                    base_str = f"({', '.join(bases)})" if bases else ""

                    result += (
                        f"📦 **class {node.name}{base_str}** (line {node.lineno})\n"
                    )
                    if dec_str:
                        result += f"   Decorators: {dec_str}\n"

                    doc = ast.get_docstring(node)
                    if doc:
                        result += f"   {doc.split(chr(10))[0][:60]}...\n"

                    # List methods
                    methods = [
                        item
                        for item in node.body
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    for method in methods[:8]:
                        async_prefix = (
                            "async " if isinstance(method, ast.AsyncFunctionDef) else ""
                        )
                        result += f"   └─ {async_prefix}def {method.name}() (line {method.lineno})\n"
                    if len(methods) > 8:
                        result += f"   └─ ... and {len(methods) - 8} more methods\n"
                    result += "\n"

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    async_prefix = (
                        "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                    )
                    decorators = (
                        [f"@{ast.unparse(d)}" for d in node.decorator_list]
                        if node.decorator_list
                        else []
                    )
                    dec_str = " ".join(decorators) + " " if decorators else ""

                    result += (
                        f"🔧 **{async_prefix}def {node.name}()** (line {node.lineno})\n"
                    )
                    if dec_str:
                        result += f"   Decorators: {dec_str}\n"

                    doc = ast.get_docstring(node)
                    if doc:
                        result += f"   {doc.split(chr(10))[0][:60]}...\n"
                    result += "\n"

            return result

        except Exception as e:
            return f"Error generating outline: {str(e)}"

    async def git_fetch(
        self,
        remote: str = "origin",
        prune: bool = False,
    ) -> str:
        """
        Fetch updates from a remote repository.

        Args:
            remote (str): Remote name. Default: "origin"
            prune (bool): Remove remote-tracking branches that no longer exist. Default: False

        Returns:
            str: Fetch result or error

        Notes:
            - Does not merge, only downloads new data
            - Restricted to agent workspace
        """
        try:
            cmd = ["git", "fetch", remote]
            if prune:
                cmd.append("--prune")

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return f"Error: {result.stderr}"

            output = result.stdout or result.stderr or "Fetch completed (no new data)"
            return f"✅ Git fetch from `{remote}` completed\n\n{output}"

        except Exception as e:
            return f"Error during git fetch: {str(e)}"

    async def git_pull(
        self,
        remote: str = "origin",
        branch: str = "",
        rebase: bool = False,
    ) -> str:
        """
        Pull changes from a remote repository.

        Args:
            remote (str): Remote name. Default: "origin"
            branch (str): Branch to pull. If empty, pulls current branch.
            rebase (bool): Use rebase instead of merge. Default: False

        Returns:
            str: Pull result or error

        Notes:
            - Fetches and merges/rebases changes
            - Restricted to agent workspace
        """
        try:
            cmd = ["git", "pull"]
            if rebase:
                cmd.append("--rebase")
            cmd.append(remote)
            if branch:
                cmd.append(branch)

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                stderr = result.stderr
                if "CONFLICT" in stderr or "conflict" in result.stdout:
                    return f"⚠️ Pull resulted in conflicts:\n\n{result.stdout}\n{stderr}"
                return f"Error: {stderr}"

            return f"✅ Git pull completed\n\n{result.stdout}"

        except Exception as e:
            return f"Error during git pull: {str(e)}"

    async def git_merge(
        self,
        branch: str,
        no_ff: bool = False,
        message: str = "",
    ) -> str:
        """
        Merge a branch into the current branch.

        Args:
            branch (str): Branch name to merge
            no_ff (bool): Create merge commit even for fast-forward. Default: False
            message (str): Custom merge commit message

        Returns:
            str: Merge result or error

        Notes:
            - May result in conflicts that need resolution
            - Restricted to agent workspace
        """
        try:
            cmd = ["git", "merge", branch]
            if no_ff:
                cmd.append("--no-ff")
            if message:
                cmd.extend(["-m", message])

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                stderr = result.stderr
                if "CONFLICT" in stderr or "CONFLICT" in result.stdout:
                    return f"⚠️ Merge conflicts detected:\n\n{result.stdout}\n{stderr}\n\nResolve conflicts and commit."
                return f"Error: {stderr}"

            return f"✅ Merged `{branch}` into current branch\n\n{result.stdout}"

        except Exception as e:
            return f"Error during git merge: {str(e)}"

    async def git_revert(
        self,
        commit: str,
        no_commit: bool = False,
    ) -> str:
        """
        Revert a specific commit.

        Args:
            commit (str): Commit hash to revert
            no_commit (bool): Stage changes but don't commit. Default: False

        Returns:
            str: Revert result or error

        Notes:
            - Creates a new commit that undoes the changes
            - Restricted to agent workspace
        """
        try:
            cmd = ["git", "revert", commit]
            if no_commit:
                cmd.append("--no-commit")

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return f"Error: {result.stderr}"

            return f"✅ Reverted commit `{commit}`\n\n{result.stdout}"

        except Exception as e:
            return f"Error during git revert: {str(e)}"

    async def git_cherry_pick(
        self,
        commit: str,
        no_commit: bool = False,
    ) -> str:
        """
        Cherry-pick a specific commit onto the current branch.

        Args:
            commit (str): Commit hash to cherry-pick
            no_commit (bool): Stage changes but don't commit. Default: False

        Returns:
            str: Cherry-pick result or error

        Notes:
            - Applies changes from a specific commit
            - May result in conflicts
            - Restricted to agent workspace
        """
        try:
            cmd = ["git", "cherry-pick", commit]
            if no_commit:
                cmd.append("--no-commit")

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                stderr = result.stderr
                if "CONFLICT" in stderr:
                    return f"⚠️ Cherry-pick conflicts:\n\n{result.stdout}\n{stderr}"
                return f"Error: {stderr}"

            return f"✅ Cherry-picked commit `{commit}`\n\n{result.stdout}"

        except Exception as e:
            return f"Error during cherry-pick: {str(e)}"

    async def find_test_file(
        self,
        source_file: str,
    ) -> str:
        """
        Find the test file corresponding to a source file.

        Args:
            source_file (str): Path to the source file

        Returns:
            str: Path to test file(s) if found, or suggestions

        Notes:
            - Checks common test file naming conventions
            - Looks in tests/, test/, and same directory
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(source_file)

            if not os.path.exists(full_path):
                return f"Error: Source file `{source_file}` not found"

            base_name = os.path.basename(source_file)
            name_without_ext = os.path.splitext(base_name)[0]
            ext = os.path.splitext(base_name)[1]
            source_dir = os.path.dirname(full_path)

            # Common test file patterns
            test_patterns = [
                f"test_{name_without_ext}{ext}",
                f"{name_without_ext}_test{ext}",
                f"test_{name_without_ext.replace('_', '')}{ext}",
                f"{name_without_ext}Test{ext}",
            ]

            # Directories to search
            search_dirs = [
                source_dir,
                os.path.join(self.WORKING_DIRECTORY, "tests"),
                os.path.join(self.WORKING_DIRECTORY, "test"),
                os.path.join(source_dir, "tests"),
                os.path.join(source_dir, "test"),
            ]

            found_tests = []

            for search_dir in search_dirs:
                if not os.path.exists(search_dir):
                    continue

                for pattern in test_patterns:
                    test_path = os.path.join(search_dir, pattern)
                    if os.path.exists(test_path):
                        rel_path = os.path.relpath(test_path, self.WORKING_DIRECTORY)
                        found_tests.append(rel_path)

                # Also search recursively
                for root, dirs, files in os.walk(search_dir):
                    for file in files:
                        if file in test_patterns:
                            rel_path = os.path.relpath(
                                os.path.join(root, file), self.WORKING_DIRECTORY
                            )
                            if rel_path not in found_tests:
                                found_tests.append(rel_path)

            if found_tests:
                result = (
                    f"🧪 Found {len(found_tests)} test file(s) for `{source_file}`:\n\n"
                )
                for test_file in found_tests:
                    result += f"  - `{test_file}`\n"
                return result

            # Suggest where to create test
            suggested = os.path.join("tests", f"test_{name_without_ext}{ext}")
            return f"No test file found for `{source_file}`\n\nSuggested location: `{suggested}`"

        except Exception as e:
            return f"Error finding test file: {str(e)}"

    async def lint_file(
        self,
        file_path: str,
        linter: str = "auto",
    ) -> str:
        """
        Run a linter on a file and report issues.

        Args:
            file_path (str): Path to the file to lint
            linter (str): Linter to use: "auto", "flake8", "pylint", "ruff". Default: "auto"

        Returns:
            str: Linting results with issues found

        Notes:
            - Auto-detects linter based on file type
            - For Python: tries ruff, flake8, then pylint
            - Shows line numbers and issue descriptions
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            if ext != ".py":
                return f"Linting currently only supported for Python files"

            # Try different linters
            linters_to_try = []
            if linter == "auto":
                linters_to_try = ["ruff", "flake8", "pylint"]
            else:
                linters_to_try = [linter]

            for lint_tool in linters_to_try:
                try:
                    if lint_tool == "ruff":
                        cmd = ["ruff", "check", full_path, "--output-format", "text"]
                    elif lint_tool == "flake8":
                        cmd = ["flake8", full_path]
                    elif lint_tool == "pylint":
                        cmd = [
                            "pylint",
                            full_path,
                            "--output-format",
                            "text",
                            "--score=no",
                        ]
                    else:
                        continue

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                    )

                    # Linters often return non-zero when issues found
                    output = result.stdout or result.stderr

                    if output.strip():
                        issues = output.strip().split("\n")
                        return f"🔍 Lint results for `{file_path}` (using {lint_tool}):\n\n```\n{output}\n```\n\n**Issues found:** {len(issues)}"
                    else:
                        return f"✅ No lint issues found in `{file_path}` (using {lint_tool})"

                except FileNotFoundError:
                    continue

            return f"Error: No linter available. Install ruff, flake8, or pylint."

        except Exception as e:
            return f"Error linting file: {str(e)}"

    async def sort_lines(
        self,
        file_path: str,
        start_line: int = 0,
        end_line: int = 0,
        reverse: bool = False,
        ignore_case: bool = False,
    ) -> str:
        """
        Sort lines in a file or a specific range.

        Args:
            file_path (str): Path to the file
            start_line (int): First line to sort (1-indexed). 0 = start of file.
            end_line (int): Last line to sort (1-indexed). 0 = end of file.
            reverse (bool): Sort in descending order. Default: False
            ignore_case (bool): Case-insensitive sorting. Default: False

        Returns:
            str: Success message or error

        Notes:
            - Sorts in-place
            - Use start_line/end_line to sort a specific range
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Determine range
            start_idx = max(0, start_line - 1) if start_line > 0 else 0
            end_idx = min(len(lines), end_line) if end_line > 0 else len(lines)

            # Extract, sort, and reinsert
            to_sort = lines[start_idx:end_idx]
            key_func = (lambda x: x.lower()) if ignore_case else None
            sorted_lines = sorted(to_sort, key=key_func, reverse=reverse)

            lines[start_idx:end_idx] = sorted_lines

            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            range_desc = f"lines {start_line or 1}-{end_line or len(lines)}"
            return (
                f"✅ Sorted {len(sorted_lines)} lines in `{file_path}` ({range_desc})"
            )

        except Exception as e:
            return f"Error sorting lines: {str(e)}"

    async def remove_duplicate_lines(
        self,
        file_path: str,
        preserve_order: bool = True,
    ) -> str:
        """
        Remove duplicate lines from a file.

        Args:
            file_path (str): Path to the file
            preserve_order (bool): Keep first occurrence of each line. Default: True

        Returns:
            str: Success message with count of removed duplicates

        Notes:
            - By default preserves the order of first occurrences
            - Considers trailing whitespace as part of the line
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            original_count = len(lines)

            if preserve_order:
                seen = set()
                unique_lines = []
                for line in lines:
                    if line not in seen:
                        seen.add(line)
                        unique_lines.append(line)
            else:
                unique_lines = list(set(lines))

            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(unique_lines)

            removed = original_count - len(unique_lines)
            return f"✅ Removed {removed} duplicate line(s) from `{file_path}`\n\n- Original: {original_count} lines\n- After: {len(unique_lines)} lines"

        except Exception as e:
            return f"Error removing duplicates: {str(e)}"

    async def extract_comments(
        self,
        file_path: str,
        include_docstrings: bool = True,
    ) -> str:
        """
        Extract all comments from a code file.

        Args:
            file_path (str): Path to the code file
            include_docstrings (bool): Include docstrings as comments. Default: True

        Returns:
            str: List of comments with line numbers

        Notes:
            - Supports Python and JavaScript/TypeScript
            - Groups by type (inline, block, docstring)
            - Restricted to agent workspace
        """
        try:
            full_path = self.safe_join(file_path)

            if not os.path.exists(full_path):
                return f"Error: File `{file_path}` not found"

            ext = os.path.splitext(file_path)[1].lower()

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
                f.seek(0)
                lines = f.readlines()

            comments = {
                "inline": [],
                "block": [],
                "docstring": [],
            }

            if ext == ".py":
                # Extract docstrings using AST
                if include_docstrings:
                    try:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(
                                node,
                                (
                                    ast.Module,
                                    ast.ClassDef,
                                    ast.FunctionDef,
                                    ast.AsyncFunctionDef,
                                ),
                            ):
                                doc = ast.get_docstring(node)
                                if doc:
                                    if isinstance(node, ast.Module):
                                        loc = "module"
                                    else:
                                        loc = f"{node.name}"
                                    comments["docstring"].append(
                                        (
                                            (
                                                node.lineno
                                                if hasattr(node, "lineno")
                                                else 1
                                            ),
                                            loc,
                                            doc[:100],
                                        )
                                    )
                    except SyntaxError:
                        pass

                # Extract inline comments
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        comments["inline"].append((i, stripped))
                    elif "#" in line and not line.strip().startswith("#"):
                        # Inline comment at end of line
                        comment_part = line.split("#", 1)[1].strip()
                        comments["inline"].append((i, f"# {comment_part}"))

            elif ext in [".js", ".ts", ".jsx", ".tsx"]:
                # Single-line comments
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("//"):
                        comments["inline"].append((i, stripped))

                # Multi-line comments
                in_block = False
                block_start = 0
                block_content = []
                for i, line in enumerate(lines, 1):
                    if "/*" in line and not in_block:
                        in_block = True
                        block_start = i
                        block_content = [line.split("/*")[1]]
                    elif in_block:
                        if "*/" in line:
                            block_content.append(line.split("*/")[0])
                            comments["block"].append(
                                (block_start, " ".join(block_content).strip()[:100])
                            )
                            in_block = False
                            block_content = []
                        else:
                            block_content.append(line.strip().lstrip("*").strip())

            # Format output
            result = f"💬 Comments in `{file_path}`:\n\n"

            if comments["docstring"] and include_docstrings:
                result += f"**Docstrings ({len(comments['docstring'])}):**\n"
                for line, loc, doc in comments["docstring"][:10]:
                    result += f"  Line {line} ({loc}): `{doc[:60]}...`\n"
                result += "\n"

            if comments["inline"]:
                result += f"**Inline Comments ({len(comments['inline'])}):**\n"
                for line, comment in comments["inline"][:15]:
                    result += f"  Line {line}: `{comment[:60]}`\n"
                if len(comments["inline"]) > 15:
                    result += f"  ... and {len(comments['inline']) - 15} more\n"
                result += "\n"

            if comments["block"]:
                result += f"**Block Comments ({len(comments['block'])}):**\n"
                for line, comment in comments["block"][:5]:
                    result += f"  Line {line}: `{comment[:60]}...`\n"
                result += "\n"

            total = sum(len(v) for v in comments.values())
            if total == 0:
                return f"No comments found in `{file_path}`"

            result += f"**Total:** {total} comment(s)"
            return result

        except Exception as e:
            return f"Error extracting comments: {str(e)}"

    async def generate_changelog(
        self,
        count: int = 20,
        since: str = "",
        format_type: str = "markdown",
    ) -> str:
        """
        Generate a changelog from git commit history.

        Args:
            count (int): Number of commits to include. Default: 20
            since (str): Only commits after this date (YYYY-MM-DD). Optional.
            format_type (str): Output format: "markdown", "plain". Default: "markdown"

        Returns:
            str: Generated changelog

        Notes:
            - Groups commits by type if using conventional commits
            - Includes commit hash, author, and date
            - Restricted to agent workspace
        """
        try:
            cmd = ["git", "log", f"-n{count}", "--format=%H|%an|%ad|%s", "--date=short"]
            if since:
                cmd.append(f"--since={since}")

            result = subprocess.run(
                cmd,
                cwd=self.WORKING_DIRECTORY,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return f"Error: {result.stderr}"

            if not result.stdout.strip():
                return "No commits found"

            commits = []
            for line in result.stdout.strip().split("\n"):
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append(
                        {
                            "hash": parts[0][:7],
                            "author": parts[1],
                            "date": parts[2],
                            "message": parts[3],
                        }
                    )

            # Try to categorize by conventional commits
            categories = {
                "feat": [],
                "fix": [],
                "docs": [],
                "style": [],
                "refactor": [],
                "test": [],
                "chore": [],
                "other": [],
            }

            for commit in commits:
                msg = commit["message"].lower()
                categorized = False
                for cat in categories:
                    if msg.startswith(f"{cat}:") or msg.startswith(f"{cat}("):
                        categories[cat].append(commit)
                        categorized = True
                        break
                if not categorized:
                    categories["other"].append(commit)

            # Format output
            if format_type == "markdown":
                result_text = "# Changelog\n\n"

                category_names = {
                    "feat": "✨ Features",
                    "fix": "🐛 Bug Fixes",
                    "docs": "📚 Documentation",
                    "style": "💅 Styling",
                    "refactor": "♻️ Refactoring",
                    "test": "🧪 Tests",
                    "chore": "🔧 Chores",
                    "other": "📝 Other Changes",
                }

                for cat, name in category_names.items():
                    if categories[cat]:
                        result_text += f"## {name}\n\n"
                        for commit in categories[cat]:
                            result_text += f"- {commit['message']} (`{commit['hash']}`) - {commit['author']}, {commit['date']}\n"
                        result_text += "\n"

            else:
                result_text = "CHANGELOG\n" + "=" * 50 + "\n\n"
                for commit in commits:
                    result_text += (
                        f"[{commit['hash']}] {commit['date']} - {commit['author']}\n"
                    )
                    result_text += f"  {commit['message']}\n\n"

            return result_text

        except Exception as e:
            return f"Error generating changelog: {str(e)}"

    async def head_file(
        self,
        file_path: str,
        lines: int = 10,
    ) -> str:
        """
        Get the first N lines of a file efficiently without reading the entire file.

        Args:
            file_path: Path to the file (relative to workspace or absolute)
            lines: Number of lines to return from the beginning (default: 10)

        Returns:
            The first N lines of the file
        """
        try:
            safe_path = self.safe_join(file_path)
            if not safe_path:
                return f"Error: Access denied - path '{file_path}' is outside the workspace"

            if not os.path.exists(safe_path):
                return f"Error: File not found: {file_path}"

            if not os.path.isfile(safe_path):
                return f"Error: Path is not a file: {file_path}"

            lines = int(lines)
            result_lines = []
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= lines:
                        break
                    result_lines.append(line.rstrip("\n"))

            return f"First {len(result_lines)} lines of {file_path}:\n" + "\n".join(
                f"{i+1}: {line}" for i, line in enumerate(result_lines)
            )

        except Exception as e:
            return f"Error reading file head: {str(e)}"

    async def tail_file(
        self,
        file_path: str,
        lines: int = 10,
    ) -> str:
        """
        Get the last N lines of a file efficiently.

        Args:
            file_path: Path to the file (relative to workspace or absolute)
            lines: Number of lines to return from the end (default: 10)

        Returns:
            The last N lines of the file
        """
        try:
            safe_path = self.safe_join(file_path)
            if not safe_path:
                return f"Error: Access denied - path '{file_path}' is outside the workspace"

            if not os.path.exists(safe_path):
                return f"Error: File not found: {file_path}"

            if not os.path.isfile(safe_path):
                return f"Error: Path is not a file: {file_path}"

            lines = int(lines)
            # Use deque for efficient tail operation
            from collections import deque

            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                result_lines = deque(f, maxlen=lines)

            result_lines = [line.rstrip("\n") for line in result_lines]

            # Get total line count for accurate line numbers
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                total_lines = sum(1 for _ in f)

            start_line = total_lines - len(result_lines) + 1

            return (
                f"Last {len(result_lines)} lines of {file_path} (lines {start_line}-{total_lines}):\n"
                + "\n".join(
                    f"{start_line + i}: {line}" for i, line in enumerate(result_lines)
                )
            )

        except Exception as e:
            return f"Error reading file tail: {str(e)}"

    async def check_path_exists(
        self,
        path: str,
        check_type: str = "any",
    ) -> str:
        """
        Check if a path exists without reading its contents.

        Args:
            path: Path to check (relative to workspace or absolute)
            check_type: Type to check for - 'any', 'file', or 'directory'

        Returns:
            JSON with existence status and path details
        """
        try:
            safe_path = self.safe_join(path)
            if not safe_path:
                return json.dumps(
                    {
                        "exists": False,
                        "error": f"Access denied - path '{path}' is outside the workspace",
                        "path": path,
                    }
                )

            exists = os.path.exists(safe_path)
            is_file = os.path.isfile(safe_path) if exists else False
            is_dir = os.path.isdir(safe_path) if exists else False
            is_symlink = os.path.islink(safe_path) if exists else False

            # Check type-specific existence
            type_match = True
            if check_type == "file":
                type_match = is_file
            elif check_type == "directory":
                type_match = is_dir

            result = {
                "exists": exists and type_match,
                "path": path,
                "absolute_path": safe_path,
                "is_file": is_file,
                "is_directory": is_dir,
                "is_symlink": is_symlink,
                "check_type": check_type,
            }

            if exists:
                stat_info = os.stat(safe_path)
                result["size_bytes"] = stat_info.st_size
                result["readable"] = os.access(safe_path, os.R_OK)
                result["writable"] = os.access(safe_path, os.W_OK)

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({"exists": False, "error": str(e), "path": path})

    async def get_file_hash(
        self,
        file_path: str,
        algorithm: str = "sha256",
    ) -> str:
        """
        Calculate the hash of a file for integrity verification.

        Args:
            file_path: Path to the file (relative to workspace or absolute)
            algorithm: Hash algorithm - 'md5', 'sha1', 'sha256', 'sha512'

        Returns:
            The file hash and metadata
        """
        import hashlib

        try:
            safe_path = self.safe_join(file_path)
            if not safe_path:
                return f"Error: Access denied - path '{file_path}' is outside the workspace"

            if not os.path.exists(safe_path):
                return f"Error: File not found: {file_path}"

            if not os.path.isfile(safe_path):
                return f"Error: Path is not a file: {file_path}"

            algorithm = algorithm.lower()
            valid_algorithms = ["md5", "sha1", "sha256", "sha512"]
            if algorithm not in valid_algorithms:
                return f"Error: Invalid algorithm. Choose from: {', '.join(valid_algorithms)}"

            # Create hash object
            hash_obj = hashlib.new(algorithm)

            # Read file in chunks for memory efficiency
            file_size = os.path.getsize(safe_path)
            with open(safe_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_obj.update(chunk)

            file_hash = hash_obj.hexdigest()

            result = {
                "file": file_path,
                "algorithm": algorithm.upper(),
                "hash": file_hash,
                "size_bytes": file_size,
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error calculating file hash: {str(e)}"

    async def truncate_file(
        self,
        file_path: str,
        confirm: bool = False,
    ) -> str:
        """
        Truncate a file to zero length (empty it) while preserving the file.

        Args:
            file_path: Path to the file (relative to workspace or absolute)
            confirm: Must be True to confirm the truncation

        Returns:
            Success or error message
        """
        try:
            safe_path = self.safe_join(file_path)
            if not safe_path:
                return f"Error: Access denied - path '{file_path}' is outside the workspace"

            if not os.path.exists(safe_path):
                return f"Error: File not found: {file_path}"

            if not os.path.isfile(safe_path):
                return f"Error: Path is not a file: {file_path}"

            # Require explicit confirmation
            if not confirm:
                file_size = os.path.getsize(safe_path)
                return f"Warning: This will permanently empty '{file_path}' ({file_size} bytes). Set confirm=True to proceed."

            # Get original size for reporting
            original_size = os.path.getsize(safe_path)

            # Truncate the file
            with open(safe_path, "w") as f:
                pass  # Opening in write mode truncates

            return f"Successfully truncated '{file_path}'. Original size: {original_size} bytes, New size: 0 bytes"

        except Exception as e:
            return f"Error truncating file: {str(e)}"

    async def find_large_files(
        self,
        directory: str = ".",
        min_size_mb: float = 10.0,
        max_results: int = 50,
    ) -> str:
        """
        Find files larger than a specified size in a directory.

        Args:
            directory: Directory to search (relative to workspace or absolute)
            min_size_mb: Minimum file size in megabytes to include (default: 10 MB)
            max_results: Maximum number of results to return (default: 50)

        Returns:
            List of large files with sizes, sorted by size descending
        """
        try:
            safe_path = self.safe_join(directory)
            if not safe_path:
                return f"Error: Access denied - path '{directory}' is outside the workspace"

            if not os.path.exists(safe_path):
                return f"Error: Directory not found: {directory}"

            if not os.path.isdir(safe_path):
                return f"Error: Path is not a directory: {directory}"

            min_size_bytes = float(min_size_mb) * 1024 * 1024
            max_results = int(max_results)
            large_files = []

            for root, dirs, files in os.walk(safe_path):
                # Skip hidden and common non-essential directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d
                    not in [
                        "node_modules",
                        "__pycache__",
                        ".git",
                        "venv",
                        ".venv",
                        "dist",
                        "build",
                    ]
                ]

                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        size = os.path.getsize(file_path)
                        if size >= min_size_bytes:
                            rel_path = os.path.relpath(file_path, safe_path)
                            large_files.append(
                                {
                                    "path": rel_path,
                                    "size_bytes": size,
                                    "size_mb": round(size / (1024 * 1024), 2),
                                }
                            )
                    except (OSError, PermissionError):
                        continue

            # Sort by size descending
            large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
            large_files = large_files[:max_results]

            # Calculate totals
            total_size = sum(f["size_bytes"] for f in large_files)

            result = {
                "directory": directory,
                "min_size_mb": min_size_mb,
                "files_found": len(large_files),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "files": large_files,
            }

            if not large_files:
                return f"No files found larger than {min_size_mb} MB in '{directory}'"

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error finding large files: {str(e)}"

    async def send_feedback_to_dev_team(
        self,
        feedback: str,
        issue: str,
        suggestion_to_resolve_issue: str,
    ) -> str:
        """
        Send feedback to the AGiXT development team. This can be used for feature suggestions, reporting problems, and making suggestions for improving the way the software and website function including UX.

        Args:
            feedback (str): General feedback about the system, feature, or experience
            issue (str): Description of any issue or problem encountered
            suggestion_to_resolve_issue (str): Suggested solution or improvement to resolve the issue

        Returns:
            str: Confirmation message indicating the feedback was sent

        Notes:
        - This sends feedback directly to the development team's Discord channel
        - Include as much detail as possible to help the team understand and address the feedback
        - User information (email, agent ID, company ID) is automatically included for context
        - If a user is complaining about how something works on the website, this command should be used to assist the dev team on improving the website.
        """
        from middleware import send_discord_notification
        from MagicalAuth import get_user_company_id

        try:
            # Get user email from self.user (can be string or dict)
            user_email = None
            if isinstance(self.user, dict):
                user_email = self.user.get("email")
            elif isinstance(self.user, str):
                user_email = self.user

            # Get company ID
            company_id = None
            if self.user:
                company_id = get_user_company_id(self.user)

            # Build the fields for the Discord embed
            fields = [
                {
                    "name": "📝 Feedback",
                    "value": feedback[:1000] if feedback else "No feedback provided",
                    "inline": False,
                },
                {
                    "name": "⚠️ Issue",
                    "value": issue[:1000] if issue else "No issue described",
                    "inline": False,
                },
                {
                    "name": "💡 Suggested Resolution",
                    "value": (
                        suggestion_to_resolve_issue[:1000]
                        if suggestion_to_resolve_issue
                        else "No suggestion provided"
                    ),
                    "inline": False,
                },
                {
                    "name": "🤖 Agent ID",
                    "value": f"`{self.agent_id}`" if self.agent_id else "Unknown",
                    "inline": True,
                },
                {
                    "name": "🏢 Company ID",
                    "value": f"`{company_id}`" if company_id else "Unknown",
                    "inline": True,
                },
            ]

            await send_discord_notification(
                title="📣 User Feedback Received",
                description="A user has submitted feedback through the agent.",
                color=5814783,  # Purple color for feedback
                fields=fields,
                user_email=user_email,
                user_id=str(self.user_id) if self.user_id else None,
            )

            return "Thank you! Your feedback has been successfully sent to the development team. They will review your feedback, issue, and suggestion to help improve the system."

        except Exception as e:
            logging.error(f"Failed to send feedback to development team: {str(e)}")
            return f"We apologize, but there was an error sending your feedback: {str(e)}. Please try again later or contact support directly."

    async def create_or_update_codebase_map(
        self,
        path: str = "",
        update_file: str = "",
    ) -> str:
        """
        Create or update a comprehensive map of a codebase within the workspace.

        This command scans the specified directory (or entire workspace) and generates
        a detailed architecture map including file purposes, dependencies, data flows,
        and navigation guides. The map is saved to docs/CODEBASE_MAP.md.

        Args:
            path (str): Directory path relative to workspace to map. Use "" for entire workspace,
                       or a subdirectory like "src/" or "backend/". Must be within workspace.
            update_file (str): If specified, only update the map based on changes to this specific
                              file rather than rescanning everything. Useful for incremental updates.

        Returns:
            str: Status message indicating success with location of generated map, or error message.

        Notes:
            - Respects .gitignore patterns and skips binary/generated files automatically
            - For large codebases, content is chunked and analyzed in batches
            - Creates docs/CODEBASE_MAP.md with architecture diagrams, module guides, and navigation
            - If map already exists, it will be updated with new analysis
            - Token counts are included to help understand codebase complexity
        """
        from Globals import get_tokens
        import fnmatch
        import datetime

        # Default patterns to always ignore (common non-code files and directories)
        DEFAULT_IGNORE_DIRS = {
            ".git",
            ".svn",
            ".hg",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "venv",
            ".venv",
            "env",
            ".env",
            "dist",
            "build",
            ".next",
            ".nuxt",
            ".output",
            "coverage",
            ".coverage",
            ".nyc_output",
            "target",
            "vendor",
            ".bundle",
            ".cargo",
            ".tox",
            "eggs",
            ".eggs",
            "*.egg-info",
            "htmlcov",
            ".hypothesis",
        }

        DEFAULT_IGNORE_FILES = {
            ".DS_Store",
            "Thumbs.db",
            "*.pyc",
            "*.pyo",
            "*.so",
            "*.dylib",
            "*.dll",
            "*.exe",
            "*.o",
            "*.a",
            "*.lib",
            "*.class",
            "*.jar",
            "*.war",
            "*.egg",
            "*.whl",
            "*.lock",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "bun.lockb",
            "Cargo.lock",
            "poetry.lock",
            "Gemfile.lock",
            "composer.lock",
            "*.png",
            "*.jpg",
            "*.jpeg",
            "*.gif",
            "*.ico",
            "*.svg",
            "*.webp",
            "*.mp3",
            "*.mp4",
            "*.wav",
            "*.avi",
            "*.mov",
            "*.pdf",
            "*.zip",
            "*.tar",
            "*.gz",
            "*.rar",
            "*.7z",
            "*.woff",
            "*.woff2",
            "*.ttf",
            "*.eot",
            "*.otf",
            "*.min.js",
            "*.min.css",
            "*.map",
            "*.chunk.js",
            "*.bundle.js",
        }

        TEXT_EXTENSIONS = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".vue",
            ".svelte",
            ".html",
            ".htm",
            ".css",
            ".scss",
            ".sass",
            ".less",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".xml",
            ".md",
            ".mdx",
            ".txt",
            ".rst",
            ".sh",
            ".bash",
            ".zsh",
            ".fish",
            ".ps1",
            ".bat",
            ".cmd",
            ".sql",
            ".graphql",
            ".gql",
            ".proto",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".java",
            ".kt",
            ".kts",
            ".scala",
            ".clj",
            ".cljs",
            ".edn",
            ".ex",
            ".exs",
            ".erl",
            ".hrl",
            ".hs",
            ".lhs",
            ".ml",
            ".mli",
            ".fs",
            ".fsx",
            ".fsi",
            ".cs",
            ".vb",
            ".swift",
            ".m",
            ".mm",
            ".h",
            ".hpp",
            ".c",
            ".cpp",
            ".cc",
            ".cxx",
            ".r",
            ".R",
            ".jl",
            ".lua",
            ".vim",
            ".el",
            ".lisp",
            ".scm",
            ".rkt",
            ".zig",
            ".nim",
            ".d",
            ".dart",
            ".v",
            ".sv",
            ".vhd",
            ".vhdl",
            ".tf",
            ".hcl",
            ".dockerfile",
            ".containerfile",
            ".makefile",
            ".cmake",
            ".gradle",
            ".groovy",
            ".rake",
            ".gemspec",
            ".podspec",
            ".cabal",
            ".nix",
            ".dhall",
            ".jsonc",
            ".json5",
            ".cson",
            ".ini",
            ".cfg",
            ".conf",
            ".config",
            ".gitignore",
            ".gitattributes",
            ".editorconfig",
            ".prettierrc",
            ".eslintrc",
            ".stylelintrc",
            ".babelrc",
            ".nvmrc",
            ".ruby-version",
            ".python-version",
            ".node-version",
            ".tool-versions",
        }

        TEXT_FILENAMES = {
            "readme",
            "license",
            "licence",
            "changelog",
            "authors",
            "contributors",
            "copying",
            "dockerfile",
            "containerfile",
            "makefile",
            "rakefile",
            "gemfile",
            "procfile",
            "brewfile",
            "vagrantfile",
            "justfile",
            "taskfile",
        }

        CHUNK_TOKEN_LIMIT = 20000  # Chunk content over 20k tokens

        def parse_gitignore(root_path: str) -> list:
            """Parse .gitignore file and return patterns."""
            gitignore_path = os.path.join(root_path, ".gitignore")
            patterns = []
            if os.path.exists(gitignore_path):
                try:
                    with open(
                        gitignore_path, "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                patterns.append(line)
                except Exception:
                    pass
            return patterns

        def matches_pattern(name: str, rel_path: str, pattern: str) -> bool:
            """Check if a path matches a gitignore-style pattern."""
            if pattern.startswith("!"):
                return False
            if pattern.endswith("/"):
                pattern = pattern[:-1]
            if "/" in pattern:
                if pattern.startswith("/"):
                    pattern = pattern[1:]
                return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(
                    rel_path, pattern + "/**"
                )
            return fnmatch.fnmatch(name, pattern)

        def should_ignore(
            name: str, rel_path: str, is_dir: bool, gitignore_patterns: list
        ) -> bool:
            """Check if a path should be ignored."""
            # Check default ignores
            if is_dir:
                if name in DEFAULT_IGNORE_DIRS:
                    return True
            else:
                for pattern in DEFAULT_IGNORE_FILES:
                    if "*" in pattern:
                        if fnmatch.fnmatch(name, pattern):
                            return True
                    elif name == pattern:
                        return True
            # Check gitignore patterns
            for pattern in gitignore_patterns:
                if matches_pattern(name, rel_path, pattern):
                    return True
            return False

        def is_text_file(filepath: str) -> bool:
            """Check if a file is likely a text file."""
            name = os.path.basename(filepath).lower()
            suffix = os.path.splitext(filepath)[1].lower()

            if suffix in TEXT_EXTENSIONS:
                return True
            if name in TEXT_FILENAMES:
                return True

            # Try to detect binary by reading first bytes
            try:
                with open(filepath, "rb") as f:
                    chunk = f.read(8192)
                    if b"\x00" in chunk:
                        return False
                    try:
                        chunk.decode("utf-8")
                        return True
                    except UnicodeDecodeError:
                        return False
            except Exception:
                return False

        def scan_directory(root_path: str, gitignore_patterns: list) -> dict:
            """Scan a directory and return file information with token counts."""
            files = []
            directories = []
            skipped = []
            total_tokens = 0

            for dirpath, dirnames, filenames in os.walk(root_path):
                rel_dir = os.path.relpath(dirpath, root_path)
                if rel_dir == ".":
                    rel_dir = ""

                # Filter directories in-place to prevent walking into ignored dirs
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not should_ignore(
                        d,
                        os.path.join(rel_dir, d) if rel_dir else d,
                        True,
                        gitignore_patterns,
                    )
                ]

                if rel_dir:
                    directories.append(rel_dir)

                for filename in sorted(filenames):
                    rel_path = os.path.join(rel_dir, filename) if rel_dir else filename
                    full_path = os.path.join(dirpath, filename)

                    if should_ignore(filename, rel_path, False, gitignore_patterns):
                        skipped.append({"path": rel_path, "reason": "ignored_pattern"})
                        continue

                    try:
                        size_bytes = os.path.getsize(full_path)
                    except OSError:
                        skipped.append({"path": rel_path, "reason": "cannot_stat"})
                        continue

                    # Skip very large files (>1MB)
                    if size_bytes > 1_000_000:
                        skipped.append(
                            {
                                "path": rel_path,
                                "reason": "too_large",
                                "size_bytes": size_bytes,
                            }
                        )
                        continue

                    if not is_text_file(full_path):
                        skipped.append({"path": rel_path, "reason": "binary"})
                        continue

                    try:
                        with open(
                            full_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            content = f.read()
                        tokens = get_tokens(content)

                        files.append(
                            {
                                "path": rel_path,
                                "tokens": tokens,
                                "size_bytes": size_bytes,
                                "content": content,
                            }
                        )
                        total_tokens += tokens

                    except Exception as e:
                        skipped.append(
                            {"path": rel_path, "reason": f"read_error: {str(e)}"}
                        )

            return {
                "root": root_path,
                "files": files,
                "directories": sorted(directories),
                "total_tokens": total_tokens,
                "total_files": len(files),
                "skipped": skipped,
            }

        try:
            # Determine the target directory
            if path:
                target_path = self.safe_join(path.strip("/"))
            else:
                target_path = self.WORKING_DIRECTORY

            if not os.path.exists(target_path):
                return f"Error: Path `{path}` does not exist in the workspace."

            if not os.path.isdir(target_path):
                return f"Error: `{path}` is not a directory."

            # Parse .gitignore from workspace root
            gitignore_patterns = parse_gitignore(self.WORKING_DIRECTORY)

            # If updating based on a single file
            if update_file:
                update_file_path = self.safe_join(update_file)
                if not os.path.exists(update_file_path):
                    return f"Error: Update file `{update_file}` does not exist."

                # Read the existing map
                map_path = self.safe_join("docs/CODEBASE_MAP.md")
                existing_map = ""
                if os.path.exists(map_path):
                    with open(map_path, "r", encoding="utf-8") as f:
                        existing_map = f.read()

                # Read the updated file
                try:
                    with open(
                        update_file_path, "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        file_content = f.read()
                    file_tokens = get_tokens(file_content)
                except Exception as e:
                    return f"Error reading file {update_file}: {str(e)}"

                # Prompt the agent to update the map
                update_prompt = f"""You are updating an existing codebase map based on changes to a single file.

## Existing Codebase Map
{existing_map if existing_map else "(No existing map exists yet - you will create the initial entry for this file)"}

## Updated/New File: {update_file} ({file_tokens} tokens)
```
{file_content[:50000]}
```

## Your Task
Analyze this file and update the codebase map accordingly. You must:

1. **Analyze the file** for:
   - Purpose: What does this file do?
   - Exports: What functions, classes, types does it export?
   - Imports: What does it depend on?
   - Patterns: What design patterns or conventions does it use?
   - Gotchas: Any non-obvious behavior or warnings?

2. **Update the map** by:
   - Adding/updating the entry for this file in the Module Guide section
   - Updating the Directory Structure if this is a new file
   - Updating Data Flow diagrams if this file changes data flow
   - Updating Navigation Guide if this file is relevant to common tasks
   - Updating Conventions if this file introduces new patterns
   - Adding any new Gotchas discovered

3. **Preserve everything else**:
   - Keep all existing sections intact
   - Only modify parts directly related to this file
   - Update the `last_mapped` timestamp in frontmatter
   - Maintain consistent formatting with the rest of the document

## Output
Provide the COMPLETE updated codebase map in Markdown format.
Do not summarize or abbreviate - output the full document with your updates integrated."""

                update_response = self.ApiClient.prompt_agent(
                    agent_id=self.agent_id,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": update_prompt,
                        "disable_commands": True,
                        "log_user_input": False,
                        "log_output": False,
                        "conversation_name": self.conversation_id,
                    },
                )

                # Save the updated map
                os.makedirs(os.path.dirname(map_path), exist_ok=True)
                with open(map_path, "w", encoding="utf-8") as f:
                    f.write(update_response)

                return f"Codebase map updated based on changes to `{update_file}`. Map saved to: {self.output_url}docs/CODEBASE_MAP.md"

            # Full scan mode
            logging.info(f"[create_or_update_codebase_map] Scanning: {target_path}")
            scan_result = scan_directory(target_path, gitignore_patterns)

            if scan_result["total_files"] == 0:
                return f"No text files found to map in `{path or 'workspace'}`."

            logging.info(
                f"[create_or_update_codebase_map] Found {scan_result['total_files']} files, "
                f"{scan_result['total_tokens']:,} total tokens"
            )

            # Group files by directory for organization
            files_by_dir = {}
            for file_info in scan_result["files"]:
                dir_name = os.path.dirname(file_info["path"]) or "(root)"
                if dir_name not in files_by_dir:
                    files_by_dir[dir_name] = []
                files_by_dir[dir_name].append(file_info)

            # Build file tree overview
            tree_lines = [f"# {os.path.basename(target_path) or 'workspace'}/"]
            tree_lines.append(
                f"Total: {scan_result['total_files']} files, {scan_result['total_tokens']:,} tokens\n"
            )

            for dir_name in sorted(files_by_dir.keys()):
                if dir_name != "(root)":
                    tree_lines.append(f"\n## {dir_name}/")
                dir_files = files_by_dir[dir_name]
                dir_tokens = sum(f["tokens"] for f in dir_files)
                tree_lines.append(f"({len(dir_files)} files, {dir_tokens:,} tokens)")
                for f in sorted(dir_files, key=lambda x: x["path"]):
                    tree_lines.append(
                        f"  - {os.path.basename(f['path'])} ({f['tokens']:,} tokens)"
                    )

            file_tree_overview = "\n".join(tree_lines)

            # Chunk files for analysis if total tokens exceed limit
            chunks = []
            current_chunk = {"files": [], "tokens": 0}

            for file_info in sorted(scan_result["files"], key=lambda x: x["path"]):
                # If adding this file would exceed chunk limit, start new chunk
                if (
                    current_chunk["tokens"] + file_info["tokens"] > CHUNK_TOKEN_LIMIT
                    and current_chunk["files"]
                ):
                    chunks.append(current_chunk)
                    current_chunk = {"files": [], "tokens": 0}

                current_chunk["files"].append(file_info)
                current_chunk["tokens"] += file_info["tokens"]

            if current_chunk["files"]:
                chunks.append(current_chunk)

            logging.info(
                f"[create_or_update_codebase_map] Split into {len(chunks)} chunks for analysis"
            )

            # Analyze each chunk
            chunk_analyses = []
            for i, chunk in enumerate(chunks):
                chunk_content = []
                for file_info in chunk["files"]:
                    chunk_content.append(
                        f"\n### File: {file_info['path']} ({file_info['tokens']} tokens)\n```\n{file_info['content']}\n```"
                    )

                chunk_text = "\n".join(chunk_content)

                analysis_prompt = f"""You are mapping part of a codebase. Your goal is to thoroughly analyze each file and understand how they connect.

## Codebase Structure Overview
{file_tree_overview}

## Files to Analyze (Chunk {i + 1} of {len(chunks)})
{chunk_text}

## Analysis Instructions

For EACH file in this chunk, document:

1. **Purpose**: One-line description of what this file does
2. **Exports**: Key functions, classes, types, or values exported (with brief descriptions)
3. **Imports/Dependencies**: Notable imports and what they're used for
4. **Dependents**: If you can identify what other files might import this (based on exports)
5. **Patterns**: Design patterns or conventions used (e.g., singleton, factory, middleware pattern)
6. **Gotchas**: Non-obvious behavior, edge cases, warnings, or potential issues

Also identify across all files in this chunk:
- **Connections**: How these files connect to and depend on each other
- **Entry Points**: Which files serve as entry points or are called first
- **Data Flow**: How data moves between these files
- **Configuration**: Any environment variables or config dependencies
- **Technical Debt**: Areas that could use improvement or refactoring

Format your response as structured Markdown:
- Use `### filename.ext` headers for each file
- Use bullet points for lists
- Use code blocks for important function signatures
- Be thorough but concise"""

                chunk_response = self.ApiClient.prompt_agent(
                    agent_id=self.agent_id,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": analysis_prompt,
                        "disable_commands": True,
                        "log_user_input": False,
                        "log_output": False,
                        "conversation_name": self.conversation_id,
                    },
                )
                chunk_analyses.append(chunk_response)
                logging.info(
                    f"[create_or_update_codebase_map] Analyzed chunk {i + 1}/{len(chunks)}"
                )

            # Synthesize all chunk analyses into final map
            all_analyses = "\n\n---\n\n".join(chunk_analyses)

            synthesis_prompt = f"""You are synthesizing file analyses into a comprehensive codebase map document.

## Codebase Statistics
- Total Files: {scan_result['total_files']}
- Total Tokens: {scan_result['total_tokens']:,}
- Directories: {len(scan_result['directories'])}

## File Tree Overview
{file_tree_overview}

## Individual File Analyses
{all_analyses}

## Your Task
Create a comprehensive, well-structured CODEBASE_MAP.md. Follow this EXACT structure:

### 1. Frontmatter (Required)
```yaml
---
last_mapped: {datetime.datetime.utcnow().isoformat()}Z
total_files: {scan_result['total_files']}
total_tokens: {scan_result['total_tokens']}
---
```

### 2. System Overview
- Write a 2-3 sentence summary of what this codebase does
- Include a Mermaid architecture diagram showing major components:

```mermaid
graph TB
    subgraph Layer1[Layer Name]
        Component1[Component]
    end
    subgraph Layer2[Layer Name]
        Component2[Component]
    end
    Component1 --> Component2
```

Adapt the diagram to show the ACTUAL architecture based on your analysis.

### 3. Directory Structure
Create an annotated tree showing each directory's purpose:
```
project/
├── src/           # Source code
│   ├── api/       # REST API endpoints
│   ├── models/    # Data models
│   └── utils/     # Utility functions
├── tests/         # Test files
└── config/        # Configuration
```

### 4. Module Guide
For EACH major module/directory, create a section:

#### [Module Name]
**Purpose**: [What this module does]
**Entry Point**: [Main file that starts execution]

| File | Purpose | Tokens |
|------|---------|--------|
| file1.py | Description | 1,234 |
| file2.py | Description | 567 |

**Key Exports**: List main functions/classes exposed
**Dependencies**: What this module needs
**Dependents**: What depends on this module

### 5. Data Flow
Include Mermaid sequence diagrams for key flows:

```mermaid
sequenceDiagram
    participant User
    participant API
    participant Service
    participant Database
    
    User->>API: Request
    API->>Service: Process
    Service->>Database: Query
    Database-->>Service: Result
    Service-->>API: Response
    API-->>User: Result
```

Create diagrams for: authentication flow, main data operations, etc.

### 6. Conventions
Document naming conventions, coding patterns, and style:
- File naming conventions
- Function/class naming patterns
- Common design patterns used
- Error handling approach

### 7. Gotchas
List non-obvious behaviors and warnings:
- Edge cases developers should know
- Common mistakes to avoid
- Performance considerations
- Security considerations

### 8. Navigation Guide
Quick reference for common tasks:
- **To add a new API endpoint**: [list files to modify]
- **To add a new model**: [list files to modify]
- **To modify authentication**: [list files to modify]
- **To add tests**: [list files to modify]

## Output Requirements
- Use proper Markdown formatting
- Make it scannable with clear headers
- Use tables for file listings
- Include working Mermaid diagrams
- Be comprehensive but not verbose
- Focus on being useful for developers new to the codebase"""

            final_map = self.ApiClient.prompt_agent(
                agent_id=self.agent_id,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": synthesis_prompt,
                    "disable_commands": True,
                    "log_user_input": False,
                    "log_output": False,
                    "conversation_name": self.conversation_id,
                },
            )

            # Save the map
            map_path = self.safe_join("docs/CODEBASE_MAP.md")
            os.makedirs(os.path.dirname(map_path), exist_ok=True)
            with open(map_path, "w", encoding="utf-8") as f:
                f.write(final_map)

            # Generate summary statistics
            summary = f"""Codebase map created successfully!

**Statistics:**
- Files analyzed: {scan_result['total_files']}
- Total tokens: {scan_result['total_tokens']:,}
- Directories: {len(scan_result['directories'])}
- Analysis chunks: {len(chunks)}
- Skipped files: {len(scan_result['skipped'])}

**Map saved to:** {self.output_url}docs/CODEBASE_MAP.md

The map includes:
- System architecture overview with Mermaid diagrams
- Module-by-module documentation
- Data flow analysis
- Code conventions and patterns
- Navigation guide for common tasks"""

            return summary

        except Exception as e:
            logging.error(f"[create_or_update_codebase_map] Error: {str(e)}")
            return f"Error creating codebase map: {str(e)}"
