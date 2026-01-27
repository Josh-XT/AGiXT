import os
import logging
import requests
import base64
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from fastapi import HTTPException


"""
Microsoft SharePoint Extension - SharePoint site and document management.

This extension provides access to Microsoft SharePoint sites and document libraries,
including browsing sites, managing files, and searching across SharePoint. It requires
separate OAuth authorization from the main Microsoft SSO connection.

Required environment variables:

- MICROSOFT_CLIENT_ID: Microsoft OAuth client ID
- MICROSOFT_CLIENT_SECRET: Microsoft OAuth client secret

Required scopes:
- offline_access: Required for refresh tokens
- User.Read: Read user profile information
- Sites.ReadWrite.All: Full access to SharePoint sites
"""

SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Sites.ReadWrite.All",
]
AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
PKCE_REQUIRED = False


class MicrosoftSharepointSSO:
    """SSO handler for Microsoft SharePoint with site-specific scopes."""

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
            raise Exception(f"Microsoft SharePoint token refresh failed: {response.text}")

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


def sso(code, redirect_uri=None) -> MicrosoftSharepointSSO:
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
        logging.error(f"Error getting Microsoft SharePoint access token: {response.text}")
        return None
    data = response.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "Not provided")
    return MicrosoftSharepointSSO(access_token=access_token, refresh_token=refresh_token)


