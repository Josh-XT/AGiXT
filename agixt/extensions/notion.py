import logging
import json
import base64
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
Required environment variables:

- NOTION_CLIENT_ID: Notion OAuth client ID (public integration)
- NOTION_CLIENT_SECRET: Notion OAuth client secret (public integration)

How to set up a Notion public integration:

1. Go to https://www.notion.so/my-integrations
2. Click "+ New integration"
3. Name your integration and select "Public" as the type
4. Fill in required fields (company name, website, redirect URIs)
5. Under Capabilities, enable:
   - Read content
   - Update content
   - Insert content
   - Read user information (optional, for user info)
6. Submit the integration
7. Copy the OAuth client ID and OAuth client secret from the Configuration tab
8. Set redirect URI to your AGiXT APP_URI + /v1/oauth2/notion/callback

The OAuth flow grants access only to pages/databases the user explicitly shares
with the integration during authorization.
"""

SCOPES = (
    []
)  # Notion doesn't use traditional scopes; permissions are set in integration settings
AUTHORIZE = "https://api.notion.com/v1/oauth/authorize"
TOKEN_URL = "https://api.notion.com/v1/oauth/token"
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = True
NOTION_API_VERSION = "2022-06-28"


class NotionSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("NOTION_CLIENT_ID")
        self.client_secret = getenv("NOTION_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refreshes the Notion access token using the refresh token."""
        if not self.refresh_token:
            raise HTTPException(
                status_code=400,
                detail="No refresh token available for Notion.",
            )

        encoded = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        try:
            response = requests.post(
                TOKEN_URL,
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
            )
            response.raise_for_status()
            data = response.json()

            if "access_token" in data:
                self.access_token = data["access_token"]
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]

            logging.info("Successfully refreshed Notion token.")
            return data
        except requests.exceptions.RequestException as e:
            logging.error(f"Error refreshing Notion token: {e}")
            raise HTTPException(
                status_code=401,
                detail=f"Failed to refresh Notion token: {str(e)}",
            )

    def get_user_info(self):
        """Gets user information from the Notion API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Notion-Version": NOTION_API_VERSION,
        }
        try:
            # Get the bot user info first
            response = requests.get(
                "https://api.notion.com/v1/users/me",
                headers=headers,
            )

            if response.status_code == 401:
                logging.info("Notion token likely expired, attempting refresh.")
                self.get_new_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                response = requests.get(
                    "https://api.notion.com/v1/users/me",
                    headers=headers,
                )

            data = response.json()

            if data.get("object") == "error":
                raise Exception(f"Notion API error: {data.get('message')}")

            # For bot users, the owner contains user info
            bot = data.get("bot", {})
            owner = bot.get("owner", {})

            if owner.get("type") == "user":
                user = owner.get("user", {})
                name = user.get("name", "")
                email = user.get("person", {}).get("email", "")
                parts = name.split() if name else [""]
                return {
                    "email": email if email else f"{data.get('id', '')}@notion.user",
                    "first_name": parts[0] if parts else "",
                    "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
                    "provider_user_id": user.get("id", data.get("id")),
                }
            else:
                # Workspace-level token
                name = data.get("name", "Notion User")
                parts = name.split() if name else [""]
                return {
                    "email": f"{data.get('id', '')}@notion.workspace",
                    "first_name": parts[0] if parts else "",
                    "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
                    "provider_user_id": data.get("id"),
                }
        except requests.exceptions.RequestException as e:
            logging.error(f"Error getting user info from Notion: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Notion: {str(e)}",
            )


def sso(code, redirect_uri=None) -> NotionSSO:
    """Handles the OAuth2 authorization code flow for Notion."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("NOTION_CLIENT_ID")
    client_secret = getenv("NOTION_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Notion Client ID or Secret not configured.")
        return None

    # Notion uses HTTP Basic Auth for token exchange
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    try:
        response = requests.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )

        data = response.json()

        if data.get("object") == "error":
            logging.error(f"Notion OAuth error: {data.get('message')}")
            return None

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token", "Not provided")

        if not access_token:
            logging.error(f"No access token in Notion OAuth response: {data}")
            return None

        logging.info("Notion token obtained successfully.")
        return NotionSSO(access_token=access_token, refresh_token=refresh_token)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error obtaining Notion access token: {e}")
        return None


