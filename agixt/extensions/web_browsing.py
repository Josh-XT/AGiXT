from typing import List, Union
import logging
import subprocess
import uuid
import sys
import os
import re

try:
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "beautifulsoup4==4.12.2"]
    )
    from bs4 import BeautifulSoup
try:
    from playwright.async_api import async_playwright
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    from playwright.async_api import async_playwright

# Additional dependencies
try:
    import pyotp
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyotp"])
    import pyotp
try:
    import cv2
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "opencv-python"])
    import cv2
try:
    import numpy as np
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])
    import numpy as np
try:
    from pyzbar.pyzbar import decode
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyzbar"])
    from pyzbar.pyzbar import decode
try:
    import pytesseract
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pytesseract"])
    import pytesseract

from Extensions import Extensions
from Websearch import search_the_web
import xml.etree.ElementTree as ET

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def escape_css_classname(classname: str) -> str:
    # Minimal example that replaces `:` and `/` with escaped versions
    # You can add more replacements if needed.
    return classname.replace(":", "\\:").replace("/", "\\/")


class web_browsing(Extensions):
    """
    The AGiXT Web Browsing extension enables sophisticated web interaction and data extraction.
    It provides high-level commands for:
    - Automated web navigation and interaction workflows
    - Structured data extraction and analysis
    - Form filling and submission
    - Authentication handling
    - Screenshot and visual analysis
    - Network request monitoring and manipulation

    The extension uses Playwright for reliable cross-browser automation and adds
    intelligent workflow management and error recovery on top.
    """

    def __init__(self, **kwargs):
        self.agent_name = kwargs.get("agent_name", "gpt4free")
        self.user_id = kwargs.get("user_id", "")
        self.conversation_name = kwargs.get("conversation_name", "")
        self.WORKING_DIRECTORY = kwargs.get(
            "conversation_directory", os.path.join(os.getcwd(), "WORKSPACE")
        )
        os.makedirs(self.WORKING_DIRECTORY, exist_ok=True)
        self.conversation_id = kwargs.get("conversation_id", "")
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.api_key = kwargs["api_key"] if "api_key" in kwargs else None
        self.activity_id = kwargs["activity_id"] if "activity_id" in kwargs else None
        self.output_url = kwargs["output_url"] if "output_url" in kwargs else None
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.commands = {
            "Interact with Webpage": self.interact_with_webpage,
        }
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.popup = None

    async def get_form_fields(self) -> str:
        """
        Enhanced method to detect form fields, handling modern web apps and dynamic content.
        """
        if self.page is None:
            return "Error: No page loaded."

        try:
            # Wait for network to be idle and page to stabilize
            await self.page.wait_for_load_state("networkidle", timeout=5000)

            # Use JavaScript to get all input fields, including those in shadow DOM
            fields = await self.page.evaluate(
                """() => {
                const getAllFields = (root) => {
                    let elements = [];
                    
                    // Get regular form fields
                    const formFields = root.querySelectorAll('input, select, textarea, button');
                    elements = [...elements, ...formFields];
                    
                    // Get shadow roots
                    const shadowHosts = root.querySelectorAll('*');
                    shadowHosts.forEach(host => {
                        if (host.shadowRoot) {
                            elements = [...elements, ...getAllFields(host.shadowRoot)];
                        }
                    });
                    
                    return elements;
                };
                
                const elements = getAllFields(document);
                return elements.map(el => ({
                    tagName: el.tagName.toLowerCase(),
                    type: el.type || '',
                    id: el.id || '',
                    name: el.name || '',
                    className: el.className || '',
                    placeholder: el.placeholder || '',
                    value: el.value || '',
                    isVisible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                    ariaLabel: el.getAttribute('aria-label') || '',
                    role: el.getAttribute('role') || '',
                    dataTestId: el.getAttribute('data-testid') || '',
                }));
            }"""
            )

            # Process fields into structured description
            structured_content = []

            # Group fields by type
            input_fields = [f for f in fields if f["tagName"] == "input"]
            select_fields = [f for f in fields if f["tagName"] == "select"]
            textarea_fields = [f for f in fields if f["tagName"] == "textarea"]
            button_fields = [
                f for f in fields if f["tagName"] == "button" or f["type"] == "submit"
            ]

            # Process input fields
            if input_fields:
                structured_content.append("\nInput Fields:")
                for field in input_fields:
                    if not field["isVisible"]:
                        continue

                    desc = f"Field: {field['type'] or 'text'}"
                    selectors = []

                    # Build selectors in order of specificity
                    if field["id"]:
                        selectors.append(f"#{field['id']}")
                    if field["name"]:
                        selectors.append(f"[name='{field['name']}']")
                    if field["className"]:
                        class_names = field["className"].split()
                        if class_names:
                            # Escape each class
                            escaped_classes = [
                                escape_css_classname(c) for c in class_names
                            ]
                            selectors.append("." + ".".join(escaped_classes))
                    if field["placeholder"]:
                        selectors.append(f"[placeholder='{field['placeholder']}']")
                    if field["ariaLabel"]:
                        selectors.append(f"[aria-label='{field['ariaLabel']}']")
                    if field["dataTestId"]:
                        selectors.append(f"[data-testid='{field['dataTestId']}']")

                    # Add field attributes to description
                    if field["name"]:
                        desc += f" (name: {field['name']})"
                    if field["placeholder"]:
                        desc += f" (placeholder: {field['placeholder']})"
                    if field["ariaLabel"]:
                        desc += f" (aria-label: {field['ariaLabel']})"

                    # Add selectors
                    desc += "\nSelectors (in order of reliability):"
                    for selector in selectors:
                        desc += f"\n  - {selector}"

                    structured_content.append(desc)

            # Process buttons
            if button_fields:
                structured_content.append("\nButtons:")
                for button in button_fields:
                    if not button["isVisible"]:
                        continue

                    selectors = []
                    desc = "Button"

                    # Build button selectors
                    if button["id"]:
                        selectors.append(f"#{button['id']}")
                    if button["className"]:
                        class_names = button["className"].split()
                        if class_names:
                            selectors.append("." + ".".join(class_names))
                    if button["type"] == "submit":
                        selectors.append("button[type='submit']")

                    # Add button attributes
                    if button["value"]:
                        desc += f" (value: {button['value']})"
                    if button["ariaLabel"]:
                        desc += f" (aria-label: {button['ariaLabel']})"

                    # Add selectors
                    desc += "\nSelectors (in order of reliability):"
                    for selector in selectors:
                        desc += f"\n  - {selector}"

                    structured_content.append(desc)

            # Format and return content
            return "\n".join(structured_content)

        except Exception as e:
            error_msg = f"Error detecting form fields: {str(e)}"
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                conversation_name=self.conversation_name,
            )
            return error_msg

    async def get_search_results(self, query: str) -> List[dict]:
        """
        Get search results from a search engine

        Args:
        query (str): The search query

        Returns:
        str: The search results
        """
        return await search_the_web(
            query=query,
            token=self.api_key,
            agent_name=self.agent_name,
            conversation_name=self.conversation_name,
        )

    async def navigate_to_url_with_playwright(
        self, url: str, headless: bool = True
    ) -> str:
        """
        Navigate to a URL using Playwright

        Args:
        url (str): The URL to navigate to
        headless (bool): Whether to run the browser in headless mode

        Returns:
        str: Confirmation message
        """
        try:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(headless=headless)
                self.context = await self.browser.new_context()
                self.page = await self.context.new_page()
            await self.page.goto(url)
            logging.info(f"Navigated to {url}")
            return f"Navigated to {url}"
        except Exception as e:
            logging.error(f"Error navigating to {url}: {str(e)}")
            return f"Error: {str(e)}"

    async def click_element_with_playwright(self, selector: str) -> str:
        """
        Click an element specified by a selector using Playwright

        Args:
        selector (str): The CSS selector of the element to click

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."
            await self.page.click(selector)
            logging.info(f"Clicked element with selector {selector}")
            return f"Clicked element with selector {selector}"
        except Exception as e:
            logging.error(f"Error clicking element {selector}: {str(e)}")
            return f"Error: {str(e)}"

    async def fill_input_with_playwright(self, selector: str, text: str) -> str:
        """
        Enhanced version of fill_input that tries multiple strategies
        """
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."

            # Try different selector variations
            selector_variations = [
                selector,
                f"input{selector}",  # Try with input prefix
                f"{selector}:not([type='hidden'])",  # Exclude hidden fields
                f"[name='{selector}']",  # Try as name attribute
                f"[placeholder='{selector}']",  # Try as placeholder
                f"input[name='{selector}']",  # Try as input with name
            ]

            # Try label-based selection
            label_element = await self.page.query_selector(f"label:has-text('{text}')")
            if label_element:
                label_for = await label_element.get_attribute("for")
                if label_for:
                    selector_variations.append(f"#{label_for}")

            success = False
            error_messages = []

            for sel in selector_variations:
                try:
                    # Wait briefly for the element
                    await self.page.wait_for_selector(sel, timeout=2000)

                    # Try to fill
                    await self.page.fill(sel, text)

                    # Verify the fill worked
                    element = await self.page.query_selector(sel)
                    if element:
                        value = await element.get_property("value")
                        actual_value = await value.json_value()
                        if actual_value == text:
                            success = True
                            break

                except Exception as e:
                    error_messages.append(f"Selector '{sel}' failed: {str(e)}")
                    continue

            if success:
                return f"Successfully filled input with text '{text}'"
            else:
                return f"Failed to fill input. Tried these selectors:\n" + "\n".join(
                    error_messages
                )

        except Exception as e:
            return f"Error: {str(e)}"

    async def select_option_with_playwright(self, selector: str, value: str) -> str:
        """
        Select an option from a dropdown menu specified by a selector using Playwright

        Args:
        selector (str): The CSS selector of the dropdown element
        value (str): The value or label of the option to select

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."
            await self.page.select_option(selector, value)
            logging.info(f"Selected option '{value}' in dropdown '{selector}'")
            return f"Selected option '{value}' in dropdown '{selector}'"
        except Exception as e:
            logging.error(f"Error selecting option {value} in {selector}: {str(e)}")
            return f"Error: {str(e)}"

    async def check_checkbox_with_playwright(self, selector: str) -> str:
        """
        Check a checkbox specified by a selector using Playwright

        Args:
        selector (str): The CSS selector of the checkbox

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."
            await self.page.check(selector)
            logging.info(f"Checked checkbox '{selector}'")
            return f"Checked checkbox '{selector}'"
        except Exception as e:
            logging.error(f"Error checking checkbox {selector}: {str(e)}")
            return f"Error: {str(e)}"

    async def handle_mfa_with_playwright(self, otp_selector: str) -> str:
        """
        Handle MFA by detecting QR code on the page, decoding it, and entering the TOTP code

        Args:
        otp_selector (str): The CSS selector where the OTP code should be entered

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."

            # Take a screenshot of the page
            screenshot = await self.page.screenshot()
            # Decode QR code from the screenshot
            nparr = np.frombuffer(screenshot, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            decoded_objects = decode(img)
            otp_uri = None
            for obj in decoded_objects:
                if obj.type == "QRCODE":
                    otp_uri = obj.data.decode("utf-8")
                    break
            if not otp_uri:
                return "Error: No QR code found on the page."
            # Extract secret key from OTP URI
            import re

            match = re.search(r"secret=([\w\d]+)", otp_uri)
            if match:
                secret_key = match.group(1)
                totp = pyotp.TOTP(secret_key)
                otp_token = totp.now()
                # Enter the OTP token into the input field
                await self.page.fill(otp_selector, otp_token)
                # Submit the form (you might need to adjust the selector)
                await self.page.click('button[type="submit"]')
                logging.info("MFA handled successfully.")
                return "MFA handled successfully."
            else:
                return "Error: Failed to extract secret key from OTP URI."
        except Exception as e:
            logging.error(f"Error handling MFA: {str(e)}")
            return f"Error: {str(e)}"

    async def handle_popup_with_playwright(self) -> str:
        """
        Handle a popup window, such as during an OAuth flow

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."

            popup = await self.page.wait_for_event("popup")
            self.popup = popup
            logging.info(f"Popup opened with URL: {popup.url}")
            # You can now interact with the popup as a new page
            # Example: await self.popup.fill("#email", "user@example.com")
            # Close the popup when done
            await self.popup.close()
            self.popup = None
            logging.info("Popup handled and closed successfully.")
            return "Popup handled successfully."
        except Exception as e:
            logging.error(f"Error handling popup: {str(e)}")
            return f"Error: {str(e)}"

    async def upload_file_with_playwright(self, selector: str, file_path: str) -> str:
        """
        Upload a file to a file input element specified by a selector using Playwright

        Args:
        selector (str): The CSS selector of the file input element
        file_path (str): The path to the file to upload

        Returns:
        str: Confirmation message
        """
        try:
            if not os.path.isfile(file_path):
                return f"Error: File '{file_path}' does not exist."
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."
            await self.page.set_input_files(selector, file_path)
            logging.info(f"Uploaded file '{file_path}' to input '{selector}'")
            return f"Uploaded file '{file_path}' to input '{selector}'"
        except Exception as e:
            logging.error(f"Error uploading file {file_path}: {str(e)}")
            return f"Error: {str(e)}"

    async def download_file_with_playwright(
        self, download_url: str, save_path: str
    ) -> str:
        """
        Download a file from a URL using Playwright

        Args:
        download_url (str): The URL of the file to download
        save_path (str): The path to save the downloaded file

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                await self.navigate_to_url_with_playwright(download_url)
            # Start the download
            download = await self.page.wait_for_event("download")
            # Save the file to the specified path
            await download.save_as(save_path)
            logging.info(f"Downloaded file to '{save_path}'")
            return f"Downloaded file to '{save_path}'"
        except Exception as e:
            logging.error(f"Error downloading file from {download_url}: {str(e)}")
            return f"Error: {str(e)}"

    async def go_back_with_playwright(self) -> str:
        """
        Navigate back in the browser history

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."
            await self.page.go_back()
            logging.info("Navigated back in browser history.")
            return "Navigated back in browser history."
        except Exception as e:
            logging.error(f"Error navigating back: {str(e)}")
            return f"Error: {str(e)}"

    async def go_forward_with_playwright(self) -> str:
        """
        Navigate forward in the browser history

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."
            await self.page.go_forward()
            logging.info("Navigated forward in browser history.")
            return "Navigated forward in browser history."
        except Exception as e:
            logging.error(f"Error navigating forward: {str(e)}")
            return f"Error: {str(e)}"

    async def wait_for_selector_with_playwright(
        self, selector: str, timeout: int = 30000
    ) -> str:
        """
        Wait for an element to appear on the page

        Args:
        selector (str): The CSS selector of the element
        timeout (int): Maximum time to wait in milliseconds

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."
            await self.page.wait_for_selector(selector, timeout=timeout)
            logging.info(f"Element '{selector}' appeared on the page.")
            return f"Element '{selector}' appeared on the page."
        except Exception as e:
            logging.error(f"Error waiting for selector {selector}: {str(e)}")
            return f"Error: {str(e)}"

    async def extract_table_with_playwright(
        self, selector: str
    ) -> Union[str, List[List[str]]]:
        """
        Extract data from a table element

        Args:
        selector (str): The CSS selector of the table element

        Returns:
        Union[str, List[List[str]]]: The extracted table data or error message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."
            table = await self.page.query_selector(selector)
            if not table:
                return f"Error: Table '{selector}' not found."
            rows = await table.query_selector_all("tr")
            table_data = []
            for row in rows:
                cells = await row.query_selector_all("th, td")
                cell_texts = [await cell.inner_text() for cell in cells]
                table_data.append(cell_texts)
            logging.info(f"Extracted data from table '{selector}'.")
            return table_data
        except Exception as e:
            logging.error(f"Error extracting table {selector}: {str(e)}")
            return f"Error: {str(e)}"

    async def assert_element_with_playwright(
        self, selector: str, expected_text: str
    ) -> str:
        """
        Assert that an element contains the expected text

        Args:
        selector (str): The CSS selector of the element
        expected_text (str): The expected text content

        Returns:
        str: Confirmation message or error message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."
            element = await self.page.query_selector(selector)
            if not element:
                return f"Error: Element '{selector}' not found."
            text_content = await element.inner_text()
            if expected_text in text_content:
                logging.info(
                    f"Assertion passed: '{expected_text}' is in element '{selector}'."
                )
                return (
                    f"Assertion passed: '{expected_text}' is in element '{selector}'."
                )
            else:
                logging.warning(
                    f"Assertion failed: '{expected_text}' not found in element '{selector}'."
                )
                return f"Assertion failed: '{expected_text}' not found in element '{selector}'."
        except Exception as e:
            logging.error(f"Error asserting element {selector}: {str(e)}")
            return f"Error: {str(e)}"

    async def evaluate_javascript_with_playwright(self, script: str) -> str:
        """
        Evaluate JavaScript code on the page using Playwright

        Args:
        script (str): The JavaScript code to evaluate

        Returns:
        str: The result of the script evaluation
        """
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."
            result = await self.page.evaluate(script)
            logging.info(f"Evaluated script: {script}")
            return f"Script result: {result}"
        except Exception as e:
            logging.error(f"Error evaluating script: {str(e)}")
            return f"Error: {str(e)}"

    async def close_browser_with_playwright(self) -> str:
        """
        Close the Playwright browser instance

        Returns:
        str: Confirmation message
        """
        try:
            if self.browser is not None:
                await self.browser.close()
                self.browser = None
                self.context = None
                self.page = None
                if self.playwright is not None:
                    await self.playwright.stop()
                    self.playwright = None
                logging.info("Browser closed successfully.")
                return "Browser closed successfully."
            else:
                logging.info("Browser is already closed.")
                return "Browser is already closed."
        except Exception as e:
            logging.error(f"Error closing browser: {str(e)}")
            return f"Error: {str(e)}"

    # Additional features

    async def set_viewport_with_playwright(self, width: int, height: int) -> str:
        """
        Set the viewport size of the browser

        Args:
        width (int): The width of the viewport
        height (int): The height of the viewport

        Returns:
        str: Confirmation message
        """
        try:
            if self.context is None:
                return "Error: Browser context not initialized."
            await self.context.set_viewport_size({"width": width, "height": height})
            logging.info(f"Viewport size set to {width}x{height}.")
            return f"Viewport size set to {width}x{height}."
        except Exception as e:
            logging.error(f"Error setting viewport size: {str(e)}")
            return f"Error: {str(e)}"

    async def emulate_device_with_playwright(self, device_name: str) -> str:
        """
        Emulate a device using predefined device settings

        Args:
        device_name (str): The name of the device to emulate (e.g., 'iPhone 12')

        Returns:
        str: Confirmation message
        """
        try:
            if self.playwright is None:
                return "Error: Playwright not started."
            device = self.playwright.devices.get(device_name)
            if not device:
                return f"Error: Device '{device_name}' not found."
            if self.context is not None:
                await self.context.close()
            self.context = await self.browser.new_context(**device)
            self.page = await self.context.new_page()
            logging.info(f"Emulating device '{device_name}'.")
            return f"Emulating device '{device_name}'."
        except Exception as e:
            logging.error(f"Error emulating device {device_name}: {str(e)}")
            return f"Error: {str(e)}"

    async def get_cookies_with_playwright(self) -> Union[str, List[dict]]:
        """
        Get cookies from the current page

        Returns:
        Union[str, List[dict]]: List of cookies or error message
        """
        try:
            if self.context is None:
                return "Error: Browser context not initialized."
            cookies = await self.context.cookies()
            logging.info("Retrieved cookies from the browser context.")
            return cookies
        except Exception as e:
            logging.error(f"Error getting cookies: {str(e)}")
            return f"Error: {str(e)}"

    async def set_cookies_with_playwright(self, cookies: List[dict]) -> str:
        """
        Set cookies in the browser context

        Args:
        cookies (List[dict]): List of cookie dictionaries

        Returns:
        str: Confirmation message
        """
        try:
            if self.context is None:
                return "Error: Browser context not initialized."
            await self.context.add_cookies(cookies)
            logging.info("Cookies set in the browser context.")
            return "Cookies set successfully."
        except Exception as e:
            logging.error(f"Error setting cookies: {str(e)}")
            return f"Error: {str(e)}"

    async def handle_dialog_with_playwright(
        self, action: str = "accept", prompt_text: str = ""
    ) -> str:
        """
        Handle JavaScript dialogs (alerts, confirms, prompts)

        Args:
        action (str): The action to perform ('accept' or 'dismiss')
        prompt_text (str): Text to enter into a prompt dialog

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."

            async def dialog_handler(dialog):
                if action == "accept":
                    await dialog.accept(prompt_text)
                    logging.info(f"Dialog accepted with text '{prompt_text}'.")
                else:
                    await dialog.dismiss()
                    logging.info("Dialog dismissed.")

            self.page.on("dialog", dialog_handler)
            return f"Dialog will be handled with action '{action}'."
        except Exception as e:
            logging.error(f"Error handling dialog: {str(e)}")
            return f"Error: {str(e)}"

    async def intercept_requests_with_playwright(
        self, url_pattern: str, action: str = "block"
    ) -> str:
        """
        Intercept network requests matching a pattern

        Args:
        url_pattern (str): The URL pattern to match
        action (str): The action to perform ('block', 'modify', 'continue')

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."

            async def route_handler(route, request):
                if action == "block":
                    await route.abort()
                    logging.info(f"Blocked request to {request.url}")
                elif action == "continue":
                    await route.continue_()
                    logging.info(f"Allowed request to {request.url}")
                # Add 'modify' action as needed

            await self.page.route(url_pattern, route_handler)
            return f"Requests matching '{url_pattern}' will be handled with action '{action}'."
        except Exception as e:
            logging.error(f"Error intercepting requests: {str(e)}")
            return f"Error: {str(e)}"

    async def take_screenshot_with_highlight_with_playwright(
        self, selector: str, save_path: str
    ) -> str:
        """
        Take a screenshot of the page with a specific element highlighted

        Args:
        selector (str): The CSS selector of the element to highlight
        save_path (str): The path to save the screenshot

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."
            # Add a highlight style to the element
            await self.page.evaluate(
                f"""
                const element = document.querySelector('{selector}');
                if (element) {{
                    element.style.border = '2px solid red';
                }}
            """
            )
            await self.page.screenshot(path=save_path, full_page=True)
            logging.info(
                f"Screenshot saved to '{save_path}' with element '{selector}' highlighted."
            )
            return f"Screenshot saved to '{save_path}' with element '{selector}' highlighted."
        except Exception as e:
            logging.error(f"Error taking screenshot with highlight: {str(e)}")
            return f"Error: {str(e)}"

    async def extract_text_from_image_with_playwright(
        self, image_selector: str
    ) -> Union[str, List[str]]:
        """
        Extract text from an image element using OCR

        Args:
        image_selector (str): The CSS selector of the image element

        Returns:
        Union[str, List[str]]: Extracted text or error message
        """
        try:
            if self.page is None:
                return "Error: No page loaded."
            element = await self.page.query_selector(image_selector)
            if not element:
                return f"Error: Image '{image_selector}' not found."
            # Take a screenshot of the image element
            image_bytes = await element.screenshot()
            # Use pytesseract to extract text
            from PIL import Image
            import io

            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)
            logging.info(f"Extracted text from image '{image_selector}'.")
            return text
        except Exception as e:
            logging.error(
                f"Error extracting text from image {image_selector}: {str(e)}"
            )
            return f"Error: {str(e)}"

    async def handle_step(self, step, current_url):
        """
        Handle execution of a single interaction step with enhanced form handling and logging
        """
        operation = step.find("operation").text
        selector = step.find("selector").text
        description = step.find("description").text
        value = step.find("value").text if step.find("value") is not None else None
        retry_info = step.find("retry")

        # For form operations, get detailed field information first
        if operation in ["fill", "select"]:
            form_fields = await self.get_form_fields()
            logging.info(f"Available form fields:\n{form_fields}")
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Form fields detected:\n{form_fields}",
                conversation_name=self.conversation_name,
            )

        # Take screenshot before action
        screenshot_path = os.path.join(
            self.WORKING_DIRECTORY, f"before_{uuid.uuid4()}.png"
        )
        await self.page.screenshot(path=screenshot_path, full_page=True)
        before_screenshot = os.path.basename(screenshot_path)

        # Log step with current URL and before screenshot
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{self.activity_id}] About to perform: {description} on [{current_url}]\n![Before Screenshot]({self.output_url}/{before_screenshot})",
            conversation_name=self.conversation_name,
        )

        # Initialize retry parameters
        max_attempts = 3
        alternate_selector = None
        fallback_operation = None

        if retry_info is not None:
            alt_selector_elem = retry_info.find("alternate_selector")
            if alt_selector_elem is not None:
                alternate_selector = alt_selector_elem.text

            fallback_op_elem = retry_info.find("fallback_operation")
            if fallback_op_elem is not None:
                fallback_operation = fallback_op_elem.text

            max_attempts_elem = retry_info.find("max_attempts")
            if max_attempts_elem is not None:
                max_attempts = int(max_attempts_elem.text)

        # Execute step with retries
        attempt = 0
        success = False
        last_error = None

        while attempt < max_attempts and not success:
            try:
                # Take screenshot before operation
                pre_op_screenshot_path = os.path.join(
                    self.WORKING_DIRECTORY, f"pre_op_{uuid.uuid4()}.png"
                )
                await self.page.screenshot(path=pre_op_screenshot_path, full_page=True)
                pre_op_screenshot = os.path.basename(pre_op_screenshot_path)

                # Log the current state before operation
                current_url = self.page.url
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Attempting {operation} (try {attempt + 1}/{max_attempts}) on [{current_url}]\n![Pre-Operation Screenshot]({self.output_url}/{pre_op_screenshot})",
                    conversation_name=self.conversation_name,
                )

                # Enhanced operation handling with more detailed feedback
                if operation == "click":
                    # Wait for element to be clickable
                    await self.page.wait_for_selector(
                        selector, state="visible", timeout=5000
                    )
                    await self.click_element_with_playwright(selector)
                    await self.page.wait_for_load_state("networkidle")

                elif operation == "fill":
                    # Enhanced fill operation with retries and validation
                    fill_result = await self.fill_input_with_playwright(selector, value)
                    if "Error" in fill_result:
                        raise Exception(fill_result)

                    # Verify the fill operation
                    element = await self.page.query_selector(selector)
                    if element:
                        element_value = await element.get_property("value")
                        actual_value = await element_value.json_value()
                        if actual_value != value:
                            raise Exception(
                                f"Fill verification failed. Expected '{value}' but got '{actual_value}'"
                            )

                elif operation == "select":
                    await self.select_option_with_playwright(selector, value)

                elif operation == "wait":
                    await self.wait_for_selector_with_playwright(selector)

                elif operation == "verify":
                    await self.assert_element_with_playwright(selector, value)

                elif operation == "screenshot":
                    await self.take_screenshot_with_highlight_with_playwright(
                        selector, value
                    )

                elif operation == "extract":
                    await self.extract_text_from_image_with_playwright(selector)

                elif operation == "download":
                    download_path = os.path.join(
                        self.WORKING_DIRECTORY, value or f"download_{uuid.uuid4()}"
                    )
                    await self.download_file_with_playwright(selector, download_path)
                    file_name = os.path.basename(download_path)

                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}] Downloaded file on [{current_url}]\nFile available at: {self.output_url}/{file_name}",
                        conversation_name=self.conversation_name,
                    )
                    return f"Downloaded file saved as: {self.output_url}/{file_name}"

                # Take screenshot after operation
                post_op_screenshot_path = os.path.join(
                    self.WORKING_DIRECTORY, f"post_op_{uuid.uuid4()}.png"
                )
                await self.page.screenshot(path=post_op_screenshot_path, full_page=True)
                post_op_screenshot = os.path.basename(post_op_screenshot_path)

                # Get updated URL after operation
                new_url = self.page.url

                # Log the completion of operation with before/after screenshots
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Successfully completed {operation} operation\nStarted on: [{current_url}]\nEnded on: [{new_url}]\n![Post-Operation Screenshot]({self.output_url}/{post_op_screenshot})",
                    conversation_name=self.conversation_name,
                )

                success = True

                # Generate page summary after successful operation
                new_content = await self.get_page_content()
                page_summary = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": f"""Please provide a concise summary of the current page state:
