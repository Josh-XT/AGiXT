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
        }
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.popup = None

    async def take_verified_screenshot(
        self, prefix: str, extra_logging: str = "", element_to_highlight: str = None
    ) -> tuple[str, str]:
        """
        Take and verify a screenshot, with optional element highlighting

        Args:
            prefix: String prefix for the screenshot filename
            extra_logging: Additional context to add to log messages
            element_to_highlight: Optional CSS selector of element to highlight

        Returns:
            tuple: (filename, full_path) if successful, (None, None) if failed
        """
        try:
            # Set up screenshot path
            filename = f"{prefix}_{uuid.uuid4()}.png"
            full_path = os.path.join(self.WORKING_DIRECTORY, filename)

            # Wait for network idle
            await self.page.wait_for_load_state("networkidle")

            # Get viewport and layout dimensions
            dimensions = await self.page.evaluate(
                """() => {
                return {
                    viewport: {
                        width: window.innerWidth,
                        height: window.innerHeight
                    },
                    layout: {
                        width: Math.max(
                            document.documentElement.scrollWidth,
                            document.documentElement.clientWidth
                        ),
                        height: Math.max(
                            document.documentElement.scrollHeight,
                            document.documentElement.clientHeight
                        )
                    },
                    scroll: {
                        x: window.scrollX,
                        y: window.scrollY
                    }
                }
            }"""
            )

            # If highlighting an element, get its position
            if element_to_highlight:
                element = await self.page.query_selector(element_to_highlight)
                if element:
                    box = await element.bounding_box()
                    if box:
                        # Ensure viewport includes element
                        await element.scroll_into_view_if_needed()
                        # Set scroll position to show context around element
                        scroll_y = max(
                            0, box["y"] - (dimensions["viewport"]["height"] / 4)
                        )
                        await self.page.evaluate(f"window.scrollTo(0, {scroll_y});")

            # Take the screenshot
            await self.page.screenshot(
                path=full_path,
                full_page=False,  # Only capture current viewport
                timeout=10000,
            )

            # Verify the screenshot was saved and has content
            if not os.path.exists(full_path):
                raise Exception("Screenshot file was not created")

            file_size = os.path.getsize(full_path)
            if file_size == 0:
                raise Exception("Screenshot file is empty")

            logging.info(
                f"Screenshot {filename} ({file_size} bytes) {extra_logging}\n"
                f"Viewport: {dimensions['viewport']}\n"
                f"Scroll position: {dimensions['scroll']}"
            )
            return filename, full_path

        except Exception as e:
            logging.error(f"Failed to take screenshot: {str(e)}")
            return None, None

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
        """Navigate to a URL using Playwright"""
        try:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(headless=headless)
                self.context = await self.browser.new_context()
                self.page = await self.context.new_page()
            await self.page.goto(url)
            logging.info(f"Navigated to {url}")

            # Take a screenshot after navigation
            screenshot_name, _ = await self.take_verified_screenshot(
                "navigation", f"after navigating to {url}"
            )
            if screenshot_name:
                return f"Navigated to {url}\n![Navigation Screenshot]({self.output_url}/{screenshot_name})"
            return f"Navigated to {url}"
        except Exception as e:
            logging.error(f"Error navigating to {url}: {str(e)}")
            return f"Error: {str(e)}"

    async def click_element_with_playwright(self, selector: str) -> str:
        """Enhanced click operation with multiple fallback strategies"""
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."

            current_url = self.page.url
            logging.info(f"Attempting to click element {selector} on {current_url}")

            # Take screenshot of current state
            pre_scroll_name, _ = await self.take_verified_screenshot(
                "pre_scroll", f"before attempting to click {selector}"
            )

            # Try different selector strategies
            strategies = [
                # Direct selector
                selector,
                # Button or link with exact text
                f"button:has-text('{selector}')",
                f"a:has-text('{selector}')",
                # Case-insensitive text match
                f"button:has-text('{selector}'i)",
                f"a:has-text('{selector}'i)",
                # Elements with role=button and text
                f"[role='button']:has-text('{selector}')",
                # Div or span with text
                f"div:has-text('{selector}')",
                f"span:has-text('{selector}')",
                # By aria-label
                f"[aria-label='{selector}']",
            ]

            element = None
            used_strategy = None

            # Log all visible clickable elements for debugging
            elements_debug = await self.page.evaluate(
                """() => {
                const getAllClickable = () => {
                    const elements = [];
                    document.querySelectorAll('button, a, [role="button"], [onclick], .btn, .button').forEach(el => {
                        if (el.offsetWidth > 0 && el.offsetHeight > 0 && el.innerText.trim()) {
                            elements.push({
                                tag: el.tagName,
                                text: el.innerText.trim(),
                                classes: el.className,
                                href: el.href || '',
                                role: el.getAttribute('role') || '',
                                id: el.id || ''
                            });
                        }
                    });
                    return elements;
                };
                return getAllClickable();
            }"""
            )

            logging.info(f"Clickable elements found: {elements_debug}")

            # Try each strategy
            for strat in strategies:
                try:
                    logging.info(f"Trying selector strategy: {strat}")
                    # First check if element exists
                    element = await self.page.query_selector(strat)
                    if element:
                        # Check if element is visible
                        is_visible = await element.is_visible()
                        if is_visible:
                            # Get element position
                            box = await element.bounding_box()
                            if box:
                                used_strategy = strat
                                break
                except Exception as e:
                    logging.info(f"Strategy {strat} failed: {str(e)}")
                    continue

            if not element or not used_strategy:
                # Try JavaScript click as last resort
                try:
                    await self.page.evaluate(
                        f"""
                        const findAndClick = (text) => {{
                            const elements = Array.from(document.querySelectorAll('button, a, [role="button"], [onclick], .btn, .button'));
                            const element = elements.find(el => 
                                el.innerText.trim().toLowerCase() === text.toLowerCase() ||
                                el.value?.toLowerCase() === text.toLowerCase()
                            );
                            if (element) {{
                                element.click();
                                return true;
                            }}
                            return false;
                        }};
                        return findAndClick("{selector}");
                    """
                    )
                    logging.info(f"Attempted JavaScript click for '{selector}'")

                    # Take screenshot after JavaScript click attempt
                    post_js_name, _ = await self.take_verified_screenshot(
                        "post_js_click", f"after JavaScript click attempt on {selector}"
                    )

                    # Check if URL changed after JavaScript click
                    new_url = self.page.url
                    if new_url != current_url:
                        return f"Successfully clicked element using JavaScript strategy. Navigation detected from {current_url} to {new_url}"

                except Exception as js_error:
                    logging.error(f"JavaScript click failed: {str(js_error)}")

            if not element:
                error_msg = f"Failed to find clickable element matching '{selector}'. Available elements: {elements_debug}"
                logging.error(error_msg)
                return f"Error: {error_msg}"

            # Element found, proceed with click
            box = await element.bounding_box()
            center_x = box["x"] + box["width"] / 2
            center_y = box["y"] + box["height"] / 2

            # Scroll element into view
            await element.scroll_into_view_if_needed()

            # Take screenshot with element in view
            pre_click_name, _ = await self.take_verified_screenshot(
                "pre_click", f"with {selector} in view"
            )

            # Highlight element temporarily for screenshot
            await self.page.evaluate(
                f"""(selector) => {{
                const element = document.querySelector("{used_strategy}");
                if (element) {{
                    element.style.outline = '2px solid red';
                    element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            }}""",
                used_strategy,
            )

            # Take screenshot with highlight
            highlight_name, _ = await self.take_verified_screenshot(
                "highlight", f"with {selector} highlighted"
            )

            # Remove highlight
            await self.page.evaluate(
                f"""(selector) => {{
                const element = document.querySelector("{used_strategy}");
                if (element) {{
                    element.style.outline = '';
                }}
            }}""",
                used_strategy,
            )

            # Click the element
            await element.click()

            # Wait for any navigation or network activity
            await self.page.wait_for_load_state("networkidle")

            # Take screenshot after click
            post_click_name, _ = await self.take_verified_screenshot(
                "post_click", f"after clicking {selector}"
            )

            # Get new URL in case of navigation
            new_url = self.page.url

            success_msg = (
                f"Successfully clicked element {selector} using strategy: {used_strategy}\n"
                f"Started on: [{current_url}]\n"
                f"Ended on: [{new_url}]\n"
                f"Element position: x={center_x}, y={center_y}\n"
                f"Screenshot progression:\n"
                f"1. Before scrolling: {self.output_url}/{pre_scroll_name}\n"
                f"2. Element in view: {self.output_url}/{pre_click_name}\n"
                f"3. Element highlighted: {self.output_url}/{highlight_name}\n"
                f"4. After click: {self.output_url}/{post_click_name}"
            )

            logging.info(success_msg)
            return success_msg

        except Exception as e:
            error_msg = f"Error clicking element {selector}: {str(e)}"
            logging.error(error_msg)

            # Take error screenshot
            error_name, _ = await self.take_verified_screenshot(
                "click_error", f"after click error on {selector}"
            )

            return (
                f"Error: {error_msg}\nError Screenshot: {self.output_url}/{error_name}"
            )

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
        Handle execution of a single interaction step with screenshots and logging
        """
        operation = step.find("operation").text
        selector = step.find("selector").text
        description = step.find("description").text
        value = step.find("value").text if step.find("value") is not None else None
        retry_info = step.find("retry")

        # Take screenshot before action
        screenshot_path = os.path.join(
            self.WORKING_DIRECTORY, f"before_{uuid.uuid4()}.png"
        )
        await self.page.screenshot(path=screenshot_path, full_page=True)
        before_screenshot = os.path.basename(screenshot_path)

        # Log step with current URL and before screenshot
        self.ApiClient.new_conversation_message(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{self.activity_id}] {description} on [{current_url}]\n![Before Screenshot]({self.output_url}/{before_screenshot})",
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
                    message=f"[SUBACTIVITY][{self.activity_id}] About to perform: {operation} on [{current_url}]\n![Pre-Operation Screenshot]({self.output_url}/{pre_op_screenshot})",
                    conversation_name=self.conversation_name,
                )

                # Try primary operation
                if operation == "click":
                    await self.click_element_with_playwright(selector)
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
                elif operation == "download":
                    # New operation to handle file downloads
                    download_path = os.path.join(
                        self.WORKING_DIRECTORY, value or f"download_{uuid.uuid4()}"
                    )
                    await self.download_file_with_playwright(selector, download_path)
                    file_name = os.path.basename(download_path)

                    # Log the download completion
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
                    message=f"[SUBACTIVITY][{self.activity_id}] Completed {operation} operation\nStarted on: [{current_url}]\nEnded on: [{new_url}]\n![Post-Operation Screenshot]({self.output_url}/{post_op_screenshot})",
                    conversation_name=self.conversation_name,
                )

                success = True

                # Take screenshot after successful action
                screenshot_path = os.path.join(
                    self.WORKING_DIRECTORY, f"after_{uuid.uuid4()}.png"
                )
                await self.page.screenshot(path=screenshot_path, full_page=True)
                after_screenshot = os.path.basename(screenshot_path)

                # Get updated URL and page content
                current_url = self.page.url
                new_content = await self.get_page_content()

                # Generate page summary
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

                # Log successful operation with after screenshot and updated URL
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Successfully completed: {description} on [{current_url}]\n![After Screenshot]({self.output_url}/{after_screenshot})\n\n{page_summary}",
                    conversation_name=self.conversation_name,
                )

                return "Success"

            except Exception as e:
                last_error = str(e)
                attempt += 1

                # Try alternate selector if available
                if not success and alternate_selector and attempt < max_attempts:
                    try:
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

                        # Log successful alternate operation
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}] Successfully completed with alternate selector: {description} on [{current_url}]\n![After Screenshot]({self.output_url}/{after_screenshot})\n\n{page_summary}",
                            conversation_name=self.conversation_name,
                        )
                        return "Success"

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

    async def parse_interaction_plan(self, plan_text: str) -> ET.Element:
        """
        Parse the interaction plan with enhanced error handling and debugging
        """
        logging.info(f"Raw interaction plan:\n{plan_text}")

        # Try different patterns to extract XML
        patterns = [
            r"<answer>\s*(.*?)\s*</answer>",  # Standard <answer> tags
            r"<interaction>\s*(.*?)\s*</interaction>",  # Direct <interaction> tags
            r"```xml\s*(.*?)\s*```",  # XML in code blocks
            r"```\s*(<.*?>.*?</.*?>)\s*```",  # Any XML in code blocks
        ]

        xml_content = None
        for pattern in patterns:
            match = re.search(pattern, plan_text, re.DOTALL)
            if match:
                xml_content = match.group(1)
                logging.info(f"Found XML using pattern {pattern}:\n{xml_content}")
                break

        if not xml_content:
            # If no XML found, try to construct it from the response
            lines = plan_text.split("\n")
            constructed_xml = []
            in_step = False

            for line in lines:
                if "step" in line.lower() and ":" in line:
                    if in_step:
                        constructed_xml.append("</step>")
                    constructed_xml.append("<step>")
                    in_step = True
                elif "operation" in line.lower() and ":" in line:
                    op = line.split(":", 1)[1].strip().lower()
                    constructed_xml.append(f"<operation>{op}</operation>")
                elif "selector" in line.lower() and ":" in line:
                    sel = line.split(":", 1)[1].strip()
                    constructed_xml.append(f"<selector>{sel}</selector>")
                elif "value" in line.lower() and ":" in line:
                    val = line.split(":", 1)[1].strip()
                    constructed_xml.append(f"<value>{val}</value>")
                elif "description" in line.lower() and ":" in line:
                    desc = line.split(":", 1)[1].strip()
                    constructed_xml.append(f"<description>{desc}</description>")

            if in_step:
                constructed_xml.append("</step>")

            if constructed_xml:
                xml_content = f"<interaction>{''.join(constructed_xml)}</interaction>"
                logging.info(f"Constructed XML from response:\n{xml_content}")

        if not xml_content:
            raise Exception(f"Could not extract valid XML from response:\n{plan_text}")

        # Clean up XML content
        xml_content = xml_content.replace("&", "&amp;")
        xml_content = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", xml_content)

        try:
            root = ET.fromstring(xml_content)
            # Verify we have valid steps
            steps = root.findall(".//step")
            if not steps:
                raise Exception("No valid steps found in XML")
            return root
        except ET.ParseError as e:
            logging.error(f"XML Parse Error: {str(e)}\nContent:\n{xml_content}")
            raise Exception(f"Failed to parse XML: {str(e)}")

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
        try:
            if self.page is None:
                self.ApiClient.new_conversation_message(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{self.activity_id}] Navigating to [{url}]",
                    conversation_name=self.conversation_name,
                )
                await self.navigate_to_url_with_playwright(url=url, headless=True)

            # Get current state
            current_url = self.page.url
            current_content = await self.get_page_content()
            button_analysis = await self.analyze_button_presence()

            # Get interaction plan
            plan_response = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"""Analyze this page and provide EXACT steps to accomplish the task.
