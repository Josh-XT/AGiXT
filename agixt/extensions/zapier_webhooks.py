import logging
import requests
import json
from Extensions import Extensions
from Globals import getenv
from typing import Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Zapier Webhooks Extension for AGiXT

This extension enables triggering Zapier Zaps and Make (Integromat) scenarios
via webhooks, connecting AGiXT to 5000+ apps and services without individual
integrations.

No OAuth required - uses webhook URLs directly.

Required environment variables:

- ZAPIER_WEBHOOK_URL: Default Zapier webhook URL (optional, can be set per-command)

Setup:
1. In Zapier, create a Zap with "Webhooks by Zapier" as the trigger
2. Choose "Catch Hook" and copy the webhook URL
3. Set it as ZAPIER_WEBHOOK_URL or pass directly to commands
4. The Zap can then route to any of 5000+ Zapier-supported apps
"""


class zapier_webhooks(Extensions):
    """
    The Zapier Webhooks extension for AGiXT enables triggering automation
    workflows in Zapier, Make (Integromat), n8n, and other webhook-compatible
    automation platforms.

    This is a simple but powerful extension that acts as a bridge between
    AGiXT and thousands of third-party services through webhook-based
    automation platforms.

    No API keys or OAuth required - just webhook URLs.

    Setup:
    1. Create a Zapier Zap with "Webhooks by Zapier" trigger
    2. Copy the webhook URL
    3. Set ZAPIER_WEBHOOK_URL environment variable or pass URL directly
    """

    CATEGORY = "Productivity"
    friendly_name = "Zapier Webhooks"

    def __init__(self, ZAPIER_WEBHOOK_URL: str = "", **kwargs):
        self.default_webhook_url = ZAPIER_WEBHOOK_URL
        self.commands = {
            "Zapier - Trigger Webhook": self.trigger_webhook,
            "Zapier - Send Data to Webhook": self.send_data_to_webhook,
            "Zapier - Trigger Named Webhook": self.trigger_named_webhook,
            "Zapier - Get Webhook Status": self.get_webhook_status,
            "Zapier - Trigger Multiple Webhooks": self.trigger_multiple_webhooks,
        }

    async def trigger_webhook(
        self,
        webhook_url: str = "",
        message: str = "",
        event_type: str = "agixt_trigger",
    ):
        """
        Trigger a webhook with a simple message. Works with Zapier, Make, n8n,
        and any webhook-compatible automation platform.

        Args:
            webhook_url (str, optional): The webhook URL. Uses default ZAPIER_WEBHOOK_URL if empty.
            message (str): The message or data to send with the webhook.
            event_type (str, optional): Event type identifier. Default 'agixt_trigger'.

        Returns:
            str: Confirmation or error message.
        """
        try:
            url = webhook_url.strip() if webhook_url else self.default_webhook_url
            if not url:
                return "Error: No webhook URL provided and no default ZAPIER_WEBHOOK_URL configured."

            payload = {
                "event": event_type,
                "message": message,
                "source": "agixt",
            }

            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )

            if response.status_code in (200, 201, 202):
                return f"Webhook triggered successfully.\n- **URL:** {url[:50]}...\n- **Event:** {event_type}\n- **Status:** {response.status_code}"
            else:
                return f"Webhook returned status {response.status_code}: {response.text[:500]}"
        except requests.exceptions.Timeout:
            return "Error: Webhook request timed out after 30 seconds."
        except requests.exceptions.ConnectionError:
            return f"Error: Could not connect to webhook URL."
        except Exception as e:
            return f"Error triggering webhook: {str(e)}"

    async def send_data_to_webhook(
        self,
        webhook_url: str = "",
        data: str = "{}",
        method: str = "POST",
    ):
        """
        Send structured data to a webhook. The data parameter should be a JSON string.

        Args:
            webhook_url (str, optional): The webhook URL. Uses default if empty.
            data (str): JSON string of data to send. Default '{}'. Example: '{"name": "John", "email": "john@example.com"}'.
            method (str, optional): HTTP method - 'POST', 'PUT', 'PATCH'. Default 'POST'.

        Returns:
            str: Webhook response or error message.
        """
        try:
            url = webhook_url.strip() if webhook_url else self.default_webhook_url
            if not url:
                return "Error: No webhook URL provided and no default ZAPIER_WEBHOOK_URL configured."

            # Parse JSON data
            try:
                payload = json.loads(data) if isinstance(data, str) else data
            except json.JSONDecodeError as e:
                return f"Error: Invalid JSON data - {str(e)}"

            # Add source metadata
            if isinstance(payload, dict):
                payload["_source"] = "agixt"

            method = method.upper()
            if method not in ("POST", "PUT", "PATCH"):
                method = "POST"

            response = requests.request(
                method,
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )

            result = f"Webhook {method} completed.\n"
            result += f"- **Status:** {response.status_code}\n"

            try:
                resp_data = response.json()
                result += f"- **Response:** {json.dumps(resp_data, indent=2)[:500]}"
            except (json.JSONDecodeError, ValueError):
                resp_text = response.text[:500]
                if resp_text:
                    result += f"- **Response:** {resp_text}"

            return result
        except requests.exceptions.Timeout:
            return "Error: Webhook request timed out after 30 seconds."
        except Exception as e:
            return f"Error sending data to webhook: {str(e)}"

    async def trigger_named_webhook(
        self,
        name: str,
        webhook_url: str = "",
        data: str = "{}",
    ):
        """
        Trigger a webhook with a named event, useful for routing different types
        of automations through a single webhook endpoint.

        Args:
            name (str): A descriptive name for this automation trigger (e.g., 'new_lead', 'task_complete', 'alert').
            webhook_url (str, optional): The webhook URL. Uses default if empty.
            data (str, optional): Additional JSON data to include. Default '{}'. Example: '{"priority": "high"}'.

        Returns:
            str: Confirmation or error message.
        """
        try:
            url = webhook_url.strip() if webhook_url else self.default_webhook_url
            if not url:
                return "Error: No webhook URL provided and no default ZAPIER_WEBHOOK_URL configured."

            try:
                extra_data = json.loads(data) if isinstance(data, str) else data
            except json.JSONDecodeError:
                extra_data = {}

            payload = {
                "automation_name": name,
                "source": "agixt",
                **extra_data,
            }

            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )

            if response.status_code in (200, 201, 202):
                return f"Named webhook '{name}' triggered successfully.\n- **Status:** {response.status_code}"
            else:
                return f"Webhook returned status {response.status_code}: {response.text[:500]}"
        except Exception as e:
            return f"Error triggering named webhook: {str(e)}"

    async def get_webhook_status(self, webhook_url: str = ""):
        """
        Test a webhook URL by sending a ping/test request.

        Args:
            webhook_url (str, optional): The webhook URL to test. Uses default if empty.

        Returns:
            str: Webhook status/reachability information.
        """
        try:
            url = webhook_url.strip() if webhook_url else self.default_webhook_url
            if not url:
                return "Error: No webhook URL provided and no default ZAPIER_WEBHOOK_URL configured."

            payload = {
                "event": "ping",
                "source": "agixt",
                "test": True,
            }

            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )

            result = f"**Webhook Status:**\n\n"
            result += f"- **URL:** {url[:80]}{'...' if len(url) > 80 else ''}\n"
            result += f"- **Status Code:** {response.status_code}\n"
            result += (
                f"- **Reachable:** {'Yes' if response.status_code < 500 else 'No'}\n"
            )
            result += f"- **Response Time:** {response.elapsed.total_seconds():.2f}s\n"

            if response.status_code in (200, 201, 202):
                result += f"- **Result:** Webhook is active and accepting requests.\n"
            elif response.status_code == 410:
                result += f"- **Result:** Webhook URL has expired or been deleted.\n"
            elif response.status_code >= 400:
                result += f"- **Result:** Webhook returned an error.\n"

            return result
        except requests.exceptions.Timeout:
            return f"**Webhook Status:**\n- **URL:** {url[:80]}\n- **Result:** Timed out after 15 seconds. URL may be unreachable."
        except requests.exceptions.ConnectionError:
            return f"**Webhook Status:**\n- **URL:** {url[:80]}\n- **Result:** Connection failed. URL may be invalid or unreachable."
        except Exception as e:
            return f"Error testing webhook: {str(e)}"

    async def trigger_multiple_webhooks(
        self,
        webhook_urls: str,
        message: str = "",
        event_type: str = "agixt_broadcast",
    ):
        """
        Trigger multiple webhooks simultaneously. Useful for broadcasting events
        to multiple automation platforms at once.

        Args:
            webhook_urls (str): Comma-separated list of webhook URLs.
            message (str, optional): Message to send to all webhooks.
            event_type (str, optional): Event type identifier. Default 'agixt_broadcast'.

        Returns:
            str: Summary of results for each webhook.
        """
        try:
            urls = [u.strip() for u in webhook_urls.split(",") if u.strip()]
            if not urls:
                return "Error: No webhook URLs provided."

            payload = {
                "event": event_type,
                "message": message,
                "source": "agixt",
                "broadcast": True,
            }

            result = f"**Broadcast Results ({len(urls)} webhooks):**\n\n"
            success_count = 0
            fail_count = 0

            for url in urls:
                try:
                    response = requests.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=15,
                    )
                    if response.status_code in (200, 201, 202):
                        result += (
                            f"- **{url[:50]}...** - Success ({response.status_code})\n"
                        )
                        success_count += 1
                    else:
                        result += (
                            f"- **{url[:50]}...** - Failed ({response.status_code})\n"
                        )
                        fail_count += 1
                except Exception as e:
                    result += f"- **{url[:50]}...** - Error: {str(e)[:100]}\n"
                    fail_count += 1

            result += f"\n**Summary:** {success_count} succeeded, {fail_count} failed."
            return result
        except Exception as e:
            return f"Error broadcasting to webhooks: {str(e)}"