1. The main purpose or topic of the page
2. Any key information, data, or options present
3. Available interaction elements (forms, buttons, etc.)
4. Any error messages or important notices
5. The result of the last operation ({operation})

Page Content:
{new_content}""",
                        "conversation_name": self.conversation_name,
                        "log_user_input": False,
                        "log_output": False,
                        "tts": False,
                        "analyze_user_input": False,
                        "disable_commands": True,
                        "browse_links": False,
                        "websearch": False,
                    },
                )

                return f"Operation successful: {page_summary}"

            except Exception as e:
                last_error = str(e)
                attempt += 1

                # Log the error attempt
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Operation {operation} failed (attempt {attempt}/{max_attempts}): {last_error}",
                    conversation_name=self.conversation_name,
                )

                # Try alternate selector if available
                if not success and alternate_selector and attempt < max_attempts:
                    try:
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] Trying alternate selector: {alternate_selector}",
                            conversation_name=self.conversation_name,
                        )

                        if operation == "click":
                            await self.click_element_with_playwright(alternate_selector)
                            await self.page.wait_for_load_state("networkidle")
                        elif operation == "fill":
                            await self.fill_input_with_playwright(
                                alternate_selector, value
                            )
                        elif operation == "select":
                            await self.select_option_with_playwright(
                                alternate_selector, value
                            )
                        elif operation == "wait":
                            await self.wait_for_selector_with_playwright(
                                alternate_selector
                            )
                        elif operation == "verify":
                            await self.assert_element_with_playwright(
                                alternate_selector, value
                            )

                        success = True

                        # Take screenshot after successful alternate action
                        screenshot_path = os.path.join(
                            self.WORKING_DIRECTORY, f"after_alt_{uuid.uuid4()}.png"
                        )
                        await self.page.screenshot(path=screenshot_path, full_page=True)
                        after_screenshot = os.path.basename(screenshot_path)

                        # Get updated URL and content
                        current_url = self.page.url
                        new_content = await self.get_page_content()
                        page_summary = self.ApiClient.prompt_agent(
                            agent_name=self.agent_name,
                            prompt_name="Think About It",
                            prompt_args={
                                "user_input": f"""Please provide a concise summary of the current page state after using alternate selector:
