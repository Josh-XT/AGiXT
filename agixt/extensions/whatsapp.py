import os
import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth


"""
WhatsApp Business API Extension for AGiXT

This extension uses the WhatsApp Business Cloud API (via Meta/Facebook).
It requires a Meta Business account and WhatsApp Business app setup.

Required environment variables:
- WHATSAPP_BUSINESS_ACCOUNT_ID: WhatsApp Business Account ID
- WHATSAPP_PHONE_NUMBER_ID: Phone number ID from WhatsApp Business
- WHATSAPP_ACCESS_TOKEN: Permanent access token or System User Token

Companies can also configure their own WhatsApp settings:
- whatsapp_phone_number_id: Company's WhatsApp phone number ID
- whatsapp_access_token: Company's access token
- whatsapp_verify_token: Webhook verification token

Setup Instructions:
1. Create a Meta Business account at business.facebook.com
2. Create an app at developers.facebook.com
3. Add WhatsApp product to your app
4. Get your Phone Number ID and generate an access token
5. Configure webhook URL for incoming messages

WhatsApp Cloud API Documentation: https://developers.facebook.com/docs/whatsapp/cloud-api
"""


def get_whatsapp_user_ids(company_id=None):
    """
    Get mapping of WhatsApp phone numbers to AGiXT user IDs for a company.
    
    WhatsApp identifies users by their phone numbers.
    Users link their accounts by sending a message to the bot
    and completing verification.
    
    Args:
        company_id: Optional company ID to filter by
        
    Returns:
        Dict mapping WhatsApp phone number -> AGiXT user ID
    """
    from DB import get_session, UserOAuth, OAuthProvider
    
    user_ids = {}
    with get_session() as session:
        provider = session.query(OAuthProvider).filter_by(name="whatsapp").first()
        if not provider:
            return user_ids
            
        query = session.query(UserOAuth).filter_by(provider_id=provider.id)
        
        if company_id:
            query = query.filter(UserOAuth.company_id == company_id)
            
        for oauth in query.all():
            if oauth.provider_user_id:
                user_ids[oauth.provider_user_id] = str(oauth.user_id)
                
    return user_ids


