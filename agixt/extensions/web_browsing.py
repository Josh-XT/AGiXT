from typing import List, Union
import logging
import subprocess
import uuid
import sys
import os

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
        self.activity_id = kwargs["activity_id"] if "activity_id" in kwargs else None
        self.output_url = kwargs["output_url"] if "output_url" in kwargs else None
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
            user_id=self.user_id,
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
        - Execute each step in sequence
        - Handle any errors or unexpected states
        - Maintain session state throughout
        - Verify successful completion

        Args:
        url (str): Starting URL for the workflow
        task (str): Natural language description of what needs to be accomplished

        Example Usage:
        <execute>
        <name>Interact with Webpage</name>
        <url>https://example.com/login</url>
        <task>Log in using credentials, navigate to the profile page, and update the bio field with 'AI Developer'</task>
        </execute>

        Returns:
        str: Description of actions taken and results
        """
        # First check if we have an active session
        if self.page is None:
            await self.navigate_to_url_with_playwright(url=url, headless=True)

        # Use Think About It prompt to plan the interaction steps
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
Currently on: {self.page.url if self.page else 'No page loaded'}

Analyze this task and determine:
1. What steps are needed
2. What selectors to use
3. How to verify success

In the <answer> block, respond with steps: prefix followed by sequence of commands in format:
command|selector|value (if needed)

Example formats:
- click|#submit-button
- fill|input[name='username']|myuser
- select|#dropdown|option2
- wait|.loaded-element
- verify|selector|expected_text
- screenshot|description
- content|description
""",
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

        if not interaction_plan.startswith("steps:"):
            return "Error: Unable to determine interaction steps."

        steps = interaction_plan.replace("steps:", "").strip().split("\n")
        results = []

        try:
            for step in steps:
                parts = step.strip().split("|")
                command = parts[0]
                selector = parts[1]
                value = parts[2] if len(parts) > 2 else None

                result = None
                if command == "click":
                    result = await self.click_element_with_playwright(selector)
                elif command == "fill":
                    result = await self.fill_input_with_playwright(selector, value)
                elif command == "select":
                    result = await self.select_option_with_playwright(selector, value)
                elif command == "wait":
                    result = await self.wait_for_selector_with_playwright(selector)
                elif command == "verify":
                    result = await self.assert_element_with_playwright(selector, value)
                elif command == "screenshot":
                    result = await self.analyze_page_visually(
                        selector
                    )  # using selector as description
                elif command == "content":
                    result = await self.get_page_content()
                if result and result.startswith("Error"):
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {result}",
                        conversation_name=self.conversation_name,
                    )
                    return f"Workflow failed at step '{step}': {result}"

                results.append(result)
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Completed step: {result}",
                    conversation_name=self.conversation_name,
                )

            return f"Successfully completed webpage interaction:\n" + "\n".join(results)

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
        Get the content of the current page for analysis. This command should be used when:
        - Needing to analyze text content of a page
        - Extracting specific information from the current page
        - Storing page content in memory for later reference
        - Verifying page content after interactions

        Returns:
        str: The text content of the current page with structure preserved
        """
        try:
            if self.page is None:
                return "Error: No page loaded."

            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()

            # Get text while preserving some structure
            lines = []
            for element in soup.find_all(
                ["p", "h1", "h2", "h3", "h4", "h5", "h6", "div"]
            ):
                text = element.get_text().strip()
                if text:
                    lines.append(text)

            content = "\n\n".join(lines)

            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{self.activity_id}] Retrieved current page content for analysis.",
                conversation_name=self.conversation_name,
            )

            return content

        except Exception as e:
            error_msg = f"Error getting page content: {str(e)}"
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
