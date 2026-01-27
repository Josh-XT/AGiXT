import os
import logging
import requests
import base64
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from fastapi import HTTPException


"""
Microsoft OneDrive Extension - Cloud file storage functionality.

This extension provides access to Microsoft OneDrive cloud storage, including
file management, upload, download, and search capabilities. It requires separate
OAuth authorization from the main Microsoft SSO connection.

Required environment variables:

- MICROSOFT_CLIENT_ID: Microsoft OAuth client ID
- MICROSOFT_CLIENT_SECRET: Microsoft OAuth client secret

Required scopes:
- offline_access: Required for refresh tokens
- User.Read: Read user profile information
- Files.ReadWrite.All: Full access to OneDrive files
"""

SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Files.ReadWrite.All",
]
AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
PKCE_REQUIRED = False


class MicrosoftOnedriveSSO:
    """SSO handler for Microsoft OneDrive with file-specific scopes."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(SCOPES),
            },
        )

        if response.status_code != 200:
            logging.error(f"Token refresh failed with response: {response.text}")
            raise Exception(f"Microsoft OneDrive token refresh failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            logging.error("No access_token in refresh response")

        return token_data

    def get_user_info(self):
        uri = "https://graph.microsoft.com/v1.0/me"

        if not self.access_token:
            logging.error("No access token available")

        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

        if response.status_code == 401:
            self.access_token = self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        try:
            data = response.json()
            first_name = data.get("givenName", "") or ""
            last_name = data.get("surname", "") or ""
            email = data.get("mail") or data.get("userPrincipalName", "")

            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error parsing Microsoft user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Microsoft",
            )


def sso(code, redirect_uri=None) -> MicrosoftOnedriveSSO:
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")
    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )
    response = requests.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": getenv("MICROSOFT_CLIENT_ID"),
            "client_secret": getenv("MICROSOFT_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
        },
    )
    if response.status_code != 200:
        logging.error(f"Error getting Microsoft OneDrive access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "Not provided")
    return MicrosoftOnedriveSSO(access_token=access_token, refresh_token=refresh_token)


class microsoft_onedrive(Extensions):
    """
    Microsoft OneDrive Extension.

    This extension provides comprehensive integration with Microsoft OneDrive cloud storage,
    allowing AI agents to manage files and folders in the user's OneDrive.

    Features:
    - List files and folders
    - Get file content
    - Upload files
    - Download files
    - Create folders
    - Delete items
    - Search files
    - Move and copy items

    This extension requires separate authorization with OneDrive-specific scopes,
    independent from the basic Microsoft SSO connection.
    """

    CATEGORY = "Productivity"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("MICROSOFT_ONEDRIVE_ACCESS_TOKEN", None)
        microsoft_client_id = getenv("MICROSOFT_CLIENT_ID")
        microsoft_client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.timezone = getenv("TZ")
        self.auth = None

        if microsoft_client_id and microsoft_client_secret:
            self.commands = {
                "List OneDrive Files": self.list_files,
                "Get OneDrive File Content": self.get_file_content,
                "Upload File to OneDrive": self.upload_file,
                "Download File from OneDrive": self.download_file,
                "Create OneDrive Folder": self.create_folder,
                "Delete OneDrive Item": self.delete_item,
                "Search OneDrive": self.search,
                "Move OneDrive Item": self.move_item,
                "Copy OneDrive Item": self.copy_item,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(f"Error initializing Microsoft OneDrive client: {str(e)}")

        self.attachments_dir = kwargs.get(
            "conversation_directory", "./WORKSPACE/attachments"
        )
        os.makedirs(self.attachments_dir, exist_ok=True)

    def verify_user(self):
        """Verifies that the current access token is valid."""
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="microsoft_onedrive")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the Microsoft OneDrive extension is connected."
            )

    async def list_files(self, folder_path="root", max_items=50):
        """
        Lists files and folders in OneDrive.

        Args:
            folder_path (str): Path to the folder to list (use "root" for root folder, or a path like "Documents/Reports")
            max_items (int): Maximum number of items to retrieve

        Returns:
            list: List of file/folder dictionaries with id, name, type, size, and other metadata
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if folder_path == "root" or not folder_path:
                url = f"https://graph.microsoft.com/v1.0/me/drive/root/children?$top={max_items}"
            else:
                encoded_path = folder_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/children?$top={max_items}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"OneDrive list files error: {response.text}")
                return {"error": f"Failed to list files: {response.text}"}

            data = response.json()
            items = []

            for item in data.get("value", []):
                item_info = {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": "folder" if "folder" in item else "file",
                    "size": item.get("size", 0),
                    "created_time": item.get("createdDateTime"),
                    "modified_time": item.get("lastModifiedDateTime"),
                    "web_url": item.get("webUrl"),
                }

                if "file" in item:
                    item_info["mime_type"] = item.get("file", {}).get("mimeType")

                if "folder" in item:
                    item_info["child_count"] = item.get("folder", {}).get("childCount", 0)

                items.append(item_info)

            return items

        except Exception as e:
            logging.error(f"Error listing OneDrive files: {str(e)}")
            return {"error": str(e)}

    async def get_file_content(self, file_path=None, file_id=None):
        """
        Gets the content of a file from OneDrive.

        Args:
            file_path (str): Path to the file (e.g., "Documents/report.txt")
            file_id (str): Alternatively, the unique file ID

        Returns:
            dict: File content and encoding information
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            if file_id:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/content"
            else:
                return {"error": "Either file_path or file_id must be provided"}

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"OneDrive get file error: {response.text}")
                return {"error": f"Failed to get file content: {response.text}"}

            try:
                return {"content": response.text, "encoding": "text"}
            except:
                return {
                    "content": base64.b64encode(response.content).decode(),
                    "encoding": "base64",
                }

        except Exception as e:
            logging.error(f"Error getting OneDrive file content: {str(e)}")
            return {"error": str(e)}

    async def upload_file(self, file_path, destination_path, content=None):
        """
        Uploads a file to OneDrive.

        Args:
            file_path (str): Local path to the file to upload, or filename if content is provided
            destination_path (str): Destination path in OneDrive (e.g., "Documents/uploads/myfile.txt")
            content (str): Optional - direct content to upload instead of reading from file_path

        Returns:
            dict: Upload result with file ID and web URL
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            }

            if content:
                file_content = content.encode() if isinstance(content, str) else content
            elif os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    file_content = f.read()
            else:
                return {"error": f"File not found: {file_path}"}

            encoded_path = destination_path.replace(" ", "%20")
            url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/content"

            response = requests.put(url, headers=headers, data=file_content)

            if response.status_code in [200, 201]:
                data = response.json()
                return {
                    "success": True,
                    "file_id": data.get("id"),
                    "name": data.get("name"),
                    "web_url": data.get("webUrl"),
                    "size": data.get("size"),
                }
            else:
                logging.error(f"OneDrive upload error: {response.text}")
                return {"error": f"Failed to upload file: {response.text}"}

        except Exception as e:
            logging.error(f"Error uploading to OneDrive: {str(e)}")
            return {"error": str(e)}

    async def download_file(self, file_path=None, file_id=None, save_to=None):
        """
        Downloads a file from OneDrive.

        Args:
            file_path (str): Path to the file in OneDrive
            file_id (str): Alternatively, the unique file ID
            save_to (str): Optional local path to save the file

        Returns:
            dict: Download result with local path or content
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            # First get file metadata
            if file_id:
                metadata_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
                content_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                metadata_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}"
                content_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/content"
            else:
                return {"error": "Either file_path or file_id must be provided"}

            # Get metadata for filename
            metadata_response = requests.get(metadata_url, headers=headers)
            if metadata_response.status_code != 200:
                return {"error": f"Failed to get file metadata: {metadata_response.text}"}

            metadata = metadata_response.json()
            filename = metadata.get("name", "downloaded_file")

            # Download content
            response = requests.get(content_url, headers=headers)

            if response.status_code != 200:
                return {"error": f"Failed to download file: {response.text}"}

            if save_to:
                save_path = save_to
            else:
                save_path = os.path.join(self.attachments_dir, filename)

            os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)

            with open(save_path, "wb") as f:
                f.write(response.content)

            return {
                "success": True,
                "local_path": save_path,
                "filename": filename,
                "size": len(response.content),
            }

        except Exception as e:
            logging.error(f"Error downloading from OneDrive: {str(e)}")
            return {"error": str(e)}

    async def create_folder(self, folder_name, parent_path="root"):
        """
        Creates a new folder in OneDrive.

        Args:
            folder_name (str): Name of the folder to create
            parent_path (str): Parent folder path (use "root" for root)

        Returns:
            dict: Folder creation result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if parent_path == "root" or not parent_path:
                url = "https://graph.microsoft.com/v1.0/me/drive/root/children"
            else:
                encoded_path = parent_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}:/children"

            folder_data = {
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename",
            }

            response = requests.post(url, headers=headers, json=folder_data)

            if response.status_code == 201:
                data = response.json()
                return {
                    "success": True,
                    "folder_id": data.get("id"),
                    "name": data.get("name"),
                    "web_url": data.get("webUrl"),
                }
            else:
                logging.error(f"OneDrive create folder error: {response.text}")
                return {"error": f"Failed to create folder: {response.text}"}

        except Exception as e:
            logging.error(f"Error creating OneDrive folder: {str(e)}")
            return {"error": str(e)}

    async def delete_item(self, file_path=None, file_id=None):
        """
        Deletes a file or folder from OneDrive.

        Args:
            file_path (str): Path to the item to delete
            file_id (str): Alternatively, the unique item ID

        Returns:
            dict: Deletion result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            if file_id:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}"
            else:
                return {"error": "Either file_path or file_id must be provided"}

            response = requests.delete(url, headers=headers)

            if response.status_code == 204:
                return {"success": True, "message": "Item deleted successfully"}
            else:
                logging.error(f"OneDrive delete error: {response.text}")
                return {"error": f"Failed to delete item: {response.text}"}

        except Exception as e:
            logging.error(f"Error deleting OneDrive item: {str(e)}")
            return {"error": str(e)}

    async def search(self, query, max_results=25):
        """
        Searches for files in OneDrive.

        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return

        Returns:
            list: List of matching items
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{query}')?$top={max_results}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"OneDrive search error: {response.text}")
                return {"error": f"Search failed: {response.text}"}

            data = response.json()
            items = []

            for item in data.get("value", []):
                item_info = {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": "folder" if "folder" in item else "file",
                    "size": item.get("size", 0),
                    "web_url": item.get("webUrl"),
                    "path": item.get("parentReference", {}).get("path", ""),
                }
                items.append(item_info)

            return items

        except Exception as e:
            logging.error(f"Error searching OneDrive: {str(e)}")
            return {"error": str(e)}

    async def move_item(self, source_path=None, source_id=None, destination_folder_path=None, destination_folder_id=None):
        """
        Moves an item to a different folder in OneDrive.

        Args:
            source_path (str): Path of item to move
            source_id (str): Alternatively, item ID
            destination_folder_path (str): Destination folder path
            destination_folder_id (str): Alternatively, destination folder ID

        Returns:
            dict: Move operation result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Determine source URL
            if source_id:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{source_id}"
            elif source_path:
                encoded_path = source_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}"
            else:
                return {"error": "Either source_path or source_id must be provided"}

            # Get destination folder ID
            if destination_folder_id:
                dest_id = destination_folder_id
            elif destination_folder_path:
                if destination_folder_path == "root":
                    dest_id = "root"
                else:
                    # Look up folder ID
                    encoded_dest = destination_folder_path.replace(" ", "%20")
                    dest_response = requests.get(
                        f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_dest}",
                        headers=headers,
                    )
                    if dest_response.status_code != 200:
                        return {"error": f"Destination folder not found: {destination_folder_path}"}
                    dest_id = dest_response.json().get("id")
            else:
                return {"error": "Either destination_folder_path or destination_folder_id must be provided"}

            move_data = {
                "parentReference": {"id": dest_id}
            }

            response = requests.patch(url, headers=headers, json=move_data)

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "new_path": data.get("parentReference", {}).get("path", ""),
                }
            else:
                return {"error": f"Failed to move item: {response.text}"}

        except Exception as e:
            logging.error(f"Error moving OneDrive item: {str(e)}")
            return {"error": str(e)}

    async def copy_item(self, source_path=None, source_id=None, destination_folder_path=None, destination_folder_id=None, new_name=None):
        """
        Copies an item to a different location in OneDrive.

        Args:
            source_path (str): Path of item to copy
            source_id (str): Alternatively, item ID
            destination_folder_path (str): Destination folder path
            destination_folder_id (str): Alternatively, destination folder ID
            new_name (str): Optional new name for the copied item

        Returns:
            dict: Copy operation result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Determine source URL
            if source_id:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{source_id}/copy"
            elif source_path:
                encoded_path = source_path.replace(" ", "%20")
                # First get the item ID
                item_response = requests.get(
                    f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_path}",
                    headers=headers,
                )
                if item_response.status_code != 200:
                    return {"error": f"Source item not found: {source_path}"}
                item_id = item_response.json().get("id")
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/copy"
            else:
                return {"error": "Either source_path or source_id must be provided"}

            # Get destination folder ID
            if destination_folder_id:
                dest_id = destination_folder_id
            elif destination_folder_path:
                if destination_folder_path == "root":
                    dest_id = "root"
                else:
                    encoded_dest = destination_folder_path.replace(" ", "%20")
                    dest_response = requests.get(
                        f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded_dest}",
                        headers=headers,
                    )
                    if dest_response.status_code != 200:
                        return {"error": f"Destination folder not found: {destination_folder_path}"}
                    dest_id = dest_response.json().get("id")
            else:
                return {"error": "Either destination_folder_path or destination_folder_id must be provided"}

            copy_data = {
                "parentReference": {"driveId": "me", "id": dest_id}
            }
            if new_name:
                copy_data["name"] = new_name

            response = requests.post(url, headers=headers, json=copy_data)

            if response.status_code == 202:
                return {
                    "success": True,
                    "message": "Copy operation started. It may take a moment to complete.",
                    "monitor_url": response.headers.get("Location"),
                }
            else:
                return {"error": f"Failed to copy item: {response.text}"}

        except Exception as e:
            logging.error(f"Error copying OneDrive item: {str(e)}")
            return {"error": str(e)}
