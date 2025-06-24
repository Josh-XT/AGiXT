from Extensions import Extensions
import requests
import json
import logging


class xt_systems(Extensions):
    """
    The XT Systems extension for AGiXT enables you to interact with the XT Systems API
    to manage assets, contacts, integrations, machines, secrets, and tickets.
    """

    def __init__(
        self,
        XT_SYSTEMS_API_KEY: str = "",
        XT_SYSTEMS_BASE_URL: str = "https://api.xt.systems",
        **kwargs,
    ):
        self.base_uri = XT_SYSTEMS_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"{XT_SYSTEMS_API_KEY}"})
        self.commands = {
            # Asset Template Commands
            "Create Asset Template": self.create_asset_template,
            "Get Asset Templates": self.get_asset_templates,
            "Get Asset Template": self.get_asset_template,
            "Update Asset Template": self.update_asset_template,
            "Delete Asset Template": self.delete_asset_template,
            "Get Company Asset Templates": self.get_company_asset_templates,
            # Asset Commands
            "Create Asset": self.create_asset,
            "Get Assets": self.get_assets,
            "Get Asset": self.get_asset,
            "Update Asset": self.update_asset,
            "Delete Asset": self.delete_asset,
            "Get Asset File": self.get_asset_file,
            "Update Asset Owner": self.update_asset_owner,
            "Get Company Assets": self.get_company_assets,
            # Contact Commands
            "Create Contact": self.create_contact,
            "Get All Contacts": self.get_all_contacts,
            "Get Contact": self.get_contact,
            "Update Contact": self.update_contact,
            "Delete Contact": self.delete_contact,
            # Integration Commands
            "Create Integration": self.create_integration,
            "Get Integrations": self.get_integrations,
            "Get Integration": self.get_integration,
            "Update Integration": self.update_integration,
            "Delete Integration": self.delete_integration,
            "Sync Integration": self.sync_integration,
            # Secret Commands
            "Create Secret": self.create_secret,
            # Ticket Commands
            "Create Ticket": self.create_ticket,
            "Get All Tickets": self.get_all_tickets,
            "Get Ticket": self.get_ticket,
            "Update Ticket": self.update_ticket,
            "Delete Ticket": self.delete_ticket,
            # Ticket Type Commands
            "Create Ticket Type": self.create_ticket_type,
            "Get All Ticket Types": self.get_all_ticket_types,
            "Get Ticket Type": self.get_ticket_type,
            "Update Ticket Type": self.update_ticket_type,
            "Delete Ticket Type": self.delete_ticket_type,
            # Ticket Template Commands
            "Create Ticket Template": self.create_ticket_template,
            "Get All Ticket Templates": self.get_all_ticket_templates,
            "Get Ticket Template": self.get_ticket_template,
            "Update Ticket Template": self.update_ticket_template,
            "Delete Ticket Template": self.delete_ticket_template,
            # Ticket Note Commands
            "Create Ticket Note": self.create_ticket_note,
            "Get Ticket Notes": self.get_ticket_notes,
            "Update Ticket Note": self.update_ticket_note,
            "Delete Ticket Note": self.delete_ticket_note,
            # Ticket Status Commands
            "Create Ticket Status": self.create_ticket_status,
            "Get All Ticket Statuses": self.get_all_ticket_statuses,
            "Update Ticket Status": self.update_ticket_status,
            "Delete Ticket Status": self.delete_ticket_status,
            # Ticket Priority Commands
            "Create Ticket Priority": self.create_ticket_priority,
            "Get All Ticket Priorities": self.get_all_ticket_priorities,
            "Update Ticket Priority": self.update_ticket_priority,
            "Delete Ticket Priority": self.delete_ticket_priority,
        }

    async def _make_request(
        self, method, endpoint, data=None, params=None, allow_machine=False
    ):
        """
        Make a request to the XT Systems API.

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE)
            endpoint (str): API endpoint
            data (dict): Request body data
            params (dict): Query parameters
            allow_machine (bool): Whether to allow machine access

        Returns:
            dict: Response data or error information
        """
        url = f"{self.base_uri}/{endpoint}"

        if params is None:
            params = {}

        if allow_machine:
            params["allow_machine"] = allow_machine

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, params=params)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, params=params)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, params=params)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}

            response.raise_for_status()

            # Handle different response types
            if response.status_code == 204:  # No content
                return {"success": True}

            try:
                return response.json()
            except json.JSONDecodeError:
                return {"success": True, "message": "Operation completed successfully"}

        except requests.exceptions.HTTPError as err:
            status_code = err.response.status_code if err.response else None
            try:
                error_detail = err.response.json() if err.response else {}
            except json.JSONDecodeError:
                error_detail = {"message": str(err)}

            return {
                "error": True,
                "status_code": status_code,
                "message": str(err),
                "details": error_detail,
            }
        except Exception as e:
            logging.error(f"XT Systems API request failed: {e}")
            return {"error": True, "message": str(e)}

    # Asset Template Commands
    async def create_asset_template(
        self,
        name: str,
        fields: dict,
        company_id: str,
        description: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new asset template.

        Args:
            name (str): Name of the asset template
            fields (dict): Template fields configuration
            company_id (str): Company ID
            description (str, optional): Template description
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created asset template data or error information
        """
        data = {"name": name, "fields": fields, "company_id": company_id}
        if description:
            data["description"] = description

        return await self._make_request(
            "POST",
            "v1/asset-templates",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def get_asset_templates(
        self, company_id: str = None, allow_machine: bool = False
    ):
        """
        Get all asset templates.

        Args:
            company_id (str, optional): Filter by company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Asset templates or error information
        """
        params = {"allow_machine": allow_machine}
        if company_id:
            params["company_id"] = company_id

        return await self._make_request("GET", "v1/asset-templates", params=params)

    async def get_asset_template(self, template_id: str, allow_machine: bool = False):
        """
        Get a specific asset template by ID.

        Args:
            template_id (str): Asset template ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Asset template data or error information
        """
        return await self._make_request(
            "GET",
            f"v1/asset-templates/{template_id}",
            params={"allow_machine": allow_machine},
        )

    async def update_asset_template(
        self,
        template_id: str,
        name: str,
        fields: dict,
        description: str = None,
        allow_machine: bool = False,
    ):
        """
        Update an asset template.

        Args:
            template_id (str): Asset template ID
            name (str): Updated name
            fields (dict): Updated fields configuration
            description (str, optional): Updated description
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated asset template data or error information
        """
        data = {"name": name, "fields": fields}
        if description:
            data["description"] = description

        return await self._make_request(
            "PUT",
            f"v1/asset-templates/{template_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_asset_template(
        self, template_id: str, allow_machine: bool = False
    ):
        """
        Delete an asset template.

        Args:
            template_id (str): Asset template ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE",
            f"v1/asset-templates/{template_id}",
            params={"allow_machine": allow_machine},
        )

    async def get_company_asset_templates(
        self, company_id: str, allow_machine: bool = False
    ):
        """
        Get all asset templates for a specific company.

        Args:
            company_id (str): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Company asset templates or error information
        """
        return await self._make_request(
            "GET",
            f"v1/companies/{company_id}/asset-templates",
            params={"allow_machine": allow_machine},
        )

    # Asset Commands
    async def create_asset(
        self, asset_data: dict, files: list = None, allow_machine: bool = False
    ):
        """
        Create a new asset.

        Args:
            asset_data (dict): Asset data as JSON string
            files (list, optional): List of files to attach
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created asset data or error information
        """
        # Note: This endpoint expects multipart/form-data for file uploads
        # For now, we'll handle the JSON data portion
        data = {"asset": json.dumps(asset_data)}
        return await self._make_request(
            "POST", "v1/assets", data=data, params={"allow_machine": allow_machine}
        )

    async def get_assets(self, allow_machine: bool = False):
        """
        Get all assets.

        Args:
            allow_machine (bool): Allow machine access

        Returns:
            list: Assets or error information
        """
        return await self._make_request(
            "GET", "v1/assets", params={"allow_machine": allow_machine}
        )

    async def get_asset(self, asset_id: str, allow_machine: bool = False):
        """
        Get a specific asset by ID.

        Args:
            asset_id (str): Asset ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Asset data or error information
        """
        return await self._make_request(
            "GET", f"v1/assets/{asset_id}", params={"allow_machine": allow_machine}
        )

    async def update_asset(
        self,
        asset_id: str,
        asset_data: dict,
        files: list = None,
        allow_machine: bool = False,
    ):
        """
        Update an asset.

        Args:
            asset_id (str): Asset ID
            asset_data (dict): Updated asset data
            files (list, optional): List of files to attach
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated asset data or error information
        """
        data = {"asset": json.dumps(asset_data)}
        return await self._make_request(
            "PUT",
            f"v1/assets/{asset_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_asset(self, asset_id: str, allow_machine: bool = False):
        """
        Delete an asset.

        Args:
            asset_id (str): Asset ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE", f"v1/assets/{asset_id}", params={"allow_machine": allow_machine}
        )

    async def get_asset_file(
        self, asset_id: str, file_id: str, allow_machine: bool = False
    ):
        """
        Get a specific file from an asset.

        Args:
            asset_id (str): Asset ID
            file_id (str): File ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: File data or error information
        """
        return await self._make_request(
            "GET",
            f"v1/assets/{asset_id}/files/{file_id}",
            params={"allow_machine": allow_machine},
        )

    async def update_asset_owner(
        self, asset_id: str, contact_id: str, allow_machine: bool = False
    ):
        """
        Update the owner of an asset.

        Args:
            asset_id (str): Asset ID
            contact_id (str): New owner contact ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated asset data or error information
        """
        return await self._make_request(
            "PUT",
            f"v1/assets/{asset_id}/owner/{contact_id}",
            params={"allow_machine": allow_machine},
        )

    async def get_company_assets(self, company_id: str, allow_machine: bool = False):
        """
        Get all assets for a specific company.

        Args:
            company_id (str): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Company assets or error information
        """
        return await self._make_request(
            "GET",
            f"v1/companies/{company_id}/assets",
            params={"allow_machine": allow_machine},
        )

    # Contact Commands
    async def create_contact(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: str = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new contact.

        Args:
            first_name (str): Contact's first name
            last_name (str): Contact's last name
            email (str): Contact's email address
            phone (str, optional): Contact's phone number
            company_id (str, optional): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created contact data or error information
        """
        data = {"first_name": first_name, "last_name": last_name, "email": email}
        if phone:
            data["phone"] = phone
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "POST", "v1/contacts", data=data, params={"allow_machine": allow_machine}
        )

    async def get_all_contacts(
        self, company_id: str = None, allow_machine: bool = False
    ):
        """
        Get all contacts.

        Args:
            company_id (str, optional): Filter by company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Contacts or error information
        """
        params = {"allow_machine": allow_machine}
        if company_id:
            params["company_id"] = company_id

        return await self._make_request("GET", "v1/contacts", params=params)

    async def get_contact(self, contact_id: str, allow_machine: bool = False):
        """
        Get a specific contact by ID.

        Args:
            contact_id (str): Contact ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Contact data or error information
        """
        return await self._make_request(
            "GET", f"v1/contacts/{contact_id}", params={"allow_machine": allow_machine}
        )

    async def update_contact(
        self,
        contact_id: str,
        first_name: str = None,
        last_name: str = None,
        email: str = None,
        phone: str = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Update a contact.

        Args:
            contact_id (str): Contact ID
            first_name (str, optional): Updated first name
            last_name (str, optional): Updated last name
            email (str, optional): Updated email
            phone (str, optional): Updated phone
            company_id (str, optional): Updated company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated contact data or error information
        """
        data = {}
        if first_name:
            data["first_name"] = first_name
        if last_name:
            data["last_name"] = last_name
        if email:
            data["email"] = email
        if phone:
            data["phone"] = phone
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "PUT",
            f"v1/contacts/{contact_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_contact(self, contact_id: str, allow_machine: bool = False):
        """
        Delete a contact.

        Args:
            contact_id (str): Contact ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE",
            f"v1/contacts/{contact_id}",
            params={"allow_machine": allow_machine},
        )

    # Integration Commands
    async def create_integration(
        self,
        status: str,
        company_id: str,
        name: str = None,
        last_sync: str = None,
        next_sync: str = None,
        secret_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new integration.

        Args:
            status (str): Integration status
            company_id (str): Company ID
            name (str, optional): Integration name
            last_sync (str, optional): Last sync datetime
            next_sync (str, optional): Next sync datetime
            secret_id (str, optional): Associated secret ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created integration data or error information
        """
        data = {"status": status, "company_id": company_id}
        if name:
            data["name"] = name
        if last_sync:
            data["last_sync"] = last_sync
        if next_sync:
            data["next_sync"] = next_sync
        if secret_id:
            data["secret_id"] = secret_id

        return await self._make_request(
            "POST",
            "v1/integrations",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def get_integrations(self, allow_machine: bool = False):
        """
        Get all integrations.

        Args:
            allow_machine (bool): Allow machine access

        Returns:
            list: Integrations or error information
        """
        return await self._make_request(
            "GET", "v1/integrations", params={"allow_machine": allow_machine}
        )

    async def get_integration(self, integration_id: str, allow_machine: bool = False):
        """
        Get a specific integration by ID.

        Args:
            integration_id (str): Integration ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Integration data or error information
        """
        return await self._make_request(
            "GET",
            f"v1/integrations/{integration_id}",
            params={"allow_machine": allow_machine},
        )

    async def update_integration(
        self,
        integration_id: str,
        status: str,
        name: str = None,
        last_sync: str = None,
        next_sync: str = None,
        secret_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Update an integration.

        Args:
            integration_id (str): Integration ID
            status (str): Updated status
            name (str, optional): Updated name
            last_sync (str, optional): Updated last sync datetime
            next_sync (str, optional): Updated next sync datetime
            secret_id (str, optional): Updated secret ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated integration data or error information
        """
        data = {"status": status}
        if name:
            data["name"] = name
        if last_sync:
            data["last_sync"] = last_sync
        if next_sync:
            data["next_sync"] = next_sync
        if secret_id:
            data["secret_id"] = secret_id

        return await self._make_request(
            "PUT",
            f"v1/integrations/{integration_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_integration(
        self, integration_id: str, allow_machine: bool = False
    ):
        """
        Delete an integration.

        Args:
            integration_id (str): Integration ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE",
            f"v1/integrations/{integration_id}",
            params={"allow_machine": allow_machine},
        )

    async def sync_integration(self, integration_id: str, allow_machine: bool = False):
        """
        Sync an integration.

        Args:
            integration_id (str): Integration ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Sync result or error information
        """
        return await self._make_request(
            "POST",
            f"v1/integrations/{integration_id}/sync",
            params={"allow_machine": allow_machine},
        )

    # Machine Commands
    async def register_machine(self, company_id: str, hostname: str, device_data: dict):
        """
        Register a new machine.

        Args:
            company_id (str): Company ID
            hostname (str): Machine hostname
            device_data (dict): Device data

        Returns:
            dict: Registration result or error information
        """
        data = {
            "company_id": company_id,
            "hostname": hostname,
            "device_data": device_data,
        }
        return await self._make_request("POST", "v1/machine/register", data=data)

    async def approve_machine(
        self, asset_id: str, company_id: str, allow_machine: bool = False
    ):
        """
        Approve a machine.

        Args:
            asset_id (str): Asset ID
            company_id (str): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Approval result or error information
        """
        data = {"asset_id": asset_id, "company_id": company_id}
        return await self._make_request(
            "POST",
            "v1/machine/approve",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def deny_machine(
        self, asset_id: str, company_id: str, allow_machine: bool = False
    ):
        """
        Deny a machine.

        Args:
            asset_id (str): Asset ID
            company_id (str): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Denial result or error information
        """
        data = {"asset_id": asset_id, "company_id": company_id}
        return await self._make_request(
            "POST",
            "v1/machine/deny",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def machine_login(self, asset_id: str, mfa_token: str):
        """
        Machine login.

        Args:
            asset_id (str): Asset ID
            mfa_token (str): MFA token

        Returns:
            dict: Login result or error information
        """
        data = {"asset_id": asset_id, "mfa_token": mfa_token}
        return await self._make_request("POST", "v1/machine/login", data=data)

    async def get_machine_status(self):
        """
        Get machine status.

        Returns:
            dict: Machine status or error information
        """
        return await self._make_request("GET", "v1/machine/status")

    async def get_machines_by_status(
        self, company_id: str, status: str = None, allow_machine: bool = False
    ):
        """
        Get machines by status for a company.

        Args:
            company_id (str): Company ID
            status (str, optional): Filter by status
            allow_machine (bool): Allow machine access

        Returns:
            list: Machines or error information
        """
        params = {"allow_machine": allow_machine}
        if status:
            params["status"] = status

        return await self._make_request(
            "GET", f"v1/companies/{company_id}/machines", params=params
        )

    async def sync_device_data(self, device_data: dict):
        """
        Sync device data.

        Args:
            device_data (dict): Device data to sync

        Returns:
            dict: Sync result or error information
        """
        data = {"device_data": device_data}
        return await self._make_request("POST", "v1/machine", data=data)

    async def add_approved_ip_range(
        self, company_id: str, start_ip: str, end_ip: str, allow_machine: bool = False
    ):
        """
        Add an approved IP range for a company.

        Args:
            company_id (str): Company ID
            start_ip (str): Start IP address
            end_ip (str): End IP address
            allow_machine (bool): Allow machine access

        Returns:
            dict: Added IP range or error information
        """
        params = {
            "start_ip": start_ip,
            "end_ip": end_ip,
            "allow_machine": allow_machine,
        }
        return await self._make_request(
            "POST", f"v1/companies/{company_id}/approved-ip-ranges", params=params
        )

    async def get_approved_ip_ranges(
        self, company_id: str, allow_machine: bool = False
    ):
        """
        Get approved IP ranges for a company.

        Args:
            company_id (str): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Approved IP ranges or error information
        """
        return await self._make_request(
            "GET",
            f"v1/companies/{company_id}/approved-ip-ranges",
            params={"allow_machine": allow_machine},
        )

    # Secret Commands
    async def create_secret(
        self,
        name: str,
        items: list,
        company_id: str = None,
        description: str = None,
        expires_at: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new secret.

        Args:
            name (str): Secret name
            items (list): List of secret items (key-value pairs)
            company_id (str, optional): Company ID
            description (str, optional): Secret description
            expires_at (str, optional): Expiration datetime
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created secret data or error information
        """
        data = {"name": name, "items": items}
        if company_id:
            data["company_id"] = company_id
        if description:
            data["description"] = description
        if expires_at:
            data["expires_at"] = expires_at

        return await self._make_request(
            "POST", "v1/secrets", data=data, params={"allow_machine": allow_machine}
        )

    async def get_secrets(self, allow_machine: bool = False):
        """
        Get all secrets.

        Args:
            allow_machine (bool): Allow machine access

        Returns:
            list: Secrets or error information
        """
        return await self._make_request(
            "GET", "v1/secrets", params={"allow_machine": allow_machine}
        )

    async def get_secret(self, secret_id: str, allow_machine: bool = False):
        """
        Get a specific secret by ID.

        Args:
            secret_id (str): Secret ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Secret data or error information
        """
        return await self._make_request(
            "GET", f"v1/secret/{secret_id}", params={"allow_machine": allow_machine}
        )

    async def update_secret(
        self,
        secret_id: str,
        name: str,
        items: list,
        company_id: str = None,
        description: str = None,
        expires_at: str = None,
        allow_machine: bool = False,
    ):
        """
        Update a secret.

        Args:
            secret_id (str): Secret ID
            name (str): Updated name
            items (list): Updated items
            company_id (str, optional): Updated company ID
            description (str, optional): Updated description
            expires_at (str, optional): Updated expiration datetime
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated secret data or error information
        """
        data = {"name": name, "items": items}
        if company_id:
            data["company_id"] = company_id
        if description:
            data["description"] = description
        if expires_at:
            data["expires_at"] = expires_at

        return await self._make_request(
            "PUT",
            f"v1/secret/{secret_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_secret(self, secret_id: str, allow_machine: bool = False):
        """
        Delete a secret.

        Args:
            secret_id (str): Secret ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE", f"v1/secret/{secret_id}", params={"allow_machine": allow_machine}
        )

    async def get_expired_secrets(self, allow_machine: bool = False):
        """
        Get expired secrets.

        Args:
            allow_machine (bool): Allow machine access

        Returns:
            list: Expired secrets or error information
        """
        return await self._make_request(
            "GET", "v1/secrets/expired", params={"allow_machine": allow_machine}
        )

    async def get_expiring_soon_secrets(
        self, days: int = 30, allow_machine: bool = False
    ):
        """
        Get secrets expiring soon.

        Args:
            days (int): Number of days to look ahead (default: 30)
            allow_machine (bool): Allow machine access

        Returns:
            list: Expiring secrets or error information
        """
        params = {"days": days, "allow_machine": allow_machine}
        return await self._make_request(
            "GET", "v1/secrets/expiring-soon", params=params
        )

    # Ticket Commands
    async def create_ticket(
        self,
        title: str,
        description: str = None,
        status_id: str = None,
        priority_id: str = None,
        due_date: str = None,
        contact_id: str = None,
        assigned_to: str = None,
        ticket_type_id: str = None,
        template_id: str = None,
        template_data: dict = None,
        asset_ids: list = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new ticket.

        Args:
            title (str): Ticket title
            description (str, optional): Ticket description
            status_id (str, optional): Status ID
            priority_id (str, optional): Priority ID
            due_date (str, optional): Due date
            contact_id (str, optional): Contact ID
            assigned_to (str, optional): Assigned user
            ticket_type_id (str, optional): Ticket type ID
            template_id (str, optional): Template ID
            template_data (dict, optional): Template data
            asset_ids (list, optional): Associated asset IDs
            company_id (str, optional): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created ticket data or error information
        """
        data = {"title": title}

        if description:
            data["description"] = description
        if status_id:
            data["status_id"] = status_id
        if priority_id:
            data["priority_id"] = priority_id
        if due_date:
            data["due_date"] = due_date
        if contact_id:
            data["contact_id"] = contact_id
        if assigned_to:
            data["assigned_to"] = assigned_to
        if ticket_type_id:
            data["ticket_type_id"] = ticket_type_id
        if template_id:
            data["template_id"] = template_id
        if template_data:
            data["template_data"] = template_data
        if asset_ids:
            data["asset_ids"] = asset_ids
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "POST", "v1/tickets", data=data, params={"allow_machine": allow_machine}
        )

    async def get_all_tickets(self, allow_machine: bool = False):
        """
        Get all tickets.

        Args:
            allow_machine (bool): Allow machine access

        Returns:
            list: Tickets or error information
        """
        return await self._make_request(
            "GET", "v1/tickets", params={"allow_machine": allow_machine}
        )

    async def get_ticket(self, ticket_identifier: str, allow_machine: bool = False):
        """
        Get a ticket by either its UUID or sequential ID.

        Args:
            ticket_identifier (str): Either a UUID or a sequential number
            allow_machine (bool): Allow machine access

        Returns:
            dict: Ticket data or error information
        """
        return await self._make_request(
            "GET",
            f"v1/tickets/{ticket_identifier}",
            params={"allow_machine": allow_machine},
        )

    async def update_ticket(
        self,
        ticket_id: str,
        title: str = None,
        description: str = None,
        status_id: str = None,
        priority_id: str = None,
        due_date: str = None,
        contact_id: str = None,
        assigned_to: str = None,
        ticket_type_id: str = None,
        template_id: str = None,
        template_data: dict = None,
        asset_ids: list = None,
        allow_machine: bool = False,
    ):
        """
        Update a ticket.

        Args:
            ticket_id (str): Ticket ID
            title (str, optional): Updated title
            description (str, optional): Updated description
            status_id (str, optional): Updated status ID
            priority_id (str, optional): Updated priority ID
            due_date (str, optional): Updated due date
            contact_id (str, optional): Updated contact ID
            assigned_to (str, optional): Updated assigned user
            ticket_type_id (str, optional): Updated ticket type ID
            template_id (str, optional): Updated template ID
            template_data (dict, optional): Updated template data
            asset_ids (list, optional): Updated asset IDs
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated ticket data or error information
        """
        data = {}

        if title:
            data["title"] = title
        if description:
            data["description"] = description
        if status_id:
            data["status_id"] = status_id
        if priority_id:
            data["priority_id"] = priority_id
        if due_date:
            data["due_date"] = due_date
        if contact_id:
            data["contact_id"] = contact_id
        if assigned_to:
            data["assigned_to"] = assigned_to
        if ticket_type_id:
            data["ticket_type_id"] = ticket_type_id
        if template_id:
            data["template_id"] = template_id
        if template_data:
            data["template_data"] = template_data
        if asset_ids:
            data["asset_ids"] = asset_ids

        return await self._make_request(
            "PUT",
            f"v1/tickets/{ticket_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_ticket(self, ticket_id: str, allow_machine: bool = False):
        """
        Delete a ticket.

        Args:
            ticket_id (str): Ticket ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE", f"v1/tickets/{ticket_id}", params={"allow_machine": allow_machine}
        )

    # Ticket Type Commands
    async def create_ticket_type(
        self,
        name: str = None,
        description: str = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new ticket type.

        Args:
            name (str, optional): Ticket type name
            description (str, optional): Ticket type description
            company_id (str, optional): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created ticket type data or error information
        """
        data = {}
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "POST",
            "v1/ticket-types",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def get_all_ticket_types(
        self, company_id: str = None, allow_machine: bool = False
    ):
        """
        Get all ticket types.

        Args:
            company_id (str, optional): Filter by company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Ticket types or error information
        """
        params = {"allow_machine": allow_machine}
        if company_id:
            params["company_id"] = company_id

        return await self._make_request("GET", "v1/ticket-types", params=params)

    async def get_ticket_type(self, ticket_type_id: str, allow_machine: bool = False):
        """
        Get a specific ticket type by ID.

        Args:
            ticket_type_id (str): Ticket type ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Ticket type data or error information
        """
        return await self._make_request(
            "GET",
            f"v1/ticket-types/{ticket_type_id}",
            params={"allow_machine": allow_machine},
        )

    async def update_ticket_type(
        self,
        ticket_type_id: str,
        name: str = None,
        description: str = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Update a ticket type.

        Args:
            ticket_type_id (str): Ticket type ID
            name (str, optional): Updated name
            description (str, optional): Updated description
            company_id (str, optional): Updated company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated ticket type data or error information
        """
        data = {}
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "PUT",
            f"v1/ticket-types/{ticket_type_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_ticket_type(
        self, ticket_type_id: str, allow_machine: bool = False
    ):
        """
        Delete a ticket type.

        Args:
            ticket_type_id (str): Ticket type ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE",
            f"v1/ticket-types/{ticket_type_id}",
            params={"allow_machine": allow_machine},
        )

    # Ticket Template Commands
    async def create_ticket_template(
        self,
        name: str,
        fields: dict,
        description: str = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new ticket template.

        Args:
            name (str): Template name
            fields (dict): Template fields
            description (str, optional): Template description
            company_id (str, optional): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created ticket template data or error information
        """
        data = {"name": name, "fields": fields}
        if description:
            data["description"] = description
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "POST",
            "v1/ticket-templates",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def get_all_ticket_templates(
        self, company_id: str = None, allow_machine: bool = False
    ):
        """
        Get all ticket templates.

        Args:
            company_id (str, optional): Filter by company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Ticket templates or error information
        """
        params = {"allow_machine": allow_machine}
        if company_id:
            params["company_id"] = company_id

        return await self._make_request("GET", "v1/ticket-templates", params=params)

    async def get_ticket_template(
        self, ticket_template_id: str, allow_machine: bool = False
    ):
        """
        Get a specific ticket template by ID.

        Args:
            ticket_template_id (str): Ticket template ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Ticket template data or error information
        """
        return await self._make_request(
            "GET",
            f"v1/ticket-templates/{ticket_template_id}",
            params={"allow_machine": allow_machine},
        )

    async def update_ticket_template(
        self,
        ticket_template_id: str,
        name: str,
        fields: dict,
        description: str = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Update a ticket template.

        Args:
            ticket_template_id (str): Ticket template ID
            name (str): Updated name
            fields (dict): Updated fields
            description (str, optional): Updated description
            company_id (str, optional): Updated company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated ticket template data or error information
        """
        data = {"name": name, "fields": fields}
        if description:
            data["description"] = description
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "PUT",
            f"v1/ticket-templates/{ticket_template_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_ticket_template(
        self, ticket_template_id: str, allow_machine: bool = False
    ):
        """
        Delete a ticket template.

        Args:
            ticket_template_id (str): Ticket template ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE",
            f"v1/ticket-templates/{ticket_template_id}",
            params={"allow_machine": allow_machine},
        )

    # Ticket Note Commands
    async def create_ticket_note(
        self, ticket_id: str, content: str, allow_machine: bool = False
    ):
        """
        Create a new ticket note.

        Args:
            ticket_id (str): Ticket ID
            content (str): Note content
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created ticket note data or error information
        """
        data = {"content": content}
        return await self._make_request(
            "POST",
            f"v1/tickets/{ticket_id}/notes",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def get_ticket_notes(self, ticket_id: str, allow_machine: bool = False):
        """
        Get all notes for a ticket.

        Args:
            ticket_id (str): Ticket ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Ticket notes or error information
        """
        return await self._make_request(
            "GET",
            f"v1/tickets/{ticket_id}/notes",
            params={"allow_machine": allow_machine},
        )

    async def update_ticket_note(
        self, ticket_id: str, note_id: str, content: str, allow_machine: bool = False
    ):
        """
        Update a ticket note.

        Args:
            ticket_id (str): Ticket ID
            note_id (str): Note ID
            content (str): Updated content
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated ticket note data or error information
        """
        data = {"content": content}
        return await self._make_request(
            "PUT",
            f"v1/tickets/{ticket_id}/notes/{note_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_ticket_note(
        self, ticket_id: str, note_id: str, allow_machine: bool = False
    ):
        """
        Delete a ticket note.

        Args:
            ticket_id (str): Ticket ID
            note_id (str): Note ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE",
            f"v1/tickets/{ticket_id}/notes/{note_id}",
            params={"allow_machine": allow_machine},
        )

    # Ticket Status Commands
    async def create_ticket_status(
        self,
        name: str,
        description: str = None,
        color: str = None,
        is_closed: bool = False,
        order: int = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new ticket status.

        Args:
            name (str): Status name
            description (str, optional): Status description
            color (str, optional): Status color
            is_closed (bool): Whether this status indicates a closed ticket
            order (int, optional): Status order
            company_id (str, optional): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created ticket status data or error information
        """
        data = {"name": name, "is_closed": is_closed}
        if description:
            data["description"] = description
        if color:
            data["color"] = color
        if order is not None:
            data["order"] = order
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "POST",
            "v1/ticket-statuses",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def get_all_ticket_statuses(
        self, company_id: str = None, allow_machine: bool = False
    ):
        """
        Get all ticket statuses.

        Args:
            company_id (str, optional): Filter by company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Ticket statuses or error information
        """
        params = {"allow_machine": allow_machine}
        if company_id:
            params["company_id"] = company_id

        return await self._make_request("GET", "v1/ticket-statuses", params=params)

    async def update_ticket_status(
        self,
        status_id: str,
        name: str,
        description: str = None,
        color: str = None,
        is_closed: bool = False,
        order: int = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Update a ticket status.

        Args:
            status_id (str): Status ID
            name (str): Updated name
            description (str, optional): Updated description
            color (str, optional): Updated color
            is_closed (bool): Updated closed status
            order (int, optional): Updated order
            company_id (str, optional): Updated company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated ticket status data or error information
        """
        data = {"name": name, "is_closed": is_closed}
        if description:
            data["description"] = description
        if color:
            data["color"] = color
        if order is not None:
            data["order"] = order
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "PUT",
            f"v1/ticket-statuses/{status_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_ticket_status(self, status_id: str, allow_machine: bool = False):
        """
        Delete a ticket status.

        Args:
            status_id (str): Status ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE",
            f"v1/ticket-statuses/{status_id}",
            params={"allow_machine": allow_machine},
        )

    # Ticket Priority Commands
    async def create_ticket_priority(
        self,
        name: str,
        description: str = None,
        color: str = None,
        order: int = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Create a new ticket priority.

        Args:
            name (str): Priority name
            description (str, optional): Priority description
            color (str, optional): Priority color
            order (int, optional): Priority order
            company_id (str, optional): Company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Created ticket priority data or error information
        """
        data = {"name": name}
        if description:
            data["description"] = description
        if color:
            data["color"] = color
        if order is not None:
            data["order"] = order
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "POST",
            "v1/ticket-priorities",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def get_all_ticket_priorities(
        self, company_id: str = None, allow_machine: bool = False
    ):
        """
        Get all ticket priorities.

        Args:
            company_id (str, optional): Filter by company ID
            allow_machine (bool): Allow machine access

        Returns:
            list: Ticket priorities or error information
        """
        params = {"allow_machine": allow_machine}
        if company_id:
            params["company_id"] = company_id

        return await self._make_request("GET", "v1/ticket-priorities", params=params)

    async def update_ticket_priority(
        self,
        priority_id: str,
        name: str,
        description: str = None,
        color: str = None,
        order: int = None,
        company_id: str = None,
        allow_machine: bool = False,
    ):
        """
        Update a ticket priority.

        Args:
            priority_id (str): Priority ID
            name (str): Updated name
            description (str, optional): Updated description
            color (str, optional): Updated color
            order (int, optional): Updated order
            company_id (str, optional): Updated company ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Updated ticket priority data or error information
        """
        data = {"name": name}
        if description:
            data["description"] = description
        if color:
            data["color"] = color
        if order is not None:
            data["order"] = order
        if company_id:
            data["company_id"] = company_id

        return await self._make_request(
            "PUT",
            f"v1/ticket-priorities/{priority_id}",
            data=data,
            params={"allow_machine": allow_machine},
        )

    async def delete_ticket_priority(
        self, priority_id: str, allow_machine: bool = False
    ):
        """
        Delete a ticket priority.

        Args:
            priority_id (str): Priority ID
            allow_machine (bool): Allow machine access

        Returns:
            dict: Success status or error information
        """
        return await self._make_request(
            "DELETE",
            f"v1/ticket-priorities/{priority_id}",
            params={"allow_machine": allow_machine},
        )
