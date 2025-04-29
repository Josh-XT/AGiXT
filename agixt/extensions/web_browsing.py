from typing import List, Union
import logging
import subprocess
import uuid
import sys
import os
import re
import io

try:
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "beautifulsoup4==4.12.2"]
    )
    from bs4 import BeautifulSoup
try:
    from playwright.async_api import (
        async_playwright,
        TimeoutError as PlaywrightTimeoutError,
    )
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    from playwright.async_api import (
        async_playwright,
        TimeoutError as PlaywrightTimeoutError,
    )

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
try:
    from PIL import Image
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image

from Extensions import Extensions
from Websearch import search_the_web
import xml.etree.ElementTree as ET

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def escape_css_classname(classname: str) -> str:
    # Minimal example that replaces special characters in CSS class names
    return re.sub(r"([^\w\-])", r"\\\1", classname)


class web_browsing(Extensions):
    """
    The AGiXT Web Browsing extension enables sophisticated web interaction and data extraction.
    It provides high-level commands for:
    - Automated web navigation and interaction workflows via Playwright
    - Structured data extraction and analysis from web pages
    - Form filling and submission automation
    - Handling authentication mechanisms like MFA (QR code based)
    - Taking screenshots and performing visual analysis of pages
    - Interacting with popups, file uploads/downloads, and browser navigation

    The extension uses Playwright for reliable cross-browser automation and adds
    intelligent workflow management, error recovery, and detailed logging.
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
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.api_key = kwargs["api_key"] if "api_key" in kwargs else None
        self.activity_id = kwargs["activity_id"] if "activity_id" in kwargs else None
        self.output_url = kwargs["output_url"] if "output_url" in kwargs else None
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None

        # Command mapping - Add new user-facing commands here
        self.commands = {
            "Interact with Webpage": self.interact_with_webpage,
            "Web Search": self.websearch,
        }
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.popup = None

    async def websearch(
        self,
        query: str,
        websearch_depth: int = 3,
        websearch_timeout: int = 0,
    ):
        """
        Perform a web search using the provided query and return the results.

        Args:
            query (str): The search query.
            websearch_depth (int): The depth of the web search.
            websearch_timeout (int): The timeout for the web search.

        Returns:
            str: The results of the web search.
        """
        try:
            int(websearch_depth)
        except:
            websearch_depth = 3
        try:
            int(websearch_timeout)
        except:
            websearch_timeout = 0
        return self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": query,
                "websearch": True,
                "websearch_depth": websearch_depth,
                "websearch_timeout": websearch_timeout,
                "conversation_name": self.conversation_name,
                "disable_commands": True,
                "log_user_input": False,
                "log_output": False,
                "tts": False,
                "analyze_user_input": False,
                "browse_links": True,
            },
        )

    async def _ensure_browser_page(self, headless: bool = True):
        """Internal helper to ensure Playwright, browser, context, and page are initialized."""
        if self.page is None:
            logging.info("Initializing Playwright browser...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=headless)
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            self.page = await self.context.new_page()
            logging.info("Playwright browser initialized.")
        elif self.page.is_closed():
            logging.info("Page was closed, creating a new one.")
            self.page = await self.context.new_page()

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
            text = element.get_text(separator=" ", strip=True)
            return text if text else ""
        except (AttributeError, TypeError):
            return ""

    async def get_form_fields(self) -> str:
        """
        Detects form fields on the current page, including those within shadow DOMs.
        Provides a structured description of inputs, selects, textareas, and buttons,
        along with potential CSS selectors for interaction. Useful for understanding
        how to interact with forms before attempting to fill them.

        Returns:
            str: A structured string describing detected form fields and buttons,
                 including types, names, placeholders, and potential selectors.
                 Returns an error message if the page is not loaded.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        try:
            # Wait for the page to be reasonably stable
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)

            # Use JavaScript to get all relevant form elements, traversing shadow DOM
            fields = await self.page.evaluate(
                """() => {
                    const getAllFields = (root) => {
                        let elements = [];
                        const selectors = 'input, select, textarea, button, a[role="button"], div[role="button"]';

                        // Get regular form fields & common interactive elements
                        const formFields = root.querySelectorAll(selectors);
                        elements = [...elements, ...Array.from(formFields)];

                        // Traverse shadow roots
                        const shadowHosts = root.querySelectorAll('*');
                        shadowHosts.forEach(host => {
                            if (host.shadowRoot) {
                                elements = [...elements, ...getAllFields(host.shadowRoot)];
                            }
                        });
                        return elements;
                    };

                    const elements = getAllFields(document);
                    return elements.map(el => {
                        const rect = el.getBoundingClientRect();
                        const isVisible = !!(rect.width || rect.height || el.getClientRects().length) && window.getComputedStyle(el).visibility !== 'hidden';
                        return {
                            tagName: el.tagName.toLowerCase(),
                            type: el.type || '',
                            id: el.id || '',
                            name: el.name || '',
                            className: el.className || '',
                            placeholder: el.placeholder || '',
                            value: el.value || el.textContent || '', // Use textContent for buttons/links
                            isVisible: isVisible,
                            ariaLabel: el.getAttribute('aria-label') || '',
                            role: el.getAttribute('role') || '',
                            dataTestId: el.getAttribute('data-testid') || '',
                            href: el.getAttribute('href') || '', // For links
                        };
                    });
                }"""
            )

            structured_content = []

            # Filter and process visible elements
            visible_fields = [f for f in fields if f["isVisible"]]

            input_fields = [
                f
                for f in visible_fields
                if f["tagName"] == "input"
                and f["type"] not in ["button", "submit", "reset"]
            ]
            select_fields = [f for f in visible_fields if f["tagName"] == "select"]
            textarea_fields = [f for f in visible_fields if f["tagName"] == "textarea"]
            button_like_elements = [
                f
                for f in visible_fields
                if f["tagName"] == "button"
                or f["type"] in ["button", "submit", "reset"]
                or f["role"] == "button"
            ]
            link_elements = [
                f for f in visible_fields if f["tagName"] == "a" and f["href"]
            ]

            # Helper to generate selectors
            def generate_selectors(field):
                selectors = []
                # Prefer unique identifiers
                if field["id"]:
                    selectors.append(f"#{field['id']}")
                if field["dataTestId"]:
                    selectors.append(f"[data-testid='{field['dataTestId']}']")
                # Attributes commonly used for targeting
                if field["name"]:
                    selectors.append(
                        f"[{field['tagName']}[name='{field['name']}']"
                    )  # Be specific
                if field["ariaLabel"]:
                    selectors.append(
                        f"[{field['tagName']}[aria-label='{field['ariaLabel']}']"
                    )
                if field["placeholder"]:
                    selectors.append(
                        f"input[placeholder='{field['placeholder']}']"
                    )  # Placeholder specific to input
                if field["type"] and field["tagName"] == "input":
                    selectors.append(f"input[type='{field['type']}']")
                # Class selectors (less reliable, escaped)
                if field["className"]:
                    class_names = field["className"].split()
                    if class_names:
                        escaped_classes = [
                            escape_css_classname(c) for c in class_names if c
                        ]
                        if escaped_classes:
                            selectors.append(
                                f"{field['tagName']}.{'.'.join(escaped_classes)}"
                            )
                # Text content for buttons/links (used as fallback for interaction, not stable selector)
                if field["value"] and field["tagName"] in ["button", "a"]:
                    pass  # Text handled separately during interaction
                # Href for links
                if field["href"] and field["tagName"] == "a":
                    selectors.append(f"a[href='{field['href']}']")

                return selectors

            # Process input fields
            if input_fields:
                structured_content.append("\nInput Fields:")
                for field in input_fields:
                    desc = f"  Input: type='{field['type'] or 'text'}'"
                    details = []
                    if field["name"]:
                        details.append(f"name='{field['name']}'")
                    if field["placeholder"]:
                        details.append(f"placeholder='{field['placeholder']}'")
                    if field["ariaLabel"]:
                        details.append(f"aria-label='{field['ariaLabel']}'")
                    if field["value"]:
                        details.append(
                            f"current value='{field['value'][:50]}'..."
                        )  # Show partial current value
                    if details:
                        desc += f" ({', '.join(details)})"

                    selectors = generate_selectors(field)
                    if selectors:
                        desc += "\n    Selectors: " + ", ".join(
                            [f"'{s}'" for s in selectors]
                        )
                    structured_content.append(desc)

            # Process select fields
            if select_fields:
                structured_content.append("\nSelect Fields (Dropdowns):")
                for field in select_fields:
                    desc = f"  Select:"
                    details = []
                    if field["name"]:
                        details.append(f"name='{field['name']}'")
                    if field["ariaLabel"]:
                        details.append(f"aria-label='{field['ariaLabel']}'")
                    if details:
                        desc += f" ({', '.join(details)})"

                    selectors = generate_selectors(field)
                    if selectors:
                        desc += "\n    Selectors: " + ", ".join(
                            [f"'{s}'" for s in selectors]
                        )
                    # Try to get options (might require another evaluate or be complex)
                    # For simplicity, just list the field for now. Getting options dynamically is harder.
                    structured_content.append(desc)

            # Process textarea fields
            if textarea_fields:
                structured_content.append("\nText Areas:")
                for field in textarea_fields:
                    desc = f"  Textarea:"
                    details = []
                    if field["name"]:
                        details.append(f"name='{field['name']}'")
                    if field["ariaLabel"]:
                        details.append(f"aria-label='{field['ariaLabel']}'")
                    if field["value"]:
                        details.append(f"current value='{field['value'][:50]}'...")
                    if details:
                        desc += f" ({', '.join(details)})"

                    selectors = generate_selectors(field)
                    if selectors:
                        desc += "\n    Selectors: " + ", ".join(
                            [f"'{s}'" for s in selectors]
                        )
                    structured_content.append(desc)

            # Process buttons and button-like elements
            if button_like_elements:
                structured_content.append("\nButtons / Clickable Elements:")
                for field in button_like_elements:
                    text_content = (
                        field["value"].strip() or field["ariaLabel"]
                    )  # Prioritize value/aria-label
                    desc = f"  Button: text='{text_content}'"
                    details = []
                    if field["type"] and field["tagName"] == "input":
                        details.append(f"type='{field['type']}'")
                    if field["name"]:
                        details.append(f"name='{field['name']}'")
                    if details:
                        desc += f" ({', '.join(details)})"

                    selectors = generate_selectors(field)
                    if selectors:
                        desc += "\n    Selectors: " + ", ".join(
                            [f"'{s}'" for s in selectors]
                        )
                    # Add text locator info
                    if text_content:
                        desc += f"\n    (Can potentially be clicked by text: '{text_content}')"
                    structured_content.append(desc)

            # Process links
            if link_elements:
                structured_content.append("\nLinks:")
                for field in link_elements:
                    text_content = field["value"].strip() or field["ariaLabel"]
                    desc = f"  Link: text='{text_content}'"
                    if field["href"]:
                        desc += f" (href='{field['href']}')"

                    selectors = generate_selectors(field)
                    if selectors:
                        desc += "\n    Selectors: " + ", ".join(
                            [f"'{s}'" for s in selectors]
                        )
                    if text_content:
                        desc += f"\n    (Can potentially be clicked by text: '{text_content}')"
                    structured_content.append(desc)

            if not structured_content:
                return "No interactive form fields or buttons detected on the page."

            return "\n".join(structured_content)

        except PlaywrightTimeoutError:
            error_msg = (
                "Error detecting form fields: Page took too long to load or stabilize."
            )
            logging.error(error_msg)
            # Optionally send to APIClient
            # self.ApiClient.new_conversation_message(...)
            return error_msg
        except Exception as e:
            error_msg = f"Error detecting form fields: {str(e)}"
            logging.error(error_msg, exc_info=True)
            if self.ApiClient:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                    conversation_name=self.conversation_name,
                )
            return error_msg

    async def get_search_results(self, query: str) -> List[dict]:
        """
        Performs a web search using an external service (via AGiXT's search_the_web).

        Args:
            query (str): The search query string.

        Returns:
            List[dict]: A list of search result dictionaries, typically containing
                        keys like 'title', 'link', 'snippet'. Returns an empty list
                        or raises an error if the search fails.
        """
        logging.info(f"Performing web search for: {query}")
        try:
            results = await search_the_web(
                query=query,
                token=self.api_key,  # Assuming api_key is the relevant token for search_the_web
                agent_name=self.agent_name,
                conversation_name=self.conversation_name,
            )
            logging.info(f"Found {len(results)} search results.")
            return results
        except Exception as e:
            logging.error(f"Error during web search for '{query}': {str(e)}")
            return [{"error": f"Failed to get search results: {str(e)}"}]

    async def navigate_to_url_with_playwright(
        self, url: str, headless: bool = True
    ) -> str:
        """
        Navigates the browser to the specified URL using Playwright. Initializes the browser
        if it's not already running.

        Args:
            url (str): The URL to navigate to. Should include the scheme (http/https).
            headless (bool): Whether to run the browser in headless mode (no visible UI).
                             Defaults to True.

        Returns:
            str: A confirmation message indicating success or an error message.
        """
        try:
            if not url.startswith("http"):
                url = "https://" + url
                logging.info(f"Assuming HTTPS for URL: {url}")

            await self._ensure_browser_page(headless=headless)

            logging.info(f"Navigating to {url}...")
            await self.page.goto(
                url, wait_until="networkidle", timeout=60000
            )  # Increased timeout
            current_url = self.page.url
            logging.info(f"Successfully navigated to {current_url}")
            return f"Successfully navigated to {current_url}"
        except PlaywrightTimeoutError:
            error_msg = (
                f"Error navigating to {url}: Navigation timed out after 60 seconds."
            )
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            logging.error(f"Error navigating to {url}: {str(e)}", exc_info=True)
            return f"Error navigating to {url}: {str(e)}"

    async def click_element_with_playwright(
        self, selector: str, timeout: int = 10000
    ) -> str:
        """
        Clicks an element on the page specified by a CSS selector using Playwright.
        Waits for the element to be visible and enabled before clicking.

        Args:
            selector (str): The CSS selector of the element to click.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 10000 (10s).

        Returns:
            str: Confirmation message or error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed. Please navigate to a URL first."
        try:
            logging.info(f"Attempting to click element with selector: {selector}")
            element = self.page.locator(
                selector
            ).first  # Use locator and take the first match
            await element.wait_for(state="visible", timeout=timeout)
            await element.wait_for(state="enabled", timeout=timeout)
            await element.click(timeout=timeout)
            # Optional: Wait for navigation or network idle if click causes page change
            try:
                await self.page.wait_for_load_state(
                    "networkidle", timeout=15000
                )  # Wait after click
            except PlaywrightTimeoutError:
                logging.warning(
                    f"Network did not become idle after clicking {selector}, proceeding anyway."
                )
            logging.info(f"Clicked element with selector '{selector}'")
            return f"Clicked element with selector '{selector}'"
        except PlaywrightTimeoutError:
            error_msg = f"Error clicking element '{selector}': Element not visible/enabled or click timed out after {timeout}ms."
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            logging.error(
                f"Error clicking element '{selector}': {str(e)}", exc_info=True
            )
            return f"Error clicking element '{selector}': {str(e)}"

    async def fill_input_with_playwright(
        self, selector: str, text: str, timeout: int = 10000
    ) -> str:
        """
        Fills an input field specified by a CSS selector with the provided text using Playwright.
        Waits for the input field to be visible and editable. Includes retries with common variations
        if the initial selector fails.

        Args:
            selector (str): The CSS selector of the input field.
            text (str): The text to fill into the input field.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 10000 (10s).


        Returns:
            str: Confirmation message or error message detailing failures.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed. Please navigate to a URL first."

        logging.info(f"Attempting to fill input '{selector}' with text.")

        try:
            element = self.page.locator(selector).first
            await element.wait_for(state="visible", timeout=timeout)
            await element.wait_for(state="editable", timeout=timeout)
            await element.fill(text, timeout=timeout)

            # Verification step
            filled_value = await element.input_value()
            if filled_value == text:
                logging.info(f"Successfully filled input '{selector}'.")
                return f"Successfully filled input '{selector}' with text."
            else:
                logging.warning(
                    f"Filled input '{selector}' but verification failed. Expected '{text}', got '{filled_value}'."
                )
                return f"Filled input '{selector}', but verification failed (expected value mismatch)."

        except PlaywrightTimeoutError:
            error_msg = f"Error filling input '{selector}': Element not visible/editable or fill timed out after {timeout}ms."
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            logging.error(f"Error filling input '{selector}': {str(e)}", exc_info=True)
            return f"Error filling input '{selector}': {str(e)}"

    async def select_option_with_playwright(
        self, selector: str, value: str, timeout: int = 10000
    ) -> str:
        """
        Selects an option from a <select> dropdown menu specified by a selector using Playwright.
        Can select by option value or visible text (label).

        Args:
            selector (str): The CSS selector of the <select> element.
            value (str): The value or the visible text (label) of the option to select.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 10000 (10s).

        Returns:
            str: Confirmation message or error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed. Please navigate to a URL first."
        try:
            logging.info(
                f"Attempting to select option '{value}' in dropdown '{selector}'"
            )
            element = self.page.locator(selector).first
            await element.wait_for(state="visible", timeout=timeout)
            # Playwright's select_option can handle value or label automatically
            await element.select_option(value, timeout=timeout)
            logging.info(f"Selected option '{value}' in dropdown '{selector}'")
            return f"Selected option '{value}' in dropdown '{selector}'"
        except PlaywrightTimeoutError:
            error_msg = f"Error selecting option '{value}' in '{selector}': Element not visible or option not found within {timeout}ms."
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            # Check if it's because the option wasn't found
            if "options available" in str(e):
                error_msg = f"Error selecting option '{value}' in '{selector}': Option not found. Available options might be different."
                logging.error(error_msg)
                return error_msg
            logging.error(
                f"Error selecting option '{value}' in '{selector}': {str(e)}",
                exc_info=True,
            )
            return f"Error selecting option '{value}' in '{selector}': {str(e)}"

    async def check_checkbox_with_playwright(
        self, selector: str, timeout: int = 10000
    ) -> str:
        """
        Checks a checkbox specified by a selector using Playwright.
        Waits for the checkbox to be visible and enabled.

        Args:
            selector (str): The CSS selector of the checkbox input element.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 10000 (10s).

        Returns:
            str: Confirmation message or error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed. Please navigate to a URL first."
        try:
            logging.info(f"Attempting to check checkbox '{selector}'")
            element = self.page.locator(selector).first
            await element.wait_for(state="visible", timeout=timeout)
            await element.wait_for(state="enabled", timeout=timeout)
            await element.check(timeout=timeout)
            logging.info(f"Checked checkbox '{selector}'")
            return f"Checked checkbox '{selector}'"
        except PlaywrightTimeoutError:
            error_msg = f"Error checking checkbox '{selector}': Element not visible/enabled or check timed out after {timeout}ms."
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            logging.error(
                f"Error checking checkbox '{selector}': {str(e)}", exc_info=True
            )
            return f"Error checking checkbox '{selector}': {str(e)}"

    async def handle_mfa_with_playwright(
        self, otp_selector: str, submit_selector: str = 'button[type="submit"]'
    ) -> str:
        """
        Handles Time-based One-Time Password (TOTP) MFA by attempting to find a QR code
        on the current page, extract the secret, generate the current code, and enter it
        into the specified input field, then clicks a submit button.

        Args:
            otp_selector (str): The CSS selector of the input field where the OTP code should be entered.
            submit_selector (str): The CSS selector for the submit button to click after entering the code.
                                   Defaults to 'button[type="submit"]'.

        Returns:
            str: Confirmation message on success, or an error message if QR code is not found,
                 secret extraction fails, or interaction fails.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded. Please navigate to a URL first."

        logging.info("Attempting to handle MFA via QR code...")
        try:
            # 1. Take screenshot of the page
            screenshot_bytes = await self.page.screenshot()
            logging.info("Took screenshot for QR code detection.")

            # 2. Decode QR code from the screenshot using pyzbar and OpenCV
            nparr = np.frombuffer(screenshot_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return "Error: Could not decode screenshot image."

            decoded_objects = decode(img)
            otp_uri = None
            for obj in decoded_objects:
                if obj.type == "QRCODE":
                    try:
                        data = obj.data.decode("utf-8")
                        if data.startswith("otpauth://totp/"):
                            otp_uri = data
                            logging.info(f"Found potential TOTP QR code URI.")
                            break
                    except UnicodeDecodeError:
                        continue  # Ignore QR codes with non-UTF8 data

            if not otp_uri:
                logging.warning("No TOTP QR code found on the page screenshot.")
                return "Error: No TOTP QR code found on the page."

            # 3. Extract secret key from OTP URI
            match = re.search(r"[?&]secret=([\w\d]+)", otp_uri, re.IGNORECASE)
            if match:
                secret_key = match.group(1)
                logging.info("Extracted TOTP secret key from URI.")

                # 4. Generate TOTP token
                try:
                    totp = pyotp.TOTP(secret_key)
                    otp_token = totp.now()
                    logging.info(f"Generated TOTP token: {otp_token}")
                except Exception as otp_error:
                    logging.error(f"Error generating TOTP token: {otp_error}")
                    return f"Error: Failed to generate TOTP token: {otp_error}"

                # 5. Enter the OTP token into the input field
                fill_result = await self.fill_input_with_playwright(
                    otp_selector, otp_token
                )
                if "Error" in fill_result:
                    return f"Error entering OTP code: {fill_result}"

                # 6. Submit the form
                click_result = await self.click_element_with_playwright(submit_selector)
                if "Error" in click_result:
                    return f"Error submitting OTP form: {click_result}"

                logging.info(
                    "MFA handled successfully (QR code scanned, code entered and submitted)."
                )
                return "MFA handled successfully."
            else:
                logging.error("Failed to extract secret key from the found OTP URI.")
                return "Error: Found QR code, but failed to extract secret key from OTP URI."
        except ImportError as ie:
            logging.error(
                f"Import error during MFA handling (missing dependency?): {ie}"
            )
            return f"Error: Missing dependency for MFA handling: {ie}. Please install opencv-python, pyzbar, numpy, pyotp."
        except Exception as e:
            logging.error(f"Error handling MFA: {str(e)}", exc_info=True)
            return f"Error handling MFA: {str(e)}"

    async def handle_popup_with_playwright(
        self, action: str = "close", fill_details: dict = None, timeout: int = 10000
    ) -> str:
        """
        Handles the next popup window that appears (e.g., during OAuth flows).
        Can simply close it, or attempt to fill details before closing/proceeding.

        Args:
            action (str): Action to perform on the popup. 'close' (default), 'fill_and_proceed'.
            fill_details (dict): If action is 'fill_and_proceed', a dictionary mapping
                                 CSS selectors within the popup to values to fill.
                                 Example: {'#username': 'user', '#password': 'pass'}
            timeout (int): Maximum time in milliseconds to wait for the popup event. Defaults to 10000 (10s).

        Returns:
            str: Confirmation message or error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        logging.info(f"Waiting for popup window (action: {action})...")
        try:
            async with self.page.expect_popup(timeout=timeout) as popup_info:
                # The code that triggers the popup should be executed *after* starting to expect it.
                # This method assumes the action triggering the popup happens *after* this call.
                # If the popup is triggered by a click, call `click_element_with_playwright` *after* this.
                # For now, we just wait. The caller needs to ensure the popup is triggered.
                # Let's add a placeholder message.
                logging.info(
                    "Popup expectation set. Trigger the action that opens the popup now."
                )
                # In a real scenario, you might need to return control here or have the triggering action passed in.
                # For simplicity, we proceed assuming the popup will appear shortly.

            popup = await popup_info.value  # Get the Page object for the popup
            popup_url = popup.url
            logging.info(f"Popup detected with URL: {popup_url}")

            if action == "fill_and_proceed" and fill_details:
                logging.info("Attempting to fill details in popup...")
                for selector, value in fill_details.items():
                    try:
                        # Use the popup's page context to fill
                        await popup.fill(selector, value, timeout=5000)
                        logging.info(f"Filled '{selector}' in popup.")
                    except Exception as fill_error:
                        logging.error(
                            f"Error filling '{selector}' in popup: {fill_error}"
                        )
                        await popup.close()  # Close popup if filling fails
                        return f"Error filling '{selector}' in popup: {fill_error}"
                # Assume submission or next step happens automatically or needs another click
                # For now, we just log success of filling. A 'submit_selector' could be added.
                logging.info("Filled details in popup.")
                # Optionally keep popup open or close it based on workflow needs.
                # await popup.close()
                # logging.info("Popup filled and left open (or closed depending on workflow).")
                return f"Popup handled: Filled details. Popup URL: {popup_url}"

            elif action == "close":
                await popup.close()
                logging.info("Popup handled and closed successfully.")
                return "Popup handled and closed successfully."
            else:
                # Default to closing if action is unknown or fill details are missing
                await popup.close()
                logging.warning(
                    f"Unknown action '{action}' or missing details. Closed popup."
                )
                return f"Popup handled: Closed (unknown action/missing details). Popup URL: {popup_url}"

        except PlaywrightTimeoutError:
            logging.warning(f"No popup appeared within {timeout}ms.")
            return "No popup appeared within the specified timeout."
        except Exception as e:
            logging.error(f"Error handling popup: {str(e)}", exc_info=True)
            # Attempt to close popup if it exists and an error occurred
            if "popup" in locals() and not popup.is_closed():
                await popup.close()
            return f"Error handling popup: {str(e)}"

    async def upload_file_with_playwright(
        self, selector: str, file_path: str, timeout: int = 10000
    ) -> str:
        """
        Uploads a local file to a file input element (<input type="file">) on the page.

        Args:
            selector (str): The CSS selector of the file input element.
            file_path (str): The absolute or relative path to the local file to upload.
            timeout (int): Maximum time in milliseconds to wait for the file chooser event. Defaults to 10000 (10s).

        Returns:
            str: Confirmation message or error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        absolute_file_path = os.path.abspath(file_path)
        if not os.path.isfile(absolute_file_path):
            logging.error(f"File not found at path: {absolute_file_path}")
            return f"Error: File '{file_path}' (abs: {absolute_file_path}) does not exist or is not a file."

        logging.info(
            f"Attempting to upload file '{absolute_file_path}' to input '{selector}'"
        )
        try:
            # Use expect_file_chooser to handle the event gracefully
            async with self.page.expect_file_chooser(timeout=timeout) as fc_info:
                await self.page.locator(
                    selector
                ).first.click()  # Click the element that opens the chooser
            file_chooser = await fc_info.value
            await file_chooser.set_files(absolute_file_path)
            logging.info(
                f"Successfully set file '{absolute_file_path}' for upload via input '{selector}'"
            )
            return f"File '{os.path.basename(absolute_file_path)}' set for upload via input '{selector}'."
        except PlaywrightTimeoutError:
            error_msg = f"Error uploading file: File chooser did not appear for selector '{selector}' within {timeout}ms."
            logging.error(error_msg)
            # Fallback: Try setting input files directly (works for some non-standard inputs)
            try:
                logging.info(
                    f"Fallback: Trying direct set_input_files for '{selector}'"
                )
                await self.page.locator(selector).first.set_input_files(
                    absolute_file_path, timeout=timeout
                )
                logging.info(
                    f"Fallback successful: Uploaded file '{absolute_file_path}' to input '{selector}' directly."
                )
                return f"Uploaded file '{os.path.basename(absolute_file_path)}' to input '{selector}' (using direct method)."
            except Exception as direct_error:
                logging.error(
                    f"Direct set_input_files also failed for '{selector}': {direct_error}"
                )
                return f"{error_msg} Direct input also failed: {direct_error}"
        except Exception as e:
            logging.error(
                f"Error uploading file '{absolute_file_path}' to '{selector}': {str(e)}",
                exc_info=True,
            )
            return f"Error uploading file '{os.path.basename(absolute_file_path)}': {str(e)}"

    async def download_file_with_playwright(
        self, trigger_selector: str, save_path: str = None, timeout: int = 30000
    ) -> str:
        """
        Triggers a file download by clicking an element and saves the downloaded file.

        Args:
            trigger_selector (str): The CSS selector of the element (e.g., link or button)
                                    that initiates the download when clicked.
            save_path (str): Optional. The desired path (including filename) to save the
                             downloaded file. If None, a unique name is generated in the
                             WORKING_DIRECTORY.
            timeout (int): Maximum time in milliseconds to wait for the download event to start.
                           Defaults to 30000 (30s).

        Returns:
            str: Message indicating the path where the file was saved or an error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        if save_path:
            absolute_save_path = os.path.abspath(save_path)
            save_dir = os.path.dirname(absolute_save_path)
            os.makedirs(save_dir, exist_ok=True)  # Ensure directory exists
        else:
            # Generate a unique path in the working directory if none provided
            pass  # Will be handled by download.suggested_filename or generated later

        logging.info(
            f"Attempting to download file triggered by clicking '{trigger_selector}'..."
        )

        try:
            # Start waiting for the download event *before* clicking
            async with self.page.expect_download(timeout=timeout) as download_info:
                # Click the element that triggers the download
                logging.info(f"Clicking trigger element: {trigger_selector}")
                await self.page.locator(trigger_selector).first.click()
                logging.info("Waiting for download to start...")

            download = await download_info.value
            suggested_filename = download.suggested_filename
            logging.info(f"Download started: Suggested filename = {suggested_filename}")

            # Determine final save path
            if not save_path:
                final_save_path = os.path.join(
                    self.WORKING_DIRECTORY, f"{uuid.uuid4()}_{suggested_filename}"
                )
            else:
                # If save_path is a directory, append filename
                if os.path.isdir(absolute_save_path):
                    final_save_path = os.path.join(
                        absolute_save_path, suggested_filename
                    )
                else:  # Assume it's a full path including filename
                    final_save_path = absolute_save_path

            logging.info(f"Saving downloaded file to: {final_save_path}")
            await download.save_as(final_save_path)

            # Verify download success (check file existence and size)
            if os.path.exists(final_save_path) and os.path.getsize(final_save_path) > 0:
                logging.info(
                    f"File successfully downloaded and saved to '{final_save_path}'."
                )
                # Provide relative path if within working directory for easier access in logs/output
                rel_path = os.path.relpath(final_save_path, self.WORKING_DIRECTORY)
                if not rel_path.startswith(".."):
                    return f"File downloaded successfully to: WORKSPACE/{rel_path}"
                else:
                    return f"File downloaded successfully to: {final_save_path}"
            else:
                download_failure_reason = await download.failure()
                error_msg = f"Download failed: File not saved correctly to '{final_save_path}'. Reason: {download_failure_reason or 'Unknown'}"
                logging.error(error_msg)
                return error_msg

        except PlaywrightTimeoutError:
            error_msg = f"Error downloading file: Download did not start after clicking '{trigger_selector}' within {timeout}ms."
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            # Capture potential failure reason if available
            failure_reason = None
            if "download" in locals():
                failure_reason = await download.failure()
            logging.error(
                f"Error downloading file triggered by '{trigger_selector}': {str(e)}. Failure reason: {failure_reason}",
                exc_info=True,
            )
            return (
                f"Error downloading file: {str(e)} (Failure: {failure_reason or 'N/A'})"
            )

    async def go_back_with_playwright(self) -> str:
        """
        Navigates back in the browser's history (like clicking the back button).

        Returns:
            str: Confirmation message or error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."
        try:
            logging.info("Navigating back in browser history.")
            await self.page.go_back(wait_until="networkidle", timeout=30000)
            new_url = self.page.url
            logging.info(f"Navigated back. Current URL: {new_url}")
            return f"Navigated back in browser history. Current URL: {new_url}"
        except PlaywrightTimeoutError:
            logging.warning(
                "Timeout waiting for network idle after going back. Navigation might be incomplete."
            )
            return "Navigated back, but network idle wait timed out."
        except Exception as e:
            logging.error(f"Error navigating back: {str(e)}", exc_info=True)
            return f"Error navigating back: {str(e)}"

    async def go_forward_with_playwright(self) -> str:
        """
        Navigates forward in the browser's history (like clicking the forward button).

        Returns:
            str: Confirmation message or error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."
        try:
            logging.info("Navigating forward in browser history.")
            await self.page.go_forward(wait_until="networkidle", timeout=30000)
            new_url = self.page.url
            logging.info(f"Navigated forward. Current URL: {new_url}")
            return f"Navigated forward in browser history. Current URL: {new_url}"
        except PlaywrightTimeoutError:
            logging.warning(
                "Timeout waiting for network idle after going forward. Navigation might be incomplete."
            )
            return "Navigated forward, but network idle wait timed out."
        except Exception as e:
            logging.error(f"Error navigating forward: {str(e)}", exc_info=True)
            return f"Error navigating forward: {str(e)}"

    async def wait_for_selector_with_playwright(
        self, selector: str, state: str = "visible", timeout: int = 30000
    ) -> str:
        """
        Waits for an element specified by a selector to appear on the page and reach a specific state.

        Args:
            selector (str): The CSS selector of the element to wait for.
            state (str): The state to wait for ('visible', 'hidden', 'attached', 'detached', 'enabled', 'disabled', 'editable').
                         Defaults to 'visible'.
            timeout (int): Maximum time to wait in milliseconds. Defaults to 30000 (30s).

        Returns:
            str: Confirmation message if the element appears in the specified state, or an error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."
        try:
            logging.info(f"Waiting for element '{selector}' to be {state}...")
            await self.page.locator(selector).first.wait_for(
                state=state, timeout=timeout
            )
            logging.info(f"Element '{selector}' is now {state}.")
            return f"Element '{selector}' reached state '{state}'."
        except PlaywrightTimeoutError:
            error_msg = f"Error waiting for selector '{selector}': Element did not reach state '{state}' within {timeout}ms."
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            logging.error(
                f"Error waiting for selector '{selector}' with state '{state}': {str(e)}",
                exc_info=True,
            )
            return f"Error waiting for selector '{selector}': {str(e)}"

    async def extract_table_with_playwright(
        self, selector: str
    ) -> Union[str, List[List[str]]]:
        """
        Extracts data from an HTML table element specified by a CSS selector.
        Parses `<th>` (header) and `<td>` (data) cells within `<tr>` (rows).

        Args:
            selector (str): The CSS selector uniquely identifying the table element (e.g., '#myTable', '.data-table').

        Returns:
            Union[str, List[List[str]]]: A list of lists representing the table rows and cells
                                         (List[rows][cells]), or an error message string if the
                                         table is not found or parsing fails.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."
        try:
            logging.info(f"Attempting to extract data from table '{selector}'")
            table_element = self.page.locator(selector).first
            await table_element.wait_for(
                state="attached", timeout=10000
            )  # Wait for table to be in DOM

            # Use evaluate to process the table structure efficiently in the browser context
            table_data = await table_element.evaluate(
                """
                (table) => {
                    const data = [];
                    const rows = table.querySelectorAll('tr');
                    rows.forEach(row => {
                        const rowData = [];
                        // Consider both th and td cells in order
                        const cells = row.querySelectorAll('th, td');
                        cells.forEach(cell => {
                            rowData.push(cell.innerText.trim());
                        });
                        if (rowData.length > 0) { // Avoid adding empty rows if structure is weird
                           data.push(rowData);
                        }
                    });
                    return data;
                }
            """
            )

            if not table_data:
                logging.warning(
                    f"Table '{selector}' found, but no data extracted (maybe empty or complex structure?)."
                )
                return f"Warning: Table '{selector}' found, but no data could be extracted."

            logging.info(f"Extracted {len(table_data)} rows from table '{selector}'.")
            return table_data
        except PlaywrightTimeoutError:
            error_msg = f"Error extracting table '{selector}': Table element not found or attached within timeout."
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            logging.error(
                f"Error extracting table '{selector}': {str(e)}", exc_info=True
            )
            return f"Error extracting table '{selector}': {str(e)}"

    async def assert_element_with_playwright(
        self,
        selector: str,
        expected_text: str = None,
        check_visibility: bool = True,
        timeout: int = 10000,
    ) -> str:
        """
        Asserts the state of an element: checks if it exists, optionally if it's visible,
        and optionally if its text content contains the expected text.

        Args:
            selector (str): The CSS selector of the element to assert.
            expected_text (str, optional): If provided, asserts that the element's text content
                                          contains this string (case-sensitive). Defaults to None.
            check_visibility (bool): If True (default), asserts that the element is visible on the page.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 10000 (10s).


        Returns:
            str: Confirmation message indicating the assertion passed, or an error message detailing the failure.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed. Please navigate to a URL first."
        try:
            logging.info(f"Asserting element '{selector}'...")
            element = self.page.locator(selector).first

            # 1. Check Existence (implicitly done by waiting)
            await element.wait_for(state="attached", timeout=timeout)
            logging.info(f"Element '{selector}' exists.")

            # 2. Check Visibility (if requested)
            if check_visibility:
                await element.wait_for(state="visible", timeout=timeout)
                logging.info(f"Element '{selector}' is visible.")

            # 3. Check Text Content (if requested)
            assertion_details = ["exists"]
            if check_visibility:
                assertion_details.append("is visible")

            if expected_text is not None:
                actual_text = await element.text_content(timeout=timeout)
                if expected_text in actual_text:
                    logging.info(f"Element '{selector}' contains expected text.")
                    assertion_details.append(f"contains text '{expected_text}'")
                else:
                    error_msg = f"Assertion failed: Element '{selector}' exists but text content '{actual_text}' does not contain expected text '{expected_text}'."
                    logging.warning(error_msg)
                    return error_msg

            # If all checks passed
            passed_msg = f"Assertion passed: Element '{selector}' {', '.join(assertion_details)}."
            logging.info(passed_msg)
            return passed_msg

        except PlaywrightTimeoutError:
            error_msg = f"Assertion failed: Element '{selector}' not found or did not meet state requirements (visible={check_visibility}) within {timeout}ms."
            logging.error(error_msg)
            return error_msg
        except Exception as e:
            logging.error(
                f"Error asserting element '{selector}': {str(e)}", exc_info=True
            )
            return f"Error during assertion for element '{selector}': {str(e)}"

    async def evaluate_javascript_with_playwright(self, script: str) -> str:
        """
        Executes arbitrary JavaScript code within the context of the current page
        and returns the result. Use with caution, as this can directly manipulate the page.

        Args:
            script (str): The JavaScript code string to evaluate.

        Returns:
            str: A string representation of the result returned by the JavaScript execution,
                 or an error message if execution fails.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded. Please navigate to a URL first."
        try:
            logging.info(
                f"Evaluating JavaScript: {script[:100]}{'...' if len(script) > 100 else ''}"
            )
            result = await self.page.evaluate(script)
            logging.info(f"JavaScript evaluation completed.")
            try:
                # Attempt to serialize complex results
                result_str = str(result)  # Basic conversion first
                if isinstance(result, (dict, list)):
                    import json

                    result_str = json.dumps(result)
            except Exception:
                result_str = repr(result)  # Fallback representation

            return f"Script evaluation result: {result_str}"
        except Exception as e:
            logging.error(f"Error evaluating JavaScript: {str(e)}", exc_info=True)
            return f"Error evaluating JavaScript: {str(e)}"

    async def close_browser_with_playwright(self) -> str:
        """
        Closes the Playwright browser instance and cleans up associated resources (context, page).

        Returns:
            str: Confirmation message.
        """
        try:
            if self.browser is not None and self.browser.is_connected():
                logging.info("Closing Playwright browser...")
                await self.browser.close()
                logging.info("Browser closed successfully.")
            else:
                logging.info("Browser already closed or not initialized.")

            if self.playwright is not None:
                await self.playwright.stop()
                logging.info("Playwright stopped.")

            self.browser = None
            self.context = None
            self.page = None
            self.playwright = None
            return "Browser closed successfully."
        except Exception as e:
            logging.error(f"Error closing browser: {str(e)}", exc_info=True)
            # Reset state variables even if closing fails partially
            self.browser = None
            self.context = None
            self.page = None
            self.playwright = None
            return f"Error closing browser: {str(e)}"

    # --- Additional/Utility Features ---

    async def set_viewport_with_playwright(self, width: int, height: int) -> str:
        """
        Sets the viewport size (the visible area of the page) for the current browser context.

        Args:
            width (int): The desired viewport width in pixels.
            height (int): The desired viewport height in pixels.

        Returns:
            str: Confirmation message or error message.
        """
        try:
            # Ensure context exists, might need to init browser if not yet done
            await self._ensure_browser_page()
            if (
                self.page is None
            ):  # Check page specifically as context might exist but page closed
                self.page = await self.context.new_page()

            await self.page.set_viewport_size({"width": width, "height": height})
            logging.info(f"Viewport size set to {width}x{height}.")
            return f"Viewport size set to {width}x{height}."
        except Exception as e:
            logging.error(f"Error setting viewport size: {str(e)}", exc_info=True)
            return f"Error setting viewport size: {str(e)}"

    async def emulate_device_with_playwright(self, device_name: str) -> str:
        """
        Emulates a specific device (e.g., 'iPhone 13', 'Pixel 5') using Playwright's built-in
        device descriptors. This reconfigures the browser context (viewport, user agent, etc.).
        The current page will be closed and a new one opened in the emulated context.

        Args:
            device_name (str): The name of the device to emulate (must match a name in
                               `playwright.devices`, e.g., 'iPhone 13 Pro Max').

        Returns:
            str: Confirmation message or error message if the device name is invalid.
        """
        try:
            if self.playwright is None:
                # Need to start playwright to access devices, ensure browser starts too
                await self._ensure_browser_page()

            device = self.playwright.devices.get(device_name)
            if not device:
                available_devices = list(self.playwright.devices.keys())
                logging.error(f"Device '{device_name}' not found.")
                return f"Error: Device '{device_name}' not found. Available devices: {', '.join(available_devices[:10])}..."  # Show some examples
            logging.info(f"Emulating device '{device_name}'...")

            # Close existing context/page if they exist
            if self.page and not self.page.is_closed():
                await self.page.close()
            if self.context:
                await self.context.close()

            # Create new context with device parameters
            self.context = await self.browser.new_context(**device)
            self.page = (
                await self.context.new_page()
            )  # Open a new page in the emulated context

            logging.info(
                f"Successfully emulating device '{device_name}'. New page created."
            )
            return f"Emulating device '{device_name}'. A new page has been opened with these settings."
        except Exception as e:
            logging.error(
                f"Error emulating device '{device_name}': {str(e)}", exc_info=True
            )
            return f"Error emulating device '{device_name}': {str(e)}"

    async def get_cookies_with_playwright(self) -> Union[str, List[dict]]:
        """
        Retrieves all cookies associated with the current browser context.

        Returns:
            Union[str, List[dict]]: A list of cookie dictionaries (containing keys like 'name',
                                    'value', 'domain', 'path', etc.) or an error message string.
        """
        try:
            await self._ensure_browser_page()  # Ensure context exists
            if self.context is None:
                return "Error: Browser context not initialized."

            cookies = await self.context.cookies()
            logging.info(f"Retrieved {len(cookies)} cookies from the browser context.")
            return cookies
        except Exception as e:
            logging.error(f"Error getting cookies: {str(e)}", exc_info=True)
            return f"Error getting cookies: {str(e)}"

    async def set_cookies_with_playwright(self, cookies: List[dict]) -> str:
        """
        Adds or updates cookies in the current browser context.

        Args:
            cookies (List[dict]): A list of cookie dictionaries. Each dictionary must have
                                  'name' and 'value', and should typically include 'domain'
                                  or 'url' to specify where the cookie applies.

        Returns:
            str: Confirmation message or error message.
        """
        if not isinstance(cookies, list):
            return "Error: Input must be a list of cookie dictionaries."
        if not all(
            isinstance(c, dict) and "name" in c and "value" in c for c in cookies
        ):
            return "Error: Each item in the list must be a dictionary with at least 'name' and 'value' keys."

        try:
            await self._ensure_browser_page()  # Ensure context exists
            if self.context is None:
                return "Error: Browser context not initialized."

            await self.context.add_cookies(cookies)
            logging.info(
                f"Attempted to set {len(cookies)} cookies in the browser context."
            )
            return f"{len(cookies)} cookies set successfully."
        except Exception as e:
            logging.error(f"Error setting cookies: {str(e)}", exc_info=True)
            return f"Error setting cookies: {str(e)}"

    async def handle_dialog_with_playwright(
        self, action: str = "accept", prompt_text: str = None, listen_once: bool = True
    ) -> str:
        """
        Sets up a handler for the next JavaScript dialog (alert, confirm, prompt) that appears.
        The handler will automatically perform the specified action.

        Args:
            action (str): The action to perform: 'accept' (default) or 'dismiss'.
            prompt_text (str, optional): If the dialog is a prompt, this text will be entered
                                        before accepting. Required if action is 'accept' for a prompt.
                                        Defaults to None.
            listen_once (bool): If True (default), the handler automatically removes itself
                                after handling one dialog. If False, it persists for subsequent dialogs.

        Returns:
            str: Confirmation message indicating the handler is set up. The actual handling
                 happens asynchronously when a dialog appears.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        logging.info(
            f"Setting up dialog handler: action='{action}', prompt_text='{prompt_text}', once={listen_once}"
        )

        async def dialog_handler(dialog):
            dialog_type = dialog.type
            logging.info(
                f"Dialog appeared: type='{dialog_type}', message='{dialog.message}'"
            )
            if action == "accept":
                if dialog_type == "prompt":
                    await dialog.accept(prompt_text if prompt_text is not None else "")
                    logging.info(f"Dialog accepted with text: '{prompt_text}'")
                else:
                    await dialog.accept()
                    logging.info("Dialog accepted.")
            elif action == "dismiss":
                await dialog.dismiss()
                logging.info("Dialog dismissed.")
            else:
                logging.warning(
                    f"Unknown dialog action '{action}'. Dismissing dialog by default."
                )
                await dialog.dismiss()

            # Remove listener after handling if listen_once is True
            if listen_once:
                try:
                    self.page.remove_listener("dialog", dialog_handler)
                    logging.info("Dialog listener removed (listen_once=True).")
                except (
                    Exception
                ) as remove_error:  # Handle potential errors if listener already removed
                    logging.warning(f"Could not remove dialog listener: {remove_error}")

        try:
            # Register the event handler
            self.page.on("dialog", dialog_handler)
            msg = f"Dialog handler set up: will '{action}' the next dialog."
            if listen_once:
                msg += " (Handler active for one dialog only)"
            return msg
        except Exception as e:
            logging.error(f"Error setting up dialog handler: {str(e)}", exc_info=True)
            return f"Error setting up dialog handler: {str(e)}"

    async def intercept_requests_with_playwright(
        self, url_pattern: str, action: str = "block", modification: dict = None
    ) -> str:
        """
        Intercepts network requests matching a URL pattern (glob pattern or regex) and
        performs an action: 'block', 'modify', or 'continue'.

        Args:
            url_pattern (str): A glob pattern (e.g., "**/*.css") or regular expression
                               (e.g., re.compile(r"(\.png$|\.jpg$)")) to match request URLs.
            action (str): The action to perform:
                          'block' (default): Aborts the request.
                          'continue': Allows the request to proceed unchanged.
                          'modify': Modifies the request before it proceeds (requires 'modification' arg).
                          'fulfill': Fulfills the request with a mock response (requires 'modification' arg).
            modification (dict, optional): Required if action is 'modify' or 'fulfill'.
                                           For 'modify': Dict with keys like 'method', 'post_data', 'headers'.
                                           For 'fulfill': Dict with keys like 'status', 'headers', 'contentType', 'body'.

        Returns:
            str: Confirmation message that the interception route is set up, or an error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        logging.info(
            f"Setting up request interception: pattern='{url_pattern}', action='{action}'"
        )

        async def route_handler(route):
            request = route.request
            should_handle = False
            if isinstance(url_pattern, re.Pattern):
                if url_pattern.search(request.url):
                    should_handle = True
            elif (
                url_pattern in request.url
            ):  # Simple substring check for glob-like behavior (can be improved)
                # TODO: Implement proper glob matching if needed
                should_handle = True

            if should_handle:
                logging.info(
                    f"Intercepted request: {request.method} {request.url} (Action: {action})"
                )
                try:
                    if action == "block":
                        await route.abort()
                        logging.info(f"Blocked request to {request.url}")
                    elif action == "modify":
                        if modification:
                            await route.continue_(**modification)
                            logging.info(
                                f"Modified and continued request to {request.url}"
                            )
                        else:
                            logging.warning(
                                "Action 'modify' requested but no modifications provided. Continuing request."
                            )
                            await route.continue_()
                    elif action == "fulfill":
                        if modification:
                            await route.fulfill(**modification)
                            logging.info(
                                f"Fulfilled request to {request.url} with mock response."
                            )
                        else:
                            logging.warning(
                                "Action 'fulfill' requested but no response provided. Aborting request."
                            )
                            await route.abort(
                                error_code="failed"
                            )  # Abort if no fulfillment details
                    elif action == "continue":
                        await route.continue_()
                        # logging.info(f"Continued request to {request.url}") # Can be verbose
                    else:
                        logging.warning(
                            f"Unknown interception action '{action}'. Continuing request."
                        )
                        await route.continue_()
                except Exception as handler_error:
                    logging.error(
                        f"Error handling intercepted request {request.url}: {handler_error}",
                        exc_info=True,
                    )
                    # Ensure request is handled somehow to avoid hangs
                    if not route._handled:
                        await route.abort(error_code="failed")
            else:
                # If pattern doesn't match, continue the request normally
                await route.continue_()

        try:
            await self.page.route(url_pattern, route_handler)
            return f"Request interception set up for pattern '{url_pattern}' with action '{action}'."
        except Exception as e:
            logging.error(
                f"Error setting up request interception for '{url_pattern}': {str(e)}",
                exc_info=True,
            )
            return f"Error setting up request interception: {str(e)}"

    async def take_screenshot_with_highlight_with_playwright(
        self, selector: str = None, save_path: str = None, full_page: bool = True
    ) -> str:
        """
        Takes a screenshot of the current page. Optionally highlights a specific element
        before taking the screenshot and saves it to a specified path or generates one.

        Args:
            selector (str, optional): The CSS selector of the element to highlight with a red border
                                      before taking the screenshot. Defaults to None (no highlight).
            save_path (str, optional): The path (including filename, e.g., 'screenshot.png') where
                                       the screenshot should be saved. If None, a unique filename is
                                       generated in the WORKING_DIRECTORY. Defaults to None.
            full_page (bool): Whether to capture the entire scrollable page (True, default) or only
                              the current viewport (False).

        Returns:
            str: Message indicating the path where the screenshot was saved, or an error message.
                 Includes a relative path if saved within the working directory.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        if not save_path:
            save_path = os.path.join(
                self.WORKING_DIRECTORY, f"screenshot_{uuid.uuid4()}.png"
            )
        absolute_save_path = os.path.abspath(save_path)
        save_dir = os.path.dirname(absolute_save_path)
        os.makedirs(save_dir, exist_ok=True)

        highlight_style = "border: 3px solid red; box-shadow: 0 0 10px red;"
        original_style = None

        try:
            # Highlight element if selector is provided
            if selector:
                logging.info(f"Highlighting element '{selector}' for screenshot.")
                element = self.page.locator(selector).first
                try:
                    await element.wait_for(state="visible", timeout=5000)
                    # Get original style to restore it later
                    original_style = await element.get_attribute("style")
                    # Apply highlight style
                    await element.evaluate(
                        f"(element, style) => {{ element.style.cssText += style; }}",
                        highlight_style,
                    )
                except Exception as highlight_error:
                    logging.warning(
                        f"Could not highlight element '{selector}': {highlight_error}. Proceeding without highlight."
                    )
                    selector = None  # Clear selector so log message is accurate

            # Take screenshot
            logging.info(f"Taking screenshot (full_page={full_page})...")
            await self.page.screenshot(path=absolute_save_path, full_page=full_page)

            # Restore original style if element was highlighted
            if selector and original_style is not None:
                try:
                    await element.evaluate(
                        f"(element, style) => {{ element.style.cssText = style; }}",
                        original_style or "",
                    )
                    logging.info(f"Restored original style for '{selector}'.")
                except Exception as restore_error:
                    logging.warning(
                        f"Could not restore original style for '{selector}': {restore_error}"
                    )

            # Format confirmation message
            rel_path = os.path.relpath(absolute_save_path, self.WORKING_DIRECTORY)
            if not rel_path.startswith(".."):
                path_info = f"WORKSPACE/{rel_path}"
            else:
                path_info = absolute_save_path

            msg = f"Screenshot saved to '{path_info}'"
            if selector:
                msg += f" (element '{selector}' was highlighted)."
            logging.info(msg)
            return msg

        except Exception as e:
            logging.error(f"Error taking screenshot: {str(e)}", exc_info=True)
            # Attempt to remove highlight even if screenshot fails
            if selector and original_style is not None:
                try:
                    await element.evaluate(
                        f"(element, style) => {{ element.style.cssText = style; }}",
                        original_style or "",
                    )
                except:
                    pass  # Ignore errors during cleanup
            return f"Error taking screenshot: {str(e)}"

    async def extract_text_from_image_with_playwright(
        self, image_selector: str
    ) -> Union[str, List[str]]:
        """
        Extracts text from an image element on the page using Optical Character Recognition (OCR)
        via Tesseract (requires Tesseract OCR engine to be installed on the system).

        Args:
            image_selector (str): The CSS selector uniquely identifying the image element (`<img>`).

        Returns:
            Union[str, str]: The extracted text as a single string, or an error message string
                             if the image is not found, screenshot fails, or OCR fails.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        logging.info(
            f"Attempting to extract text from image '{image_selector}' using OCR..."
        )
        try:
            element = self.page.locator(image_selector).first
            await element.wait_for(
                state="visible", timeout=10000
            )  # Wait for image to be visible

            # Take a screenshot of just the image element
            image_bytes = await element.screenshot()
            logging.info(f"Took screenshot of image element '{image_selector}'.")

            # Use pytesseract to extract text
            img = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img)
            extracted_text = text.strip()

            if extracted_text:
                logging.info(
                    f"Extracted text from image '{image_selector}'. Length: {len(extracted_text)}"
                )
                return extracted_text
            else:
                logging.warning(
                    f"OCR completed for image '{image_selector}', but no text was detected."
                )
                return "No text extracted from the image."

        except PlaywrightTimeoutError:
            error_msg = f"Error extracting text from image '{image_selector}': Image not found or not visible within timeout."
            logging.error(error_msg)
            return error_msg
        except ImportError:
            logging.error(
                "ImportError during OCR: Pillow or pytesseract might be missing."
            )
            return "Error: Missing dependency for OCR (Pillow or pytesseract). Please install them."
        except pytesseract.TesseractNotFoundError:
            logging.error(
                "Tesseract OCR engine not found. Please install Tesseract and ensure it's in the system PATH."
            )
            return (
                "Error: Tesseract OCR not found. Install Tesseract and add it to PATH."
            )
        except Exception as e:
            logging.error(
                f"Error extracting text from image '{image_selector}': {str(e)}",
                exc_info=True,
            )
            return f"Error extracting text from image '{image_selector}': {str(e)}"

    async def _execute_interaction_step(
        self, step: ET.Element, current_url: str
    ) -> str:
        """
        Internal method to handle execution of a single interaction step defined in XML.
        Includes retries, logging, screenshots, and page state summaries.

        Args:
            step (ET.Element): The XML element representing the step to execute.
            current_url (str): The URL of the page *before* executing this step.

        Returns:
            str: A result message indicating success (possibly with a page summary) or failure.
        """
        operation = self.safe_get_text(step.find("operation")).lower()
        selector = self.safe_get_text(step.find("selector"))
        description = self.safe_get_text(step.find("description"))
        value = self.safe_get_text(
            step.find("value")
        )  # Value can be input text OR target text for click
        retry_info = step.find("retry")  # Optional retry instructions

        if self.page is None or self.page.is_closed():
            return f"Error: Cannot execute step '{operation} {selector}': Page is not loaded or closed."

        # Log intent
        log_msg = f"[SUBACTIVITY][{self.activity_id}] Planning to perform: {operation}"
        if selector:
            log_msg += f" on selector '{selector}'"
        if value:
            log_msg += (
                f" with value/text '{value[:50]}{'...' if len(value)>50 else ''}'"
            )
        log_msg += f"\nDescription: {description}\nOn URL: [{current_url}]"

        if self.ApiClient:
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=log_msg,
                conversation_name=self.conversation_name,
            )

        # Take screenshot before action
        before_screenshot_path = os.path.join(
            self.WORKING_DIRECTORY, f"before_{operation}_{uuid.uuid4()}.png"
        )
        before_screenshot_url = ""
        try:
            await self.page.screenshot(path=before_screenshot_path, full_page=True)
            before_screenshot_name = os.path.basename(before_screenshot_path)
            if self.output_url:
                before_screenshot_url = f"{self.output_url}/{before_screenshot_name}"
                # Add screenshot link to the previous log message (optional, depends on API capabilities)
                # self.ApiClient.append_to_last_message(f"\n![Before Screenshot]({before_screenshot_url})")
        except Exception as ss_error:
            logging.error(f"Failed to take 'before' screenshot: {ss_error}")

        # Initialize retry parameters (Defaults + overrides from XML)
        max_attempts = 1  # Default to 1 attempt unless retry specified
        alternate_selector = None
        # fallback_operation = None # Fallback operation not implemented yet

        if retry_info is not None:
            alt_selector_elem = retry_info.find("alternate_selector")
            if alt_selector_elem is not None:
                alternate_selector = alt_selector_elem.text

            # fallback_op_elem = retry_info.find("fallback_operation")
            # if fallback_op_elem is not None: fallback_operation = fallback_op_elem.text

            max_attempts_elem = retry_info.find("max_attempts")
            if max_attempts_elem is not None and max_attempts_elem.text.isdigit():
                max_attempts = max(
                    1, int(max_attempts_elem.text)
                )  # Ensure at least 1 attempt

        # --- Execution Loop with Retries ---
        attempt = 0
        success = False
        last_error = "Operation not attempted."
        step_result_msg = ""

        while attempt < max_attempts and not success:
            attempt += 1
            current_selector = (
                alternate_selector if attempt > 1 and alternate_selector else selector
            )
            if not current_selector and operation not in [
                "wait",
                "done",
                "evaluate",
            ]:  # Need selector for most ops
                last_error = f"No selector provided for operation '{operation}' (Attempt {attempt})"
                logging.error(last_error)
                break  # No point retrying without a selector

            logging.info(
                f"Executing step (Attempt {attempt}/{max_attempts}): {operation} on '{current_selector}'"
            )

            try:
                op_result = None
                if operation == "click":
                    # Try text-based click first if value is provided
                    text_click_success = False
                    if value:
                        logging.info(f"Attempting text-based click for: '{value}'")
                        try:
                            # Try exact match first
                            locator = self.page.get_by_text(value, exact=True)
                            count = await locator.count()
                            if count == 1:  # Only click if unique exact match
                                await locator.click(timeout=5000)
                                text_click_success = True
                                op_result = f"Clicked element by exact text '{value}'"
                            elif count == 0:
                                # Try partial match if exact fails
                                locator = self.page.get_by_text(value, exact=False)
                                count = await locator.count()
                                if count == 1:  # Only click if unique partial match
                                    await locator.click(timeout=5000)
                                    text_click_success = True
                                    op_result = (
                                        f"Clicked element by partial text '{value}'"
                                    )
                                elif count > 1:
                                    logging.warning(
                                        f"Multiple elements contain text '{value}'. Skipping text click."
                                    )
                            # else count > 1 for exact match, also skip

                        except PlaywrightTimeoutError:
                            logging.info(f"Text-based click timed out for '{value}'.")
                        except Exception as text_error:
                            logging.warning(
                                f"Text-based click failed for '{value}': {text_error}. Falling back to selector."
                            )

                    # If text click didn't work or wasn't applicable, use selector
                    if not text_click_success:
                        if not current_selector:
                            raise ValueError(
                                "Click operation requires a selector if text matching fails or isn't applicable."
                            )
                        op_result = await self.click_element_with_playwright(
                            current_selector
                        )  # Uses its own internal waits
                    # Wait for page potentially changing
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                    await self.page.wait_for_timeout(500)  # Small extra wait

                elif operation == "fill":
                    if not current_selector:
                        raise ValueError("Fill operation requires a selector.")
                    op_result = await self.fill_input_with_playwright(
                        current_selector, value
                    )

                elif operation == "select":
                    if not current_selector:
                        raise ValueError("Select operation requires a selector.")
                    op_result = await self.select_option_with_playwright(
                        current_selector, value
                    )

                elif operation == "wait":
                    if value and value.isdigit():  # Wait for timeout
                        await self.page.wait_for_timeout(int(value))
                        op_result = f"Waited for {value} milliseconds."
                    elif current_selector:  # Wait for selector state
                        # Default state 'visible', could be specified in 'value' like "selector|hidden"
                        wait_state = "visible"
                        sel_to_wait = current_selector
                        if "|" in current_selector:
                            parts = current_selector.split("|", 1)
                            sel_to_wait = parts[0]
                            if parts[1] in [
                                "visible",
                                "hidden",
                                "attached",
                                "detached",
                                "enabled",
                                "disabled",
                                "editable",
                            ]:
                                wait_state = parts[1]
                        op_result = await self.wait_for_selector_with_playwright(
                            sel_to_wait, state=wait_state
                        )
                    else:
                        raise ValueError(
                            "Wait operation requires a duration (ms) in 'value' or a selector."
                        )

                elif operation == "verify":
                    if not current_selector:
                        raise ValueError("Verify operation requires a selector.")
                    op_result = await self.assert_element_with_playwright(
                        current_selector, expected_text=value
                    )

                elif operation == "screenshot":
                    # 'value' here is the save_path (optional)
                    op_result = (
                        await self.take_screenshot_with_highlight_with_playwright(
                            selector=current_selector, save_path=value
                        )
                    )

                elif operation == "extract_text":  # Renamed from 'extract' for clarity
                    if not current_selector:
                        raise ValueError(
                            "Extract Text operation requires an image selector."
                        )
                    op_result = await self.extract_text_from_image_with_playwright(
                        current_selector
                    )  # Returns extracted text or error

                elif operation == "download":
                    # 'selector' is the trigger, 'value' is optional save path
                    if not current_selector:
                        raise ValueError(
                            "Download operation requires a trigger selector."
                        )
                    op_result = await self.download_file_with_playwright(
                        trigger_selector=current_selector, save_path=value
                    )

                elif operation == "evaluate":
                    # 'value' contains the script
                    if not value:
                        raise ValueError(
                            "Evaluate operation requires JavaScript code in 'value'."
                        )
                    op_result = await self.evaluate_javascript_with_playwright(value)

                elif (
                    operation == "get_content"
                ):  # New operation to explicitly get content
                    op_result = (
                        await self.get_page_content()
                    )  # Returns content string or error

                elif (
                    operation == "get_fields"
                ):  # New operation to explicitly get fields
                    op_result = (
                        await self.get_form_fields()
                    )  # Returns field string or error

                elif operation == "done":
                    op_result = "Task marked as complete by plan."
                    success = True  # Mark as success to exit loop

                else:
                    raise ValueError(f"Unknown operation specified: {operation}")

                # Check if operation itself returned an error message
                if isinstance(op_result, str) and (
                    "Error:" in op_result
                    or "failed" in op_result.lower()
                    or "Warning:" in op_result
                ):
                    raise Exception(
                        op_result
                    )  # Treat internal errors/failures as exceptions for retry logic

                # If no exception, assume success for this attempt
                success = True
                step_result_msg = (
                    op_result
                    if isinstance(op_result, str)
                    else f"{operation} completed successfully."
                )
                logging.info(f"Step successful (Attempt {attempt}): {step_result_msg}")

            except Exception as e:
                last_error = f"Error during {operation} on '{current_selector}' (Attempt {attempt}/{max_attempts}): {str(e)}"
                logging.warning(last_error)
                if attempt >= max_attempts:  # If this was the last attempt
                    break  # Exit loop, failure will be handled below
                else:
                    # Optional: Wait before retrying
                    await self.page.wait_for_timeout(1000)
                    logging.info("Retrying step...")

        # --- Post-Execution ---
        post_op_screenshot_url = ""
        if success:
            # Take screenshot after successful action
            after_screenshot_path = os.path.join(
                self.WORKING_DIRECTORY, f"after_{operation}_{uuid.uuid4()}.png"
            )
            try:
                await self.page.screenshot(path=after_screenshot_path, full_page=True)
                after_screenshot_name = os.path.basename(after_screenshot_path)
                if self.output_url:
                    post_op_screenshot_url = (
                        f"{self.output_url}/{after_screenshot_name}"
                    )
            except Exception as ss_error:
                logging.error(f"Failed to take 'after' screenshot: {ss_error}")

            # Get updated URL and generate summary
            new_url = self.page.url
            summary = ""
            try:
                # Only generate summary if operation wasn't just getting content/fields
                if operation not in [
                    "get_content",
                    "get_fields",
                    "screenshot",
                    "verify",
                    "wait",
                    "evaluate",
                    "done",
                ]:
                    new_content = await self.get_page_content()  # Get fresh content
                    summary_prompt = f"""Analyze the current page state after successfully performing the operation '{operation}'.

Operation Result: {step_result_msg}
Previous URL: {current_url}
Current URL: {new_url}

Provide a concise summary including:
1. Key changes observed on the page (if any).
2. The main purpose/content of the current view.
3. Any immediately obvious next steps or calls to action.

Current Page Content Snippet (for context):
{new_content[:2000]}...
"""
                    if self.ApiClient:
                        summary = self.ApiClient.prompt_agent(
                            agent_name=self.agent_name,
                            prompt_name="Think About It",  # Or a dedicated summarization prompt
                            prompt_args={
                                "user_input": summary_prompt,
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
                        logging.info("Generated page summary after successful step.")
            except Exception as summary_error:
                logging.error(f"Failed to generate page summary: {summary_error}")
                summary = "(Failed to generate summary)"

            final_message = (
                f"[SUBACTIVITY][{self.activity_id}] Successfully completed: {operation}"
            )
            if selector:
                final_message += f" on '{selector}'"
            final_message += f"\nResult: {step_result_msg}\nStarted on: [{current_url}]\nEnded on: [{new_url}]"
            if before_screenshot_url:
                final_message += f"\n![Before]({before_screenshot_url})"
            if post_op_screenshot_url:
                final_message += f"\n![After]({post_op_screenshot_url})"
            if summary:
                final_message += f"\n\nPage Summary:\n{summary}"

            if self.ApiClient:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=final_message,
                    conversation_name=self.conversation_name,
                )
            return step_result_msg  # Return the core result message

        else:  # Step failed after all attempts
            error_screenshot_path = os.path.join(
                self.WORKING_DIRECTORY, f"error_{operation}_{uuid.uuid4()}.png"
            )
            error_screenshot_url = ""
            try:
                await self.page.screenshot(path=error_screenshot_path, full_page=True)
                error_screenshot_name = os.path.basename(error_screenshot_path)
                if self.output_url:
                    error_screenshot_url = f"{self.output_url}/{error_screenshot_name}"
            except Exception as ss_error:
                logging.error(f"Failed to take 'error' screenshot: {ss_error}")

            error_msg = f"Failed to complete '{operation}' on selector '{selector}' after {max_attempts} attempt(s)."
            final_message = f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}\nLast Error: {last_error}\nOn URL: [{self.page.url}]"
            if error_screenshot_url:
                final_message += f"\n![Error Screenshot]({error_screenshot_url})"

            if self.ApiClient:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=final_message,
                    conversation_name=self.conversation_name,
                )
            return (
                f"Error: {error_msg}. Last Error: {last_error}"  # Return detailed error
            )

    def safe_get_text(self, element, default="") -> str:
        """Safely extracts text from an XML element."""
        if element is None or element.text is None:
            return default
        return element.text.strip()

    def extract_interaction_block(self, response: str) -> str:
        """Extracts the <interaction>...</interaction> XML block from a response string."""
        # Allow for potential variations in whitespace and attributes within the interaction tag
        match = re.search(
            r"<interaction.*?>.*?</interaction>", response, re.DOTALL | re.IGNORECASE
        )
        if not match:
            # Fallback: Maybe the AI just gave the <step> directly?
            match = re.search(r"<step>.*?</step>", response, re.DOTALL | re.IGNORECASE)
            if match:
                # Wrap the step in an interaction block
                logging.warning(
                    "Found <step> block outside <interaction>, wrapping it."
                )
                return f'<?xml version="1.0" encoding="UTF-8"?>\n<interaction>{match.group(0)}</interaction>'
            raise ValueError(
                "No valid <interaction> or <step> block found in response."
            )

        xml_block = match.group(0).strip()
        # Basic cleaning (less aggressive)
        xml_block = re.sub(
            r"^\s+", "", xml_block, flags=re.MULTILINE
        )  # Remove leading whitespace per line
        # Ensure XML declaration
        if not xml_block.startswith("<?xml"):
            xml_block = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_block
        return xml_block

    def is_valid_selector(self, selector: str) -> bool:
        """
        Validates if a selector is likely to be stable and usable.
        Allows IDs, name, placeholder, data-testid, aria-label attributes,
        specific input/button types, and link hrefs.
        Rejects selectors starting with '.' (classes) or containing complex CSS combinators.
        """
        if not selector or not isinstance(selector, str):
            return False

        selector = selector.strip()

        # Reject complex selectors or class-based ones immediately
        if selector.startswith(".") or any(
            c in selector for c in [" > ", " + ", " ~ ", ":nth-child"]
        ):
            logging.warning(
                f"Rejecting potentially unstable/complex selector: {selector}"
            )
            return False

        # Allow specific, generally stable patterns
        # Note: These patterns are simplified; robust CSS parsing is complex.
        valid_patterns = [
            r"^#[\w\-]+$",  # IDs: #my-id
            r'^\[name=[\'"]?[\w\-]+[\'"]?\]$',  # name attribute: [name="user"]
            r'^input\[name=[\'"]?[\w\-]+[\'"]?\]$',  # input name: input[name="email"]
            r'^\[placeholder=[\'"]?.*[\'"]?\]$',  # placeholder attribute: [placeholder="Search..."]
            r'^input\[placeholder=[\'"]?.*[\'"]?\]$',  # input placeholder: input[placeholder="Enter name"]
            r'^button\[type=[\'"]?(submit|button|reset)[\'"]?\]$',  # button types: button[type="submit"]
            r'^input\[type=[\'"]?\w+[\'"]?\]$',  # input types: input[type="checkbox"]
            r'^a\[href=[\'"]?.*?[\'"]?\]$',  # links by href: a[href="/login"]
            r'^\[data-testid=[\'"]?[\w\-]+[\'"]?\]$',  # data-testid: [data-testid="login-button"]
            r'^[\w]+\[data-testid=[\'"]?[\w\-]+[\'"]?\]$',  # tag with data-testid: button[data-testid="submit"]
            r'^\[aria-label=[\'"]?.*[\'"]?\]$',  # aria-label: [aria-label="Close dialog"]
            r'^[\w]+\[aria-label=[\'"]?.*[\'"]?\]$',  # tag with aria-label: button[aria-label="Settings"]
            r'^select\[name=[\'"]?[\w\-]+[\'"]?\]$',  # select by name: select[name="country"]
            r'^textarea\[name=[\'"]?[\w\-]+[\'"]?\]$',  # textarea by name: textarea[name="message"]
            # Simple tag names (less specific, use with caution)
            # r'^button$',
            # r'^select$',
            # r'^textarea$',
            # r'^a$'
        ]

        if any(re.fullmatch(pattern, selector) for pattern in valid_patterns):
            return True
        else:
            logging.warning(
                f"Selector '{selector}' did not match allowed stable patterns."
            )
            return False

    def is_repeat_failure(self, operation, selector, value, attempt_history, window=3):
        """Checks if the same action (op+selector+value) has failed recently."""
        # Normalize the action description for comparison
        action_key = f"{operation}|{selector}|{value}"
        action_key_no_val = f"{operation}|{selector}|"  # Check without value too, in case value changed slightly

        recent_failures = 0
        # Look at the last 'window' entries in the history
        for past_attempt_record in attempt_history[-window:]:
            # Check if the record indicates a failure and matches the action
            if (
                "Error:" in past_attempt_record
                or "fail" in past_attempt_record.lower()
                or "EXCEPTION:" in past_attempt_record
            ):
                # Check if the core action matches (with or without value)
                if (
                    action_key in past_attempt_record
                    or action_key_no_val in past_attempt_record
                ):
                    recent_failures += 1

        # Consider it a repeat failure if it failed multiple times recently (e.g., >= 2)
        return recent_failures >= 2

    async def interact_with_webpage(self, url: str, task: str):
        """
        Executes a multi-step web interaction workflow based on a natural language task.
        This command is suitable for complex actions like form filling, multi-page navigation,
        login processes, and information extraction across pages.

        The assistant uses Playwright to interact with the page and an LLM to plan each step.
        It iteratively:
        1. Analyzes the current page state (URL, content, form fields).
        2. Prompts an LLM to determine the *single next best step* (e.g., click, fill, wait)
           based on the overall task and current state, using only stable selectors.
        3. Executes the planned step using Playwright actions.
        4. Validates the step's outcome and handles errors with retries or stops if necessary.
        5. Logs detailed sub-activities, including screenshots and page summaries.
        6. Continues until the task is marked 'done' by the LLM plan or a maximum number
           of iterations is reached.

        Args:
            url (str): The starting URL for the web interaction workflow.
            task (str): A natural language description of the overall goal to be accomplished
                      (e.g., "Log in using username 'test' and password 'pass123'",
                      "Find the contact email address on the about page",
                      "Add the first product to the cart").

        Returns:
            str: A summary of the actions taken, the final status (success or failure),
                 and potentially the result of the task (e.g., extracted information).
                 Detailed logs are sent via ApiClient messages.
        """

        if not url:
            return "Error: URL must be provided."
        if not task:
            return "Error: Task description must be provided."

        if not url.startswith("http"):
            url = "https://" + url

        # Initialize browser if needed, navigate to start URL
        try:
            nav_result = await self.navigate_to_url_with_playwright(
                url=url, headless=True
            )
            if "Error" in nav_result:
                return f"Failed to start interaction: {nav_result}"
        except Exception as nav_error:
            return (
                f"Failed to initialize browser or navigate to starting URL: {nav_error}"
            )

        max_iterations = 15  # Increased max iterations
        iteration_count = 0
        results_summary = []  # User-facing summary of steps/results
        attempt_history = []  # Internal history for LLM planning context

        last_url = None

        while iteration_count < max_iterations:
            iteration_count += 1
            logging.info(
                f"--- Interaction Iteration {iteration_count}/{max_iterations} ---"
            )

            if self.page is None or self.page.is_closed():
                error_msg = "Page closed unexpectedly during interaction. Stopping."
                logging.error(error_msg)
                results_summary.append(
                    f"[Iteration {iteration_count}] Error: {error_msg}"
                )
                if self.ApiClient:
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                        conversation_name=self.conversation_name,
                    )
                break

            current_url = self.page.url
            url_changed = current_url != last_url
            last_url = current_url

            # --- 1. Analyze Current State ---
            try:
                current_page_content = await self.get_page_content()

                form_fields_info = await self.get_form_fields()
                # Extract only the stable selectors from form_fields_info for the prompt
                available_selectors = []
                if isinstance(form_fields_info, str):
                    for line in form_fields_info.split("\n"):
                        if "Selectors: " in line:
                            selectors_part = line.split("Selectors: ")[1]
                            # Extract selectors within quotes
                            found_sels = re.findall(r"\'(.*?)\'", selectors_part)
                            for sel in found_sels:
                                if (
                                    self.is_valid_selector(sel)
                                    and sel not in available_selectors
                                ):
                                    available_selectors.append(sel)
                else:
                    logging.warning("Could not parse form fields for stable selectors.")

            except Exception as analysis_error:
                error_msg = f"Error analyzing page state: {analysis_error}. Stopping interaction."
                logging.error(error_msg, exc_info=True)
                results_summary.append(
                    f"[Iteration {iteration_count}] Error: {error_msg}"
                )
                if self.ApiClient:
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                        conversation_name=self.conversation_name,
                    )
                break

            # --- 2. Plan Next Step ---
            planning_context = f"""You are an autonomous web interaction agent. Plan the *single next step* to accomplish the overall task.

OVERALL TASK: {task}

CURRENT STATE:
- Iteration: {iteration_count}/{max_iterations}
- Current URL: {current_url}
- URL Changed Since Last Step: {url_changed}

AVAILABLE STABLE SELECTORS (Prefer these):
{os.linesep.join([f'- {s}' for s in available_selectors]) if available_selectors else '- (No specific stable selectors detected, rely on standard attributes like name, type, placeholder or text content for clicks/verification)'}

FORM FIELDS & INTERACTIVE ELEMENTS (Details for context):
{form_fields_info[:1500] + '...' if len(form_fields_info) > 1500 else form_fields_info}

VISIBLE PAGE CONTENT:
{current_page_content}

PREVIOUS STEP ATTEMPTS & OUTCOMES (Recent history):
{os.linesep.join(attempt_history[-5:])}

RULES & INSTRUCTIONS FOR YOUR RESPONSE:
1.  Respond with ONLY a single XML block `<interaction><step>...</step></interaction>` wrapped in <answer> and </answer> tags.
2.  Define ONE operation: `click`, `fill`, `select`, `wait`, `verify`, `get_content`, `get_fields`, `evaluate`, `screenshot`, `download`, `extract_text`, `done`.
3.  Use the `<selector>` tag with a stable selector (ID, name, data-testid, aria-label, placeholder, type, href). AVOID CLASS SELECTORS (like '.btn'). If no stable selector is obvious, describe the element and consider 'wait' or using text for clicks.
4.  For `click`: If clicking a button/link with visible text, put the EXACT text in the `<value>` tag. The system will try clicking by text first, then fall back to the selector if needed.
5.  For `fill`, `select`, `evaluate`: Put the text/value/script to use in the `<value>` tag.
6.  For `wait`: Use `<selector>` for an element to wait for (e.g., `#results|visible`), OR put milliseconds in `<value>` (e.g., 5000).
7.  For `verify`: Use `<selector>` for the element, and the text it should contain in `<value>`.
8.  For `download`: Use `<selector>` for the trigger element (link/button), `<value>` for optional save path.
9.  For `extract_text`: Use `<selector>` for the target image.
10. For `get_content` / `get_fields`: No selector/value needed, they operate on the current page.
11. Use `<description>` to explain WHY this step helps achieve the main task.
12. If the task is fully complete, use operation `done`.
13. If stuck (e.g., element not found after waiting, repeated failures), consider `wait` or describe the issue and use `done` if truly blocked. Avoid infinite loops of failed actions.

EXAMPLE CLICKS:
<interaction><step><operation>click</operation><selector>button[data-testid='login-btn']</selector><value>Log In</value><description>Click the login button using its test ID and text.</description></step></interaction>
<interaction><step><operation>click</operation><selector>a[href='/about']</selector><value>About Us</value><description>Navigate to the About Us page using its link text.</description></step></interaction>

EXAMPLE FILL:
<interaction><step><operation>fill</operation><selector>input[name='username']</selector><value>my_user</value><description>Fill the username field.</description></step></interaction>

EXAMPLE WAIT:
<interaction><step><operation>wait</operation><selector>#results-table|visible</selector><value></value><description>Wait for the results table to become visible.</description></step></interaction>

NOW, PROVIDE THE XML FOR THE NEXT STEP:
"""

            try:
                if not self.ApiClient:
                    raise RuntimeError("ApiClient is not configured.")

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

                if not raw_plan or not isinstance(raw_plan, str):
                    raise ValueError("LLM did not return a valid plan string.")

                # --- 3. Parse and Validate Step ---
                interaction_xml = self.extract_interaction_block(raw_plan)
                root = ET.fromstring(interaction_xml)
                steps = root.findall(".//step")

                if not steps:
                    raise ValueError("Parsed XML does not contain a <step> element.")

                step = steps[0]  # Process only the first step per iteration
                operation = self.safe_get_text(step.find("operation")).lower()
                selector = self.safe_get_text(step.find("selector"))
                value = self.safe_get_text(step.find("value"))
                description = self.safe_get_text(step.find("description"))

                # Basic validation
                if not operation:
                    raise ValueError("Operation is missing in the plan step.")
                if operation not in [
                    "click",
                    "fill",
                    "select",
                    "wait",
                    "verify",
                    "done",
                    "get_content",
                    "get_fields",
                    "evaluate",
                    "screenshot",
                    "download",
                    "extract_text",
                ]:
                    raise ValueError(f"Invalid operation '{operation}' planned.")

                # Validate selector stability (unless not needed for the operation)
                if (
                    operation
                    not in ["wait", "done", "evaluate", "get_content", "get_fields"]
                    and selector
                    and not self.is_valid_selector(selector)
                ):
                    # If selector is invalid, but we have text value for click, maybe allow it? Risky.
                    if operation == "click" and value:
                        logging.warning(
                            f"Planned click has invalid selector '{selector}' but text value '{value}'. Will rely solely on text matching."
                        )
                        # Clear the invalid selector to prevent its use
                        selector = ""  # Overwrite the invalid selector from the step object for execution
                        step.find("selector").text = (
                            ""  # Also update the XML element if needed elsewhere
                        )
                    else:
                        raise ValueError(
                            f"Invalid or unstable selector '{selector}' planned for operation '{operation}'. Use ID, name, data-testid, aria-label, placeholder, type, href, or rely on text for clicks."
                        )

                # Check for task completion
                if operation == "done":
                    logging.info(
                        f"Plan indicates task is complete. Reason: {description}"
                    )
                    results_summary.append(
                        f"[Iteration {iteration_count}] Task marked as complete. {description}"
                    )
                    break  # Exit the main loop

                # Check for repeated failed actions to prevent loops
                if self.is_repeat_failure(operation, selector, value, attempt_history):
                    error_msg = f"Preventing repeated failed action: '{operation}' on '{selector}'. Need a different approach. Stopping."
                    logging.error(error_msg)
                    results_summary.append(
                        f"[Iteration {iteration_count}] Error: {error_msg}"
                    )
                    attempt_history.append(
                        f"FAILED_REPEAT: {operation}|{selector}|{value} -> {error_msg}"
                    )
                    if self.ApiClient:
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                            conversation_name=self.conversation_name,
                        )
                    break  # Stop if we detect a loop of failures

                # Record this attempt *before* execution for the history
                attempt_record = f"Attempt {iteration_count}: {operation}|{selector}|{value} - {description}"
                # Don't add to attempt_history here yet, add based on outcome below

                # --- 4. Execute Step ---
                step_result = await self._execute_interaction_step(step, current_url)

                # --- 5. Process Result ---
                results_summary.append(
                    f"[Iteration {iteration_count}] {operation}: {step_result}"
                )

                # Update history based on outcome for next planning iteration
                if "Error:" in step_result or "failed" in step_result.lower():
                    attempt_history.append(
                        f"{attempt_record} -> Outcome: FAILED - {step_result}"
                    )
                    # Optional: break on first error? Or let LLM try to recover?
                    # For now, let's allow LLM to try recovering unless it's a repeat failure.
                    # break
                else:
                    attempt_history.append(
                        f"{attempt_record} -> Outcome: SUCCESS - {step_result}"
                    )

            except (ET.ParseError, ValueError, RuntimeError) as plan_exec_error:
                error_msg = f"Error processing or executing plan on iteration {iteration_count}: {str(plan_exec_error)}"
                logging.error(error_msg, exc_info=True)
                results_summary.append(
                    f"[Iteration {iteration_count}] Error: {error_msg}"
                )
                attempt_history.append(
                    f"EXCEPTION Iteration {iteration_count}: {error_msg}"
                )
                # Take screenshot on planning/parsing failure
                screenshot_path = os.path.join(
                    self.WORKING_DIRECTORY,
                    f"error_plan_exec_{iteration_count}_{uuid.uuid4()}.png",
                )
                screenshot_msg = ""
                try:
                    if self.page and not self.page.is_closed():
                        await self.page.screenshot(path=screenshot_path, full_page=True)
                        screenshot_name = os.path.basename(screenshot_path)
                        if self.output_url:
                            screenshot_msg = f"\n\n![Error Screenshot]({self.output_url}/{screenshot_name})"
                except Exception as ss_error:
                    screenshot_msg = (
                        f"\n\n(Failed to take error screenshot: {ss_error})"
                    )

                if self.ApiClient:
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}{screenshot_msg}",
                        conversation_name=self.conversation_name,
                    )
                break  # Stop interaction on fatal planning/execution error

            except Exception as e:  # Catch unexpected errors
                error_msg = f"Unexpected error on iteration {iteration_count}: {str(e)}"
                logging.error(error_msg, exc_info=True)
                results_summary.append(
                    f"[Iteration {iteration_count}] Error: {error_msg}"
                )
                attempt_history.append(
                    f"EXCEPTION Iteration {iteration_count}: {error_msg}"
                )
                # Take screenshot on unexpected failure
                screenshot_path = os.path.join(
                    self.WORKING_DIRECTORY,
                    f"error_unexpected_{iteration_count}_{uuid.uuid4()}.png",
                )
                screenshot_msg = ""
                try:
                    if self.page and not self.page.is_closed():
                        await self.page.screenshot(path=screenshot_path, full_page=True)
                        screenshot_name = os.path.basename(screenshot_path)
                        if self.output_url:
                            screenshot_msg = f"\n\n![Error Screenshot]({self.output_url}/{screenshot_name})"
                except Exception as ss_error:
                    screenshot_msg = (
                        f"\n\n(Failed to take error screenshot: {ss_error})"
                    )

                if self.ApiClient:
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}{screenshot_msg}",
                        conversation_name=self.conversation_name,
                    )
                break  # Stop interaction

        # --- End of Loop ---
        if iteration_count >= max_iterations and operation != "done":
            logging.warning(
                f"Interaction stopped after reaching max iterations ({max_iterations}) without completion."
            )
            results_summary.append("Interaction stopped: Reached maximum iterations.")
            if self.ApiClient:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Interaction stopped after {max_iterations} iterations.",
                    conversation_name=self.conversation_name,
                )

        # --- 7. Final Result ---
        final_output = (
            f"Web interaction task '{task}' finished.\nSummary of actions:\n"
            + "\n".join(results_summary)
        )
        logging.info(f"Interaction task '{task}' finished. Final URL: {last_url}")

        # Optionally close browser here or let it persist
        # await self.close_browser_with_playwright()

        return final_output

    async def get_page_content(self) -> str:
        """
        Retrieves and structures the content of the current page, focusing on text,
        links, and semantic elements. Uses BeautifulSoup for parsing.

        This is useful for providing context to the LLM for planning or analysis.

        Returns:
            str: A structured string representation of the page content, including title,
                 headers, main text blocks, and links. Returns an error message if
                 the page is not loaded or parsing fails.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        logging.info("Retrieving and structuring page content...")
        try:
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")
            structured_content = []

            # Extract title
            if soup.title and soup.title.string:
                title_text = soup.title.string.strip()
                if title_text:
                    structured_content.append(f"Page Title: {title_text}")

            # Extract main content, headers, paragraphs, lists
            # Try common semantic tags first
            main_areas = soup.find_all(["main", "article", "section"])
            if not main_areas:
                main_areas = [soup.body]  # Fallback to body

            content_texts = []
            for area in main_areas:
                if not area:
                    continue
                # Find text-bearing elements, avoid script/style/nav/form
                elements = area.find_all(
                    ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "span", "div", "a"],
                    recursive=True,
                )
                for element in elements:
                    # Basic filtering
                    if element.find_parent(
                        ["script", "style", "nav", "footer", "form", "button"]
                    ):
                        continue
                    # Get text, clean whitespace, ignore if too short
                    text = self.get_text_safely(element)
                    text = " ".join(text.split())  # Normalize whitespace
                    if text and len(text) > 10:  # Filter out very short/empty strings
                        # Prepend header markers
                        if element.name.startswith("h") and element.name[1].isdigit():
                            level = int(element.name[1])
                            content_texts.append(f"{'#' * level} {text}")
                        elif element.name == "a" and element.get("href"):
                            # Include link text and href
                            href = element.get("href")
                            content_texts.append(f"Link: '{text}' (href: {href})")
                        elif element.name == "li":
                            content_texts.append(f"- {text}")  # Simple list marker
                        # Avoid adding redundant text from parents already captured
                        elif not any(
                            parent == element
                            for parent in element.find_parents(["p", "div", "span"])
                        ):
                            if text not in content_texts[-5:]:  # Avoid near duplicates
                                content_texts.append(text)

            if content_texts:
                structured_content.append("\n=== Page Content ===")
                # Limit the number of text elements to avoid huge output
                structured_content.extend(
                    content_texts[:100]
                )  # Limit to first 100 significant text blocks
                if len(content_texts) > 100:
                    structured_content.append("\n[... Content truncated ...]")

            final_content = "\n".join(filter(None, structured_content))
            # Further cleanup
            final_content = re.sub(
                r"\n\s*\n", "\n\n", final_content
            )  # Consolidate multiple newlines

            logging.info(
                f"Page content retrieved and structured. Length: {len(final_content)}"
            )
            return (
                final_content.strip()
                if final_content
                else "No significant content extracted."
            )

        except Exception as e:
            error_msg = f"Error extracting page content: {str(e)}"
            logging.error(error_msg, exc_info=True)
            if self.ApiClient:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                    conversation_name=self.conversation_name,
                )
            return error_msg

    async def analyze_page_visually(self, description: str = "") -> str:
        """
        Takes a screenshot of the current page and uses an LLM (via APIClient) to analyze it
        visually based on the provided description or task context.

        This command is useful when:
        - The structure is complex and text extraction is insufficient.
        - Verifying visual layout, element presence, or state (e.g., "Is the error message visible?").
        - Debugging interaction issues ("Why didn't the click work? Analyze the screenshot.").
        - Understanding pages heavily reliant on images or canvas elements.

        Args:
            description (str): A natural language description of what the analysis should focus on.
                               If empty, a general visual analysis will be requested.
                               Example: "Check if the login form appears correctly with username,
                                         password fields, and a login button."

        Example Usage in Agent Thought/Plan:
        <execute>
          <command>Analyze Page Visually</command>
          <args>
            <description>Verify that the shopping cart icon shows '1 item' after adding the product.</description>
          </args>
        </execute>

        Returns:
            str: The textual analysis result provided by the LLM based on the screenshot,
                 or an error message if the process fails.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."
        if not self.ApiClient:
            return "Error: ApiClient is not configured, cannot perform visual analysis."

        logging.info(
            f"Starting visual page analysis. Description: {description or 'General analysis'}"
        )

        try:
            # 1. Take screenshot
            screenshot_path = os.path.join(
                self.WORKING_DIRECTORY, f"visual_analysis_{uuid.uuid4()}.png"
            )
            await self.page.screenshot(path=screenshot_path, full_page=True)
            file_name = os.path.basename(screenshot_path)
            output_url = f"{self.output_url}/{file_name}" if self.output_url else None

            if not output_url:
                # Fallback: Maybe encode image data if URL output isn't available? Requires agent support.
                logging.warning(
                    "Output URL not configured. Visual analysis may fail if agent cannot access local files."
                )
                # For now, proceed assuming agent might handle path or URL is implicitly known
                image_ref = screenshot_path  # Pass local path if no URL
            else:
                image_ref = output_url  # Pass URL

            # 2. Get context
            current_url = self.page.url

            # 3. Prompt LLM for analysis
            analysis_prompt = f"""Analyze the provided webpage screenshot based on the following task/description.

### Current URL
{current_url}

### Analysis Task
{description if description else "Provide a general analysis of the page's visual state, structure, and key elements."}

### Instructions
Focus your analysis on the elements relevant to the task. Describe:
1.  The presence, appearance, and state of key UI elements mentioned or implied in the task.
2.  Overall layout and structure relevant to the task.
3.  Any visible text, icons, or data directly related to the task.
4.  Conclude whether the visual state aligns with what's expected based on the task description.

Analyze the attached screenshot.
"""
            logging.info(f"Sending screenshot ({image_ref}) to LLM for analysis.")
            analysis_result = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": analysis_prompt,
                    "images": [image_ref],  # Pass image URL or path
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

            if not analysis_result or not isinstance(analysis_result, str):
                raise RuntimeError("LLM did not return a valid analysis string.")

            # 4. Log and return result
            log_message = f"[SUBACTIVITY][{self.activity_id}] Visual Analysis Complete for '{description or 'page'}':\n{analysis_result}\nScreenshot: {image_ref}"
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=log_message,
                conversation_name=self.conversation_name,
            )
            logging.info("Visual analysis completed successfully.")
            return analysis_result

        except (
            RuntimeError
        ) as rt_error:  # Catch specific runtime errors like no ApiClient
            logging.error(f"Runtime error during visual analysis: {rt_error}")
            return f"Error: {rt_error}"
        except Exception as e:
            error_msg = f"Error analyzing page visually: {str(e)}"
            logging.error(error_msg, exc_info=True)
            if self.ApiClient:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}][ERROR] {error_msg}",
                    conversation_name=self.conversation_name,
                )
            return error_msg
