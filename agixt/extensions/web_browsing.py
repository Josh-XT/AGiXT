from typing import List, Union
import logging
import subprocess
import uuid
import sys
import os
import re
import io
import hashlib
import time
import importlib
import asyncio

logger = logging.getLogger(__name__)


def _import_optional(module_path: str, package_name: str = None):
    """Import an optional dependency, attempting installation if needed.

    Returns the imported module (or attribute for dotted names) on success, or None on failure.
    This helper prevents import failures from breaking extension registration during startup.
    """

    target_attr = None
    module_name = module_path

    if "." in module_path:
        module_name, target_attr = module_path.rsplit(".", 1)

    try:
        module = importlib.import_module(module_name)
    except ImportError as initial_error:
        if package_name is None:
            logger.warning(
                "Optional dependency '%s' is unavailable: %s",
                module_path,
                initial_error,
            )
            return None
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package_name]
            )
            module = importlib.import_module(module_name)
        except Exception as install_error:
            logger.warning(
                "Failed to install optional dependency '%s': %s",
                package_name,
                install_error,
            )
            return None
    except Exception as unexpected_error:
        logger.warning(
            "Unexpected error importing optional dependency '%s': %s",
            module_path,
            unexpected_error,
        )
        return None

    if target_attr:
        return getattr(module, target_attr, None)
    return module


BeautifulSoup = _import_optional("bs4.BeautifulSoup", "beautifulsoup4==4.12.2")
_playwright_module = _import_optional("playwright.async_api", "playwright")
if _playwright_module:
    async_playwright = getattr(_playwright_module, "async_playwright", None)
    PlaywrightTimeoutError = getattr(_playwright_module, "TimeoutError", TimeoutError)
else:
    async_playwright = None

    class PlaywrightTimeoutError(Exception):
        pass


