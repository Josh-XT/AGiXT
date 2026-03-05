import logging
import json
import requests
from Extensions import Extensions
from Globals import getenv
from typing import Optional, List

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Obsidian Extension for AGiXT

This extension enables interaction with Obsidian vaults via the
Obsidian Local REST API plugin (https://github.com/coddingtonbear/obsidian-local-rest-api).

Required environment variables:

- OBSIDIAN_API_URL: The URL of the Obsidian Local REST API (e.g., https://localhost:27124)
- OBSIDIAN_API_KEY: The API key configured in the Local REST API plugin settings

Setup instructions:

1. Install the "Local REST API" community plugin in Obsidian
   - Open Obsidian Settings -> Community plugins -> Browse
   - Search for "Local REST API" and install it
   - Enable the plugin
2. Configure the plugin:
   - Go to Settings -> Local REST API
   - Note the port (default: 27124) and the API key
   - Enable HTTPS if desired (recommended for security)
3. Set environment variables:
   - OBSIDIAN_API_URL=https://localhost:27124
   - OBSIDIAN_API_KEY=<your API key from plugin settings>

The plugin must be running (Obsidian must be open) for the extension to work.
"""


class obsidian(Extensions):
    """
    The Obsidian extension for AGiXT enables interaction with Obsidian vaults via the
    Local REST API plugin. It supports reading, creating, updating, and searching notes,
    managing daily notes, listing vault contents, and working with tags.

    Requires the Obsidian Local REST API community plugin to be installed and configured.

    To set up:
    1. Install "Local REST API" plugin in Obsidian
    2. Enable it and note the API key from plugin settings
    3. Set OBSIDIAN_API_URL and OBSIDIAN_API_KEY environment variables
    """

    CATEGORY = "Productivity & Organization"
    friendly_name = "Obsidian"

    def __init__(self, **kwargs):
        self.base_url = kwargs.get("OBSIDIAN_API_URL", getenv("OBSIDIAN_API_URL", ""))
        self.api_key = kwargs.get("OBSIDIAN_API_KEY", getenv("OBSIDIAN_API_KEY", ""))
        self.commands = {}

        if self.base_url and self.api_key:
            self.commands = {
                "Obsidian - Get Note": self.get_note,
                "Obsidian - Create Note": self.create_note,
                "Obsidian - Update Note": self.update_note,
                "Obsidian - Append to Note": self.append_to_note,
                "Obsidian - Delete Note": self.delete_note,
                "Obsidian - Search Vault": self.search_vault,
                "Obsidian - List Vault Files": self.list_vault_files,
                "Obsidian - Get Active Note": self.get_active_note,
                "Obsidian - Insert into Active Note": self.insert_into_active_note,
                "Obsidian - Open Note": self.open_note,
                "Obsidian - List Commands": self.list_commands,
                "Obsidian - Execute Command": self.execute_command,
            }

    def _get_headers(self):
        """Returns authorization headers for the Obsidian Local REST API."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.olrapi.note+json",
        }

    def _make_request(self, method, endpoint, **kwargs):
        """Make a request to the Obsidian Local REST API."""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = kwargs.pop("headers", self._get_headers())

        try:
            response = requests.request(
                method, url, headers=headers, verify=False, **kwargs
            )

            if response.status_code == 404:
                return None, "Resource not found in vault."
            if response.status_code == 401:
                return None, "Authentication failed. Check your OBSIDIAN_API_KEY."
            if response.status_code >= 400:
                return None, f"API error (HTTP {response.status_code}): {response.text}"

            # Some endpoints return no content
            if response.status_code == 204 or not response.text:
                return {"success": True}, None

            content_type = response.headers.get("Content-Type", "")
            if (
                "application/json" in content_type
                or "application/vnd.olrapi" in content_type
            ):
                return response.json(), None
            else:
                return {"content": response.text}, None

        except requests.exceptions.ConnectionError:
            return (
                None,
                "Cannot connect to Obsidian. Make sure Obsidian is running with the Local REST API plugin enabled.",
            )
        except Exception as e:
            return None, f"Request error: {str(e)}"

    async def get_note(self, file_path: str):
        """
        Get the content of a note from the Obsidian vault.

        Args:
            file_path (str): Path to the note relative to vault root (e.g., 'folder/note.md').
                             The .md extension is optional.

        Returns:
            str: The note content and metadata, or an error message.
        """
        if not file_path.endswith(".md"):
            file_path += ".md"

        data, error = self._make_request("GET", f"/vault/{file_path}")

        if error:
            return f"Error getting note: {error}"

        if isinstance(data, dict):
            content = data.get("content", "")
            tags = data.get("tags", [])
            frontmatter = data.get("frontmatter", {})

            result = f"**Note: {file_path}**\n\n"
            if frontmatter:
                result += f"**Frontmatter:** {json.dumps(frontmatter, indent=2)}\n\n"
            if tags:
                result += f"**Tags:** {', '.join(tags)}\n\n"
            result += f"**Content:**\n{content}"
            return result

        return str(data)

    async def create_note(self, file_path: str, content: str):
        """
        Create a new note in the Obsidian vault.

        Args:
            file_path (str): Path for the new note relative to vault root (e.g., 'folder/note.md').
                             The .md extension is optional.
            content (str): The markdown content for the note.

        Returns:
            str: Confirmation message or error.
        """
        if not file_path.endswith(".md"):
            file_path += ".md"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "text/markdown",
        }

        data, error = self._make_request(
            "PUT",
            f"/vault/{file_path}",
            headers=headers,
            data=content.encode("utf-8"),
        )

        if error:
            return f"Error creating note: {error}"

        return f"Successfully created note: {file_path}"

    async def update_note(self, file_path: str, content: str):
        """
        Update (overwrite) an existing note in the Obsidian vault.

        Args:
            file_path (str): Path to the note relative to vault root (e.g., 'folder/note.md').
            content (str): The new markdown content for the note.

        Returns:
            str: Confirmation message or error.
        """
        if not file_path.endswith(".md"):
            file_path += ".md"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "text/markdown",
        }

        data, error = self._make_request(
            "PUT",
            f"/vault/{file_path}",
            headers=headers,
            data=content.encode("utf-8"),
        )

        if error:
            return f"Error updating note: {error}"

        return f"Successfully updated note: {file_path}"

    async def append_to_note(self, file_path: str, content: str):
        """
        Append content to an existing note in the Obsidian vault.

        Args:
            file_path (str): Path to the note relative to vault root (e.g., 'folder/note.md').
            content (str): The markdown content to append to the note.

        Returns:
            str: Confirmation message or error.
        """
        if not file_path.endswith(".md"):
            file_path += ".md"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "text/markdown",
        }

        data, error = self._make_request(
            "POST",
            f"/vault/{file_path}",
            headers=headers,
            data=content.encode("utf-8"),
        )

        if error:
            return f"Error appending to note: {error}"

        return f"Successfully appended content to note: {file_path}"

    async def delete_note(self, file_path: str):
        """
        Delete a note from the Obsidian vault (moves to trash).

        Args:
            file_path (str): Path to the note relative to vault root (e.g., 'folder/note.md').

        Returns:
            str: Confirmation message or error.
        """
        if not file_path.endswith(".md"):
            file_path += ".md"

        data, error = self._make_request("DELETE", f"/vault/{file_path}")

        if error:
            return f"Error deleting note: {error}"

        return f"Successfully deleted note: {file_path}"

    async def search_vault(self, query: str):
        """
        Search for notes in the Obsidian vault using a text query.

        Args:
            query (str): The search query string. Supports Obsidian search syntax.

        Returns:
            str: Search results with matching notes and context, or an error message.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        data, error = self._make_request(
            "POST",
            "/search/simple/",
            headers=headers,
            data=query.encode("utf-8"),
        )

        if error:
            return f"Error searching vault: {error}"

        if isinstance(data, list):
            if not data:
                return f"No results found for query: '{query}'"

            results = []
            for item in data[:20]:  # Limit to 20 results
                filename = item.get("filename", "Unknown")
                matches = item.get("matches", [])
                match_context = ""
                if matches:
                    contexts = []
                    for match in matches[:3]:  # Show up to 3 match contexts per file
                        match_text = match.get("match", {}).get("content", "")
                        if match_text:
                            contexts.append(f"  - ...{match_text.strip()}...")
                    match_context = "\n".join(contexts)

                result = f"- **{filename}**"
                if match_context:
                    result += f"\n{match_context}"
                results.append(result)

            return f"Search results for '{query}':\n\n" + "\n".join(results)

        return str(data)

    async def list_vault_files(self, folder_path: str = "/"):
        """
        List files and folders in the Obsidian vault.

        Args:
            folder_path (str): Path to list, relative to vault root. Use '/' for root.

        Returns:
            str: List of files and folders, or an error message.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        data, error = self._make_request(
            "GET",
            f"/vault/{folder_path.lstrip('/')}",
            headers=headers,
        )

        if error:
            return f"Error listing vault files: {error}"

        if isinstance(data, dict) and "files" in data:
            files = data["files"]
            if not files:
                return f"No files found in: {folder_path}"

            folders = [f for f in files if f.endswith("/")]
            notes = [f for f in files if f.endswith(".md")]
            other = [f for f in files if not f.endswith("/") and not f.endswith(".md")]

            result = f"**Vault contents ({folder_path}):**\n\n"
            if folders:
                result += (
                    "**Folders:**\n"
                    + "\n".join(f"  📁 {f}" for f in sorted(folders))
                    + "\n\n"
                )
            if notes:
                result += (
                    "**Notes:**\n"
                    + "\n".join(f"  📝 {f}" for f in sorted(notes))
                    + "\n\n"
                )
            if other:
                result += (
                    "**Other files:**\n"
                    + "\n".join(f"  📎 {f}" for f in sorted(other))
                    + "\n\n"
                )

            return result

        return str(data)

    async def get_active_note(self):
        """
        Get the content of the currently active/open note in Obsidian.

        Returns:
            str: The active note content and metadata, or an error message.
        """
        data, error = self._make_request("GET", "/active/")

        if error:
            return f"Error getting active note: {error}"

        if isinstance(data, dict):
            content = data.get("content", "")
            path = data.get("path", "Unknown")
            tags = data.get("tags", [])
            frontmatter = data.get("frontmatter", {})

            result = f"**Active Note: {path}**\n\n"
            if frontmatter:
                result += f"**Frontmatter:** {json.dumps(frontmatter, indent=2)}\n\n"
            if tags:
                result += f"**Tags:** {', '.join(tags)}\n\n"
            result += f"**Content:**\n{content}"
            return result

        return str(data)

    async def insert_into_active_note(self, content: str, position: str = "end"):
        """
        Insert content into the currently active/open note in Obsidian.

        Args:
            content (str): The markdown content to insert.
            position (str): Where to insert - 'beginning' or 'end'. Default is 'end'.

        Returns:
            str: Confirmation message or error.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "text/markdown",
        }

        if position == "beginning":
            # Prepend by using PATCH with heading insertion
            data, error = self._make_request(
                "PATCH",
                "/active/",
                headers=headers,
                data=content.encode("utf-8"),
            )
        else:
            # Append using POST
            data, error = self._make_request(
                "POST",
                "/active/",
                headers=headers,
                data=content.encode("utf-8"),
            )

        if error:
            return f"Error inserting into active note: {error}"

        return f"Successfully inserted content into active note ({position})."

    async def open_note(self, file_path: str):
        """
        Open a note in Obsidian application.

        Args:
            file_path (str): Path to the note relative to vault root (e.g., 'folder/note.md').

        Returns:
            str: Confirmation message or error.
        """
        if not file_path.endswith(".md"):
            file_path += ".md"

        data, error = self._make_request(
            "POST",
            "/open/",
            json={"file": file_path},
        )

        if error:
            return f"Error opening note: {error}"

        return f"Opened note in Obsidian: {file_path}"

    async def list_commands(self):
        """
        List all available Obsidian commands.

        Returns:
            str: List of available commands, or an error message.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        data, error = self._make_request("GET", "/commands/", headers=headers)

        if error:
            return f"Error listing commands: {error}"

        if isinstance(data, dict) and "commands" in data:
            commands = data["commands"]
            if not commands:
                return "No commands available."

            result = "**Available Obsidian Commands:**\n\n"
            for cmd in commands:
                cmd_id = cmd.get("id", "")
                cmd_name = cmd.get("name", "Unknown")
                result += f"- **{cmd_name}** (`{cmd_id}`)\n"
            return result

        return str(data)

    async def execute_command(self, command_id: str):
        """
        Execute an Obsidian command by its ID.

        Args:
            command_id (str): The command ID to execute (e.g., 'daily-notes:open-daily-note').

        Returns:
            str: Confirmation message or error.
        """
        data, error = self._make_request(
            "POST",
            f"/commands/{command_id}/",
        )

        if error:
            return f"Error executing command: {error}"

        return f"Successfully executed command: {command_id}"
