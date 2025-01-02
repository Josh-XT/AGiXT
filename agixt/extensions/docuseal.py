import os
import logging
import requests
import asyncio
from typing import Dict, List
from datetime import datetime
from Extensions import Extensions


class docuseal_extension(Extensions):
    """
    The DocuSeal extension enables AI agents to manage electronic document signatures.

    This extension allows AI agents to:
    - Send signature requests for documents
    - Track signature status and progress
    - Receive notifications for signature events
    - Manage DocuSeal server configurations

    The extension requires DocuSeal API credentials and server configuration.
    AI agents should use this when they need to handle document signing workflows.
    """

    def __init__(
        self,
        DOCUSEAL_API_KEY: str = "",
        DOCUSEAL_SERVER_URL: str = "",
        **kwargs,
    ):
        """
        Initialize the DocuSeal extension with required credentials and settings.

        Args:
            DOCUSEAL_API_KEY (str): API key for DocuSeal authentication
            DOCUSEAL_SERVER_URL (str): Base URL for DocuSeal server
            **kwargs: Additional settings passed from the agent configuration
        """
        self.api_key = DOCUSEAL_API_KEY
        self.base_url = DOCUSEAL_SERVER_URL.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

        # Register available commands if credentials are provided
        self.commands = (
            {
                "Send Signature Request": self.send_signature_request,
                "Check Signature Status": self.check_signature_status,
                "Get Signature Updates": self.get_signature_updates,
            }
            if DOCUSEAL_API_KEY and DOCUSEAL_SERVER_URL
            else {}
        )

        # Store the working directory from kwargs
        self.working_dir = kwargs.get(
            "conversation_directory", os.path.join(os.getcwd(), "WORKSPACE")
        )

    async def send_signature_request(
        self,
        document_path: str,
        recipients: List[Dict[str, str]],
        template_name: str = "",
        message: str = "",
    ) -> str:
        """
        Create and send a signature request to specified recipients.

        This command is particularly useful for:
        - Initiating document signing workflows
        - Sending documents to multiple signers
        - Tracking new signature requests

        The AI should use this command when:
        - A document needs to be signed by one or more people
        - Starting a new document approval process

        Args:
            document_path (str): Path to the document file within working directory
            recipients (List[Dict[str, str]]): List of recipient details with email and name
            template_name (str, optional): Name of the DocuSeal template to use
            message (str, optional): Custom message for recipients

        Returns:
            str: Response with signature request ID and status

        Example Usage:
            <execute>
            <name>Send Signature Request</name>
            <document_path>contract.pdf</document_path>
            <recipients>[{"email": "john@example.com", "name": "John Doe"}]</recipients>
            <template_name>Standard Contract</template_name>
            <message>Please sign this contract at your earliest convenience.</message>
            </execute>
        """
        try:
            # Validate document path is within working directory
            full_path = os.path.join(self.working_dir, document_path)
            if not os.path.exists(full_path):
                return f"Error: Document not found at {document_path}"

            # Prepare multipart form data
            files = {
                "file": (document_path, open(full_path, "rb")),
                "recipients": (None, str(recipients)),
                "template_name": (None, template_name),
                "message": (None, message),
            }

            # Send request to DocuSeal
            response = self.session.post(
                f"{self.base_url}/api/v1/signature_requests", files=files
            )
            response.raise_for_status()

            # Log the activity using AGiXT SDK
            await self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[DOCUSEAL] Sent signature request for {document_path}",
                conversation_name=self.conversation_name,
            )

            return f"Signature request created successfully. Request ID: {response.json()['id']}"

        except Exception as e:
            logging.error(f"Error sending signature request: {str(e)}")
            return f"Error: {str(e)}"

    async def check_signature_status(self, request_id: str) -> str:
        """
        Check the current status of a signature request.

        This command is useful for:
        - Monitoring signature progress
        - Verifying document completion
        - Tracking pending signatures

        The AI should use this command when:
        - Checking if a document has been signed
        - Following up on pending signatures

        Args:
            request_id (str): The ID of the signature request to check

        Returns:
            str: Current status of the signature request

        Example Usage:
            <execute>
            <name>Check Signature Status</name>
            <request_id>123456</request_id>
            </execute>
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/signature_requests/{request_id}"
            )
            response.raise_for_status()

            status_data = response.json()

            # Format status information
            status_message = (
                f"Status for request {request_id}:\n"
                f"Overall Status: {status_data['status']}\n"
                f"Created: {datetime.fromisoformat(status_data['created_at'])}\n"
                "Recipient Status:\n"
            )

            for recipient in status_data["recipients"]:
                status_message += (
                    f"- {recipient['name']} ({recipient['email']}): "
                    f"{recipient['status']}\n"
                )

            return status_message

        except Exception as e:
            logging.error(f"Error checking signature status: {str(e)}")
            return f"Error: {str(e)}"

    async def get_signature_updates(self, request_id: str, timeout: int = 60) -> str:
        """
        Poll for real-time updates on a signature request.

        This command is useful for:
        - Getting immediate notification of signature completion
        - Monitoring document status changes
        - Triggering follow-up actions

        The AI should use this command when:
        - Waiting for signature completion
        - Needing real-time status updates

        Args:
            request_id (str): The ID of the signature request to monitor
            timeout (int): Maximum time in seconds to wait for updates

        Returns:
            str: Status updates received during polling

        Example Usage:
            <execute>
            <name>Get Signature Updates</name>
            <request_id>123456</request_id>
            <timeout>120</timeout>
            </execute>
        """
        try:
            # Initialize polling
            start_time = datetime.now()
            last_status = None

            while (datetime.now() - start_time).seconds < timeout:
                response = self.session.get(
                    f"{self.base_url}/api/v1/signature_requests/{request_id}"
                )
                response.raise_for_status()

                current_status = response.json()["status"]

                # Check for status changes
                if current_status != last_status:
                    if current_status in ["completed", "declined"]:
                        return f"Signature request {request_id}: {current_status}"
                    last_status = current_status

                await asyncio.sleep(5)  # Poll every 5 seconds

            return "Timeout reached without final status"

        except Exception as e:
            logging.error(f"Error getting signature updates: {str(e)}")
            return f"Error: {str(e)}"