Return the steps in XML format as shown in the example.

Current URL: {current_url}
Task to accomplish: {task}

Page Content:
{current_content}

Button Analysis:
{button_analysis}

Example format:
<answer>
<interaction>
<step>
    <operation>click</operation>
    <selector>Register</selector>
    <description>Click the Register button</description>
</step>
<step>
    <operation>fill</operation>
    <selector>#email</selector>
    <value>test@example.com</value>
    <description>Fill in email address</description>
</step>
</interaction>
</answer>

Provide ONLY the XML plan inside <answer> tags. Do not include any other text.""",
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

            # Parse the interaction plan
            root = await self.parse_interaction_plan(plan_response)
            steps = root.findall(".//step")

            results = []
            for step in steps:
                try:
                    operation = step.find("operation").text.strip()
                    selector = step.find("selector").text.strip()
                    description = step.find("description").text.strip()
                    value = (
                        step.find("value").text.strip()
                        if step.find("value") is not None
                        else None
                    )

                    # Log step details
                    logging.info(f"Executing step: {description}")
                    logging.info(f"Operation: {operation}")
                    logging.info(f"Selector: {selector}")
                    logging.info(f"Value: {value}")

                    # Execute step
                    if operation == "click":
                        result = await self.click_element_with_playwright(selector)
                    elif operation == "fill":
                        result = await self.fill_input_with_playwright(selector, value)
                    elif operation == "select":
                        result = await self.select_option_with_playwright(
                            selector, value
                        )
                    else:
                        raise Exception(f"Unknown operation: {operation}")

                    results.append(result)

                    if "Error:" in result:
                        return "\n".join(results)

                    await self.page.wait_for_load_state("networkidle")

                except Exception as step_error:
                    error_msg = f"Error executing step: {str(step_error)}"
                    logging.error(error_msg)
                    results.append(error_msg)
                    return "\n".join(results)

            return "Successfully completed interaction:\n" + "\n".join(results)

        except Exception as e:
            error_msg = f"Error during webpage interaction: {str(e)}"
            logging.error(error_msg)
            return error_msg

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
        """Get enhanced page content with better button/link detection"""
        try:
            if self.page is None:
                return "Error: No page loaded."

            # First get standard page content
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Get button analysis
            button_analysis = await self.analyze_button_presence()

            # Combine all the content
            content = ["=== PAGE CONTENT ANALYSIS ===\n"]

            # Title
            if soup.title and soup.title.string:
                content.append(f"Title: {soup.title.string.strip()}\n")

            # Current URL
            content.append(f"URL: {self.page.url}\n")

            # Clickable Elements Analysis
            content.append("=== CLICKABLE ELEMENTS ===\n")
            content.append(button_analysis)
            content.append("\n")

            # Find all links with non-empty text
            content.append("=== LINKS ===\n")
            links = []
            for link in soup.find_all("a", href=True):
                text = self.get_text_safely(link)
                if text:
                    href = link["href"]
                    classes = " ".join(link.get("class", []))
                    selectors = []

                    if link.get("id"):
                        selectors.append(f"#{link['id']}")
                    if classes:
                        selectors.append(f"a.{classes.replace(' ', '.')}")
                    selectors.append(f"a[href='{href}']")
                    if text:
                        selectors.append(f"a:text('{text}')")

                    links.append(f"Link: {text}")
                    links.append(f"  Href: {href}")
                    links.append("  Selectors:")
                    for idx, selector in enumerate(selectors, 1):
                        links.append(f"    {idx}. {selector}")
                    links.append("")

            content.extend(links)

            # Forms Analysis
            content.append("=== FORMS AND INPUTS ===\n")
            forms = []
            # Look for both explicit forms and implicit form groups
            form_elements = soup.find_all(["form", 'div[role="form"]', "div.form"])

            for form in form_elements:
                form_id = form.get("id", "")
                form_class = " ".join(form.get("class", []))
                form_info = [
                    f"Form{f' ID: {form_id}' if form_id else ''}{f' Class: {form_class}' if form_class else ''}"
                ]

                # Get all inputs, including those styled as buttons
                inputs = form.find_all(
                    [
                        "input",
                        "button",
                        "textarea",
                        "select",
                        'div[role="button"]',
                        'span[role="button"]',
                    ]
                )

                for input_elem in inputs:
                    input_type = input_elem.get("type", "text")
                    input_id = input_elem.get("id", "")
                    input_name = input_elem.get("name", "")
                    input_class = " ".join(input_elem.get("class", []))
                    input_value = input_elem.get("value", "")
                    placeholder = input_elem.get("placeholder", "")

                    selectors = []
                    if input_id:
                        selectors.append(f"#{input_id}")
                    if input_name:
                        selectors.append(f"[name='{input_name}']")
                    if input_class:
                        selectors.append(f".{input_class.replace(' ', '.')}")
                    if placeholder:
                        selectors.append(f"[placeholder='{placeholder}']")

                    input_info = [
                        f"  Input:",
                        f"    Type: {input_type}",
                    ]

                    if input_id:
                        input_info.append(f"    ID: {input_id}")
                    if input_name:
                        input_info.append(f"    Name: {input_name}")
                    if placeholder:
                        input_info.append(f"    Placeholder: {placeholder}")
                    if input_value:
                        input_info.append(f"    Value: {input_value}")

                    input_info.append("    Selectors:")
                    for idx, selector in enumerate(selectors, 1):
                        input_info.append(f"      {idx}. {selector}")

                    forms.extend(input_info)
                forms.append("")  # Add spacing between forms

            content.extend(forms)

            # Interactive Elements (not already covered)
            content.append("=== OTHER INTERACTIVE ELEMENTS ===\n")
            other_elements = self._get_other_interactive_elements(soup)
            content.extend(other_elements)

            # Look for error messages or notifications
            content.append("\n=== NOTIFICATIONS AND MESSAGES ===\n")
            error_classes = ["error", "alert", "notification", "message", "toast"]
            messages = []
            for class_name in error_classes:
                for elem in soup.find_all(
                    class_=lambda x: x and class_name in x.lower()
                ):
                    text = self.get_text_safely(elem)
                    if text:
                        messages.append(f"{class_name.title()}: {text}")
            if messages:
                content.extend(messages)
            else:
                content.append("No notifications or messages found.")

            return "\n".join(content)

        except Exception as e:
            error_msg = f"Error analyzing page content: {str(e)}"
            logging.error(error_msg)
            return error_msg

    def _analyze_input_field(self, input_field, form_id=None) -> str:
        """
        Analyze a single input field and generate detailed information about it
        """
        try:
            # Collect all relevant attributes
            field_type = input_field.get("type", "text")
            field_name = input_field.get("name", "")
            field_id = input_field.get("id", "")
            placeholder = input_field.get("placeholder", "")
            field_class = " ".join(input_field.get("class", []))
            aria_label = input_field.get("aria-label", "")
            value = input_field.get("value", "")
            required = input_field.get("required") is not None
            readonly = input_field.get("readonly") is not None
            disabled = input_field.get("disabled") is not None

            # Build selectors list from most to least specific
            selectors = []

            # ID is most specific
            if field_id:
                selectors.append(f"#{field_id}")

            # Name with form context
            if field_name:
                if form_id:
                    selectors.append(f"#{form_id} [name='{field_name}']")
                selectors.append(f"[name='{field_name}']")

            # Placeholder text
            if placeholder:
                if form_id:
                    selectors.append(f"#{form_id} [placeholder='{placeholder}']")
                selectors.append(f"[placeholder='{placeholder}']")

            # Aria label
            if aria_label:
                if form_id:
                    selectors.append(f"#{form_id} [aria-label='{aria_label}']")
                selectors.append(f"[aria-label='{aria_label}']")

            # Class-based (least specific)
            if field_class:
                if form_id:
                    selectors.append(f"#{form_id} .{field_class.replace(' ', '.')}")
                selectors.append(f".{field_class.replace(' ', '.')}")

            if not selectors:
                return None

            # Build comprehensive description
            input_desc = [f"\nInput Field:"]
            input_desc.append(f"- Type: {field_type}")

            if field_id:
                input_desc.append(f"- ID: {field_id}")
            if field_name:
                input_desc.append(f"- Name: {field_name}")
            if placeholder:
                input_desc.append(f"- Placeholder: {placeholder}")
            if aria_label:
                input_desc.append(f"- Aria Label: {aria_label}")
            if field_class:
                input_desc.append(f"- Classes: {field_class}")
            if value:
                input_desc.append(f"- Default Value: {value}")
            if required:
                input_desc.append("- Required: Yes")
            if readonly:
                input_desc.append("- Readonly: Yes")
            if disabled:
                input_desc.append("- Disabled: Yes")

            input_desc.append("\nSelectors (in order of preference):")
            for idx, selector in enumerate(selectors, 1):
                input_desc.append(f"  {idx}. {selector}")

            return "\n".join(input_desc)

        except Exception as e:
            logging.error(f"Error analyzing input field: {str(e)}")
            return None

    async def fill_input_with_playwright(self, selector: str, text: str) -> str:
        """Fill an input field with enhanced error handling and screenshots"""
        try:
            if self.page is None:
                return "Error: No page loaded. Please navigate to a URL first."

            current_url = self.page.url
            logging.info(f"Attempting to fill input {selector} on {current_url}")

            # Take before screenshot
            pre_screenshot_name, _ = await self.take_verified_screenshot(
                "pre_fill", f"before filling {selector}"
            )

            # Wait for element with timeout
            try:
                element = await self.page.wait_for_selector(
                    selector, state="visible", timeout=5000
                )
                if not element:
                    raise Exception(f"Element not found: {selector}")
            except Exception as wait_error:
                error_screenshot_name, _ = await self.take_verified_screenshot(
                    "error_fill", f"after element not found: {selector}"
                )

                page_content = await self.get_page_content()

                error_msg = (
                    f"Failed to find input element: {selector}\n"
                    f"Current URL: {current_url}\n"
                    f"Pre-attempt Screenshot: {self.output_url}/{pre_screenshot_name}\n"
                    f"Error Screenshot: {self.output_url}/{error_screenshot_name}\n"
                    f"Available form elements:\n{page_content}"
                )
                logging.error(error_msg)
                return f"Error: {error_msg}"

            # Try to fill the input
            try:
                await element.evaluate('el => el.value = ""')
                await element.fill(text)
                actual_value = await element.input_value()

                if actual_value != text:
                    raise Exception(
                        f"Value mismatch - Expected: {text}, Got: {actual_value}"
                    )

                # Take after screenshot
                post_screenshot_name, _ = await self.take_verified_screenshot(
                    "post_fill", f"after successfully filling {selector}"
                )

                success_msg = (
                    f"Successfully filled input {selector} with text '{text}'\n"
                    f"Current URL: {current_url}\n"
                    f"Before Screenshot: {self.output_url}/{pre_screenshot_name}\n"
                    f"After Screenshot: {self.output_url}/{post_screenshot_name}"
                )
                logging.info(success_msg)
                return success_msg

            except Exception as fill_error:
                error_screenshot_name, _ = await self.take_verified_screenshot(
                    "error_fill", f"after fill failure: {selector}"
                )

                error_msg = (
                    f"Failed to fill input: {str(fill_error)}\n"
                    f"Current URL: {current_url}\n"
                    f"Pre-attempt Screenshot: {self.output_url}/{pre_screenshot_name}\n"
                    f"Error Screenshot: {self.output_url}/{error_screenshot_name}"
                )
                logging.error(error_msg)
                return f"Error: {error_msg}"

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logging.error(error_msg)
            return f"Error: {error_msg}"

    def _get_other_interactive_elements(self, soup) -> list:
        """
        Find other interactive elements on the page with enhanced detection
        """
        interactive_elements = []

        # Common interactive classes and attributes
        interactive_classes = [
            "button",
            "btn",
            "clickable",
            "interactive",
            "dropdown",
            "register",
            "signup",
            "sign-up",
            "login",
            "submit",
            "cta",
            "call-to-action",
        ]
        interactive_roles = ["button", "link", "menuitem", "tab", "checkbox", "radio"]

        # Find elements by class, role, type, or other common button indicators
        selectors = [
            # By role
            {"role": interactive_roles},
            # By type
            {"type": ["button", "submit"]},
            # By class containing common button terms
            {
                "class": lambda x: x
                and any(cls in str(x).lower() for cls in interactive_classes)
            },
            # Any element with onclick attribute
            {"onclick": True},
            # Any element with event listeners (data-* attributes)
            {"data-action": True},
            # Elements with specific tags that might be clickable
            {"tag": ["button", "a", "div", "span"]},
        ]

        for selector in selectors:
            if "tag" in selector:
                elements = soup.find_all(selector["tag"])
            else:
                elements = soup.find_all(attrs=selector)

            for element in elements:
                try:
                    # Skip if already processed
                    if element.get("processed"):
                        continue

                    # Get text content
                    text = self.get_text_safely(element)
                    href = element.get("href", "")
                    onclick = element.get("onclick", "")
                    role = element.get("role", "")
                    classes = " ".join(element.get("class", []))

                    # Build selector based on available attributes
                    selectors = []

                    # ID is most specific
                    if element.get("id"):
                        selectors.append(f"#{element.get('id')}")

                    # Role is next best
                    if role:
                        selectors.append(f"[role='{role}']")

                    # Class-based selectors
                    if classes:
                        selectors.append(f".{classes.replace(' ', '.')}")

                    # Type
                    if element.get("type"):
                        selectors.append(f"[type='{element.get('type')}']")

                    # Text content for buttons/links
                    if text:
                        selectors.append(f"{element.name}:has-text('{text}')")

                    # Only add if we have valid identifiers
                    if text or href or onclick or role or classes:
                        element_info = [f"\nInteractive Element:"]
                        element_info.append(f"- Tag: {element.name}")
                        if text:
                            element_info.append(f"- Text: {text}")
                        if role:
                            element_info.append(f"- Role: {role}")
                        if classes:
                            element_info.append(f"- Classes: {classes}")
                        if href:
                            element_info.append(f"- Link: {href}")
                        if onclick:
                            element_info.append(f"- Has Click Handler: Yes")

                        element_info.append("\nPossible Selectors:")
                        for idx, selector in enumerate(selectors, 1):
                            element_info.append(f"  {idx}. {selector}")

                        interactive_elements.extend(element_info)
                        element["processed"] = True

                except Exception as e:
                    logging.error(f"Error processing interactive element: {str(e)}")
                    continue

        return interactive_elements

    async def analyze_button_presence(self) -> str:
        """
        Specifically analyze the page for buttons and their clickability
        """
        try:
            # Get all buttons using multiple methods
            buttons = await self.page.evaluate(
                """() => {
                const getClickableElements = () => {
                    const elements = [];
                    // Direct button elements
                    document.querySelectorAll('button').forEach(el => elements.push({
                        tag: 'button',
                        text: el.innerText,
                        isVisible: el.offsetWidth > 0 && el.offsetHeight > 0,
                        selector: el.id ? `#${el.id}` : (el.className ? `.${el.className.split(' ').join('.')}` : null)
                    }));
                    
                    // Links that look like buttons
                    document.querySelectorAll('a').forEach(el => elements.push({
                        tag: 'a',
                        text: el.innerText,
                        href: el.href,
                        isVisible: el.offsetWidth > 0 && el.offsetHeight > 0,
                        selector: el.id ? `#${el.id}` : (el.className ? `.${el.className.split(' ').join('.')}` : null)
                    }));
                    
                    // Div/span buttons
                    document.querySelectorAll('div[role="button"], span[role="button"], div.button, div.btn').forEach(el => 
                        elements.push({
                            tag: el.tagName.toLowerCase(),
                            text: el.innerText,
                            isVisible: el.offsetWidth > 0 && el.offsetHeight > 0,
                            selector: el.id ? `#${el.id}` : (el.className ? `.${el.className.split(' ').join('.')}` : null)
                        })
                    );
                    
                    // Additional button detection
                    document.querySelectorAll('*').forEach(el => {
                        if (el.onclick || 
                            el.getAttribute('role') === 'button' || 
                            el.className.toLowerCase().includes('button') ||
                            el.className.toLowerCase().includes('btn') ||
                            el.innerText.toLowerCase().includes('register') ||
                            el.innerText.toLowerCase().includes('sign up')
                        ) {
                            elements.push({
                                tag: el.tagName.toLowerCase(),
                                text: el.innerText,
                                isVisible: el.offsetWidth > 0 && el.offsetHeight > 0,
                                selector: el.id ? `#${el.id}` : (el.className ? `.${el.className.split(' ').join('.')}` : null)
                            });
                        }
                    });
                    
                    return elements;
                };
                return getClickableElements();
            }"""
            )

            if buttons:
                result = ["Found clickable elements:"]
                for btn in buttons:
                    if btn.get("isVisible", False):
                        result.append(
                            f"\n- {btn.get('text', 'Unnamed Button')} ({btn.get('tag', 'element')})"
                        )
                        if btn.get("selector"):
                            result.append(f"  Selector: {btn['selector']}")
                        if btn.get("href"):
                            result.append(f"  Link: {btn['href']}")
                return "\n".join(result)
            else:
                return "No clickable elements found on page"

        except Exception as e:
            logging.error(f"Error analyzing buttons: {str(e)}")
            return f"Error analyzing buttons: {str(e)}"

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