1. The main purpose or topic of the page
2. Any key information, data, or options present
3. Available interaction elements (forms, buttons, etc.)
4. Any error messages or important notices

Page Content:
{new_content}""",
                                "conversation_name": self.conversation_name,
                                "log_user_input": False,
                                "log_output": False,
                                "tts": False,
                                "analyze_user_input": False,
                                "disable_commands": True,
                                "browse_links": False,
                                "websearch": False,
                            },
                        )

                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] Successfully completed with alternate selector: {description} on [{current_url}]\n![After Screenshot]({self.output_url}/{after_screenshot})\n\n{page_summary}",
                            conversation_name=self.conversation_name,
                        )
                        return "Success with alternate selector"

                    except Exception as alt_e:
                        last_error = f"Alternative selector failed: {str(alt_e)}"

        if not success:
            error_msg = f"Failed to complete {operation} after {max_attempts} attempts. Last error: {last_error}"

            # Take error screenshot
            screenshot_path = os.path.join(
                self.WORKING_DIRECTORY, f"error_{uuid.uuid4()}.png"
            )
            await self.page.screenshot(path=screenshot_path, full_page=True)
            error_screenshot = os.path.basename(screenshot_path)

            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg} on [{current_url}]\n![Error Screenshot]({self.output_url}/{error_screenshot})",
                conversation_name=self.conversation_name,
            )
            return error_msg

    async def interact_with_webpage(self, url: str, task: str):
        """
        Execute a complex web interaction workflow. This command should be used when:
        - Navigating through multi-step web processes
        - Filling out forms and clicking through pages
        - Handling login flows or authentication
        - Extracting information across multiple pages
        - Automating web-based tasks

        The assistant will:
        - Plan the interaction steps needed
        - Execute each step in sequence with error recovery
        - Handle retries with alternative approaches
        - Maintain session state throughout
        - Verify successful completion
        - Log detailed subactivities for each interaction
        - Generate summaries of important page content
        - Unless otherwise specified, the assistant prefers Brave for search.

        Args:
        url (str): Starting URL for the workflow
        task (str): Natural language description of what needs to be accomplished

        Returns:
        str: Description of actions taken and results
        """

        def safe_get_text(element, default="") -> str:
            """Safely get .text from XML element."""
            if element is None or element.text is None:
                return default
            return element.text.strip()

        def extract_interaction_block(response: str) -> str:
            """
            Extract and clean the <interaction>...</interaction> XML block from an LLM response.
            Raises ValueError if no <interaction> block is found.
            """
            match = re.search(r"<interaction>.*?</interaction>", response, re.DOTALL)
            if not match:
                raise ValueError("No <interaction> block found in the response.")
            xml_block = match.group(0).strip()

            # Minor whitespace cleanups
            xml_block = re.sub(r"\s+<", "<", xml_block)
            xml_block = re.sub(r">\s+", ">", xml_block)
            xml_block = re.sub(r"\s+(?=</)", "", xml_block)
            xml_block = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_block
            return xml_block

        # 1) If Playwright not started, navigate to the URL
        if self.page is None:
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Navigating to [{url}]",
                conversation_name=self.conversation_name,
            )
            await self.navigate_to_url_with_playwright(url=url, headless=True)

        # We'll keep track of each "top-level" iteration, in case
        # it takes multiple page transitions to finish the overall task.
        iteration_count = 0
        overall_results = []
        max_iterations = 10

        while iteration_count < max_iterations:
            iteration_count += 1

            current_url = self.page.url
            # Gather page content and available form fields for the plan
            current_page_content = await self.get_page_content()
            form_fields = await self.get_form_fields()

            # Extract a short list of "available selectors" from the form_fields text
            available_selectors = []
            for line in form_fields.split("\n"):
                if "  - " in line:  # lines with '  - ' are selector lines
                    selector = line.split("  - ")[-1].strip()
                    # Keep only basic selectors from known attributes
                    if (
                        selector.startswith("#")
                        or selector.startswith("[name=")
                        or selector.startswith("[placeholder=")
                        or selector == "button[type='submit']"
                    ):
                        available_selectors.append(selector)

            # Create context that includes form field information
            planning_context = f"""Current webpage state:

