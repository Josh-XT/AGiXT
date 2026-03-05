import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Optional, List
from fastapi import HTTPException

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Dropbox Extension for AGiXT

This extension enables cloud file management via the Dropbox API.

Required environment variables:

- DROPBOX_CLIENT_ID: Dropbox App Key (OAuth App)
- DROPBOX_CLIENT_SECRET: Dropbox App Secret

How to set up a Dropbox OAuth App:

1. Go to https://www.dropbox.com/developers/apps
2. Click "Create app"
3. Choose "Scoped access" and "Full Dropbox" access type
4. Name your app
5. Under Settings, set the redirect URI to:
   your AGiXT APP_URI + /v1/oauth2/dropbox/callback
6. Under Permissions, enable:
   - files.metadata.read
   - files.metadata.write
   - files.content.read
   - files.content.write
   - sharing.read
   - sharing.write
   - account_info.read
7. Copy the App key (DROPBOX_CLIENT_ID) and App secret (DROPBOX_CLIENT_SECRET)
"""

SCOPES = [
    "files.metadata.read",
    "files.metadata.write",
    "files.content.read",
    "files.content.write",
    "sharing.read",
    "sharing.write",
    "account_info.read",
]
AUTHORIZE = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = True


class DropboxSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("DROPBOX_CLIENT_ID")
        self.client_secret = getenv("DROPBOX_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refreshes the Dropbox access token."""
        if not self.refresh_token:
            raise HTTPException(
                status_code=400, detail="No refresh token available for Dropbox."
            )

        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            response.raise_for_status()
            data = response.json()

            if "access_token" in data:
                self.access_token = data["access_token"]

            return data
        except Exception as e:
            logging.error(f"Error refreshing Dropbox token: {e}")
            raise HTTPException(
                status_code=401, detail=f"Failed to refresh Dropbox token: {str(e)}"
            )

    def get_user_info(self):
        """Gets user information from the Dropbox API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        try:
            response = requests.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

            if response.status_code == 401:
                self.get_new_token()
                response = requests.post(
                    "https://api.dropboxapi.com/2/users/get_current_account",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )

            data = response.json()
            name = data.get("name", {})

            return {
                "email": data.get("email", ""),
                "first_name": name.get("given_name", ""),
                "last_name": name.get("surname", ""),
                "provider_user_id": data.get("account_id", ""),
            }
        except Exception as e:
            logging.error(f"Error getting Dropbox user info: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Dropbox: {str(e)}",
            )


def sso(code, redirect_uri=None) -> DropboxSSO:
    """Handles the OAuth2 authorization code flow for Dropbox."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("DROPBOX_CLIENT_ID")
    client_secret = getenv("DROPBOX_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Dropbox Client ID or Secret not configured.")
        return None

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        data = response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not access_token:
            logging.error(f"No access token in Dropbox OAuth response: {data}")
            return None

        return DropboxSSO(access_token=access_token, refresh_token=refresh_token)
    except Exception as e:
        logging.error(f"Error obtaining Dropbox access token: {e}")
        return None