class notion(Extensions):
    """
    The Notion extension for AGiXT enables comprehensive interaction with Notion workspaces.
    It supports reading and writing pages, querying and creating databases, managing blocks,
    searching content, and working with comments. Requires a Notion public integration with
    OAuth2 configured for user-level access, or an internal integration token.

    To get a Notion Integration Token (internal integration):
    1. Go to https://www.notion.so/my-integrations
    2. Click "+ New integration"
    3. Name your integration and select a workspace
    4. Click "Submit"
    5. Copy the "Internal Integration Token" (starts with secret_)

    Important: You must share pages with your integration:
    1. Open a Notion page you want to access
    2. Click "..." menu -> "Add connections"
    3. Select your integration
    """

    CATEGORY = "Productivity & Organization"
    friendly_name = "Notion"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("NOTION_ACCESS_TOKEN", None)
        self.api_version = NOTION_API_VERSION
        self.base_url = "https://api.notion.com/v1"
        self.auth = None
        self.commands = {}

        notion_client_id = getenv("NOTION_CLIENT_ID")
        notion_client_secret = getenv("NOTION_CLIENT_SECRET")

        if notion_client_id and notion_client_secret:
            self.commands = {
                # Search
                "Notion - Search": self.search,
                # Pages
                "Notion - Get Page": self.get_page,
                "Notion - Create Page": self.create_page,
                "Notion - Update Page Properties": self.update_page_properties,
                "Notion - Archive Page": self.archive_page,
                "Notion - Restore Page": self.restore_page,
                "Notion - Get Page Content": self.get_page_content,
                "Notion - Get Page Property": self.get_page_property,
                # Databases
                "Notion - List Databases": self.list_databases,
                "Notion - Get Database": self.get_database,
                "Notion - Query Database": self.query_database,
                "Notion - Create Database": self.create_database,
                "Notion - Update Database": self.update_database,
                # Blocks
                "Notion - Get Block": self.get_block,
                "Notion - Get Block Children": self.get_block_children,
                "Notion - Append Block Children": self.append_block_children,
                "Notion - Update Block": self.update_block,
                "Notion - Delete Block": self.delete_block,
                # Comments
                "Notion - Get Comments": self.get_comments,
                "Notion - Add Comment": self.add_comment,
                # Users
                "Notion - List Users": self.list_users,
                "Notion - Get User": self.get_user,
                "Notion - Get Current User": self.get_current_user,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Notion extension auth: {str(e)}")

    def _get_headers(self):
        """Returns authorization headers for Notion API requests."""
        if not self.access_token:
            raise Exception("Notion Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Notion-Version": self.api_version,
        }

    def verify_user(self):
        """Verifies the access token and refreshes it if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="notion")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("notion_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
            logging.info("Notion token verified/refreshed successfully.")
        except Exception as e:
            logging.error(f"Error verifying/refreshing Notion token: {str(e)}")
            raise Exception(f"Notion authentication error: {str(e)}")

    def _make_request(self, method, endpoint, **kwargs):
        """Make an authenticated request to the Notion API with error handling."""
        url = f"{self.base_url}/{endpoint}"
        response = requests.request(method, url, headers=self._get_headers(), **kwargs)
        data = response.json()

        if data.get("object") == "error":
            error_msg = data.get("message", "Unknown error")
            code = data.get("code", "unknown")
            status = data.get("status", response.status_code)
            return None, f"Notion API error ({code}, HTTP {status}): {error_msg}"

        return data, None

    def _paginate(self, method, endpoint, body=None, max_pages=10):
        """Handle Notion API pagination automatically."""
        results = []
        has_more = True
        start_cursor = None
        page_count = 0

        while has_more and page_count < max_pages:
            if body is None:
                body = {}
            if start_cursor:
                body["start_cursor"] = start_cursor

            if method.upper() == "GET":
                params = {}
                if start_cursor:
                    params["start_cursor"] = start_cursor
                data, error = self._make_request(method, endpoint, params=params)
            else:
                data, error = self._make_request(method, endpoint, json=body)

            if error:
                return results, error

            results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
            page_count += 1

        return results, None

    def _extract_plain_text(self, rich_text_list):
        """Extract plain text from a Notion rich_text array."""
        if not rich_text_list:
            return ""
        return "".join([rt.get("plain_text", "") for rt in rich_text_list])

    def _format_page_summary(self, page):
        """Format a Notion page object into a readable summary."""
        page_id = page.get("id", "Unknown")
        url = page.get("url", "")
        created = page.get("created_time", "")
        edited = page.get("last_edited_time", "")
        archived = page.get("archived", False)

        # Extract title from properties
        title = "Untitled"
        properties = page.get("properties", {})
        for prop_name, prop_val in properties.items():
            if prop_val.get("type") == "title":
                title_arr = prop_val.get("title", [])
                if title_arr:
                    title = self._extract_plain_text(title_arr)
                break

        icon = ""
        if page.get("icon"):
            icon_obj = page["icon"]
            if icon_obj.get("type") == "emoji":
                icon = icon_obj.get("emoji", "") + " "

        return {
            "id": page_id,
            "title": f"{icon}{title}",
            "url": url,
            "created_time": created,
            "last_edited_time": edited,
            "archived": archived,
        }

    def _format_database_summary(self, db):
        """Format a Notion database object into a readable summary."""
        db_id = db.get("id", "Unknown")
        url = db.get("url", "")
        created = db.get("created_time", "")
        edited = db.get("last_edited_time", "")

        title_arr = db.get("title", [])
        title = self._extract_plain_text(title_arr) if title_arr else "Untitled"

        description_arr = db.get("description", [])
        description = (
            self._extract_plain_text(description_arr) if description_arr else ""
        )

        # Get property names and types
        props = {}
        for prop_name, prop_val in db.get("properties", {}).items():
            props[prop_name] = prop_val.get("type", "unknown")

        icon = ""
        if db.get("icon"):
            icon_obj = db["icon"]
            if icon_obj.get("type") == "emoji":
                icon = icon_obj.get("emoji", "") + " "

        return {
            "id": db_id,
            "title": f"{icon}{title}",
            "description": description,
            "url": url,
            "created_time": created,
            "last_edited_time": edited,
            "properties": props,
        }

    def _format_block(self, block):
        """Format a Notion block into a readable representation."""
        block_type = block.get("type", "unknown")
        block_id = block.get("id", "")
        has_children = block.get("has_children", False)

        content = ""
        type_data = block.get(block_type, {})

        if block_type in [
            "paragraph",
            "heading_1",
            "heading_2",
            "heading_3",
            "bulleted_list_item",
            "numbered_list_item",
            "quote",
            "callout",
            "toggle",
        ]:
            rich_text = type_data.get("rich_text", [])
            content = self._extract_plain_text(rich_text)
        elif block_type == "to_do":
            rich_text = type_data.get("rich_text", [])
            checked = type_data.get("checked", False)
            text = self._extract_plain_text(rich_text)
            content = f"[{'x' if checked else ' '}] {text}"
        elif block_type == "code":
            rich_text = type_data.get("rich_text", [])
            language = type_data.get("language", "")
            content = f"```{language}\n{self._extract_plain_text(rich_text)}\n```"
        elif block_type == "equation":
            content = type_data.get("expression", "")
        elif block_type == "divider":
            content = "---"
        elif block_type == "table_of_contents":
            content = "[Table of Contents]"
        elif block_type == "breadcrumb":
            content = "[Breadcrumb]"
        elif block_type == "image":
            img = type_data.get("file", type_data.get("external", {}))
            content = f"[Image: {img.get('url', 'No URL')}]"
        elif block_type == "video":
            vid = type_data.get("file", type_data.get("external", {}))
            content = f"[Video: {vid.get('url', 'No URL')}]"
        elif block_type == "file":
            f = type_data.get("file", type_data.get("external", {}))
            content = f"[File: {f.get('url', 'No URL')}]"
        elif block_type == "pdf":
            pdf = type_data.get("file", type_data.get("external", {}))
            content = f"[PDF: {pdf.get('url', 'No URL')}]"
        elif block_type == "bookmark":
            content = f"[Bookmark: {type_data.get('url', 'No URL')}]"
        elif block_type == "embed":
            content = f"[Embed: {type_data.get('url', 'No URL')}]"
        elif block_type == "link_preview":
            content = f"[Link Preview: {type_data.get('url', 'No URL')}]"
        elif block_type == "link_to_page":
            linked_id = type_data.get("page_id", type_data.get("database_id", ""))
            content = f"[Link to: {linked_id}]"
        elif block_type == "child_page":
            content = f"[Child Page: {type_data.get('title', '')}]"
        elif block_type == "child_database":
            content = f"[Child Database: {type_data.get('title', '')}]"
        elif block_type == "table":
            content = f"[Table: {type_data.get('table_width', '?')} columns]"
        elif block_type == "table_row":
            cells = type_data.get("cells", [])
            row_text = " | ".join([self._extract_plain_text(cell) for cell in cells])
            content = f"| {row_text} |"
        elif block_type == "column_list":
            content = "[Column List]"
        elif block_type == "column":
            content = "[Column]"
        elif block_type == "synced_block":
            content = "[Synced Block]"
        elif block_type == "template":
            rich_text = type_data.get("rich_text", [])
            content = f"[Template: {self._extract_plain_text(rich_text)}]"
        elif block_type == "audio":
            audio = type_data.get("file", type_data.get("external", {}))
            content = f"[Audio: {audio.get('url', 'No URL')}]"

        return {
            "id": block_id,
            "type": block_type,
            "content": content,
            "has_children": has_children,
        }

    def _format_property_value(self, prop_name, prop_val):
        """Format a property value into a readable string."""
        prop_type = prop_val.get("type", "unknown")

        if prop_type == "title":
            return self._extract_plain_text(prop_val.get("title", []))
        elif prop_type == "rich_text":
            return self._extract_plain_text(prop_val.get("rich_text", []))
        elif prop_type == "number":
            return str(prop_val.get("number", ""))
        elif prop_type == "select":
            sel = prop_val.get("select")
            return sel.get("name", "") if sel else ""
        elif prop_type == "multi_select":
            items = prop_val.get("multi_select", [])
            return ", ".join([item.get("name", "") for item in items])
        elif prop_type == "status":
            status = prop_val.get("status")
            return status.get("name", "") if status else ""
        elif prop_type == "date":
            date = prop_val.get("date")
            if not date:
                return ""
            start = date.get("start", "")
            end = date.get("end", "")
            return f"{start}" + (f" to {end}" if end else "")
        elif prop_type == "people":
            people = prop_val.get("people", [])
            return ", ".join([p.get("name", p.get("id", "")) for p in people])
        elif prop_type == "files":
            files = prop_val.get("files", [])
            return ", ".join([f.get("name", "") for f in files])
        elif prop_type == "checkbox":
            return str(prop_val.get("checkbox", False))
        elif prop_type == "url":
            return prop_val.get("url", "")
        elif prop_type == "email":
            return prop_val.get("email", "")
        elif prop_type == "phone_number":
            return prop_val.get("phone_number", "")
        elif prop_type == "formula":
            formula = prop_val.get("formula", {})
            f_type = formula.get("type", "")
            return str(formula.get(f_type, ""))
        elif prop_type == "relation":
            relations = prop_val.get("relation", [])
            return ", ".join([r.get("id", "") for r in relations])
        elif prop_type == "rollup":
            rollup = prop_val.get("rollup", {})
            r_type = rollup.get("type", "")
            if r_type == "array":
                items = rollup.get("array", [])
                return str(items)
            return str(rollup.get(r_type, ""))
        elif prop_type == "created_time":
            return prop_val.get("created_time", "")
        elif prop_type == "created_by":
            user = prop_val.get("created_by", {})
            return user.get("name", user.get("id", ""))
        elif prop_type == "last_edited_time":
            return prop_val.get("last_edited_time", "")
        elif prop_type == "last_edited_by":
            user = prop_val.get("last_edited_by", {})
            return user.get("name", user.get("id", ""))
        elif prop_type == "unique_id":
            uid = prop_val.get("unique_id", {})
            prefix = uid.get("prefix", "")
            number = uid.get("number", "")
            return f"{prefix}-{number}" if prefix else str(number)
        elif prop_type == "verification":
            verification = prop_val.get("verification", {})
            return verification.get("state", "")
        else:
            return str(prop_val)

    def _build_rich_text(self, text):
        """Build a Notion rich_text array from plain text."""
        if not text:
            return []
        return [{"type": "text", "text": {"content": text}}]

    def _text_to_blocks(self, text):
        """Convert plain text into Notion block objects (paragraphs)."""
        if not text:
            return []

        blocks = []
        lines = text.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Headings
            if line.startswith("### "):
                blocks.append(
                    {
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {"rich_text": self._build_rich_text(line[4:])},
                    }
                )
            elif line.startswith("## "):
                blocks.append(
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": self._build_rich_text(line[3:])},
                    }
                )
            elif line.startswith("# "):
                blocks.append(
                    {
                        "object": "block",
                        "type": "heading_1",
                        "heading_1": {"rich_text": self._build_rich_text(line[2:])},
                    }
                )
            # To-do items
            elif line.startswith("- [x] ") or line.startswith("- [X] "):
                blocks.append(
                    {
                        "object": "block",
                        "type": "to_do",
                        "to_do": {
                            "rich_text": self._build_rich_text(line[6:]),
                            "checked": True,
                        },
                    }
                )
            elif line.startswith("- [ ] "):
                blocks.append(
                    {
                        "object": "block",
                        "type": "to_do",
                        "to_do": {
                            "rich_text": self._build_rich_text(line[6:]),
                            "checked": False,
                        },
                    }
                )
            # Bulleted list
            elif line.startswith("- ") or line.startswith("* "):
                blocks.append(
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": self._build_rich_text(line[2:])
                        },
                    }
                )
            # Numbered list
            elif len(line) > 2 and line[0].isdigit() and ". " in line[:5]:
                idx = line.index(". ")
                blocks.append(
                    {
                        "object": "block",
                        "type": "numbered_list_item",
                        "numbered_list_item": {
                            "rich_text": self._build_rich_text(line[idx + 2 :])
                        },
                    }
                )
            # Blockquote
            elif line.startswith("> "):
                blocks.append(
                    {
                        "object": "block",
                        "type": "quote",
                        "quote": {"rich_text": self._build_rich_text(line[2:])},
                    }
                )
            # Horizontal rule
            elif line.strip() in ("---", "***", "___"):
                blocks.append(
                    {
                        "object": "block",
                        "type": "divider",
                        "divider": {},
                    }
                )
            # Code block
            elif line.startswith("```"):
                language = line[3:].strip() or "plain text"
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                blocks.append(
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": self._build_rich_text("\n".join(code_lines)),
                            "language": language,
                        },
                    }
                )
            # Empty line
            elif line.strip() == "":
                blocks.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": []},
                    }
                )
            # Regular paragraph
            else:
                blocks.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": self._build_rich_text(line)},
                    }
                )

            i += 1

        return blocks

    # ─────────────────────────── SEARCH ───────────────────────────

    async def search(
        self,
        query: str,
        filter_type: str = "",
        sort_direction: str = "descending",
        page_size: int = 20,
    ):
        """
        Search across all pages and databases shared with the integration.

        Args:
            query (str): The search query text.
            filter_type (str): Filter by object type - "page", "database", or empty for both.
            sort_direction (str): Sort by last edited time - "ascending" or "descending". Default "descending".
            page_size (int): Number of results to return (1-100). Default 20.

        Returns:
            str: JSON formatted search results.
        """
        try:
            self.verify_user()
            body = {
                "query": query,
                "page_size": min(max(page_size, 1), 100),
            }

            if filter_type in ("page", "database"):
                body["filter"] = {"value": filter_type, "property": "object"}

            if sort_direction in ("ascending", "descending"):
                body["sort"] = {
                    "direction": sort_direction,
                    "timestamp": "last_edited_time",
                }

            data, error = self._make_request("POST", "search", json=body)
            if error:
                return f"Error searching Notion: {error}"

            results = data.get("results", [])
            formatted = []
            for item in results:
                if item.get("object") == "page":
                    formatted.append(self._format_page_summary(item))
                elif item.get("object") == "database":
                    formatted.append(self._format_database_summary(item))

            return json.dumps(
                {
                    "total_results": len(formatted),
                    "has_more": data.get("has_more", False),
                    "results": formatted,
                },
                indent=2,
            )
        except Exception as e:
            logging.error(f"Error searching Notion: {str(e)}")
            return f"Error searching Notion: {str(e)}"

    # ─────────────────────────── PAGES ───────────────────────────

    async def get_page(self, page_id: str):
        """
        Retrieve a Notion page by its ID.

        Args:
            page_id (str): The ID of the Notion page to retrieve.

        Returns:
            str: JSON formatted page information including properties.
        """
        try:
            self.verify_user()
            data, error = self._make_request("GET", f"pages/{page_id}")
            if error:
                return f"Error getting page: {error}"

            summary = self._format_page_summary(data)

            # Add formatted properties
            properties = {}
            for prop_name, prop_val in data.get("properties", {}).items():
                properties[prop_name] = self._format_property_value(prop_name, prop_val)

            summary["properties"] = properties
            return json.dumps(summary, indent=2)
        except Exception as e:
            logging.error(f"Error getting Notion page: {str(e)}")
            return f"Error getting page: {str(e)}"

    async def create_page(
        self,
        title: str,
        content: str = "",
        parent_page_id: str = "",
        parent_database_id: str = "",
        icon_emoji: str = "",
        properties_json: str = "",
    ):
        """
        Create a new Notion page under a parent page or database.

        Args:
            title (str): The title of the new page.
            content (str): The body content in markdown-like format. Supports headings (#, ##, ###), bullet lists (- ), numbered lists (1. ), to-dos (- [ ], - [x]), blockquotes (> ), code blocks (```), and horizontal rules (---).
            parent_page_id (str): The ID of the parent page. Either this or parent_database_id is required.
            parent_database_id (str): The ID of the parent database. Either this or parent_page_id is required.
            icon_emoji (str): Optional emoji to use as the page icon (e.g., "📝").
            properties_json (str): Optional JSON string of additional database properties to set when creating under a database. Example: {"Status": {"status": {"name": "In Progress"}}, "Priority": {"select": {"name": "High"}}}

        Returns:
            str: JSON formatted created page information.
        """
        try:
            self.verify_user()

            body = {}

            # Set parent
            if parent_database_id:
                body["parent"] = {"database_id": parent_database_id}
                # For database pages, title goes in properties
                body["properties"] = {
                    "Name": {"title": self._build_rich_text(title)},
                }
                # Merge additional properties
                if properties_json:
                    try:
                        extra_props = json.loads(properties_json)
                        body["properties"].update(extra_props)
                    except json.JSONDecodeError:
                        logging.warning(f"Invalid properties_json: {properties_json}")
            elif parent_page_id:
                body["parent"] = {"page_id": parent_page_id}
                body["properties"] = {
                    "title": {"title": self._build_rich_text(title)},
                }
            else:
                return "Error: Either parent_page_id or parent_database_id is required."

            # Set icon
            if icon_emoji:
                body["icon"] = {"type": "emoji", "emoji": icon_emoji}

            # Convert content to blocks
            if content:
                blocks = self._text_to_blocks(content)
                if blocks:
                    body["children"] = blocks[:100]  # Notion limit

            data, error = self._make_request("POST", "pages", json=body)
            if error:
                return f"Error creating page: {error}"

            summary = self._format_page_summary(data)
            return json.dumps(
                {
                    "success": True,
                    "message": "Page created successfully",
                    "page": summary,
                },
                indent=2,
            )
        except Exception as e:
            logging.error(f"Error creating Notion page: {str(e)}")
            return f"Error creating page: {str(e)}"

    async def update_page_properties(self, page_id: str, properties_json: str):
        """
        Update properties of an existing Notion page.

        Args:
            page_id (str): The ID of the page to update.
            properties_json (str): JSON string of properties to update. Format depends on property type. Examples: {"Name": {"title": [{"text": {"content": "New Title"}}]}} or {"Status": {"status": {"name": "Done"}}} or {"Priority": {"select": {"name": "High"}}}

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()

            try:
                properties = json.loads(properties_json)
            except json.JSONDecodeError:
                return "Error: Invalid JSON in properties_json."

            body = {"properties": properties}

            data, error = self._make_request("PATCH", f"pages/{page_id}", json=body)
            if error:
                return f"Error updating page properties: {error}"

            summary = self._format_page_summary(data)
            return json.dumps(
                {
                    "success": True,
                    "message": "Page properties updated successfully",
                    "page": summary,
                },
                indent=2,
            )
        except Exception as e:
            logging.error(f"Error updating Notion page: {str(e)}")
            return f"Error updating page properties: {str(e)}"

    async def archive_page(self, page_id: str):
        """
        Archive (soft-delete) a Notion page.

        Args:
            page_id (str): The ID of the page to archive.

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            body = {"archived": True}
            data, error = self._make_request("PATCH", f"pages/{page_id}", json=body)
            if error:
                return f"Error archiving page: {error}"

            return f"Page {page_id} archived successfully."
        except Exception as e:
            logging.error(f"Error archiving Notion page: {str(e)}")
            return f"Error archiving page: {str(e)}"

    async def restore_page(self, page_id: str):
        """
        Restore a previously archived Notion page.

        Args:
            page_id (str): The ID of the page to restore.

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            body = {"archived": False}
            data, error = self._make_request("PATCH", f"pages/{page_id}", json=body)
            if error:
                return f"Error restoring page: {error}"

            return f"Page {page_id} restored successfully."
        except Exception as e:
            logging.error(f"Error restoring Notion page: {str(e)}")
            return f"Error restoring page: {str(e)}"

    async def get_page_content(self, page_id: str, max_depth: int = 2):
        """
        Get the full content of a Notion page by retrieving all its blocks recursively.

        Args:
            page_id (str): The ID of the Notion page.
            max_depth (int): Maximum depth to retrieve nested blocks. Default 2.

        Returns:
            str: The page content formatted as readable text.
        """
        try:
            self.verify_user()

            def _get_children(block_id, depth=0):
                blocks, error = self._paginate("GET", f"blocks/{block_id}/children")
                if error:
                    return [f"[Error loading children: {error}]"]

                content_parts = []
                indent = "  " * depth

                for block in blocks:
                    formatted = self._format_block(block)
                    block_type = formatted["type"]
                    text = formatted["content"]

                    # Add appropriate prefix based on type
                    if block_type == "heading_1":
                        content_parts.append(f"\n# {text}")
                    elif block_type == "heading_2":
                        content_parts.append(f"\n## {text}")
                    elif block_type == "heading_3":
                        content_parts.append(f"\n### {text}")
                    elif block_type == "bulleted_list_item":
                        content_parts.append(f"{indent}- {text}")
                    elif block_type == "numbered_list_item":
                        content_parts.append(f"{indent}1. {text}")
                    elif block_type == "to_do":
                        content_parts.append(f"{indent}{text}")
                    elif block_type == "code":
                        content_parts.append(f"\n{text}\n")
                    elif block_type == "divider":
                        content_parts.append(f"\n{text}\n")
                    elif block_type == "quote":
                        content_parts.append(f"{indent}> {text}")
                    elif text:
                        content_parts.append(f"{indent}{text}")

                    # Recursively get children
                    if formatted["has_children"] and depth < max_depth:
                        children_content = _get_children(block["id"], depth + 1)
                        content_parts.extend(children_content)

                return content_parts

            # Get page info first
            page_data, page_error = self._make_request("GET", f"pages/{page_id}")
            if page_error:
                return f"Error getting page: {page_error}"

            page_summary = self._format_page_summary(page_data)

            # Get content
            content_parts = _get_children(page_id)
            content_text = "\n".join(content_parts)

            result = f"# {page_summary['title']}\n"
            result += f"URL: {page_summary['url']}\n"
            result += f"Last edited: {page_summary['last_edited_time']}\n"
            result += f"\n{content_text}"

            return result
        except Exception as e:
            logging.error(f"Error getting Notion page content: {str(e)}")
            return f"Error getting page content: {str(e)}"

    async def get_page_property(self, page_id: str, property_id: str):
        """
        Get a specific property value from a Notion page. Useful for paginated properties
        like relations and rollups.

        Args:
            page_id (str): The ID of the page.
            property_id (str): The ID of the property to retrieve.

        Returns:
            str: The property value.
        """
        try:
            self.verify_user()
            data, error = self._make_request(
                "GET", f"pages/{page_id}/properties/{property_id}"
            )
            if error:
                return f"Error getting property: {error}"

            return json.dumps(data, indent=2)
        except Exception as e:
            logging.error(f"Error getting Notion page property: {str(e)}")
            return f"Error getting page property: {str(e)}"

    # ─────────────────────────── DATABASES ───────────────────────────

    async def list_databases(self):
        """
        List all databases shared with the integration.

        Returns:
            str: JSON formatted list of databases with their properties schema.
        """
        try:
            self.verify_user()
            body = {
                "filter": {"value": "database", "property": "object"},
                "page_size": 100,
            }
            data, error = self._make_request("POST", "search", json=body)
            if error:
                return f"Error listing databases: {error}"

            results = data.get("results", [])
            formatted = [self._format_database_summary(db) for db in results]

            return json.dumps(
                {"total": len(formatted), "databases": formatted}, indent=2
            )
        except Exception as e:
            logging.error(f"Error listing Notion databases: {str(e)}")
            return f"Error listing databases: {str(e)}"

    async def get_database(self, database_id: str):
        """
        Get the schema and details of a specific Notion database.

        Args:
            database_id (str): The ID of the database.

        Returns:
            str: JSON formatted database information including all property definitions.
        """
        try:
            self.verify_user()
            data, error = self._make_request("GET", f"databases/{database_id}")
            if error:
                return f"Error getting database: {error}"

            summary = self._format_database_summary(data)

            # Include full property definitions for schema inspection
            full_properties = {}
            for pname, pval in data.get("properties", {}).items():
                full_properties[pname] = {
                    "id": pval.get("id", ""),
                    "type": pval.get("type", ""),
                    "name": pname,
                }
                ptype = pval.get("type", "")
                if ptype == "select":
                    options = pval.get("select", {}).get("options", [])
                    full_properties[pname]["options"] = [
                        {"name": o.get("name"), "color": o.get("color")}
                        for o in options
                    ]
                elif ptype == "multi_select":
                    options = pval.get("multi_select", {}).get("options", [])
                    full_properties[pname]["options"] = [
                        {"name": o.get("name"), "color": o.get("color")}
                        for o in options
                    ]
                elif ptype == "status":
                    options = pval.get("status", {}).get("options", [])
                    groups = pval.get("status", {}).get("groups", [])
                    full_properties[pname]["options"] = [
                        {"name": o.get("name"), "color": o.get("color")}
                        for o in options
                    ]
                    full_properties[pname]["groups"] = [
                        {"name": g.get("name"), "color": g.get("color")} for g in groups
                    ]
                elif ptype == "relation":
                    rel = pval.get("relation", {})
                    full_properties[pname]["database_id"] = rel.get("database_id", "")
                    full_properties[pname]["synced_property_name"] = rel.get(
                        "synced_property_name", ""
                    )
                elif ptype == "formula":
                    full_properties[pname]["expression"] = pval.get("formula", {}).get(
                        "expression", ""
                    )
                elif ptype == "rollup":
                    rollup = pval.get("rollup", {})
                    full_properties[pname]["relation_property_name"] = rollup.get(
                        "relation_property_name", ""
                    )
                    full_properties[pname]["rollup_property_name"] = rollup.get(
                        "rollup_property_name", ""
                    )
                    full_properties[pname]["function"] = rollup.get("function", "")
                elif ptype == "number":
                    full_properties[pname]["format"] = pval.get("number", {}).get(
                        "format", ""
                    )

            summary["property_definitions"] = full_properties
            return json.dumps(summary, indent=2)
        except Exception as e:
            logging.error(f"Error getting Notion database: {str(e)}")
            return f"Error getting database: {str(e)}"

    async def query_database(
        self,
        database_id: str,
        filter_json: str = "",
        sorts_json: str = "",
        page_size: int = 50,
    ):
        """
        Query a Notion database to get its entries (pages), with optional filtering and sorting.

        Args:
            database_id (str): The ID of the database to query.
            filter_json (str): Optional JSON filter. Example for checkbox: {"property": "Done", "checkbox": {"equals": true}}. Example for compound filter: {"and": [{"property": "Status", "status": {"equals": "In Progress"}}, {"property": "Priority", "select": {"equals": "High"}}]}
            sorts_json (str): Optional JSON array of sorts. Example: [{"property": "Created", "direction": "descending"}] or [{"timestamp": "last_edited_time", "direction": "ascending"}]
            page_size (int): Number of results per page (1-100). Default 50.

        Returns:
            str: JSON formatted list of database entries with their property values.
        """
        try:
            self.verify_user()
            body = {"page_size": min(max(page_size, 1), 100)}

            if filter_json:
                try:
                    body["filter"] = json.loads(filter_json)
                except json.JSONDecodeError:
                    return "Error: Invalid JSON in filter_json."

            if sorts_json:
                try:
                    body["sorts"] = json.loads(sorts_json)
                except json.JSONDecodeError:
                    return "Error: Invalid JSON in sorts_json."

            data, error = self._make_request(
                "POST", f"databases/{database_id}/query", json=body
            )
            if error:
                return f"Error querying database: {error}"

            results = data.get("results", [])
            formatted_entries = []

            for page in results:
                entry = self._format_page_summary(page)
                # Add all formatted property values
                props = {}
                for pname, pval in page.get("properties", {}).items():
                    props[pname] = self._format_property_value(pname, pval)
                entry["properties"] = props
                formatted_entries.append(entry)

            return json.dumps(
                {
                    "total_results": len(formatted_entries),
                    "has_more": data.get("has_more", False),
                    "next_cursor": data.get("next_cursor"),
                    "entries": formatted_entries,
                },
                indent=2,
            )
        except Exception as e:
            logging.error(f"Error querying Notion database: {str(e)}")
            return f"Error querying database: {str(e)}"

    async def create_database(
        self,
        parent_page_id: str,
        title: str,
        properties_json: str,
        icon_emoji: str = "",
        description: str = "",
    ):
        """
        Create a new database as a child of a page.

        Args:
            parent_page_id (str): The ID of the parent page to create the database under.
            title (str): The title of the database.
            properties_json (str): JSON string defining the database properties schema. Example: {"Name": {"title": {}}, "Status": {"select": {"options": [{"name": "Not Started", "color": "red"}, {"name": "In Progress", "color": "yellow"}, {"name": "Done", "color": "green"}]}}, "Due Date": {"date": {}}, "Tags": {"multi_select": {"options": [{"name": "Bug", "color": "red"}, {"name": "Feature", "color": "blue"}]}}, "Assignee": {"people": {}}, "Priority": {"select": {"options": [{"name": "High", "color": "red"}, {"name": "Medium", "color": "yellow"}, {"name": "Low", "color": "green"}]}}}
            icon_emoji (str): Optional emoji for the database icon.
            description (str): Optional description for the database.

        Returns:
            str: JSON formatted created database information.
        """
        try:
            self.verify_user()

            try:
                properties = json.loads(properties_json)
            except json.JSONDecodeError:
                return "Error: Invalid JSON in properties_json."

            # Ensure there's a title property
            has_title = any(
                "title" in v for v in properties.values() if isinstance(v, dict)
            )
            if not has_title:
                properties["Name"] = {"title": {}}

            body = {
                "parent": {"type": "page_id", "page_id": parent_page_id},
                "title": self._build_rich_text(title),
                "properties": properties,
            }

            if icon_emoji:
                body["icon"] = {"type": "emoji", "emoji": icon_emoji}

            if description:
                body["description"] = self._build_rich_text(description)

            data, error = self._make_request("POST", "databases", json=body)
            if error:
                return f"Error creating database: {error}"

            summary = self._format_database_summary(data)
            return json.dumps(
                {
                    "success": True,
                    "message": "Database created successfully",
                    "database": summary,
                },
                indent=2,
            )
        except Exception as e:
            logging.error(f"Error creating Notion database: {str(e)}")
            return f"Error creating database: {str(e)}"

    async def update_database(
        self,
        database_id: str,
        title: str = "",
        description: str = "",
        properties_json: str = "",
    ):
        """
        Update a database's title, description, or properties schema.

        Args:
            database_id (str): The ID of the database to update.
            title (str): New title for the database (optional).
            description (str): New description (optional).
            properties_json (str): JSON string of property schema modifications to apply. To add a new property: {"New Column": {"number": {"format": "dollar"}}}. To rename: {"old_name": {"name": "new_name"}}. To remove: {"Column Name": null}.

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()

            body = {}

            if title:
                body["title"] = self._build_rich_text(title)

            if description:
                body["description"] = self._build_rich_text(description)

            if properties_json:
                try:
                    body["properties"] = json.loads(properties_json)
                except json.JSONDecodeError:
                    return "Error: Invalid JSON in properties_json."

            if not body:
                return "Error: No updates provided. Specify title, description, or properties_json."

            data, error = self._make_request(
                "PATCH", f"databases/{database_id}", json=body
            )
            if error:
                return f"Error updating database: {error}"

            summary = self._format_database_summary(data)
            return json.dumps(
                {
                    "success": True,
                    "message": "Database updated successfully",
                    "database": summary,
                },
                indent=2,
            )
        except Exception as e:
            logging.error(f"Error updating Notion database: {str(e)}")
            return f"Error updating database: {str(e)}"

    # ─────────────────────────── BLOCKS ───────────────────────────

    async def get_block(self, block_id: str):
        """
        Retrieve a specific block by its ID.

        Args:
            block_id (str): The ID of the block to retrieve.

        Returns:
            str: JSON formatted block information.
        """
        try:
            self.verify_user()
            data, error = self._make_request("GET", f"blocks/{block_id}")
            if error:
                return f"Error getting block: {error}"

            formatted = self._format_block(data)
            return json.dumps(formatted, indent=2)
        except Exception as e:
            logging.error(f"Error getting Notion block: {str(e)}")
            return f"Error getting block: {str(e)}"

    async def get_block_children(self, block_id: str, page_size: int = 100):
        """
        Get the children blocks of a specific block or page.

        Args:
            block_id (str): The ID of the parent block or page.
            page_size (int): Number of children to return (1-100). Default 100.

        Returns:
            str: JSON formatted list of child blocks.
        """
        try:
            self.verify_user()
            blocks, error = self._paginate("GET", f"blocks/{block_id}/children")
            if error:
                return f"Error getting block children: {error}"

            formatted = [self._format_block(b) for b in blocks]
            return json.dumps({"total": len(formatted), "blocks": formatted}, indent=2)
        except Exception as e:
            logging.error(f"Error getting Notion block children: {str(e)}")
            return f"Error getting block children: {str(e)}"

    async def append_block_children(self, block_id: str, content: str):
        """
        Append new content blocks as children of a block or page. Use this to add
        content to an existing page.

        Args:
            block_id (str): The ID of the parent block or page to add content to.
            content (str): The content to append in markdown-like format. Supports headings (#, ##, ###), bullet lists (- ), numbered lists (1. ), to-dos (- [ ], - [x]), blockquotes (> ), code blocks (```), and horizontal rules (---).

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()

            blocks = self._text_to_blocks(content)
            if not blocks:
                return "Error: No content to append."

            # Notion allows max 100 blocks per request
            total_appended = 0
            for i in range(0, len(blocks), 100):
                chunk = blocks[i : i + 100]
                body = {"children": chunk}
                data, error = self._make_request(
                    "PATCH", f"blocks/{block_id}/children", json=body
                )
                if error:
                    return f"Error appending blocks (batch {i // 100 + 1}): {error}"
                total_appended += len(chunk)

            return f"Successfully appended {total_appended} blocks to {block_id}."
        except Exception as e:
            logging.error(f"Error appending Notion blocks: {str(e)}")
            return f"Error appending blocks: {str(e)}"

    async def update_block(self, block_id: str, content: str, block_type: str = ""):
        """
        Update the content of an existing block.

        Args:
            block_id (str): The ID of the block to update.
            content (str): The new text content for the block.
            block_type (str): The type of block (e.g., "paragraph", "heading_1", "to_do", "bulleted_list_item", etc.). If empty, will attempt to detect from existing block.

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()

            # If no block_type, fetch current block to detect type
            if not block_type:
                existing, error = self._make_request("GET", f"blocks/{block_id}")
                if error:
                    return f"Error getting block for update: {error}"
                block_type = existing.get("type", "paragraph")

            body = {}

            if block_type in [
                "paragraph",
                "heading_1",
                "heading_2",
                "heading_3",
                "bulleted_list_item",
                "numbered_list_item",
                "quote",
                "callout",
                "toggle",
            ]:
                body[block_type] = {"rich_text": self._build_rich_text(content)}
            elif block_type == "to_do":
                # Parse checkbox state from content
                checked = content.startswith("[x]") or content.startswith("[X]")
                text = content
                if text.startswith("[x] ") or text.startswith("[X] "):
                    text = text[4:]
                elif text.startswith("[ ] "):
                    text = text[4:]
                body["to_do"] = {
                    "rich_text": self._build_rich_text(text),
                    "checked": checked,
                }
            elif block_type == "code":
                body["code"] = {
                    "rich_text": self._build_rich_text(content),
                }
            elif block_type == "equation":
                body["equation"] = {"expression": content}
            elif block_type == "bookmark":
                body["bookmark"] = {"url": content}
            elif block_type == "embed":
                body["embed"] = {"url": content}
            else:
                return f"Error: Unsupported block type '{block_type}' for update."

            data, error = self._make_request("PATCH", f"blocks/{block_id}", json=body)
            if error:
                return f"Error updating block: {error}"

            return f"Block {block_id} updated successfully."
        except Exception as e:
            logging.error(f"Error updating Notion block: {str(e)}")
            return f"Error updating block: {str(e)}"

    async def delete_block(self, block_id: str):
        """
        Delete (archive) a block from a page.

        Args:
            block_id (str): The ID of the block to delete.

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            data, error = self._make_request("DELETE", f"blocks/{block_id}")
            if error:
                return f"Error deleting block: {error}"

            return f"Block {block_id} deleted successfully."
        except Exception as e:
            logging.error(f"Error deleting Notion block: {str(e)}")
            return f"Error deleting block: {str(e)}"

    # ─────────────────────────── COMMENTS ───────────────────────────

    async def get_comments(self, block_id: str = "", page_id: str = ""):
        """
        Retrieve comments from a page or a specific discussion thread on a block.

        Args:
            block_id (str): The ID of the block to get discussion comments from. Either block_id or page_id is required.
            page_id (str): The ID of the page to get all comments from. Either block_id or page_id is required.

        Returns:
            str: JSON formatted list of comments.
        """
        try:
            self.verify_user()

            target_id = block_id or page_id
            if not target_id:
                return "Error: Either block_id or page_id is required."

            params = {"block_id": target_id}
            data, error = self._make_request("GET", "comments", params=params)
            if error:
                return f"Error getting comments: {error}"

            comments = []
            for comment in data.get("results", []):
                rich_text = comment.get("rich_text", [])
                comments.append(
                    {
                        "id": comment.get("id", ""),
                        "created_time": comment.get("created_time", ""),
                        "created_by": comment.get("created_by", {}).get("id", ""),
                        "text": self._extract_plain_text(rich_text),
                        "discussion_id": comment.get("discussion_id", ""),
                    }
                )

            return json.dumps({"total": len(comments), "comments": comments}, indent=2)
        except Exception as e:
            logging.error(f"Error getting Notion comments: {str(e)}")
            return f"Error getting comments: {str(e)}"

    async def add_comment(self, text: str, page_id: str = "", discussion_id: str = ""):
        """
        Add a comment to a page or reply to an existing discussion thread.

        Args:
            text (str): The comment text.
            page_id (str): The ID of the page to comment on. Use this for top-level page comments. Either page_id or discussion_id is required.
            discussion_id (str): The ID of the discussion thread to reply to. Use this to reply to existing comments. Either page_id or discussion_id is required.

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()

            body = {"rich_text": self._build_rich_text(text)}

            if discussion_id:
                body["discussion_id"] = discussion_id
            elif page_id:
                body["parent"] = {"page_id": page_id}
            else:
                return "Error: Either page_id or discussion_id is required."

            data, error = self._make_request("POST", "comments", json=body)
            if error:
                return f"Error adding comment: {error}"

            return json.dumps(
                {
                    "success": True,
                    "comment_id": data.get("id", ""),
                    "message": "Comment added successfully",
                },
                indent=2,
            )
        except Exception as e:
            logging.error(f"Error adding Notion comment: {str(e)}")
            return f"Error adding comment: {str(e)}"

    # ─────────────────────────── USERS ───────────────────────────

    async def list_users(self):
        """
        List all users in the Notion workspace that the integration can see.

        Returns:
            str: JSON formatted list of users.
        """
        try:
            self.verify_user()
            users, error = self._paginate("GET", "users")
            if error:
                return f"Error listing users: {error}"

            formatted = []
            for user in users:
                formatted.append(
                    {
                        "id": user.get("id", ""),
                        "type": user.get("type", ""),
                        "name": user.get("name", ""),
                        "avatar_url": user.get("avatar_url", ""),
                        "email": (
                            user.get("person", {}).get("email", "")
                            if user.get("type") == "person"
                            else ""
                        ),
                    }
                )

            return json.dumps({"total": len(formatted), "users": formatted}, indent=2)
        except Exception as e:
            logging.error(f"Error listing Notion users: {str(e)}")
            return f"Error listing users: {str(e)}"

    async def get_user(self, user_id: str):
        """
        Get information about a specific Notion user.

        Args:
            user_id (str): The ID of the user.

        Returns:
            str: JSON formatted user information.
        """
        try:
            self.verify_user()
            data, error = self._make_request("GET", f"users/{user_id}")
            if error:
                return f"Error getting user: {error}"

            return json.dumps(
                {
                    "id": data.get("id", ""),
                    "type": data.get("type", ""),
                    "name": data.get("name", ""),
                    "avatar_url": data.get("avatar_url", ""),
                    "email": (
                        data.get("person", {}).get("email", "")
                        if data.get("type") == "person"
                        else ""
                    ),
                },
                indent=2,
            )
        except Exception as e:
            logging.error(f"Error getting Notion user: {str(e)}")
            return f"Error getting user: {str(e)}"

    async def get_current_user(self):
        """
        Get information about the current bot user (the integration itself).

        Returns:
            str: JSON formatted bot user information including workspace details.
        """
        try:
            self.verify_user()
            data, error = self._make_request("GET", "users/me")
            if error:
                return f"Error getting current user: {error}"

            result = {
                "id": data.get("id", ""),
                "type": data.get("type", ""),
                "name": data.get("name", ""),
                "avatar_url": data.get("avatar_url", ""),
            }

            bot = data.get("bot", {})
            if bot:
                owner = bot.get("owner", {})
                result["owner_type"] = owner.get("type", "")
                if owner.get("type") == "user":
                    user = owner.get("user", {})
                    result["owner_name"] = user.get("name", "")
                    result["owner_email"] = user.get("person", {}).get("email", "")
                result["workspace_name"] = bot.get("workspace_name", "")

            return json.dumps(result, indent=2)
        except Exception as e:
            logging.error(f"Error getting Notion current user: {str(e)}")
            return f"Error getting current user: {str(e)}"