CURRENT PAGE URL: {current_url}

AVAILABLE SELECTORS (ONLY these may be used):
{os.linesep.join(available_selectors)}

DETECTED FORM FIELDS:
{form_fields}

CURRENT PAGE CONTENT:
{current_page_content}

TASK TO COMPLETE:
{task}

STRICT RULES - READ CAREFULLY:
1. You may ONLY use selectors that are EXPLICITLY listed above
2. Do NOT use complex class selectors
3. Prefer simple selectors like #email, #name, button[type='submit']
4. Each selector must be COPIED EXACTLY as shown
5. If a field isn't listed above, you CANNOT use it

IMPORTANT INSTRUCTIONS:
1. You can ONLY use selectors that are explicitly listed above under "AVAILABLE FORM FIELDS AND SELECTORS"
2. Do not assume or invent selectors that aren't listed
3. If a field you need isn't available, use the 'wait' operation to wait for it to appear
4. Each step must use an element that currently exists on the page
5. Only plan steps for the current page state! Do not try to plan ahead, you will be asked to plan the next steps on the next page.

Generate an interaction plan using ONLY the available selectors above.

YOUR RESPONSE MUST BE A SINGLE, VALID XML BLOCK LIKE THIS in the <answer> tag:
<interaction>
    <step>
        <operation>click|fill|wait|verify</operation>
        <selector>EXACT selector from available fields</selector>
        <value>Value if needed</value>
        <description>Human-readable description</description>
    </step>