pyotp = _import_optional("pyotp", "pyotp")
cv2 = _import_optional("cv2", "opencv-python")
np = _import_optional("numpy", "numpy")
_pyzbar = _import_optional("pyzbar.pyzbar", "pyzbar")
decode = getattr(_pyzbar, "decode", None) if _pyzbar else None
pytesseract = _import_optional("pytesseract", "pytesseract")
Image = _import_optional("PIL.Image", "Pillow")

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

    CATEGORY = "Core Abilities"
    friendly_name = "Web Browsing"

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
            "Research on arXiv": self.search_arxiv,
        }
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.popup = None
        self._cleanup_attempted = False  # Track cleanup attempts

    def __del__(self):
        """Destructor to ensure cleanup on garbage collection"""
        try:
            if (
                not self._cleanup_attempted
                and hasattr(self, "playwright")
                and self.playwright
            ):
                # Create new event loop if necessary for cleanup
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, schedule cleanup for later
                        loop.create_task(self._sync_cleanup())
                    else:
                        loop.run_until_complete(self._sync_cleanup())
                except RuntimeError:
                    # No event loop available, create one
                    asyncio.run(self._sync_cleanup())
        except Exception as e:
            # Don't raise exceptions in destructor
            try:
                logging.error(f"Error in web_browsing destructor: {e}")
            except:
                pass  # Logging may not be available during shutdown

    async def _sync_cleanup(self):
        """Internal cleanup method for destructor"""
        try:
            await self.ensure_cleanup()
        except Exception:
            pass  # Ignore exceptions during destructor cleanup

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
        websearch_llm_timeout = getattr(self, "websearch_timeout_seconds", 60)
        return await self._call_prompt_agent(
            timeout=websearch_llm_timeout,
            agent_name=self.agent_name,
            prompt_name="User Input",
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
        try:
            if async_playwright is None:
                raise RuntimeError(
                    "Playwright is not available. Please install the 'playwright' package to use browser automation."
                )
            if self.page is None:
                logging.info(
                    "Initializing Playwright browser with stealth configuration..."
                )
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    headless=headless,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=VizDisplayCompositor",
                    ],  # Improve stability and avoid detection
                )

                # Comprehensive stealth configuration to appear as regular user
                self.context = await self.browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    ignore_https_errors=True,  # Handle SSL issues more gracefully
                    locale="en-US",
                    timezone_id="America/New_York",
                    permissions=["geolocation", "notifications"],
                    geolocation={"latitude": 40.7128, "longitude": -74.0060},  # NYC
                    color_scheme="light",
                    device_scale_factor=1,
                    has_touch=False,
                    is_mobile=False,
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "DNT": "1",  # Do Not Track
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Cache-Control": "max-age=0",
                    },
                )

                self.page = await self.context.new_page()

                # Inject scripts to mask automation indicators
                await self.page.add_init_script(
                    """
                    // Override the navigator.webdriver property
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => false,
                    });
                    
                    // Mock plugins to appear like a real browser
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [
                            {
                                0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: Plugin},
                                description: "Portable Document Format",
                                filename: "internal-pdf-viewer",
                                length: 1,
                                name: "Chrome PDF Plugin"
                            },
                            {
                                0: {type: "application/pdf", suffixes: "pdf", description: "", enabledPlugin: Plugin},
                                description: "",
                                filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                                length: 1,
                                name: "Chrome PDF Viewer"
                            },
                            {
                                0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable", enabledPlugin: Plugin},
                                1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable", enabledPlugin: Plugin},
                                description: "",
                                filename: "internal-nacl-plugin",
                                length: 2,
                                name: "Native Client"
                            }
                        ],
                    });
                    
                    // Mock languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en'],
                    });
                    
                    // Add chrome object
                    window.chrome = {
                        runtime: {},
                        loadTimes: function() {},
                        csi: function() {},
                        app: {}
                    };
                    
                    // Mock permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                    
                    // Add realistic screen properties
                    Object.defineProperty(screen, 'availWidth', {get: () => 1920});
                    Object.defineProperty(screen, 'availHeight', {get: () => 1040});
                    Object.defineProperty(screen, 'width', {get: () => 1920});
                    Object.defineProperty(screen, 'height', {get: () => 1080});
                    Object.defineProperty(screen, 'colorDepth', {get: () => 24});
                    Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
                """
                )

                # Set reasonable timeouts to prevent hanging
                self.page.set_default_timeout(
                    30000
                )  # 30 seconds for element interactions
                self.page.set_default_navigation_timeout(
                    120000
                )  # 2 minutes for navigation

                logging.info("Playwright browser initialized.")
            elif self.page.is_closed():
                logging.info("Page was closed, creating a new one.")
                self.page = await self.context.new_page()
                self.page.set_default_timeout(30000)
                self.page.set_default_navigation_timeout(120000)
        except Exception as e:
            logging.error(f"Error initializing browser: {e}")
            await self.ensure_cleanup()
            raise

    async def _call_prompt_agent(self, timeout: int = None, **kwargs):
        """Call ApiClient.prompt_agent in a background thread (with optional timeout for stuck requests)."""
        if not self.ApiClient:
            raise RuntimeError("ApiClient is not configured.")

        import concurrent.futures

        # Use ThreadPoolExecutor for better timeout control than asyncio.to_thread
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        start_time = time.time()

        try:
            logging.debug(f"Starting prompt_agent call with timeout={timeout}s...")

            # Submit the blocking call to the executor
            future = executor.submit(self.ApiClient.prompt_agent, **kwargs)

            # Wait for completion with timeout
            if timeout:
                try:
                    # Use run_in_executor to await the future with timeout
                    response = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: future.result(timeout=timeout)
                        ),
                        timeout=timeout
                        + 1,  # Give slightly more time than the future's timeout
                    )
                except (
                    concurrent.futures.TimeoutError,
                    asyncio.TimeoutError,
                ) as timeout_error:
                    elapsed = time.time() - start_time
                    error_msg = f"LLM call timed out after {elapsed:.1f}s (timeout was {timeout}s)"
                    logging.error(error_msg)
                    logging.warning(
                        "The background thread is still running and cannot be killed. "
                        "If ezlocalai is overloaded, consider restarting it or increasing MAX_CONCURRENT_REQUESTS."
                    )
                    # Cancel the future (won't stop the thread but marks it as cancelled)
                    future.cancel()
                    raise TimeoutError(error_msg)
            else:
                response = await asyncio.get_event_loop().run_in_executor(
                    None, future.result
                )

            elapsed = time.time() - start_time
            logging.debug(
                f"prompt_agent call completed in {elapsed:.1f}s, response length: {len(str(response)) if response else 0}"
            )

        except TimeoutError:
            # Re-raise timeout errors
            raise
        except Exception as e:
            elapsed = time.time() - start_time
            logging.error(
                f"Error in _call_prompt_agent after {elapsed:.1f}s: {e}", exc_info=True
            )
            raise
        finally:
            # Shutdown executor (won't kill threads but prevents new submissions)
            executor.shutdown(wait=False)

        logging.info(f"Response: {response}")
        return response

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

    async def get_clickable_links(self) -> List[str]:
        """
        Extract visible, clickable link texts from the page.
        This is specifically designed to capture search result links and other
        clickable content that might not be traditional form elements.

        Returns:
            List[str]: List of clickable link texts found on the page
        """
        if self.page is None or self.page.is_closed():
            return []

        try:
            # Extract all visible clickable elements with meaningful text
            link_texts = await self.page.evaluate(
                """() => {
                    const elements = [];
                    
                    // Get all <a> tags with visible text
                    const links = document.querySelectorAll('a');
                    links.forEach(link => {
                        const rect = link.getBoundingClientRect();
                        const isVisible = (rect.width > 0 || rect.height > 0) && 
                                        window.getComputedStyle(link).visibility !== 'hidden' &&
                                        window.getComputedStyle(link).display !== 'none';
                        
                        if (isVisible) {
                            // Get text content, stripping extra whitespace
                            const text = link.innerText || link.textContent || '';
                            const cleanText = text.trim().replace(/\\s+/g, ' ');
                            
                            // Only include links with meaningful text (3+ chars, not just icons/emojis)
                            if (cleanText.length >= 3 && cleanText.length <= 200) {
                                elements.push(cleanText);
                            }
                        }
                    });
                    
                    // Also check for clickable divs/spans that might be styled as links
                    const clickables = document.querySelectorAll('[role="link"], [onclick], .result-title, .search-result-title');
                    clickables.forEach(elem => {
                        if (elem.tagName.toLowerCase() !== 'a') {  // Skip if already processed as <a>
                            const rect = elem.getBoundingClientRect();
                            const isVisible = (rect.width > 0 || rect.height > 0) && 
                                            window.getComputedStyle(elem).visibility !== 'hidden' &&
                                            window.getComputedStyle(elem).display !== 'none';
                            
                            if (isVisible) {
                                const text = elem.innerText || elem.textContent || '';
                                const cleanText = text.trim().replace(/\\s+/g, ' ');
                                
                                if (cleanText.length >= 3 && cleanText.length <= 200) {
                                    elements.push(cleanText);
                                }
                            }
                        }
                    });
                    
                    // Return unique texts
                    return [...new Set(elements)];
                }"""
            )

            return link_texts

        except Exception as e:
            logging.warning(f"Error extracting clickable links: {e}")
            return []

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
        self, url: str, headless: bool = True, timeout: int = 30000
    ) -> str:
        """
        Navigates the browser to the specified URL using Playwright. Initializes the browser
        if it's not already running.

        Args:
            url (str): The URL to navigate to. Should include the scheme (http/https).
            headless (bool): Whether to run the browser in headless mode (no visible UI).
                             Defaults to True.
            timeout (int): Navigation timeout in milliseconds. Defaults to 30000 (30 seconds).

        Returns:
            str: A confirmation message indicating success or an error message.
        """
        try:
            if not url.startswith("http"):
                url = "https://" + url
                logging.info(f"Assuming HTTPS for URL: {url}")

            await self._ensure_browser_page(headless=headless)

            logging.info(f"Navigating to {url}...")

            # Try different wait strategies in order of preference
            wait_strategies = ["domcontentloaded", "load", "networkidle"]
            last_error = None

            for wait_strategy in wait_strategies:
                try:
                    logging.info(
                        f"Attempting navigation with wait_until='{wait_strategy}'"
                    )
                    await self.page.goto(url, wait_until=wait_strategy, timeout=timeout)
                    current_url = self.page.url
                    logging.info(
                        f"Successfully navigated to {current_url} using {wait_strategy}"
                    )

                    # Additional validation - ensure we actually got to a page
                    if current_url and current_url != "about:blank":
                        return f"Successfully navigated to {current_url}"
                    else:
                        logging.warning(
                            f"Navigation resulted in blank page, trying next strategy..."
                        )
                        continue

                except PlaywrightTimeoutError as e:
                    last_error = e
                    logging.warning(
                        f"Navigation with {wait_strategy} timed out, trying next strategy..."
                    )
                    continue
                except Exception as e:
                    # Check for common network errors that we might want to retry
                    error_str = str(e).lower()
                    if any(
                        net_error in error_str
                        for net_error in [
                            "net::err_name_not_resolved",
                            "net::err_connection_refused",
                            "net::err_connection_timed_out",
                        ]
                    ):
                        logging.warning(
                            f"Network error with {wait_strategy}: {e}, trying next strategy..."
                        )
                        last_error = e
                        continue
                    else:
                        # For other errors, don't try other strategies
                        raise e

            # If all strategies failed, return a more detailed error
            timeout_seconds = timeout // 1000
            if last_error:
                error_detail = str(last_error)
                if "net::err_name_not_resolved" in error_detail.lower():
                    error_msg = f"Error navigating to {url}: Domain name could not be resolved. Please check the URL."
                elif "net::err_connection_refused" in error_detail.lower():
                    error_msg = f"Error navigating to {url}: Connection refused. The server may be down or unreachable."
                elif "net::err_connection_timed_out" in error_detail.lower():
                    error_msg = f"Error navigating to {url}: Connection timed out. The server is taking too long to respond."
                else:
                    error_msg = f"Error navigating to {url}: Navigation timed out after {timeout_seconds} seconds using all wait strategies. Last error: {error_detail}"
            else:
                error_msg = f"Error navigating to {url}: Navigation timed out after {timeout_seconds} seconds using all wait strategies."

            logging.error(error_msg)
            return error_msg

        except Exception as e:
            logging.error(f"Error navigating to {url}: {str(e)}", exc_info=True)
            return f"Error navigating to {url}: {str(e)}"

    async def click_element_with_playwright(
        self, selector: str, timeout: int = 30000
    ) -> str:
        """
        Clicks an element on the page specified by a CSS selector using Playwright.
        Waits for the element to be visible and enabled before clicking.
        Uses increased timeout and scroll-into-view to handle dynamic content.

        Args:
            selector (str): The CSS selector of the element to click.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 30000 (30s).

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

            # Wait for element to be visible with increased timeout
            await element.wait_for(state="visible", timeout=timeout)

            # Scroll element into view to ensure it's clickable
            try:
                await element.scroll_into_view_if_needed(timeout=5000)
            except Exception as scroll_error:
                logging.warning(f"Could not scroll element into view: {scroll_error}")

            # Check if element is enabled using is_enabled() method
            is_enabled = await element.is_enabled()
            if not is_enabled:
                return f"Error: Element '{selector}' is not enabled/clickable."

            # Click with force option as fallback if normal click fails
            try:
                await element.click(timeout=timeout)
            except PlaywrightTimeoutError:
                logging.warning(f"Normal click timed out, trying force click...")
                await element.click(force=True, timeout=timeout)
            # Optional: Wait for navigation or network idle if click causes page change
            try:
                # Try shorter networkidle timeout first
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeoutError:
                try:
                    # Fall back to load state
                    await self.page.wait_for_load_state("load", timeout=10000)
                except PlaywrightTimeoutError:
                    logging.warning(
                        f"Page load states did not stabilize after clicking {selector}, proceeding anyway."
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
        self, selector: str, text: str, timeout: int = 5000
    ) -> str:
        """
        Fills an input field specified by a CSS selector with the provided text using Playwright.
        Waits for the input field to be visible and editable. Includes retries with common variations
        if the initial selector fails.

        Args:
            selector (str): The CSS selector of the input field.
            text (str): The text to fill into the input field.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 5000 (5s).


        Returns:
            str: Confirmation message or error message detailing failures.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed. Please navigate to a URL first."

        logging.info(f"Attempting to fill input '{selector}' with text.")

        try:
            element = self.page.locator(selector).first
            await element.wait_for(state="visible", timeout=timeout)
            # Check if the element is enabled (can accept input)
            is_enabled = await element.is_enabled()
            if not is_enabled:
                return f"Error: Input field '{selector}' is not enabled/interactive."

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
        self, selector: str, value: str, timeout: int = 5000
    ) -> str:
        """
        Selects an option from a <select> dropdown menu specified by a selector using Playwright.
        Can select by option value or visible text (label).

        Args:
            selector (str): The CSS selector of the <select> element.
            value (str): The value or the visible text (label) of the option to select.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 5000 (5s).

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
        self, selector: str, timeout: int = 5000
    ) -> str:
        """
        Checks a checkbox specified by a selector using Playwright.
        Waits for the checkbox to be visible and enabled.

        Args:
            selector (str): The CSS selector of the checkbox input element.
            timeout (int): Maximum time in milliseconds to wait for the element. Defaults to 5000 (5s).

        Returns:
            str: Confirmation message or error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed. Please navigate to a URL first."
        try:
            logging.info(f"Attempting to check checkbox '{selector}'")
            element = self.page.locator(selector).first
            await element.wait_for(state="visible", timeout=timeout)
            # Check if element is enabled using is_enabled() method
            is_enabled = await element.is_enabled()
            if not is_enabled:
                return f"Error: Checkbox '{selector}' is not enabled."
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

        missing_dependencies = []
        if np is None:
            missing_dependencies.append("numpy")
        if cv2 is None:
            missing_dependencies.append("opencv-python (cv2)")
        if decode is None:
            missing_dependencies.append("pyzbar")
        if pyotp is None:
            missing_dependencies.append("pyotp")

        if missing_dependencies:
            return (
                "Error: Missing dependencies for MFA handling: "
                + ", ".join(missing_dependencies)
                + "."
            )

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
        self, trigger_selector: str, save_path: str = None, timeout: int = 15000
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
                           Defaults to 15000 (15s).

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
            await self.page.go_back(wait_until="networkidle", timeout=10000)
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
            await self.page.go_forward(wait_until="networkidle", timeout=10000)
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
        self, selector: str, state: str = "visible", timeout: int = 10000
    ) -> str:
        """
        Waits for an element specified by a selector to appear on the page and reach a specific state.

        Args:
            selector (str): The CSS selector of the element to wait for.
            state (str): The state to wait for ('visible', 'hidden', 'attached', 'detached').
                         Defaults to 'visible'.
            timeout (int): Maximum time to wait in milliseconds. Defaults to 10000 (10s).

        Returns:
            str: Confirmation message if the element appears in the specified state, or an error message.
        """
        if self.page is None or self.page.is_closed():
            return "Error: No page loaded or page is closed."

        # Validate state parameter
        valid_states = ["visible", "hidden", "attached", "detached"]
        if state not in valid_states:
            return f"Error: Invalid state '{state}'. Valid states are: {', '.join(valid_states)}"

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
                               (e.g., re.compile(r"(\\.png$|\\.jpg$)")) to match request URLs.
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
        if pytesseract is None or Image is None:
            return (
                "Error: Missing dependencies for OCR (requires Pillow and pytesseract)."
            )

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
        except Exception as e:
            tesseract_error = (
                getattr(pytesseract, "TesseractNotFoundError", None)
                if pytesseract
                else None
            )
            if isinstance(e, ImportError):
                logging.error(
                    "ImportError during OCR: Pillow or pytesseract might be missing."
                )
                return "Error: Missing dependency for OCR (Pillow or pytesseract). Please install them."
            if tesseract_error and isinstance(e, tesseract_error):
                logging.error(
                    "Tesseract OCR engine not found. Please install Tesseract and ensure it's in the system PATH."
                )
                return "Error: Tesseract OCR not found. Install Tesseract and add it to PATH."
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
                log_msg += f"\n![Screenshot]({before_screenshot_url})"
                # Add screenshot link to the previous log message (optional, depends on API capabilities)
                # self.ApiClient.append_to_last_message(f"\n![Before Screenshot]({before_screenshot_url})")
        except Exception as ss_error:
            logging.error(f"Failed to take 'before' screenshot: {ss_error}")

        if self.ApiClient:
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=log_msg,
                conversation_name=self.conversation_name,
            )
        # Initialize retry parameters (Defaults + overrides from XML)
        max_attempts = 3  # Default to 1 attempt unless retry specified
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

            # Check if we need a selector for this operation
            # Click can work with just text/value, some operations don't need selectors
            needs_selector_operations = [
                "fill",
                "select",
                "check",
                "upload",
                "download",
                "assert",
                "extract_table",
            ]
            can_work_without_selector = operation in [
                "click",
                "wait",
                "done",
                "evaluate",
                "screenshot",
                "get_fields",
                "get_content",
                "press",
                "scrape_to_memory",
                "respond",
            ]

            if not current_selector and operation in needs_selector_operations:
                last_error = f"No selector provided for operation '{operation}' which requires a selector (Attempt {attempt})"
                logging.error(last_error)
                break  # No point retrying without a selector for operations that need one
            elif not current_selector and not can_work_without_selector and not value:
                # For other operations, we need either a selector OR a value (for text-based operations)
                last_error = f"No selector or value provided for operation '{operation}' (Attempt {attempt})"
                logging.error(last_error)
                break

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
                            logging.info(
                                f"Exact match for '{value}': found {count} elements"
                            )

                            if count == 1:  # Only click if unique exact match
                                await locator.click(timeout=30000)
                                text_click_success = True
                                op_result = f"Clicked element by exact text '{value}'"
                            elif count == 0:
                                # Try partial match if exact fails
                                locator = self.page.get_by_text(value, exact=False)
                                count = await locator.count()
                                logging.info(
                                    f"Partial match for '{value}': found {count} elements"
                                )

                                if count == 1:  # Only click if unique partial match
                                    await locator.click(timeout=30000)
                                    text_click_success = True
                                    op_result = (
                                        f"Clicked element by partial text '{value}'"
                                    )
                                elif count > 1:
                                    logging.warning(
                                        f"Multiple elements contain text '{value}'. Skipping text click."
                                    )
                                elif count == 0:
                                    # Try case-insensitive search as a last resort
                                    logging.info(
                                        f"No partial matches found for '{value}', trying case-insensitive and flexible search..."
                                    )
                                    try:
                                        # Get all clickable elements and their text
                                        clickable_elements = await self.page.query_selector_all(
                                            "a, button, [role='button'], input[type='submit'], input[type='button'], .btn, [onclick]"
                                        )
                                        found_texts = []
                                        search_variations = [
                                            value.lower(),
                                            value.lower().replace(" ", ""),
                                            value.lower().replace(" ", "-"),
                                            value.lower().replace(" ", "_"),
                                        ]

                                        for elem in clickable_elements[
                                            :15
                                        ]:  # Check up to 15 elements
                                            try:
                                                text_content = await elem.text_content()
                                                if (
                                                    text_content
                                                    and text_content.strip()
                                                ):
                                                    clean_text = text_content.strip()
                                                    found_texts.append(clean_text)

                                                    # Case-insensitive match with variations
                                                    clean_text_lower = (
                                                        clean_text.lower()
                                                    )
                                                    for search_var in search_variations:
                                                        if (
                                                            search_var
                                                            in clean_text_lower
                                                            or clean_text_lower
                                                            in search_var
                                                        ):
                                                            await elem.click(
                                                                timeout=30000
                                                            )
                                                            text_click_success = True
                                                            op_result = f"Clicked element by flexible text match '{clean_text}' (searched for '{value}')"
                                                            break

                                                    if text_click_success:
                                                        break

                                            except Exception as elem_error:
                                                continue

                                        if not text_click_success and found_texts:
                                            logging.info(
                                                f"Available clickable text options: {found_texts[:10]}"
                                            )
                                            # Try one more approach - look for common login/auth patterns
                                            login_patterns = [
                                                "login",
                                                "log in",
                                                "sign in",
                                                "signin",
                                                "log-in",
                                                "sign-in",
                                                "auth",
                                                "register",
                                                "signup",
                                                "sign up",
                                            ]
                                            value_lower = value.lower()

                                            for pattern in login_patterns:
                                                if (
                                                    pattern in value_lower
                                                    or value_lower in pattern
                                                ):
                                                    for text in found_texts[:10]:
                                                        text_lower = text.lower()
                                                        if pattern in text_lower:
                                                            # Try to click this element
                                                            try:
                                                                pattern_locator = self.page.get_by_text(
                                                                    text, exact=True
                                                                )
                                                                pattern_count = (
                                                                    await pattern_locator.count()
                                                                )
                                                                if pattern_count >= 1:
                                                                    await pattern_locator.first.click(
                                                                        timeout=30000
                                                                    )
                                                                    text_click_success = (
                                                                        True
                                                                    )
                                                                    op_result = f"Clicked element by pattern match '{text}' (pattern: '{pattern}', searched for '{value}')"
                                                                    break
                                                            except Exception:
                                                                continue
                                                    if text_click_success:
                                                        break

                                    except Exception as case_insensitive_error:
                                        logging.warning(
                                            f"Flexible search failed: {case_insensitive_error}"
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
                            # If we have no selector and text click failed, that's an error
                            op_result = f"Error: Could not find clickable element with text '{value}' and no selector provided."
                            logging.error(op_result)
                        else:
                            op_result = await self.click_element_with_playwright(
                                current_selector
                            )  # Uses its own internal waits

                    # Only wait for page changes if the click was successful
                    if text_click_success or (
                        op_result and not op_result.startswith("Error:")
                    ):
                        # Wait for page potentially changing - use multiple strategies with shorter timeouts
                        try:
                            # Try networkidle first with short timeout
                            await self.page.wait_for_load_state(
                                "networkidle", timeout=2000
                            )
                        except Exception:
                            try:
                                # Fall back to load state
                                await self.page.wait_for_load_state(
                                    "load", timeout=3000
                                )
                            except Exception:
                                # Just wait for DOM to be ready
                                await self.page.wait_for_load_state(
                                    "domcontentloaded", timeout=2000
                                )

                        await self.page.wait_for_timeout(200)  # Small extra wait

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

                elif operation == "press":  # New operation to press keyboard keys
                    # 'value' contains the key to press (e.g., "Enter", "Escape", "Tab")
                    if not value:
                        raise ValueError(
                            "Press operation requires a key name in 'value' (e.g., 'Enter', 'Escape', 'Tab')."
                        )

                    # For Enter key, we expect navigation/page update - wait for it
                    if value.lower() == "enter":
                        try:
                            # Capture URL and content before pressing Enter
                            url_before_press = self.page.url
                            content_before_press = None
                            try:
                                content_before_press = await self.page.content()
                            except Exception:
                                pass

                            # Press Enter and wait for navigation or network idle
                            await self.page.keyboard.press(value)
                            logging.info("Pressed Enter, waiting for page to load...")

                            # Wait for either navigation or network to settle (whichever comes first)
                            try:
                                await self.page.wait_for_load_state(
                                    "networkidle", timeout=5000
                                )
                                logging.info("Network idle after Enter press")
                            except PlaywrightTimeoutError:
                                # If no network idle, at least wait for DOM to be ready
                                try:
                                    await self.page.wait_for_load_state(
                                        "domcontentloaded", timeout=3000
                                    )
                                    logging.info("DOM loaded after Enter press")
                                except PlaywrightTimeoutError:
                                    logging.info(
                                        "No clear load state change detected after Enter"
                                    )

                            # Additional wait to ensure content is rendered
                            await self.page.wait_for_timeout(
                                2000
                            )  # Increased from 1000 to 2000ms

                            # Check if URL or content actually changed
                            url_after_press = self.page.url
                            content_after_press = None
                            try:
                                content_after_press = await self.page.content()
                            except Exception:
                                pass

                            url_changed_after_press = (
                                url_after_press != url_before_press
                            )
                            content_changed_after_press = False
                            if content_before_press and content_after_press:
                                digest_before = hashlib.md5(
                                    content_before_press.encode("utf-8", "ignore")
                                ).hexdigest()
                                digest_after = hashlib.md5(
                                    content_after_press.encode("utf-8", "ignore")
                                ).hexdigest()
                                content_changed_after_press = (
                                    digest_before != digest_after
                                )

                            if url_changed_after_press or content_changed_after_press:
                                change_type = []
                                if url_changed_after_press:
                                    change_type.append(
                                        f"URL changed from {url_before_press} to {url_after_press}"
                                    )
                                if content_changed_after_press:
                                    change_type.append("content changed")
                                op_result = f"Pressed Enter and page updated ({', '.join(change_type)})"
                                logging.info(op_result)
                            else:
                                op_result = f"Pressed Enter (no detectable page changes after 2 second wait)"
                                logging.warning(op_result)

                        except Exception as press_error:
                            logging.warning(
                                f"Error during Enter press with navigation wait: {press_error}"
                            )
                            op_result = f"Pressed Enter (navigation wait issue: {str(press_error)})"
                    else:
                        # For other keys, just press and wait briefly
                        await self.page.keyboard.press(value)
                        op_result = f"Pressed key: {value}"
                        await self.page.wait_for_timeout(200)

                elif operation == "scrape_to_memory":
                    # Agent explicitly requests to scrape current page content into memory
                    # This is used when the agent needs detailed content for analysis/reference
                    if not self.ApiClient:
                        raise ValueError(
                            "Cannot scrape to memory: ApiClient unavailable"
                        )

                    try:
                        # Get current page content
                        page_content_to_scrape = await self.get_page_content()
                        if not page_content_to_scrape:
                            raise ValueError("No page content available to scrape")

                        content_length = len(page_content_to_scrape)
                        scrape_url = self.page.url if self.page else current_url

                        logging.info(
                            f"Agent requested scraping {scrape_url} into memory ({content_length} chars)"
                        )

                        # Use the browse_links pattern to scrape into memory
                        # Use _call_prompt_agent for reliable timeout handling
                        await self._call_prompt_agent(
                            timeout=90,  # Explicit timeout for scraping large pages
                            agent_name=self.agent_name,
                            prompt_name="Think About It",
                            prompt_args={
                                "user_input": f"{scrape_url} \n Scraping page content into memory for detailed analysis",
                                "websearch": False,
                                "analyze_user_input": False,
                                "disable_commands": True,
                                "log_user_input": False,
                                "log_output": False,
                                "browse_links": True,  # Triggers scrape_websites() flow
                                "tts": False,
                                "conversation_name": self.conversation_name,
                            },
                        )

                        op_result = f"Successfully scraped {content_length} characters from {scrape_url} into conversational memory"
                        logging.info(op_result)

                    except Exception as scrape_error:
                        raise Exception(f"Failed to scrape to memory: {scrape_error}")

                elif operation == "handle_mfa":
                    # Agent wants to handle MFA by scanning QR code and entering TOTP
                    # The 'selector' should be the OTP input field
                    # The 'value' can optionally be the submit button selector (defaults to button[type="submit"])
                    if not selector:
                        raise ValueError(
                            "handle_mfa requires a selector for the OTP input field"
                        )

                    submit_button = value if value else 'button[type="submit"]'
                    logging.info(
                        f"Attempting to handle MFA: OTP field={selector}, Submit button={submit_button}"
                    )

                    try:
                        mfa_result = await self.handle_mfa_with_playwright(
                            otp_selector=selector, submit_selector=submit_button
                        )

                        if "Error" in mfa_result:
                            raise Exception(mfa_result)

                        op_result = mfa_result
                        logging.info("MFA handling completed successfully")

                    except Exception as mfa_error:
                        raise Exception(
                            f"Failed to handle MFA: {type(mfa_error).__name__}"
                        )

                elif operation == "get_cookies":
                    # Agent wants to retrieve cookies from the current page
                    # Optional: If 'value' is provided, filter cookies by name (supports wildcards)
                    if self.page is None or self.page.is_closed():
                        raise ValueError("No page loaded to get cookies from")

                    try:
                        # Get all cookies from the current browser context
                        cookies = await self.context.cookies()

                        # If value is provided, use it as a filter (supports wildcards)
                        filter_pattern = value.strip() if value else None

                        if filter_pattern:
                            import fnmatch

                            filtered_cookies = [
                                c
                                for c in cookies
                                if fnmatch.fnmatch(c.get("name", ""), filter_pattern)
                            ]
                            cookies_to_report = filtered_cookies
                            filter_msg = f" (filtered by pattern: {filter_pattern})"
                        else:
                            cookies_to_report = cookies
                            filter_msg = ""

                        # Format cookies for readable output
                        if cookies_to_report:
                            cookie_details = []
                            for cookie in cookies_to_report:
                                details = f"  - {cookie['name']}={cookie['value']}"
                                if cookie.get("domain"):
                                    details += f" (domain: {cookie['domain']})"
                                if cookie.get("path"):
                                    details += f" (path: {cookie['path']})"
                                if cookie.get("httpOnly"):
                                    details += " [HttpOnly]"
                                if cookie.get("secure"):
                                    details += " [Secure]"
                                if cookie.get("sameSite"):
                                    details += f" [SameSite={cookie['sameSite']}]"
                                cookie_details.append(details)

                            op_result = (
                                f"Found {len(cookies_to_report)} cookie(s){filter_msg}:\n"
                                + "\n".join(cookie_details)
                            )
                        else:
                            op_result = f"No cookies found{filter_msg}"

                        logging.info(
                            f"Retrieved {len(cookies_to_report)} cookies from current page{filter_msg}"
                        )

                    except Exception as cookie_error:
                        raise Exception(f"Failed to get cookies: {cookie_error}")

                elif operation == "set_cookies":
                    # Agent wants to set one or more cookies on the current page
                    # The 'value' contains cookie data in format: name=value or JSON with full cookie details
                    if self.page is None or self.page.is_closed():
                        raise ValueError("No page loaded to set cookies on")

                    if not value:
                        raise ValueError("set_cookies requires cookie data in <value>")

                    try:
                        import json

                        cookies_to_set = []

                        # Try to parse as JSON first (for advanced cookie settings)
                        try:
                            cookie_data = json.loads(value)
                            # Support both single cookie object and array of cookies
                            if isinstance(cookie_data, dict):
                                cookies_to_set.append(cookie_data)
                            elif isinstance(cookie_data, list):
                                cookies_to_set.extend(cookie_data)
                            else:
                                raise ValueError(
                                    "JSON must be a cookie object or array of cookie objects"
                                )
                        except json.JSONDecodeError:
                            # Not JSON, parse as simple name=value format
                            # Support multiple cookies separated by semicolon
                            cookie_pairs = value.split(";")
                            current_domain = (
                                self.page.url.split("/")[2] if self.page else None
                            )

                            for pair in cookie_pairs:
                                pair = pair.strip()
                                if "=" in pair:
                                    name, val = pair.split("=", 1)
                                    cookie_obj = {
                                        "name": name.strip(),
                                        "value": val.strip(),
                                        "domain": current_domain,
                                        "path": "/",
                                    }
                                    cookies_to_set.append(cookie_obj)

                        if not cookies_to_set:
                            raise ValueError("No valid cookies to set")

                        # Set cookies in the browser context
                        await self.context.add_cookies(cookies_to_set)

                        # Format result message
                        cookie_names = [c["name"] for c in cookies_to_set]
                        op_result = f"Successfully set {len(cookies_to_set)} cookie(s): {', '.join(cookie_names)}"
                        logging.info(op_result)

                    except Exception as cookie_error:
                        raise Exception(f"Failed to set cookies: {cookie_error}")

                elif operation == "respond":
                    # Agent wants to communicate back to the user and exit
                    # The 'value' contains the message to return
                    response_msg = value if value else description
                    if not response_msg:
                        response_msg = "Task completed or encountered an issue."
                    op_result = f"AGENT_RESPONSE: {response_msg}"
                    success = True  # Mark as success to exit loop gracefully
                    # Set a flag so we can include this in the final output prominently
                    self._agent_response_message = response_msg

                elif operation == "done":
                    op_result = "Task marked as complete by plan."
                    success = True  # Mark as success to exit loop

                else:
                    raise ValueError(f"Unknown operation specified: {operation}")

                # Check if operation itself returned an error message
                if isinstance(op_result, str) and (
                    op_result.startswith(
                        "Error"
                    )  # Catch "Error clicking...", "Error: ...", etc.
                    or "failed" in op_result.lower()
                    or op_result.startswith("Warning")
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
                logging.info(
                    f"Step successful (Attempt {attempt}): {operation} completed"
                )

            except Exception as e:
                last_error = f"Error during {operation} on selector (Attempt {attempt}/{max_attempts}): {type(e).__name__}"
                logging.warning(last_error)
                if attempt >= max_attempts:  # If this was the last attempt
                    break  # Exit loop, failure will be handled below
                else:
                    # Optional: Wait before retrying
                    await self.page.wait_for_timeout(500)
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
                # Only generate summary if operation wasn't just getting content/fields or pressing keys
                # Note: Disabling summary for 'press' and 'scrape_to_memory' as they can cause hangs
                if operation not in [
                    "get_content",
                    "get_fields",
                    "screenshot",
                    "verify",
                    "wait",
                    "evaluate",
                    "done",
                    "press",  # skip summary for key presses to avoid hangs
                    "scrape_to_memory",  # skip summary - already scraping content, no need for additional summary
                ]:
                    try:
                        new_content = await self.get_page_content()  # Get fresh content
                    except Exception as content_error:
                        logging.warning(
                            f"Failed to get page content for summary: {content_error}"
                        )
                        new_content = "(Unable to retrieve page content)"

                    summary_prompt = f"""Analyze the current page state after successfully performing the operation '{operation}'.

Operation Result: {step_result_msg}
Previous URL: {current_url}
Current URL: {new_url}

Provide a concise summary including:
1. Key changes observed on the page (if any).
2. The main purpose/content of the current view.
3. Any immediately obvious next steps or calls to action.

Current Page Content Snippet (for context):
{new_content[:2000] if len(new_content) > 2000 else new_content}{'...' if len(new_content) > 2000 else ''}
"""
                    if self.ApiClient:
                        summary_timeout = getattr(
                            self,
                            "step_summary_timeout_seconds",
                            15,  # 15 seconds default
                        )
                        summary = await self._call_prompt_agent(
                            timeout=summary_timeout,
                            agent_name=self.agent_name,
                            prompt_name="User Input",  # Or a dedicated summarization prompt
                            prompt_args={
                                "user_input": summary_prompt,
                                "conversation_name": self.conversation_name,
                                "log_user_input": False,
                                "log_output": False,
                                "tts": False,
                                "analyze_user_input": False,
                                "running_command": "Interact with Webpage",
                                "browse_links": False,
                                "websearch": False,
                            },
                        )
                        logging.info("Generated page summary after successful step.")
            except Exception as summary_error:
                logging.error(f"Failed to generate page summary: {summary_error}")

            final_message = (
                f"[SUBACTIVITY][{self.activity_id}] Successfully completed: {operation}"
            )
            if selector:
                final_message += f" on '{selector}'"
            final_message += f"\nResult: {step_result_msg}\nStarted on: [{current_url}]\nEnded on: [{new_url}]"
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
                f"No valid <interaction> or <step> block found in response.\nResponse was:\n{response}"
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

        # Check if selector uses stable attributes
        # These are attributes that typically don't change during app lifecycle
        stable_attributes = [
            "id",
            "name",
            "data-testid",
            "aria-label",
            "placeholder",
            "type",
            "href",
            "role",
        ]

        # Check if selector contains any stable attributes
        has_stable_attribute = any(f"{attr}=" in selector for attr in stable_attributes)

        # Also accept simple ID selectors
        if selector.startswith("#"):
            has_stable_attribute = True

        if has_stable_attribute:
            # Additional check: make sure it doesn't use unstable patterns
            # Reject if it uses position-based selectors mixed with stable ones
            if (
                ":nth-child" in selector
                or ":first-child" in selector
                or ":last-child" in selector
            ):
                logging.warning(
                    f"Rejecting selector with position-based pseudo-classes: {selector}"
                )
                return False
            return True

        # If no stable attributes found, reject it
        logging.warning(
            f"Selector '{selector}' does not use stable attributes (id, name, data-testid, aria-label, placeholder, type, href, role)."
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

    def is_making_progress(self, attempt_history, window=10):
        """
        Determines if the automation is making meaningful progress.
        Looks for successful operations, URL changes, or other progress indicators.
        """
        if len(attempt_history) < window:
            return True  # Too early to judge, assume progress

        recent_attempts = attempt_history[-window:]

        # Count successful operations (those without error indicators)
        successful_ops = 0
        url_changes = 0

        for attempt in recent_attempts:
            # Count as successful if it doesn't contain error indicators
            if not any(
                error_word in attempt.lower()
                for error_word in ["error:", "failed", "exception:", "timeout"]
            ):
                successful_ops += 1

            # Check for URL changes (indicates navigation progress)
            if "ended on:" in attempt.lower() and "started on:" in attempt.lower():
                url_changes += 1

        # Consider it progress if we have some successful operations or URL changes
        progress_ratio = successful_ops / len(recent_attempts)
        return (
            progress_ratio > 0.3 or url_changes > 0
        )  # 30% success rate or any navigation

    def estimate_task_complexity(self, task: str) -> int:
        """
        Estimates task complexity based on keywords and returns suggested iteration budget.
        """
        task_lower = task.lower()

        # Complex task indicators
        complex_keywords = [
            "register",
            "registration",
            "sign up",
            "signup",
            "create account",
            "login",
            "log in",
            "authentication",
            "verify",
            "verification",
            "multi-step",
            "workflow",
            "form",
            "multiple pages",
            "navigation",
            "chat",
            "message",
            "conversation",
            "upload",
            "download",
            "search and",
            "find and",
            "extract and",
            "scrape and",
        ]

        # Count complexity indicators
        complexity_score = sum(
            1 for keyword in complex_keywords if keyword in task_lower
        )

        # Base complexity on word count too
        word_count = len(task.split())
        if word_count > 20:
            complexity_score += 2
        elif word_count > 10:
            complexity_score += 1

        # Return suggested iteration budget
        if complexity_score >= 4:
            return 50  # Very complex task
        elif complexity_score >= 2:
            return 35  # Moderately complex
        else:
            return 25  # Simple task

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

        Notes: If you need to search the web, use search.brave.com as the url.
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
                url=url, headless=True, timeout=30000  # 30 seconds timeout
            )
            if "Error" in nav_result:
                return f"Failed to start interaction: {nav_result}"
        except Exception as nav_error:
            return (
                f"Failed to initialize browser or navigate to starting URL: {nav_error}"
            )

        # Estimate task complexity and adjust iteration limit accordingly
        suggested_iterations = self.estimate_task_complexity(task)
        max_iterations = max(
            suggested_iterations, 50
        )  # Always allow at least 50, but increase if needed

        logging.info(
            f"Task complexity assessment: {suggested_iterations} iterations suggested, using {max_iterations} as limit"
        )

        iteration_count = 0
        results_summary = []  # User-facing summary of steps/results
        attempt_history = []  # Internal history for LLM planning context
        self._agent_response_message = None  # For 'respond' operation

        last_url = None
        max_runtime_seconds = getattr(
            self, "interaction_timeout_seconds", 300
        )  # 5 minutes default
        start_time = time.monotonic()
        last_step_signature = None
        stalled_plan_count = 0
        stalled_plan_threshold = 5
        last_observed_content_digest = None
        operation = ""

        while iteration_count < max_iterations:
            iteration_count += 1
            logging.info(
                f"--- Interaction Iteration {iteration_count}/{max_iterations} ---"
            )

            elapsed_seconds = time.monotonic() - start_time
            if elapsed_seconds > max_runtime_seconds:
                runtime_msg = f"Interaction stopped after {int(elapsed_seconds)} seconds without completion."
                logging.warning(runtime_msg)
                results_summary.append(
                    f"[Iteration {iteration_count}] Warning: {runtime_msg}"
                )
                attempt_history.append(
                    f"TIMEOUT Iteration {iteration_count}: exceeded {max_runtime_seconds} seconds"
                )
                if self.ApiClient:
                    self.ApiClient.new_conversation_message(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{self.activity_id}][WARNING] {runtime_msg}",
                        conversation_name=self.conversation_name,
                    )
                break

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
            content_changed_since_last = True
            current_content_digest = None

            try:
                current_page_content = await self.get_page_content()

                form_fields_info = await self.get_form_fields()
                if isinstance(form_fields_info, str):
                    logging.info(
                        "Form field summary length: %s characters",
                        len(form_fields_info),
                    )
                else:
                    logging.info("Form field summary unavailable or non-textual.")

                # Extract stable selectors and clickable link texts
                available_selectors = []
                clickable_link_texts = []
                if isinstance(form_fields_info, str):
                    for line in form_fields_info.split("\n"):
                        # Extract stable selectors
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

                        # Extract clickable link/button texts
                        if "(Can potentially be clicked by text:" in line:
                            text_match = re.search(r"clicked by text: '([^']+)'", line)
                            if text_match:
                                text = text_match.group(1).strip()
                                if (
                                    text
                                    and len(text) > 2
                                    and text not in clickable_link_texts
                                ):
                                    clickable_link_texts.append(text)
                else:
                    logging.warning("Could not parse form fields for stable selectors.")

                # ADDITIONALLY: Extract all clickable link texts from the page directly
                # This captures search results and other links that aren't in form_fields
                page_link_texts = await self.get_clickable_links()
                for link_text in page_link_texts:
                    if (
                        link_text
                        and len(link_text) > 2
                        and link_text not in clickable_link_texts
                    ):
                        clickable_link_texts.append(link_text)

                logging.info(
                    "Detected %d stable selectors and %d clickable texts for planning.",
                    len(available_selectors),
                    len(clickable_link_texts),
                )

                # Log what was actually detected (INFO level for visibility)
                if available_selectors:
                    logging.info(
                        f"Available selectors (first 10): {available_selectors[:10]}"
                    )
                if clickable_link_texts:
                    logging.info(
                        f"Clickable texts (first 10): {clickable_link_texts[:10]}"
                    )

                digest_source = current_page_content or ""
                if self.page and not self.page.is_closed():
                    try:
                        digest_source = await self.page.content()
                    except Exception as digest_error:
                        logging.debug(
                            f"Unable to capture raw page HTML for digest: {digest_error}"
                        )

                current_content_digest = hashlib.md5(
                    digest_source.encode("utf-8", "ignore")
                ).hexdigest()
                content_changed_since_last = (
                    last_observed_content_digest is None
                    or current_content_digest != last_observed_content_digest
                )

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
            # Check if last step was a fill operation - remind to press Enter
            # BUT only if we didn't already press Enter and navigate successfully
            last_action_reminder = ""
            if attempt_history:
                last_attempt = attempt_history[-1]
                # Check if last action was filling a field successfully
                if "fill|" in last_attempt.lower() and "SUCCESS" in last_attempt:
                    # Check if we haven't pressed Enter yet in the last 2 attempts
                    if not any(
                        "press|" in h.lower() and "enter" in h.lower()
                        for h in attempt_history[-2:]
                    ):
                        last_action_reminder = """
**CRITICAL REMINDER**: Your last action was FILLING a field. You MUST press Enter in this step to submit/search.
Do NOT fill another field or wait - press Enter NOW to trigger the action!
"""
                # Check if we just scraped content successfully
                elif (
                    "scrape_to_memory|" in last_attempt.lower()
                    and "SUCCESS" in last_attempt
                ):
                    # Count recent scrape operations
                    recent_scrapes = sum(
                        1
                        for h in attempt_history[-3:]
                        if "scrape_to_memory" in h.lower()
                    )
                    if recent_scrapes >= 1:
                        # Check if we're on a search results page (shallow content)
                        is_search_results = (
                            "search" in current_url.lower()
                            or "results" in current_url.lower()
                        )

                        if is_search_results:
                            last_action_reminder = """
**SEARCH RESULTS SCRAPED**: You scraped a search results page, which only contains snippets and links.
To provide detailed information to the user, you should:
1. CLICK on the TOP result or most relevant link to get the actual detailed content, OR
2. CLICK on the official website/documentation link for comprehensive information
3. After visiting and scraping a detailed page, THEN use 'respond' to provide your findings

Do NOT respond with just search snippets - click into actual content pages first!
"""
                        else:
                            last_action_reminder = """
**CONTENT ALREADY SCRAPED**: You have already scraped the current page content into memory. 
Do NOT scrape again - the content is already saved. Instead:
- Use 'respond' operation to provide your findings to the user, OR
- Click on another link to explore related content, OR
- Use 'done' to mark the task complete.
"""
                # If we just pressed Enter, check if page changed (URL or content)
                elif (
                    "press|" in last_attempt.lower()
                    and "enter" in last_attempt.lower()
                    and "SUCCESS" in last_attempt
                ):
                    # Check if URL changed OR content changed after pressing Enter
                    if url_changed or content_changed_since_last:
                        last_action_reminder = """
**PAGE UPDATED**: You successfully pressed Enter and the page content has changed (results loaded or navigated to new page).
Analyze the current content and decide your next action (e.g., click a search result, extract information, scrape content, etc.).
Do NOT press Enter again unless you're filling a new search box or form field.
"""
                    else:
                        # Pressing Enter but nothing changed - check if we're doing it repeatedly
                        recent_enter_presses = sum(
                            1
                            for h in attempt_history[-3:]
                            if "press|" in h.lower() and "enter" in h.lower()
                        )
                        if recent_enter_presses >= 2:
                            last_action_reminder = """
**WARNING**: You have pressed Enter multiple times but the page is NOT changing (same URL and content).
This means either:
1. The search results are already displayed - you should now CLICK on a search result link or SCRAPE the current page
2. The Enter key is not working on this element - try a different approach

Do NOT press Enter again! Instead, look for clickable links in the current page content and click one, or use scrape_to_memory to save the current page information.
"""

            planning_context = f"""You are an autonomous web interaction agent. Plan the *single next step* to accomplish the overall task.
{last_action_reminder}
OVERALL TASK: {task}

CURRENT STATE:
- Iteration: {iteration_count}/{max_iterations}
- Current URL: {current_url}
- URL Changed Since Last Step: {url_changed}
- Page Content: {len(current_page_content)} characters available (not in planning context for efficiency)

**NOTE**: Full page content is NOT included in planning context to keep it lean. Use `scrape_to_memory` operation if you need to save detailed page content to your conversational memory for later reference.

AVAILABLE STABLE SELECTORS (Prefer these):
{os.linesep.join([f'- {s}' for s in available_selectors]) if available_selectors else '- (No specific stable selectors detected, rely on standard attributes like name, type, placeholder or text content for clicks/verification)'}

CLICKABLE LINKS/BUTTONS BY TEXT (Use these EXACT texts in <value> for click operations):
{os.linesep.join([f'- "{text}"' for text in clickable_link_texts[:20]]) if clickable_link_texts else '- (No clickable text elements detected - consider using get_content to see page details, or use scrape_to_memory to analyze the page)'}

FORM FIELDS & INTERACTIVE ELEMENTS (Details for context):
{form_fields_info[:1500] + '...' if len(form_fields_info) > 1500 else form_fields_info}

PREVIOUS STEP ATTEMPTS & OUTCOMES (Recent history):
{os.linesep.join(attempt_history[-5:])}

RULES & INSTRUCTIONS FOR YOUR RESPONSE:
1.  Respond with ONLY a single XML block `<interaction><step>...</step></interaction>` wrapped in <answer> and </answer> tags.
2.  Define ONE operation: `click`, `fill`, `select`, `wait`, `verify`, `get_content`, `get_fields`, `evaluate`, `screenshot`, `download`, `extract_text`, `press`, `scrape_to_memory`, `handle_mfa`, `get_cookies`, `set_cookies`, `respond`, `done`.
3.  Use the `<selector>` tag with a stable selector (ID, name, data-testid, aria-label, placeholder, type, href). AVOID CLASS SELECTORS (like '.btn'). If no stable selector is obvious, describe the element and consider 'wait' or using text for clicks.
4.  For `click`: If clicking a button/link with visible text, put the EXACT text in the `<value>` tag. The system will try clicking by text first, then fall back to the selector if needed.
5.  For `fill`, `select`, `evaluate`: Put the text/value/script to use in the `<value>` tag.
6.  For `press`: Put the key name in `<value>` (e.g., "Enter", "Escape", "Tab", "ArrowDown"). Use this to submit forms or navigate with keyboard.
7.  **IMPORTANT**: After filling a search box, chat input, or form field, you MUST press Enter in the next step to submit/search. Don't just fill and wait - actively press Enter to trigger the action.
8.  For `scrape_to_memory`: Use this to save the current page's detailed content into your conversational memory for later reference. No selector/value needed. Use this when you need to deeply analyze content (articles, documentation, product details, etc.) or save information for the user. **IMPORTANT FOR SEARCH RESULTS**: If you're on a search results page:
    - First use `get_content` or `scrape_to_memory` to see the actual search results with their titles and URLs
    - Then identify a specific result link (by looking at the titles/descriptions in the content)
    - CLICK on that result by using its visible text in the <value> field (e.g., "GitHub - devxt/agixt" or "AGiXT Documentation")
    - Search results pages only have brief snippets - you need to click through to get detailed information
9.  For `handle_mfa`: Use this to automatically handle MFA by scanning a QR code on the current page and entering the generated TOTP code. Put the OTP input field selector in `<selector>` and optionally the submit button selector in `<value>` (defaults to 'button[type="submit"]'). This will: scan the page for a TOTP QR code, extract the secret, generate the current code, fill it in, and submit.
10. For `get_cookies`: Use this to retrieve all cookies from the current page. Optionally provide a filter pattern in `<value>` to match specific cookie names (supports wildcards like 'session*'). No selector needed. Useful for debugging authentication flows or checking session state.
11. For `set_cookies`: Use this to set cookies on the current page. Put cookie data in `<value>` as either 'name=value' (simple) or JSON with full details. Multiple cookies can be separated by semicolons. No selector needed. JSON format example: {{"name":"session","value":"abc123","domain":".example.com","path":"/","secure":true}}. Useful for setting auth tokens, session IDs, or testing cookie-based flows.
12. For `respond`: Use this to communicate back to the user and gracefully exit. Put your message in `<value>` explaining what you found, what worked, what failed, or why you're stopping. This is useful when encountering errors, completing part of the task, or needing to report findings. The user will see your message prominently and can decide on next steps.
13. For `wait`: Use `<selector>` for an element to wait for (e.g., `#results|visible`), OR put milliseconds in `<value>` (e.g., 2000).
14. For `verify`: Use `<selector>` for the element, and the text it should contain in `<value>`.
15. For `download`: Use `<selector>` for the trigger element (link/button), `<value>` for optional save path.
16. For `extract_text`: Use `<selector>` for the target image.
17. For `get_content` / `get_fields` / `get_cookies` / `set_cookies`: No selector needed, they operate on the current page.
18. Use `<description>` to explain WHY this step helps achieve the main task.
19. If the task is fully complete, use operation `done`.
20. COMPLEX TASKS: You have up to 50 iterations to complete multi-step workflows (registration, login, navigation, etc.). Break complex tasks into small atomic steps. Take your time and be methodical.
21. If stuck (e.g., element not found after waiting, repeated failures), use `respond` to explain the issue and suggest alternative approaches. The system has intelligent failure detection to prevent infinite loops.

EXAMPLE CLICKS:
<interaction><step><operation>click</operation><selector>button[data-testid='login-btn']</selector><value>Log In</value><description>Click the login button using its test ID and text.</description></step></interaction>
<interaction><step><operation>click</operation><selector>a[href='/about']</selector><value>About Us</value><description>Navigate to the About Us page using its link text.</description></step></interaction>

EXAMPLE FILL THEN PRESS (IMPORTANT PATTERN):
<interaction><step><operation>fill</operation><selector>input[name='q']</selector><value>AGiXT</value><description>Fill the search box with query.</description></step></interaction>
Then next step MUST be:
<interaction><step><operation>press</operation><selector></selector><value>Enter</value><description>Press Enter to submit the search.</description></step></interaction>

EXAMPLE FILL (single field):
<interaction><step><operation>fill</operation><selector>input[name='username']</selector><value>my_user</value><description>Fill the username field.</description></step></interaction>

EXAMPLE PRESS:
<interaction><step><operation>press</operation><selector></selector><value>Enter</value><description>Press Enter key to submit the search form.</description></step></interaction>

EXAMPLE SCRAPE TO MEMORY (save detailed content):
<interaction><step><operation>scrape_to_memory</operation><selector></selector><value></value><description>Scrape the GitHub repository README and details into memory for detailed analysis.</description></step></interaction>
<interaction><step><operation>scrape_to_memory</operation><selector></selector><value></value><description>Save this article content to memory so I can reference it when answering questions.</description></step></interaction>

EXAMPLE HANDLE MFA (scan QR code and enter TOTP):
<interaction><step><operation>handle_mfa</operation><selector>input[name='mfa_token']</selector><value></value><description>Scan the QR code on the page and automatically enter the generated TOTP code into the MFA field, then submit.</description></step></interaction>
<interaction><step><operation>handle_mfa</operation><selector>input[id='otp-input']</selector><value>button[id='verify-button']</value><description>Handle MFA by scanning QR code, entering TOTP, and clicking the custom verify button.</description></step></interaction>

EXAMPLE GET COOKIES (retrieve page cookies):
<interaction><step><operation>get_cookies</operation><selector></selector><value></value><description>Get all cookies from the current page to check authentication state.</description></step></interaction>
<interaction><step><operation>get_cookies</operation><selector></selector><value>session*</value><description>Get all session-related cookies (matching pattern 'session*') to debug login issues.</description></step></interaction>
<interaction><step><operation>get_cookies</operation><selector></selector><value>auth_token</value><description>Check if the auth_token cookie is set after login.</description></step></interaction>

EXAMPLE SET COOKIES (set page cookies):
<interaction><step><operation>set_cookies</operation><selector></selector><value>session_id=abc123; user_token=xyz789</value><description>Set session and auth cookies for testing authenticated flows.</description></step></interaction>
<interaction><step><operation>set_cookies</operation><selector></selector><value>auth_token=my_test_token</value><description>Set a single auth token cookie to bypass login.</description></step></interaction>
<interaction><step><operation>set_cookies</operation><selector></selector><value>[{{"name":"session","value":"abc123","domain":".example.com","path":"/","secure":true,"httpOnly":true}}]</value><description>Set a secure session cookie with full control over attributes using JSON format.</description></step></interaction>

EXAMPLE RESPOND (report back to user and exit):
<interaction><step><operation>respond</operation><selector></selector><value>I successfully searched for AGiXT on DuckDuckGo and found 10 results. The top result is the official GitHub repository at github.com/Josh-XT/AGiXT. Would you like me to click on a specific result or perform another action?</value><description>Report findings to user and await further instructions.</description></step></interaction>
<interaction><step><operation>respond</operation><selector></selector><value>I encountered an error: the login button could not be found after 3 attempts. The page may have changed its structure. I recommend trying a different selector or verifying the page URL is correct.</value><description>Report error to user with helpful context.</description></step></interaction>

EXAMPLE WAIT:
<interaction><step><operation>wait</operation><selector>#results-table|visible</selector><value></value><description>Wait for the results table to become visible.</description></step></interaction>

NOW, PROVIDE THE XML FOR THE NEXT STEP:
"""

            # --- 2.5 Plan with Retry Logic for XML Parsing ---
            max_plan_attempts = 3
            plan_attempt = 0
            parsed_step = None
            last_parse_error = None

            while plan_attempt < max_plan_attempts and parsed_step is None:
                plan_attempt += 1
                try:
                    # Set timeout to 90 seconds to handle typical LLM response times (30-60s)
                    # This prevents indefinite hangs while being generous enough for slow responses
                    plan_timeout = getattr(
                        self, "plan_step_timeout_seconds", 90
                    )  # 90 seconds default

                    # Adjust prompt for retry attempts
                    current_planning_context = planning_context
                    if plan_attempt > 1:
                        current_planning_context = f"""IMPORTANT: Your previous response had invalid XML formatting. 
You MUST respond with ONLY valid XML following this exact structure:

<answer>
<interaction>
<step>
<operation>operation_name</operation>
<selector>css_selector_or_empty</selector>
<value>value_or_empty</value>
<description>brief description</description>
</step>
</interaction>
</answer>

Do NOT include any text before or after the XML block. Do NOT use markdown code blocks.

Previous error: {last_parse_error}

{planning_context}"""

                    logging.info(
                        "Requesting LLM plan for iteration %d (attempt %d/%d, timeout %ss)...",
                        iteration_count,
                        plan_attempt,
                        max_plan_attempts,
                        plan_timeout,
                    )

                    # Log a snippet of the planning context (INFO level)
                    context_lines = current_planning_context.split("\n")
                    # Show task, current state, and the clickable texts section
                    important_lines = []
                    capture = False
                    for line in context_lines[
                        :50
                    ]:  # First 50 lines should cover what we need
                        if (
                            "OVERALL TASK:" in line
                            or "CURRENT STATE:" in line
                            or "CLICKABLE LINKS/BUTTONS BY TEXT" in line
                        ):
                            capture = True
                        if capture:
                            important_lines.append(line)
                            if "FORM FIELDS" in line:  # Stop before form fields
                                break
                    logging.info(
                        f"Planning context key sections extracted: {len(important_lines[:30])} lines"
                    )

                    logging.debug(
                        f"About to await _call_prompt_agent for iteration {iteration_count}..."
                    )
                    raw_plan = await self._call_prompt_agent(
                        timeout=plan_timeout,
                        agent_name=self.agent_name,
                        prompt_name="User Input",
                        prompt_args={
                            "user_input": current_planning_context,
                            "conversation_name": self.conversation_name,
                            "log_user_input": False,
                            "log_output": False,
                            "tts": False,
                            "analyze_user_input": False,
                            "running_command": "Interact with Webpage",
                            "browse_links": False,
                            "websearch": False,
                        },
                    )
                    logging.debug(
                        f"Returned from await _call_prompt_agent for iteration {iteration_count}"
                    )
                    logging.info(
                        "Received plan response for iteration %d (attempt %d).",
                        iteration_count,
                        plan_attempt,
                    )

                    if not raw_plan or not isinstance(raw_plan, str):
                        raise ValueError("LLM did not return a valid plan string.")

                    # --- 3. Parse and Validate Step ---
                    interaction_xml = self.extract_interaction_block(raw_plan)
                    root = ET.fromstring(interaction_xml)
                    steps = root.findall(".//step")

                    if not steps:
                        raise ValueError(
                            f"Parsed XML does not contain a <step> element.\nResponse was:\n{raw_plan}"
                        )

                    parsed_step = steps[0]  # Process only the first step per iteration
                    logging.info(
                        "Successfully parsed step on attempt %d/%d",
                        plan_attempt,
                        max_plan_attempts,
                    )

                except (ET.ParseError, ValueError) as parse_error:
                    last_parse_error = str(parse_error)
                    logging.warning(
                        "Failed to parse plan on attempt %d/%d: %s",
                        plan_attempt,
                        max_plan_attempts,
                        last_parse_error,
                    )
                    if plan_attempt >= max_plan_attempts:
                        # Final attempt failed - give up on this iteration
                        raise ValueError(
                            f"Failed to parse valid XML after {max_plan_attempts} attempts. "
                            f"Last error: {last_parse_error}"
                            f"\nLast response was:\n{raw_plan}"
                        )
                    # Otherwise, loop will retry with corrective prompt
                except (TimeoutError, asyncio.TimeoutError) as timeout_error:
                    last_parse_error = f"LLM timeout: {timeout_error}"
                    logging.error(
                        "LLM planning timed out on attempt %d/%d: %s",
                        plan_attempt,
                        max_plan_attempts,
                        timeout_error,
                    )
                    if plan_attempt >= max_plan_attempts:
                        # All attempts timed out
                        raise TimeoutError(
                            f"LLM planning timed out after {max_plan_attempts} attempts ({plan_timeout}s each). "
                            f"The AI service may be overloaded or stuck."
                        )
                    # Otherwise, retry after brief pause
                    logging.info("Waiting 3 seconds before retry...")
                    await asyncio.sleep(3)

            if parsed_step is None:
                raise ValueError("Failed to obtain a valid parsed step after retries.")

            step = parsed_step

            # Continue with validation and execution wrapped in try block
            try:
                operation = self.safe_get_text(step.find("operation")).lower()
                selector = self.safe_get_text(step.find("selector"))
                value = self.safe_get_text(step.find("value"))
                description = self.safe_get_text(step.find("description"))

                # Sanitize selector to fix common LLM mistakes
                if selector:
                    # Remove trailing } that LLMs sometimes add (e.g., textarea[aria-label='Search']})
                    if selector.endswith("}") and not selector.endswith("]}"):
                        selector = selector[:-1]
                        logging.warning(
                            f"Removed trailing '}}' from selector: now '{selector}'"
                        )

                    # Remove leading { that LLMs sometimes add
                    if selector.startswith("{") and not selector.startswith("{["):
                        selector = selector[1:]
                        logging.warning(
                            f"Removed leading '{{' from selector: now '{selector}'"
                        )

                    # Strip any extra whitespace
                    selector = selector.strip()

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
                    "respond",
                    "get_content",
                    "get_fields",
                    "evaluate",
                    "screenshot",
                    "download",
                    "extract_text",
                    "press",
                    "scrape_to_memory",
                    "handle_mfa",
                    "get_cookies",
                    "set_cookies",
                ]:
                    raise ValueError(f"Invalid operation '{operation}' planned.")

                # Validate selector stability (unless not needed for the operation)
                if (
                    operation
                    not in [
                        "wait",
                        "done",
                        "respond",
                        "evaluate",
                        "get_content",
                        "get_fields",
                        "press",
                        "scrape_to_memory",
                        "get_cookies",
                        "set_cookies",
                    ]
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

                # Check if agent responded to user (also indicates completion)
                if operation == "respond":
                    logging.info(
                        f"Agent responded to user, task complete. Response: {value[:100] if value else description[:100]}..."
                    )
                    results_summary.append(
                        f"[Iteration {iteration_count}] Agent provided response to user."
                    )
                    break  # Exit the main loop

                step_signature = (operation, selector or "", value or "")
                repeated_plan = step_signature == last_step_signature

                # Operations that don't change page state but are still valid/completion actions
                # These should have a higher tolerance or skip stall detection
                non_changing_valid_ops = {
                    "wait",
                    "get_content",
                    "get_fields",
                    "scrape_to_memory",
                    "get_cookies",
                    "screenshot",
                    "download",
                }

                dynamic_stall_threshold = (
                    stalled_plan_threshold + 3
                    if operation in non_changing_valid_ops
                    else stalled_plan_threshold
                )

                # Check if the PREVIOUS step reported a successful page change
                # (This is important for Enter key presses that navigate but we haven't detected yet)
                previous_step_changed_page = False
                if attempt_history:
                    last_attempt = attempt_history[-1]
                    # Check if last step reported page changes in its result
                    if any(
                        indicator in last_attempt.lower()
                        for indicator in [
                            "page updated",
                            "url changed",
                            "content changed",
                            "navigated to",
                        ]
                    ):
                        previous_step_changed_page = True

                # Check if operation completed successfully (even if page didn't change)
                operation_completed_successfully = False
                if attempt_history:
                    last_attempt = attempt_history[-1]
                    if any(
                        indicator in last_attempt.lower()
                        for indicator in [
                            "success",
                            "completed",
                            "scraped",
                            "retrieved",
                            "downloaded",
                        ]
                    ):
                        operation_completed_successfully = True

                if (
                    repeated_plan
                    and not content_changed_since_last
                    and not url_changed
                    and not previous_step_changed_page
                    and not operation_completed_successfully  # Don't stall if operation succeeded
                ):
                    stalled_plan_count += 1
                else:
                    stalled_plan_count = 0

                if stalled_plan_count >= dynamic_stall_threshold:
                    stall_msg = (
                        f"No page changes detected after repeating '{operation}' {stalled_plan_count} times."
                        " Stopping to prevent the workflow from hanging."
                    )
                    logging.warning(stall_msg)
                    results_summary.append(
                        f"[Iteration {iteration_count}] Warning: {stall_msg}"
                    )
                    attempt_history.append(
                        f"STALLED Iteration {iteration_count}: {operation}|{selector}|{value}"
                    )
                    if self.ApiClient:
                        self.ApiClient.new_conversation_message(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{self.activity_id}][WARNING] {stall_msg}",
                            conversation_name=self.conversation_name,
                        )
                    break

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

                # Check if we're making progress - allow more iterations if we are
                if (
                    iteration_count > 25
                ):  # Only start checking progress after reasonable number of steps
                    if not self.is_making_progress(attempt_history):
                        error_msg = f"No meaningful progress detected in recent iterations. Task may be too complex or have encountered insurmountable obstacles."
                        logging.warning(error_msg)
                        results_summary.append(
                            f"[Iteration {iteration_count}] Warning: {error_msg}"
                        )
                        if self.ApiClient:
                            self.ApiClient.new_conversation_message(
                                role=self.agent_name,
                                message=f"[SUBACTIVITY][{self.activity_id}][WARNING] {error_msg}",
                                conversation_name=self.conversation_name,
                            )
                        # Don't break immediately - give it a few more chances
                        if (
                            iteration_count > 35
                        ):  # More aggressive stopping if still no progress
                            break

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

                last_step_signature = step_signature

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

            finally:
                if current_content_digest is not None:
                    last_observed_content_digest = current_content_digest

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
        # If agent used 'respond' operation, prioritize that message
        if self._agent_response_message:
            final_output = f"**Agent Response**: {self._agent_response_message}\n\n"
            final_output += (
                f"Web interaction task '{task}' finished.\nSummary of actions:\n"
            )
            final_output += "\n".join(results_summary)
        else:
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
        if BeautifulSoup is None:
            return "Error: BeautifulSoup is not available. Please install beautifulsoup4 to parse page content."

        logging.info("Retrieving and structuring page content...")
        try:
            # Add timeout to page.content() call to prevent hanging on large/complex pages
            try:
                html_content = await asyncio.wait_for(self.page.content(), timeout=30.0)
            except asyncio.TimeoutError:
                logging.warning(
                    "Page content retrieval timed out after 30s, using fallback method"
                )
                # Fallback: try to get just the body text
                html_content = await self.page.evaluate("() => document.body.innerHTML")

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
            analysis_timeout = getattr(self, "visual_analysis_timeout_seconds", 120)
            analysis_result = await self._call_prompt_agent(
                timeout=analysis_timeout,
                agent_name=self.agent_name,
                prompt_name="User Input",
                prompt_args={
                    "user_input": analysis_prompt,
                    "images": [image_ref],  # Pass image URL or path
                    "log_user_input": False,
                    "running_command": "Interact with Webpage",
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

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensure cleanup"""
        await self.close_browser()

    async def ensure_cleanup(self):
        """Ensure all resources are cleaned up"""
        if self._cleanup_attempted:
            return  # Already cleaned up

        self._cleanup_attempted = True
        try:
            if hasattr(self, "page") and self.page and not self.page.is_closed():
                await self.page.close()
            if hasattr(self, "context") and self.context:
                await self.context.close()
            if (
                hasattr(self, "browser")
                and self.browser
                and self.browser.is_connected()
            ):
                await self.browser.close()
            if hasattr(self, "playwright") and self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logging.error(f"Error during web browsing cleanup: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None

    async def search_arxiv(self, query: str, max_articles: int = 5):
        """
        Search for articles on arXiv and learn from them

        Args:
        query (str): The search query
        max_articles (int): The maximum number of articles to read

        Returns:
        str: Success message
        """
        return self.ApiClient.learn_arxiv(
            query=query,
            article_ids=None,
            max_articles=max_articles,
            collection_number="0",
        )
