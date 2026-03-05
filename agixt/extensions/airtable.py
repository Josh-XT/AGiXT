import logging
import json
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
Airtable Extension for AGiXT

This extension enables interaction with Airtable bases, tables, and records
via the Airtable REST API.

Required environment variables:

- AIRTABLE_CLIENT_ID: Airtable OAuth integration client ID
- AIRTABLE_CLIENT_SECRET: Airtable OAuth integration client secret

How to set up an Airtable OAuth integration:

1. Go to https://airtable.com/create/oauth
2. Click "Register a new OAuth integration"
3. Fill in the integration name and description
4. Set redirect URI to your AGiXT APP_URI + /v1/oauth2/airtable/callback
5. Under Scopes, enable:
   - data.records:read
   - data.records:write
   - schema.bases:read
   - schema.bases:write
6. Copy the Client ID and Client Secret
7. Set them as environment variables

Alternatively, use a Personal Access Token from https://airtable.com/create/tokens
"""

SCOPES = [
    "data.records:read",
    "data.records:write",
    "schema.bases:read",
    "schema.bases:write",
]
AUTHORIZE = "https://airtable.com/oauth2/v1/authorize"
TOKEN_URL = "https://airtable.com/oauth2/v1/token"
PKCE_REQUIRED = True
SSO_ONLY = False
LOGIN_CAPABLE = False


class AirtableSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("AIRTABLE_CLIENT_ID")
        self.client_secret = getenv("AIRTABLE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refreshes the Airtable access token using the refresh token."""
        if not self.refresh_token:
            raise HTTPException(
                status_code=400, detail="No refresh token available for Airtable."
            )

        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=(self.client_id, self.client_secret),
            )
            response.raise_for_status()
            data = response.json()

            if "access_token" in data:
                self.access_token = data["access_token"]
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]

            return data
        except Exception as e:
            logging.error(f"Error refreshing Airtable token: {e}")
            raise HTTPException(
                status_code=401, detail=f"Failed to refresh Airtable token: {str(e)}"
            )

    def get_user_info(self):
        """Gets user information from the Airtable API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        try:
            response = requests.get(
                "https://api.airtable.com/v0/meta/whoami",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

            if response.status_code == 401:
                self.get_new_token()
                response = requests.get(
                    "https://api.airtable.com/v0/meta/whoami",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )

            data = response.json()

            return {
                "email": data.get("email", f"{data.get('id', '')}@airtable.user"),
                "first_name": data.get("id", "Airtable"),
                "last_name": "User",
                "provider_user_id": data.get("id", ""),
            }
        except Exception as e:
            logging.error(f"Error getting Airtable user info: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Airtable: {str(e)}",
            )


def sso(code, redirect_uri=None) -> AirtableSSO:
    """Handles the OAuth2 authorization code flow for Airtable."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("AIRTABLE_CLIENT_ID")
    client_secret = getenv("AIRTABLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Airtable Client ID or Secret not configured.")
        return None

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(client_id, client_secret),
        )
        data = response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not access_token:
            logging.error(f"No access token in Airtable OAuth response: {data}")
            return None

        return AirtableSSO(access_token=access_token, refresh_token=refresh_token)
    except Exception as e:
        logging.error(f"Error obtaining Airtable access token: {e}")
        return None