</interaction>

Follow these rules:
1. Only use selectors that are EXPLICITLY listed in the form fields section
2. Each step must check if needed elements exist before proceeding
3. If a required field isn't available yet, add a wait step
4. Verify each major state change

Example of good interaction plan:
<interaction>
    <step>
        <operation>fill</operation>
        <selector>#email</selector>
        <value>user@example.com</value>
        <description>Fill in email field</description>
    </step>
    <step>
        <operation>wait</operation>
        <selector>#continue-button</selector>
        <value>2000</value>
        <description>Wait for continue button to appear</description>
    </step>
</interaction>

Example of CORRECT selectors:
- #email
- #name
- button[type='submit']
- [placeholder='Enter your email']
Example of INCORRECT selectors:
- Complex class selectors
- Made up IDs
- Modified selectors
- Selectors not in the available list
"""
            # Log the iteration
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=(
                    f"[SUBACTIVITY][{self.activity_id}] Iteration {iteration_count}.\n"
                    f"URL: {current_url}\n"
                    f"Available Selectors:\n{os.linesep.join(available_selectors)}\n"
                    f"Form Fields:\n{form_fields}"
                ),
                conversation_name=self.conversation_name,
            )

            # 2) Prompt the LLM for the plan
            try:
                raw_plan = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": planning_context,
                        "conversation_name": self.conversation_name,
                        "log_user_input": False,
                        "log_output": False,
                        "tts": False,
                        "analyze_user_input": False,
                        "disable_commands": True,
                        "browse_links": False,
                        "websearch": False,
                    },
                )
                # Extract the <interaction> block
                interaction_xml = extract_interaction_block(raw_plan)

            except Exception as e:
                err_msg = (
                    f"No valid interaction plan on iteration {iteration_count}: {e}"
                )
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {err_msg}",
                    conversation_name=self.conversation_name,
                )
                overall_results.append(err_msg)
                break

            # 3) Parse steps
            try:
                root = ET.fromstring(interaction_xml)
                steps = root.findall(".//step")
                if not steps:
                    msg = "No steps found in the plan. Stopping."
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}] {msg}",
                        conversation_name=self.conversation_name,
                    )
                    overall_results.append(msg)
                    break

                # If the first step says "done", we are finished
                if safe_get_text(steps[0].find("operation")).lower() == "done":
                    msg = "Agent signaled task completion."
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}] {msg}",
                        conversation_name=self.conversation_name,
                    )
                    overall_results.append(msg)
                    break

                # 4) Execute each step in the plan
                step_idx = 0
                while step_idx < len(steps):
                    step_elem = steps[step_idx]
                    operation = safe_get_text(step_elem.find("operation")).lower()
                    selector = safe_get_text(step_elem.find("selector"))
                    value = safe_get_text(step_elem.find("value"))
                    description = safe_get_text(
                        step_elem.find("description"), "No desc"
                    )

                    # Log that we are about to attempt a step
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=(
                            f"[SUBACTIVITY][{self.activity_id}] Attempting step {step_idx + 1}/{len(steps)}: "
                            f"{operation.upper()} (selector: {selector}, value: {value})"
                        ),
                        conversation_name=self.conversation_name,
                    )

                    # Take a "before" screenshot
                    before_screenshot_path = os.path.join(
                        self.WORKING_DIRECTORY, f"before_{uuid.uuid4()}.png"
                    )
                    await self.page.screenshot(
                        path=before_screenshot_path, full_page=True
                    )
                    before_image_name = os.path.basename(before_screenshot_path)

                    # Try the step
                    step_success = False
                    try:
                        if operation == "click":
                            if not selector:
                                raise ValueError(
                                    "No selector provided for click operation."
                                )
                            await self.page.wait_for_selector(
                                selector, state="visible", timeout=5000
                            )
                            await self.click_element_with_playwright(selector)
                            await self.page.wait_for_load_state("networkidle")

                        elif operation == "fill":
                            if not selector:
                                raise ValueError("No selector for fill operation.")
                            if not value:
                                raise ValueError("No 'value' for fill operation.")
                            await self.page.wait_for_selector(
                                selector, state="visible", timeout=5000
                            )
                            await self.fill_input_with_playwright(selector, value)

                        elif operation == "wait":
                            # If numeric, treat as ms timeout
                            if value.isdigit():
                                ms_val = int(value)
                                await self.page.wait_for_timeout(ms_val)
                            else:
                                # Wait for a selector to appear
                                await self.wait_for_selector_with_playwright(
                                    value or selector
                                )

                        elif operation == "verify":
                            # Simple check that the selector's text includes 'value'
                            await self.assert_element_with_playwright(selector, value)

                        elif operation == "done":
                            # Just in case it appears in the middle
                            overall_results.append("Agent indicated done mid-plan.")
                            break

                        else:
                            raise ValueError(f"Unknown operation: {operation}")

                        # If we got here, step succeeded
                        step_success = True

                    except Exception as step_error:
                        # Step failed. Let's do the self-correcting approach:
                        error_details = (
                            f"STEP FAILURE: operation='{operation}', selector='{selector}', "
                            f"value='{value}' => {step_error}"
                        )
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_details}",
                            conversation_name=self.conversation_name,
                        )
                        overall_results.append(error_details)

                        # -- Re-prompt the LLM for a fix plan. Provide the same context, plus the error:
                        fix_context = f"""