class microsoft_sharepoint(Extensions):
    """
    Microsoft SharePoint Extension.

    This extension provides comprehensive integration with Microsoft SharePoint,
    allowing AI agents to access and manage SharePoint sites and document libraries.

    Features:
    - List accessible SharePoint sites
    - Browse document libraries
    - List, upload, download files
    - Create folders
    - Delete items
    - Search across SharePoint

    This extension requires separate authorization with SharePoint-specific scopes,
    independent from the basic Microsoft SSO connection.
    """

    CATEGORY = "Productivity"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("MICROSOFT_SHAREPOINT_ACCESS_TOKEN", None)
        microsoft_client_id = getenv("MICROSOFT_CLIENT_ID")
        microsoft_client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.timezone = getenv("TZ")
        self.auth = None

        if microsoft_client_id and microsoft_client_secret:
            self.commands = {
                "List SharePoint Sites": self.list_sites,
                "Get SharePoint Site": self.get_site,
                "List SharePoint Document Libraries": self.list_libraries,
                "List SharePoint Files": self.list_files,
                "Get SharePoint File Content": self.get_file_content,
                "Upload File to SharePoint": self.upload_file,
                "Download File from SharePoint": self.download_file,
                "Create SharePoint Folder": self.create_folder,
                "Delete SharePoint Item": self.delete_item,
                "Search SharePoint": self.search,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(f"Error initializing Microsoft SharePoint client: {str(e)}")

        self.attachments_dir = kwargs.get(
            "conversation_directory", "./WORKSPACE/attachments"
        )
        os.makedirs(self.attachments_dir, exist_ok=True)

    def verify_user(self):
        """Verifies that the current access token is valid."""
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="microsoft_sharepoint")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the Microsoft SharePoint extension is connected."
            )

    async def list_sites(self, search_query=None, max_sites=50):
        """
        Lists SharePoint sites accessible to the user.

        Args:
            search_query (str): Optional search query to filter sites
            max_sites (int): Maximum number of sites to return

        Returns:
            list: List of site dictionaries
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if search_query:
                url = f"https://graph.microsoft.com/v1.0/sites?search={search_query}&$top={max_sites}"
            else:
                url = f"https://graph.microsoft.com/v1.0/sites?$top={max_sites}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint list sites error: {response.text}")
                return {"error": f"Failed to list sites: {response.text}"}

            data = response.json()
            sites = []

            for site in data.get("value", []):
                sites.append({
                    "id": site.get("id"),
                    "name": site.get("name"),
                    "display_name": site.get("displayName"),
                    "web_url": site.get("webUrl"),
                    "created_time": site.get("createdDateTime"),
                    "description": site.get("description", ""),
                })

            return sites

        except Exception as e:
            logging.error(f"Error listing SharePoint sites: {str(e)}")
            return {"error": str(e)}

    async def get_site(self, site_id=None, site_url=None):
        """
        Gets detailed information about a SharePoint site.

        Args:
            site_id (str): The site ID
            site_url (str): Alternatively, the site URL (e.g., "contoso.sharepoint.com:/sites/teamsite")

        Returns:
            dict: Site information
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if site_id:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}"
            elif site_url:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_url}"
            else:
                return {"error": "Either site_id or site_url must be provided"}

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint get site error: {response.text}")
                return {"error": f"Failed to get site: {response.text}"}

            site = response.json()
            return {
                "id": site.get("id"),
                "name": site.get("name"),
                "display_name": site.get("displayName"),
                "web_url": site.get("webUrl"),
                "created_time": site.get("createdDateTime"),
                "description": site.get("description", ""),
                "root": site.get("root", {}),
            }

        except Exception as e:
            logging.error(f"Error getting SharePoint site: {str(e)}")
            return {"error": str(e)}

    async def list_libraries(self, site_id):
        """
        Lists document libraries in a SharePoint site.

        Args:
            site_id (str): The SharePoint site ID

        Returns:
            list: List of document library dictionaries
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint list libraries error: {response.text}")
                return {"error": f"Failed to list libraries: {response.text}"}

            data = response.json()
            libraries = []

            for drive in data.get("value", []):
                libraries.append({
                    "id": drive.get("id"),
                    "name": drive.get("name"),
                    "description": drive.get("description", ""),
                    "web_url": drive.get("webUrl"),
                    "drive_type": drive.get("driveType"),
                    "created_time": drive.get("createdDateTime"),
                    "quota": drive.get("quota", {}),
                })

            return libraries

        except Exception as e:
            logging.error(f"Error listing SharePoint libraries: {str(e)}")
            return {"error": str(e)}

    async def list_files(self, site_id, drive_id=None, folder_path="root", max_items=50):
        """
        Lists files in a SharePoint document library.

        Args:
            site_id (str): The SharePoint site ID
            drive_id (str): The document library (drive) ID
            folder_path (str): Path within the library (use "root" for root)
            max_items (int): Maximum number of items to return

        Returns:
            list: List of files and folders
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {"error": f"Failed to get default library: {drive_response.text}"}
                drive_id = drive_response.json().get("id")

            if folder_path == "root" or not folder_path:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/children?$top={max_items}"
            else:
                encoded_path = folder_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/children?$top={max_items}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logging.error(f"SharePoint list files error: {response.text}")
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
                    "created_by": item.get("createdBy", {}).get("user", {}).get("displayName"),
                    "modified_by": item.get("lastModifiedBy", {}).get("user", {}).get("displayName"),
                }

                if "file" in item:
                    item_info["mime_type"] = item.get("file", {}).get("mimeType")

                if "folder" in item:
                    item_info["child_count"] = item.get("folder", {}).get("childCount", 0)

                items.append(item_info)

            return items

        except Exception as e:
            logging.error(f"Error listing SharePoint files: {str(e)}")
            return {"error": str(e)}

    async def get_file_content(self, site_id, drive_id=None, file_path=None, file_id=None):
        """
        Gets the content of a file from SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            drive_id (str): The document library ID (optional)
            file_path (str): Path to the file
            file_id (str): Alternatively, the unique file ID

        Returns:
            dict: File content
        """
        try:
            self.verify_user()

            headers = {"Authorization": f"Bearer {self.access_token}"}

            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {"error": f"Failed to get default library: {drive_response.text}"}
                drive_id = drive_response.json().get("id")

            if file_id:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{file_id}/content"
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/content"
            else:
                return {"error": "Either file_path or file_id must be provided"}

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                return {"error": f"Failed to get file content: {response.text}"}

            try:
                return {"content": response.text, "encoding": "text"}
            except:
                return {
                    "content": base64.b64encode(response.content).decode(),
                    "encoding": "base64",
                }

        except Exception as e:
            logging.error(f"Error getting SharePoint file content: {str(e)}")
            return {"error": str(e)}

    async def upload_file(self, site_id, destination_path, file_path=None, content=None, drive_id=None):
        """
        Uploads a file to SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            destination_path (str): Destination path in the library
            file_path (str): Local file path or filename if content is provided
            content (str): Direct content to upload
            drive_id (str): Document library ID (optional)

        Returns:
            dict: Upload result
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            }

            if content:
                file_content = content.encode() if isinstance(content, str) else content
            elif file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    file_content = f.read()
            else:
                return {"error": f"File not found: {file_path}"}

            if not drive_id:
                get_headers = {"Authorization": f"Bearer {self.access_token}"}
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=get_headers)
                if drive_response.status_code != 200:
                    return {"error": f"Failed to get default library: {drive_response.text}"}
                drive_id = drive_response.json().get("id")

            encoded_dest = destination_path.replace(" ", "%20")
            url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_dest}:/content"

            response = requests.put(url, headers=headers, data=file_content)

            if response.status_code in [200, 201]:
                result = response.json()
                return {
                    "success": True,
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "web_url": result.get("webUrl"),
                    "size": result.get("size"),
                }
            else:
                return {"error": f"Failed to upload file: {response.text}"}

        except Exception as e:
            logging.error(f"Error uploading to SharePoint: {str(e)}")
            return {"error": str(e)}

    async def download_file(self, site_id, drive_id=None, file_path=None, file_id=None, save_to=None):
        """
        Downloads a file from SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            drive_id (str): The document library ID (optional)
            file_path (str): Path to the file in SharePoint
            file_id (str): Alternatively, the unique file ID
            save_to (str): Local path to save the file

        Returns:
            dict: Download result with local file path
        """
        try:
            self.verify_user()

            headers = {"Authorization": f"Bearer {self.access_token}"}

            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {"error": f"Failed to get default library: {drive_response.text}"}
                drive_id = drive_response.json().get("id")

            if file_id:
                meta_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{file_id}"
            elif file_path:
                encoded_path = file_path.replace(" ", "%20")
                meta_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}"
            else:
                return {"error": "Either file_path or file_id must be provided"}

            meta_response = requests.get(meta_url, headers=headers)
            if meta_response.status_code != 200:
                return {"error": f"Failed to get file metadata: {meta_response.text}"}

            file_metadata = meta_response.json()
            file_name = file_metadata.get("name", "downloaded_file")

            download_url = file_metadata.get("@microsoft.graph.downloadUrl")
            if download_url:
                download_response = requests.get(download_url)
            else:
                if file_id:
                    content_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{file_id}/content"
                else:
                    content_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/content"
                download_response = requests.get(content_url, headers=headers)

            if download_response.status_code != 200:
                return {"error": f"Failed to download file: {download_response.text}"}

            if save_to:
                local_path = save_to
            else:
                os.makedirs(self.attachments_dir, exist_ok=True)
                local_path = os.path.join(self.attachments_dir, file_name)

            with open(local_path, "wb") as f:
                f.write(download_response.content)

            return {
                "success": True,
                "local_path": local_path,
                "file_name": file_name,
                "size": len(download_response.content),
            }

        except Exception as e:
            logging.error(f"Error downloading from SharePoint: {str(e)}")
            return {"error": str(e)}

    async def create_folder(self, site_id, folder_name, parent_path="root", drive_id=None):
        """
        Creates a folder in SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            folder_name (str): Name of the folder to create
            parent_path (str): Parent folder path
            drive_id (str): Document library ID (optional)

        Returns:
            dict: Created folder information
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {"error": f"Failed to get default library: {drive_response.text}"}
                drive_id = drive_response.json().get("id")

            if parent_path == "root" or not parent_path:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/children"
            else:
                encoded_path = parent_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}:/children"

            folder_data = {
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename",
            }

            response = requests.post(url, headers=headers, json=folder_data)

            if response.status_code == 201:
                result = response.json()
                return {
                    "success": True,
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "web_url": result.get("webUrl"),
                }
            else:
                return {"error": f"Failed to create folder: {response.text}"}

        except Exception as e:
            logging.error(f"Error creating SharePoint folder: {str(e)}")
            return {"error": str(e)}

    async def delete_item(self, site_id, drive_id=None, item_path=None, item_id=None):
        """
        Deletes a file or folder from SharePoint.

        Args:
            site_id (str): The SharePoint site ID
            drive_id (str): Document library ID (optional)
            item_path (str): Path to the item
            item_id (str): Alternatively, the unique item ID

        Returns:
            dict: Deletion result
        """
        try:
            self.verify_user()

            headers = {"Authorization": f"Bearer {self.access_token}"}

            if not drive_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {"error": f"Failed to get default library: {drive_response.text}"}
                drive_id = drive_response.json().get("id")

            if item_id:
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{item_id}"
            elif item_path:
                encoded_path = item_path.replace(" ", "%20")
                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{encoded_path}"
            else:
                return {"error": "Either item_path or item_id must be provided"}

            response = requests.delete(url, headers=headers)

            if response.status_code == 204:
                return {"success": True, "message": "Item deleted successfully"}
            else:
                return {"error": f"Failed to delete item: {response.text}"}

        except Exception as e:
            logging.error(f"Error deleting SharePoint item: {str(e)}")
            return {"error": str(e)}

    async def search(self, query, site_id=None, max_results=25):
        """
        Searches for files across SharePoint.

        Args:
            query (str): Search query
            site_id (str): Optional site ID to limit search
            max_results (int): Maximum number of results

        Returns:
            list: List of matching items
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if site_id:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code != 200:
                    return {"error": f"Failed to get site drive: {drive_response.text}"}
                drive_id = drive_response.json().get("id")

                url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/search(q='{query}')?$top={max_results}"
                response = requests.get(url, headers=headers)

                if response.status_code != 200:
                    return {"error": f"Search failed: {response.text}"}

                data = response.json()
                items = []

                for item in data.get("value", []):
                    items.append({
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "type": "folder" if "folder" in item else "file",
                        "size": item.get("size", 0),
                        "path": item.get("parentReference", {}).get("path", ""),
                        "web_url": item.get("webUrl"),
                        "modified_time": item.get("lastModifiedDateTime"),
                    })

                return items
            else:
                # Search across all SharePoint
                url = "https://graph.microsoft.com/v1.0/search/query"
                search_body = {
                    "requests": [
                        {
                            "entityTypes": ["driveItem"],
                            "query": {"queryString": query},
                            "from": 0,
                            "size": max_results,
                        }
                    ]
                }

                response = requests.post(url, headers=headers, json=search_body)

                if response.status_code != 200:
                    return {"error": f"Search failed: {response.text}"}

                data = response.json()
                items = []

                for hit_container in data.get("value", []):
                    for hit in hit_container.get("hitsContainers", []):
                        for result in hit.get("hits", []):
                            resource = result.get("resource", {})
                            items.append({
                                "id": resource.get("id"),
                                "name": resource.get("name"),
                                "web_url": resource.get("webUrl"),
                                "size": resource.get("size"),
                                "modified_time": resource.get("lastModifiedDateTime"),
                                "site_name": resource.get("parentReference", {}).get("siteId"),
                            })

                return items

        except Exception as e:
            logging.error(f"Error searching SharePoint: {str(e)}")
            return {"error": str(e)}
