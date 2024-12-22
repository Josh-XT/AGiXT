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
            "Get Web Search Results": self.get_search_results,
        }
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.popup = None

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
        Fill an input field specified by a selector using Playwright

        Args:
        selector (str): The CSS selector of the input field
        text (str): The text to fill into the input field

        Returns:
        str: Confirmation message
        """
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."
            await self.page.fill(selector, text)
            logging.info(f"Filled input {selector} with text '{text}'")
            return f"Filled input {selector} with text '{text}'"
        except Exception as e:
            logging.error(f"Error filling input {selector}: {str(e)}")
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

        Args:
        url (str): Starting URL for the workflow
        task (str): Natural language description of what needs to be accomplished

        Returns:
        str: Description of actions taken and results
        """
        # First check if we have an active session
        if self.page is None:
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Navigating to [{url}]",
                conversation_name=self.conversation_name,
            )
            await self.navigate_to_url_with_playwright(url=url, headless=True)
            # Get and summarize initial page content
            initial_content = await self.get_page_content()
            page_summary = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"""Please provide a concise summary of this page content that captures:
1. The main purpose or topic of the page
2. Any key information, data, or options present
3. Available interaction elements (forms, buttons, etc.)
4. Any error messages or important notices

Page Content:
{initial_content}""",
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
                message=f"[SUBACTIVITY][{self.activity_id}] Loaded initial page.\n{page_summary}",
                conversation_name=self.conversation_name,
            )

        # Build context of the current page state
        current_page_content = await self.get_page_content()
        current_url = self.page.url if self.page else "No page loaded"

        # Use AI to plan interaction steps
        interaction_plan = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"""Need to interact with a webpage to accomplish the following task:

### Starting URL
{url}

### Task to Complete
{task}

### Current Page State
Currently on: {current_url}

### Page Content
{current_page_content}

Please analyze the task and provide the necessary interaction steps using the following XML format inside an <answer> block:

<interaction>
<step>
    <operation>click|fill|select|wait|verify|screenshot|extract</operation>
    <selector>CSS selector or XPath</selector>
    <value>Value for fill/select operations if needed</value>
    <description>Human-readable description of this step's purpose</description>
    <retry>
        <alternate_selector>Alternative selector if primary fails</alternate_selector>
        <fallback_operation>Alternative operation type</fallback_operation>
        <max_attempts>3</max_attempts>
    </retry>
</step>
</interaction>

Important Guidelines:
1. Each <step> must include operation, selector, and description
2. Add <value> for fill/select operations
3. Include <retry> blocks for critical steps
4. Provide precise selectors using:
- Unique IDs when available
- Specific CSS selectors
- XPath as last resort
5. Consider page load timing
6. Add verification steps after important actions

Example:
<interaction>
<step>
    <operation>fill</operation>
    <selector>#email-input</selector>
    <value>user@example.com</value>
    <description>Filling in the email address field</description>
    <retry>
        <alternate_selector>input[type='email']</alternate_selector>
        <fallback_operation>fill</fallback_operation>
        <max_attempts>3</max_attempts>
    </retry>
</step>
</interaction>""",
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

        # Parse interaction steps
        try:
            root = ET.fromstring(interaction_plan)
            steps = root.findall(".//step")
            results = []

            for step in steps:
                operation = step.find("operation").text
                selector = step.find("selector").text
                description = step.find("description").text
                value = (
                    step.find("value").text if step.find("value") is not None else None
                )
                retry_info = step.find("retry")

                # Log the step we're about to attempt
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] {description} on [{current_url}]",
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
                        # Try primary operation
                        if operation == "click":
                            await self.click_element_with_playwright(selector)
                            # Wait for potential page load after click
                            await self.page.wait_for_load_state("networkidle")
                        elif operation == "fill":
                            await self.fill_input_with_playwright(selector, value)
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

                        success = True
                        results.append(
                            f"Successfully completed {operation} on {selector}"
                        )

                        # After successful operation, get updated page content and summarize
                        new_content = await self.get_page_content()
                        page_summary = self.ApiClient.prompt_agent(
                            agent_name=self.agent_name,
                            prompt_name="Think About It",
                            prompt_args={
                                "user_input": f"""Please provide a concise summary of this page content that captures:
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

                        # Log successful operation and page summary
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] Successfully completed: {description}\n{page_summary}",
                            conversation_name=self.conversation_name,
                        )

                    except Exception as e:
                        last_error = str(e)
                        attempt += 1

                        # Try alternate selector if available
                        if (
                            not success
                            and alternate_selector
                            and attempt < max_attempts
                        ):
                            try:
                                if operation == "click":
                                    await self.click_element_with_playwright(
                                        alternate_selector
                                    )
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
                                results.append(
                                    f"Successfully completed {operation} using alternate selector {alternate_selector}"
                                )

                                # Get and summarize page content after successful alternate attempt
                                new_content = await self.get_page_content()
                                page_summary = self.ApiClient.prompt_agent(
                                    agent_name=self.agent_name,
                                    prompt_name="Think About It",
                                    prompt_args={
                                        "user_input": f"""Please provide a concise summary of this page content that captures:
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

                                # Log successful alternate operation and page summary
                                self.ApiClient.new_conversation_message(
                                    role=self.agent_name,
                                    message=f"[SUBACTIVITY][{self.activity_id}] Successfully completed with alternate selector: {description}\n{page_summary}",
                                    conversation_name=self.conversation_name,
                                )
                                continue

                            except Exception as alt_e:
                                last_error = (
                                    f"Alternative selector failed: {str(alt_e)}"
                                )

                        # Try fallback operation if available
                        if (
                            not success
                            and fallback_operation
                            and attempt < max_attempts
                        ):
                            try:
                                if fallback_operation == "click":
                                    await self.click_element_with_playwright(selector)
                                    await self.page.wait_for_load_state("networkidle")
                                elif fallback_operation == "fill":
                                    await self.fill_input_with_playwright(
                                        selector, value
                                    )
                                elif fallback_operation == "select":
                                    await self.select_option_with_playwright(
                                        selector, value
                                    )
                                elif fallback_operation == "wait":
                                    await self.wait_for_selector_with_playwright(
                                        selector
                                    )
                                elif fallback_operation == "verify":
                                    await self.assert_element_with_playwright(
                                        selector, value
                                    )

                                success = True
                                results.append(
                                    f"Successfully completed fallback operation {fallback_operation}"
                                )

                                # Get and summarize page content after successful fallback
                                new_content = await self.get_page_content()
                                page_summary = self.ApiClient.prompt_agent(
                                    agent_name=self.agent_name,
                                    prompt_name="Think About It",
                                    prompt_args={
                                        "user_input": f"""Please provide a concise summary of this page content that captures:
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

                                # Log successful fallback operation and page summary
                                self.ApiClient.new_conversation_message(
                                    role=self.agent_name,
                                    message=f"[SUBACTIVITY][{self.activity_id}] Successfully completed with fallback operation: {description}\n{page_summary}",
                                    conversation_name=self.conversation_name,
                                )
                                continue

                            except Exception as fallback_e:
                                last_error = (
                                    f"Fallback operation failed: {str(fallback_e)}"
                                )

                        # If on last attempt and still not successful
                        if attempt == max_attempts and not success:
                            error_msg = f"Failed to complete {operation} after {max_attempts} attempts. Last error: {last_error}"
                            self.ApiClient.new_conversation_message(
                                role=self.agent_name,
                                message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                                conversation_name=self.conversation_name,
                            )
                            return error_msg

            # Log final success message
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Successfully completed all web interactions for task: {task}",
                conversation_name=self.conversation_name,
            )

            return "Successfully completed webpage interaction:\n" + "\n".join(results)

        except Exception as e:
            error_msg = f"Error during webpage interaction: {str(e)}"
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                conversation_name=self.conversation_name,
            )
            return error_msg

    async def get_page_content(self) -> str:
        """
        Get the content of the current page in a well-structured format using BeautifulSoup.
        Extracts and organizes:
        - Page title and headers
        - Main content sections
        - Navigation elements
        - Forms and input fields
        - Links and buttons
        - Lists and tables
        - Error messages and notifications

        Returns:
        str: Structured text content of the current page
        """
        try:
            if self.page is None:
                return "Error: No page loaded."

            # Get the page HTML
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove unwanted elements
            for element in soup.find_all(
                ["script", "style", "meta", "link", "noscript"]
            ):
                element.decompose()

            structured_content = []

            # Extract title
            if soup.title:
                structured_content.append(f"Page Title: {soup.title.string.strip()}")

            # Extract headers hierarchically
            headers = []
            for level in range(1, 7):
                for header in soup.find_all(f"h{level}"):
                    text = header.get_text().strip()
                    if text:
                        headers.append(f"{'#' * level} {text}")
            if headers:
                structured_content.append("\nHeaders:")
                structured_content.extend(headers)

            # Extract main content
            main_content = soup.find("main")
            if not main_content:
                main_content = soup.find("body")

            # Extract forms and inputs
            forms = soup.find_all("form")
            if forms:
                structured_content.append("\nForms and Inputs:")
                for form in forms:
                    form_info = []
                    if form.get("id"):
                        form_info.append(f"Form ID: {form['id']}")
                    if form.get("action"):
                        form_info.append(f"Action: {form['action']}")

                    # Extract input fields
                    inputs = form.find_all(["input", "select", "textarea"])
                    for input_field in inputs:
                        input_type = input_field.get("type", "text")
                        input_name = input_field.get("name", "unnamed")
                        input_id = input_field.get("id", "")
                        field_info = f"- {input_type} field"
                        if input_name != "unnamed":
                            field_info += f" (name: {input_name})"
                        if input_id:
                            field_info += f" (id: {input_id})"
                        form_info.append(field_info)

                    structured_content.extend(form_info)

            # Extract navigation elements
            nav = soup.find_all(["nav", "menu"])
            if nav:
                structured_content.append("\nNavigation:")
                for nav_elem in nav:
                    links = nav_elem.find_all("a")
                    for link in links:
                        text = link.get_text().strip()
                        if text:
                            structured_content.append(f"- {text}")

            # Extract lists
            lists = main_content.find_all(["ul", "ol"]) if main_content else []
            if lists:
                structured_content.append("\nLists:")
                for list_elem in lists:
                    items = list_elem.find_all("li")
                    for item in items:
                        text = item.get_text().strip()
                        if text:
                            structured_content.append(f"• {text}")

            # Extract tables
            tables = soup.find_all("table")
            if tables:
                structured_content.append("\nTables:")
                for table in tables:
                    # Get table headers
                    headers = []
                    for th in table.find_all("th"):
                        text = th.get_text().strip()
                        if text:
                            headers.append(text)
                    if headers:
                        structured_content.append(
                            "Table Headers: " + " | ".join(headers)
                        )

                    # Get table rows
                    for tr in table.find_all("tr"):
                        row_data = []
                        for td in tr.find_all("td"):
                            text = td.get_text().strip()
                            if text:
                                row_data.append(text)
                        if row_data:
                            structured_content.append("Row: " + " | ".join(row_data))

            # Extract error messages and notifications
            error_messages = soup.find_all(
                class_=lambda x: x
                and (
                    "error" in x.lower()
                    or "alert" in x.lower()
                    or "notification" in x.lower()
                )
            )
            if error_messages:
                structured_content.append("\nMessages and Notifications:")
                for msg in error_messages:
                    text = msg.get_text().strip()
                    if text:
                        structured_content.append(f"! {text}")

            # Extract main content paragraphs and text
            if main_content:
                content_sections = []
                for element in main_content.find_all(
                    ["p", "article", "section", "div"]
                ):
                    # Skip if element is part of already processed structures
                    if (
                        element.find_parent("form")
                        or element.find_parent("nav")
                        or element.find_parent("table")
                    ):
                        continue

                    text = element.get_text().strip()
                    if text and len(text) > 20:  # Filter out tiny text fragments
                        content_sections.append(text)

                if content_sections:
                    structured_content.append("\nMain Content:")
                    structured_content.extend(content_sections)

            # Extract any remaining important buttons
            buttons = soup.find_all(
                ["button", "a"], class_=lambda x: x and "btn" in x.lower()
            )
            if buttons:
                structured_content.append("\nImportant Buttons:")
                for button in buttons:
                    text = button.get_text().strip()
                    if text:
                        structured_content.append(f"[Button] {text}")

            # Clean up and finalize content
            final_content = "\n".join(filter(None, structured_content))

            # Remove excessive newlines and spaces
            final_content = re.sub(r"\n\s*\n", "\n\n", final_content)
            final_content = re.sub(r" +", " ", final_content)

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