class dropbox(Extensions):
    """
    The Dropbox extension for AGiXT enables cloud file management through the Dropbox API.
    It supports listing, uploading, downloading, searching, sharing, and managing files
    and folders in the user's Dropbox account.

    Requires a Dropbox App with OAuth2 configured.

    To set up:
    1. Create an app at https://www.dropbox.com/developers/apps
    2. Set DROPBOX_CLIENT_ID and DROPBOX_CLIENT_SECRET environment variables
    3. Connect your Dropbox account through AGiXT OAuth flow
    """

    CATEGORY = "Cloud Storage"
    friendly_name = "Dropbox"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("DROPBOX_ACCESS_TOKEN", None)
        self.api_url = "https://api.dropboxapi.com/2"
        self.content_url = "https://content.dropboxapi.com/2"
        self.auth = None
        self.commands = {}

        dropbox_client_id = getenv("DROPBOX_CLIENT_ID")
        dropbox_client_secret = getenv("DROPBOX_CLIENT_SECRET")

        if dropbox_client_id and dropbox_client_secret:
            self.commands = {
                "Dropbox - List Files": self.list_files,
                "Dropbox - Get File Info": self.get_file_info,
                "Dropbox - Download File": self.download_file,
                "Dropbox - Upload File": self.upload_file,
                "Dropbox - Delete": self.delete,
                "Dropbox - Move": self.move,
                "Dropbox - Copy": self.copy,
                "Dropbox - Create Folder": self.create_folder,
                "Dropbox - Search": self.search,
                "Dropbox - Get Shared Link": self.get_shared_link,
                "Dropbox - Create Shared Link": self.create_shared_link,
                "Dropbox - Get Space Usage": self.get_space_usage,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(
                        f"Error initializing Dropbox extension auth: {str(e)}"
                    )

    def _get_headers(self, content_type="application/json"):
        """Returns authorization headers for Dropbox API requests."""
        if not self.access_token:
            raise Exception("Dropbox Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type,
        }

    def verify_user(self):
        """Verifies the access token and refreshes if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="dropbox")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("dropbox_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
        except Exception as e:
            logging.error(f"Error verifying Dropbox token: {str(e)}")
            raise Exception(f"Dropbox authentication error: {str(e)}")

    def _format_size(self, size_bytes):
        """Format bytes into human-readable size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def _format_entry(self, entry):
        """Format a Dropbox file/folder entry."""
        tag = entry.get(".tag", "")
        name = entry.get("name", "")
        path = entry.get("path_display", "")

        if tag == "folder":
            return f"📁 **{name}** (`{path}`)"
        else:
            size = self._format_size(entry.get("size", 0))
            modified = entry.get("client_modified", "")
            return f"📄 **{name}** ({size}) (`{path}`) Modified: {modified[:10] if modified else 'N/A'}"

    async def list_files(self, path: str = "", recursive: bool = False):
        """
        List files and folders in a Dropbox directory.

        Args:
            path (str): Path to list. Use empty string for root. Default is root.
            recursive (bool): Whether to list recursively. Default False.

        Returns:
            str: Formatted list of files and folders or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/files/list_folder",
                headers=self._get_headers(),
                json={
                    "path": path if path else "",
                    "recursive": recursive,
                    "limit": 100,
                },
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            entries = data.get("entries", [])

            if not entries:
                return f"No files or folders found in '{path or '/'}'."

            folders = [e for e in entries if e.get(".tag") == "folder"]
            files = [e for e in entries if e.get(".tag") == "file"]

            result = f"**Contents of '{path or '/'}':**\n\n"
            if folders:
                result += "**Folders:**\n"
                for f in sorted(folders, key=lambda x: x.get("name", "")):
                    result += f"- {self._format_entry(f)}\n"
                result += "\n"
            if files:
                result += "**Files:**\n"
                for f in sorted(files, key=lambda x: x.get("name", "")):
                    result += f"- {self._format_entry(f)}\n"

            if data.get("has_more"):
                result += f"\n_More files available (showing first {len(entries)})_"

            return result
        except Exception as e:
            return f"Error listing files: {str(e)}"

    async def get_file_info(self, path: str):
        """
        Get metadata/info about a specific file or folder.

        Args:
            path (str): Path to the file or folder in Dropbox.

        Returns:
            str: File/folder details or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/files/get_metadata",
                headers=self._get_headers(),
                json={"path": path, "include_media_info": True},
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            tag = data.get(".tag", "")
            result = f"**{'Folder' if tag == 'folder' else 'File'}: {data.get('name', '')}**\n\n"
            result += f"- **Path:** {data.get('path_display', '')}\n"
            result += f"- **ID:** {data.get('id', '')}\n"

            if tag == "file":
                result += f"- **Size:** {self._format_size(data.get('size', 0))}\n"
                result += f"- **Modified:** {data.get('client_modified', 'N/A')}\n"
                result += (
                    f"- **Server Modified:** {data.get('server_modified', 'N/A')}\n"
                )
                result += f"- **Content Hash:** {data.get('content_hash', 'N/A')}\n"

            return result
        except Exception as e:
            return f"Error getting file info: {str(e)}"

    async def download_file(self, path: str):
        """
        Download a text file from Dropbox and return its content.
        Only works for text-based files (txt, md, json, csv, etc.).

        Args:
            path (str): Path to the file in Dropbox.

        Returns:
            str: File content or error message.
        """
        try:
            self.verify_user()
            import json as json_lib

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Dropbox-API-Arg": json_lib.dumps({"path": path}),
            }

            response = requests.post(
                f"{self.content_url}/files/download",
                headers=headers,
            )

            if response.status_code != 200:
                return f"Error downloading file: HTTP {response.status_code}"

            # Check if it's a text file by trying to decode
            try:
                content = response.content.decode("utf-8")
                if len(content) > 50000:
                    content = (
                        content[:50000] + "\n\n... (file truncated, showing first 50KB)"
                    )
                return f"**Content of {path}:**\n\n```\n{content}\n```"
            except UnicodeDecodeError:
                return f"File '{path}' is a binary file ({self._format_size(len(response.content))}). Cannot display content."
        except Exception as e:
            return f"Error downloading file: {str(e)}"

    async def upload_file(self, path: str, content: str):
        """
        Upload text content as a file to Dropbox.

        Args:
            path (str): Destination path in Dropbox (e.g., '/Documents/note.txt').
            content (str): The text content to upload.

        Returns:
            str: Upload confirmation or error message.
        """
        try:
            self.verify_user()
            import json as json_lib

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": json_lib.dumps(
                    {
                        "path": path,
                        "mode": "overwrite",
                        "autorename": False,
                        "mute": False,
                    }
                ),
            }

            response = requests.post(
                f"{self.content_url}/files/upload",
                headers=headers,
                data=content.encode("utf-8"),
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            return f"File uploaded successfully!\n- **Path:** {data.get('path_display', '')}\n- **Size:** {self._format_size(data.get('size', 0))}"
        except Exception as e:
            return f"Error uploading file: {str(e)}"

    async def delete(self, path: str):
        """
        Delete a file or folder from Dropbox.

        Args:
            path (str): Path to the file or folder to delete.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/files/delete_v2",
                headers=self._get_headers(),
                json={"path": path},
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            metadata = data.get("metadata", {})
            return f"Deleted: {metadata.get('path_display', path)}"
        except Exception as e:
            return f"Error deleting: {str(e)}"

    async def move(self, from_path: str, to_path: str):
        """
        Move or rename a file or folder in Dropbox.

        Args:
            from_path (str): Current path of the file/folder.
            to_path (str): New path for the file/folder.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/files/move_v2",
                headers=self._get_headers(),
                json={"from_path": from_path, "to_path": to_path},
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            metadata = data.get("metadata", {})
            return f"Moved to: {metadata.get('path_display', to_path)}"
        except Exception as e:
            return f"Error moving: {str(e)}"

    async def copy(self, from_path: str, to_path: str):
        """
        Copy a file or folder in Dropbox.

        Args:
            from_path (str): Path of the file/folder to copy.
            to_path (str): Destination path for the copy.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/files/copy_v2",
                headers=self._get_headers(),
                json={"from_path": from_path, "to_path": to_path},
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            metadata = data.get("metadata", {})
            return f"Copied to: {metadata.get('path_display', to_path)}"
        except Exception as e:
            return f"Error copying: {str(e)}"

    async def create_folder(self, path: str):
        """
        Create a folder in Dropbox.

        Args:
            path (str): Path for the new folder (e.g., '/Documents/NewFolder').

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/files/create_folder_v2",
                headers=self._get_headers(),
                json={"path": path, "autorename": False},
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            metadata = data.get("metadata", {})
            return f"Folder created: {metadata.get('path_display', path)}"
        except Exception as e:
            return f"Error creating folder: {str(e)}"

    async def search(self, query: str, path: str = "", max_results: int = 25):
        """
        Search for files and folders in Dropbox.

        Args:
            query (str): The search query.
            path (str, optional): Path to search within. Default is entire Dropbox.
            max_results (int): Maximum results to return (1-100). Default 25.

        Returns:
            str: Search results or error message.
        """
        try:
            self.verify_user()
            payload = {
                "query": query,
                "options": {
                    "max_results": min(int(max_results), 100),
                },
            }
            if path:
                payload["options"]["path"] = path

            response = requests.post(
                f"{self.api_url}/files/search_v2",
                headers=self._get_headers(),
                json=payload,
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            matches = data.get("matches", [])

            if not matches:
                return f"No results found for '{query}'."

            result = f"**Search results for '{query}' ({len(matches)} results):**\n\n"
            for match in matches:
                metadata = match.get("metadata", {}).get("metadata", {})
                result += f"- {self._format_entry(metadata)}\n"

            return result
        except Exception as e:
            return f"Error searching: {str(e)}"

    async def get_shared_link(self, path: str):
        """
        Get existing shared links for a file or folder.

        Args:
            path (str): Path to the file or folder.

        Returns:
            str: Shared links or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/sharing/list_shared_links",
                headers=self._get_headers(),
                json={"path": path, "direct_only": True},
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            links = data.get("links", [])
            if not links:
                return f"No shared links found for '{path}'. Use 'Create Shared Link' to create one."

            result = "**Shared Links:**\n\n"
            for link in links:
                result += f"- {link.get('url', '')} (Visibility: {link.get('link_permissions', {}).get('resolved_visibility', {}).get('.tag', 'unknown')})\n"

            return result
        except Exception as e:
            return f"Error getting shared links: {str(e)}"

    async def create_shared_link(self, path: str):
        """
        Create a shared link for a file or folder.

        Args:
            path (str): Path to the file or folder to share.

        Returns:
            str: The shared link URL or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/sharing/create_shared_link_with_settings",
                headers=self._get_headers(),
                json={
                    "path": path,
                    "settings": {
                        "requested_visibility": "public",
                    },
                },
            )
            data = response.json()

            if "error" in data:
                error_tag = data.get("error", {}).get(".tag", "")
                if error_tag == "shared_link_already_exists":
                    # Get existing link
                    return await self.get_shared_link(path)
                return f"Error: {data.get('error_summary', data['error'])}"

            return f"Shared link created: {data.get('url', '')}"
        except Exception as e:
            return f"Error creating shared link: {str(e)}"

    async def get_space_usage(self):
        """
        Get the user's Dropbox space usage information.

        Returns:
            str: Space usage details or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.api_url}/users/get_space_usage",
                headers=self._get_headers(),
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('error_summary', data['error'])}"

            used = data.get("used", 0)
            allocation = data.get("allocation", {})
            allocated = allocation.get("allocated", 0)

            result = "**Dropbox Space Usage:**\n\n"
            result += f"- **Used:** {self._format_size(used)}\n"
            result += f"- **Allocated:** {self._format_size(allocated)}\n"
            if allocated > 0:
                pct = (used / allocated) * 100
                result += f"- **Usage:** {pct:.1f}%\n"

            return result
        except Exception as e:
            return f"Error getting space usage: {str(e)}"