We attempted this step:
Operation: {operation}
Selector: {selector}
Value: {value}

But it failed with error: {step_error}

Current page content:
{await self.get_page_content()}

Available selectors:
{os.linesep.join(available_selectors)}


STRICT RULES - READ CAREFULLY:
1. You may ONLY use selectors that are EXPLICITLY listed above
2. Do NOT use complex class selectors
3. Prefer simple selectors like #email, #name, button[type='submit']
4. Each selector must be COPIED EXACTLY as shown
5. If a field isn't listed above, you CANNOT use it

IMPORTANT INSTRUCTIONS:
1. You can ONLY use selectors that are explicitly listed above under "AVAILABLE FORM FIELDS AND SELECTORS"
2. Do not assume or invent selectors that aren't listed
3. If a field you need isn't available, use the 'wait' operation to wait for it to appear
4. Each step must use an element that currently exists on the page
5. Only plan steps for the current page state! Do not try to plan ahead, you will be asked to plan the next steps on the next page.

Generate an interaction plan using ONLY the available selectors above.

YOUR RESPONSE MUST BE A SINGLE, VALID XML BLOCK LIKE THIS in the <answer> tag:
<interaction>
    <step>
        <operation>click|fill|wait|verify</operation>
        <selector>EXACT selector from available fields</selector>
        <value>Value if needed</value>
        <description>Human-readable description</description>
    </step>