class whatsapp(Extensions):
    """
    The WhatsApp extension provides integration with WhatsApp Business Cloud API.
    This extension allows AI agents to:
    - Send text messages
    - Send media (images, documents, audio, video)
    - Send template messages
    - Send interactive messages (buttons, lists)
    - Mark messages as read
    - Get business profile information
    
    The extension requires WhatsApp Business API access through Meta.
    AI agents should use this when they need to communicate via WhatsApp
    for customer support, notifications, or conversational AI.
    
    Note: WhatsApp has strict policies on messaging. You can only message
    users who have messaged you first within the last 24 hours, unless
    using approved template messages.
    """

    CATEGORY = "Social & Communication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("WHATSAPP_ACCESS_TOKEN", None)
        self.phone_number_id = kwargs.get("WHATSAPP_PHONE_NUMBER_ID", None)
        self.business_account_id = kwargs.get("WHATSAPP_BUSINESS_ACCOUNT_ID", None)
        self.auth = None
        
        # Fallback to environment variables
        if not self.access_token:
            self.access_token = getenv("WHATSAPP_ACCESS_TOKEN")
        if not self.phone_number_id:
            self.phone_number_id = getenv("WHATSAPP_PHONE_NUMBER_ID")
        if not self.business_account_id:
            self.business_account_id = getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
        
        self.base_url = "https://graph.facebook.com/v18.0"

        if self.access_token and self.phone_number_id:
            self.commands = {
                "WhatsApp - Send Text Message": self.send_text_message,
                "WhatsApp - Send Image": self.send_image,
                "WhatsApp - Send Document": self.send_document,
                "WhatsApp - Send Template Message": self.send_template_message,
                "WhatsApp - Send Interactive Buttons": self.send_interactive_buttons,
                "WhatsApp - Send Interactive List": self.send_interactive_list,
                "WhatsApp - Mark Message Read": self.mark_message_read,
                "WhatsApp - Get Business Profile": self.get_business_profile,
                "WhatsApp - Update Business Profile": self.update_business_profile,
                "WhatsApp - Get Media URL": self.get_media_url,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing WhatsApp client: {str(e)}")

        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )

    def _get_headers(self):
        """Get authorization headers."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _make_request(self, method: str, endpoint: str, data: dict = None, files: dict = None):
        """
        Make a request to the WhatsApp Cloud API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request data
            files: Files to upload
            
        Returns:
            API response
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=self._get_headers(), params=data)
            elif files:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.post(url, headers=headers, data=data, files=files)
            else:
                response = requests.post(url, headers=self._get_headers(), json=data)
            
            result = response.json()
            
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                logging.error(f"WhatsApp API error: {error_msg}")
                return {"error": error_msg}
            
            return result
            
        except Exception as e:
            logging.error(f"WhatsApp request failed: {str(e)}")
            return {"error": str(e)}

    async def send_text_message(
        self,
        recipient_phone: str,
        message: str,
        preview_url: bool = False,
    ):
        """
        Sends a text message to a WhatsApp user.

        Args:
            recipient_phone (str): Recipient's phone number (with country code, no + or spaces)
            message (str): Message text (max 4096 characters)
            preview_url (bool): Whether to show URL previews

        Returns:
            dict: Response containing message ID and success status
        """
        try:
            # WhatsApp has a 4096 character limit
            if len(message) > 4096:
                # Split into chunks
                chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
                results = []
                for chunk in chunks:
                    result = await self.send_text_message(recipient_phone, chunk, preview_url)
                    results.append(result)
                return results[-1]
            
            # Normalize phone number (remove + and spaces)
            recipient_phone = recipient_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_phone,
                "type": "text",
                "text": {
                    "preview_url": preview_url,
                    "body": message,
                },
            }
            
            result = self._make_request("POST", f"{self.phone_number_id}/messages", data)
            
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id", ""),
            }

        except Exception as e:
            logging.error(f"Error sending WhatsApp message: {str(e)}")
            return {"success": False, "error": str(e)}

    async def send_image(
        self,
        recipient_phone: str,
        image_url: str = None,
        image_path: str = None,
        caption: str = None,
    ):
        """
        Sends an image to a WhatsApp user.

        Args:
            recipient_phone (str): Recipient's phone number
            image_url (str): URL of the image (if hosted)
            image_path (str): Path to local image file (will be uploaded first)
            caption (str): Image caption

        Returns:
            dict: Response containing message ID and success status
        """
        try:
            recipient_phone = recipient_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            if image_path and not image_url:
                # Need to upload the image first
                full_path = os.path.join(self.WORKING_DIRECTORY, image_path)
                if not os.path.exists(full_path):
                    if os.path.exists(image_path):
                        full_path = image_path
                    else:
                        return {"success": False, "error": f"Image not found: {image_path}"}
                
                # Upload media
                with open(full_path, "rb") as f:
                    upload_result = self._make_request(
                        "POST",
                        f"{self.phone_number_id}/media",
                        data={"messaging_product": "whatsapp"},
                        files={"file": f},
                    )
                
                if "error" in upload_result:
                    return {"success": False, "error": upload_result["error"]}
                
                media_id = upload_result.get("id")
                
                data = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient_phone,
                    "type": "image",
                    "image": {"id": media_id},
                }
            else:
                data = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient_phone,
                    "type": "image",
                    "image": {"link": image_url},
                }
            
            if caption:
                data["image"]["caption"] = caption[:1024]
            
            result = self._make_request("POST", f"{self.phone_number_id}/messages", data)
            
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id", ""),
            }

        except Exception as e:
            logging.error(f"Error sending WhatsApp image: {str(e)}")
            return {"success": False, "error": str(e)}

    async def send_document(
        self,
        recipient_phone: str,
        document_url: str = None,
        document_path: str = None,
        filename: str = None,
        caption: str = None,
    ):
        """
        Sends a document to a WhatsApp user.

        Args:
            recipient_phone (str): Recipient's phone number
            document_url (str): URL of the document
            document_path (str): Path to local document file
            filename (str): Display filename
            caption (str): Document caption

        Returns:
            dict: Response containing message ID and success status
        """
        try:
            recipient_phone = recipient_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            if document_path and not document_url:
                full_path = os.path.join(self.WORKING_DIRECTORY, document_path)
                if not os.path.exists(full_path):
                    if os.path.exists(document_path):
                        full_path = document_path
                    else:
                        return {"success": False, "error": f"Document not found: {document_path}"}
                
                # Upload media
                with open(full_path, "rb") as f:
                    upload_result = self._make_request(
                        "POST",
                        f"{self.phone_number_id}/media",
                        data={"messaging_product": "whatsapp"},
                        files={"file": f},
                    )
                
                if "error" in upload_result:
                    return {"success": False, "error": upload_result["error"]}
                
                media_id = upload_result.get("id")
                
                document_data = {"id": media_id}
            else:
                document_data = {"link": document_url}
            
            if filename:
                document_data["filename"] = filename
            if caption:
                document_data["caption"] = caption[:1024]
            
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_phone,
                "type": "document",
                "document": document_data,
            }
            
            result = self._make_request("POST", f"{self.phone_number_id}/messages", data)
            
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id", ""),
            }

        except Exception as e:
            logging.error(f"Error sending WhatsApp document: {str(e)}")
            return {"success": False, "error": str(e)}

    async def send_template_message(
        self,
        recipient_phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: list = None,
    ):
        """
        Sends a pre-approved template message.
        Template messages can be sent outside the 24-hour window.

        Args:
            recipient_phone (str): Recipient's phone number
            template_name (str): Name of the approved template
            language_code (str): Template language code
            components (list): Template components (header, body, buttons variables)

        Returns:
            dict: Response containing message ID and success status
        """
        try:
            recipient_phone = recipient_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                },
            }
            
            if components:
                data["template"]["components"] = components
            
            result = self._make_request("POST", f"{self.phone_number_id}/messages", data)
            
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id", ""),
            }

        except Exception as e:
            logging.error(f"Error sending template message: {str(e)}")
            return {"success": False, "error": str(e)}

    async def send_interactive_buttons(
        self,
        recipient_phone: str,
        body_text: str,
        buttons: list,
        header_text: str = None,
        footer_text: str = None,
    ):
        """
        Sends an interactive message with reply buttons.

        Args:
            recipient_phone (str): Recipient's phone number
            body_text (str): Message body
            buttons (list): List of button dicts with 'id' and 'title' (max 3 buttons)
            header_text (str): Optional header text
            footer_text (str): Optional footer text

        Returns:
            dict: Response containing message ID and success status
        """
        try:
            recipient_phone = recipient_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            # Format buttons (max 3, title max 20 chars)
            formatted_buttons = []
            for i, btn in enumerate(buttons[:3]):
                formatted_buttons.append({
                    "type": "reply",
                    "reply": {
                        "id": btn.get("id", f"btn_{i}"),
                        "title": btn.get("title", f"Button {i+1}")[:20],
                    }
                })
            
            interactive = {
                "type": "button",
                "body": {"text": body_text[:1024]},
                "action": {"buttons": formatted_buttons},
            }
            
            if header_text:
                interactive["header"] = {"type": "text", "text": header_text[:60]}
            if footer_text:
                interactive["footer"] = {"text": footer_text[:60]}
            
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_phone,
                "type": "interactive",
                "interactive": interactive,
            }
            
            result = self._make_request("POST", f"{self.phone_number_id}/messages", data)
            
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id", ""),
            }

        except Exception as e:
            logging.error(f"Error sending interactive buttons: {str(e)}")
            return {"success": False, "error": str(e)}

    async def send_interactive_list(
        self,
        recipient_phone: str,
        body_text: str,
        button_text: str,
        sections: list,
        header_text: str = None,
        footer_text: str = None,
    ):
        """
        Sends an interactive list message.

        Args:
            recipient_phone (str): Recipient's phone number
            body_text (str): Message body
            button_text (str): Text for the list button
            sections (list): List of section dicts with 'title' and 'rows'
            header_text (str): Optional header text
            footer_text (str): Optional footer text

        Returns:
            dict: Response containing message ID and success status
        """
        try:
            recipient_phone = recipient_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            # Format sections (max 10 sections, 10 rows each)
            formatted_sections = []
            for section in sections[:10]:
                formatted_rows = []
                for row in section.get("rows", [])[:10]:
                    formatted_rows.append({
                        "id": row.get("id", ""),
                        "title": row.get("title", "")[:24],
                        "description": row.get("description", "")[:72],
                    })
                formatted_sections.append({
                    "title": section.get("title", "")[:24],
                    "rows": formatted_rows,
                })
            
            interactive = {
                "type": "list",
                "body": {"text": body_text[:1024]},
                "action": {
                    "button": button_text[:20],
                    "sections": formatted_sections,
                },
            }
            
            if header_text:
                interactive["header"] = {"type": "text", "text": header_text[:60]}
            if footer_text:
                interactive["footer"] = {"text": footer_text[:60]}
            
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_phone,
                "type": "interactive",
                "interactive": interactive,
            }
            
            result = self._make_request("POST", f"{self.phone_number_id}/messages", data)
            
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id", ""),
            }

        except Exception as e:
            logging.error(f"Error sending interactive list: {str(e)}")
            return {"success": False, "error": str(e)}

    async def mark_message_read(self, message_id: str):
        """
        Marks a message as read.

        Args:
            message_id (str): ID of the message to mark as read

        Returns:
            dict: Success status
        """
        try:
            data = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            }
            
            result = self._make_request("POST", f"{self.phone_number_id}/messages", data)
            
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            return {"success": True}

        except Exception as e:
            logging.error(f"Error marking message as read: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_business_profile(self):
        """
        Gets the WhatsApp Business profile information.

        Returns:
            dict: Business profile information
        """
        try:
            result = self._make_request(
                "GET",
                f"{self.phone_number_id}/whatsapp_business_profile",
                {"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
            )
            
            if "error" in result:
                return {"error": result["error"]}
            
            data = result.get("data", [{}])[0]
            return {
                "about": data.get("about", ""),
                "address": data.get("address", ""),
                "description": data.get("description", ""),
                "email": data.get("email", ""),
                "profile_picture_url": data.get("profile_picture_url", ""),
                "websites": data.get("websites", []),
                "vertical": data.get("vertical", ""),
            }

        except Exception as e:
            logging.error(f"Error getting business profile: {str(e)}")
            return {"error": str(e)}

    async def update_business_profile(
        self,
        about: str = None,
        address: str = None,
        description: str = None,
        email: str = None,
        websites: list = None,
        vertical: str = None,
    ):
        """
        Updates the WhatsApp Business profile.

        Args:
            about (str): Short description (max 139 chars)
            address (str): Business address
            description (str): Business description (max 512 chars)
            email (str): Contact email
            websites (list): List of website URLs (max 2)
            vertical (str): Business category

        Returns:
            dict: Success status
        """
        try:
            data = {"messaging_product": "whatsapp"}
            
            if about:
                data["about"] = about[:139]
            if address:
                data["address"] = address
            if description:
                data["description"] = description[:512]
            if email:
                data["email"] = email
            if websites:
                data["websites"] = websites[:2]
            if vertical:
                data["vertical"] = vertical
            
            result = self._make_request(
                "POST",
                f"{self.phone_number_id}/whatsapp_business_profile",
                data,
            )
            
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            return {"success": True}

        except Exception as e:
            logging.error(f"Error updating business profile: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_media_url(self, media_id: str):
        """
        Gets the download URL for a media file.
        Media URLs are only valid for 5 minutes.

        Args:
            media_id (str): Media ID from received message

        Returns:
            dict: Media URL and metadata
        """
        try:
            result = self._make_request("GET", media_id)
            
            if "error" in result:
                return {"error": result["error"]}
            
            return {
                "url": result.get("url", ""),
                "mime_type": result.get("mime_type", ""),
                "file_size": result.get("file_size", 0),
                "sha256": result.get("sha256", ""),
            }

        except Exception as e:
            logging.error(f"Error getting media URL: {str(e)}")
            return {"error": str(e)}