class airtable(Extensions):
    """
    The Airtable extension for AGiXT enables interaction with Airtable bases, tables,
    and records. It supports listing bases, creating/reading/updating/deleting records,
    searching tables, and managing table schemas.

    Requires an Airtable OAuth integration or Personal Access Token.

    To set up:
    1. Register an OAuth integration at https://airtable.com/create/oauth
    2. Set AIRTABLE_CLIENT_ID and AIRTABLE_CLIENT_SECRET environment variables
    3. Connect your Airtable account through AGiXT OAuth flow
    """

    CATEGORY = "Productivity & Organization"
    friendly_name = "Airtable"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("AIRTABLE_ACCESS_TOKEN", None)
        self.base_url = "https://api.airtable.com/v0"
        self.meta_url = "https://api.airtable.com/v0/meta"
        self.auth = None
        self.commands = {}

        airtable_client_id = getenv("AIRTABLE_CLIENT_ID")
        airtable_client_secret = getenv("AIRTABLE_CLIENT_SECRET")

        if airtable_client_id and airtable_client_secret:
            self.commands = {
                "Airtable - List Bases": self.list_bases,
                "Airtable - Get Base Schema": self.get_base_schema,
                "Airtable - List Records": self.list_records,
                "Airtable - Get Record": self.get_record,
                "Airtable - Create Record": self.create_record,
                "Airtable - Update Record": self.update_record,
                "Airtable - Delete Record": self.delete_record,
                "Airtable - Search Records": self.search_records,
                "Airtable - Create Table": self.create_table,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Airtable extension auth: {str(e)}")

    def _get_headers(self):
        """Returns authorization headers for Airtable API requests."""
        if not self.access_token:
            raise Exception("Airtable Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def verify_user(self):
        """Verifies the access token and refreshes if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="airtable")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("airtable_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
        except Exception as e:
            logging.error(f"Error verifying Airtable token: {str(e)}")
            raise Exception(f"Airtable authentication error: {str(e)}")

    async def list_bases(self):
        """
        List all bases (workspaces) accessible by the authenticated user.

        Returns:
            str: Formatted list of bases or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.meta_url}/bases",
                headers=self._get_headers(),
            )
            data = response.json()
            bases = data.get("bases", [])

            if not bases:
                return "No bases found."

            result = "**Your Airtable Bases:**\n\n"
            for base in bases:
                result += f"- **{base.get('name', '')}** (ID: `{base.get('id', '')}`)\n"
                permission = base.get("permissionLevel", "")
                if permission:
                    result += f"  Permission: {permission}\n"

            return result
        except Exception as e:
            return f"Error listing bases: {str(e)}"

    async def get_base_schema(self, base_id: str):
        """
        Get the schema (tables and fields) of a base.

        Args:
            base_id (str): The base ID (e.g., 'appXXXXXXXXXXXXXX').

        Returns:
            str: Base schema details or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.meta_url}/bases/{base_id}/tables",
                headers=self._get_headers(),
            )
            data = response.json()
            tables = data.get("tables", [])

            if not tables:
                return "No tables found in this base."

            result = f"**Base Schema ({base_id}):**\n\n"
            for table in tables:
                result += f"### {table.get('name', '')} (ID: `{table.get('id', '')}`)\n"
                if table.get("description"):
                    result += f"_{table['description']}_\n"
                fields = table.get("fields", [])
                if fields:
                    result += "**Fields:**\n"
                    for field in fields:
                        field_type = field.get("type", "unknown")
                        result += f"- `{field.get('name', '')}` ({field_type})"
                        if field.get("description"):
                            result += f" - {field['description']}"
                        result += "\n"
                result += "\n"

            return result
        except Exception as e:
            return f"Error getting base schema: {str(e)}"

    async def list_records(
        self, base_id: str, table_name: str, max_records: int = 100, view: str = None
    ):
        """
        List records from a table.

        Args:
            base_id (str): The base ID.
            table_name (str): The table name or ID.
            max_records (int): Maximum number of records to return. Default 100.
            view (str, optional): View name or ID to filter by.

        Returns:
            str: Formatted list of records or error message.
        """
        try:
            self.verify_user()
            params = {"maxRecords": min(int(max_records), 100)}
            if view:
                params["view"] = view

            # URL-encode table name
            import urllib.parse
            encoded_table = urllib.parse.quote(table_name, safe="")

            response = requests.get(
                f"{self.base_url}/{base_id}/{encoded_table}",
                headers=self._get_headers(),
                params=params,
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            records = data.get("records", [])

            if not records:
                return "No records found."

            result = f"**Records from {table_name} ({len(records)} records):**\n\n"
            for record in records:
                record_id = record.get("id", "")
                fields = record.get("fields", {})
                result += f"**Record `{record_id}`:**\n"
                for key, value in fields.items():
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    result += f"  - {key}: {value}\n"
                result += "\n"

            return result
        except Exception as e:
            return f"Error listing records: {str(e)}"

    async def get_record(self, base_id: str, table_name: str, record_id: str):
        """
        Get a specific record by ID.

        Args:
            base_id (str): The base ID.
            table_name (str): The table name or ID.
            record_id (str): The record ID (e.g., 'recXXXXXXXXXXXXXX').

        Returns:
            str: Record details or error message.
        """
        try:
            self.verify_user()
            import urllib.parse
            encoded_table = urllib.parse.quote(table_name, safe="")

            response = requests.get(
                f"{self.base_url}/{base_id}/{encoded_table}/{record_id}",
                headers=self._get_headers(),
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            fields = data.get("fields", {})
            result = f"**Record `{data.get('id', '')}`:**\n\n"
            for key, value in fields.items():
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                result += f"- **{key}:** {value}\n"

            result += f"\n_Created: {data.get('createdTime', 'N/A')}_"
            return result
        except Exception as e:
            return f"Error getting record: {str(e)}"

    async def create_record(self, base_id: str, table_name: str, fields_json: str):
        """
        Create a new record in a table.

        Args:
            base_id (str): The base ID.
            table_name (str): The table name or ID.
            fields_json (str): JSON string of field values (e.g., '{"Name": "John", "Email": "john@example.com"}').

        Returns:
            str: Created record details or error message.
        """
        try:
            self.verify_user()
            try:
                fields = json.loads(fields_json)
            except json.JSONDecodeError:
                return "Error: fields_json must be a valid JSON string."

            import urllib.parse
            encoded_table = urllib.parse.quote(table_name, safe="")

            response = requests.post(
                f"{self.base_url}/{base_id}/{encoded_table}",
                headers=self._get_headers(),
                json={"fields": fields},
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            return f"Record created!\n- **ID:** `{data.get('id', '')}`\n- **Created:** {data.get('createdTime', '')}"
        except Exception as e:
            return f"Error creating record: {str(e)}"

    async def update_record(
        self, base_id: str, table_name: str, record_id: str, fields_json: str
    ):
        """
        Update an existing record.

        Args:
            base_id (str): The base ID.
            table_name (str): The table name or ID.
            record_id (str): The record ID.
            fields_json (str): JSON string of field values to update.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            try:
                fields = json.loads(fields_json)
            except json.JSONDecodeError:
                return "Error: fields_json must be a valid JSON string."

            import urllib.parse
            encoded_table = urllib.parse.quote(table_name, safe="")

            response = requests.patch(
                f"{self.base_url}/{base_id}/{encoded_table}/{record_id}",
                headers=self._get_headers(),
                json={"fields": fields},
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            return f"Record `{record_id}` updated successfully."
        except Exception as e:
            return f"Error updating record: {str(e)}"

    async def delete_record(self, base_id: str, table_name: str, record_id: str):
        """
        Delete a record from a table.

        Args:
            base_id (str): The base ID.
            table_name (str): The table name or ID.
            record_id (str): The record ID to delete.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            import urllib.parse
            encoded_table = urllib.parse.quote(table_name, safe="")

            response = requests.delete(
                f"{self.base_url}/{base_id}/{encoded_table}/{record_id}",
                headers=self._get_headers(),
            )
            data = response.json()

            if data.get("deleted"):
                return f"Record `{record_id}` deleted."
            else:
                return f"Error deleting record: {data}"
        except Exception as e:
            return f"Error deleting record: {str(e)}"

    async def search_records(
        self,
        base_id: str,
        table_name: str,
        formula: str,
        max_records: int = 100,
    ):
        """
        Search records using an Airtable formula filter.

        Args:
            base_id (str): The base ID.
            table_name (str): The table name or ID.
            formula (str): Airtable formula to filter records (e.g., "{Name} = 'John'" or "FIND('search', {Notes})").
            max_records (int): Maximum number of records to return. Default 100.

        Returns:
            str: Matching records or error message.
        """
        try:
            self.verify_user()
            import urllib.parse
            encoded_table = urllib.parse.quote(table_name, safe="")

            response = requests.get(
                f"{self.base_url}/{base_id}/{encoded_table}",
                headers=self._get_headers(),
                params={
                    "filterByFormula": formula,
                    "maxRecords": min(int(max_records), 100),
                },
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            records = data.get("records", [])
            if not records:
                return f"No records found matching formula: {formula}"

            result = f"**Search results ({len(records)} records):**\n\n"
            for record in records:
                record_id = record.get("id", "")
                fields = record.get("fields", {})
                result += f"**Record `{record_id}`:**\n"
                for key, value in fields.items():
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    result += f"  - {key}: {value}\n"
                result += "\n"

            return result
        except Exception as e:
            return f"Error searching records: {str(e)}"

    async def create_table(
        self, base_id: str, name: str, fields_json: str, description: str = None
    ):
        """
        Create a new table in a base.

        Args:
            base_id (str): The base ID.
            name (str): The table name.
            fields_json (str): JSON array of field definitions (e.g., '[{"name": "Name", "type": "singleLineText"}, {"name": "Notes", "type": "multilineText"}]').
            description (str, optional): Table description.

        Returns:
            str: Created table details or error message.
        """
        try:
            self.verify_user()
            try:
                fields = json.loads(fields_json)
            except json.JSONDecodeError:
                return "Error: fields_json must be a valid JSON array."

            payload = {"name": name, "fields": fields}
            if description:
                payload["description"] = description

            response = requests.post(
                f"{self.meta_url}/bases/{base_id}/tables",
                headers=self._get_headers(),
                json=payload,
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            return f"Table created!\n- **Name:** {data.get('name', '')}\n- **ID:** `{data.get('id', '')}`"
        except Exception as e:
            return f"Error creating table: {str(e)}"