</interaction>

Follow these rules:
1. Only use selectors that are EXPLICITLY listed in the form fields section
2. Each step must check if needed elements exist before proceeding
3. If a required field isn't available yet, add a wait step
4. Verify each major state change

Example of good interaction plan:
<interaction>
    <step>
        <operation>fill</operation>
        <selector>#email</selector>
        <value>user@example.com</value>
        <description>Fill in email field</description>
    </step>
    <step>
        <operation>wait</operation>
        <selector>#continue-button</selector>
        <value>2000</value>
        <description>Wait for continue button to appear</description>
    </step>
</interaction>

Example of CORRECT selectors:
- #email
- #name
- button[type='submit']
- [placeholder='Enter your email']
Example of INCORRECT selectors:
- Complex class selectors
- Made up IDs
- Modified selectors
- Selectors not in the available list

Please provide a CORRECTIVE plan in <interaction>...</interaction> format,
with steps to fix or retry. If you are done, use <operation>done</operation>.
"""
                        try:
                            fix_response = self.ApiClient.prompt_agent(
                                agent_name=self.agent_name,
                                prompt_name="Think About It",
                                prompt_args={
                                    "user_input": fix_context,
                                    "conversation_name": self.conversation_name,
                                    "log_user_input": False,
                                    "log_output": False,
                                    "tts": False,
                                    "analyze_user_input": False,
                                    "disable_commands": True,
                                    "browse_links": False,
                                    "websearch": False,
                                },
                            )
                            # Parse the fix plan
                            fix_xml = extract_interaction_block(fix_response)
                            fix_root = ET.fromstring(fix_xml)
                            fix_steps = fix_root.findall(".//step")
                            if not fix_steps:
                                raise ValueError("No <step> found in corrective plan.")

                            # If the first step says "done", we're done
                            if (
                                safe_get_text(fix_steps[0].find("operation")).lower()
                                == "done"
                            ):
                                msg = "Corrective plan indicates done. Stopping."
                                self.ApiClient.new_conversation_message(
                                    role=self.agent_name,
                                    message=f"[SUBACTIVITY][{self.activity_id}] {msg}",
                                    conversation_name=self.conversation_name,
                                )
                                overall_results.append(msg)
                                # End the entire process
                                return "\n".join(overall_results)

                            # Otherwise, REPLACE the failing step with the new fix steps
                            # and insert them at the current step index:
                            # Example approach:
                            steps = steps[:step_idx] + fix_steps + steps[step_idx + 1 :]
                            self.ApiClient.new_conversation_message(
                                role=self.agent_name,
                                message=f"[SUBACTIVITY][{self.activity_id}] Replacing failing step with corrective plan of {len(fix_steps)} steps.",
                                conversation_name=self.conversation_name,
                            )
                            # Don't increment step_idx, because we want to run the new step(s) in the next iteration
                            continue

                        except Exception as fix_ex:
                            # If we can't fix it, break out
                            fix_err_msg = f"Failed to apply corrective plan: {fix_ex}"
                            self.ApiClient.new_conversation_message(
                                role=self.agent_name,
                                message=(
                                    f"[SUBACTIVITY][{self.activity_id}][ERROR] "
                                    f"{fix_err_msg}"
                                ),
                                conversation_name=self.conversation_name,
                            )
                            overall_results.append(fix_err_msg)
                            # End the process or choose to keep going
                            return "\n".join(overall_results)

                    # If the step succeeded, we log success and move on
                    if step_success:
                        # After screenshot
                        after_screenshot_path = os.path.join(
                            self.WORKING_DIRECTORY, f"after_{uuid.uuid4()}.png"
                        )
                        await self.page.screenshot(
                            path=after_screenshot_path, full_page=True
                        )
                        after_image_name = os.path.basename(after_screenshot_path)

                        success_message = (
                            f"STEP SUCCESS: {operation.upper()} on {selector}\n"
                            f"Before: ![Before]({self.output_url}/{before_image_name})\n"
                            f"After:  ![After]({self.output_url}/{after_image_name})"
                        )
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] {success_message}",
                            conversation_name=self.conversation_name,
                        )
                        overall_results.append(success_message)

                    step_idx += 1  # Move to next step

            except Exception as parse_ex:
                parse_err_msg = f"Error parsing or executing steps on iteration {iteration_count}: {parse_ex}"
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {parse_err_msg}",
                    conversation_name=self.conversation_name,
                )
                overall_results.append(parse_err_msg)
                break

            # If we reach the end of steps, we loop again to see if there's more
            # to do (if the page changed, for instance).
            # If the agent is truly finished, it should produce <operation>done.
            # We do not forcibly break here because the agent might need multiple
            # interactions across pages.

        else:
            # If we exit the loop by hitting max_iterations
            stop_msg = f"Reached max_iterations ({max_iterations}) without 'done'."
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}][WARNING] {stop_msg}",
                conversation_name=self.conversation_name,
            )
            overall_results.append(stop_msg)

        return "\n".join(overall_results)

    def get_text_safely(self, element) -> str:
        """
        Safely extract text from a BeautifulSoup element, handling None values.

        Args:
        element: BeautifulSoup element to extract text from

        Returns:
        str: Extracted and cleaned text, or empty string if extraction fails
        """
        try:
            if element is None:
                return ""
            text = element.get_text()
            return text.strip() if text else ""
        except (AttributeError, TypeError):
            return ""

    async def get_page_content(self) -> str:
        """
        Get the content of the current page with special focus on interactive elements.
        Extracts and organizes:
        - All clickable elements (links, buttons)
        - Form inputs and their types
        - Interactive elements and their selectors
        - Other page content in structured format
        """
        try:
            if self.page is None:
                return "Error: No page loaded."

            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")
            structured_content = []

            # Extract title safely
            if soup.title and soup.title.string:
                title_text = soup.title.string.strip()
                if title_text:
                    structured_content.append(f"Page Title: {title_text}")

            # SECTION 1: Interactive Elements
            structured_content.append("\n=== INTERACTIVE ELEMENTS ===")

            # 1.1 Links with their text and selectors
            links = []
            for link in soup.find_all("a", href=True):
                try:
                    text = self.get_text_safely(link)
                    href = link.get("href", "")
                    if text and href:
                        # Build selector (try ID first, then other attributes)
                        if link.get("id"):
                            selector = f"#{link['id']}"
                        elif link.get("class"):
                            selector = f"a.{'.'.join(link['class'])}"
                        else:
                            # Create a selector based on text content
                            selector = f"a[href='{href}']"
                        links.append(f"Link: '{text}' -> Selector: '{selector}'")
                except Exception as e:
                    continue

            if links:
                structured_content.append("\nClickable Links:")
                structured_content.extend(links)

            # 1.2 Buttons with their text and selectors
            buttons = []
            for button in soup.find_all(
                ["button", 'input[type="button"]', 'input[type="submit"]']
            ):
                try:
                    text = self.get_text_safely(button) or button.get("value", "")
                    if text:
                        if button.get("id"):
                            selector = f"#{button['id']}"
                        elif button.get("class"):
                            selector = f"button.{'.'.join(button['class'])}"
                        else:
                            selector = f"button:has-text('{text}')"
                        buttons.append(f"Button: '{text}' -> Selector: '{selector}'")
                except Exception as e:
                    continue

            if buttons:
                structured_content.append("\nClickable Buttons:")
                structured_content.extend(buttons)

            # 1.3 Form Inputs with their details and selectors
            forms = soup.find_all("form")
            form_sections = []

            for form in forms:
                try:
                    form_info = []
                    if form.get("id"):
                        form_info.append(f"Form: #{form['id']}")
                    elif form.get("name"):
                        form_info.append(f"Form: {form['name']}")

                    # Extract all input fields with their selectors
                    for input_field in form.find_all(["input", "select", "textarea"]):
                        try:
                            field_type = input_field.get("type", "text")
                            field_name = input_field.get("name", "")
                            field_id = input_field.get("id", "")
                            placeholder = input_field.get("placeholder", "")

                            # Build the most reliable selector
                            if field_id:
                                selector = f"#{field_id}"
                            elif field_name:
                                selector = f"[name='{field_name}']"
                            elif placeholder:
                                selector = f"[placeholder='{placeholder}']"
                            else:
                                continue  # Skip if we can't create a reliable selector

                            # Build a descriptive string based on available attributes
                            desc = f"Input: {field_type}"
                            if field_name:
                                desc += f" (name: {field_name})"
                            if placeholder:
                                desc += f" (placeholder: {placeholder})"
                            desc += f" -> Selector: '{selector}'"

                            # Additional details for specific input types
                            if field_type == "select":
                                options = []
                                for option in input_field.find_all("option"):
                                    option_text = self.get_text_safely(option)
                                    if option_text:
                                        options.append(option_text)
                                if options:
                                    desc += f"\n    Options: {', '.join(options)}"

                            form_info.append(desc)
                        except Exception as e:
                            continue

                    if form_info:
                        form_sections.extend(form_info)
                        form_sections.append("")  # Add spacing between forms
                except Exception as e:
                    continue

            if form_sections:
                structured_content.append("\nForm Fields:")
                structured_content.extend(form_sections)

            # 1.4 Other Interactive Elements (e.g., custom elements, clickable divs)
            other_interactive = []
            for element in soup.find_all(
                class_=lambda x: x
                and any(
                    cls in str(x).lower()
                    for cls in ["clickable", "button", "interactive", "dropdown"]
                )
            ):
                try:
                    if element.name in [
                        "a",
                        "button",
                        "input",
                    ]:  # Skip elements we've already processed
                        continue

                    text = self.get_text_safely(element)
                    if text:
                        if element.get("id"):
                            selector = f"#{element['id']}"
                        elif element.get("class"):
                            selector = f".{'.'.join(element['class'])}"
                        else:
                            continue  # Skip if we can't create a reliable selector

                        other_interactive.append(
                            f"Interactive Element: '{text}' -> Selector: '{selector}'"
                        )
                except Exception as e:
                    continue

            if other_interactive:
                structured_content.append("\nOther Interactive Elements:")
                structured_content.extend(other_interactive)

            # SECTION 2: Regular Content (for context)
            structured_content.append("\n=== PAGE CONTENT ===")

            # Headers
            headers = []
            for level in range(1, 7):
                for header in soup.find_all(f"h{level}"):
                    text = self.get_text_safely(header)
                    if text:
                        headers.append(f"{'#' * level} {text}")
            if headers:
                structured_content.append("\nHeaders:")
                structured_content.extend(headers)

            # Main content sections
            main_content = soup.find("main") or soup.find("body")
            if main_content:
                content_sections = []
                for element in main_content.find_all(["p", "article", "section"]):
                    try:
                        # Skip if element is part of already processed structures
                        if element.find_parent("form") or element.find_parent("nav"):
                            continue

                        text = self.get_text_safely(element)
                        if text and len(text) > 20:  # Filter out tiny text fragments
                            text = " ".join(text.split())  # Normalize whitespace
                            content_sections.append(text)
                    except Exception as e:
                        continue

                if content_sections:
                    structured_content.append("\nMain Content:")
                    structured_content.extend(content_sections)

            # Clean up and finalize content
            final_content = "\n".join(filter(None, structured_content))
            final_content = re.sub(r"\n\s*\n", "\n\n", final_content)
            return final_content.strip()

        except Exception as e:
            error_msg = f"Error extracting page content: {str(e)}"
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                conversation_name=self.conversation_name,
            )
            return error_msg

    async def analyze_page_visually(self, description: str = "") -> str:
        """
        Take a screenshot of the current page and analyze it visually. This command should be used when:
        - Verifying visual elements or layout
        - Analyzing complex page structures
        - Debugging interaction issues
        - Checking for specific visual elements
        - Verifying page state after interactions

        Args:
        description (str): Natural language description of what to look for or verify

        Example Usage:
        <execute>
        <name>Analyze Page Visually</name>
        <description>Check if the login form appears correctly with both username and password fields</description>
        </execute>

        Returns:
        str: Analysis of the visual state of the page
        """
        try:
            if self.page is None:
                return "Error: No page loaded."

            # Take screenshot
            screenshot_path = os.path.join(
                self.WORKING_DIRECTORY, f"{uuid.uuid4()}.png"
            )
            await self.page.screenshot(path=screenshot_path, full_page=True)
            file_name = os.path.basename(screenshot_path)
            output_url = f"{self.output_url}/{file_name}" if self.output_url else ""
            # Get current URL for context
            current_url = self.page.url

            # Have the agent analyze the screenshot with the description as context
            analysis = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"""Analyze this webpage screenshot in the context of this task:

### Current URL
{current_url}

### Analysis Task
{description if description else "Provide a general analysis of the page's visual state"}

### Context
The screenshot has been taken to verify the page state during web interaction.

In your analysis, consider:
1. The presence and state of key UI elements
2. Any error messages or warnings
3. The overall layout and structure
4. Whether the page appears to be in the expected state
""",
                    "images": [output_url],
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )

            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Analyzed page visually: {analysis}",
                conversation_name=self.conversation_name,
            )

            return analysis

        except Exception as e:
            error_msg = f"Error analyzing page visually: {str(e)}"
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                conversation_name=self.conversation_name,
            )
            return error_msg
